"""
Agentic detection service: replaces the original PeopleDetector with the agentic pipeline.
- Single-frame APIs: multi-model YOLO (LOW/MED/HIGH) with a default mode; same response shape.
- Video APIs: full pipeline (motion, agent, presence, alerts) with optional camera_id.
"""
from __future__ import annotations

import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

# Agentic pipeline
from agentic.core.policy import (
    load_policies,
    is_access_allowed,
    CameraPolicy,
)
from agentic.core.events import AlertEvent
from agentic.core.presence import PresenceTracker
from agentic.core.budget import BudgetManager, BudgetConfig
from agentic.core.agent import WorkflowAgent
from agentic.vision.detector_yolo import MultiModelYoloPersonDetector, Detection
from agentic.vision.roi import point_in_polygon, bbox_center
from agentic.vision.motion import MotionDetector, MotionConfig


def _agentic_detections_to_dicts(dets: List[Detection]) -> List[Dict[str, Any]]:
    """Convert agentic Detection list to backend API format."""
    return [
        {
            "bbox": list(d.bbox),
            "confidence": float(d.conf),
            "class": "person",
            "class_id": 0,
        }
        for d in dets
    ]


def _get_config_path() -> str:
    base = Path(__file__).resolve().parent
    return os.environ.get("AGENTIC_ZONES_CONFIG", str(base / "config" / "zones.yaml"))


def _load_policy_for_camera(camera_id: Optional[str]) -> Tuple[CameraPolicy, str]:
    path = _get_config_path()
    policies = load_policies(path)
    if camera_id and camera_id in policies:
        return policies[camera_id], camera_id
    if policies:
        first = next(iter(policies.keys()))
        return policies[first], first
    raise RuntimeError(f"No camera policies in {path}. Add a 'default' or camera id to config.")


def compute_in_roi_count(dets: List[Detection], policy: CameraPolicy) -> int:
    if not policy.roi.polygon:
        return len(dets)
    in_roi = 0
    for d in dets:
        cx, cy = bbox_center(d.bbox)
        if point_in_polygon(cx, cy, policy.roi.polygon):
            in_roi += 1
    return in_roi


def decide_alert(
    ts: datetime, policy: CameraPolicy, in_roi_count: int, presence_seconds: float
) -> Optional[AlertEvent]:
    if policy.zone_type == "UNRESTRICTED":
        if in_roi_count > policy.allowed_occupancy and presence_seconds >= 5:
            return AlertEvent(
                timestamp=ts,
                camera_id=policy.camera_id,
                zone_name=policy.zone_name,
                zone_type=policy.zone_type,
                alert_type="MEETING_ROOM_OVER_CAPACITY",
                severity="MEDIUM",
                details={
                    "reason": "Meeting room occupancy exceeds configured capacity",
                    "allowed_occupancy": policy.allowed_occupancy,
                    "in_roi_person_count": in_roi_count,
                    "presence_seconds": round(presence_seconds, 2),
                },
            )
        return None
    if policy.zone_type != "RESTRICTED":
        return None
    if in_roi_count <= 0 or presence_seconds < float(policy.min_presence_seconds):
        return None
    if not is_access_allowed(ts, policy):
        return AlertEvent(
            timestamp=ts,
            camera_id=policy.camera_id,
            zone_name=policy.zone_name,
            zone_type=policy.zone_type,
            alert_type="UNAUTHORIZED_ENTRY_TIME",
            severity="HIGH",
            details={
                "reason": "Person present in restricted zone outside allowed time/day",
                "allowed_days": policy.allowed_days,
                "allowed_time": list(policy.allowed_time),
                "in_roi_person_count": in_roi_count,
                "presence_seconds": round(presence_seconds, 2),
            },
        )
    if in_roi_count > policy.allowed_occupancy:
        return AlertEvent(
            timestamp=ts,
            camera_id=policy.camera_id,
            zone_name=policy.zone_name,
            zone_type=policy.zone_type,
            alert_type="RESTRICTED_ZONE_OVER_OCCUPANCY",
            severity="MEDIUM",
            details={
                "reason": "Occupancy exceeds allowed limit for restricted zone",
                "allowed_occupancy": policy.allowed_occupancy,
                "in_roi_person_count": in_roi_count,
                "presence_seconds": round(presence_seconds, 2),
            },
        )
    return None


