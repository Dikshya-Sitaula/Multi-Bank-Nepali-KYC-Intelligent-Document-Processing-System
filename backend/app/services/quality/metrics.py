"""Page image-quality metrics.

WHY: a blurry, low-contrast or low-resolution page produces bad OCR. Measuring quality
up front lets the system (a) warn the user at upload time and (b) decide which blank
source forms are clean enough to generate training data from.

All metrics are computed on the real image; nothing is estimated or hard-coded.
"""
from __future__ import annotations

import cv2
import numpy as np

# Sharpness is measured on a fixed-width resize so that values are comparable
# across images of different resolution.
SHARPNESS_REF_WIDTH = 1600


def to_gray(img: np.ndarray) -> np.ndarray:
    """Convert BGR or BGRA to single-channel grayscale; pass grayscale through."""
    if img.ndim == 2:
        return img
    if img.shape[2] == 4:
        return cv2.cvtColor(img, cv2.COLOR_BGRA2GRAY)
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


def sharpness_laplacian_var(gray: np.ndarray) -> float:
    """Variance of the Laplacian: high when the image has crisp edges, low when blurry."""
    h, w = gray.shape[:2]
    if w > SHARPNESS_REF_WIDTH:
        scale = SHARPNESS_REF_WIDTH / w
        gray = cv2.resize(gray, (SHARPNESS_REF_WIDTH, max(1, int(h * scale))),
                          interpolation=cv2.INTER_AREA)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def contrast_rms(gray: np.ndarray) -> float:
    """RMS contrast = standard deviation of pixel intensities (0-255 scale)."""
    return float(gray.std())


def ink_contrast(gray: np.ndarray) -> float:
    """Distance between paper (median grey) and ink (0.1th percentile grey).

    Unlike RMS contrast, this does not drop just because a page is mostly blank
    or printed in a light colour (e.g. orange ink on white). The low percentile is
    used so that sparse pages, with very little ink, are still measured on ink."""
    lo, hi = np.percentile(gray, [0.1, 50])
    return float(hi - lo)


def glare_fraction(gray: np.ndarray, level: int = 250) -> float:
    """Fraction of pixels inside smoothed near-saturated regions.

    Blank paper is also bright, so this is a warning signal for the upload screen,
    not a verdict on its own."""
    blurred = cv2.GaussianBlur(gray, (21, 21), 0)
    return float((blurred >= level).mean())


def page_quality_metrics(img: np.ndarray) -> dict:
    """All metrics for one page image (BGR or grayscale numpy array)."""
    gray = to_gray(img)
    h, w = gray.shape[:2]
    return {
        "width_px": int(w),
        "height_px": int(h),
        "sharpness_laplacian_var": round(sharpness_laplacian_var(gray), 2),
        "contrast_rms": round(contrast_rms(gray), 2),
        "ink_contrast": round(ink_contrast(gray), 2),
        "mean_intensity": round(float(gray.mean()), 2),
        "glare_fraction": round(glare_fraction(gray), 4),
    }
