from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.end_to_end_wiring import run_end_to_end_wiring_check


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check Nova's end-to-end wiring posture.")
    parser.add_argument("--offline", action="store_true", help="Skip live runtime checks.")
    parser.add_argument("--json", action="store_true", help="Emit JSON.")
    parser.add_argument("--timeout-sec", type=int, default=60, help="Timeout for subprocess checks.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    report = run_end_to_end_wiring_check(
        root=ROOT,
        include_runtime=not args.offline,
        timeout_sec=args.timeout_sec,
    )
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"Nova wiring-check: {'OK' if report.get('ok') else 'FAIL'}")
        print(f"root: {report.get('root')}")
        print(f"checks: {report.get('check_count')} failed: {report.get('failed_count')}")
        for check in report.get("checks", []):
            status = "OK" if check.get("ok") else "FAIL"
            required = "" if check.get("required") else " (optional)"
            print(f"- {status} {check.get('name')}{required}: {check.get('detail')}")
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
