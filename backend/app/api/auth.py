"""Authentication and user management endpoints."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func, select

from app.api.deps import DB, AdminUser, CurrentUser, client_ip
from app.core.config import get_settings
from app.core.rate_limit import SlidingWindowLimiter
from app.core.security import create_access_token, hash_password, verify_password
from app.models import User
from app.models.base import utcnow
from app.schemas.common import LoginRequest, TokenResponse, UserCreate, UserOut, UserUpdate
from app.services import audit

router = APIRouter(prefix="/auth", tags=["auth"])

_settings = get_settings()
login_limiter = SlidingWindowLimiter(_settings.login_rate_limit_attempts, _settings.login_rate_limit_window_s)

# A real bcrypt hash of a random string; used so failed logins for unknown usernames take
# the same time as for known ones (no username enumeration via timing).
_DUMMY_HASH = hash_password("timing-equaliser-not-a-real-password")


def _login(db: DB, request: Request, username: str, password: str) -> TokenResponse:
    ip = client_ip(request) or "unknown"
    limiter_key = f"{ip}|{username.lower()}"
    allowed, retry = login_limiter.hit(limiter_key)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Try again later.",
            headers={"Retry-After": str(int(retry) + 1)},
        )
    user = db.execute(select(User).where(func.lower(User.username) == username.lower())).scalar_one_or_none()
    ok = verify_password(password, user.password_hash if user else _DUMMY_HASH)
    if not user or not ok or not user.is_active:
        audit.record(db, "auth.login_failed", details={"username": username[:64]}, ip_address=ip)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect username or password")
    login_limiter.reset(limiter_key)  # a successful login clears earlier failed attempts
    user.last_login_at = utcnow()
    audit.record(db, "auth.login", user_id=user.id, entity_type="user", entity_id=user.id, ip_address=ip)
    s = get_settings()
    return TokenResponse(
        access_token=create_access_token(user.id, user.role.value),
        expires_in=s.access_token_expire_minutes * 60,
        user=UserOut.model_validate(user),
    )


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, request: Request, db: DB) -> TokenResponse:
    return _login(db, request, body.username, body.password)


@router.post("/token", response_model=TokenResponse, include_in_schema=True)
def token(form: Annotated[OAuth2PasswordRequestForm, Depends()], request: Request, db: DB) -> TokenResponse:
    """OAuth2 form login, used by the OpenAPI 'Authorize' button."""
    return _login(db, request, form.username, form.password)


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> User:
    return user


@router.get("/users", response_model=list[UserOut])
def list_users(_: AdminUser, db: DB) -> list[User]:
    return list(db.execute(select(User).order_by(User.username)).scalars())


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(body: UserCreate, admin: AdminUser, db: DB, request: Request) -> User:
    exists = db.execute(select(User.id).where(func.lower(User.username) == body.username.lower())).first()
    if exists:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already exists")
    user = User(username=body.username, full_name=body.full_name, role=body.role,
                password_hash=hash_password(body.password))
    db.add(user)
    db.flush()
    audit.record(db, "user.create", user_id=admin.id, entity_type="user", entity_id=user.id,
                 details={"username": user.username, "role": user.role.value}, ip_address=client_ip(request))
    return user


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(user_id: int, body: UserUpdate, admin: AdminUser, db: DB, request: Request) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    changed: list[str] = []
    if body.full_name is not None:
        user.full_name = body.full_name
        changed.append("full_name")
    if body.role is not None and body.role is not user.role:
        if user.id == admin.id:
            raise HTTPException(status_code=400, detail="You cannot change your own role")
        user.role = body.role
        changed.append("role")
    if body.is_active is not None and body.is_active != user.is_active:
        if user.id == admin.id:
            raise HTTPException(status_code=400, detail="You cannot deactivate yourself")
        user.is_active = body.is_active
        changed.append("is_active")
    if body.password:
        user.password_hash = hash_password(body.password)
        changed.append("password")
    audit.record(db, "user.update", user_id=admin.id, entity_type="user", entity_id=user.id,
                 details={"changed": changed}, ip_address=client_ip(request))
    return user
