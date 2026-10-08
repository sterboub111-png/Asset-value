"""Lookups, dashboard, master data and settings."""
from __future__ import annotations

from ... import auth, services as s

from ..router import route


BACKUP_KEYS = {"BackupFolder", "AttachmentFolder", "BackupSchedule", "BackupTime", "BackupWeekday", "BackupDayOfMonth", "BackupKeep"}

# ------------------------------------------------------------------ routes
@route("GET", "/api/lookups")
def _lookups(c):
    d = s.lookups(c.con)
    if not auth.allowed(c.user, "backup.manage"):   # folder paths and backup state are administrative details
        d["settings"] = {k: v for k, v in d["settings"].items() if k not in BACKUP_KEYS and not k.startswith("BackupLast")}
    return d

@route("GET", "/api/dashboard")
def _dash(c):
    d = s.dashboard(c.con)
    # the workspace only shows the maintenance and custody figures a user may open
    if not auth.allowed(c.user, "maintenance.view"):
        d.update(maint_open=None, maint_overdue=None, maint_due=[])
    if not auth.allowed(c.user, "custody.view"):
        d.update(custody_held=None, custody_list=[], custody_unsigned=None)
    d["attention"] = [a for a in s.attention(c.con, d) if auth.allowed(c.user, a["perm"])]
    return d

@route("GET", "/api/integrity")
def _integrity(c): return s.run_checks(c.con)

@route("GET", "/api/master/(\\w+)")
def _ml(c, n): return s.master_list(c.con, n)

@route("POST", "/api/master/(\\w+)")
def _mc(c, n): return s.master_save(c.con, n, c.body)

@route("PUT", "/api/master/(\\w+)/(\\d+)")
def _mu(c, n, i): return s.master_save(c.con, n, c.body, int(i))

@route("DELETE", "/api/master/(\\w+)/(\\d+)")
def _md(c, n, i): return s.master_delete(c.con, n, int(i))

@route("GET", "/api/settings")
def _sg(c): return s.get_settings(c.con)

@route("PUT", "/api/settings")
def _sp(c):
    keys = set(c.body)
    if keys & BACKUP_KEYS and not auth.allowed(c.user, "backup.manage"):
        raise s.ApiError("You do not have permission to do this", 403)
    if keys - BACKUP_KEYS and not auth.allowed(c.user, "settings.manage"):
        raise s.ApiError("You do not have permission to do this", 403)
    return s.save_settings(c.con, c.body)
