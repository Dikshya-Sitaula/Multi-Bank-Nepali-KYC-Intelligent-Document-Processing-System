"""All relational tables (SPEC section 13.1).

WHY relational and not one JSON blob per document: search, review queues, dashboards,
per-field edit history and evaluation all query individual fields, so fields, pages,
detections and edits are rows with foreign keys. JSON columns are used only for
genuinely free-form payloads (metrics, parameters, quality numbers).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UTCDateTime, utcnow
from app.models.enums import DocumentStatus, FieldStatus, JobStatus, ModelKind, Role


def _enum(e: type) -> Enum:
    return Enum(e, native_enum=False, length=32, validate_strings=True)


# --------------------------------------------------------------------------- users


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(128))
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    role: Mapped[Role] = mapped_column(_enum(Role), nullable=False, default=Role.employee)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


# --------------------------------------------------------------------------- templates


class FormTemplate(TimestampMixin, Base):
    """A bank form enrolled from templates/<template_id>/template.json."""

    __tablename__ = "form_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    template_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    bank_name: Mapped[str] = mapped_column(String(128), nullable=False)
    form_name: Mapped[str | None] = mapped_column(String(256))
    languages: Mapped[list[str]] = mapped_column(JSON, default=list)
    page_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="training")
    enrollment_status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    template_json_sha256: Mapped[str | None] = mapped_column(String(64))

    pages: Mapped[list[TemplatePage]] = relationship(
        back_populates="template", cascade="all, delete-orphan", order_by="TemplatePage.page_number"
    )


class TemplatePage(Base):
    __tablename__ = "template_pages"
    __table_args__ = (UniqueConstraint("template_id", "page_number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    template_id: Mapped[int] = mapped_column(ForeignKey("form_templates.id", ondelete="CASCADE"), nullable=False)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    width_px: Mapped[int] = mapped_column(Integer, nullable=False)
    height_px: Mapped[int] = mapped_column(Integer, nullable=False)
    image_path: Mapped[str] = mapped_column(String(512), nullable=False)

    template: Mapped[FormTemplate] = relationship(back_populates="pages")
    regions: Mapped[list[TemplateRegion]] = relationship(back_populates="page", cascade="all, delete-orphan")


class TemplateRegion(Base):
    """One annotated region; bbox is normalized [0,1] in template page coordinates."""

    __tablename__ = "template_regions"

    id: Mapped[int] = mapped_column(primary_key=True)
    page_id: Mapped[int] = mapped_column(ForeignKey("template_pages.id", ondelete="CASCADE"), nullable=False)
    region_key: Mapped[str] = mapped_column(String(64), nullable=False)
    field_id: Mapped[str] = mapped_column(String(64), nullable=False)
    x: Mapped[float] = mapped_column(Float, nullable=False)
    y: Mapped[float] = mapped_column(Float, nullable=False)
    w: Mapped[float] = mapped_column(Float, nullable=False)
    h: Mapped[float] = mapped_column(Float, nullable=False)
    applicant_index: Mapped[int | None] = mapped_column(Integer)
    row_index: Mapped[int | None] = mapped_column(Integer)
    group_id: Mapped[str | None] = mapped_column(String(64))
    cell_count: Mapped[int | None] = mapped_column(Integer)
    printed_prefill: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    checkbox_options: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON)

    page: Mapped[TemplatePage] = relationship(back_populates="regions")


# --------------------------------------------------------------------------- documents


class Document(TimestampMixin, Base):
    __tablename__ = "documents"
    __table_args__ = (Index("ix_documents_status_created", "status", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[str] = mapped_column(String(36), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(256), nullable=False)
    template_id: Mapped[int | None] = mapped_column(ForeignKey("form_templates.id", ondelete="SET NULL"))
    template_confidence: Mapped[float | None] = mapped_column(Float)
    status: Mapped[DocumentStatus] = mapped_column(
        _enum(DocumentStatus), nullable=False, default=DocumentStatus.uploaded
    )
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    processing_started_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    processing_finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    processing_seconds: Mapped[float | None] = mapped_column(Float)
    verified_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    verified_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    template: Mapped[FormTemplate | None] = relationship()
    pages: Mapped[list[Page]] = relationship(
        back_populates="document", cascade="all, delete-orphan", order_by="Page.order_index"
    )
    fields: Mapped[list[ExtractedField]] = relationship(back_populates="document", cascade="all, delete-orphan")
    jobs: Mapped[list[ProcessingJob]] = relationship(back_populates="document", cascade="all, delete-orphan")


class Page(TimestampMixin, Base):
    __tablename__ = "pages"
    __table_args__ = (UniqueConstraint("document_id", "order_index"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    original_path: Mapped[str] = mapped_column(String(512), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(256), nullable=False)
    processed_path: Mapped[str | None] = mapped_column(String(512))
    width_px: Mapped[int | None] = mapped_column(Integer)
    height_px: Mapped[int | None] = mapped_column(Integer)
    quality: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    quality_warnings: Mapped[list[str] | None] = mapped_column(JSON)
    template_page_number: Mapped[int | None] = mapped_column(Integer)
    registration_confidence: Mapped[float | None] = mapped_column(Float)
    homography: Mapped[list[list[float]] | None] = mapped_column(JSON)

    document: Mapped[Document] = relationship(back_populates="pages")
    detections: Mapped[list[FieldDetection]] = relationship(back_populates="page", cascade="all, delete-orphan")


class FieldDetection(Base):
    """Raw YOLO output on the aligned page, kept separately from the extracted value."""

    __tablename__ = "field_detections"

    id: Mapped[int] = mapped_column(primary_key=True)
    page_id: Mapped[int] = mapped_column(ForeignKey("pages.id", ondelete="CASCADE"), nullable=False, index=True)
    yolo_class: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    x: Mapped[float] = mapped_column(Float, nullable=False)
    y: Mapped[float] = mapped_column(Float, nullable=False)
    w: Mapped[float] = mapped_column(Float, nullable=False)
    h: Mapped[float] = mapped_column(Float, nullable=False)
    model_id: Mapped[int | None] = mapped_column(ForeignKey("ml_models.id", ondelete="SET NULL"))
    crop_path: Mapped[str | None] = mapped_column(String(512))

    page: Mapped[Page] = relationship(back_populates="detections")


class ExtractedField(TimestampMixin, Base):
    __tablename__ = "extracted_fields"
    __table_args__ = (
        Index("ix_extracted_fields_doc_field", "document_id", "field_id"),
        Index("ix_extracted_fields_status", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    detection_id: Mapped[int | None] = mapped_column(ForeignKey("field_detections.id", ondelete="SET NULL"))
    page_id: Mapped[int | None] = mapped_column(ForeignKey("pages.id", ondelete="SET NULL"))
    field_id: Mapped[str] = mapped_column(String(64), nullable=False)
    applicant_index: Mapped[int | None] = mapped_column(Integer)
    row_index: Mapped[int | None] = mapped_column(Integer)
    raw_text: Mapped[str | None] = mapped_column(Text)
    normalized_value: Mapped[str | None] = mapped_column(Text)
    detection_confidence: Mapped[float | None] = mapped_column(Float)
    ocr_confidence: Mapped[float | None] = mapped_column(Float)
    engine: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[FieldStatus] = mapped_column(_enum(FieldStatus), nullable=False, default=FieldStatus.needs_review)
    validation_messages: Mapped[list[str] | None] = mapped_column(JSON)
    crop_path: Mapped[str | None] = mapped_column(String(512))
    verified_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    verified_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    document: Mapped[Document] = relationship(back_populates="fields")
    edits: Mapped[list[FieldEdit]] = relationship(
        back_populates="field", cascade="all, delete-orphan", order_by="FieldEdit.created_at"
    )


class FieldEdit(Base):
    __tablename__ = "field_edits"

    id: Mapped[int] = mapped_column(primary_key=True)
    field_id: Mapped[int] = mapped_column(ForeignKey("extracted_fields.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    old_value: Mapped[str | None] = mapped_column(Text)
    new_value: Mapped[str | None] = mapped_column(Text)
    old_status: Mapped[str | None] = mapped_column(String(32))
    new_status: Mapped[str | None] = mapped_column(String(32))
    reason: Mapped[str | None] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False)

    field: Mapped[ExtractedField] = relationship(back_populates="edits")


# --------------------------------------------------------------------------- jobs


class ProcessingJob(TimestampMixin, Base):
    """Every long task (document processing, dataset build, training, evaluation)."""

    __tablename__ = "processing_jobs"
    __table_args__ = (Index("ix_processing_jobs_status_created", "status", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    job_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[JobStatus] = mapped_column(_enum(JobStatus), nullable=False, default=JobStatus.QUEUED)
    progress: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    message: Mapped[str | None] = mapped_column(String(512))
    params: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
    stage_timings: Mapped[dict[str, float] | None] = mapped_column(JSON)
    log: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON)
    document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    heartbeat_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    document: Mapped[Document | None] = relationship(back_populates="jobs")


# --------------------------------------------------------------------------- ML


class MLModel(TimestampMixin, Base):
    """Registered weights. Only files produced by real training runs are registered."""

    __tablename__ = "ml_models"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[ModelKind] = mapped_column(_enum(ModelKind), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    weights_path: Mapped[str] = mapped_column(String(512), nullable=False)
    weights_sha256: Mapped[str | None] = mapped_column(String(64))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    training_run_id: Mapped[int | None] = mapped_column(ForeignKey("training_runs.id", ondelete="SET NULL"))
    meta: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class DatasetBuild(TimestampMixin, Base):
    __tablename__ = "dataset_builds"

    id: Mapped[int] = mapped_column(primary_key=True)
    preset: Mapped[str] = mapped_column(String(32), nullable=False)
    seed: Mapped[int] = mapped_column(Integer, nullable=False)
    output_dir: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    params: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    summary: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("processing_jobs.id", ondelete="SET NULL"))


class TrainingRun(TimestampMixin, Base):
    __tablename__ = "training_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    kind: Mapped[ModelKind] = mapped_column(_enum(ModelKind), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    dataset_build_id: Mapped[int | None] = mapped_column(ForeignKey("dataset_builds.id", ondelete="SET NULL"))
    run_dir: Mapped[str] = mapped_column(String(512), nullable=False)
    params: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    hardware: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    metrics: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    duration_seconds: Mapped[float | None] = mapped_column(Float)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("processing_jobs.id", ondelete="SET NULL"))


class EvaluationRun(TimestampMixin, Base):
    __tablename__ = "evaluation_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    experiment: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    data_source: Mapped[str] = mapped_column(String(64), nullable=False)
    params: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    model_ids: Mapped[list[int] | None] = mapped_column(JSON)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("processing_jobs.id", ondelete="SET NULL"))

    results: Mapped[list[EvaluationResult]] = relationship(back_populates="run", cascade="all, delete-orphan")


class EvaluationResult(Base):
    """One measured number: e.g. metric='cer', group='nep/text', engine='crnn'."""

    __tablename__ = "evaluation_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("evaluation_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    metric: Mapped[str] = mapped_column(String(64), nullable=False)
    group: Mapped[str | None] = mapped_column(String(128))
    engine: Mapped[str | None] = mapped_column(String(32))
    value: Mapped[float] = mapped_column(Float, nullable=False)
    sample_count: Mapped[int | None] = mapped_column(Integer)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    run: Mapped[EvaluationRun] = relationship(back_populates="results")


# --------------------------------------------------------------------------- audit


class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_log_created", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(64))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    details: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    ip_address: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False)
