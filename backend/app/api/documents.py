"""Documents API: upload, process, list, detail, stage manifests, files, lab re-run,
field edit/verify, search, export, dashboard statistics.

All values returned come from the database or from files produced by the pipeline.
Uploaded and derived images are served only through this authenticated API.
"""
from __future__ import annotations

import csv
import io
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select

from app.api.deps import DB, CurrentUser, client_ip
from app.core.config import get_settings
from app.models import (Document, DocumentStatus, ExtractedField, FieldEdit, FieldStatus, FormTemplate, Page,
                        ProcessingJob)
from app.models.base import utcnow
from app.services import audit
from app.services.extraction.vision import DEFAULT_PARAMS, lab_rerun
from app.services.preprocessing.steps import decode_image_bytes, rasterize_pdf_bytes
from app.services.quality.page_check import check_page
from app.services.storage.files import UploadRejected, open_stored, resolve_inside, save_upload, validate_upload
from app.services.template.schema import load_vocabulary
from app.workers import jobs as job_queue
from app.workers.document_job import stage_dir

router = APIRouter(tags=["documents"])


# --------------------------------------------------------------------------- helpers


def _doc(db, doc_id: int) -> Document:  # noqa: ANN001
    d = db.get(Document, doc_id)
    if d is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return d


def _field_out(f: ExtractedField, vocab: dict) -> dict[str, Any]:
    fd = vocab.get(f.field_id)
    extra = f.extra or {}
    return {
        "id": f.id, "field_id": f.field_id, "display_name": fd.display_name if fd else f.field_id,
        "section": fd.section if fd else "other", "field_type": fd.field_type if fd else "text",
        "priority": fd.priority if fd else None, "group_id": f.group_id, "row_index": f.row_index,
        "applicant_index": f.applicant_index, "page_id": f.page_id, "region_id": extra.get("region_id"),
        "raw_text": f.raw_text, "normalized_value": f.normalized_value,
        "detection_confidence": f.detection_confidence, "ocr_confidence": f.ocr_confidence, "engine": f.engine,
        "status": f.status.value, "validation_messages": f.validation_messages or [], "crop_path": f.crop_path,
        "checkbox": extra.get("checkbox"), "ocr_raw": extra.get("ocr_raw"), "ink": extra.get("ink"), "bbox": extra.get("bbox"),
        "verified_by": f.verified_by, "verified_at": f.verified_at,
    }


def _doc_summary(d: Document, db) -> dict[str, Any]:  # noqa: ANN001
    counts = dict(db.execute(select(ExtractedField.status, func.count()).where(ExtractedField.document_id == d.id)
                             .group_by(ExtractedField.status)).all())
    avg = db.execute(select(func.avg(ExtractedField.ocr_confidence)).where(
        ExtractedField.document_id == d.id, ExtractedField.ocr_confidence.is_not(None))).scalar()
    return {"id": d.id, "public_id": d.public_id, "display_name": d.display_name, "status": d.status.value,
            "template_id": d.template.template_id if d.template else None,
            "bank_name": d.template.bank_name if d.template else None,
            "template_confidence": d.template_confidence, "page_count": len(d.pages),
            "created_at": d.created_at, "processing_seconds": d.processing_seconds,
            "field_counts": {k.value: v for k, v in counts.items()},
            "avg_ocr_confidence": None if avg is None else round(float(avg), 4)}


# --------------------------------------------------------------------------- upload / process


@router.post("/documents", status_code=201)
async def upload(request: Request, user: CurrentUser, db: DB, files: list[UploadFile] = File(...),
                 name: str | None = Query(default=None, max_length=200), process: bool = True) -> dict[str, Any]:
    """Upload 1..N images or PDFs as one document (in the given order) and queue processing."""
    s = get_settings()
    blobs = []
    for f in files:
        data = await f.read()
        try:
            media, _ = validate_upload(data, f.filename)
        except UploadRejected as exc:
            raise HTTPException(status_code=415, detail=f"{f.filename}: {exc}") from None
        blobs.append((f.filename, data, media))
    public_id = uuid.uuid4().hex
    pages: list[tuple[str, bytes]] = []
    for fname, data, media in blobs:
        if media == "application/pdf":
            import cv2

            try:
                imgs = rasterize_pdf_bytes(data, dpi=200, max_pages=s.max_pages_per_document)
            except Exception:  # noqa: BLE001
                raise HTTPException(status_code=415, detail=f"{fname}: the PDF could not be read") from None
            for k, img in enumerate(imgs, start=1):
                ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 92])
                pages.append((f"{fname}#page{k}.jpg", buf.tobytes()))
        else:
            pages.append((fname, data))
    if not pages:
        raise HTTPException(status_code=422, detail="No pages found")
    if len(pages) > s.max_pages_per_document:
        raise HTTPException(status_code=413, detail=f"At most {s.max_pages_per_document} pages per document")
    doc = Document(public_id=public_id, display_name=(name or blobs[0][0] or "document")[:200], uploaded_by=user.id)
    db.add(doc)
    db.flush()
    warnings_out = []
    for i, (fname, data) in enumerate(pages):
        stored = save_upload(public_id, data, fname)
        img = decode_image_bytes(data)
        q = check_page(img)
        db.add(Page(document_id=doc.id, order_index=i, original_path=stored.relative_path,
                    original_filename=stored.original_filename, width_px=img.shape[1], height_px=img.shape[0],
                    quality=q.metrics, quality_warnings=q.warnings))
        warnings_out.append({"page": i + 1, "filename": stored.original_filename, "warnings": q.warnings,
                             "codes": q.codes, "metrics": q.metrics})
    db.commit()
    audit.record(db, "document.upload", user_id=user.id, entity_type="document", entity_id=doc.id,
                 details={"pages": len(pages)}, ip_address=client_ip(request))
    job_id = job_queue.enqueue("process_document", {}, document_id=doc.id, created_by=user.id) if process else None
    return {"document_id": doc.id, "job_id": job_id, "pages": warnings_out}


