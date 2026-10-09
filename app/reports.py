"""Usool - report builders. Every report returns
{title, params, columns:[{key,label,type}], rows:[...], group_by?, totals:[keys]}.

Book values follow services/book.py (cost with additions, accumulated depreciation, revaluation / impairment, NBV).
Every asset query keeps to the branches in scope (services/common.py scope_sql) and the branch / country filters.
"""
from __future__ import annotations

from datetime import date

from .services import ApiError, to_int, get_settings, one, parse_date, r2, rows
from .services.book import VALUE_IN, doc_no_sql
from .services.branches import COUNTRY_AR_SQL, COUNTRY_SQL
from .services.common import scope_sql

ORG = ["branch", "country"]
REPORTS = [
    dict(id="asset-register", group="Fixed assets", params=["as_of", "category", "branch", "country", "location", "costcenter", "status"]),
    dict(id="vat-purchases", group="Fixed assets", params=["from", "to", "vat", "branch"]),
    dict(id="asset-summary", group="Fixed assets", params=["as_of", "group_by", "branch", "country"]),
    dict(id="rollforward", group="Fixed assets", params=["from", "to", "rgroup", "branch", "country"]),
    dict(id="depreciation-schedule", group="Depreciation", params=["fiscal_year", "category", "branch"]),
    dict(id="depreciation-forecast", group="Depreciation", params=["months", "category", "branch"]),
    dict(id="depreciation-journal", group="Depreciation", params=["from", "to", "jview", "branch"]),
    dict(id="gl-balances", group="Depreciation", params=["as_of", "account", "branch"]),
    dict(id="disposals", group="Transactions", params=["from", "to", "branch"]),
    dict(id="revaluations", group="Transactions", params=["from", "to", "branch"]),
    dict(id="transactions", group="Transactions", params=["from", "to", "type", "branch"]),
    dict(id="fully-depreciated", group="Exceptions", params=["as_of", "branch"]),
    dict(id="warranty-expiry", group="Exceptions", params=["days", "branch"]),
    dict(id="custody-by-employee", group="Contacts", params=["from", "to", "employee", "cstatus"], perm="custody.view"),
    dict(id="employees-directory", group="Contacts", params=["sactive"], perm="contacts.view"),
    dict(id="suppliers-directory", group="Suppliers", params=["sactive", "stype"], perm="contacts.view"),
    dict(id="supplier-purchases", group="Suppliers", params=["from", "to", "supplier"], perm="contacts.view"),
    dict(id="supplier-summary", group="Suppliers", params=["from", "to"], perm="contacts.view"),
    dict(id="maintenance-history", group="Maintenance", params=["from", "to", "mstatus", "mtype", "category"], perm="maintenance.view"),
    dict(id="maintenance-cost", group="Maintenance", params=["from", "to", "mgroup"], perm="maintenance.view"),
    dict(id="maintenance-schedule", group="Maintenance", params=["days"], perm="maintenance.view"),
]
REPORT_PERM = {r["id"]: r.get("perm") for r in REPORTS}   # on top of reports.view: contact, custody and maintenance data keep their own permission


def _cols(*spec):
    return [dict(key=k, label=l, type=t) for k, l, t in spec]


def _as_of(p):
    return parse_date(p.get("as_of"), "As of date") or date.today().isoformat()


def _span(f: str, t: str) -> str:
    return f"{f if f > '1901' else 'Beginning'} to {t if t < '2999' else 'today'}"


def _org(p: dict | None, alias: str = "A") -> tuple[str, list]:
    """SQL and arguments keeping to the branches in scope and the report's branch / country filters."""
    sql, args = scope_sql(alias), []
    p = p or {}
    if p.get("branch"):
        sql += f" AND {alias}.LocationID IN (SELECT LocationID FROM tbl_Locations WHERE BranchID=?)"
        args.append(to_int(p["branch"], "Branch"))
    if p.get("country"):
        sql += f" AND {alias}.LocationID IN (SELECT L.LocationID FROM tbl_Locations L JOIN tbl_Branches B ON B.BranchID=L.BranchID WHERE B.CountryCode=?)"
        args.append(str(p["country"]).upper())
    return sql, args


def _quiet(rows_: list[dict], keys) -> list[str]:
    """Columns with nothing to show in these rows (no branches set up, no revaluations): kept for analysis, hidden at first."""
    return [k for k in keys if not any(r.get(k) for r in rows_)]


def _sums(con, sql: str, args) -> dict[int, float]:
    return {r[0]: r[1] or 0 for r in con.execute(sql, args)}


def asset_state(con, as_of: str, p: dict | None = None) -> list[dict]:
    """Cost / accumulated depreciation / revaluation and impairment / NBV of every asset at a given date."""
    accum = _sums(con, """SELECT D.AssetID, SUM(D.PeriodDepreciation) FROM tbl_Depreciation D JOIN tbl_DepreciationPeriods P ON P.PeriodID=D.PeriodID
           WHERE D.PostingStatus='POSTED' AND P.EndDate<=? GROUP BY D.AssetID""", (as_of,))
    adds = _sums(con, "SELECT AssetID, SUM(Amount) FROM tbl_AssetTransactions WHERE TransactionType='ADDITION' AND TransactionDate<=? GROUP BY AssetID", (as_of,))
    adj = _sums(con, f"SELECT AssetID, SUM(Amount) FROM tbl_AssetTransactions WHERE TransactionType IN {VALUE_IN} AND TransactionDate<=? GROUP BY AssetID", (as_of,))
    org, args = _org(p)
    out = []
    for a in rows(con, f"""SELECT A.*, C.CategoryName, C.CategoryNameAr, L.LocationName, L.LocationNameAr, CC.CostCenterName, CC.CostCenterNameAr,
            B.BranchID, B.BranchCode, B.BranchName, B.BranchNameAr, B.Region, B.CountryCode, {COUNTRY_SQL} AS CountryName, {COUNTRY_AR_SQL} AS CountryNameAr
            FROM tbl_Assets A LEFT JOIN tbl_AssetCategories C ON C.CategoryID=A.CategoryID LEFT JOIN tbl_Locations L ON L.LocationID=A.LocationID
            LEFT JOIN tbl_Branches B ON B.BranchID=L.BranchID LEFT JOIN tbl_CostCenters CC ON CC.CostCenterID=A.CostCenterID
            WHERE A.AcquisitionDate<=?{org} ORDER BY A.AssetCode""", [as_of, *args]):
        if a["DisposalDate"] and a["DisposalDate"] <= as_of:
            continue
        aid = a["AssetID"]
        a["AccumDep"] = r2((a["OpeningAccumDep"] or 0) + accum.get(aid, 0))
        a["Cost"] = r2((a["AcquisitionCost"] or 0) + adds.get(aid, 0))
        a["ValueAdj"] = r2(adj.get(aid, 0))
        a["NBV"] = r2(a["Cost"] - a["AccumDep"] + a["ValueAdj"])
        a["VatStatus"] = "With VAT" if a.get("VatApplicable") else "No VAT"
        out.append(a)
    return out


