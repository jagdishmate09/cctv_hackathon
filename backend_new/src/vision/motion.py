from __future__ import annotations

from dataclasses import dataclass
import cv2
import numpy as np


@dataclass
class MotionConfig:
    resize_width: int = 320
    diff_threshold: int = 25
    min_changed_fraction: float = 0.01
    ema_alpha: float = 0.2


class MotionDetector:
    def __init__(self, cfg: MotionConfig):
        self.cfg = cfg
        self.prev_gray: np.ndarray | None = None
        self.ema_score: float = 0.0

    def score(self, frame: np.ndarray) -> float:
        # Resize for speed
        h, w = frame.shape[:2]
        rw = self.cfg.resize_width
        if w > rw:
            scale = rw / float(w)
            frame_small = cv2.resize(frame, (rw, int(h * scale)))
        else:
            frame_small = frame

        gray = cv2.cvtColor(frame_small, cv2.COLOR_BGR2GRAY)

        if self.prev_gray is None:
            self.prev_gray = gray
            self.ema_score = 0.0
            return 0.0

        diff = cv2.absdiff(gray, self.prev_gray)
        _, thresh = cv2.threshold(diff, self.cfg.diff_threshold, 255, cv2.THRESH_BINARY)

        changed = float(np.count_nonzero(thresh))
        total = float(thresh.size)
        raw = (changed / total) if total > 0 else 0.0

        # EMA smoothing
        a = self.cfg.ema_alpha
        self.ema_score = a * raw + (1.0 - a) * self.ema_score

        self.prev_gray = gray
        return float(self.ema_score)

    def has_motion(self, motion_score: float) -> bool:
        return motion_score >= float(self.cfg.min_changed_fraction)
