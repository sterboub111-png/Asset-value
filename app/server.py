"""Usool - local HTTP server (stdlib only). Serves the SPA and the JSON API on 127.0.0.1."""
from __future__ import annotations

import json
import mimetypes
import re
import sys
import traceback
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

from . import auth, db, scheduler, services as s
from .services import branches
from .api import routes
from .api.router import ROUTES, Ctx

assert routes.__all__   # importing the package registers every route

STATIC = db.ROOT / "web" / "static"

HOSTS = {"127.0.0.1", "localhost", "[::1]"}

MAX_BODY = 60 * 1024 * 1024


# ------------------------------------------------------------------ handler
class Handler(BaseHTTPRequestHandler):
    server_version = "Usool/1.0"

    def log_message(self, fmt, *args):
        if "--quiet" not in sys.argv and self.path.startswith("/api/"):
            sys.stderr.write("%s %s\n" % (self.command, self.path))

    def _send(self, status, payload: bytes, ctype="application/json; charset=utf-8", extra=None):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(payload)

    def _json(self, status, obj, cookies=None):
        payload = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        for ck in cookies or []:
            self.send_header("Set-Cookie", ck)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(payload)

    def _host_ok(self) -> bool:
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0]
        if host not in HOSTS:
            return False
        origin = self.headers.get("Origin")
        if not origin:
            return True
        o = urlparse(origin)
        return o.hostname in {"127.0.0.1", "localhost", "::1"} and (o.port or 80) == self.server.server_address[1]

    def _session_token(self) -> str | None:
        raw = self.headers.get("Cookie")
        if not raw:
            return None
        try:
            morsel = SimpleCookie(raw).get(auth.COOKIE)
        except Exception:  # noqa: BLE001
            return None
        return morsel.value if morsel else None

    def _dispatch(self):
        if not self._host_ok():
            return self._json(403, {"error": "Forbidden"})
        u = urlparse(self.path)
        if not u.path.startswith("/api/"):
            return self._static(u.path)
        if self.command not in ("GET", "HEAD") and self.headers.get("X-Requested-With") != "GooyaAsset":
            return self._json(403, {"error": "Forbidden"})   # a page on another site cannot set this header
        s.set_lang(self.headers.get("X-Lang", "en"))
        s.set_actor(None)
        s.set_scope([])   # nothing in scope until the user is known (threads are reused between requests)
        public = (self.command, u.path) in (("POST", "/api/auth/login"), ("POST", "/api/auth/setup"), ("GET", "/api/auth/status"))
        token = self._session_token()
        con = db.connect()
        try:
            user = auth.session_user(con, token)
            if not user and not public:
                return self._json(401, {"error": "Please sign in", "auth": "required"})
            if user:
                s.set_actor(user["UserName"])
                branches.apply_scope(con, user["UserID"], self.headers.get("X-Scope"))
                # an account flagged "must change password" may only change it (or sign out)
                if user["MustChangePassword"] and (self.command, u.path) not in (("POST", "/api/auth/password"), ("POST", "/api/auth/logout"), ("GET", "/api/auth/me"), ("GET", "/api/auth/status")):
                    return self._json(403, {"error": "You must change your password first", "auth": "password"})
                perm = None if u.path.startswith("/api/auth/") else auth.required_permission(self.command, u.path)
                att = re.match(r"^/api/attachments/(\d+)", u.path)
                if att:   # signed custody forms follow the custody permissions, not the asset ones
                    row = con.execute("SELECT CustodyID FROM tbl_AssetAttachments WHERE AttachmentID=?", (int(att.group(1)),)).fetchone()
                    if row and row[0]:
                        perm = "custody.view" if self.command in ("GET", "HEAD") else "custody.manage"
                if not auth.allowed(user, perm):
                    return self._json(403, {"error": "You do not have permission to do this"})
            if u.path.startswith("/api/attachments/") and u.path.endswith("/download") and self.command == "GET":
                return self._download(u.path)
            if u.path.startswith("/api/backups/") and u.path.endswith("/download") and self.command == "GET":
                return self._download_backup(u.path)
            if u.path == "/api/assets/import-template" and self.command == "GET":
                from .services import importer
                lang = "ar" if self.headers.get("X-Lang") == "ar" or parse_qs(u.query).get("lang") == ["ar"] else "en"
                return self._send(200, importer.template(con, lang), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                  {"Content-Disposition": "attachment; filename=\"usool-assets-import.xlsx\""})
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                return self._json(400, {"error": "Invalid request"})
            if length < 0:
                return self._json(400, {"error": "Invalid request"})
            if length > MAX_BODY:
                self.close_connection = True
                return self._json(413, {"error": "The request is too large"})
            raw = self.rfile.read(length) if length else b""
            body = {}
            if raw and "json" in (self.headers.get("Content-Type") or ""):
                try:
                    body = json.loads(raw.decode("utf-8"))
                except ValueError:
                    return self._json(400, {"error": "Invalid JSON"})
                if not isinstance(body, dict):
                    return self._json(400, {"error": "Invalid JSON"})
            for method, rx, fn in ROUTES:
                m = rx.match(u.path)
                if m and method == self.command:
                    ctx = Ctx(con, parse_qs(u.query), body, raw, self.headers, user, token)
                    try:
                        res = fn(ctx, *m.groups())
                        return self._json(200, res, ctx.cookies)
                    except s.ApiError as e:
                        con.rollback()
                        return self._json(e.status, {"error": str(e)})
                    except db.DatabaseError as e:
                        con.rollback()
                        return self._json(400, {"error": f"Database error: {e}"})
                    except Exception:  # noqa: BLE001
                        con.rollback()
                        traceback.print_exc()
                        return self._json(500, {"error": "Unexpected server error"})
            self._json(404, {"error": "Not found"})
        finally:
            con.close()

    def _download(self, path):
        m = re.match(r"^/api/attachments/(\d+)/download$", path)
        con = db.connect()
        try:
            att = s.get_attachment(con, int(m.group(1)))
        except s.ApiError as e:
            return self._json(e.status, {"error": str(e)})
        finally:
            con.close()
        data = Path(att["FilePath"]).read_bytes()
        ctype = mimetypes.guess_type(att["FileName"])[0] or "application/octet-stream"
        fn = att["FileName"].replace('"', "")
        safe_inline = ctype in ("application/pdf", "image/png", "image/jpeg", "image/gif", "image/webp")
        disp = "inline" if safe_inline else "attachment"
        self._send(200, data, ctype, {"Content-Disposition": f"{disp}; filename*=UTF-8''{quote(fn)}"})

    def _download_backup(self, path):
        name = unquote(path[len("/api/backups/"):-len("/download")])
        con = db.connect()
        try:
            p = s.backup_path(con, name)
        except s.ApiError as e:
            return self._json(e.status, {"error": str(e)})
        finally:
            con.close()
        self._send(200, p.read_bytes(), "application/zip", {"Content-Disposition": f"attachment; filename=\"{p.name}\""})

    def _static(self, path):
        rel = "index.html" if path in ("/", "") else unquote(path).lstrip("/")
        try:
            target = (STATIC / rel).resolve()
            ok = STATIC.resolve() in target.parents and target.is_file()
        except (ValueError, OSError):
            ok = False
        if not ok:
            target = STATIC / "index.html"  # SPA fallback
        ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if target.suffix in (".js", ".css", ".html", ".svg"):
            ctype += "; charset=utf-8"
        csp = {"Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
                                          "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"}
        self._send(200, target.read_bytes(), ctype, csp if target.suffix == ".html" else None)

    do_GET = do_POST = do_PUT = do_DELETE = do_HEAD = _dispatch

def serve(port: int = 8742, open_browser: bool = True) -> None:
    db.init_db()
    if (not db.is_pg() and not db.DB_PATH.exists()) or not _has_data():
        if db.EXPORT_PATH.exists():
            print("First run: importing data from Access export…", db.migrate_from_access())
    scheduler.start()
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}/"
    print(f"Usool is running at {url}  (Ctrl+C to stop)  ·  database: {'PostgreSQL ' if db.is_pg() else 'SQLite '}{db.describe()}")
    if open_browser:
        import webbrowser
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


def _has_data() -> bool:
    con = db.connect()
    try:
        return bool(con.execute("SELECT COUNT(*) FROM tbl_GLAccounts").fetchone()[0])
    finally:
        con.close()
