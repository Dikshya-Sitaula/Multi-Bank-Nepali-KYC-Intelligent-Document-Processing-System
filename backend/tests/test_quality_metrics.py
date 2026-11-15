"""Tests for page quality metrics using synthetic images built in the test itself."""
import cv2
import numpy as np

from app.services.quality.metrics import ink_contrast, page_quality_metrics, sharpness_laplacian_var


def _text_page(color=0) -> np.ndarray:
    img = np.full((1200, 900), 255, np.uint8)
    for y in range(100, 1100, 60):
        cv2.putText(img, "SAMPLE FORM LINE 123", (50, y), cv2.FONT_HERSHEY_SIMPLEX, 1.2, color, 2)
    return img


def test_blur_lowers_sharpness():
    page = _text_page()
    blurred = cv2.GaussianBlur(page, (15, 15), 0)
    assert sharpness_laplacian_var(blurred) < sharpness_laplacian_var(page) / 3


def test_ink_contrast_survives_sparse_and_light_ink():
    # Light grey ink (like orange in grayscale) on a mostly blank page.
    sparse = np.full((1200, 900), 255, np.uint8)
    cv2.putText(sparse, "Right  Left", (300, 600), cv2.FONT_HERSHEY_SIMPLEX, 1.0, 150, 2)
    assert ink_contrast(sparse) >= 80


def test_blank_page_has_no_ink_contrast():
    assert ink_contrast(np.full((500, 500), 255, np.uint8)) == 0


def test_metrics_accept_bgr_and_report_size():
    bgr = cv2.cvtColor(_text_page(), cv2.COLOR_GRAY2BGR)
    m = page_quality_metrics(bgr)
    assert (m["width_px"], m["height_px"]) == (900, 1200)
    assert set(m) >= {"sharpness_laplacian_var", "contrast_rms", "ink_contrast", "glare_fraction"}
