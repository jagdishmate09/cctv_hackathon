from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class BudgetConfig:
    gpu_seconds_per_hour: float = 900.0
    # Conservative estimate per YOLO run, used if caller doesn't provide a measured time.
    est_seconds_per_inference: float = 0.05


class BudgetManager:
    def __init__(self, cfg: BudgetConfig):
        self.cfg = cfg
        self._hour_start: datetime | None = None
        self._used: float = 0.0

    def _reset_if_new_hour(self, ts: datetime):
        if self._hour_start is None:
            self._hour_start = ts.replace(minute=0, second=0, microsecond=0)
            self._used = 0.0
            return

        hour_start = ts.replace(minute=0, second=0, microsecond=0)
        if hour_start != self._hour_start:
            self._hour_start = hour_start
            self._used = 0.0

    def charge(self, ts: datetime, seconds: float | None = None):
        self._reset_if_new_hour(ts)
        self._used += float(seconds if seconds is not None else self.cfg.est_seconds_per_inference)

    def remaining(self, ts: datetime) -> float:
        self._reset_if_new_hour(ts)
        return max(0.0, float(self.cfg.gpu_seconds_per_hour) - self._used)

    def is_exhausted(self, ts: datetime, reserve_seconds: float = 0.0) -> bool:
        return self.remaining(ts) <= reserve_seconds
