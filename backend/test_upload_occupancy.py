"""
Test script: upload sample occupancy data to OCCUPANCY_DATA using the same
function and SQL as the app (oracle_occupancy.insert_occupancy_buckets).
Run from backend folder with venv active: python test_upload_occupancy.py
"""
import os
from pathlib import Path
from datetime import datetime

# Load .env from backend directory (same as app)
env_path = Path(__file__).resolve().parent / ".env"
if env_path.exists():
    from dotenv import load_dotenv
    load_dotenv(env_path)
else:
    print("No .env found in backend folder.")
    exit(1)

# Use the same insert function as the app
from oracle_occupancy import insert_occupancy_buckets

def main():
    # Sample data that matches what the app would send (same columns/format)
    camera_number = "TEST_SCRIPT"
    today = datetime.utcnow().strftime("%Y-%m-%d")
    start_hour = datetime.utcnow().hour
    start_min = (datetime.utcnow().minute // 10) * 10  # round down to 10-min
    start_sec = 0
    # 3 buckets = 3 rows, like 10-min windows
    buckets = [
        {"max_people": 5},
        {"max_people": 8},
        {"max_people": 3},
    ]

    print("Connecting to Oracle and inserting into OCCUPANCY_DATA...")
    print(f"  CAMERA_NUMBER={camera_number}")
    print(f"  OCCUPANCY_DATE={today}")
    print(f"  start_hour={start_hour}, start_min={start_min}, start_sec={start_sec}")
    print(f"  buckets (rows): {buckets}")

    ok, err = insert_occupancy_buckets(
        camera_number=camera_number,
        occupancy_date=today,
        start_hour=start_hour,
        start_min=start_min,
        start_sec=start_sec,
        buckets=buckets,
    )

    if ok:
        print("OK: 3 rows inserted into OCCUPANCY_DATA. Check the table in your DB client.")
    else:
        print(f"FAILED: {err}")
        exit(1)

if __name__ == "__main__":
    main()
