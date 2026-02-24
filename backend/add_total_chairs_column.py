"""
Add TOTAL_CHAIRS and OCCUPANCY_RATE as virtual columns (if table had no virtual cols).
Or: ensure chair columns exist and are nullable; app does not insert chair data.
Usage: cd backend && python add_total_chairs_column.py
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

# Drop existing TOTAL_CHAIRS and OCCUPANCY_RATE if they exist (as stored columns)
for col in ("TOTAL_CHAIRS", "OCCUPANCY_RATE"):
    try:
        cur.execute(f"ALTER TABLE OCCUPANCY_DATA DROP COLUMN {col}")
        conn.commit()
        print(f"Dropped column {col}.")
    except oracledb.Error as e:
        if "ORA-00904" in str(e):
            print(f"Column {col} does not exist, skipping drop.")
        else:
            print(f"Error dropping {col}: {e}")
            cur.close()
            conn.close()
            exit(1)

# Add as virtual columns
try:
    cur.execute("""
        ALTER TABLE OCCUPANCY_DATA ADD (
            TOTAL_CHAIRS NUMBER GENERATED ALWAYS AS (NO_OF_UNOCCUPIED_CHAIRS + NO_OF_OCCUPIED_CHAIRS) VIRTUAL,
            OCCUPANCY_RATE NUMBER(5,2) GENERATED ALWAYS AS (
                CASE WHEN (NO_OF_UNOCCUPIED_CHAIRS + NO_OF_OCCUPIED_CHAIRS) > 0
                     THEN ROUND(100 * NO_OF_PEOPLE / (NO_OF_UNOCCUPIED_CHAIRS + NO_OF_OCCUPIED_CHAIRS), 2)
                     ELSE NULL END
            ) VIRTUAL
        )
    """)
    conn.commit()
    print("TOTAL_CHAIRS and OCCUPANCY_RATE added as virtual columns.")
except oracledb.Error as e:
    if "ORA-01430" in str(e):
        print("Virtual columns already exist. Nothing to do.")
    else:
        print(f"Error adding virtual columns: {e}")
finally:
    cur.close()
    conn.close()
