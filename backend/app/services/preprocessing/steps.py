"""Individual OpenCV preprocessing steps.

Each function does one thing, takes its parameters explicitly and returns new arrays,
so the Pipeline Lab can run and visualise any step on its own. Images are BGR uint8
unless stated otherwise.

Design rule: handwriting must survive. Steps that can erase faint pen strokes
(thresholding, strong denoising) are off or mild by default.
"""
from __future__ import annotations

import io
import math

import cv2
import numpy as np
from PIL import Image, ImageOps


# --------------------------------------------------------------------------- loading


def decode_image_bytes(data: bytes) -> np.ndarray:
    """Decode an uploaded image and apply its EXIF orientation.

    Phones store photos sideways and record the rotation in EXIF; OpenCV ignores EXIF,
    so Pillow's exif_transpose is applied first."""
    with Image.open(io.BytesIO(data)) as im:
        im = ImageOps.exif_transpose(im)
        im = im.convert("RGB")
        rgb = np.asarray(im)
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


def rasterize_pdf_bytes(data: bytes, dpi: int = 300, max_pages: int | None = None) -> list[np.ndarray]:
    import pymupdf

    pages: list[np.ndarray] = []
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        for i, page in enumerate(doc):
            if max_pages is not None and i >= max_pages:
                break
            pix = page.get_pixmap(dpi=dpi, alpha=False)
            arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
            pages.append(cv2.cvtColor(arr, cv2.COLOR_RGB2BGR if pix.n == 3 else cv2.COLOR_GRAY2BGR))
    return pages


# --------------------------------------------------------------------------- basics


def to_gray(img: np.ndarray) -> np.ndarray:
    return img if img.ndim == 2 else cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


def resize_to_width(img: np.ndarray, width: int) -> tuple[np.ndarray, float]:
    """Resize keeping aspect ratio. Returns (image, scale factor applied)."""
    h, w = img.shape[:2]
    if w == width:
        return img, 1.0
    scale = width / float(w)
    interp = cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC
    return cv2.resize(img, (width, max(1, round(h * scale))), interpolation=interp), scale


def rotate_to_portrait(img: np.ndarray) -> tuple[np.ndarray, int]:
    """Bank forms are portrait. A landscape capture is rotated 90 degrees clockwise.
    Whether the page is upside down is resolved later by feature matching, which is
    rotation invariant."""
    h, w = img.shape[:2]
    if w > h * 1.05:
        return cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE), 90
    return img, 0


# --------------------------------------------------------------------------- boundary


def order_quad(pts: np.ndarray) -> np.ndarray:
    """Order 4 points as top-left, top-right, bottom-right, bottom-left."""
    pts = np.asarray(pts, dtype=np.float32).reshape(4, 2)
    s = pts.sum(axis=1)
    d = np.diff(pts, axis=1).ravel()
    return np.array([pts[np.argmin(s)], pts[np.argmin(d)], pts[np.argmax(s)], pts[np.argmax(d)]], np.float32)


