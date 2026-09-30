"""Remove all operational (test) data and leave a clean, consistent system.

    python tools/reset_test_data.py --yes [--keep-contacts]

Deletes assets, depreciation, journal, transactions, maintenance, custody, attachments (files too),
suppliers, employees and the audit log; removes locations / cost centers whose code starts with TEST-;
resets the numbering counters and re-opens every depreciation period.
Keeps the settings, groups, ledger accounts, methods, currencies and periods.
Runs database integrity checks afterwards and exits with an error if anything is inconsistent.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app import db, services as s  # noqa: E402

OPERATIONAL = ["tbl_DepreciationJournal", "tbl_Depreciation", "tbl_AssetAttachments", "tbl_AssetCustody", "tbl_Maintenance",
               "tbl_AssetTransactions", "tbl_Assets", "tbl_AuditLog"]
CONTACTS = ["tbl_Suppliers", "tbl_Employees"]


def counts(con, tables):
    return {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in tables}


def main(keep_contacts: bool) -> int:
    con = db.connect()
    tables = OPERATIONAL + ([] if keep_contacts else CONTACTS)
    print("before:", {k: v for k, v in counts(con, tables).items() if v})
    # files first, through the app's own removal (also prunes emptied folders)
    files = [r[0] for r in con.execute("SELECT FilePath FROM tbl_AssetAttachments")]
    for p in files:
        s._remove_file(p)
    for t in tables:
        con.execute(f"DELETE FROM {t}")
        con.execute("DELETE FROM sqlite_sequence WHERE name=?", (t,))
    for t, col in (("tbl_Locations", "LocationCode"), ("tbl_CostCenters", "CostCenterCode")):
        con.execute(f"DELETE FROM {t} WHERE {col} LIKE 'TEST-%'")
        if not con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]:
            con.execute("DELETE FROM sqlite_sequence WHERE name=?", (t,))
    con.execute("UPDATE tbl_DepreciationPeriods SET PeriodStatus='OPEN'")
    con.commit()

    # ---- consistency checks
    problems = []
    if con.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
        problems.append("integrity_check failed")
    fk = con.execute("PRAGMA foreign_key_check").fetchall()
    if fk:
        problems.append(f"{len(fk)} foreign key violation(s)")
    left = {k: v for k, v in counts(con, tables).items() if v}
    if left:
        problems.append(f"rows left: {left}")
    if con.execute("SELECT COUNT(*) FROM tbl_DepreciationPeriods WHERE PeriodStatus<>'OPEN'").fetchone()[0]:
        problems.append("a period is still closed")
    if con.execute("SELECT COUNT(*) FROM tbl_Settings WHERE SettingKey IN ('DefaultCurrency','VATRate','DisposalClearingAccountID')").fetchone()[0] != 3:
        problems.append("settings missing")
    att_root = s._attach_root(con)
    leftovers = [p for p in att_root.rglob("*") if p.is_file()]
    if leftovers:
        problems.append(f"{len(leftovers)} attachment file(s) left on disk")
    con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    print(f"removed {len(files)} attachment file(s)")
    if problems:
        print("PROBLEMS:", "; ".join(problems))
        return 1
    print("clean and consistent: numbering restarts at 0001, all periods open, settings and master data intact")
    return 0


if __name__ == "__main__":
    if "--yes" not in sys.argv:
        sys.exit(__doc__)
    sys.exit(main("--keep-contacts" in sys.argv))
