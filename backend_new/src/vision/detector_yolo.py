from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

import numpy as np


@dataclass
class Detection:
    bbox: tuple[float, float, float, float]
    conf: float


class MultiModelYoloPersonDetector:
    """Loads 3 YOLO models (LOW/MED/HIGH) and runs the one matching the selected mode."""

    def __init__(self, model_low: str, model_med: str, model_high: str):
        from ultralytics import YOLO

        self.model_paths = {
            'LOW': model_low,
            'MED': model_med,
            'HIGH': model_high,
        }
        self.models: Dict[str, any] = {}
        for k, p in self.model_paths.items():
            m = YOLO(p)
            # fuse if available
            try:
                m.fuse()
            except Exception:
                pass
            self.models[k] = m

    def detect(self, frame: np.ndarray, conf_thres: float, mode: str = 'LOW') -> List[Detection]:
        mode = (mode or 'LOW').upper()
        if mode not in self.models:
            mode = 'LOW'
        model = self.models[mode]

        results = model(
            frame,
            classes=[0],
            conf=float(conf_thres),
            iou=0.45,
            max_det=100,
            verbose=False,
        )

        dets: List[Detection] = []
        for r in results:
            if r.boxes is None or len(r.boxes) == 0:
                continue
            for b in r.boxes:
                x1, y1, x2, y2 = b.xyxy[0].cpu().numpy().tolist()
                c = float(b.conf[0].cpu().numpy())
                dets.append(Detection(bbox=(x1, y1, x2, y2), conf=c))
        return dets
