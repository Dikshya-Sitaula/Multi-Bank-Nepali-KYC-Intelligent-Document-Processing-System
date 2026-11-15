"""Audit trail.

WHY: in a bank, who viewed, edited, verified, exported or deleted a customer record must
be traceable. Every such action calls `record()`. Details never contain OCR text values;
they record ids and field names only.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditLog


def record(
    db: Session,
    action: str,
    *,
    user_id: int | None = None,
    entity_type: str | None = None,
    entity_id: str | int | None = None,
    details: dict[str, Any] | None = None,
    ip_address: str | None = None,
    commit: bool = True,
) -> AuditLog:
    entry = AuditLog(
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=None if entity_id is None else str(entity_id),
        details=details,
        ip_address=ip_address,
    )
    db.add(entry)
    if commit:
        db.commit()
    return entry
