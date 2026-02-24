"""
Drop chair and occupancy_rate columns from OCCUPANCY_DATA so the table
stores only person count (chairs managed manually).
Run if you have the old table with NO_OF_UNOCCUPIED_CHAIRS, NO_OF_OCCUPIED_CHAIRS,
TOTAL_CHAIRS, OCCUPANCY_RATE.
Usage: cd backend && python migrate_occupancy_person_only.py
"""
import os
from pathlib import Path

env_path = Path(__file__).resolve().parent / ".env"
if env_path.exists():
    from dotenv import load_dotenv
    load_dotenv(env_path)

for key in ("ORACLE_URL", "ORACLE_USERNAME", "ORACLE_PASSWORD"):
    if not os.environ.get(key):
        print(f"Missing {key} in .env")
        exit(1)

try:
    import oracledb
except ImportError:
    print("Install oracledb: pip install oracledb")
    exit(1)

conn = oracledb.connect(
    user=os.environ["ORACLE_USERNAME"],
    password=os.environ["ORACLE_PASSWORD"],
    dsn=os.environ["ORACLE_URL"],
)
cur = conn.cursor()
cols_to_drop = ["NO_OF_UNOCCUPIED_CHAIRS", "NO_OF_OCCUPIED_CHAIRS", "TOTAL_CHAIRS", "OCCUPANCY_RATE"]
for col in cols_to_drop:
    try:
        cur.execute(f"ALTER TABLE OCCUPANCY_DATA DROP COLUMN {col}")
        conn.commit()
        print(f"Dropped column {col}.")
    except oracledb.Error as e:
        if "ORA-00904" in str(e):
            print(f"Column {col} does not exist, skipping.")
        else:
            print(f"Error dropping {col}: {e}")
cur.close()
conn.close()
print("Done. Table now has only CAMERA_NUMBER, OCCUPANCY_DATE, OCCUPANCY_TIME, NO_OF_PEOPLE, CREATED_AT.")
