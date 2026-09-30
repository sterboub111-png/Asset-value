"""Fixed assets: register, create/update/delete, status, transfers."""
from __future__ import annotations

import re
import sqlite3
from datetime import date
from typing import Any

from .files import _remove_file
from .common import ASSET_STATUSES, ApiError, _ctx, actor, audit, now, num, one, parse_date, r2, rows, to_int
from .custody import list_custody
from .maintenance import list_maintenance
from .settings import get_settings

# ---------------------------------------------------------------- assets
ASSET_FIELDS = ["AssetName", "AssetNameAr", "AssetDescription", "CategoryID", "AcquisitionDate", "InServiceDate",
                "DepreciationStartDate", "AcquisitionCost", "ResidualValue", "UsefulLifeYears", "DepreciationRate",
                "MethodID", "OpeningAccumDep", "LocationID", "CostCenterID", "ResponsiblePerson", "SupplierName",
                "InvoiceNumber", "PurchaseOrderNumber", "SerialNumber", "ModelNumber", "Manufacturer",
                "WarrantyExpiryDate", "Notes"]

BOOK_SQL = """
SELECT A.*, C.CategoryCode, C.CategoryName, C.CategoryNameAr, M.MethodCode, M.MethodName, M.MethodNameAr,
       L.LocationName, L.LocationNameAr, L.LocationCode, CC.CostCenterName, CC.CostCenterNameAr, CC.CostCenterCode, SP.SupplierNameAr,
       (SELECT E.EmployeeName FROM tbl_AssetCustody U JOIN tbl_Employees E ON E.EmployeeID=U.EmployeeID WHERE U.AssetID=A.AssetID AND U.Status='Issued') AS CustodianName,
       (SELECT E.EmployeeNameAr FROM tbl_AssetCustody U JOIN tbl_Employees E ON E.EmployeeID=U.EmployeeID WHERE U.AssetID=A.AssetID AND U.Status='Issued') AS CustodianNameAr,
       COALESCE(A.OpeningAccumDep,0) + COALESCE((SELECT SUM(PeriodDepreciation) FROM tbl_Depreciation D
            WHERE D.AssetID=A.AssetID AND D.PostingStatus='POSTED'),0) AS AccumDep
FROM tbl_Assets A
LEFT JOIN tbl_AssetCategories C ON C.CategoryID=A.CategoryID
LEFT JOIN tbl_DepreciationMethods M ON M.MethodID=A.MethodID
LEFT JOIN tbl_Locations L ON L.LocationID=A.LocationID
LEFT JOIN tbl_CostCenters CC ON CC.CostCenterID=A.CostCenterID
LEFT JOIN tbl_Suppliers SP ON SP.SupplierID=A.SupplierID
"""


def _with_nbv(a: dict) -> dict:
    a["AccumDep"] = r2(a["AccumDep"])
    a["NBV"] = r2((a["AcquisitionCost"] or 0) - a["AccumDep"])
    return a


def list_assets(con, q: str = "", status: str = "", category: str = "") -> list[dict]:
    sql, args = BOOK_SQL + " WHERE 1=1", []
    if status:
        sql += " AND A.AssetStatus=?"
        args.append(status)
    if category:
        sql += " AND A.CategoryID=?"
        args.append(category)
    if q:
        sql += " AND (A.AssetCode LIKE ? OR A.AssetName LIKE ? OR A.AssetNameAr LIKE ? OR A.SerialNumber LIKE ?)"
        args += [f"%{q}%"] * 4
    return [_with_nbv(a) for a in rows(con, sql + " ORDER BY A.AssetCode", args)]


