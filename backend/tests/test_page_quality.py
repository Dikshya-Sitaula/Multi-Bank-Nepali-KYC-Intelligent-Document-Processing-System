"""Upload-time quality warnings."""
import cv2
import numpy as np

from app.services.preprocessing.steps import rotate_image
from app.services.quality.page_check import check_page, glare_fraction
from tests.cv_helpers import synthetic_form


def test_clean_page_has_no_warnings():
    rep = check_page(synthetic_form(1))
    assert rep.ok, rep.warnings


def test_low_resolution_warned():
    small = cv2.resize(synthetic_form(1), (500, 707), interpolation=cv2.INTER_AREA)
    assert "low_resolution" in check_page(small).codes


def test_blur_warned():
    blurred = cv2.GaussianBlur(synthetic_form(1), (0, 0), 6)
    assert "blur" in check_page(blurred).codes


def test_skew_warned():
    assert "skew" in check_page(rotate_image(synthetic_form(1), 8)).codes


def test_low_contrast_warned():
    faded = (synthetic_form(1).astype(np.float32) * 0.15 + 200).astype(np.uint8)
    assert "low_contrast" in check_page(faded).codes


def test_glare_detected_only_on_photo_like_paper():
    grey_paper = np.full((1000, 800), 190, np.uint8)
    cv2.circle(grey_paper, (400, 500), 120, 255, -1)
    assert glare_fraction(grey_paper) > 0.02
    assert glare_fraction(np.full((1000, 800), 255, np.uint8)) is None  # white scan: n/a


def test_thresholds_are_configurable():
    rep = check_page(synthetic_form(1), {"min_short_side_px": 5000})
    assert "low_resolution" in rep.codes
