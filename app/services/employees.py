"""Employees."""
from __future__ import annotations

import re
from typing import Any

from .common import ApiError, actor, audit, now, one, parse_date, rows
from .custody import list_custody

# ---------------------------------------------------------------- employees
EMPLOYEE_FIELDS = ["EmployeeName", "EmployeeNameAr", "JobTitle", "Department", "Phone", "Mobile", "Email", "NationalID", "HireDate", "Notes"]

EMPLOYEE_LIST_SQL = """SELECT E.*,
  (SELECT COUNT(*) FROM tbl_AssetCustody C WHERE C.EmployeeID=E.EmployeeID AND C.Status='Issued') AS HeldCount,
  (SELECT COUNT(*) FROM tbl_AssetCustody C WHERE C.EmployeeID=E.EmployeeID) AS TotalCustody
  FROM tbl_Employees E"""


def list_employees(con, q: str = "", status: str = "") -> list[dict]:
    sql, args = EMPLOYEE_LIST_SQL + " WHERE 1=1", []
    if status in ("1", "0"):
        sql += " AND E.IsActive=?"
        args.append(int(status))
    if q:
        sql += " AND (E.EmployeeCode LIKE ? OR E.EmployeeName LIKE ? OR E.EmployeeNameAr LIKE ? OR E.Department LIKE ? OR E.Mobile LIKE ? OR E.Email LIKE ?)"
        args += [f"%{q}%"] * 6
    return rows(con, sql + " ORDER BY E.EmployeeName", args)


def get_employee(con, eid: int) -> dict:
    emp = one(con, EMPLOYEE_LIST_SQL + " WHERE E.EmployeeID=?", (eid,), raw=True)
    if not emp:
        raise ApiError("Employee not found", 404)
    emp["custody"] = list_custody(con, employee=str(eid))
    return emp


def next_employee_code(con) -> str:
    mx = 0
    for r in con.execute("SELECT EmployeeCode FROM tbl_Employees"):
        m = re.fullmatch(r"EMP-(\d+)", r["EmployeeCode"])
        if m:
            mx = max(mx, int(m.group(1)))
    return f"EMP-{mx + 1:04d}"


def save_employee(con, data: dict, eid: int | None = None) -> dict:
    v: dict[str, Any] = {}
    for f in EMPLOYEE_FIELDS:
        raw = data.get(f)
        v[f] = (str(raw).strip() or None) if raw is not None else None
    if not v["EmployeeName"]:
        raise ApiError("Employee name is required")
    v["HireDate"] = parse_date(v["HireDate"], "Hire date")
    if v["Email"] and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", v["Email"]):
        raise ApiError("Email address is not valid")
    for f in ("Phone", "Mobile"):
        if v[f] and not re.fullmatch(r"[+0-9 ()\-./]{5,25}", v[f]):
            raise ApiError(f"{f} is not a valid phone number")
    if v["NationalID"]:
        dup = one(con, "SELECT EmployeeCode FROM tbl_Employees WHERE NationalID=? AND EmployeeID<>?", (v["NationalID"], eid or 0), raw=True)
        if dup:
            raise ApiError(f"This ID number already belongs to employee {dup['EmployeeCode']}")
    active = 0 if data.get("IsActive") in (False, 0, "0", "false") else 1
    code = (data.get("EmployeeCode") or "").strip()
    if len(code) > 20:
        raise ApiError("Employee code is too long")
    if eid is None:
        code = code or next_employee_code(con)
        if one(con, "SELECT 1 x FROM tbl_Employees WHERE lower(EmployeeCode)=lower(?)", (code,), raw=True):
            raise ApiError(f"Employee code {code} already exists")
        cur = con.execute(f"INSERT INTO tbl_Employees(EmployeeCode,{','.join(v)},IsActive,CreatedAt,CreatedBy) VALUES(?,{','.join('?' * len(v))},?,?,?)",
                          [code, *v.values(), active, now(), actor()])
        eid = cur.lastrowid
        audit(con, "CREATE", "tbl_Employees", eid, f"{code} {v['EmployeeName']}")
    else:
        cur_e = one(con, "SELECT EmployeeCode FROM tbl_Employees WHERE EmployeeID=?", (eid,), raw=True)
        if not cur_e:
            raise ApiError("Employee not found", 404)
        code = code or cur_e["EmployeeCode"]
        if one(con, "SELECT 1 x FROM tbl_Employees WHERE lower(EmployeeCode)=lower(?) AND EmployeeID<>?", (code, eid), raw=True):
            raise ApiError(f"Employee code {code} already exists")
        if not active and one(con, "SELECT 1 x FROM tbl_AssetCustody WHERE EmployeeID=? AND Status='Issued' LIMIT 1", (eid,)):
            raise ApiError("This employee still holds assets; take them back before deactivating")
        con.execute(f"UPDATE tbl_Employees SET EmployeeCode=?,{','.join(k + '=?' for k in v)},IsActive=?,ModifiedAt=?,ModifiedBy=? WHERE EmployeeID=?",
                    [code, *v.values(), active, now(), actor(), eid])
        audit(con, "UPDATE", "tbl_Employees", eid, code)
    con.commit()
    return get_employee(con, eid)


def delete_employee(con, eid: int) -> dict:
    emp = get_employee(con, eid)
    if emp["custody"]:
        raise ApiError("This employee has custody records and cannot be deleted. Mark the employee inactive instead.")
    con.execute("DELETE FROM tbl_Employees WHERE EmployeeID=?", (eid,))
    audit(con, "DELETE", "tbl_Employees", eid, emp["EmployeeCode"])
    con.commit()
    return {"deleted": eid}