def get_asset(con, asset_id: int) -> dict:
    a = one(con, BOOK_SQL + " WHERE A.AssetID=?", (asset_id,), raw=True)
    if not a:
        raise ApiError("Asset not found", 404)
    for k in ("CategoryName", "MethodName", "LocationName", "CostCenterName"):
        if getattr(_ctx, "lang", "en") == "ar" and a.get(k + "Ar"):
            a[k] = a[k + "Ar"]
    _with_nbv(a)
    a["transactions"] = rows(con, """
        SELECT T.*, FL.LocationName FromLocation, FL.LocationNameAr FromLocationAr, TL.LocationName ToLocation, TL.LocationNameAr ToLocationAr,
               FC.CostCenterName FromCostCenter, FC.CostCenterNameAr FromCostCenterAr, TC.CostCenterName ToCostCenter, TC.CostCenterNameAr ToCostCenterAr
        FROM tbl_AssetTransactions T
        LEFT JOIN tbl_Locations FL ON FL.LocationID=T.FromLocationID
        LEFT JOIN tbl_Locations TL ON TL.LocationID=T.ToLocationID
        LEFT JOIN tbl_CostCenters FC ON FC.CostCenterID=T.FromCostCenterID
        LEFT JOIN tbl_CostCenters TC ON TC.CostCenterID=T.ToCostCenterID
        WHERE T.AssetID=? ORDER BY T.TransactionDate DESC, T.TransactionID DESC""", (asset_id,))
    a["depreciation"] = rows(con, """
        SELECT D.*, P.PeriodName, P.StartDate, P.EndDate, P.PeriodStatus FROM tbl_Depreciation D
        JOIN tbl_DepreciationPeriods P ON P.PeriodID=D.PeriodID WHERE D.AssetID=? ORDER BY P.StartDate""", (asset_id,))
    a["attachments"] = rows(con, "SELECT * FROM tbl_AssetAttachments WHERE AssetID=? ORDER BY AttachmentID DESC", (asset_id,))
    a["maintenance"] = list_maintenance(con, asset=str(asset_id))
    a["custody"] = list_custody(con, asset=str(asset_id))
    a["has_posted"] = any(d["PostingStatus"] == "POSTED" for d in a["depreciation"])
    return a


def next_asset_code(con, category_id: int | str | None = None) -> str:
    """Numbering per fixed asset group: <group code>-0001, <group code>-0002 …"""
    cat = one(con, "SELECT CategoryCode FROM tbl_AssetCategories WHERE CategoryID=?", (category_id or 0,), raw=True)
    if not cat or not (cat["CategoryCode"] or "").strip():
        raise ApiError("Fixed asset group is required")
    prefix = cat["CategoryCode"].strip()
    mx = 0
    for r in con.execute("SELECT AssetCode FROM tbl_Assets WHERE AssetCode LIKE ?", (prefix + "-%",)):
        m = re.fullmatch(re.escape(prefix) + r"-(\d+)", r["AssetCode"])
        if m:
            mx = max(mx, int(m.group(1)))
    return f"{prefix}-{mx + 1:04d}"


