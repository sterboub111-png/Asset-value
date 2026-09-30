"""Asset custody and signed handover forms."""
from __future__ import annotations

from urllib.parse import unquote

from ... import services as s

from ..router import route


@route("GET", "/api/custody")
def _cl(c): return s.list_custody(c.con, c.q("status"), c.q("employee"), c.q("asset"))

@route("POST", "/api/custody")
def _cc(c): return s.issue_custody(c.con, c.body)

@route("GET", "/api/custody/(\\d+)")
def _cg(c, i): return s.get_custody(c.con, int(i))

@route("PUT", "/api/custody/(\\d+)")
def _cu(c, i): return s.update_custody(c.con, int(i), c.body)

@route("DELETE", "/api/custody/(\\d+)")
def _cd(c, i): return s.delete_custody(c.con, int(i))

@route("POST", "/api/custody/(\\d+)/return")
def _cr(c, i): return s.return_custody(c.con, int(i), c.body)

@route("POST", "/api/custody/(\\d+)/attachments")
def _ca(c, i):
    name = unquote(c.headers.get("X-File-Name", "file"))
    meta = {"title": unquote(c.headers.get("X-Doc-Title", "")), "type": unquote(c.headers.get("X-Doc-Type", "")), "notes": unquote(c.headers.get("X-Doc-Notes", ""))}
    return s.add_custody_attachment(c.con, int(i), name, c.raw, meta)
