"""Validation-runtime bootstrap for operator probes.

Must run before importing autonomy_maintenance or other modules that bind
RUNTIME_DIR at import time.
"""
from __future__ import annotations

import os
from pathlib import Path


def validation_runtime_dir(base_dir: Path) -> Path:
    return (base_dir / "runtime" / "validation").resolve()


def apply_validation_probe_env(base_dir: Path) -> dict[str, str | None]:
    """Pin probe execution to the validation runtime scope."""
    base = Path(base_dir).resolve()
    validation_runtime = validation_runtime_dir(base)
    validation_runtime.mkdir(parents=True, exist_ok=True)
    (validation_runtime / "_internal").mkdir(parents=True, exist_ok=True)

    previous: dict[str, str | None] = {}
    keys = (
        "NOVA_TEST_RUNNER",
        "NOVA_VALIDATION_RUNTIME_DIR",
        "NOVA_WORK_TREE_DB",
        "NOVA_MEMORY_DB",
    )
    for key in keys:
        previous[key] = os.environ.get(key)

    os.environ["NOVA_TEST_RUNNER"] = "1"
    os.environ["NOVA_VALIDATION_RUNTIME_DIR"] = str(validation_runtime)
    os.environ.setdefault("NOVA_WORK_TREE_DB", str(validation_runtime / "_internal" / "work_tree.db"))
    os.environ.setdefault("NOVA_MEMORY_DB", str(validation_runtime / "nova_memory.sqlite"))
    return previous


def restore_probe_env(previous: dict[str, str | None]) -> None:
    for key, value in previous.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value