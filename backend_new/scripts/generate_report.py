import json
import os
from collections import defaultdict, Counter
from datetime import datetime

LOG_DIR = "logs"
OUT_DIR = "reports"
OUT_FILE = os.path.join(OUT_DIR, "report.md")


def read_jsonl(path):
    if not os.path.exists(path):
        return []
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def parse_ts(s: str) -> datetime:
    return datetime.fromisoformat(s)


def percentile(values, p: int):
    if not values:
        return 0
    values = sorted(values)
    k = int(len(values) * p / 100)
    k = min(k, len(values) - 1)
    return values[k]


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    metrics = read_jsonl(os.path.join(LOG_DIR, "metrics.jsonl"))
    alerts = read_jsonl(os.path.join(LOG_DIR, "alerts.jsonl"))
    decisions = read_jsonl(os.path.join(LOG_DIR, "decisions.jsonl"))

    if not metrics:
        print("No metrics found. Run the pipeline first.")
        return

    metrics_by_cam = defaultdict(list)
    alerts_by_cam = defaultdict(list)
    decisions_by_cam = defaultdict(list)

    for r in metrics:
        # ignore bucket snapshots for core stats
        if r.get("kind") == "bucket_snapshot":
            continue
        metrics_by_cam[r["camera_id"]].append(r)

    for a in alerts:
        alerts_by_cam[a.get("camera_id", "UNKNOWN")].append(a)

    for d in decisions:
        decisions_by_cam[d.get("camera_id", "UNKNOWN")].append(d)

    lines = []
    lines.append("# CCTV Whole-Run Analytics Report\n")

    for cam_id, rows in metrics_by_cam.items():
        rows = sorted(rows, key=lambda r: r["timestamp"])

        zone_name = rows[0].get("zone_name", "UNKNOWN")
        zone_type = rows[0].get("zone_type", "UNKNOWN")

        ts_list = [parse_ts(r["timestamp"]) for r in rows]
        window_start = min(ts_list)
        window_end = max(ts_list)
        duration_sec = (window_end - window_start).total_seconds()

        total_samples = len(rows)
        occ = [int(r.get("in_roi_person_count", 0)) for r in rows]
        avg_occ = sum(occ) / total_samples if total_samples else 0.0
        max_occ = max(occ) if occ else 0
        p95_occ = percentile(occ, 95)
        presence_rate = sum(1 for v in occ if v > 0) / total_samples if total_samples else 0.0

        yolo_run = sum(1 for r in rows if r.get("yolo_ran") is True)
        yolo_skip = sum(1 for r in rows if r.get("yolo_ran") is False)
        skip_rate = yolo_skip / total_samples if total_samples else 0.0

        mode_counter = Counter(r.get("mode", "UNKNOWN") for r in rows)

        cam_alerts = alerts_by_cam.get(cam_id, [])
        cam_decisions = decisions_by_cam.get(cam_id, [])
        decision_reasons = Counter(d.get("reason", "UNKNOWN") for d in cam_decisions if d.get("reason"))

        lines.append(f"## Camera: {cam_id}")
        lines.append(f"- Zone: {zone_name}")
        lines.append(f"- Zone Type: {zone_type}\n")

        lines.append("### Run Window")
        lines.append(f"- Start: {window_start}")
        lines.append(f"- End: {window_end}")
        lines.append(f"- Duration (sec): {duration_sec:.1f}")
        lines.append(f"- Samples: {total_samples}\n")

        lines.append("### Occupancy Statistics (whole run)")
        lines.append(f"- Average occupancy: {avg_occ:.2f} (mean of sampled in_roi_person_count)")
        lines.append(f"- Max occupancy: {max_occ}")
        lines.append(f"- P95 occupancy: {p95_occ}")
        lines.append(f"- Presence rate: {presence_rate*100:.1f}% (fraction of samples with occupancy > 0)\n")

        lines.append("### Workflow / Inference Efficiency")
        lines.append(f"- YOLO ran: {yolo_run}")
        lines.append(f"- YOLO skipped: {yolo_skip}")
        lines.append(f"- YOLO skip rate: {skip_rate*100:.1f}%")
        lines.append(f"- Mode distribution: {dict(mode_counter)}\n")

        lines.append("### Alerts")
        lines.append(f"- Total alerts: {len(cam_alerts)}")
        if cam_alerts:
            lines.append(f"- Alert types: {dict(Counter(a.get('alert_type','UNKNOWN') for a in cam_alerts))}")
        lines.append("")

        lines.append("### Agent Decision Insights")
        if decision_reasons:
            for reason, cnt in decision_reasons.most_common(5):
                lines.append(f"- {reason}: {cnt}")
        else:
            lines.append("- No agent mode changes logged.")

        lines.append("\n---\n")

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"[OK] Report generated at {OUT_FILE}")


if __name__ == "__main__":
    main()
