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
    mins_per_bucket: int = 1,
) -> str:
    """Format bucket as 'HH:MM-HH:MM' (e.g. 1-min '13:16-13:17' or 10-min '13:00-13:10')."""
    start_total_mins = start_hour * 60 + start_min
    window_start_mins = start_total_mins + bucket_index * mins_per_bucket
    window_end_mins = window_start_mins + mins_per_bucket
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
    mins_per_bucket: int = 1,
    bucket_start_index: int = 0,
) -> Tuple[bool, Optional[str]]:
    """
    buckets: list of dicts with key max_people (one per time bucket, in order).
    mins_per_bucket: 1 = one row per minute with max people in that minute; 10 = per 10 minutes.
    bucket_start_index: when passing a single bucket, this is the minute index (so time window is correct).
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

    # MERGE (upsert): no duplicate rows for same camera+date+time. Update NO_OF_PEOPLE to max if row exists.
    merge_sql = """
    MERGE INTO OCCUPANCY_DATA t
    USING (
        SELECT :cam AS camera_number,
               TO_DATE(:dt, 'YYYY-MM-DD') AS occupancy_date,
               :tm AS occupancy_time,
               :people AS no_of_people
        FROM DUAL
    ) s
    ON (t.CAMERA_NUMBER = s.camera_number
        AND t.OCCUPANCY_DATE = s.occupancy_date
        AND t.OCCUPANCY_TIME = s.occupancy_time)
    WHEN MATCHED THEN
        UPDATE SET t.NO_OF_PEOPLE = GREATEST(t.NO_OF_PEOPLE, s.no_of_people)
    WHEN NOT MATCHED THEN
        INSERT (CAMERA_NUMBER, OCCUPANCY_DATE, OCCUPANCY_TIME, NO_OF_PEOPLE,
                NO_OF_UNOCCUPIED_CHAIRS, NO_OF_OCCUPIED_CHAIRS)
        VALUES (s.camera_number, s.occupancy_date, s.occupancy_time, s.no_of_people, 0, 0)
    """
    try:
        conn = oracledb.connect(user=user, password=password, dsn=url)
        cur = conn.cursor()
        for i, b in enumerate(buckets):
            time_window = bucket_index_to_time_window(
                bucket_start_index + i, start_hour, start_min, start_sec, mins_per_bucket
            )
            cur.execute(
                merge_sql,
                {
                    "cam": camera_number,
                    "dt": occupancy_date,
                    "tm": time_window,
                    "people": b.get("max_people", 0),
                },
            )
        conn.commit()
        cur.close()
        conn.close()
        print(f"[DB] Merged {len(buckets)} rows into OCCUPANCY_DATA (no duplicates) | camera={camera_number} date={occupancy_date}")
        return True, None
    except Exception as e:
        return False, str(e)


def insert_test_row() -> Tuple[bool, Optional[str]]:
    """
    Insert a single test row into OCCUPANCY_DATA (same table) with current timestamp.
    Use for testing that DB writes work. Inserts CAMERA_NUMBER='TEST_1MIN', current date,
    time window = current minute (e.g. 14:32-14:33), NO_OF_PEOPLE=0.
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
    from datetime import datetime
    now = datetime.utcnow()
    occupancy_date = now.strftime("%Y-%m-%d")
    # One-minute window: e.g. 14:32-14:33
    time_window = f"{now.hour:02d}:{now.minute:02d}-{now.hour:02d}:{(now.minute + 1) % 60:02d}"
    insert_sql = """
    INSERT INTO OCCUPANCY_DATA (
        CAMERA_NUMBER, OCCUPANCY_DATE, OCCUPANCY_TIME, NO_OF_PEOPLE,
        NO_OF_UNOCCUPIED_CHAIRS, NO_OF_OCCUPIED_CHAIRS
    ) VALUES (
        :1, TO_DATE(:2, 'YYYY-MM-DD'), :3, :4, 0, 0
    )
    """
    # Use placeholder 1 for test rows so NO_OF_PEOPLE isn't 0 (real counts come from video uploads)
    try:
        conn = oracledb.connect(user=user, password=password, dsn=url)
        cur = conn.cursor()
        cur.execute(
            insert_sql,
            ("TEST_1MIN", occupancy_date, time_window, 1),
        )
        conn.commit()
        cur.close()
        conn.close()
        print(f"[DB] (test inserter) 1 row TEST_1MIN | {occupancy_date} {time_window}")
        return True, None
    except Exception as e:
        return False, str(e)
