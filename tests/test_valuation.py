"""Declining balance, capital additions, revaluation and impairment, the fixed asset ledger, and branch scope.
Run:  python3 -m tests.test_valuation"""
from tests.fixture import fresh_db

fresh_db("val.db")
from app import db, reports, services as s  # noqa: E402  (after the database path is set)
from app.services import ledger  # noqa: E402

con = db.connect()
s.set_actor("tester")
s.generate_periods(con, 2026)
s.generate_periods(con, 2027)
per = {(p["FiscalYear"], p["PeriodNumber"]): p["PeriodID"] for p in s.rows(con, "SELECT * FROM tbl_DepreciationPeriods", raw=True)}
cat = {r["CategoryCode"]: r["CategoryID"] for r in s.rows(con, "SELECT * FROM tbl_AssetCategories", raw=True)}
method = {r["MethodCode"]: r["MethodID"] for r in s.rows(con, "SELECT * FROM tbl_DepreciationMethods", raw=True)}
st = s.get_settings(con)
assert st["ImpairmentAccountID"] and st["RevaluationSurplusAccountID"], "the valuation accounts are set up with the database"


def expect_error(fn, *a, contains=""):
    try:
        fn(*a)
    except s.ApiError as e:
        assert contains in str(e), f"wrong error: {e}"
        return
    raise AssertionError(f"expected ApiError containing {contains!r}")


def checks_pass():
    bad = [c for c in s.run_checks(con) if not c["ok"]]
    assert not bad, [(c["id"], c["issues"][:3]) for c in bad]


def line(asset, period):
    return next(l for l in s.propose(con, period) if l["AssetID"] == asset["AssetID"])


def post(fy, n):
    s.run_depreciation(con, per[(fy, n)]); s.post_depreciation(con, per[(fy, n)])


# ---- declining balance with a switch to straight line, as a pure rule: double declining over 5 years
charges, accum, fy_dep = [], 0.0, 0.0
for k in range(60):
    if k % 12 == 0:
        fy_dep = 0.0
    c = s.monthly_charge("DB", 5, 40, 12000, 0, accum, 0, k, fy_dep, False)
    charges.append(c); accum += c; fy_dep += c
years = [round(sum(charges[i:i + 12]), 2) for i in range(0, 60, 12)]
assert years[:3] == [4800, 2880, 1728], years             # 40% of 12,000, of 7,200, of 4,320
assert charges[36] == 108.0, charges[36]                   # year 4: straight line over the 24 months left (2,592 / 24) beats 86.40
assert round(sum(charges), 2) == 12000 and charges[-1] > 0, sum(charges)   # fully depreciated exactly at the end of the life
# straight line stays (cost - residual) / life until an addition or a value change
assert s.monthly_charge("SL", 5, None, 12000, 0, 2400, 0, 12, 0, False) == 200
assert s.monthly_charge("SL", 5, None, 18000, 0, 2400, 0, 12, 0, True) == 325            # 15,600 over 48 months
assert s.monthly_charge("SL", 5, None, 12000, 0, 11950, 0, 59, 0, False) == 50           # the last month takes the remainder

# ---- a declining balance asset through the depreciation run: the rate defaults to double the straight-line rate
db_asset = s.save_asset(con, {"AssetName": "Press", "CategoryID": cat["KIT"], "AcquisitionDate": "2026-01-05", "PurchaseAmount": 12000,
                              "VatApplicable": 0, "MethodID": method["DB"], "UsefulLifeYears": 5})
assert db_asset["DepreciationRate"] == 40 and db_asset["MethodCode"] == "DB", db_asset["DepreciationRate"]
expect_error(s.save_asset, con, {"AssetName": "X", "CategoryID": cat["KIT"], "AcquisitionDate": "2026-01-05", "PurchaseAmount": 100,
                                 "MethodID": method["DB"], "UsefulLifeYears": 5, "DepreciationRate": 150}, contains="between 0 and 100")

# ---- capital addition on a straight-line asset after a year in use
van = s.save_asset(con, {"AssetName": "Van", "CategoryID": cat["VEH"], "AcquisitionDate": "2026-01-10", "PurchaseAmount": 12000,
                         "VatApplicable": 0, "UsefulLifeYears": 5})
ext = s.save_asset(con, {"AssetName": "Fridge", "CategoryID": cat["KIT"], "AcquisitionDate": "2026-01-10", "PurchaseAmount": 12000,
                         "VatApplicable": 0, "UsefulLifeYears": 5})
for n in range(1, 13):
    post(2026, n)
