"""Gooya Asset - report builders. Every report returns
{title, params, columns:[{key,label,type}], rows:[...], group_by?, totals:[keys]}."""
from __future__ import annotations

from datetime import date

from .services import ApiError, get_settings, one, parse_date, r2, rows

REPORTS = [
    dict(id="asset-register", group="Fixed assets", params=["as_of", "category", "location", "costcenter", "status"]),
    dict(id="vat-purchases", group="Fixed assets", params=["from", "to", "vat"]),
    dict(id="asset-summary", group="Fixed assets", params=["as_of", "group_by"]),
    dict(id="rollforward", group="Fixed assets", params=["from", "to"]),
    dict(id="depreciation-schedule", group="Depreciation", params=["fiscal_year", "category"]),
    dict(id="depreciation-journal", group="Depreciation", params=["from", "to"]),
    dict(id="gl-balances", group="Depreciation", params=["as_of"]),
    dict(id="disposals", group="Transactions", params=["from", "to"]),
    dict(id="transactions", group="Transactions", params=["from", "to", "type"]),
    dict(id="fully-depreciated", group="Exceptions", params=["as_of"]),
    dict(id="warranty-expiry", group="Exceptions", params=["days"]),
    dict(id="custody-by-employee", group="Contacts", params=["from", "to", "employee", "cstatus"]),
    dict(id="employees-directory", group="Contacts", params=["sactive"]),
    dict(id="suppliers-directory", group="Suppliers", params=["sactive", "stype"]),
    dict(id="supplier-purchases", group="Suppliers", params=["from", "to", "supplier"]),
    dict(id="supplier-summary", group="Suppliers", params=["from", "to"]),
    dict(id="maintenance-history", group="Maintenance", params=["from", "to", "mstatus", "mtype", "category"]),
    dict(id="maintenance-cost", group="Maintenance", params=["from", "to", "mgroup"]),
    dict(id="maintenance-schedule", group="Maintenance", params=["days"]),
]


def _cols(*spec):
    return [dict(key=k, label=l, type=t) for k, l, t in spec]


def _as_of(p):
    return parse_date(p.get("as_of"), "As of date") or date.today().isoformat()


def asset_state(con, as_of: str) -> list[dict]:
    """Cost / accumulated depreciation / NBV of every asset at a given date."""
    accum = {r["AssetID"]: r["s"] for r in con.execute(
        """SELECT D.AssetID, SUM(D.PeriodDepreciation) s FROM tbl_Depreciation D JOIN tbl_DepreciationPeriods P ON P.PeriodID=D.PeriodID
           WHERE D.PostingStatus='POSTED' AND P.EndDate<=? GROUP BY D.AssetID""", (as_of,))}
    out = []
    for a in rows(con, """SELECT A.*, C.CategoryName, C.CategoryNameAr, L.LocationName, L.LocationNameAr, CC.CostCenterName, CC.CostCenterNameAr FROM tbl_Assets A
            LEFT JOIN tbl_AssetCategories C ON C.CategoryID=A.CategoryID LEFT JOIN tbl_Locations L ON L.LocationID=A.LocationID
            LEFT JOIN tbl_CostCenters CC ON CC.CostCenterID=A.CostCenterID WHERE A.AcquisitionDate<=? ORDER BY A.AssetCode""", (as_of,)):
        if a["DisposalDate"] and a["DisposalDate"] <= as_of:
            continue
        a["AccumDep"] = r2((a["OpeningAccumDep"] or 0) + (accum.get(a["AssetID"]) or 0))
        a["Cost"] = r2(a["AcquisitionCost"])
        a["NBV"] = r2(a["Cost"] - a["AccumDep"])
        a["VatStatus"] = "With VAT" if a.get("VatApplicable") else "No VAT"
        out.append(a)
    return out


def asset_register(con, p):
    d = _as_of(p)
    data = asset_state(con, d)
    for key, col in (("category", "CategoryID"), ("location", "LocationID"), ("costcenter", "CostCenterID")):
        if p.get(key):
            data = [a for a in data if str(a[col]) == str(p[key])]
    if p.get("status"):
        data = [a for a in data if a["AssetStatus"] == p["status"]]
    return dict(columns=_cols(("AssetCode", "Asset", "text"), ("AssetName", "Name", "text"), ("CategoryName", "Group", "text"),
                              ("LocationName", "Location", "text"), ("AcquisitionDate", "Acquired", "date"),
                              ("VatStatus", "VAT", "text"),
                              ("Cost", "Cost", "money"), ("AccumDep", "Accum. depreciation", "money"), ("NBV", "Net book value", "money")),
                rows=data, group_by="CategoryName", totals=["Cost", "AccumDep", "NBV"], subtitle=f"As of {d}")


