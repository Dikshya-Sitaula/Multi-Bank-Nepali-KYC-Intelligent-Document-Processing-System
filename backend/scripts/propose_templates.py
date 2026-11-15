"""Auto-propose template regions for each enrolled bank form (SPEC section 9).

Pipeline per page:
1. detect structural candidates (checkboxes, letter-cell strips, boxes, frames,
   write-on lines) with OpenCV, plus exact PDF vector rectangles where available;
2. OCR the printed text on the blank page with EasyOCR (English + Nepali) - cached in
   templates/<id>/proposals/ocr_page_N.json because it is slow on CPU;
3. for each candidate, collect nearby printed text (inside, to the left on the same row,
   the column header above, the text above) and match it against
   config/label_keywords.yaml to suggest a field_id and group_id;
4. group checkboxes that sit on one row into checkbox groups with option labels;
5. write templates/<id>/proposals/page_N.json and an overlay image with numbered,
   colour-coded boxes for review. backend/scripts/build_template.py then combines the
   proposals with the human corrections in templates/<id>/review_edits.yaml into
   template.json.

Nothing here is final: suggestions are reviewed and corrected (by the developer looking
at the overlays, then by the user in Template Studio at Checkpoint A).

Run:  .venv\\Scripts\\python.exe backend\\scripts\\propose_templates.py [template_id ...]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.template.proposals import (  # noqa: E402
    Candidate,
    detect_raster,
    draw_overlay,
    merge_vector,
    vector_rects,
)
from app.services.template.registry import discover_templates  # noqa: E402

SOURCE_CFG = ROOT / "config" / "source_forms.yaml"
KEYWORDS = ROOT / "config" / "label_keywords.yaml"

_reader = None


def ocr_page(img: np.ndarray, cache: Path) -> list[dict]:
    """Printed text boxes on the blank page: [{"text", "bbox": [x,y,w,h], "conf"}]."""
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    global _reader
    if _reader is None:
        import easyocr  # imported lazily: heavy, and only needed when the cache is cold

        _reader = easyocr.Reader(["ne", "en"], gpu=False, verbose=False)
    res = _reader.readtext(img, paragraph=False, width_ths=0.3, mag_ratio=1.0)
    items = []
    for pts, text, conf in res:
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        x0, y0 = int(min(xs)), int(min(ys))
        items.append({"text": text, "bbox": [x0, y0, int(max(xs)) - x0, int(max(ys)) - y0], "conf": round(float(conf), 3)})
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(items, ensure_ascii=False, indent=0), encoding="utf-8")
    return items


def _overlap_1d(a0: float, a1: float, b0: float, b1: float) -> float:
    return max(0.0, min(a1, b1) - max(a0, b0))


def context_text(c: Candidate, texts: list[dict], scale: float) -> dict[str, str]:
    """Printed text around a candidate, by position."""
    cx0, cy0, cx1, cy1 = c.x, c.y, c.x + c.w, c.y + c.h
    inside, left, above, right = [], [], [], []
    for t in texts:
        x, y, w, h = t["bbox"]
        tx0, ty0, tx1, ty1 = x, y, x + w, y + h
        area = w * h
        ov = _overlap_1d(cx0, cx1, tx0, tx1) * _overlap_1d(cy0, cy1, ty0, ty1)
        if area and ov / area > 0.6:
            inside.append(t)
            continue
        v_ov = _overlap_1d(cy0, cy1, ty0, ty1) / max(1, min(h, c.h))
        if v_ov > 0.4 and tx1 <= cx0 + 10 and cx0 - tx1 < 700 * scale:
            left.append((cx0 - tx1, t))
        elif v_ov > 0.4 and tx0 >= cx1 - 10 and tx0 - cx1 < 300 * scale:
            right.append((tx0 - cx1, t))
        h_ov = _overlap_1d(cx0, cx1, tx0, tx1) / max(1, min(w, c.w))
        if h_ov > 0.3 and ty1 <= cy0 + 5 and cy0 - ty1 < 90 * scale:
            above.append((cy0 - ty1, t))
    left.sort(key=lambda p: p[0])
    right.sort(key=lambda p: p[0])
    above.sort(key=lambda p: p[0])
    return {
        "inside": " ".join(t["text"] for t in sorted(inside, key=lambda t: (t["bbox"][1], t["bbox"][0]))),
        "left": " ".join(t["text"] for _, t in reversed(left[:3])),
        "right": " ".join(t["text"] for _, t in right[:1]),
        "above": " ".join(t["text"] for _, t in above[:2]),
    }


def table_context(c: Candidate, boxes: list[Candidate], texts: list[dict]) -> dict[str, str]:
    """For a table cell: the text of the row-header cell (leftmost box in the row) and of
    the column-header cell (nearest box above in the same column that contains text)."""
    row = [b for b in boxes if b is not c and abs(b.y - c.y) < 0.3 * c.h and abs(b.h - c.h) < 0.5 * c.h and b.x < c.x]
    col = [b for b in boxes if b is not c and abs(b.x - c.x) < 0.15 * c.w and abs(b.w - c.w) < 0.3 * c.w and b.y < c.y]

    def text_in(b: Candidate) -> str:
        out = []
        for t in texts:
            x, y, w, h = t["bbox"]
            if b.x - 5 <= x and x + w <= b.x + b.w + 5 and b.y - 5 <= y and y + h <= b.y + b.h + 5:
                out.append(t["text"])
        return " ".join(out)

    row_label = text_in(min(row, key=lambda b: b.x)) if row else ""
    col_label = ""
    for b in sorted(col, key=lambda b: c.y - b.y):
        col_label = text_in(b)
        if col_label:
            break
    return {"row": row_label, "col": col_label}


def match_rules(text: str, rules: list[dict]) -> dict | None:
    t = text.lower()
    for r in rules:
        if any(k.lower() in t for k in r["any"]):
            if "all_any" in r and not any(k.lower() in t for k in r["all_any"]):
                continue
            return r
    return None


def group_checkboxes(boxes: list[Candidate], scale: float) -> list[list[Candidate]]:
    """Checkboxes on one row within a reasonable gap form one checkbox group."""
    boxes = sorted(boxes, key=lambda b: (b.y, b.x))
    groups: list[list[Candidate]] = []
    for b in boxes:
        for g in groups:
            last = g[-1]
            if abs(b.y - last.y) < 0.6 * last.h and 0 < b.x - last.x < 750 * scale:
                g.append(b)
                break
        else:
            groups.append([b])
    return groups


ADDRESS_GROUPS = [("permanent", ["permanent", "स्थायी"]), ("current", ["present", "current", "temporary", "हालको", "हाल"]),
                  ("mailing", ["mailing", "correspond", "पत्राचार"]), ("office", ["office"]),
                  ("local_contact", ["local contact", "स्थानीय"])]


def address_group(text: str) -> str | None:
    t = text.lower()
    for gid, keys in ADDRESS_GROUPS:
        if any(k in t for k in keys):
            return gid
    return None


def propose_page(tid: str, pno: int, img: np.ndarray, texts: list[dict], vec: list[Candidate],
                 rules: list[dict], section_titles: list[dict]) -> list[dict]:
    h, w = img.shape[:2]
    scale = w / 2480.0
    cands = detect_raster(img)
    if vec:
        cands = merge_vector(cands, vec, scale, img)
    boxes = [c for c in cands if c.kind in ("box", "frame")]
    checkboxes = [c for c in cands if c.kind == "checkbox"]
    proposals: list[dict] = []

    def section_above(y: int) -> str:
        """Nearest address-block title above y (e.g. 'Permanent Address')."""
        best, by = "", -1
        for s in section_titles:
            sy = s["bbox"][1]
            if sy < y and sy > by:
                best, by = s["text"], sy
        return best

    for c in cands:
        if c.kind == "checkbox":
            continue
        ctx = context_text(c, texts, scale)
        tctx = table_context(c, boxes, texts) if c.kind == "box" else {"row": "", "col": ""}
        is_label_cell = bool(ctx["inside"]) and c.kind == "box" and len(ctx["inside"]) > 2
        rule = None
        source = ""
        if c.kind == "frame" and ctx["inside"]:
            rule, source = match_rules(ctx["inside"], rules), "inside"
            is_label_cell = False
        for key in ("left", "row", "above", "col"):
            if rule:
                break
            text = ctx.get(key) or tctx.get(key, "")
            if text:
                rule, source = match_rules(text, rules), key
        group = rule.get("group_id") if rule else None
        fid = rule["field_id"] if rule else None
        if fid and fid.startswith("address_") and not group:
            group = address_group(" ".join([tctx["col"], ctx["above"], section_above(c.y)]))
        if c.kind == "cell_strip" and fid in (None, "family_member_name") and "block" in (ctx["left"] + tctx["row"]).lower():
            fid = "family_member_name" if group else "name_boxed"
        proposals.append({
            "kind": c.kind, "bbox": [c.x, c.y, c.w, c.h], "source": c.source,
            "cell_count": len(c.cells) if c.cells else None,
            "cells": [list(x) for x in c.cells] if c.cells else None,
            "suggested_field": None if is_label_cell else fid,
            "group_id": None if is_label_cell else group,
            "label_cell": is_label_cell,
            "context": {**ctx, **tctx, "matched_on": source},
        })

    for g in group_checkboxes(checkboxes, scale):
        x0 = min(b.x for b in g)
        y0 = min(b.y for b in g)
        opts = []
        x_end = max(b.x + b.w for b in g)
        for b in g:
            ctx = context_text(b, texts, scale)
            opts.append({"label": ctx["right"], "bbox": [b.x, b.y, b.w, b.h]})
            # The group's box extends over the option labels to the right of the last box.
            if ctx["right"]:
                for t in texts:
                    if t["text"] == ctx["right"]:
                        x_end = max(x_end, t["bbox"][0] + t["bbox"][2])
                        break
        first = context_text(g[0], texts, scale)
        label_text = first["left"]
        rule = match_rules(label_text, rules) if label_text else None
        if rule is None:
            rule = match_rules(" ".join(o["label"] for o in opts), rules)
        y1 = max(b.y + b.h for b in g)
        proposals.append({
            "kind": "checkbox_group", "bbox": [x0, y0, x_end - x0, y1 - y0], "source": "raster",
            "options": opts, "suggested_field": rule["field_id"] if rule else None,
            "group_id": rule.get("group_id") if rule else None, "label_cell": False,
            "context": {"left": label_text, "options": [o["label"] for o in opts]},
        })
    for i, p in enumerate(proposals):
        p["n"] = i
    return proposals


def main() -> int:
    ap = argparse.ArgumentParser(description="Auto-propose template regions")
    ap.add_argument("templates", nargs="*", help="template ids (default: all)")
    ap.add_argument("--force", action="store_true",
                    help="re-propose a template that already has review_edits.yaml (its candidate numbers change)")
    args = ap.parse_args()

    rules = yaml.safe_load(KEYWORDS.read_text(encoding="utf-8"))["rules"]
    src_cfg = yaml.safe_load(SOURCE_CFG.read_text(encoding="utf-8"))["forms"]
    import pymupdf

    for info in discover_templates():
        tid = info.template_id
        if args.templates and tid not in args.templates:
            continue
        tdir = ROOT / "templates" / tid
        if (tdir / "review_edits.yaml").exists() and not args.force:
            print(f"{tid}: already reviewed (review_edits.yaml refers to these candidate numbers); "
                  "skipped. Use --force to re-propose and then re-review.")
            continue
        out = tdir / "proposals"
        out.mkdir(exist_ok=True)
        pdf_path = ROOT / "data" / "source_forms" / src_cfg.get(tid, {}).get("file", "")
        doc = pymupdf.open(pdf_path) if pdf_path.is_file() else None
        page_props: dict[int, list[dict]] = {}
        sizes = []
        for ref in info.pages:
            img = cv2.imread(str(ref.image_path))
            h, w = img.shape[:2]
            sizes.append((ref.page_number, w, h))
            texts = ocr_page(img, out / f"ocr_page_{ref.page_number}.json")
            vec = vector_rects(doc[ref.page_number - 1]) if doc is not None else []
            if len(vec) < 5:
                vec = []  # embedded scans have no useful vector drawings
            titles = [t for t in texts if address_group(t["text"])]
            props = propose_page(tid, ref.page_number, img, texts, vec, rules, titles)
            page_props[ref.page_number] = props
            (out / f"page_{ref.page_number}.json").write_text(json.dumps(props, ensure_ascii=False, indent=1), encoding="utf-8")
            items = [{"n": p["n"], "bbox": p["bbox"], "kind": p["kind"],
                      "label": (p["suggested_field"] or ("label" if p["label_cell"] else "?")) +
                               (f":{p['group_id']}" if p.get("group_id") else "")}
                     for p in props]
            cv2.imwrite(str(out / f"overlay_page_{ref.page_number}.jpg"), draw_overlay(img, items),
                        [cv2.IMWRITE_JPEG_QUALITY, 80])
            n_sug = sum(1 for p in props if p["suggested_field"])
            print(f"{tid} p{ref.page_number}: {len(props)} candidates, {n_sug} with a suggested field")
        meta = {"template_id": tid, "bank_name": info.bank_name,
                 "role": "training" if "training" in info.role else "evaluation_only",
                 "pages": [{"page_number": n, "width": w, "height": h} for n, w, h in sizes]}
        (out / "meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
        print(f"{tid}: proposals written; run build_template.py {tid} to create template.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
