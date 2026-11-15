"""Save every preprocessing / identification / registration stage for one image.

WHY: to inspect what the pipeline does to a real photo, step by step, without the UI
(and as figures for the report or viva). Output goes to outputs/debug/<name>/.

Run:
  .venv\\Scripts\\python.exe backend\\scripts\\debug_pipeline.py path\\to\\photo.jpg
  .venv\\Scripts\\python.exe backend\\scripts\\debug_pipeline.py --simulate nicasia 1 --level strong
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.datasets.phone_sim import simulate_capture  # noqa: E402
from app.services.preprocessing.pipeline import preprocess  # noqa: E402
from app.services.preprocessing.steps import decode_image_bytes  # noqa: E402
from app.services.quality.page_check import check_page  # noqa: E402
from app.services.template.identify import draw_matches, identify  # noqa: E402
from app.services.template.register import overlay_debug, register  # noqa: E402
from app.services.template.registry import all_template_pages  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Dump pipeline debug images")
    ap.add_argument("image", nargs="?", help="photo or scan to process")
    ap.add_argument("--simulate", nargs=2, metavar=("TEMPLATE", "PAGE"),
                    help="instead of a file, simulate a phone photo of this template page")
    ap.add_argument("--level", default="medium", choices=["none", "light", "medium", "strong"])
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    if args.simulate:
        tid, pno = args.simulate[0], int(args.simulate[1])
        ref = next((r for r in all_template_pages() if r.template_id == tid and r.page_number == pno), None)
        if ref is None:
            print(f"No template page {tid} p{pno}")
            return 1
        img = simulate_capture(cv2.imread(str(ref.image_path)), np.random.default_rng(args.seed), args.level).image
        name = f"sim_{tid}_p{pno}_{args.level}_s{args.seed}"
    elif args.image:
        img = decode_image_bytes(Path(args.image).read_bytes())
        name = Path(args.image).stem
    else:
        ap.error("give an image path or --simulate TEMPLATE PAGE")

    out = ROOT / "outputs" / "debug" / name
    out.mkdir(parents=True, exist_ok=True)
    quality = check_page(img)
    pre = preprocess(img, keep_debug=True)
    for i, step in enumerate(pre.steps):
        if step.image is not None:
            cv2.imwrite(str(out / f"{i:02d}_{step.name}.jpg"), step.image, [cv2.IMWRITE_JPEG_QUALITY, 85])
    res = identify(pre.image)
    summary = {"quality": {"warnings": quality.warnings, **quality.metrics},
               "steps": [{"name": s.name, "applied": s.applied, "ms": s.ms, **s.details} for s in pre.steps],
               "identification": {k: v for k, v in res.to_dict().items() if k != "homography"}}
    if res.status == "identified":
        ref = next(r for r in all_template_pages() if r.template_id == res.template_id and r.page_number == res.page_number)
        cv2.imwrite(str(out / "20_matches.jpg"), draw_matches(pre.image, ref))
        reg = register(pre.image, res.homography, ref.image_path)
        cv2.imwrite(str(out / "21_aligned.jpg"), reg.aligned, [cv2.IMWRITE_JPEG_QUALITY, 85])
        cv2.imwrite(str(out / "22_alignment_overlay.jpg"), overlay_debug(reg.aligned, ref.image_path),
                    [cv2.IMWRITE_JPEG_QUALITY, 85])
        summary["registration"] = {k: v for k, v in reg.to_dict().items() if k != "homography"}
    (out / "summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"Wrote {out.relative_to(ROOT)}")
    print(json.dumps(summary["identification"], indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
