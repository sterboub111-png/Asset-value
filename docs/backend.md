# Backend

Python 3.12, standard library only. Entry points: `run.py` → `app.server.serve()`.

## Packages and modules

### `app/services/` — business logic

`from app import services as s` still works: `services/__init__.py` re-exports every public function, so callers use
`s.save_asset(...)`, `s.propose(...)` and so on. Inside the package, modules import from each other directly.

| Module | Responsibility | Main functions |
|---|---|---|
| `common.py` | request context and shared helpers | `set_actor/actor`, `set_lang`, `localize`, `ApiError`, `now`, `r2`, `rows`, `one`, `audit`, `parse_date`, `num`, `to_int` |
| `settings.py` | settings, master data, UI lookups | `get_settings`, `save_settings`, `master_list/save/delete`, `lookups` |
| `periods.py` | depreciation periods | `generate_periods`, `set_period_status`, `period_for_date` |
| `assets.py` | the asset register | `list_assets`, `get_asset`, `save_asset`, `delete_asset`, `change_status`, `transfer_asset`, `next_asset_code` |
| `depreciation.py` | monthly depreciation | `propose`, `run_depreciation`, `draft_lines`, `discard_drafts`, `post_depreciation`, `suggest_period` |
| `disposal.py` | disposal and its journal | `dispose_asset` |
| `files.py` | where attachment files live, safe removal | `_attach_root`, `_remove_file` |
| `attachments.py` | files attached to assets | `add_attachment`, `get_attachment`, `delete_attachment` |
| `inquiries.py` | journal, transactions, audit log lists | `journal`, `transactions`, `audit_log` |
| `dashboard.py` | workspace figures | `dashboard` |
| `maintenance.py` | maintenance orders and their workflow | `list/get/save/delete_maintenance`, `maintenance_action` |
| `suppliers.py` | suppliers and other contacts | `list/get/save/delete_supplier`, `next_supplier_code` |
| `employees.py` | employees | `list/get/save/delete_employee`, `next_employee_code` |
| `custody.py` | custody issue / return, signed forms | `issue_custody`, `update_custody`, `return_custody`, `delete_custody`, `add_custody_attachment` |
| `backup.py` | backups and the schedule | `create_backup`, `list_backups`, `backup_path`, `backup_schedule`, `run_due_backup`, `open_backup_folder` |

Dependencies point one way (no import cycles): `common` ← `settings` ← `periods` ← … ← `assets` ← `attachments`/`depreciation` ← `disposal`.
`custody.add_custody_attachment` imports `attachments` inside the function, because `attachments → assets → custody`.

### `app/api/` — HTTP endpoints

- `router.py`: the `ROUTES` list, the `@route(method, regex)` decorator and `Ctx` (connection, query, JSON body, raw body, headers,
  user, session token, cookies to set). `c.q("name")` reads a query parameter.
- `routes/*.py`: each file only maps requests to service calls and shapes the response, for example

```python
@route("PUT", "/api/assets/(\\d+)")
def _au(c, i): return _asset_out(c, s.save_asset(c.con, c.body, int(i)))
```

  Importing `app.api.routes` registers all routes. The permission a route needs is **not** declared here but in
  `auth.required_permission`, so security rules sit in one place.

### Other modules

- `db.py` — `connect()`, `init_db()` (idempotent: creates tables, seeds groups/accounts/methods/currencies/periods/settings, applies
  `ALTER TABLE` upgrades, seeds roles), `migrate_from_access()` (one-time import of the Access export).
- `auth.py` — password hashing (PBKDF2-SHA256, 200 000 rounds, per-password salt), users and roles CRUD, sessions, login lockout, the
  permission catalog and `required_permission`.
- `reports.py` — `REPORTS` metadata and `run_report(con, id, params)`; every builder returns
  `{title, params, columns, rows, group_by?, totals}` so one viewer renders and exports all of them.
- `scheduler.py` — a daemon thread that calls `run_due_backup` every 30 seconds under the actor `system`.
- `server.py` — handler, security checks, static files, `serve()` (creates/upgrades the database, starts the scheduler, opens the browser).

## Conventions

- **Validation in services.** Use `parse_date`, `num`, `to_int`; raise `ApiError("message")` (English key; the UI translates it via
  `core/ar.ts`). Never trust a number or id from a request.
- **Audit.** Call `audit(con, ACTION, table, id, details)` for every create/update/delete/post; `CreatedBy/ModifiedBy` use `actor()`.
- **Transactions.** A service commits once at the end (`con.commit()`); posting and disposal write state and journal together.
- **Bilingual output.** Fetch lists with `rows()` / `one()` (they localize). Use `raw=True` for internal logic that needs English values.
- **SQL.** Parameterised queries only; identifiers that vary come from fixed whitelists (`MASTERS`).
- **New endpoint:** service function → route in `api/routes/<feature>.py` → permission rule in `auth.required_permission` →
  test → (if there are new messages) `tools/gen_ar.py`.
