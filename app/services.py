"""Gooya Asset - business logic: masters, assets, depreciation, transfers, disposals."""
from __future__ import annotations

import calendar
import getpass
import os
import re
import shutil
import sqlite3
import threading
from datetime import date, datetime
from pathlib import Path
from typing import Any

from . import db

USER = getpass.getuser()
ASSET_STATUSES = ["Active", "Inactive", "Under Repair"]


class ApiError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def r2(v: float | None) -> float:
    return round(float(v or 0), 2)


_ctx = threading.local()


def set_lang(lang: str) -> None:
    _ctx.lang = "ar" if lang == "ar" else "en"


def localize(row: dict, skip: tuple = ()) -> dict:
    """In Arabic mode replace every <Field> by <Field>Ar when an Arabic value exists."""
    if getattr(_ctx, "lang", "en") == "ar":
        for k in list(row):
            if k.endswith("Ar") and k[:-2] not in skip and row[k] and (k[:-2] in row):
                row[k[:-2]] = row[k]
    return row


def rows(con, sql, args=(), raw=False) -> list[dict]:
    out = [dict(r) for r in con.execute(sql, args).fetchall()]
    return out if raw else [localize(r) for r in out]


def one(con, sql, args=(), raw=False) -> dict | None:
    r = con.execute(sql, args).fetchone()
    if not r:
        return None
    return dict(r) if raw else localize(dict(r))


def audit(con, action: str, entity: str, entity_id: Any, details: str = "") -> None:
    con.execute("INSERT INTO tbl_AuditLog(LogDate,UserName,Action,Entity,EntityID,Details) VALUES(?,?,?,?,?,?)",
                (now(), USER, action, entity, str(entity_id), details))


def parse_date(v: Any, field: str = "Date", required: bool = False) -> str | None:
    if v in (None, ""):
        if required:
            raise ApiError(f"{field} is required")
        return None
    try:
        return datetime.strptime(str(v)[:10], "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError:
        raise ApiError(f"{field} is not a valid date (YYYY-MM-DD)")


def num(v: Any, field: str, default: float | None = 0, minimum: float | None = None) -> float | None:
    if v in (None, ""):
        return default
    try:
        x = float(v)
    except (TypeError, ValueError):
        raise ApiError(f"{field} must be a number")
    if minimum is not None and x < minimum:
        raise ApiError(f"{field} must be at least {minimum}")
    return x


def get_settings(con) -> dict[str, str]:
    return {r["SettingKey"]: r["SettingValue"] or "" for r in con.execute("SELECT * FROM tbl_Settings")}


# ---------------------------------------------------------------- master data
MASTERS: dict[str, dict] = {
    "categories": dict(table="tbl_AssetCategories", pk="CategoryID", code="CategoryCode", name="CategoryName",
                       fields=["CategoryCode", "CategoryName", "CategoryNameAr", "UsefulLifeYears", "DepreciationRate", "MethodID",
                               "AssetAccountID", "AccumDepAccountID", "DepExpenseAccountID", "GainAccountID",
                               "LossAccountID", "IsActive"],
                       used_by=[("tbl_Assets", "CategoryID")], order="CategoryCode"),
    "locations": dict(table="tbl_Locations", pk="LocationID", code="LocationCode", name="LocationName",
                      fields=["LocationCode", "LocationName", "LocationNameAr", "IsActive"],
                      used_by=[("tbl_Assets", "LocationID")], order="LocationCode"),
    "costcenters": dict(table="tbl_CostCenters", pk="CostCenterID", code="CostCenterCode", name="CostCenterName",
                        fields=["CostCenterCode", "CostCenterName", "CostCenterNameAr", "IsActive"],
                        used_by=[("tbl_Assets", "CostCenterID")], order="CostCenterCode"),
    "glaccounts": dict(table="tbl_GLAccounts", pk="GLAccountID", code="AccountCode", name="AccountName",
                       fields=["AccountCode", "AccountName", "AccountNameAr", "AccountType", "IsActive"],
                       used_by=[("tbl_DepreciationJournal", "GLAccountID"), ("tbl_AssetCategories", "AssetAccountID"),
                                ("tbl_AssetCategories", "AccumDepAccountID"),
                                ("tbl_AssetCategories", "DepExpenseAccountID"),
                                ("tbl_AssetCategories", "GainAccountID"), ("tbl_AssetCategories", "LossAccountID")],
                       order="AccountCode"),
    "methods": dict(table="tbl_DepreciationMethods", pk="MethodID", code="MethodCode", name="MethodName",
                    fields=["MethodCode", "MethodName", "MethodNameAr", "IsActive"],
                    used_by=[("tbl_Assets", "MethodID"), ("tbl_AssetCategories", "MethodID")], order="MethodCode"),
}


def _master(name: str) -> dict:
    m = MASTERS.get(name)
    if not m:
        raise ApiError("Unknown list", 404)
    return m


def master_list(con, name: str) -> list[dict]:
    m = _master(name)
    return rows(con, f"SELECT * FROM {m['table']} ORDER BY {m['order']}", raw=True)


def master_save(con, name: str, data: dict, rec_id: int | None = None) -> dict:
    m = _master(name)
    vals = {}
    for f in m["fields"]:
        if f not in data and rec_id is not None:
            continue
        v = data.get(f)
        if f == "IsActive":
            v = 1 if v in (None, True, 1, "1", "true") else 0
        elif isinstance(v, str):
            v = v.strip() or None
        vals[f] = v
    for req in (m["code"], m["name"]):
        if req in vals and not vals[req]:
            raise ApiError(f"{req} is required")
    if name == "categories":
        if vals.get("UsefulLifeYears") not in (None, ""):
            life = num(vals["UsefulLifeYears"], "Useful life", None, 0)
            vals["UsefulLifeYears"] = life
            if life and vals.get("DepreciationRate") in (None, ""):
                vals["DepreciationRate"] = round(100 / life, 4)
    try:
        if rec_id is None:
            cur = con.execute(f"INSERT INTO {m['table']}({','.join(vals)}) VALUES({','.join('?' * len(vals))})",
                              list(vals.values()))
            rec_id = cur.lastrowid
            audit(con, "CREATE", m["table"], rec_id, str(vals.get(m["code"])))
        else:
            if not one(con, f"SELECT 1 x FROM {m['table']} WHERE {m['pk']}=?", (rec_id,)):
                raise ApiError("Record not found", 404)
            con.execute(f"UPDATE {m['table']} SET {','.join(k + '=?' for k in vals)} WHERE {m['pk']}=?",
                        list(vals.values()) + [rec_id])
            audit(con, "UPDATE", m["table"], rec_id, str(vals.get(m["code"], "")))
    except sqlite3.IntegrityError as e:
        raise ApiError("Code already exists or a required value is missing" if "UNIQUE" in str(e) else str(e))
    con.commit()
    return one(con, f"SELECT * FROM {m['table']} WHERE {m['pk']}=?", (rec_id,), raw=True)


def master_delete(con, name: str, rec_id: int) -> dict:
    m = _master(name)
    for table, col in m["used_by"]:
        if one(con, f"SELECT 1 x FROM {table} WHERE {col}=? LIMIT 1", (rec_id,)):
            raise ApiError("This record is in use and cannot be deleted. Mark it inactive instead.")
    con.execute(f"DELETE FROM {m['table']} WHERE {m['pk']}=?", (rec_id,))
    audit(con, "DELETE", m["table"], rec_id)
    con.commit()
    return {"deleted": rec_id}


def save_settings(con, data: dict) -> dict:
    known = {r["SettingKey"] for r in con.execute("SELECT SettingKey FROM tbl_Settings")}
    for k, v in data.items():
        if k not in known:
            continue
        v = "" if v is None else str(v).strip()
        if k == "FiscalYearStartMonth" and not (v.isdigit() and 1 <= int(v) <= 12):
            raise ApiError("Fiscal year start month must be 1-12")
        if k == "AssetCodePrefix" and not v:
            raise ApiError("Asset code prefix is required")
        con.execute("UPDATE tbl_Settings SET SettingValue=? WHERE SettingKey=?", (v, k))
    audit(con, "UPDATE", "tbl_Settings", "-", ", ".join(data))
    con.commit()
    return get_settings(con)


def lookups(con) -> dict:
    return {
        "categories": master_list(con, "categories"),
        "locations": master_list(con, "locations"),
        "costcenters": master_list(con, "costcenters"),
        "glaccounts": master_list(con, "glaccounts"),
        "methods": master_list(con, "methods"),
        "periods": rows(con, "SELECT * FROM tbl_DepreciationPeriods ORDER BY StartDate"),
        "settings": get_settings(con),
        "statuses": ASSET_STATUSES,
        "maint_types": MAINT_TYPES, "maint_priorities": MAINT_PRIORITIES, "maint_statuses": MAINT_STATUSES,
        "user": USER,
    }


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
                        (fiscal_year, n, first.strftime("%B %Y"), first.isoformat(), last.isoformat(), now(), USER))
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