@router.post("/documents/{doc_id}/process")
def reprocess(doc_id: int, user: CurrentUser, db: DB, request: Request, body: dict | None = None) -> dict[str, Any]:
    _doc(db, doc_id)
    jid = job_queue.enqueue("process_document", {"vision_params": (body or {}).get("params")},
                            document_id=doc_id, created_by=user.id)
    audit.record(db, "document.reprocess", user_id=user.id, entity_type="document", entity_id=doc_id,
                 ip_address=client_ip(request))
    return {"job_id": jid}


# --------------------------------------------------------------------------- read


@router.get("/documents")
def list_documents(_: CurrentUser, db: DB, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
                   status: DocumentStatus | None = None, template: str | None = None, q: str | None = None,
                   sort: str = Query("-created_at", pattern=r"^-?(created_at|display_name|status|processing_seconds)$")
                   ) -> dict[str, Any]:
    stmt = select(Document)
    if status:
        stmt = stmt.where(Document.status == status)
    if template:
        stmt = stmt.join(FormTemplate, Document.template_id == FormTemplate.id).where(FormTemplate.template_id == template)
    if q:
        stmt = stmt.where(Document.display_name.ilike(f"%{q}%"))
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    col = getattr(Document, sort.lstrip("-"))
    stmt = stmt.order_by(col.desc() if sort.startswith("-") else col.asc(), Document.id.desc())
    rows = db.execute(stmt.offset((page - 1) * page_size).limit(page_size)).scalars().all()
    return {"items": [_doc_summary(d, db) for d in rows], "total": total, "page": page, "page_size": page_size}


@router.get("/documents/{doc_id}")
def document_detail(doc_id: int, _: CurrentUser, db: DB) -> dict[str, Any]:
    d = _doc(db, doc_id)
    vocab = load_vocabulary().by_id()
    fields = db.execute(select(ExtractedField).where(ExtractedField.document_id == doc_id)
                        .order_by(ExtractedField.page_id, ExtractedField.id)).scalars().all()
    jobs = db.execute(select(ProcessingJob).where(ProcessingJob.document_id == doc_id)
                      .order_by(ProcessingJob.id.desc())).scalars().all()
    pages = []
    for p in d.pages:
        man = stage_dir(d.public_id, p.order_index) / "manifest.json"
        ident = None
        if man.exists():
            ident = json.loads(man.read_text(encoding="utf-8")).get("identification")
        pages.append({"id": p.id, "index": p.order_index, "original_filename": p.original_filename,
                      "original_path": p.original_path, "processed_path": p.processed_path,
                      "width": p.width_px, "height": p.height_px, "quality": p.quality,
                      "quality_warnings": p.quality_warnings or [], "template_page_number": p.template_page_number,
                      "registration_confidence": p.registration_confidence, "identification": ident,
                      "has_stages": man.exists()})
    return {**_doc_summary(d, db), "pages": pages, "fields": [_field_out(f, vocab) for f in fields],
            "jobs": [{"id": j.id, "status": j.status.value, "progress": j.progress, "message": j.message,
                      "stage_timings": j.stage_timings, "created_at": j.created_at, "finished_at": j.finished_at,
                      "error": j.error} for j in jobs]}


@router.get("/documents/{doc_id}/pages/{index}/stages")
def page_stages(doc_id: int, index: int, _: CurrentUser, db: DB) -> dict[str, Any]:
    d = _doc(db, doc_id)
    man = stage_dir(d.public_id, index) / "manifest.json"
    if not man.exists():
        raise HTTPException(status_code=404, detail="This page has not been processed yet")
    data = json.loads(man.read_text(encoding="utf-8"))
    data.pop("fields", None)
    return data


