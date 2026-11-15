"""Shared FastAPI dependencies: database session, current user, role guards."""
from __future__ import annotations

from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.database.session import get_db
from app.models import Role, User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token", auto_error=False)

DB = Annotated[Session, Depends(get_db)]

_UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated",
    headers={"WWW-Authenticate": "Bearer"},
)


def _token_from_request(request: Request, bearer: str | None) -> str | None:
    """Bearer header, or `?access_token=` for EventSource/<img> requests that cannot set
    headers (used only by SSE streams and authenticated image endpoints)."""
    if bearer:
        return bearer
    return request.query_params.get("access_token")


def get_current_user(
    request: Request, db: DB, bearer: Annotated[str | None, Depends(oauth2_scheme)]
) -> User:
    token = _token_from_request(request, bearer)
    if not token:
        raise _UNAUTHORIZED
    try:
        payload = decode_access_token(token)
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise _UNAUTHORIZED from None
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise _UNAUTHORIZED
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_admin(user: CurrentUser) -> User:
    if user.role is not Role.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Administrator role required")
    return user


AdminUser = Annotated[User, Depends(require_admin)]


def client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None
