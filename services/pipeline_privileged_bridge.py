from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Optional

from pipelines.privileged_protocol import build_protocol_paths
from pipelines.privileged_protocol import submit_request
from pipelines.privileged_protocol import wait_for_response
from services.nova_runtime_context import RUNTIME_DIR


RUNTIME_ROOT = RUNTIME_DIR


def queue_privileged_pipeline_query(
    pipeline_id: str,
    operation: str,
    params: Optional[Mapping[str, Any]] = None,
    *,
    row_limit: Optional[int] = None,
    requested_by: str = "",
    timeout_sec: int = 60,
    runtime_root: Optional[Path] = None,
) -> dict[str, Any]:
    paths = build_protocol_paths(runtime_root or RUNTIME_ROOT, pipeline_id)
    return submit_request(
        paths,
        pipeline_id=pipeline_id,
        operation=operation,
        params=params,
        row_limit=row_limit,
        requested_by=requested_by,
        timeout_sec=timeout_sec,
    )


def wait_for_privileged_pipeline_query(
    pipeline_id: str,
    request_id: str,
    *,
    timeout_sec: int = 60,
    poll_interval_sec: float = 0.5,
    runtime_root: Optional[Path] = None,
) -> Optional[dict[str, Any]]:
    paths = build_protocol_paths(runtime_root or RUNTIME_ROOT, pipeline_id)
    return wait_for_response(
        paths,
        request_id,
        timeout_sec=timeout_sec,
        poll_interval_sec=poll_interval_sec,
    )


def run_privileged_pipeline_query(
    pipeline_id: str,
    operation: str,
    params: Optional[Mapping[str, Any]] = None,
    *,
    row_limit: Optional[int] = None,
    requested_by: str = "",
    timeout_sec: int = 60,
    poll_interval_sec: float = 0.5,
    runtime_root: Optional[Path] = None,
) -> dict[str, Any]:
    request = queue_privileged_pipeline_query(
        pipeline_id,
        operation,
        params,
        row_limit=row_limit,
        requested_by=requested_by,
        timeout_sec=timeout_sec,
        runtime_root=runtime_root,
    )
    response = wait_for_privileged_pipeline_query(
        pipeline_id,
        str(request["request_id"]),
        timeout_sec=timeout_sec,
        poll_interval_sec=poll_interval_sec,
        runtime_root=runtime_root,
    )
    if response is None:
        return {
            "ok": False,
            "pipeline_id": pipeline_id,
            "operation": operation,
            "request_id": request["request_id"],
            "error": "Timed out waiting for privileged pipeline response.",
        }
    return response