# ---------------------------------------------------------------- assets
ASSET_FIELDS = ["AssetName", "AssetNameAr", "AssetDescription", "CategoryID", "AcquisitionDate", "InServiceDate",
                "DepreciationStartDate", "AcquisitionCost", "ResidualValue", "UsefulLifeYears", "DepreciationRate",
                "MethodID", "OpeningAccumDep", "LocationID", "CostCenterID", "ResponsiblePerson", "SupplierName",
                "InvoiceNumber", "PurchaseOrderNumber", "SerialNumber", "ModelNumber", "Manufacturer",
                "WarrantyExpiryDate", "Notes"]

BOOK_SQL = """
SELECT A.*, C.CategoryCode, C.CategoryName, C.CategoryNameAr, M.MethodCode, M.MethodName, M.MethodNameAr,
       L.LocationName, L.LocationNameAr, L.LocationCode, CC.CostCenterName, CC.CostCenterNameAr, CC.CostCenterCode,
       COALESCE(A.OpeningAccumDep,0) + COALESCE((SELECT SUM(PeriodDepreciation) FROM tbl_Depreciation D
            WHERE D.AssetID=A.AssetID AND D.PostingStatus='POSTED'),0) AS AccumDep
FROM tbl_Assets A
LEFT JOIN tbl_AssetCategories C ON C.CategoryID=A.CategoryID
LEFT JOIN tbl_DepreciationMethods M ON M.MethodID=A.MethodID
LEFT JOIN tbl_Locations L ON L.LocationID=A.LocationID
LEFT JOIN tbl_CostCenters CC ON CC.CostCenterID=A.CostCenterID
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
    v["CategoryID"] = int(data.get("CategoryID") or 0) or None
    cat = one(con, "SELECT * FROM tbl_AssetCategories WHERE CategoryID=?", (v["CategoryID"],)) if v["CategoryID"] else None
    if not cat:
        raise ApiError("Fixed asset group is required")
    v["AcquisitionDate"] = parse_date(data.get("AcquisitionDate"), "Acquisition date", True)
    v["InServiceDate"] = parse_date(data.get("InServiceDate"), "In-service date") or v["AcquisitionDate"]
    v["DepreciationStartDate"] = parse_date(data.get("DepreciationStartDate"), "Depreciation start date") or v["InServiceDate"]
    if v["InServiceDate"] < v["AcquisitionDate"]:
        raise ApiError("In-service date cannot be before the acquisition date")
    v["AcquisitionCost"] = num(data.get("AcquisitionCost"), "Acquisition cost", 0, 0)
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
    v["MethodID"] = int(data.get("MethodID") or 0) or cat["MethodID"]
    v["OpeningNBV"] = v["AcquisitionCost"] - v["OpeningAccumDep"]
    for f in ("LocationID", "CostCenterID"):
        v[f] = int(data.get(f) or 0) or None
    for f in ("AssetDescription", "ResponsiblePerson", "SupplierName", "InvoiceNumber", "PurchaseOrderNumber",
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
                f"VALUES(?,{','.join('?' * len(v))},'Active',1,?,?)", [code, *v.values(), now(), USER])
        except sqlite3.IntegrityError:
            raise ApiError(f"Asset code {code} already exists")
        asset_id = cur.lastrowid
        con.execute("INSERT INTO tbl_AssetTransactions(AssetID,TransactionType,TransactionDate,Amount,ReferenceNumber,"
                    "ToLocationID,ToCostCenterID,Notes,CreatedAt,CreatedBy) VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (asset_id, "ACQUISITION", v["AcquisitionDate"], v["AcquisitionCost"], v["InvoiceNumber"],
                     v["LocationID"], v["CostCenterID"], "Asset acquired", now(), USER))
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
                      "DepreciationStartDate", "InServiceDate", "CategoryID"]
            changed = [f for f in locked if str(cur_a[f] if cur_a[f] is not None else "") != str(v[f] if v[f] is not None else "")
                       and not (isinstance(v[f], float) and cur_a[f] is not None and abs(float(cur_a[f]) - v[f]) < 0.0001)]
            if changed:
                raise ApiError("Depreciation is already posted; these fields cannot be changed: " + ", ".join(changed))
        if (v["LocationID"], v["CostCenterID"]) != (cur_a["LocationID"], cur_a["CostCenterID"]):
            raise ApiError("Use the Transfer command to change location or cost center")
        v.pop("LocationID"); v.pop("CostCenterID")
        con.execute(f"UPDATE tbl_Assets SET {','.join(k + '=?' for k in v)},ModifiedAt=?,ModifiedBy=? WHERE AssetID=?",
                    [*v.values(), now(), USER, asset_id])
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
    con.execute("UPDATE tbl_Assets SET AssetStatus=?,ModifiedAt=?,ModifiedBy=? WHERE AssetID=?", (status, now(), USER, asset_id))
    con.execute("INSERT INTO tbl_AssetTransactions(AssetID,TransactionType,TransactionDate,Notes,CreatedAt,CreatedBy) "
                "VALUES(?,?,?,?,?,?)", (asset_id, "STATUS", date.today().isoformat(), f"{a['AssetStatus']} -> {status}", now(), USER))
    audit(con, "STATUS", "tbl_Assets", asset_id, f"{a['AssetStatus']} -> {status}")
    con.commit()
    return get_asset(con, asset_id)


def delete_asset(con, asset_id: int) -> dict:
    a = get_asset(con, asset_id)
    if one(con, "SELECT 1 x FROM tbl_Maintenance WHERE AssetID=? LIMIT 1", (asset_id,)):
        raise ApiError("This asset has maintenance records and cannot be deleted")
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
    to_loc = int(data.get("ToLocationID") or 0) or None
    to_cc = int(data.get("ToCostCenterID") or 0) or None
    if (to_loc, to_cc) == (a["LocationID"], a["CostCenterID"]) and not data.get("ResponsiblePerson"):
        raise ApiError("Nothing to transfer: choose a different location or cost center")
    con.execute("INSERT INTO tbl_AssetTransactions(AssetID,TransactionType,TransactionDate,FromLocationID,ToLocationID,"
                "FromCostCenterID,ToCostCenterID,ReferenceNumber,Notes,CreatedAt,CreatedBy) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (asset_id, "TRANSFER", d, a["LocationID"], to_loc, a["CostCenterID"], to_cc,
                 data.get("ReferenceNumber") or None, data.get("Notes") or None, now(), USER))
    resp = (data.get("ResponsiblePerson") or "").strip() or a["ResponsiblePerson"]
    con.execute("UPDATE tbl_Assets SET LocationID=?,CostCenterID=?,ResponsiblePerson=?,ModifiedAt=?,ModifiedBy=? WHERE AssetID=?",
                (to_loc, to_cc, resp, now(), USER, asset_id))
    audit(con, "TRANSFER", "tbl_Assets", asset_id, a["AssetCode"])
    con.commit()
    return get_asset(con, asset_id)


# ---------------------------------------------------------------- depreciation
def _month_index(d: str) -> int:
    return int(d[:4]) * 12 + int(d[5:7])


def _sequence_ok(con, asset: dict, period: dict) -> str | None:
    """All earlier existing periods (from depreciation start) must be POSTED for this asset."""
    start = asset["DepreciationStartDate"] or asset["InServiceDate"] or asset["AcquisitionDate"]
    missing = rows(con, """
        SELECT P.PeriodName FROM tbl_DepreciationPeriods P
        WHERE P.EndDate>=? AND P.StartDate<? AND NOT EXISTS (
          SELECT 1 FROM tbl_Depreciation D WHERE D.AssetID=? AND D.PeriodID=P.PeriodID AND D.PostingStatus='POSTED')
        ORDER BY P.StartDate""", (start, period["StartDate"], asset["AssetID"]))
    if asset["DisposalDate"]:
        return None
    return missing[0]["PeriodName"] if missing else None


def propose(con, period_id: int) -> list[dict]:
    """Compute (but do not store) depreciation for every eligible asset in a period."""
    p = one(con, "SELECT * FROM tbl_DepreciationPeriods WHERE PeriodID=?", (period_id,))
    if not p:
        raise ApiError("Period not found", 404)
    out = []
    for a in rows(con, BOOK_SQL + " WHERE A.IsActive=1 AND A.AssetStatus<>'Disposed' ORDER BY A.AssetCode"):
        line = {"AssetID": a["AssetID"], "AssetCode": a["AssetCode"], "AssetName": a["AssetName"],
                "CategoryName": a["CategoryName"], "AcquisitionCost": a["AcquisitionCost"],
                "ResidualValue": a["ResidualValue"], "eligible": False, "reason": ""}
        start = a["DepreciationStartDate"] or a["InServiceDate"] or a["AcquisitionDate"]
        if a["MethodCode"] != "SL":
            line["reason"] = "Method: no depreciation"
        elif not a["UsefulLifeYears"]:
            line["reason"] = "Missing useful life"
        elif _month_index(start) > _month_index(p["StartDate"]):
            line["reason"] = "Not yet in depreciation"
        elif a["DisposalDate"]:
            line["reason"] = "Disposed"
        else:
            existing = one(con, "SELECT * FROM tbl_Depreciation WHERE AssetID=? AND PeriodID=?", (a["AssetID"], period_id))
            if existing and existing["PostingStatus"] == "POSTED":
                line.update(reason="Already posted", status="POSTED", PeriodDepreciation=existing["PeriodDepreciation"],
                            OpeningAccumDep=existing["OpeningAccumDep"], ClosingAccumDep=existing["ClosingAccumDep"],
                            ClosingNBV=existing["ClosingNBV"])
            else:
                prior = _sequence_ok(con, a, p)
                if prior:
                    line["reason"] = f"{prior} must be posted first"
                else:
                    last = one(con, """SELECT D.ClosingAccumDep FROM tbl_Depreciation D
                                       JOIN tbl_DepreciationPeriods P2 ON P2.PeriodID=D.PeriodID
                                       WHERE D.AssetID=? AND D.PostingStatus='POSTED' AND P2.StartDate<?
                                       ORDER BY P2.StartDate DESC LIMIT 1""", (a["AssetID"], p["StartDate"]))
                    opening = last["ClosingAccumDep"] if last else (a["OpeningAccumDep"] or 0)
                    base = (a["AcquisitionCost"] or 0) - (a["ResidualValue"] or 0)
                    monthly = base / (a["UsefulLifeYears"] * 12)
                    amount = r2(max(0, min(monthly, base - opening)))
                    if amount <= 0:
                        line["reason"] = "Fully depreciated"
                    else:
                        line.update(eligible=True, reason="", status="DRAFT" if existing else "NEW",
                                    DepreciableAmount=base, UsefulLifeYears=a["UsefulLifeYears"],
                                    DepreciationRate=a["DepreciationRate"], OpeningAccumDep=r2(opening),
                                    OpeningNBV=r2(a["AcquisitionCost"] - opening), PeriodDepreciation=amount,
                                    ClosingAccumDep=r2(opening + amount),
                                    ClosingNBV=r2(a["AcquisitionCost"] - opening - amount))
        out.append(line)
    return out


def suggest_period(con) -> dict:
    """Earliest open period that still has something to depreciate or post."""
    for p in rows(con, "SELECT PeriodID FROM tbl_DepreciationPeriods WHERE PeriodStatus='OPEN' ORDER BY StartDate"):
        if any(l["eligible"] for l in propose(con, p["PeriodID"])):
            return {"period_id": p["PeriodID"]}
    return {"period_id": None}


def run_depreciation(con, period_id: int, asset_ids: list[int] | None = None) -> dict:
    p = one(con, "SELECT * FROM tbl_DepreciationPeriods WHERE PeriodID=?", (period_id,))
    if not p:
        raise ApiError("Period not found", 404)
    if p["PeriodStatus"] != "OPEN":
        raise ApiError("The period is closed")
    created = 0
    for ln in propose(con, period_id):
        if not ln["eligible"] or (asset_ids and ln["AssetID"] not in asset_ids):
            continue
        con.execute("DELETE FROM tbl_Depreciation WHERE AssetID=? AND PeriodID=? AND PostingStatus='DRAFT'",
                    (ln["AssetID"], period_id))
        con.execute("""INSERT INTO tbl_Depreciation(AssetID,PeriodID,AcquisitionCost,ResidualValue,DepreciableAmount,
            UsefulLifeYears,DepreciationRate,OpeningAccumDep,OpeningNBV,PeriodDepreciation,ClosingAccumDep,ClosingNBV,
            PostingStatus,CreatedAt,CreatedBy) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,'DRAFT',?,?)""",
                    (ln["AssetID"], period_id, ln["AcquisitionCost"], ln["ResidualValue"], ln["DepreciableAmount"],
                     ln["UsefulLifeYears"], ln["DepreciationRate"], ln["OpeningAccumDep"], ln["OpeningNBV"],
                     ln["PeriodDepreciation"], ln["ClosingAccumDep"], ln["ClosingNBV"], now(), USER))
        created += 1
    audit(con, "RUN", "tbl_Depreciation", period_id, f"{p['PeriodName']}: {created} lines proposed")
    con.commit()
    return {"created": created}


def draft_lines(con, period_id: int) -> list[dict]:
    return rows(con, """
        SELECT D.*, A.AssetCode, A.AssetName, A.AssetNameAr, C.CategoryName, C.CategoryNameAr FROM tbl_Depreciation D
        JOIN tbl_Assets A ON A.AssetID=D.AssetID LEFT JOIN tbl_AssetCategories C ON C.CategoryID=A.CategoryID
        WHERE D.PeriodID=? ORDER BY A.AssetCode""", (period_id,))


def discard_drafts(con, period_id: int) -> dict:
    n = con.execute("DELETE FROM tbl_Depreciation WHERE PeriodID=? AND PostingStatus='DRAFT'", (period_id,)).rowcount
    audit(con, "DISCARD", "tbl_Depreciation", period_id, f"{n} draft lines removed")
    con.commit()
    return {"deleted": n}


def post_depreciation(con, period_id: int) -> dict:
    p = one(con, "SELECT * FROM tbl_DepreciationPeriods WHERE PeriodID=?", (period_id,))
    if not p:
        raise ApiError("Period not found", 404)
    if p["PeriodStatus"] != "OPEN":
        raise ApiError("The period is closed")
    drafts = rows(con, """SELECT D.*, A.AssetCode, A.AssetName, A.AssetStatus, C.DepExpenseAccountID, C.AccumDepAccountID
        FROM tbl_Depreciation D JOIN tbl_Assets A ON A.AssetID=D.AssetID
        JOIN tbl_AssetCategories C ON C.CategoryID=A.CategoryID WHERE D.PeriodID=? AND D.PostingStatus='DRAFT'""", (period_id,))
    if not drafts:
        raise ApiError("There are no unposted depreciation lines for this period")
    for d in drafts:
        if not d["DepExpenseAccountID"] or not d["AccumDepAccountID"]:
            raise ApiError(f"Asset group of {d['AssetCode']} has no depreciation accounts configured")
        if d["AssetStatus"] == "Disposed":
            raise ApiError(f"{d['AssetCode']} is disposed")
        sp = _sequence_ok(con, one(con, "SELECT * FROM tbl_Assets WHERE AssetID=?", (d["AssetID"],)), p)
        if sp:
            raise ApiError(f"{d['AssetCode']}: {sp} must be posted first")
    ts = now()
    total = 0.0
    for d in drafts:
        desc = f"Depreciation - {d['AssetCode']} - {d['AssetName']} - {p['PeriodName']}"
        for acc, dr, cr in ((d["DepExpenseAccountID"], d["PeriodDepreciation"], 0), (d["AccumDepAccountID"], 0, d["PeriodDepreciation"])):
            con.execute("""INSERT INTO tbl_DepreciationJournal(DepreciationID,AssetID,PeriodID,JournalDate,GLAccountID,
                DebitAmount,CreditAmount,JournalType,Reference,Description,PostingStatus,PostedAt,PostedBy,CreatedAt)
                VALUES(?,?,?,?,?,?,?,'DEPRECIATION',?,?,'POSTED',?,?,?)""",
                        (d["DepreciationID"], d["AssetID"], period_id, p["EndDate"], acc, dr, cr, d["AssetCode"], desc, ts, USER, ts))
        con.execute("UPDATE tbl_Depreciation SET PostingStatus='POSTED',PostedAt=?,PostedBy=? WHERE DepreciationID=?",
                    (ts, USER, d["DepreciationID"]))
        total += d["PeriodDepreciation"]
    audit(con, "POST", "tbl_Depreciation", period_id, f"{p['PeriodName']}: {len(drafts)} lines, {r2(total)}")
    con.commit()
    return {"posted": len(drafts), "total": r2(total)}


# ---------------------------------------------------------------- disposal
def dispose_asset(con, asset_id: int, data: dict) -> dict:
    a = get_asset(con, asset_id)
    if a["AssetStatus"] == "Disposed":
        raise ApiError("Asset is already disposed")
    if one(con, "SELECT 1 x FROM tbl_Maintenance WHERE AssetID=? AND Status IN ('Planned','In Progress') LIMIT 1", (asset_id,)):
        raise ApiError("Complete or cancel the open maintenance orders of this asset first")
    d = parse_date(data.get("TransactionDate"), "Disposal date", True)
    if d < a["AcquisitionDate"]:
        raise ApiError("Disposal date cannot be before the acquisition date")
    proceeds = num(data.get("DisposalProceeds"), "Sale proceeds", 0, 0)
    per = period_for_date(con, d)
    if per and per["PeriodStatus"] != "OPEN":
        raise ApiError("The period of the disposal date is closed")
    # Depreciation must be posted for every period that ends before the disposal month
    mstart = d[:8] + "01"
    start = a["DepreciationStartDate"] or a["InServiceDate"] or a["AcquisitionDate"]
    if a["MethodCode"] == "SL":
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
                       a["CostCenterID"], data.get("ReferenceNumber") or None, data.get("Notes") or None, now(), USER))
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
                    (tx, asset_id, per["PeriodID"] if per else None, d, acc, dr, cr, a["AssetCode"], desc, now(), USER, now()))
    con.execute("UPDATE tbl_Assets SET AssetStatus='Disposed',DisposalDate=?,ModifiedAt=?,ModifiedBy=? WHERE AssetID=?",
                (d, now(), USER, asset_id))
    audit(con, "DISPOSE", "tbl_Assets", asset_id, f"{a['AssetCode']} proceeds={proceeds} gain/loss={gain}")
    con.commit()
    return get_asset(con, asset_id)


# ---------------------------------------------------------------- attachments
def _attach_root(con) -> Path:
    folder = get_settings(con).get("AttachmentFolder")
    root = Path(folder) if folder else db.ROOT / "attachments"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _remove_file(path: str | None) -> None:
    try:
        if path and Path(path).is_file():
            Path(path).unlink()
            parent = Path(path).parent  # prune the now-empty asset / month / group folders (never further up)
            for _ in range(3):
                if any(parent.iterdir()):
                    break
                parent.rmdir()
                parent = parent.parent
    except OSError:
        pass


def add_attachment(con, asset_id: int, filename: str, content: bytes, meta: dict) -> dict:
    a = get_asset(con, asset_id)
    if not content:
        raise ApiError("The file is empty")
    if len(content) > 50 * 1024 * 1024:
        raise ApiError("File is larger than 50 MB")
    clean = lambda x: re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(x)).strip(" .") or "x"
    ext = Path(os.path.basename(filename)).suffix.lower()[:12]
    cat = one(con, "SELECT CategoryCode, CategoryName FROM tbl_AssetCategories WHERE CategoryID=?", (a["CategoryID"],), raw=True) or {}
    raw_asset = one(con, "SELECT AssetCode, AcquisitionDate FROM tbl_Assets WHERE AssetID=?", (asset_id,), raw=True)
    # <root>/<group>/<purchase year-month>/<asset number>/<asset number>_<purchase date>[_n].<ext>
    folder = (_attach_root(con) / clean(f"{cat.get('CategoryCode', '')} - {cat.get('CategoryName', '')}")
              / raw_asset["AcquisitionDate"][:7] / clean(raw_asset["AssetCode"]))
    folder.mkdir(parents=True, exist_ok=True)
    base = f"{clean(raw_asset['AssetCode'])}_{raw_asset['AcquisitionDate']}"
    target, n = folder / f"{base}{ext}", 1
    while target.exists():
        n += 1
        target = folder / f"{base}_{n}{ext}"
    safe = target.name
    target.write_bytes(content)
    con.execute("INSERT INTO tbl_AssetAttachments(AssetID,DocumentTitle,DocumentType,FileName,FileExtension,FilePath,Notes,"
                "CreatedAt,CreatedBy) VALUES(?,?,?,?,?,?,?,?,?)",
                (asset_id, meta.get("title") or safe, meta.get("type") or None, target.name,
                 target.suffix.lstrip(".").lower(), str(target), meta.get("notes") or None, now(), USER))
    audit(con, "ATTACH", "tbl_Assets", asset_id, target.name)
    con.commit()
    return get_asset(con, asset_id)


def get_attachment(con, att_id: int) -> dict:
    att = one(con, "SELECT * FROM tbl_AssetAttachments WHERE AttachmentID=?", (att_id,))
    if not att or not Path(att["FilePath"] or "").is_file():
        raise ApiError("Attachment file not found", 404)
    return att


def delete_attachment(con, att_id: int) -> dict:
    att = one(con, "SELECT * FROM tbl_AssetAttachments WHERE AttachmentID=?", (att_id,))
    if not att:
        raise ApiError("Attachment not found", 404)
    _remove_file(att["FilePath"])
    con.execute("DELETE FROM tbl_AssetAttachments WHERE AttachmentID=?", (att_id,))
    audit(con, "DETACH", "tbl_Assets", att["AssetID"], att["FileName"])
    con.commit()
    return get_asset(con, att["AssetID"])


# ---------------------------------------------------------------- inquiries & dashboard
def journal(con, period_id: str = "", jtype: str = "") -> list[dict]:
    sql = """SELECT J.*, G.AccountCode, G.AccountName, G.AccountNameAr, P.PeriodName FROM tbl_DepreciationJournal J
             LEFT JOIN tbl_GLAccounts G ON G.GLAccountID=J.GLAccountID
             LEFT JOIN tbl_DepreciationPeriods P ON P.PeriodID=J.PeriodID WHERE 1=1"""
    args: list = []
    if period_id:
        sql += " AND J.PeriodID=?"; args.append(period_id)
    if jtype:
        sql += " AND J.JournalType=?"; args.append(jtype)
    return rows(con, sql + " ORDER BY J.JournalDate DESC, J.JournalID DESC", args)


def transactions(con) -> list[dict]:
    return rows(con, """SELECT T.*, A.AssetCode, A.AssetName, A.AssetNameAr FROM tbl_AssetTransactions T
        JOIN tbl_Assets A ON A.AssetID=T.AssetID ORDER BY T.TransactionDate DESC, T.TransactionID DESC LIMIT 2000""")


def audit_log(con) -> list[dict]:
    return rows(con, "SELECT * FROM tbl_AuditLog ORDER BY LogID DESC LIMIT 1000")


def dashboard(con) -> dict:
    assets = [a for a in list_assets(con) if a["AssetStatus"] != "Disposed"]
    cost = sum(a["AcquisitionCost"] for a in assets)
    acc = sum(a["AccumDep"] for a in assets)
    by_cat: dict[str, dict] = {}
    for a in assets:
        c = by_cat.setdefault(a["CategoryName"] or "-", {"name": a["CategoryName"] or "-", "cost": 0, "nbv": 0, "count": 0})
        c["cost"] += a["AcquisitionCost"]; c["nbv"] += a["NBV"]; c["count"] += 1
    today = date.today().isoformat()
    cur = period_for_date(con, today)
    by_year = rows(con, """SELECT P.FiscalYear y, P.PeriodNumber n, P.PeriodName name, SUM(D.PeriodDepreciation) amt
        FROM tbl_Depreciation D JOIN tbl_DepreciationPeriods P ON P.PeriodID=D.PeriodID WHERE D.PostingStatus='POSTED'
        GROUP BY P.PeriodID ORDER BY P.StartDate DESC LIMIT 12""")[::-1]
    open_p = one(con, """SELECT P.* FROM tbl_DepreciationPeriods P WHERE P.PeriodStatus='OPEN' AND NOT EXISTS
        (SELECT 1 FROM tbl_Depreciation D WHERE D.PeriodID=P.PeriodID AND D.PostingStatus='POSTED')
        ORDER BY P.StartDate LIMIT 1""")
    warranty = rows(con, """SELECT AssetID,AssetCode,AssetName,AssetNameAr,WarrantyExpiryDate FROM tbl_Assets WHERE AssetStatus<>'Disposed'
        AND WarrantyExpiryDate IS NOT NULL AND WarrantyExpiryDate BETWEEN ? AND date(?,'+90 day') ORDER BY WarrantyExpiryDate""", (today, today))
    return {
        "asset_count": len(assets), "cost": r2(cost), "accum_dep": r2(acc), "nbv": r2(cost - acc),
        "by_category": sorted(by_cat.values(), key=lambda c: -c["cost"]),
        "dep_trend": by_year,
        "next_period": open_p, "current_period": cur,
        "draft_lines": one(con, "SELECT COUNT(*) n FROM tbl_Depreciation WHERE PostingStatus='DRAFT'")["n"],
        "status_counts": rows(con, "SELECT AssetStatus s, COUNT(*) n FROM tbl_Assets GROUP BY AssetStatus"),
        "warranty": warranty,
        "recent": rows(con, """SELECT T.*, A.AssetCode, A.AssetName, A.AssetNameAr FROM tbl_AssetTransactions T JOIN tbl_Assets A ON A.AssetID=T.AssetID
                               ORDER BY T.TransactionID DESC LIMIT 8"""),
        "currency": get_settings(con).get("DefaultCurrency") or "SAR",
        "maint_open": one(con, "SELECT COUNT(*) n FROM tbl_Maintenance WHERE Status IN ('Planned','In Progress')")["n"],
        "maint_overdue": one(con, "SELECT COUNT(*) n FROM tbl_Maintenance WHERE Status IN ('Planned','In Progress') AND ScheduledDate<?", (today,))["n"],
        "maint_due": [_maint_flags(m) for m in rows(con, MAINT_SQL + " WHERE M.Status IN ('Planned','In Progress') ORDER BY M.ScheduledDate LIMIT 6")],
    }


# ---------------------------------------------------------------- maintenance
MAINT_TYPES = ["Preventive", "Corrective", "Inspection"]
MAINT_PRIORITIES = ["Low", "Medium", "High"]
MAINT_STATUSES = ["Planned", "In Progress", "Completed", "Cancelled"]

MAINT_SQL = """SELECT M.*, A.AssetCode, A.AssetName, A.AssetNameAr, A.CategoryID, C.CategoryName, C.CategoryNameAr
    FROM tbl_Maintenance M JOIN tbl_Assets A ON A.AssetID=M.AssetID
    LEFT JOIN tbl_AssetCategories C ON C.CategoryID=A.CategoryID"""


def _maint_flags(m: dict) -> dict:
    m["IsOverdue"] = bool(m["Status"] in ("Planned", "In Progress") and m["ScheduledDate"] < date.today().isoformat())
    return m


def list_maintenance(con, status: str = "", mtype: str = "", asset: str = "") -> list[dict]:
    sql, args = MAINT_SQL + " WHERE 1=1", []
    if status == "Open":
        sql += " AND M.Status IN ('Planned','In Progress')"
    elif status:
        sql += " AND M.Status=?"
        args.append(status)
    if mtype:
        sql += " AND M.MaintenanceType=?"
        args.append(mtype)
    if asset:
        sql += " AND M.AssetID=?"
        args.append(asset)
    return [_maint_flags(m) for m in rows(con, sql + " ORDER BY M.ScheduledDate DESC, M.MaintenanceID DESC", args)]


def get_maintenance(con, mid: int) -> dict:
    m = one(con, MAINT_SQL + " WHERE M.MaintenanceID=?", (mid,), raw=True)
    if not m:
        raise ApiError("Maintenance order not found", 404)
    return _maint_flags(m)


def _next_maint_no(con) -> str:
    mx = 0
    for r in con.execute("SELECT MaintenanceNo FROM tbl_Maintenance"):
        m = re.fullmatch(r"MT-(\d+)", r["MaintenanceNo"])
        if m:
            mx = max(mx, int(m.group(1)))
    return f"MT-{mx + 1:04d}"


def _clean_maint(con, data: dict) -> dict:
    v: dict[str, Any] = {}
    aid = int(data.get("AssetID") or 0)
    a = one(con, "SELECT AssetID,AssetStatus FROM tbl_Assets WHERE AssetID=?", (aid,))
    if not a:
        raise ApiError("Asset is required")
    if a["AssetStatus"] == "Disposed":
        raise ApiError("Asset is disposed")
    v["AssetID"] = aid
    v["MaintenanceType"] = data.get("MaintenanceType") or "Corrective"
    if v["MaintenanceType"] not in MAINT_TYPES:
        raise ApiError("Invalid maintenance type")
    v["Priority"] = data.get("Priority") or "Medium"
    if v["Priority"] not in MAINT_PRIORITIES:
        raise ApiError("Invalid priority")
    v["Title"] = (data.get("Title") or "").strip()
    if not v["Title"]:
        raise ApiError("Title is required")
    v["ScheduledDate"] = parse_date(data.get("ScheduledDate"), "Scheduled date", True)
    v["NextDueDate"] = parse_date(data.get("NextDueDate"), "Next due date")
    v["Cost"] = num(data.get("Cost"), "Cost", 0, 0)
    v["OutOfService"] = 1 if data.get("OutOfService") in (True, 1, "1", "true") else 0
    for f in ("Description", "Vendor", "PerformedBy", "InvoiceNumber", "Notes"):
        v[f] = (data.get(f) or "").strip() or None
    return v


def save_maintenance(con, data: dict, mid: int | None = None) -> dict:
    v = _clean_maint(con, data)
    if mid is None:
        no = _next_maint_no(con)
        cur = con.execute(f"INSERT INTO tbl_Maintenance(MaintenanceNo,{','.join(v)},Status,CreatedAt,CreatedBy) "
                          f"VALUES(?,{','.join('?' * len(v))},'Planned',?,?)", [no, *v.values(), now(), USER])
        mid = cur.lastrowid
        audit(con, "CREATE", "tbl_Maintenance", mid, no)
    else:
        cur_m = get_maintenance(con, mid)
        if cur_m["Status"] in ("Completed", "Cancelled"):
            raise ApiError("A completed or cancelled order cannot be edited")
        if v["AssetID"] != cur_m["AssetID"] and cur_m["Status"] != "Planned":
            raise ApiError("The asset cannot be changed once work has started")
        con.execute(f"UPDATE tbl_Maintenance SET {','.join(k + '=?' for k in v)},ModifiedAt=?,ModifiedBy=? WHERE MaintenanceID=?",
                    [*v.values(), now(), USER, mid])
        if cur_m["Status"] == "In Progress" and cur_m["OutOfService"] != v["OutOfService"]:
            if v["OutOfService"]:
                _set_asset_status(con, v["AssetID"], "Under Repair", cur_m["MaintenanceNo"])
            else:
                _release_asset(con, {**cur_m, "OutOfService": 0})
        audit(con, "UPDATE", "tbl_Maintenance", mid, cur_m["MaintenanceNo"])
    con.commit()
    return get_maintenance(con, mid)


def _set_asset_status(con, asset_id: int, new: str, note: str) -> None:
    cur = one(con, "SELECT AssetStatus FROM tbl_Assets WHERE AssetID=?", (asset_id,))["AssetStatus"]
    if cur == new or cur == "Disposed":
        return
    con.execute("UPDATE tbl_Assets SET AssetStatus=?,ModifiedAt=?,ModifiedBy=? WHERE AssetID=?", (new, now(), USER, asset_id))
    con.execute("INSERT INTO tbl_AssetTransactions(AssetID,TransactionType,TransactionDate,Notes,CreatedAt,CreatedBy) VALUES(?,?,?,?,?,?)",
                (asset_id, "STATUS", date.today().isoformat(), f"{cur} -> {new} ({note})", now(), USER))


def _release_asset(con, m: dict) -> None:
    """Back to Active when no other out-of-service order is still running for the asset."""
    other = one(con, "SELECT 1 x FROM tbl_Maintenance WHERE AssetID=? AND MaintenanceID<>? AND Status='In Progress' AND OutOfService=1",
                (m["AssetID"], m["MaintenanceID"]))
    asset = one(con, "SELECT AssetStatus FROM tbl_Assets WHERE AssetID=?", (m["AssetID"],))
    if not other and asset["AssetStatus"] == "Under Repair":
        _set_asset_status(con, m["AssetID"], "Active", m["MaintenanceNo"])


def maintenance_action(con, mid: int, action: str, data: dict) -> dict:
    m = get_maintenance(con, mid)
    st = m["Status"]
    if action == "start":
        if st != "Planned":
            raise ApiError("Only a planned order can be started")
        d = parse_date(data.get("StartDate"), "Start date") or date.today().isoformat()
        con.execute("UPDATE tbl_Maintenance SET Status='In Progress',StartDate=?,ModifiedAt=?,ModifiedBy=? WHERE MaintenanceID=?",
                    (d, now(), USER, mid))
        if m["OutOfService"]:
            _set_asset_status(con, m["AssetID"], "Under Repair", m["MaintenanceNo"])
    elif action == "complete":
        if st not in ("Planned", "In Progress"):
            raise ApiError("Only an open order can be completed")
        done = parse_date(data.get("CompletionDate"), "Completion date", True)
        start = m["StartDate"] or done
        if done < start:
            raise ApiError("Completion date cannot be before the start date")
        cost = num(data.get("Cost"), "Cost", m["Cost"], 0)
        nxt = parse_date(data.get("NextDueDate"), "Next due date") or m["NextDueDate"]
        if nxt and nxt <= done:
            raise ApiError("Next due date must be after the completion date")
        con.execute("UPDATE tbl_Maintenance SET Status='Completed',StartDate=?,CompletionDate=?,Cost=?,NextDueDate=?,"
                    "Vendor=COALESCE(?,Vendor),PerformedBy=COALESCE(?,PerformedBy),InvoiceNumber=COALESCE(?,InvoiceNumber),"
                    "Notes=COALESCE(?,Notes),ModifiedAt=?,ModifiedBy=? WHERE MaintenanceID=?",
                    (start, done, cost, nxt, (data.get("Vendor") or "").strip() or None, (data.get("PerformedBy") or "").strip() or None,
                     (data.get("InvoiceNumber") or "").strip() or None, (data.get("Notes") or "").strip() or None, now(), USER, mid))
        _release_asset(con, m)
    elif action == "cancel":
        if st not in ("Planned", "In Progress"):
            raise ApiError("Only an open order can be cancelled")
        con.execute("UPDATE tbl_Maintenance SET Status='Cancelled',ModifiedAt=?,ModifiedBy=? WHERE MaintenanceID=?", (now(), USER, mid))
        _release_asset(con, m)
    else:
        raise ApiError("Unknown action")
    audit(con, action.upper(), "tbl_Maintenance", mid, m["MaintenanceNo"])
    con.commit()
    return get_maintenance(con, mid)


def delete_maintenance(con, mid: int) -> dict:
    m = get_maintenance(con, mid)
    if m["Status"] not in ("Planned", "Cancelled"):
        raise ApiError("Only a planned or cancelled order can be deleted")
    con.execute("DELETE FROM tbl_Maintenance WHERE MaintenanceID=?", (mid,))
    audit(con, "DELETE", "tbl_Maintenance", mid, m["MaintenanceNo"])
    con.commit()
    return {"deleted": mid}
