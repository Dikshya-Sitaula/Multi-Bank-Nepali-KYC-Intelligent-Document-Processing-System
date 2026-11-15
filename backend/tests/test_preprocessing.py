"""OpenCV preprocessing steps and pipeline."""
import cv2
import numpy as np
import pytest

from app.services.preprocessing import steps
from app.services.preprocessing.pipeline import preprocess
from tests.cv_helpers import H, W, place_on_background, synthetic_form

ALL_OFF = {
    "orientation": {"enabled": False}, "boundary": {"enabled": False}, "perspective": {"enabled": False},
    "deskew": {"enabled": False}, "denoise": {"method": "none"}, "contrast": {"method": "none"},
    "threshold": {"enabled": False}, "target_width": W,
}


def test_rotate_to_portrait():
    land = np.zeros((100, 300, 3), np.uint8)
    out, deg = steps.rotate_to_portrait(land)
    assert deg == 90 and out.shape[:2] == (300, 100)
    port, deg = steps.rotate_to_portrait(np.zeros((300, 100, 3), np.uint8))
    assert deg == 0 and port.shape[:2] == (300, 100)


@pytest.mark.parametrize("angle", [0.0, 7.0, -12.0])
def test_page_quad_detected_in_photo(angle):
    photo, true_corners = place_on_background(synthetic_form(1), angle_deg=angle, seed=3)
    quad, info = steps.detect_page_quad(photo)
    assert quad is not None, info
    err = np.linalg.norm(steps.order_quad(quad) - steps.order_quad(true_corners), axis=1).max()
    assert err < 0.02 * photo.shape[1], (err, info)


def test_flat_scan_has_no_quad():
    quad, info = steps.detect_page_quad(synthetic_form(2))
    assert quad is None


@pytest.mark.parametrize("angle", [3.0, -4.5])
def test_skew_estimated_and_corrected(angle):
    page = synthetic_form(5)
    tilted = steps.rotate_image(page, angle)
    est, n = steps.estimate_skew(tilted)
    assert est is not None and n >= 3
    assert abs(est - angle) < 0.3
    fixed = steps.rotate_image(tilted, -est)
    residual, _ = steps.estimate_skew(fixed)
    assert residual is None or abs(residual) < 0.3


def test_clahe_keeps_ink_colour():
    img = np.full((200, 200, 3), 230, np.uint8)
    cv2.line(img, (10, 100), (190, 100), (200, 60, 20), 4)  # blue ink (BGR)
    out = steps.enhance_contrast(img)
    b, g, r = out[100, 100].astype(int)
    assert b > r + 60  # still clearly blue


def test_threshold_is_binary():
    out = steps.adaptive_threshold(synthetic_form(1))
    assert out.ndim == 2 and set(np.unique(out)) <= {0, 255}


def test_all_steps_can_be_disabled():
    page = synthetic_form(1)
    res = preprocess(page, ALL_OFF)
    assert np.array_equal(res.image, page)
    applied = {s.name for s in res.steps if s.applied}
    assert applied == {"resize"}
    assert np.allclose(res.transform, np.eye(3))


def test_pipeline_flattens_photo_and_tracks_transform():
    photo, corners = place_on_background(synthetic_form(1), angle_deg=6.0, seed=1)
    res = preprocess(photo, {"target_width": W})
    h, w = res.image.shape[:2]
    assert w == W
    assert abs(h / w - H / W) < 0.06  # A4 aspect recovered
    mapped = cv2.perspectiveTransform(steps.order_quad(corners).reshape(-1, 1, 2), res.transform.astype(np.float32))
    expected = np.array([[0, 0], [w, 0], [w, h], [0, h]], np.float32)
    assert np.linalg.norm(mapped.reshape(-1, 2) - expected, axis=1).max() < 0.03 * w
    assert res.page_quad is not None
    assert all(s.ms >= 0 for s in res.steps)


def test_debug_images_only_on_request():
    page = synthetic_form(1)
    assert all(s.image is None for s in preprocess(page).steps)
    dbg = preprocess(page, keep_debug=True)
    names = [s.name for s in dbg.steps if s.image is not None]
    for expected in ("original", "grayscale", "edges", "boundary", "deskew", "contrast"):
        assert expected in names


def test_decode_applies_exif_orientation():
    from io import BytesIO

    from PIL import Image

    im = Image.new("RGB", (40, 20), (255, 0, 0))
    exif = Image.Exif()
    exif[0x0112] = 6  # rotate 90 CW on display
    buf = BytesIO()
    im.save(buf, format="JPEG", exif=exif)
    out = steps.decode_image_bytes(buf.getvalue())
    assert out.shape[:2] == (40, 20)
