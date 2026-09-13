"""
RentFlow — desktop launcher.

Runs Django on an embedded production server (waitress) and opens the UI in a
native window via pywebview. Falls back to the default web browser if pywebview
isn't installed. This is what PyInstaller packages into RentFlow.exe so the
application runs as normal Windows software — no visible browser, no console.
"""
import os
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

BASE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
# When frozen by PyInstaller, keep the writable database next to the EXE.
if getattr(sys, "frozen", False):
    data_dir = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "RentFlow"
    data_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("RENTFLOW_DB", str(data_dir / "rentflow.sqlite3"))

sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from django.core.management import call_command  # noqa: E402


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def run_server(port: int):
    from waitress import serve
    from config.wsgi import application
    serve(application, host="127.0.0.1", port=port, threads=8)


def main():
    # Ensure DB schema exists and demo/admin user is available on first run.
    call_command("migrate", interactive=False, verbosity=0)
    try:
        call_command("seed_demo")
    except Exception:
        pass

    port = free_port()
    t = threading.Thread(target=run_server, args=(port,), daemon=True)
    t.start()
    time.sleep(1.0)
    url = f"http://127.0.0.1:{port}/"

    try:
        import webview  # pywebview → native window
        webview.create_window(
            "RentFlow — Property Management",
            url, width=1360, height=860, min_size=(1024, 700),
        )
        webview.start()
    except ImportError:
        webbrowser.open(url)
        print(f"RentFlow running at {url} — close this window to stop.")
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
