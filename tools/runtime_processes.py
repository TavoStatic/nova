from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import psutil


def normalize_identity_path(value: str | Path) -> str:
    try:
        return str(Path(value).resolve()).lower()
    except Exception:
        return str(value or "").strip().lower()


def matches_script_process(cmdline: list[str] | tuple[str, ...] | None, script_path: str | Path) -> bool:
    target = normalize_identity_path(script_path)
    for token in list(cmdline or []):
        if normalize_identity_path(token) == target:
            return True
    return False


def logical_service_processes(script_path: str | Path) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    parent_ids: set[int] = set()
    for process in psutil.process_iter(["pid", "ppid", "cmdline", "create_time"]):
        try:
            info = process.info or {}
            if not matches_script_process(info.get("cmdline"), script_path):
                continue
            pid = int(info.get("pid") or 0)
            ppid = int(info.get("ppid") or 0)
            create_time = float(info.get("create_time") or 0.0)
            matches.append({
                "pid": pid,
                "ppid": ppid,
                "create_time": create_time,
                "cmdline": list(info.get("cmdline") or []),
            })
            if ppid > 0:
                parent_ids.add(ppid)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess, ValueError, TypeError):
            continue
    logical = [item for item in matches if int(item.get("pid") or 0) not in parent_ids]
    return logical or matches


def select_logical_process(
    processes: list[dict[str, Any]],
    *,
    pid: int | None = None,
    create_time: float | None = None,
) -> dict[str, Any] | None:
    if not processes:
        return None
    if isinstance(pid, int) and pid > 0:
        for item in processes:
            if int(item.get("pid") or 0) != pid:
                continue
            item_create_time = float(item.get("create_time") or 0.0)
            if create_time is None or abs(item_create_time - float(create_time)) < 1.0:
                return item
    if isinstance(create_time, (int, float)):
        for item in processes:
            item_create_time = float(item.get("create_time") or 0.0)
            if abs(item_create_time - float(create_time)) < 1.0:
                return item
    return processes[0]


def read_identity_file(path: Path) -> tuple[int | None, float | None, dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8") or "{}")
    except Exception:
        return None, None, {}
    pid_raw = data.get("pid")
    pid: int | None = None
    if isinstance(pid_raw, int) and pid_raw > 0:
        pid = pid_raw
    elif isinstance(pid_raw, str) and pid_raw.isdigit():
        pid = int(pid_raw)
    create_time_raw = data.get("create_time")
    create_time = float(create_time_raw) if isinstance(create_time_raw, (int, float)) else None
    return pid, create_time, data
