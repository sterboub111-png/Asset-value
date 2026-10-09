"""Settings, master data (groups, locations, ...) and the lookup bundle sent to the UI."""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from .branches import check_country, countries
from .common import ASSET_STATUSES, ApiError, actor, audit, num, one, rows, to_int
from .maintenance import MAINT_PRIORITIES, MAINT_STATUSES, MAINT_TYPES
from .suppliers import SUPPLIER_TYPES

def get_settings(con) -> dict[str, str]:
    return {r["SettingKey"]: r["SettingValue"] or "" for r in con.execute("SELECT * FROM tbl_Settings")}


# ---------------------------------------------------------------- master data
MASTERS: dict[str, dict] = {
    "categories": dict(table="tbl_AssetCategories", pk="CategoryID", code="CategoryCode", name="CategoryName",
                       fields=["CategoryCode", "CategoryName", "CategoryNameAr", "UsefulLifeYears", "DepreciationRate", "MethodID",
                               "AssetAccountID", "AccumDepAccountID", "DepExpenseAccountID", "GainAccountID",
                               "LossAccountID", "IsActive"],
                       used_by=[("tbl_Assets", "CategoryID")], order="CategoryCode"),
    "branches": dict(table="tbl_Branches", pk="BranchID", code="BranchCode", name="BranchName",
                     fields=["BranchCode", "BranchName", "BranchNameAr", "CountryCode", "City", "Region", "IsActive"],
                     used_by=[("tbl_Locations", "BranchID"), ("tbl_UserBranches", "BranchID")], order="CountryCode, BranchCode"),
    "locations": dict(table="tbl_Locations", pk="LocationID", code="LocationCode", name="LocationName",
                      fields=["LocationCode", "LocationName", "LocationNameAr", "BranchID", "IsActive"],
                      used_by=[("tbl_Assets", "LocationID"), ("tbl_AssetTransactions", "FromLocationID"), ("tbl_AssetTransactions", "ToLocationID")], order="LocationCode"),
    "costcenters": dict(table="tbl_CostCenters", pk="CostCenterID", code="CostCenterCode", name="CostCenterName",
                        fields=["CostCenterCode", "CostCenterName", "CostCenterNameAr", "IsActive"],
                        used_by=[("tbl_Assets", "CostCenterID"), ("tbl_AssetTransactions", "FromCostCenterID"), ("tbl_AssetTransactions", "ToCostCenterID")], order="CostCenterCode"),
    "glaccounts": dict(table="tbl_GLAccounts", pk="GLAccountID", code="AccountCode", name="AccountName",
                       fields=["AccountCode", "AccountName", "AccountNameAr", "AccountType", "IsActive"],
                       used_by=[("tbl_DepreciationJournal", "GLAccountID"), ("tbl_AssetCategories", "AssetAccountID"),
                                ("tbl_AssetCategories", "AccumDepAccountID"),
                                ("tbl_AssetCategories", "DepExpenseAccountID"),
                                ("tbl_AssetCategories", "GainAccountID"), ("tbl_AssetCategories", "LossAccountID")],
                       order="AccountCode"),
    "currencies": dict(table="tbl_Currencies", pk="CurrencyID", code="CurrencyCode", name="CurrencyName",
                       fields=["CurrencyCode", "CurrencyName", "CurrencyNameAr", "Symbol", "IsActive"], used_by=[], order="CurrencyCode"),
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
    if name == "currencies":
        if "CurrencyCode" in vals:
            vals["CurrencyCode"] = (vals["CurrencyCode"] or "").upper()
            if not re.fullmatch(r"[A-Z]{3}", vals["CurrencyCode"]):
                raise ApiError("Currency code must be 3 letters (ISO 4217)")
        if vals.get("IsActive") == 0 and rec_id:
            cur = one(con, "SELECT CurrencyCode FROM tbl_Currencies WHERE CurrencyID=?", (rec_id,), raw=True)
            if cur and cur["CurrencyCode"] == get_settings(con).get("DefaultCurrency"):
                raise ApiError("The default currency cannot be made inactive")
    if name == "branches" and ("CountryCode" in vals or rec_id is None):
        vals["CountryCode"] = check_country(vals.get("CountryCode"))
    if name == "locations" and ("BranchID" in vals or rec_id is None):
        vals["BranchID"] = to_int(vals.get("BranchID"), "Branch") or None
        if vals["BranchID"] and not one(con, "SELECT 1 x FROM tbl_Branches WHERE BranchID=?", (vals["BranchID"],)):
            raise ApiError("Branch not found")
        if not vals["BranchID"] and one(con, "SELECT 1 x FROM tbl_Branches LIMIT 1"):
            raise ApiError("Choose the branch of this location")
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
    if name == "currencies":
        cur = one(con, "SELECT CurrencyCode FROM tbl_Currencies WHERE CurrencyID=?", (rec_id,), raw=True)
        if cur and cur["CurrencyCode"] == get_settings(con).get("DefaultCurrency"):
            raise ApiError("The default currency cannot be deleted")
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
        if k == "FiscalYearStartMonth" and v != (get_settings(con).get("FiscalYearStartMonth") or "1") and \
                one(con, "SELECT 1 x FROM tbl_DepreciationPeriods LIMIT 1", raw=True):
            raise ApiError("The fiscal year start month cannot be changed after periods have been created")
        if k == "AssetCodePrefix" and not v:
            raise ApiError("Asset code prefix is required")
        if k == "DefaultCurrency" and not one(con, "SELECT 1 x FROM tbl_Currencies WHERE CurrencyCode=? AND IsActive=1", (v,)):
            raise ApiError("Choose a currency from the list")
        if k == "VATRate":
            try:
                ok = 0 <= float(v) <= 100
            except ValueError:
                ok = False
            if not ok:
                raise ApiError("VAT rate must be between 0 and 100")
        if k in ("VATEnabled", "VATDefaultApplicable", "VATDefaultInclusive"):
            v = "1" if v in ("1", "true", "True") else "0"
        if k == "BackupSchedule" and v not in ("OFF", "DAILY", "WEEKLY", "MONTHLY", "QUARTERLY"):
            raise ApiError("Invalid backup frequency")
        if k == "BackupTime" and not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", v):
            raise ApiError("Backup time must be HH:MM")
        if k == "BackupWeekday" and v not in [str(i) for i in range(7)]:
            raise ApiError("Invalid weekday")
        if k == "BackupDayOfMonth" and not (v.isdigit() and 1 <= int(v) <= 28):
            raise ApiError("Day of month must be 1-28")
        if k == "BackupKeep" and not (v.isdigit() and int(v) <= 999):
            raise ApiError("Backups to keep must be 0-999")
        if k in ("BackupFolder", "AttachmentFolder") and v:
            try:
                Path(v).mkdir(parents=True, exist_ok=True)
                probe = Path(v) / ".gooya_write_test"
                probe.write_text("ok")
                probe.unlink()
            except OSError:
                raise ApiError("This folder cannot be used (missing or not writable)")
        con.execute("UPDATE tbl_Settings SET SettingValue=? WHERE SettingKey=?", (v, k))
    audit(con, "UPDATE", "tbl_Settings", "-", ", ".join(data))
    con.commit()
    return get_settings(con)


def lookups(con) -> dict:
    return {
        "categories": master_list(con, "categories"),
        "locations": master_list(con, "locations"),
        "branches": master_list(con, "branches"),
        "countries": countries(),
        "costcenters": master_list(con, "costcenters"),
        "glaccounts": master_list(con, "glaccounts"),
        "methods": master_list(con, "methods"),
        "currencies": master_list(con, "currencies"),
        "suppliers": rows(con, "SELECT SupplierID,SupplierCode,SupplierName,SupplierNameAr,IsActive FROM tbl_Suppliers ORDER BY SupplierName", raw=True),
        "employees": rows(con, "SELECT EmployeeID,EmployeeCode,EmployeeName,EmployeeNameAr,JobTitle,Department,IsActive FROM tbl_Employees ORDER BY EmployeeName", raw=True),
        "supplier_types": SUPPLIER_TYPES,
        "periods": rows(con, "SELECT * FROM tbl_DepreciationPeriods ORDER BY StartDate"),
        "settings": get_settings(con),
        "statuses": ASSET_STATUSES,
        "maint_types": MAINT_TYPES, "maint_priorities": MAINT_PRIORITIES, "maint_statuses": MAINT_STATUSES,
        "user": actor(),
    }