assert s.get_asset(con, db_asset["AssetID"])["AccumDep"] == 4800, "a full first year of 400 a month"
assert line(db_asset, per[(2027, 1)])["PeriodDepreciation"] == 240, "the second year starts from the carrying amount 7,200"
v = s.get_asset(con, van["AssetID"])
assert v["AccumDep"] == 2400 and v["NBV"] == 9600
expect_error(s.add_capital, con, van["AssetID"], {"TransactionDate": "2026-12-15", "Amount": 6000}, contains="already posted")
expect_error(s.add_capital, con, van["AssetID"], {"TransactionDate": "2027-01-15", "Amount": 0}, contains="amount")
pv = s.add_capital(con, van["AssetID"], {"TransactionDate": "2027-01-15", "Amount": 6000}, dry=True)
assert pv["CostAfter"] == 18000 and pv["NBVAfter"] == 15600 and pv["MonthlyAfter"] == 325 and pv["MonthsLeft"] == 48, pv
assert not s.get_asset(con, van["AssetID"])["Additions"], "a preview saves nothing"
v = s.add_capital(con, van["AssetID"], {"TransactionDate": "2027-01-15", "Amount": 6000, "ReferenceNumber": "INV-9"})
assert v["Cost"] == 18000 and v["Additions"] == 6000 and v["AcquisitionCost"] == 12000 and v["NBV"] == 15600, (v["Cost"], v["NBV"])
assert line(van, per[(2027, 1)])["PeriodDepreciation"] == 325, "the new carrying amount over the remaining 48 months"
# extending the useful life at the same time spreads it over longer
expect_error(s.add_capital, con, ext["AssetID"], {"TransactionDate": "2027-01-20", "Amount": 6000, "UsefulLifeYears": 0.5}, contains="longer")
assert s.add_capital(con, ext["AssetID"], {"TransactionDate": "2027-01-20", "Amount": 6000, "UsefulLifeYears": 7}, dry=True)["MonthlyAfter"] == 216.67
checks_pass()

# ---- impairment, reversal and revaluation (IAS 36 / IAS 16), each with its own journal
post(2027, 1)
v = s.get_asset(con, van["AssetID"])
assert v["NBV"] == 15275, v["NBV"]
expect_error(s.revalue, con, van["AssetID"], {"TransactionDate": "2027-02-10", "NewValue": 15275}, contains="equals")
imp = s.revalue(con, van["AssetID"], {"TransactionDate": "2027-02-10", "NewValue": 11000}, dry=True)
assert imp["Change"] == -4275 and imp["ToProfitLoss"] == 4275 and imp["ToSurplus"] == 0, imp
v = s.revalue(con, van["AssetID"], {"TransactionDate": "2027-02-10", "NewValue": 11000, "Notes": "Impairment test"})
assert v["NBV"] == 11000 and v["ValueAdj"] == -4275, v["ValueAdj"]
assert line(van, per[(2027, 2)])["PeriodDepreciation"] == round(11000 / 47, 2), "the impaired amount over the 47 months left"
up = s.revalue(con, van["AssetID"], {"TransactionDate": "2027-02-20", "NewValue": 17000}, dry=True)
assert up["Change"] == 6000 and up["ToProfitLoss"] == -4275 and up["ToSurplus"] == 1725, up   # reverse the loss first, the rest to surplus
s.revalue(con, van["AssetID"], {"TransactionDate": "2027-02-20", "NewValue": 17000})
down = s.revalue(con, van["AssetID"], {"TransactionDate": "2027-02-25", "NewValue": 15000}, dry=True)
assert down["ToSurplus"] == -1725 and down["ToProfitLoss"] == 275, down                       # the surplus absorbs the decrease first
s.revalue(con, van["AssetID"], {"TransactionDate": "2027-02-25", "NewValue": 15000})
expect_error(s.revalue, con, van["AssetID"], {"TransactionDate": "2027-02-21", "NewValue": 14000}, contains="after this date")
j = s.rows(con, """SELECT G.AccountCode, SUM(J.DebitAmount-J.CreditAmount) net FROM tbl_DepreciationJournal J JOIN tbl_GLAccounts G ON G.GLAccountID=J.GLAccountID
    WHERE J.JournalType IN ('IMPAIRMENT','REVALUATION') GROUP BY G.AccountCode""", raw=True)
net = {r["AccountCode"]: round(r["net"], 2) for r in j}
assert net["620102"] == 275 and net["330101"] == 0, net        # net loss 4,275 - 4,275 + 275; surplus 1,725 - 1,725
# below the residual value: the residual comes down with it, so depreciation never goes past the new value
low = s.save_asset(con, {"AssetName": "Sign", "CategoryID": cat["FUR"], "AcquisitionDate": "2027-01-05", "PurchaseAmount": 5000, "ResidualValue": 1000, "VatApplicable": 0})
assert s.revalue(con, low["AssetID"], {"TransactionDate": "2027-01-20", "NewValue": 600})["ResidualValue"] == 600
checks_pass()