def asset_summary(con, p):
    d = _as_of(p)
    gb = p.get("group_by") or "category"
    col, label = {"category": ("CategoryName", "Group"), "location": ("LocationName", "Location"),
                  "costcenter": ("CostCenterName", "Cost center")}.get(gb, ("CategoryName", "Group"))
    agg: dict[str, dict] = {}
    for a in asset_state(con, d):
        k = a[col] or "(none)"
        g = agg.setdefault(k, dict(k=k, Count=0, Cost=0, AccumDep=0, NBV=0))
        g["Count"] += 1; g["Cost"] += a["Cost"]; g["AccumDep"] += a["AccumDep"]; g["NBV"] += a["NBV"]
    data = [{**g, "Cost": r2(g["Cost"]), "AccumDep": r2(g["AccumDep"]), "NBV": r2(g["NBV"])} for g in sorted(agg.values(), key=lambda g: g["k"])]
    return dict(columns=_cols(("k", label, "text"), ("Count", "Assets", "int"), ("Cost", "Cost", "money"),
                              ("AccumDep", "Accum. depreciation", "money"), ("NBV", "Net book value", "money")),
                rows=data, totals=["Count", "Cost", "AccumDep", "NBV"], subtitle=f"As of {d}")


def rollforward(con, p):
    f = parse_date(p.get("from"), "From date", True)
    t = parse_date(p.get("to"), "To date", True)
    if f > t:
        raise ApiError("From date is after To date")
    prev = date.fromordinal(date.fromisoformat(f).toordinal() - 1).isoformat()
    keys = ["OpenCost", "Additions", "Disposals", "CloseCost", "OpenDep", "BroughtIn", "Charge", "DepDisposed", "CloseDep", "NBV"]
    agg = {c["CategoryID"]: dict(Group=c["CategoryName"], **{k: 0.0 for k in keys})
           for c in rows(con, "SELECT * FROM tbl_AssetCategories")}
    opening = {a["AssetID"]: a for a in asset_state(con, prev)}
    closing = {a["AssetID"]: a for a in asset_state(con, t)}
    for a in opening.values():
        g = agg[a["CategoryID"]]; g["OpenCost"] += a["Cost"]; g["OpenDep"] += a["AccumDep"]
    for aid, a in closing.items():
        g = agg[a["CategoryID"]]; g["CloseDep"] += a["AccumDep"]
        if aid not in opening:
            g["Additions"] += a["Cost"]; g["BroughtIn"] += a["OpeningAccumDep"] or 0
    for aid, a in opening.items():
        if aid in closing:
            continue
        g = agg[a["CategoryID"]]; g["Disposals"] += a["Cost"]
        acc = one(con, """SELECT SUM(J.DebitAmount) s FROM tbl_DepreciationJournal J JOIN tbl_GLAccounts G ON G.GLAccountID=J.GLAccountID
                          JOIN tbl_AssetTransactions T ON T.TransactionID=J.TransactionID
                          WHERE T.AssetID=? AND T.TransactionType='DISPOSAL' AND G.AccountType LIKE 'ACCUM%'""", (aid,))["s"]
        g["DepDisposed"] += acc or 0
    data = []
    for g in agg.values():
        g["CloseCost"] = g["OpenCost"] + g["Additions"] - g["Disposals"]
        g["NBV"] = g["CloseCost"] - g["CloseDep"]
        g["Charge"] = g["CloseDep"] - g["OpenDep"] - g["BroughtIn"] + g["DepDisposed"]
        if any(abs(g[k]) > 0.004 for k in keys):
            data.append({k: (v if k == "Group" else r2(v)) for k, v in g.items()})
    data.sort(key=lambda g: g["Group"])
    return dict(columns=_cols(("Group", "Group", "text"), ("OpenCost", "Opening cost", "money"), ("Additions", "Additions", "money"),
                              ("Disposals", "Disposals", "money"), ("CloseCost", "Closing cost", "money"),
                              ("OpenDep", "Opening accum. dep.", "money"), ("BroughtIn", "Dep. on additions", "money"),
                              ("Charge", "Depreciation charge", "money"), ("DepDisposed", "Dep. on disposals", "money"),
                              ("CloseDep", "Closing accum. dep.", "money"), ("NBV", "Net book value", "money")),
                rows=data, totals=keys, subtitle=f"{f} to {t}")


