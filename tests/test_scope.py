"""Branch scope over HTTP: a user limited to one branch sees only it through every route, the branch picker narrows an
unrestricted user, and one request's scope never carries over to the next request on the same server thread.
Run:  python3 -m tests.test_scope"""
import http.client
import json
import threading
from http.server import ThreadingHTTPServer

from tests.fixture import fresh_db

fresh_db("scope.db")
from app import auth, db, services as s  # noqa: E402  (after the database path is set)
from app import server  # noqa: E402

con = db.connect()
s.set_actor("tester")
s.generate_periods(con, 2026)
cat = {r["CategoryCode"]: r["CategoryID"] for r in s.rows(con, "SELECT * FROM tbl_AssetCategories", raw=True)}
for code, name, cc in (("RYD", "Riyadh", "SA"), ("JED", "Jeddah", "SA"), ("DXB", "Dubai", "AE")):
    s.master_save(con, "branches", {"BranchCode": code, "BranchName": name, "CountryCode": cc})
br = {r["BranchCode"]: r["BranchID"] for r in s.rows(con, "SELECT * FROM tbl_Branches", raw=True)}
for code in br:
    s.master_save(con, "locations", {"LocationCode": f"{code}-1", "LocationName": f"{code} store", "BranchID": br[code]})
loc = {r["LocationCode"][:3]: r["LocationID"] for r in s.rows(con, "SELECT * FROM tbl_Locations", raw=True)}
assets = {code: s.save_asset(con, {"AssetName": f"PC {code}", "CategoryID": cat["IT"], "AcquisitionDate": "2026-01-10", "PurchaseAmount": 3600,
                                   "VatApplicable": 0, "LocationID": loc[code]}) for code in br}
auth.seed(con)
admin_role = auth.admin_role_id(con)
viewer = s.one(con, "SELECT RoleID FROM tbl_Roles WHERE RoleName='Asset Accountant'")["RoleID"]
auth.save_user(con, {"UserName": "boss", "FullName": "Boss", "RoleID": admin_role, "Password": "Passw0rd!x"})
auth.save_user(con, {"UserName": "ryd", "FullName": "Riyadh accountant", "RoleID": viewer, "Password": "Passw0rd!x", "Branches": [br["RYD"]]})
con.close()

httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
PORT = httpd.server_address[1]
threading.Thread(target=httpd.serve_forever, daemon=True).start()


class Client:
    def __init__(self, scope=""):
        self.cookie, self.scope = None, scope

    def call(self, method, path, body=None):
        conn = http.client.HTTPConnection("127.0.0.1", PORT)
        headers = {"Content-Type": "application/json", "X-Requested-With": "GooyaAsset", "X-Scope": self.scope}
        if self.cookie:
            headers["Cookie"] = self.cookie
        conn.request(method, path, json.dumps(body).encode() if body is not None else None, headers)
        r = conn.getresponse()
        raw = r.read()
        sc = r.getheader("Set-Cookie")
        if sc:
            self.cookie = sc.split(";")[0]
        data = json.loads(raw) if raw and r.getheader("Content-Type", "").startswith("application/json") else None
        conn.close()
        return r.status, data

    def login(self, user):
        st, _ = self.call("POST", "/api/auth/login", {"UserName": user, "Password": "Passw0rd!x"})
        assert st == 200, st
        return self


codes = lambda rows: {r["AssetCode"] for r in rows}
boss, ryd = Client().login("boss"), Client().login("ryd")
mine, other = assets["RYD"], assets["JED"]

# the branch-limited user, through every route that shows assets
st, rows = ryd.call("GET", "/api/assets")
assert st == 200 and codes(rows) == {mine["AssetCode"]}, codes(rows)
assert ryd.call("GET", f"/api/assets/{other['AssetID']}")[0] == 404
assert ryd.call("GET", f"/api/ledger?asset={other['AssetID']}")[1]["total"] == 0
assert codes(ryd.call("GET", "/api/reports/asset-register?as_of=2026-12-31")[1]["rows"]) == {mine["AssetCode"]}
assert ryd.call("GET", "/api/dashboard")[1]["asset_count"] == 1
tree = ryd.call("GET", "/api/branches/tree")[1]
assert tree["limited"] and [b["BranchCode"] for c in tree["countries"] for b in c["branches"]] == ["RYD"], tree
assert ryd.call("POST", f"/api/assets/{other['AssetID']}/transfer", {"TransactionDate": "2026-02-01", "ToLocationID": loc["RYD"]})[0] == 404
st, err = ryd.call("POST", "/api/assets", {"AssetName": "X", "CategoryID": cat["IT"], "AcquisitionDate": "2026-02-01", "PurchaseAmount": 1, "LocationID": loc["DXB"]})
assert st == 400 and "branches you work in" in err["error"], err
# asking for another branch in the picker does not widen what the user may see
ryd.scope = f"branch:{br['DXB']}"
assert codes(ryd.call("GET", "/api/assets")[1]) == {mine["AssetCode"]}
# the depreciation run of a limited user proposes and posts only their branch
jan = s.rows(db.connect(), "SELECT PeriodID FROM tbl_DepreciationPeriods WHERE FiscalYear=2026 AND PeriodNumber=1", raw=True)[0]["PeriodID"]
ryd.scope = ""
assert ryd.call("POST", f"/api/depreciation/{jan}/run", {})[1]["created"] == 1

# the administrator: everything, narrowed by the picker to a country, and never left with the last user's scope
assert codes(boss.call("GET", "/api/assets")[1]) == {a["AssetCode"] for a in assets.values()}
boss.scope = "country:SA"
assert codes(boss.call("GET", "/api/assets")[1]) == {assets["RYD"]["AssetCode"], assets["JED"]["AssetCode"]}
boss.scope = ""
for _ in range(5):   # alternate users on the same server threads
    assert len(ryd.call("GET", "/api/assets")[1]) == 1
    assert len(boss.call("GET", "/api/assets")[1]) == 3
anon = Client()
assert anon.call("GET", "/api/assets")[0] == 401
httpd.shutdown()
print("All branch scope tests passed")
