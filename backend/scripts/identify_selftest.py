"""Template identification and registration self-test.

WHY: before any model is trained, the classical part of the pipeline must be shown to
work. For every enrolled template page, simulated phone captures are generated at four
distortion levels and run through the real pipeline:

    simulate_capture -> preprocess -> identify -> register

Measured:
- identification accuracy (correct template AND page), per level and per template;
- "unknown" rate on negative samples (procedurally generated non-form pages that must
  NOT be identified as any bank form);
- registration error: grid points on the template are mapped through the known
  simulated geometry and through the pipeline's estimated geometry; the distance between
  the two, in template pixels (300 DPI, 1 px = 0.085 mm), is the alignment error;
- printed-structure overlap and timings.

Results: reports/template_identification.md and .json. Nothing in the report is typed by
hand; every number comes from this run. Seeds are recorded for reproducibility.

Run:  .venv\\Scripts\\python.exe backend\\scripts\\identify_selftest.py --samples 2
"""
from __future__ import annotations

import argparse
import json
import platform
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.app_config import section  # noqa: E402
from app.services.datasets.phone_sim import simulate_capture  # noqa: E402
from app.services.preprocessing.pipeline import preprocess  # noqa: E402
from app.services.template.identify import identify  # noqa: E402
from app.services.template.register import register  # noqa: E402
from app.services.template.registry import all_template_pages  # noqa: E402

LEVELS = ["none", "light", "medium", "strong"]
REPORT_MD = ROOT / "reports" / "template_identification.md"
REPORT_JSON = ROOT / "reports" / "template_identification.json"


def negative_page(rng: np.random.Generator, w: int = 2480, h: int = 3508) -> np.ndarray:
    """A procedurally generated document that is not any enrolled form: random text
    lines, random boxes and a random table, in random layout."""
    img = np.full((h, w, 3), 255, np.uint8)
    y = int(rng.integers(150, 300))
    fonts = [cv2.FONT_HERSHEY_SIMPLEX, cv2.FONT_HERSHEY_DUPLEX, cv2.FONT_HERSHEY_COMPLEX]
    while y < h - 200:
        kind = rng.random()
        if kind < 0.6:
            words = ["".join(chr(int(c)) for c in rng.integers(65, 91, int(rng.integers(3, 10))))
                     for _ in range(int(rng.integers(3, 9)))]
            cv2.putText(img, " ".join(words), (int(rng.integers(100, 300)), y), fonts[int(rng.integers(0, 3))],
                        float(rng.uniform(1.2, 2.2)), (0, 0, 0), int(rng.integers(2, 4)))
            y += int(rng.integers(70, 120))
        elif kind < 0.85:
            x0 = int(rng.integers(100, 600))
            cv2.rectangle(img, (x0, y), (x0 + int(rng.integers(400, 1700)), y + int(rng.integers(60, 300))), (0, 0, 0), 3)
            y += int(rng.integers(150, 400))
        else:
            rows, cols = int(rng.integers(3, 7)), int(rng.integers(2, 6))
            cw, rh = int(1900 / cols), int(rng.integers(60, 90))
            for r in range(rows + 1):
                cv2.line(img, (250, y + r * rh), (250 + cols * cw, y + r * rh), (0, 0, 0), 2)
            for c in range(cols + 1):
                cv2.line(img, (250 + c * cw, y), (250 + c * cw, y + rows * rh), (0, 0, 0), 2)
            y += rows * rh + 120
    return img


def registration_error(cap_h: np.ndarray, pre_m: np.ndarray, reg_h: np.ndarray, size: tuple[int, int]) -> np.ndarray:
    """Distances (px) between true and estimated template positions of a 9x9 grid."""
    w, h = size
    xs, ys = np.meshgrid(np.linspace(0.05 * w, 0.95 * w, 9), np.linspace(0.05 * h, 0.95 * h, 9))
    pts = np.stack([xs.ravel(), ys.ravel()], 1).astype(np.float32).reshape(-1, 1, 2)
    in_capture = cv2.perspectiveTransform(pts, cap_h.astype(np.float32))
    estimated = cv2.perspectiveTransform(in_capture, (reg_h @ pre_m).astype(np.float32))
    return np.linalg.norm((estimated - pts).reshape(-1, 2), axis=1)


