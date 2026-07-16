from __future__ import annotations

import argparse
import atexit
import os
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipelines.privileged_worker import process_next_privileged_request
from services.edfi.change_tracking import maybe_advance_tracked_cursors
from services.nova_runtime_context import RUNTIME_DIR
from services.pipeline_worker_supervision import (
    acquire_worker_lease,
    release_worker_lease,
    write_worker_heartbeat,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a privileged Nova data-pipeline worker.")
    parser.add_argument("--pipeline", required=True, help="Pipeline id to service, e.g. sis_test")
    parser.add_argument("--runtime-root", default=str(RUNTIME_DIR))
    parser.add_argument("--data-sources-root", default=str(ROOT / "data_sources"))
    parser.add_argument("--once", action="store_true", help="Process at most one request and exit.")
    parser.add_argument("--poll-interval", type=float, default=1.0, help="Seconds between polls when idle.")
    parser.add_argument(
        "--connection-id",
        default="district-main",
        help="Ed-Fi connection id for scheduled change-cursor maintenance.",
    )
    return parser


def _worker_error_log_path(pipeline_id: str, *, runtime_root: Path) -> Path:
    slug = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in str(pipeline_id or "").strip()) or "unknown_pipeline"
    return runtime_root / "pipelines" / slug / "worker.error.log"


def _append_worker_error(runtime_root: Path, pipeline_id: str, message: str) -> None:
    path = _worker_error_log_path(pipeline_id, runtime_root=runtime_root)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(message.rstrip() + "\n")
    except Exception:
        pass


def main() -> int:
    args = build_parser().parse_args()
    runtime_root = Path(args.runtime_root).resolve()
    data_sources_root = Path(args.data_sources_root).resolve()
    owner_pid = int(os.getpid())

    lease = acquire_worker_lease(
        args.pipeline,
        runtime_root=runtime_root,
        candidate_owner_pid=owner_pid,
    )
    if str(lease.get("status") or "") == "duplicate_ownership":
        return 2

    write_worker_heartbeat(
        args.pipeline,
        runtime_root=runtime_root,
        status="running",
        detail="worker_started",
        pid=owner_pid,
    )

    def _release_lease() -> None:
        release_worker_lease(
            args.pipeline,
            runtime_root=runtime_root,
            expected_owner_pid=owner_pid,
        )

    atexit.register(_release_lease)

    if args.once:
        process_next_privileged_request(
            args.pipeline,
            runtime_root=runtime_root,
            data_sources_root=data_sources_root,
        )
        maybe_advance_tracked_cursors(str(args.connection_id or "district-main").strip() or "district-main")
        return 0

    idle_cycles = 0
    while True:
        try:
            processed = process_next_privileged_request(
                args.pipeline,
                runtime_root=runtime_root,
                data_sources_root=data_sources_root,
            )
        except Exception as exc:
            detail = f"worker_loop_error:{exc}"
            _append_worker_error(runtime_root, args.pipeline, traceback.format_exc())
            write_worker_heartbeat(
                args.pipeline,
                runtime_root=runtime_root,
                status="error",
                detail=detail[:240],
                pid=owner_pid,
            )
            time.sleep(max(0.5, float(args.poll_interval)))
            continue
        if processed is None:
            idle_cycles += 1
            if idle_cycles % 30 == 0:
                write_worker_heartbeat(
                    args.pipeline,
                    runtime_root=runtime_root,
                    status="idle",
                    detail="no_pending_requests",
                    pid=owner_pid,
                )
            if idle_cycles % 60 == 0:
                maybe_advance_tracked_cursors(str(args.connection_id or "district-main").strip() or "district-main")
            time.sleep(max(0.1, float(args.poll_interval)))
        else:
            idle_cycles = 0


if __name__ == "__main__":
    raise SystemExit(main())