@router.get("/files/{path:path}")
def get_file(path: str, _: CurrentUser) -> FileResponse:
    """Authenticated access to uploaded and derived images (never a public static URL)."""
    try:
        p = open_stored(path)
    except (PermissionError, FileNotFoundError):
        raise HTTPException(status_code=404, detail="File not found") from None
    return FileResponse(p, headers={"Cache-Control": "private, max-age=600"})


class LabParams(BaseModel):
    denoise_method: str = Field(default=DEFAULT_PARAMS["denoise_method"], pattern="^(none|median|nlmeans)$")
    denoise_strength: int = Field(default=DEFAULT_PARAMS["denoise_strength"], ge=0, le=15)
    clahe_clip: float = Field(default=DEFAULT_PARAMS["clahe_clip"], ge=0.5, le=8.0)
    clahe_tile: int = Field(default=DEFAULT_PARAMS["clahe_tile"], ge=2, le=32)
    threshold_method: str = Field(default=DEFAULT_PARAMS["threshold_method"], pattern="^(adaptive_gaussian|adaptive_mean|otsu)$")
    threshold_block: int = Field(default=DEFAULT_PARAMS["threshold_block"], ge=3, le=151)
    threshold_c: int = Field(default=DEFAULT_PARAMS["threshold_c"], ge=-20, le=40)
    canny_low: int = Field(default=DEFAULT_PARAMS["canny_low"], ge=0, le=500)
    canny_high: int = Field(default=DEFAULT_PARAMS["canny_high"], ge=0, le=800)
    matcher: str = Field(default=DEFAULT_PARAMS["matcher"], pattern="^(sift|orb)$")


@router.post("/documents/{doc_id}/pages/{index}/lab")
def lab(doc_id: int, index: int, params: LabParams, _: CurrentUser, db: DB) -> dict[str, Any]:
    """Re-run the parameterised stages with new parameters (no OCR). Results go to a
    separate lab folder; the saved processing run is not changed."""
    d = _doc(db, doc_id)
    page = next((p for p in d.pages if p.order_index == index), None)
    if page is None:
        raise HTTPException(status_code=404, detail="Page not found")
    img = decode_image_bytes(open_stored(page.original_path).read_bytes())
    out = stage_dir(d.public_id, index) / "lab" / uuid.uuid4().hex[:8]
    return lab_rerun(img, out, get_settings().upload_dir, params.model_dump())


# --------------------------------------------------------------------------- edit / verify


class FieldPatch(BaseModel):
    value: str | None = Field(default=None, max_length=500)
    status: str | None = Field(default=None, pattern="^(needs_review|unreadable|empty)$")


def _field(db, fid: int) -> ExtractedField:  # noqa: ANN001
    f = db.get(ExtractedField, fid)
    if f is None:
        raise HTTPException(status_code=404, detail="Field not found")
    return f


@router.patch("/fields/{fid}")
def patch_field(fid: int, body: FieldPatch, user: CurrentUser, db: DB, request: Request) -> dict[str, Any]:
    f = _field(db, fid)
    old_v, old_s = f.normalized_value, f.status.value
    if body.value is not None:
        f.normalized_value = body.value
        f.status = FieldStatus.needs_review  # an edited value still needs an explicit Verify
        f.verified_by = None
        f.verified_at = None
    if body.status:
        f.status = FieldStatus(body.status)
    db.add(FieldEdit(field_id=f.id, user_id=user.id, old_value=old_v, new_value=f.normalized_value,
                     old_status=old_s, new_status=f.status.value, reason="edit"))
    db.commit()
    audit.record(db, "field.edit", user_id=user.id, entity_type="field", entity_id=f.id,
                 details={"field_id": f.field_id}, ip_address=client_ip(request))
    return _field_out(f, load_vocabulary().by_id())


@router.post("/fields/{fid}/verify")
def verify_field(fid: int, user: CurrentUser, db: DB, request: Request) -> dict[str, Any]:
    f = _field(db, fid)
    old_s = f.status.value
    f.status = FieldStatus.verified
    f.verified_by = user.id
    f.verified_at = utcnow()
    db.add(FieldEdit(field_id=f.id, user_id=user.id, old_value=f.normalized_value, new_value=f.normalized_value,
                     old_status=old_s, new_status="verified", reason="verify"))
    doc = db.get(Document, f.document_id)
    db.flush()
    remaining = db.execute(select(func.count()).where(ExtractedField.document_id == doc.id,
                                                      ExtractedField.status.in_([FieldStatus.needs_review, FieldStatus.auto_accepted,
                                                                                 FieldStatus.unreadable]))).scalar_one()
    if remaining == 0:
        doc.status = DocumentStatus.verified
        doc.verified_by, doc.verified_at = user.id, utcnow()
    db.commit()
    audit.record(db, "field.verify", user_id=user.id, entity_type="field", entity_id=f.id,
                 details={"field_id": f.field_id}, ip_address=client_ip(request))
    return _field_out(f, load_vocabulary().by_id())