def asset_register(con, p):
    d = _as_of(p)
    data = asset_state(con, d, p)
    for key, col in (("category", "CategoryID"), ("location", "LocationID"), ("costcenter", "CostCenterID")):
        if p.get(key):
            data = [a for a in data if str(a[col]) == str(p[key])]
    if p.get("status"):
        data = [a for a in data if a["AssetStatus"] == p["status"]]
    return dict(columns=_cols(("AssetCode", "Asset", "text"), ("AssetName", "Name", "text"), ("CategoryName", "Group", "text"),
                              ("CountryName", "Country", "text"), ("BranchCode", "Branch", "text"), ("BranchName", "Branch name", "text"),
                              ("LocationName", "Location", "text"), ("AcquisitionDate", "Acquired", "date"), ("VatStatus", "VAT", "text"),
                              ("Cost", "Cost", "money"), ("AccumDep", "Accum. depreciation", "money"), ("ValueAdj", "Revaluation / (impairment)", "money"),
                              ("NBV", "Net book value", "money")),
                rows=data, group_by="CategoryName", totals=["Cost", "AccumDep", "ValueAdj", "NBV"], subtitle=f"As of {d}",
                hidden=["CountryName", "BranchName", "VatStatus"] + _quiet(data, ("BranchCode", "ValueAdj")))


GROUPINGS = {"category": ("CategoryName", "Group"), "country": ("CountryName", "Country"), "branch": ("BranchName", "Branch"),
             "region": ("Region", "Region"), "location": ("LocationName", "Location"), "costcenter": ("CostCenterName", "Cost center")}


def asset_summary(con, p):
    d = _as_of(p)
    col, label = GROUPINGS.get(p.get("group_by") or "category", GROUPINGS["category"])
    agg: dict[str, dict] = {}
    for a in asset_state(con, d, p):
        k = a[col] or "(none)"
        g = agg.setdefault(k, dict(k=k, Count=0, Cost=0, AccumDep=0, ValueAdj=0, NBV=0))
        g["Count"] += 1
        for f in ("Cost", "AccumDep", "ValueAdj", "NBV"):
            g[f] += a[f]
    data = [{**g, **{f: r2(g[f]) for f in ("Cost", "AccumDep", "ValueAdj", "NBV")}} for g in sorted(agg.values(), key=lambda g: g["k"])]
    return dict(columns=_cols(("k", label, "text"), ("Count", "Assets", "int"), ("Cost", "Cost", "money"),
                              ("AccumDep", "Accum. depreciation", "money"), ("ValueAdj", "Revaluation / (impairment)", "money"),
                              ("NBV", "Net book value", "money")),
                rows=data, totals=["Count", "Cost", "AccumDep", "ValueAdj", "NBV"], subtitle=f"As of {d}", hidden=_quiet(data, ("ValueAdj",)))


def rollforward(con, p):
    """The movement of cost and of accumulated depreciation and impairment over a window (IAS 16.73(e)), per group,
    branch or country. Accumulated depreciation and impairment = accumulated depreciation - revaluation / impairment."""
    f = parse_date(p.get("from"), "From date", True)
    t = parse_date(p.get("to"), "To date", True)
    if f > t:
        raise ApiError("From date is after To date")
    prev = date.fromordinal(date.fromisoformat(f).toordinal() - 1).isoformat()
    col, label = GROUPINGS.get(p.get("rgroup") or "category", GROUPINGS["category"])
    keys = ["OpenCost", "Additions", "Disposals", "CloseCost", "OpenDep", "BroughtIn", "Charge", "Impairment", "DepDisposed", "CloseDep", "NBV"]
    agg: dict[str, dict] = {}
    grp = lambda a: agg.setdefault(a[col] or "(none)", dict(Group=a[col] or "(none)", **{k: 0.0 for k in keys}))
    opening = {a["AssetID"]: a for a in asset_state(con, prev, p)}
    closing = {a["AssetID"]: a for a in asset_state(con, t, p)}
    org, args = _org(p)
    # disposals in the window: the cost and the net accumulated depreciation they took out of the books
    disposed = {r["AssetID"]: r for r in rows(con, f"""SELECT T.AssetID, T.Amount, COALESCE((SELECT SUM(J.DebitAmount-J.CreditAmount)
            FROM tbl_DepreciationJournal J JOIN tbl_AssetCategories C ON C.AccumDepAccountID=J.GLAccountID
            WHERE J.TransactionID=T.TransactionID AND C.CategoryID=A.CategoryID),0) AS AccumOut
            FROM tbl_AssetTransactions T JOIN tbl_Assets A ON A.AssetID=T.AssetID
            WHERE T.TransactionType='DISPOSAL' AND T.TransactionDate>? AND T.TransactionDate<=?{org}""", [prev, t, *args], raw=True)}
    value_moves = _sums(con, f"""SELECT T.AssetID, SUM(T.Amount) FROM tbl_AssetTransactions T JOIN tbl_Assets A ON A.AssetID=T.AssetID
            WHERE T.TransactionType IN {VALUE_IN} AND T.TransactionDate>? AND T.TransactionDate<=?{org} GROUP BY T.AssetID""", [prev, t, *args])
    for a in opening.values():
        g = grp(a); g["OpenCost"] += a["Cost"]; g["OpenDep"] += a["AccumDep"] - a["ValueAdj"]
    for aid, a in closing.items():
        g = grp(a); g["CloseCost"] += a["Cost"]; g["CloseDep"] += a["AccumDep"] - a["ValueAdj"]
        if aid in opening:
            g["Additions"] += a["Cost"] - opening[aid]["Cost"]          # capital additions in the window
        else:
            g["Additions"] += a["Cost"]; g["BroughtIn"] += a["OpeningAccumDep"] or 0
    # disposed in the window: from the opening books, or acquired and disposed in between
    gone = [aid for aid in disposed if aid not in closing]
    born = {r["AssetID"]: r for r in rows(con, f"""SELECT A.*, C.CategoryName, C.CategoryNameAr, L.LocationName, L.LocationNameAr,
            CC.CostCenterName, CC.CostCenterNameAr, B.BranchName, B.BranchNameAr, B.Region, {COUNTRY_SQL} AS CountryName, {COUNTRY_AR_SQL} AS CountryNameAr
            FROM tbl_Assets A LEFT JOIN tbl_AssetCategories C ON C.CategoryID=A.CategoryID LEFT JOIN tbl_Locations L ON L.LocationID=A.LocationID
            LEFT JOIN tbl_Branches B ON B.BranchID=L.BranchID LEFT JOIN tbl_CostCenters CC ON CC.CostCenterID=A.CostCenterID
            WHERE A.AcquisitionDate>? AND A.AcquisitionDate<=? AND A.DisposalDate IS NOT NULL AND A.DisposalDate<=?{org}""", [prev, t, t, *args])}
    for aid in gone:
        dsp = disposed[aid]
        if aid in opening:
            a = opening[aid]; g = grp(a)
            g["Additions"] += (dsp["Amount"] or 0) - a["Cost"]
        elif aid in born:
            a = born[aid]; g = grp(a)
            g["Additions"] += dsp["Amount"] or 0; g["BroughtIn"] += a["OpeningAccumDep"] or 0
        else:
            continue
        g["Disposals"] += dsp["Amount"] or 0; g["DepDisposed"] += dsp["AccumOut"]
    names = {**{aid: a for aid, a in opening.items()}, **{aid: a for aid, a in closing.items()}, **born}
    for aid, amount in value_moves.items():
        if aid in names:
            grp(names[aid])["Impairment"] -= amount                     # an impairment raises accumulated depreciation and impairment
    data = []
    for g in agg.values():
        g["NBV"] = g["CloseCost"] - g["CloseDep"]
        g["Charge"] = g["CloseDep"] - g["OpenDep"] - g["BroughtIn"] - g["Impairment"] + g["DepDisposed"]
        if any(abs(g[k]) > 0.004 for k in keys):
            data.append({k: (v if k == "Group" else r2(v)) for k, v in g.items()})
    data.sort(key=lambda g: g["Group"])
    return dict(columns=_cols(("Group", label, "text"), ("OpenCost", "Opening cost", "money"), ("Additions", "Additions", "money"),
                              ("Disposals", "Disposals", "money"), ("CloseCost", "Closing cost", "money"),
                              ("OpenDep", "Opening accum. dep. & impairment", "money"), ("BroughtIn", "Dep. on additions", "money"),
                              ("Charge", "Depreciation charge", "money"), ("Impairment", "Impairment / (revaluation)", "money"),
                              ("DepDisposed", "Dep. on disposals", "money"), ("CloseDep", "Closing accum. dep. & impairment", "money"),
                              ("NBV", "Net book value", "money")),
                rows=data, totals=keys, subtitle=f"{f} to {t}", hidden=_quiet(data, ("BroughtIn", "Impairment")))


