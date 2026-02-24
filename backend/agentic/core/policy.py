from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Tuple
import yaml


@dataclass
class ROIConfig:
    polygon: List[List[int]]


@dataclass
class CameraPolicy:
    camera_id: str
    zone_name: str
    zone_type: str  # RESTRICTED / UNRESTRICTED
    allowed_days: List[str]
    allowed_time: Tuple[str, str]  # (start, end) HH:MM
    allowed_occupancy: int
    min_presence_seconds: float
    person_conf_threshold: float
    roi: ROIConfig


def load_policies(path: str) -> Dict[str, CameraPolicy]:
    with open(path, 'r', encoding='utf-8') as f:
        cfg = yaml.safe_load(f) or {}

    cams = cfg.get('cameras', {})
    policies: Dict[str, CameraPolicy] = {}
    for cam_id, c in cams.items():
        if cam_id == 'run_command':
            continue
        roi_cfg = c.get('roi', {}) or {}
        policy = CameraPolicy(
            camera_id=cam_id,
            zone_name=c.get('zone_name', cam_id),
            zone_type=str(c.get('zone_type', 'UNRESTRICTED')).upper(),
            allowed_days=list(c.get('allowed_days', ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'])),
            allowed_time=tuple(c.get('allowed_time', ['00:00','23:59'])),
            allowed_occupancy=int(c.get('allowed_occupancy', 999)),
            min_presence_seconds=float(c.get('min_presence_seconds', 0)),
            person_conf_threshold=float(c.get('person_conf_threshold', 0.35)),
            roi=ROIConfig(polygon=list(roi_cfg.get('polygon', []))),
        )
        policies[cam_id] = policy
    return policies


def _weekday_str(ts: datetime) -> str:
    return ts.strftime('%a')


def _hhmm(ts: datetime) -> str:
    return ts.strftime('%H:%M')


def is_access_allowed(ts: datetime, policy: CameraPolicy) -> bool:
    day = _weekday_str(ts)
    if policy.allowed_days and day not in policy.allowed_days:
        return False
    start, end = policy.allowed_time
    now = _hhmm(ts)
    if start <= end:
        return start <= now <= end
    return now >= start or now <= end
