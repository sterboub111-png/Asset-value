"""Depreciation: the monthly charge, the proposal for a period, running and posting it.

One rule computes a month's depreciation (`monthly_charge`); the proposal, the forecast report and the tests all use it.

  SL    straight line: (cost - residual) / life in months. After a capital addition or a revaluation / impairment the
        remaining amount (carrying amount - residual) is spread over the remaining life (IAS 16.50, IAS 36.63).
  DB    declining balance, switching to straight line: a year's charge is the rate x the carrying amount at the start of
        the fiscal year, spread evenly over its months; once straight line over the remaining life gives more, that is
        charged instead, so the asset reaches its residual value at the end of its life.
  NONE  no depreciation (land, assets under construction).

The month that reaches the residual value takes the exact remainder, so rounding never leaves a stray cent.
The proposal reads the whole book in a handful of grouped queries, so a period with tens of thousands of assets is
proposed and posted in seconds.
"""
from __future__ import annotations

from bisect import bisect_left

from .. import db
from .book import VALUE_IN
from .common import ApiError, actor, audit, now, one, r2, rows, scope_sql

DEPRECIATING = ("SL", "DB")


def _month_index(d: str) -> int:
    return int(d[:4]) * 12 + int(d[5:7])


def _start(a: dict) -> str:
    return a["DepreciationStartDate"] or a["InServiceDate"] or a["AcquisitionDate"]


def monthly_charge(method: str, life_years: float, rate: float | None, cost: float, residual: float, accum: float,
                   value_adj: float, elapsed: int, fy_dep: float, adjusted: bool) -> float:
    """Depreciation for one month.
    accum: accumulated depreciation before this month; value_adj: revaluations - impairments to date;
    elapsed: months already gone since the depreciation start (0 in the first month); fy_dep: depreciation charged
    earlier in the same fiscal year (declining balance only); adjusted: the asset has had an addition or a value change."""
    months = life_years * 12
    carrying = cost - accum + value_adj
    remaining = carrying - residual
    if remaining <= 0.004 or months <= 0:
        return 0.0
    left = months - elapsed                                   # months of life still to go, this one included
    over_rest = remaining / left if left >= 1 else remaining  # straight line over what is left of the life
    if method == "DB":
        amount = max((carrying + fy_dep) * (rate or 0) / 100 / 12, over_rest)
    elif adjusted:
        amount = over_rest
    else:
        amount = (cost - residual) / months
    amount = r2(max(0.0, min(amount, remaining)))
    if amount > 0 and remaining - amount < min(months * 0.005, amount * 0.5) + 1e-9:
        amount = r2(remaining)
    return amount


def _fully_depreciated(con, asset: dict) -> bool:
    """The carrying amount (cost + additions - accumulated + value adjustments) has come down to the residual value."""
    from .book import values
    v = values(con, asset["AssetID"])
    return v["nbv"] <= v["residual"] + 0.005


def _periods(con) -> list[dict]:
    return rows(con, "SELECT PeriodID, FiscalYear, PeriodName, StartDate, EndDate FROM tbl_DepreciationPeriods ORDER BY StartDate", raw=True)


def _first_missing(con, asset_id: int, start: str, before: str) -> str | None:
    r = one(con, """SELECT P.PeriodName FROM tbl_DepreciationPeriods P WHERE P.EndDate>=? AND P.StartDate<? AND NOT EXISTS (
        SELECT 1 FROM tbl_Depreciation D WHERE D.AssetID=? AND D.PeriodID=P.PeriodID AND D.PostingStatus='POSTED')
        ORDER BY P.StartDate LIMIT 1""", (start, before, asset_id))
    return r["PeriodName"] if r else None


def _sequence_ok(con, asset: dict, period: dict) -> str | None:
    """The first earlier period (from the depreciation start) still without posted depreciation for this asset, if any."""
    if asset["DisposalDate"] or _fully_depreciated(con, asset):
        return None   # nothing left to depreciate, so skipped months do not block anything
    return _first_missing(con, asset["AssetID"], _start(asset), period["StartDate"])


