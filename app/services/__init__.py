"""Business logic, one module per feature. `services.<name>` keeps working for every public function."""
from __future__ import annotations

from .. import db  # tests point services.db at a temporary folder
from .common import (
    ASSET_STATUSES, ApiError, MONTHS_AR, USER, _ctx, actor, audit, localize, month_ar, now, num, one, parse_date, r2, rows, set_actor, set_lang, to_int,
)
from .settings import (
    _master, get_settings, lookups, master_delete, master_list, master_save, save_settings,
)
from .periods import (
    generate_periods, period_for_date, set_period_status,
)
from .assets import (
    ASSET_FIELDS, BOOK_SQL, _clean_asset, _with_nbv, change_status, delete_asset, get_asset, list_assets, next_asset_code, save_asset, transfer_asset,
)
from .depreciation import (
    _fully_depreciated, _month_index, _sequence_ok, discard_drafts, draft_lines, post_depreciation, propose, run_depreciation, suggest_period,
)
from .disposal import (
    dispose_asset,
)
from .files import _attach_root, _remove_file
from .attachments import (
    add_attachment, delete_attachment, get_attachment,
)
from .inquiries import (
    audit_log, journal, transactions,
)
from .dashboard import (
    dashboard,
)
from .maintenance import (
    MAINT_PRIORITIES, MAINT_SQL, MAINT_STATUSES, MAINT_TYPES, _clean_maint, _maint_flags, _next_maint_no, _release_asset, _set_asset_status, _vendor, delete_maintenance, get_maintenance, list_maintenance, maintenance_action, save_maintenance,
)
from .suppliers import (
    SUPPLIER_FIELDS, SUPPLIER_LIST_SQL, SUPPLIER_TYPES, _next_supplier_code, delete_supplier, get_supplier, list_suppliers, next_supplier_code, save_supplier,
)
from .backup import (
    BACKUP_RE, _backup_root, _put_setting, _slots, backup_path, backup_schedule, create_backup, list_backups, open_backup_folder, run_due_backup,
)
from .employees import (
    EMPLOYEE_FIELDS, EMPLOYEE_LIST_SQL, delete_employee, get_employee, list_employees, next_employee_code, save_employee,
)
from .custody import (
    CUSTODY_SQL, _next_custody_no, add_custody_attachment, delete_custody, get_custody, issue_custody, list_custody, return_custody, update_custody,
)

__all__ = [
    "ASSET_STATUSES",
    "ApiError",
    "MONTHS_AR",
    "USER",
    "_ctx",
    "actor",
    "audit",
    "localize",
    "month_ar",
    "now",
    "num",
    "one",
    "parse_date",
    "r2",
    "rows",
    "set_actor",
    "set_lang",
    "to_int",
    "_master",
    "get_settings",
    "lookups",
    "master_delete",
    "master_list",
    "master_save",
    "save_settings",
    "generate_periods",
    "period_for_date",
    "set_period_status",
    "ASSET_FIELDS",
    "BOOK_SQL",
    "_clean_asset",
    "_with_nbv",
    "change_status",
    "delete_asset",
    "get_asset",
    "list_assets",
    "next_asset_code",
    "save_asset",
    "transfer_asset",
    "_fully_depreciated",
    "_month_index",
    "_sequence_ok",
    "discard_drafts",
    "draft_lines",
    "post_depreciation",
    "propose",
    "run_depreciation",
    "suggest_period",
    "dispose_asset",
    "_attach_root",
    "_remove_file",
    "add_attachment",
    "delete_attachment",
    "get_attachment",
    "audit_log",
    "journal",
    "transactions",
    "dashboard",
    "MAINT_PRIORITIES",
    "MAINT_SQL",
    "MAINT_STATUSES",
    "MAINT_TYPES",
    "_clean_maint",
    "_maint_flags",
    "_next_maint_no",
    "_release_asset",
    "_set_asset_status",
    "_vendor",
    "delete_maintenance",
    "get_maintenance",
    "list_maintenance",
    "maintenance_action",
    "save_maintenance",
    "SUPPLIER_FIELDS",
    "SUPPLIER_LIST_SQL",
    "SUPPLIER_TYPES",
    "_next_supplier_code",
    "delete_supplier",
    "get_supplier",
    "list_suppliers",
    "next_supplier_code",
    "save_supplier",
    "BACKUP_RE",
    "_backup_root",
    "_put_setting",
    "_slots",
    "backup_path",
    "backup_schedule",
    "create_backup",
    "list_backups",
    "open_backup_folder",
    "run_due_backup",
    "EMPLOYEE_FIELDS",
    "EMPLOYEE_LIST_SQL",
    "delete_employee",
    "get_employee",
    "list_employees",
    "next_employee_code",
    "save_employee",
    "CUSTODY_SQL",
    "_next_custody_no",
    "add_custody_attachment",
    "delete_custody",
    "get_custody",
    "issue_custody",
    "list_custody",
    "return_custody",
    "update_custody",
    "db",
]