def depreciation_schedule(con, p):
    fy = int(p.get("fiscal_year") or date.today().year)
    sql = """SELECT A.AssetCode, A.AssetName, A.AssetNameAr, C.CategoryName, C.CategoryNameAr, P.PeriodName, P.PeriodNumber, P.PeriodStatus, D.AcquisitionCost,
             D.OpeningAccumDep, D.PeriodDepreciation, D.ClosingAccumDep, D.ClosingNBV, D.PostingStatus
             FROM tbl_Depreciation D JOIN tbl_Assets A ON A.AssetID=D.AssetID JOIN tbl_DepreciationPeriods P ON P.PeriodID=D.PeriodID
             LEFT JOIN tbl_AssetCategories C ON C.CategoryID=A.CategoryID WHERE P.FiscalYear=?"""
    args = [fy]
    if p.get("category"):
        sql += " AND A.CategoryID=?"; args.append(p["category"])
    data = rows(con, sql + " ORDER BY A.AssetCode, P.PeriodNumber", args)
    return dict(columns=_cols(("AssetCode", "Asset", "text"), ("AssetName", "Name", "text"), ("PeriodName", "Period", "text"),
                              ("AcquisitionCost", "Cost", "money"), ("OpeningAccumDep", "Opening accum. dep.", "money"),
                              ("PeriodDepreciation", "Depreciation", "money"), ("ClosingAccumDep", "Closing accum. dep.", "money"),
                              ("ClosingNBV", "Net book value", "money"), ("PostingStatus", "Status", "text")),
                rows=data, group_by="AssetCode", totals=["PeriodDepreciation"], subtotal_only=["PeriodDepreciation"],
                subtitle=f"Fiscal year {fy}")


def depreciation_journal(con, p):
    f = parse_date(p.get("from"), "From date") or "1900-01-01"
    t = parse_date(p.get("to"), "To date") or "2999-12-31"
    data = rows(con, """SELECT J.JournalDate, J.JournalType, J.Reference, G.AccountCode, G.AccountName, G.AccountNameAr, J.Description, J.DebitAmount, J.CreditAmount
            FROM tbl_DepreciationJournal J LEFT JOIN tbl_GLAccounts G ON G.GLAccountID=J.GLAccountID
            WHERE J.JournalDate BETWEEN ? AND ? ORDER BY J.JournalDate, J.JournalID""", (f, t))
    return dict(columns=_cols(("JournalDate", "Date", "date"), ("JournalType", "Type", "text"), ("Reference", "Asset", "text"),
                              ("AccountCode", "Account", "text"), ("AccountName", "Account name", "text"),
                              ("Description", "Description", "text"), ("DebitAmount", "Debit", "money"), ("CreditAmount", "Credit", "money")),
                rows=data, totals=["DebitAmount", "CreditAmount"], subtitle=f"{f if f > '1901' else 'Beginning'} to {t if t < '2999' else 'today'}")


def gl_balances(con, p):
    d = _as_of(p)
    data = rows(con, """SELECT G.AccountCode, G.AccountName, G.AccountNameAr, G.AccountType, SUM(J.DebitAmount) Debit, SUM(J.CreditAmount) Credit,
            SUM(J.DebitAmount)-SUM(J.CreditAmount) Balance FROM tbl_DepreciationJournal J JOIN tbl_GLAccounts G ON G.GLAccountID=J.GLAccountID
            WHERE J.JournalDate<=? GROUP BY G.GLAccountID ORDER BY G.AccountCode""", (d,))
    for r in data:
        for k in ("Debit", "Credit", "Balance"):
            r[k] = r2(r[k])
    return dict(columns=_cols(("AccountCode", "Account", "text"), ("AccountName", "Account name", "text"), ("Debit", "Debit", "money"),
                              ("Credit", "Credit", "money"), ("Balance", "Balance", "money")),
                rows=data, totals=["Debit", "Credit", "Balance"], subtitle=f"Fixed asset postings as of {d}")


