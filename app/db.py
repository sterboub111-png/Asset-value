"""Usool - storage layer: schema, connection, upgrades, Access migration, and a portable copy of all data.

The database is PostgreSQL when a URL is configured (the USOOL_DATABASE_URL environment variable, or the first line of
data/database.url), otherwise the SQLite file data/gooya_asset.db. The services write one SQL for both; on PostgreSQL
app/dbpg.py adapts it (quoted CamelCase names, placeholders, identity keys).
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "gooya_asset.db"
EXPORT_PATH = DATA_DIR / "access_export.json"
URL_FILE = DATA_DIR / "database.url"


def _configured_url() -> str | None:
    url = os.environ.get("USOOL_DATABASE_URL", "").strip()
    if not url and URL_FILE.exists():
        url = URL_FILE.read_text(encoding="utf-8").strip().splitlines()[0].strip() if URL_FILE.read_text(encoding="utf-8").strip() else ""
    return url or None


URL: str | None = _configured_url()   # tests and tools may set it; None = SQLite at DB_PATH


def is_pg() -> bool:
    return bool(URL and URL.startswith(("postgresql://", "postgres://")))


def describe() -> str:
    """Where the data lives, for the start-up message (the password is never shown)."""
    return re.sub(r"//([^:/@]+):[^@]+@", r"//\1:***@", URL) if is_pg() else str(DB_PATH)

SCHEMA = """
CREATE TABLE IF NOT EXISTS tbl_DepreciationMethods(
  MethodID INTEGER PRIMARY KEY AUTOINCREMENT,
  MethodCode TEXT NOT NULL UNIQUE, MethodName TEXT NOT NULL, MethodNameAr TEXT, IsActive INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS tbl_GLAccounts(
  GLAccountID INTEGER PRIMARY KEY AUTOINCREMENT,
  AccountCode TEXT NOT NULL UNIQUE, AccountName TEXT NOT NULL, AccountNameAr TEXT, AccountType TEXT, IsActive INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS tbl_Locations(
  LocationID INTEGER PRIMARY KEY AUTOINCREMENT,
  LocationCode TEXT NOT NULL UNIQUE, LocationName TEXT NOT NULL, LocationNameAr TEXT, IsActive INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS tbl_CostCenters(
  CostCenterID INTEGER PRIMARY KEY AUTOINCREMENT,
  CostCenterCode TEXT NOT NULL UNIQUE, CostCenterName TEXT NOT NULL, CostCenterNameAr TEXT, IsActive INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS tbl_AssetCategories(
  CategoryID INTEGER PRIMARY KEY AUTOINCREMENT,
  CategoryCode TEXT NOT NULL UNIQUE, CategoryName TEXT NOT NULL, CategoryNameAr TEXT,
  UsefulLifeYears REAL, DepreciationRate REAL,
  MethodID INTEGER REFERENCES tbl_DepreciationMethods(MethodID),
  AssetAccountID INTEGER REFERENCES tbl_GLAccounts(GLAccountID),
  AccumDepAccountID INTEGER REFERENCES tbl_GLAccounts(GLAccountID),
  DepExpenseAccountID INTEGER REFERENCES tbl_GLAccounts(GLAccountID),
  GainAccountID INTEGER REFERENCES tbl_GLAccounts(GLAccountID),
  LossAccountID INTEGER REFERENCES tbl_GLAccounts(GLAccountID),
  IsActive INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS tbl_Assets(
  AssetID INTEGER PRIMARY KEY AUTOINCREMENT,
  AssetCode TEXT NOT NULL UNIQUE, AssetName TEXT NOT NULL, AssetNameAr TEXT, AssetDescription TEXT,
  CategoryID INTEGER NOT NULL REFERENCES tbl_AssetCategories(CategoryID),
  AssetStatus TEXT NOT NULL DEFAULT 'Active',
  AcquisitionDate TEXT NOT NULL, InServiceDate TEXT, DepreciationStartDate TEXT,
  AcquisitionCost REAL NOT NULL DEFAULT 0, ResidualValue REAL NOT NULL DEFAULT 0,
  VatApplicable INTEGER NOT NULL DEFAULT 0, VatInclusive INTEGER NOT NULL DEFAULT 0, VatRate REAL, PurchaseAmount REAL, VatAmount REAL NOT NULL DEFAULT 0,
  UsefulLifeYears REAL, DepreciationRate REAL,
  MethodID INTEGER REFERENCES tbl_DepreciationMethods(MethodID),
  OpeningAccumDep REAL NOT NULL DEFAULT 0, OpeningNBV REAL,
  LocationID INTEGER REFERENCES tbl_Locations(LocationID),
  CostCenterID INTEGER REFERENCES tbl_CostCenters(CostCenterID),
  ResponsiblePerson TEXT,
  SupplierName TEXT, SupplierID INTEGER, InvoiceNumber TEXT, PurchaseOrderNumber TEXT,
  SerialNumber TEXT, ModelNumber TEXT, Manufacturer TEXT, WarrantyExpiryDate TEXT,
  DisposalDate TEXT, Notes TEXT,
  IsActive INTEGER NOT NULL DEFAULT 1,
  CreatedAt TEXT, CreatedBy TEXT, ModifiedAt TEXT, ModifiedBy TEXT);
CREATE TABLE IF NOT EXISTS tbl_DepreciationPeriods(
  PeriodID INTEGER PRIMARY KEY AUTOINCREMENT,
  FiscalYear INTEGER NOT NULL, PeriodNumber INTEGER NOT NULL, PeriodName TEXT NOT NULL,
  StartDate TEXT NOT NULL, EndDate TEXT NOT NULL,
  PeriodStatus TEXT NOT NULL DEFAULT 'OPEN',
  CreatedAt TEXT, CreatedBy TEXT, UNIQUE(FiscalYear, PeriodNumber));
CREATE TABLE IF NOT EXISTS tbl_Depreciation(
  DepreciationID INTEGER PRIMARY KEY AUTOINCREMENT,
  AssetID INTEGER NOT NULL REFERENCES tbl_Assets(AssetID),
  PeriodID INTEGER NOT NULL REFERENCES tbl_DepreciationPeriods(PeriodID),
  AcquisitionCost REAL, ResidualValue REAL, DepreciableAmount REAL,
  UsefulLifeYears REAL, DepreciationRate REAL,
  OpeningAccumDep REAL, OpeningNBV REAL, PeriodDepreciation REAL,
  ClosingAccumDep REAL, ClosingNBV REAL,
  PostingStatus TEXT NOT NULL DEFAULT 'DRAFT',
  PostedAt TEXT, PostedBy TEXT, CreatedAt TEXT, CreatedBy TEXT,
  UNIQUE(AssetID, PeriodID));
CREATE TABLE IF NOT EXISTS tbl_AssetTransactions(
  TransactionID INTEGER PRIMARY KEY AUTOINCREMENT,
  AssetID INTEGER NOT NULL REFERENCES tbl_Assets(AssetID),
  TransactionType TEXT NOT NULL, TransactionDate TEXT NOT NULL,
  Amount REAL, DisposalProceeds REAL, DisposalReason TEXT,
  FromLocationID INTEGER, ToLocationID INTEGER,
  FromCostCenterID INTEGER, ToCostCenterID INTEGER,
  ReferenceNumber TEXT, Notes TEXT, CreatedAt TEXT, CreatedBy TEXT);
CREATE TABLE IF NOT EXISTS tbl_DepreciationJournal(
  JournalID INTEGER PRIMARY KEY AUTOINCREMENT,
  DepreciationID INTEGER REFERENCES tbl_Depreciation(DepreciationID),
  TransactionID INTEGER REFERENCES tbl_AssetTransactions(TransactionID),
  AssetID INTEGER REFERENCES tbl_Assets(AssetID),
  PeriodID INTEGER REFERENCES tbl_DepreciationPeriods(PeriodID),
  JournalDate TEXT, GLAccountID INTEGER REFERENCES tbl_GLAccounts(GLAccountID),
  DebitAmount REAL NOT NULL DEFAULT 0, CreditAmount REAL NOT NULL DEFAULT 0,
  JournalType TEXT, Reference TEXT, Description TEXT,
  PostingStatus TEXT, PostedAt TEXT, PostedBy TEXT, CreatedAt TEXT);
CREATE TABLE IF NOT EXISTS tbl_AssetAttachments(
  AttachmentID INTEGER PRIMARY KEY AUTOINCREMENT,
  AssetID INTEGER NOT NULL REFERENCES tbl_Assets(AssetID),
  CustodyID INTEGER, DocumentTitle TEXT, DocumentType TEXT, FileName TEXT, FileExtension TEXT, FilePath TEXT,
  Notes TEXT, CreatedAt TEXT, CreatedBy TEXT);
CREATE TABLE IF NOT EXISTS tbl_Settings(
  SettingID INTEGER PRIMARY KEY AUTOINCREMENT,
  SettingKey TEXT NOT NULL UNIQUE, SettingValue TEXT, SettingDescription TEXT,
  IsActive INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS tbl_Roles(
  RoleID INTEGER PRIMARY KEY AUTOINCREMENT,
  RoleName TEXT NOT NULL UNIQUE, RoleNameAr TEXT, Description TEXT, IsSystem INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS tbl_RolePermissions(
  RoleID INTEGER NOT NULL REFERENCES tbl_Roles(RoleID), Permission TEXT NOT NULL, PRIMARY KEY(RoleID, Permission));
CREATE TABLE IF NOT EXISTS tbl_Users(
  UserID INTEGER PRIMARY KEY AUTOINCREMENT,
  UserName TEXT NOT NULL UNIQUE COLLATE NOCASE, FullName TEXT NOT NULL, FullNameAr TEXT, Email TEXT, Phone TEXT,
  PasswordHash TEXT NOT NULL, RoleID INTEGER NOT NULL REFERENCES tbl_Roles(RoleID),
  IsActive INTEGER NOT NULL DEFAULT 1, MustChangePassword INTEGER NOT NULL DEFAULT 0, Language TEXT, Theme TEXT,
  LastLogin TEXT, FailedAttempts INTEGER NOT NULL DEFAULT 0, LockedUntil TEXT, CreatedAt TEXT, CreatedBy TEXT);
CREATE TABLE IF NOT EXISTS tbl_Sessions(
  TokenHash TEXT PRIMARY KEY, UserID INTEGER NOT NULL REFERENCES tbl_Users(UserID),
  CreatedAt TEXT NOT NULL, LastSeen TEXT NOT NULL, ExpiresAt TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS ix_sessions_user ON tbl_Sessions(UserID);
CREATE TABLE IF NOT EXISTS tbl_Currencies(
  CurrencyID INTEGER PRIMARY KEY AUTOINCREMENT,
  CurrencyCode TEXT NOT NULL UNIQUE, CurrencyName TEXT NOT NULL, CurrencyNameAr TEXT, Symbol TEXT,
  IsActive INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS tbl_Employees(
  EmployeeID INTEGER PRIMARY KEY AUTOINCREMENT,
  EmployeeCode TEXT NOT NULL UNIQUE,
  EmployeeName TEXT NOT NULL, EmployeeNameAr TEXT,
  JobTitle TEXT, Department TEXT, Phone TEXT, Mobile TEXT, Email TEXT, NationalID TEXT, HireDate TEXT,
  Notes TEXT, IsActive INTEGER NOT NULL DEFAULT 1,
  CreatedAt TEXT, CreatedBy TEXT, ModifiedAt TEXT, ModifiedBy TEXT);
CREATE TABLE IF NOT EXISTS tbl_AssetCustody(
  CustodyID INTEGER PRIMARY KEY AUTOINCREMENT,
  CustodyNo TEXT NOT NULL UNIQUE,
  AssetID INTEGER NOT NULL REFERENCES tbl_Assets(AssetID),
  EmployeeID INTEGER NOT NULL REFERENCES tbl_Employees(EmployeeID),
  IssueDate TEXT NOT NULL, ReturnDate TEXT,
  Status TEXT NOT NULL DEFAULT 'Issued',
  ConditionOnIssue TEXT, ConditionOnReturn TEXT, Accessories TEXT, Notes TEXT, ReturnNotes TEXT, IssuedBy TEXT,
  CreatedAt TEXT, CreatedBy TEXT, ModifiedAt TEXT, ModifiedBy TEXT);
CREATE UNIQUE INDEX IF NOT EXISTS ix_custody_active ON tbl_AssetCustody(AssetID) WHERE Status='Issued';
CREATE INDEX IF NOT EXISTS ix_custody_emp ON tbl_AssetCustody(EmployeeID);
CREATE TABLE IF NOT EXISTS tbl_Suppliers(
  SupplierID INTEGER PRIMARY KEY AUTOINCREMENT,
  SupplierCode TEXT NOT NULL UNIQUE,
  SupplierName TEXT NOT NULL, SupplierNameAr TEXT,
  SupplierType TEXT NOT NULL DEFAULT 'Supplier',
  ContactPerson TEXT, Phone TEXT, Mobile TEXT, Email TEXT, Website TEXT,
  Address TEXT, City TEXT, Country TEXT,
  TaxNumber TEXT, CRNumber TEXT, PaymentTerms TEXT, BankName TEXT, IBAN TEXT,
  Notes TEXT, IsActive INTEGER NOT NULL DEFAULT 1,
  CreatedAt TEXT, CreatedBy TEXT, ModifiedAt TEXT, ModifiedBy TEXT);
CREATE TABLE IF NOT EXISTS tbl_Maintenance(
  MaintenanceID INTEGER PRIMARY KEY AUTOINCREMENT,
  MaintenanceNo TEXT NOT NULL UNIQUE,
  AssetID INTEGER NOT NULL REFERENCES tbl_Assets(AssetID),
  MaintenanceType TEXT NOT NULL DEFAULT 'Corrective',
  Title TEXT NOT NULL, Description TEXT,
  Priority TEXT NOT NULL DEFAULT 'Medium',
  Status TEXT NOT NULL DEFAULT 'Planned',
  ScheduledDate TEXT NOT NULL, StartDate TEXT, CompletionDate TEXT, NextDueDate TEXT,
  OutOfService INTEGER NOT NULL DEFAULT 0,
  Vendor TEXT, SupplierID INTEGER, PerformedBy TEXT, InvoiceNumber TEXT, Cost REAL NOT NULL DEFAULT 0,
  Notes TEXT, CreatedAt TEXT, CreatedBy TEXT, ModifiedAt TEXT, ModifiedBy TEXT);
CREATE INDEX IF NOT EXISTS ix_mt_asset ON tbl_Maintenance(AssetID);
CREATE INDEX IF NOT EXISTS ix_mt_status ON tbl_Maintenance(Status);
CREATE TABLE IF NOT EXISTS tbl_AssetCounts(
  CountID INTEGER PRIMARY KEY AUTOINCREMENT,
  CountNo TEXT NOT NULL UNIQUE, Title TEXT NOT NULL, CountDate TEXT NOT NULL,
  LocationID INTEGER REFERENCES tbl_Locations(LocationID),
  Status TEXT NOT NULL DEFAULT 'Open', Notes TEXT,
  CreatedAt TEXT, CreatedBy TEXT, ClosedAt TEXT, ClosedBy TEXT);
CREATE TABLE IF NOT EXISTS tbl_AssetCountLines(
  LineID INTEGER PRIMARY KEY AUTOINCREMENT,
  CountID INTEGER NOT NULL REFERENCES tbl_AssetCounts(CountID),
  AssetID INTEGER REFERENCES tbl_Assets(AssetID),
  ScannedCode TEXT, Expected INTEGER NOT NULL DEFAULT 0, Found INTEGER NOT NULL DEFAULT 0,
  FoundLocationID INTEGER REFERENCES tbl_Locations(LocationID), FoundAt TEXT, FoundBy TEXT, Notes TEXT);
CREATE UNIQUE INDEX IF NOT EXISTS ix_countline_asset ON tbl_AssetCountLines(CountID, AssetID) WHERE AssetID IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_countline_count ON tbl_AssetCountLines(CountID);
CREATE TABLE IF NOT EXISTS tbl_Branches(
  BranchID INTEGER PRIMARY KEY AUTOINCREMENT,
  BranchCode TEXT NOT NULL UNIQUE, BranchName TEXT NOT NULL, BranchNameAr TEXT,
  CountryCode TEXT NOT NULL, City TEXT, Region TEXT, IsActive INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS tbl_UserBranches(
  UserID INTEGER NOT NULL REFERENCES tbl_Users(UserID) ON DELETE CASCADE,
  BranchID INTEGER NOT NULL REFERENCES tbl_Branches(BranchID), PRIMARY KEY(UserID, BranchID));
CREATE TABLE IF NOT EXISTS tbl_AuditLog(
  LogID INTEGER PRIMARY KEY AUTOINCREMENT,
  LogDate TEXT NOT NULL, UserName TEXT, Action TEXT, Entity TEXT, EntityID TEXT, Details TEXT);
CREATE INDEX IF NOT EXISTS ix_dep_asset ON tbl_Depreciation(AssetID);
CREATE INDEX IF NOT EXISTS ix_dep_period ON tbl_Depreciation(PeriodID);
CREATE INDEX IF NOT EXISTS ix_tx_asset ON tbl_AssetTransactions(AssetID);
CREATE INDEX IF NOT EXISTS ix_jr_period ON tbl_DepreciationJournal(PeriodID);
"""

DEFAULT_SETTINGS = [
    ("CompanyName", "", "Company legal name"),
    ("AssetCodePrefix", "FA", "Fixed asset code prefix"),
    ("FiscalYearStartMonth", "1", "Fiscal year starting month"),
    ("DefaultCurrency", "SAR", "Default reporting currency"),
    ("DepreciationFrequency", "MONTHLY", "Default depreciation frequency"),
    ("DepreciationStartRule", "IN_SERVICE_DATE", "Depreciation start rule"),
    ("AttachmentFolder", "", "Root folder for asset attachments"),
    ("DisposalClearingAccountID", "", "GL account that receives disposal proceeds"),
    ("ImpairmentAccountID", "", "GL account for impairment losses and their reversals"),
    ("RevaluationSurplusAccountID", "", "GL account (equity) for the revaluation surplus"),
    ("BackupFolder", "", "Folder where backups are written"),
    ("VATEnabled", "1", "Track value added tax on purchases"),
    ("VATRate", "15", "Standard VAT rate (%)"),
    ("VATDefaultApplicable", "1", "New assets are purchased with VAT by default"),
    ("VATDefaultInclusive", "0", "Invoice amounts include VAT by default"),
    ("VATNumber", "", "Company VAT registration number"),
    ("BackupSchedule", "OFF", "Automatic backup frequency: OFF, DAILY, WEEKLY, MONTHLY, QUARTERLY"),
    ("BackupTime", "02:00", "Automatic backup time (HH:MM)"),
    ("BackupWeekday", "0", "Weekly backups: 0=Monday ... 6=Sunday"),
    ("BackupDayOfMonth", "1", "Monthly / quarterly backups: day of month (1-28)"),
    ("BackupKeep", "30", "Automatic backups to keep (0 = keep all)"),
    ("BackupLastRun", "", "Last successful automatic backup"),
    ("BackupLastAttempt", "", "Last automatic backup attempt"),
    ("BackupLastResult", "", "Result of the last automatic backup"),
]


_PKS: dict[str, str] | None = None


def primary_keys() -> dict[str, str]:
    """table -> its auto-numbered key, read from the schema."""
    global _PKS
    if _PKS is None:
        _PKS = dict(re.findall(r"CREATE TABLE IF NOT EXISTS (\w+)\(\s*(\w+) INTEGER PRIMARY KEY AUTOINCREMENT", SCHEMA))
    return _PKS


try:
    from . import dbpg as _pg
    IntegrityError: tuple = (sqlite3.IntegrityError, _pg.IntegrityError)
    DatabaseError: tuple = (sqlite3.Error, _pg.Error)
except ImportError:   # the PostgreSQL driver is only needed when PostgreSQL is configured
    _pg = None
    IntegrityError = (sqlite3.IntegrityError,)
    DatabaseError = (sqlite3.Error,)


def connect():
    if is_pg():
        if _pg is None:
            raise RuntimeError("PostgreSQL is configured but the driver is missing: pip install \"psycopg[binary]\" (see requirements.txt)")
        return _pg.Connection(URL, primary_keys())
    DATA_DIR.mkdir(exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("PRAGMA journal_mode=WAL")
    return con


ARABIC_COLUMNS = [("tbl_Assets", "AssetNameAr"), ("tbl_AssetCategories", "CategoryNameAr"), ("tbl_Locations", "LocationNameAr"),
                  ("tbl_CostCenters", "CostCenterNameAr"), ("tbl_GLAccounts", "AccountNameAr"), ("tbl_DepreciationMethods", "MethodNameAr")]

CATEGORY_AR = {"Furniture & Fixtures": "الأثاث والتجهيزات", "Kitchen Equipment": "معدات المطبخ", "Computers & IT Equipment": "أجهزة الحاسب وتقنية المعلومات",
               "POS Equipment": "أجهزة نقاط البيع", "Vehicles": "المركبات", "Office Equipment": "المعدات المكتبية", "HVAC Equipment": "معدات التكييف والتبريد",
               "Electrical Equipment": "المعدات الكهربائية", "Security Equipment": "معدات الأمن والسلامة", "Leasehold Improvements": "تحسينات المباني المستأجرة"}
METHOD_AR = {"Straight Line": "القسط الثابت", "No Depreciation": "بدون إهلاك"}


def _seed_arabic(con) -> None:
    """Fill Arabic names for the stock chart of accounts / groups when still empty."""
    for en, ar in CATEGORY_AR.items():
        con.execute("UPDATE tbl_AssetCategories SET CategoryNameAr=? WHERE CategoryName=? AND CategoryNameAr IS NULL", (ar, en))
        con.execute("UPDATE tbl_GLAccounts SET AccountNameAr=? WHERE AccountName=? AND AccountNameAr IS NULL", (ar, en))
        con.execute("UPDATE tbl_GLAccounts SET AccountNameAr=? WHERE AccountName=? AND AccountNameAr IS NULL", ("مجمع إهلاك - " + ar, "Accum. Dep. - " + en))
        con.execute("UPDATE tbl_GLAccounts SET AccountNameAr=? WHERE AccountName=? AND AccountNameAr IS NULL", ("مصروف إهلاك - " + ar, "Dep. Expense - " + en))
    for en, ar in METHOD_AR.items():
        con.execute("UPDATE tbl_DepreciationMethods SET MethodNameAr=? WHERE MethodName=? AND MethodNameAr IS NULL", (ar, en))
    for en, ar in {"Gain on Disposal of Fixed Assets": "أرباح استبعاد الأصول الثابتة", "Loss on Disposal of Fixed Assets": "خسائر استبعاد الأصول الثابتة",
                   "Fixed Asset Disposal Clearing": "حساب وسيط استبعاد الأصول الثابتة"}.items():
        con.execute("UPDATE tbl_GLAccounts SET AccountNameAr=? WHERE AccountName=? AND AccountNameAr IS NULL", (ar, en))


def _seed_valuation(con) -> None:
    """Declining balance, and the accounts revaluations and impairments post to (created once, only when not set yet)."""
    if not con.execute("SELECT 1 FROM tbl_GLAccounts LIMIT 1").fetchone():
        return   # an empty database (first run, before the Access export is loaded)
    con.execute("INSERT INTO tbl_DepreciationMethods(MethodCode,MethodName,MethodNameAr) SELECT 'DB','Declining Balance','القسط المتناقص' "
                "WHERE NOT EXISTS (SELECT 1 FROM tbl_DepreciationMethods WHERE MethodCode='DB')")
    for key, code, name, name_ar, kind in (("ImpairmentAccountID", "620102", "Impairment Loss on Fixed Assets", "خسائر الانخفاض في قيمة الأصول الثابتة", "OTHER EXPENSE"),
                                           ("RevaluationSurplusAccountID", "330101", "Revaluation Surplus", "فائض إعادة التقييم", "EQUITY")):
        cur = con.execute("SELECT SettingValue FROM tbl_Settings WHERE SettingKey=?", (key,)).fetchone()
        if cur and cur[0]:
            continue
        con.execute("INSERT INTO tbl_GLAccounts(AccountCode,AccountName,AccountNameAr,AccountType) SELECT ?,?,?,? "
                    "WHERE NOT EXISTS (SELECT 1 FROM tbl_GLAccounts WHERE AccountCode=?)", (code, name, name_ar, kind, code))
        gid = con.execute("SELECT GLAccountID FROM tbl_GLAccounts WHERE AccountCode=?", (code,)).fetchone()[0]
        con.execute("UPDATE tbl_Settings SET SettingValue=? WHERE SettingKey=?", (str(gid), key))


CURRENCIES = [
    ("SAR", "Saudi Riyal", "ريال سعودي", "SAR"), ("USD", "US Dollar", "دولار أمريكي", "$"), ("EUR", "Euro", "يورو", "€"),
    ("GBP", "British Pound", "جنيه إسترليني", "£"), ("AED", "UAE Dirham", "درهم إماراتي", "AED"), ("KWD", "Kuwaiti Dinar", "دينار كويتي", "KWD"),
    ("BHD", "Bahraini Dinar", "دينار بحريني", "BHD"), ("OMR", "Omani Rial", "ريال عماني", "OMR"), ("QAR", "Qatari Riyal", "ريال قطري", "QAR"),
    ("EGP", "Egyptian Pound", "جنيه مصري", "EGP"), ("JOD", "Jordanian Dinar", "دينار أردني", "JOD"), ("LBP", "Lebanese Pound", "ليرة لبنانية", "LBP"),
    ("IQD", "Iraqi Dinar", "دينار عراقي", "IQD"), ("MAD", "Moroccan Dirham", "درهم مغربي", "MAD"), ("TND", "Tunisian Dinar", "دينار تونسي", "TND"),
    ("TRY", "Turkish Lira", "ليرة تركية", "TRY"), ("INR", "Indian Rupee", "روبية هندية", "INR"), ("PKR", "Pakistani Rupee", "روبية باكستانية", "PKR"),
    ("CNY", "Chinese Yuan", "يوان صيني", "CNY"), ("JPY", "Japanese Yen", "ين ياباني", "JPY"), ("CHF", "Swiss Franc", "فرنك سويسري", "CHF"),
    ("CAD", "Canadian Dollar", "دولار كندي", "CAD"), ("AUD", "Australian Dollar", "دولار أسترالي", "AUD"),
]


def _now() -> str:
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def bulk_insert(con, table: str, cols: list[str], rows: list) -> None:
    """Insert many rows: COPY on PostgreSQL, executemany on SQLite."""
    if not rows:
        return
    if is_pg():
        con.bulk_insert(table, cols, rows)
    else:
        con.executemany(f"INSERT INTO {table}({','.join(cols)}) VALUES({','.join('?' * len(cols))})", rows)


def table_columns(con, table: str) -> list[str]:
    if is_pg():
        return _pg.columns(con, table)
    return [r["name"] for r in con.execute(f"PRAGMA table_info({table})")]


def init_db() -> None:
    con = connect()
    if is_pg():   # ROUND(x, 2) on a double, as SQLite allows it
        con._con.execute("""CREATE OR REPLACE FUNCTION round(double precision, integer) RETURNS double precision
            AS 'SELECT round($1::numeric, $2)::double precision' LANGUAGE sql IMMUTABLE""")
    con.executescript(SCHEMA)
    for table, col, ctype in [(t, c, "TEXT") for t, c in ARABIC_COLUMNS] + [("tbl_Assets", "SupplierID", "INTEGER"), ("tbl_Maintenance", "SupplierID", "INTEGER"),
                                                 ("tbl_Assets", "VatApplicable", "INTEGER NOT NULL DEFAULT 0"), ("tbl_Assets", "VatInclusive", "INTEGER NOT NULL DEFAULT 0"),
                                                 ("tbl_AssetAttachments", "CustodyID", "INTEGER"), ("tbl_Assets", "VatRate", "REAL"), ("tbl_Assets", "PurchaseAmount", "REAL"), ("tbl_Assets", "VatAmount", "REAL NOT NULL DEFAULT 0"),
                                                 ("tbl_Locations", "BranchID", "INTEGER REFERENCES tbl_Branches(BranchID)"),
                                                 ("tbl_AssetTransactions", "PnlAmount", "REAL"), ("tbl_AssetTransactions", "SurplusAmount", "REAL")]:
        # upgrade databases created before these columns existed
        if col not in table_columns(con, table):
            con.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ctype}")
    # indexes for a large register (hundreds of locations, tens of thousands of assets)
    con.executescript("""
CREATE INDEX IF NOT EXISTS ix_loc_branch ON tbl_Locations(BranchID);
CREATE INDEX IF NOT EXISTS ix_assets_location ON tbl_Assets(LocationID);
CREATE INDEX IF NOT EXISTS ix_assets_category ON tbl_Assets(CategoryID);
CREATE INDEX IF NOT EXISTS ix_assets_status ON tbl_Assets(AssetStatus);
CREATE INDEX IF NOT EXISTS ix_tx_type_date ON tbl_AssetTransactions(TransactionType, TransactionDate);
CREATE INDEX IF NOT EXISTS ix_jr_dep ON tbl_DepreciationJournal(DepreciationID);
CREATE INDEX IF NOT EXISTS ix_jr_tx ON tbl_DepreciationJournal(TransactionID);
CREATE INDEX IF NOT EXISTS ix_jr_date ON tbl_DepreciationJournal(JournalDate);
CREATE INDEX IF NOT EXISTS ix_dep_status ON tbl_Depreciation(PostingStatus, AssetID);
CREATE UNIQUE INDEX IF NOT EXISTS ix_users_name_ci ON tbl_Users(lower(UserName));
""")
    _seed_arabic(con)
    con.execute("UPDATE tbl_Assets SET PurchaseAmount=AcquisitionCost WHERE PurchaseAmount IS NULL")
    # only insert what is missing (INSERT OR IGNORE still advances the AUTOINCREMENT counter on every start)
    for code, en, ar, sym in CURRENCIES:
        con.execute("INSERT INTO tbl_Currencies(CurrencyCode,CurrencyName,CurrencyNameAr,Symbol) "
                    "SELECT ?,?,?,? WHERE NOT EXISTS (SELECT 1 FROM tbl_Currencies WHERE CurrencyCode=?)", (code, en, ar, sym, code))
    for key, val, desc in DEFAULT_SETTINGS:
        con.execute("INSERT INTO tbl_Settings(SettingKey,SettingValue,SettingDescription) "
                    "SELECT ?,?,? WHERE NOT EXISTS (SELECT 1 FROM tbl_Settings WHERE SettingKey=?)", (key, val, desc, key))
    _seed_valuation(con)
    if is_pg():
        _pg.reset_sequences(con, primary_keys())
    else:
        for t, pk in (("tbl_Settings", "SettingID"), ("tbl_Currencies", "CurrencyID")):  # one-off tidy of counters that already ran ahead
            con.execute("UPDATE sqlite_sequence SET seq=(SELECT COALESCE(MAX(%s),0) FROM %s) WHERE name=?" % (pk, t), (t,))
    con.commit()
    from . import auth  # default roles (imported here to avoid a circular import at load time)
    auth.seed(con)
    con.close()


def _date(v):
    return v[:10] if v else None


def migrate_from_access(export: Path = EXPORT_PATH) -> dict:
    """Load the JSON dump produced by tools/export_access.ps1 into an empty database."""
    init_db()
    con = connect()
    if con.execute("SELECT COUNT(*) FROM tbl_Assets").fetchone()[0] or \
       con.execute("SELECT COUNT(*) FROM tbl_GLAccounts").fetchone()[0]:
        con.close()
        raise RuntimeError("Database already contains data; delete data/gooya_asset.db to re-import.")
    d = json.loads(export.read_text(encoding="utf-8-sig"))

    def ins(table, rows, cols, conv=None):
        for r in rows:
            vals = []
            for c in cols:
                v = r.get(c)
                if isinstance(v, bool):
                    v = int(v)
                if conv and c in conv:
                    v = conv[c](v)
                vals.append(v)
            con.execute(f"INSERT INTO {table}({','.join(cols)}) VALUES({','.join('?' * len(cols))})", vals)

    ins("tbl_DepreciationMethods", d["tbl_DepreciationMethods"], ["MethodID", "MethodCode", "MethodName", "IsActive"])
    ins("tbl_GLAccounts", d["tbl_GLAccounts"], ["GLAccountID", "AccountCode", "AccountName", "AccountType", "IsActive"])
    ins("tbl_Locations", d["tbl_Locations"], ["LocationID", "LocationCode", "LocationName", "IsActive"])
    ins("tbl_CostCenters", d["tbl_CostCenters"], ["CostCenterID", "CostCenterCode", "CostCenterName", "IsActive"])
    ins("tbl_AssetCategories", d["tbl_AssetCategories"],
        ["CategoryID", "CategoryCode", "CategoryName", "UsefulLifeYears", "DepreciationRate", "MethodID",
         "AssetAccountID", "AccumDepAccountID", "DepExpenseAccountID", "GainAccountID", "LossAccountID", "IsActive"])
    dt = {"AcquisitionDate": _date, "InServiceDate": _date, "WarrantyExpiryDate": _date,
          "OpeningAccumDep": lambda v: v or 0, "ResidualValue": lambda v: v or 0}
    ins("tbl_Assets", d["tbl_Assets"],
        ["AssetID", "AssetCode", "AssetName", "AssetDescription", "CategoryID", "AssetStatus", "AcquisitionDate",
         "InServiceDate", "AcquisitionCost", "ResidualValue", "UsefulLifeYears", "DepreciationRate", "MethodID",
         "OpeningAccumDep", "OpeningNBV", "LocationID", "CostCenterID", "SupplierName", "InvoiceNumber",
         "PurchaseOrderNumber", "SerialNumber", "ModelNumber", "Manufacturer", "WarrantyExpiryDate", "Notes",
         "IsActive", "CreatedAt", "CreatedBy", "ModifiedAt", "ModifiedBy"], dt)
    con.execute("UPDATE tbl_Assets SET DepreciationStartDate=COALESCE(InServiceDate,AcquisitionDate)")
    ins("tbl_DepreciationPeriods", d["tbl_DepreciationPeriods"],
        ["PeriodID", "FiscalYear", "PeriodNumber", "PeriodName", "StartDate", "EndDate", "PeriodStatus",
         "CreatedAt", "CreatedBy"], {"StartDate": _date, "EndDate": _date, "PeriodNumber": lambda v: int(v) if v is not None else None})
    ins("tbl_Depreciation", d["tbl_Depreciation"],
        ["DepreciationID", "AssetID", "PeriodID", "AcquisitionCost", "ResidualValue", "DepreciableAmount",
         "UsefulLifeYears", "DepreciationRate", "OpeningAccumDep", "OpeningNBV", "PeriodDepreciation",
         "ClosingAccumDep", "ClosingNBV", "PostingStatus", "PostedAt", "PostedBy", "CreatedAt", "CreatedBy"])
    ins("tbl_DepreciationJournal", d["tbl_DepreciationJournal"],
        ["JournalID", "DepreciationID", "AssetID", "PeriodID", "JournalDate", "GLAccountID", "DebitAmount",
         "CreditAmount", "JournalType", "Reference", "Description", "PostingStatus", "PostedAt", "PostedBy",
         "CreatedAt"], {"JournalDate": _date})
    for s in d["tbl_Settings"]:
        con.execute("UPDATE tbl_Settings SET SettingValue=?, SettingDescription=?, IsActive=? WHERE SettingKey=?",
                    (s["SettingValue"] or "", s["SettingDescription"], int(bool(s["IsActive"])), s["SettingKey"]))
    if is_pg():   # rows came with their own keys: new keys continue after them
        _pg.reset_sequences(con, primary_keys())
    # One acquisition transaction per migrated asset (needed by roll-forward reports)
    for a in con.execute("SELECT * FROM tbl_Assets").fetchall():
        con.execute(
            "INSERT INTO tbl_AssetTransactions(AssetID,TransactionType,TransactionDate,Amount,ReferenceNumber,Notes,"
            "ToLocationID,ToCostCenterID,CreatedAt,CreatedBy) VALUES(?,?,?,?,?,?,?,?,?,'migration')",
            (a["AssetID"], "ACQUISITION", a["AcquisitionDate"], a["AcquisitionCost"], a["InvoiceNumber"],
             "Migrated from Gooya asset.accdb", a["LocationID"], a["CostCenterID"], _now()))
    # Disposal clearing account (new)
    con.execute("INSERT OR IGNORE INTO tbl_GLAccounts(AccountCode,AccountName,AccountType) "
                      "VALUES('199901','Fixed Asset Disposal Clearing','CLEARING')")
    gid = con.execute("SELECT GLAccountID FROM tbl_GLAccounts WHERE AccountCode='199901'").fetchone()[0]
    con.execute("UPDATE tbl_Settings SET SettingValue=? WHERE SettingKey='DisposalClearingAccountID'", (str(gid),))
    _seed_valuation(con)
    con.commit()
    counts = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
              for t in ("tbl_Assets", "tbl_AssetCategories", "tbl_Depreciation", "tbl_DepreciationJournal",
                        "tbl_DepreciationPeriods", "tbl_GLAccounts")}
    con.close()
    return counts


if __name__ == "__main__":
    if not DB_PATH.exists():
        print("Migrating from Access export ->", migrate_from_access())
    else:
        init_db()
        print("Database ready:", DB_PATH)


# ---------------------------------------------------------------- portable copy of all data (backups, moving between databases)
# parents before children, so foreign keys hold while loading
TABLES = ["tbl_DepreciationMethods", "tbl_GLAccounts", "tbl_Branches", "tbl_Locations", "tbl_CostCenters", "tbl_AssetCategories", "tbl_Currencies",
          "tbl_Settings", "tbl_Roles", "tbl_RolePermissions", "tbl_Users", "tbl_UserBranches", "tbl_Sessions", "tbl_Suppliers", "tbl_Employees",
          "tbl_Assets", "tbl_DepreciationPeriods", "tbl_Depreciation", "tbl_AssetTransactions", "tbl_DepreciationJournal", "tbl_AssetAttachments",
          "tbl_AssetCustody", "tbl_Maintenance", "tbl_AssetCounts", "tbl_AssetCountLines", "tbl_AuditLog"]
DUMP_FORMAT = "usool-data/1"


def dump_rows(con, table: str, batch: int = 5000):
    """(columns, row batches) of one table, in key order."""
    cols = table_columns(con, table)
    pk = primary_keys().get(table)
    cur = con.execute(f"SELECT {','.join(cols)} FROM {table}" + (f" ORDER BY {pk}" if pk else ""))
    data = [list(r) for r in cur.fetchall()]
    return cols, [data[i:i + batch] for i in range(0, len(data), batch)] or [[]]


def _column_types(con, table: str) -> dict[str, str]:
    if is_pg():
        return {r[0]: r[1] for r in con._con.execute(
            "SELECT column_name, data_type FROM information_schema.columns WHERE table_schema=current_schema() AND table_name=%s", (table,)).fetchall()}
    return {r["name"]: (r["type"] or "").lower() for r in con.execute(f"PRAGMA table_info({table})")}


def _coerce(v, kind: str):
    """SQLite stores what it is given; PostgreSQL wants each value in its column's type."""
    if v is None or kind == "":
        return v
    if "int" in kind:
        if v == "":
            return None
        return int(float(v)) if not isinstance(v, int) else v
    if "double" in kind or "real" in kind or "numeric" in kind:
        return None if v == "" else float(v)
    return v if isinstance(v, str) else str(v)


def load_tables(con, tables: dict[str, tuple[list[str], list]]) -> dict[str, int]:
    """Replace every table's rows with the given ones ({table: (columns, rows)}), keys included, in one transaction."""
    present = [t for t in TABLES if t in tables]
    for t in reversed(TABLES):
        con.execute(f"DELETE FROM {t}")
    counts = {}
    for t in present:
        cols, data = tables[t]
        target = _column_types(con, t)
        keep = [i for i, c in enumerate(cols) if c in target]
        names = [cols[i] for i in keep]
        sql = f"INSERT INTO {t}({','.join(names)}) VALUES({','.join('?' * len(names))})"
        rows = [[_coerce(r[i], target[cols[i]]) for i in keep] for r in data]
        for i in range(0, len(rows), 5000):
            con.executemany(sql, rows[i:i + 5000])
        counts[t] = len(rows)
    if is_pg():
        _pg.reset_sequences(con, primary_keys())
    con.commit()
    return counts
