"""Physical inventory (asset counts): compare what is on the floor with what is in the books.

A count takes a snapshot of the assets expected (one location, or all of them). Each scan or typed code marks an asset
found; assets found elsewhere, unknown codes and disposed assets are recorded as such. Closing the count can move the
assets found at another location there (a normal transfer), and leaves the missing ones listed for follow-up.
"""
from __future__ import annotations

import re

from .assets import transfer_asset
from .common import ApiError, actor, audit, now, one, parse_date, rows, to_int

COUNT_SQL = """SELECT C.*, L.LocationName, L.LocationNameAr,
  (SELECT COUNT(*) FROM tbl_AssetCountLines X WHERE X.CountID=C.CountID AND X.Expected=1) AS ExpectedCount,
  (SELECT COUNT(*) FROM tbl_AssetCountLines X WHERE X.CountID=C.CountID AND X.Found=1 AND X.Expected=1) AS FoundCount,
  (SELECT COUNT(*) FROM tbl_AssetCountLines X WHERE X.CountID=C.CountID AND X.Found=1 AND X.Expected=0) AS ExtraCount
  FROM tbl_AssetCounts C LEFT JOIN tbl_Locations L ON L.LocationID=C.LocationID"""

LINE_SQL = """SELECT X.*, A.AssetCode, A.AssetName, A.AssetNameAr, A.AssetStatus, A.SerialNumber, A.LocationID AS BookLocationID,
  C.CategoryName, C.CategoryNameAr, BL.LocationName AS BookLocation, BL.LocationNameAr AS BookLocationAr,
  FL.LocationName AS FoundLocation, FL.LocationNameAr AS FoundLocationAr, A.AcquisitionCost,
  A.AcquisitionCost - COALESCE(A.OpeningAccumDep,0) - COALESCE((SELECT SUM(D.PeriodDepreciation) FROM tbl_Depreciation D
     WHERE D.AssetID=A.AssetID AND D.PostingStatus='POSTED'),0) AS NBV
  FROM tbl_AssetCountLines X LEFT JOIN tbl_Assets A ON A.AssetID=X.AssetID
  LEFT JOIN tbl_AssetCategories C ON C.CategoryID=A.CategoryID
  LEFT JOIN tbl_Locations BL ON BL.LocationID=A.LocationID LEFT JOIN tbl_Locations FL ON FL.LocationID=X.FoundLocationID"""


def _result(line: dict) -> str:
    """found / missing / extra (found where it was not expected) / unknown (no such asset) / disposed / moved (found at another location)."""
    if not line["AssetID"]:
        return "unknown"
    if line["Found"] and line["AssetStatus"] == "Disposed":
        return "disposed"
    if line["Found"] and not line["Expected"]:
        return "extra"
    if not line["Found"]:
        return "missing"
    if line["FoundLocationID"] and line["BookLocationID"] != line["FoundLocationID"]:
        return "moved"
    return "found"


def list_counts(con) -> list[dict]:
    return rows(con, COUNT_SQL + " ORDER BY C.CountDate DESC, C.CountID DESC")


def get_count(con, cid: int) -> dict:
    c = one(con, COUNT_SQL + " WHERE C.CountID=?", (cid,))
    if not c:
        raise ApiError("Count not found", 404)
    lines = rows(con, LINE_SQL + " WHERE X.CountID=? ORDER BY X.Found, A.AssetCode, X.LineID", (cid,))
    summary = {k: 0 for k in ("found", "missing", "extra", "unknown", "disposed", "moved")}
    for ln in lines:
        ln["Result"] = _result(ln)
        ln["NBV"] = round(ln["NBV"] or 0, 2) if ln["AssetID"] else None
        summary[ln["Result"]] += 1
    c["lines"], c["summary"] = lines, summary
    c["MissingNBV"] = round(sum(ln["NBV"] or 0 for ln in lines if ln["Result"] == "missing"), 2)
    return c


def _next_no(con) -> str:
    mx = 0
    for r in con.execute("SELECT CountNo FROM tbl_AssetCounts"):
        m = re.fullmatch(r"CNT-(\d+)", r["CountNo"])
        if m:
            mx = max(mx, int(m.group(1)))
    return f"CNT-{mx + 1:04d}"


def create_count(con, data: dict) -> dict:
    d = parse_date(data.get("CountDate"), "Count date", True)
    loc = to_int(data.get("LocationID"), "Location") or None
    if loc and not one(con, "SELECT 1 x FROM tbl_Locations WHERE LocationID=?", (loc,), raw=True):
        raise ApiError("Location not found")
    if one(con, "SELECT 1 x FROM tbl_AssetCounts WHERE Status='Open' AND COALESCE(LocationID,0)=?", (loc or 0,), raw=True):
        raise ApiError("A count for this location is already open. Close it first.")
    title = (data.get("Title") or "").strip()
    no = _next_no(con)
    cid = con.execute("INSERT INTO tbl_AssetCounts(CountNo,Title,CountDate,LocationID,Status,Notes,CreatedAt,CreatedBy) VALUES(?,?,?,?,'Open',?,?,?)",
                      (no, title or no, d, loc, (data.get("Notes") or "").strip() or None, now(), actor())).lastrowid
    # the snapshot: every asset in the books (at that location) is expected
    sql = "SELECT AssetID FROM tbl_Assets WHERE AssetStatus<>'Disposed' AND AcquisitionDate<=?" + (" AND LocationID=?" if loc else "")
    con.executemany("INSERT INTO tbl_AssetCountLines(CountID,AssetID,Expected,Found) VALUES(?,?,1,0)",
                    [(cid, r["AssetID"]) for r in con.execute(sql, (d, loc) if loc else (d,))])
    audit(con, "COUNT OPEN", "tbl_AssetCounts", cid, no)
    con.commit()
    return get_count(con, cid)


