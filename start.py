"""
Synthesis Architect — One-Command Launcher

Usage:
    python start.py

Starts the server and opens http://localhost:8000 in your browser.
"""
import os
import subprocess
import sys
import time
import threading
import webbrowser
from pathlib import Path

PORT = 8000
URL = f"http://localhost:{PORT}"


def open_browser():
    """Open the app in the default browser (cross-platform)."""
    time.sleep(1.5)  # Wait for server to start

    # webbrowser picks the right launcher per OS (Windows, macOS, Linux),
    # avoiding shell-specific commands like `open`/`xdg-open`/`start`.
    webbrowser.open(URL)

    print(f"\n🌐 Opened {URL} in your browser")


if __name__ == "__main__":
    import sys
    if sys.stdout.encoding != 'utf-8':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except Exception:
            pass

    # Change to the project root
    project_dir = Path(__file__).resolve().parent
    os.chdir(project_dir)

    print("=" * 50)
    print("  🔬 Synthesis Architect")
    print("=" * 50)
    print(f"\n  Starting server on {URL}")
    print("  Press Ctrl+C to stop\n")

    # Open browser in background thread
    threading.Thread(target=open_browser, daemon=True).start()

    # Start uvicorn
    try:
        subprocess.run([
            sys.executable, "-m", "uvicorn",
            "app.main:app",
            "--host", "0.0.0.0",
            "--port", str(PORT),
            "--reload"
        ])
    except KeyboardInterrupt:
        print("\n\n👋 Synthesis Architect stopped.")
