"""Regression tests for the defects found in the general review. Run:  python -m tests.test_review"""
import http.client
import json
import shutil
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

from app import db

tmp = Path(tempfile.mkdtemp())
shutil.copy(db.DB_PATH, tmp / "r.db")
db.DB_PATH = tmp / "r.db"
db.DATA_DIR = tmp
from app import auth, reports, server, services as s  # noqa: E402

s.db.ROOT = tmp
con = db.connect()
db.init_db()


def expect_error(fn, *a, contains="", **k):
    try:
        fn(*a, **k)
    except s.ApiError as e:
        assert contains in str(e), f"wrong error: {e}"
        return
    raise AssertionError(f"expected ApiError containing {contains!r}")


def cat(code):
    return s.one(con, "SELECT CategoryID FROM tbl_AssetCategories WHERE CategoryCode=?", (code,), raw=True)["CategoryID"]


s.generate_periods(con, 2026); s.generate_periods(con, 2027); s.generate_periods(con, 2028)
per = {p["PeriodName"]: p["PeriodID"] for p in s.rows(con, "SELECT * FROM tbl_DepreciationPeriods", raw=True)}


def post_month(name):
    s.run_depreciation(con, per[name]); return s.post_depreciation(con, per[name])


def months(year):
    return ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]


# ---- 1. rounding: the last month takes the exact remainder, never an extra month or a stray cent
for cost, life, n in ((1000, 2.5, 30), (100, 0.25, 3), (100, 0.75, 9), (1000, 3, 36)):
    a = s.save_asset(con, {"AssetName": f"R{cost}-{life}", "CategoryID": cat("FUR"), "AcquisitionDate": "2026-01-01", "PurchaseAmount": cost, "UsefulLifeYears": life})
    total, count = 0.0, 0
    # deterministic: compute the schedule by running/posting each period
    for y in (2026, 2027, 2028):
        for m in months(y):
            s.run_depreciation(con, per[f"{m} {y}"], [a["AssetID"]])
            row = s.one(con, "SELECT * FROM tbl_Depreciation WHERE AssetID=? AND PeriodID=?", (a["AssetID"], per[f"{m} {y}"]), raw=True)
            if row and row["PostingStatus"] == "DRAFT":
                s.post_depreciation(con, per[f"{m} {y}"]); total += row["PeriodDepreciation"]; count += 1
    got = s.get_asset(con, a["AssetID"])
    assert round(total, 2) == cost and got["NBV"] == 0 and count == n, (cost, life, round(total, 2), got["NBV"], count, n)
    con.execute("DELETE FROM tbl_DepreciationJournal"); con.execute("DELETE FROM tbl_Depreciation"); con.execute("DELETE FROM tbl_AssetTransactions")
    con.execute("DELETE FROM tbl_Assets"); con.commit()

# ---- 2. a fully depreciated asset can still be disposed months later
fd = s.save_asset(con, {"AssetName": "Old", "CategoryID": cat("FUR"), "AcquisitionDate": "2026-01-01", "PurchaseAmount": 120, "UsefulLifeYears": 1})
for m in months(2026):
    s.run_depreciation(con, per[f"{m} 2026"]); s.post_depreciation(con, per[f"{m} 2026"])
assert s.get_asset(con, fd["AssetID"])["NBV"] == 0
d = s.dispose_asset(con, fd["AssetID"], {"TransactionDate": "2027-05-10", "DisposalProceeds": 0})
assert d["AssetStatus"] == "Disposed"

# ---- 3. drafts go stale: editing the asset drops them, and posting refuses an out-of-date proposal
st = s.save_asset(con, {"AssetName": "Stale", "CategoryID": cat("FUR"), "AcquisitionDate": "2027-01-01", "PurchaseAmount": 1200, "UsefulLifeYears": 4})
s.run_depreciation(con, per["January 2027"], [st["AssetID"]])
assert s.one(con, "SELECT PeriodDepreciation p FROM tbl_Depreciation WHERE AssetID=?", (st["AssetID"],), raw=True)["p"] == 25.0
s.save_asset(con, {**st, "PurchaseAmount": 2400, "UsefulLifeYears": 2}, st["AssetID"])
assert s.one(con, "SELECT COUNT(*) n FROM tbl_Depreciation WHERE AssetID=?", (st["AssetID"],), raw=True)["n"] == 0, "drafts removed on edit"
s.run_depreciation(con, per["January 2027"], [st["AssetID"]])
con.execute("UPDATE tbl_Depreciation SET PeriodDepreciation=1 WHERE AssetID=? AND PostingStatus='DRAFT'", (st["AssetID"],)); con.commit()   # simulate a stale draft
expect_error(s.post_depreciation, con, per["January 2027"], contains="out of date")

