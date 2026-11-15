"""Health endpoint, banners, audit log access, config guards and migration drift."""
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from app.core.config import ROOT, Settings, get_settings
from app.database.session import get_engine
from app.models import Role


def test_health_reports_missing_model_honestly(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["database"]["ok"] is True
    assert body["mock_cv"] is False
    yolo = next(c for c in body["components"] if c["name"] == "yolo")
    assert yolo["ok"] is False
    assert any("YOLO model not loaded" in b for b in body["banners"])
    assert not any("MOCK" in b for b in body["banners"])


def test_mock_banner_when_enabled(app_env, monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import create_app

    monkeypatch.setenv("MOCK_CV", "true")
    get_settings.cache_clear()
    with TestClient(create_app()) as c:
        body = c.get("/api/v1/health").json()
    assert body["mock_cv"] is True
    assert any(b.startswith("MOCK MODE") for b in body["banners"])


def test_audit_requires_admin_and_lists_logins(client, make_user):
    _, emp = make_user("asha", Role.employee)
    _, adm = make_user("root", Role.admin)
    assert client.get("/api/v1/audit", headers=emp).status_code == 403
    page = client.get("/api/v1/audit?action=auth.login", headers=adm).json()
    assert page["total"] == 2
    assert {i["action"] for i in page["items"]} == {"auth.login"}


def test_empty_database_has_no_users_or_jobs(client, make_user):
    _, adm = make_user("root", Role.admin)
    jobs = client.get("/api/v1/jobs", headers=adm).json()
    assert jobs == {"items": [], "total": 0, "page": 1, "page_size": 20}


def test_production_requires_secret():
    with pytest.raises(ValueError):
        Settings(app_env="production", _env_file=None)
    Settings(app_env="production", app_secret_key="x" * 40, _env_file=None)


def test_relative_paths_resolve_to_repo_root():
    s = Settings(database_url="sqlite:///./x.db", upload_dir=Path("uploads"), _env_file=None)
    assert s.database_url == "sqlite:///" + (ROOT / "x.db").resolve().as_posix()
    assert s.upload_dir == (ROOT / "uploads").resolve()


def test_migrations_match_models(client):
    """Alembic head must equal the ORM models (no un-migrated schema changes)."""
    backend = Path(__file__).resolve().parents[1]
    cfg = Config(str(backend / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend / "alembic"))
    cfg.attributes["configure_logger"] = False
    with get_engine().begin() as conn:
        cfg.attributes["connection"] = conn
        command.check(cfg)  # raises if autogenerate finds differences


def test_timestamps_are_utc_aware(client, make_user):
    _, headers = make_user("asha")
    created = client.get("/api/v1/auth/me", headers=headers).json()["created_at"]
    assert created.endswith("Z") or created.endswith("+00:00")
