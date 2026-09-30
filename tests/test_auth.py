"""Sign-in, roles and permissions, against a real server on a throw-away database.
Run:  python -m tests.test_auth"""
import http.client
import json
import shutil
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

from app import db

tmp = Path(tempfile.mkdtemp())
db.DB_PATH = tmp / "auth.db"
db.DATA_DIR = tmp
db.init_db()
from app import server  # noqa: E402  (after the database path is patched)

httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
PORT = httpd.server_address[1]
threading.Thread(target=httpd.serve_forever, daemon=True).start()


class Client:
    def __init__(self):
        self.cookie = None

    def call(self, method, path, body=None):
        conn = http.client.HTTPConnection("127.0.0.1", PORT)
        headers = {"Content-Type": "application/json", "X-Requested-With": "GooyaAsset"}
        if self.cookie:
            headers["Cookie"] = self.cookie
        conn.request(method, path, json.dumps(body).encode() if body is not None else None, headers)
        r = conn.getresponse()
        raw = r.read()
        sc = r.getheader("Set-Cookie")
        if sc:
            self.cookie = sc.split(";")[0] if "Max-Age=0" not in sc else None
        data = json.loads(raw) if raw and r.getheader("Content-Type", "").startswith("application/json") else None
        conn.close()
        return r.status, data, sc


def ok(cond, msg):
    assert cond, msg


admin = Client()
anon = Client()

# --- first start: everything is locked until the administrator is created
st, d, _ = anon.call("GET", "/api/auth/status")
ok(st == 200 and d["needs_setup"] and d["user"] is None, "status before setup")
ok(anon.call("GET", "/api/assets")[0] == 401, "API needs a session")
ok(anon.call("GET", "/api/dashboard")[0] == 401, "dashboard needs a session")
ok(anon.call("POST", "/api/auth/setup", {"UserName": "boss", "FullName": "The Boss", "Password": "short", "ConfirmPassword": "short"})[0] == 400, "weak password rejected")
st, d, sc = admin.call("POST", "/api/auth/setup", {"UserName": "boss", "FullName": "The Boss", "Password": "Passw0rd!x", "ConfirmPassword": "Passw0rd!x"})
ok(st == 200 and d["IsAdmin"] == 1 and "PasswordHash" not in json.dumps(d), "setup creates the administrator")
ok("HttpOnly" in sc and "SameSite=Strict" in sc, "session cookie flags: " + sc)
ok(anon.call("POST", "/api/auth/setup", {"UserName": "x1x", "FullName": "X", "Password": "Passw0rd!x"})[0] == 403, "setup only once")
ok(admin.call("GET", "/api/auth/me")[1]["UserName"] == "boss", "me")

# --- wrong password / unknown user look the same; lock after 5 failures
bad = Client()
st1, d1, _ = bad.call("POST", "/api/auth/login", {"UserName": "boss", "Password": "wrong-pass1"})
st2, d2, _ = bad.call("POST", "/api/auth/login", {"UserName": "nobody", "Password": "wrong-pass1"})
ok(st1 == st2 == 401 and d1["error"] == d2["error"], "no user enumeration")
for _ in range(3):
    bad.call("POST", "/api/auth/login", {"UserName": "boss", "Password": "wrong-pass1"})
st, d, _ = bad.call("POST", "/api/auth/login", {"UserName": "boss", "Password": "wrong-pass1"})   # 5th failure locks
st, d, _ = bad.call("POST", "/api/auth/login", {"UserName": "boss", "Password": "Passw0rd!x"})
ok(st == 429 and "Too many" in d["error"], "locked after 5 failures even with the right password")
users = admin.call("GET", "/api/users")[1]
boss = next(u for u in users if u["UserName"] == "boss")
ok(boss["IsLocked"] and "PasswordHash" not in boss, "locked flag, no hash exposed")
admin.call("POST", f"/api/users/{boss['UserID']}/unlock")
ok(Client().call("POST", "/api/auth/login", {"UserName": "boss", "Password": "Passw0rd!x"})[0] == 200, "unlock works")

# --- roles and permissions
roles = {r["RoleName"]: r for r in admin.call("GET", "/api/roles")[1]}
ok(set(roles) >= {"Administrator", "Asset Accountant", "Asset Officer", "Viewer"}, "seeded roles")
st, d, _ = admin.call("POST", "/api/users", {"UserName": "vera", "FullName": "Vera Viewer", "RoleID": roles["Viewer"]["RoleID"], "Password": "Viewer123"})
ok(st == 200, str(d))
admin.call("POST", "/api/users", {"UserName": "olga", "FullName": "Olga Officer", "RoleID": roles["Asset Officer"]["RoleID"], "Password": "Officer123"})
viewer, officer = Client(), Client()
ok(viewer.call("POST", "/api/auth/login", {"UserName": "vera", "Password": "Viewer123"})[0] == 200, "viewer signs in")
ok(officer.call("POST", "/api/auth/login", {"UserName": "olga", "Password": "Officer123"})[0] == 200, "officer signs in")
ok(viewer.call("GET", "/api/assets")[0] == 200, "viewer can read assets")
ok(viewer.call("GET", "/api/reports/asset-register?as_of=2026-12-31")[0] == 200, "viewer can run reports")
ok(viewer.call("POST", "/api/assets", {"AssetName": "x", "CategoryID": 5, "AcquisitionDate": "2026-01-01", "PurchaseAmount": 10})[0] == 403, "viewer cannot create assets")
for path in ("/api/settings", "/api/users", "/api/audit", "/api/backups", "/api/master/categories"):
    ok(viewer.call("GET", path)[0] == 403, f"viewer blocked from {path}")