def propose(con, period_id: int) -> list[dict]:
    """Compute (but do not store) depreciation for every eligible asset in a period."""
    p = one(con, "SELECT * FROM tbl_DepreciationPeriods WHERE PeriodID=?", (period_id,))
    if not p:
        raise ApiError("Period not found", 404)
    ps, pe = p["StartDate"], p["EndDate"]
    periods = _periods(con)
    first = periods[0]["StartDate"] if periods else None
    ends = [x["EndDate"] for x in periods]
    n_before = sum(1 for x in periods if x["StartDate"] < ps)
    sc = scope_sql("A")
    # the whole book in grouped queries: posted depreciation, this period's lines, additions and value adjustments
    posted = {r["AssetID"]: r for r in rows(con, f"""
        SELECT D.AssetID, COUNT(*) n,
          SUM(CASE WHEN P.StartDate<? THEN D.PeriodDepreciation ELSE 0 END) before,
          SUM(D.PeriodDepreciation) total,
          SUM(CASE WHEN P.StartDate<? AND P.FiscalYear=? THEN D.PeriodDepreciation ELSE 0 END) fy,
          SUM(CASE WHEN P.StartDate<? AND P.EndDate>=COALESCE(A.DepreciationStartDate,A.InServiceDate,A.AcquisitionDate) THEN 1 ELSE 0 END) in_range
        FROM tbl_Depreciation D JOIN tbl_DepreciationPeriods P ON P.PeriodID=D.PeriodID JOIN tbl_Assets A ON A.AssetID=D.AssetID
        WHERE D.PostingStatus='POSTED'{sc} GROUP BY D.AssetID""", (ps, ps, p["FiscalYear"], ps), raw=True)}
    existing = {r["AssetID"]: r for r in rows(con, "SELECT * FROM tbl_Depreciation WHERE PeriodID=?", (period_id,), raw=True)}
    adj_upto = {r["AssetID"]: r for r in rows(con, f"""SELECT AssetID,
        COALESCE(SUM(CASE WHEN TransactionType='ADDITION' THEN Amount END),0) additions,
        COALESCE(SUM(CASE WHEN TransactionType IN {VALUE_IN} THEN Amount END),0) value_adj
        FROM tbl_AssetTransactions WHERE TransactionType IN ('ADDITION','IMPAIRMENT','REVALUATION') AND TransactionDate<=?
        GROUP BY AssetID""", (pe,), raw=True)}
    adj_all = {r["AssetID"]: r for r in rows(con, f"""SELECT AssetID,
        COALESCE(SUM(CASE WHEN TransactionType='ADDITION' THEN Amount END),0) additions,
        COALESCE(SUM(CASE WHEN TransactionType IN {VALUE_IN} THEN Amount END),0) value_adj
        FROM tbl_AssetTransactions WHERE TransactionType IN ('ADDITION','IMPAIRMENT','REVALUATION') GROUP BY AssetID""", raw=True)}
    out = []
    for a in rows(con, f"""SELECT A.AssetID, A.AssetCode, A.AssetName, A.AssetNameAr, A.CategoryID, C.CategoryName, C.CategoryNameAr,
            A.AcquisitionCost, A.ResidualValue, A.UsefulLifeYears, A.DepreciationRate, A.OpeningAccumDep, A.DepreciationStartDate,
            A.InServiceDate, A.AcquisitionDate, A.DisposalDate, M.MethodCode
            FROM tbl_Assets A LEFT JOIN tbl_AssetCategories C ON C.CategoryID=A.CategoryID LEFT JOIN tbl_DepreciationMethods M ON M.MethodID=A.MethodID
            WHERE A.IsActive=1 AND A.AssetStatus<>'Disposed'{sc} ORDER BY A.AssetCode"""):
        aid = a["AssetID"]
        up = adj_upto.get(aid) or {"additions": 0, "value_adj": 0}
        cost = (a["AcquisitionCost"] or 0) + up["additions"]
        line = {"AssetID": aid, "AssetCode": a["AssetCode"], "AssetName": a["AssetName"], "CategoryName": a["CategoryName"],
                "AcquisitionCost": r2(cost), "ResidualValue": a["ResidualValue"], "Method": a["MethodCode"], "eligible": False, "reason": ""}
        start = _start(a)
        pst = posted.get(aid) or {"n": 0, "before": 0, "total": 0, "fy": 0, "in_range": 0}
        ex = existing.get(aid)
        if a["MethodCode"] not in DEPRECIATING:
            line["reason"] = "Method: no depreciation"
        elif not a["UsefulLifeYears"]:
            line["reason"] = "Missing useful life"
        elif _month_index(start) > _month_index(ps):
            line["reason"] = "Not yet in depreciation"
        elif a["DisposalDate"]:
            line["reason"] = "Disposed"
        elif ex and ex["PostingStatus"] == "POSTED":
            line.update(reason="Already posted", status="POSTED", PeriodDepreciation=ex["PeriodDepreciation"],
                        OpeningAccumDep=ex["OpeningAccumDep"], ClosingAccumDep=ex["ClosingAccumDep"], ClosingNBV=ex["ClosingNBV"])
        elif not (a["OpeningAccumDep"] or 0) and first and _month_index(start) < _month_index(first) and not pst["n"]:
            # months before the first period cannot be proposed, so they must come in as opening accumulated depreciation
            line["reason"] = "Started before the first period: enter the opening accumulated depreciation"
        else:
            opening = (a["OpeningAccumDep"] or 0) + pst["before"]
            # every period from the depreciation start up to this one must be posted first, unless nothing is left
            expected = n_before - bisect_left(ends, start)
            allv = adj_all.get(aid) or {"additions": 0, "value_adj": 0}
            done = (a["AcquisitionCost"] or 0) + allv["additions"] - (a["OpeningAccumDep"] or 0) - pst["total"] + allv["value_adj"] \
                <= (a["ResidualValue"] or 0) + 0.005
            prior = _first_missing(con, aid, start, ps) if pst["in_range"] < expected and not done else None
            if prior:
                line["reason"] = f"{prior} must be posted first"
            else:
                amount = monthly_charge(a["MethodCode"], a["UsefulLifeYears"], a["DepreciationRate"], cost, a["ResidualValue"] or 0,
                                        opening, up["value_adj"], _month_index(ps) - _month_index(start), pst["fy"], aid in adj_upto)
                if amount <= 0:
                    line["reason"] = "Fully depreciated"
                else:
                    line.update(eligible=True, reason="", status="DRAFT" if ex else "NEW",
                                DepreciableAmount=r2(cost - (a["ResidualValue"] or 0)), UsefulLifeYears=a["UsefulLifeYears"],
                                DepreciationRate=a["DepreciationRate"], OpeningAccumDep=r2(opening),
                                OpeningNBV=r2(cost - opening + up["value_adj"]), PeriodDepreciation=amount,
                                ClosingAccumDep=r2(opening + amount), ClosingNBV=r2(cost - opening - amount + up["value_adj"]))
        out.append(line)
    return out


