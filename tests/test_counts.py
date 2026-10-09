"""Physical inventory and the depreciation forecast.
Run:  python -m tests.test_counts"""
from tests.fixture import fresh_db

fresh_db("cnt.db")
from app import db, reports, services as s  # noqa: E402  (after the database path is set)

con = db.connect()
s.set_actor("tester")
s.generate_periods(con, 2026)
for code, name in (("RYD", "Riyadh"), ("JED", "Jeddah")):
    con.execute("INSERT INTO tbl_Locations(LocationCode,LocationName) VALUES(?,?)", (code, name))
con.commit()
loc = {r["LocationCode"]: r["LocationID"] for r in s.rows(con, "SELECT * FROM tbl_Locations", raw=True)}
cat = {r["CategoryCode"]: r["CategoryID"] for r in s.rows(con, "SELECT * FROM tbl_AssetCategories", raw=True)}


def expect_error(fn, *a, contains=""):
    try:
        fn(*a)
    except s.ApiError as e:
        assert contains in str(e), f"wrong error: {e}"
        return
    raise AssertionError(f"expected ApiError containing {contains!r}")


mk = lambda name, c, where, sn=None: s.save_asset(con, {"AssetName": name, "CategoryID": cat[c], "AcquisitionDate": "2026-01-10", "PurchaseAmount": 12000,
                                                       "VatApplicable": 0, "LocationID": loc[where], "SerialNumber": sn})
desk, oven, van, pc = mk("Desk", "FUR", "RYD"), mk("Oven", "KIT", "RYD", "OV-77"), mk("Van", "VEH", "RYD"), mk("PC", "IT", "JED")

# ---- a count of Riyadh expects the three Riyadh assets
c = s.create_count(con, {"Title": "Riyadh", "CountDate": "2026-10-01", "LocationID": loc["RYD"]})
cid = c["CountID"]
assert c["ExpectedCount"] == 3 and c["summary"]["missing"] == 3, c["summary"]
expect_error(s.create_count, con, {"Title": "again", "CountDate": "2026-10-01", "LocationID": loc["RYD"]}, contains="already open")

assert s.scan(con, cid, {"code": desk["AssetCode"].lower()})["status"] == "found"           # codes are not case sensitive
assert s.scan(con, cid, {"code": desk["AssetCode"]})["status"] == "already"
assert s.scan(con, cid, {"code": "ov-77"})["status"] == "found"                              # the serial number works too
r = s.scan(con, cid, {"code": pc["AssetCode"]})                                              # booked in Jeddah, standing in Riyadh
assert r["status"] == "extra", r["status"]
assert s.scan(con, cid, {"code": "NO-SUCH-CODE"})["status"] == "unknown"
g = s.get_count(con, cid)
assert g["summary"] == {"found": 2, "missing": 1, "extra": 1, "unknown": 1, "disposed": 0, "moved": 0}, g["summary"]
assert g["MissingNBV"] == 12000, g["MissingNBV"]                                             # the van, at cost (nothing posted)

# undo: an expected asset goes back to missing, an extra line disappears
desk_line = next(l for l in g["lines"] if l["AssetID"] == desk["AssetID"])
assert s.unscan(con, cid, desk_line["LineID"])["summary"]["missing"] == 2
s.scan(con, cid, {"code": desk["AssetCode"]})

# closing moves the PC found in Riyadh there, as a real transfer
res = s.close_count(con, cid, {"apply_locations": True})
assert res["Status"] == "Closed" and res["transferred"] == 1, res
moved = s.get_asset(con, pc["AssetID"])
assert moved["LocationID"] == loc["RYD"] and moved["transactions"][0]["TransactionType"] == "TRANSFER", moved["transactions"][0]
expect_error(s.scan, con, cid, {"code": van["AssetCode"]}, contains="closed")
expect_error(s.delete_count, con, cid, contains="closed")

# ---- the forecast is what the depreciation run will propose, month after month
jan = s.one(con, "SELECT PeriodID FROM tbl_DepreciationPeriods WHERE FiscalYear=2026 AND PeriodNumber=1", raw=True)["PeriodID"]
fc = reports.run_report(con, "depreciation-forecast", {"months": "3"})
per_month = {}
for row in fc["rows"]:
    per_month[row["MonthKey"]] = round(per_month.get(row["MonthKey"], 0) + row["Depreciation"], 2)
proposed = round(sum(l["PeriodDepreciation"] for l in s.propose(con, jan) if l["eligible"]), 2)
assert per_month["2026-01"] == proposed, (per_month, proposed)
s.run_depreciation(con, jan); s.post_depreciation(con, jan)
feb = s.one(con, "SELECT PeriodID FROM tbl_DepreciationPeriods WHERE FiscalYear=2026 AND PeriodNumber=2", raw=True)["PeriodID"]
fc2 = reports.run_report(con, "depreciation-forecast", {"months": "1"})
assert fc2["rows"][0]["MonthKey"] == "2026-02", "the forecast starts after the last posted month"
assert round(sum(r["Depreciation"] for r in fc2["rows"]), 2) == round(sum(l["PeriodDepreciation"] for l in s.propose(con, feb) if l["eligible"]), 2)
# over the whole life the forecast ends exactly at cost less residual (the last month takes the remainder)
whole = reports.run_report(con, "depreciation-forecast", {"months": "60"})
desk_rows = [r for r in whole["rows"] if r["AssetCode"] == desk["AssetCode"]]
assert desk_rows[-1]["ClosingNBV"] == 0 or len(desk_rows) == 59, desk_rows[-1]
expect_error(reports.run_report, con, "depreciation-forecast", {"months": "0"}, contains="between 1 and 60")
assert all(c["ok"] for c in s.run_checks(con)), [c for c in s.run_checks(con) if not c["ok"]]
print("All count and forecast tests passed")
