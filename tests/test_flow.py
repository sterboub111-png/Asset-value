"""End-to-end business-rule tests against a throw-away copy of the database.
Run:  python -m tests.test_flow"""
import shutil
import tempfile
from pathlib import Path

from app import db, reports, services as s

tmp = Path(tempfile.mkdtemp()) / "t.db"
shutil.copy(db.DB_PATH, tmp)
db.DB_PATH = tmp
con = db.connect()


def expect_error(fn, *a, contains=""):
    try:
        fn(*a)
    except s.ApiError as e:
        assert contains in str(e), f"wrong error: {e}"
        return
    raise AssertionError(f"expected ApiError containing {contains!r}")


s.generate_periods(con, 2027)
periods = {p["PeriodName"]: p["PeriodID"] for p in s.rows(con, "SELECT * FROM tbl_DepreciationPeriods")}
con.execute("INSERT INTO tbl_Locations(LocationCode,LocationName) VALUES('MAIN','Main')")
kit = s.one(con, "SELECT * FROM tbl_AssetCategories WHERE CategoryCode='KIT'")["CategoryID"]
s.save_asset(con, {"AssetName": "Refrigerator", "CategoryID": kit, "AcquisitionDate": "2026-01-01", "AcquisitionCost": 12000})
for n in range(1, 11):  # Jan-Oct 2026 already posted
    pid = s.one(con, "SELECT PeriodID FROM tbl_DepreciationPeriods WHERE FiscalYear=2026 AND PeriodNumber=?", (n,))["PeriodID"]
    s.run_depreciation(con, pid); s.post_depreciation(con, pid)

# new asset: IT group, cost 4800, 4 years => 100/month, starts Nov 2026 (period before is posted already)
cat = s.one(con, "SELECT * FROM tbl_AssetCategories WHERE CategoryCode='IT'")
loc = s.one(con, "SELECT * FROM tbl_Locations")["LocationID"]
a = s.save_asset(con, {"AssetName": "Laptop", "CategoryID": cat["CategoryID"], "AcquisitionDate": "2026-11-05",
                       "AcquisitionCost": 4800, "ResidualValue": 0, "LocationID": loc})
assert a["AssetCode"] == "IT-0001" and a["UsefulLifeYears"] == 4 and a["DepreciationRate"] == 25
assert a["NBV"] == 4800

# sequence: December before November must be refused / ineligible
dec = s.propose(con, periods["December 2026"])
line = next(x for x in dec if x["AssetCode"] == "IT-0001")
assert not line["eligible"] and "must be posted first" in line["reason"], line
# KIT-0001 has Nov not posted either (Oct is last posted)
nov = periods["November 2026"]
assert s.run_depreciation(con, nov)["created"] == 2
assert s.post_depreciation(con, nov) == {"posted": 2, "total": 300.0}
expect_error(s.post_depreciation, con, nov, contains="no unposted")
assert s.get_asset(con, a["AssetID"])["AccumDep"] == 100 and s.get_asset(con, a["AssetID"])["NBV"] == 4700
# posted values are locked
expect_error(s.save_asset, con, {**a, "AcquisitionCost": 5000}, a["AssetID"], contains="cannot be changed")
s.save_asset(con, {**a, "AssetName": "Laptop Dell"}, a["AssetID"])  # harmless edit allowed

# closing a period blocks posting
s.set_period_status(con, nov, "CLOSED")
expect_error(s.run_depreciation, con, nov, contains="closed")
s.set_period_status(con, nov, "OPEN")

# depreciation proceeds: December
dec_id = periods["December 2026"]
s.run_depreciation(con, dec_id); s.post_depreciation(con, dec_id)
assert s.get_asset(con, a["AssetID"])["AccumDep"] == 200

# transfer
loc2 = con.execute("INSERT INTO tbl_Locations(LocationCode,LocationName) VALUES('HQ','Head office')").lastrowid
t = s.transfer_asset(con, a["AssetID"], {"TransactionDate": "2026-12-10", "ToLocationID": loc2})
assert t["LocationID"] == loc2

