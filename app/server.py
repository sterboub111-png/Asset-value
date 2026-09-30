"""Gooya Asset - local HTTP server (stdlib only). Serves the SPA and a JSON API on 127.0.0.1."""
from __future__ import annotations

import json
import mimetypes
import re
import sqlite3
import sys
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

from . import db, reports, services as s

STATIC = db.ROOT / "web" / "static"
HOSTS = {"127.0.0.1", "localhost", "[::1]"}
Route = tuple[str, "re.Pattern[str]", callable]
ROUTES: list[Route] = []


def route(method: str, pattern: str):
    def deco(fn):
        ROUTES.append((method, re.compile("^" + pattern + "$"), fn))
        return fn
    return deco


class Ctx:
    def __init__(self, con, query, body, raw, headers):
        self.con, self.query, self.body, self.raw, self.headers = con, query, body, raw, headers

    def q(self, k, default=""):
        return self.query.get(k, [default])[0]


# ------------------------------------------------------------------ routes
@route("GET", "/api/lookups")
def _lookups(c): return s.lookups(c.con)

@route("GET", "/api/dashboard")
def _dash(c): return s.dashboard(c.con)

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
def _sp(c): return s.save_settings(c.con, c.body)

@route("GET", "/api/assets")
def _al(c): return s.list_assets(c.con, c.q("q"), c.q("status"), c.q("category"))

@route("GET", "/api/assets/next-code")
def _anc(c): return {"code": s.next_asset_code(c.con, c.q("category"))}

@route("POST", "/api/assets")
def _ac(c): return s.save_asset(c.con, c.body)

@route("GET", "/api/assets/(\\d+)")
def _ag(c, i): return s.get_asset(c.con, int(i))

@route("PUT", "/api/assets/(\\d+)")
def _au(c, i): return s.save_asset(c.con, c.body, int(i))

@route("DELETE", "/api/assets/(\\d+)")
def _ad(c, i): return s.delete_asset(c.con, int(i))

@route("POST", "/api/assets/(\\d+)/status")
def _as(c, i): return s.change_status(c.con, int(i), c.body.get("status", ""))

@route("POST", "/api/assets/(\\d+)/transfer")
def _at(c, i): return s.transfer_asset(c.con, int(i), c.body)

@route("POST", "/api/assets/(\\d+)/dispose")
def _adp(c, i): return s.dispose_asset(c.con, int(i), c.body)

@route("POST", "/api/assets/(\\d+)/attachments")
def _aa(c, i):
    name = unquote(c.headers.get("X-File-Name", "file"))
    meta = {"title": unquote(c.headers.get("X-Doc-Title", "")), "type": unquote(c.headers.get("X-Doc-Type", "")),
            "notes": unquote(c.headers.get("X-Doc-Notes", ""))}
    return s.add_attachment(c.con, int(i), name, c.raw, meta)

@route("DELETE", "/api/attachments/(\\d+)")
def _atd(c, i): return s.delete_attachment(c.con, int(i))

@route("GET", "/api/periods")
def _pl(c): return s.rows(c.con, "SELECT * FROM tbl_DepreciationPeriods ORDER BY StartDate")

@route("POST", "/api/periods/generate")
def _pg(c): return s.generate_periods(c.con, int(c.body.get("fiscal_year") or 0))

@route("POST", "/api/periods/(\\d+)/status")
def _ps(c, i): return s.set_period_status(c.con, int(i), c.body.get("status", ""))

@route("GET", "/api/depreciation/(\\d+)/proposal")
def _dp(c, i): return s.propose(c.con, int(i))

@route("GET", "/api/depreciation/suggest")
def _dsg(c): return s.suggest_period(c.con)

@route("GET", "/api/depreciation/(\\d+)/lines")
def _dl(c, i): return s.draft_lines(c.con, int(i))

@route("POST", "/api/depreciation/(\\d+)/run")
def _dr(c, i): return s.run_depreciation(c.con, int(i), c.body.get("asset_ids"))

@route("POST", "/api/depreciation/(\\d+)/post")
def _dpo(c, i): return s.post_depreciation(c.con, int(i))

@route("DELETE", "/api/depreciation/(\\d+)/drafts")
def _dd(c, i): return s.discard_drafts(c.con, int(i))

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

@route("GET", "/api/suppliers")
def _sl(c): return s.list_suppliers(c.con, c.q("q"), c.q("active"), c.q("type"))