def depreciation_schedule(con, p):
    fy = to_int(p.get("fiscal_year"), "Fiscal year", date.today().year)
    if not 1990 <= fy <= 2100:
        raise ApiError("Fiscal year is not valid")
    org, oargs = _org(p)
    sql = f"""SELECT A.AssetCode, A.AssetName, A.AssetNameAr, C.CategoryName, C.CategoryNameAr, P.PeriodName, P.PeriodNumber, P.PeriodStatus, D.AcquisitionCost,
             D.OpeningAccumDep, D.PeriodDepreciation, D.ClosingAccumDep, D.ClosingNBV, D.PostingStatus
             FROM tbl_Depreciation D JOIN tbl_Assets A ON A.AssetID=D.AssetID JOIN tbl_DepreciationPeriods P ON P.PeriodID=D.PeriodID
             LEFT JOIN tbl_AssetCategories C ON C.CategoryID=A.CategoryID WHERE P.FiscalYear=?{org}"""
    args = [fy, *oargs]
    if p.get("category"):
        sql += " AND A.CategoryID=?"; args.append(p["category"])
    data = rows(con, sql + " ORDER BY A.AssetCode, P.PeriodNumber", args)
    return dict(columns=_cols(("AssetCode", "Asset", "text"), ("AssetName", "Name", "text"), ("CategoryName", "Group", "text"), ("PeriodName", "Period", "text"),
                              ("AcquisitionCost", "Cost", "money"), ("OpeningAccumDep", "Opening accum. dep.", "money"),
                              ("PeriodDepreciation", "Depreciation", "money"), ("ClosingAccumDep", "Closing accum. dep.", "money"),
                              ("ClosingNBV", "Net book value", "money"), ("PostingStatus", "Status", "text")),
                rows=data, group_by="AssetCode", totals=["PeriodDepreciation"], subtotal_only=["PeriodDepreciation"],
                order={"PeriodName": "PeriodNumber"}, subtitle=f"Fiscal year {fy}")


