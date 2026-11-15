"""Pydantic schemas shared across the API (the typed REST contract)."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import JobStatus, Role

T = TypeVar("T")


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel, Generic[T]):
    """Server-side pagination envelope."""

    items: list[T]
    total: int
    page: int
    page_size: int


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: "UserOut"


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class UserOut(ORMModel):
    id: int
    username: str
    full_name: str | None
    role: Role
    is_active: bool
    last_login_at: datetime | None
    created_at: datetime


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    full_name: str | None = Field(default=None, max_length=128)
    password: str = Field(min_length=8, max_length=72)
    role: Role = Role.employee


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, max_length=128)
    role: Role | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=8, max_length=72)


class JobOut(ORMModel):
    id: int
    job_type: str
    status: JobStatus
    progress: float
    message: str | None
    params: dict[str, Any] | None
    result: dict[str, Any] | None
    error: str | None
    stage_timings: dict[str, float] | None
    log: list[dict[str, Any]] | None
    document_id: int | None
    created_by: int | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class AuditOut(ORMModel):
    id: int
    user_id: int | None
    action: str
    entity_type: str | None
    entity_id: str | None
    details: dict[str, Any] | None
    ip_address: str | None
    created_at: datetime


class ComponentStatus(BaseModel):
    name: str
    ok: bool
    detail: str


class HealthOut(BaseModel):
    status: str
    version: str
    environment: str
    mock_cv: bool
    mode: str
    database: ComponentStatus
    worker: ComponentStatus
    components: list[ComponentStatus]
    banners: list[str]


TokenResponse.model_rebuild()
