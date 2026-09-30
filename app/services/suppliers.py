"""Suppliers and other business contacts."""
from __future__ import annotations

import re
from typing import Any

from .common import ApiError, actor, audit, now, one, rows

# ---------------------------------------------------------------- suppliers
SUPPLIER_TYPES = ["Supplier", "Manufacturer", "Maintenance provider", "Service provider"]
SUPPLIER_FIELDS = ["SupplierName", "SupplierNameAr", "SupplierType", "ContactPerson", "Phone", "Mobile", "Email", "Website", "Address",
                   "City", "Country", "TaxNumber", "CRNumber", "PaymentTerms", "BankName", "IBAN", "Notes"]

SUPPLIER_LIST_SQL = """SELECT S.*,
  (SELECT COUNT(*) FROM tbl_Assets A WHERE A.SupplierID=S.SupplierID) AS AssetCount,
  (SELECT COALESCE(SUM(A.AcquisitionCost),0) FROM tbl_Assets A WHERE A.SupplierID=S.SupplierID) AS PurchaseTotal,
  (SELECT COUNT(*) FROM tbl_Maintenance M WHERE M.SupplierID=S.SupplierID) AS MaintenanceCount,
  (SELECT COALESCE(SUM(M.Cost),0) FROM tbl_Maintenance M WHERE M.SupplierID=S.SupplierID AND M.Status='Completed') AS MaintenanceTotal
  FROM tbl_Suppliers S"""


def list_suppliers(con, q: str = "", status: str = "", stype: str = "") -> list[dict]:
    sql, args = SUPPLIER_LIST_SQL + " WHERE 1=1", []
    if status in ("1", "0"):
        sql += " AND S.IsActive=?"
        args.append(int(status))
    if stype:
        sql += " AND S.SupplierType=?"
        args.append(stype)
    if q:
        sql += " AND (S.SupplierCode LIKE ? OR S.SupplierName LIKE ? OR S.SupplierNameAr LIKE ? OR S.ContactPerson LIKE ? OR S.Phone LIKE ? OR S.Mobile LIKE ? OR S.Email LIKE ? OR S.TaxNumber LIKE ?)"
        args += [f"%{q}%"] * 8
    return rows(con, sql + " ORDER BY S.SupplierName", args)


def get_supplier(con, sid: int) -> dict:
    sup = one(con, SUPPLIER_LIST_SQL + " WHERE S.SupplierID=?", (sid,), raw=True)
    if not sup:
        raise ApiError("Supplier not found", 404)
    sup["assets"] = rows(con, """SELECT A.AssetID, A.AssetCode, A.AssetName, A.AssetNameAr, A.AcquisitionDate, A.InvoiceNumber, A.AcquisitionCost, A.AssetStatus
        FROM tbl_Assets A WHERE A.SupplierID=? ORDER BY A.AcquisitionDate DESC""", (sid,))
    sup["maintenance"] = rows(con, """SELECT M.MaintenanceID, M.MaintenanceNo, M.ScheduledDate, M.Title, M.Status, M.Cost, A.AssetCode
        FROM tbl_Maintenance M JOIN tbl_Assets A ON A.AssetID=M.AssetID WHERE M.SupplierID=? ORDER BY M.ScheduledDate DESC""", (sid,))
    return sup


def next_supplier_code(con) -> str:
    return _next_supplier_code(con)


def _next_supplier_code(con) -> str:
    mx = 0
    for r in con.execute("SELECT SupplierCode FROM tbl_Suppliers"):
        m = re.fullmatch(r"SUP-(\d+)", r["SupplierCode"])
        if m:
            mx = max(mx, int(m.group(1)))
    return f"SUP-{mx + 1:04d}"


