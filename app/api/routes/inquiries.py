"""Journal, transactions, audit log and reports."""
from __future__ import annotations

from ... import auth, reports, services as s

from ..router import route


@route("GET", "/api/journal")
def _j(c): return s.journal(c.con, c.q("period"), c.q("type"))

@route("GET", "/api/transactions")
def _t(c): return s.transactions(c.con)

@route("GET", "/api/audit")
def _au_log(c): return s.audit_log(c.con)

@route("GET", "/api/reports")
def _rl(c): return [r for r in reports.REPORTS if auth.allowed(c.user, r.get("perm"))]

@route("GET", "/api/reports/([\\w-]+)")
def _rr(c, rid):
    if not auth.allowed(c.user, reports.REPORT_PERM.get(rid)):
        raise s.ApiError("You do not have permission to do this", 403)
    return reports.run_report(c.con, rid, {k: v[0] for k, v in c.query.items()})
