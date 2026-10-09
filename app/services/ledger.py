"""Fixed asset ledger entries: every event that changed an asset's book value or whereabouts, in one list.

    acquisition   cost +            (and the opening accumulated depreciation of an asset brought in)
    addition      cost +
    depreciation  accumulated depreciation +   (posted months only)
    impairment / revaluation   carrying amount - / +
    disposal      cost, accumulated depreciation and value adjustments all out
    transfer, status   no amounts

Each entry carries its document number (services/book.py doc_no) and opens to its journal lines. For one asset the
entries add up to its net book value (a running balance); for the whole register they are paged.
"""
from __future__ import annotations

from .book import VALUE_IN, doc_no, doc_no_sql
from .common import ApiError, _ctx, month_ar, one, parse_date, r2, rows, scope_sql, to_int

KINDS = ("ACQUISITION", "ADDITION", "DEPRECIATION", "IMPAIRMENT", "REVALUATION", "DISPOSAL", "TRANSFER", "STATUS")


def ledger(con, asset: int | None = None, f: str | None = None, t: str | None = None, kind: str = "", q: str = "",
           branch: int | None = None, limit: int = 500, offset: int = 0) -> dict:
    f = parse_date(f, "From date") or "1900-01-01"
    t = parse_date(t, "To date") or "2999-12-31"
    if kind and kind not in KINDS:
        raise ApiError("Unknown entry type")
    where, args = scope_sql("A"), []
    if asset:
        where += " AND A.AssetID=?"; args.append(asset)
    if branch:
        where += " AND A.LocationID IN (SELECT LocationID FROM tbl_Locations WHERE BranchID=?)"; args.append(branch)
    if q:
        where += " AND (A.AssetCode LIKE ? OR A.AssetName LIKE ? OR A.AssetNameAr LIKE ?)"; args += [f"%{q}%"] * 3
    parts, pargs = [], []
    if kind in ("", "DEPRECIATION"):
        parts.append(f"""SELECT 'DEP-'||substr(P.StartDate,1,7) AS Document, P.EndDate AS EntryDate, 'DEPRECIATION' AS EntryType,
            A.AssetID, A.AssetCode, A.AssetName, A.AssetNameAr, P.PeriodName AS Description,
            0 AS CostChange, D.PeriodDepreciation AS DepChange, 0 AS ValueChange, NULL AS Proceeds,
            NULL AS FromLocation, NULL AS FromLocationAr, NULL AS ToLocation, NULL AS ToLocationAr, D.PostedBy AS UserName,
            NULL AS TransactionID, D.DepreciationID, 2 AS Ord
            FROM tbl_Depreciation D JOIN tbl_DepreciationPeriods P ON P.PeriodID=D.PeriodID JOIN tbl_Assets A ON A.AssetID=D.AssetID
            WHERE D.PostingStatus='POSTED' AND P.EndDate BETWEEN ? AND ?{where}""")
        pargs += [f, t, *args]
    if kind != "DEPRECIATION":
        tw = " AND T.TransactionType=?" if kind else ""
        # a disposal takes out the cost, the net accumulated depreciation and the value changes recorded until then
        parts.append(f"""SELECT {doc_no_sql('T.TransactionType', 'T.TransactionID')} AS Document, T.TransactionDate AS EntryDate, T.TransactionType AS EntryType,
            A.AssetID, A.AssetCode, A.AssetName, A.AssetNameAr, COALESCE(T.Notes, T.DisposalReason, '') AS Description,
            CASE T.TransactionType WHEN 'ACQUISITION' THEN T.Amount WHEN 'ADDITION' THEN T.Amount WHEN 'DISPOSAL' THEN -T.Amount ELSE 0 END AS CostChange,
            CASE T.TransactionType WHEN 'ACQUISITION' THEN COALESCE(A.OpeningAccumDep,0)
                 WHEN 'DISPOSAL' THEN -(COALESCE(A.OpeningAccumDep,0) + COALESCE((SELECT SUM(D.PeriodDepreciation) FROM tbl_Depreciation D
                      JOIN tbl_DepreciationPeriods P ON P.PeriodID=D.PeriodID WHERE D.AssetID=A.AssetID AND D.PostingStatus='POSTED' AND P.EndDate<=T.TransactionDate),0))
                 ELSE 0 END AS DepChange,
            CASE WHEN T.TransactionType IN {VALUE_IN} THEN T.Amount
                 WHEN T.TransactionType='DISPOSAL' THEN -COALESCE((SELECT SUM(X.Amount) FROM tbl_AssetTransactions X WHERE X.AssetID=A.AssetID
                      AND X.TransactionType IN {VALUE_IN} AND X.TransactionDate<=T.TransactionDate),0)
                 ELSE 0 END AS ValueChange,
            T.DisposalProceeds AS Proceeds, FL.LocationName AS FromLocation, FL.LocationNameAr AS FromLocationAr,
            TL.LocationName AS ToLocation, TL.LocationNameAr AS ToLocationAr, T.CreatedBy AS UserName, T.TransactionID, NULL AS DepreciationID,
            CASE T.TransactionType WHEN 'ACQUISITION' THEN 0 WHEN 'DISPOSAL' THEN 9 ELSE 1 END AS Ord
            FROM tbl_AssetTransactions T JOIN tbl_Assets A ON A.AssetID=T.AssetID
            LEFT JOIN tbl_Locations FL ON FL.LocationID=T.FromLocationID LEFT JOIN tbl_Locations TL ON TL.LocationID=T.ToLocationID
            WHERE T.TransactionDate BETWEEN ? AND ?{tw}{where}""")
        pargs += [f, t, *([kind] if kind else []), *args]
    sql = " UNION ALL ".join(parts)
    total = con.execute(f"SELECT COUNT(*), COALESCE(SUM(CostChange),0), COALESCE(SUM(DepChange),0), COALESCE(SUM(ValueChange),0) FROM ({sql}) E", pargs).fetchone()
    order = "EntryDate, Ord, AssetCode, Document" if asset else "EntryDate DESC, Ord DESC, AssetCode, Document"
    limit = max(1, min(to_int(limit, "Limit", 500), 5000))
    data = rows(con, f"SELECT * FROM ({sql}) E ORDER BY {order} LIMIT ? OFFSET ?", [*pargs, limit, max(0, to_int(offset, "Offset"))])
    ar = getattr(_ctx, "lang", "en") == "ar"
    for r in data:
        r["CostChange"], r["DepChange"], r["ValueChange"] = r2(r["CostChange"]), r2(r["DepChange"]), r2(r["ValueChange"])
        if ar and r["EntryType"] == "DEPRECIATION":
            r["Description"] = month_ar(r["Description"])
        r["NBVChange"] = r2(r["CostChange"] - r["DepChange"] + r["ValueChange"])
    if asset:   # one asset from its first entry: the running net book value
        run = 0.0
        for r in data:
            run += r["NBVChange"]
            r["Balance"] = r2(run)
    return {"rows": data, "total": total[0], "sums": {"CostChange": r2(total[1]), "DepChange": r2(total[2]), "ValueChange": r2(total[3]),
                                                     "NBVChange": r2(total[1] - total[2] + total[3])}, "limit": limit}


