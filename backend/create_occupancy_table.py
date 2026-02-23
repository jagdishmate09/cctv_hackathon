"""
Create OCCUPANCY_DATA table in Oracle. Run once to set up the table.
TOTAL_CHAIRS and OCCUPANCY_RATE are virtual (generated) columns.
Usage: from backend folder with venv active: python create_occupancy_table.py
"""
import os
from pathlib import Path

# Load .env from backend directory
env_path = Path(__file__).resolve().parent / ".env"
if env_path.exists():
    from dotenv import load_dotenv
    load_dotenv(env_path)

ORACLE_URL = os.environ.get("ORACLE_URL")
ORACLE_USERNAME = os.environ.get("ORACLE_USERNAME")
ORACLE_PASSWORD = os.environ.get("ORACLE_PASSWORD")

if not all([ORACLE_URL, ORACLE_USERNAME, ORACLE_PASSWORD]):
    print("Missing ORACLE_URL, ORACLE_USERNAME, or ORACLE_PASSWORD in .env")
    exit(1)

CREATE_TABLE_SQL = """
CREATE TABLE OCCUPANCY_DATA (
    ID NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    CAMERA_NUMBER VARCHAR2(100) NOT NULL,
    OCCUPANCY_DATE DATE NOT NULL,
    OCCUPANCY_TIME VARCHAR2(20) NOT NULL,
    NO_OF_PEOPLE NUMBER NOT NULL,
    NO_OF_UNOCCUPIED_CHAIRS NUMBER NOT NULL,
    NO_OF_OCCUPIED_CHAIRS NUMBER NOT NULL,
    TOTAL_CHAIRS NUMBER GENERATED ALWAYS AS (NO_OF_UNOCCUPIED_CHAIRS + NO_OF_OCCUPIED_CHAIRS) VIRTUAL,
    OCCUPANCY_RATE NUMBER(5,2) GENERATED ALWAYS AS (
        CASE WHEN (NO_OF_UNOCCUPIED_CHAIRS + NO_OF_OCCUPIED_CHAIRS) > 0
             THEN ROUND(100 * NO_OF_PEOPLE / (NO_OF_UNOCCUPIED_CHAIRS + NO_OF_OCCUPIED_CHAIRS), 2)
             ELSE NULL END
    ) VIRTUAL,
    CREATED_AT TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
)
"""

def main():
    try:
        import oracledb
    except ImportError:
        print("Install oracledb: pip install oracledb")
        exit(1)

    try:
        conn = oracledb.connect(
            user=ORACLE_USERNAME,
            password=ORACLE_PASSWORD,
            dsn=ORACLE_URL,
        )
        cur = conn.cursor()
        cur.execute(CREATE_TABLE_SQL)
        conn.commit()
        print("Table OCCUPANCY_DATA created successfully.")
        cur.close()
        conn.close()
    except oracledb.Error as e:
        print(f"Oracle error: {e}")
        exit(1)

if __name__ == "__main__":
    main()