@route("POST", "/api/suppliers")
def _sc(c): return s.save_supplier(c.con, c.body)

@route("GET", "/api/suppliers/(\\d+)")
def _sg2(c, i): return s.get_supplier(c.con, int(i))

@route("PUT", "/api/suppliers/(\\d+)")
def _su(c, i): return s.save_supplier(c.con, c.body, int(i))

@route("DELETE", "/api/suppliers/(\\d+)")
def _sd(c, i): return s.delete_supplier(c.con, int(i))

@route("GET", "/api/backups")
def _bl(c): return s.list_backups(c.con)

@route("POST", "/api/backups")
def _bc(c): return s.create_backup(c.con)

@route("GET", "/api/journal")
def _j(c): return s.journal(c.con, c.q("period"), c.q("type"))

@route("GET", "/api/transactions")
def _t(c): return s.transactions(c.con)

@route("GET", "/api/audit")
def _au_log(c): return s.audit_log(c.con)

@route("GET", "/api/reports")
def _rl(c): return reports.REPORTS

@route("GET", "/api/reports/([\\w-]+)")
def _rr(c, rid): return reports.run_report(c.con, rid, {k: v[0] for k, v in c.query.items()})


# ------------------------------------------------------------------ handler
class Handler(BaseHTTPRequestHandler):
    server_version = "GooyaAsset/1.0"

    def log_message(self, fmt, *args):
        if "--quiet" not in sys.argv and self.path.startswith("/api/"):
            sys.stderr.write("%s %s\n" % (self.command, self.path))

    def _send(self, status, payload: bytes, ctype="application/json; charset=utf-8", extra=None):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(payload)

    def _json(self, status, obj):
        self._send(status, json.dumps(obj, ensure_ascii=False).encode("utf-8"))

    def _host_ok(self) -> bool:
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0]
        if host not in HOSTS:
            return False
        origin = self.headers.get("Origin")
        return not origin or urlparse(origin).hostname in {"127.0.0.1", "localhost", "::1"}

    def _dispatch(self):
        if not self._host_ok():
            return self._json(403, {"error": "Forbidden"})
        u = urlparse(self.path)
        if not u.path.startswith("/api/"):
            return self._static(u.path)
        if u.path.startswith("/api/attachments/") and u.path.endswith("/download") and self.command == "GET":
            return self._download(u.path)
        if u.path.startswith("/api/backups/") and u.path.endswith("/download") and self.command == "GET":
            return self._download_backup(u.path)
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        body = {}
        if raw and "json" in (self.headers.get("Content-Type") or ""):
            try:
                body = json.loads(raw.decode("utf-8"))
            except ValueError:
                return self._json(400, {"error": "Invalid JSON"})
        s.set_lang(self.headers.get("X-Lang", "en"))
        for method, rx, fn in ROUTES:
            m = rx.match(u.path)
            if m and method == self.command:
                con = db.connect()
                try:
                    res = fn(Ctx(con, parse_qs(u.query), body, raw, self.headers), *m.groups())
                    return self._json(200, res)
                except s.ApiError as e:
                    con.rollback()
                    return self._json(e.status, {"error": str(e)})
                except sqlite3.Error as e:
                    con.rollback()
                    return self._json(400, {"error": f"Database error: {e}"})
                except Exception as e:  # noqa: BLE001
                    con.rollback()
                    traceback.print_exc()
                    return self._json(500, {"error": f"Unexpected error: {e}"})
                finally:
                    con.close()
        self._json(404, {"error": "Not found"})

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
        target = (STATIC / rel).resolve()
        if STATIC.resolve() not in target.parents or not target.is_file():
            target = STATIC / "index.html"  # SPA fallback
        ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if target.suffix in (".js", ".css", ".html", ".svg"):
            ctype += "; charset=utf-8"
        self._send(200, target.read_bytes(), ctype)

    do_GET = do_POST = do_PUT = do_DELETE = do_HEAD = _dispatch


def serve(port: int = 8742, open_browser: bool = True) -> None:
    db.init_db()
    if not db.DB_PATH.exists() or not _has_data():
        if db.EXPORT_PATH.exists():
            print("First run: importing data from Access export…", db.migrate_from_access())
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}/"
    print(f"Gooya Asset is running at {url}  (Ctrl+C to stop)")
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