def _clean_asset(con, data: dict, existing: dict | None) -> dict:
    v: dict[str, Any] = {}
    v["AssetName"] = (data.get("AssetName") or "").strip()
    if not v["AssetName"]:
        raise ApiError("Asset name is required")
    v["AssetNameAr"] = (data.get("AssetNameAr") or "").strip() or None
    v["CategoryID"] = to_int(data.get("CategoryID"), "CategoryID") or None
    cat = one(con, "SELECT * FROM tbl_AssetCategories WHERE CategoryID=?", (v["CategoryID"],)) if v["CategoryID"] else None
    if not cat:
        raise ApiError("Fixed asset group is required")
    v["AcquisitionDate"] = parse_date(data.get("AcquisitionDate"), "Acquisition date", True)
    v["InServiceDate"] = parse_date(data.get("InServiceDate"), "In-service date") or v["AcquisitionDate"]
    v["DepreciationStartDate"] = parse_date(data.get("DepreciationStartDate"), "Depreciation start date") or v["InServiceDate"]
    if v["DepreciationStartDate"] < v["AcquisitionDate"]:
        raise ApiError("Depreciation start date cannot be before the acquisition date")
    if v["InServiceDate"] < v["AcquisitionDate"]:
        raise ApiError("In-service date cannot be before the acquisition date")
    # The books always carry the NET cost (excluding VAT); VAT only records how the asset was bought.
    st = get_settings(con)
    amount = num(data.get("PurchaseAmount") if data.get("PurchaseAmount") not in (None, "") else data.get("AcquisitionCost"), "Invoice amount", 0, 0)
    truthy = (True, 1, "1", "true", "True")
    applicable = 1 if (st.get("VATEnabled", "1") == "1" and data.get("VatApplicable") in truthy) else 0
    rate = num(data.get("VatRate"), "VAT rate", float(st.get("VATRate") or 15), 0)
    if rate > 100:
        raise ApiError("VAT rate must be between 0 and 100")
    inclusive = 1 if (applicable and data.get("VatInclusive") in truthy) else 0
    if applicable:
        net = round(amount / (1 + rate / 100), 2) if inclusive else round(amount, 2)
        vat = round(amount - net, 2) if inclusive else round(net * rate / 100, 2)
    else:
        net, vat, rate = round(amount, 2), 0.0, None
    v["VatApplicable"], v["VatInclusive"], v["VatRate"], v["PurchaseAmount"], v["VatAmount"] = applicable, inclusive, rate, round(amount, 2), vat
    v["AcquisitionCost"] = net
    v["ResidualValue"] = num(data.get("ResidualValue"), "Residual value", 0, 0)
    if v["ResidualValue"] > v["AcquisitionCost"]:
        raise ApiError("Residual value cannot exceed the acquisition cost")
    v["OpeningAccumDep"] = num(data.get("OpeningAccumDep"), "Opening accumulated depreciation", 0, 0)
    if v["OpeningAccumDep"] > v["AcquisitionCost"] - v["ResidualValue"]:
        raise ApiError("Opening accumulated depreciation exceeds the depreciable amount")
    life = num(data.get("UsefulLifeYears"), "Useful life", None, 0)
    if life is None:
        life = cat["UsefulLifeYears"]
    v["UsefulLifeYears"] = life
    rate = num(data.get("DepreciationRate"), "Depreciation rate", None, 0)
    v["DepreciationRate"] = rate if rate is not None else (round(100 / life, 4) if life else cat["DepreciationRate"])
    v["MethodID"] = to_int(data.get("MethodID"), "MethodID") or cat["MethodID"]
    v["OpeningNBV"] = v["AcquisitionCost"] - v["OpeningAccumDep"]
    for f in ("LocationID", "CostCenterID"):
        v[f] = to_int(data.get(f), f) or None
    sid = to_int(data.get("SupplierID"), "SupplierID") or None
    sup = one(con, "SELECT SupplierName, IsActive FROM tbl_Suppliers WHERE SupplierID=?", (sid,), raw=True) if sid else None
    if sid and not sup:
        raise ApiError("Supplier not found")
    if sup and not sup["IsActive"] and (not existing or existing.get("SupplierID") != sid):
        raise ApiError("This supplier is inactive")
    v["SupplierID"] = sid
    v["SupplierName"] = sup["SupplierName"] if sup else None
    for f in ("AssetDescription", "ResponsiblePerson", "InvoiceNumber", "PurchaseOrderNumber",
              "SerialNumber", "ModelNumber", "Manufacturer", "Notes"):
        v[f] = (data.get(f) or "").strip() or None
    v["WarrantyExpiryDate"] = parse_date(data.get("WarrantyExpiryDate"), "Warranty expiry date")
    return v


