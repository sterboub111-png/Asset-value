"""Fixed assets and their attachments."""
from __future__ import annotations

from urllib.parse import unquote

from ... import auth, services as s

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

@route("POST", "/api/assets/(\\d+)/attachments")
def _aa(c, i):
    name = unquote(c.headers.get("X-File-Name", "file"))
    meta = {"title": unquote(c.headers.get("X-Doc-Title", "")), "type": unquote(c.headers.get("X-Doc-Type", "")),
            "notes": unquote(c.headers.get("X-Doc-Notes", ""))}
    return _asset_out(c, s.add_attachment(c.con, int(i), name, c.raw, meta))

@route("DELETE", "/api/attachments/(\\d+)")
def _atd(c, i): return _asset_out(c, s.delete_attachment(c.con, int(i)))
