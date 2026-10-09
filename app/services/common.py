"""Shared helpers: request context (actor, language), errors, validation, row helpers, audit trail."""
from __future__ import annotations

import getpass
import math
import threading
from datetime import datetime
from typing import Any

USER = getpass.getuser()  # fallback for scripts / background jobs


def set_actor(name: str | None) -> None:
    _ctx.actor = name or None


def actor() -> str:
    """User name written to audit trails: the signed-in user of the current request, else the OS account."""
    return getattr(_ctx, "actor", None) or USER
ASSET_STATUSES = ["Active", "Inactive", "Under Repair"]


class ApiError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def r2(v: float | None) -> float:
    return round(float(v or 0), 2)


_ctx = threading.local()


def set_lang(lang: str) -> None:
    _ctx.lang = "ar" if lang == "ar" else "en"


# ---- branch scope: which branches the current request may see (None = all). Set per request from the user's
# branches and the branch picker; every asset query adds scope_sql() so lists, reports and postings agree.
def set_scope(branch_ids: list[int] | None) -> None:
    _ctx.scope = None if branch_ids is None else sorted({int(b) for b in branch_ids})


def scope() -> list[int] | None:
    return getattr(_ctx, "scope", None)


def scope_sql(alias: str = "A") -> str:
    """' AND <alias>.LocationID IN (locations of the branches in scope)'; empty when everything is in scope.
    Assets without a location belong to no branch, so only an unrestricted scope sees them."""
    ids = scope()
    if ids is None:
        return ""
    if not ids:
        return " AND 0"
    return f" AND {alias}.LocationID IN (SELECT LocationID FROM tbl_Locations WHERE BranchID IN ({','.join(str(i) for i in ids)}))"


class unscoped:
    """`with unscoped():` lifts the branch scope for one step that legitimately reaches outside it (a count closing moves
    an asset of another branch to the location where it was found)."""
    def __enter__(self):
        self.prev = getattr(_ctx, "scope", None)
        _ctx.scope = None

    def __exit__(self, *exc):
        _ctx.scope = self.prev


def in_scope(con, location_id) -> bool:
    ids = scope()
    if ids is None:
        return True
    if not location_id:
        return False
    r = con.execute("SELECT BranchID FROM tbl_Locations WHERE LocationID=?", (location_id,)).fetchone()
    return bool(r and r[0] in ids)


MONTHS_AR = {"January": "يناير", "February": "فبراير", "March": "مارس", "April": "أبريل", "May": "مايو", "June": "يونيو", "July": "يوليو",
             "August": "أغسطس", "September": "سبتمبر", "October": "أكتوبر", "November": "نوفمبر", "December": "ديسمبر"}


def month_ar(name):
    """'January 2026' -> 'يناير 2026' (only used in Arabic mode)."""
    if isinstance(name, str):
        for en, ar in MONTHS_AR.items():
            if name.startswith(en):
                return ar + name[len(en):]
    return name


def localize(row: dict, skip: tuple = ()) -> dict:
    """In Arabic mode replace every <Field> by <Field>Ar when an Arabic value exists."""
    if getattr(_ctx, "lang", "en") == "ar":
        if row.get("PeriodName"):
            row["PeriodName"] = month_ar(row["PeriodName"])
        for k in list(row):
            if k.endswith("Ar") and k[:-2] not in skip and row[k] and (k[:-2] in row):
                row[k[:-2]] = row[k]
    return row


def rows(con, sql, args=(), raw=False) -> list[dict]:
    out = [dict(r) for r in con.execute(sql, args).fetchall()]
    return out if raw else [localize(r) for r in out]


def one(con, sql, args=(), raw=False) -> dict | None:
    r = con.execute(sql, args).fetchone()
    if not r:
        return None
    return dict(r) if raw else localize(dict(r))


def audit(con, action: str, entity: str, entity_id: Any, details: str = "") -> None:
    con.execute("INSERT INTO tbl_AuditLog(LogDate,UserName,Action,Entity,EntityID,Details) VALUES(?,?,?,?,?,?)",
                (now(), actor(), action, entity, str(entity_id), details))


def parse_date(v: Any, field: str = "Date", required: bool = False) -> str | None:
    if v in (None, ""):
        if required:
            raise ApiError(f"{field} is required")
        return None
    try:
        return datetime.strptime(str(v)[:10], "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError:
        raise ApiError(f"{field} is not a valid date (YYYY-MM-DD)")


def num(v: Any, field: str, default: float | None = 0, minimum: float | None = None) -> float | None:
    if v in (None, ""):
        return default
    try:
        x = float(v)
    except (TypeError, ValueError):
        raise ApiError(f"{field} must be a number")
    if not math.isfinite(x):
        raise ApiError(f"{field} must be a number")
    if minimum is not None and x < minimum:
        raise ApiError(f"{field} must be at least {minimum}")
    return x


def to_int(v: Any, field: str = "Value", default: int = 0) -> int:
    """Whole number from a request value; anything else is a clean 400 instead of a crash."""
    if v in (None, "", False):
        return default
    if isinstance(v, bool):
        raise ApiError(f"{field} is not valid")
    try:
        return int(str(v).strip())
    except ValueError:
        raise ApiError(f"{field} is not valid")
