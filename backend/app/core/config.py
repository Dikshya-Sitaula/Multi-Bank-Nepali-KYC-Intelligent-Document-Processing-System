"""Application settings.

WHY: every secret, path and switch comes from environment variables (or `.env`), never
from code, so the same code runs in development, tests and a hardened deployment.
Relative paths are resolved against the repository root so the app behaves the same no
matter which directory it is started from.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[3]

# Placeholder secret for local development only. Startup refuses it in production.
_DEV_SECRET = "dev-only-insecure-secret-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    app_secret_key: str = _DEV_SECRET
    database_url: str = f"sqlite:///{(ROOT / 'kyc_idp.db').as_posix()}"

    upload_dir: Path = ROOT / "uploads"
    output_dir: Path = ROOT / "outputs"
    models_dir: Path = ROOT / "models"
    templates_dir: Path = ROOT / "templates"
    config_dir: Path = ROOT / "config"

    cors_origins: str = "http://localhost:5173"
    access_token_expire_minutes: int = 480
    jwt_algorithm: str = "HS256"

    # Upload limits (validated server-side, SPEC section 13.4).
    max_upload_mb: int = 25
    max_pages_per_document: int = 20

    # Login rate limit: attempts per window per client+username.
    login_rate_limit_attempts: int = 10
    login_rate_limit_window_s: int = 300

    # UI development only. When true every screen shows a MOCK banner.
    mock_cv: bool = False
    # OCR text is personal data; it is not logged unless explicitly enabled.
    log_ocr_text: bool = False

    # Background worker.
    worker_enabled: bool = True
    worker_poll_interval_s: float = 1.0

    # Optional: create the first admin on startup if the users table is empty.
    bootstrap_admin_username: str | None = None
    bootstrap_admin_password: str | None = Field(default=None, repr=False)

    @field_validator("upload_dir", "output_dir", "models_dir", "templates_dir", "config_dir", mode="after")
    @classmethod
    def _absolute(cls, v: Path) -> Path:
        return v if v.is_absolute() else (ROOT / v).resolve()

    @field_validator("database_url", mode="after")
    @classmethod
    def _sqlite_relative_to_root(cls, v: str) -> str:
        """Make `sqlite:///./x.db` relative to the repo root, not the working directory."""
        prefix = "sqlite:///"
        if v.startswith(prefix):
            rest = v[len(prefix):]
            if rest and rest != ":memory:" and not Path(rest).is_absolute() and not rest.startswith("/"):
                return prefix + (ROOT / rest).resolve().as_posix()
        return v

    @model_validator(mode="after")
    def _production_guard(self) -> "Settings":
        if self.app_env == "production" and self.app_secret_key == _DEV_SECRET:
            raise ValueError("APP_SECRET_KEY must be set to a strong secret in production")
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()
