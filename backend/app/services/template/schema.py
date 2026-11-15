"""Typed loaders for config/fields.yaml and templates/<id>/template.json.

WHY: business logic reads form structure only from these two files (SPEC section 8).
Validating them with Pydantic means a typo in a field id or a box outside the page is
caught when the file is loaded, not deep inside the pipeline.

template.json (schema_version 1):

{
  "schema_version": 1,
  "template_id": "laxmisunrise",
  "bank_name": "Laxmi Sunrise Bank",
  "form_name": "Individual KYC",
  "languages": ["eng", "nep"],
  "role": "training" | "evaluation_only",
  "pages": [{"page_number": 1, "image": "pages/page_1.png", "width": 2481, "height": 3508}],
  "regions": [
    {"id": "p1_r001", "page": 1, "field_id": "name_english",
     "bbox": [x, y, w, h],                 # normalised 0..1, top-left origin
     "party": "customer",                  # customer | guardian | joint_applicant | local_contact | introducer | ...
     "applicant_index": null,              # 1, 2 ... for joint forms (from the template, never from YOLO)
     "row_index": null,                    # table row
     "group_id": null,                     # which address / relation / question / ID document
     "cell_count": null,                   # letter cells -> read as boxed characters
     "cells": null,                        # optional per-cell boxes, normalised
     "printed_prefill": false,             # printed on the blank form: never written over, not a field to train
     "checkbox_options": null,             # [{"id": "male", "label": "Male", "bbox": [...]}]
     "label": "Name Surname",              # printed label text near the region (for humans)
     "source": "proposed" | "manual",
     "review_status": "proposed" | "approved"}
  ],
  "enrollment": {"status": "proposed" | "approved", "approved_by": null, "approved_at": null}
}
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.config import get_settings

FieldType = Literal["text", "boxed_chars", "checkbox_group", "visual"]


class FieldDef(BaseModel):
    id: str
    display_name: str
    yolo_class: str
    field_type: FieldType
    language: Literal["eng", "nep", "digits", "mixed"]
    ocr: bool
    validation: str
    required: bool
    section: str
    priority: Literal["P1", "P2", "P3"]


class Vocabulary(BaseModel):
    version: int
    train_priorities: list[str]
    sections: list[dict]
    fields: list[FieldDef]

    @model_validator(mode="after")
    def _unique(self) -> "Vocabulary":
        ids = [f.id for f in self.fields]
        dup = {i for i in ids if ids.count(i) > 1}
        if dup:
            raise ValueError(f"duplicate field ids: {sorted(dup)}")
        sections = {s["id"] for s in self.sections}
        bad = [f.id for f in self.fields if f.section not in sections]
        if bad:
            raise ValueError(f"fields with unknown section: {bad}")
        return self

    def by_id(self) -> dict[str, FieldDef]:
        return {f.id: f for f in self.fields}

    def yolo_classes(self, priorities: list[str] | None = None) -> list[str]:
        """Ordered, de-duplicated detector class names. The order defines the YOLO class
        index, so it follows fields.yaml order and never depends on dict ordering."""
        pri = set(priorities or self.train_priorities)
        out: list[str] = []
        for f in self.fields:
            if f.priority in pri and f.yolo_class not in out:
                out.append(f.yolo_class)
        return out


class CheckboxOption(BaseModel):
    id: str
    label: str | None = None
    bbox: list[float] = Field(min_length=4, max_length=4)


class Region(BaseModel):
    id: str
    page: int = Field(ge=1)
    field_id: str
    bbox: list[float] = Field(min_length=4, max_length=4)
    party: str = "customer"
    applicant_index: int | None = None
    row_index: int | None = None
    group_id: str | None = None
    cell_count: int | None = None
    cells: list[list[float]] | None = None
    printed_prefill: bool = False
    checkbox_options: list[CheckboxOption] | None = None
    label: str | None = None
    source: Literal["proposed", "manual"] = "proposed"
    review_status: Literal["proposed", "approved"] = "proposed"

    @field_validator("bbox")
    @classmethod
    def _bbox_inside(cls, v: list[float]) -> list[float]:
        x, y, w, h = v
        if w <= 0 or h <= 0 or x < -0.01 or y < -0.01 or x + w > 1.01 or y + h > 1.01:
            raise ValueError(f"bbox {v} must be normalised and inside the page")
        return v


class TemplatePage(BaseModel):
    page_number: int = Field(ge=1)
    image: str
    width: int
    height: int


class Enrollment(BaseModel):
    status: Literal["proposed", "approved"] = "proposed"
    approved_by: str | None = None
    approved_at: str | None = None


class Template(BaseModel):
    schema_version: Literal[1] = 1
    template_id: str
    bank_name: str
    form_name: str | None = None
    languages: list[str] = ["eng", "nep"]
    role: Literal["training", "evaluation_only"] = "training"
    pages: list[TemplatePage]
    regions: list[Region] = []
    enrollment: Enrollment = Enrollment()

    @model_validator(mode="after")
    def _consistent(self) -> "Template":
        pages = {p.page_number for p in self.pages}
        ids: set[str] = set()
        for r in self.regions:
            if r.page not in pages:
                raise ValueError(f"region {r.id} on unknown page {r.page}")
            if r.id in ids:
                raise ValueError(f"duplicate region id {r.id}")
            ids.add(r.id)
        return self

    def check_against(self, vocab: Vocabulary) -> list[str]:
        """Field ids that are not in the vocabulary (returned, so callers can report all)."""
        known = vocab.by_id()
        return sorted({r.field_id for r in self.regions if r.field_id not in known})


@lru_cache
def load_vocabulary(path: str | None = None) -> Vocabulary:
    p = Path(path) if path else get_settings().config_dir / "fields.yaml"
    return Vocabulary.model_validate(yaml.safe_load(p.read_text(encoding="utf-8")))


def template_path(template_id: str, templates_dir: Path | None = None) -> Path:
    return (templates_dir or get_settings().templates_dir) / template_id / "template.json"


def load_template(template_id: str, templates_dir: Path | None = None) -> Template:
    t = Template.model_validate_json(template_path(template_id, templates_dir).read_text(encoding="utf-8"))
    unknown = t.check_against(load_vocabulary())
    if unknown:
        raise ValueError(f"template {template_id} uses unknown field ids: {unknown}")
    return t


def save_template(t: Template, templates_dir: Path | None = None) -> Path:
    p = template_path(t.template_id, templates_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(t.model_dump(mode="json"), indent=1, ensure_ascii=False), encoding="utf-8")
    tmp.replace(p)  # atomic on the same filesystem: a crash never leaves half a file
    return p
