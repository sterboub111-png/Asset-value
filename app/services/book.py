"""The book value of an asset: one definition, used by the register, the depreciation run, disposals, reports and checks.

    cost            = acquisition cost (net of VAT) + capital additions
    accumulated     = opening accumulated depreciation + posted depreciation
    value adjusted  = revaluations (+) and impairments (-) of the carrying amount
    net book value  = cost - accumulated + value adjusted

Capital additions and value adjustments are asset transactions (services/valuation.py); a date limits each part to what
was recorded on or before it.
"""
from __future__ import annotations

from .common import r2

ADDITION = "ADDITION"
VALUE_TYPES = ("IMPAIRMENT", "REVALUATION")      # a decrease / an increase of the carrying amount
VALUE_IN = "('IMPAIRMENT','REVALUATION')"

# SQL parts for a query over tbl_Assets aliased A
ADDITIONS_SQL = "COALESCE((SELECT SUM(X.Amount) FROM tbl_AssetTransactions X WHERE X.AssetID=A.AssetID AND X.TransactionType='ADDITION'),0)"
VALUE_ADJ_SQL = f"COALESCE((SELECT SUM(X.Amount) FROM tbl_AssetTransactions X WHERE X.AssetID=A.AssetID AND X.TransactionType IN {VALUE_IN}),0)"
ACCUM_SQL = ("COALESCE(A.OpeningAccumDep,0) + COALESCE((SELECT SUM(D.PeriodDepreciation) FROM tbl_Depreciation D "
             "WHERE D.AssetID=A.AssetID AND D.PostingStatus='POSTED'),0)")
NBV_SQL = f"(A.AcquisitionCost + {ADDITIONS_SQL} - ({ACCUM_SQL}) + {VALUE_ADJ_SQL})"


def adjustments(con, as_of: str | None = None, asset_id: int | None = None) -> dict[int, dict]:
    """{AssetID: {additions, value_adj, pnl, surplus, n}} from the transactions dated on or before `as_of` (all when None)."""
    sql = f"""SELECT AssetID, COALESCE(SUM(CASE WHEN TransactionType='ADDITION' THEN Amount END),0) additions,
        COALESCE(SUM(CASE WHEN TransactionType IN {VALUE_IN} THEN Amount END),0) value_adj,
        COALESCE(SUM(PnlAmount),0) pnl, COALESCE(SUM(SurplusAmount),0) surplus, COUNT(*) n
        FROM tbl_AssetTransactions WHERE TransactionType IN ('ADDITION','IMPAIRMENT','REVALUATION')"""
    args: list = []
    if as_of:
        sql += " AND TransactionDate<=?"; args.append(as_of)
    if asset_id is not None:
        sql += " AND AssetID=?"; args.append(asset_id)
    return {r[0]: {"additions": r[1], "value_adj": r[2], "pnl": r[3], "surplus": r[4], "n": r[5]}
            for r in con.execute(sql + " GROUP BY AssetID", args)}


def values(con, asset_id: int) -> dict:
    """Current book values of one asset (all posted depreciation and every addition / adjustment)."""
    a = con.execute("SELECT AcquisitionCost, OpeningAccumDep, ResidualValue FROM tbl_Assets WHERE AssetID=?", (asset_id,)).fetchone()
    posted = con.execute("SELECT COALESCE(SUM(PeriodDepreciation),0) FROM tbl_Depreciation WHERE AssetID=? AND PostingStatus='POSTED'",
                         (asset_id,)).fetchone()[0]
    adj = adjustments(con, None, asset_id).get(asset_id, {"additions": 0, "value_adj": 0, "pnl": 0, "surplus": 0, "n": 0})
    cost = (a[0] or 0) + adj["additions"]
    accum = (a[1] or 0) + posted
    return {"cost": r2(cost), "additions": r2(adj["additions"]), "accum": r2(accum), "value_adj": r2(adj["value_adj"]),
            "nbv": r2(cost - accum + adj["value_adj"]), "residual": r2(a[2]), "pnl": r2(adj["pnl"]), "surplus": r2(adj["surplus"]),
            "adjusted": adj["n"] > 0}


# ---- document numbers: every transaction and posting shows one (derived from its id, so nothing extra is stored)
DOC_PREFIX = {"ACQUISITION": "ACQ", "ADDITION": "ADD", "TRANSFER": "TRF", "DISPOSAL": "DSP", "IMPAIRMENT": "IMP", "REVALUATION": "REV",
              "STATUS": "STS", "DEPRECIATION": "DEP"}


def doc_no(kind: str, tx_id: int | None = None, period_start: str | None = None) -> str:
    """DEP-2026-10 for a month's depreciation, otherwise <prefix>-<transaction id>, e.g. DSP-000042."""
    if kind == "DEPRECIATION":
        return f"DEP-{(period_start or '')[:7]}"
    return f"{DOC_PREFIX.get(kind, 'TRX')}-{int(tx_id or 0):06d}"


def doc_no_sql(type_col: str, id_col: str) -> str:
    cases = " ".join(f"WHEN '{k}' THEN '{v}'" for k, v in DOC_PREFIX.items() if k != "DEPRECIATION")
    padded = f"substr('000000', 1, 6 - length(CAST({id_col} AS TEXT))) || CAST({id_col} AS TEXT)"   # the same in SQLite and PostgreSQL
    return f"(CASE {type_col} {cases} ELSE 'TRX' END || '-' || {padded})"