def depreciation_forecast(con, p):
    """Depreciation still to come, month by month, from the first month not yet posted: the depreciation run's own rule
    (services/depreciation.py monthly_charge), including declining balance, additions and revaluations."""
    from .services.depreciation import DEPRECIATING, _month_index, _start, monthly_charge
    months = to_int(p.get("months"), "Months", 12)
    if not 1 <= months <= 60:
        raise ApiError("Months must be between 1 and 60")
    first = one(con, """SELECT MIN(P.StartDate) s FROM tbl_DepreciationPeriods P WHERE NOT EXISTS
        (SELECT 1 FROM tbl_Depreciation D WHERE D.PeriodID=P.PeriodID AND D.PostingStatus='POSTED')""", raw=True)["s"] or date.today().isoformat()
    y0, m0 = int(first[:4]), int(first[5:7])
    start_idx = y0 * 12 + m0 - 1
    fsm = int(get_settings(con).get("FiscalYearStartMonth") or 1)
    fy_of = lambda k: (k - (fsm - 1)) // 12                      # month index -> fiscal year (the calendar year it starts in)
    names = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
    org, oargs = _org(p)
    sql = f"""SELECT A.*, C.CategoryName, C.CategoryNameAr, M.MethodCode,
        COALESCE(A.OpeningAccumDep,0) + COALESCE((SELECT SUM(D.PeriodDepreciation) FROM tbl_Depreciation D WHERE D.AssetID=A.AssetID AND D.PostingStatus='POSTED'),0) AS Accum,
        (SELECT COUNT(*) FROM tbl_Depreciation D WHERE D.AssetID=A.AssetID AND D.PostingStatus='POSTED') AS Posted
        FROM tbl_Assets A LEFT JOIN tbl_AssetCategories C ON C.CategoryID=A.CategoryID LEFT JOIN tbl_DepreciationMethods M ON M.MethodID=A.MethodID
        WHERE A.AssetStatus<>'Disposed' AND A.IsActive=1{org}"""
    args: list = list(oargs)
    if p.get("category"):
        sql += " AND A.CategoryID=?"; args.append(p["category"])
    first_period = one(con, "SELECT MIN(StartDate) s FROM tbl_DepreciationPeriods", raw=True)["s"]
    # what the current fiscal year already charged (declining balance), and every addition / value change with its date
    fy0 = fy_of(start_idx)
    fy_start = f"{fy0 + (fsm - 1) // 12:04d}-{(fsm - 1) % 12 + 1:02d}-01"
    fy_dep = _sums(con, """SELECT D.AssetID, SUM(D.PeriodDepreciation) FROM tbl_Depreciation D JOIN tbl_DepreciationPeriods P ON P.PeriodID=D.PeriodID
        WHERE D.PostingStatus='POSTED' AND P.StartDate>=? AND P.StartDate<? GROUP BY D.AssetID""", (fy_start, first))
    moves: dict[int, list] = {}
    for r in con.execute("SELECT AssetID, TransactionType, TransactionDate, Amount FROM tbl_AssetTransactions WHERE TransactionType IN ('ADDITION','IMPAIRMENT','REVALUATION')"):
        moves.setdefault(r[0], []).append((r[2], r[1], r[3] or 0))
    out = []
    for a in rows(con, sql + " ORDER BY A.AssetCode", args):
        if a["MethodCode"] not in DEPRECIATING or not a["UsefulLifeYears"]:
            continue
        start = _start(a)
        if first_period and start[:7] < first_period[:7] and not (a["OpeningAccumDep"] or 0) and not a["Posted"]:
            continue   # the depreciation run refuses it until the opening balance is entered; so does the forecast
        accum, fy_charged, fy_cur = a["Accum"], fy_dep.get(a["AssetID"], 0), fy0
        sidx = _month_index(start) - 1
        for k in range(max(start_idx, sidx), start_idx + months):
            yy, mm = divmod(k, 12)
            month_end = f"{yy:04d}-{mm + 1:02d}-31"
            if fy_of(k) != fy_cur:
                fy_cur, fy_charged = fy_of(k), 0
            done = [x for x in moves.get(a["AssetID"], []) if x[0] <= month_end]
            cost = (a["AcquisitionCost"] or 0) + sum(x[2] for x in done if x[1] == "ADDITION")
            adj = sum(x[2] for x in done if x[1] != "ADDITION")
            amount = monthly_charge(a["MethodCode"], a["UsefulLifeYears"], a["DepreciationRate"], cost, a["ResidualValue"] or 0,
                                    accum, adj, k - sidx, fy_charged, bool(done))
            if amount <= 0:
                if not any(x[0] > month_end for x in moves.get(a["AssetID"], [])):
                    break
                continue
            accum += amount
            fy_charged += amount
            out.append({"AssetCode": a["AssetCode"], "AssetName": a["AssetName"], "AssetNameAr": a["AssetNameAr"], "CategoryName": a["CategoryName"],
                        "CategoryNameAr": a["CategoryNameAr"], "Year": str(yy), "MonthKey": f"{yy}-{mm + 1:02d}", "Month": f"{names[mm]} {yy}",
                        "Depreciation": amount, "ClosingNBV": r2(cost - accum + adj)})
    from .services.common import month_ar, _ctx
    if getattr(_ctx, "lang", "en") == "ar":
        for r in out:
            r["Month"] = month_ar(r["Month"])
            r["AssetName"] = r["AssetNameAr"] or r["AssetName"]; r["CategoryName"] = r["CategoryNameAr"] or r["CategoryName"]
    return dict(columns=_cols(("Month", "Month", "text"), ("Year", "Year", "text"), ("AssetCode", "Asset", "text"), ("AssetName", "Name", "text"),
                              ("CategoryName", "Group", "text"), ("Depreciation", "Depreciation", "money"), ("ClosingNBV", "Net book value", "money")),
                rows=out, group_by="Month", totals=["Depreciation"], subtotal_only=["Depreciation"], order={"Month": "MonthKey"},
                subtitle=f"{months} months from {first}")


DOC_SQL = f"""CASE WHEN J.DepreciationID IS NOT NULL THEN 'DEP-'||substr(P.StartDate,1,7) ELSE {doc_no_sql('T.TransactionType', 'J.TransactionID')} END"""


def depreciation_journal(con, p):
    """The fixed asset journal as vouchers: one document per month's depreciation (DEP-2026-10) and per transaction
    (DSP-000042 ...), with its debit and credit lines. The summary view adds them up per document and account: the entry
    to post to the general ledger."""
    f = parse_date(p.get("from"), "From date") or "1900-01-01"
    t = parse_date(p.get("to"), "To date") or "2999-12-31"
    org, oargs = _org(p)
    base = f"""FROM tbl_DepreciationJournal J LEFT JOIN tbl_GLAccounts G ON G.GLAccountID=J.GLAccountID
            LEFT JOIN tbl_DepreciationPeriods P ON P.PeriodID=J.PeriodID LEFT JOIN tbl_AssetTransactions T ON T.TransactionID=J.TransactionID
            JOIN tbl_Assets A ON A.AssetID=J.AssetID WHERE J.JournalDate BETWEEN ? AND ?{org}"""
    if p.get("jview") == "summary":
        data = rows(con, f"""SELECT {DOC_SQL} AS Document, J.JournalDate, J.JournalType, G.AccountCode, G.AccountName, G.AccountNameAr,
                COUNT(DISTINCT J.AssetID) AS Assets, SUM(J.DebitAmount) AS DebitAmount, SUM(J.CreditAmount) AS CreditAmount
                {base} GROUP BY 1, J.JournalDate, J.JournalType, G.GLAccountID ORDER BY J.JournalDate, 1, G.AccountCode""", [f, t, *oargs])
        for r in data:
            r["DebitAmount"], r["CreditAmount"] = r2(r["DebitAmount"]), r2(r["CreditAmount"])
        return dict(columns=_cols(("JournalDate", "Date", "date"), ("JournalType", "Type", "text"), ("AccountCode", "Account", "text"),
                                  ("AccountName", "Account name", "text"), ("Assets", "Assets", "int"),
                                  ("DebitAmount", "Debit", "money"), ("CreditAmount", "Credit", "money")),
                    rows=data, group_by="Document", totals=["DebitAmount", "CreditAmount"], subtitle=_span(f, t))
    data = rows(con, f"""SELECT {DOC_SQL} AS Document, J.JournalDate, J.JournalType, J.Reference, G.AccountCode, G.AccountName, G.AccountNameAr,
            J.Description, J.DebitAmount, J.CreditAmount {base} ORDER BY J.JournalDate, Document, J.JournalID""", [f, t, *oargs])
    return dict(columns=_cols(("JournalDate", "Date", "date"), ("JournalType", "Type", "text"), ("Reference", "Asset", "text"),
                              ("AccountCode", "Account", "text"), ("AccountName", "Account name", "text"),
                              ("Description", "Description", "text"), ("DebitAmount", "Debit", "money"), ("CreditAmount", "Credit", "money")),
                rows=data, group_by="Document", totals=["DebitAmount", "CreditAmount"], subtitle=_span(f, t))


