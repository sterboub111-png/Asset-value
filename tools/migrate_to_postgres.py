"""Move the Usool data from the SQLite file to PostgreSQL, check it arrived whole, and switch the app over.

    .venv/bin/python tools/migrate_to_postgres.py postgresql:///usool            # stop the app first
    .venv/bin/python tools/migrate_to_postgres.py postgresql:///usool --replace  # the target already has data

1. creates the schema in PostgreSQL (the same `init_db` the app runs at start);
2. copies every table, keys included, then sets the key counters after the highest key;
3. compares the two databases: rows per table, totals of cost, depreciation and journal, and the data checks;
4. writes the URL to data/database.url, so the app starts on PostgreSQL. The SQLite file is left as it was (keep it as
   a copy; deleting data/database.url switches back to it).
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app import db  # noqa: E402

TOTALS = [("assets", "SELECT COUNT(*), COALESCE(SUM(AcquisitionCost),0) FROM tbl_Assets"),
          ("posted depreciation", "SELECT COUNT(*), COALESCE(SUM(PeriodDepreciation),0) FROM tbl_Depreciation WHERE PostingStatus='POSTED'"),
          ("journal debit", "SELECT COUNT(*), COALESCE(SUM(DebitAmount),0) FROM tbl_DepreciationJournal"),
          ("journal credit", "SELECT COUNT(*), COALESCE(SUM(CreditAmount),0) FROM tbl_DepreciationJournal"),
          ("transactions", "SELECT COUNT(*), COALESCE(SUM(Amount),0) FROM tbl_AssetTransactions")]


def snapshot(con) -> dict:
    out = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in db.TABLES}
    for name, sql in TOTALS:
        n, total = con.execute(sql).fetchone()
        out[name] = (n, round(float(total), 2))
    return out


def main(url: str, replace: bool) -> None:
    if not url.startswith(("postgresql://", "postgres://")):
        sys.exit("Give a PostgreSQL URL, e.g. postgresql:///usool or postgresql://user:password@host:5432/usool")
    if not db.DB_PATH.exists():
        sys.exit(f"No SQLite database at {db.DB_PATH}")
    # ---- read the SQLite database
    db.URL = None
    src = db.connect()
    data = {}
    for t in db.TABLES:
        cols, batches = db.dump_rows(src, t)
        data[t] = (cols, [r for b in batches for r in b])
    before = snapshot(src)
    src.close()
    # ---- write PostgreSQL
    db.URL = url
    db.init_db()
    dst = db.connect()
    if not replace and (dst.execute("SELECT COUNT(*) FROM tbl_Assets").fetchone()[0] or dst.execute("SELECT COUNT(*) FROM tbl_Users").fetchone()[0]):
        sys.exit("The PostgreSQL database already holds assets or users. Run again with --replace to overwrite them.")
    counts = db.load_tables(dst, data)
    after = snapshot(dst)
    # ---- compare
    diff = {k: (before[k], after[k]) for k in before if before[k] != after[k]}
    from app import services as s
    failed = [c["id"] for c in s.run_checks(dst) if not c["ok"]]
    dst.close()
    print(f"Copied {sum(counts.values())} rows in {len(counts)} tables to {db.describe()}")
    for name, _ in TOTALS:
        print(f"  {name:20s} {after[name][0]:>8} rows  total {after[name][1]:,.2f}")
    if diff or failed:
        print("NOT switched: the copy differs from the source" if diff else "NOT switched: data checks failed", diff or failed)
        sys.exit(1)
    db.URL_FILE.write_text(url + "\n", encoding="utf-8")
    print(f"Identical row counts and totals; every data check passes. The app now uses PostgreSQL ({db.URL_FILE.name}).")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 1:
        sys.exit(__doc__)
    main(args[0], "--replace" in sys.argv)
