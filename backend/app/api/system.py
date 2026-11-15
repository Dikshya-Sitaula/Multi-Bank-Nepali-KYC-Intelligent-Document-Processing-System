"""Health / system status and audit log endpoints.

The health response drives the frontend's system-status chip and its banners. Component
availability is probed for real (database query, registered weights on disk, importable
OCR engines); nothing is assumed.
"""
from __future__ import annotations

import importlib.util
import shutil
from datetime import datetime

from fastapi import APIRouter, Query, Request
from sqlalchemy import func, select, text

from app import __version__
from app.api.deps import DB, AdminUser
from app.core.config import get_settings
from app.models import AuditLog, MLModel, ModelKind
from app.schemas.common import AuditOut, ComponentStatus, HealthOut, Page

router = APIRouter(tags=["system"])


def _active_model_status(db, kind: ModelKind, label: str) -> ComponentStatus:
    model = db.execute(
        select(MLModel).where(MLModel.kind == kind, MLModel.is_active.is_(True)).limit(1)
    ).scalar_one_or_none()
    if model is None:
        return ComponentStatus(name=label, ok=False, detail="No trained model registered yet")
    path = get_settings().models_dir.parent / model.weights_path
    if not path.is_file():
        return ComponentStatus(name=label, ok=False, detail=f"Weights file missing for '{model.name}'")
    return ComponentStatus(name=label, ok=True, detail=f"Loaded: {model.name}")


def _import_status(module: str, label: str) -> ComponentStatus:
    found = importlib.util.find_spec(module) is not None
    return ComponentStatus(name=label, ok=found, detail="Installed" if found else "Not installed")


@router.get("/health", response_model=HealthOut)
def health(request: Request, db: DB) -> HealthOut:
    s = get_settings()
    try:
        db.execute(text("SELECT 1"))
        database = ComponentStatus(name="database", ok=True, detail=s.database_url.split(":", 1)[0])
    except Exception as exc:  # noqa: BLE001
        database = ComponentStatus(name="database", ok=False, detail=type(exc).__name__)

    worker = getattr(request.app.state, "worker", None)
    worker_status = ComponentStatus(
        name="worker", ok=bool(worker and worker.alive),
        detail="Running" if worker and worker.alive else "Not running",
    )

    yolo = _active_model_status(db, ModelKind.yolo, "yolo")
    htr = _active_model_status(db, ModelKind.htr, "htr")
    components = [
        yolo,
        htr,
        _import_status("easyocr", "easyocr"),
        ComponentStatus(name="tesseract", ok=shutil.which("tesseract") is not None,
                        detail="Installed" if shutil.which("tesseract") else "Not installed (optional)"),
    ]

    from app.services.detection.template_snap import TemplateSnapDetector
    from app.services.ocr.engine import get_engine

    ocr = get_engine()
    components.append(ComponentStatus(name="ocr_models", ok=ocr.status == "ready", detail=f"EasyOCR en+ne: {ocr.status}"))
    banners: list[str] = [f"{TemplateSnapDetector.status_text} YOLO model not trained yet."]
    if s.mock_cv:
        banners.append("MOCK MODE: computer-vision output is simulated for UI development. "
                       "Nothing shown is real model output.")

    overall = "ok" if database.ok else "degraded"
    return HealthOut(status=overall, version=__version__, environment=s.app_env, mock_cv=s.mock_cv,
                     mode="template_alignment+snap",
                     database=database, worker=worker_status, components=components, banners=banners)


@router.get("/audit", response_model=Page[AuditOut], tags=["audit"])
def audit_log(
    _: AdminUser,
    db: DB,
    action: str | None = None,
    user_id: int | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> Page[AuditOut]:
    q = select(AuditLog)
    if action:
        q = q.where(AuditLog.action.like(f"{action}%"))
    if user_id is not None:
        q = q.where(AuditLog.user_id == user_id)
    if entity_type:
        q = q.where(AuditLog.entity_type == entity_type)
    if entity_id:
        q = q.where(AuditLog.entity_id == entity_id)
    if since:
        q = q.where(AuditLog.created_at >= since)
    if until:
        q = q.where(AuditLog.created_at <= until)
    total = db.execute(select(func.count()).select_from(q.subquery())).scalar_one()
    rows = db.execute(
        q.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).offset((page - 1) * page_size).limit(page_size)
    ).scalars()
    return Page(items=[AuditOut.model_validate(r) for r in rows], total=total, page=page, page_size=page_size)