# disposal in Jan 2027 needs December posted (yes) -> proceeds 4000 vs NBV 4600 => loss 600
d = s.dispose_asset(con, a["AssetID"], {"TransactionDate": "2027-01-15", "DisposalProceeds": 4000, "DisposalReason": "Sold"})
assert d["AssetStatus"] == "Disposed"
j = s.s if False else s.rows(con, "SELECT * FROM tbl_DepreciationJournal WHERE JournalType='DISPOSAL'")
assert round(sum(x["DebitAmount"] for x in j), 2) == round(sum(x["CreditAmount"] for x in j), 2) == 4800.0, j
assert any(x["DebitAmount"] == 600 for x in j)  # loss line
expect_error(s.dispose_asset, con, a["AssetID"], {"TransactionDate": "2027-02-01"}, contains="already disposed")
expect_error(s.save_asset, con, {**a}, a["AssetID"], contains="disposed")

# journal balances overall
tot = con.execute("SELECT ROUND(SUM(DebitAmount),2), ROUND(SUM(CreditAmount),2) FROM tbl_DepreciationJournal").fetchone()
assert tot[0] == tot[1], tuple(tot)

# roll-forward over 2027 must tie: the disposed laptop leaves opening balances untouched and KIT-0001 keeps depreciating
jan = periods["January 2027"]
s.run_depreciation(con, jan); s.post_depreciation(con, jan)
rf = reports.run_report(con, "rollforward", {"from": "2026-11-01", "to": "2027-01-31"})
for r in rf["rows"]:
    assert round(r["OpenCost"] + r["Additions"] - r["Disposals"], 2) == r["CloseCost"], r
    assert round(r["OpenDep"] + r["BroughtIn"] + r["Charge"] - r["DepDisposed"], 2) == r["CloseDep"], r
    assert round(r["CloseCost"] - r["CloseDep"], 2) == r["NBV"], r
reg = reports.run_report(con, "asset-register", {"as_of": "2027-01-31"})
assert [x["AssetCode"] for x in reg["rows"]] == ["KIT-0001"], reg["rows"]
dsp = reports.run_report(con, "disposals", {"to": "2027-12-31"})
assert dsp["rows"][0]["GainLoss"] == -600.0 and dsp["rows"][0]["NBV"] == 4600.0, dsp["rows"]
for rid in reports.BUILDERS:
    reports.run_report(con, rid, {"from": "2026-01-01", "to": "2027-12-31", "fiscal_year": "2026"})

# legacy asset with opening accumulated depreciation starting later
b = s.save_asset(con, {"AssetName": "Old truck", "CategoryID": s.one(con, "SELECT * FROM tbl_AssetCategories WHERE CategoryCode='VEH'")["CategoryID"],
                       "AcquisitionDate": "2020-01-01", "InServiceDate": "2020-01-01", "DepreciationStartDate": "2027-02-01",
                       "AcquisitionCost": 60000, "OpeningAccumDep": 59900})
feb = periods["February 2027"]
s.run_depreciation(con, feb)
row = s.one(con, "SELECT * FROM tbl_Depreciation WHERE AssetID=? AND PeriodID=?", (b["AssetID"], feb))
assert row["PeriodDepreciation"] == 100 and row["ClosingNBV"] == 0, row   # capped at what is left