class AgenticPeopleDetector:
    """
    Drop-in replacement for PeopleDetector using the agentic pipeline.
    - Single-frame: runs YOLO in default mode (MED), returns same dict format.
    - draw_detections / get_detection_stats match the original API.
    """

    def __init__(
        self,
        model_low: str = "yolov10n.pt",
        model_med: str = "yolov10s.pt",
        model_high: str = "yolov10m.pt",
        default_mode: str = "MED",
    ):
        self._detector = MultiModelYoloPersonDetector(model_low, model_med, model_high)
        self._default_mode = (default_mode or "MED").upper()
        if self._default_mode not in ("LOW", "MED", "HIGH"):
            self._default_mode = "MED"
        self._policy, self._camera_id = _load_policy_for_camera(None)

    def detect_people(
        self,
        frame: np.ndarray,
        conf_threshold: float = 0.25,
        iou_threshold: float = 0.45,
        fast_inference: bool = False,
    ) -> List[Dict[str, Any]]:
        conf = max(0.1, float(conf_threshold))
        mode = "LOW" if fast_inference else self._default_mode
        policy_conf = getattr(self._policy, "person_conf_threshold", 0.25)
        conf = max(conf, policy_conf * 0.5)
        dets = self._detector.detect(frame, conf_thres=conf, mode=mode)
        return _agentic_detections_to_dicts(dets)

    def draw_detections(self, frame: np.ndarray, detections: List[Dict]) -> np.ndarray:
        annotated = frame.copy()
        for det in detections:
            x1, y1, x2, y2 = det["bbox"]
            confidence = det.get("confidence", 0)
            x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)
            cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 0), 2)
            label = f"Person {confidence:.2f}"
            label_size, _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
            cv2.rectangle(
                annotated,
                (x1, y1 - label_size[1] - 10),
                (x1 + label_size[0], y1),
                (0, 255, 0),
                -1,
            )
            cv2.putText(
                annotated,
                label,
                (x1, y1 - 5),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (0, 0, 0),
                2,
            )
        return annotated

    def get_detection_stats(self, detections: List[Dict]) -> Dict[str, Any]:
        if not detections:
            return {
                "count": 0,
                "avg_confidence": 0,
                "max_confidence": 0,
                "min_confidence": 0,
            }
        confidences = [d.get("confidence", 0) for d in detections]
        return {
            "count": len(detections),
            "avg_confidence": float(np.mean(confidences)),
            "max_confidence": float(np.max(confidences)),
            "min_confidence": float(np.min(confidences)),
        }


