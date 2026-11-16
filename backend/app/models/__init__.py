"""ORM models. Importing this package registers every table on Base.metadata."""
from app.models.base import Base
from app.models.entities import (
    AuditLog,
    CustomerProfile,
    DatasetBuild,
    Document,
    EvaluationResult,
    EvaluationRun,
    ExtractedField,
    FieldDetection,
    FieldEdit,
    FormTemplate,
    MLModel,
    Page,
    ProcessingJob,
    TemplatePage,
    TemplateRegion,
    TrainingRun,
    User,
)
from app.models.enums import DocumentStatus, FieldStatus, JobStatus, ModelKind, Role

__all__ = [
    "AuditLog", "Base", "CustomerProfile", "DatasetBuild", "Document", "DocumentStatus", "EvaluationResult",
    "EvaluationRun", "ExtractedField", "FieldDetection", "FieldEdit", "FieldStatus",
    "FormTemplate", "JobStatus", "MLModel", "ModelKind", "Page", "ProcessingJob", "Role",
    "TemplatePage", "TemplateRegion", "TrainingRun", "User",
]
