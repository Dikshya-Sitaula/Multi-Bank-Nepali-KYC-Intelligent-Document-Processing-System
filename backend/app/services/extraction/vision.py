"""The page-level computer-vision pipeline with inspectable stages.

Every stage records: key, title, why it exists, the image it produced (saved to disk),
the parameters used, measured metrics and wall time. The Vision Lab shows these records;
nothing in them is typed by hand.

Execution order (as actually run):
  original -> quality -> grayscale -> denoise -> CLAHE (+histograms) -> threshold ->
  Canny edges -> contours + page quadrilateral -> perspective -> deskew (+ resize and the
  same denoise/CLAHE applied to the colour page) -> keypoints -> matches vs every template
  page (RANSAC) -> identification -> homography alignment -> template regions ->
  OpenCV box snapping -> crops -> checkboxes -> OCR -> normalise/validate.
The pixel-level stages (grayscale..threshold) are shown on the photo as uploaded; the
final processed page uses the same denoise and CLAHE settings after the geometric fixes.
"""
from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from app.core.app_config import section
from app.services.detection.template_snap import TemplateSnapDetector
from app.services.extraction import checkbox as cb
from app.services.extraction.validators import normalise, validate
from app.services.preprocessing import steps
from app.services.quality.page_check import check_page
from app.services.template.features import extract
from app.services.template.identify import draw_matches, identify
from app.services.template.register import overlay_debug, register
from app.services.template.registry import all_template_pages
from app.services.template.schema import load_template, load_vocabulary, template_path

WHY = {
    "original": "The photo exactly as uploaded (EXIF rotation applied). Everything else is derived from it; it is never modified.",
    "quality": "Blur, resolution, skew and glare are measured first so a bad photo is flagged before any time is spent on OCR. Image: Laplacian edge strength (bright = sharp).",
    "grayscale": "Colour is not needed to find structure; one channel makes filtering and thresholding simpler and faster.",
    "denoise": "Removes sensor noise and JPEG speckle that would otherwise create false edges and false 'ink'. Kept mild so thin pen strokes survive.",
    "clahe": "Contrast Limited Adaptive Histogram Equalisation evens out shadows and uneven lighting locally, without blowing out bright areas.",
    "threshold": "Separates ink from paper. Adaptive thresholding copes with lighting that changes across the page; shown for inspection, not used to destroy handwriting.",
    "edges": "Canny edges reveal the paper border and the printed lines; they feed the page-boundary search.",
    "contours": "The largest four-sided contour is taken as the sheet of paper (the document quadrilateral).",
    "perspective": "A four-point perspective transform flattens the photographed sheet into a rectangle.",
    "deskew": "Small residual rotation is measured from the form's long printed lines (Hough) and removed; the page is resized to the template scale (A4 at 300 DPI).",
    "keypoints": "SIFT/ORB keypoints are distinctive local patterns that can be found again despite rotation, scale and lighting changes.",
    "matching": "Keypoints are matched against every enrolled template page; RANSAC keeps only matches consistent with one homography (inliers).",
    "identification": "The template page with the most RANSAC inliers wins, if it passes a minimum and a geometry sanity check; otherwise the form is 'unknown'.",
    "alignment": "The homography warps the photo onto the template canvas, optionally refined with ECC; red = template's printed lines over the aligned page.",
    "regions": "Field boxes defined once per template (template.json) are now valid on this page because both share the same coordinates.",
    "snapping": "Each template box is snapped to the real printed box OpenCV finds on the aligned page, absorbing the last few pixels of misalignment.",
    "crops": "Each field is cut out so OCR sees only that field.",
    "checkboxes": "Each option square's ink-fill ratio is compared with the empty box on the blank template; a clear increase means 'ticked'.",
    "ocr": "EasyOCR reads English and Nepali text from each non-empty text crop, with a confidence per crop.",
    "validation": "Values are normalised (e.g. Devanagari digits to ASCII) and checked (mobile, PAN, dates, email). Low confidence or invalid values need review.",
}
TITLES = {k: k.replace("_", " ").title() for k in WHY} | {"clahe": "CLAHE", "ocr": "OCR (EasyOCR)",
                                                          "edges": "Canny edges", "contours": "Contours + quad"}

