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
# The imported Access data already has an asset and posted months; these tests build their own from a clean ledger.
for t in ("tbl_DepreciationJournal", "tbl_Depreciation", "tbl_AssetTransactions", "tbl_Assets"):
    con.execute(f"DELETE FROM {t}")
con.execute("UPDATE tbl_DepreciationPeriods SET PeriodStatus='OPEN'")
con.commit()


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
expect_error(s.save_asset, con, {**a, "PurchaseAmount": 5000}, a["AssetID"], contains="cannot be changed")
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

# ---- VAT: books always carry the net cost
v1 = s.save_asset(con, {"AssetName": "VAT inc", "CategoryID": cat["CategoryID"], "AcquisitionDate": "2027-04-01", "PurchaseAmount": 1150, "VatApplicable": True, "VatInclusive": True, "VatRate": 15})
assert (v1["AcquisitionCost"], v1["VatAmount"], v1["PurchaseAmount"]) == (1000.0, 150.0, 1150.0), v1
v2 = s.save_asset(con, {"AssetName": "VAT exc", "CategoryID": cat["CategoryID"], "AcquisitionDate": "2027-04-01", "PurchaseAmount": 1000, "VatApplicable": True, "VatInclusive": False, "VatRate": 15})
assert (v2["AcquisitionCost"], v2["VatAmount"]) == (1000.0, 150.0)
v3 = s.save_asset(con, {"AssetName": "No VAT", "CategoryID": cat["CategoryID"], "AcquisitionDate": "2027-04-01", "PurchaseAmount": 1000, "VatApplicable": False})
assert (v3["AcquisitionCost"], v3["VatAmount"], v3["VatApplicable"]) == (1000.0, 0.0, 0)
vr = reports.run_report(con, "vat-purchases", {"from": "2027-04-01", "to": "2027-04-30"})
assert [r["VatAmount"] for r in vr["rows"]] == [150.0, 150.0, 0.0] and vr["rows"][0]["Gross"] == 1150.0
reg2 = reports.run_report(con, "asset-register", {"as_of": "2027-04-30"})
assert {r["AssetName"]: r["Cost"] for r in reg2["rows"] if r["AssetName"].startswith(("VAT", "No"))} == {"VAT inc": 1000.0, "VAT exc": 1000.0, "No VAT": 1000.0}
s.save_settings(con, {"VATEnabled": "0"})
v4 = s.save_asset(con, {"AssetName": "VAT off", "CategoryID": cat["CategoryID"], "AcquisitionDate": "2027-04-01", "PurchaseAmount": 500, "VatApplicable": True})
assert v4["VatApplicable"] == 0 and v4["AcquisitionCost"] == 500
s.save_settings(con, {"VATEnabled": "1"})
expect_error(s.save_settings, con, {"VATRate": "120"}, contains="VAT rate")

# ---- currency
expect_error(s.save_settings, con, {"DefaultCurrency": "XXX"}, contains="currency")
s.save_settings(con, {"DefaultCurrency": "USD"}); s.save_settings(con, {"DefaultCurrency": "SAR"})
usd = s.one(con, "SELECT CurrencyID FROM tbl_Currencies WHERE CurrencyCode='SAR'", raw=True)["CurrencyID"]
expect_error(s.master_delete, con, "currencies", usd, contains="default currency")
expect_error(s.master_save, con, "currencies", {"CurrencyCode": "AB", "CurrencyName": "x"}, contains="3 letters")

# ---- backup schedule
from datetime import datetime as _dt
s.save_settings(con, {"BackupSchedule": "WEEKLY", "BackupWeekday": "2", "BackupTime": "03:30", "BackupKeep": "2"})
ref = _dt(2027, 6, 10, 12, 0)  # a Thursday
sc = s.backup_schedule(con, ref)
assert sc["due_slot"].startswith("2027-06-09 03:30") and sc["next_run"].startswith("2027-06-16 03:30"), sc
s.save_settings(con, {"BackupSchedule": "QUARTERLY", "BackupDayOfMonth": "5"})
sc = s.backup_schedule(con, ref); assert sc["due_slot"].startswith("2027-04-05") and sc["next_run"].startswith("2027-07-05"), sc
s.save_settings(con, {"BackupSchedule": "MONTHLY", "BackupDayOfMonth": "28"}); sc = s.backup_schedule(con, _dt(2027, 2, 27, 1, 0))
assert sc["due_slot"].startswith("2027-01-28") and sc["next_run"].startswith("2027-02-28"), sc
s.save_settings(con, {"BackupSchedule": "DAILY", "BackupTime": "02:00"})
import tempfile as _tf
s.db.ROOT = Path(_tf.mkdtemp())
expect_error(s.create_backup, con, contains="backup folder")
s.save_settings(con, {"BackupFolder": str(Path(_tf.mkdtemp()))})
r1 = s.run_due_backup(con, _dt.now().replace(hour=23, minute=59)); assert r1 and r1["name"].startswith("Usool_auto_")
assert s.run_due_backup(con, _dt.now().replace(hour=23, minute=59)) is None  # already taken for this slot
assert s.list_backups(con)["items"][0]["kind"] == "auto"
s.save_settings(con, {"BackupSchedule": "OFF"}); assert s.run_due_backup(con) is None

