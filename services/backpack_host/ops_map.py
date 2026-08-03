from __future__ import annotations

"""Map pipeline-level operation names to backpack operation ids (operations.json)."""

from pathlib import Path
from typing import Any

from services.backpack_host.grant_enforcer import load_operations


def pipeline_op_to_backpack_op(backpack_dir: Path, pipeline_operation: str) -> str | None:
    """
    Resolve a pipeline safe_query operation name to a backpack operation id.

    Returns None if no operations.json mapping exists for that pipeline op.
    """
    wanted = str(pipeline_operation or "").strip()
    if not wanted:
        return None
    for op in load_operations(backpack_dir):
        op_id = str(op.get("id") or "").strip()
        if not op_id:
            continue
        single = str(op.get("pipeline_operation") or "").strip()
        if single and single == wanted:
            return op_id
        multi = op.get("pipeline_operations") or []
        if isinstance(multi, list) and wanted in {str(x) for x in multi}:
            return op_id
    return None


def backpack_dir_for_pipeline_id(
    pipeline_id: str,
    *,
    backpacks_root: Path,
) -> Path | None:
    """Locate backpacks/<id> when pipeline_id matches backpack.json pipeline_id or id."""
    root = Path(backpacks_root)
    if not root.is_dir():
        return None
    wanted = str(pipeline_id or "").strip().lower()
    if not wanted:
        return None
    # Fast path: folder name == id
    direct = root / wanted
    if (direct / "backpack.json").is_file():
        return direct
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        path = child / "backpack.json"
        if not path.is_file():
            continue
        try:
            import json

            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        pid = str(data.get("pipeline_id") or data.get("id") or "").strip().lower()
        bid = str(data.get("id") or "").strip().lower()
        if wanted in {pid, bid}:
            return child
    return None


def resolve_shell_role(
    *,
    role: str | None = None,
    is_admin: bool = False,
    context_extra: dict[str, Any] | None = None,
    policy: dict[str, Any] | None = None,
) -> str:
    """
    Resolve a Shell role string for grant checks.

    Priority: explicit role → context.extra.shell_role → policy.role →
    account_admin if is_admin else standard_user.
    """
    if role and str(role).strip():
        return str(role).strip()
    extra = context_extra or {}
    for key in ("shell_role", "role", "nova_shell_role"):
        value = extra.get(key)
        if value and str(value).strip():
            return str(value).strip()
    pol = policy or {}
    for key in ("shell_role", "role"):
        value = pol.get(key)
        if value and str(value).strip():
            return str(value).strip()
    if is_admin:
        return "account_admin"
    return "standard_user"
