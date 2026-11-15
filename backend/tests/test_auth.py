"""Authentication, roles, rate limiting and audit of login events."""
from sqlalchemy import select

from app.core.security import create_access_token
from app.database.session import session_scope
from app.models import AuditLog, Role
from tests.conftest import TEST_PASSWORD


def test_login_and_me(client, make_user):
    uid, headers = make_user("asha", Role.employee)
    r = client.get("/api/v1/auth/me", headers=headers)
    assert r.status_code == 200
    assert r.json()["username"] == "asha"
    assert r.json()["role"] == "employee"
    assert "password_hash" not in r.json()


def test_wrong_password_rejected_and_audited(client, make_user):
    make_user("asha")
    r = client.post("/api/v1/auth/login", json={"username": "asha", "password": "nope-nope"})
    assert r.status_code == 401
    with session_scope() as db:
        actions = [a.action for a in db.execute(select(AuditLog)).scalars()]
    assert "auth.login_failed" in actions


def test_unknown_user_same_error(client):
    r = client.post("/api/v1/auth/login", json={"username": "ghost", "password": "whatever1"})
    assert r.status_code == 401
    assert r.json()["detail"] == "Incorrect username or password"


def test_inactive_user_cannot_login(client, make_user):
    make_user("old", active=False)
    r = client.post("/api/v1/auth/login", json={"username": "old", "password": TEST_PASSWORD})
    assert r.status_code == 401


def test_missing_and_tampered_tokens(client, make_user):
    _, headers = make_user()
    assert client.get("/api/v1/auth/me").status_code == 401
    bad = headers["Authorization"][:-3] + "abc"
    assert client.get("/api/v1/auth/me", headers={"Authorization": bad}).status_code == 401


def test_expired_token(client, make_user):
    uid, _ = make_user()
    token = create_access_token(uid, "employee", expires_minutes=-1)
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_rate_limit(client, make_user):
    make_user("asha")
    codes = [
        client.post("/api/v1/auth/login", json={"username": "asha", "password": "wrong-pass"}).status_code
        for _ in range(11)
    ]
    assert codes[:10] == [401] * 10
    assert codes[10] == 429


def test_employee_cannot_manage_users(client, make_user):
    _, headers = make_user("asha", Role.employee)
    assert client.get("/api/v1/auth/users", headers=headers).status_code == 403
    r = client.post("/api/v1/auth/users", headers=headers,
                    json={"username": "x_user", "password": "longenough1"})
    assert r.status_code == 403


def test_admin_creates_and_updates_users(client, make_user):
    admin_id, headers = make_user("root", Role.admin)
    r = client.post("/api/v1/auth/users", headers=headers,
                    json={"username": "new.emp", "password": "longenough1", "role": "employee"})
    assert r.status_code == 201
    new_id = r.json()["id"]
    dup = client.post("/api/v1/auth/users", headers=headers,
                      json={"username": "NEW.emp", "password": "longenough1"})
    assert dup.status_code == 409
    r = client.patch(f"/api/v1/auth/users/{new_id}", headers=headers, json={"is_active": False})
    assert r.status_code == 200 and r.json()["is_active"] is False
    r = client.patch(f"/api/v1/auth/users/{admin_id}", headers=headers, json={"role": "employee"})
    assert r.status_code == 400
    names = [u["username"] for u in client.get("/api/v1/auth/users", headers=headers).json()]
    assert names == ["new.emp", "root"]


def test_short_password_rejected(client, make_user):
    _, headers = make_user("root", Role.admin)
    r = client.post("/api/v1/auth/users", headers=headers, json={"username": "abc", "password": "short"})
    assert r.status_code == 422