# ---- supplier code is editable
assert s.next_supplier_code(con) == "SUP-0002"
s2 = s.save_supplier(con, {"SupplierName": "Zed Co", "SupplierCode": "ZED-01"}); assert s2["SupplierCode"] == "ZED-01"
expect_error(s.save_supplier, con, {"SupplierName": "Other Co", "SupplierCode": "zed-01"}, contains="already exists")
s2 = s.save_supplier(con, {**s2, "SupplierCode": "SUP-0002"}, s2["SupplierID"]); assert s2["SupplierCode"] == "SUP-0002"
expect_error(s.save_supplier, con, {**s2, "SupplierCode": "SUP-0001"}, s2["SupplierID"], contains="already exists")

# ---- employees and custody (handover): never touches cost, depreciation or asset reports
emp = s.save_employee(con, {"EmployeeName": "Sara Test", "EmployeeNameAr": "سارة", "JobTitle": "Accountant", "Department": "Finance", "Mobile": "0500000001", "NationalID": "1000000001"})
assert emp["EmployeeCode"] == "EMP-0001" and s.next_employee_code(con) == "EMP-0002"
expect_error(s.save_employee, con, {"EmployeeName": "Dup", "NationalID": "1000000001"}, contains="ID number")
before = reports.run_report(con, "asset-register", {"as_of": "2027-12-31"})["rows"]
acc_before = s.get_asset(con, a3["AssetID"])["AccumDep"]
cu = s.issue_custody(con, {"AssetID": a3["AssetID"], "EmployeeID": emp["EmployeeID"], "IssueDate": "2027-02-10", "ConditionOnIssue": "New", "Accessories": "Key x2"})
assert cu["CustodyNo"] == "CU-0001" and cu["Status"] == "Issued"
assert s.list_assets(con, "Desk")[0]["CustodianName"] == "Sara Test"
assert reports.run_report(con, "asset-register", {"as_of": "2027-12-31"})["rows"] == before      # asset report unchanged
assert s.get_asset(con, a3["AssetID"])["AccumDep"] == acc_before and s.get_asset(con, a3["AssetID"])["AssetStatus"] == "Active"
expect_error(s.issue_custody, con, {"AssetID": a3["AssetID"], "EmployeeID": emp["EmployeeID"], "IssueDate": "2027-02-11"}, contains="already with")
expect_error(s.issue_custody, con, {"AssetID": fa1, "EmployeeID": emp["EmployeeID"], "IssueDate": "2020-01-01"}, contains="acquisition")
expect_error(s.dispose_asset, con, a3["AssetID"], {"TransactionDate": "2027-06-01"}, contains="custody")
expect_error(s.delete_employee, con, emp["EmployeeID"], contains="custody records")
expect_error(s.save_employee, con, {**emp, "IsActive": False}, emp["EmployeeID"], contains="still holds")
import tempfile as _tf2
s.save_settings(con, {"AttachmentFolder": str(Path(_tf2.mkdtemp()))})
cu = s.add_custody_attachment(con, cu["CustodyID"], "signed.pdf", b"%PDF-signed", {"title": "Signed handover"})
att = cu["attachments"][0]
assert att["CustodyID"] == cu["CustodyID"] and att["FileName"].startswith("FUR-0001_CU-0001_2027-02-10") and att["FileName"].endswith(".pdf"), att
expect_error(s.delete_custody, con, cu["CustodyID"], contains="without signed")
expect_error(s.return_custody, con, cu["CustodyID"], {"ReturnDate": "2027-01-01"}, contains="before the issue")
cu = s.return_custody(con, cu["CustodyID"], {"ReturnDate": "2027-03-01", "ConditionOnReturn": "Good"})
assert cu["Status"] == "Returned" and s.list_assets(con, "Desk")[0]["CustodianName"] is None
cu2 = s.issue_custody(con, {"AssetID": a3["AssetID"], "EmployeeID": emp["EmployeeID"], "IssueDate": "2027-03-05"})
assert cu2["CustodyNo"] == "CU-0002"
rp = reports.run_report(con, "custody-by-employee", {})
assert [r["CustodyNo"] for r in rp["rows"]] == ["CU-0001", "CU-0002"], rp["rows"]
assert len(reports.run_report(con, "custody-by-employee", {"cstatus": "Issued"})["rows"]) == 1
assert reports.run_report(con, "employees-directory", {})["rows"][0]["Held"] == 1
s.delete_custody(con, cu2["CustodyID"])
expect_error(s.delete_asset, con, a3["AssetID"], contains="maintenance")
print("All flow tests passed")
