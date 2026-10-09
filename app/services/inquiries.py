"""Journal, transaction and audit-log inquiries."""
from __future__ import annotations

from .common import rows, scope_sql

# ---------------------------------------------------------------- inquiries & dashboard
def journal(con, period_id: str = "", jtype: str = "") -> list[dict]:
    sql = """SELECT J.*, G.AccountCode, G.AccountName, G.AccountNameAr, P.PeriodName FROM tbl_DepreciationJournal J
             LEFT JOIN tbl_GLAccounts G ON G.GLAccountID=J.GLAccountID
             LEFT JOIN tbl_DepreciationPeriods P ON P.PeriodID=J.PeriodID JOIN tbl_Assets A ON A.AssetID=J.AssetID WHERE 1=1""" + scope_sql("A")
    args: list = []
    if period_id:
        sql += " AND J.PeriodID=?"; args.append(period_id)
    if jtype:
        sql += " AND J.JournalType=?"; args.append(jtype)
    return rows(con, sql + " ORDER BY J.JournalDate DESC, J.JournalID DESC", args)


def transactions(con) -> list[dict]:
    return rows(con, """SELECT T.*, A.AssetCode, A.AssetName, A.AssetNameAr FROM tbl_AssetTransactions T
        JOIN tbl_Assets A ON A.AssetID=T.AssetID WHERE 1=1""" + scope_sql("A") + " ORDER BY T.TransactionDate DESC, T.TransactionID DESC LIMIT 2000")


def audit_log(con) -> list[dict]:
    return rows(con, "SELECT * FROM tbl_AuditLog ORDER BY LogID DESC LIMIT 1000")