# ---- maintenance
fa1 = s.one(con, "SELECT AssetID FROM tbl_Assets WHERE AssetCode='KIT-0001'", raw=True)["AssetID"]
m = s.save_maintenance(con, {"AssetID": fa1, "MaintenanceType": "Corrective", "Title": "Compressor", "ScheduledDate": "2027-03-01", "OutOfService": True})
assert m["MaintenanceNo"] == "MT-0001" and m["Status"] == "Planned"
expect_error(s.dispose_asset, con, fa1, {"TransactionDate": "2027-03-05"}, contains="maintenance")
s.maintenance_action(con, m["MaintenanceID"], "start", {"StartDate": "2027-03-02"})
assert s.get_asset(con, fa1)["AssetStatus"] == "Under Repair"
expect_error(s.maintenance_action, con, m["MaintenanceID"], "start", {}, contains="planned")
expect_error(s.maintenance_action, con, m["MaintenanceID"], "complete", {"CompletionDate": "2027-03-01"}, contains="before the start")
s.maintenance_action(con, m["MaintenanceID"], "complete", {"CompletionDate": "2027-03-04", "Cost": 350, "NextDueDate": "2027-09-04"})
assert s.get_asset(con, fa1)["AssetStatus"] == "Active"
expect_error(s.save_maintenance, con, {"AssetID": fa1, "MaintenanceType": "Corrective", "Title": "x", "ScheduledDate": "2027-03-01"}, m["MaintenanceID"], contains="cannot be edited")
m2 = s.save_maintenance(con, {"AssetID": fa1, "MaintenanceType": "Preventive", "Title": "Service", "ScheduledDate": "2027-09-01"})
s.maintenance_action(con, m2["MaintenanceID"], "cancel", {})
s.delete_maintenance(con, m2["MaintenanceID"])
expect_error(s.delete_maintenance, con, m["MaintenanceID"], contains="planned or cancelled")
expect_error(s.delete_asset, con, fa1, contains="maintenance")
hist = reports.run_report(con, "maintenance-history", {"from": "2027-01-01", "to": "2027-12-31"})
assert hist["rows"][0]["Cost"] == 350
cost = reports.run_report(con, "maintenance-cost", {"mgroup": "category"})
assert cost["rows"][0]["Cost"] == 350 and cost["rows"][0]["Orders"] == 1
sch = reports.run_report(con, "maintenance-schedule", {"days": "3000"})
assert sch["rows"] and sch["rows"][0]["Source"] == "Recurring due date", sch["rows"]

# ---- suppliers
sup = s.save_supplier(con, {"SupplierName": "Acme Trading", "SupplierNameAr": "شركة أكمي", "Phone": "+966 11 555 0100", "Email": "info@acme.sa",
                            "TaxNumber": "300000000000003", "IBAN": "sa03 8000 0000 6080 1016 7519", "City": "Riyadh"})
assert sup["SupplierCode"] == "SUP-0001" and sup["IBAN"] == "SA0380000000608010167519"
expect_error(s.save_supplier, con, {"SupplierName": "acme trading"}, contains="already exists")
expect_error(s.save_supplier, con, {"SupplierName": "Other", "TaxNumber": "300000000000003"}, contains="tax number")
expect_error(s.save_supplier, con, {"SupplierName": "Bad", "Email": "nope"}, contains="Email")
a3 = s.save_asset(con, {"AssetName": "Desk", "CategoryID": s.one(con, "SELECT CategoryID FROM tbl_AssetCategories WHERE CategoryCode='FUR'", raw=True)["CategoryID"],
                        "AcquisitionDate": "2027-02-01", "AcquisitionCost": 900, "SupplierID": sup["SupplierID"], "InvoiceNumber": "A-77"})
assert a3["SupplierName"] == "Acme Trading" and a3["AssetCode"] == "FUR-0001"
mo = s.save_maintenance(con, {"AssetID": a3["AssetID"], "MaintenanceType": "Corrective", "Title": "Fix", "ScheduledDate": "2027-03-01", "SupplierID": sup["SupplierID"]})
assert mo["Vendor"] == "Acme Trading"
s.maintenance_action(con, mo["MaintenanceID"], "complete", {"CompletionDate": "2027-03-02", "Cost": 120})
s.set_lang("ar"); assert s.list_assets(con, "Desk")[0]["SupplierName"] == "شركة أكمي"; s.set_lang("en")
sm = reports.run_report(con, "supplier-summary", {})
assert sm["rows"][0]["Purchases"] == 900 and sm["rows"][0]["MaintCost"] == 120 and sm["rows"][0]["Total"] == 1020, sm["rows"]
sp = reports.run_report(con, "supplier-purchases", {"supplier": str(sup["SupplierID"])})
assert sp["rows"][0]["AcquisitionCost"] == 900
assert len(reports.run_report(con, "suppliers-directory", {"sactive": "1"})["rows"]) == 1
expect_error(s.delete_supplier, con, sup["SupplierID"], contains="linked")
s.save_supplier(con, {**sup, "SupplierName": "Acme Co", "IsActive": False}, sup["SupplierID"])
assert s.get_asset(con, a3["AssetID"])["SupplierName"] == "Acme Co"
print("All flow tests passed")
