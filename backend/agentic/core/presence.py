from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict


@dataclass
class PresenceState:
    last_ts: datetime | None = None
    seconds_present: float = 0.0


class PresenceTracker:
    def __init__(self):
        self._states: Dict[str, PresenceState] = {}

    def update(self, camera_id: str, ts: datetime, is_present: bool) -> PresenceState:
        st = self._states.get(camera_id)
        if st is None:
            st = PresenceState(last_ts=ts, seconds_present=0.0)
            self._states[camera_id] = st
            return st
        if st.last_ts is None:
            st.last_ts = ts
            st.seconds_present = 0.0
            return st
        dt = (ts - st.last_ts).total_seconds()
        st.last_ts = ts
        if is_present:
            st.seconds_present += max(0.0, dt)
        else:
            st.seconds_present = 0.0
        return st