def suggest_period(con) -> dict:
    """Earliest open period that still has something to depreciate or post."""
    for p in rows(con, "SELECT PeriodID FROM tbl_DepreciationPeriods WHERE PeriodStatus='OPEN' ORDER BY StartDate"):
        if any(l["eligible"] for l in propose(con, p["PeriodID"])):
            return {"period_id": p["PeriodID"]}
    return {"period_id": None}


def run_depreciation(con, period_id: int, asset_ids: list[int] | None = None) -> dict:
    p = one(con, "SELECT * FROM tbl_DepreciationPeriods WHERE PeriodID=?", (period_id,))
    if not p:
        raise ApiError("Period not found", 404)
    if p["PeriodStatus"] != "OPEN":
        raise ApiError("The period is closed")
    wanted = set(asset_ids or [])
    lines = [ln for ln in propose(con, period_id) if ln["eligible"] and (not wanted or ln["AssetID"] in wanted)]
    ts, who = now(), actor()
    if wanted:
        con.executemany("DELETE FROM tbl_Depreciation WHERE AssetID=? AND PeriodID=? AND PostingStatus='DRAFT'", [(ln["AssetID"], period_id) for ln in lines])
    else:   # the whole period in scope is proposed again
        con.execute(f"""DELETE FROM tbl_Depreciation WHERE PeriodID=? AND PostingStatus='DRAFT'
            AND AssetID IN (SELECT A.AssetID FROM tbl_Assets A WHERE 1=1{scope_sql('A')})""", (period_id,))
    db.bulk_insert(con, "tbl_Depreciation", ["AssetID", "PeriodID", "AcquisitionCost", "ResidualValue", "DepreciableAmount", "UsefulLifeYears",
                                             "DepreciationRate", "OpeningAccumDep", "OpeningNBV", "PeriodDepreciation", "ClosingAccumDep", "ClosingNBV",
                                             "PostingStatus", "CreatedAt", "CreatedBy"],
                   [(ln["AssetID"], period_id, ln["AcquisitionCost"], ln["ResidualValue"], ln["DepreciableAmount"],
                     ln["UsefulLifeYears"], ln["DepreciationRate"], ln["OpeningAccumDep"], ln["OpeningNBV"],
                     ln["PeriodDepreciation"], ln["ClosingAccumDep"], ln["ClosingNBV"], "DRAFT", ts, who) for ln in lines])
    audit(con, "RUN", "tbl_Depreciation", period_id, f"{p['PeriodName']}: {len(lines)} lines proposed")
    con.commit()
    return {"created": len(lines)}


