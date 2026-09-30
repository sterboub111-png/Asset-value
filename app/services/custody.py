"""Asset custody: issue, return, signed handover forms."""
from __future__ import annotations

import re

from .common import ApiError, actor, audit, now, one, parse_date, rows, to_int
from .settings import get_settings

# ---------------------------------------------------------------- asset custody (employee handover)
# Custody only records who holds an asset; it never touches cost, depreciation or the asset reports.
CUSTODY_SQL = """SELECT U.*, A.AssetCode, A.AssetName, A.AssetNameAr, A.SerialNumber, A.ModelNumber, A.Manufacturer, A.CategoryID,
    C.CategoryName, C.CategoryNameAr, E.EmployeeCode, E.EmployeeName, E.EmployeeNameAr, E.JobTitle, E.Department, E.NationalID, E.Mobile,
    (SELECT COUNT(*) FROM tbl_AssetAttachments T WHERE T.CustodyID=U.CustodyID) AS AttachmentCount
    FROM tbl_AssetCustody U JOIN tbl_Assets A ON A.AssetID=U.AssetID JOIN tbl_Employees E ON E.EmployeeID=U.EmployeeID
    LEFT JOIN tbl_AssetCategories C ON C.CategoryID=A.CategoryID"""


def list_custody(con, status: str = "", employee: str = "", asset: str = "") -> list[dict]:
    sql, args = CUSTODY_SQL + " WHERE 1=1", []
    if status in ("Issued", "Returned"):
        sql += " AND U.Status=?"
        args.append(status)
    if employee:
        sql += " AND U.EmployeeID=?"
        args.append(employee)
    if asset:
        sql += " AND U.AssetID=?"
        args.append(asset)
    return rows(con, sql + " ORDER BY U.IssueDate DESC, U.CustodyID DESC", args)


def get_custody(con, cid: int) -> dict:
    cu = one(con, CUSTODY_SQL + " WHERE U.CustodyID=?", (cid,), raw=True)
    if not cu:
        raise ApiError("Custody record not found", 404)
    cu["attachments"] = rows(con, "SELECT * FROM tbl_AssetAttachments WHERE CustodyID=? ORDER BY AttachmentID DESC", (cid,), raw=True)
    cu["CompanyName"] = get_settings(con).get("CompanyName", "")
    return cu


def _next_custody_no(con) -> str:
    mx = 0
    for r in con.execute("SELECT CustodyNo FROM tbl_AssetCustody"):
        m = re.fullmatch(r"CU-(\d+)", r["CustodyNo"])
        if m:
            mx = max(mx, int(m.group(1)))
    return f"CU-{mx + 1:04d}"


def issue_custody(con, data: dict) -> dict:
    aid = to_int(data.get("AssetID"), "AssetID")
    eid = to_int(data.get("EmployeeID"), "EmployeeID")
    asset = one(con, "SELECT AssetID, AssetCode, AssetStatus, AcquisitionDate FROM tbl_Assets WHERE AssetID=?", (aid,), raw=True)
    emp = one(con, "SELECT EmployeeID, EmployeeCode, IsActive FROM tbl_Employees WHERE EmployeeID=?", (eid,), raw=True)
    if not asset:
        raise ApiError("Asset is required")
    if not emp:
        raise ApiError("Employee is required")
    if asset["AssetStatus"] == "Disposed":
        raise ApiError("Asset is disposed")
    if not emp["IsActive"]:
        raise ApiError("This employee is inactive")
    held = one(con, "SELECT U.CustodyNo, E.EmployeeName FROM tbl_AssetCustody U JOIN tbl_Employees E ON E.EmployeeID=U.EmployeeID WHERE U.AssetID=? AND U.Status='Issued'", (aid,), raw=True)
    if held:
        raise ApiError(f"This asset is already with {held['EmployeeName']} ({held['CustodyNo']}). Return it first.")
    issue = parse_date(data.get("IssueDate"), "Issue date", True)
    if issue < asset["AcquisitionDate"]:
        raise ApiError("Issue date cannot be before the acquisition date")
    v = {f: ((data.get(f) or "").strip() or None) for f in ("ConditionOnIssue", "Accessories", "Notes", "IssuedBy")}
    no = _next_custody_no(con)
    cur = con.execute("INSERT INTO tbl_AssetCustody(CustodyNo,AssetID,EmployeeID,IssueDate,Status,ConditionOnIssue,Accessories,Notes,IssuedBy,CreatedAt,CreatedBy) "
                      "VALUES(?,?,?,?,'Issued',?,?,?,?,?,?)", (no, aid, eid, issue, v["ConditionOnIssue"], v["Accessories"], v["Notes"], v["IssuedBy"], now(), actor()))
    audit(con, "CUSTODY ISSUE", "tbl_AssetCustody", cur.lastrowid, f"{no}: {asset['AssetCode']} -> {emp['EmployeeCode']}")
    con.commit()
    return get_custody(con, cur.lastrowid)


