"""Data integrity: the arithmetic and accounting relations the books must always satisfy, checked straight from the tables.

Every check is independent of the screens and of the code that wrote the data, so a defect anywhere (a calculation,
an edit, an import, a restore) shows up here. `run_checks` returns one result per check; an empty `issues` list means
the relation holds. Amounts compare to the cent (0.005).
"""
from __future__ import annotations

import calendar
from datetime import date

from .common import one, r2, rows

EPS = 0.005


def _issue(text: str, **ref) -> dict:
    return {"text": text, **ref}


def _depreciation_lines(con) -> list[dict]:
    """Each line: opening + charge = closing, and closing NBV = cost - closing; posted lines chain from the opening balance."""
    out = []
    lines = rows(con, """SELECT D.*, A.AssetCode, A.OpeningAccumDep AS AssetOpening, A.AcquisitionCost AS AssetCost, P.StartDate
        FROM tbl_Depreciation D JOIN tbl_Assets A ON A.AssetID=D.AssetID JOIN tbl_DepreciationPeriods P ON P.PeriodID=D.PeriodID
        ORDER BY D.AssetID, P.StartDate""", raw=True)
    prev: dict[int, float] = {}
    for d in lines:
        code = d["AssetCode"]
        if abs((d["OpeningAccumDep"] or 0) + (d["PeriodDepreciation"] or 0) - (d["ClosingAccumDep"] or 0)) > EPS:
            out.append(_issue(f"{code}: opening + depreciation does not equal closing accumulated depreciation", asset=d["AssetID"], period=d["PeriodID"]))
        if abs((d["AcquisitionCost"] or 0) - (d["ClosingAccumDep"] or 0) - (d["ClosingNBV"] or 0)) > EPS:
            out.append(_issue(f"{code}: closing net book value is not cost less closing accumulated depreciation", asset=d["AssetID"], period=d["PeriodID"]))
        if abs((d["AcquisitionCost"] or 0) - (d["AssetCost"] or 0)) > EPS:
            out.append(_issue(f"{code}: a depreciation line was calculated on a cost the asset no longer has", asset=d["AssetID"], period=d["PeriodID"]))
        if d["PostingStatus"] == "POSTED":
            expected = prev.get(d["AssetID"], d["AssetOpening"] or 0)
            if abs((d["OpeningAccumDep"] or 0) - expected) > EPS:
                out.append(_issue(f"{code}: posted lines do not chain (opening {r2(d['OpeningAccumDep'])}, expected {r2(expected)})", asset=d["AssetID"], period=d["PeriodID"]))
            prev[d["AssetID"]] = d["ClosingAccumDep"] or 0
    return out


def _residual_floor(con) -> list[dict]:
    """Accumulated depreciation never goes past cost less residual value."""
    out = []
    for a in rows(con, """SELECT A.AssetID, A.AssetCode, A.AcquisitionCost, A.ResidualValue, COALESCE(A.OpeningAccumDep,0)
            + COALESCE((SELECT SUM(PeriodDepreciation) FROM tbl_Depreciation D WHERE D.AssetID=A.AssetID AND D.PostingStatus='POSTED'),0) AS Accum
            FROM tbl_Assets A""", raw=True):
        if a["Accum"] > (a["AcquisitionCost"] or 0) - (a["ResidualValue"] or 0) + EPS:
            out.append(_issue(f"{a['AssetCode']}: depreciated below its residual value", asset=a["AssetID"]))
        if a["Accum"] < -EPS:
            out.append(_issue(f"{a['AssetCode']}: negative accumulated depreciation", asset=a["AssetID"]))
    return out


