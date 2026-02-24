from __future__ import annotations

import argparse
from datetime import datetime
import os
import time
import cv2

from src.core.policy import load_policies, is_access_allowed, CameraPolicy
from src.core.events import AlertEvent
from src.core.presence import PresenceTracker
from src.core.budget import BudgetManager, BudgetConfig
from src.core.agent import WorkflowAgent

from src.vision.detector_yolo import MultiModelYoloPersonDetector
from src.vision.roi import point_in_polygon, bbox_center
from src.vision.motion import MotionDetector, MotionConfig

from src.io.video_stream import VideoStream
from src.io.logger import JSONLLogger, JSONLogger


def compute_in_roi_count(dets, policy: CameraPolicy) -> int:
    if not policy.roi.polygon:
        return len(dets)
    in_roi = 0
    for d in dets:
        cx, cy = bbox_center(d.bbox)
        if point_in_polygon(cx, cy, policy.roi.polygon):
            in_roi += 1
    return in_roi


def decide_alert(ts: datetime, policy: CameraPolicy, in_roi_count: int, presence_seconds: float) -> AlertEvent | None:
    """Generate alerts based on policy.

    - Restricted zones: unauthorized time/day + over occupancy
    - Unrestricted (meeting rooms): optional over-capacity alert
    """

    # Meeting room / unrestricted over-capacity
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

    # Restricted zone alerts
    if policy.zone_type != "RESTRICTED":
        return None
    if in_roi_count <= 0:
        return None
    if presence_seconds < float(policy.min_presence_seconds):
        return None

    allowed_now = is_access_allowed(ts, policy)

    if not allowed_now:
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