def gl_balances(con, p):
    d = _as_of(p)
    acc = to_int(p.get("account"), "Account")
    org, oargs = _org(p)
    data = rows(con, f"""SELECT G.AccountCode, G.AccountName, G.AccountNameAr, G.AccountType, SUM(J.DebitAmount) Debit, SUM(J.CreditAmount) Credit,
            SUM(J.DebitAmount)-SUM(J.CreditAmount) Balance FROM tbl_DepreciationJournal J JOIN tbl_GLAccounts G ON G.GLAccountID=J.GLAccountID
            JOIN tbl_Assets A ON A.AssetID=J.AssetID
            WHERE J.JournalDate<=? AND (?=0 OR G.GLAccountID=?){org} GROUP BY G.GLAccountID ORDER BY G.AccountCode""", [d, acc, acc, *oargs])
    for r in data:
        for k in ("Debit", "Credit", "Balance"):
            r[k] = r2(r[k])
    return dict(columns=_cols(("AccountCode", "Account", "text"), ("AccountName", "Account name", "text"), ("Debit", "Debit", "money"),
                              ("Credit", "Credit", "money"), ("Balance", "Balance", "money")),
                rows=data, totals=["Debit", "Credit", "Balance"], subtitle=f"Fixed asset postings as of {d}")


def disposals(con, p):
    f = parse_date(p.get("from"), "From date") or "1900-01-01"
    t = parse_date(p.get("to"), "To date") or date.today().isoformat()
    org, oargs = _org(p)
    out = []
    for r in rows(con, f"""SELECT T.*, A.AssetCode, A.AssetName, A.AssetNameAr, A.AcquisitionDate, C.CategoryName, C.CategoryNameAr, B.BranchName, B.BranchNameAr,
            COALESCE((SELECT SUM(J.DebitAmount-J.CreditAmount) FROM tbl_DepreciationJournal J WHERE J.TransactionID=T.TransactionID
                AND J.GLAccountID=C.AccumDepAccountID),0) AS AccumOut
            FROM tbl_AssetTransactions T JOIN tbl_Assets A ON A.AssetID=T.AssetID LEFT JOIN tbl_AssetCategories C ON C.CategoryID=A.CategoryID
            LEFT JOIN tbl_Locations L ON L.LocationID=T.FromLocationID LEFT JOIN tbl_Branches B ON B.BranchID=L.BranchID
            WHERE T.TransactionType='DISPOSAL' AND T.TransactionDate BETWEEN ? AND ?{org} ORDER BY T.TransactionDate""", [f, t, *oargs]):
        nbv = r2((r["Amount"] or 0) - r["AccumOut"])
        out.append(dict(Document=f"DSP-{r['TransactionID']:06d}", TransactionDate=r["TransactionDate"], AssetCode=r["AssetCode"], AssetName=r["AssetName"],
                        CategoryName=r["CategoryName"], BranchName=r["BranchName"], Cost=r2(r["Amount"]), AccumDep=r2(r["AccumOut"]), NBV=nbv,
                        Proceeds=r2(r["DisposalProceeds"]), GainLoss=r2((r["DisposalProceeds"] or 0) - nbv), DisposalReason=r["DisposalReason"]))
    return dict(columns=_cols(("Document", "Document", "text"), ("TransactionDate", "Date", "date"), ("AssetCode", "Asset", "text"), ("AssetName", "Name", "text"),
                              ("CategoryName", "Group", "text"), ("BranchName", "Branch", "text"), ("Cost", "Cost", "money"),
                              ("AccumDep", "Accum. dep. & impairment", "money"), ("NBV", "NBV at disposal", "money"), ("Proceeds", "Proceeds", "money"),
                              ("GainLoss", "Gain / (loss)", "money"), ("DisposalReason", "Reason", "text")),
                rows=out, totals=["Cost", "AccumDep", "NBV", "Proceeds", "GainLoss"], subtitle=f"{f if f > '1901' else 'Beginning'} to {t}")


def revaluations(con, p):
    """Capital additions, revaluations and impairments: how each changed the asset and where it was posted."""
    f = parse_date(p.get("from"), "From date") or "1900-01-01"
    t = parse_date(p.get("to"), "To date") or "2999-12-31"
    org, oargs = _org(p)
    data = rows(con, f"""SELECT {doc_no_sql('T.TransactionType', 'T.TransactionID')} AS Document, T.TransactionDate, T.TransactionType,
            A.AssetCode, A.AssetName, A.AssetNameAr, C.CategoryName, C.CategoryNameAr, T.Amount, T.PnlAmount, T.SurplusAmount, T.ReferenceNumber, T.Notes
            FROM tbl_AssetTransactions T JOIN tbl_Assets A ON A.AssetID=T.AssetID LEFT JOIN tbl_AssetCategories C ON C.CategoryID=A.CategoryID
            WHERE T.TransactionType IN ('ADDITION','IMPAIRMENT','REVALUATION') AND T.TransactionDate BETWEEN ? AND ?{org}
            ORDER BY T.TransactionDate, T.TransactionID""", [f, t, *oargs])
    for r in data:
        r["CostChange"] = r2(r["Amount"]) if r["TransactionType"] == "ADDITION" else 0.0
        r["ValueChange"] = 0.0 if r["TransactionType"] == "ADDITION" else r2(r["Amount"])
        r["PnlAmount"], r["SurplusAmount"] = r2(-(r["PnlAmount"] or 0)), r2(r["SurplusAmount"])
    return dict(columns=_cols(("Document", "Document", "text"), ("TransactionDate", "Date", "date"), ("TransactionType", "Type", "text"),
                              ("AssetCode", "Asset", "text"), ("AssetName", "Name", "text"), ("CategoryName", "Group", "text"),
                              ("CostChange", "Cost added", "money"), ("ValueChange", "Carrying amount change", "money"),
                              ("PnlAmount", "Profit / (loss)", "money"), ("SurplusAmount", "Revaluation surplus", "money"),
                              ("ReferenceNumber", "Reference", "text")),
                rows=data, totals=["CostChange", "ValueChange", "PnlAmount", "SurplusAmount"], subtitle=_span(f, t))


def transactions_report(con, p):
    f = parse_date(p.get("from"), "From date") or "1900-01-01"
    t = parse_date(p.get("to"), "To date") or "2999-12-31"
    org, oargs = _org(p)
    sql = f"""SELECT {doc_no_sql('T.TransactionType', 'T.TransactionID')} AS Document, T.TransactionDate, T.TransactionType, A.AssetCode, A.AssetName, A.AssetNameAr,
             T.Amount, T.DisposalProceeds, FL.LocationName FromLocation, FL.LocationNameAr FromLocationAr, TL.LocationName ToLocation, TL.LocationNameAr ToLocationAr,
             T.ReferenceNumber, T.Notes, T.CreatedBy
             FROM tbl_AssetTransactions T JOIN tbl_Assets A ON A.AssetID=T.AssetID
             LEFT JOIN tbl_Locations FL ON FL.LocationID=T.FromLocationID LEFT JOIN tbl_Locations TL ON TL.LocationID=T.ToLocationID
             WHERE T.TransactionDate BETWEEN ? AND ?{org}"""
    args = [f, t, *oargs]
    if p.get("type"):
        sql += " AND T.TransactionType=?"; args.append(p["type"])
    return dict(columns=_cols(("Document", "Document", "text"), ("TransactionDate", "Date", "date"), ("TransactionType", "Type", "text"), ("AssetCode", "Asset", "text"),
                              ("AssetName", "Name", "text"), ("Amount", "Amount", "money"), ("FromLocation", "From", "text"),
                              ("ToLocation", "To", "text"), ("ReferenceNumber", "Reference", "text"), ("Notes", "Notes", "text"),
                              ("CreatedBy", "User", "text")),
                rows=rows(con, sql + " ORDER BY T.TransactionDate, T.TransactionID", args), totals=[], subtitle=_span(f, t))


