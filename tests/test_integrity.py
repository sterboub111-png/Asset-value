"""The integrity checks: a full year of activity must satisfy every relation, and each kind of corruption must be caught.
Run:  python -m tests.test_integrity"""
from tests.fixture import fresh_db

fresh_db("i.db")
from app import db, services as s  # noqa: E402  (after the database path is set)

con = db.connect()
s.set_actor("tester")
cat = {r["CategoryCode"]: r["CategoryID"] for r in s.rows(con, "SELECT * FROM tbl_AssetCategories", raw=True)}
s.generate_periods(con, 2026)
per = {p["PeriodNumber"]: p["PeriodID"] for p in s.rows(con, "SELECT * FROM tbl_DepreciationPeriods WHERE FiscalYear=2026", raw=True)}

# ---- a year of activity: every VAT basis, an asset brought in with depreciation, sales at a gain and at a loss
kit = s.save_asset(con, {"AssetName": "Oven", "CategoryID": cat["KIT"], "AcquisitionDate": "2026-01-10", "PurchaseAmount": 12000, "VatApplicable": 1, "VatInclusive": 0, "VatRate": 15})
fur = s.save_asset(con, {"AssetName": "Tables", "CategoryID": cat["FUR"], "AcquisitionDate": "2026-02-01", "PurchaseAmount": 11500, "VatApplicable": 1, "VatInclusive": 1, "VatRate": 15})
it = s.save_asset(con, {"AssetName": "Server", "CategoryID": cat["IT"], "AcquisitionDate": "2025-06-01", "PurchaseAmount": 6000, "VatApplicable": 0, "OpeningAccumDep": 875})
veh = s.save_asset(con, {"AssetName": "Van", "CategoryID": cat["VEH"], "AcquisitionDate": "2026-01-05", "PurchaseAmount": 100000, "VatApplicable": 0})
assert fur["AcquisitionCost"] == 10000 and fur["VatAmount"] == 1500, fur   # 11,500 inclusive of 15% = 10,000 + 1,500
assert kit["AcquisitionCost"] == 12000 and kit["VatAmount"] == 1800, kit
for n in range(1, 7):
    s.run_depreciation(con, per[n]); s.post_depreciation(con, per[n])
s.dispose_asset(con, kit["AssetID"], {"TransactionDate": "2026-07-15", "DisposalProceeds": 15000})   # gain
s.dispose_asset(con, fur["AssetID"], {"TransactionDate": "2026-07-20", "DisposalProceeds": 1000})    # loss
m = s.save_maintenance(con, {"AssetID": veh["AssetID"], "Title": "Engine", "ScheduledDate": "2026-07-01", "OutOfService": True})
s.maintenance_action(con, m["MaintenanceID"], "start", {"StartDate": "2026-07-01"})
emp = s.save_employee(con, {"EmployeeName": "Holder"})
s.issue_custody(con, {"AssetID": it["AssetID"], "EmployeeID": emp["EmployeeID"], "IssueDate": "2026-07-01"})

# ---- the arithmetic of the scenario, checked by hand
oven = s.get_asset(con, kit["AssetID"])
assert oven["AccumDep"] == 1200.0, oven["AccumDep"]                    # 12,000 / 60 months = 200 a month, January-June posted
srv = s.get_asset(con, it["AssetID"])
assert srv["AccumDep"] == 875 + 6 * 125, srv["AccumDep"]               # 6,000 / 48 = 125 a month on top of the opening 875
gain = con.execute("""SELECT SUM(CreditAmount) FROM tbl_DepreciationJournal J JOIN tbl_AssetTransactions T ON T.TransactionID=J.TransactionID
    WHERE T.AssetID=? AND J.GLAccountID=(SELECT GainAccountID FROM tbl_AssetCategories WHERE CategoryID=?)""", (kit["AssetID"], cat["KIT"])).fetchone()[0]
assert abs(gain - (15000 - (12000 - 1200))) < 0.005, gain              # proceeds - NBV = 15,000 - 10,800

results = {c["id"]: c for c in s.run_checks(con)}
bad = {k: c["issues"] for k, c in results.items() if not c["ok"]}
assert not bad, bad

# ---- every kind of corruption is caught by its check (each change is rolled back afterwards)
def caught(check: str, *sql: tuple[str, tuple]) -> None:
    for q, args in sql:
        con.execute(q, args)
    got = {c["id"]: c for c in s.run_checks(con)}
    con.rollback()
    assert not got[check]["ok"], f"{check} missed the corruption"

posted = con.execute("SELECT DepreciationID, AssetID FROM tbl_Depreciation WHERE AssetID=? AND PostingStatus='POSTED' ORDER BY DepreciationID LIMIT 1", (veh["AssetID"],)).fetchone()
caught("depreciation-lines", ("UPDATE tbl_Depreciation SET ClosingAccumDep=ClosingAccumDep+10 WHERE DepreciationID=?", (posted[0],)))
caught("depreciation-lines", ("UPDATE tbl_Depreciation SET OpeningAccumDep=OpeningAccumDep+5, ClosingAccumDep=ClosingAccumDep+5, ClosingNBV=ClosingNBV-5 WHERE DepreciationID=?", (posted[0],)))
caught("depreciation-journal", ("DELETE FROM tbl_DepreciationJournal WHERE JournalID=(SELECT MIN(JournalID) FROM tbl_DepreciationJournal WHERE DepreciationID=?)", (posted[0],)))
caught("journal-balanced", ("UPDATE tbl_DepreciationJournal SET DebitAmount=DebitAmount+1 WHERE JournalID=(SELECT MIN(JournalID) FROM tbl_DepreciationJournal WHERE DebitAmount>0)", ()))
caught("residual-floor", ("UPDATE tbl_Assets SET ResidualValue=AcquisitionCost WHERE AssetID=?", (veh["AssetID"],)))
caught("disposals", ("UPDATE tbl_Assets SET AcquisitionCost=AcquisitionCost+100 WHERE AssetID=?", (kit["AssetID"],)))
caught("disposals", ("UPDATE tbl_AssetTransactions SET DisposalProceeds=DisposalProceeds+50 WHERE AssetID=? AND TransactionType='DISPOSAL'", (fur["AssetID"],)))
caught("vat", ("UPDATE tbl_Assets SET VatAmount=VatAmount+1 WHERE AssetID=?", (fur["AssetID"],)))
caught("periods", ("UPDATE tbl_DepreciationPeriods SET EndDate='2026-03-15' WHERE PeriodID=?", (per[3],)))
caught("statuses", ("UPDATE tbl_Assets SET AssetStatus='Under Repair' WHERE AssetID=?", (it["AssetID"],)))
# (reports-tie guards the report arithmetic itself; it is covered by the clean run above)

# the API returns the same results to a user who may run reports
assert s.run_checks(con) and all(c["ok"] for c in s.run_checks(con))
print("All integrity tests passed")
