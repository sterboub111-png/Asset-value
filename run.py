"""Start Usool:  python3 run.py [--no-browser] [--port 8742]

With PostgreSQL configured (data/database.url or USOOL_DATABASE_URL) the driver comes from the project's .venv;
run.py switches to that Python by itself when the one it was started with does not have it."""
import os
import sys
from pathlib import Path

from app import db

if db.is_pg():
    try:
        import psycopg  # noqa: F401
    except ImportError:
        home = Path(__file__).resolve().parent / ".venv"
        venv = home / "bin" / "python"
        if venv.exists() and Path(sys.prefix).resolve() != home.resolve():   # not already running inside .venv
            os.execv(str(venv), [str(venv), *sys.argv])
        sys.exit("PostgreSQL is configured but its driver is missing. Run:  python3 -m venv .venv && .venv/bin/pip install -r requirements.txt")

from app.server import serve  # noqa: E402

port = int(sys.argv[sys.argv.index("--port") + 1]) if "--port" in sys.argv else 8742
serve(port, open_browser="--no-browser" not in sys.argv)
