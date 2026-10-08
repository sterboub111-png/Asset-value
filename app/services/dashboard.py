"""Workspace dashboard figures."""
from __future__ import annotations

from datetime import date

from .assets import list_assets
from .common import _ctx, month_ar, one, r2, rows
from .maintenance import MAINT_SQL, _maint_flags
from .periods import period_for_date
from .settings import get_settings

def dashboard(con) -> dict:
    assets = [a for a in list_assets(con) if a["AssetStatus"] != "Disposed"]
    cost = sum(a["AcquisitionCost"] for a in assets)
    acc = sum(a["AccumDep"] for a in assets)
    by_cat: dict[str, dict] = {}
    for a in assets:
        c = by_cat.setdefault(a["CategoryName"] or "-", {"name": a["CategoryName"] or "-", "cost": 0, "nbv": 0, "count": 0})
        c["cost"] += a["AcquisitionCost"]; c["nbv"] += a["NBV"]; c["count"] += 1
    today = date.today().isoformat()
    cur = period_for_date(con, today)
    by_year = rows(con, """SELECT P.FiscalYear y, P.PeriodNumber n, P.PeriodName name, SUM(D.PeriodDepreciation) amt
        FROM tbl_Depreciation D JOIN tbl_DepreciationPeriods P ON P.PeriodID=D.PeriodID WHERE D.PostingStatus='POSTED'
        GROUP BY P.PeriodID ORDER BY P.StartDate DESC LIMIT 12""")[::-1]
    if getattr(_ctx, "lang", "en") == "ar":
        for r_ in by_year:
            r_["name"] = month_ar(r_["name"])
    open_p = one(con, """SELECT P.* FROM tbl_DepreciationPeriods P WHERE P.PeriodStatus='OPEN' AND NOT EXISTS
        (SELECT 1 FROM tbl_Depreciation D WHERE D.PeriodID=P.PeriodID AND D.PostingStatus='POSTED')
        ORDER BY P.StartDate LIMIT 1""")
    warranty = rows(con, """SELECT AssetID,AssetCode,AssetName,AssetNameAr,WarrantyExpiryDate FROM tbl_Assets WHERE AssetStatus<>'Disposed'
        AND WarrantyExpiryDate IS NOT NULL AND WarrantyExpiryDate BETWEEN ? AND date(?,'+90 day') ORDER BY WarrantyExpiryDate""", (today, today))
    return {
        "asset_count": len(assets), "cost": r2(cost), "accum_dep": r2(acc), "nbv": r2(cost - acc),
        "by_category": sorted(by_cat.values(), key=lambda c: -c["cost"]),
        "dep_trend": by_year,
        "next_period": open_p, "current_period": cur,
        "draft_lines": one(con, "SELECT COUNT(*) n FROM tbl_Depreciation WHERE PostingStatus='DRAFT'")["n"],
        "status_counts": rows(con, "SELECT AssetStatus s, COUNT(*) n FROM tbl_Assets GROUP BY AssetStatus"),
        "warranty": warranty,
        "recent": rows(con, """SELECT T.*, A.AssetCode, A.AssetName, A.AssetNameAr FROM tbl_AssetTransactions T JOIN tbl_Assets A ON A.AssetID=T.AssetID
                               ORDER BY T.TransactionID DESC LIMIT 8"""),
        "currency": get_settings(con).get("DefaultCurrency") or "SAR",
        "custody_held": one(con, "SELECT COUNT(*) n FROM tbl_AssetCustody WHERE Status='Issued'")["n"],
        "maint_open": one(con, "SELECT COUNT(*) n FROM tbl_Maintenance WHERE Status IN ('Planned','In Progress')")["n"],
        "maint_overdue": one(con, "SELECT COUNT(*) n FROM tbl_Maintenance WHERE Status IN ('Planned','In Progress') AND ScheduledDate<?", (today,))["n"],
        "maint_due": [_maint_flags(m) for m in rows(con, MAINT_SQL + " WHERE M.Status IN ('Planned','In Progress') ORDER BY M.ScheduledDate LIMIT 8")],
        "custody_list": rows(con, """SELECT U.CustodyID, U.CustodyNo, U.IssueDate, U.AssetID, A.AssetCode, A.AssetName, A.AssetNameAr, E.EmployeeName, E.EmployeeNameAr,
            (SELECT COUNT(*) FROM tbl_AssetAttachments T WHERE T.CustodyID=U.CustodyID) AS AttachmentCount
            FROM tbl_AssetCustody U JOIN tbl_Assets A ON A.AssetID=U.AssetID JOIN tbl_Employees E ON E.EmployeeID=U.EmployeeID
            WHERE U.Status='Issued' ORDER BY U.IssueDate DESC, U.CustodyID DESC LIMIT 8"""),
        "custody_unsigned": one(con, """SELECT COUNT(*) n FROM tbl_AssetCustody U WHERE U.Status='Issued'
            AND NOT EXISTS (SELECT 1 FROM tbl_AssetAttachments T WHERE T.CustodyID=U.CustodyID)""")["n"],
        "under_repair": sum(1 for a in assets if a["AssetStatus"] == "Under Repair"),
        "no_location": sum(1 for a in assets if not a["LocationID"]),
        "missing_opening": _missing_opening(con),
        "cycle": _cycle(con, open_p, today),
    }


