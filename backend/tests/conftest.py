"""Test fixtures.

Every test that needs the app gets a fresh SQLite file and upload folder under pytest's
tmp_path, built by the real Alembic migrations. Tests never touch the development database.
The background worker thread is disabled; tests drive the queue with `run_one()` so job
behaviour is deterministic.
"""
from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402
from app.database.session import reset_engine  # noqa: E402

TEST_PASSWORD = "correct-horse-battery"


@pytest.fixture
def app_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'test.db').as_posix()}")
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "outputs"))
    monkeypatch.setenv("WORKER_ENABLED", "false")
    monkeypatch.setenv("OCR_PRELOAD", "false")
    monkeypatch.setenv("MOCK_CV", "false")
    monkeypatch.delenv("BOOTSTRAP_ADMIN_USERNAME", raising=False)
    monkeypatch.delenv("BOOTSTRAP_ADMIN_PASSWORD", raising=False)
    get_settings.cache_clear()
    reset_engine()
    from app.api.auth import login_limiter

    login_limiter.reset()
    yield tmp_path
    reset_engine()
    get_settings.cache_clear()


@pytest.fixture
def client(app_env: Path):
    from fastapi.testclient import TestClient

    from app.main import create_app

    with TestClient(create_app()) as c:
        yield c


@pytest.fixture
def make_user(client):
    """Create a user directly in the database and return (user_id, auth headers)."""
    from app.core.security import hash_password
    from app.database.session import session_scope
    from app.models import Role, User

    def _make(username: str = "employee1", role: Role = Role.employee, active: bool = True):
        with session_scope() as db:
            u = User(username=username, role=role, is_active=active, password_hash=hash_password(TEST_PASSWORD))
            db.add(u)
            db.flush()
            uid = u.id
        if not active:
            return uid, {}
        r = client.post("/api/v1/auth/login", json={"username": username, "password": TEST_PASSWORD})
        assert r.status_code == 200, r.text
        return uid, {"Authorization": f"Bearer {r.json()['access_token']}"}

    return _make
