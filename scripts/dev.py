r"""Start the development servers with one command.

    .venv\Scripts\python.exe scripts\dev.py            (Windows)
    .venv/bin/python scripts/dev.py                     (macOS / Linux)

Starts the FastAPI backend on http://localhost:8000 (API docs at /api/v1/docs) and,
once the frontend exists (Phase 6), the Vite dev server on http://localhost:5173.
Ctrl+C stops both.
"""
from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    procs: list[subprocess.Popen] = []
    backend = [sys.executable, "-m", "uvicorn", "app.main:app", "--reload", "--port", "8000",
               "--reload-dir", "app"]
    print("backend : http://localhost:8000/api/v1/docs")
    procs.append(subprocess.Popen(backend, cwd=ROOT / "backend"))

    frontend_dir = ROOT / "frontend"
    npm = shutil.which("npm")
    if (frontend_dir / "package.json").exists() and npm:
        if not (frontend_dir / "node_modules").exists():
            subprocess.run([npm, "install"], cwd=frontend_dir, check=True)
        print("frontend: http://localhost:5173")
        procs.append(subprocess.Popen([npm, "run", "dev"], cwd=frontend_dir))
    else:
        print("frontend: not started (frontend/package.json or npm not found)")

    try:
        while all(p.poll() is None for p in procs):
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        for p in procs:
            if p.poll() is None:
                if os.name == "nt":
                    # Kill the whole tree: uvicorn --reload runs the app in a child
                    # process that would otherwise keep port 8000 open.
                    subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], capture_output=True)
                else:
                    p.send_signal(signal.SIGINT)
        for p in procs:
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
