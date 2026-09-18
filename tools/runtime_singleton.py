"""Cross-process singleton for Nova long-running roles.

Windows uses a named mutex (same pattern as the setup wizard). Other
platforms use an exclusive lock file under runtime/. One process per role.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

_HOLDINGS: dict[str, tuple[str, Any]] = {}


def _role_key(role: str) -> str:
    return str(role or "").strip().lower().replace(" ", "-")


def _mutex_name(role: str) -> str:
    return f"Local\\NovaRuntime-{_role_key(role)}"


def _lock_path(role: str, runtime_dir: Path) -> Path:
    return Path(runtime_dir) / f"{_role_key(role)}.singleton.lock"


def acquire_role_singleton(
    role: str,
    *,
    runtime_dir: Path | None = None,
    use_mutex: bool | None = None,
) -> tuple[bool, str]:
    """Claim this process as the only live owner of `role`.

    Returns (True, reason) on success. A second caller gets (False, reason).
    """
    key = _role_key(role)
    if not key:
        return False, "role_required"
    if key in _HOLDINGS:
        return True, "already_held_in_process"

    if use_mutex is None:
        use_mutex = os.name == "nt"
    if use_mutex and os.name == "nt":
        ok, detail, handle = _acquire_windows_mutex(key)
        if ok and handle is not None:
            _HOLDINGS[key] = ("mutex", handle)
            return True, detail
        if not ok:
            return False, detail

    root = Path(runtime_dir) if runtime_dir is not None else Path(__file__).resolve().parents[1] / "runtime"
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    path = _lock_path(key, root)
    try:
        handle = open(path, "x", encoding="utf-8")
    except FileExistsError:
        existing = _read_lock_pid(path)
        if existing > 0 and _pid_is_alive(existing):
            return False, f"already_running pid={existing}"
        try:
            path.unlink()
        except OSError:
            return False, "lock_busy"
        try:
            handle = open(path, "x", encoding="utf-8")
        except FileExistsError:
            return False, "already_running"
    except OSError as exc:
        return False, f"lock_failed:{exc}"
    try:
        handle.write(str(os.getpid()))
        handle.flush()
    except OSError:
        pass
    _HOLDINGS[key] = ("file", (handle, path))
    return True, f"lock_acquired:{path.name}"


def release_role_singleton(role: str) -> None:
    key = _role_key(role)
    held = _HOLDINGS.pop(key, None)
    if not held:
        return
    kind, payload = held
    try:
        if kind == "mutex" and os.name == "nt":
            import ctypes

            ctypes.windll.kernel32.CloseHandle(payload)
        elif kind == "file":
            handle, path = payload
            try:
                handle.close()
            except OSError:
                pass
            try:
                path.unlink()
            except OSError:
                pass
    except Exception:
        pass


def _acquire_windows_mutex(role: str) -> tuple[bool, str, object | None]:
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.CreateMutexW(None, False, _mutex_name(role))
        last_error = int(kernel32.GetLastError() or 0)
        error_already_exists = 183
        if not handle:
            return False, "mutex_create_failed", None
        if last_error == error_already_exists:
            kernel32.CloseHandle(handle)
            return False, "already_running", None
        return True, "mutex_acquired", handle
    except Exception as exc:
        return False, f"mutex_failed:{exc}", None


def _read_lock_pid(path: Path) -> int:
    try:
        raw = path.read_text(encoding="utf-8").strip()
        return int(raw) if raw.isdigit() else 0
    except Exception:
        return 0


def _pid_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        import psutil

        return bool(psutil.pid_exists(pid))
    except Exception:
        return False
