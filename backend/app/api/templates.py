"""Template endpoints used by the Templates page and Template Studio.

Reading templates is open to every signed-in user; changing them is admin-only and
audited. Page images are served through this authenticated API, never as static files.
"""
from __future__ import annotations

import io
import json
from typing import Any

import cv2
import numpy as np
from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response
from pydantic import ValidationError

from app.api.deps import DB, AdminUser, CurrentUser, client_ip
from app.services import audit
from app.services.preprocessing.pipeline import preprocess
from app.services.preprocessing.steps import decode_image_bytes, rasterize_pdf_bytes
from app.services.storage.files import UploadRejected, validate_upload
from app.services.template import store, yolo_io
from app.services.template.identify import identify
from app.services.template.registry import discover_templates
from app.services.template.schema import Template, load_template, load_vocabulary, template_path

router = APIRouter(tags=["templates"])


def _load(tid: str) -> Template:
    if not template_path(tid).exists():
        raise HTTPException(status_code=404, detail="Template not enrolled")
    try:
        return load_template(tid)
    except (ValueError, ValidationError) as exc:
        raise HTTPException(status_code=500, detail=f"template.json is invalid: {exc}") from None


@router.get("/fields")
def vocabulary(_: CurrentUser) -> dict[str, Any]:
    v = load_vocabulary()
    return {"version": v.version, "train_priorities": v.train_priorities, "sections": v.sections,
            "fields": [f.model_dump() for f in v.fields], "yolo_classes": v.yolo_classes()}


@router.get("/templates")
def list_templates(_: CurrentUser) -> list[dict[str, Any]]:
    out = []
    for info in discover_templates():
        item: dict[str, Any] = {"template_id": info.template_id, "bank_name": info.bank_name, "role": info.role,
                                "page_count": len(info.pages), "enrolled": info.has_template_json,
                                "enrollment_status": None, "region_count": 0, "approved_regions": 0}
        if info.has_template_json:
            try:
                t = load_template(info.template_id)
                item.update(enrollment_status=t.enrollment.status, region_count=len(t.regions),
                            approved_regions=sum(r.review_status == "approved" for r in t.regions),
                            form_name=t.form_name, role=t.role)
            except (ValueError, ValidationError):
                item["enrollment_status"] = "invalid"
        out.append(item)
    return out


@router.get("/templates/{tid}")
def get_template(tid: str, _: CurrentUser) -> dict[str, Any]:
    t = _load(tid)
    return {**t.model_dump(mode="json"), "sha256": store.template_sha(t)}


@router.put("/templates/{tid}")
def save_template(tid: str, body: dict[str, Any], admin: AdminUser, db: DB, request: Request,
                  base_sha256: str | None = Query(default=None)) -> dict[str, Any]:
    current = _load(tid)
    if base_sha256 and base_sha256 != store.template_sha(current):
        raise HTTPException(status_code=409, detail="The template changed since you opened it. Reload and re-apply your edits.")
    try:
        t = Template.model_validate(body)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=json.loads(exc.json())) from None
    if t.template_id != tid:
        raise HTTPException(status_code=400, detail="template_id cannot be changed")
    unknown = t.check_against(load_vocabulary())
    if unknown:
        raise HTTPException(status_code=422, detail=f"Unknown field ids: {unknown}")
    if [p.model_dump() for p in t.pages] != [p.model_dump() for p in current.pages]:
        raise HTTPException(status_code=400, detail="Pages are defined by the rasterized source and cannot be edited here")
    if current.enrollment.status == "approved" and t.enrollment.status == "approved":
        # Any edit to an approved template sends it back for review.
        t.enrollment.status = "proposed"
    store.save_and_sync(db, t)
    audit.record(db, "template.save", user_id=admin.id, entity_type="template", entity_id=tid,
                 details={"regions": len(t.regions)}, ip_address=client_ip(request))
    return {**t.model_dump(mode="json"), "sha256": store.template_sha(t)}


@router.post("/templates/{tid}/approve")
def approve_template(tid: str, admin: AdminUser, db: DB, request: Request) -> dict[str, Any]:
    t = store.approve(db, _load(tid), admin.username)
    audit.record(db, "template.approve", user_id=admin.id, entity_type="template", entity_id=tid,
                 details={"regions": len(t.regions)}, ip_address=client_ip(request))
    return {**t.model_dump(mode="json"), "sha256": store.template_sha(t)}


@router.get("/templates/{tid}/pages/{page}/image")
def page_image(tid: str, page: int, _: CurrentUser, width: int | None = Query(default=None, ge=200, le=4000)) -> Response:
    info = next((i for i in discover_templates() if i.template_id == tid), None)
    ref = next((p for p in info.pages if p.page_number == page), None) if info else None
    if ref is None:
        raise HTTPException(status_code=404, detail="Page not found")
    img = cv2.imread(str(ref.image_path))
    if width and width < img.shape[1]:
        img = cv2.resize(img, (width, round(img.shape[0] * width / img.shape[1])), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 88])
    return Response(content=buf.tobytes(), media_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"})


@router.get("/templates/{tid}/export/yolo")
def export_yolo(tid: str, _: CurrentUser) -> Response:
    data = yolo_io.export_zip(_load(tid), load_vocabulary())
    return Response(content=data, media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{tid}_yolo_labels.zip"'})


@router.post("/templates/{tid}/import/yolo")
async def import_yolo(tid: str, admin: AdminUser, db: DB, request: Request, page: int = Query(ge=1),
                      file: UploadFile = File(...), replace: bool = True) -> dict[str, Any]:
    t = _load(tid)
    if page not in {p.page_number for p in t.pages}:
        raise HTTPException(status_code=404, detail="Page not found")
    raw = await file.read(2_000_000)
    try:
        n = yolo_io.import_page_labels(t, page, raw.decode("utf-8"), load_vocabulary(), replace=replace)
    except (ValueError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    t.enrollment.status = "proposed"
    store.save_and_sync(db, t)
    audit.record(db, "template.import_yolo", user_id=admin.id, entity_type="template", entity_id=tid,
                 details={"page": page, "regions": n}, ip_address=client_ip(request))
    return {"imported": n}


@router.post("/templates/identify-test")
async def identify_test(_: CurrentUser, file: UploadFile = File(...)) -> dict[str, Any]:
    """Run preprocessing + identification on an uploaded page (not stored)."""
    data = await file.read()
    try:
        media, _ext = validate_upload(data, file.filename)
    except UploadRejected as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from None
    img = rasterize_pdf_bytes(data, max_pages=1)[0] if media == "application/pdf" else decode_image_bytes(data)
    pre = preprocess(img)
    res = identify(pre.image)
    return {"identification": {k: v for k, v in res.to_dict().items() if k != "homography"},
            "preprocessing": [{"name": s.name, "applied": s.applied, "ms": s.ms} for s in pre.steps]}
