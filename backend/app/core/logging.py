"""Structured logging.

WHY: logs are needed to debug the pipeline, but OCR output is customer personal data.
Log records are one JSON object per line, and nothing in the codebase passes OCR text to
the logger unless LOG_OCR_TEXT=true. `redact_text` is the single helper for that rule.
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone

from app.core.config import get_settings


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data = {
            "ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        extra = getattr(record, "ctx", None)
        if isinstance(extra, dict):
            data.update(extra)
        if record.exc_info:
            data["exc"] = self.formatException(record.exc_info)
        return json.dumps(data, ensure_ascii=False, default=str)


def configure_logging(level: int = logging.INFO) -> None:
    root = logging.getLogger()
    if any(getattr(h, "_kyc_json", False) for h in root.handlers):
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    handler._kyc_json = True  # type: ignore[attr-defined]
    root.addHandler(handler)
    root.setLevel(level)


def redact_text(text: str | None) -> str:
    """Return the text only when OCR-text logging is explicitly enabled."""
    if text is None:
        return "<none>"
    if get_settings().log_ocr_text:
        return text
    return f"<redacted {len(text)} chars>"
