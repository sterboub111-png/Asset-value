"""Import from Excel / CSV: the template, every way a value can be written, row checks, all-or-nothing, and hostile files.
Run:  python -m tests.test_import"""
import io
import zipfile

from tests.fixture import fresh_db

fresh_db("imp.db")
from app import db, services as s  # noqa: E402  (after the database path is set)
from app.services import importer  # noqa: E402

con = db.connect()
s.set_actor("tester")
s.generate_periods(con, 2026)
con.execute("INSERT INTO tbl_Locations(LocationCode,LocationName,LocationNameAr) VALUES('RYD','Riyadh branch','فرع الرياض')"); con.commit()


def expect_error(fn, *a, contains=""):
    try:
        fn(*a)
    except s.ApiError as e:
        assert contains in str(e), f"wrong error: {e}"
        return
    raise AssertionError(f"expected ApiError containing {contains!r}")


# ---- the template reads back: headers in both languages, the hint row skipped, the example ready to import
for lang in ("en", "ar"):
    x = importer.template(con, lang)
    p = importer.preview(con, "t.xlsx", x)
    assert p["total"] == 1 and p["ready"] == 1, (lang, p)
    assert p["rows"][0]["AcquisitionCost"] == 1000 and p["rows"][0]["VatAmount"] == 150, p["rows"][0]   # 1,150 inclusive of 15%
    names = zipfile.ZipFile(io.BytesIO(x)).namelist()
    assert "xl/worksheets/sheet2.xml" in names, "the Lists sheet is there"

# ---- an Arabic workbook written by Excel: serial dates, Arabic digits, a numeric group code, names instead of codes
cat = s.one(con, "SELECT CategoryID, CategoryCode FROM tbl_AssetCategories WHERE CategoryCode='IT'", raw=True)
con.execute("UPDATE tbl_AssetCategories SET CategoryCode='12' WHERE CategoryID=?", (cat["CategoryID"],)); con.commit()
head = ["اسم الأصل *", "مجموعة الأصل *", "تاريخ الاقتناء *", "مبلغ الفاتورة *", "خاضع للضريبة", "المبلغ شامل الضريبة", "الموقع", "الرقم التسلسلي", "مجمع الإهلاك الافتتاحي"]
book = importer.write_xlsx([("Assets", [head,
    ["Laptop", 12.0, 46023.0, "٢٣٠٠", "نعم", "لا", "فرع الرياض", "SN-1", ""],                    # 2026-01-01 as an Excel date
    ["Old server", "Computers & IT Equipment", "01/06/2025", 6000, "no", "", "RYD", "SN-2", "875"],  # by name, opening balance given
    ["Twin", "12", "2026-02-01", 100, "no", "", "", "sn-1", ""],                                      # serial repeats row 2 (case-insensitive)
    ["Broken", "NOPE", "31/02/2026", "abc", "maybe", "", "Nowhere", "", ""],
    ["", "", "", "", "", "", "", "", ""]], [20] * 9)])
p = importer.preview(con, "ar.xlsx", book)
st = {r["row"]: r for r in p["rows"]}
assert p["total"] == 4 and p["ready"] == 3 and p["errors"] == 1, p
assert st[2]["AcquisitionDate"] == "2026-01-01" and st[2]["PurchaseAmount"] == 2300 and st[2]["AcquisitionCost"] == 2300 and st[2]["VatAmount"] == 345, st[2]
assert st[3]["status"] == "ok", st[3]
assert st[4]["status"] == "warning" and st[4]["warnings"][0]["t"] == "Same serial number as row {0}", st[4]
bad = {e["t"] for e in st[5]["errors"]}
assert {"{0} '{1}' was not found", "{0} '{1}' is not valid"} <= bad and len(st[5]["errors"]) == 5, st[5]["errors"]   # group, location, date, amount, yes/no

# ---- a file with errors imports nothing unless the user asks for the ready rows only
before = con.execute("SELECT COUNT(*) FROM tbl_Assets").fetchone()[0]
expect_error(importer.run_import, con, "ar.xlsx", book, False, contains="row(s) have errors")
assert con.execute("SELECT COUNT(*) FROM tbl_Assets").fetchone()[0] == before
res = importer.run_import(con, "ar.xlsx", book, True)
assert len(res["created"]) == 3 and res["skipped"] == 1, res
codes = [c["AssetCode"] for c in res["created"]]
assert codes == ["12-0001", "12-0002", "12-0003"], codes
srv = s.get_asset(con, res["created"][1]["AssetID"])
assert srv["OpeningAccumDep"] == 875 and srv["LocationName"] == "Riyadh branch", srv
assert s.one(con, "SELECT 1 x FROM tbl_AuditLog WHERE Action='IMPORT'", raw=True), "the import is audited"
assert all(c["ok"] for c in s.run_checks(con)), [c for c in s.run_checks(con) if not c["ok"]]

# ---- an old asset without its opening balance is flagged before import
csv = "Asset name,Fixed asset group,Acquisition date,Invoice amount,Purchased with VAT\nOld van,VEH,45000,90000,no\n"
w = importer.preview(con, "a.csv", csv.encode())["rows"][0]
assert w["AcquisitionDate"] == "2023-03-15" and w["status"] == "warning" and "opening accumulated depreciation" in w["warnings"][0]["t"], w

# ---- files that are not what they claim, or too big, are refused cleanly
expect_error(importer.preview, con, "x.xlsx", b"PK\x03\x04not a zip", contains="not a readable Excel")
expect_error(importer.preview, con, "x.txt", b"hello", contains="Choose an Excel")
expect_error(importer.preview, con, "x.xlsx", b"", contains="empty")
expect_error(importer.preview, con, "x.csv", b"a,b\n1,2\n", contains="header row was not found")
expect_error(importer.preview, con, "x.csv", "Asset name,Fixed asset group\nDesk,FUR\n".encode(), contains="Columns missing")
evil = io.BytesIO()
with zipfile.ZipFile(evil, "w") as z:
    z.writestr("xl/workbook.xml", '<?xml version="1.0"?><!DOCTYPE lol [<!ENTITY a "aaaa">]><workbook/>')
expect_error(importer.preview, con, "evil.xlsx", evil.getvalue(), contains="not allowed")
print("All import tests passed")
