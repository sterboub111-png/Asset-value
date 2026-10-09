"""Storage: a backup restores to exactly the same books, and the portable copy moves between SQLite and PostgreSQL.
Run:  python3 -m tests.test_storage            (SQLite)
      npm run test:pg                          (the same on PostgreSQL, plus PostgreSQL -> SQLite)"""
import tempfile
import zipfile
from pathlib import Path

from tests.fixture import fresh_db

tmp = fresh_db("st.db")
from app import db, services as s  # noqa: E402
from tools import restore_backup  # noqa: E402

con = db.connect()
s.set_actor("tester")
s.generate_periods(con, 2026)
cat = {r["CategoryCode"]: r["CategoryID"] for r in s.rows(con, "SELECT * FROM tbl_AssetCategories", raw=True)}
per = {p["PeriodNumber"]: p["PeriodID"] for p in s.rows(con, "SELECT * FROM tbl_DepreciationPeriods WHERE FiscalYear=2026", raw=True)}
s.master_save(con, "branches", {"BranchCode": "RYD", "BranchName": "Riyadh", "BranchNameAr": "الرياض", "CountryCode": "SA"})
van = s.save_asset(con, {"AssetName": "Van", "AssetNameAr": "سيارة نقل", "CategoryID": cat["VEH"], "AcquisitionDate": "2026-01-10", "PurchaseAmount": 12000, "VatApplicable": 0})
s.save_asset(con, {"AssetName": "Desk", "CategoryID": cat["FUR"], "AcquisitionDate": "2026-02-01", "PurchaseAmount": 3450, "VatApplicable": 1, "VatInclusive": 1})
for n in (1, 2, 3):
    s.run_depreciation(con, per[n]); s.post_depreciation(con, per[n])
s.revalue(con, van["AssetID"], {"TransactionDate": "2026-04-05", "NewValue": 9000})
s.save_settings(con, {"BackupFolder": str(tmp / "backups"), "AttachmentFolder": str(tmp / "att")})
s.add_attachment(con, van["AssetID"], "invoice.pdf", b"%PDF-1.4 test", {"title": "Invoice"})


def snapshot(c) -> dict:
    out = {t: c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in db.TABLES}
    out["nbv"] = round(sum(a["NBV"] for a in s.list_assets(c)), 2)
    out["journal"] = tuple(round(x or 0, 2) for x in c.execute("SELECT SUM(DebitAmount), SUM(CreditAmount) FROM tbl_DepreciationJournal").fetchone())
    out["names"] = sorted(r[0] for r in c.execute("SELECT AssetNameAr FROM tbl_Assets WHERE AssetNameAr IS NOT NULL"))
    return out


before = snapshot(con)
b = s.create_backup(con)
zpath = tmp / "backups" / b["name"]
names = zipfile.ZipFile(zpath).namelist()
assert ("usool-data.json" if db.is_pg() else "gooya_asset.db") in names and any(n.startswith("attachments/") for n in names), names

# ---- wipe the books, restore, and compare
for t in reversed(db.TABLES):
    con.execute(f"DELETE FROM {t}")
con.commit()
assert con.execute("SELECT COUNT(*) FROM tbl_Assets").fetchone()[0] == 0
con.close()
restore_backup.main(str(zpath))
con = db.connect()
after = snapshot(con)
assert after == before, {k: (before[k], after[k]) for k in before if before[k] != after[k]}
assert not [c["id"] for c in s.run_checks(con) if not c["ok"]]
new = s.save_asset(con, {"AssetName": "After restore", "CategoryID": cat["IT"], "AcquisitionDate": "2026-05-01", "PurchaseAmount": 100, "VatApplicable": 0})
assert new["AssetID"] > van["AssetID"], "new keys continue after the restored ones"

# ---- the portable copy: this database into a fresh SQLite file, identical
data = {}
for t in db.TABLES:
    cols, batches = db.dump_rows(con, t)
    data[t] = (cols, [r for bt in batches for r in bt])
here = snapshot(con)
con.close()
url, path = db.URL, db.DB_PATH
db.URL, db.DB_PATH = None, Path(tempfile.mkdtemp()) / "copy.db"
db.init_db()
c2 = db.connect()
db.load_tables(c2, data)
assert snapshot(c2) == here, "the copy in SQLite holds the same books"
c2.close()
db.URL, db.DB_PATH = url, path
print(f"All storage tests passed ({'PostgreSQL' if db.is_pg() else 'SQLite'})")
