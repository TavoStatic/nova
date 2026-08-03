from __future__ import annotations

"""
Backpack Grant Enforcer

Reads operations.json and resolves whether a Nova Shell role is granted
a specific backpack operation.

Layer model:
  Nova Shell role (account_admin, standard_user, etc.)
      ↓
  operations.json default_grants[role]  ← this module enforces
      ↓
  pipeline.safe_query() / tool.run()

The Shell's coarse permissions (backpacks.run, backpacks.view) get the
caller to the door. This module decides which door they can open.

Custom role grants (per-user, per-backpack overrides) are a future
extension — they would shadow default_grants when present in the Shell store.
"""

import json
from pathlib import Path
from typing import Any


def _read_operations_list(backpack_dir: Path) -> list[dict[str, Any]]:
    path = Path(backpack_dir) / "operations.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(data, dict):
        return []
    return [op for op in (data.get("operations") or []) if isinstance(op, dict)]


def load_operations(backpack_dir: Path) -> list[dict[str, Any]]:
    """Return the full operations list from operations.json."""
    return _read_operations_list(backpack_dir)


def check_grant(backpack_dir: Path, operation_id: str, role: str) -> bool:
    """
    Return True if `role` has a default_grant for `operation_id`.

    Returns False for unknown operations or unknown roles.
    """
    for op in _read_operations_list(backpack_dir):
        if str(op.get("id") or "") != operation_id:
            continue
        grants = op.get("default_grants") or {}
        return bool(grants.get(role, False))
    return False


def require_grant(backpack_dir: Path, operation_id: str, role: str) -> None:
    """
    Raise PermissionError if role is not granted operation_id.

    Used as a gate before running any pipeline operation or tool action.
    """
    if not check_grant(backpack_dir, operation_id, role):
        raise PermissionError(
            f"backpack_grant_denied:operation={operation_id}:role={role}"
        )


def list_allowed_operations(backpack_dir: Path, role: str) -> list[str]:
    """Return all operation ids the role is granted in this backpack."""
    return [
        str(op.get("id") or "")
        for op in _read_operations_list(backpack_dir)
        if bool((op.get("default_grants") or {}).get(role, False))
        and str(op.get("id") or "")
    ]


def operation_summary(backpack_dir: Path, role: str) -> dict[str, Any]:
    """
    Return a summary of all operations and whether the role is granted each one.

    Useful for rendering the UI: which buttons does this user see?
    """
    ops = _read_operations_list(backpack_dir)
    return {
        "role": role,
        "operation_count": len(ops),
        "operations": [
            {
                "id": str(op.get("id") or ""),
                "label": str(op.get("label") or ""),
                "description": str(op.get("description") or ""),
                "read_only": bool(op.get("read_only", True)),
                "granted": bool((op.get("default_grants") or {}).get(role, False)),
            }
            for op in ops
        ],
    }