def save_asset(con, data: dict, asset_id: int | None = None) -> dict:
    if asset_id is None:
        v = _clean_asset(con, data, None)
        code = next_asset_code(con, v["CategoryID"])
        try:
            cur = con.execute(
                f"INSERT INTO tbl_Assets(AssetCode,{','.join(v)},AssetStatus,IsActive,CreatedAt,CreatedBy) "
                f"VALUES(?,{','.join('?' * len(v))},'Active',1,?,?)", [code, *v.values(), now(), actor()])
        except sqlite3.IntegrityError as e:
            if "AssetCode" in str(e):
                raise ApiError(f"Asset code {code} already exists")
            raise ApiError("The asset could not be saved: a required value is missing or invalid")
        asset_id = cur.lastrowid
        con.execute("INSERT INTO tbl_AssetTransactions(AssetID,TransactionType,TransactionDate,Amount,ReferenceNumber,"
                    "ToLocationID,ToCostCenterID,Notes,CreatedAt,CreatedBy) VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (asset_id, "ACQUISITION", v["AcquisitionDate"], v["AcquisitionCost"], v["InvoiceNumber"],
                     v["LocationID"], v["CostCenterID"], "Asset acquired", now(), actor()))
        audit(con, "CREATE", "tbl_Assets", asset_id, code)
    else:
        cur_a = one(con, "SELECT * FROM tbl_Assets WHERE AssetID=?", (asset_id,))
        if not cur_a:
            raise ApiError("Asset not found", 404)
        if cur_a["AssetStatus"] == "Disposed":
            raise ApiError("A disposed asset cannot be edited")
        v = _clean_asset(con, data, cur_a)
        posted = one(con, "SELECT 1 x FROM tbl_Depreciation WHERE AssetID=? AND PostingStatus='POSTED' LIMIT 1", (asset_id,))
        if posted:
            locked = ["AcquisitionCost", "ResidualValue", "UsefulLifeYears", "MethodID", "OpeningAccumDep",
                      "DepreciationStartDate", "InServiceDate", "AcquisitionDate", "CategoryID"]
            changed = [f for f in locked if str(cur_a[f] if cur_a[f] is not None else "") != str(v[f] if v[f] is not None else "")
                       and not (isinstance(v[f], float) and cur_a[f] is not None and abs(float(cur_a[f]) - v[f]) < 0.0001)]
            if changed:
                raise ApiError("Depreciation is already posted; these fields cannot be changed: " + ", ".join(changed))
        if (v["LocationID"], v["CostCenterID"]) != (cur_a["LocationID"], cur_a["CostCenterID"]):
            raise ApiError("Use the Transfer command to change location or cost center")
        v.pop("LocationID"); v.pop("CostCenterID")
        # an unposted proposal is stale as soon as anything it was calculated from changes
        same = lambda x, y: (abs(float(x) - float(y)) < 0.0001) if isinstance(x, (int, float)) and isinstance(y, (int, float)) else (x or None) == (y or None)
        dep_fields = ("AcquisitionCost", "ResidualValue", "UsefulLifeYears", "MethodID", "OpeningAccumDep", "DepreciationStartDate", "InServiceDate", "CategoryID")
        if any(not same(cur_a[f], v[f]) for f in dep_fields):
            n = con.execute("DELETE FROM tbl_Depreciation WHERE AssetID=? AND PostingStatus='DRAFT'", (asset_id,)).rowcount
            if n:
                audit(con, "DISCARD", "tbl_Depreciation", asset_id, f"{n} draft line(s) removed because the asset changed")
        con.execute(f"UPDATE tbl_Assets SET {','.join(k + '=?' for k in v)},ModifiedAt=?,ModifiedBy=? WHERE AssetID=?",
                    [*v.values(), now(), actor(), asset_id])
        con.execute("UPDATE tbl_AssetTransactions SET Amount=?, TransactionDate=? WHERE AssetID=? AND TransactionType='ACQUISITION'",
                    (v["AcquisitionCost"], v["AcquisitionDate"], asset_id))
        audit(con, "UPDATE", "tbl_Assets", asset_id, cur_a["AssetCode"])
    con.commit()
    return get_asset(con, asset_id)


