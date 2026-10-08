"""A clean, throw-away database for the tests: schema and master data (groups, accounts, periods, settings) rebuilt from
the committed Access export, with no operational data - so the tests never depend on what is in data/gooya_asset.db."""
import tempfile
from pathlib import Path

from app import db

OPERATIONAL = ["tbl_DepreciationJournal", "tbl_Depreciation", "tbl_AssetAttachments", "tbl_AssetCustody", "tbl_Maintenance",
               "tbl_AssetTransactions", "tbl_Assets", "tbl_Suppliers", "tbl_Employees", "tbl_AuditLog", "tbl_Sessions", "tbl_Users"]


def fresh_db(name: str = "t.db") -> Path:
    """Point the app at a new database in a temporary folder and fill it with master data only. Returns the folder."""
    tmp = Path(tempfile.mkdtemp())
    db.DB_PATH = tmp / name
    db.DATA_DIR = tmp
    db.migrate_from_access()
    con = db.connect()
    for t in OPERATIONAL:
        con.execute(f"DELETE FROM {t}")
    con.execute("UPDATE tbl_DepreciationPeriods SET PeriodStatus='OPEN'")
    con.commit()
    con.close()
    return tmp
