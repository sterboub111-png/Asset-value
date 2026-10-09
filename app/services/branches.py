"""Organisation: countries, branches and their locations, and which branches each user works in.

    country -> branch -> location -> asset

A location belongs to one branch, so an asset's branch and country follow its location (a transfer moves it).
A user with no branches assigned sees every branch; otherwise only theirs (services/common.py scope_sql).
"""
from __future__ import annotations

from .common import ApiError, audit, one, rows, set_scope, to_int

# ISO 3166 codes with English and Arabic names: the Gulf and the Arab world first, then the main trading countries
COUNTRIES = [
    ("SA", "Saudi Arabia", "المملكة العربية السعودية"), ("AE", "United Arab Emirates", "الإمارات العربية المتحدة"), ("KW", "Kuwait", "الكويت"),
    ("QA", "Qatar", "قطر"), ("BH", "Bahrain", "البحرين"), ("OM", "Oman", "عُمان"), ("EG", "Egypt", "مصر"), ("JO", "Jordan", "الأردن"),
    ("LB", "Lebanon", "لبنان"), ("IQ", "Iraq", "العراق"), ("SY", "Syria", "سوريا"), ("PS", "Palestine", "فلسطين"), ("YE", "Yemen", "اليمن"),
    ("SD", "Sudan", "السودان"), ("LY", "Libya", "ليبيا"), ("TN", "Tunisia", "تونس"), ("DZ", "Algeria", "الجزائر"), ("MA", "Morocco", "المغرب"),
    ("MR", "Mauritania", "موريتانيا"), ("TR", "Türkiye", "تركيا"), ("PK", "Pakistan", "باكستان"), ("IN", "India", "الهند"),
    ("BD", "Bangladesh", "بنغلاديش"), ("ID", "Indonesia", "إندونيسيا"), ("MY", "Malaysia", "ماليزيا"), ("SG", "Singapore", "سنغافورة"),
    ("CN", "China", "الصين"), ("JP", "Japan", "اليابان"), ("KR", "South Korea", "كوريا الجنوبية"), ("GB", "United Kingdom", "المملكة المتحدة"),
    ("IE", "Ireland", "أيرلندا"), ("FR", "France", "فرنسا"), ("DE", "Germany", "ألمانيا"), ("IT", "Italy", "إيطاليا"), ("ES", "Spain", "إسبانيا"),
    ("PT", "Portugal", "البرتغال"), ("NL", "Netherlands", "هولندا"), ("BE", "Belgium", "بلجيكا"), ("CH", "Switzerland", "سويسرا"),
    ("SE", "Sweden", "السويد"), ("PL", "Poland", "بولندا"), ("US", "United States", "الولايات المتحدة"), ("CA", "Canada", "كندا"),
    ("MX", "Mexico", "المكسيك"), ("BR", "Brazil", "البرازيل"), ("AU", "Australia", "أستراليا"), ("ZA", "South Africa", "جنوب أفريقيا"),
    ("NG", "Nigeria", "نيجيريا"), ("KE", "Kenya", "كينيا"), ("ET", "Ethiopia", "إثيوبيا"),
]
COUNTRY_CODES = {c for c, _, _ in COUNTRIES}
COUNTRY_SQL = "CASE B.CountryCode " + " ".join(f"WHEN '{c}' THEN '{en}'" for c, en, _ in COUNTRIES) + " ELSE B.CountryCode END"
COUNTRY_AR_SQL = "CASE B.CountryCode " + " ".join(f"WHEN '{c}' THEN '{ar}'" for c, _, ar in COUNTRIES) + " ELSE B.CountryCode END"


def countries() -> list[dict]:
    return [{"code": c, "name": en, "nameAr": ar} for c, en, ar in COUNTRIES]


def check_country(code) -> str:
    code = (code or "").strip().upper()
    if code not in COUNTRY_CODES:
        raise ApiError("Choose a country from the list")
    return code


# ---- which branches a user works in
def user_branches(con, uid: int) -> list[int]:
    return [r[0] for r in con.execute("SELECT BranchID FROM tbl_UserBranches WHERE UserID=? ORDER BY BranchID", (uid,))]


def set_user_branches(con, uid: int, branch_ids) -> None:
    ids = sorted({to_int(b, "Branch") for b in (branch_ids or []) if b not in (None, "")})
    known = {r[0] for r in con.execute("SELECT BranchID FROM tbl_Branches")}
    if any(b not in known for b in ids):
        raise ApiError("Branch not found")
    if ids != user_branches(con, uid):
        con.execute("DELETE FROM tbl_UserBranches WHERE UserID=?", (uid,))
        con.executemany("INSERT INTO tbl_UserBranches(UserID,BranchID) VALUES(?,?)", [(uid, b) for b in ids])
        audit(con, "UPDATE", "tbl_UserBranches", uid, ",".join(map(str, ids)) or "all branches")


def apply_scope(con, uid: int | None, requested: str | None) -> dict:
    """Set the request scope: the user's branches, narrowed by the branch picker ('', 'country:SA' or 'branch:12').
    Returns {allowed: [ids] | None, scope: [ids] | None} for the picker."""
    allowed = user_branches(con, uid) if uid else []
    allowed_or_all = allowed or None
    pick: list[int] | None = None
    req = (requested or "").strip()
    if req.startswith("branch:") and req[7:].isdigit():
        pick = [int(req[7:])]
    elif req.startswith("country:"):
        pick = [r[0] for r in con.execute("SELECT BranchID FROM tbl_Branches WHERE CountryCode=?", (req[8:].upper(),))]
    if pick is None:
        eff = allowed_or_all
    elif allowed_or_all is None:
        eff = pick
    else:
        eff = [b for b in pick if b in allowed_or_all]
        if not eff:
            eff = allowed_or_all   # a stale pick outside the user's branches falls back to all of theirs
    set_scope(eff)
    return {"allowed": allowed_or_all, "scope": eff}


def branch_tree(con) -> list[dict]:
    """Countries with their branches (and location counts) for the branch picker and the settings page."""
    out: dict[str, dict] = {}
    names = {c: (en, ar) for c, en, ar in COUNTRIES}
    for b in rows(con, """SELECT B.*, (SELECT COUNT(*) FROM tbl_Locations L WHERE L.BranchID=B.BranchID) AS Locations
            FROM tbl_Branches B ORDER BY B.CountryCode, B.BranchCode""", raw=True):
        en, ar = names.get(b["CountryCode"], (b["CountryCode"], b["CountryCode"]))
        out.setdefault(b["CountryCode"], {"code": b["CountryCode"], "name": en, "nameAr": ar, "branches": []})["branches"].append(b)
    return list(out.values())


def branch_of_location(con, location_id) -> dict | None:
    return one(con, "SELECT B.* FROM tbl_Locations L JOIN tbl_Branches B ON B.BranchID=L.BranchID WHERE L.LocationID=?", (location_id,), raw=True)