# ---- the forecast keeps following the run after additions and value changes, and for declining balance
fc = reports.run_report(con, "depreciation-forecast", {"months": "2"})
feb = round(sum(l["PeriodDepreciation"] for l in s.propose(con, per[(2027, 2)]) if l["eligible"]), 2)
assert round(sum(r["Depreciation"] for r in fc["rows"] if r["MonthKey"] == "2027-02"), 2) == feb, feb

# ---- disposal after all of it: cost with the addition, net accumulated depreciation, gain against the revalued amount
post(2027, 2)
v = s.get_asset(con, van["AssetID"])
d = s.dispose_asset(con, van["AssetID"], {"TransactionDate": "2027-03-05", "DisposalProceeds": 16000})
rows_ = s.rows(con, "SELECT * FROM tbl_DepreciationJournal WHERE TransactionID=(SELECT MAX(TransactionID) FROM tbl_AssetTransactions WHERE TransactionType='DISPOSAL')", raw=True)
assert round(sum(r["CreditAmount"] for r in rows_ if r["GLAccountID"] == s.one(con, "SELECT AssetAccountID a FROM tbl_AssetCategories WHERE CategoryID=?", (cat["VEH"],))["a"]), 2) == 18000
gain = round(sum(r["CreditAmount"] - r["DebitAmount"] for r in rows_ if r["GLAccountID"] in (
    s.one(con, "SELECT GainAccountID g FROM tbl_AssetCategories WHERE CategoryID=?", (cat["VEH"],))["g"],
    s.one(con, "SELECT LossAccountID l FROM tbl_AssetCategories WHERE CategoryID=?", (cat["VEH"],))["l"])), 2)
assert gain == round(16000 - v["NBV"], 2), (gain, v["NBV"])
checks_pass()

# ---- reports: the register and the roll-forward show the value changes and still tie
reg = reports.run_report(con, "asset-register", {"as_of": "2027-02-28"})
row = next(r for r in reg["rows"] if r["AssetCode"] == van["AssetCode"])
assert row["Cost"] == 18000 and row["ValueAdj"] == -275 and row["NBV"] == round(18000 - row["AccumDep"] - 275, 2), row
rf = reports.run_report(con, "rollforward", {"from": "2027-01-01", "to": "2027-03-31"})
tot = {k: round(sum(r[k] for r in rf["rows"]), 2) for k in ("OpenCost", "Additions", "Disposals", "CloseCost", "Charge", "Impairment", "CloseDep", "NBV")}
posted = round(s.one(con, """SELECT SUM(D.PeriodDepreciation) s FROM tbl_Depreciation D JOIN tbl_DepreciationPeriods P ON P.PeriodID=D.PeriodID
    WHERE D.PostingStatus='POSTED' AND P.FiscalYear=2027""")["s"], 2)
assert tot["Charge"] == posted, (tot["Charge"], posted)
assert tot["Additions"] == 6000 + 5000 and tot["Disposals"] == 18000, tot             # the van addition and the new sign; the van out
assert tot["Impairment"] == round(-(-4275 + 6000 - 2000) + 4400, 2), tot                      # van 275 net, the sign 4,400 down
reval = reports.run_report(con, "revaluations", {})
assert len(reval["rows"]) == 5 and {r["TransactionType"] for r in reval["rows"]} == {"ADDITION", "IMPAIRMENT", "REVALUATION"}
jr = reports.run_report(con, "depreciation-journal", {"from": "2027-01-01", "to": "2027-03-31", "jview": "summary"})
assert {r["Document"] for r in jr["rows"]} >= {"DEP-2027-01", "DEP-2027-02"} and round(sum(r["DebitAmount"] - r["CreditAmount"] for r in jr["rows"]), 2) == 0

# ---- the ledger: one asset's entries add up to its net book value, in order, each with a document number
lg = ledger.ledger(con, asset=db_asset["AssetID"])
assert lg["rows"][0]["EntryType"] == "ACQUISITION" and lg["rows"][-1]["Balance"] == s.get_asset(con, db_asset["AssetID"])["NBV"], lg["rows"][-1]
assert lg["rows"][1]["Document"] == "DEP-2026-01" and lg["total"] == 1 + 14, lg["total"]
lv = ledger.ledger(con, asset=van["AssetID"])
assert lv["rows"][-1]["EntryType"] == "DISPOSAL" and lv["rows"][-1]["Balance"] == 0, lv["rows"][-1]   # a disposed asset ends at zero
ej = ledger.entry_journal(con, tx=lv["rows"][-1]["TransactionID"])
assert ej["head"]["Document"].startswith("DSP-") and round(sum(l["DebitAmount"] - l["CreditAmount"] for l in ej["lines"]), 2) == 0
page = ledger.ledger(con, limit=5, offset=0)
assert len(page["rows"]) == 5 and page["total"] > 5 and page["rows"][0]["EntryDate"] >= page["rows"][-1]["EntryDate"]