def _missing_opening(con) -> list[dict]:
    """Assets that started depreciating before the first period but carry no opening accumulated depreciation."""
    first = one(con, "SELECT MIN(StartDate) s FROM tbl_DepreciationPeriods", raw=True)["s"]
    if not first:
        return []
    return rows(con, """SELECT A.AssetID, A.AssetCode, A.AssetName, A.AssetNameAr FROM tbl_Assets A
        JOIN tbl_DepreciationMethods M ON M.MethodID=A.MethodID
        WHERE A.AssetStatus<>'Disposed' AND M.MethodCode='SL' AND COALESCE(A.OpeningAccumDep,0)=0
          AND substr(COALESCE(A.DepreciationStartDate, A.InServiceDate, A.AcquisitionDate),1,7) < substr(?,1,7)
          AND NOT EXISTS (SELECT 1 FROM tbl_Depreciation D WHERE D.AssetID=A.AssetID AND D.PostingStatus='POSTED')
        ORDER BY A.AssetCode""", (first,))


def _cycle(con, next_p: dict | None, today: str) -> dict:
    """Where the monthly depreciation cycle stands: the period to work on, its drafts, months behind, periods ready to close."""
    month_start = today[:8] + "01"
    out = {"period": next_p, "drafts": 0, "behind": 0, "closable": []}
    if next_p:
        out["drafts"] = one(con, "SELECT COUNT(*) n FROM tbl_Depreciation WHERE PeriodID=? AND PostingStatus='DRAFT'", (next_p["PeriodID"],))["n"]
        out["behind"] = one(con, "SELECT COUNT(*) n FROM tbl_DepreciationPeriods WHERE StartDate>=? AND EndDate<?", (next_p["StartDate"], month_start))["n"]
    # past open periods that are fully posted (something posted, no drafts left) can be closed
    out["closable"] = rows(con, """SELECT P.PeriodID, P.PeriodName FROM tbl_DepreciationPeriods P WHERE P.PeriodStatus='OPEN' AND P.EndDate<?
        AND EXISTS (SELECT 1 FROM tbl_Depreciation D WHERE D.PeriodID=P.PeriodID AND D.PostingStatus='POSTED')
        AND NOT EXISTS (SELECT 1 FROM tbl_Depreciation D WHERE D.PeriodID=P.PeriodID AND D.PostingStatus='DRAFT')
        AND (? IS NULL OR P.StartDate<?) ORDER BY P.StartDate""", (month_start, next_p["StartDate"] if next_p else None, next_p["StartDate"] if next_p else None))
    return out
