# Gooya Asset — local fixed-asset register

Local application (Python + HTML/CSS/TypeScript),  Data lives in `data/gooya_asset.db` (SQLite),
imported once from `Gooya asset.accdb`.

**Run:** double-click `Gooya Asset.bat` (or `python run.py`) → http://127.0.0.1:8742/

## Structure
- `app/` Python backend — `db.py` schema + Access import, `services.py` rules (depreciation, transfer, disposal, periods),
  `reports.py` reports, `server.py` HTTP/JSON API (stdlib only, bound to 127.0.0.1)
- `web/src/` TypeScript source → compiled to `web/static/js` with `node node_modules/typescript/bin/tsc -p .`
- `tools/export_access.ps1` re-exports the Access file to `data/access_export.json`; `tools/gen_ar.py` builds the Arabic dictionary
- `tests/test_flow.py` business-rule tests on a temp copy: `python -m tests.test_flow`

## Rules
- Straight line, monthly: (cost − residual) ÷ (life × 12), full month from the depreciation-start month, capped at the depreciable amount.
- Workflow: Create proposal → review → Post (writes Dr expense / Cr accumulated depreciation). Periods must post in sequence; closed periods are locked.
- After posting, cost / life / method / dates are locked. Location and cost center change only through Transfer.
- Disposal: requires depreciation posted up to the month before; posts Dr accum. dep, Dr proceeds clearing, Dr loss / Cr gain, Cr cost.
