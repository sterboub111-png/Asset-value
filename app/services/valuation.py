"""Changes to the value of an asset in use: capital additions (IAS 16.13) and revaluation / impairment (IAS 16.31, IAS 36).

Capital addition: an improvement or a component that extends the asset. It raises the cost; like the acquisition it is
recorded in the purchase ledger, so it writes no journal here. The useful life may be extended at the same time.

Revaluation / impairment: the carrying amount is brought to a new value (fair value or recoverable amount).
  A decrease first uses the revaluation surplus of the asset, the rest is an impairment loss:
      Dr Revaluation surplus / Dr Impairment loss    Cr Accumulated depreciation and impairment
  An increase first reverses impairment losses charged before, the rest goes to the revaluation surplus:
      Dr Accumulated depreciation and impairment     Cr Impairment loss (reversal) / Cr Revaluation surplus
Both are dated after the last posted depreciation of the asset; from the next month the depreciation spreads the new
carrying amount less the residual value over the remaining life. Book values: services/book.py.
"""
from __future__ import annotations

from .assets import get_asset
from .book import values
from .common import ApiError, actor, audit, now, num, one, parse_date, r2
from .depreciation import DEPRECIATING, _month_index, _start, monthly_charge
from .periods import period_for_date
from .settings import get_settings


def _check_date(con, a: dict, d: str) -> dict | None:
    """Shared rules for the date of an addition or a value change; returns its period."""
    if a["AssetStatus"] == "Disposed":
        raise ApiError("Asset is disposed")
    if d < a["AcquisitionDate"]:
        raise ApiError("The date cannot be before the acquisition date")
    per = period_for_date(con, d)
    if per and per["PeriodStatus"] != "OPEN":
        raise ApiError("The period of this date is closed")
    last = one(con, """SELECT MAX(P.EndDate) e FROM tbl_Depreciation D JOIN tbl_DepreciationPeriods P ON P.PeriodID=D.PeriodID
                       WHERE D.AssetID=? AND D.PostingStatus='POSTED'""", (a["AssetID"],), raw=True)["e"]
    if last and d <= last:
        raise ApiError("Depreciation is already posted for this date. Choose a date after the last posted month.")
    later = one(con, "SELECT MAX(TransactionDate) d FROM tbl_AssetTransactions WHERE AssetID=? AND TransactionType IN ('ADDITION','IMPAIRMENT','REVALUATION')",
                (a["AssetID"],), raw=True)["d"]
    if later and d < later:
        raise ApiError("An addition or revaluation is already recorded after this date")
    return per


def _monthly_after(a: dict, d: str, cost: float, accum: float, value_adj: float, residual: float, life: float | None) -> float:
    """What the depreciation of the month of `d` becomes with the new values (the preview shown before saving)."""
    if a["MethodCode"] not in DEPRECIATING or not life:
        return 0.0
    elapsed = max(0, _month_index(d) - _month_index(_start(a)))
    return monthly_charge(a["MethodCode"], life, a["DepreciationRate"], cost, residual, accum, value_adj, elapsed, 0, True)


def _discard_drafts(con, asset_id: int) -> None:
    n = con.execute("DELETE FROM tbl_Depreciation WHERE AssetID=? AND PostingStatus='DRAFT'", (asset_id,)).rowcount
    if n:
        audit(con, "DISCARD", "tbl_Depreciation", asset_id, f"{n} draft line(s) removed because the asset value changed")


# ---------------------------------------------------------------- capital addition
def add_capital(con, asset_id: int, data: dict, dry: bool = False) -> dict:
    a = get_asset(con, asset_id)
    d = parse_date(data.get("TransactionDate"), "Date", True)
    amount = r2(num(data.get("Amount"), "Amount", 0, 0))
    if amount <= 0:
        raise ApiError("Enter the amount of the addition")
    _check_date(con, a, d)
    v = values(con, asset_id)
    life = num(data.get("UsefulLifeYears"), "Useful life", None, 0) or a["UsefulLifeYears"]
    elapsed = max(0, _month_index(d) - _month_index(_start(a)))
    if life and life != a["UsefulLifeYears"] and life * 12 <= elapsed:
        raise ApiError("The new useful life must be longer than the time already in use")
    preview = {"CostBefore": v["cost"], "CostAfter": r2(v["cost"] + amount), "NBVBefore": v["nbv"], "NBVAfter": r2(v["nbv"] + amount),
               "LifeBefore": a["UsefulLifeYears"], "LifeAfter": life, "MonthsLeft": max(0, round((life or 0) * 12 - elapsed)),
               "MonthlyBefore": _monthly_after(a, d, v["cost"], v["accum"], v["value_adj"], v["residual"], a["UsefulLifeYears"]),
               "MonthlyAfter": _monthly_after(a, d, v["cost"] + amount, v["accum"], v["value_adj"], v["residual"], life)}
    if dry:
        return preview
    con.execute("INSERT INTO tbl_AssetTransactions(AssetID,TransactionType,TransactionDate,Amount,ToLocationID,ToCostCenterID,"
                "ReferenceNumber,Notes,CreatedAt,CreatedBy) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (asset_id, "ADDITION", d, amount, a["LocationID"], a["CostCenterID"], (data.get("ReferenceNumber") or "").strip() or None,
                 (data.get("Notes") or "").strip() or None, now(), actor()))
    if life != a["UsefulLifeYears"]:
        con.execute("UPDATE tbl_Assets SET UsefulLifeYears=?, DepreciationRate=CASE WHEN ? THEN DepreciationRate ELSE ? END WHERE AssetID=?",
                    (life, a["MethodCode"] == "DB", round(100 / life, 4) if life else None, asset_id))
        audit(con, "UPDATE", "tbl_Assets", asset_id, f"useful life {a['UsefulLifeYears']} -> {life} with a capital addition")
    _discard_drafts(con, asset_id)
    con.execute("UPDATE tbl_Assets SET ModifiedAt=?,ModifiedBy=? WHERE AssetID=?", (now(), actor(), asset_id))
    audit(con, "ADDITION", "tbl_Assets", asset_id, f"{a['AssetCode']} +{amount}")
    con.commit()
    return get_asset(con, asset_id)


