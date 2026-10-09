"""A clean, throw-away database for the tests: schema and master data (groups, accounts, periods, settings) rebuilt from
the committed Access export, with no operational data - so the tests never depend on what is in the real database.

SQLite by default (a file in a temporary folder). With USOOL_TEST_DATABASE_URL set (npm run test:pg) the same tests run on
PostgreSQL: that database is emptied first, so point it at a database used only for tests."""
import os
import tempfile
from pathlib import Path

from app import db

OPERATIONAL = ["tbl_AssetCountLines", "tbl_AssetCounts", "tbl_DepreciationJournal", "tbl_Depreciation", "tbl_AssetAttachments", "tbl_AssetCustody", "tbl_Maintenance",
               "tbl_AssetTransactions", "tbl_Assets", "tbl_Suppliers", "tbl_Employees", "tbl_AuditLog", "tbl_Sessions", "tbl_UserBranches", "tbl_Users"]
PG_URL = os.environ.get("USOOL_TEST_DATABASE_URL", "").strip()


def empty_db(name: str = "t.db") -> Path:
    """Point the app at a new, empty database (no tables yet). Returns a temporary folder for files."""
    tmp = Path(tempfile.mkdtemp())
    db.DB_PATH = tmp / name
    db.DATA_DIR = tmp
    db.URL = PG_URL or None
    if PG_URL:
        import psycopg
        with psycopg.connect(PG_URL, autocommit=True) as c:
            c.execute("DROP SCHEMA IF EXISTS public CASCADE")
            c.execute("CREATE SCHEMA public")
    return tmp


def fresh_db(name: str = "t.db") -> Path:
    """An empty database filled with master data only. Returns the temporary folder."""
    tmp = empty_db(name)
    db.migrate_from_access()
    con = db.connect()
    for t in OPERATIONAL:
        con.execute(f"DELETE FROM {t}")
    con.execute("UPDATE tbl_DepreciationPeriods SET PeriodStatus='OPEN'")
    con.commit()
    con.close()
    return tmp
