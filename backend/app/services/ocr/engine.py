"""OCR engine abstraction (SPEC section 12.1).

WHY an interface: OCR is independent of field detection. Any engine (EasyOCR now, the
custom CRNN later, Tesseract if installed) implements `process_text_crop`, so engines can
be swapped or compared on the same crop without touching the pipeline.

EasyOCR readers are large (the Nepali/Devanagari model plus the CRAFT detector), so they
are created once, shared, and preloaded in a background thread at startup.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any

import numpy as np

log = logging.getLogger(__name__)


@dataclass
class OCRResult:
    text: str
    confidence: float          # 0..1, as reported by the engine
    language: str
    engine: str
    raw: list[dict[str, Any]] = field(default_factory=list)
    ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {"text": self.text, "confidence": round(self.confidence, 4), "language": self.language,
                "engine": self.engine, "ms": round(self.ms, 1), "raw": self.raw}


class OCREngine:
    name = "base"

    def process_text_crop(self, image: np.ndarray, language: str, field_type: str) -> OCRResult:  # pragma: no cover
        raise NotImplementedError


# Field language (config/fields.yaml) -> EasyOCR language list.
_LANGS = {"eng": ("en",), "digits": ("en",), "nep": ("ne", "en"), "mixed": ("ne", "en")}


class EasyOCREngine(OCREngine):
    name = "easyocr"

    def __init__(self) -> None:
        self._readers: dict[tuple[str, ...], Any] = {}
        self._lock = threading.Lock()
        self.status = "not loaded"
        self.load_seconds: float | None = None

    def _reader(self, langs: tuple[str, ...]):  # noqa: ANN202
        with self._lock:
            if langs not in self._readers:
                import easyocr  # heavy import, deferred

                self._readers[langs] = easyocr.Reader(list(langs), gpu=False, verbose=False)
            return self._readers[langs]

    def preload(self) -> None:
        t0 = time.perf_counter()
        self.status = "loading"
        try:
            for langs in {("en",), ("ne", "en")}:
                self._reader(langs)
            self.status = "ready"
        except Exception as exc:  # noqa: BLE001 - reported in system status, never fatal
            self.status = f"failed: {type(exc).__name__}"
            log.exception("EasyOCR preload failed")
        self.load_seconds = round(time.perf_counter() - t0, 1)

    def process_text_crop(self, image: np.ndarray, language: str, field_type: str) -> OCRResult:
        langs = _LANGS.get(language, ("ne", "en"))
        t0 = time.perf_counter()
        allow = "0123456789०१२३४५६७८९/-. " if language == "digits" else None
        res = self._reader(langs).readtext(image, detail=1, paragraph=False, allowlist=allow)
        res = sorted(res, key=lambda r: (min(p[0] for p in r[0])))  # left to right
        text = " ".join(r[1] for r in res).strip()
        conf = float(np.mean([r[2] for r in res])) if res else 0.0
        raw = [{"text": r[1], "conf": round(float(r[2]), 4),
                "box": [[int(p[0]), int(p[1])] for p in r[0]]} for r in res]
        return OCRResult(text, conf, language, self.name, raw, (time.perf_counter() - t0) * 1000)


_engine: EasyOCREngine | None = None


def get_engine() -> EasyOCREngine:
    global _engine
    if _engine is None:
        _engine = EasyOCREngine()
    return _engine


def preload_in_background() -> None:
    threading.Thread(target=get_engine().preload, name="easyocr-preload", daemon=True).start()