def disposals(con, p):
    f = parse_date(p.get("from"), "From date") or "1900-01-01"
    t = parse_date(p.get("to"), "To date") or date.today().isoformat()
    out = []
    for r in rows(con, """SELECT T.*, A.AssetCode, A.AssetName, A.AssetNameAr, A.AcquisitionDate, A.OpeningAccumDep, C.CategoryName, C.CategoryNameAr FROM tbl_AssetTransactions T
            JOIN tbl_Assets A ON A.AssetID=T.AssetID LEFT JOIN tbl_AssetCategories C ON C.CategoryID=A.CategoryID
            WHERE T.TransactionType='DISPOSAL' AND T.TransactionDate BETWEEN ? AND ? ORDER BY T.TransactionDate""", (f, t)):
        acc = one(con, "SELECT SUM(DebitAmount) s FROM tbl_DepreciationJournal J JOIN tbl_GLAccounts G ON G.GLAccountID=J.GLAccountID "
                       "WHERE J.TransactionID=? AND G.AccountType LIKE 'ACCUM%'", (r["TransactionID"],))["s"] or 0
        nbv = r2(r["Amount"] - acc)
        out.append(dict(TransactionDate=r["TransactionDate"], AssetCode=r["AssetCode"], AssetName=r["AssetName"],
                        CategoryName=r["CategoryName"], Cost=r2(r["Amount"]), AccumDep=r2(acc), NBV=nbv,
                        Proceeds=r2(r["DisposalProceeds"]), GainLoss=r2((r["DisposalProceeds"] or 0) - nbv),
                        DisposalReason=r["DisposalReason"]))
    return dict(columns=_cols(("TransactionDate", "Date", "date"), ("AssetCode", "Asset", "text"), ("AssetName", "Name", "text"),
                              ("CategoryName", "Group", "text"), ("Cost", "Cost", "money"), ("AccumDep", "Accum. dep.", "money"),
                              ("NBV", "NBV at disposal", "money"), ("Proceeds", "Proceeds", "money"),
                              ("GainLoss", "Gain / (loss)", "money"), ("DisposalReason", "Reason", "text")),
                rows=out, totals=["Cost", "AccumDep", "NBV", "Proceeds", "GainLoss"], subtitle=f"{f if f > '1901' else 'Beginning'} to {t}")


def transactions_report(con, p):
    f = parse_date(p.get("from"), "From date") or "1900-01-01"
    t = parse_date(p.get("to"), "To date") or "2999-12-31"
    sql = """SELECT T.TransactionDate, T.TransactionType, A.AssetCode, A.AssetName, A.AssetNameAr, T.Amount, T.DisposalProceeds,
             FL.LocationName FromLocation, FL.LocationNameAr FromLocationAr, TL.LocationName ToLocation, TL.LocationNameAr ToLocationAr, T.ReferenceNumber, T.Notes, T.CreatedBy
             FROM tbl_AssetTransactions T JOIN tbl_Assets A ON A.AssetID=T.AssetID
             LEFT JOIN tbl_Locations FL ON FL.LocationID=T.FromLocationID LEFT JOIN tbl_Locations TL ON TL.LocationID=T.ToLocationID
             WHERE T.TransactionDate BETWEEN ? AND ?"""
    args = [f, t]
    if p.get("type"):
        sql += " AND T.TransactionType=?"; args.append(p["type"])
    return dict(columns=_cols(("TransactionDate", "Date", "date"), ("TransactionType", "Type", "text"), ("AssetCode", "Asset", "text"),
                              ("AssetName", "Name", "text"), ("Amount", "Amount", "money"), ("FromLocation", "From", "text"),
                              ("ToLocation", "To", "text"), ("ReferenceNumber", "Reference", "text"), ("Notes", "Notes", "text"),
                              ("CreatedBy", "User", "text")),
                rows=rows(con, sql + " ORDER BY T.TransactionDate, T.TransactionID", args), totals=[],
                subtitle=f"{f if f > '1901' else 'Beginning'} to {t if t < '2999' else 'today'}")


def fully_depreciated(con, p):
    d = _as_of(p)
    data = [a for a in asset_state(con, d) if a["Cost"] > 0 and a["NBV"] <= (a["ResidualValue"] or 0) + 0.005]
    return dict(columns=_cols(("AssetCode", "Asset", "text"), ("AssetName", "Name", "text"), ("CategoryName", "Group", "text"),
                              ("AcquisitionDate", "Acquired", "date"), ("Cost", "Cost", "money"), ("AccumDep", "Accum. dep.", "money"),
                              ("NBV", "Net book value", "money")), rows=data, totals=["Cost", "AccumDep", "NBV"], subtitle=f"As of {d}")