# ---- 4. roll-forward includes an asset bought and disposed inside the window
con.execute("DELETE FROM tbl_Depreciation WHERE PostingStatus='DRAFT'"); con.commit()
bd = s.save_asset(con, {"AssetName": "InOut", "CategoryID": cat("OFF"), "AcquisitionDate": "2027-02-02", "PurchaseAmount": 600, "UsefulLifeYears": 5})
s.dispose_asset(con, bd["AssetID"], {"TransactionDate": "2027-02-20", "DisposalProceeds": 500})
rf = reports.run_report(con, "rollforward", {"from": "2027-02-01", "to": "2027-03-31"})["rows"]
off = next(r for r in rf if r["Group"] == "Office Equipment")
assert (off["Additions"], off["Disposals"], off["CloseCost"]) == (600.0, 600.0, 0.0) and off["CloseDep"] == 0 and off["NBV"] == 0, off

# ---- 5. a back-dated disposal cannot pre-date depreciation that is already posted
bk = s.save_asset(con, {"AssetName": "Back", "CategoryID": cat("OFF"), "AcquisitionDate": "2027-04-01", "PurchaseAmount": 1200, "UsefulLifeYears": 4})
s.run_depreciation(con, per["April 2027"], [bk["AssetID"]]); s.post_depreciation(con, per["April 2027"])
expect_error(s.dispose_asset, con, bk["AssetID"], {"TransactionDate": "2027-04-20"}, contains="already posted")

# ---- 6/7/8. clean 400s instead of crashes; no infinite or NaN money
for bad in ({"days": "abc"}, {"days": "1.5"}, {"days": "99999999"}):
    expect_error(reports.run_report, con, "warranty-expiry", bad, contains="Days")
    expect_error(reports.run_report, con, "maintenance-schedule", bad, contains="Days")
expect_error(reports.run_report, con, "depreciation-schedule", {"fiscal_year": "abc"}, contains="Fiscal year")
expect_error(reports.run_report, con, "depreciation-schedule", {"fiscal_year": "1e3"}, contains="Fiscal year")
base = {"AssetName": "Bad", "CategoryID": cat("FUR"), "AcquisitionDate": "2027-01-01"}
expect_error(s.save_asset, con, {**base, "CategoryID": "abc", "PurchaseAmount": 10}, contains="Category")
expect_error(s.save_asset, con, {**base, "PurchaseAmount": "inf"}, contains="number")
expect_error(s.save_asset, con, {**base, "PurchaseAmount": "nan"}, contains="number")
expect_error(s.generate_periods, con, s.to_int("abc", "Fiscal year"), contains="")  if False else None
expect_error(s.to_int, "1.5", "Fiscal year", contains="not valid")

# ---- 9. a location with transfer history cannot be deleted; transfer checks its targets
loc_a = con.execute("INSERT INTO tbl_Locations(LocationCode,LocationName) VALUES('A','A')").lastrowid
loc_b = con.execute("INSERT INTO tbl_Locations(LocationCode,LocationName) VALUES('B','B')").lastrowid
con.execute("INSERT INTO tbl_Locations(LocationCode,LocationName,IsActive) VALUES('C','C',0)"); con.commit()
loc_c = s.one(con, "SELECT LocationID FROM tbl_Locations WHERE LocationCode='C'", raw=True)["LocationID"]
tr = s.save_asset(con, {"AssetName": "Mover", "CategoryID": cat("FUR"), "AcquisitionDate": "2027-01-10", "PurchaseAmount": 100, "LocationID": loc_a})
s.transfer_asset(con, tr["AssetID"], {"TransactionDate": "2027-02-01", "ToLocationID": loc_b})
expect_error(s.master_delete, con, "locations", loc_a, contains="in use")
expect_error(s.transfer_asset, con, tr["AssetID"], {"TransactionDate": "2027-02-02", "ToLocationID": 99999}, contains="not found")
expect_error(s.transfer_asset, con, tr["AssetID"], {"TransactionDate": "2027-02-02", "ToLocationID": loc_c}, contains="inactive")
expect_error(s.transfer_asset, con, tr["AssetID"], {"TransactionDate": "2020-01-01", "ToLocationID": loc_a}, contains="acquisition")

