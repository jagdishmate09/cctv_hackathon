from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Tuple

from src.core.policy import CameraPolicy
from src.core.budget import BudgetManager


@dataclass
class AgentConfig:
    motion_to_med: float = 0.02
    meeting_room_med_ratio: float = 0.8
    meeting_room_high_ratio: float = 1.0
    budget_reserve_seconds: float = 30.0


class WorkflowAgent:
    """Simple agent that chooses LOW/MED/HIGH based on policy, signals, and budget."""

    def __init__(self, budget: BudgetManager, cfg: AgentConfig | None = None):
        self.budget = budget
        self.cfg = cfg or AgentConfig()
        self._mode_by_cam: Dict[str, str] = {}

    def decide(
        self,
        ts: datetime,
        policy: CameraPolicy,
        motion_score: float,
        in_roi_person_count: int,
        presence_seconds: float,
    ) -> Tuple[str, Dict[str, Any] | None]:
        cam_id = policy.camera_id
        prev = self._mode_by_cam.get(cam_id, 'LOW')
        target = prev
        reason = None

        # Budget gating: if near exhausted, force LOW
        if self.budget.is_exhausted(ts, reserve_seconds=self.cfg.budget_reserve_seconds):
            if prev != 'LOW':
                target = 'LOW'
                reason = 'Budget low -> forcing LOW'
        else:
            # Baseline for restricted zones
            if policy.zone_type == 'RESTRICTED' and prev == 'LOW':
                target = 'MED'
                reason = 'Restricted zone baseline monitoring'

            # Meeting room utilization logic (occupancy-based escalation)
            if policy.zone_type == 'UNRESTRICTED' and policy.allowed_occupancy > 0:
                if in_roi_person_count > policy.allowed_occupancy:
                    if prev != 'HIGH':
                        target = 'HIGH'
                        reason = 'Meeting room over capacity'
                elif in_roi_person_count >= int(self.cfg.meeting_room_med_ratio * policy.allowed_occupancy):
                    if prev == 'LOW':
                        target = 'MED'
                        reason = 'Meeting room high occupancy'
                else:
                    # downgrade from MED/HIGH when occupancy normal
                    if prev in ('MED', 'HIGH') and in_roi_person_count <= int(0.6 * policy.allowed_occupancy):
                        target = 'LOW'
                        reason = 'Meeting room occupancy normalized'

            # Motion-based escalation (generic)
            if reason is None and motion_score >= self.cfg.motion_to_med and prev == 'LOW':
                target = 'MED'
                reason = 'Motion above threshold'

        decision = None
        if target != prev:
            self._mode_by_cam[cam_id] = target
            decision = {
                'timestamp': ts.isoformat(),
                'camera_id': cam_id,
                'decision': 'SET_MODE',
                'from_mode': prev,
                'to_mode': target,
                'reason': reason or '',
                'signals': {
                    'motion_score': round(float(motion_score), 4),
                    'in_roi_person_count': int(in_roi_person_count),
                    'presence_seconds': round(float(presence_seconds), 2),
                },
                'budget_remaining_sec': round(self.budget.remaining(ts), 2),
            }
        else:
            self._mode_by_cam[cam_id] = prev

        return self._mode_by_cam[cam_id], decision
