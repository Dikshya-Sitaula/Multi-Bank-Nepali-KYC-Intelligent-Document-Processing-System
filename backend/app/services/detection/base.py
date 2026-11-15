"""Field detection interface.

WHY an interface: the pipeline asks a detector "where are the fields on this aligned
page?". Today the only working detector is template alignment + OpenCV box snapping. The
trained YOLO detector (SPEC section 11) will implement the same interface, so swapping it
in changes no pipeline code. Every detection records which method produced it, and the
UI never calls a template-alignment detection a YOLO result.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from app.services.template.schema import Region


@dataclass
class Detection:
    region: Region
    bbox_px: tuple[int, int, int, int]          # final box on the aligned page
    template_bbox_px: tuple[int, int, int, int]  # box as defined in the template
    confidence: float                          # method-specific score in [0, 1]
    method: str                                # "template_alignment+snap" | "template_alignment" | "yolo"
    snap: dict[str, Any] = field(default_factory=dict)


class FieldDetector:
    name = "base"
    available = False
    status_text = ""

    def detect(self, aligned: np.ndarray, regions: list[Region], registration_overlap: float) -> list[Detection]:  # pragma: no cover
        raise NotImplementedError


class YOLODetectorUnavailable(FieldDetector):
    """Placeholder that reports honestly that no trained YOLO weights exist."""

    name = "yolo"
    available = False
    status_text = "YOLO model not trained yet."

    def detect(self, aligned, regions, registration_overlap):  # noqa: ANN001
        raise RuntimeError(self.status_text)
