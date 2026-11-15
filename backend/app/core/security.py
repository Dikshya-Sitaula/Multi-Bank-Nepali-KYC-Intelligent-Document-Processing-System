"""Password hashing and JWT tokens.

WHY: employees log in before seeing any customer document. Passwords are stored only as
bcrypt hashes; sessions are short-lived signed JWTs carrying the user id and role.
bcrypt is used directly because passlib 1.7 is incompatible with bcrypt 5.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.core.config import get_settings

# bcrypt only uses the first 72 bytes of a password; longer input is rejected
# rather than silently truncated.
_BCRYPT_MAX_BYTES = 72


class PasswordTooLongError(ValueError):
    pass


def hash_password(password: str) -> str:
    raw = password.encode("utf-8")
    if len(raw) > _BCRYPT_MAX_BYTES:
        raise PasswordTooLongError("password longer than 72 bytes")
    return bcrypt.hashpw(raw, bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, hashed: str) -> bool:
    raw = password.encode("utf-8")
    if len(raw) > _BCRYPT_MAX_BYTES:
        return False
    try:
        return bcrypt.checkpw(raw, hashed.encode("ascii"))
    except ValueError:
        return False


def create_access_token(user_id: int, role: str, expires_minutes: int | None = None) -> str:
    s = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=expires_minutes or s.access_token_expire_minutes),
    }
    return jwt.encode(payload, s.app_secret_key, algorithm=s.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    """Raise jwt.PyJWTError on any invalid, expired or tampered token."""
    s = get_settings()
    return jwt.decode(token, s.app_secret_key, algorithms=[s.jwt_algorithm])
