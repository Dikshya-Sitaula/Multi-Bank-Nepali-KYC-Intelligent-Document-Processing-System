"""Discovery of enrolled template pages on disk.

A template is a folder templates/<template_id>/ containing pages/page_N.png (rasterized by
backend/scripts/rasterize_sources.py) and, once enrolled, template.json. Nothing about
which banks exist is written in code: the folder listing is the registry.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.core.config import get_settings

_PAGE_RE = re.compile(r"^page_(\d+)\.png$")


@dataclass(frozen=True)
class TemplatePageRef:
    template_id: str
    page_number: int
    image_path: Path

    @property
    def key(self) -> str:
        return f"{self.template_id}/p{self.page_number}"


@dataclass(frozen=True)
class TemplateInfo:
    template_id: str
    bank_name: str | None
    role: str                # "training" | "evaluation_only ..." from triage or template.json
    pages: tuple[TemplatePageRef, ...]
    has_template_json: bool


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def discover_templates(templates_dir: Path | None = None) -> list[TemplateInfo]:
    root = templates_dir or get_settings().templates_dir
    out: list[TemplateInfo] = []
    if not root.is_dir():
        return out
    for tdir in sorted(p for p in root.iterdir() if p.is_dir()):
        pages_dir = tdir / "pages"
        if not pages_dir.is_dir():
            continue
        pages = []
        for f in pages_dir.iterdir():
            m = _PAGE_RE.match(f.name)
            if m:
                pages.append(TemplatePageRef(tdir.name, int(m.group(1)), f))
        if not pages:
            continue
        pages.sort(key=lambda r: r.page_number)
        tj = _read_json(tdir / "template.json")
        si = _read_json(tdir / "source_info.json")
        out.append(TemplateInfo(
            template_id=tdir.name,
            bank_name=tj.get("bank_name") or si.get("bank_name"),
            role=tj.get("role") or si.get("suggested_role") or "training",
            pages=tuple(pages),
            has_template_json=bool(tj),
        ))
    return out


def all_template_pages(templates_dir: Path | None = None, template_ids: list[str] | None = None) -> list[TemplatePageRef]:
    refs = [p for t in discover_templates(templates_dir) for p in t.pages]
    if template_ids is not None:
        refs = [r for r in refs if r.template_id in set(template_ids)]
    return refs


@lru_cache(maxsize=256)
def file_sha256(path: Path, mtime_ns: int) -> str:  # mtime in the key invalidates the cache
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def page_sha(ref: TemplatePageRef) -> str:
    return file_sha256(ref.image_path, ref.image_path.stat().st_mtime_ns)
