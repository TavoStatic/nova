from __future__ import annotations

"""
Backpack Query — In-Process Direct Lane

Runs a backpack pipeline query in-process without going through the
privileged worker (file-based IPC).

Why not the privileged worker?
  The existing privileged_worker uses data_pipeline_registry.run_pipeline_query()
  which calls build_pipeline_registry(data_sources_root) — it only knows about
  data_sources/*/pipeline.json pipelines, not backpacks.

  Wiring backpacks into the privileged worker requires touching
  data_pipeline_registry.py. That's a future task.

  For v1, backpack pipelines are read-only and governed (safe_query with audit).
  In-process is sufficient. The audit log in DataConnectorPipeline.audit records every call.

Usage:
    from services.backpack_host.query import run_backpack_query
    result = run_backpack_query("edfi", "list_schools", row_limit=10)
"""

from pathlib import Path
from typing import Any, Mapping, Optional

from services.nova_runtime_context import BASE_DIR, RUNTIME_DIR

BACKPACKS_ROOT = BASE_DIR / "backpacks"
DATA_SOURCES_ROOT = BASE_DIR / "data_sources"


def _registry():
    from services.backpack_host.registry import BackpackAwarePipelineRegistry
    return BackpackAwarePipelineRegistry(
        DATA_SOURCES_ROOT,
        BACKPACKS_ROOT,
        nova_root=BASE_DIR,
        runtime_root=RUNTIME_DIR,
    )


def _enforce_grant(
    pipeline_id: str,
    pipeline_operation: str,
    *,
    role: str,
) -> dict[str, Any] | None:
    """Return an error payload if the role may not run this pipeline op; else None."""
    from services.backpack_host.grant_enforcer import check_grant
    from services.backpack_host.ops_map import backpack_dir_for_pipeline_id, pipeline_op_to_backpack_op

    backpack_dir = backpack_dir_for_pipeline_id(pipeline_id, backpacks_root=BACKPACKS_ROOT)
    if backpack_dir is None:
        # Not a backpack folder — allow (legacy data_sources-only ids use other paths).
        return None
    backpack_op = pipeline_op_to_backpack_op(backpack_dir, pipeline_operation)
    if not backpack_op:
        # Unmapped pipeline ops stay available to host internals (status helpers, etc.).
        return None
    if check_grant(backpack_dir, backpack_op, role):
        return None
    return {
        "ok": False,
        "pipeline_id": pipeline_id,
        "operation": pipeline_operation,
        "backpack_operation": backpack_op,
        "role": role,
        "error": f"backpack_grant_denied:operation={backpack_op}:role={role}",
    }


def run_backpack_query(
    pipeline_id: str,
    operation: str,
    params: Optional[Mapping[str, Any]] = None,
    *,
    row_limit: Optional[int] = None,
    dry_run: bool = False,
    role: str = "standard_user",
    skip_grant_check: bool = False,
) -> dict[str, Any]:
    """
    Run a governed query against a backpack pipeline.

    Args:
        pipeline_id:  Backpack pipeline_id (e.g. 'edfi').
        operation:    Pipeline operation name (e.g. 'list_schools').
        params:       Optional operation parameters.
        row_limit:    Optional row cap (pipeline enforces hard cap regardless).
        dry_run:      If True, validate + preview without executing.
        role:         Nova Shell role for operations.json default_grants.
        skip_grant_check: Install/system callers only — bypasses op grants.

    Returns:
        Result dict with 'ok', data fields, and audit metadata.
    """
    if not skip_grant_check:
        denied = _enforce_grant(pipeline_id, operation, role=str(role or "standard_user"))
        if denied is not None:
            return denied

    try:
        from services.backpack_host.install_state import backpack_runtime_installed

        if not backpack_runtime_installed(str(pipeline_id or "")):
            return {
                "ok": False,
                "pipeline_id": pipeline_id,
                "operation": operation,
                "error": "backpack_not_installed",
                "detail": "This backpack is not installed.",
            }
    except Exception:
        pass

    # Operator on/off switch (control panel). Uninstalled backpacks are off.
    # Read enabled.json directly to avoid circular imports with control_backpacks.
    try:
        import json as _json

        enabled_path = RUNTIME_DIR / str(pipeline_id) / "enabled.json"
        if enabled_path.is_file():
            data = _json.loads(enabled_path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "enabled" in data and not bool(data.get("enabled")):
                return {
                    "ok": False,
                    "pipeline_id": pipeline_id,
                    "operation": operation,
                    "error": "backpack_disabled",
                    "detail": "This backpack is turned off in the control panel.",
                }
    except Exception:
        pass

    try:
        pipeline = _registry().instantiate(pipeline_id)
    except KeyError:
        return {
            "ok": False,
            "pipeline_id": pipeline_id,
            "operation": operation,
            "error": f"backpack_not_found:{pipeline_id}",
        }
    except Exception as exc:
        return {
            "ok": False,
            "pipeline_id": pipeline_id,
            "operation": operation,
            "error": f"backpack_load_failed:{exc}",
        }

    try:
        result = pipeline.safe_query(
            operation,
            params,
            row_limit=row_limit,
            dry_run=dry_run,
            role=str(role or "standard_user"),
        )
        if isinstance(result, dict):
            result.setdefault("backpack_role", str(role or "standard_user"))
            result.setdefault("governed_route", "backpack_host")
        return result
    except Exception as exc:
        return {
            "ok": False,
            "pipeline_id": pipeline_id,
            "operation": operation,
            "error": str(exc),
        }


def backpack_status(pipeline_id: str) -> dict[str, Any]:
    """Return pipeline status for a backpack by pipeline_id."""
    try:
        pipeline = _registry().instantiate(pipeline_id)
        return pipeline.status()
    except KeyError:
        return {
            "ok": False,
            "pipeline_id": pipeline_id,
            "error": f"backpack_not_found:{pipeline_id}",
        }
    except Exception as exc:
        return {
            "ok": False,
            "pipeline_id": pipeline_id,
            "error": str(exc),
        }


def list_backpack_summaries() -> list[dict[str, Any]]:
    """Return manifest summaries for all discovered backpacks."""
    try:
        registry = _registry()
        return [
            m.summary()
            for m in registry.discover()
            if m.kind == "backpack"
        ]
    except Exception:
        return []