DEFAULT_PARAMS = {"denoise_method": "median", "denoise_strength": 3, "clahe_clip": 2.0, "clahe_tile": 8,
                  "threshold_method": "adaptive_gaussian", "threshold_block": 35, "threshold_c": 10,
                  "canny_low": 30, "canny_high": 120, "matcher": "sift"}
MAX_SAVE_WIDTH = 1600
INK_MIN = 0.006  # fraction of a field box with new ink below which the field is "empty"


@dataclass
class StageRecorder:
    out_dir: Path
    rel_root: Path
    stages: list[dict[str, Any]] = field(default_factory=list)

    def save_image(self, name: str, img: np.ndarray, max_width: int = MAX_SAVE_WIDTH) -> str:
        self.out_dir.mkdir(parents=True, exist_ok=True)
        if img.shape[1] > max_width:
            img = cv2.resize(img, (max_width, round(img.shape[0] * max_width / img.shape[1])), interpolation=cv2.INTER_AREA)
        p = self.out_dir / f"{name}.jpg"
        cv2.imwrite(str(p), img, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return p.relative_to(self.rel_root).as_posix()

    def add(self, key: str, ms: float, img: np.ndarray | None = None, params: dict | None = None,
            metrics: dict | None = None, data: dict | None = None, applied: bool = True) -> None:
        rec = {"key": key, "title": TITLES.get(key, key), "why": WHY.get(key, ""), "ms": round(ms, 1),
               "applied": applied, "params": params or {}, "metrics": metrics or {}, "data": data or {}, "image": None}
        if img is not None:
            rec["image"] = self.save_image(f"{len(self.stages):02d}_{key}", img)
        self.stages.append(rec)


def _hist(gray: np.ndarray, bins: int = 64) -> list[int]:
    return np.histogram(gray, bins=bins, range=(0, 256))[0].astype(int).tolist()


def _threshold(gray: np.ndarray, method: str, block: int, c: int) -> np.ndarray:
    if method == "otsu":
        return cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    kind = cv2.ADAPTIVE_THRESH_MEAN_C if method == "adaptive_mean" else cv2.ADAPTIVE_THRESH_GAUSSIAN_C
    return cv2.adaptiveThreshold(gray, 255, kind, cv2.THRESH_BINARY, max(3, int(block) | 1), int(c))


def _denoise(img: np.ndarray, method: str, strength: int) -> np.ndarray:
    if method == "none" or strength <= 0:
        return img
    if method == "nlmeans":
        return steps.denoise(img, "nlmeans", nlmeans_h=int(strength))
    return steps.denoise(img, "median", median_ksize=int(strength))


def preprocess_stages(img: np.ndarray, rec: StageRecorder, p: dict) -> dict[str, Any]:
    """Stages original..deskew. Returns the processed page and the original->page transform."""
    t = time.perf_counter
    t0 = t()
    rec.add("original", 0.0, img, metrics={"width": img.shape[1], "height": img.shape[0]})

    t0 = t()
    q = check_page(img)
    small, _ = steps.resize_to_width(steps.to_gray(img), min(1200, img.shape[1]))
    lap = cv2.convertScaleAbs(cv2.Laplacian(small, cv2.CV_16S, ksize=3), alpha=3)
    rec.add("quality", (t() - t0) * 1000, cv2.applyColorMap(lap, cv2.COLORMAP_INFERNO),
            metrics=q.metrics, data={"warnings": q.warnings, "codes": q.codes})

    t0 = t()
    gray = steps.to_gray(img)
    rec.add("grayscale", (t() - t0) * 1000, gray)

    t0 = t()
    den = _denoise(gray, p["denoise_method"], p["denoise_strength"])
    rec.add("denoise", (t() - t0) * 1000, den, params={"method": p["denoise_method"], "strength": p["denoise_strength"]},
            metrics={"mean_abs_change": round(float(np.mean(cv2.absdiff(gray, den))), 3)})

    t0 = t()
    cl = cv2.createCLAHE(clipLimit=float(p["clahe_clip"]), tileGridSize=(int(p["clahe_tile"]),) * 2).apply(den)
    rec.add("clahe", (t() - t0) * 1000, cl, params={"clip_limit": p["clahe_clip"], "tile": p["clahe_tile"]},
            metrics={"std_before": round(float(den.std()), 2), "std_after": round(float(cl.std()), 2)},
            data={"hist_before": _hist(den), "hist_after": _hist(cl)})

    t0 = t()
    th = _threshold(cl, p["threshold_method"], p["threshold_block"], p["threshold_c"])
    rec.add("threshold", (t() - t0) * 1000, th,
            params={"method": p["threshold_method"], "block": p["threshold_block"], "c": p["threshold_c"]},
            metrics={"ink_fraction": round(float((th == 0).mean()), 4)})

    t0 = t()
    small_c, scale = steps.resize_to_width(img, min(1000, img.shape[1]))
    edges = cv2.Canny(cv2.GaussianBlur(steps.to_gray(small_c), (5, 5), 0), int(p["canny_low"]), int(p["canny_high"]))
    rec.add("edges", (t() - t0) * 1000, edges, params={"low": p["canny_low"], "high": p["canny_high"]},
            metrics={"edge_fraction": round(float((edges > 0).mean()), 4)})

    # Geometry: orientation, boundary quad, perspective, deskew, resize.
    M = np.eye(3)
    cur, rot = steps.rotate_to_portrait(img)
    if rot == 90:
        M = np.array([[0, -1, img.shape[0] - 1], [1, 0, 0], [0, 0, 1]], float) @ M
    t0 = t()
    bcfg = section("preprocessing")["boundary"]
    quad, info = steps.detect_page_quad(cur, bcfg["work_width"], bcfg["min_area_fraction"], int(p["canny_low"]), int(p["canny_high"]))
    vis, s = steps.resize_to_width(cur.copy(), min(1000, cur.shape[1]))
    ed = cv2.dilate(cv2.Canny(cv2.GaussianBlur(steps.to_gray(vis), (5, 5), 0), int(p["canny_low"]), int(p["canny_high"])),
                    np.ones((5, 5), np.uint8), iterations=2)
    cnts, _ = cv2.findContours(ed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cnts = sorted(cnts, key=cv2.contourArea, reverse=True)[:12]
    cv2.drawContours(vis, cnts, -1, (255, 180, 0), 2)
    if quad is not None:
        cv2.polylines(vis, [(quad * s).astype(np.int32)], True, (0, 255, 120), 5)
        for pt in quad * s:
            cv2.circle(vis, tuple(int(v) for v in pt), 10, (0, 255, 120), -1)
    rec.add("contours", (t() - t0) * 1000, vis,
            metrics={"contours_drawn": len(cnts), "quad_found": quad is not None,
                     "page_area_fraction": round(info.get("area_fraction", 0.0), 4) if quad is not None else None,
                     "method": info.get("method"), "rotated_to_portrait_deg": rot},
            data={"quad": None if quad is None else quad.round(1).tolist()})

    t0 = t()
    if quad is not None:
        cur, P = steps.warp_quad_to_rect(cur, quad)
        M = P.astype(float) @ M
    rec.add("perspective", (t() - t0) * 1000, cur, applied=quad is not None,
            metrics={"size": [cur.shape[1], cur.shape[0]]})

    t0 = t()
    dcfg = section("preprocessing")["deskew"]
    skew, nlines = steps.estimate_skew(cur, dcfg["max_angle_deg"], dcfg["min_line_fraction"])
    if skew is not None and abs(skew) >= 0.1:
        R = cv2.getRotationMatrix2D((cur.shape[1] / 2, cur.shape[0] / 2), -skew, 1.0)
        cur = steps.rotate_image(cur, -skew)
        M = np.vstack([R, [0, 0, 1]]) @ M
    hw = cur.shape[:2]
    cur, _ = steps.resize_to_width(cur, int(section("preprocessing")["target_width"]))
    M = np.diag([cur.shape[1] / hw[1], cur.shape[0] / hw[0], 1.0]) @ M
    cur = _denoise(cur, p["denoise_method"], p["denoise_strength"])
    cur = steps.enhance_contrast(cur, "clahe", float(p["clahe_clip"]), int(p["clahe_tile"]))
    rec.add("deskew", (t() - t0) * 1000, cur, metrics={"skew_deg": None if skew is None else round(skew, 3),
                                                       "hough_lines": nlines, "final_size": [cur.shape[1], cur.shape[0]]})
    return {"page": cur, "transform": M, "quality": q}


def identify_stages(page: np.ndarray, rec: StageRecorder, p: dict) -> dict[str, Any]:
    t = time.perf_counter
    icfg = {"detector": p["matcher"], "shortlist": 100}
    t0 = t()
    cfg = section("identification", icfg)
    feats = extract(page, cfg["detector"], cfg["work_width"], cfg["max_features"])
    small, _ = steps.resize_to_width(page, cfg["work_width"])
    kp = cv2.drawKeypoints(small, [cv2.KeyPoint(float(x), float(y), 6) for x, y in feats.points], None,
                           color=(0, 220, 255), flags=cv2.DRAW_MATCHES_FLAGS_DEFAULT)
    rec.add("keypoints", (t() - t0) * 1000, kp, params={"detector": cfg["detector"], "max_features": cfg["max_features"]},
            metrics={"keypoints": int(len(feats.points))})

    t0 = t()
    res = identify(page, icfg)
    ms_match = (t() - t0) * 1000
    refs = all_template_pages()
    best_ref = next((r for r in refs if r.template_id == res.template_id and r.page_number == res.page_number), None)
    match_img = draw_matches(page, best_ref, icfg) if best_ref else None
    rec.add("matching", ms_match, match_img, params={"ratio_test": cfg["ratio_test"], "ransac_px": cfg["ransac_reproj_px"]},
            metrics={"template_pages_compared": len(refs),
                     "best_inliers": res.inliers},
            data={"candidates": res.candidates})
    rec.add("identification", 0.0, None,
            metrics={"status": res.status, "template_id": res.template_id, "page_number": res.page_number,
                     "confidence": round(res.confidence, 4), "inliers": res.inliers},
            data={"reason": res.reason})
    return {"identification": res, "ref": best_ref}


def process_page(img: np.ndarray, out_dir: Path, rel_root: Path, params: dict | None = None,
                 progress: Callable[[str, float], None] | None = None, run_ocr: bool = True,
                 restrict_template: str | None = None) -> dict[str, Any]:
    p = {**DEFAULT_PARAMS, **(params or {})}
    rec = StageRecorder(out_dir, rel_root)
    say = progress or (lambda *_: None)
    t_page = time.perf_counter()

    say("PREPROCESSING", 0.05)
    pre = preprocess_stages(img, rec, p)
    page = pre["page"]
    say("IDENTIFYING", 0.3)
    ident = identify_stages(page, rec, p)
    res = ident["identification"]
    result: dict[str, Any] = {"params": p, "stages": rec.stages, "quality": pre["quality"].metrics,
                              "quality_warnings": pre["quality"].warnings, "identification": res.to_dict(),
                              "fields": [], "processed_image": rec.save_image("processed_page", page, 2480)}
    if res.status != "identified":
        result["total_ms"] = round((time.perf_counter() - t_page) * 1000, 1)
        _write_manifest(out_dir, result)
        return result

    t = time.perf_counter
    say("DETECTING", 0.45)
    tid, pno = res.template_id, res.page_number
    tpl_path = ident["ref"].image_path
    t0 = t()
    reg = register(page, res.homography, tpl_path)
    tpl = cv2.imread(str(tpl_path))
    rec.add("alignment", (t() - t0) * 1000, overlay_debug(reg.aligned, tpl_path),
            metrics={"printed_structure_overlap": round(reg.overlap, 4), "ecc_refined": reg.refined},
            data={"aligned_image": rec.save_image("aligned", reg.aligned),
                  "template_image": rec.save_image("template", tpl),
                  "homography": (reg.homography).round(6).tolist()})
    result["registration"] = {"overlap": reg.overlap, "homography": (reg.homography @ pre["transform"]).tolist(),
                              "aligned_image": rec.stages[-1]["data"]["aligned_image"]}

    template = load_template(tid) if template_path(tid).exists() else None
    regions = [r for r in (template.regions if template else []) if r.page == pno and not r.printed_prefill]
    vocab = load_vocabulary().by_id()
    H, W = reg.aligned.shape[:2]

    t0 = t()
    vis = reg.aligned.copy()
    for r in regions:
        x, y, w, h = r.bbox
        cv2.rectangle(vis, (int(x * W), int(y * H)), (int((x + w) * W), int((y + h) * H)), (255, 140, 0), 3)
    rec.add("regions", (t() - t0) * 1000, vis, metrics={"regions": len(regions), "template_id": tid, "page": pno,
                                                         "template_enrolled": template is not None})

    t0 = t()
    det = TemplateSnapDetector()
    dets = det.detect(reg.aligned, regions, reg.overlap)
    vis = reg.aligned.copy()
    snapped = [d for d in dets if d.snap.get("snapped")]
    for d in dets:
        tx, ty, tw, th = d.template_bbox_px
        cv2.rectangle(vis, (tx, ty), (tx + tw, ty + th), (255, 140, 0), 2)
        if d.snap.get("snapped"):
            fx, fy, fw, fh = d.bbox_px
            cv2.rectangle(vis, (fx, fy), (fx + fw, fy + fh), (60, 220, 60), 3)
    rec.add("snapping", (t() - t0) * 1000, vis, params={"min_iou": det.min_iou},
            metrics={"printed_boxes_found": len(det.last_candidates), "snapped": len(snapped), "kept_template_box": len(dets) - len(snapped),
                     "mean_iou_snapped": round(float(np.mean([d.snap["iou_before"] for d in snapped])), 4) if snapped else None,
                     "mean_shift_px": round(float(np.mean([d.snap["shift_px"] for d in snapped])), 2) if snapped else None},
            data={"boxes": [{"region_id": d.region.id, "template": list(d.template_bbox_px), "snapped": list(d.bbox_px),
                             **d.snap} for d in dets]})

    say("OCR", 0.55)
    aligned_gray = steps.to_gray(reg.aligned)
    tpl_gray = steps.to_gray(tpl)
    crop_dir = out_dir / "crops"
    crop_dir.mkdir(parents=True, exist_ok=True)
    fields: list[dict[str, Any]] = []
    t_crops = t_cb = t_ocr = t_val = 0.0
    cb_vis = reg.aligned.copy()
    from app.services.ocr.engine import get_engine

    engine = get_engine()
    text_dets = [d for d in dets if vocab[d.region.field_id].field_type in ("text", "boxed_chars")]
    for i, d in enumerate(dets):
        fd = vocab[d.region.field_id]
        x, y, w, h = d.bbox_px
        t0 = t()
        pad = 6
        crop = reg.aligned[max(0, y - pad):y + h + pad, max(0, x - pad):x + w + pad]
        crop_rel = None
        if crop.size:
            cp = crop_dir / f"{d.region.id}.jpg"
            cv2.imwrite(str(cp), crop, [cv2.IMWRITE_JPEG_QUALITY, 90])
            crop_rel = cp.relative_to(rel_root).as_posix()
        t_crops += t() - t0
        f: dict[str, Any] = {"region_id": d.region.id, "field_id": d.region.field_id, "display_name": fd.display_name,
                             "field_type": fd.field_type, "section": fd.section, "priority": fd.priority,
                             "group_id": d.region.group_id, "row_index": d.region.row_index,
                             "applicant_index": d.region.applicant_index, "party": d.region.party,
                             "bbox": list(d.bbox_px), "detection_confidence": d.confidence, "detection_method": d.method,
                             "crop": crop_rel, "raw_text": None, "normalized_value": None, "ocr_confidence": None,
                             "engine": None, "status": "empty", "validation_messages": [], "ink": 0.0}
        if fd.field_type == "checkbox_group" and d.region.checkbox_options:
            t0 = t()
            opts = [(o.id, (int(o.bbox[0] * W), int(o.bbox[1] * H), int(o.bbox[2] * W), int(o.bbox[3] * H)))
                    for o in d.region.checkbox_options]
            states = cb.read_options(aligned_gray, tpl_gray, opts)
            sel = [s["option_id"] for s in states if s["state"] == "selected"]
            amb = [s for s in states if s["state"] == "ambiguous"]
            for s in states:
                ix, iy, iw, ih = s["inner"]
                col = {"selected": (60, 220, 60), "ambiguous": (0, 190, 255), "empty": (160, 160, 160)}[s["state"]]
                cv2.rectangle(cb_vis, (ix, iy), (ix + iw, iy + ih), col, 3)
            f.update(raw_text=",".join(sel) or None, normalized_value=",".join(sel) or None, engine="checkbox_fill",
                     ocr_confidence=round(min(s["confidence"] for s in states), 3) if states else None,
                     checkbox=states)
            if not sel and not amb:
                f["status"] = "empty"
            elif amb or (len(sel) > 1 and d.region.field_id in ("gender", "marital_status", "yes_no")):
                f["status"] = "needs_review"
                f["validation_messages"] = ["Ambiguous or multiple marks."]
            else:
                f["status"] = "auto_accepted" if f["ocr_confidence"] and f["ocr_confidence"] >= 0.5 else "needs_review"
            t_cb += t() - t0
        elif fd.field_type == "visual":
            ink = cb.ink_added(aligned_gray, tpl_gray, d.bbox_px)
            f.update(ink=round(ink, 4), normalized_value="<image>" if ink > 0.01 else None,
                     status="needs_review" if ink > 0.01 else "empty")
        else:
            ink = cb.ink_added(aligned_gray, tpl_gray, d.bbox_px)
            f["ink"] = round(ink, 4)
            if ink > INK_MIN and run_ocr and crop.size:
                t0 = t()
                k = text_dets.index(d) if d in text_dets else 0
                say("OCR", 0.55 + 0.35 * (k / max(1, len(text_dets))))
                src = cb.remove_grid_lines(crop) if d.region.cell_count else crop
                big = cv2.resize(src, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC) if src.shape[0] < 60 else src
                o = engine.process_text_crop(big, fd.language, fd.field_type)
                t_ocr += t() - t0
                t0 = t()
                norm = normalise(o.text, fd.validation)
                msgs = validate(norm, fd.validation)
                if not o.text:
                    status = "unreadable"
                elif o.confidence >= 0.75 and not msgs:
                    status = "auto_accepted"
                else:
                    status = "needs_review"
                f.update(raw_text=o.text, normalized_value=norm, ocr_confidence=round(o.confidence, 4),
                         engine=o.engine, status=status, validation_messages=msgs, ocr_raw=o.raw)
                t_val += t() - t0
            elif ink > INK_MIN:
                f["status"] = "needs_review"
        fields.append(f)
    rec.add("crops", t_crops * 1000, None, metrics={"crops": sum(1 for f in fields if f["crop"])},
            data={"crops": [{"region_id": f["region_id"], "crop": f["crop"], "field_id": f["field_id"]} for f in fields]})
    cbf = [f for f in fields if f["field_type"] == "checkbox_group"]
    rec.add("checkboxes", t_cb * 1000, cb_vis, metrics={"groups": len(cbf),
                                                        "selected": sum(1 for f in cbf if f["normalized_value"])})
    ocrf = [f for f in fields if f["engine"] == "easyocr"]
    rec.add("ocr", t_ocr * 1000, None, params={"engine": "easyocr", "languages": "en / ne+en by field"},
            metrics={"crops_read": len(ocrf), "skipped_empty": sum(1 for f in fields if f["field_type"] in ("text", "boxed_chars") and f["status"] == "empty"),
                     "mean_confidence": round(float(np.mean([f["ocr_confidence"] for f in ocrf])), 4) if ocrf else None})
    rec.add("validation", t_val * 1000, None,
            metrics={s: sum(1 for f in fields if f["status"] == s) for s in ("auto_accepted", "needs_review", "unreadable", "empty")})
    result["fields"] = fields
    result["template_id"], result["page_number"] = tid, pno
    result["total_ms"] = round((time.perf_counter() - t_page) * 1000, 1)
    _write_manifest(out_dir, result)
    return result


def _write_manifest(out_dir: Path, result: dict) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "manifest.json").write_text(json.dumps(result, ensure_ascii=False, default=str), encoding="utf-8")


def lab_rerun(img: np.ndarray, out_dir: Path, rel_root: Path, params: dict) -> dict[str, Any]:
    """Re-run the parameterised stages (preprocessing + identification) with new
    parameters, without OCR, into a separate folder so the saved run is untouched."""
    p = {**DEFAULT_PARAMS, **(params or {})}
    rec = StageRecorder(out_dir, rel_root)
    t0 = time.perf_counter()
    pre = preprocess_stages(img, rec, p)
    identify_stages(pre["page"], rec, p)
    return {"params": p, "stages": rec.stages, "total_ms": round((time.perf_counter() - t0) * 1000, 1)}
