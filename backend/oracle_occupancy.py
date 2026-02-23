"""
Oracle occupancy: parse DAV filename and insert 10-minute bucket stats.
Filename format: XVR_<camera>_main_<startYYYYMMDDhhmmss>_<endYYYYMMDDhhmmss>.dav
Example: XVR_ch13_main_20250421130012_20250421140012.dav
"""
import re
import os
from datetime import datetime
from typing import Optional, Tuple, List, Dict, Any

# Optional: load .env when this module is used from app
try:
    from dotenv import load_dotenv
    from pathlib import Path
    env_path = Path(__file__).resolve().parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except Exception:
    pass

# Pattern: XVR_<camera>_main_<14 digits>_<14 digits>.dav
DAV_FILENAME_PATTERN = re.compile(
    r"^XVR_(.+)_main_(\d{14})_(\d{14})\.dav$",
    re.IGNORECASE
)


def parse_dav_filename(filename: str) -> Optional[Dict[str, Any]]:
    """
    Parse DAV filename. Returns None if format doesn't match.
    Returns dict with: camera_number, occupancy_date (YYYY-MM-DD), start_ts (seconds from midnight of start day),
                       start_hour, start_min, start_sec for building time windows.
    """
    if not filename:
        return None
    base = os.path.basename(filename)
    m = DAV_FILENAME_PATTERN.match(base.strip())
    if not m:
        return None
    camera_number = m.group(1).strip()
    start_str = m.group(2)  # 20250421130012
    end_str = m.group(3)
    try:
        start_dt = datetime.strptime(start_str, "%Y%m%d%H%M%S")
    except ValueError:
        return None
    occupancy_date = start_dt.strftime("%Y-%m-%d")
    start_sec_from_midnight = (
        start_dt.hour * 3600 + start_dt.minute * 60 + start_dt.second
    )
    return {
        "camera_number": camera_number,
        "occupancy_date": occupancy_date,
        "start_ts_sec": start_sec_from_midnight,
        "start_hour": start_dt.hour,
        "start_min": start_dt.minute,
        "start_sec": start_dt.second,
    }


def bucket_index_to_time_window(
    bucket_index: int,
    start_hour: int,
    start_min: int,
    start_sec: int,
) -> str:
    """Format 10-minute bucket as 'HH:MM-HH:MM' (e.g. '13:00-13:10')."""
    start_total_mins = start_hour * 60 + start_min
    window_start_mins = start_total_mins + bucket_index * 10
    window_end_mins = window_start_mins + 10
    h1, m1 = divmod(window_start_mins, 60)
    h2, m2 = divmod(window_end_mins, 60)
    return f"{h1:02d}:{m1:02d}-{h2:02d}:{m2:02d}"


def insert_occupancy_buckets(
    camera_number: str,
    occupancy_date: str,
    start_hour: int,
    start_min: int,
    start_sec: int,
    buckets: List[Dict[str, Any]],
) -> Tuple[bool, Optional[str]]:
    """
    buckets: list of dicts with keys max_people, unoccupied_chairs, occupied_chairs, occupancy_rate
    (one per 10-minute bucket, in order).
    Returns (success, error_message).
    """
    url = os.environ.get("ORACLE_URL")
    user = os.environ.get("ORACLE_USERNAME")
    password = os.environ.get("ORACLE_PASSWORD")
    if not all([url, user, password]):
        return False, "Oracle credentials not configured"

    try:
        import oracledb
    except ImportError:
        return False, "oracledb not installed"

    insert_sql = """
    INSERT INTO OCCUPANCY_DATA (
        CAMERA_NUMBER, OCCUPANCY_DATE, OCCUPANCY_TIME,
        NO_OF_PEOPLE, NO_OF_UNOCCUPIED_CHAIRS, NO_OF_OCCUPIED_CHAIRS
    ) VALUES (
        :1, TO_DATE(:2, 'YYYY-MM-DD'), :3, :4, :5, :6
    )
    """
    try:
        conn = oracledb.connect(user=user, password=password, dsn=url)
        cur = conn.cursor()
        for i, b in enumerate(buckets):
            time_window = bucket_index_to_time_window(
                i, start_hour, start_min, start_sec
            )
            cur.execute(
                insert_sql,
                (
                    camera_number,
                    occupancy_date,
                    time_window,
                    b.get("max_people", 0),
                    b.get("unoccupied_chairs", 0),
                    b.get("occupied_chairs", 0),
                ),
            )
        conn.commit()
        cur.close()
        conn.close()
        return True, None
    except Exception as e:
        return False, str(e)
