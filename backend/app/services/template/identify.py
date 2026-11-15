"""Template identification: which bank form, and which page, is this image?

Method (classical CV, no training needed):
1. extract local features from the preprocessed page;
2. for every enrolled template page, match descriptors (k-NN with Lowe's ratio test);
3. for the `shortlist` pages with the most ratio-test matches, fit a homography with
   RANSAC and count geometrically consistent inliers (RANSAC is the expensive part, and
   a page with few raw matches cannot win, so it is not fitted);
4. the page with the most inliers wins if it passes the minimum and a sanity check on
   the recovered geometry; otherwise the result is "unknown form" (a valid outcome).

Confidence is a documented score, not a calibrated probability:
    strength        = min(1, best_inliers / full_confidence_inliers)
    distinctiveness = 1 - second_best_inliers / best_inliers
    confidence      = strength * (0.5 + 0.5 * distinctiveness)
so a page that matches strongly but is nearly identical to another enrolled page
(e.g. the two joint-applicant pages of the Nabil form) is reported with lower confidence.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import cv2
import numpy as np

from app.core.app_config import section
from app.services.template.features import PageFeatures, extract, template_features
from app.services.template.registry import TemplatePageRef, all_template_pages


@dataclass
class Candidate:
    template_id: str
    page_number: int
    good_matches: int
    inliers: int
    homography_full: np.ndarray | None   # input full-res -> template full-res
    template_size: tuple[int, int]
    plausible: bool


@dataclass
class IdentificationResult:
    status: str                          # "identified" | "unknown"
    template_id: str | None
    page_number: int | None
    confidence: float
    inliers: int
    homography: np.ndarray | None        # input full-res -> template full-res
    template_size: tuple[int, int] | None
    candidates: list[dict[str, Any]] = field(default_factory=list)
    ms: float = 0.0
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "template_id": self.template_id,
            "page_number": self.page_number,
            "confidence": round(self.confidence, 4),
            "inliers": self.inliers,
            "homography": None if self.homography is None else self.homography.tolist(),
            "template_size": self.template_size,
            "candidates": self.candidates,
            "ms": round(self.ms, 1),
            "reason": self.reason,
        }


def _matcher(detector: str):  # noqa: ANN202
    # Brute force is exact and, at a few thousand descriptors, faster than building a
    # FLANN index per template page.
    return cv2.BFMatcher(cv2.NORM_L2 if detector == "sift" else cv2.NORM_HAMMING)


def _scale_matrix(s: float) -> np.ndarray:
    return np.diag([s, s, 1.0])


def _plausible(h_full: np.ndarray, in_size: tuple[int, int], t_size: tuple[int, int], cfg: dict) -> bool:
    """Reject degenerate homographies (folded, mirrored or wildly scaled)."""
    if not np.isfinite(h_full).all() or abs(np.linalg.det(h_full[:2, :2])) < 1e-8:
        return False
    tw, th = t_size
    # Project the template rectangle back into the input image and check it is a convex,
    # non-mirrored quadrilateral of reasonable size.
    try:
        inv = np.linalg.inv(h_full)
    except np.linalg.LinAlgError:
        return False
    corners = np.array([[[0, 0], [tw, 0], [tw, th], [0, th]]], np.float32)
    quad = cv2.perspectiveTransform(corners, inv)[0]
    if not cv2.isContourConvex(quad.astype(np.float32)):
        return False
    signed = 0.5 * float(np.sum(quad[:, 0] * np.roll(quad[:, 1], -1) - np.roll(quad[:, 0], -1) * quad[:, 1]))
    if signed <= 0:  # mirrored
        return False
    iw, ih = in_size
    ratio = signed / float(iw * ih)
    return cfg["min_page_area_ratio"] <= ratio <= cfg["max_page_area_ratio"]


def ratio_matches(q: PageFeatures, t: PageFeatures, ratio: float) -> list:
    if len(q.points) < 2 or len(t.points) < 2:
        return []
    knn = _matcher(q.detector).knnMatch(q.descriptors, t.descriptors, k=2)
    good = [m[0] for m in knn if len(m) == 2 and m[0].distance < ratio * m[1].distance]
    # One-to-one: keep only the best match per template keypoint. Without this, repeated
    # glyphs or cells can send many photo keypoints to the same template keypoint, and
    # RANSAC can then "explain" them with a degenerate, collapsing homography.
    best: dict[int, cv2.DMatch] = {}
    for m in good:
        if m.trainIdx not in best or m.distance < best[m.trainIdx].distance:
            best[m.trainIdx] = m
    return list(best.values())


def match_page(q: PageFeatures, t: PageFeatures, cfg: dict, good: list | None = None) -> Candidate | None:
    if len(q.points) < 4 or len(t.points) < 4:
        return None
    if good is None:
        good = ratio_matches(q, t, cfg["ratio_test"])
    if len(good) < max(4, cfg["min_inliers"]):
        return Candidate("", 0, len(good), 0, None, t.full_size, False)
    src = q.points[[m.queryIdx for m in good]].reshape(-1, 1, 2)
    dst = t.points[[m.trainIdx for m in good]].reshape(-1, 1, 2)
    h_work, mask = cv2.findHomography(src, dst, cv2.USAC_MAGSAC, cfg["ransac_reproj_px"], maxIters=3000, confidence=0.995)
    if h_work is None:
        return Candidate("", 0, len(good), 0, None, t.full_size, False)
    inliers = int(mask.sum())
    h_full = np.linalg.inv(_scale_matrix(t.scale)) @ h_work @ _scale_matrix(q.scale)
    h_full /= h_full[2, 2]
    plausible = _plausible(h_full, q.full_size, t.full_size, cfg)
    return Candidate("", 0, len(good), inliers, h_full, t.full_size, plausible)


def identify(img: np.ndarray, overrides: dict[str, Any] | None = None,
             pages: list[TemplatePageRef] | None = None) -> IdentificationResult:
    cfg = section("identification", overrides)
    t0 = time.perf_counter()
    refs = pages if pages is not None else all_template_pages()
    if not refs:
        return IdentificationResult("unknown", None, None, 0.0, 0, None, None, [], 0.0,
                                    "No templates are enrolled.")
    q = extract(img, cfg["detector"], cfg["work_width"], cfg["max_features"])
    scored = []
    for ref in refs:
        t = template_features(ref, cfg["detector"], cfg["work_width"], cfg["max_features"])
        scored.append((ref, t, ratio_matches(q, t, cfg["ratio_test"])))
    scored.sort(key=lambda x: len(x[2]), reverse=True)
    cands: list[Candidate] = []
    for ref, t, good in scored[: cfg["shortlist"]]:
        c = match_page(q, t, cfg, good)
        if c is None:
            continue
        c.template_id, c.page_number = ref.template_id, ref.page_number
        cands.append(c)

    ranked = sorted(cands, key=lambda c: (c.plausible, c.inliers), reverse=True)
    summary = [{"template_id": c.template_id, "page_number": c.page_number, "inliers": c.inliers,
                "good_matches": c.good_matches, "plausible": c.plausible} for c in ranked]
    ms = (time.perf_counter() - t0) * 1000
    best = ranked[0] if ranked else None
    if best is None or not best.plausible or best.inliers < cfg["min_inliers"]:
        reason = ("No enrolled page matched with enough consistent features "
                  f"(best: {best.inliers if best else 0} inliers, minimum {cfg['min_inliers']}).")
        return IdentificationResult("unknown", None, None, 0.0, best.inliers if best else 0,
                                    None, None, summary, ms, reason)
    second = next((c.inliers for c in ranked[1:] if c.plausible), 0)
    strength = min(1.0, best.inliers / float(cfg["full_confidence_inliers"]))
    distinct = 1.0 - second / float(best.inliers)
    conf = strength * (0.5 + 0.5 * distinct)
    return IdentificationResult("identified", best.template_id, best.page_number, conf, best.inliers,
                                best.homography_full, best.template_size, summary, ms)


def draw_matches(img: np.ndarray, ref: TemplatePageRef, overrides: dict[str, Any] | None = None,
                 max_draw: int = 150) -> np.ndarray:
    """Debug image for the Pipeline Lab: input and template side by side with RANSAC
    inlier matches drawn."""
    cfg = section("identification", overrides)
    det = cfg["detector"]
    q = extract(img, det, cfg["work_width"], cfg["max_features"])
    t = template_features(ref, det, cfg["work_width"], cfg["max_features"])
    good = ratio_matches(q, t, cfg["ratio_test"])
    from app.services.preprocessing.steps import resize_to_width, to_gray

    qa = cv2.cvtColor(resize_to_width(to_gray(img), round(q.full_size[0] * q.scale))[0], cv2.COLOR_GRAY2BGR)
    tpl = cv2.imread(str(ref.image_path), cv2.IMREAD_GRAYSCALE)
    ta = cv2.cvtColor(resize_to_width(tpl, round(t.full_size[0] * t.scale))[0], cv2.COLOR_GRAY2BGR)
    inlier_matches = good
    if len(good) >= 4:
        src = q.points[[m.queryIdx for m in good]].reshape(-1, 1, 2)
        dst = t.points[[m.trainIdx for m in good]].reshape(-1, 1, 2)
        _, mask = cv2.findHomography(src, dst, cv2.RANSAC, cfg["ransac_reproj_px"])
        if mask is not None:
            inlier_matches = [m for m, keep in zip(good, mask.ravel()) if keep]
    kq = [cv2.KeyPoint(float(x), float(y), 4) for x, y in q.points]
    kt = [cv2.KeyPoint(float(x), float(y), 4) for x, y in t.points]
    return cv2.drawMatches(qa, kq, ta, kt, inlier_matches[:max_draw], None, matchColor=(0, 200, 0),
                           singlePointColor=None, flags=cv2.DrawMatchesFlags_NOT_DRAW_SINGLE_POINTS)
