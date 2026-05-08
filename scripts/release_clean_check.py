from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.release_clean import run_release_clean


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Nova's release-clean package readiness lane.")
    parser.add_argument("--label", default="release-clean", help="Release package label suffix.")
    parser.add_argument(
        "--no-regression",
        action="store_true",
        help="Skip the full regression lane. Use only for quick local diagnostics.",
    )
    parser.add_argument(
        "--no-promote",
        action="store_true",
        help="Verify the package without writing a promotion ledger row.",
    )
    parser.add_argument(
        "--timeout-sec",
        type=int,
        default=1800,
        help="Timeout for the full regression command.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    report = run_release_clean(
        root=ROOT,
        label=args.label,
        run_regression=not args.no_regression,
        promote=not args.no_promote,
        timeout_sec=args.timeout_sec,
    )

    print(f"Nova release-clean: {'OK' if report.get('ok') else 'FAIL'}")
    print(f"artifact: {report.get('artifact') or 'none'}")
    readiness = report.get("readiness") or {}
    if readiness:
        readiness_state = readiness.get("latest_readiness_state") or readiness.get("state") or "unknown"
        print(f"readiness: {readiness_state}")
    print(f"report: {report.get('report_path')}")

    for step in report.get("steps", []):
        status = "ok" if step.get("returncode") == 0 else f"failed({step.get('returncode')})"
        print(f"- {step.get('name')}: {status} in {step.get('duration_sec')}s")

    if report.get("ok"):
        return 0
    print(f"failure_reason: {report.get('failure_reason')}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
