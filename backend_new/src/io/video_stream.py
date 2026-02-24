from __future__ import annotations

from typing import Iterator, Tuple, Any
from datetime import datetime, timedelta
import cv2
import time
import math


class VideoStream:
    """
    Reads frames from webcam index / video file / RTSP (later).

    Behavior:
      - FILE inputs (mp4, etc): offline sampling based on VIDEO time.
        * No sleeping
        * Deterministic sampling ~target_fps using fractional frame steps
        * Reaches EOF reliably
      - LIVE inputs (webcam/rtsp): wall-clock throttled sampling.
    """

    def __init__(self, source, camera_id: str, target_fps: float = 2.0):
        self.source = source
        self.camera_id = camera_id
        self.target_fps = max(float(target_fps), 0.1)

        self.cap = cv2.VideoCapture(source)
        if not self.cap.isOpened():
            raise RuntimeError(f"Failed to open video source: {source}")

        self.is_file = isinstance(source, str) and not source.lower().startswith((
            'rtsp://', 'http://', 'https://'
        ))

        # Live throttling
        self._min_interval = 1.0 / self.target_fps
        self._last_wall_ts = 0.0

        # File sampling
        self.file_fps = 0.0
        self.frame_index = 0
        self.start_ts = datetime.now()
        self._step_exact = None
        self._next_sample_frame = 0

        if self.is_file:
            fps = self.cap.get(cv2.CAP_PROP_FPS)
            if fps is None or fps <= 0:
                fps = 25.0
            self.file_fps = float(fps)
            self._step_exact = self.file_fps / self.target_fps
            self._next_sample_frame = 0

    def frames(self) -> Iterator[Tuple[datetime, str, Any]]:
        while True:
            ok, frame = self.cap.read()
            if not ok:
                break

            if self.is_file:
                idx = self.frame_index
                self.frame_index += 1

                if idx < self._next_sample_frame:
                    continue

                # fractional stepping: avoids rounding bias
                self._next_sample_frame = int(math.floor(self._next_sample_frame + float(self._step_exact)))

                video_seconds = idx / max(self.file_fps, 1e-9)
                ts = self.start_ts + timedelta(seconds=video_seconds)
                yield ts, self.camera_id, frame

            else:
                # live source: wall-clock throttling
                now = time.time()
                if now - self._last_wall_ts < self._min_interval:
                    time.sleep(0.001)
                    continue

                self._last_wall_ts = now
                yield datetime.now(), self.camera_id, frame

    def close(self):
        try:
            self.cap.release()
        except Exception:
            pass
