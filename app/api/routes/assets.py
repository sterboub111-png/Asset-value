"""Fixed assets and their attachments."""
from __future__ import annotations

from urllib.parse import unquote

from ... import auth, services as s
from ...services import importer, ledger

from ..router import route


def _asset_out(c, data):
    """Hide custody details (who holds an asset, signed custody forms) from users without custody.view."""
    if auth.allowed(c.user, "custody.view"):
        return data
    for a in (data if isinstance(data, list) else [data]):
        a["CustodianName"] = a["CustodianNameAr"] = None
        if "custody" in a:
            a["custody"] = []
        if "attachments" in a:
            a["attachments"] = [x for x in a["attachments"] if not x.get("CustodyID")]
    return data

@route("GET", "/api/assets")
def _al(c): return _asset_out(c, s.list_assets(c.con, c.q("q"), c.q("status"), c.q("category")))

@route("POST", "/api/assets/import")
def _aimp(c):
    """?dry=1 previews the file row by row; without it the ready rows are created (?skip=1 leaves the rows with errors out)."""
    name = unquote(c.headers.get("X-File-Name", "assets.xlsx"))
    if c.q("dry") == "1":
        p = importer.preview(c.con, name, c.raw)
        for r in p["rows"]:
            r.pop("data", None)
        return p
    return importer.run_import(c.con, name, c.raw, c.q("skip") == "1")

# ---- physical inventory (counts)
@route("GET", "/api/counts")
def _cnl(c): return s.list_counts(c.con)

@route("POST", "/api/counts")
def _cnc(c): return s.create_count(c.con, c.body)

@route("GET", "/api/counts/(\\d+)")
def _cng(c, i): return s.get_count(c.con, int(i))

@route("POST", "/api/counts/(\\d+)/scan")
def _cns(c, i): return s.scan(c.con, int(i), c.body)

@route("DELETE", "/api/counts/(\\d+)/lines/(\\d+)")
def _cnu(c, i, ln): return s.unscan(c.con, int(i), int(ln))

@route("POST", "/api/counts/(\\d+)/close")
def _cnx(c, i): return s.close_count(c.con, int(i), c.body)

@route("DELETE", "/api/counts/(\\d+)")
def _cnd(c, i): return s.delete_count(c.con, int(i))

@route("GET", "/api/assets/next-code")
def _anc(c): return {"code": s.next_asset_code(c.con, c.q("category"))}

@route("POST", "/api/assets")
def _ac(c): return _asset_out(c, s.save_asset(c.con, c.body))

@route("GET", "/api/assets/(\\d+)")
def _ag(c, i): return _asset_out(c, s.get_asset(c.con, int(i)))

@route("PUT", "/api/assets/(\\d+)")
def _au(c, i): return _asset_out(c, s.save_asset(c.con, c.body, int(i)))

@route("DELETE", "/api/assets/(\\d+)")
def _ad(c, i): return s.delete_asset(c.con, int(i))

@route("POST", "/api/assets/(\\d+)/status")
def _as(c, i): return _asset_out(c, s.change_status(c.con, int(i), c.body.get("status", "")))

@route("POST", "/api/assets/(\\d+)/transfer")
def _at(c, i): return _asset_out(c, s.transfer_asset(c.con, int(i), c.body))

@route("POST", "/api/assets/(\\d+)/dispose")
def _adp(c, i): return _asset_out(c, s.dispose_asset(c.con, int(i), c.body))

@route("POST", "/api/assets/(\\d+)/addition")
def _aadd(c, i):
    """A capital addition; ?dry=1 returns the preview (cost, NBV and monthly depreciation before and after)."""
    res = s.add_capital(c.con, int(i), c.body, c.q("dry") == "1")
    return res if c.q("dry") == "1" else _asset_out(c, res)

@route("POST", "/api/assets/(\\d+)/revalue")
def _arev(c, i):
    """A revaluation or impairment to a new carrying amount; ?dry=1 returns the preview with the profit or loss / surplus split."""
    res = s.revalue(c.con, int(i), c.body, c.q("dry") == "1")
    return res if c.q("dry") == "1" else _asset_out(c, res)

# ---- fixed asset ledger entries
@route("GET", "/api/ledger")
def _ledger(c):
    return ledger.ledger(c.con, s.to_int(c.q("asset"), "Asset") or None, c.q("from") or None, c.q("to") or None, c.q("type"), c.q("q"),
                         s.to_int(c.q("branch"), "Branch") or None, c.q("limit") or 500, c.q("offset") or 0)

@route("GET", "/api/ledger/journal")
def _ledger_j(c):
    return ledger.entry_journal(c.con, s.to_int(c.q("tx"), "Entry") or None, s.to_int(c.q("dep"), "Entry") or None)

@route("POST", "/api/assets/(\\d+)/attachments")
def _aa(c, i):
    name = unquote(c.headers.get("X-File-Name", "file"))
    meta = {"title": unquote(c.headers.get("X-Doc-Title", "")), "type": unquote(c.headers.get("X-Doc-Type", "")),
            "notes": unquote(c.headers.get("X-Doc-Notes", ""))}
    return _asset_out(c, s.add_attachment(c.con, int(i), name, c.raw, meta))

@route("DELETE", "/api/attachments/(\\d+)")
def _atd(c, i): return _asset_out(c, s.delete_attachment(c.con, int(i)))
