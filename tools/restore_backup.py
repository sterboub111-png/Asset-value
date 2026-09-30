"""Restore a Gooya Asset backup.  Stop the app first.

    python tools/restore_backup.py backups/GooyaAsset_backup_2026-10-01_101500.zip

The current database is kept as data/gooya_asset.before-restore.db, attachments are extracted into the
configured attachment folder and the stored file paths are re-pointed to it (so a backup also works on another PC).
"""
import json
import shutil
import sqlite3
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app import db  # noqa: E402


def main(zip_path: str) -> None:
    z = zipfile.ZipFile(zip_path)
    manifest = json.loads(z.read("manifest.json"))
    if db.DB_PATH.exists():
        shutil.copy2(db.DB_PATH, db.DB_PATH.with_name("gooya_asset.before-restore.db"))
    for ext in ("-wal", "-shm"):
        db.DB_PATH.with_name(db.DB_PATH.name + ext).unlink(missing_ok=True)
    db.DB_PATH.write_bytes(z.read("gooya_asset.db"))
    con = sqlite3.connect(db.DB_PATH)
    folder = con.execute("SELECT SettingValue FROM tbl_Settings WHERE SettingKey='AttachmentFolder'").fetchone()
    att_root = Path(folder[0]) if folder and folder[0] else ROOT / "attachments"
    att_root.mkdir(parents=True, exist_ok=True)
    count = 0
    for name in z.namelist():
        if name.startswith("attachments/") and not name.endswith("/"):
            target = att_root / name[len("attachments/"):]
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
    print(f"Restored database and {count} attachment file(s) from {zip_path}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
