"""Checkbox reader (SPEC section 12.5).

For each option square: find the square's inner area by contours inside the option box,
measure the ink-fill ratio there on the filled page, and compare it with the same
measurement on the blank template page (the empty-box baseline). A clear increase means
the box is marked; a small increase is reported as ambiguous.
"""
from __future__ import annotations

import cv2
import numpy as np


def _inner(gray: np.ndarray, box: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    """Inner rectangle of the printed square (excludes its border) via contours."""
    x, y, w, h = box
    pad = max(2, int(0.15 * max(w, h)))
    x0, y0 = max(0, x - pad), max(0, y - pad)
    crop = gray[y0:y + h + pad, x0:x + w + pad]
    if crop.size == 0:
        return box
    bw = cv2.adaptiveThreshold(crop, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 15, 8)
    cnts, hier = cv2.findContours(bw, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    best = None
    if hier is not None:
        for i, c in enumerate(cnts):
            if hier[0][i][3] < 0:
                continue
            cx, cy, cw, ch = cv2.boundingRect(c)
            if 0.5 * w <= cw <= 1.4 * w and 0.5 * h <= ch <= 1.4 * h and (best is None or cw * ch > best[2] * best[3]):
                best = (cx, cy, cw, ch)
    if best is None:
        m = max(2, int(0.18 * min(w, h)))
        return x + m, y + m, max(1, w - 2 * m), max(1, h - 2 * m)
    cx, cy, cw, ch = best
    m = max(1, int(0.08 * min(cw, ch)))
    return x0 + cx + m, y0 + cy + m, max(1, cw - 2 * m), max(1, ch - 2 * m)


def fill_ratio(gray: np.ndarray, box: tuple[int, int, int, int]) -> float:
    x, y, w, h = box
    patch = gray[y:y + h, x:x + w]
    if patch.size == 0:
        return 0.0
    _, bw = cv2.threshold(patch, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    if float(patch.std()) < 12:  # uniform patch: no ink, Otsu would invent some
        return 0.0
    return float((bw > 0).mean())


def read_options(page_gray: np.ndarray, template_gray: np.ndarray,
                 options: list[tuple[str, tuple[int, int, int, int]]],
                 marked_delta: float = 0.10, ambiguous_delta: float = 0.04) -> list[dict]:
    out = []
    for oid, box in options:
        inner = _inner(page_gray, box)
        ratio = fill_ratio(page_gray, inner)
        base = fill_ratio(template_gray, inner)
        delta = ratio - base
        state = "selected" if delta >= marked_delta else ("ambiguous" if delta >= ambiguous_delta else "empty")
        conf = min(1.0, abs(delta - (marked_delta + ambiguous_delta) / 2) / marked_delta)
        out.append({"option_id": oid, "box": list(box), "inner": list(inner), "fill_ratio": round(ratio, 4),
                    "baseline_ratio": round(base, 4), "delta": round(delta, 4), "state": state,
                    "confidence": round(conf, 3)})
    return out


def _ink_map(gray: np.ndarray) -> np.ndarray:
    """Ink by adaptive threshold: robust to shadows and uneven lighting in photos."""
    return cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 31, 18) > 0


def ink_added(page_gray: np.ndarray, template_gray: np.ndarray, box: tuple[int, int, int, int]) -> float:
    """Fraction of the box with new ink compared with the blank template (used to decide
    'empty' without running OCR). The template's printed ink is dilated so that small
    registration errors on printed lines are not counted as handwriting."""
    x, y, w, h = box
    pad = 4
    x0, y0 = max(0, x - pad), max(0, y - pad)
    a = page_gray[y0:y + h + pad, x0:x + w + pad]
    b = template_gray[y0:y + h + pad, x0:x + w + pad]
    if a.size == 0 or a.shape != b.shape:
        return 0.0
    a_ink = _ink_map(a)
    b_ink = cv2.dilate(_ink_map(b).astype(np.uint8), np.ones((7, 7), np.uint8)) > 0
    new = (a_ink & ~b_ink).astype(np.uint8)
    new = cv2.morphologyEx(new, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))  # drop isolated noise pixels
    return float(new.mean())


def remove_grid_lines(crop: np.ndarray) -> np.ndarray:
    """Morphological removal of printed cell borders from a boxed-character crop, so OCR
    sees only the handwritten characters (SPEC section 12.2)."""
    gray = crop if crop.ndim == 2 else cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    bw = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 25, 12)
    h, w = gray.shape[:2]
    vert = cv2.morphologyEx(bw, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(10, int(h * 0.7)))))
    horiz = cv2.morphologyEx(bw, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (max(10, int(w * 0.3)), 1)))
    lines = cv2.dilate(cv2.bitwise_or(vert, horiz), np.ones((3, 3), np.uint8))
    out = crop.copy()
    out[lines > 0] = 255
    return out
