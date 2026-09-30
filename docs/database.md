# Database

SQLite file `data/gooya_asset.db` (the file name is kept from the original Access project so existing installations continue to work).
WAL mode, `PRAGMA foreign_keys=ON`. `db.init_db()` runs at every start and is idempotent: it creates missing tables, adds missing
columns (`ALTER TABLE`), and seeds groups, ledger accounts, methods, currencies, periods, settings and the four standard roles.

## Tables

### Master data
| Table | Content |
|---|---|
| `tbl_AssetCategories` | fixed asset groups: code, name (+`Ar`), default life/rate/method, ledger accounts (asset, accumulated depreciation, expense, gain, loss) |
| `tbl_Locations`, `tbl_CostCenters` | locations and cost centers (code, name, name `Ar`, active) |
| `tbl_DepreciationMethods` | `SL` straight line, `NONE` no depreciation |
| `tbl_GLAccounts` | ledger accounts (`FIXED ASSET`, `ACCUMULATED DEPRECIATION`, expense, gain/loss, clearing) |
| `tbl_Currencies` | currency code, name, symbol |
| `tbl_Settings` | key/value settings (company, VAT, fiscal year, asset code prefix, backup schedule and results, folders) |

### Assets and transactions
| Table | Content |
|---|---|
| `tbl_Assets` | the register: code `AssetCode`, names, group, dates (acquisition, in service, depreciation start, disposal), cost (net), residual, life, rate, method, opening accumulated depreciation, location/cost center, supplier, invoice/PO, serial/model/manufacturer, warranty, VAT fields (`VatApplicable`, `VatInclusive`, `VatRate`, `PurchaseAmount`, `VatAmount`), status |
| `tbl_AssetTransactions` | `ACQUISITION`, `TRANSFER`, `STATUS`, `DISPOSAL` with from/to location and cost center, amounts, reference |
| `tbl_AssetAttachments` | files attached to an asset (or to a custody record via `CustodyID`): title, type, name, extension, path on disk |

### Depreciation
| Table | Content |
|---|---|
| `tbl_DepreciationPeriods` | monthly periods per fiscal year: `OPEN` / `CLOSED` |
| `tbl_Depreciation` | one row per asset and period: opening/closing accumulated depreciation, period amount, `DRAFT` or `POSTED` |
| `tbl_DepreciationJournal` | posted ledger lines (`DEPRECIATION` and `DISPOSAL` types): account, debit, credit, reference, description |

### Contacts and operations
| Table | Content |
|---|---|
| `tbl_Suppliers` | suppliers, manufacturers, maintenance and service providers (contact, tax number, address, active) |
| `tbl_Employees` | employees (code, name, job title, department, phones, e-mail, national ID, hire date, active) |
| `tbl_AssetCustody` | custody records `CU-nnnn`: asset, employee, issue/return dates, condition and accessories, `Issued` / `Returned` |
| `tbl_Maintenance` | maintenance orders `MO-nnnn`: type, priority, status, dates, vendor/supplier, cost, next due date, out-of-service flag |

### Security and audit
| Table | Content |
|---|---|
| `tbl_Users` | user name, PBKDF2 hash, role, language/theme, failed attempts and lock time, must-change-password |
| `tbl_Roles`, `tbl_RolePermissions` | roles and the permission keys granted to each |
| `tbl_Sessions` | hashed session tokens with creation, last seen and expiry |
| `tbl_AuditLog` | date, user, action, entity, id, details (every create, update, delete, post, dispose, sign-in event) |

## Accounting entries

All amounts use the asset's **net** cost.

| Event | Debit | Credit |
|---|---|---|
| Posting monthly depreciation | Depreciation expense (group account) | Accumulated depreciation (group account) |
| Disposal — accumulated depreciation to date | Accumulated depreciation | — |
| Disposal — cost removed | — | Asset (group account) |
| Disposal — sale proceeds (if any) | Disposal clearing account (Settings) | — |
| Disposal — net book value below proceeds | — | Gain on disposal |
| Disposal — net book value above proceeds | Loss on disposal | — |

Acquisition itself creates no ledger entry (it is an `ACQUISITION` transaction only); the purchase is expected to be booked in
purchasing/payables.

## Files on disk

- Attachments: `<attachment root>/<group>/<year-month>/<asset code>/<asset code>_<purchase date>[_n].<ext>`; the root defaults to
  `attachments/` and can be changed in Settings > Backup. Empty folders are removed when the last file is deleted.
- Backups: `<backup folder>/Usool_backup_YYYY-MM-DD_HHMMSS.zip` (manual) or `Usool_auto_…zip` (scheduled); each holds a consistent
  snapshot of the database plus all attachment files. Restore with `tools/restore_backup.py` (see development.md).
