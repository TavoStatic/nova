from __future__ import annotations

import argparse
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.runtime_detach import spawn_unattached

LOG_DIR = ROOT / "logs"
HTTP_STDOUT_LOG = LOG_DIR / "nova_http.out.log"
HTTP_STDERR_LOG = LOG_DIR / "nova_http.err.log"
HTTP_EXIT_CODE_FILE = LOG_DIR / "nova_http.exitcode"


def _tail(path: Path, limit: int = 80) -> str:
    if not path.exists():
        return ""
    return "\n".join(path.read_text(encoding="utf-8", errors="replace").splitlines()[-limit:])


def _http_ready(host: str, port: int, timeout: float = 3.0) -> bool:
    try:
        with urllib.request.urlopen(f"http://{host}:{port}/api/health", timeout=timeout) as response:
            return response.status == 200
    except (OSError, urllib.error.URLError):
        return False


def _pid_exists(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        import psutil

        return psutil.pid_exists(pid)
    except Exception:
        return True


def wait_for_http_ready(pid: int | None, host: str, port: int, timeout: float = 30.0, poll: float = 0.5) -> bool:
    deadline = time.monotonic() + max(0.0, timeout)
    while time.monotonic() < deadline:
        if _http_ready(host, port):
            return True
        if pid and not _pid_exists(pid):
            return False
        time.sleep(max(0.01, poll))
    return _http_ready(host, port)


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

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    HTTP_STDOUT_LOG.touch()
    HTTP_STDERR_LOG.touch()
    HTTP_EXIT_CODE_FILE.unlink(missing_ok=True)

    command = [
        str(python_exe),
        str(http_py),
        "--host",
        str(args.host),
        "--port",
        str(int(args.port)),
    ]
    ok, pid, detail = spawn_unattached(
        command,
        cwd=ROOT,
        stdout_path=HTTP_STDOUT_LOG,
        stderr_path=HTTP_STDERR_LOG,
        exit_code_path=HTTP_EXIT_CODE_FILE,
    )
    if not ok:
        print(f"[FAIL] unattached HTTP start failed: {detail}", file=sys.stderr)
        return 1
    print(f"[INFO] nova_http wrapper creation accepted wrapper_pid={pid} detail={detail}", flush=True)
    if wait_for_http_ready(pid, args.host, int(args.port)):
        return 0

    exit_code = ""
    if HTTP_EXIT_CODE_FILE.exists():
        exit_code = HTTP_EXIT_CODE_FILE.read_text(encoding="utf-8", errors="replace").strip()
    print(f"[FAIL] nova_http did not become ready wrapper_pid={pid} exit_code={exit_code or 'unknown'}", file=sys.stderr)
    stderr_tail = _tail(HTTP_STDERR_LOG)
    if stderr_tail:
        print("[FAIL] nova_http stderr tail:", file=sys.stderr)
        print(stderr_tail, file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())