def fully_depreciated(con, p):
    d = _as_of(p)
    data = [a for a in asset_state(con, d, p) if a["Cost"] > 0 and a["NBV"] <= (a["ResidualValue"] or 0) + 0.005]
    return dict(columns=_cols(("AssetCode", "Asset", "text"), ("AssetName", "Name", "text"), ("CategoryName", "Group", "text"),
                              ("BranchName", "Branch", "text"), ("AcquisitionDate", "Acquired", "date"), ("Cost", "Cost", "money"),
                              ("AccumDep", "Accum. dep.", "money"), ("NBV", "Net book value", "money")),
                rows=data, totals=["Cost", "AccumDep", "NBV"], subtitle=f"As of {d}")


def warranty_expiry(con, p):
    days = to_int(p.get("days"), "Days", 90)
    if not 0 <= days <= 36500:
        raise ApiError("Days must be between 0 and 36500")
    org, oargs = _org(p)
    today = date.today()
    limit = date.fromordinal(today.toordinal() + days).isoformat()
    data = rows(con, f"""SELECT A.AssetCode, A.AssetName, A.AssetNameAr, C.CategoryName, C.CategoryNameAr, A.SupplierName, A.WarrantyExpiryDate
            FROM tbl_Assets A LEFT JOIN tbl_AssetCategories C ON C.CategoryID=A.CategoryID WHERE A.AssetStatus<>'Disposed' AND A.WarrantyExpiryDate IS NOT NULL
            AND A.WarrantyExpiryDate<=?{org} ORDER BY A.WarrantyExpiryDate""", [limit, *oargs])
    for r in data:
        r["DaysLeft"] = date.fromisoformat(r["WarrantyExpiryDate"][:10]).toordinal() - today.toordinal()
    return dict(columns=_cols(("AssetCode", "Asset", "text"), ("AssetName", "Name", "text"), ("CategoryName", "Group", "text"),
                              ("SupplierName", "Supplier", "text"), ("WarrantyExpiryDate", "Warranty expiry", "date"),
                              ("DaysLeft", "Days left", "int")), rows=data, totals=[], subtitle=f"Expiring within {days} days")


def _mdate(p, key, default):
    return parse_date(p.get(key), key.title() + " date") or default


_MDATE = "COALESCE(M.CompletionDate, M.StartDate, M.ScheduledDate)"


def maintenance_history(con, p):
    f, t = _mdate(p, "from", "1900-01-01"), _mdate(p, "to", "2999-12-31")
    sql = f"""SELECT M.MaintenanceNo, {_MDATE} AS EventDate, M.AssetID, A.AssetCode, A.AssetName, A.AssetNameAr, M.MaintenanceType, M.Title,
              M.Priority, M.Status, M.Vendor, M.Cost FROM tbl_Maintenance M JOIN tbl_Assets A ON A.AssetID=M.AssetID
              WHERE {_MDATE} BETWEEN ? AND ?{scope_sql('A')}"""
    args = [f, t]
    for key, col in (("mstatus", "M.Status"), ("mtype", "M.MaintenanceType"), ("category", "A.CategoryID")):
        if p.get(key):
            sql += f" AND {col}=?"
            args.append(p[key])
    data = rows(con, sql + " ORDER BY A.AssetCode, EventDate, M.MaintenanceID", args)
    for r in data:
        r["Asset"] = f"{r['AssetCode']} - {r['AssetName']}"
    return dict(columns=_cols(("MaintenanceNo", "Order", "text"), ("EventDate", "Date", "date"), ("MaintenanceType", "Type", "text"),
                              ("Title", "Title", "text"), ("Priority", "Priority", "text"), ("Status", "Status", "text"),
                              ("Vendor", "Vendor", "text"), ("Cost", "Cost", "money")),
                rows=data, group_by="Asset", totals=["Cost"],
                subtitle=f"{f if f > '1901' else 'Beginning'} to {t if t < '2999' else 'today'}")


def maintenance_cost(con, p):
    f, t = _mdate(p, "from", "1900-01-01"), _mdate(p, "to", "2999-12-31")
    gb = p.get("mgroup") or "asset"
    data = rows(con, """SELECT M.MaintenanceID, M.MaintenanceType, M.Cost, A.AssetCode, A.AssetName, A.AssetNameAr, C.CategoryName, C.CategoryNameAr
            FROM tbl_Maintenance M JOIN tbl_Assets A ON A.AssetID=M.AssetID LEFT JOIN tbl_AssetCategories C ON C.CategoryID=A.CategoryID
            WHERE M.Status='Completed' AND M.CompletionDate BETWEEN ? AND ?""" + scope_sql("A"), (f, t))
    agg: dict[str, dict] = {}
    for r in data:
        k = {"asset": f"{r['AssetCode']} - {r['AssetName']}", "category": r["CategoryName"] or "(none)", "type": r["MaintenanceType"]}.get(gb, r["AssetCode"])
        g = agg.setdefault(k, dict(k=k, Orders=0, Cost=0.0))
        g["Orders"] += 1
        g["Cost"] += r["Cost"] or 0
    out = []
    for g in sorted(agg.values(), key=lambda x: -x["Cost"]):
        out.append(dict(k=g["k"], Orders=g["Orders"], Cost=r2(g["Cost"]), Average=r2(g["Cost"] / g["Orders"])))
    label = {"asset": "Asset", "category": "Group", "type": "Type"}.get(gb, "Asset")
    return dict(columns=_cols(("k", label, "text"), ("Orders", "Completed orders", "int"), ("Cost", "Total cost", "money"), ("Average", "Average cost", "money")),
                rows=out, totals=["Orders", "Cost"], subtitle=f"{f if f > '1901' else 'Beginning'} to {t if t < '2999' else 'today'}")


