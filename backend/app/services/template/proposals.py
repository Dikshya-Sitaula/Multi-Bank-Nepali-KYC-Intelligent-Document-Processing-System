"""Automatic proposal of fill-in regions on a blank form page (SPEC section 9).

WHY: annotating hundreds of boxes by hand is slow and error-prone. Printed forms are
built from a small set of structures, and each can be found with classical CV:

    checkbox        small square
    cell            letter/digit cell; adjacent cells of equal size form a *cell strip*
                    (block-letter names, dates, account numbers)
    box             a rectangle big enough to write in (text box, table cell)
    frame           a large rectangle (photo, signature, thumbprint, location map)
    underline       a long horizontal line that is not part of a box (write-on-the-line)

Detection works on the rasterized page with morphology: horizontal and vertical line
maps are extracted with long thin kernels, their union is the form's ruling, and the
holes of that ruling are the boxes. For PDFs with vector drawings, rectangles from the
PDF itself are merged in because they are pixel-exact.

These are *proposals*. The field each box belongs to is suggested later from nearby
printed labels, and a human approves everything in Template Studio (Checkpoint A).
All sizes are relative to a 300 DPI A4 page and scale with the image.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import cv2
import numpy as np

REF_WIDTH = 2480.0  # A4 at 300 DPI


@dataclass
class Candidate:
    kind: str                       # checkbox | cell_strip | box | frame | underline
    x: int
    y: int
    w: int
    h: int
    source: str = "raster"          # raster | vector
    cells: list[tuple[int, int, int, int]] = field(default_factory=list)  # for cell strips

    @property
    def area(self) -> int:
        return self.w * self.h

    def as_xyxy(self) -> tuple[int, int, int, int]:
        return self.x, self.y, self.x + self.w, self.y + self.h

    def to_dict(self) -> dict[str, Any]:
        d = {"kind": self.kind, "bbox": [self.x, self.y, self.w, self.h], "source": self.source}
        if self.cells:
            d["cell_count"] = len(self.cells)
            d["cells"] = [list(c) for c in self.cells]
        return d


def iou(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    ix = max(0, min(ax1, bx1) - max(ax0, bx0))
    iy = max(0, min(ay1, by1) - max(ay0, by0))
    inter = ix * iy
    union = (ax1 - ax0) * (ay1 - ay0) + (bx1 - bx0) * (by1 - by0) - inter
    return inter / union if union else 0.0


def line_maps(gray: np.ndarray, scale: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Binary ink map plus horizontal and vertical ruling maps."""
    ink = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 35, 12)
    h_len = max(15, int(40 * scale))
    v_len = max(12, int(30 * scale))
    horiz = cv2.morphologyEx(ink, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (h_len, 1)))
    vert = cv2.morphologyEx(ink, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, v_len)))
    return ink, horiz, vert


