from __future__ import annotations

from pathlib import Path
import time
from typing import Any, Mapping, Optional

from pipelines.privileged_protocol import archive_request
from pipelines.privileged_protocol import build_protocol_paths
from pipelines.privileged_protocol import claim_next_request
from pipelines.privileged_protocol import load_request
from pipelines.privileged_protocol import write_response
from services.data_pipeline_registry import run_pipeline_query
from services.pipeline_worker_supervision import write_worker_heartbeat


def process_next_privileged_request(
    pipeline_id: str,
    *,
    runtime_root: Path,
    data_sources_root: Optional[Path] = None,
    execute_fn=None,
) -> Optional[dict[str, Any]]:
    paths = build_protocol_paths(runtime_root, pipeline_id)
    write_worker_heartbeat(
        pipeline_id,
        runtime_root=runtime_root,
        status="running",
        detail="processing_request",
    )
    claimed_path = claim_next_request(paths)
    if claimed_path is None:
        write_worker_heartbeat(
            pipeline_id,
            runtime_root=runtime_root,
            status="idle",
            detail="no_pending_requests",
        )
        return None

    request = load_request(claimed_path)
    request_id = str(request.get("request_id") or "")
    operation = str(request.get("operation") or "")
    params = request.get("params") or {}
    row_limit = request.get("row_limit")
    if execute_fn is None:
        execute_fn = run_pipeline_query

    started_at = int(time.time())
    try:
        result = execute_fn(
            pipeline_id,
            operation,
            params,
            row_limit=row_limit,
            data_sources_root=data_sources_root,
        )
        response = {
            "protocol_version": 1,
            "request_id": request_id,
            "pipeline_id": pipeline_id,
            "operation": operation,
            "ok": bool(result.get("ok")),
            "completed_at": int(time.time()),
            "started_at": started_at,
            "result": result,
        }
        write_response(paths, request_id, response)
        archive_request(paths, claimed_path, status="done")
        write_worker_heartbeat(
            pipeline_id,
            runtime_root=runtime_root,
            status="idle",
            detail="request_completed",
        )
        return response
    except Exception as exc:
        response = {
            "protocol_version": 1,
            "request_id": request_id,
            "pipeline_id": pipeline_id,
            "operation": operation,
            "ok": False,
            "completed_at": int(time.time()),
            "started_at": started_at,
            "error": str(exc),
        }
        write_response(paths, request_id, response)
        archive_request(paths, claimed_path, status="error")
        write_worker_heartbeat(
            pipeline_id,
            runtime_root=runtime_root,
            status="error",
            detail=str(exc),
        )
        return response