def entry_journal(con, tx: int | None = None, dep: int | None = None) -> dict:
    """The journal lines of one ledger entry (a transaction, or one asset's posted depreciation of a month)."""
    if not tx and not dep:
        raise ApiError("Entry not found", 404)
    col, key = ("TransactionID", tx) if tx else ("DepreciationID", dep)
    head = one(con, f"""SELECT A.AssetID, A.AssetCode, A.AssetName, A.AssetNameAr, MIN(J.JournalDate) JournalDate, MIN(J.JournalType) JournalType,
        MIN(J.Description) Description, MIN(J.PostedBy) PostedBy, MIN(J.PostedAt) PostedAt, MIN(P.StartDate) PeriodStart
        FROM tbl_DepreciationJournal J JOIN tbl_Assets A ON A.AssetID=J.AssetID LEFT JOIN tbl_DepreciationPeriods P ON P.PeriodID=J.PeriodID
        WHERE J.{col}=?{scope_sql('A')} GROUP BY A.AssetID""", (key,))
    lines = rows(con, f"""SELECT G.AccountCode, G.AccountName, G.AccountNameAr, J.DebitAmount, J.CreditAmount FROM tbl_DepreciationJournal J
        LEFT JOIN tbl_GLAccounts G ON G.GLAccountID=J.GLAccountID JOIN tbl_Assets A ON A.AssetID=J.AssetID
        WHERE J.{col}=?{scope_sql('A')} ORDER BY J.DebitAmount DESC, J.JournalID""", (key,))
    if head:
        head["Document"] = doc_no(head["JournalType"], tx, head["PeriodStart"])
    return {"head": head, "lines": lines}
