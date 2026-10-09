"""Restore a Usool backup into the database the app is configured for (SQLite or PostgreSQL).  Stop the app first.

    python3 tools/restore_backup.py backups/Usool_backup_2026-10-01_101500.zip
    .venv/bin/python tools/restore_backup.py <zip>        # when the app uses PostgreSQL

A backup holds either the SQLite file (gooya_asset.db) or every table as JSON (usool-data.json, written when the app runs on
PostgreSQL); either kind restores into either database. With SQLite the current file is kept as
data/gooya_asset.before-restore.db. Attachments are extracted into the configured attachment folder and the stored file
paths are re-pointed to it (so a backup also works on another computer).
"""
import json
import shutil
import sqlite3
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app import db  # noqa: E402


def _tables_from_zip(z: zipfile.ZipFile) -> dict:
    names = z.namelist()
    if "usool-data.json" in names:
        data = json.loads(z.read("usool-data.json"))
        if data.get("format") != db.DUMP_FORMAT:
            raise SystemExit(f"Unknown data format: {data.get('format')}")
        return {t: (v["columns"], v["rows"]) for t, v in data["tables"].items()}
    with tempfile.TemporaryDirectory() as tmp:   # an SQLite backup: read its tables
        path = Path(tmp) / "gooya_asset.db"
        path.write_bytes(z.read("gooya_asset.db"))
        url, dbpath = db.URL, db.DB_PATH
        db.URL, db.DB_PATH = None, path
        try:
            con = db.connect()
            out = {}
            for t in db.TABLES:
                if db.table_columns(con, t):   # an older backup may not have every table
                    cols, batches = db.dump_rows(con, t)
                    out[t] = (cols, [r for b in batches for r in b])
            con.close()
        finally:
            db.URL, db.DB_PATH = url, dbpath
        return out


def main(zip_path: str) -> None:
    z = zipfile.ZipFile(zip_path)
    manifest = json.loads(z.read("manifest.json"))
    if not db.is_pg() and "gooya_asset.db" in z.namelist():
        # SQLite into SQLite: the file itself
        if db.DB_PATH.exists():
            shutil.copy2(db.DB_PATH, db.DB_PATH.with_name("gooya_asset.before-restore.db"))
        for ext in ("-wal", "-shm"):
            db.DB_PATH.with_name(db.DB_PATH.name + ext).unlink(missing_ok=True)
        db.DB_PATH.write_bytes(z.read("gooya_asset.db"))
        db.init_db()   # brings an older backup up to the current schema
    else:
        if not db.is_pg() and db.DB_PATH.exists():
            shutil.copy2(db.DB_PATH, db.DB_PATH.with_name("gooya_asset.before-restore.db"))
        tables = _tables_from_zip(z)
        db.init_db()
        con = db.connect()
        counts = db.load_tables(con, tables)
        con.close()
        db.init_db()   # adds what an older backup did not have yet (settings, roles, accounts)
        print(f"Loaded {sum(counts.values())} rows into {db.describe()}")
    con = db.connect()
    folder = con.execute("SELECT SettingValue FROM tbl_Settings WHERE SettingKey='AttachmentFolder'").fetchone()
    att_root = Path(folder[0]) if folder and folder[0] else ROOT / "attachments"
    att_root.mkdir(parents=True, exist_ok=True)
    count = 0
    for name in z.namelist():
        if name.startswith("attachments/") and not name.endswith("/"):
            target = (att_root / name[len("attachments/"):]).resolve()
            if att_root.resolve() not in target.parents:   # never write outside the attachment folder (zip-slip)
                raise SystemExit(f"Unsafe path in the backup: {name}")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(z.read(name))
            count += 1
    old = manifest.get("attachment_root", "")
    for att_id, path in con.execute("SELECT AttachmentID, FilePath FROM tbl_AssetAttachments").fetchall():
        if path and old and path.startswith(old):
            rel = Path(path[len(old):].lstrip("\\/"))
            con.execute("UPDATE tbl_AssetAttachments SET FilePath=? WHERE AttachmentID=?", (str(att_root / rel), att_id))
    con.commit()
    con.close()
    print(f"Restored the database and {count} attachment file(s) from {zip_path}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