def warranty_expiry(con, p):
    days = int(p.get("days") or 90)
    data = rows(con, """SELECT A.AssetCode, A.AssetName, A.AssetNameAr, C.CategoryName, C.CategoryNameAr, A.SupplierName, A.WarrantyExpiryDate,
            CAST(julianday(A.WarrantyExpiryDate)-julianday('now') AS INTEGER) DaysLeft FROM tbl_Assets A
            LEFT JOIN tbl_AssetCategories C ON C.CategoryID=A.CategoryID WHERE A.AssetStatus<>'Disposed' AND A.WarrantyExpiryDate IS NOT NULL
            AND A.WarrantyExpiryDate<=date('now',?) ORDER BY A.WarrantyExpiryDate""", (f"+{days} day",))
    return dict(columns=_cols(("AssetCode", "Asset", "text"), ("AssetName", "Name", "text"), ("CategoryName", "Group", "text"),
                              ("SupplierName", "Supplier", "text"), ("WarrantyExpiryDate", "Warranty expiry", "date"),
                              ("DaysLeft", "Days left", "int")), rows=data, totals=[], subtitle=f"Expiring within {days} days")


def _mdate(p, key, default):
    return parse_date(p.get(key), key.title() + " date") or default


_MDATE = "COALESCE(M.CompletionDate, M.StartDate, M.ScheduledDate)"


def maintenance_history(con, p):
    f, t = _mdate(p, "from", "1900-01-01"), _mdate(p, "to", "2999-12-31")
    sql = f"""SELECT M.MaintenanceNo, {_MDATE} AS EventDate, M.AssetID, A.AssetCode, A.AssetName, A.AssetNameAr, M.MaintenanceType, M.Title,
              M.Priority, M.Status, M.Vendor, M.Cost FROM tbl_Maintenance M JOIN tbl_Assets A ON A.AssetID=M.AssetID
              WHERE {_MDATE} BETWEEN ? AND ?"""
    args = [f, t]
    for key, col in (("mstatus", "M.Status"), ("mtype", "M.MaintenanceType"), ("category", "A.CategoryID")):
        if p.get(key):
            sql += f" AND {col}=?"
            args.append(p[key])
    data = rows(con, sql + " ORDER BY A.AssetCode, EventDate, M.MaintenanceID", args)
    for r in data:
        r["Asset"] = f"{r['AssetCode']} - {r['AssetName']}"
    return dict(columns=_cols(("MaintenanceNo", "Order", "text"), ("EventDate", "Date", "date"), ("MaintenanceType", "Type", "text"),
                              ("Title", "Title", "text"), ("Priority", "Priority", "text"), ("Status", "Status", "text"),
                              ("Vendor", "Vendor", "text"), ("Cost", "Cost", "money")),
                rows=data, group_by="Asset", totals=["Cost"],
                subtitle=f"{f if f > '1901' else 'Beginning'} to {t if t < '2999' else 'today'}")


def maintenance_cost(con, p):
    f, t = _mdate(p, "from", "1900-01-01"), _mdate(p, "to", "2999-12-31")
    gb = p.get("mgroup") or "asset"
    data = rows(con, f"""SELECT M.MaintenanceID, M.MaintenanceType, M.Cost, A.AssetCode, A.AssetName, A.AssetNameAr, C.CategoryName, C.CategoryNameAr
            FROM tbl_Maintenance M JOIN tbl_Assets A ON A.AssetID=M.AssetID LEFT JOIN tbl_AssetCategories C ON C.CategoryID=A.CategoryID
            WHERE M.Status='Completed' AND M.CompletionDate BETWEEN ? AND ?""", (f, t))
    agg: dict[str, dict] = {}
    for r in data:
        k = {"asset": f"{r['AssetCode']} - {r['AssetName']}", "category": r["CategoryName"] or "(none)", "type": r["MaintenanceType"]}.get(gb, r["AssetCode"])
        g = agg.setdefault(k, dict(k=k, Orders=0, Cost=0.0))
        g["Orders"] += 1
        g["Cost"] += r["Cost"] or 0
    out = []
    for g in sorted(agg.values(), key=lambda x: -x["Cost"]):
        out.append(dict(k=g["k"], Orders=g["Orders"], Cost=r2(g["Cost"]), Average=r2(g["Cost"] / g["Orders"])))
    label = {"asset": "Asset", "category": "Group", "type": "Type"}.get(gb, "Asset")
    return dict(columns=_cols(("k", label, "text"), ("Orders", "Completed orders", "int"), ("Cost", "Total cost", "money"), ("Average", "Average cost", "money")),
                rows=out, totals=["Orders", "Cost"], subtitle=f"{f if f > '1901' else 'Beginning'} to {t if t < '2999' else 'today'}")