# --------------------------------------------------------------------------- search / export / stats


@router.get("/search")
def search(_: CurrentUser, db: DB, q: str = Query(min_length=1, max_length=100), field_id: str | None = None,
           status: str | None = None, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)) -> dict[str, Any]:
    like = f"%{q}%"
    stmt = (select(ExtractedField, Document).join(Document, ExtractedField.document_id == Document.id)
            .where(or_(ExtractedField.normalized_value.ilike(like), ExtractedField.raw_text.ilike(like))))
    if field_id:
        stmt = stmt.where(ExtractedField.field_id == field_id)
    if status:
        stmt = stmt.where(ExtractedField.status == FieldStatus(status))
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = db.execute(stmt.order_by(Document.created_at.desc(), ExtractedField.id)
                      .offset((page - 1) * page_size).limit(page_size)).all()
    vocab = load_vocabulary().by_id()
    return {"items": [{**_field_out(f, vocab), "document": {"id": d.id, "display_name": d.display_name,
                                                             "status": d.status.value}} for f, d in rows],
            "total": total, "page": page, "page_size": page_size}


@router.get("/documents/{doc_id}/export")
def export(doc_id: int, user: CurrentUser, db: DB, request: Request, format: str = Query("json", pattern="^(json|csv)$")) -> Response:
    detail = document_detail(doc_id, user, db)
    audit.record(db, "document.export", user_id=user.id, entity_type="document", entity_id=doc_id,
                 details={"format": format}, ip_address=client_ip(request))
    if format == "json":
        body = json.dumps({k: detail[k] for k in ("id", "display_name", "template_id", "status", "fields")},
                          default=str, ensure_ascii=False, indent=1)
        return Response(body, media_type="application/json",
                        headers={"Content-Disposition": f'attachment; filename="document_{doc_id}.json"'})
    buf = io.StringIO()
    cols = ["field_id", "display_name", "group_id", "row_index", "raw_text", "normalized_value", "ocr_confidence",
            "detection_confidence", "status"]
    w = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
    w.writeheader()
    for f in detail["fields"]:
        w.writerow(f)
    return Response("﻿" + buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="document_{doc_id}.csv"'})


@router.get("/dashboard")
def dashboard(_: CurrentUser, db: DB) -> dict[str, Any]:
    by_status = {s.value: 0 for s in DocumentStatus}
    by_status.update({k.value: v for k, v in db.execute(select(Document.status, func.count()).group_by(Document.status)).all()})
    fields_by_status = {s.value: 0 for s in FieldStatus}
    fields_by_status.update({k.value: v for k, v in db.execute(
        select(ExtractedField.status, func.count()).group_by(ExtractedField.status)).all()})
    avg_conf = db.execute(select(func.avg(ExtractedField.ocr_confidence)).where(ExtractedField.ocr_confidence.is_not(None))).scalar()
    avg_secs = db.execute(select(func.avg(Document.processing_seconds)).where(Document.processing_seconds.is_not(None))).scalar()
    per_tpl = db.execute(select(FormTemplate.template_id, FormTemplate.bank_name, func.count(Document.id))
                         .join(Document, Document.template_id == FormTemplate.id).group_by(FormTemplate.id)).all()
    since = datetime.now(timezone.utc) - timedelta(days=13)
    days = {(since + timedelta(days=i)).date().isoformat(): 0 for i in range(14)}
    for (created,) in db.execute(select(Document.created_at).where(Document.created_at >= since)).all():
        k = created.date().isoformat()
        if k in days:
            days[k] += 1
    recent = db.execute(select(Document).order_by(Document.created_at.desc()).limit(6)).scalars().all()
    return {"documents_total": sum(by_status.values()), "documents_by_status": by_status,
            "fields_by_status": fields_by_status, "fields_total": sum(fields_by_status.values()),
            "avg_ocr_confidence": None if avg_conf is None else round(float(avg_conf), 4),
            "avg_processing_seconds": None if avg_secs is None else round(float(avg_secs), 2),
            "per_template": [{"template_id": t, "bank_name": b, "documents": n} for t, b, n in per_tpl],
            "uploads_per_day": [{"date": k, "documents": v} for k, v in days.items()],
            "recent": [_doc_summary(d, db) for d in recent]}
