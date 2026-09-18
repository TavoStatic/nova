from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _runtime_root(runtime_root: Path | None = None) -> Path:
    if runtime_root is not None:
        return Path(runtime_root)
    from services.nova_runtime_context import RUNTIME_DIR

    return Path(RUNTIME_DIR)


def backpack_settings_path(backpack_id: str, *, runtime_root: Path | None = None) -> Path:
    safe = "".join(ch for ch in str(backpack_id or "").strip() if ch.isalnum() or ch in {"_", "-"})
    return _runtime_root(runtime_root) / safe / "settings.json"


def backpack_runtime_installed(backpack_id: str, *, runtime_root: Path | None = None) -> bool:
    """True only when install residue exists. Package files under backpacks/ do not count."""
    return backpack_settings_path(backpack_id, runtime_root=runtime_root).is_file()


def backpack_uninstall_mark_path(backpack_id: str, *, runtime_root: Path | None = None) -> Path:
    safe = "".join(ch for ch in str(backpack_id or "").strip() if ch.isalnum() or ch in {"_", "-"})
    return _runtime_root(runtime_root) / "backpacks" / "uninstalled" / f"{safe}.json"


def write_backpack_uninstall_mark(
    backpack_id: str,
    *,
    runtime_root: Path | None = None,
    payload: dict[str, Any] | None = None,
) -> Path:
    path = backpack_uninstall_mark_path(backpack_id, runtime_root=runtime_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {"backpack_id": str(backpack_id or "").strip(), "status": "uninstalled"}
    if isinstance(payload, dict):
        body.update(payload)
    path.write_text(json.dumps(body, indent=2), encoding="utf-8")
    return path


def clear_backpack_uninstall_mark(backpack_id: str, *, runtime_root: Path | None = None) -> None:
    path = backpack_uninstall_mark_path(backpack_id, runtime_root=runtime_root)
    if path.is_file():
        path.unlink()