def maintenance_schedule(con, p):
    days = int(p.get("days") or 30)
    today = date.today().isoformat()
    limit = date.fromordinal(date.today().toordinal() + days).isoformat()
    out = []
    for r in rows(con, """SELECT M.MaintenanceNo, M.ScheduledDate AS DueDate, A.AssetCode, A.AssetName, A.AssetNameAr, M.MaintenanceType, M.Title,
            M.Priority, M.Status FROM tbl_Maintenance M JOIN tbl_Assets A ON A.AssetID=M.AssetID
            WHERE M.Status IN ('Planned','In Progress') AND M.ScheduledDate<=?""", (limit,)):
        r["Source"] = "Open order"
        out.append(r)
    for r in rows(con, """SELECT M.MaintenanceNo, M.NextDueDate AS DueDate, A.AssetCode, A.AssetName, A.AssetNameAr, M.MaintenanceType, M.Title,
            M.Priority, 'Next due' AS Status FROM tbl_Maintenance M JOIN tbl_Assets A ON A.AssetID=M.AssetID
            WHERE M.Status='Completed' AND M.NextDueDate IS NOT NULL AND M.NextDueDate<=? AND A.AssetStatus<>'Disposed'
            AND NOT EXISTS (SELECT 1 FROM tbl_Maintenance N WHERE N.AssetID=M.AssetID AND N.Status IN ('Planned','In Progress'))
            AND M.MaintenanceID=(SELECT MAX(X.MaintenanceID) FROM tbl_Maintenance X WHERE X.AssetID=M.AssetID AND X.Status='Completed' AND X.NextDueDate IS NOT NULL)""", (limit,)):
        r["Source"] = "Recurring due date"
        out.append(r)
    for r in out:
        r["DaysToDue"] = date.fromisoformat(r["DueDate"]).toordinal() - date.today().toordinal()
        r["Timing"] = "Overdue" if r["DueDate"] < today else "Due"
    out.sort(key=lambda r: r["DueDate"])
    return dict(columns=_cols(("DueDate", "Due date", "date"), ("DaysToDue", "Days to due", "int"), ("Timing", "Timing", "text"),
                              ("AssetCode", "Asset", "text"), ("AssetName", "Name", "text"), ("MaintenanceType", "Type", "text"),
                              ("Title", "Title", "text"), ("Priority", "Priority", "text"), ("Status", "Status", "text"),
                              ("Source", "Source", "text"), ("MaintenanceNo", "Order", "text")),
                rows=out, totals=[], subtitle=f"Due within {days} days")


def suppliers_directory(con, p):
    sql, args = "SELECT * FROM tbl_Suppliers WHERE 1=1", []
    if p.get("sactive") in ("1", "0"):
        sql += " AND IsActive=?"
        args.append(int(p["sactive"]))
    if p.get("stype"):
        sql += " AND SupplierType=?"
        args.append(p["stype"])
    data = rows(con, sql + " ORDER BY SupplierName", args)
    for r in data:
        r["Status"] = "Active" if r["IsActive"] else "Inactive"
    return dict(columns=_cols(("SupplierCode", "Code", "text"), ("SupplierName", "Name", "text"), ("SupplierType", "Type", "text"),
                              ("ContactPerson", "Contact person", "text"), ("Phone", "Phone", "text"), ("Mobile", "Mobile", "text"),
                              ("Email", "Email", "text"), ("City", "City", "text"), ("Country", "Country", "text"),
                              ("TaxNumber", "Tax number", "text"), ("PaymentTerms", "Payment terms", "text"), ("Status", "Status", "text")),
                rows=data, totals=[], subtitle=f"{len(data)} suppliers")


def supplier_purchases(con, p):
    f, t = _mdate(p, "from", "1900-01-01"), _mdate(p, "to", "2999-12-31")
    sql = """SELECT S.SupplierID, S.SupplierCode, S.SupplierName, S.SupplierNameAr, A.AssetCode, A.AssetName, A.AssetNameAr, C.CategoryName, C.CategoryNameAr,
             A.AcquisitionDate, A.InvoiceNumber, A.PurchaseOrderNumber, A.AcquisitionCost
             FROM tbl_Assets A JOIN tbl_Suppliers S ON S.SupplierID=A.SupplierID LEFT JOIN tbl_AssetCategories C ON C.CategoryID=A.CategoryID
             WHERE A.AcquisitionDate BETWEEN ? AND ?"""
    args = [f, t]
    if p.get("supplier"):
        sql += " AND S.SupplierID=?"
        args.append(p["supplier"])
    data = rows(con, sql + " ORDER BY S.SupplierName, A.AcquisitionDate", args)
    for r in data:
        r["Supplier"] = f"{r['SupplierCode']} - {r['SupplierName']}"
    return dict(columns=_cols(("AcquisitionDate", "Date", "date"), ("AssetCode", "Asset", "text"), ("AssetName", "Name", "text"),
                              ("CategoryName", "Group", "text"), ("InvoiceNumber", "Invoice", "text"), ("PurchaseOrderNumber", "Purchase order", "text"),
                              ("AcquisitionCost", "Cost", "money")),
                rows=data, group_by="Supplier", totals=["AcquisitionCost"],
                subtitle=f"{f if f > '1901' else 'Beginning'} to {t if t < '2999' else 'today'}")