class AgenticVideoProcessor:
    """
    Stateful processor for video file / stream: motion, agent mode, presence, alerts.
    Call process_frame() for each frame; optional camera_id from request.
    """

    def __init__(
        self,
        camera_id: Optional[str] = None,
        model_low: str = "yolov10n.pt",
        model_med: str = "yolov10s.pt",
        model_high: str = "yolov10m.pt",
        gpu_budget_sec_per_hour: float = 900.0,
        motion_threshold: float = 0.01,
        min_yolo_interval_seconds: float = 2.0,
        stale_occupancy_ttl_seconds: float = 15.0,
        skip_yolo_when_low_motion: bool = True,
    ):
        self._policy, self._camera_id = _load_policy_for_camera(camera_id)
        self._detector = MultiModelYoloPersonDetector(model_low, model_med, model_high)
        self._motion = MotionDetector(MotionConfig(min_changed_fraction=motion_threshold))
        self._presence = PresenceTracker()
        self._budget = BudgetManager(BudgetConfig(gpu_seconds_per_hour=gpu_budget_sec_per_hour))
        self._agent = WorkflowAgent(self._budget)
        self._min_yolo_interval = min_yolo_interval_seconds
        self._stale_ttl = stale_occupancy_ttl_seconds
        self._skip_yolo_when_low_motion = skip_yolo_when_low_motion

        self._last_yolo_ts: Optional[datetime] = None
        self._last_in_roi_count: int = 0
        self._last_in_roi_ts: Optional[datetime] = None
        self._mode: str = "HIGH"  # Start in HIGH (yolov10m) for best accuracy; agent can downgrade
        self._last_alert_ts: Optional[datetime] = None
        self._alert_cooldown = 30.0

    @property
    def policy(self) -> CameraPolicy:
        return self._policy

    @property
    def camera_id(self) -> str:
        return self._camera_id

    def process_frame(
        self,
        frame: np.ndarray,
        ts: Optional[datetime] = None,
        frame_index: int = 0,
        fps: float = 25.0,
    ) -> Dict[str, Any]:
        if ts is None:
            ts = datetime.now()
        motion_score = self._motion.score(frame)
        heartbeat_due = (
            self._last_yolo_ts is None
            or (ts - self._last_yolo_ts).total_seconds() >= self._min_yolo_interval
        )
        low_motion = not self._motion.has_motion(motion_score)
        run_yolo = True
        if (
            self._skip_yolo_when_low_motion
            and self._mode == "LOW"
            and low_motion
            and (not heartbeat_due)
        ):
            run_yolo = False

        dets: List[Detection] = []
        if run_yolo:
            t0 = time.time()
            dets = self._detector.detect(
                frame,
                conf_thres=self._policy.person_conf_threshold,
                mode=self._mode,
            )
            self._budget.charge(ts, seconds=time.time() - t0)
            self._last_yolo_ts = ts
            in_roi_count = compute_in_roi_count(dets, self._policy)
            self._last_in_roi_count = in_roi_count
            self._last_in_roi_ts = ts
        else:
            if (
                self._last_in_roi_ts is not None
                and (ts - self._last_in_roi_ts).total_seconds() <= self._stale_ttl
            ):
                in_roi_count = self._last_in_roi_count
            else:
                in_roi_count = 0

        st = self._presence.update(
            self._camera_id, ts, is_present=(in_roi_count > 0)
        )
        mode2, _ = self._agent.decide(
            ts=ts,
            policy=self._policy,
            motion_score=motion_score,
            in_roi_person_count=in_roi_count,
            presence_seconds=st.seconds_present,
        )
        self._mode = mode2

        alert = decide_alert(ts, self._policy, in_roi_count, st.seconds_present)
        alert_dict: Optional[Dict] = None
        if alert is not None:
            if (
                self._last_alert_ts is None
                or (ts - self._last_alert_ts).total_seconds() >= self._alert_cooldown
            ):
                alert_dict = alert.to_dict()
                self._last_alert_ts = ts

        detections_dict = _agentic_detections_to_dicts(dets)
        return {
            "detections": detections_dict,
            "count": len(detections_dict),
            "in_roi_count": in_roi_count,
            "mode": self._mode,
            "motion_score": round(motion_score, 4),
            "presence_seconds": round(st.seconds_present, 2),
            "yolo_ran": run_yolo,
            "allowed_now": is_access_allowed(ts, self._policy),
            "alert": alert_dict,
        }


# Re-export for app.py: use agentic detector and keep extract_video_datetime from original
def extract_video_datetime(frame: np.ndarray) -> Optional[str]:
    """Extract date/time from CCTV OSD. Delegates to original detection_service if available."""
    try:
        from detection_service import extract_video_datetime as _extract
        return _extract(frame)
    except Exception:
        return None
