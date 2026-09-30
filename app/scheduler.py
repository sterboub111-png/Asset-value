"""Background thread that takes the automatic backups chosen in Settings > Backup."""
import threading
import time
import traceback

from . import db, services as s


def _loop() -> None:
    while True:
        con = None
        try:
            con = db.connect()
            s.run_due_backup(con)
        except Exception:  # noqa: BLE001
            traceback.print_exc()
        finally:
            if con:
                con.close()
        time.sleep(30)


def start() -> None:
    threading.Thread(target=_loop, name="backup-scheduler", daemon=True).start()