def supplier_summary(con, p):
    f, t = _mdate(p, "from", "1900-01-01"), _mdate(p, "to", "2999-12-31")
    data = rows(con, """SELECT S.SupplierCode, S.SupplierName, S.SupplierNameAr, S.SupplierType,
        (SELECT COUNT(*) FROM tbl_Assets A WHERE A.SupplierID=S.SupplierID AND A.AcquisitionDate BETWEEN ? AND ?) AS Assets,
        (SELECT COALESCE(SUM(A.AcquisitionCost),0) FROM tbl_Assets A WHERE A.SupplierID=S.SupplierID AND A.AcquisitionDate BETWEEN ? AND ?) AS Purchases,
        (SELECT COUNT(*) FROM tbl_Maintenance M WHERE M.SupplierID=S.SupplierID AND M.Status='Completed' AND M.CompletionDate BETWEEN ? AND ?) AS Orders,
        (SELECT COALESCE(SUM(M.Cost),0) FROM tbl_Maintenance M WHERE M.SupplierID=S.SupplierID AND M.Status='Completed' AND M.CompletionDate BETWEEN ? AND ?) AS MaintCost
        FROM tbl_Suppliers S ORDER BY S.SupplierName""", (f, t) * 4)
    data = [r for r in data if r["Assets"] or r["Orders"]]
    for r in data:
        r["Purchases"], r["MaintCost"] = r2(r["Purchases"]), r2(r["MaintCost"])
        r["Total"] = r2(r["Purchases"] + r["MaintCost"])
    data.sort(key=lambda r: -r["Total"])
    return dict(columns=_cols(("SupplierCode", "Code", "text"), ("SupplierName", "Supplier", "text"), ("SupplierType", "Type", "text"),
                              ("Assets", "Assets purchased", "int"), ("Purchases", "Purchases", "money"), ("Orders", "Maintenance orders", "int"),
                              ("MaintCost", "Maintenance cost", "money"), ("Total", "Total spend", "money")),
                rows=data, totals=["Assets", "Purchases", "Orders", "MaintCost", "Total"],
                subtitle=f"{f if f > '1901' else 'Beginning'} to {t if t < '2999' else 'today'}")


def vat_purchases(con, p):
    f, t = _mdate(p, "from", "1900-01-01"), _mdate(p, "to", "2999-12-31")
    sql = """SELECT A.AssetCode, A.AssetName, A.AssetNameAr, A.AcquisitionDate, A.InvoiceNumber, A.SupplierName, SP.SupplierNameAr, A.VatApplicable,
             A.VatInclusive, A.VatRate, A.PurchaseAmount, A.AcquisitionCost, A.VatAmount FROM tbl_Assets A
             LEFT JOIN tbl_Suppliers SP ON SP.SupplierID=A.SupplierID WHERE A.AcquisitionDate BETWEEN ? AND ?"""
    args = [f, t]
    if p.get("vat") in ("1", "0"):
        sql += " AND A.VatApplicable=?"
        args.append(int(p["vat"]))
    data = rows(con, sql + " ORDER BY A.AcquisitionDate, A.AssetCode", args)
    for r in data:
        r["VatStatus"] = "With VAT" if r["VatApplicable"] else "No VAT"
        r["Basis"] = ("Inclusive" if r["VatInclusive"] else "Exclusive") if r["VatApplicable"] else ""
        r["Gross"] = r2((r["AcquisitionCost"] or 0) + (r["VatAmount"] or 0))
    return dict(columns=_cols(("AcquisitionDate", "Date", "date"), ("AssetCode", "Asset", "text"), ("AssetName", "Name", "text"),
                              ("SupplierName", "Supplier", "text"), ("InvoiceNumber", "Invoice", "text"), ("VatStatus", "VAT", "text"),
                              ("Basis", "Invoice basis", "text"), ("VatRate", "VAT rate", "pct"), ("AcquisitionCost", "Net cost", "money"),
                              ("VatAmount", "VAT amount", "money"), ("Gross", "Total with VAT", "money")),
                rows=data, totals=["AcquisitionCost", "VatAmount", "Gross"],
                subtitle=f"{f if f > '1901' else 'Beginning'} to {t if t < '2999' else 'today'}")


