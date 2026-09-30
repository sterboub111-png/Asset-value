"""Maintenance orders."""
from __future__ import annotations

from ... import services as s

from ..router import route


@route("GET", "/api/maintenance")
def _ml2(c): return s.list_maintenance(c.con, c.q("status"), c.q("type"), c.q("asset"))

@route("POST", "/api/maintenance")
def _mc2(c): return s.save_maintenance(c.con, c.body)

@route("GET", "/api/maintenance/(\\d+)")
def _mg2(c, i): return s.get_maintenance(c.con, int(i))

@route("PUT", "/api/maintenance/(\\d+)")
def _mu2(c, i): return s.save_maintenance(c.con, c.body, int(i))

@route("DELETE", "/api/maintenance/(\\d+)")
def _md2(c, i): return s.delete_maintenance(c.con, int(i))

@route("POST", "/api/maintenance/(\\d+)/(start|complete|cancel)")
def _ma2(c, i, act): return s.maintenance_action(c.con, int(i), act, c.body)
