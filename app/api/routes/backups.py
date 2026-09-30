"""Backups."""
from __future__ import annotations

from ... import services as s

from ..router import route


@route("GET", "/api/backups")
def _bl(c): return s.list_backups(c.con)

@route("POST", "/api/backups/open-folder")
def _bo(c): return s.open_backup_folder(c.con)

@route("POST", "/api/backups")
def _bc(c): return s.create_backup(c.con)
