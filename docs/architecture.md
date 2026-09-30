# Architecture

## Overview

```
 Browser (SPA, TypeScript → ES modules)            Python process (stdlib only)
┌──────────────────────────────────────┐   JSON   ┌──────────────────────────────────────────┐
│ web/src  main → shell → pages → ui   │◄────────►│ server.py  (HTTP handler, static files)   │
│ hash router, i18n (AR/EN), theme     │  cookie  │  └ api/router + api/routes/*  (endpoints) │
└──────────────────────────────────────┘  session │      └ auth.py   (users, roles, sessions) │
                                                   │      └ services/ (business rules)         │
                                                   │      └ reports.py (report builders)       │
                                                   │ scheduler.py (auto backup thread)         │
                                                   │ db.py  → SQLite  data/gooya_asset.db      │
                                                   └──────────────────────────────────────────┘
                                                   attachments/  backups/  (files on disk)
```

- **No framework, no external service.** Backend: Python standard library (`http.server`, `sqlite3`, `zipfile`, `hashlib`).
  Frontend: TypeScript compiled by `tsc` to plain ES modules; no bundler and no runtime dependency.
- The server binds to `127.0.0.1` only. It also validates the `Host` and `Origin` headers.
- SQLite runs in WAL mode with foreign keys on. Every request opens its own connection.

## Folder layout

```
run.py                     start the server        Usool.bat   Windows launcher
app/
  db.py                    schema, seed data, upgrades, one-time Access import
  auth.py                  passwords, users, roles, permissions, sessions, lockout
  reports.py               19 report builders (one function per report, common result shape)
  scheduler.py             background thread for scheduled backups
  server.py                HTTP handler: security checks, dispatch, static files, startup
  api/
    router.py              route table, @route decorator, per-request Ctx
    routes/                one module per feature: setup, assets, depreciation, maintenance,
                           contacts, custody, backups, accounts, inquiries
  services/                business logic, one module per feature (see backend.md)
web/
  src/                     TypeScript source
    main.ts                entry: boot, session start, page rendering
    core/                  api client, i18n, session/permissions, shared types, Arabic dictionary
    shell/                 routes + navigation tree, navigation pane (rail), top bar, account menu
    ui/                    UI kit: dom, icons, format, dialogs, form, layout, grid, helpers
    pages/                 screens grouped by feature: workspace, assets, depreciation, maintenance,
                           contacts (suppliers/employees/custody), reports, settings, auth
  static/                  index.html, css/*.css, js/ (compiled output — do not edit)
tests/                     test_flow, test_auth, test_review
tools/                     export_access.ps1, extract_keys.py, gen_ar.py, reset_test_data.py, restore_backup.py
data/                      SQLite database, Access export (created at run time)
attachments/  backups/     default locations for uploaded files and backup archives
docs/                      this documentation
```

## Request lifecycle

1. `server.Handler` receives the request, checks `Host` / `Origin`, and (for state-changing calls) the `X-Requested-With` header.
2. Static paths are served from `web/static` (SPA fallback to `index.html`, security headers and CSP).
3. For `/api/...` the session cookie `gooya_session` is resolved to a user; `auth.required_permission(method, path)` decides which
   permission the call needs (default deny → `users.manage`). Users who must change their password can only reach the password call.
4. The thread-local context is set: the actor (for audit fields) and the language (`X-Lang`) so that `localize()` returns Arabic
   names when the UI is in Arabic.
5. The matching route function runs, calls a service (`services.<function>`), and returns a dict/list serialised as JSON.
6. `ApiError(message, status)` becomes `{"error": message}`; any other exception becomes a generic 500 (details go to the log only).

## Design decisions

- **Business rules live in `services/`, never in the routes and never only in the browser.** The UI hides what a user may not do,
  but the server enforces every rule (permissions, locked fields, closed periods, sequence of depreciation).
- **The books use net cost.** VAT is recorded on the asset for reporting but never enters depreciation or journals.
- **Journal entries are written when depreciation is posted or an asset is disposed**, in the same transaction as the state change.
- **Bilingual data:** master data and assets carry `<Field>` and `<Field>Ar`; `localize()` swaps them by request language.
  UI strings are keys in English; `core/ar.ts` maps them to Arabic (generated from `tools/gen_ar.py`).
- **Everything is local and private:** no telemetry, no CDN, fonts and icons are inline.