def maintenance_schedule(con, p):
    days = to_int(p.get("days"), "Days", 30)
    if not 0 <= days <= 36500:
        raise ApiError("Days must be between 0 and 36500")
    today = date.today().isoformat()
    limit = date.fromordinal(date.today().toordinal() + days).isoformat()
    out = []
    for r in rows(con, """SELECT M.MaintenanceNo, M.ScheduledDate AS DueDate, A.AssetCode, A.AssetName, A.AssetNameAr, M.MaintenanceType, M.Title,
            M.Priority, M.Status FROM tbl_Maintenance M JOIN tbl_Assets A ON A.AssetID=M.AssetID
            WHERE M.Status IN ('Planned','In Progress') AND M.ScheduledDate<=?""" + scope_sql("A"), (limit,)):
        r["Source"] = "Open order"
        out.append(r)
    for r in rows(con, """SELECT M.MaintenanceNo, M.NextDueDate AS DueDate, A.AssetCode, A.AssetName, A.AssetNameAr, M.MaintenanceType, M.Title,
            M.Priority, 'Next due' AS Status FROM tbl_Maintenance M JOIN tbl_Assets A ON A.AssetID=M.AssetID
            WHERE M.Status='Completed' AND M.NextDueDate IS NOT NULL AND M.NextDueDate<=? AND A.AssetStatus<>'Disposed'
            AND NOT EXISTS (SELECT 1 FROM tbl_Maintenance N WHERE N.AssetID=M.AssetID AND N.Status IN ('Planned','In Progress'))
            AND M.MaintenanceID=(SELECT MAX(X.MaintenanceID) FROM tbl_Maintenance X WHERE X.AssetID=M.AssetID AND X.Status='Completed' AND X.NextDueDate IS NOT NULL)""" + scope_sql("A"), (limit,)):
        r["Source"] = "Recurring due date"
        out.append(r)
    for r in out:
        r["DaysToDue"] = date.fromisoformat(r["DueDate"]).toordinal() - date.today().toordinal()
        r["Timing"] = "Overdue" if r["DueDate"] < today else "Due"
    out.sort(key=lambda r: r["DueDate"])
    return dict(columns=_cols(("DueDate", "Due date", "date"), ("DaysToDue", "Days to due", "int"), ("Timing", "Timing", "text"),
                              ("AssetCode", "Asset", "text"), ("AssetName", "Name", "text"), ("MaintenanceType", "Type", "text"),
                              ("Title", "Title", "text"), ("Priority", "Priority", "text"), ("Status", "Status", "text"),
                              ("Source", "Source", "text"), ("MaintenanceNo", "Order", "text")),
                rows=out, totals=[], subtitle=f"Due within {days} days")


def suppliers_directory(con, p):
    sql, args = "SELECT * FROM tbl_Suppliers WHERE 1=1", []
    if p.get("sactive") in ("1", "0"):
        sql += " AND IsActive=?"
        args.append(to_int(p["sactive"], "Status"))
    if p.get("stype"):
        sql += " AND SupplierType=?"
        args.append(p["stype"])
    data = rows(con, sql + " ORDER BY SupplierName", args)
    for r in data:
        r["Status"] = "Active" if r["IsActive"] else "Inactive"
    return dict(columns=_cols(("SupplierCode", "Code", "text"), ("SupplierName", "Name", "text"), ("SupplierType", "Type", "text"),
                              ("ContactPerson", "Contact person", "text"), ("Phone", "Phone", "text"), ("Mobile", "Mobile", "text"),
                              ("Email", "Email", "text"), ("City", "City", "text"), ("Country", "Country", "text"),
                              ("TaxNumber", "Tax number", "text"), ("PaymentTerms", "Payment terms", "text"), ("Status", "Status", "text")),
                rows=data, totals=[], subtitle=f"{len(data)} suppliers")


def supplier_purchases(con, p):
    f, t = _mdate(p, "from", "1900-01-01"), _mdate(p, "to", "2999-12-31")
    sql = """SELECT S.SupplierID, S.SupplierCode, S.SupplierName, S.SupplierNameAr, A.AssetCode, A.AssetName, A.AssetNameAr, C.CategoryName, C.CategoryNameAr,
             A.AcquisitionDate, A.InvoiceNumber, A.PurchaseOrderNumber, A.AcquisitionCost
             FROM tbl_Assets A JOIN tbl_Suppliers S ON S.SupplierID=A.SupplierID LEFT JOIN tbl_AssetCategories C ON C.CategoryID=A.CategoryID
             WHERE A.AcquisitionDate BETWEEN ? AND ?""" + scope_sql("A")
    args = [f, t]
    if p.get("supplier"):
        sql += " AND S.SupplierID=?"
        args.append(p["supplier"])
    data = rows(con, sql + " ORDER BY S.SupplierName, A.AcquisitionDate", args)
    for r in data:
        r["Supplier"] = f"{r['SupplierCode']} - {r['SupplierName']}"
    return dict(columns=_cols(("AcquisitionDate", "Date", "date"), ("AssetCode", "Asset", "text"), ("AssetName", "Name", "text"),
                              ("CategoryName", "Group", "text"), ("InvoiceNumber", "Invoice", "text"), ("PurchaseOrderNumber", "Purchase order", "text"),
                              ("AcquisitionCost", "Cost", "money")),
                rows=data, group_by="Supplier", totals=["AcquisitionCost"],
                subtitle=f"{f if f > '1901' else 'Beginning'} to {t if t < '2999' else 'today'}")


def supplier_summary(con, p):
    f, t = _mdate(p, "from", "1900-01-01"), _mdate(p, "to", "2999-12-31")
    data = rows(con, """SELECT S.SupplierCode, S.SupplierName, S.SupplierNameAr, S.SupplierType,
        (SELECT COUNT(*) FROM tbl_Assets A WHERE A.SupplierID=S.SupplierID AND A.AcquisitionDate BETWEEN ? AND ?) AS Assets,
        (SELECT COALESCE(SUM(A.AcquisitionCost),0) FROM tbl_Assets A WHERE A.SupplierID=S.SupplierID AND A.AcquisitionDate BETWEEN ? AND ?) AS Purchases,
        (SELECT COUNT(*) FROM tbl_Maintenance M WHERE M.SupplierID=S.SupplierID AND M.Status='Completed' AND M.CompletionDate BETWEEN ? AND ?) AS Orders,
        (SELECT COALESCE(SUM(M.Cost),0) FROM tbl_Maintenance M WHERE M.SupplierID=S.SupplierID AND M.Status='Completed' AND M.CompletionDate BETWEEN ? AND ?) AS MaintCost
        FROM tbl_Suppliers S ORDER BY S.SupplierName""", (f, t) * 4)
    data = [r for r in data if r["Assets"] or r["Orders"]]
    for r in data:
        r["Purchases"], r["MaintCost"] = r2(r["Purchases"]), r2(r["MaintCost"])
        r["Total"] = r2(r["Purchases"] + r["MaintCost"])
    data.sort(key=lambda r: -r["Total"])
    return dict(columns=_cols(("SupplierCode", "Code", "text"), ("SupplierName", "Supplier", "text"), ("SupplierType", "Type", "text"),
                              ("Assets", "Assets purchased", "int"), ("Purchases", "Purchases", "money"), ("Orders", "Maintenance orders", "int"),
                              ("MaintCost", "Maintenance cost", "money"), ("Total", "Total spend", "money")),
                rows=data, totals=["Assets", "Purchases", "Orders", "MaintCost", "Total"],
                subtitle=f"{f if f > '1901' else 'Beginning'} to {t if t < '2999' else 'today'}")