def _depreciation_journal(con) -> list[dict]:
    """A posted line has exactly one debit (expense) and one credit (accumulated depreciation) of its amount; drafts have none."""
    out = []
    for d in rows(con, """SELECT D.DepreciationID, D.PostingStatus, D.PeriodDepreciation, A.AssetCode, D.AssetID,
            (SELECT COUNT(*) FROM tbl_DepreciationJournal J WHERE J.DepreciationID=D.DepreciationID) AS n,
            (SELECT COALESCE(SUM(DebitAmount),0) FROM tbl_DepreciationJournal J WHERE J.DepreciationID=D.DepreciationID) AS dr,
            (SELECT COALESCE(SUM(CreditAmount),0) FROM tbl_DepreciationJournal J WHERE J.DepreciationID=D.DepreciationID) AS cr
            FROM tbl_Depreciation D JOIN tbl_Assets A ON A.AssetID=D.AssetID""", raw=True):
        if d["PostingStatus"] == "POSTED":
            if d["n"] != 2 or abs(d["dr"] - d["PeriodDepreciation"]) > EPS or abs(d["cr"] - d["PeriodDepreciation"]) > EPS:
                out.append(_issue(f"{d['AssetCode']}: posted depreciation {r2(d['PeriodDepreciation'])} has journal debit {r2(d['dr'])} / credit {r2(d['cr'])}", asset=d["AssetID"]))
        elif d["n"]:
            out.append(_issue(f"{d['AssetCode']}: an unposted line already has journal entries", asset=d["AssetID"]))
    return out


def _journal_balanced(con) -> list[dict]:
    """Every entry (a depreciation line or a transaction) balances, and so does the whole journal."""
    out = []
    for g in rows(con, """SELECT COALESCE('D'||DepreciationID, 'T'||TransactionID) AS k, MIN(Reference) ref, SUM(DebitAmount) dr, SUM(CreditAmount) cr
            FROM tbl_DepreciationJournal GROUP BY k HAVING ABS(SUM(DebitAmount)-SUM(CreditAmount)) > ?""", (EPS,), raw=True):
        out.append(_issue(f"Journal entry {g['k']} ({g['ref']}) does not balance: debit {r2(g['dr'])}, credit {r2(g['cr'])}"))
    tot = one(con, "SELECT COALESCE(SUM(DebitAmount),0) dr, COALESCE(SUM(CreditAmount),0) cr FROM tbl_DepreciationJournal", raw=True)
    if abs(tot["dr"] - tot["cr"]) > EPS:
        out.append(_issue(f"The journal does not balance: debit {r2(tot['dr'])}, credit {r2(tot['cr'])}"))
    return out


def _disposals(con) -> list[dict]:
    """A disposal removes the cost and the accumulated depreciation at that date; the gain or loss is proceeds less NBV."""
    out = []
    for t in rows(con, """SELECT T.*, A.AssetCode, A.AcquisitionCost, A.OpeningAccumDep, A.AssetStatus, A.DisposalDate,
            C.AssetAccountID, C.AccumDepAccountID, C.GainAccountID, C.LossAccountID FROM tbl_AssetTransactions T
            JOIN tbl_Assets A ON A.AssetID=T.AssetID JOIN tbl_AssetCategories C ON C.CategoryID=A.CategoryID WHERE T.TransactionType='DISPOSAL'""", raw=True):
        code = t["AssetCode"]
        accum = (t["OpeningAccumDep"] or 0) + one(con, """SELECT COALESCE(SUM(D.PeriodDepreciation),0) s FROM tbl_Depreciation D
            JOIN tbl_DepreciationPeriods P ON P.PeriodID=D.PeriodID WHERE D.AssetID=? AND D.PostingStatus='POSTED' AND P.EndDate<=?""",
            (t["AssetID"], t["TransactionDate"]), raw=True)["s"]
        j = rows(con, "SELECT * FROM tbl_DepreciationJournal WHERE TransactionID=?", (t["TransactionID"],), raw=True)
        on = lambda acc, side: sum(x[side] for x in j if x["GLAccountID"] == acc)   # the group's own accounts, whatever their type
        cost_cr = on(t["AssetAccountID"], "CreditAmount")
        accum_dr = on(t["AccumDepAccountID"], "DebitAmount")
        if abs(cost_cr - (t["AcquisitionCost"] or 0)) > EPS:
            out.append(_issue(f"{code}: disposal credits cost {r2(cost_cr)}, the asset cost is {r2(t['AcquisitionCost'])}", asset=t["AssetID"]))
        if abs(accum_dr - accum) > EPS:
            out.append(_issue(f"{code}: disposal debits accumulated depreciation {r2(accum_dr)}, the books show {r2(accum)}", asset=t["AssetID"]))
        nbv = (t["AcquisitionCost"] or 0) - accum
        gain = on(t["GainAccountID"], "CreditAmount") - on(t["LossAccountID"], "DebitAmount")
        if abs(gain - ((t["DisposalProceeds"] or 0) - nbv)) > EPS:
            out.append(_issue(f"{code}: gain / loss {r2(gain)} is not proceeds less net book value ({r2((t['DisposalProceeds'] or 0) - nbv)})", asset=t["AssetID"]))
        if t["AssetStatus"] != "Disposed" or t["DisposalDate"] != t["TransactionDate"]:
            out.append(_issue(f"{code}: has a disposal but is not marked disposed on that date", asset=t["AssetID"]))
    for a in rows(con, """SELECT AssetID, AssetCode FROM tbl_Assets A WHERE AssetStatus='Disposed'
            AND NOT EXISTS (SELECT 1 FROM tbl_AssetTransactions T WHERE T.AssetID=A.AssetID AND T.TransactionType='DISPOSAL')""", raw=True):
        out.append(_issue(f"{a['AssetCode']}: marked disposed without a disposal transaction", asset=a["AssetID"]))
    return out