def _rect_holes(ruling: np.ndarray, scale: float) -> list[tuple[int, int, int, int]]:
    """Inner holes of the ruling = enclosed rectangles (boxes and cells)."""
    closed = cv2.dilate(ruling, cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)))
    contours, hierarchy = cv2.findContours(closed, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    out = []
    if hierarchy is None:
        return out
    min_side = max(8, int(14 * scale))
    for i, c in enumerate(contours):
        if hierarchy[0][i][3] < 0:  # outer contour of a ruling blob, not a hole
            continue
        x, y, w, h = cv2.boundingRect(c)
        if w < min_side or h < min_side:
            continue
        # A hole must be roughly rectangular to count as a box.
        if cv2.contourArea(c) < 0.80 * w * h:
            continue
        out.append((x - 1, y - 1, w + 2, h + 2))
    return out


def _group_cells(cells: list[tuple[int, int, int, int]], scale: float) -> tuple[list[Candidate], list[tuple]]:
    """Group equal-sized, horizontally adjacent cells into strips."""
    used = set()
    strips: list[Candidate] = []
    cells = sorted(cells, key=lambda c: (c[1], c[0]))
    gap_max = int(40 * scale)
    for i, c in enumerate(cells):
        if i in used:
            continue
        row = [i]
        last = c
        for j in range(i + 1, len(cells)):
            if j in used:
                continue
            d = cells[j]
            same_row = abs(d[1] - last[1]) <= 0.35 * last[3] and abs(d[3] - last[3]) <= 0.35 * last[3]
            adjacent = 0 <= d[0] - (last[0] + last[2]) <= gap_max
            similar_w = abs(d[2] - last[2]) <= 0.6 * last[2]
            if same_row and adjacent and similar_w:
                row.append(j)
                last = d
        if len(row) >= 3:
            used.update(row)
            members = [cells[k] for k in row]
            x0 = min(m[0] for m in members)
            y0 = min(m[1] for m in members)
            x1 = max(m[0] + m[2] for m in members)
            y1 = max(m[1] + m[3] for m in members)
            strips.append(Candidate("cell_strip", x0, y0, x1 - x0, y1 - y0, cells=members))
    rest = [c for k, c in enumerate(cells) if k not in used]
    return strips, rest


def _underlines(horiz: np.ndarray, ink: np.ndarray, boxes: list[Candidate], scale: float, page_w: int) -> list[Candidate]:
    """Long horizontal lines that are not edges of a detected box: write-on-the-line fields.
    Dotted lines are joined first with a horizontal closing.

    Devanagari words have a horizontal headline (shirorekha) that looks like a line to a
    morphological filter. A real write-on line has empty paper just above it (that is
    where the customer writes) and nothing hanging below it, while a headline has letters
    hanging below. Both bands are measured and text headlines are rejected."""
    joined = cv2.morphologyEx(horiz, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (int(25 * scale), 1)))
    n, _, stats, _ = cv2.connectedComponentsWithStats(joined, connectivity=8)
    out = []
    min_len = int(120 * scale)
    write_h = int(60 * scale)  # writing space above the line
    for i in range(1, n):
        x, y, w, h, _ = stats[i]
        if w < min_len or h > 12 * scale or w > 0.97 * page_w:
            continue
        # A table rule runs along the top or bottom edge of the boxes it borders.
        tol = max(6, int(10 * scale))
        on_box_edge = any(
            (abs(y - b.y) <= tol or abs(y - (b.y + b.h)) <= tol)
            and min(x + w, b.x + b.w) - max(x, b.x) >= 0.5 * min(b.w, w)
            for b in boxes
        )
        if on_box_edge:
            continue
        band = int(28 * scale)
        below = ink[y + h + 2: y + h + 2 + band, x: x + w]
        # Ignore the left 25%: a printed label often sits just left of/above a field line.
        x_mid = x + w // 4
        above = ink[max(0, y - band): max(0, y - 2), x_mid: x + w]
        if below.size and float((below > 0).mean()) > 0.06:
            continue
        if above.size and float((above > 0).mean()) > 0.05:
            continue
        out.append(Candidate("underline", int(x), int(max(0, y - write_h)), int(w), int(write_h + h)))
    return out


