from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import shutil
import time
from typing import Any, Mapping, Optional
from uuid import uuid4


@dataclass(frozen=True)
class PipelineProtocolPaths:
    root: Path
    requests_dir: Path
    responses_dir: Path
    archive_dir: Path


def _sanitize_pipeline_id(pipeline_id: str) -> str:
    text = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in (pipeline_id or "").strip())
    return text or "unknown_pipeline"


def build_protocol_paths(runtime_root: Path, pipeline_id: str) -> PipelineProtocolPaths:
    slug = _sanitize_pipeline_id(pipeline_id)
    root = runtime_root / "pipelines" / slug
    return PipelineProtocolPaths(
        root=root,
        requests_dir=root / "requests",
        responses_dir=root / "responses",
        archive_dir=root / "archive",
    )


def ensure_protocol_dirs(paths: PipelineProtocolPaths) -> None:
    for path in (paths.root, paths.requests_dir, paths.responses_dir, paths.archive_dir):
        path.mkdir(parents=True, exist_ok=True)


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), indent=2, ensure_ascii=True), encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def submit_request(
    paths: PipelineProtocolPaths,
    *,
    pipeline_id: str,
    operation: str,
    params: Optional[Mapping[str, Any]] = None,
    row_limit: Optional[int] = None,
    requested_by: str = "",
    timeout_sec: int = 60,
) -> dict[str, Any]:
    ensure_protocol_dirs(paths)
    request_id = f"{int(time.time())}_{uuid4().hex[:12]}"
    payload: dict[str, Any] = {
        "protocol_version": 1,
        "request_id": request_id,
        "pipeline_id": pipeline_id,
        "operation": operation,
        "params": dict(params or {}),
        "requested_by": requested_by,
        "created_at": int(time.time()),
        "timeout_sec": max(1, int(timeout_sec)),
    }
    if row_limit is not None:
        payload["row_limit"] = max(1, int(row_limit))
    request_path = paths.requests_dir / f"{request_id}.request.json"
    _write_json(request_path, payload)
    return payload


def claim_next_request(paths: PipelineProtocolPaths) -> Optional[Path]:
    ensure_protocol_dirs(paths)
    for request_path in sorted(paths.requests_dir.glob("*.request.json"), key=lambda item: item.name):
        working_path = request_path.with_suffix("").with_suffix(".working.json")
        try:
            request_path.replace(working_path)
            return working_path
        except OSError:
            continue
    return None


def load_request(path: Path) -> dict[str, Any]:
    return _read_json(path)


def response_path(paths: PipelineProtocolPaths, request_id: str) -> Path:
    return paths.responses_dir / f"{request_id}.response.json"


def write_response(
    paths: PipelineProtocolPaths,
    request_id: str,
    payload: Mapping[str, Any],
) -> Path:
    ensure_protocol_dirs(paths)
    target = response_path(paths, request_id)
    _write_json(target, payload)
    return target


def load_response(paths: PipelineProtocolPaths, request_id: str) -> Optional[dict[str, Any]]:
    target = response_path(paths, request_id)
    if not target.exists():
        return None
    return _read_json(target)


def wait_for_response(
    paths: PipelineProtocolPaths,
    request_id: str,
    *,
    timeout_sec: int = 60,
    poll_interval_sec: float = 0.5,
) -> Optional[dict[str, Any]]:
    deadline = time.time() + max(1, int(timeout_sec))
    while time.time() < deadline:
        payload = load_response(paths, request_id)
        if payload is not None:
            return payload
        time.sleep(max(0.05, float(poll_interval_sec)))
    return None


def archive_request(paths: PipelineProtocolPaths, working_path: Path, *, status: str) -> Path:
    ensure_protocol_dirs(paths)
    stem = working_path.name.replace(".working.json", "")
    target = paths.archive_dir / f"{stem}.{status}.json"
    if target.exists():
        target.unlink(missing_ok=True)
    shutil.move(str(working_path), str(target))
    return target