def _open(con, cid: int) -> dict:
    c = one(con, "SELECT * FROM tbl_AssetCounts WHERE CountID=?", (cid,), raw=True)
    if not c:
        raise ApiError("Count not found", 404)
    if c["Status"] != "Open":
        raise ApiError("This count is closed")
    return c


def scan(con, cid: int, data: dict) -> dict:
    """One scanned or typed code: the asset code (or its serial number). Returns what happened and the line."""
    c = _open(con, cid)
    code = (data.get("code") or "").strip()
    if not code:
        raise ApiError("Scan or type an asset code")
    found_loc = to_int(data.get("LocationID"), "Location") or c["LocationID"]
    a = one(con, "SELECT AssetID, AssetCode, AssetStatus FROM tbl_Assets WHERE lower(AssetCode)=lower(?)", (code,), raw=True) or \
        one(con, "SELECT AssetID, AssetCode, AssetStatus FROM tbl_Assets WHERE SerialNumber IS NOT NULL AND lower(SerialNumber)=lower(?) LIMIT 1", (code,), raw=True)
    if not a:
        dup = one(con, "SELECT LineID FROM tbl_AssetCountLines WHERE CountID=? AND AssetID IS NULL AND lower(ScannedCode)=lower(?)", (cid, code), raw=True)
        if dup:
            return {"status": "already", "line": _line(con, dup["LineID"])}
        lid = con.execute("INSERT INTO tbl_AssetCountLines(CountID,ScannedCode,Expected,Found,FoundLocationID,FoundAt,FoundBy) VALUES(?,?,0,1,?,?,?)",
                          (cid, code, found_loc, now(), actor())).lastrowid
        con.commit()
        return {"status": "unknown", "line": _line(con, lid)}
    ln = one(con, "SELECT * FROM tbl_AssetCountLines WHERE CountID=? AND AssetID=?", (cid, a["AssetID"]), raw=True)
    if ln and ln["Found"]:
        return {"status": "already", "line": _line(con, ln["LineID"])}
    if ln:
        con.execute("UPDATE tbl_AssetCountLines SET Found=1, FoundLocationID=?, FoundAt=?, FoundBy=?, ScannedCode=? WHERE LineID=?",
                    (found_loc, now(), actor(), code, ln["LineID"]))
        lid = ln["LineID"]
    else:
        lid = con.execute("INSERT INTO tbl_AssetCountLines(CountID,AssetID,ScannedCode,Expected,Found,FoundLocationID,FoundAt,FoundBy) VALUES(?,?,?,0,1,?,?,?)",
                          (cid, a["AssetID"], code, found_loc, now(), actor())).lastrowid
    con.commit()
    line = _line(con, lid)
    return {"status": line["Result"], "line": line}


def _line(con, lid: int) -> dict:
    ln = one(con, LINE_SQL + " WHERE X.LineID=?", (lid,))
    ln["Result"] = _result(ln)
    return ln


def unscan(con, cid: int, lid: int) -> dict:
    """Undo a scan: an expected asset goes back to missing, anything else is removed from the count."""
    _open(con, cid)
    ln = one(con, "SELECT * FROM tbl_AssetCountLines WHERE LineID=? AND CountID=?", (lid, cid), raw=True)
    if not ln:
        raise ApiError("Line not found", 404)
    if ln["Expected"]:
        con.execute("UPDATE tbl_AssetCountLines SET Found=0, FoundLocationID=NULL, FoundAt=NULL, FoundBy=NULL, ScannedCode=NULL WHERE LineID=?", (lid,))
    else:
        con.execute("DELETE FROM tbl_AssetCountLines WHERE LineID=?", (lid,))
    con.commit()
    return get_count(con, cid)


def close_count(con, cid: int, data: dict) -> dict:
    """Close the count. With apply_locations, assets found at another location are transferred there on the count date."""
    c = _open(con, cid)
    moved = 0
    if data.get("apply_locations") in (True, 1, "1", "true"):
        for ln in get_count(con, cid)["lines"]:
            if ln["Result"] == "moved" or (ln["Result"] == "extra" and ln["FoundLocationID"] and ln["FoundLocationID"] != ln["BookLocationID"]):
                a = one(con, "SELECT CostCenterID FROM tbl_Assets WHERE AssetID=?", (ln["AssetID"],), raw=True)
                transfer_asset(con, ln["AssetID"], {"TransactionDate": max(c["CountDate"], one(con, "SELECT AcquisitionDate d FROM tbl_Assets WHERE AssetID=?", (ln["AssetID"],), raw=True)["d"]),
                                                    "ToLocationID": ln["FoundLocationID"], "ToCostCenterID": a["CostCenterID"],
                                                    "ReferenceNumber": c["CountNo"], "Notes": "Found at this location during the physical count"})
                moved += 1
    con.execute("UPDATE tbl_AssetCounts SET Status='Closed', ClosedAt=?, ClosedBy=? WHERE CountID=?", (now(), actor(), cid))
    s = get_count(con, cid)["summary"]
    audit(con, "COUNT CLOSE", "tbl_AssetCounts", cid, f"{c['CountNo']}: {s['found'] + s['moved']} found, {s['missing']} missing, {moved} moved")
    con.commit()
    return {**get_count(con, cid), "transferred": moved}


def delete_count(con, cid: int) -> dict:
    c = _open(con, cid)
    con.execute("DELETE FROM tbl_AssetCountLines WHERE CountID=?", (cid,))
    con.execute("DELETE FROM tbl_AssetCounts WHERE CountID=?", (cid,))
    audit(con, "COUNT DELETE", "tbl_AssetCounts", cid, c["CountNo"])
    con.commit()
    return {"deleted": cid}
