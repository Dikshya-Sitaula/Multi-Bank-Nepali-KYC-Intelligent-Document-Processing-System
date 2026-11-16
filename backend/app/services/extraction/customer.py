"""Consolidation of extracted fields into customer profiles."""
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select

from app.models.base import utcnow
from app.models.entities import CustomerProfile, Document, ExtractedField

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def _format_address(components: dict[str, str]) -> str | None:
    parts = []
    if "house_no" in components:
        parts.append(f"House No. {components['house_no']}")
    if "tole" in components:
        parts.append(f"Tole {components['tole']}")
    if "ward" in components and components["ward"]:
        parts.append(f"Ward {components['ward']}")
    if "municipality" in components:
        parts.append(components["municipality"])
    if "district" in components:
        parts.append(components["district"])
    if "province" in components:
        parts.append(components["province"])
    if "country" in components:
        parts.append(components["country"])
    return ", ".join(parts) if parts else None


def sync_customer_profile(db: Session, document_id: int) -> CustomerProfile | None:
    """Read extracted fields for document_id and upsert customer_profiles row."""
    doc = db.get(Document, document_id)
    if not doc:
        return None

    fields = db.execute(
        select(ExtractedField).where(ExtractedField.document_id == document_id)
    ).scalars().all()

    if not fields:
        return None

    data: dict[str, str] = {}
    perm_addr: dict[str, str] = {}
    curr_addr: dict[str, str] = {}

    for f in fields:
        val = f.normalized_value or f.raw_text
        if not val or val == "<image>":
            continue
        val = val.strip()
        if not val:
            continue

        fid = f.field_id
        gid = f.group_id

        if fid.startswith("address_"):
            part = fid[len("address_"):]
            if gid == "permanent":
                perm_addr[part] = val
            elif gid == "current":
                curr_addr[part] = val
        else:
            # First non-empty or prefer higher confidence
            if fid not in data or (f.ocr_confidence or 0) > 0.5:
                data[fid] = val

    name = data.get("name_english") or data.get("name_boxed") or data.get("name_nepali")
    if not name and not data.get("bank_account_number") and not data.get("customer_id"):
        # If no identifiable info yet, don't create an empty customer
        return None

    prof = db.execute(
        select(CustomerProfile).where(CustomerProfile.document_id == document_id)
    ).scalar_one_or_none()

    now = utcnow()
    if not prof:
        prof = CustomerProfile(
            document_id=document_id,
            created_at=now,
            updated_at=now,
        )
        db.add(prof)

    prof.name_english = name
    prof.customer_id = data.get("customer_id")
    prof.account_number = data.get("bank_account_number")
    prof.branch_name = data.get("branch_name")
    prof.gender = data.get("gender")
    prof.marital_status = data.get("marital_status")
    prof.dob_bs = data.get("dob_bs")
    prof.nationality = data.get("nationality")
    prof.email = data.get("email")
    prof.mobile = data.get("mobile") or data.get("phone")
    prof.permanent_address = _format_address(perm_addr)
    prof.current_address = _format_address(curr_addr)
    prof.education = data.get("education_choice") or data.get("education")
    prof.verification_status = doc.status.value
    prof.updated_at = now

    db.flush()
    return prof