ok(viewer.call("POST", "/api/depreciation/1/post", {})[0] == 403, "viewer cannot post depreciation")
cat = admin.call("POST", "/api/master/categories", {"CategoryCode": "FUR", "CategoryName": "Furniture", "UsefulLifeYears": 5, "IsActive": True})[1]["CategoryID"]
ok(officer.call("POST", "/api/assets", {"AssetName": "Desk", "CategoryID": cat, "AcquisitionDate": "2026-01-01", "PurchaseAmount": 500})[0] == 200, "officer can create assets")
ok(officer.call("POST", "/api/depreciation/1/post", {})[0] == 403, "officer cannot post depreciation")
ok(officer.call("GET", "/api/users")[0] == 403, "officer cannot manage users")
# attachments / downloads sit behind the same gate
ok(anon.call("GET", "/api/attachments/1/download")[0] == 401 and anon.call("GET", "/api/backups/x/download")[0] == 401, "downloads need a session")

# changing a role takes effect at once
custom = admin.call("POST", "/api/roles", {"RoleName": "Poster", "permissions": ["depreciation.view", "depreciation.post", "bogus.perm"]})[1]
ok(custom["permissions"] == ["depreciation.post", "depreciation.view"], "unknown permissions are ignored: " + str(custom["permissions"]))
admin.call("PUT", f"/api/users/{next(u for u in admin.call('GET', '/api/users')[1] if u['UserName'] == 'vera')['UserID']}",
           {"UserName": "vera", "FullName": "Vera Viewer", "RoleID": custom["RoleID"], "IsActive": True})
ok(viewer.call("GET", "/api/auth/me")[0] == 401, "role change signs the user out")
viewer = Client(); viewer.call("POST", "/api/auth/login", {"UserName": "vera", "Password": "Viewer123"})
ok(viewer.call("GET", "/api/assets")[0] == 403 and viewer.call("GET", "/api/depreciation/suggest")[0] == 200, "custom role permissions")
admin.call("PUT", f"/api/roles/{custom['RoleID']}", {"RoleName": "Poster", "permissions": ["assets.view"]})
ok(viewer.call("GET", "/api/assets")[0] == 200 and viewer.call("GET", "/api/depreciation/suggest")[0] == 403, "role edit applies immediately")
ok(admin.call("PUT", f"/api/roles/{roles['Administrator']['RoleID']}", {"RoleName": "Administrator", "permissions": []})[0] == 400, "administrator role is locked")
ok(admin.call("DELETE", f"/api/roles/{custom['RoleID']}")[0] == 400, "role in use cannot be deleted")

# --- last administrator protection
me_id = admin.call("GET", "/api/auth/me")[1]["UserID"]
ok(admin.call("DELETE", f"/api/users/{me_id}")[0] == 400, "cannot delete yourself")
st, d, _ = admin.call("PUT", f"/api/users/{me_id}", {"UserName": "boss", "FullName": "The Boss", "RoleID": roles["Viewer"]["RoleID"], "IsActive": True})
ok(st == 400 and "administrator" in d["error"], "cannot demote the last administrator: " + str(d))
ok(admin.call("PUT", f"/api/users/{me_id}", {"UserName": "boss", "FullName": "The Boss", "RoleID": roles["Administrator"]["RoleID"], "IsActive": False})[0] == 400, "cannot deactivate yourself")

# --- profile and password
ok(admin.call("PUT", "/api/auth/profile", {"FullName": "Boss Person", "Language": "ar", "Theme": "dark"})[1]["Language"] == "ar", "profile preferences")
ok(admin.call("POST", "/api/auth/password", {"Current": "nope", "New": "Another1x"})[0] == 400, "wrong current password")
ok(admin.call("POST", "/api/auth/password", {"Current": "Passw0rd!x", "New": "short"})[0] == 400, "new password policy")
other = Client(); other.call("POST", "/api/auth/login", {"UserName": "boss", "Password": "Passw0rd!x"})
ok(admin.call("POST", "/api/auth/password", {"Current": "Passw0rd!x", "New": "Another1x"})[0] == 200, "password changed")
ok(other.call("GET", "/api/auth/me")[0] == 401 and admin.call("GET", "/api/auth/me")[0] == 200, "other sessions end, this one stays")
ok(Client().call("POST", "/api/auth/login", {"UserName": "boss", "Password": "Passw0rd!x"})[0] == 401 and Client().call("POST", "/api/auth/login", {"UserName": "BOSS", "Password": "Another1x"})[0] == 200, "new password works, user names are case-insensitive")

# --- forced password change
admin.call("POST", "/api/users", {"UserName": "newbie", "FullName": "New Person", "RoleID": roles["Viewer"]["RoleID"], "Password": "Temp12345", "MustChangePassword": True})
nb = Client(); nb.call("POST", "/api/auth/login", {"UserName": "newbie", "Password": "Temp12345"})
st, d, _ = nb.call("GET", "/api/assets")
ok(st == 403 and d.get("auth") == "password", "must change password first")
ok(nb.call("POST", "/api/auth/password", {"Current": "Temp12345", "New": "Fresh12345"})[0] == 200 and nb.call("GET", "/api/assets")[0] == 200, "then access is granted")

# --- sign out
ok(admin.call("POST", "/api/auth/logout")[0] == 200 and admin.call("GET", "/api/assets")[0] == 401, "sign out")
# passwords are salted hashes
con = db.connect()
hashes = [r[0] for r in con.execute("SELECT PasswordHash FROM tbl_Users")]
ok(all(h.startswith("pbkdf2_sha256$") for h in hashes) and len(set(hashes)) == len(hashes), "hashed and salted")
ok(not any("Passw0rd" in h or "Another1x" in h for h in hashes), "no plaintext")
httpd.shutdown()
shutil.rmtree(tmp, ignore_errors=True)
print("All authentication tests passed")
