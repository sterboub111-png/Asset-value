# Usool (أصول) — local fixed-asset register

Local application (Python + HTML/CSS/TypeScript),  Data lives in `data/gooya_asset.db` (SQLite),
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

## Import from Excel
- Fixed assets > Import from Excel (`#/assets/import`): download the template (Arabic or English headers, a Lists sheet with valid groups, locations, cost centers and suppliers), choose an .xlsx or .csv file, review every row (checked with the asset form's rules), then import the ready rows. Read with the standard library only (`app/services/importer.py`).

## Physical counts, labels and forecast
- **Asset labels** (`#/assets/labels`): Code 39 barcodes of the asset codes on A4 label sheets (24 or 14 per page).
- **Physical counts** (`#/counts`): a count snapshots the assets expected at a location; scan (any barcode scanner) or type codes / serial numbers; the count shows found, missing, found elsewhere, not expected and unknown; closing can transfer the assets found elsewhere (`app/services/counts.py`).
- **Depreciation forecast** report: the depreciation still to come month by month (up to 60 months), by the same rules as the depreciation run.

## Tests and tools
- `python -m tests.test_flow` business rules, `python -m tests.test_auth` sign-in and permissions, `python -m tests.test_review` regression tests for the review fixes,
  `python -m tests.test_integrity` the data checks, `python -m tests.test_import` import from Excel, `python -m tests.test_counts` physical counts and the depreciation forecast (`npm test` runs all six). Every suite builds its own clean database from `data/access_export.json`; none reads `data/gooya_asset.db`.
- **Data checks** (Inquiries > Data checks, `GET /api/integrity`, `app/services/integrity.py`): the arithmetic the books must satisfy, recalculated from the tables - depreciation lines, journal balance, disposals, VAT, periods, and reports tied to the books.
- `python tools/reset_test_data.py --yes` removes test data safely; `python tools/restore_backup.py <zip>` restores a backup.
- `node node_modules/typescript/bin/tsc -p .` builds the front end (strict, unused code is an error).