def main() -> int:
    ap = argparse.ArgumentParser(description="Template identification/registration self-test")
    ap.add_argument("--samples", type=int, default=2, help="captures per page per level")
    ap.add_argument("--negatives", type=int, default=10, help="non-form pages to test rejection")
    ap.add_argument("--seed", type=int, default=1234)
    ap.add_argument("--levels", nargs="*", default=LEVELS)
    args = ap.parse_args()

    refs = all_template_pages()
    if not refs:
        print("No template pages found. Run rasterize_sources.py first.")
        return 1
    rng = np.random.default_rng(args.seed)
    rows: list[dict] = []
    t_start = time.time()
    total = len(refs) * len(args.levels) * args.samples
    done = 0
    for ref in refs:
        page = cv2.imread(str(ref.image_path))
        size = (page.shape[1], page.shape[0])
        for level in args.levels:
            for s in range(args.samples):
                cap = simulate_capture(page, rng, level)
                t0 = time.perf_counter()
                pre = preprocess(cap.image)
                t1 = time.perf_counter()
                res = identify(pre.image)
                t2 = time.perf_counter()
                row = {"template": ref.template_id, "page": ref.page_number, "level": level, "sample": s,
                       "capture": cap.params, "pred_template": res.template_id, "pred_page": res.page_number,
                       "status": res.status, "confidence": round(res.confidence, 4), "inliers": res.inliers,
                       "correct": res.template_id == ref.template_id and res.page_number == ref.page_number,
                       "ms_preprocess": round((t1 - t0) * 1000, 1), "ms_identify": round((t2 - t1) * 1000, 1)}
                if res.status == "identified" and row["correct"]:
                    reg = register(pre.image, res.homography, ref.image_path)
                    err = registration_error(cap.homography, pre.transform, reg.homography, size)
                    row.update(reg_overlap=round(reg.overlap, 4), reg_refined=reg.refined,
                               reg_err_median_px=round(float(np.median(err)), 2),
                               reg_err_max_px=round(float(err.max()), 2), ms_register=round(reg.ms, 1))
                rows.append(row)
                done += 1
                if done % 20 == 0:
                    print(f"{done}/{total} captures, {time.time() - t_start:.0f}s")

    negatives = []
    for i in range(args.negatives):
        cap = simulate_capture(negative_page(rng), rng, "light")
        res = identify(preprocess(cap.image).image)
        negatives.append({"sample": i, "status": res.status, "pred_template": res.template_id,
                          "pred_page": res.page_number, "inliers": res.inliers})

    summary = summarise(rows, negatives)
    meta = {"generated": datetime.now().isoformat(timespec="seconds"), "seed": args.seed,
            "samples_per_page_level": args.samples, "levels": args.levels, "template_pages": len(refs),
            "negatives": args.negatives, "identification_config": section("identification"),
            "registration_config": section("registration"), "machine": platform.platform(),
            "python": sys.version.split()[0], "runtime_s": round(time.time() - t_start, 1)}
    REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps({"meta": meta, "summary": summary, "rows": rows, "negatives": negatives},
                                      indent=1), encoding="utf-8")
    write_markdown(meta, summary, rows)
    print(f"Written {REPORT_MD.relative_to(ROOT)}")
    return 0


def _pct(n: int, d: int) -> str:
    return f"{100.0 * n / d:.1f}% ({n}/{d})" if d else "n/a"


