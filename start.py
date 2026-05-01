"""
Synthesis Architect — One-Command Launcher

Usage:
    python start.py

Starts the server and opens http://localhost:8000 in your browser.
"""
import subprocess
import sys
import os
import time
import threading

PORT = 8000
URL = f"http://localhost:{PORT}"


def open_browser():
    """Open the app in the default browser (WSL-aware)."""
    time.sleep(1.5)  # Wait for server to start

    # Detect WSL
    is_wsl = False
    try:
        with open('/proc/version', 'r') as f:
            is_wsl = 'microsoft' in f.read().lower()
    except:
        pass

    if is_wsl:
        os.system(f'cmd.exe /c start {URL}')
    elif sys.platform == 'darwin':
        os.system(f'open {URL}')
    elif sys.platform == 'linux':
        os.system(f'xdg-open {URL}')
    else:
        os.system(f'start {URL}')

    print(f"\n🌐 Opened {URL} in your browser")


if __name__ == "__main__":
    # Change to the project root
    project_dir = os.path.dirname(os.path.abspath(__file__))
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
