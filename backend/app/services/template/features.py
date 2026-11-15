"""Local feature extraction and the on-disk feature cache for template pages.

WHY local features: a photographed form is rotated, scaled and seen in perspective.
SIFT/ORB keypoints are invariant to rotation and scale, and matching them between the
photo and each enrolled template page both identifies the page and gives the point
correspondences needed for the homography that aligns it.

Template features are generated (never hand-written) and cached in
templates/<id>/features/page_N_<detector>.npz, keyed by the page image hash and the
extraction parameters, so a changed page or parameter rebuilds the cache automatically.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from app.services.preprocessing.steps import resize_to_width, to_gray
from app.services.template.registry import TemplatePageRef, page_sha


@dataclass
class PageFeatures:
    points: np.ndarray        # (N, 2) float32 keypoint coordinates at work scale
    descriptors: np.ndarray   # (N, D) float32 (SIFT) or uint8 (ORB)
    scale: float              # work-scale / full-resolution scale factor
    full_size: tuple[int, int]  # (width, height) of the full-resolution image
    detector: str


def make_detector(detector: str, max_features: int):  # noqa: ANN201
    if detector == "sift":
        return cv2.SIFT_create(nfeatures=max_features)
    if detector == "orb":
        return cv2.ORB_create(nfeatures=max_features, scaleFactor=1.2, nlevels=8, fastThreshold=10)
    raise ValueError(f"unknown detector: {detector}")


def extract(img: np.ndarray, detector: str, work_width: int, max_features: int) -> PageFeatures:
    gray = to_gray(img)
    h, w = gray.shape[:2]
    small, scale = resize_to_width(gray, min(work_width, w) if w > work_width else work_width)
    # Local contrast normalisation makes features comparable between a crisp vector
    # rendering and an unevenly lit phone photo.
    small = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(small)
    kps, desc = make_detector(detector, max_features).detectAndCompute(small, None)
    if desc is None or not kps:
        dim, dtype = (128, np.float32) if detector == "sift" else (32, np.uint8)
        return PageFeatures(np.zeros((0, 2), np.float32), np.zeros((0, dim), dtype), scale, (w, h), detector)
    pts = np.array([k.pt for k in kps], np.float32)
    return PageFeatures(pts, desc, scale, (w, h), detector)


def _cache_path(ref: TemplatePageRef, detector: str) -> Path:
    return ref.image_path.parent.parent / "features" / f"page_{ref.page_number}_{detector}.npz"


_MEMORY: dict[tuple, PageFeatures] = {}


def template_features(ref: TemplatePageRef, detector: str, work_width: int, max_features: int) -> PageFeatures:
    """Load template features (memory, then disk cache), rebuilding them if the page
    image or the extraction parameters changed."""
    sha = page_sha(ref)
    mem_key = (str(ref.image_path), sha, detector, work_width, max_features)
    if mem_key in _MEMORY:
        return _MEMORY[mem_key]
    feats = _load_or_build(ref, sha, detector, work_width, max_features)
    _MEMORY[mem_key] = feats
    return feats


def _load_or_build(ref: TemplatePageRef, sha: str, detector: str, work_width: int, max_features: int) -> PageFeatures:
    path = _cache_path(ref, detector)
    if path.exists():
        try:
            z = np.load(path, allow_pickle=False)
            if (str(z["sha"]) == sha and int(z["work_width"]) == work_width
                    and int(z["max_features"]) == max_features):
                return PageFeatures(z["points"], z["descriptors"], float(z["scale"]),
                                    (int(z["full_w"]), int(z["full_h"])), detector)
        except (OSError, KeyError, ValueError):
            pass
    img = cv2.imread(str(ref.image_path), cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise FileNotFoundError(ref.image_path)
    feats = extract(img, detector, work_width, max_features)
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, points=feats.points, descriptors=feats.descriptors, scale=feats.scale,
                        full_w=feats.full_size[0], full_h=feats.full_size[1], sha=sha,
                        work_width=work_width, max_features=max_features)
    return feats