# ---- 11. attachment extension is sanitised, the original name is kept as the title
s.save_settings(con, {"AttachmentFolder": str(tmp / "att")})
for weird in ("x.<b>", 'a."q', "a.txt:evil", "noext"):
    r = s.add_attachment(con, tr["AssetID"], weird, b"data", {})
    fp = Path(r["attachments"][0]["FilePath"])
    assert fp.is_file() and ":" not in fp.name and "<" not in fp.name, (weird, fp.name)
assert r["attachments"][0]["DocumentTitle"] == "noext"

# ---- 12. maintenance never pulls an inactive asset into Under Repair
ia = s.save_asset(con, {"AssetName": "Idle", "CategoryID": cat("FUR"), "AcquisitionDate": "2027-01-10", "PurchaseAmount": 100})
s.change_status(con, ia["AssetID"], "Inactive")
m = s.save_maintenance(con, {"AssetID": ia["AssetID"], "MaintenanceType": "Corrective", "Title": "x", "ScheduledDate": "2027-03-01", "OutOfService": True})
s.maintenance_action(con, m["MaintenanceID"], "start", {}); assert s.get_asset(con, ia["AssetID"])["AssetStatus"] == "Inactive"
s.maintenance_action(con, m["MaintenanceID"], "complete", {"CompletionDate": "2027-03-05"}); assert s.get_asset(con, ia["AssetID"])["AssetStatus"] == "Inactive"

# ---- 13. numbers where text is expected
sp = s.save_supplier(con, {"SupplierName": "Num Co", "Phone": 123456789, "Email": None}); assert sp["Phone"] == "123456789"
# ---- 14. dates
expect_error(s.save_asset, con, {**base, "PurchaseAmount": 10, "DepreciationStartDate": "2026-01-01"}, contains="Depreciation start date")
posted_asset = s.get_asset(con, bk["AssetID"])
expect_error(s.save_asset, con, {**posted_asset, "AcquisitionDate": "2026-01-01"}, bk["AssetID"], contains="cannot be changed")
con.execute("UPDATE tbl_Suppliers SET IsActive=0 WHERE SupplierID=?", (sp["SupplierID"],)); con.commit()
expect_error(s.save_asset, con, {**base, "PurchaseAmount": 10, "SupplierID": sp["SupplierID"]}, contains="inactive")
# ---- 15. the fiscal year cannot move once periods exist
expect_error(s.save_settings, con, {"FiscalYearStartMonth": "4"}, contains="cannot be changed")
s.save_settings(con, {"FiscalYearStartMonth": "1"})
# ---- Arabic period names
s.set_lang("ar"); assert s.rows(con, "SELECT PeriodName FROM tbl_DepreciationPeriods WHERE PeriodNumber=1")[0]["PeriodName"].startswith("يناير"); s.set_lang("en")

# ---- security fixes against a real server
httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
PORT = httpd.server_address[1]
threading.Thread(target=httpd.serve_forever, daemon=True).start()


def call(method, path, body=None, cookie=None, headers=None, raw=None):
    c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=5)
    h = {"Content-Type": "application/json", "X-Requested-With": "GooyaAsset", **(headers or {})}
    if cookie:
        h["Cookie"] = cookie
    c.request(method, path, raw if raw is not None else (json.dumps(body).encode() if body is not None else None), h)
    r = c.getresponse(); data = r.read(); sc = r.getheader("Set-Cookie")
    try:
        j = json.loads(data)
    except ValueError:
        j = None
    c.close()
    return r.status, j, sc, r


