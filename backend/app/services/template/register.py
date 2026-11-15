"""Template registration: warp an identified page onto its template canvas.

WHY: after registration, pixel (x, y) on the aligned page corresponds to (x, y) on the
blank template. That lets every YOLO detection be resolved to a specific question,
applicant or table row in template.json, and it is what the "template-alignment-only"
baseline relies on.

Steps: feature homography (from identification) -> optional ECC refinement for sub-pixel
accuracy -> warp -> measure alignment quality.

Registration confidence = printed-structure overlap: the fraction of the template's dark
printed pixels (lines, boxes, labels) that land on dark pixels of the aligned page within
a small tolerance. It measures alignment directly and is easy to explain; handwriting on
the filled page can only add dark pixels, so it does not lower the score.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from app.core.app_config import section
from app.services.preprocessing.steps import resize_to_width, to_gray

_OVERLAP_WIDTH = 1240  # half of template width; enough to measure line overlap


@dataclass
class RegistrationResult:
    aligned: np.ndarray            # page warped into the template canvas (template size)
    homography: np.ndarray         # final input full-res -> template full-res
    overlap: float                 # printed-structure overlap in [0, 1]
    refined: bool
    ms: float

    def to_dict(self) -> dict[str, Any]:
        return {"homography": self.homography.tolist(), "overlap": round(self.overlap, 4),
                "refined": self.refined, "ms": round(self.ms, 1)}


def _dark_mask(gray: np.ndarray) -> np.ndarray:
    return cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 31, 15)


@lru_cache(maxsize=64)
def _template_structure(path: Path, mtime_ns: int) -> tuple[np.ndarray, np.ndarray]:
    """(work-size template gray, printed-structure mask) cached per template page."""
    gray = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    small, _ = resize_to_width(gray, _OVERLAP_WIDTH)
    return small, _dark_mask(small)


def structure_overlap(aligned: np.ndarray, template_path: Path, tolerance_px: int) -> float:
    _, tmask = _template_structure(template_path, template_path.stat().st_mtime_ns)
    small, _ = resize_to_width(to_gray(aligned), _OVERLAP_WIDTH)
    amask = _dark_mask(small)
    k = 2 * max(1, tolerance_px // 2) + 1
    amask = cv2.dilate(amask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
    t_on = tmask > 0
    total = int(t_on.sum())
    return float((amask[t_on] > 0).sum()) / total if total else 0.0


def _ecc_refine(aligned_gray: np.ndarray, template_gray: np.ndarray, cfg: dict) -> np.ndarray | None:
    """Estimate a small residual homography between the aligned page and the template
    (in template full-res coordinates). Returns None if ECC does not converge."""
    tw = template_gray.shape[1]
    work = cfg["ecc_work_width"]
    s = work / float(tw)
    a, _ = resize_to_width(aligned_gray, work)
    t, _ = resize_to_width(template_gray, work)
    a = cv2.GaussianBlur(a, (5, 5), 0).astype(np.float32)
    t = cv2.GaussianBlur(t, (5, 5), 0).astype(np.float32)
    warp = np.eye(3, dtype=np.float32)
    crit = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, cfg["ecc_iterations"], cfg["ecc_epsilon"])
    try:
        _, warp = cv2.findTransformECC(t, a, warp, cv2.MOTION_HOMOGRAPHY, crit, None, 5)
    except cv2.error:
        return None
    # warp maps template(work) coords -> aligned(work) coords. Convert to full-res and invert
    # so it maps aligned -> template, which is what we compose with.
    sm = np.diag([s, s, 1.0])
    w_full = np.linalg.inv(sm) @ warp.astype(np.float64) @ sm
    # Refuse large "corrections": ECC is for sub-pixel polishing, not for fixing a wrong match.
    corners = np.array([[[0, 0], [tw, 0], [tw, template_gray.shape[0]], [0, template_gray.shape[0]]]], np.float32)
    moved = cv2.perspectiveTransform(corners, w_full.astype(np.float32))
    if float(np.abs(moved - corners).max()) > 0.02 * tw:
        return None
    return np.linalg.inv(w_full)


def register(img: np.ndarray, homography: np.ndarray, template_path: Path,
             overrides: dict[str, Any] | None = None) -> RegistrationResult:
    cfg = section("registration", overrides)
    t0 = time.perf_counter()
    tpl_gray = cv2.imread(str(template_path), cv2.IMREAD_GRAYSCALE)
    if tpl_gray is None:
        raise FileNotFoundError(template_path)
    th, tw = tpl_gray.shape[:2]
    H = homography.astype(np.float64)
    aligned = cv2.warpPerspective(img, H, (tw, th), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    refined = False
    if cfg["refine_ecc"]:
        corr = _ecc_refine(to_gray(aligned), tpl_gray, cfg)
        if corr is not None:
            H_ref = corr @ H
            H_ref /= H_ref[2, 2]
            cand = cv2.warpPerspective(img, H_ref, (tw, th), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
            # Keep the refinement only if it actually improves alignment.
            if structure_overlap(cand, template_path, cfg["overlap_tolerance_px"]) >= \
                    structure_overlap(aligned, template_path, cfg["overlap_tolerance_px"]):
                aligned, H, refined = cand, H_ref, True
    overlap = structure_overlap(aligned, template_path, cfg["overlap_tolerance_px"])
    return RegistrationResult(aligned, H, overlap, refined, (time.perf_counter() - t0) * 1000)


def overlay_debug(aligned: np.ndarray, template_path: Path) -> np.ndarray:
    """Template printed structure in red over the aligned page in grey, for visual checks."""
    tpl = cv2.imread(str(template_path), cv2.IMREAD_GRAYSCALE)
    a = to_gray(aligned)
    out = cv2.cvtColor(a, cv2.COLOR_GRAY2BGR)
    mask = _dark_mask(tpl) > 0
    out[mask] = (0.35 * out[mask] + 0.65 * np.array([0, 0, 255])).astype(np.uint8)
    return out
