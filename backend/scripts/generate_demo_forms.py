"""Generate SYNTHETIC filled demo forms for the live demo (sprint step 2).

For each training template (nicasia, laxmisunrise, machhapuchhre) two fictional customers
are generated. Every P1 region in template.json that maps to a value of the identity is
filled with synthetic handwriting (or a tick, procedural signature, thumbprint, avatar or
sketch map), then each page is turned into a simulated phone photo.

Outputs (all clearly marked SYNTHETIC, nothing from real people):
  data/demo_forms/SYNTHETIC_<template>_<n>/page_<k>.jpg   phone-photo pages to upload
  data/demo_forms/SYNTHETIC_<template>_<n>.pdf            the same pages as one PDF
  data/demo_forms/ground_truth/SYNTHETIC_<template>_<n>.json
      the values written, kept in a separate folder; the processing pipeline never
      reads it (it exists only for evaluation and for checking the demo).
  data/demo_forms/SYNTHETIC_strong_rotation_shadow/page_1.jpg  extra hard capture

Run:  .venv\\Scripts\\python.exe backend\\scripts\\generate_demo_forms.py [--seed 7]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.datasets import handwriting as hw  # noqa: E402
from app.services.datasets.identity import make_identity  # noqa: E402
from app.services.datasets.phone_sim import simulate_capture  # noqa: E402
from app.services.template.schema import load_template, load_vocabulary  # noqa: E402

OUT = ROOT / "data" / "demo_forms"
TEMPLATES = ["nicasia", "laxmisunrise", "machhapuchhre"]


def value_for(region, ident: dict, rng: np.random.Generator) -> tuple[str | None, str]:
    """Return (value, script) for a text region, or (None, '') if the identity has none."""
    f, g = region.field_id, region.group_id
    nep = rng.random() < 0.35  # some fields are written in Nepali
    pick = lambda d: d["ne"] if nep else d["en"]  # noqa: E731
    addr = ident["address"].get(g or "permanent") or ident["address"]["permanent"]
    m = {
        "name_english": ident["name"]["en"].upper() if rng.random() < 0.5 else ident["name"]["en"],
        "name_nepali": ident["name"]["ne"],
        "name_boxed": ident["name"]["en"].upper(),
        "dob_bs": ident["dob_bs"], "dob_ad": ident["dob_ad"],
        "nationality": pick(ident["nationality"]),
        "citizenship_number": ident["citizenship_number"],
        "citizenship_issue_date": ident["citizenship_issue_date"],
        "citizenship_issue_district": pick(ident["citizenship_issue_district"]),
        "pan_number": ident["pan_number"], "national_id_number": ident["national_id_number"],
        "passport_number": ident["passport_number"],
        "mobile": ident["mobile"], "phone": ident["phone"], "email": ident["email"],
        "employer_name": ident["employer"], "designation": ident["designation"],
        "occupation_text": ident["occupation"], "annual_income": ident["annual_income"],
        "education": ident["education"],
    }
    if f.startswith("address_"):
        part = f[len("address_"):]
        if part in addr and g in (None, "permanent", "current"):
            return pick(addr[part]), "ne" if nep else "en"
        return None, ""
    if f == "family_member_name":
        person = ident["family"].get(g or "")
        if person:
            return (person["ne"] if nep else person["en"].upper()), "ne" if nep else "en"
        return None, ""
    if region.party != "customer" or (g and f in ("citizenship_number",) and g != "citizenship"):
        return None, ""
    v = m.get(f)
    return (v or None), "en"


def choose_option(region, ident: dict, rng: np.random.Generator) -> str | None:
    ids = [o.id for o in region.checkbox_options or []]
    if not ids:
        return None
    wanted = {"gender": ident["gender"], "marital_status": ident["marital_status"]}.get(region.field_id)
    if wanted and wanted in ids:
        return wanted
    if region.field_id == "yes_no":
        return "no" if "no" in ids and rng.random() < 0.9 else ids[0]
    return ids[int(rng.integers(0, len(ids)))]


def fill_page(img: np.ndarray, regions: list, ident: dict, writer: hw.Writer, rng: np.random.Generator,
              truth: list[dict], page_no: int) -> np.ndarray:
    H, W = img.shape[:2]
    page = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB)).convert("RGBA")
    px = lambda b: (int(b[0] * W), int(b[1] * H), int(b[2] * W), int(b[3] * H))  # noqa: E731
    vocab = load_vocabulary().by_id()
    for r in regions:
        fd = vocab[r.field_id]
        if r.printed_prefill or fd.priority != "P1":
            continue
        box = px(r.bbox)
        entry = {"region_id": r.id, "page": page_no, "field_id": r.field_id, "group_id": r.group_id}
        if fd.field_type == "checkbox_group":
            opt = choose_option(r, ident, rng)
            if opt:
                o = next(o for o in r.checkbox_options if o.id == opt)
                entry.update(value=opt, mark=hw.draw_tick(page, px(o.bbox), writer, rng))
                truth.append(entry)
            continue
        if fd.field_type == "visual":
            {"person_photo": lambda: hw.draw_avatar(page, box, rng),
             "signature": lambda: hw.draw_signature(page, box, writer, rng),
             "thumbprint_right": lambda: hw.draw_thumbprint(page, box, rng),
             "thumbprint_left": lambda: hw.draw_thumbprint(page, box, rng),
             "location_map": lambda: hw.draw_location_map(page, box, writer, rng)}.get(r.field_id, lambda: None)()
            entry["value"] = "<visual>"
            truth.append(entry)
            continue
        value, _script = value_for(r, ident, rng)
        if not value:
            continue
        if r.cell_count and fd.field_type in ("boxed_chars", "text"):
            cells = [px(c) for c in r.cells] if r.cells else [
                (box[0] + i * box[2] // r.cell_count, box[1], box[2] // r.cell_count, box[3])
                for i in range(r.cell_count)]
            value = value[: len(cells)]
            hw.write_cells(page, value, cells, writer, rng)
        else:
            hw.write_text(page, value, box, writer, rng)
        entry["value"] = value
        truth.append(entry)
    out = cv2.cvtColor(np.asarray(page.convert("RGB")), cv2.COLOR_RGB2BGR)
    return hw.paper_texture(out, rng)


def save_pdf(pages: list[Path], path: Path) -> None:
    ims = [Image.open(p).convert("RGB") for p in pages]
    ims[0].save(path, save_all=True, append_images=ims[1:], resolution=200.0)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--per-template", type=int, default=2)
    args = ap.parse_args()
    rng = np.random.default_rng(args.seed)
    (OUT / "ground_truth").mkdir(parents=True, exist_ok=True)
    first_filled = None
    for tid in TEMPLATES:
        t = load_template(tid)
        for n in range(1, args.per_template + 1):
            name = f"SYNTHETIC_{tid}_{n}"
            ident = make_identity(rng, name)
            writer = hw.Writer.sample(rng)
            truth: list[dict] = []
            ddir = OUT / name
            ddir.mkdir(parents=True, exist_ok=True)
            files = []
            for p in t.pages:
                clean = cv2.imread(str(ROOT / "templates" / tid / p.image))
                filled = fill_page(clean, [r for r in t.regions if r.page == p.page_number], ident, writer, rng,
                                   truth, p.page_number)
                if first_filled is None:
                    first_filled = (filled, tid)
                cap = simulate_capture(filled, rng, str(rng.choice(["light", "medium"])))
                f = ddir / f"page_{p.page_number}.jpg"
                cv2.imwrite(str(f), cap.image, [cv2.IMWRITE_JPEG_QUALITY, 88])
                files.append(f)
            save_pdf(files, OUT / f"{name}.pdf")
            (OUT / "ground_truth" / f"{name}.json").write_text(json.dumps(
                {"synthetic": True, "template_id": tid, "seed": args.seed, "writer": writer.__dict__,
                 "identity": ident, "written_fields": truth}, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"{name}: {len(files)} pages, {len(truth)} fields written")
    # One extra, deliberately hard capture: strong rotation + forced shadow.
    filled, tid = first_filled
    hard = simulate_capture(filled, rng, "strong", overrides={"rotation_exact_deg": 24.0, "shadow_prob": 1.0,
                                                               "glare_prob": 0.0, "landscape_prob": 0.0})
    hdir = OUT / "SYNTHETIC_strong_rotation_shadow"
    hdir.mkdir(exist_ok=True)
    cv2.imwrite(str(hdir / f"{tid}_page_1.jpg"), hard.image, [cv2.IMWRITE_JPEG_QUALITY, 88])
    print(f"extra hard capture: {hdir.name}/{tid}_page_1.jpg  {hard.params}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
