"""Depreciation periods and the depreciation run."""
from __future__ import annotations

from ... import services as s

from ..router import route


@route("GET", "/api/periods")
def _pl(c): return s.rows(c.con, "SELECT * FROM tbl_DepreciationPeriods ORDER BY StartDate")

@route("POST", "/api/periods/generate")
def _pg(c): return s.generate_periods(c.con, s.to_int(c.body.get("fiscal_year"), "Fiscal year"))

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
