"""Upload-time page quality check.

WHY: telling the employee "this photo is blurry, retake it" at upload time is cheaper than
discovering unreadable fields during review. Warnings are advisory; processing still runs.

Each warning comes from a measured number compared with a threshold in config/app.yaml.
The glare check is a heuristic and is described as such.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import cv2
import numpy as np

from app.core.app_config import section
from app.services.preprocessing.steps import estimate_skew
from app.services.quality.metrics import ink_contrast, sharpness_laplacian_var, to_gray


@dataclass
class QualityReport:
    metrics: dict[str, Any]
    warnings: list[str] = field(default_factory=list)
    codes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.codes


def glare_fraction(gray: np.ndarray) -> float | None:
    """Fraction of the page covered by large saturated blobs that are clearly brighter
    than the surrounding paper.

    Returns None for scan-like images whose paper is already near white (the check is
    meaningless there). Heuristic: specular glare in a phone photo is a saturated patch
    on paper that is otherwise grey-ish (around 170-240)."""
    paper = float(np.median(gray))
    if paper >= 245:
        return None
    sat = (cv2.GaussianBlur(gray, (9, 9), 0) >= 250).astype(np.uint8)
    n, _, stats, _ = cv2.connectedComponentsWithStats(sat, connectivity=8)
    min_blob = gray.size * 0.001
    area = sum(int(stats[i, cv2.CC_STAT_AREA]) for i in range(1, n) if stats[i, cv2.CC_STAT_AREA] >= min_blob)
    return area / float(gray.size)


def check_page(img: np.ndarray, overrides: dict[str, Any] | None = None) -> QualityReport:
    cfg = section("quality", overrides)
    gray = to_gray(img)
    h, w = gray.shape[:2]
    sharp = sharpness_laplacian_var(gray)
    skew, _ = estimate_skew(img)
    glare = glare_fraction(gray)
    contrast = ink_contrast(gray)
    report = QualityReport(metrics={
        "width_px": w,
        "height_px": h,
        "sharpness_laplacian_var": round(sharp, 2),
        "skew_deg": None if skew is None else round(skew, 2),
        "glare_fraction": None if glare is None else round(glare, 4),
        "ink_contrast": round(contrast, 2),
    })

    def warn(code: str, msg: str) -> None:
        report.codes.append(code)
        report.warnings.append(msg)

    if min(h, w) < cfg["min_short_side_px"]:
        warn("low_resolution", f"Low resolution ({w}x{h} px). Small handwriting may be unreadable; "
                               f"use at least {cfg['min_short_side_px']} px on the short side.")
    if sharp < cfg["min_sharpness"]:
        warn("blur", "The page looks blurry. Hold the phone steady and make sure it is in focus.")
    if skew is not None and abs(skew) > cfg["max_skew_deg"]:
        warn("skew", f"The page is tilted by about {abs(skew):.1f} degrees. It will be straightened, "
                     "but a straighter photo gives better results.")
    if glare is not None and glare > cfg["max_glare_fraction"]:
        warn("glare", "Bright glare detected on the page. Avoid direct light or flash reflections.")
    if contrast < cfg["min_ink_contrast"]:
        warn("low_contrast", "Very low contrast between ink and paper. Improve the lighting.")
    return report
