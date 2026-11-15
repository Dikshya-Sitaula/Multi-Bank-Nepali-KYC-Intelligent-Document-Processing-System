"""FastAPI application factory.

Startup sequence (lifespan):
1. apply database migrations (Alembic upgrade head),
2. optionally create the first admin from env vars (never a hard-coded password),
3. mark jobs interrupted by a previous shutdown as FAILED,
4. start the background job worker.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select

from app import __version__
from app.api import auth, jobs, system, templates
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.security import hash_password
from app.database.session import get_engine, session_scope
from app.models import Role, User
from app.workers import jobs as job_queue

log = logging.getLogger(__name__)
BACKEND_DIR = Path(__file__).resolve().parents[1]


def run_migrations() -> None:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.attributes["configure_logger"] = False
    with get_engine().begin() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "head")


def bootstrap_admin() -> None:
    s = get_settings()
    if not (s.bootstrap_admin_username and s.bootstrap_admin_password):
        return
    with session_scope() as db:
        if db.execute(select(func.count(User.id))).scalar_one() > 0:
            return
        db.add(User(username=s.bootstrap_admin_username, full_name="Administrator", role=Role.admin,
                    password_hash=hash_password(s.bootstrap_admin_password)))
        log.info("bootstrap admin created", extra={"ctx": {"username": s.bootstrap_admin_username}})


def sync_templates() -> None:
    """Mirror templates/<id>/template.json files into the database tables."""
    from app.services.template.store import sync_all

    with session_scope() as db:
        try:
            n = sync_all(db)
            log.info("templates synced", extra={"ctx": {"count": n}})
        except Exception:  # noqa: BLE001 - an invalid template must not stop the app
            log.exception("template sync failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    run_migrations()
    bootstrap_admin()
    sync_templates()
    interrupted = job_queue.recover_interrupted_jobs()
    if interrupted:
        log.warning("marked interrupted jobs as failed", extra={"ctx": {"count": interrupted}})
    worker = job_queue.Worker()
    app.state.worker = worker
    if get_settings().worker_enabled:
        worker.start()
    try:
        yield
    finally:
        worker.stop()


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(
        title="Multi-Bank Nepali KYC IDP API",
        version=__version__,
        description="Intelligent document processing for Nepali bank KYC forms. "
        "Out of scope: identity verification, face/signature matching, AML screening, "
        "document authenticity checks.",
        lifespan=lifespan,
        openapi_url="/api/v1/openapi.json",
        docs_url="/api/v1/docs",
        redoc_url=None,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=s.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )
    api = APIRouter(prefix="/api/v1")
    api.include_router(system.router)
    api.include_router(auth.router)
    api.include_router(jobs.router)
    api.include_router(templates.router)
    app.include_router(api)
    return app


app = create_app()