def draw_roi(overlay, policy: CameraPolicy):
    if policy.roi.polygon:
        pts = policy.roi.polygon
        for i in range(len(pts)):
            x1, y1 = pts[i]
            x2, y2 = pts[(i + 1) % len(pts)]
            cv2.line(overlay, (x1, y1), (x2, y2), (0, 255, 255), 2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/zones.yaml")
    ap.add_argument("--camera-id", required=True, help="Tags the source as this camera/zone policy")
    ap.add_argument("--source", required=True, help="0 for webcam, or mp4 path (rtsp later)")
    ap.add_argument("--base-fps", type=float, default=2.0, help="Base sampling FPS")

    # YOLO variants by mode
    ap.add_argument("--model-low", default="yolov10s.pt")
    ap.add_argument("--model-med", default="yolov10m.pt")
    ap.add_argument("--model-high", default="yolov10b.pt")

    ap.add_argument("--gpu-budget-sec-per-hour", type=float, default=900.0)
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--save-debug", action="store_true")

    # Motion precheck tuning
    ap.add_argument("--motion-threshold", type=float, default=0.01, help="Min changed fraction (smoothed) to treat as motion")
    ap.add_argument("--skip-yolo-when-low-motion", action="store_true", help="If LOW mode and low motion, skip YOLO (heartbeat may still force it)")
    ap.add_argument("--min-yolo-interval-seconds", type=float, default=5.0, help="Force YOLO to run at least once every N seconds even if motion is low")
    ap.add_argument("--stale-occupancy-ttl-seconds", type=float, default=30.0, help="If YOLO is skipped, reuse last occupancy for up to N seconds")

    # Logging density
    ap.add_argument("--log-every-n-seconds", type=float, default=0.0, help="If >0, write an extra time-bucket metric row every N seconds (for TS analysis)")

    args = ap.parse_args()

    policies = load_policies(args.config)
    if args.camera_id not in policies:
        raise SystemExit(f"camera-id '{args.camera_id}' not found in {args.config}")
    policy = policies[args.camera_id]

    source = args.source
    if isinstance(source, str) and source.isdigit():
        source = int(source)

    detector = MultiModelYoloPersonDetector(args.model_low, args.model_med, args.model_high)
    presence = PresenceTracker()

    os.makedirs("logs", exist_ok=True)
    alerts_log = JSONLLogger("logs/alerts.jsonl")
    decisions_log = JSONLLogger("logs/decisions.jsonl")
    metrics_log = JSONLLogger("logs/metrics.jsonl")
    summary_writer = JSONLogger("logs/run_summary.json")

    # Ensure log files exist even if no events happen
    open("logs/alerts.jsonl", "a", encoding="utf-8").close()
    open("logs/decisions.jsonl", "a", encoding="utf-8").close()
    open("logs/metrics.jsonl", "a", encoding="utf-8").close()

    budget = BudgetManager(BudgetConfig(gpu_seconds_per_hour=args.gpu_budget_sec_per_hour))
    agent = WorkflowAgent(budget)

    motion = MotionDetector(MotionConfig(min_changed_fraction=args.motion_threshold))

    stream = VideoStream(source=source, camera_id=args.camera_id, target_fps=args.base_fps)

    if args.save_debug:
        os.makedirs("outputs/debug_frames", exist_ok=True)

    last_alert_time: datetime | None = None
    alert_cooldown_seconds = 30.0

    stats = {
        "camera_id": args.camera_id,
        "zone_name": policy.zone_name,
        "zone_type": policy.zone_type,
        "source": str(args.source),
        "alerts_count": 0,
        "decisions_count": 0,
        "frames_seen": 0,
        "frames_yolo_run": 0,
        "frames_yolo_skipped": 0,
        "avg_in_roi_occupancy": 0.0,
        "yolo_skip_rate": 0.0,
    }

    occ_sum = 0.0
    mode = "LOW"

    last_yolo_ts: datetime | None = None
    last_in_roi_count: int = 0
    last_in_roi_ts: datetime | None = None

    # optional time bucket logging
    last_bucket_log_ts: datetime | None = None

    try:
        for ts, cam_id, frame in stream.frames():
            stats["frames_seen"] += 1

            motion_score = motion.score(frame)

            # Pre-pass agent decision (motion only)
            mode_candidate, decision = agent.decide(
                ts=ts,
                policy=policy,
                motion_score=motion_score,
                in_roi_person_count=0,
                presence_seconds=0.0,
            )
            if decision is not None:
                decisions_log.log(decision)
                stats["decisions_count"] += 1
                mode = mode_candidate

            # Motion + heartbeat gating
            if last_yolo_ts is None:
                heartbeat_due = True
            else:
                heartbeat_due = (ts - last_yolo_ts).total_seconds() >= args.min_yolo_interval_seconds

            low_motion = not motion.has_motion(motion_score)

            run_yolo = True
            if args.skip_yolo_when_low_motion and mode == "LOW" and low_motion and (not heartbeat_due):
                run_yolo = False

            dets = []
            if run_yolo:
                # Charge budget by measured inference time (best-effort)
                t0 = time.time()
                dets = detector.detect(frame, conf_thres=policy.person_conf_threshold, mode=mode)
                dt = time.time() - t0
                budget.charge(ts, seconds=dt)

                stats["frames_yolo_run"] += 1
                last_yolo_ts = ts

                in_roi_count = compute_in_roi_count(dets, policy)
                last_in_roi_count = in_roi_count
                last_in_roi_ts = ts
            else:
                stats["frames_yolo_skipped"] += 1

                # Persist last occupancy for seated people
                if last_in_roi_ts is not None and (ts - last_in_roi_ts).total_seconds() <= args.stale_occupancy_ttl_seconds:
                    in_roi_count = last_in_roi_count
                else:
                    in_roi_count = 0

            # Presence based on (possibly persisted) occupancy
            st = presence.update(cam_id, ts, is_present=(in_roi_count > 0))
            occ_sum += in_roi_count

            # Second pass agent decision (true signals)
            mode2, decision2 = agent.decide(
                ts=ts,
                policy=policy,
                motion_score=motion_score,
                in_roi_person_count=in_roi_count,
                presence_seconds=st.seconds_present,
            )
            if decision2 is not None:
                # Avoid duplicate event logging if identical to first-pass
                if decision is None or decision2.get('to_mode') != decision.get('to_mode'):
                    decisions_log.log(decision2)
                    stats["decisions_count"] += 1
            mode = mode2

            # Metrics (per sample)
            metrics_log.log({
                "timestamp": ts.isoformat(),
                "camera_id": cam_id,
                "zone_name": policy.zone_name,
                "zone_type": policy.zone_type,
                "mode": mode,
                "motion_score": round(motion_score, 4),
                "yolo_ran": bool(run_yolo),
                "in_roi_person_count": int(in_roi_count),
                "presence_seconds": round(st.seconds_present, 2),
                "allowed_now": bool(is_access_allowed(ts, policy)),
                "budget_remaining_sec": round(budget.remaining(ts), 2),
            })

            # Optional bucket log for time-series analysis
            if args.log_every_n_seconds and args.log_every_n_seconds > 0:
                if last_bucket_log_ts is None or (ts - last_bucket_log_ts).total_seconds() >= args.log_every_n_seconds:
                    metrics_log.log({
                        "timestamp": ts.isoformat(),
                        "camera_id": cam_id,
                        "zone_name": policy.zone_name,
                        "zone_type": policy.zone_type,
                        "kind": "bucket_snapshot",
                        "mode": mode,
                        "in_roi_person_count": int(in_roi_count),
                        "presence_seconds": round(st.seconds_present, 2),
                        "yolo_skip_rate_so_far": round(stats["frames_yolo_skipped"] / max(1, stats["frames_seen"]), 3),
                        "budget_remaining_sec": round(budget.remaining(ts), 2),
                    })
                    last_bucket_log_ts = ts

            # Alerts
            alert = decide_alert(ts, policy, in_roi_count, st.seconds_present)
            if alert is not None:
                if last_alert_time is None or (ts - last_alert_time).total_seconds() >= alert_cooldown_seconds:
                    alerts_log.log(alert.to_dict())
                    stats["alerts_count"] += 1
                    last_alert_time = ts
                    print(f"[ALERT] {alert.alert_type} | {alert.camera_id} | {alert.zone_name}")

            # Debug overlays
            if args.show or args.save_debug:
                overlay = frame.copy()
                draw_roi(overlay, policy)

                for d in dets:
                    x1, y1, x2, y2 = map(int, d.bbox)
                    cv2.rectangle(overlay, (x1, y1), (x2, y2), (0, 255, 0), 2)

                txt = (
                    f"{cam_id} | {policy.zone_name} | mode={mode} | motion={motion_score:.3f} | "
                    f"yolo={run_yolo} | inROI={in_roi_count} | pres={st.seconds_present:.1f}s | "
                    f"allowed={is_access_allowed(ts, policy)} | budget={budget.remaining(ts):.0f}s"
                )
                cv2.putText(overlay, txt, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (50, 255, 50), 2)

                if args.show:
                    cv2.imshow("CCTV Agentic Debug", overlay)
                    if cv2.waitKey(1) & 0xFF == ord("q"):
                        break

                if args.save_debug:
                    out_path = os.path.join("outputs/debug_frames", f"{cam_id}_{ts.strftime('%Y%m%d_%H%M%S_%f')}.jpg")
                    cv2.imwrite(out_path, overlay)

    finally:
        stream.close()
        if args.show:
            cv2.destroyAllWindows()

        stats["avg_in_roi_occupancy"] = round(occ_sum / max(1, stats["frames_seen"]), 3)
        stats["yolo_skip_rate"] = round(stats["frames_yolo_skipped"] / max(1, stats["frames_seen"]), 3)
        summary_writer.write(stats)
        print("[DONE] Summary written to logs/run_summary.json")


if __name__ == "__main__":
    main()