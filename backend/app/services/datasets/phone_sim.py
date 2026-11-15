"""Phone-photo capture simulation.

WHY: employees will photograph forms with phones, not scan them. To train and to test
the pipeline on that reality without collecting real customer photos, a clean page image
is turned into a plausible phone capture: placed on a desk-like background, viewed in
perspective, unevenly lit, shadowed, possibly with glare, slightly blurred, noisy and
JPEG-compressed.

The function returns the exact 3x3 homography from page coordinates to capture
coordinates, so ground-truth boxes can be transformed with the image (used by the
synthetic data generator) and identification/registration accuracy can be measured.

Everything is procedural and seeded; no external photos are used.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np

# Strength presets. "strong" is still meant to leave handwriting readable.
LEVELS: dict[str, dict[str, Any]] = {
    "none": dict(corner_jitter=0.0, rotation_deg=0.0, page_fill=(0.95, 0.95), light_gradient=0.0,
                 shadow_prob=0.0, glare_prob=0.0, blur_sigma=(0.0, 0.0), motion_prob=0.0,
                 noise_sigma=(0.0, 0.0), jpeg_quality=(95, 95), landscape_prob=0.0),
    "light": dict(corner_jitter=0.03, rotation_deg=3.0, page_fill=(0.80, 0.92), light_gradient=0.15,
                  shadow_prob=0.2, glare_prob=0.1, blur_sigma=(0.0, 0.8), motion_prob=0.0,
                  noise_sigma=(1.0, 3.0), jpeg_quality=(80, 95), landscape_prob=0.0),
    "medium": dict(corner_jitter=0.07, rotation_deg=8.0, page_fill=(0.70, 0.88), light_gradient=0.30,
                   shadow_prob=0.4, glare_prob=0.25, blur_sigma=(0.3, 1.3), motion_prob=0.15,
                   noise_sigma=(2.0, 5.0), jpeg_quality=(65, 90), landscape_prob=0.1),
    "strong": dict(corner_jitter=0.11, rotation_deg=15.0, page_fill=(0.60, 0.82), light_gradient=0.45,
                   shadow_prob=0.6, glare_prob=0.4, blur_sigma=(0.6, 1.8), motion_prob=0.3,
                   noise_sigma=(3.0, 7.0), jpeg_quality=(50, 80), landscape_prob=0.2),
}


@dataclass
class Capture:
    image: np.ndarray        # simulated photo, BGR uint8
    homography: np.ndarray   # 3x3, page pixel coords -> capture pixel coords
    params: dict[str, Any]   # what was actually sampled (for reproducibility reports)


def _background(rng: np.random.Generator, h: int, w: int) -> np.ndarray:
    """Procedural desk/table texture: a base colour, low-frequency variation and grain."""
    base = np.array(rng.choice([[60, 90, 130], [40, 60, 85], [110, 120, 125], [30, 30, 35],
                                [150, 160, 170], [70, 110, 150]]), np.float32)
    low = cv2.resize(rng.normal(0, 1, (8, 8)).astype(np.float32), (w, h), interpolation=cv2.INTER_CUBIC)
    grain = cv2.GaussianBlur(rng.normal(0, 1, (h, w)).astype(np.float32), (0, 0), 1.5)
    if rng.random() < 0.5:  # wood-like streaks
        streak = cv2.resize(rng.normal(0, 1, (1, 64)).astype(np.float32), (w, h), interpolation=cv2.INTER_CUBIC)
        low = low + 0.8 * streak
    img = base[None, None, :] + 18 * low[..., None] + 6 * grain[..., None]
    return np.clip(img, 0, 255).astype(np.uint8)


def _motion_kernel(rng: np.random.Generator, length: int) -> np.ndarray:
    k = np.zeros((length, length), np.float32)
    k[length // 2, :] = 1.0
    m = cv2.getRotationMatrix2D((length / 2 - 0.5, length / 2 - 0.5), float(rng.uniform(0, 180)), 1.0)
    k = cv2.warpAffine(k, m, (length, length))
    return k / max(k.sum(), 1e-6)


def simulate_capture(page: np.ndarray, rng: np.random.Generator, level: str = "medium",
                     out_long_side: int = 3000, overrides: dict[str, Any] | None = None) -> Capture:
    p = {**LEVELS[level], **(overrides or {})}
    ph, pw = page.shape[:2]
    landscape = rng.random() < p["landscape_prob"]
    out_h, out_w = (out_long_side, int(out_long_side * 0.75))
    if landscape:
        out_h, out_w = out_w, out_h

    # Place the page: scale to the sampled fill fraction, rotate, jitter corners.
    fill = rng.uniform(*p["page_fill"])
    scale = fill * min(out_w / pw, out_h / ph) if not landscape else fill * min(out_w / ph, out_h / pw)
    sw, sh = pw * scale, ph * scale
    rot = (float(p["rotation_exact_deg"]) if p.get("rotation_exact_deg") is not None
           else rng.uniform(-p["rotation_deg"], p["rotation_deg"])) + (90.0 if landscape else 0.0)
    corners = np.array([[-sw / 2, -sh / 2], [sw / 2, -sh / 2], [sw / 2, sh / 2], [-sw / 2, sh / 2]], np.float32)
    jitter = rng.uniform(-p["corner_jitter"], p["corner_jitter"], (4, 2)).astype(np.float32) * np.array([sw, sh], np.float32)
    corners = corners + jitter
    t = np.deg2rad(rot)
    r = np.array([[np.cos(t), -np.sin(t)], [np.sin(t), np.cos(t)]], np.float32)
    corners = corners @ r.T + np.array([out_w / 2, out_h / 2], np.float32)
    corners += rng.uniform(-0.04, 0.04, 2).astype(np.float32) * np.array([out_w, out_h], np.float32)
    src = np.array([[0, 0], [pw - 1, 0], [pw - 1, ph - 1], [0, ph - 1]], np.float32)
    H = cv2.getPerspectiveTransform(src, corners.astype(np.float32))

    bg = _background(rng, out_h, out_w)
    warped = cv2.warpPerspective(page, H, (out_w, out_h), flags=cv2.INTER_AREA, borderValue=(0, 0, 0))
    mask = cv2.warpPerspective(np.full((ph, pw), 255, np.uint8), H, (out_w, out_h), flags=cv2.INTER_NEAREST)
    mask = cv2.GaussianBlur(mask, (3, 3), 0).astype(np.float32)[..., None] / 255.0
    img = (warped.astype(np.float32) * mask + bg.astype(np.float32) * (1 - mask))

    # Uneven lighting: smooth multiplicative gradient.
    g = p["light_gradient"]
    if g > 0:
        yy, xx = np.mgrid[0:out_h, 0:out_w].astype(np.float32)
        ang = rng.uniform(0, 2 * np.pi)
        ramp = (np.cos(ang) * xx / out_w + np.sin(ang) * yy / out_h)
        ramp = (ramp - ramp.min()) / max(float(np.ptp(ramp)), 1e-6)
        img *= (1.0 - g * ramp)[..., None] * rng.uniform(0.85, 1.05)

    # Soft partial shadow (e.g. a hand or the phone itself).
    shadow = rng.random() < p["shadow_prob"]
    if shadow:
        poly = (rng.uniform(0, 1, (4, 2)) * np.array([out_w, out_h])).astype(np.int32)
        sm = np.zeros((out_h, out_w), np.float32)
        cv2.fillConvexPoly(sm, cv2.convexHull(poly), 1.0)
        sm = cv2.GaussianBlur(sm, (0, 0), out_w / 40)
        img *= (1.0 - rng.uniform(0.2, 0.45) * sm)[..., None]

    # Specular glare blob.
    glare = rng.random() < p["glare_prob"]
    if glare:
        gm = np.zeros((out_h, out_w), np.float32)
        c = (int(rng.uniform(0.2, 0.8) * out_w), int(rng.uniform(0.2, 0.8) * out_h))
        axes = (int(rng.uniform(0.04, 0.10) * out_w), int(rng.uniform(0.03, 0.08) * out_h))
        cv2.ellipse(gm, c, axes, float(rng.uniform(0, 180)), 0, 360, 1.0, -1)
        gm = cv2.GaussianBlur(gm, (0, 0), axes[0] / 2)
        img = img + gm[..., None] * rng.uniform(80, 160)

    img = np.clip(img, 0, 255).astype(np.uint8)

    sigma = rng.uniform(*p["blur_sigma"])
    if sigma > 0.05:
        img = cv2.GaussianBlur(img, (0, 0), sigma)
    motion = rng.random() < p["motion_prob"]
    if motion:
        img = cv2.filter2D(img, -1, _motion_kernel(rng, int(rng.integers(3, 8))))

    noise = rng.uniform(*p["noise_sigma"])
    if noise > 0:
        img = np.clip(img.astype(np.float32) + rng.normal(0, noise, img.shape), 0, 255).astype(np.uint8)

    quality = int(rng.integers(p["jpeg_quality"][0], p["jpeg_quality"][1] + 1))
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if ok:
        img = cv2.imdecode(buf, cv2.IMREAD_COLOR)

    sampled = {"level": level, "rotation_deg": round(float(rot), 2), "fill": round(float(fill), 3),
               "landscape": bool(landscape), "shadow": bool(shadow), "glare": bool(glare),
               "blur_sigma": round(float(sigma), 2), "motion_blur": bool(motion),
               "noise_sigma": round(float(noise), 2), "jpeg_quality": quality}
    return Capture(image=img, homography=H, params=sampled)
