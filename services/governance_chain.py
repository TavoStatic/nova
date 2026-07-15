from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Callable

from services.codegen_patch_bridge import (
    bridge_codegen_to_patch,
    materialize_codegen_patch_zip,
    validate_codegen_preview,
)

RELEASE_REBUILD_REQUIRED_STEPS = frozenset(
    {"repo_hygiene", "smoke_runtime", "package_build", "package_verify"}
)


def release_rebuild_success(report: dict[str, Any] | None) -> tuple[bool, str]:
    payload = dict(report or {})
    steps = [
        step
        for step in list(payload.get("steps") or [])
        if isinstance(step, dict)
    ]
    successful = {
        str(step.get("name") or "").strip()
        for step in steps
        if int(step.get("returncode", 1) or 0) == 0
    }
    if not str(payload.get("artifact") or "").strip():
        return False, str(payload.get("failure_reason") or "release_package_missing")
    missing = sorted(RELEASE_REBUILD_REQUIRED_STEPS - successful)
    if missing:
        return False, f"release_rebuild_missing_steps:{','.join(missing)}"
    return True, ""


def release_rebuild_tool_payload(
    report: dict[str, Any] | None,
    *,
    label: str = "work-tree-rebuild",
    run_regression: bool = False,
    promote: bool = False,
) -> dict[str, Any]:
    payload = dict(report or {})
    readiness = payload.get("readiness") if isinstance(payload.get("readiness"), dict) else {}
    steps = [
        {
            "name": str(step.get("name") or ""),
            "returncode": int(step.get("returncode", 1) or 0),
            "duration_sec": step.get("duration_sec"),
        }
        for step in list(payload.get("steps") or [])
        if isinstance(step, dict)
    ]
    ok, failure_reason = release_rebuild_success(payload)
    if ok:
        failure_reason = ""
    elif not failure_reason:
        failure_reason = str(payload.get("failure_reason") or "release_rebuild_verify_failed")
    readiness_state = str(readiness.get("latest_readiness_state") or readiness.get("state") or "")
    return {
        "ok": ok,
        "artifact": str(payload.get("artifact") or ""),
        "failure_reason": failure_reason,
        "readiness_state": readiness_state,
        "ready_to_ship": bool(readiness.get("latest_ready_to_ship", False)),
        "report_path": str(payload.get("report_path") or ""),
        "promoted": bool(promote),
        "run_regression": bool(run_regression),
        "required_steps": sorted(RELEASE_REBUILD_REQUIRED_STEPS),
        "steps": steps,
    }


def _preview_path_from_output(preview_out: str) -> str:
    match = re.search(r"Preview written:\s*(.+)$", str(preview_out or ""), flags=re.M)
    return str(match.group(1) or "").strip() if match else ""


def governed_patch_apply(
    zip_path: str | Path,
    *,
    patch_preview_fn: Callable[[str, bool], str],
    execute_patch_apply_fn: Callable[..., str],
    preview_approved_fn: Callable[[str], bool] | None = None,
    force: bool = False,
) -> dict[str, Any]:
    zip_file = Path(zip_path)
    preview_out = str(patch_preview_fn(str(zip_file), True) or "")
    status = "eligible" if "Status: eligible" in preview_out else "not_eligible"
    preview_path = _preview_path_from_output(preview_out)
    if status != "eligible":
        return {
            "ok": False,
            "status": status,
            "preview_path": preview_path,
            "preview_out": preview_out,
            "apply_out": "",
            "reason": "preview_not_eligible",
        }
    if not preview_path:
        return {
            "ok": False,
            "status": status,
            "preview_path": "",
            "preview_out": preview_out,
            "apply_out": "",
            "reason": "preview_path_missing",
        }
    if not force:
        approval_checker = preview_approved_fn or (lambda _path: False)
        if not approval_checker(preview_path):
            return {
                "ok": False,
                "status": status,
                "preview_path": preview_path,
                "preview_out": preview_out,
                "apply_out": "",
                "reason": "preview_approval_missing",
            }
    apply_out = str(
        execute_patch_apply_fn(
            "apply",
            str(zip_file),
            is_admin=False,
            force=force,
        )
        or ""
    )
    ok = "rejected" not in apply_out.lower() and "failed" not in apply_out.lower()
    return {
        "ok": ok,
        "status": status,
        "preview_path": preview_path,
        "preview_out": preview_out,
        "apply_out": apply_out,
        "reason": "" if ok else "patch_apply_failed",
    }


def run_codegen_to_patch_chain(
    preview_payload: dict[str, Any],
    *,
    updates_dir: Path,
    current_revision: int,
    codegen_id: str = "",
    operator_id: str = "",
    patch_preview_fn: Callable[[str, bool], str] | None = None,
) -> dict[str, Any]:
    ok, reason, parsed = validate_codegen_preview(preview_payload)
    if not ok:
        return {
            "ok": False,
            "stage": "validate_codegen_preview",
            "reason": reason,
        }

    patch_artifact = bridge_codegen_to_patch(
        parsed,
        codegen_id=codegen_id,
        operator_id=operator_id,
    )
    zip_path = materialize_codegen_patch_zip(
        parsed,
        patch_artifact,
        updates_dir=updates_dir,
        current_revision=current_revision,
    )
    preview_out = ""
    if callable(patch_preview_fn):
        preview_out = str(patch_preview_fn(str(zip_path), True) or "")

    return {
        "ok": True,
        "stage": "materialized_patch_zip",
        "patch_id": str(patch_artifact.get("patch_id") or ""),
        "zip_path": str(zip_path),
        "preview_out": preview_out,
        "preview_kind": "codegen_bridge",
        "chain_status_path": _append_chain_status(
            updates_dir,
            {
                "schema": "nova.governance_chain.v1",
                "chain": "codegen_to_patch",
                "ok": True,
                "patch_id": str(patch_artifact.get("patch_id") or ""),
                "zip_path": str(zip_path),
                "codegen_id": str(codegen_id or ""),
                "operator_id": str(operator_id or ""),
                "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            },
        ),
    }


def _append_chain_status(updates_dir: Path, payload: dict[str, Any]) -> str:
    ledger = Path(updates_dir) / "governance_chain.jsonl"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=True) + "\n")
    return str(ledger)