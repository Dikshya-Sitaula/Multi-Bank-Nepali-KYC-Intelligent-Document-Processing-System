"""Template identification and registration on synthetic 'bank forms' built in the test."""
from pathlib import Path

import cv2
import numpy as np
import pytest

from app.services.datasets.phone_sim import simulate_capture
from app.services.preprocessing.pipeline import preprocess
from app.services.template.identify import identify
from app.services.template.register import register
from app.services.template.registry import all_template_pages, discover_templates
from tests.cv_helpers import W, synthetic_form

IDENT = {"work_width": 800, "full_confidence_inliers": 150}
PRE = {"target_width": W}


@pytest.fixture(scope="module")
def tpl_dir(tmp_path_factory) -> Path:
    """Three fake banks with two pages each, laid out like templates/<id>/pages/."""
    root = tmp_path_factory.mktemp("templates")
    for t, seeds in {"bank_a": (11, 12), "bank_b": (21, 22), "bank_c": (31, 32)}.items():
        pages = root / t / "pages"
        pages.mkdir(parents=True)
        for i, seed in enumerate(seeds, start=1):
            cv2.imwrite(str(pages / f"page_{i}.png"), synthetic_form(seed))
    return root


def test_registry_discovers_folders(tpl_dir):
    infos = discover_templates(tpl_dir)
    assert [t.template_id for t in infos] == ["bank_a", "bank_b", "bank_c"]
    assert all(len(t.pages) == 2 for t in infos)
    assert len(all_template_pages(tpl_dir, ["bank_b"])) == 2


@pytest.mark.parametrize("tid,page", [("bank_a", 1), ("bank_b", 2), ("bank_c", 1)])
def test_identifies_simulated_photo(tpl_dir, tid, page):
    refs = all_template_pages(tpl_dir)
    ref = next(r for r in refs if r.template_id == tid and r.page_number == page)
    img = cv2.imread(str(ref.image_path))
    cap = simulate_capture(img, np.random.default_rng(page), "medium", out_long_side=2000)
    pre = preprocess(cap.image, PRE)
    res = identify(pre.image, IDENT, pages=refs)
    assert res.status == "identified", res.reason
    assert (res.template_id, res.page_number) == (tid, page)
    assert 0 < res.confidence <= 1

    reg = register(pre.image, res.homography, ref.image_path)
    assert reg.aligned.shape[:2] == img.shape[:2]
    assert reg.overlap > 0.85
    # Ground-truth alignment error on a grid of template points.
    w, h = img.shape[1], img.shape[0]
    pts = np.array([[[x, y]] for x in np.linspace(0.1 * w, 0.9 * w, 5) for y in np.linspace(0.1 * h, 0.9 * h, 5)],
                   np.float32)
    est = cv2.perspectiveTransform(cv2.perspectiveTransform(pts, cap.homography.astype(np.float32)),
                                   (reg.homography @ pre.transform).astype(np.float32))
    assert np.linalg.norm((est - pts).reshape(-1, 2), axis=1).max() < 6.0


def test_unknown_form_rejected(tpl_dir):
    other = synthetic_form(999)
    cap = simulate_capture(other, np.random.default_rng(0), "light", out_long_side=2000)
    res = identify(preprocess(cap.image, PRE).image, IDENT, pages=all_template_pages(tpl_dir))
    assert res.status == "unknown"
    assert res.template_id is None and res.confidence == 0.0
    assert res.reason


def test_blank_image_is_unknown(tpl_dir):
    res = identify(np.full((1754, 1240, 3), 255, np.uint8), IDENT, pages=all_template_pages(tpl_dir))
    assert res.status == "unknown"


def test_no_templates_is_unknown():
    res = identify(synthetic_form(1), IDENT, pages=[])
    assert res.status == "unknown" and "No templates" in res.reason


def test_duplicate_pages_lower_confidence(tmp_path):
    for t in ("x", "y"):
        (tmp_path / t / "pages").mkdir(parents=True)
        cv2.imwrite(str(tmp_path / t / "pages" / "page_1.png"), synthetic_form(77))
    (tmp_path / "z" / "pages").mkdir(parents=True)
    cv2.imwrite(str(tmp_path / "z" / "pages" / "page_1.png"), synthetic_form(78))
    refs = all_template_pages(tmp_path)
    page = synthetic_form(77)
    dup = identify(page, IDENT, pages=refs)
    unique = identify(synthetic_form(78), IDENT, pages=refs)
    assert dup.status == unique.status == "identified"
    assert dup.confidence < unique.confidence
