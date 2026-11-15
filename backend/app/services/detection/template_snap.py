"""Template-alignment field detector with OpenCV box snapping.

After registration, every template region is at (almost) the right place on the aligned
page. Small residual misalignment remains, so each region is "snapped" to the real
printed box found on the aligned page by OpenCV (the same rectangle/cell/checkbox
detector used for template proposals): if a detected printed box overlaps the template
box well (IoU >= threshold) the region takes the detected box's exact coordinates. The
shift and IoU before/after are recorded so the snapping can be inspected.

Confidence = registration overlap x (snap IoU if snapped, else 0.8): a documented
heuristic, not a probability. Regions without a printed box (write-on lines) keep the
template box.
"""
from __future__ import annotations

import numpy as np

from app.services.detection.base import Detection, FieldDetector
from app.services.template.proposals import detect_raster, iou
from app.services.template.schema import Region


class TemplateSnapDetector(FieldDetector):
    name = "template_alignment+snap"
    available = True
    status_text = "Template-alignment mode with OpenCV box snapping."

    def __init__(self, min_iou: float = 0.55) -> None:
        self.min_iou = min_iou
        self.last_candidates: list = []

    def detect(self, aligned: np.ndarray, regions: list[Region], registration_overlap: float) -> list[Detection]:
        H, W = aligned.shape[:2]
        cands = [c for c in detect_raster(aligned) if c.kind in ("box", "cell_strip", "checkbox", "frame")]
        self.last_candidates = cands
        out: list[Detection] = []
        for r in regions:
            x, y, w, h = r.bbox
            tb = (int(x * W), int(y * H), int(w * W), int(h * H))
            txyxy = (tb[0], tb[1], tb[0] + tb[2], tb[1] + tb[3])
            best, best_iou = None, 0.0
            for c in cands:
                v = iou(txyxy, c.as_xyxy())
                if v > best_iou:
                    best, best_iou = c, v
            if best is not None and best_iou >= self.min_iou and r.checkbox_options is None:
                fb = (best.x, best.y, best.w, best.h)
                shift = float(np.hypot((fb[0] + fb[2] / 2) - (tb[0] + tb[2] / 2), (fb[1] + fb[3] / 2) - (tb[1] + tb[3] / 2)))
                snap = {"snapped": True, "iou_before": round(best_iou, 4), "shift_px": round(shift, 2),
                        "printed_kind": best.kind}
                conf = registration_overlap * best_iou
            else:
                fb = tb
                snap = {"snapped": False, "iou_before": round(best_iou, 4), "shift_px": 0.0}
                conf = registration_overlap * 0.8
            out.append(Detection(region=r, bbox_px=fb, template_bbox_px=tb, confidence=round(float(conf), 4),
                                 method=self.name, snap=snap))
        return out