def detect_page_quad(img: np.ndarray, work_width: int = 1000, min_area_fraction: float = 0.25,
                     canny_low: int = 30, canny_high: int = 120) -> tuple[np.ndarray | None, dict]:
    """Find the four corners of the paper in a photo.

    Two complementary detectors are tried on a downscaled copy:
    1. edges (Canny + dilation) -> largest 4-sided contour;
    2. brightness (Otsu threshold: paper is brighter than most backgrounds) -> largest
       contour approximated by its minimum-area rectangle.
    Returns (quad in full-resolution pixels or None, debug info). None means "no page
    edge visible", which is normal for flat scans; the caller then keeps the whole image.
    """
    small, scale = resize_to_width(img, min(work_width, img.shape[1]))
    gray = cv2.GaussianBlur(to_gray(small), (5, 5), 0)
    area_total = gray.shape[0] * gray.shape[1]
    candidates: list[tuple[str, np.ndarray, float]] = []

    edges = cv2.Canny(gray, canny_low, canny_high)
    edges = cv2.dilate(edges, cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5)), iterations=2)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for c in sorted(contours, key=cv2.contourArea, reverse=True)[:5]:
        peri = cv2.arcLength(c, True)
        approx = cv2.approxPolyDP(c, 0.02 * peri, True)
        if len(approx) == 4 and cv2.isContourConvex(approx):
            candidates.append(("edges", approx.reshape(4, 2).astype(np.float32), cv2.contourArea(approx)))
            break

    _, bright = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    bright = cv2.morphologyEx(bright, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (15, 15)))
    contours, _ = cv2.findContours(bright, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if contours:
        c = max(contours, key=cv2.contourArea)
        peri = cv2.arcLength(c, True)
        approx = cv2.approxPolyDP(c, 0.02 * peri, True)
        quad = approx.reshape(-1, 2).astype(np.float32) if len(approx) == 4 else cv2.boxPoints(cv2.minAreaRect(c))
        candidates.append(("brightness", quad.astype(np.float32), cv2.contourArea(c)))

    info: dict = {"work_scale": scale, "candidates": [(n, float(a) / area_total) for n, _, a in candidates]}
    valid = [(n, q, a) for n, q, a in candidates if a / area_total >= min_area_fraction]
    if not valid:
        info["method"] = None
        return None, info
    # A quad that covers (almost) the whole frame is the image border, not a page edge.
    valid = [(n, q, a) for n, q, a in valid if a / area_total < 0.985] or []
    if not valid:
        info["method"] = "full_frame"
        return None, info
    name, quad, area = max(valid, key=lambda t: t[2])
    info["method"] = name
    info["area_fraction"] = float(area / area_total)
    return order_quad(quad / scale), info


def warp_quad_to_rect(img: np.ndarray, quad: np.ndarray, out_width: int | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Perspective-correct the page. Output size follows the quad's own edge lengths
    (optionally scaled to out_width). Returns (warped image, 3x3 matrix)."""
    tl, tr, br, bl = order_quad(quad)
    width = max(np.linalg.norm(tr - tl), np.linalg.norm(br - bl))
    height = max(np.linalg.norm(bl - tl), np.linalg.norm(br - tr))
    if out_width:
        height = height * out_width / width
        width = out_width
    w, h = max(1, round(width)), max(1, round(height))
    dst = np.array([[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]], np.float32)
    m = cv2.getPerspectiveTransform(np.array([tl, tr, br, bl], np.float32), dst)
    return cv2.warpPerspective(img, m, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE), m


# --------------------------------------------------------------------------- deskew


def estimate_skew(img: np.ndarray, max_angle_deg: float = 10.0, min_line_fraction: float = 0.25) -> tuple[float | None, int]:
    """Estimate residual skew from the form's long printed horizontal lines.

    Returns (angle in degrees, number of lines used); angle is None when too few lines
    are found. Positive angle = content rotated counter-clockwise."""
    small, _ = resize_to_width(img, min(1200, img.shape[1]))
    gray = to_gray(small)
    bw = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 25, 15)
    min_len = int(small.shape[1] * min_line_fraction)
    lines = cv2.HoughLinesP(bw, 1, np.pi / 720, threshold=150, minLineLength=min_len, maxLineGap=10)
    if lines is None:
        return None, 0
    angles = []
    for x1, y1, x2, y2 in np.asarray(lines).reshape(-1, 4):  # shape differs across OpenCV versions
        a = math.degrees(math.atan2(y2 - y1, x2 - x1))
        if abs(a) <= max_angle_deg:
            angles.append(a)
    if len(angles) < 3:
        return None, len(angles)
    # Image y grows downwards, so a line rising to the right has a negative atan2 angle.
    return float(-np.median(angles)), len(angles)


def rotate_image(img: np.ndarray, angle_deg: float) -> np.ndarray:
    """Rotate about the centre (positive = counter-clockwise), keeping the canvas size and
    filling borders by edge replication (white paper margin stays white)."""
    h, w = img.shape[:2]
    m = cv2.getRotationMatrix2D((w / 2, h / 2), angle_deg, 1.0)
    return cv2.warpAffine(img, m, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)


# --------------------------------------------------------------------------- cleanup


def denoise(img: np.ndarray, method: str = "median", median_ksize: int = 3, nlmeans_h: int = 5) -> np.ndarray:
    if method == "none":
        return img
    if method == "median":
        k = max(3, median_ksize | 1)
        return cv2.medianBlur(img, k)
    if method == "nlmeans":
        if img.ndim == 2:
            return cv2.fastNlMeansDenoising(img, None, nlmeans_h, 7, 21)
        return cv2.fastNlMeansDenoisingColored(img, None, nlmeans_h, nlmeans_h, 7, 21)
    raise ValueError(f"unknown denoise method: {method}")


def enhance_contrast(img: np.ndarray, method: str = "clahe", clip: float = 2.0, tile: int = 8) -> np.ndarray:
    """CLAHE on the lightness channel only, so blue/black ink colour is preserved."""
    if method == "none":
        return img
    if method != "clahe":
        raise ValueError(f"unknown contrast method: {method}")
    clahe = cv2.createCLAHE(clipLimit=clip, tileGridSize=(tile, tile))
    if img.ndim == 2:
        return clahe.apply(img)
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    lab[:, :, 0] = clahe.apply(lab[:, :, 0])
    return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)


def adaptive_threshold(img: np.ndarray, block_size: int = 35, c: int = 10) -> np.ndarray:
    bs = max(3, block_size | 1)
    return cv2.adaptiveThreshold(to_gray(img), 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, bs, c)
