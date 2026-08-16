"""Sleep, then WMI-start a command. Used for guard/HTTP restart."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.runtime_detach import spawn_unattached


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Delay, then start a process outside the caller job.")
    parser.add_argument("--delay", type=float, default=0.0)
    parser.add_argument("--cwd", default="")
    parser.add_argument("--remove", action="append", default=[])
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = [str(item) for item in list(args.command or []) if str(item)]
    if command and command[0] == "--":
        command = command[1:]
    if len(command) < 2:
        print("command_required", file=sys.stderr)
        return 1
    delay = max(0.0, float(args.delay or 0.0))
    if delay:
        time.sleep(delay)
    for raw in list(args.remove or []):
        try:
            Path(str(raw)).unlink(missing_ok=True)
        except OSError:
            pass
    cwd = str(args.cwd or Path.cwd())
    ok, _pid, detail = spawn_unattached(command, cwd=cwd)
    if not ok:
        print(detail, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
