from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.runtime_detach import spawn_unattached


def main() -> int:
    parser = argparse.ArgumentParser(description="Start nova_http.py as a detached Windows service process.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--delay-seconds", type=float, default=0.0)
    args = parser.parse_args()

    python_exe = ROOT / ".venv" / "Scripts" / "python.exe"
    http_py = ROOT / "nova_http.py"
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
    ok, _pid, detail = spawn_unattached(command, cwd=ROOT)
    if not ok:
        print(f"[FAIL] unattached HTTP start failed: {detail}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())