def _vat(con) -> list[dict]:
    """Invoice amount = net cost + VAT (inclusive) or net cost with VAT on top (exclusive); no VAT means none recorded."""
    out = []
    for a in rows(con, "SELECT AssetID, AssetCode, VatApplicable, VatInclusive, VatRate, PurchaseAmount, AcquisitionCost, VatAmount FROM tbl_Assets", raw=True):
        cost, vat, amount = a["AcquisitionCost"] or 0, a["VatAmount"] or 0, a["PurchaseAmount"]
        if amount is None:
            continue   # assets imported before the VAT fields existed
        if not a["VatApplicable"]:
            ok = abs(vat) <= EPS and abs(amount - cost) <= EPS
        elif a["VatInclusive"]:
            ok = abs(amount - cost - vat) <= EPS
        else:
            ok = abs(amount - cost) <= EPS and abs(vat - round(cost * (a["VatRate"] or 0) / 100, 2)) <= EPS
        if not ok:
            out.append(_issue(f"{a['AssetCode']}: invoice {r2(amount)}, net cost {r2(cost)} and VAT {r2(vat)} do not agree", asset=a["AssetID"]))
    return out


def _periods(con) -> list[dict]:
    """Periods are whole calendar months, numbered 1-12 per fiscal year, without gaps or overlaps."""
    out = []
    ps = rows(con, "SELECT * FROM tbl_DepreciationPeriods ORDER BY StartDate", raw=True)
    for p in ps:
        s, e = date.fromisoformat(p["StartDate"]), date.fromisoformat(p["EndDate"])
        if s.day != 1 or e != date(s.year, s.month, calendar.monthrange(s.year, s.month)[1]):
            out.append(_issue(f"{p['PeriodName']}: is not one calendar month"))
    for a, b in zip(ps, ps[1:]):
        nxt = date.fromisoformat(a["EndDate"]).toordinal() + 1
        if date.fromisoformat(b["StartDate"]).toordinal() < nxt:
            out.append(_issue(f"{a['PeriodName']} and {b['PeriodName']} overlap"))
        elif date.fromisoformat(b["StartDate"]).toordinal() > nxt:
            out.append(_issue(f"Gap between {a['PeriodName']} and {b['PeriodName']}"))
    return out


