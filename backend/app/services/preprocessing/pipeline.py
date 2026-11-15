"""Page preprocessing pipeline.

Order and WHY:
1. orientation   - portrait pages; EXIF was already applied when decoding.
2. boundary      - find the paper in a phone photo (background, desk, hands).
3. perspective   - flatten the photographed page to a rectangle.
4. deskew        - remove small residual rotation using the form's printed lines.
5. resize        - bring every page to the template scale (A4 at 300 DPI width).
6. denoise       - mild; strong denoising erases thin pen strokes.
7. contrast      - CLAHE on lightness only, which keeps blue vs black ink distinguishable.
8. threshold     - optional and off by default; kept for experiments in the Pipeline Lab.

Every step can be disabled or re-parameterised through `overrides` (same shape as the
`preprocessing` section of config/app.yaml). With `keep_debug=True` each intermediate
image is returned so the Pipeline Lab can show the page at every stage.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import cv2
import numpy as np

from app.core.app_config import section
from app.services.preprocessing import steps


@dataclass
class StepRecord:
    name: str
    applied: bool
    ms: float
    details: dict[str, Any] = field(default_factory=dict)
    image: np.ndarray | None = None  # only with keep_debug


@dataclass
class PreprocessResult:
    image: np.ndarray                 # final processed page (BGR, or gray if thresholded)
    steps: list[StepRecord]
    page_quad: list[list[float]] | None   # paper corners in the original image, if found
    rotation_deg: int                 # coarse rotation applied (0 or 90)
    skew_deg: float | None            # residual skew that was measured
    params: dict[str, Any]
    # 3x3 matrix mapping original-image pixel coords -> processed-image pixel coords.
    # Used to draw boxes found on the processed page back onto the original photo, and
    # to measure registration error against simulated ground truth.
    transform: np.ndarray = field(default_factory=lambda: np.eye(3))

    def timings(self) -> dict[str, float]:
        return {s.name: s.ms for s in self.steps}


def preprocess(img: np.ndarray, overrides: dict[str, Any] | None = None, keep_debug: bool = False) -> PreprocessResult:
    cfg = section("preprocessing", overrides)
    records: list[StepRecord] = []

    def run(name: str, enabled: bool, fn, *args, **kwargs):  # noqa: ANN001, ANN202
        t0 = time.perf_counter()
        out = fn(*args, **kwargs) if enabled else None
        ms = round((time.perf_counter() - t0) * 1000, 2)
        return out, ms

    current = img
    M = np.eye(3)  # accumulated original -> current transform
    if keep_debug:
        records.append(StepRecord("original", True, 0.0, {"size": [img.shape[1], img.shape[0]]}, img))

    # 1. orientation
    out, ms = run("orientation", cfg["orientation"]["enabled"], steps.rotate_to_portrait, current)
    rotation = 0
    if out is not None:
        h0 = current.shape[0]
        current, rotation = out
        if rotation == 90:  # cv2.ROTATE_90_CLOCKWISE: (x, y) -> (h - 1 - y, x)
            M = np.array([[0, -1, h0 - 1], [1, 0, 0], [0, 0, 1]], float) @ M
    records.append(StepRecord("orientation", out is not None, ms, {"rotated_deg": rotation},
                              current if keep_debug else None))

    if keep_debug:
        records.append(StepRecord("grayscale", True, 0.0, {}, steps.to_gray(current)))

    # 2. boundary
    b = cfg["boundary"]
    out, ms = run("boundary", b["enabled"], steps.detect_page_quad, current, b["work_width"],
                  b["min_area_fraction"], b["canny_low"], b["canny_high"])
    quad = None
    details: dict[str, Any] = {}
    if out is not None:
        quad, details = out
    debug_img = None
    if keep_debug:
        debug_img = current.copy()
        if quad is not None:
            cv2.polylines(debug_img, [quad.astype(np.int32)], True, (0, 0, 255), max(3, current.shape[1] // 400))
        small, _ = steps.resize_to_width(steps.to_gray(current), min(b["work_width"], current.shape[1]))
        records.append(StepRecord("edges", True, 0.0, {}, cv2.Canny(cv2.GaussianBlur(small, (5, 5), 0),
                                                                      b["canny_low"], b["canny_high"])))
    records.append(StepRecord("boundary", out is not None, ms,
                              {"found": quad is not None, **{k: v for k, v in details.items() if k != "work_scale"}},
                              debug_img))

    # 3. perspective
    do_persp = cfg["perspective"]["enabled"] and quad is not None
    out, ms = run("perspective", do_persp, steps.warp_quad_to_rect, current, quad if quad is not None else np.zeros((4, 2)))
    if out is not None:
        current = out[0]
        M = out[1].astype(float) @ M
    records.append(StepRecord("perspective", out is not None, ms,
                              {"size": [current.shape[1], current.shape[0]]}, current if keep_debug else None))

    # 4. deskew
    d = cfg["deskew"]
    out, ms = run("deskew", d["enabled"], steps.estimate_skew, current, d["max_angle_deg"], d["min_line_fraction"])
    skew = None
    lines_used = 0
    if out is not None:
        skew, lines_used = out
        if skew is not None and abs(skew) >= 0.1:
            t0 = time.perf_counter()
            rot = cv2.getRotationMatrix2D((current.shape[1] / 2, current.shape[0] / 2), -skew, 1.0)
            current = steps.rotate_image(current, -skew)
            M = np.vstack([rot, [0, 0, 1]]) @ M
            ms += round((time.perf_counter() - t0) * 1000, 2)
    records.append(StepRecord("deskew", out is not None, ms,
                              {"skew_deg": None if skew is None else round(skew, 3), "lines_used": lines_used},
                              current if keep_debug else None))

    # 5. resize to template scale
    before_hw = current.shape[:2]
    out, ms = run("resize", True, steps.resize_to_width, current, int(cfg["target_width"]))
    current, scale = out
    sx, sy = current.shape[1] / before_hw[1], current.shape[0] / before_hw[0]
    M = np.diag([sx, sy, 1.0]) @ M
    records.append(StepRecord("resize", True, ms, {"scale": round(scale, 4)}, current if keep_debug else None))

    # 6. denoise
    n = cfg["denoise"]
    out, ms = run("denoise", n["method"] != "none", steps.denoise, current, n["method"], n["median_ksize"], n["nlmeans_h"])
    if out is not None:
        current = out
    records.append(StepRecord("denoise", out is not None, ms, {"method": n["method"]}, current if keep_debug else None))

    # 7. contrast
    c = cfg["contrast"]
    out, ms = run("contrast", c["method"] != "none", steps.enhance_contrast, current, c["method"], c["clahe_clip"], c["clahe_tile"])
    if out is not None:
        current = out
    records.append(StepRecord("contrast", out is not None, ms, {"method": c["method"]}, current if keep_debug else None))

    # 8. optional threshold
    t = cfg["threshold"]
    out, ms = run("threshold", t["enabled"], steps.adaptive_threshold, current, t["block_size"], t["c"])
    if out is not None:
        current = out
    records.append(StepRecord("threshold", out is not None, ms, {}, current if keep_debug else None))

    return PreprocessResult(
        image=current,
        steps=records,
        page_quad=None if quad is None else quad.round(2).tolist(),
        rotation_deg=rotation,
        skew_deg=None if skew is None else round(skew, 3),
        params=cfg,
        transform=M,
    )
