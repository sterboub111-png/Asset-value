"""Sign-in, profile, users, roles and permissions."""
from __future__ import annotations

from ... import auth

from ..router import route


# ---- authentication (login, setup, profile) and administration (users, roles)
def _cookie(token: str | None, expire: bool = False) -> str:
    if expire or not token:
        return f"{auth.COOKIE}=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0"
    return f"{auth.COOKIE}={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={auth.SESSION_MAX_DAYS * 86400}"

@route("GET", "/api/auth/status")
def _auth_status(c): return {"needs_setup": auth.needs_setup(c.con), "user": auth.me(c.user) if c.user else None}

@route("POST", "/api/auth/login")
def _auth_login(c):
    token, user = auth.login(c.con, c.body.get("UserName", ""), c.body.get("Password", ""))
    c.cookies.append(_cookie(token))
    return auth.me(user)

@route("POST", "/api/auth/setup")
def _asu(c):
    token, user = auth.setup_admin(c.con, c.body)
    c.cookies.append(_cookie(token))
    return auth.me(user)

@route("POST", "/api/auth/logout")
def _alo(c):
    auth.logout(c.con, c.token)
    c.cookies.append(_cookie(None, expire=True))
    return {"signed_out": True}

@route("GET", "/api/auth/me")
def _am(c): return auth.me(c.user)

@route("PUT", "/api/auth/profile")
def _ap(c): return auth.me({**c.user, **auth.update_profile(c.con, c.user["UserID"], c.body), "permissions": c.user["permissions"]})

@route("POST", "/api/auth/password")
def _apw(c): return auth.change_password(c.con, c.user["UserID"], c.body.get("Current", ""), c.body.get("New", ""), c.token)

@route("GET", "/api/permissions")
def _pc(c): return auth.permission_catalog()

@route("GET", "/api/users")
def _ul(c): return auth.list_users(c.con)

@route("POST", "/api/users")
def _uc(c): return auth.save_user(c.con, c.body, None, c.user["UserID"])

@route("PUT", "/api/users/(\\d+)")
def _uu(c, i): return auth.save_user(c.con, c.body, int(i), c.user["UserID"])

@route("DELETE", "/api/users/(\\d+)")
def _ud(c, i): return auth.delete_user(c.con, int(i), c.user["UserID"])

@route("POST", "/api/users/(\\d+)/unlock")
def _uk(c, i): return auth.unlock_user(c.con, int(i))

@route("GET", "/api/roles")
def _rl0(c): return auth.list_roles(c.con)

@route("POST", "/api/roles")
def _rc(c): return auth.save_role(c.con, c.body)

@route("PUT", "/api/roles/(\\d+)")
def _ru(c, i): return auth.save_role(c.con, c.body, int(i))

@route("DELETE", "/api/roles/(\\d+)")
def _rd(c, i): return auth.delete_role(c.con, int(i))
