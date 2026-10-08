"""Depreciation: propose, run and post."""
from __future__ import annotations

from .assets import BOOK_SQL
from .common import ApiError, actor, audit, now, one, r2, rows

# ---------------------------------------------------------------- depreciation
def _month_index(d: str) -> int:
    return int(d[:4]) * 12 + int(d[5:7])


def _fully_depreciated(con, asset: dict) -> bool:
    """Accumulated depreciation (opening + posted) has reached cost less residual."""
    posted = con.execute("SELECT COALESCE(SUM(PeriodDepreciation),0) FROM tbl_Depreciation WHERE AssetID=? AND PostingStatus='POSTED'", (asset["AssetID"],)).fetchone()[0]
    base = (asset["AcquisitionCost"] or 0) - (asset["ResidualValue"] or 0)
    return (asset["OpeningAccumDep"] or 0) + posted >= base - 0.005


def _sequence_ok(con, asset: dict, period: dict) -> str | None:
    """All earlier existing periods (from depreciation start) must be POSTED for this asset."""
    start = asset["DepreciationStartDate"] or asset["InServiceDate"] or asset["AcquisitionDate"]
    missing = rows(con, """
        SELECT P.PeriodName FROM tbl_DepreciationPeriods P
        WHERE P.EndDate>=? AND P.StartDate<? AND NOT EXISTS (
          SELECT 1 FROM tbl_Depreciation D WHERE D.AssetID=? AND D.PeriodID=P.PeriodID AND D.PostingStatus='POSTED')
        ORDER BY P.StartDate""", (start, period["StartDate"], asset["AssetID"]))
    if asset["DisposalDate"] or _fully_depreciated(con, asset):
        return None  # nothing left to depreciate, so skipped months do not block anything
    return missing[0]["PeriodName"] if missing else None


def propose(con, period_id: int) -> list[dict]:
    """Compute (but do not store) depreciation for every eligible asset in a period."""
    p = one(con, "SELECT * FROM tbl_DepreciationPeriods WHERE PeriodID=?", (period_id,))
    if not p:
        raise ApiError("Period not found", 404)
    out = []
    for a in rows(con, BOOK_SQL + " WHERE A.IsActive=1 AND A.AssetStatus<>'Disposed' ORDER BY A.AssetCode"):
        line = {"AssetID": a["AssetID"], "AssetCode": a["AssetCode"], "AssetName": a["AssetName"],
                "CategoryName": a["CategoryName"], "AcquisitionCost": a["AcquisitionCost"],
                "ResidualValue": a["ResidualValue"], "eligible": False, "reason": ""}
        start = a["DepreciationStartDate"] or a["InServiceDate"] or a["AcquisitionDate"]
        if a["MethodCode"] != "SL":
            line["reason"] = "Method: no depreciation"
        elif not a["UsefulLifeYears"]:
            line["reason"] = "Missing useful life"
        elif _month_index(start) > _month_index(p["StartDate"]):
            line["reason"] = "Not yet in depreciation"
        elif a["DisposalDate"]:
            line["reason"] = "Disposed"
        else:
            existing = one(con, "SELECT * FROM tbl_Depreciation WHERE AssetID=? AND PeriodID=?", (a["AssetID"], period_id))
            first = one(con, "SELECT MIN(StartDate) s FROM tbl_DepreciationPeriods", raw=True)["s"]
            # months before the first period cannot be proposed, so they must come in as opening accumulated depreciation
            missing_opening = (not (a["OpeningAccumDep"] or 0) and first and _month_index(start) < _month_index(first)
                               and not one(con, "SELECT 1 x FROM tbl_Depreciation WHERE AssetID=? AND PostingStatus='POSTED' LIMIT 1", (a["AssetID"],)))
            if existing and existing["PostingStatus"] == "POSTED":
                line.update(reason="Already posted", status="POSTED", PeriodDepreciation=existing["PeriodDepreciation"],
                            OpeningAccumDep=existing["OpeningAccumDep"], ClosingAccumDep=existing["ClosingAccumDep"],
                            ClosingNBV=existing["ClosingNBV"])
            elif missing_opening:
                line["reason"] = "Started before the first period: enter the opening accumulated depreciation"
            else:
                prior = _sequence_ok(con, a, p)
                if prior:
                    line["reason"] = f"{prior} must be posted first"
                else:
                    last = one(con, """SELECT D.ClosingAccumDep FROM tbl_Depreciation D
                                       JOIN tbl_DepreciationPeriods P2 ON P2.PeriodID=D.PeriodID
                                       WHERE D.AssetID=? AND D.PostingStatus='POSTED' AND P2.StartDate<?
                                       ORDER BY P2.StartDate DESC LIMIT 1""", (a["AssetID"], p["StartDate"]))
                    opening = last["ClosingAccumDep"] if last else (a["OpeningAccumDep"] or 0)
                    base = (a["AcquisitionCost"] or 0) - (a["ResidualValue"] or 0)
                    months = a["UsefulLifeYears"] * 12
                    monthly = base / months
                    remaining = base - opening
                    amount = r2(max(0, min(monthly, remaining)))
                    # the final month takes the exact remainder, so rounding never leaves a stray cent (or an extra month)
                    if amount > 0 and remaining - amount < min(months * 0.005, amount * 0.5) + 1e-9:
                        amount = r2(remaining)
                    if amount <= 0:
                        line["reason"] = "Fully depreciated"
                    else:
                        line.update(eligible=True, reason="", status="DRAFT" if existing else "NEW",
                                    DepreciableAmount=base, UsefulLifeYears=a["UsefulLifeYears"],
                                    DepreciationRate=a["DepreciationRate"], OpeningAccumDep=r2(opening),
                                    OpeningNBV=r2(a["AcquisitionCost"] - opening), PeriodDepreciation=amount,
                                    ClosingAccumDep=r2(opening + amount),
                                    ClosingNBV=r2(a["AcquisitionCost"] - opening - amount))
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
    created = 0
    for ln in propose(con, period_id):
        if not ln["eligible"] or (asset_ids and ln["AssetID"] not in asset_ids):
            continue
        con.execute("DELETE FROM tbl_Depreciation WHERE AssetID=? AND PeriodID=? AND PostingStatus='DRAFT'",
                    (ln["AssetID"], period_id))
        con.execute("""INSERT INTO tbl_Depreciation(AssetID,PeriodID,AcquisitionCost,ResidualValue,DepreciableAmount,
            UsefulLifeYears,DepreciationRate,OpeningAccumDep,OpeningNBV,PeriodDepreciation,ClosingAccumDep,ClosingNBV,
            PostingStatus,CreatedAt,CreatedBy) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,'DRAFT',?,?)""",
                    (ln["AssetID"], period_id, ln["AcquisitionCost"], ln["ResidualValue"], ln["DepreciableAmount"],
                     ln["UsefulLifeYears"], ln["DepreciationRate"], ln["OpeningAccumDep"], ln["OpeningNBV"],
                     ln["PeriodDepreciation"], ln["ClosingAccumDep"], ln["ClosingNBV"], now(), actor()))
        created += 1
    audit(con, "RUN", "tbl_Depreciation", period_id, f"{p['PeriodName']}: {created} lines proposed")
    con.commit()
    return {"created": created}


