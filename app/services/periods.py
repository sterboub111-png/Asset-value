"""Depreciation periods."""
from __future__ import annotations

import calendar
from datetime import date

from .common import ApiError, actor, audit, now, one, rows
from .settings import get_settings

# ---------------------------------------------------------------- periods
def generate_periods(con, fiscal_year: int) -> list[dict]:
    if not 1990 <= fiscal_year <= 2100:
        raise ApiError("Invalid fiscal year")
    start_month = int(get_settings(con).get("FiscalYearStartMonth") or 1)
    y, m = fiscal_year, start_month
    made = 0
    for n in range(1, 13):
        first = date(y, m, 1)
        last = date(y, m, calendar.monthrange(y, m)[1])
        exists = one(con, "SELECT 1 x FROM tbl_DepreciationPeriods WHERE FiscalYear=? AND PeriodNumber=?", (fiscal_year, n))
        if not exists:
            con.execute("INSERT INTO tbl_DepreciationPeriods(FiscalYear,PeriodNumber,PeriodName,StartDate,EndDate,"
                        "PeriodStatus,CreatedAt,CreatedBy) VALUES(?,?,?,?,?,'OPEN',?,?)",
                        (fiscal_year, n, first.strftime("%B %Y"), first.isoformat(), last.isoformat(), now(), actor()))
            made += 1
        m += 1
        if m > 12:
            m, y = 1, y + 1
    audit(con, "CREATE", "tbl_DepreciationPeriods", fiscal_year, f"{made} periods generated")
    con.commit()
    return rows(con, "SELECT * FROM tbl_DepreciationPeriods ORDER BY StartDate")


def set_period_status(con, period_id: int, status: str) -> dict:
    if status not in ("OPEN", "CLOSED"):
        raise ApiError("Invalid status")
    p = one(con, "SELECT * FROM tbl_DepreciationPeriods WHERE PeriodID=?", (period_id,))
    if not p:
        raise ApiError("Period not found", 404)
    if status == "CLOSED":
        drafts = one(con, "SELECT COUNT(*) n FROM tbl_Depreciation WHERE PeriodID=? AND PostingStatus='DRAFT'", (period_id,))["n"]
        if drafts:
            raise ApiError(f"Cannot close: {drafts} unposted depreciation line(s) in this period")
    con.execute("UPDATE tbl_DepreciationPeriods SET PeriodStatus=? WHERE PeriodID=?", (status, period_id))
    audit(con, "UPDATE", "tbl_DepreciationPeriods", period_id, f"{p['PeriodName']} -> {status}")
    con.commit()
    return one(con, "SELECT * FROM tbl_DepreciationPeriods WHERE PeriodID=?", (period_id,))


def period_for_date(con, d: str) -> dict | None:
    return one(con, "SELECT * FROM tbl_DepreciationPeriods WHERE StartDate<=? AND EndDate>=?", (d, d))