# ---- countries, branches and scope: a user limited to one branch sees only it, in lists, reports and postings
for code, name, cc in (("RYD", "Riyadh", "SA"), ("JED", "Jeddah", "SA"), ("DXB", "Dubai", "AE")):
    s.master_save(con, "branches", {"BranchCode": code, "BranchName": name, "CountryCode": cc})
expect_error(s.master_save, con, "branches", {"BranchCode": "X", "BranchName": "X", "CountryCode": "ZZ"}, contains="country")
br = {r["BranchCode"]: r["BranchID"] for r in s.rows(con, "SELECT * FROM tbl_Branches", raw=True)}
expect_error(s.master_save, con, "locations", {"LocationCode": "L0", "LocationName": "No branch"}, contains="branch")
for code, b in (("RYD-1", "RYD"), ("JED-1", "JED"), ("DXB-1", "DXB")):
    s.master_save(con, "locations", {"LocationCode": code, "LocationName": code, "BranchID": br[b]})
loc = {r["LocationCode"]: r["LocationID"] for r in s.rows(con, "SELECT * FROM tbl_Locations", raw=True)}
mk = lambda name, where: s.save_asset(con, {"AssetName": name, "CategoryID": cat["IT"], "AcquisitionDate": "2027-03-01", "PurchaseAmount": 3600,
                                             "VatApplicable": 0, "LocationID": loc[where]})
a_ryd, a_jed, a_dxb = mk("PC Riyadh", "RYD-1"), mk("PC Jeddah", "JED-1"), mk("PC Dubai", "DXB-1")
uid = s.one(con, "SELECT UserID FROM tbl_Users LIMIT 1")
from app import auth  # noqa: E402
auth.seed(con)
user = auth.save_user(con, {"UserName": "ryd.clerk", "FullName": "Riyadh clerk", "RoleID": auth.admin_role_id(con), "Password": "Passw0rd123",
                            "Branches": [br["RYD"]]})
assert user["Branches"] == [br["RYD"]]
sc = s.apply_scope(con, user["UserID"], None)
assert sc["scope"] == [br["RYD"]]
codes = {a["AssetCode"] for a in s.list_assets(con)}
assert a_ryd["AssetCode"] in codes and not codes & {a_jed["AssetCode"], a_dxb["AssetCode"], van["AssetCode"]}, codes
expect_error(s.get_asset, con, a_jed["AssetID"], contains="not found")
expect_error(s.save_asset, con, {"AssetName": "Y", "CategoryID": cat["IT"], "AcquisitionDate": "2027-03-01", "PurchaseAmount": 1, "LocationID": loc["DXB-1"]}, contains="branches you work in")
expect_error(s.create_count, con, {"Title": "All", "CountDate": "2027-03-10"}, contains="branches you work in")
assert {r["AssetCode"] for r in reports.run_report(con, "asset-register", {"as_of": "2027-03-31"})["rows"]} == {a_ryd["AssetCode"]}
assert {l["AssetID"] for l in s.propose(con, per[(2027, 3)])} == {a_ryd["AssetID"]}
assert all(r["AssetCode"] == a_ryd["AssetCode"] for r in ledger.ledger(con)["rows"])
assert s.dashboard(con)["asset_count"] == 1
# asking for another country falls back to the user's own branches; an unrestricted user may narrow to a country
assert s.apply_scope(con, user["UserID"], "country:AE")["scope"] == [br["RYD"]]
assert s.apply_scope(con, None, "country:SA")["scope"] == sorted([br["RYD"], br["JED"]])
assert {r["AssetCode"] for r in reports.run_report(con, "asset-register", {"as_of": "2027-03-31"})["rows"]} == {a_ryd["AssetCode"], a_jed["AssetCode"]}
s.set_scope(None)
# reports by country and branch
summ = reports.run_report(con, "asset-summary", {"group_by": "country", "as_of": "2027-03-31"})
assert {r["k"] for r in summ["rows"]} >= {"Saudi Arabia", "United Arab Emirates"}, summ["rows"]
assert len(reports.run_report(con, "asset-register", {"country": "AE", "as_of": "2027-03-31"})["rows"]) == 1
rfb = reports.run_report(con, "rollforward", {"from": "2027-01-01", "to": "2027-03-31", "rgroup": "branch"})
assert round(sum(r["CloseCost"] for r in rfb["rows"]), 2) == round(sum(r["CloseCost"] for r in reports.run_report(con, "rollforward", {"from": "2027-01-01", "to": "2027-03-31"})["rows"]), 2)
checks_pass()
print("All valuation, ledger and branch tests passed")