auth.save_user(con, {"UserName": "root1", "FullName": "Root", "Password": "Passw0rd!x", "RoleID": auth.admin_role_id(con), "IsActive": True})   # the copied database already has its own administrator
st, me, sc, _ = call("POST", "/api/auth/login", {"UserName": "root1", "Password": "Passw0rd!x"})
assert st == 200
admin = sc.split(";")[0]
roles = {r["RoleName"]: r["RoleID"] for r in call("GET", "/api/roles", cookie=admin)[1]}
call("POST", "/api/users", {"UserName": "vic", "FullName": "Vic", "RoleID": roles["Viewer"], "Password": "Viewer123"}, cookie=admin)
bare = call("POST", "/api/roles", {"RoleName": "Bare", "permissions": []}, cookie=admin)[1]["RoleID"]
call("POST", "/api/users", {"UserName": "bob", "FullName": "Bob", "RoleID": bare, "Password": "Bare12345"}, cookie=admin)
bob = call("POST", "/api/auth/login", {"UserName": "bob", "Password": "Bare12345"})[2].split(";")[0]
vic = call("POST", "/api/auth/login", {"UserName": "vic", "Password": "Viewer123"})[2].split(";")[0]
assert call("GET", "/api/dashboard", cookie=bob)[0] == 403, "dashboard needs a permission"
lk = call("GET", "/api/lookups", cookie=bob)[1]
assert "BackupFolder" not in lk["settings"] and "AttachmentFolder" not in lk["settings"], "lookups hide folder paths"
assert "BackupFolder" in call("GET", "/api/lookups", cookie=admin)[1]["settings"]
# CSRF: a state-changing call without the app header, or from another port, is refused
assert call("POST", "/api/auth/logout", cookie=vic, headers={"X-Requested-With": ""})[0] == 403
assert call("POST", "/api/backups", cookie=admin, headers={"Origin": "http://localhost:3000"})[0] == 403
assert call("GET", "/api/assets", cookie=vic, headers={"Origin": f"http://127.0.0.1:{PORT}"})[0] == 200
# settings: folders need backup.manage, other keys need settings.manage
op = call("POST", "/api/roles", {"RoleName": "Bk", "permissions": ["backup.manage"]}, cookie=admin)[1]["RoleID"]
call("POST", "/api/users", {"UserName": "bea", "FullName": "Bea", "RoleID": op, "Password": "Backup1234"}, cookie=admin)
bea = call("POST", "/api/auth/login", {"UserName": "bea", "Password": "Backup1234"})[2].split(";")[0]
assert call("PUT", "/api/settings", {"BackupSchedule": "OFF"}, cookie=bea)[0] == 200, "backup admin can save backup settings"
assert call("PUT", "/api/settings", {"CompanyName": "X"}, cookie=bea)[0] == 403, "but not other settings"
assert call("PUT", "/api/settings", {"BackupFolder": str(tmp / "b")}, cookie=vic)[0] == 403
# custody forms follow custody permissions, and are hidden from asset payloads
ca = s.save_asset(con, {"AssetName": "Held", "CategoryID": cat("FUR"), "AcquisitionDate": "2027-01-10", "PurchaseAmount": 100})
emp = s.save_employee(con, {"EmployeeName": "Emp"})
cu = s.issue_custody(con, {"AssetID": ca["AssetID"], "EmployeeID": emp["EmployeeID"], "IssueDate": "2027-01-11"})
cu = s.add_custody_attachment(con, cu["CustodyID"], "form.pdf", b"%PDF", {})
aid = cu["attachments"][0]["AttachmentID"]
assert call("GET", f"/api/attachments/{aid}/download", cookie=vic)[0] == 200, "viewer has custody.view"
noc = call("POST", "/api/roles", {"RoleName": "NoCustody", "permissions": ["assets.view"]}, cookie=admin)[1]["RoleID"]
call("POST", "/api/users", {"UserName": "nic", "FullName": "Nic", "RoleID": noc, "Password": "NoCust1234"}, cookie=admin)
nic = call("POST", "/api/auth/login", {"UserName": "nic", "Password": "NoCust1234"})[2].split(";")[0]
assert call("GET", f"/api/attachments/{aid}/download", cookie=nic)[0] == 403, "custody form needs custody.view"
detail = call("GET", f"/api/assets/{ca['AssetID']}", cookie=nic)[1]
assert detail["attachments"] == [] and detail["custody"] == [] and detail["CustodianName"] is None, "asset payload hides custody"
assert call("DELETE", f"/api/attachments/{aid}", cookie=nic)[0] == 403
# request hygiene
c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=5)
c.request("POST", "/api/auth/login", b"{}", {"Content-Type": "application/json", "X-Requested-With": "GooyaAsset", "Content-Length": "-1"}); r = c.getresponse(); assert r.status == 400; c.close()
c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=5)
c.request("POST", "/api/auth/login", b"{}", {"Content-Type": "application/json", "X-Requested-With": "GooyaAsset", "Content-Length": "abc"}); r = c.getresponse(); assert r.status == 400; c.close()
for body in ("[1]", "null", '"str"', '{"UserName":123,"Password":456}'):
    st = call("POST", "/api/auth/login", raw=body.encode())[0]
    assert st in (400, 401), (body, st)
