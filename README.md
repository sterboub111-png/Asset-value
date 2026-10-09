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
- Book value (`app/services/book.py`, one definition for every screen, report and check): cost = acquisition (net of VAT) + capital additions; NBV = cost − accumulated depreciation + revaluations − impairments.
- Straight line, monthly: (cost − residual) ÷ (life × 12), full month from the depreciation-start month, capped at the depreciable amount. After a capital addition or a revaluation / impairment, the remaining amount is spread over the remaining life (IAS 16.50, IAS 36.63).
- Declining balance (method `DB`): the year's charge is the rate × the carrying amount at the start of the fiscal year, spread over its months, switching to straight line when that gives more; the rate defaults to double the straight-line rate. One rule (`monthly_charge` in `app/services/depreciation.py`) serves the run, the forecast and the previews.
- Workflow: Create proposal → review → Post (writes Dr expense / Cr accumulated depreciation). Periods must post in sequence; closed periods are locked.
- After posting, cost / life / method / dates are locked. Location and cost center change only through Transfer.
- Disposal: requires depreciation posted up to the month before; posts Dr accum. dep, Dr proceeds clearing, Dr loss / Cr gain, Cr cost.
- Capital addition (Fixed asset > Value): raises the cost (recorded in the purchase ledger like the acquisition, so no journal here); the useful life may be extended at the same time.
- Revaluation / impairment (Fixed asset > Value): the carrying amount goes to a new value. A decrease uses the asset's revaluation surplus first, then is an impairment loss; an increase first reverses earlier impairment losses, then goes to the revaluation surplus. Posts against the accumulated depreciation account and the impairment / revaluation surplus accounts of Fixed asset parameters (`app/services/valuation.py`).
- Additions and value changes are dated after the last posted month of the asset; disposals and later changes keep that order.

## Countries, branches and scope (large organisations)
- Settings > Branches: each branch has a country (ISO list) and optionally a city and region; each location belongs to a branch, so an asset's branch and country follow its location.
- Users can be limited to some branches (Settings > Users). The branch picker in the top bar narrows everything to a country or a branch. The server applies both to every call (`scope_sql` in `app/services/common.py`): lists, cards, reports, the ledger, the workspace, counts and depreciation runs.
- Reports group and filter by country, region and branch (register, summary, roll-forward, journal, disposals ...).
- Checked at scale: 100 branches in 6 countries, 30,000 assets: a month's proposal and posting about 1.3 s, every report under 1.5 s, the data checks about 4 s.

## Fixed asset ledger
- Accounting > Fixed asset ledger (`#/ledger`, `app/services/ledger.py`): every acquisition, addition, month of depreciation, revaluation, impairment, transfer and disposal, each with a document number (DEP-2026-09, DSP-000042 ...) that opens its journal lines. On the asset card the same entries add up to its net book value.
- The journal report shows vouchers; its summary view gives one entry per account and document to post to the general ledger.

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
  `python -m tests.test_integrity` the data checks, `python -m tests.test_import` import from Excel, `python -m tests.test_counts` physical counts and the depreciation forecast, `python -m tests.test_valuation` declining balance, additions, revaluation / impairment, the ledger and branches, `python -m tests.test_scope` branch scope over HTTP (`npm test` runs all eight). Every suite builds its own clean database from `data/access_export.json`; none reads `data/gooya_asset.db`.
- **Data checks** (Accounting > Data checks, `GET /api/integrity`, `app/services/integrity.py`): the arithmetic the books must satisfy, recalculated from the tables - depreciation lines, journal balance, disposals, additions and revaluations, VAT, periods, and reports tied to the books.
- `python tools/reset_test_data.py --yes` removes test data safely; `python tools/restore_backup.py <zip>` restores a backup.
- `node node_modules/typescript/bin/tsc -p .` builds the front end (strict, unused code is an error).