def draft_lines(con, period_id: int) -> list[dict]:
    return rows(con, f"""
        SELECT D.*, A.AssetCode, A.AssetName, A.AssetNameAr, C.CategoryName, C.CategoryNameAr FROM tbl_Depreciation D
        JOIN tbl_Assets A ON A.AssetID=D.AssetID LEFT JOIN tbl_AssetCategories C ON C.CategoryID=A.CategoryID
        WHERE D.PeriodID=?{scope_sql('A')} ORDER BY A.AssetCode""", (period_id,))


def discard_drafts(con, period_id: int) -> dict:
    n = con.execute(f"""DELETE FROM tbl_Depreciation WHERE PeriodID=? AND PostingStatus='DRAFT'
        AND AssetID IN (SELECT A.AssetID FROM tbl_Assets A WHERE 1=1{scope_sql('A')})""", (period_id,)).rowcount
    audit(con, "DISCARD", "tbl_Depreciation", period_id, f"{n} draft lines removed")
    con.commit()
    return {"deleted": n}


def post_depreciation(con, period_id: int) -> dict:
    p = one(con, "SELECT * FROM tbl_DepreciationPeriods WHERE PeriodID=?", (period_id,))
    if not p:
        raise ApiError("Period not found", 404)
    if p["PeriodStatus"] != "OPEN":
        raise ApiError("The period is closed")
    drafts = rows(con, f"""SELECT D.*, A.AssetCode, A.AssetName, A.AssetStatus, C.DepExpenseAccountID, C.AccumDepAccountID
        FROM tbl_Depreciation D JOIN tbl_Assets A ON A.AssetID=D.AssetID
        JOIN tbl_AssetCategories C ON C.CategoryID=A.CategoryID WHERE D.PeriodID=? AND D.PostingStatus='DRAFT'{scope_sql('A')}""", (period_id,), raw=True)
    if not drafts:
        raise ApiError("There are no unposted depreciation lines for this period")
    # a draft is posted only while it still equals what the rules give now (eligible also means earlier months are posted)
    fresh = {l["AssetID"]: l for l in propose(con, period_id) if l["eligible"]}
    for d in drafts:
        e = fresh.get(d["AssetID"])
        if not e or abs(e["PeriodDepreciation"] - d["PeriodDepreciation"]) > 0.005 or abs(e["OpeningAccumDep"] - d["OpeningAccumDep"]) > 0.005:
            raise ApiError("The proposal is out of date. Discard it and create it again.")
        if not d["DepExpenseAccountID"] or not d["AccumDepAccountID"]:
            raise ApiError(f"Asset group of {d['AssetCode']} has no depreciation accounts configured")
        if d["AssetStatus"] == "Disposed":
            raise ApiError(f"{d['AssetCode']} is disposed")
    ts, who = now(), actor()
    journal = []
    for d in drafts:
        desc = f"Depreciation - {d['AssetCode']} - {d['AssetName']} - {p['PeriodName']}"
        for acc, dr, cr in ((d["DepExpenseAccountID"], d["PeriodDepreciation"], 0), (d["AccumDepAccountID"], 0, d["PeriodDepreciation"])):
            journal.append((d["DepreciationID"], d["AssetID"], period_id, p["EndDate"], acc, dr, cr, d["AssetCode"], desc, ts, who, ts))
    db.bulk_insert(con, "tbl_DepreciationJournal", ["DepreciationID", "AssetID", "PeriodID", "JournalDate", "GLAccountID", "DebitAmount", "CreditAmount",
                                                    "JournalType", "Reference", "Description", "PostingStatus", "PostedAt", "PostedBy", "CreatedAt"],
                   [(*j[:7], "DEPRECIATION", j[7], j[8], "POSTED", *j[9:]) for j in journal])
    # one statement for the whole run: the drafts checked above are exactly the period's drafts in scope
    con.execute(f"""UPDATE tbl_Depreciation SET PostingStatus='POSTED',PostedAt=?,PostedBy=? WHERE PeriodID=? AND PostingStatus='DRAFT'
        AND AssetID IN (SELECT A.AssetID FROM tbl_Assets A WHERE 1=1{scope_sql('A')})""", (ts, who, period_id))
    total = sum(d["PeriodDepreciation"] for d in drafts)
    audit(con, "POST", "tbl_Depreciation", period_id, f"{p['PeriodName']}: {len(drafts)} lines, {r2(total)}")
    con.commit()
    return {"posted": len(drafts), "total": r2(total)}