def vat_purchases(con, p):
    f, t = _mdate(p, "from", "1900-01-01"), _mdate(p, "to", "2999-12-31")
    sql = """SELECT A.AssetCode, A.AssetName, A.AssetNameAr, A.AcquisitionDate, A.InvoiceNumber, A.SupplierName, SP.SupplierNameAr, A.VatApplicable,
             A.VatInclusive, A.VatRate, A.PurchaseAmount, A.AcquisitionCost, A.VatAmount FROM tbl_Assets A
             LEFT JOIN tbl_Suppliers SP ON SP.SupplierID=A.SupplierID WHERE A.AcquisitionDate BETWEEN ? AND ?"""
    org, oargs = _org(p)
    sql += org
    args = [f, t, *oargs]
    if p.get("vat") in ("1", "0"):
        sql += " AND A.VatApplicable=?"
        args.append(to_int(p["vat"], "VAT status"))
    data = rows(con, sql + " ORDER BY A.AcquisitionDate, A.AssetCode", args)
    for r in data:
        r["VatStatus"] = "With VAT" if r["VatApplicable"] else "No VAT"
        r["Basis"] = ("Inclusive" if r["VatInclusive"] else "Exclusive") if r["VatApplicable"] else ""
        r["Gross"] = r2((r["AcquisitionCost"] or 0) + (r["VatAmount"] or 0))
    return dict(columns=_cols(("AcquisitionDate", "Date", "date"), ("AssetCode", "Asset", "text"), ("AssetName", "Name", "text"),
                              ("SupplierName", "Supplier", "text"), ("InvoiceNumber", "Invoice", "text"), ("VatStatus", "VAT", "text"),
                              ("Basis", "Invoice basis", "text"), ("VatRate", "VAT rate", "pct"), ("AcquisitionCost", "Net cost", "money"),
                              ("VatAmount", "VAT amount", "money"), ("Gross", "Total with VAT", "money")),
                rows=data, totals=["AcquisitionCost", "VatAmount", "Gross"],
                subtitle=f"{f if f > '1901' else 'Beginning'} to {t if t < '2999' else 'today'}")


def custody_by_employee(con, p):
    f, t = _mdate(p, "from", "1900-01-01"), _mdate(p, "to", "2999-12-31")
    sql = """SELECT U.CustodyNo, U.IssueDate, U.ReturnDate, U.Status, U.ConditionOnIssue, U.ConditionOnReturn, U.AssetID, A.AssetCode, A.AssetName, A.AssetNameAr,
             A.SerialNumber, C.CategoryName, C.CategoryNameAr, E.EmployeeCode, E.EmployeeName, E.EmployeeNameAr, E.Department
             FROM tbl_AssetCustody U JOIN tbl_Assets A ON A.AssetID=U.AssetID JOIN tbl_Employees E ON E.EmployeeID=U.EmployeeID
             LEFT JOIN tbl_AssetCategories C ON C.CategoryID=A.CategoryID WHERE U.IssueDate BETWEEN ? AND ?""" + scope_sql("A")
    args = [f, t]
    if p.get("employee"):
        sql += " AND U.EmployeeID=?"
        args.append(p["employee"])
    if p.get("cstatus") in ("Issued", "Returned"):
        sql += " AND U.Status=?"
        args.append(p["cstatus"])
    data = rows(con, sql + " ORDER BY E.EmployeeName, U.IssueDate", args)
    for r in data:
        r["Employee"] = f"{r['EmployeeCode']} - {r['EmployeeName']}" + (f" ({r['Department']})" if r["Department"] else "")
    return dict(columns=_cols(("CustodyNo", "Custody", "text"), ("AssetCode", "Asset", "text"), ("AssetName", "Name", "text"), ("CategoryName", "Group", "text"),
                              ("SerialNumber", "Serial number", "text"), ("IssueDate", "Issued", "date"), ("ReturnDate", "Returned", "date"),
                              ("Status", "Status", "text"), ("ConditionOnIssue", "Condition on issue", "text")),
                rows=data, group_by="Employee", totals=[], subtitle=f"{f if f > '1901' else 'Beginning'} to {t if t < '2999' else 'today'}")


def employees_directory(con, p):
    sql, args = "SELECT * FROM tbl_Employees WHERE 1=1", []
    if p.get("sactive") in ("1", "0"):
        sql += " AND IsActive=?"
        args.append(to_int(p["sactive"], "Status"))
    data = rows(con, sql + " ORDER BY EmployeeName", args)
    for r in data:
        r["Status"] = "Active" if r["IsActive"] else "Inactive"
        r["Held"] = con.execute("SELECT COUNT(*) FROM tbl_AssetCustody WHERE EmployeeID=? AND Status='Issued'", (r["EmployeeID"],)).fetchone()[0]
    return dict(columns=_cols(("EmployeeCode", "Code", "text"), ("EmployeeName", "Name", "text"), ("JobTitle", "Job title", "text"), ("Department", "Department", "text"),
                              ("Mobile", "Mobile", "text"), ("Email", "Email", "text"), ("Held", "Assets held", "int"), ("Status", "Status", "text")),
                rows=data, totals=["Held"], subtitle=f"{len(data)} employees")


BUILDERS = {"custody-by-employee": custody_by_employee, "employees-directory": employees_directory,
            "vat-purchases": vat_purchases,
            "suppliers-directory": suppliers_directory, "supplier-purchases": supplier_purchases, "supplier-summary": supplier_summary,
            "maintenance-history": maintenance_history, "maintenance-cost": maintenance_cost, "maintenance-schedule": maintenance_schedule,
            "asset-register": asset_register, "asset-summary": asset_summary, "rollforward": rollforward,
            "depreciation-schedule": depreciation_schedule, "depreciation-journal": depreciation_journal, "depreciation-forecast": depreciation_forecast,
            "gl-balances": gl_balances, "disposals": disposals, "transactions": transactions_report, "revaluations": revaluations,
            "fully-depreciated": fully_depreciated, "warranty-expiry": warranty_expiry}


def run_report(con, report_id: str, params: dict) -> dict:
    fn = BUILDERS.get(report_id)
    if not fn:
        raise ApiError("Unknown report", 404)
    res = fn(con, params)
    # send only what the report shows (builders select whole rows: national IDs, IBANs ... must not leak)
    keep = {c["key"] for c in res["columns"]} | ({res["group_by"]} if res.get("group_by") else set()) | set((res.get("order") or {}).values())
    res["rows"] = [{k: r.get(k) for k in keep} for r in res["rows"]]
    res.update(id=report_id, params=params, company=get_settings(con).get("CompanyName", ""),
               currency=get_settings(con).get("DefaultCurrency", ""), generated=date.today().isoformat())
    return res
