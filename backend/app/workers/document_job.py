"""Background job: process an uploaded document page by page and persist the results.

Each page runs the inspectable vision pipeline (app/services/extraction/vision.py); the
stage manifest and images are stored under uploads/<document>/stages/page_<n>/, and the
database receives the page metadata, one detection row and one extracted-field row per
template region. Nothing is auto-verified: fields start as auto_accepted / needs_review /
unreadable / empty, and only a person can mark them verified.
"""
from __future__ import annotations

import time
from collections import Counter

from sqlalchemy import delete, select

from app.core.config import get_settings
from app.database.session import session_scope
from app.models import Document, DocumentStatus, ExtractedField, FieldDetection, FieldStatus, FormTemplate, JobStatus, Page
from app.models.base import utcnow
from app.services.extraction.customer import sync_customer_profile
from app.services.extraction.vision import process_page
from app.services.preprocessing.steps import decode_image_bytes
from app.services.storage.files import open_stored
from app.workers.jobs import JobContext, register

STAGE_STATUS = {s.value: s for s in JobStatus}


def stage_dir(doc_public_id: str, page_index: int):  # noqa: ANN201
    return get_settings().upload_dir / doc_public_id / "stages" / f"page_{page_index}"


@register("process_document")
def process_document(ctx: JobContext) -> dict:
    t_doc = time.perf_counter()
    with session_scope() as db:
        doc = db.get(Document, ctx.document_id)
        if doc is None:
            raise RuntimeError("document not found")
        doc.status = DocumentStatus.processing
        doc.processing_started_at = utcnow()
        pages = [(p.id, p.order_index, p.original_path) for p in doc.pages]
        public_id = doc.public_id
    root = get_settings().upload_dir
    n = len(pages)
    templates_seen: Counter = Counter()
    conf_seen: list[float] = []
    for i, (page_id, order_index, original) in enumerate(pages):
        img = decode_image_bytes(open_stored(original).read_bytes())

        last = {"stage": None}

        def progress(stage: str, frac: float, i=i, last=last) -> None:
            status = STAGE_STATUS.get(stage, JobStatus.RUNNING)
            msg = f"Page {i + 1}/{n}: {stage.title()}"
            if last["stage"] == stage:  # same stage: progress only, no new timing segment
                ctx.progress((i + frac) / n, msg)
            else:
                ctx.stage(status, msg, (i + frac) / n)
                last["stage"] = stage

        res = process_page(img, stage_dir(public_id, order_index), root, ctx.params.get("vision_params"), progress)
        ctx.stage(JobStatus.STRUCTURING, f"Page {i + 1}/{n}: saving results", (i + 0.95) / n)
        ident = res["identification"]
        with session_scope() as db:
            page = db.get(Page, page_id)
            page.quality = res["quality"]
            page.quality_warnings = res["quality_warnings"]
            page.processed_path = res["processed_image"]
            page.template_page_number = ident.get("page_number")
            page.registration_confidence = (res.get("registration") or {}).get("overlap")
            page.homography = (res.get("registration") or {}).get("homography")
            db.execute(delete(FieldDetection).where(FieldDetection.page_id == page_id))
            db.execute(delete(ExtractedField).where(ExtractedField.page_id == page_id))
            if ident.get("template_id"):
                templates_seen[ident["template_id"]] += 1
                conf_seen.append(ident["confidence"])
            for f in res["fields"]:
                x, y, w, h = f["bbox"]
                det = FieldDetection(page_id=page_id, yolo_class=f["field_id"], confidence=f["detection_confidence"],
                                     x=x, y=y, w=w, h=h, crop_path=f["crop"], method=f["detection_method"],
                                     region_key=f["region_id"])
                db.add(det)
                db.flush()
                db.add(ExtractedField(
                    document_id=ctx.document_id, detection_id=det.id, page_id=page_id, field_id=f["field_id"],
                    applicant_index=f["applicant_index"], row_index=f["row_index"], group_id=f["group_id"],
                    raw_text=f["raw_text"], normalized_value=f["normalized_value"],
                    detection_confidence=f["detection_confidence"], ocr_confidence=f["ocr_confidence"],
                    engine=f["engine"], status=FieldStatus(f["status"]),
                    validation_messages=f["validation_messages"] or None, crop_path=f["crop"],
                    extra={k: f[k] for k in ("checkbox", "ocr_raw", "ink", "region_id", "party", "section", "display_name", "bbox")
                           if k in f}))
    with session_scope() as db:
        doc = db.get(Document, ctx.document_id)
        if templates_seen:
            tid = templates_seen.most_common(1)[0][0]
            ft = db.execute(select(FormTemplate).where(FormTemplate.template_id == tid)).scalar_one_or_none()
            doc.template_id = ft.id if ft else None
            doc.template_confidence = round(sum(conf_seen) / len(conf_seen), 4)
            doc.status = DocumentStatus.needs_review
            sync_customer_profile(db, ctx.document_id)
        else:
            doc.status = DocumentStatus.failed
        doc.processing_finished_at = utcnow()
        doc.processing_seconds = round(time.perf_counter() - t_doc, 2)
        return {"pages": n, "templates": dict(templates_seen), "seconds": doc.processing_seconds,
                "status": doc.status.value}