def change_status(con, asset_id: int, status: str) -> dict:
    a = get_asset(con, asset_id)
    if a["AssetStatus"] == "Disposed":
        raise ApiError("Asset is disposed")
    if status not in ASSET_STATUSES:
        raise ApiError("Invalid status")
    con.execute("UPDATE tbl_Assets SET AssetStatus=?,ModifiedAt=?,ModifiedBy=? WHERE AssetID=?", (status, now(), actor(), asset_id))
    con.execute("INSERT INTO tbl_AssetTransactions(AssetID,TransactionType,TransactionDate,Notes,CreatedAt,CreatedBy) "
                "VALUES(?,?,?,?,?,?)", (asset_id, "STATUS", date.today().isoformat(), f"{a['AssetStatus']} -> {status}", now(), actor()))
    audit(con, "STATUS", "tbl_Assets", asset_id, f"{a['AssetStatus']} -> {status}")
    con.commit()
    return get_asset(con, asset_id)


def delete_asset(con, asset_id: int) -> dict:
    a = get_asset(con, asset_id)
    if one(con, "SELECT 1 x FROM tbl_Maintenance WHERE AssetID=? LIMIT 1", (asset_id,)):
        raise ApiError("This asset has maintenance records and cannot be deleted")
    if one(con, "SELECT 1 x FROM tbl_AssetCustody WHERE AssetID=? LIMIT 1", (asset_id,)):
        raise ApiError("This asset has custody records and cannot be deleted")
    if any(t["TransactionType"] not in ("ACQUISITION", "STATUS") for t in a["transactions"]) or a["depreciation"]:
        raise ApiError("This asset has depreciation or other transactions and cannot be deleted")
    for att in a["attachments"]:
        _remove_file(att["FilePath"])
    con.execute("DELETE FROM tbl_AssetAttachments WHERE AssetID=?", (asset_id,))
    con.execute("DELETE FROM tbl_AssetTransactions WHERE AssetID=?", (asset_id,))
    con.execute("DELETE FROM tbl_Assets WHERE AssetID=?", (asset_id,))
    audit(con, "DELETE", "tbl_Assets", asset_id, a["AssetCode"])
    con.commit()
    return {"deleted": asset_id}


def transfer_asset(con, asset_id: int, data: dict) -> dict:
    a = get_asset(con, asset_id)
    if a["AssetStatus"] == "Disposed":
        raise ApiError("Asset is disposed")
    d = parse_date(data.get("TransactionDate"), "Transfer date", True)
    if d < a["AcquisitionDate"]:
        raise ApiError("Transfer date cannot be before the acquisition date")
    to_loc = to_int(data.get("ToLocationID"), "Location") or None
    to_cc = to_int(data.get("ToCostCenterID"), "Cost center") or None
    for tbl, pk, val, cur_val in (("tbl_Locations", "LocationID", to_loc, a["LocationID"]), ("tbl_CostCenters", "CostCenterID", to_cc, a["CostCenterID"])):
        if val and val != cur_val:
            ref = one(con, f"SELECT IsActive FROM {tbl} WHERE {pk}=?", (val,), raw=True)
            if not ref:
                raise ApiError("Location or cost center not found")
            if not ref["IsActive"]:
                raise ApiError("The location or cost center is inactive")
    if (to_loc, to_cc) == (a["LocationID"], a["CostCenterID"]) and not data.get("ResponsiblePerson"):
        raise ApiError("Nothing to transfer: choose a different location or cost center")
    con.execute("INSERT INTO tbl_AssetTransactions(AssetID,TransactionType,TransactionDate,FromLocationID,ToLocationID,"
                "FromCostCenterID,ToCostCenterID,ReferenceNumber,Notes,CreatedAt,CreatedBy) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (asset_id, "TRANSFER", d, a["LocationID"], to_loc, a["CostCenterID"], to_cc,
                 data.get("ReferenceNumber") or None, data.get("Notes") or None, now(), actor()))
    resp = (data.get("ResponsiblePerson") or "").strip() or a["ResponsiblePerson"]
    con.execute("UPDATE tbl_Assets SET LocationID=?,CostCenterID=?,ResponsiblePerson=?,ModifiedAt=?,ModifiedBy=? WHERE AssetID=?",
                (to_loc, to_cc, resp, now(), actor(), asset_id))
    audit(con, "TRANSFER", "tbl_Assets", asset_id, a["AssetCode"])
    con.commit()
    return get_asset(con, asset_id)