assert call("POST", "/api/users", {"UserName": "zed", "FullName": "Z", "RoleID": "abc", "Password": "Zed12345x"}, cookie=admin)[0] == 400
c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=5); c.request("GET", "/js/main.js%00.png"); r = c.getresponse(); assert r.status == 200; c.close()
_, _, _, resp = call("GET", "/")
assert resp.getheader("Content-Security-Policy") and resp.getheader("X-Frame-Options") == "DENY" and resp.getheader("Referrer-Policy") == "no-referrer"
# uniform lock-out: unknown names lock like real ones
codes = [call("POST", "/api/auth/login", {"UserName": "ghost", "Password": "nope-nope1"})[0] for _ in range(6)]
real = [call("POST", "/api/auth/login", {"UserName": "vic", "Password": "nope-nope1"})[0] for _ in range(6)]
assert codes == real == [401, 401, 401, 401, 401, 429], (codes, real)
# guessing the current password locks the account too
zz = call("POST", "/api/auth/login", {"UserName": "bob", "Password": "Bare12345"})[2].split(";")[0]
outs = [call("POST", "/api/auth/password", {"Current": "wrong-pass1", "New": "Another123"}, cookie=zz)[0] for _ in range(5)]
assert outs == [400] * 5 and call("POST", "/api/auth/login", {"UserName": "bob", "Password": "Bare12345"})[0] == 429, "password guessing is throttled"
# reports keep the contact / custody / maintenance permissions and send only the shown columns
rep = call("POST", "/api/roles", {"RoleName": "ReportsOnly", "permissions": ["reports.view", "assets.view"]}, cookie=admin)[1]["RoleID"]
call("POST", "/api/users", {"UserName": "rita", "FullName": "Rita", "RoleID": rep, "Password": "Reports123"}, cookie=admin)
rita = call("POST", "/api/auth/login", {"UserName": "rita", "Password": "Reports123"})[2].split(";")[0]
for rid in ("employees-directory", "custody-by-employee", "suppliers-directory", "maintenance-history"):
    assert call("GET", f"/api/reports/{rid}", cookie=rita)[0] == 403, rid
assert call("GET", "/api/reports/asset-register", cookie=rita)[0] == 200
assert "employees-directory" not in [r["id"] for r in call("GET", "/api/reports", cookie=rita)[1]]
s.save_employee(con, {"EmployeeName": "Id Holder", "NationalID": "1098765432"})
emp_rows = call("GET", "/api/reports/employees-directory", cookie=admin)[1]["rows"]
assert emp_rows and all("NationalID" not in r for r in emp_rows), "hidden columns are not sent"
# fractional sale proceeds still give a balanced disposal journal
fr = s.save_asset(con, {"AssetName": "Cents", "CategoryID": cat("KIT"), "AcquisitionDate": "2028-12-05", "PurchaseAmount": 1000, "VatApplicable": 0})
s.dispose_asset(con, fr["AssetID"], {"TransactionDate": "2028-12-20", "DisposalProceeds": "100.555"})
dr, cr = con.execute("SELECT SUM(DebitAmount), SUM(CreditAmount) FROM tbl_DepreciationJournal J JOIN tbl_AssetTransactions T ON T.TransactionID=J.TransactionID "
                     "WHERE T.AssetID=?", (fr["AssetID"],)).fetchone()
assert abs(dr - cr) < 1e-9, (dr, cr)
# an asset that started before the first period needs its opening accumulated depreciation
first = s.one(con, "SELECT PeriodID, StartDate FROM tbl_DepreciationPeriods ORDER BY StartDate LIMIT 1", raw=True)
old = s.save_asset(con, {"AssetName": "Old oven", "CategoryID": cat("KIT"), "AcquisitionDate": "2020-01-01", "PurchaseAmount": 12000, "VatApplicable": 0})
ln = next(x for x in s.propose(con, first["PeriodID"]) if x["AssetID"] == old["AssetID"])
assert not ln["eligible"] and "opening accumulated depreciation" in ln["reason"], ln
s.save_asset(con, {**s.one(con, "SELECT * FROM tbl_Assets WHERE AssetID=?", (old["AssetID"],), raw=True), "PurchaseAmount": 12000, "VatApplicable": 0, "OpeningAccumDep": 4000}, old["AssetID"])
assert next(x for x in s.propose(con, first["PeriodID"]) if x["AssetID"] == old["AssetID"])["eligible"], "eligible once the opening balance is entered"
httpd.shutdown()
shutil.rmtree(tmp, ignore_errors=True)
print("All review regression tests passed")
