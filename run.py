"""Start Gooya Asset:  python run.py [--no-browser] [--port 8742]"""
import sys
from app.server import serve

port = int(sys.argv[sys.argv.index("--port") + 1]) if "--port" in sys.argv else 8742
serve(port, open_browser="--no-browser" not in sys.argv)