def detect_raster(img: np.ndarray) -> list[Candidate]:
    gray = img if img.ndim == 2 else cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    page_h, page_w = gray.shape[:2]
    scale = page_w / REF_WIDTH
    _, horiz, vert = line_maps(gray, scale)
    ruling = cv2.bitwise_or(horiz, vert)
    rects = _rect_holes(ruling, scale)

    # Also find small squares drawn with thin strokes that the line opening may miss:
    # contours of the raw ink that are square and hollow.
    ink = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 25, 10)
    cnts, hier = cv2.findContours(ink, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    if hier is not None:
        lo, hi = int(18 * scale), int(70 * scale)
        for i, c in enumerate(cnts):
            if hier[0][i][3] < 0:
                continue
            x, y, w, h = cv2.boundingRect(c)
            if not (lo <= w <= hi and lo <= h <= hi and 0.75 <= w / h <= 1.33):
                continue
            # A checkbox hole is a square with four sharp corners; letter holes (o, D, 0)
            # are rounded and approximate to more vertices.
            approx = cv2.approxPolyDP(c, 0.08 * cv2.arcLength(c, True), True)
            if len(approx) == 4 and cv2.contourArea(c) > 0.85 * w * h:
                rects.append((x - 1, y - 1, w + 2, h + 2))

    # De-duplicate near-identical rectangles.
    rects = sorted(set(rects), key=lambda r: r[2] * r[3], reverse=True)
    uniq: list[tuple[int, int, int, int]] = []
    for r in rects:
        rx = (r[0], r[1], r[0] + r[2], r[1] + r[3])
        if all(iou(rx, (u[0], u[1], u[0] + u[2], u[1] + u[3])) < 0.7 for u in uniq):
            uniq.append(r)

    small_max = int(75 * scale)
    cell_min, cell_max = int(30 * scale), int(110 * scale)
    smalls = [r for r in uniq if r[2] <= cell_max and r[3] <= cell_max]
    others = [r for r in uniq if not (r[2] <= cell_max and r[3] <= cell_max)]

    strips, singles = _group_cells([r for r in smalls if r[2] >= cell_min * 0.6], scale)
    cands: list[Candidate] = list(strips)
    for r in singles + [r for r in smalls if r[2] < cell_min * 0.6]:
        if any(s.x <= r[0] and r[0] + r[2] <= s.x + s.w + 2 and s.y - 2 <= r[1] and r[1] + r[3] <= s.y + s.h + 2
               for s in strips):
            continue
        square = 0.7 <= r[2] / r[3] <= 1.45
        if square and r[2] <= small_max:
            cands.append(Candidate("checkbox", *r))
        else:
            cands.append(Candidate("box", *r))
    frame_min = int(250 * scale)
    for r in others:
        if r[2] > 0.97 * page_w and r[3] > 0.9 * page_h:
            continue  # page border
        kind = "frame" if (r[2] >= frame_min and r[3] >= frame_min) else "box"
        cands.append(Candidate(kind, *r))
    boxes = [c for c in cands if c.kind in ("box", "frame", "cell_strip")]
    cands.extend(_underlines(horiz, ink, boxes, scale, page_w))
    return cands


def vector_rects(page: Any, dpi: int = 300) -> list[Candidate]:
    """Rectangles drawn in the PDF itself (pymupdf page), converted to pixels."""
    s = dpi / 72.0
    out = []
    for d in page.get_drawings():
        for item in d.get("items", []):
            if item[0] != "re":
                continue
            r = item[1]
            x, y, w, h = int(r.x0 * s), int(r.y0 * s), int(r.width * s), int(r.height * s)
            if w >= 12 and h >= 12:
                out.append(Candidate("box", x, y, w, h, source="vector"))
    return out


def merge_vector(raster: list[Candidate], vector: list[Candidate], scale: float) -> list[Candidate]:
    """Snap raster boxes to matching vector rectangles (more exact); add vector-only boxes
    that are big enough to write in and not already covered."""
    out = list(raster)
    for v in vector:
        vx = v.as_xyxy()
        best = max(out, key=lambda c: iou(c.as_xyxy(), vx), default=None)
        if best is not None and iou(best.as_xyxy(), vx) >= 0.6:
            if best.kind in ("box", "frame", "checkbox"):
                best.x, best.y, best.w, best.h, best.source = v.x, v.y, v.w, v.h, "vector"
            continue
        if v.w >= 60 * scale and v.h >= 35 * scale and not any(
            c.x <= v.x + 3 and c.y <= v.y + 3 and c.x + c.w >= v.x + v.w - 3 and c.y + c.h >= v.y + v.h - 3
            and c.kind == "cell_strip" for c in out
        ):
            kind = "frame" if v.w >= 250 * scale and v.h >= 250 * scale else "box"
            out.append(Candidate(kind, v.x, v.y, v.w, v.h, source="vector"))
    return out


KIND_COLOURS = {"checkbox": (0, 160, 0), "cell_strip": (200, 0, 200), "box": (220, 120, 0),
                "frame": (0, 0, 220), "underline": (0, 170, 220)}


def draw_overlay(img: np.ndarray, items: list[dict[str, Any]], label_key: str = "label") -> np.ndarray:
    """Numbered, colour-coded boxes for visual review."""
    out = img.copy() if img.ndim == 3 else cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    out = cv2.addWeighted(out, 0.75, np.full_like(out, 255), 0.25, 0)
    for it in items:
        x, y, w, h = it["bbox"]
        col = it.get("colour") or KIND_COLOURS.get(it.get("kind", "box"), (80, 80, 80))
        cv2.rectangle(out, (x, y), (x + w, y + h), col, 3)
        text = f"{it['n']}" + (f" {it[label_key]}" if it.get(label_key) else "")
        (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
        ty = max(th + 4, y - 4)
        cv2.rectangle(out, (x, ty - th - 4), (x + tw + 4, ty + 3), (255, 255, 255), -1)
        cv2.putText(out, text, (x + 2, ty), cv2.FONT_HERSHEY_SIMPLEX, 0.7, col, 2)
    return out