def update_custody(con, cid: int, data: dict) -> dict:
    cu = get_custody(con, cid)
    if cu["Status"] != "Issued":
        raise ApiError("A returned custody record cannot be edited")
    issue = parse_date(data.get("IssueDate"), "Issue date", True)
    if issue < one(con, "SELECT AcquisitionDate FROM tbl_Assets WHERE AssetID=?", (cu["AssetID"],), raw=True)["AcquisitionDate"]:
        raise ApiError("Issue date cannot be before the acquisition date")
    v = {f: ((data.get(f) or "").strip() or None) for f in ("ConditionOnIssue", "Accessories", "Notes", "IssuedBy")}
    con.execute("UPDATE tbl_AssetCustody SET IssueDate=?,ConditionOnIssue=?,Accessories=?,Notes=?,IssuedBy=?,ModifiedAt=?,ModifiedBy=? WHERE CustodyID=?",
                (issue, v["ConditionOnIssue"], v["Accessories"], v["Notes"], v["IssuedBy"], now(), actor(), cid))
    audit(con, "CUSTODY UPDATE", "tbl_AssetCustody", cid, cu["CustodyNo"])
    con.commit()
    return get_custody(con, cid)


def return_custody(con, cid: int, data: dict) -> dict:
    cu = get_custody(con, cid)
    if cu["Status"] != "Issued":
        raise ApiError("This asset was already returned")
    ret = parse_date(data.get("ReturnDate"), "Return date", True)
    if ret < cu["IssueDate"]:
        raise ApiError("Return date cannot be before the issue date")
    con.execute("UPDATE tbl_AssetCustody SET Status='Returned',ReturnDate=?,ConditionOnReturn=?,ReturnNotes=?,ModifiedAt=?,ModifiedBy=? WHERE CustodyID=?",
                (ret, (data.get("ConditionOnReturn") or "").strip() or None, (data.get("ReturnNotes") or "").strip() or None, now(), actor(), cid))
    audit(con, "CUSTODY RETURN", "tbl_AssetCustody", cid, cu["CustodyNo"])
    con.commit()
    return get_custody(con, cid)


def delete_custody(con, cid: int) -> dict:
    cu = get_custody(con, cid)
    if cu["Status"] != "Issued" or cu["attachments"]:
        raise ApiError("Only an issued custody record without signed documents can be deleted")
    con.execute("DELETE FROM tbl_AssetCustody WHERE CustodyID=?", (cid,))
    audit(con, "CUSTODY DELETE", "tbl_AssetCustody", cid, cu["CustodyNo"])
    con.commit()
    return {"deleted": cid}


def add_custody_attachment(con, cid: int, filename: str, content: bytes, meta: dict) -> dict:
    cu = get_custody(con, cid)
    from .attachments import add_attachment   # imported here: attachments -> assets -> custody would otherwise be a cycle
    add_attachment(con, cu["AssetID"], filename, content, {**meta, "custody_id": cid, "type": meta.get("type") or "Custody form"})
    return get_custody(con, cid)
