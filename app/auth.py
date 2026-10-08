"""Usool - users, roles, permissions and sessions.

Passwords are stored as salted PBKDF2-SHA256 hashes; sessions are random tokens kept (hashed) in the database and sent
in an HttpOnly, SameSite=Strict cookie. Permissions are role based and checked on the server for every API call.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from datetime import datetime, timedelta
from typing import Any

import time

from .services import ApiError, audit, one, rows, set_actor, now, to_int

PBKDF2_ROUNDS = 200_000
SESSION_IDLE_HOURS = 12
SESSION_MAX_DAYS = 7
MAX_FAILED = 5
LOCK_MINUTES = 10
MIN_PASSWORD = 8
COOKIE = "gooya_session"

# (key, group, English label) - the labels are translated in the interface
PERMISSIONS: list[tuple[str, str, str]] = [
    ("assets.view", "Fixed assets", "View fixed assets"), ("assets.edit", "Fixed assets", "Create and edit assets, transfer, change status, attach files"),
    ("assets.delete", "Fixed assets", "Delete assets"), ("assets.dispose", "Fixed assets", "Dispose assets"),
    ("depreciation.view", "Depreciation", "View depreciation and periods"), ("depreciation.run", "Depreciation", "Create and discard depreciation proposals"),
    ("depreciation.post", "Depreciation", "Post depreciation"), ("periods.manage", "Depreciation", "Generate, close and reopen periods"),
    ("maintenance.view", "Maintenance", "View maintenance orders"), ("maintenance.edit", "Maintenance", "Create and work on maintenance orders"),
    ("contacts.view", "Contacts", "View suppliers and employees"), ("contacts.edit", "Contacts", "Create and edit suppliers and employees"),
    ("custody.view", "Custody", "View asset custody"), ("custody.manage", "Custody", "Issue and return assets, attach signed forms"),
    ("reports.view", "Reports and inquiries", "Run reports"), ("inquiries.view", "Reports and inquiries", "View the journal and transactions"),
    ("audit.view", "Reports and inquiries", "View the audit log"),
    ("settings.view", "Administration", "View settings"), ("settings.manage", "Administration", "Change settings and master data"),
    ("backup.manage", "Administration", "Create backups, change backup settings and download all data"), ("users.manage", "Administration", "Manage users and roles"),
]
ALL_KEYS = [p[0] for p in PERMISSIONS]
VIEW_KEYS = [k for k in ALL_KEYS if k.endswith(".view") and k not in ("settings.view", "audit.view")]  # what a read-only user may see

SEED_ROLES = [
    ("Administrator", "مدير النظام", "Full access, including users and settings.", ALL_KEYS, True),
    ("Asset Accountant", "محاسب أصول", "Assets, depreciation, periods and reports.",
     ["assets.view", "assets.edit", "assets.dispose", "depreciation.view", "depreciation.run", "depreciation.post", "periods.manage", "maintenance.view",
      "contacts.view", "custody.view", "reports.view", "inquiries.view", "settings.view"], False),
    ("Asset Officer", "مسؤول أصول وعهد", "Registers assets, maintenance, suppliers, employees and custody.",
     ["assets.view", "assets.edit", "maintenance.view", "maintenance.edit", "contacts.view", "contacts.edit", "custody.view", "custody.manage", "reports.view"], False),
    ("Viewer", "مطّلع (عرض فقط)", "Read-only access to data and reports.", VIEW_KEYS, False),
]


# ---------------------------------------------------------------- passwords
def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), PBKDF2_ROUNDS).hex()
    return f"pbkdf2_sha256${PBKDF2_ROUNDS}${salt}${digest}"


def verify_password(password: str, stored: str | None) -> bool:
    try:
        _, rounds, salt, digest = (stored or "").split("$")
        calc = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), int(rounds)).hex()
        return hmac.compare_digest(calc, digest)
    except (ValueError, TypeError):
        return False


_DUMMY = hash_password("not-a-real-password")  # keeps unknown-user logins as slow as real ones


def check_password_policy(password: str) -> None:
    if len(password) < MIN_PASSWORD or len(password) > 128:
        raise ApiError(f"Password must be at least {MIN_PASSWORD} characters")
    if not (re.search(r"[A-Za-z]", password) and re.search(r"\d", password)):
        raise ApiError("Password must contain letters and digits")


# ---------------------------------------------------------------- seeding
def seed(con) -> None:
    """Create the default roles on first start (permissions of the Administrator role are implicit)."""
    for name, name_ar, desc, perms, system in SEED_ROLES:
        if one(con, "SELECT 1 x FROM tbl_Roles WHERE RoleName=?", (name,), raw=True):
            continue
        cur = con.execute("INSERT INTO tbl_Roles(RoleName,RoleNameAr,Description,IsSystem) VALUES(?,?,?,?)", (name, name_ar, desc, 1 if system else 0))
        if not system:
            con.executemany("INSERT INTO tbl_RolePermissions(RoleID,Permission) VALUES(?,?)", [(cur.lastrowid, p) for p in dict.fromkeys(perms)])
    con.commit()


def admin_role_id(con) -> int:
    return one(con, "SELECT RoleID FROM tbl_Roles WHERE IsSystem=1 ORDER BY RoleID LIMIT 1", raw=True)["RoleID"]


# ---------------------------------------------------------------- roles
def permission_catalog() -> list[dict]:
    return [{"key": k, "group": g, "label": lbl} for k, g, lbl in PERMISSIONS]


def role_permissions(con, role_id: int) -> list[str]:
    role = one(con, "SELECT IsSystem FROM tbl_Roles WHERE RoleID=?", (role_id,), raw=True)
    if not role:
        return []
    if role["IsSystem"]:
        return list(ALL_KEYS)
    return [r["Permission"] for r in rows(con, "SELECT Permission FROM tbl_RolePermissions WHERE RoleID=? ORDER BY Permission", (role_id,), raw=True) if r["Permission"] in ALL_KEYS]


def list_roles(con) -> list[dict]:
    out = rows(con, "SELECT R.*, (SELECT COUNT(*) FROM tbl_Users U WHERE U.RoleID=R.RoleID) AS UserCount FROM tbl_Roles R ORDER BY R.IsSystem DESC, R.RoleName", raw=True)
    for r in out:
        r["permissions"] = role_permissions(con, r["RoleID"])
    return out


def save_role(con, data: dict, role_id: int | None = None) -> dict:
    name = (data.get("RoleName") or "").strip()
    if not name:
        raise ApiError("Role name is required")
    perms = [p for p in dict.fromkeys(data.get("permissions") or []) if p in ALL_KEYS]
    if one(con, "SELECT 1 x FROM tbl_Roles WHERE lower(RoleName)=lower(?) AND RoleID<>?", (name, role_id or 0), raw=True):
        raise ApiError("A role with this name already exists")
    vals = (name, (data.get("RoleNameAr") or "").strip() or None, (data.get("Description") or "").strip() or None)
    if role_id is None:
        role_id = con.execute("INSERT INTO tbl_Roles(RoleName,RoleNameAr,Description,IsSystem) VALUES(?,?,?,0)", vals).lastrowid
        audit(con, "CREATE", "tbl_Roles", role_id, name)
    else:
        cur = one(con, "SELECT * FROM tbl_Roles WHERE RoleID=?", (role_id,), raw=True)
        if not cur:
            raise ApiError("Role not found", 404)
        if cur["IsSystem"]:
            raise ApiError("The Administrator role cannot be changed")
        con.execute("UPDATE tbl_Roles SET RoleName=?,RoleNameAr=?,Description=? WHERE RoleID=?", (*vals, role_id))
        audit(con, "UPDATE", "tbl_Roles", role_id, name)
    con.execute("DELETE FROM tbl_RolePermissions WHERE RoleID=?", (role_id,))
    con.executemany("INSERT INTO tbl_RolePermissions(RoleID,Permission) VALUES(?,?)", [(role_id, p) for p in perms])
    con.commit()
    return next(r for r in list_roles(con) if r["RoleID"] == role_id)


def delete_role(con, role_id: int) -> dict:
    role = one(con, "SELECT * FROM tbl_Roles WHERE RoleID=?", (role_id,), raw=True)
    if not role:
        raise ApiError("Role not found", 404)
    if role["IsSystem"]:
        raise ApiError("The Administrator role cannot be deleted")
    if one(con, "SELECT 1 x FROM tbl_Users WHERE RoleID=? LIMIT 1", (role_id,), raw=True):
        raise ApiError("Users are assigned to this role. Move them to another role first.")
    con.execute("DELETE FROM tbl_RolePermissions WHERE RoleID=?", (role_id,))
    con.execute("DELETE FROM tbl_Roles WHERE RoleID=?", (role_id,))
    audit(con, "DELETE", "tbl_Roles", role_id, role["RoleName"])
    con.commit()
    return {"deleted": role_id}


# ---------------------------------------------------------------- users
USER_SQL = """SELECT U.UserID,U.UserName,U.FullName,U.FullNameAr,U.Email,U.Phone,U.RoleID,U.IsActive,U.MustChangePassword,U.Language,U.Theme,
       U.LastLogin,U.FailedAttempts,U.LockedUntil,U.CreatedAt,U.CreatedBy,R.RoleName,R.RoleNameAr,R.IsSystem AS IsAdmin
       FROM tbl_Users U JOIN tbl_Roles R ON R.RoleID=U.RoleID"""


def _decorate(u: dict) -> dict:
    u["IsLocked"] = bool(u.get("LockedUntil") and u["LockedUntil"] > now())
    return u


def list_users(con) -> list[dict]:
    return [_decorate(u) for u in rows(con, USER_SQL + " ORDER BY U.UserName", raw=True)]


def get_user(con, uid: int) -> dict:
    u = one(con, USER_SQL + " WHERE U.UserID=?", (uid,), raw=True)
    if not u:
        raise ApiError("User not found", 404)
    return _decorate(u)


def _active_admins(con, excluding: int | None = None) -> int:
    return one(con, "SELECT COUNT(*) n FROM tbl_Users U JOIN tbl_Roles R ON R.RoleID=U.RoleID WHERE R.IsSystem=1 AND U.IsActive=1 AND U.UserID<>?",
               (excluding or 0,), raw=True)["n"]


def _clean_user(con, data: dict, uid: int | None) -> dict:
    name = (data.get("UserName") or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9._@-]{3,40}", name):
        raise ApiError("User name must be 3-40 characters: letters, digits and . _ @ -")
    if one(con, "SELECT 1 x FROM tbl_Users WHERE lower(UserName)=lower(?) AND UserID<>?", (name, uid or 0), raw=True):
        raise ApiError("This user name is already taken")
    full = (data.get("FullName") or "").strip()
    if not full:
        raise ApiError("Full name is required")
    email = (data.get("Email") or "").strip() or None
    if email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise ApiError("Email address is not valid")
    role_id = to_int(data.get("RoleID"), "Role")
    if not one(con, "SELECT 1 x FROM tbl_Roles WHERE RoleID=?", (role_id,), raw=True):
        raise ApiError("Role is required")
    lang = data.get("Language") if data.get("Language") in ("en", "ar") else None
    theme = data.get("Theme") if data.get("Theme") in ("light", "dark") else None
    return {"UserName": name, "FullName": full, "FullNameAr": (data.get("FullNameAr") or "").strip() or None, "Email": email,
            "Phone": (data.get("Phone") or "").strip() or None, "RoleID": role_id, "Language": lang, "Theme": theme}


def save_user(con, data: dict, uid: int | None = None, me_id: int | None = None) -> dict:
    v = _clean_user(con, data, uid)
    active = 0 if data.get("IsActive") in (False, 0, "0", "false") else 1
    must = 1 if data.get("MustChangePassword") in (True, 1, "1", "true") else 0
    password = data.get("Password") or ""
    is_admin_role = one(con, "SELECT IsSystem FROM tbl_Roles WHERE RoleID=?", (v["RoleID"],), raw=True)["IsSystem"]
    if uid is None:
        if not password:
            raise ApiError("Password is required")
        check_password_policy(password)
        cols = list(v)
        uid = con.execute(f"INSERT INTO tbl_Users({','.join(cols)},PasswordHash,IsActive,MustChangePassword,CreatedAt,CreatedBy) VALUES({','.join('?' * len(cols))},?,?,?,?,?)",
                          [*v.values(), hash_password(password), active, must, now(), _actor_name()]).lastrowid
        audit(con, "USER CREATE", "tbl_Users", uid, v["UserName"])
    else:
        cur = get_user(con, uid)
        if cur["IsAdmin"] and cur["IsActive"] and (not is_admin_role or not active) and _active_admins(con, uid) == 0:
            raise ApiError("There must be at least one active administrator")
        if uid == me_id and not active:
            raise ApiError("You cannot deactivate your own account")
        sets = [f"{k}=?" for k in v] + ["IsActive=?", "MustChangePassword=?"]
        vals = [*v.values(), active, must]
        if password:
            check_password_policy(password)
            sets.append("PasswordHash=?")
            vals.append(hash_password(password))
        con.execute(f"UPDATE tbl_Users SET {','.join(sets)} WHERE UserID=?", [*vals, uid])
        if password or not active or v["RoleID"] != cur["RoleID"]:
            end_sessions(con, uid)  # role change, deactivation or password reset signs the user out
        if password:
            con.execute("UPDATE tbl_Users SET FailedAttempts=0, LockedUntil=NULL WHERE UserID=?", (uid,))
        audit(con, "USER UPDATE", "tbl_Users", uid, v["UserName"] + (" (password reset)" if password else ""))
    con.commit()
    return get_user(con, uid)


def delete_user(con, uid: int, me_id: int | None) -> dict:
    u = get_user(con, uid)
    if uid == me_id:
        raise ApiError("You cannot delete your own account")
    if u["IsAdmin"] and u["IsActive"] and _active_admins(con, uid) == 0:
        raise ApiError("There must be at least one active administrator")
    con.execute("DELETE FROM tbl_Sessions WHERE UserID=?", (uid,))
    con.execute("DELETE FROM tbl_Users WHERE UserID=?", (uid,))
    audit(con, "USER DELETE", "tbl_Users", uid, u["UserName"])
    con.commit()
    return {"deleted": uid}


def unlock_user(con, uid: int) -> dict:
    u = get_user(con, uid)
    con.execute("UPDATE tbl_Users SET FailedAttempts=0, LockedUntil=NULL WHERE UserID=?", (uid,))
    audit(con, "USER UNLOCK", "tbl_Users", uid, u["UserName"])
    con.commit()
    return get_user(con, uid)


def _actor_name() -> str:
    from .services import actor
    return actor()


# ---------------------------------------------------------------- sessions and sign-in
def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def end_sessions(con, uid: int, keep: str | None = None) -> None:
    if keep:
        con.execute("DELETE FROM tbl_Sessions WHERE UserID=? AND TokenHash<>?", (uid, _hash_token(keep)))
    else:
        con.execute("DELETE FROM tbl_Sessions WHERE UserID=?", (uid,))


def create_session(con, uid: int) -> str:
    token = secrets.token_urlsafe(32)
    t = datetime.now()
    con.execute("INSERT INTO tbl_Sessions(TokenHash,UserID,CreatedAt,LastSeen,ExpiresAt) VALUES(?,?,?,?,?)",
                (_hash_token(token), uid, t.strftime("%Y-%m-%d %H:%M:%S"), t.strftime("%Y-%m-%d %H:%M:%S"),
                 (t + timedelta(hours=SESSION_IDLE_HOURS)).strftime("%Y-%m-%d %H:%M:%S")))
    con.execute("DELETE FROM tbl_Sessions WHERE ExpiresAt<?", (t.strftime("%Y-%m-%d %H:%M:%S"),))
    con.commit()
    return token


def session_user(con, token: str | None) -> dict | None:
    """The signed-in user for a session cookie, or None. Extends the idle timeout."""
    if not token:
        return None
    h = _hash_token(token)
    s = one(con, "SELECT * FROM tbl_Sessions WHERE TokenHash=?", (h,), raw=True)
    t = datetime.now()
    if not s or s["ExpiresAt"] < t.strftime("%Y-%m-%d %H:%M:%S") or datetime.strptime(s["CreatedAt"], "%Y-%m-%d %H:%M:%S") + timedelta(days=SESSION_MAX_DAYS) < t:
        if s:
            con.execute("DELETE FROM tbl_Sessions WHERE TokenHash=?", (h,))
            con.commit()
        return None
    u = one(con, USER_SQL + " WHERE U.UserID=?", (s["UserID"],), raw=True)
    if not u or not u["IsActive"]:
        return None
    if (t - datetime.strptime(s["LastSeen"], "%Y-%m-%d %H:%M:%S")).total_seconds() > 60:  # write at most once a minute
        con.execute("UPDATE tbl_Sessions SET LastSeen=?, ExpiresAt=? WHERE TokenHash=?",
                    (t.strftime("%Y-%m-%d %H:%M:%S"), (t + timedelta(hours=SESSION_IDLE_HOURS)).strftime("%Y-%m-%d %H:%M:%S"), h))
        con.commit()
    u["permissions"] = role_permissions(con, u["RoleID"])
    return _decorate(u)


def me(u: dict) -> dict:
    keep = ("UserID", "UserName", "FullName", "FullNameAr", "Email", "Phone", "RoleID", "RoleName", "RoleNameAr", "IsAdmin", "MustChangePassword", "Language", "Theme", "permissions")
    return {k: u[k] for k in keep}


def needs_setup(con) -> bool:
    return one(con, "SELECT COUNT(*) n FROM tbl_Users", raw=True)["n"] == 0


_UNKNOWN: dict[str, list] = {}   # user name -> [failed count, locked until (epoch)] for names that do not exist


def login(con, username: str, password: str) -> tuple[str, dict]:
    username = ("" if username is None else str(username)).strip()
    password = "" if password is None else str(password)
    u = one(con, "SELECT * FROM tbl_Users WHERE lower(UserName)=lower(?)", (username,), raw=True)
    if not u:
        verify_password(password or "", _DUMMY)
        key = username.lower()[:40]
        fails = _UNKNOWN.setdefault(key, [0, 0.0])
        if fails[1] > time.time():   # unknown names lock exactly like real ones, so a lock-out reveals nothing
            raise ApiError(f"Too many failed attempts. Try again in {max(1, int((fails[1] - time.time()) // 60) + 1)} minute(s).", 429)
        fails[0] += 1
        if fails[0] >= MAX_FAILED:
            fails[0], fails[1] = 0, time.time() + LOCK_MINUTES * 60
        if len(_UNKNOWN) > 500:
            _UNKNOWN.clear()
        set_actor(username[:40] or "?")
        audit(con, "LOGIN FAILED", "session", "-", "unknown user")
        con.commit()
        raise ApiError("Invalid user name or password", 401)
    if u["LockedUntil"] and u["LockedUntil"] > now():
        mins = max(1, int((datetime.strptime(u["LockedUntil"], "%Y-%m-%d %H:%M:%S") - datetime.now()).total_seconds() // 60) + 1)
        raise ApiError(f"Too many failed attempts. Try again in {mins} minute(s).", 429)
    if not verify_password(password or "", u["PasswordHash"]) or not u["IsActive"]:
        failed = (u["FailedAttempts"] or 0) + 1
        locked = (datetime.now() + timedelta(minutes=LOCK_MINUTES)).strftime("%Y-%m-%d %H:%M:%S") if failed >= MAX_FAILED else None
        con.execute("UPDATE tbl_Users SET FailedAttempts=?, LockedUntil=? WHERE UserID=?", (0 if locked else failed, locked, u["UserID"]))
        set_actor(u["UserName"])
        audit(con, "LOGIN FAILED", "session", u["UserID"], "locked" if locked else f"attempt {failed}")
        con.commit()
        raise ApiError("Invalid user name or password", 401)
    con.execute("UPDATE tbl_Users SET FailedAttempts=0, LockedUntil=NULL, LastLogin=? WHERE UserID=?", (now(), u["UserID"]))
    token = create_session(con, u["UserID"])
    set_actor(u["UserName"])
    audit(con, "LOGIN", "session", u["UserID"], "")
    con.commit()
    return token, session_user(con, token)  # type: ignore[return-value]


def logout(con, token: str | None) -> None:
    if token:
        con.execute("DELETE FROM tbl_Sessions WHERE TokenHash=?", (_hash_token(token),))
        con.commit()


def setup_admin(con, data: dict) -> tuple[str, dict]:
    """First start: create the administrator account."""
    if not needs_setup(con):
        raise ApiError("Setup has already been completed", 403)
    role = admin_role_id(con)
    pw = data.get("Password") or ""
    if pw != (data.get("ConfirmPassword") or pw):
        raise ApiError("The passwords do not match")
    set_actor((data.get("UserName") or "admin").strip()[:40])
    save_user(con, {**data, "RoleID": role, "IsActive": True}, None)
    return login(con, data.get("UserName") or "", pw)


def update_profile(con, uid: int, data: dict) -> dict:
    cur = get_user(con, uid)
    v = _clean_user(con, {**cur, **{k: data.get(k, cur.get(k)) for k in ("FullName", "FullNameAr", "Email", "Phone", "Language", "Theme")}}, uid)
    con.execute("UPDATE tbl_Users SET FullName=?,FullNameAr=?,Email=?,Phone=?,Language=?,Theme=? WHERE UserID=?",
                (v["FullName"], v["FullNameAr"], v["Email"], v["Phone"], v["Language"], v["Theme"], uid))
    audit(con, "PROFILE UPDATE", "tbl_Users", uid, cur["UserName"])
    con.commit()
    return get_user(con, uid)


def change_password(con, uid: int, current: str, new: str, token: str | None) -> dict:
    u = one(con, "SELECT * FROM tbl_Users WHERE UserID=?", (uid,), raw=True)
    if not u:
        raise ApiError("The current password is not correct", 400)
    if not verify_password(current or "", u["PasswordHash"]):
        failed = (u["FailedAttempts"] or 0) + 1   # guessing the current password counts like a failed sign-in
        locked = (datetime.now() + timedelta(minutes=LOCK_MINUTES)).strftime("%Y-%m-%d %H:%M:%S") if failed >= MAX_FAILED else None
        con.execute("UPDATE tbl_Users SET FailedAttempts=?, LockedUntil=? WHERE UserID=?", (0 if locked else failed, locked, uid))
        if locked:
            end_sessions(con, uid)
        audit(con, "PASSWORD CHANGE FAILED", "tbl_Users", uid, "wrong current password")
        con.commit()
        raise ApiError("The current password is not correct", 400)
    check_password_policy(new or "")
    if verify_password(new, u["PasswordHash"]):
        raise ApiError("The new password must be different from the current one")
    con.execute("UPDATE tbl_Users SET PasswordHash=?, MustChangePassword=0 WHERE UserID=?", (hash_password(new), uid))
    end_sessions(con, uid, keep=token)  # other devices are signed out
    audit(con, "PASSWORD CHANGE", "tbl_Users", uid, u["UserName"])
    con.commit()
    return {"changed": True}


# ---------------------------------------------------------------- authorisation
def required_permission(method: str, path: str) -> str | None:
    """Permission needed for an API call; None = any signed-in user. Unknown routes need the administrator permission."""
    read = method in ("GET", "HEAD")
    rules: list[tuple[str, Any]] = [
        (r"^/api/lookups$", None),
        (r"^/api/dashboard$", "assets.view"),
        (r"^/api/(users|roles|permissions)", "users.manage"),
        (r"^/api/backups", "backup.manage"),
        (r"^/api/settings$", "settings.view" if read else None),   # writes are checked per key in the handler
        (r"^/api/master/", "settings.view" if read else "settings.manage"),
        (r"^/api/assets/\d+/dispose$", "assets.dispose"),
        (r"^/api/assets", "assets.view" if read else ("assets.delete" if method == "DELETE" and re.fullmatch(r"/api/assets/\d+", path) else "assets.edit")),
        (r"^/api/attachments/", "assets.view" if read else "assets.edit"),
        (r"^/api/depreciation/\d+/post$", "depreciation.post"),
        (r"^/api/depreciation", "depreciation.view" if read else "depreciation.run"),
        (r"^/api/periods", "depreciation.view" if read else "periods.manage"),
        (r"^/api/(journal|transactions)$", "inquiries.view"),
        (r"^/api/audit$", "audit.view"),
        (r"^/api/maintenance", "maintenance.view" if read else "maintenance.edit"),
        (r"^/api/(suppliers|employees)", "contacts.view" if read else "contacts.edit"),
        (r"^/api/custody", "custody.view" if read else "custody.manage"),
        (r"^/api/reports", "reports.view"),
        (r"^/api/integrity$", "reports.view"),
    ]
    for pattern, perm in rules:
        if re.match(pattern, path):
            return perm
    return "users.manage"


def allowed(user: dict, perm: str | None) -> bool:
    return perm is None or user["IsAdmin"] == 1 or perm in user["permissions"]