# ---------------------------------------------------------------- revaluation / impairment
def _split(change: float, pnl_before: float, surplus_before: float) -> tuple[float, float]:
    """(to profit or loss, to revaluation surplus) for a change of the carrying amount; a loss is positive, surplus credit positive."""
    if change < 0:
        from_surplus = min(max(surplus_before, 0), -change)
        return r2(-change - from_surplus), r2(-from_surplus)
    reversal = min(max(pnl_before, 0), change)
    return r2(-reversal), r2(change - reversal)


def revalue(con, asset_id: int, data: dict, dry: bool = False) -> dict:
    a = get_asset(con, asset_id)
    d = parse_date(data.get("TransactionDate"), "Date", True)
    new = num(data.get("NewValue"), "New carrying amount", None, 0)
    if new is None:
        raise ApiError("Enter the new carrying amount")
    new = r2(new)
    per = _check_date(con, a, d)
    v = values(con, asset_id)
    change = r2(new - v["nbv"])
    if abs(change) < 0.005:
        raise ApiError("The new carrying amount equals the current one")
    pnl, surplus = _split(change, v["pnl"], v["surplus"])
    residual = min(v["residual"], new)       # nothing is depreciated below the new value
    preview = {"NBVBefore": v["nbv"], "NBVAfter": new, "Change": change, "ToProfitLoss": pnl, "ToSurplus": surplus,
               "ResidualBefore": v["residual"], "ResidualAfter": residual,
               "MonthlyBefore": _monthly_after(a, d, v["cost"], v["accum"], v["value_adj"], v["residual"], a["UsefulLifeYears"]),
               "MonthlyAfter": _monthly_after(a, d, v["cost"], v["accum"], v["value_adj"] + change, residual, a["UsefulLifeYears"])}
    if dry:
        return preview
    st = get_settings(con)
    cat = one(con, "SELECT * FROM tbl_AssetCategories WHERE CategoryID=?", (a["CategoryID"],), raw=True)
    if not cat["AccumDepAccountID"]:
        raise ApiError("Asset group has no asset / accumulated depreciation account")
    imp_acc, sur_acc = st.get("ImpairmentAccountID"), st.get("RevaluationSurplusAccountID")
    if pnl and not imp_acc:
        raise ApiError("Set the impairment account in Fixed asset parameters")
    if surplus and not sur_acc:
        raise ApiError("Set the revaluation surplus account in Fixed asset parameters")
    kind = "IMPAIRMENT" if change < 0 else "REVALUATION"
    cur = con.execute("INSERT INTO tbl_AssetTransactions(AssetID,TransactionType,TransactionDate,Amount,PnlAmount,SurplusAmount,"
                      "ToLocationID,ToCostCenterID,ReferenceNumber,Notes,CreatedAt,CreatedBy) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                      (asset_id, kind, d, change, pnl, surplus, a["LocationID"], a["CostCenterID"],
                       (data.get("ReferenceNumber") or "").strip() or None, (data.get("Notes") or "").strip() or None, now(), actor()))
    tx = cur.lastrowid
    desc = f"{'Impairment' if change < 0 else 'Revaluation'} - {a['AssetCode']} - {a['AssetName']}"
    lines = [(int(cat["AccumDepAccountID"]), max(change, 0), max(-change, 0))]
    if pnl:
        lines.append((int(imp_acc), max(pnl, 0), max(-pnl, 0)))
    if surplus:
        lines.append((int(sur_acc), max(-surplus, 0), max(surplus, 0)))
    for acc, dr, cr in lines:
        if dr == 0 and cr == 0:
            continue
        con.execute("""INSERT INTO tbl_DepreciationJournal(TransactionID,AssetID,PeriodID,JournalDate,GLAccountID,DebitAmount,
            CreditAmount,JournalType,Reference,Description,PostingStatus,PostedAt,PostedBy,CreatedAt)
            VALUES(?,?,?,?,?,?,?,?,?,?,'POSTED',?,?,?)""",
                    (tx, asset_id, per["PeriodID"] if per else None, d, acc, r2(dr), r2(cr), kind, a["AssetCode"], desc, now(), actor(), now()))
    if residual != v["residual"]:
        con.execute("UPDATE tbl_Assets SET ResidualValue=? WHERE AssetID=?", (residual, asset_id))
        audit(con, "UPDATE", "tbl_Assets", asset_id, f"residual value {v['residual']} -> {residual} with the {kind.lower()}")
    _discard_drafts(con, asset_id)
    con.execute("UPDATE tbl_Assets SET ModifiedAt=?,ModifiedBy=? WHERE AssetID=?", (now(), actor(), asset_id))
    audit(con, kind, "tbl_Assets", asset_id, f"{a['AssetCode']} {v['nbv']} -> {new} (P&L {pnl}, surplus {surplus})")
    con.commit()
    return get_asset(con, asset_id)

