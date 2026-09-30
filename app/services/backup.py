"""Backups: create, list, schedule, restore helpers."""
from __future__ import annotations

import calendar
import os
import re
import sqlite3
from datetime import date
from datetime import datetime
from pathlib import Path

from .files import _attach_root
from .common import ApiError, actor, audit, now
from .settings import get_settings

# ---------------------------------------------------------------- backup
BACKUP_RE = re.compile(r"^(?:Usool|GooyaAsset)_(backup|auto)_\d{4}-\d{2}-\d{2}_\d{6}\.zip$")


def _backup_root(con) -> Path:
    folder = (get_settings(con).get("BackupFolder") or "").strip()
    if not folder:
        raise ApiError("Choose the backup folder first (Settings > Backup > Location)")
    root = Path(folder)
    root.mkdir(parents=True, exist_ok=True)
    return root


def create_backup(con, auto: bool = False) -> dict:
    """Zip a consistent snapshot of the database together with every attachment file."""
    import json
    import tempfile
    import zipfile

    root = _backup_root(con)
    att_root = _attach_root(con)
    name = f"Usool_{'auto' if auto else 'backup'}_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}.zip"
    target = root / name
    files = 0
    with tempfile.TemporaryDirectory() as tmp:
        snap = Path(tmp) / "gooya_asset.db"
        dest = sqlite3.connect(snap)
        try:
            con.backup(dest)  # online, consistent copy (safe while the app is in use)
        finally:
            dest.close()
        try:
            with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
                z.write(snap, "gooya_asset.db")
                for p in sorted(att_root.rglob("*")):
                    if p.is_file():
                        z.write(p, "attachments/" + p.relative_to(att_root).as_posix())
                        files += 1
                z.writestr("manifest.json", json.dumps({"created": now(), "user": actor(), "attachments": files,
                                                        "attachment_root": str(att_root), "app": "Usool"}, indent=2))
        except Exception:
            target.unlink(missing_ok=True)
            raise
    audit(con, "AUTO BACKUP" if auto else "BACKUP", "backup", name, f"{files} attachment file(s)")
    con.commit()
    return {"name": name, "size": target.stat().st_size, "attachments": files, "folder": str(root)}


def list_backups(con) -> dict:
    folder = (get_settings(con).get("BackupFolder") or "").strip()
    if not folder:
        return {"folder": "", "custom_folder": "", "items": [], "schedule": backup_schedule(con)}
    root = _backup_root(con)
    items = []
    for p in sorted(root.glob("*.zip"), reverse=True):
        if BACKUP_RE.match(p.name):
            st = p.stat()
            items.append({"name": p.name, "size": st.st_size, "kind": "auto" if "_auto_" in p.name else "manual",
                          "created": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S")})
    return {"folder": str(root), "custom_folder": get_settings(con).get("BackupFolder") or "", "items": items, "schedule": backup_schedule(con)}


def backup_path(con, name: str) -> Path:
    p = _backup_root(con) / name
    if not BACKUP_RE.match(name) or not p.is_file():
        raise ApiError("Backup not found", 404)
    return p


# ---------------------------------------------------------------- automatic backup schedule
def _slots(mode: str, hhmm: str, weekday: int, dom: int, around: datetime) -> list[datetime]:
    hh, mm = int(hhmm[:2]), int(hhmm[3:5])
    out: list[datetime] = []
    if mode == "DAILY" or mode == "WEEKLY":
        d = around.date().toordinal() - 400
        for o in range(d, d + 800):
            day = date.fromordinal(o)
            if mode == "DAILY" or day.weekday() == weekday:
                out.append(datetime(day.year, day.month, day.day, hh, mm))
    elif mode in ("MONTHLY", "QUARTERLY"):
        for y in (around.year - 1, around.year, around.year + 1):
            for m in (range(1, 13) if mode == "MONTHLY" else (1, 4, 7, 10)):
                day = min(dom, calendar.monthrange(y, m)[1])
                out.append(datetime(y, m, day, hh, mm))
    return sorted(out)


def backup_schedule(con, at: datetime | None = None) -> dict:
    at = at or datetime.now()
    st = get_settings(con)
    mode = st.get("BackupSchedule") or "OFF"
    info = {"mode": mode, "time": st.get("BackupTime") or "02:00", "weekday": int(st.get("BackupWeekday") or 0),
            "dom": int(st.get("BackupDayOfMonth") or 1), "keep": int(st.get("BackupKeep") or 0),
            "last_run": st.get("BackupLastRun") or "", "last_result": st.get("BackupLastResult") or "", "next_run": "", "due_slot": ""}
    if mode != "OFF":
        slots = _slots(mode, info["time"], info["weekday"], info["dom"], at)
        past = [x for x in slots if x <= at]
        future = [x for x in slots if x > at]
        info["due_slot"] = past[-1].strftime("%Y-%m-%d %H:%M:%S") if past else ""
        info["next_run"] = future[0].strftime("%Y-%m-%d %H:%M") if future else ""
    return info


def _put_setting(con, key: str, value: str) -> None:
    con.execute("UPDATE tbl_Settings SET SettingValue=? WHERE SettingKey=?", (value, key))


def run_due_backup(con, at: datetime | None = None) -> dict | None:
    """Called by the scheduler thread: takes the automatic backup when its slot has passed and it was not taken yet."""
    at = at or datetime.now()
    sch = backup_schedule(con, at)
    if sch["mode"] == "OFF" or not sch["due_slot"] or not (get_settings(con).get("BackupFolder") or "").strip():
        return None
    if sch["last_run"] and sch["last_run"] >= sch["due_slot"]:
        return None
    last_try = get_settings(con).get("BackupLastAttempt") or ""
    if last_try and (at - datetime.strptime(last_try, "%Y-%m-%d %H:%M:%S")).total_seconds() < 3600:
        return None  # retry a failed attempt at most once an hour
    _put_setting(con, "BackupLastAttempt", at.strftime("%Y-%m-%d %H:%M:%S"))
    con.commit()
    try:
        res = create_backup(con, auto=True)
        _put_setting(con, "BackupLastRun", now())
        _put_setting(con, "BackupLastResult", "OK: " + res["name"])
        if sch["keep"] > 0:
            root = _backup_root(con)
            autos = sorted([p for p in root.glob("*_auto_*.zip") if BACKUP_RE.match(p.name)], reverse=True)
            for old in autos[sch["keep"]:]:
                old.unlink(missing_ok=True)
        con.commit()
        return res
    except Exception as e:  # noqa: BLE001
        _put_setting(con, "BackupLastResult", f"Error: {e}")
        con.commit()
        return None


def open_backup_folder(con) -> dict:
    """Opens the backup folder in Windows Explorer (the app only ever runs on the user's own PC)."""
    root = _backup_root(con)
    if hasattr(os, "startfile"):
        os.startfile(str(root))  # noqa: S606
    return {"folder": str(root)}