def save_supplier(con, data: dict, sid: int | None = None) -> dict:
    v: dict[str, Any] = {}
    for f in SUPPLIER_FIELDS:
        v[f] = (str(data.get(f)).strip() or None) if data.get(f) is not None else None
    if not v["SupplierName"]:
        raise ApiError("Supplier name is required")
    v["SupplierType"] = v["SupplierType"] or "Supplier"
    if v["SupplierType"] not in SUPPLIER_TYPES:
        raise ApiError("Invalid supplier type")
    if v["Email"] and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", v["Email"]):
        raise ApiError("Email address is not valid")
    if v["IBAN"]:
        v["IBAN"] = re.sub(r"\s+", "", v["IBAN"]).upper()
    for f in ("Phone", "Mobile"):
        if v[f] and not re.fullmatch(r"[+0-9 ()\-./]{5,25}", v[f]):
            raise ApiError(f"{f} is not a valid phone number")
    dup = one(con, "SELECT SupplierCode FROM tbl_Suppliers WHERE lower(SupplierName)=lower(?) AND SupplierID<>?", (v["SupplierName"], sid or 0), raw=True)
    if dup:
        raise ApiError(f"A supplier with this name already exists ({dup['SupplierCode']})")
    if v["TaxNumber"]:
        dup = one(con, "SELECT SupplierCode FROM tbl_Suppliers WHERE TaxNumber=? AND SupplierID<>?", (v["TaxNumber"], sid or 0), raw=True)
        if dup:
            raise ApiError(f"This tax number already belongs to supplier {dup['SupplierCode']}")
    active = 0 if data.get("IsActive") in (False, 0, "0", "false") else 1
    code = (data.get("SupplierCode") or "").strip()
    if len(code) > 20:
        raise ApiError("Supplier code is too long")
    if sid is None:
        code = code or _next_supplier_code(con)
        if one(con, "SELECT 1 x FROM tbl_Suppliers WHERE lower(SupplierCode)=lower(?)", (code,), raw=True):
            raise ApiError(f"Supplier code {code} already exists")
        cur = con.execute(f"INSERT INTO tbl_Suppliers(SupplierCode,{','.join(v)},IsActive,CreatedAt,CreatedBy) VALUES(?,{','.join('?' * len(v))},?,?,?)",
                          [code, *v.values(), active, now(), actor()])
        sid = cur.lastrowid
        audit(con, "CREATE", "tbl_Suppliers", sid, f"{code} {v['SupplierName']}")
    else:
        cur_s = one(con, "SELECT SupplierCode, SupplierName FROM tbl_Suppliers WHERE SupplierID=?", (sid,), raw=True)
        if not cur_s:
            raise ApiError("Supplier not found", 404)
        code = code or cur_s["SupplierCode"]
        if one(con, "SELECT 1 x FROM tbl_Suppliers WHERE lower(SupplierCode)=lower(?) AND SupplierID<>?", (code, sid), raw=True):
            raise ApiError(f"Supplier code {code} already exists")
        con.execute(f"UPDATE tbl_Suppliers SET SupplierCode=?,{','.join(k + '=?' for k in v)},IsActive=?,ModifiedAt=?,ModifiedBy=? WHERE SupplierID=?",
                    [code, *v.values(), active, now(), actor(), sid])
        if cur_s["SupplierName"] != v["SupplierName"]:  # keep the denormalised names on linked records in step
            con.execute("UPDATE tbl_Assets SET SupplierName=? WHERE SupplierID=?", (v["SupplierName"], sid))
            con.execute("UPDATE tbl_Maintenance SET Vendor=? WHERE SupplierID=?", (v["SupplierName"], sid))
        audit(con, "UPDATE", "tbl_Suppliers", sid, cur_s["SupplierCode"])
    con.commit()
    return get_supplier(con, sid)


def delete_supplier(con, sid: int) -> dict:
    sup = get_supplier(con, sid)
    if sup["assets"] or sup["maintenance"]:
        raise ApiError("This supplier is linked to assets or maintenance orders and cannot be deleted. Mark it inactive instead.")
    con.execute("DELETE FROM tbl_Suppliers WHERE SupplierID=?", (sid,))
    audit(con, "DELETE", "tbl_Suppliers", sid, sup["SupplierCode"])
    con.commit()
    return {"deleted": sid}
