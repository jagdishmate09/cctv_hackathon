from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict


@dataclass
class AlertEvent:
    timestamp: datetime
    camera_id: str
    zone_name: str
    zone_type: str
    alert_type: str
    severity: str
    details: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "camera_id": self.camera_id,
            "zone_name": self.zone_name,
            "zone_type": self.zone_type,
            "alert_type": self.alert_type,
            "severity": self.severity,
            "details": self.details,
        }
