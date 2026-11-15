"""Enumerations shared by models, schemas and the frontend API contract.

Stored as plain strings (native_enum=False) so adding a value never needs a database-
specific ALTER TYPE.
"""
from __future__ import annotations

import enum


class Role(str, enum.Enum):
    admin = "admin"
    employee = "employee"


class DocumentStatus(str, enum.Enum):
    uploaded = "uploaded"
    processing = "processing"
    needs_review = "needs_review"
    verified = "verified"
    failed = "failed"


class JobStatus(str, enum.Enum):
    """Stages from SPEC section 13.1, plus RUNNING for non-document jobs
    (dataset build, training, evaluation) and CANCELLED."""

    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    PREPROCESSING = "PREPROCESSING"
    IDENTIFYING = "IDENTIFYING"
    DETECTING = "DETECTING"
    OCR = "OCR"
    STRUCTURING = "STRUCTURING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

    @property
    def is_terminal(self) -> bool:
        return self in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED)


ACTIVE_JOB_STATUSES = tuple(s for s in JobStatus if not s.is_terminal and s is not JobStatus.QUEUED)


class FieldStatus(str, enum.Enum):
    auto_accepted = "auto_accepted"
    needs_review = "needs_review"
    unreadable = "unreadable"
    empty = "empty"
    verified = "verified"


class ModelKind(str, enum.Enum):
    yolo = "yolo"
    htr = "htr"
