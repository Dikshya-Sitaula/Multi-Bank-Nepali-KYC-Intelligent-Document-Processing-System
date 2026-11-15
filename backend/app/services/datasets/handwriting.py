"""Synthetic handwriting and mark rendering (SPEC section 10.3, demo subset).

WHY: training and demonstrating the pipeline needs filled forms, but no real customer
forms may be used. Values are rendered with open handwriting-style fonts (Kalam for
Devanagari + Latin, plus Latin-only hand fonts), with per-writer ink shade, size, slant
and per-character jitter, so different "writers" look different.

Honest limitation: font-based handwriting is cleaner and more regular than real
handwriting, and only one Devanagari hand font is available.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

FONT_DIR = Path(__file__).resolve().parents[4] / "assets" / "fonts"
DEVANAGARI_FONTS = ["Kalam-Regular.ttf", "Kalam-Light.ttf", "Kalam-Bold.ttf"]
LATIN_FONTS = DEVANAGARI_FONTS + ["PatrickHand-Regular.ttf", "Caveat[wght].ttf", "GochiHand-Regular.ttf"]

# Ink shades (RGB): blue ballpoint, dark blue, black, gel black, faded blue.
INKS = {"blue": (25, 55, 160), "dark_blue": (15, 30, 100), "black": (25, 25, 30),
        "gel_black": (5, 5, 10), "faded_blue": (90, 115, 185)}


@dataclass
class Writer:
    latin_font: str
    devanagari_font: str
    ink: str
    size_factor: float     # fraction of the field height used by the text
    slant_deg: float
    jitter: float          # per-character position jitter, fraction of font size
    opacity: float

    @staticmethod
    def sample(rng: np.random.Generator) -> "Writer":
        return Writer(
            latin_font=str(rng.choice(LATIN_FONTS)),
            devanagari_font=str(rng.choice(DEVANAGARI_FONTS)),
            ink=str(rng.choice(list(INKS))),
            size_factor=float(rng.uniform(0.55, 0.78)),
            slant_deg=float(rng.uniform(-6, 6)),
            jitter=float(rng.uniform(0.02, 0.08)),
            opacity=float(rng.uniform(0.75, 0.95)),
        )


def is_devanagari(text: str) -> bool:
    return any("ऀ" <= ch <= "ॿ" for ch in text)


def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_DIR / name), max(8, size), layout_engine=ImageFont.Layout.RAQM)


def _stamp(page: Image.Image, layer: Image.Image, x: int, y: int) -> None:
    page.alpha_composite(layer, (max(0, x), max(0, y)))


def write_text(page: Image.Image, text: str, box: tuple[int, int, int, int], w: Writer,
               rng: np.random.Generator) -> None:
    """Write text inside a box (x, y, w, h), sitting near the bottom like handwriting
    on a line, shrinking the font if the text is too long."""
    if not text:
        return
    x, y, bw, bh = box
    font_name = w.devanagari_font if is_devanagari(text) else w.latin_font
    size = int(bh * w.size_factor)
    font = _font(font_name, size)
    while size > 10 and font.getlength(text) > bw * 0.94:
        size = int(size * 0.9)
        font = _font(font_name, size)
    tw = int(font.getlength(text)) + 20
    th = int(size * 1.6) + 10
    layer = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    colour = INKS[w.ink] + (int(255 * w.opacity),)
    if is_devanagari(text):
        d.text((10, 5), text, font=font, fill=colour)  # keep clusters intact for shaping
    else:
        cx = 10.0
        for ch in text:  # per-character jitter = different strokes each time
            dy = rng.normal(0, w.jitter * size)
            d.text((cx, 5 + dy), ch, font=font, fill=colour)
            cx += font.getlength(ch) * rng.uniform(0.97, 1.05)
    layer = layer.rotate(w.slant_deg * 0.4 + rng.normal(0, 0.8), resample=Image.BICUBIC, expand=True)
    ox = x + int(rng.uniform(0.02, 0.08) * bw)
    oy = y + bh - layer.height + int(size * 0.25) + int(rng.normal(0, 0.03 * bh))
    _stamp(page, layer, ox, oy)


def write_cells(page: Image.Image, text: str, cells: list[tuple[int, int, int, int]], w: Writer,
                rng: np.random.Generator) -> None:
    """One character per letter cell, centred imperfectly."""
    for ch, (x, y, cw, ch_h) in zip(text, cells):
        if ch == " ":
            continue
        size = int(min(cw, ch_h) * rng.uniform(0.6, 0.8))
        font = _font(w.latin_font, size)
        layer = Image.new("RGBA", (cw * 2, ch_h * 2), (0, 0, 0, 0))
        ImageDraw.Draw(layer).text((cw // 2, ch_h // 2), ch, font=font,
                                   fill=INKS[w.ink] + (int(255 * w.opacity),))
        layer = layer.rotate(rng.normal(0, 4), resample=Image.BICUBIC)
        bbox = layer.getbbox()
        if not bbox:
            continue
        glyph = layer.crop(bbox)
        gx = x + (cw - glyph.width) // 2 + int(rng.normal(0, cw * 0.06))
        gy = y + (ch_h - glyph.height) // 2 + int(rng.normal(0, ch_h * 0.06))
        _stamp(page, glyph, gx, gy)


def draw_tick(page: Image.Image, box: tuple[int, int, int, int], w: Writer, rng: np.random.Generator) -> str:
    """Hand-drawn tick, cross or filled mark in a checkbox; may overshoot slightly."""
    x, y, bw, bh = box
    kind = str(rng.choice(["tick", "tick", "cross", "fill"]))
    d = ImageDraw.Draw(page)
    col = INKS[w.ink] + (int(255 * w.opacity),)
    width = max(3, int(min(bw, bh) * 0.12))
    j = lambda v: v + rng.normal(0, 0.05)  # noqa: E731
    if kind == "tick":
        pts = [(x + j(0.15) * bw, y + j(0.55) * bh), (x + j(0.42) * bw, y + j(0.85) * bh),
               (x + j(1.05) * bw, y + j(-0.05) * bh)]
        d.line(pts, fill=col, width=width, joint="curve")
    elif kind == "cross":
        d.line([(x + j(0.1) * bw, y + j(0.1) * bh), (x + j(0.9) * bw, y + j(0.9) * bh)], fill=col, width=width)
        d.line([(x + j(0.9) * bw, y + j(0.1) * bh), (x + j(0.1) * bw, y + j(0.9) * bh)], fill=col, width=width)
    else:
        d.ellipse([x + 0.2 * bw, y + 0.2 * bh, x + 0.8 * bw, y + 0.8 * bh], fill=col)
    return kind


def draw_signature(page: Image.Image, box: tuple[int, int, int, int], w: Writer, rng: np.random.Generator) -> None:
    """Procedural cursive-like strokes (not anyone's real signature)."""
    x, y, bw, bh = box
    t = np.linspace(0, 1, 400)
    loops = rng.uniform(3, 7)
    xs = x + bw * (0.1 + 0.8 * t)
    ys = y + bh * (0.55 + 0.22 * np.sin(2 * math.pi * loops * t + rng.uniform(0, 6)) * (1 - 0.5 * t)
                   + 0.05 * np.sin(2 * math.pi * 1.3 * t))
    pts = list(zip(xs.tolist(), ys.tolist()))
    d = ImageDraw.Draw(page)
    d.line(pts, fill=INKS[w.ink] + (230,), width=max(3, int(bh * 0.03)), joint="curve")
    d.line([(x + bw * 0.15, y + bh * 0.8), (x + bw * rng.uniform(0.6, 0.85), y + bh * 0.76)],
           fill=INKS[w.ink] + (220,), width=max(2, int(bh * 0.02)))


def draw_thumbprint(page: Image.Image, box: tuple[int, int, int, int], rng: np.random.Generator) -> None:
    """Procedural ridge-pattern ink blob (not a real fingerprint)."""
    x, y, bw, bh = box
    w, h = int(bw * 0.6), int(bh * 0.55)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    cx, cy = w / 2, h / 2
    r = np.sqrt(((xx - cx) / (w / 2)) ** 2 + ((yy - cy) / (h / 2)) ** 2)
    ang = np.arctan2(yy - cy, xx - cx)
    ridges = 0.5 + 0.5 * np.sin(r * rng.uniform(40, 60) + ang * rng.uniform(0.5, 1.5))
    mask = (r < 1.0) * ridges * (1 - r ** 4)
    darkness = rng.uniform(0.5, 0.9)
    alpha = (np.clip(mask, 0, 1) * 255 * darkness).astype(np.uint8)
    layer = Image.new("RGBA", (w, h), (40, 40, 70, 0))
    layer.putalpha(Image.fromarray(alpha))
    _stamp(page, layer, x + (bw - w) // 2, y + (bh - h) // 2)


def draw_avatar(page: Image.Image, box: tuple[int, int, int, int], rng: np.random.Generator) -> None:
    """Procedural passport-style avatar: gradient background, shapes for head and
    shoulders. Clearly not a photo of a real person."""
    x, y, bw, bh = box
    w, h = int(bw * 0.86), int(bh * 0.86)
    top = np.array(rng.integers(150, 230, 3), np.float32)
    bot = top * 0.7
    grad = np.linspace(0, 1, h, dtype=np.float32)[:, None, None]
    arr = (top * (1 - grad) + bot * grad).repeat(w, axis=1).astype(np.uint8)
    img = Image.fromarray(arr, "RGB").convert("RGBA")
    d = ImageDraw.Draw(img)
    skin = tuple(int(v) for v in rng.integers(120, 210, 3))
    cloth = tuple(int(v) for v in rng.integers(20, 120, 3))
    d.ellipse([w * 0.15, h * 0.68, w * 0.85, h * 1.25], fill=cloth)
    d.ellipse([w * 0.32, h * 0.18, w * 0.68, h * 0.62], fill=skin)
    d.ellipse([w * 0.30, h * 0.12, w * 0.70, h * 0.36], fill=(30, 25, 25))
    _stamp(page, img, x + (bw - w) // 2, y + (bh - h) // 2)


def draw_location_map(page: Image.Image, box: tuple[int, int, int, int], w: Writer, rng: np.random.Generator) -> None:
    """Hand-drawn sketch map: a few roads, a house square and a label."""
    x, y, bw, bh = box
    d = ImageDraw.Draw(page)
    col = INKS[w.ink] + (220,)
    for _ in range(3):
        if rng.random() < 0.5:
            yy = y + bh * rng.uniform(0.25, 0.8)
            d.line([(x + bw * 0.05, yy), (x + bw * 0.95, yy + rng.normal(0, bh * 0.03))], fill=col, width=4)
        else:
            xx = x + bw * rng.uniform(0.2, 0.8)
            d.line([(xx, y + bh * 0.1), (xx + rng.normal(0, bw * 0.03), y + bh * 0.9)], fill=col, width=4)
    hx, hy = x + bw * rng.uniform(0.3, 0.6), y + bh * rng.uniform(0.3, 0.55)
    d.rectangle([hx, hy, hx + bw * 0.08, hy + bh * 0.1], outline=col, width=4)
    write_text(page, "Home", (int(hx), int(hy + bh * 0.1), int(bw * 0.25), int(bh * 0.1)), w, rng)


def paper_texture(img: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    noise = cv2.GaussianBlur(rng.normal(0, 3, img.shape[:2]).astype(np.float32), (0, 0), 2)
    return np.clip(img.astype(np.float32) + noise[..., None], 0, 255).astype(np.uint8)
