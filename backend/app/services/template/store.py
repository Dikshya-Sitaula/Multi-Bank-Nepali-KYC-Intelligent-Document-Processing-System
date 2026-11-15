"""Template persistence: template.json on disk is the source of truth; the database
tables form_templates / template_pages / template_regions mirror it so that documents can
reference a template and queries can join on regions.

WHY a mirror and not DB-only: SPEC section 8.2 requires that a new bank form is added by
dropping a folder in templates/. The files stay authoritative and reviewable in git; the
mirror is rebuilt from them whenever a template is saved or the app starts.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import FormTemplate, TemplatePage, TemplateRegion
from app.services.template.registry import discover_templates
from app.services.template.schema import Template, load_template, save_template, template_path


def template_sha(t: Template) -> str:
    return hashlib.sha256(json.dumps(t.model_dump(mode="json"), sort_keys=True).encode()).hexdigest()


def sync_template(db: Session, t: Template) -> FormTemplate:
    row = db.execute(select(FormTemplate).where(FormTemplate.template_id == t.template_id)).scalar_one_or_none()
    if row is None:
        row = FormTemplate(template_id=t.template_id, bank_name=t.bank_name)
        db.add(row)
    row.bank_name = t.bank_name
    row.form_name = t.form_name
    row.languages = list(t.languages)
    row.page_count = len(t.pages)
    row.role = t.role
    row.enrollment_status = t.enrollment.status
    row.template_json_sha256 = template_sha(t)
    row.pages.clear()
    db.flush()
    for p in t.pages:
        page = TemplatePage(page_number=p.page_number, width_px=p.width, height_px=p.height,
                            image_path=f"templates/{t.template_id}/{p.image}")
        row.pages.append(page)
        for r in (r for r in t.regions if r.page == p.page_number):
            page.regions.append(TemplateRegion(
                region_key=r.id, field_id=r.field_id, x=r.bbox[0], y=r.bbox[1], w=r.bbox[2], h=r.bbox[3],
                applicant_index=r.applicant_index, row_index=r.row_index, group_id=r.group_id,
                cell_count=r.cell_count, printed_prefill=r.printed_prefill,
                checkbox_options=[o.model_dump() for o in r.checkbox_options] if r.checkbox_options else None))
    db.flush()
    return row


def sync_all(db: Session) -> int:
    """Mirror every template folder that has a template.json. Returns the count."""
    n = 0
    for info in discover_templates():
        if template_path(info.template_id).exists():
            sync_template(db, load_template(info.template_id))
            n += 1
    db.commit()
    return n


def save_and_sync(db: Session, t: Template) -> Template:
    save_template(t)
    sync_template(db, t)
    db.commit()
    return t


def approve(db: Session, t: Template, username: str) -> Template:
    t.enrollment.status = "approved"
    t.enrollment.approved_by = username
    t.enrollment.approved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for r in t.regions:
        r.review_status = "approved"
    return save_and_sync(db, t)
