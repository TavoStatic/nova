from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path


def _creation_flags() -> int:
    if sys.platform != "win32":
        return 0
    return (
        subprocess.DETACHED_PROCESS
        | subprocess.CREATE_NEW_PROCESS_GROUP
        | subprocess.CREATE_NO_WINDOW
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Start nova_http.py as a detached Windows service process.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--delay-seconds", type=float, default=0.0)
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    python_exe = root / ".venv" / "Scripts" / "python.exe"
    http_py = root / "nova_http.py"
    if not python_exe.exists():
        print(f"[FAIL] venv python missing: {python_exe}", file=sys.stderr)
        return 1
    if not http_py.exists():
        print(f"[FAIL] nova_http missing: {http_py}", file=sys.stderr)
        return 1

    delay_seconds = max(0.0, float(args.delay_seconds))
    if delay_seconds > 0:
        time.sleep(delay_seconds)

    command = [
        str(python_exe),
        str(http_py),
        "--host",
        str(args.host),
        "--port",
        str(int(args.port)),
    ]
    subprocess.Popen(
        command,
        cwd=str(root),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=_creation_flags(),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())