def draft_lines(con, period_id: int) -> list[dict]:
    return rows(con, """
        SELECT D.*, A.AssetCode, A.AssetName, A.AssetNameAr, C.CategoryName, C.CategoryNameAr FROM tbl_Depreciation D
        JOIN tbl_Assets A ON A.AssetID=D.AssetID LEFT JOIN tbl_AssetCategories C ON C.CategoryID=A.CategoryID
        WHERE D.PeriodID=? ORDER BY A.AssetCode""", (period_id,))


def discard_drafts(con, period_id: int) -> dict:
    n = con.execute("DELETE FROM tbl_Depreciation WHERE PeriodID=? AND PostingStatus='DRAFT'", (period_id,)).rowcount
    audit(con, "DISCARD", "tbl_Depreciation", period_id, f"{n} draft lines removed")
    con.commit()
    return {"deleted": n}


def post_depreciation(con, period_id: int) -> dict:
    p = one(con, "SELECT * FROM tbl_DepreciationPeriods WHERE PeriodID=?", (period_id,))
    if not p:
        raise ApiError("Period not found", 404)
    if p["PeriodStatus"] != "OPEN":
        raise ApiError("The period is closed")
    drafts = rows(con, """SELECT D.*, A.AssetCode, A.AssetName, A.AssetStatus, C.DepExpenseAccountID, C.AccumDepAccountID
        FROM tbl_Depreciation D JOIN tbl_Assets A ON A.AssetID=D.AssetID
        JOIN tbl_AssetCategories C ON C.CategoryID=A.CategoryID WHERE D.PeriodID=? AND D.PostingStatus='DRAFT'""", (period_id,))
    if not drafts:
        raise ApiError("There are no unposted depreciation lines for this period")
    fresh = {l["AssetID"]: l for l in propose(con, period_id) if l["eligible"]}
    for d in drafts:
        e = fresh.get(d["AssetID"])
        if not e or abs(e["PeriodDepreciation"] - d["PeriodDepreciation"]) > 0.005 or abs(e["OpeningAccumDep"] - d["OpeningAccumDep"]) > 0.005:
            raise ApiError("The proposal is out of date. Discard it and create it again.")
    for d in drafts:
        if not d["DepExpenseAccountID"] or not d["AccumDepAccountID"]:
            raise ApiError(f"Asset group of {d['AssetCode']} has no depreciation accounts configured")
        if d["AssetStatus"] == "Disposed":
            raise ApiError(f"{d['AssetCode']} is disposed")
        sp = _sequence_ok(con, one(con, "SELECT * FROM tbl_Assets WHERE AssetID=?", (d["AssetID"],)), p)
        if sp:
            raise ApiError(f"{d['AssetCode']}: {sp} must be posted first")
    ts = now()
    total = 0.0
    for d in drafts:
        desc = f"Depreciation - {d['AssetCode']} - {d['AssetName']} - {p['PeriodName']}"
        for acc, dr, cr in ((d["DepExpenseAccountID"], d["PeriodDepreciation"], 0), (d["AccumDepAccountID"], 0, d["PeriodDepreciation"])):
            con.execute("""INSERT INTO tbl_DepreciationJournal(DepreciationID,AssetID,PeriodID,JournalDate,GLAccountID,
                DebitAmount,CreditAmount,JournalType,Reference,Description,PostingStatus,PostedAt,PostedBy,CreatedAt)
                VALUES(?,?,?,?,?,?,?,'DEPRECIATION',?,?,'POSTED',?,?,?)""",
                        (d["DepreciationID"], d["AssetID"], period_id, p["EndDate"], acc, dr, cr, d["AssetCode"], desc, ts, actor(), ts))
        con.execute("UPDATE tbl_Depreciation SET PostingStatus='POSTED',PostedAt=?,PostedBy=? WHERE DepreciationID=?",
                    (ts, actor(), d["DepreciationID"]))
        total += d["PeriodDepreciation"]
    audit(con, "POST", "tbl_Depreciation", period_id, f"{p['PeriodName']}: {len(drafts)} lines, {r2(total)}")
    con.commit()
    return {"posted": len(drafts), "total": r2(total)}
