from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.release_status import RELEASE_STATUS_SERVICE
from services.release_validation import render_release_validation_report
from services.release_validation import run_release_validation


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run an observed release validation profile for a package artifact.")
    parser.add_argument("--artifact", default="", help="Release artifact zip or extracted package root.")
    parser.add_argument("--record", default="", help="Validation record path to update from observed evidence.")
    parser.add_argument("--version", default="", help="Artifact version.")
    parser.add_argument("--channel", default="rc", help="Release channel.")
    parser.add_argument("--label", default="", help="Release label.")
    parser.add_argument("--version-source", default="", help="Version source.")
    parser.add_argument("--ledger", default="", help="Release ledger path.")
    parser.add_argument("--include-runtime", action="store_true", help="Include Ollama-backed runtime smoke.")
    parser.add_argument("--keep-extract", action="store_true", help="Keep the extracted validation package workspace.")
    parser.add_argument("--timeout-sec", type=int, default=1800, help="Timeout for nova test.")
    parser.add_argument("--json", action="store_true", help="Emit JSON.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    ledger_path = Path(args.ledger) if args.ledger else ROOT / "runtime" / "exports" / "release_packages" / "release_ledger.jsonl"
    status = RELEASE_STATUS_SERVICE.status_payload(ledger_path, 8, source_root=ROOT)
    artifact = args.artifact or str(status.get("latest_artifact_path") or "")
    record = args.record or str(status.get("latest_validation_seed_path") or "")
    version = args.version or str(status.get("latest_version") or "")
    channel = args.channel or str(status.get("latest_channel") or "rc")
    label = args.label or str(status.get("latest_label") or "")

    report = run_release_validation(
        repo_root=ROOT,
        artifact_path=artifact,
        record_path=record,
        artifact_version=version,
        release_channel=channel,
        release_label=label,
        version_source=args.version_source,
        ledger_path=str(ledger_path),
        include_runtime=bool(args.include_runtime),
        timeout_sec=int(args.timeout_sec),
        keep_extract=bool(args.keep_extract),
    )
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_release_validation_report(report))
    return 0 if report.get("completed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
