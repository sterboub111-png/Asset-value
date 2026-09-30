# Usool (أصول) — local fixed-asset register

Local application (Python + HTML/CSS/TypeScript), Dynamics 365 Finance style. Data lives in `data/gooya_asset.db` (SQLite),
imported once from `Gooya asset.accdb`.

**Run:** double-click `Usool.bat` (or `python run.py`) → http://127.0.0.1:8742/

## Structure
- `app/` Python backend (stdlib only, bound to 127.0.0.1): `db.py` schema, `auth.py`, `reports.py`, `scheduler.py`, `server.py`;
  `services/` business rules (one module per feature), `api/` routes (one module per feature)
- `web/src/` TypeScript (`core/`, `shell/`, `ui/`, `pages/<feature>/`) → compiled to `web/static/js` with `npm run build`
  (`node node_modules/typescript/bin/tsc -p .`); styles in `web/static/css/*.css`
- `tools/` Access export, translation dictionary, reset and restore tools; `tests/` test suites
- **Documentation:** [docs/README.md](docs/README.md) — architecture, backend, API, database, frontend, business rules, security, user guides (EN/AR), development

## Rules
- Straight line, monthly: (cost − residual) ÷ (life × 12), full month from the depreciation-start month, capped at the depreciable amount.
- Workflow: Create proposal → review → Post (writes Dr expense / Cr accumulated depreciation). Periods must post in sequence; closed periods are locked.
- After posting, cost / life / method / dates are locked. Location and cost center change only through Transfer.
- Disposal: requires depreciation posted up to the month before; posts Dr accum. dep, Dr proceeds clearing, Dr loss / Cr gain, Cr cost.

## Sign-in, users and permissions
- First start with no users: the sign-in page offers to create the administrator. Passwords need 8+ characters with letters and digits; 5 failed sign-ins lock the account for 10 minutes.
- Settings > Users / Roles and permissions manage accounts; roles hold the permissions (checked on the server for every request).
- Changing state (POST/PUT/DELETE) requires the `X-Requested-With: GooyaAsset` header, which the app sends itself.

## Tests and tools
- `python -m tests.test_flow` business rules, `python -m tests.test_auth` sign-in and permissions, `python -m tests.test_review` regression tests for the review fixes.
- `python tools/reset_test_data.py --yes` removes test data safely; `python tools/restore_backup.py <zip>` restores a backup.
- `node node_modules/typescript/bin/tsc -p .` builds the front end (strict, unused code is an error).