def summarise(rows: list[dict], negatives: list[dict]) -> dict:
    by_level: dict[str, list] = defaultdict(list)
    by_tpl: dict[str, list] = defaultdict(list)
    for r in rows:
        by_level[r["level"]].append(r)
        by_tpl[r["template"]].append(r)

    def stats(rs: list[dict]) -> dict:
        reg = [r for r in rs if "reg_err_median_px" in r]
        return {
            "n": len(rs),
            "correct": sum(r["correct"] for r in rs),
            "unknown": sum(r["status"] == "unknown" for r in rs),
            "wrong": sum(r["status"] == "identified" and not r["correct"] for r in rs),
            "reg_n": len(reg),
            "reg_err_median_px": round(float(np.median([r["reg_err_median_px"] for r in reg])), 2) if reg else None,
            "reg_err_p95_of_max_px": round(float(np.percentile([r["reg_err_max_px"] for r in reg], 95)), 2) if reg else None,
            "overlap_median": round(float(np.median([r["reg_overlap"] for r in reg])), 4) if reg else None,
            "ms_identify_median": round(float(np.median([r["ms_identify"] for r in rs])), 1) if rs else None,
            "ms_preprocess_median": round(float(np.median([r["ms_preprocess"] for r in rs])), 1) if rs else None,
        }

    return {
        "overall": stats(rows),
        "by_level": {k: stats(v) for k, v in by_level.items()},
        "by_template": {k: stats(v) for k, v in by_tpl.items()},
        "negatives": {"n": len(negatives), "rejected": sum(n["status"] == "unknown" for n in negatives)},
        "errors": [{k: r[k] for k in ("template", "page", "level", "sample", "status", "pred_template",
                                      "pred_page", "inliers")} for r in rows if not r["correct"]],
    }


def write_markdown(meta: dict, summary: dict, rows: list[dict]) -> None:
    L = ["# Template identification and registration self-test", "",
         f"Generated by `backend/scripts/identify_selftest.py` on {meta['generated']} "
         f"(seed {meta['seed']}, {meta['samples_per_page_level']} simulated captures per page per level, "
         f"{meta['template_pages']} template pages, runtime {meta['runtime_s']} s).", "",
         "Each capture is a clean template page turned into a simulated phone photo "
         "(`app/services/datasets/phone_sim.py`) and run through preprocessing, identification and "
         "registration. Simulated captures are cleaner than many real phone photos, so these numbers "
         "are an upper bound until real photos are tested.", "",
         "Registration error = distance between where a template point truly lands and where the "
         "pipeline puts it, over a 9x9 grid, in template pixels (300 DPI; 1 px = 0.085 mm).", "",
         "## By distortion level", "",
         "| Level | Correct | Unknown | Wrong form/page | Median reg. error px | p95 of max reg. error px | Median overlap | Median identify ms | Median preprocess ms |",
         "|---|---|---|---|---|---|---|---|---|"]
    for lvl, s in summary["by_level"].items():
        L.append(f"| {lvl} | {_pct(s['correct'], s['n'])} | {s['unknown']} | {s['wrong']} | "
                 f"{s['reg_err_median_px']} | {s['reg_err_p95_of_max_px']} | {s['overlap_median']} | "
                 f"{s['ms_identify_median']} | {s['ms_preprocess_median']} |")
    o = summary["overall"]
    L.append(f"| **all** | **{_pct(o['correct'], o['n'])}** | {o['unknown']} | {o['wrong']} | "
             f"{o['reg_err_median_px']} | {o['reg_err_p95_of_max_px']} | {o['overlap_median']} | "
             f"{o['ms_identify_median']} | {o['ms_preprocess_median']} |")
    L += ["", "## By template", "", "| Template | Correct | Unknown | Wrong | Median reg. error px |", "|---|---|---|---|---|"]
    for t, s in summary["by_template"].items():
        L.append(f"| {t} | {_pct(s['correct'], s['n'])} | {s['unknown']} | {s['wrong']} | {s['reg_err_median_px']} |")
    n = summary["negatives"]
    L += ["", "## Unknown-form rejection", "",
          f"Procedurally generated non-form pages correctly reported as unknown: {_pct(n['rejected'], n['n'])}.", ""]
    if summary["errors"]:
        L += ["## Failures", "", "| Template | Page | Level | Sample | Status | Predicted | Inliers |", "|---|---|---|---|---|---|---|"]
        for e in summary["errors"]:
            pred = f"{e['pred_template']} p{e['pred_page']}" if e["pred_template"] else "-"
            L.append(f"| {e['template']} | {e['page']} | {e['level']} | {e['sample']} | {e['status']} | {pred} | {e['inliers']} |")
    else:
        L += ["## Failures", "", "None in this run."]
    L += ["", f"Machine: {meta['machine']}, Python {meta['python']}. Full per-capture rows: "
          "`reports/template_identification.json`.", ""]
    REPORT_MD.write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
