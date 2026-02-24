"""
Query OCCUPANCY_DATA from Oracle (debug). Uses backend .env.
Run from backend: python query_occupancy_db.py
"""
import os
from pathlib import Path

env_path = Path(__file__).resolve().parent / ".env"
if env_path.exists():
    from dotenv import load_dotenv
    load_dotenv(env_path)

ORACLE_URL = os.environ.get("ORACLE_URL")
ORACLE_USERNAME = os.environ.get("ORACLE_USERNAME")
ORACLE_PASSWORD = os.environ.get("ORACLE_PASSWORD")

if not all([ORACLE_URL, ORACLE_USERNAME, ORACLE_PASSWORD]):
    print("Missing ORACLE_* in .env")
    exit(1)

def main():
    try:
        import oracledb
    except ImportError:
        print("Install oracledb: pip install oracledb")
        exit(1)

    try:
        conn = oracledb.connect(user=ORACLE_USERNAME, password=ORACLE_PASSWORD, dsn=ORACLE_URL)
        cur = conn.cursor()
        cur.execute("""
            SELECT ID, CAMERA_NUMBER, OCCUPANCY_DATE, OCCUPANCY_TIME, NO_OF_PEOPLE, CREATED_AT
            FROM OCCUPANCY_DATA
            ORDER BY CAMERA_NUMBER, OCCUPANCY_DATE, OCCUPANCY_TIME
        """)
        rows = cur.fetchall()
        col_names = [c[0] for c in cur.description]
        print(f"OCCUPANCY_DATA: {len(rows)} row(s)")
        print("-" * 80)
        for r in rows:
            print(dict(zip(col_names, r)))
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Error: {e}")
        exit(1)

if __name__ == "__main__":
    main()
