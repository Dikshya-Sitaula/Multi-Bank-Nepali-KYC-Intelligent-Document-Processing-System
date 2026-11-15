"""Synthetic test images built inside the tests (no dependency on the bank PDFs)."""
from __future__ import annotations

import cv2
import numpy as np

W, H = 1240, 1754  # A4 at 150 DPI keeps tests fast


def synthetic_form(seed: int, w: int = W, h: int = H) -> np.ndarray:
    """A form-like page: title, labelled lines, letter-cell rows, boxes and a table.
    Different seeds give different layouts and text, i.e. different 'bank forms'."""
    rng = np.random.default_rng(seed)
    img = np.full((h, w, 3), 255, np.uint8)
    title = "".join(chr(int(c)) for c in rng.integers(65, 91, 14))
    cv2.putText(img, title, (80, 110), cv2.FONT_HERSHEY_DUPLEX, 1.6, (0, 0, 0), 3)
    y = 190
    while y < h - 120:
        kind = int(rng.integers(0, 4))
        label = "".join(chr(int(c)) for c in rng.integers(65, 91, int(rng.integers(4, 12))))
        cv2.putText(img, label, (60, y), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 2)
        if kind == 0:  # underline field
            cv2.line(img, (330, y + 5), (w - 60, y + 5), (0, 0, 0), 2)
            y += 60
        elif kind == 1:  # letter cells
            n = int(rng.integers(8, 24))
            for i in range(n):
                x = 330 + i * 34
                cv2.rectangle(img, (x, y - 28), (x + 30, y + 6), (0, 0, 0), 2)
            y += 70
        elif kind == 2:  # checkboxes with labels
            x = 330
            for _ in range(int(rng.integers(2, 5))):
                cv2.rectangle(img, (x, y - 22), (x + 22, y), (0, 0, 0), 2)
                opt = "".join(chr(int(c)) for c in rng.integers(97, 123, int(rng.integers(3, 8))))
                cv2.putText(img, opt, (x + 30, y - 2), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2)
                x += 200
            y += 60
        else:  # table
            rows, cols = int(rng.integers(2, 5)), int(rng.integers(2, 5))
            cw, rh = (w - 420) // cols, 46
            for r in range(rows + 1):
                cv2.line(img, (330, y + r * rh - 30), (330 + cols * cw, y + r * rh - 30), (0, 0, 0), 2)
            for c in range(cols + 1):
                cv2.line(img, (330 + c * cw, y - 30), (330 + c * cw, y + rows * rh - 30), (0, 0, 0), 2)
            y += rows * rh + 50
    return img


def place_on_background(page: np.ndarray, angle_deg: float = 0.0, jitter: float = 0.05,
                        seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """Put the page on a dark desk in perspective. Returns (photo, true 4 page corners)."""
    rng = np.random.default_rng(seed)
    ph, pw = page.shape[:2]
    out_w, out_h = int(pw * 1.4), int(ph * 1.3)
    cx, cy = out_w / 2, out_h / 2
    half = np.array([[-pw / 2, -ph / 2], [pw / 2, -ph / 2], [pw / 2, ph / 2], [-pw / 2, ph / 2]], np.float32) * 0.85
    half += rng.uniform(-jitter, jitter, (4, 2)).astype(np.float32) * np.array([pw, ph], np.float32)
    t = np.deg2rad(angle_deg)
    rot = np.array([[np.cos(t), -np.sin(t)], [np.sin(t), np.cos(t)]], np.float32)
    corners = half @ rot.T + np.array([cx, cy], np.float32)
    src = np.array([[0, 0], [pw - 1, 0], [pw - 1, ph - 1], [0, ph - 1]], np.float32)
    m = cv2.getPerspectiveTransform(src, corners)
    bg = np.full((out_h, out_w, 3), (45, 60, 80), np.uint8)
    warped = cv2.warpPerspective(page, m, (out_w, out_h))
    mask = cv2.warpPerspective(np.full((ph, pw), 255, np.uint8), m, (out_w, out_h)) > 0
    bg[mask] = warped[mask]
    return bg, corners
