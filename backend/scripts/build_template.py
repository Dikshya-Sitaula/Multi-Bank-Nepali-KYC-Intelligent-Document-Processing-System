"""Build templates/<id>/template.json from automatic proposals + reviewed corrections.

    proposals/page_N.json   (from propose_templates.py, machine generated)
  + review_edits.yaml       (human corrections, explicit and reviewable in git)
  = template.json           (what the pipeline and Template Studio use)

WHY the split: the proposer is heuristic. Every correction made while reviewing the
overlays is written down as an edit referencing a proposal candidate number, so it is
obvious what the machine proposed and what a person changed, and the result can be
rebuilt at any time. Once the user edits the template in Template Studio, template.json
is the source of truth; this script refuses to overwrite a template that was changed
after it was built, unless --force is given.

review_edits.yaml format:

template:                      # optional template-level metadata
  form_name: Individual KYC
  languages: [eng, nep]
pages:
  1:
    drop: [12, 40]             # candidate numbers to discard
    set:                       # per-candidate overrides (also includes unsuggested ones)
      7: {field_id: person_photo}
      98: {options: [female, male, other]}       # checkbox option ids, left to right
      24: {field_id: citizenship_issue_date, group_id: citizenship}
    add:                       # regions the proposer missed; pixel boxes on the 300 DPI page
      - {field_id: branch_name, bbox_px: [360, 320, 410, 60]}
    group_by_x:                # set group_id by horizontal position (table columns)
      - {y: [0.28, 0.46], columns: [[0.26, 0.50, permanent], [0.50, 0.72, current]]}
    defaults: {party: guardian, applicant_index: 2}   # applied to every region on the page
    keep_only: true            # keep only candidates listed under `set` or in a table
    tables:                    # assign many cells at once (normalised page coordinates)
      - rows: [[0.058, 0.077, national_id], [0.077, 0.097, citizenship, {field_map: {id_number: citizenship_number}}]]
        cols: [[0.25, 0.41, id_number], [0.41, 0.57, id_issued_by], [0.96, 1.0, null]]   # null = drop
        row_attr: group_id     # or row_index (then the row value is an integer)
        kinds: [box]           # optional: only these candidate kinds

Run:  .venv\\Scripts\\python.exe backend\\scripts\\build_template.py nicasia [--force]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.template.registry import discover_templates  # noqa: E402
from app.services.template.schema import (  # noqa: E402
    CheckboxOption,
    Region,
    Template,
    TemplatePage,
    load_vocabulary,
    save_template,
    template_path,
)

REGION_KEYS = {"field_id", "group_id", "party", "applicant_index", "row_index", "printed_prefill", "cell_count"}


def _oid(v) -> str:
    """Option id from YAML. Unquoted yes/no are parsed by YAML 1.1 as booleans."""
    if v is True:
        return "yes"
    if v is False:
        return "no"
    return str(v)


def _label(v):
    """Label text from YAML; unquoted Yes/No arrive as booleans."""
    if v is True:
        return "Yes"
    if v is False:
        return "No"
    return None if v is None else str(v)


def _norm(b: list[float], w: int, h: int) -> list[float]:
    x, y, bw, bh = b
    return [round(x / w, 6), round(y / h, 6), round(bw / w, 6), round(bh / h, 6)]


def build(tid: str) -> tuple[Template, list[str]]:
    info = next((i for i in discover_templates() if i.template_id == tid), None)
    if info is None:
        raise SystemExit(f"unknown template {tid}")
    tdir = ROOT / "templates" / tid
    edits_path = tdir / "review_edits.yaml"
    edits = yaml.safe_load(edits_path.read_text(encoding="utf-8")) if edits_path.exists() else {}
    edits = edits or {}
    page_edits = {int(k): v or {} for k, v in (edits.get("pages") or {}).items()}
    vocab = load_vocabulary().by_id()
    warnings: list[str] = []

    import cv2

    pages: list[TemplatePage] = []
    regions: list[Region] = []
    for ref in info.pages:
        img = cv2.imread(str(ref.image_path), cv2.IMREAD_GRAYSCALE)
        ph, pw = img.shape[:2]
        pages.append(TemplatePage(page_number=ref.page_number, image=f"pages/page_{ref.page_number}.png", width=pw, height=ph))
        prop_file = tdir / "proposals" / f"page_{ref.page_number}.json"
        props = json.loads(prop_file.read_text(encoding="utf-8")) if prop_file.exists() else []
        pe = page_edits.get(ref.page_number, {})
        drop = set(pe.get("drop") or [])
        sets = {int(k): v for k, v in (pe.get("set") or {}).items()}
        defaults = pe.get("defaults") or {}
        keep_only = bool(pe.get("keep_only"))
        # Table op: assign field by column and group/row by row for every candidate whose
        # centre falls in a cell. Explicit `set` entries still win.
        table_ov: dict[int, dict] = {}
        for tb in pe.get("tables") or []:
            for p in props:
                x, y, w, h = p["bbox"]
                cx, cy = (x + w / 2) / pw, (y + h / 2) / ph
                if tb.get("kinds") and p["kind"] not in tb["kinds"]:
                    continue
                row = next((r for r in tb["rows"] if r[0] <= cy < r[1]), None)
                col = next((c for c in tb["cols"] if c[0] <= cx < c[1]), None)
                if row is None or col is None or not col[2]:
                    continue
                # The candidate must fit inside its cell; a whole-row outline whose centre
                # happens to fall in a column is not a cell.
                if x / pw < col[0] - 0.01 or (x + w) / pw > col[1] + 0.01:
                    continue
                fid = col[2]
                extra = row[3] if len(row) > 3 and isinstance(row[3], dict) else {}
                fid = (extra.get("field_map") or {}).get(fid, fid)
                ov = {"field_id": fid}
                if row[2] is not None:
                    ov[tb.get("row_attr", "group_id")] = row[2]
                for k, v in (tb.get("attrs") or {}).items():
                    ov.setdefault(k, v)
                table_ov[p["n"]] = ov
        for n, ov in table_ov.items():
            sets[n] = {**ov, **sets.get(n, {})}
        page_regions: list[Region] = []
        for p in props:
            n = p["n"]
            if n in drop or (keep_only and n not in sets):
                continue
            ov = sets.get(n, {})
            fid = ov.get("field_id", p.get("suggested_field"))
            if not fid or (p.get("label_cell") and "field_id" not in ov):
                continue
            if fid not in vocab:
                warnings.append(f"p{ref.page_number} c{n}: unknown field_id {fid}")
                continue
            bbox = ov.get("bbox_px", p["bbox"])
            opts = None
            if p["kind"] == "checkbox_group" or ov.get("options"):
                raw = p.get("options") or []
                ids = ov.get("options") or [f"opt{i + 1}" for i in range(len(raw))]
                if len(ids) != len(raw):
                    warnings.append(f"p{ref.page_number} c{n}: {len(ids)} option ids for {len(raw)} boxes")
                opts = [CheckboxOption(id=(i["id"] if isinstance(i, dict) else _oid(i)),
                                       label=(o.get("label") or None) if not isinstance(i, dict) else i.get("label"),
                                       bbox=_norm(o["bbox"], pw, ph)) for i, o in zip(ids, raw)]
            cells = [_norm(c, pw, ph) for c in p["cells"]] if p.get("cells") else None
            ctx = p.get("context") or {}
            label = " / ".join(str(v) for v in (ctx.get("left"), ctx.get("row"), ctx.get("col"), ctx.get("inside"))
                               if v and isinstance(v, str)) or None
            attrs = {**defaults, **{k: v for k, v in ov.items() if k in REGION_KEYS}}
            attrs.setdefault("group_id", p.get("group_id"))
            attrs.setdefault("cell_count", p.get("cell_count"))
            attrs["field_id"] = fid
            page_regions.append(Region(id=f"p{ref.page_number}_c{n:03d}", page=ref.page_number,
                                       bbox=_norm(bbox, pw, ph), cells=cells, checkbox_options=opts,
                                       label=label[:160] if label else None,
                                       source="manual" if "field_id" in ov or "bbox_px" in ov else "proposed",
                                       **attrs))
        for k, a in enumerate(pe.get("add") or [], start=1):
            if a["field_id"] not in vocab:
                warnings.append(f"p{ref.page_number} add#{k}: unknown field_id {a['field_id']}")
                continue
            opts = None
            if a.get("options"):
                opts = [CheckboxOption(id=_oid(o["id"]), label=_label(o.get("label")), bbox=_norm(o["bbox_px"], pw, ph))
                        for o in a["options"]]
            attrs = {**defaults, **{k2: v for k2, v in a.items() if k2 in REGION_KEYS}}
            page_regions.append(Region(id=f"p{ref.page_number}_a{k:02d}", page=ref.page_number,
                                       bbox=_norm(a["bbox_px"], pw, ph), checkbox_options=opts,
                                       label=a.get("label"), source="manual", **attrs))
        for rule in pe.get("group_by_x") or []:
            y0, y1 = rule["y"]
            for r in page_regions:
                cx, cy = r.bbox[0] + r.bbox[2] / 2, r.bbox[1] + r.bbox[3] / 2
                if not (y0 <= cy <= y1):
                    continue
                if rule.get("fields") and r.field_id not in rule["fields"]:
                    continue
                for x0, x1, gid in rule["columns"]:
                    if x0 <= cx < x1:
                        r.group_id = gid
        regions.extend(page_regions)

    tmeta = edits.get("template") or {}
    role = "training" if "training" in info.role else "evaluation_only"
    t = Template(template_id=tid, bank_name=tmeta.get("bank_name") or info.bank_name or tid,
                 form_name=tmeta.get("form_name"), languages=tmeta.get("languages", ["eng", "nep"]),
                 role=tmeta.get("role", role), pages=pages, regions=regions)
    return t, warnings


def main() -> int:
    ap = argparse.ArgumentParser(description="Build template.json from proposals + review_edits.yaml")
    ap.add_argument("templates", nargs="+")
    ap.add_argument("--force", action="store_true", help="overwrite a template.json edited after the last build")
    args = ap.parse_args()
    for tid in args.templates:
        t, warnings = build(tid)
        path = template_path(tid)
        stamp = path.with_name(".build_sha256")
        if path.exists() and not args.force:
            import hashlib

            current = hashlib.sha256(path.read_bytes()).hexdigest()
            if not stamp.exists() or stamp.read_text().strip() != current:
                print(f"{tid}: template.json was edited after the last build (e.g. in Template Studio). "
                      "Not overwritten; use --force to discard those edits.")
                continue
        save_template(t)
        import hashlib

        stamp.write_text(hashlib.sha256(path.read_bytes()).hexdigest())
        for w in warnings:
            print("WARNING", w)
        by_page = {}
        for r in t.regions:
            by_page[r.page] = by_page.get(r.page, 0) + 1
        print(f"{tid}: {len(t.regions)} regions {by_page}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
