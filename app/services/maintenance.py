"""Maintenance orders."""
from __future__ import annotations

import re
from datetime import date
from typing import Any

from .common import ApiError, actor, audit, now, num, one, parse_date, rows, scope_sql, to_int

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
    sql, args = MAINT_SQL + " WHERE 1=1" + scope_sql("A"), []
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
    m = one(con, MAINT_SQL + " WHERE M.MaintenanceID=?" + scope_sql("A"), (mid,), raw=True)
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


def _vendor(con, data: dict) -> dict:
    """Vendor of a maintenance order: a registered supplier (preferred) or free text."""
    sid = to_int(data.get("SupplierID"), "SupplierID") or None
    if sid:
        sup = one(con, "SELECT SupplierName FROM tbl_Suppliers WHERE SupplierID=?", (sid,), raw=True)
        if not sup:
            raise ApiError("Supplier not found")
        return {"SupplierID": sid, "Vendor": sup["SupplierName"]}
    return {"SupplierID": None, "Vendor": (data.get("Vendor") or "").strip() or None}


def _clean_maint(con, data: dict) -> dict:
    v: dict[str, Any] = {}
    aid = to_int(data.get("AssetID"), "AssetID")
    a = one(con, "SELECT AssetID,AssetStatus FROM tbl_Assets A WHERE AssetID=?" + scope_sql("A"), (aid,))
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
    for f in ("Description", "PerformedBy", "InvoiceNumber", "Notes"):
        v[f] = (data.get(f) or "").strip() or None
    v.update(_vendor(con, data))
    return v


def save_maintenance(con, data: dict, mid: int | None = None) -> dict:
    v = _clean_maint(con, data)
    if mid is None:
        no = _next_maint_no(con)
        cur = con.execute(f"INSERT INTO tbl_Maintenance(MaintenanceNo,{','.join(v)},Status,CreatedAt,CreatedBy) "
                          f"VALUES(?,{','.join('?' * len(v))},'Planned',?,?)", [no, *v.values(), now(), actor()])
        mid = cur.lastrowid
        audit(con, "CREATE", "tbl_Maintenance", mid, no)
    else:
        cur_m = get_maintenance(con, mid)
        if cur_m["Status"] in ("Completed", "Cancelled"):
            raise ApiError("A completed or cancelled order cannot be edited")
        if v["AssetID"] != cur_m["AssetID"] and cur_m["Status"] != "Planned":
            raise ApiError("The asset cannot be changed once work has started")
        con.execute(f"UPDATE tbl_Maintenance SET {','.join(k + '=?' for k in v)},ModifiedAt=?,ModifiedBy=? WHERE MaintenanceID=?",
                    [*v.values(), now(), actor(), mid])
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
    if cur == new or cur == "Disposed" or (new == "Under Repair" and cur != "Active"):
        return
    con.execute("UPDATE tbl_Assets SET AssetStatus=?,ModifiedAt=?,ModifiedBy=? WHERE AssetID=?", (new, now(), actor(), asset_id))
    con.execute("INSERT INTO tbl_AssetTransactions(AssetID,TransactionType,TransactionDate,Notes,CreatedAt,CreatedBy) VALUES(?,?,?,?,?,?)",
                (asset_id, "STATUS", date.today().isoformat(), f"{cur} -> {new} ({note})", now(), actor()))


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
                    (d, now(), actor(), mid))
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
        ven = _vendor(con, data) if (data.get("SupplierID") or data.get("Vendor")) else {"SupplierID": m["SupplierID"], "Vendor": m["Vendor"]}
        con.execute("UPDATE tbl_Maintenance SET Status='Completed',StartDate=?,CompletionDate=?,Cost=?,NextDueDate=?,"
                    "Vendor=?,SupplierID=?,PerformedBy=COALESCE(?,PerformedBy),InvoiceNumber=COALESCE(?,InvoiceNumber),"
                    "Notes=COALESCE(?,Notes),ModifiedAt=?,ModifiedBy=? WHERE MaintenanceID=?",
                    (start, done, cost, nxt, ven["Vendor"], ven["SupplierID"], (data.get("PerformedBy") or "").strip() or None,
                     (data.get("InvoiceNumber") or "").strip() or None, (data.get("Notes") or "").strip() or None, now(), actor(), mid))
        _release_asset(con, m)
    elif action == "cancel":
        if st not in ("Planned", "In Progress"):
            raise ApiError("Only an open order can be cancelled")
        con.execute("UPDATE tbl_Maintenance SET Status='Cancelled',ModifiedAt=?,ModifiedBy=? WHERE MaintenanceID=?", (now(), actor(), mid))
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
