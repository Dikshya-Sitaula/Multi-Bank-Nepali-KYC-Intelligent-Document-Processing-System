"""YOLO-format label import/export for template regions.

WHY: Template Studio is the main editor, but annotators may prefer CVAT. Exporting each
page's regions as a YOLO .txt (class cx cy w h, normalised) plus a classes.txt lets the
same boxes be opened in CVAT, and importing brings corrected boxes back.

Class indices follow config/fields.yaml order over ALL priorities, so every region can
be exported; the training dataset uses its own (P1+P2) index list.
"""
from __future__ import annotations

import io
import zipfile

from app.services.template.schema import Region, Template, Vocabulary


def class_list(vocab: Vocabulary) -> list[str]:
    return vocab.yolo_classes(["P1", "P2", "P3"])


def export_zip(t: Template, vocab: Vocabulary) -> bytes:
    classes = class_list(vocab)
    by_id = vocab.by_id()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("classes.txt", "\n".join(classes) + "\n")
        for p in t.pages:
            lines = []
            for r in t.regions:
                if r.page != p.page_number or r.printed_prefill:
                    continue
                x, y, w, h = r.bbox
                cls = classes.index(by_id[r.field_id].yolo_class)
                lines.append(f"{cls} {x + w / 2:.6f} {y + h / 2:.6f} {w:.6f} {h:.6f}")
            z.writestr(f"labels/page_{p.page_number}.txt", "\n".join(lines) + ("\n" if lines else ""))
    return buf.getvalue()


def import_page_labels(t: Template, page: int, text: str, vocab: Vocabulary, replace: bool = True) -> int:
    """Replace (or add to) a page's regions from a YOLO label file. Region attributes
    beyond the box and class (groups, options) cannot be expressed in YOLO format, so
    imported regions are marked for review."""
    classes = class_list(vocab)
    field_for_class = {}
    for f in vocab.fields:  # first field that uses a class becomes its default field id
        field_for_class.setdefault(f.yolo_class, f.id)
    new: list[Region] = []
    for i, line in enumerate(l for l in text.splitlines() if l.strip()):
        parts = line.split()
        if len(parts) != 5:
            raise ValueError(f"line {i + 1}: expected 5 values, got {len(parts)}")
        cls = int(parts[0])
        if not 0 <= cls < len(classes):
            raise ValueError(f"line {i + 1}: class {cls} out of range")
        cx, cy, w, h = map(float, parts[1:])
        new.append(Region(id=f"p{page}_imp{i + 1:03d}", page=page, field_id=field_for_class[classes[cls]],
                          bbox=[cx - w / 2, cy - h / 2, w, h], source="manual", review_status="proposed"))
    if replace:
        t.regions = [r for r in t.regions if r.page != page]
    existing = {r.id for r in t.regions}
    for r in new:
        while r.id in existing:
            r.id += "x"
        existing.add(r.id)
    t.regions.extend(new)
    return len(new)
