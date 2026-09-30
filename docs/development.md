# Development guide

## Setup
```
python -m venv .venv
.venv\Scripts\python -m pip install pyflakes nodejs-wheel   # optional: linter and a local Node for the TypeScript compiler
npm install                                                 # only if node_modules/ is missing (TypeScript)
```
The application itself needs only Python 3.12 (standard library). The compiled JavaScript in `web/static/js` is committed, so running the
app needs no Node; Node is only needed to change `web/src`.

Run: `Usool.bat` or `python run.py [--no-browser] [--port 8742]`.

## Build the front end
```
node node_modules/typescript/bin/tsc -p .
```
Output goes to `web/static/js` (committed: rebuild and commit it after every change to `web/src`; `npm run build` is the same command). The compiler is strict and treats unused
locals/parameters as errors. If the browser shows old code, hard-reload (`?v=` query) — static files are served without long caching.

## Tests
```
python -m tests.test_flow      # business rules on a temporary copy of the database
python -m tests.test_auth      # sign-in, sessions, permissions, lockout over real HTTP
python -m tests.test_review    # regression tests for issues found in reviews
python -m pyflakes app tools tests run.py
```
Tests never touch `data/`: each builds a temporary database (`db.DB_PATH` / `services.db.ROOT` are pointed at a temp folder).
Add a test for every rule you add; the flow test is the place for accounting behaviour.

## Adding a feature (checklist)
1. **Database:** add the table or column in `db.py` (`CREATE TABLE IF NOT EXISTS` for new tables, an `ALTER TABLE` guarded by a column check for existing ones).
2. **Service:** functions in `app/services/<feature>.py`; validate with `parse_date/num/to_int`; raise `ApiError("English message")`;
   `audit(...)`; commit once. Export the public functions in `services/__init__.py` (and its `__all__`).
3. **Route:** `app/api/routes/<feature>.py` with `@route(...)`; add the module to `routes/__init__.py`.
4. **Permission:** add rules to `auth.required_permission` and, if new, to the catalog (`PERMISSIONS`) and the seed roles.
5. **Page:** `web/src/pages/<feature>/…`, register it in `shell/routes.ts` (route, nav entry, `permFor`).
6. **Translations:** run `python tools/extract_keys.py` then `python tools/gen_ar.py`; it prints English keys that still have no Arabic
   entry — add them to the dictionary in `tools/gen_ar.py`.
7. **Docs:** regenerate `docs/api.md` if endpoints changed (see below) and update business-rules.md.

## Translation workflow
- UI text is written in English through `t("…")`, `label: "…"`, `title: "…"` etc. The English string is the key.
- `tools/extract_keys.py` scans `web/src` and the Python sources into `data/_keys.json`; `tools/gen_ar.py` merges them with the
  dictionary and writes `web/src/core/ar.ts` (LF line endings, no duplicates). Missing keys fall back to English.
- Server messages (`ApiError`) are translated in the browser with the same dictionary.

## Tools
| Command | Purpose |
|---|---|
| `python tools/reset_test_data.py --yes [--keep-contacts]` | remove all operational data (assets, depreciation, custody, maintenance, attachments, audit log, optionally suppliers/employees), reopen periods, restart numbering; runs integrity checks |
| `python tools/restore_backup.py <backup.zip>` | restore a backup archive (stop the server first; current database kept as `data/gooya_asset.before-restore.db`; attachments are re-pointed to the configured folder) |
| `powershell -ExecutionPolicy Bypass -File tools/export_access.ps1` | re-export the original Access file to `data/access_export.json` |
| `python tools/extract_keys.py`, `python tools/gen_ar.py` | translation workflow (above) |

## Regenerating the API reference
`docs/api.md` is generated from the live route table and `auth.required_permission`. Regenerate it after adding routes:
```
python tools/gen_api_doc.py
```

## Conventions
- Match the surrounding code: short functions, comments only for the *why*, English identifiers, English message keys.
- No new runtime dependency without a strong reason (the app is meant to run from a plain Python install).
- Never build SQL from request text except from fixed whitelists; never trust ids or numbers from the client.
- Do not commit `data/`, `attachments/`, `backups/`, `.venv/`, `node_modules/`.