def custody_by_employee(con, p):
    f, t = _mdate(p, "from", "1900-01-01"), _mdate(p, "to", "2999-12-31")
    sql = """SELECT U.CustodyNo, U.IssueDate, U.ReturnDate, U.Status, U.ConditionOnIssue, U.ConditionOnReturn, U.AssetID, A.AssetCode, A.AssetName, A.AssetNameAr,
             A.SerialNumber, C.CategoryName, C.CategoryNameAr, E.EmployeeCode, E.EmployeeName, E.EmployeeNameAr, E.Department
             FROM tbl_AssetCustody U JOIN tbl_Assets A ON A.AssetID=U.AssetID JOIN tbl_Employees E ON E.EmployeeID=U.EmployeeID
             LEFT JOIN tbl_AssetCategories C ON C.CategoryID=A.CategoryID WHERE U.IssueDate BETWEEN ? AND ?"""
    args = [f, t]
    if p.get("employee"):
        sql += " AND U.EmployeeID=?"
        args.append(p["employee"])
    if p.get("cstatus") in ("Issued", "Returned"):
        sql += " AND U.Status=?"
        args.append(p["cstatus"])
    data = rows(con, sql + " ORDER BY E.EmployeeName, U.IssueDate", args)
    for r in data:
        r["Employee"] = f"{r['EmployeeCode']} - {r['EmployeeName']}" + (f" ({r['Department']})" if r["Department"] else "")
    return dict(columns=_cols(("CustodyNo", "Custody", "text"), ("AssetCode", "Asset", "text"), ("AssetName", "Name", "text"), ("CategoryName", "Group", "text"),
                              ("SerialNumber", "Serial number", "text"), ("IssueDate", "Issued", "date"), ("ReturnDate", "Returned", "date"),
                              ("Status", "Status", "text"), ("ConditionOnIssue", "Condition on issue", "text")),
                rows=data, group_by="Employee", totals=[], subtitle=f"{f if f > '1901' else 'Beginning'} to {t if t < '2999' else 'today'}")


def employees_directory(con, p):
    sql, args = "SELECT * FROM tbl_Employees WHERE 1=1", []
    if p.get("sactive") in ("1", "0"):
        sql += " AND IsActive=?"
        args.append(int(p["sactive"]))
    data = rows(con, sql + " ORDER BY EmployeeName", args)
    for r in data:
        r["Status"] = "Active" if r["IsActive"] else "Inactive"
        r["Held"] = con.execute("SELECT COUNT(*) FROM tbl_AssetCustody WHERE EmployeeID=? AND Status='Issued'", (r["EmployeeID"],)).fetchone()[0]
    return dict(columns=_cols(("EmployeeCode", "Code", "text"), ("EmployeeName", "Name", "text"), ("JobTitle", "Job title", "text"), ("Department", "Department", "text"),
                              ("Mobile", "Mobile", "text"), ("Email", "Email", "text"), ("Held", "Assets held", "int"), ("Status", "Status", "text")),
                rows=data, totals=["Held"], subtitle=f"{len(data)} employees")


BUILDERS = {"custody-by-employee": custody_by_employee, "employees-directory": employees_directory,
            "vat-purchases": vat_purchases,
            "suppliers-directory": suppliers_directory, "supplier-purchases": supplier_purchases, "supplier-summary": supplier_summary,
            "maintenance-history": maintenance_history, "maintenance-cost": maintenance_cost, "maintenance-schedule": maintenance_schedule,
            "asset-register": asset_register, "asset-summary": asset_summary, "rollforward": rollforward,
            "depreciation-schedule": depreciation_schedule, "depreciation-journal": depreciation_journal,
            "gl-balances": gl_balances, "disposals": disposals, "transactions": transactions_report,
            "fully-depreciated": fully_depreciated, "warranty-expiry": warranty_expiry}


def run_report(con, report_id: str, params: dict) -> dict:
    fn = BUILDERS.get(report_id)
    if not fn:
        raise ApiError("Unknown report", 404)
    res = fn(con, params)
    res.update(id=report_id, params=params, company=get_settings(con).get("CompanyName", ""),
               currency=get_settings(con).get("DefaultCurrency", ""), generated=date.today().isoformat())
    return res
