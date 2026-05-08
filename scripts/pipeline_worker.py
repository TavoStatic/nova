from __future__ import annotations

import argparse
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipelines.privileged_worker import process_next_privileged_request
from services.nova_runtime_context import RUNTIME_DIR


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a privileged Nova data-pipeline worker.")
    parser.add_argument("--pipeline", required=True, help="Pipeline id to service, e.g. sis_test")
    parser.add_argument("--runtime-root", default=str(RUNTIME_DIR))
    parser.add_argument("--data-sources-root", default=str(ROOT / "data_sources"))
    parser.add_argument("--once", action="store_true", help="Process at most one request and exit.")
    parser.add_argument("--poll-interval", type=float, default=1.0, help="Seconds between polls when idle.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    runtime_root = Path(args.runtime_root).resolve()
    data_sources_root = Path(args.data_sources_root).resolve()

    if args.once:
        process_next_privileged_request(
            args.pipeline,
            runtime_root=runtime_root,
            data_sources_root=data_sources_root,
        )
        return 0

    while True:
        processed = process_next_privileged_request(
            args.pipeline,
            runtime_root=runtime_root,
            data_sources_root=data_sources_root,
        )
        if processed is None:
            time.sleep(max(0.1, float(args.poll_interval)))


if __name__ == "__main__":
    raise SystemExit(main())