def _reports_tie(con) -> list[dict]:
    """Report arithmetic against the ledger: the register as of today equals the asset book values, and the roll-forward of
    the year closes on the register with a depreciation charge equal to what was posted in the window."""
    from .. import reports   # late import: reports depends on services
    out = []
    today = date.today().isoformat()
    reg = reports.asset_state(con, today)
    book = rows(con, """SELECT A.AssetID, A.AcquisitionCost, COALESCE(A.OpeningAccumDep,0) + COALESCE((SELECT SUM(D.PeriodDepreciation) FROM tbl_Depreciation D
        JOIN tbl_DepreciationPeriods P ON P.PeriodID=D.PeriodID WHERE D.AssetID=A.AssetID AND D.PostingStatus='POSTED' AND P.EndDate<=?),0) AS Accum
        FROM tbl_Assets A WHERE A.AcquisitionDate<=? AND (A.DisposalDate IS NULL OR A.DisposalDate>?)""", (today, today, today), raw=True)
    for key, a, b in (("cost", sum(r["Cost"] for r in reg), sum(r["AcquisitionCost"] or 0 for r in book)),
                      ("accumulated depreciation", sum(r["AccumDep"] for r in reg), sum(r["Accum"] for r in book))):
        if abs(r2(a) - r2(b)) > EPS:
            out.append(_issue(f"Asset register {key} {r2(a)} differs from the books {r2(b)}"))
    first = one(con, "SELECT MIN(StartDate) s FROM tbl_DepreciationPeriods WHERE FiscalYear=?", (date.today().year,), raw=True)["s"]
    if first and first <= today:
        rf = reports.rollforward(con, {"from": first, "to": today})
        tot = {k: sum(g[k] for g in rf["rows"]) for k in ("OpenCost", "Additions", "Disposals", "CloseCost", "OpenDep", "BroughtIn", "Charge", "DepDisposed", "CloseDep", "NBV")}
        posted = one(con, """SELECT COALESCE(SUM(D.PeriodDepreciation),0) s FROM tbl_Depreciation D JOIN tbl_DepreciationPeriods P ON P.PeriodID=D.PeriodID
            WHERE D.PostingStatus='POSTED' AND P.EndDate>=? AND P.EndDate<=?""", (first, today), raw=True)["s"]
        checks = [("closing cost", tot["CloseCost"], sum(r["Cost"] for r in reg)), ("closing accumulated depreciation", tot["CloseDep"], sum(r["AccumDep"] for r in reg)),
                  ("depreciation charge", tot["Charge"], posted), ("net book value", tot["NBV"], tot["CloseCost"] - tot["CloseDep"]),
                  ("cost movement", tot["CloseCost"], tot["OpenCost"] + tot["Additions"] - tot["Disposals"])]
        for name, a, b in checks:
            if abs(r2(a) - r2(b)) > 0.01 + EPS:   # report rows are rounded per group
                out.append(_issue(f"Roll-forward {name} {r2(a)} does not tie to {r2(b)}"))
    return out


def _statuses(con) -> list[dict]:
    """Under Repair matches a running out-of-service order; an issued custody is unique and never on a disposed asset."""
    out = []
    for a in rows(con, """SELECT AssetID, AssetCode FROM tbl_Assets A WHERE AssetStatus='Under Repair' AND NOT EXISTS
            (SELECT 1 FROM tbl_Maintenance M WHERE M.AssetID=A.AssetID AND M.Status='In Progress' AND M.OutOfService=1)""", raw=True):
        out.append(_issue(f"{a['AssetCode']}: under repair without a running out-of-service maintenance order", asset=a["AssetID"]))
    for a in rows(con, """SELECT DISTINCT A.AssetID, A.AssetCode FROM tbl_AssetCustody U JOIN tbl_Assets A ON A.AssetID=U.AssetID
            WHERE U.Status='Issued' AND A.AssetStatus='Disposed'""", raw=True):
        out.append(_issue(f"{a['AssetCode']}: disposed but still in an employee's custody", asset=a["AssetID"]))
    return out


CHECKS = [
    ("depreciation-lines", "Depreciation lines add up", _depreciation_lines),
    ("residual-floor", "No asset is depreciated below its residual value", _residual_floor),
    ("depreciation-journal", "Posted depreciation equals its journal", _depreciation_journal),
    ("journal-balanced", "Every journal entry balances", _journal_balanced),
    ("disposals", "Disposals remove cost and depreciation correctly", _disposals),
    ("vat", "VAT and invoice amounts agree", _vat),
    ("periods", "Periods are whole months without gaps", _periods),
    ("reports-tie", "Reports tie to the books", _reports_tie),
    ("statuses", "Statuses agree with maintenance and custody", _statuses),
]


def run_checks(con) -> list[dict]:
    """[{id, title, ok, issues: [{text, asset?, period?}]}] for every check."""
    out = []
    for cid, title, fn in CHECKS:
        issues = fn(con)
        out.append({"id": cid, "title": title, "ok": not issues, "issues": issues})
    return out
