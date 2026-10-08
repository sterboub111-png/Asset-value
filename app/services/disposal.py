"""Asset disposal and its journal."""
from __future__ import annotations

from .assets import get_asset
from .common import ApiError, actor, audit, now, num, one, parse_date, r2, rows
from .depreciation import _fully_depreciated
from .periods import period_for_date
from .settings import get_settings

# ---------------------------------------------------------------- disposal
def dispose_asset(con, asset_id: int, data: dict) -> dict:
    a = get_asset(con, asset_id)
    if a["AssetStatus"] == "Disposed":
        raise ApiError("Asset is already disposed")
    if one(con, "SELECT 1 x FROM tbl_Maintenance WHERE AssetID=? AND Status IN ('Planned','In Progress') LIMIT 1", (asset_id,)):
        raise ApiError("Complete or cancel the open maintenance orders of this asset first")
    if one(con, "SELECT 1 x FROM tbl_AssetCustody WHERE AssetID=? AND Status='Issued' LIMIT 1", (asset_id,)):
        raise ApiError("Return the asset from the employee custody first")
    d = parse_date(data.get("TransactionDate"), "Disposal date", True)
    if d < a["AcquisitionDate"]:
        raise ApiError("Disposal date cannot be before the acquisition date")
    proceeds = r2(num(data.get("DisposalProceeds"), "Sale proceeds", 0, 0))   # cents only, so the journal always balances
    per = period_for_date(con, d)
    if per and per["PeriodStatus"] != "OPEN":
        raise ApiError("The period of the disposal date is closed")
    # Depreciation must be posted for every period that ends before the disposal month
    mstart = d[:8] + "01"
    start = a["DepreciationStartDate"] or a["InServiceDate"] or a["AcquisitionDate"]
    last_posted = one(con, """SELECT MAX(P.EndDate) e FROM tbl_Depreciation D JOIN tbl_DepreciationPeriods P ON P.PeriodID=D.PeriodID
                              WHERE D.AssetID=? AND D.PostingStatus='POSTED'""", (asset_id,), raw=True)["e"]
    if last_posted and d <= last_posted:
        raise ApiError("Depreciation is already posted after this date. Choose a later disposal date.")
    if a["MethodCode"] == "SL" and not _fully_depreciated(con, a):
        pend = rows(con, """SELECT P.PeriodName FROM tbl_DepreciationPeriods P WHERE P.EndDate>=? AND P.StartDate<?
            AND NOT EXISTS (SELECT 1 FROM tbl_Depreciation D WHERE D.AssetID=? AND D.PeriodID=P.PeriodID AND D.PostingStatus='POSTED')
            ORDER BY P.StartDate""", (start, mstart, asset_id))
        eligible = [x["PeriodName"] for x in pend]
        if eligible:
            raise ApiError("Post depreciation first for: " + ", ".join(eligible[:3]) + ("…" if len(eligible) > 3 else ""))
    if con.execute("SELECT 1 FROM tbl_Depreciation WHERE AssetID=? AND PostingStatus='DRAFT'", (asset_id,)).fetchone():
        con.execute("DELETE FROM tbl_Depreciation WHERE AssetID=? AND PostingStatus='DRAFT'", (asset_id,))
    accum = a["AccumDep"]
    cost = a["AcquisitionCost"]
    nbv = r2(cost - accum)
    gain = r2(proceeds - nbv)
    cat = one(con, "SELECT * FROM tbl_AssetCategories WHERE CategoryID=?", (a["CategoryID"],))
    clearing = get_settings(con).get("DisposalClearingAccountID")
    if not (cat["AssetAccountID"] and cat["AccumDepAccountID"]):
        raise ApiError("Asset group has no asset / accumulated depreciation account")
    if not clearing and proceeds:
        raise ApiError("Set the disposal clearing account in Fixed asset parameters")
    if gain > 0 and not cat["GainAccountID"]:
        raise ApiError("Asset group has no gain-on-disposal account")
    if gain < 0 and not cat["LossAccountID"]:
        raise ApiError("Asset group has no loss-on-disposal account")
    cur = con.execute("INSERT INTO tbl_AssetTransactions(AssetID,TransactionType,TransactionDate,Amount,DisposalProceeds,"
                      "DisposalReason,FromLocationID,FromCostCenterID,ReferenceNumber,Notes,CreatedAt,CreatedBy) "
                      "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                      (asset_id, "DISPOSAL", d, cost, proceeds, data.get("DisposalReason") or None, a["LocationID"],
                       a["CostCenterID"], data.get("ReferenceNumber") or None, data.get("Notes") or None, now(), actor()))
    tx = cur.lastrowid
    desc = f"Disposal - {a['AssetCode']} - {a['AssetName']}"
    lines = [(cat["AccumDepAccountID"], accum, 0), (cat["AssetAccountID"], 0, cost)]
    if proceeds:
        lines.append((int(clearing), proceeds, 0))
    if gain > 0:
        lines.append((cat["GainAccountID"], 0, gain))
    elif gain < 0:
        lines.append((cat["LossAccountID"], -gain, 0))
    for acc, dr, cr in lines:
        if dr == 0 and cr == 0:
            continue
        con.execute("""INSERT INTO tbl_DepreciationJournal(TransactionID,AssetID,PeriodID,JournalDate,GLAccountID,DebitAmount,
            CreditAmount,JournalType,Reference,Description,PostingStatus,PostedAt,PostedBy,CreatedAt)
            VALUES(?,?,?,?,?,?,?,'DISPOSAL',?,?,'POSTED',?,?,?)""",
                    (tx, asset_id, per["PeriodID"] if per else None, d, acc, dr, cr, a["AssetCode"], desc, now(), actor(), now()))
    con.execute("UPDATE tbl_Assets SET AssetStatus='Disposed',DisposalDate=?,ModifiedAt=?,ModifiedBy=? WHERE AssetID=?",
                (d, now(), actor(), asset_id))
    audit(con, "DISPOSE", "tbl_Assets", asset_id, f"{a['AssetCode']} proceeds={proceeds} gain/loss={gain}")
    con.commit()
    return get_asset(con, asset_id)
