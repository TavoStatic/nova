from __future__ import annotations

import subprocess
import sys
from pathlib import Path


WORKSPACE_ROOT = Path(__file__).resolve().parents[1]


def _suite_command() -> list[str]:
    return [
        sys.executable,
        str(WORKSPACE_ROOT / "run_regression.py"),
        "preflight",
    ]


def check_suite() -> tuple[bool, str]:
    result = subprocess.run(
        _suite_command(),
        cwd=WORKSPACE_ROOT,
        capture_output=True,
        text=True,
    )
    output = (result.stdout or "") + (result.stderr or "")
    summary = ""
    for line in reversed(output.splitlines()):
        clean = line.strip()
        if clean:
            summary = clean
            break
    return result.returncode == 0, summary


def main() -> int:
    ok, summary = check_suite()
    print(f"Test suite: {'OK' if ok else 'FAIL'}")
    if summary:
        print(f"Suite summary: {summary}")
    print("Supervisor bypass warnings: inspect latest test output or runtime/health.log")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())