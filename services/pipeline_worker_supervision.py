from __future__ import annotations

import json
import os
import signal
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Callable, Mapping

from services.nova_runtime_context import RUNTIME_DIR

DEFAULT_HEARTBEAT_STALE_SEC = 120
_LEASE_LOCKS: dict[str, threading.RLock] = {}
_LEASE_LOCK_GUARD = threading.Lock()


def _sanitize_pipeline_id(pipeline_id: str) -> str:
    text = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in str(pipeline_id or "").strip())
    return text or "unknown_pipeline"


def _normalize_runtime_root(runtime_root: Path | None) -> Path:
    return (runtime_root or RUNTIME_DIR).resolve()


def _lease_scope_key(pipeline_id: str, runtime_root: Path | None) -> str:
    slug = _sanitize_pipeline_id(pipeline_id)
    root = _normalize_runtime_root(runtime_root)
    return f"{slug}@{root}"


def _lease_lock(scope_key: str) -> threading.RLock:
    with _LEASE_LOCK_GUARD:
        lock = _LEASE_LOCKS.get(scope_key)
        if lock is None:
            lock = threading.RLock()
            _LEASE_LOCKS[scope_key] = lock
        return lock


def worker_heartbeat_path(pipeline_id: str, *, runtime_root: Path | None = None) -> Path:
    slug = _sanitize_pipeline_id(pipeline_id)
    return _normalize_runtime_root(runtime_root) / "pipelines" / slug / "worker.heartbeat"


def worker_lease_path(pipeline_id: str, *, runtime_root: Path | None = None) -> Path:
    slug = _sanitize_pipeline_id(pipeline_id)
    return _normalize_runtime_root(runtime_root) / "pipelines" / slug / "worker.lease.json"


def worker_spawn_error_log_path(pipeline_id: str, *, runtime_root: Path | None = None) -> Path:
    slug = _sanitize_pipeline_id(pipeline_id)
    return _normalize_runtime_root(runtime_root) / "pipelines" / slug / "worker.spawn.err.log"


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    tmp_path.write_text(text, encoding="utf-8")
    contended = {5, 13}
    for attempt in range(8):
        try:
            tmp_path.replace(path)
            return
        except OSError as exc:
            winerror = getattr(exc, "winerror", None)
            if winerror not in contended and exc.errno not in contended:
                raise
            time.sleep(0.05 * (attempt + 1))
    path.write_text(text, encoding="utf-8")
    try:
        tmp_path.unlink(missing_ok=True)
    except Exception:
        pass


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    _atomic_write_text(path, json.dumps(dict(payload), ensure_ascii=True, indent=2))


def _read_json_file(path: Path) -> dict[str, Any]:
    """Best-effort JSON read. Never raise — lease/heartbeat I/O is racy on Windows."""
    try:
        if not path.exists():
            return {}
    except OSError:
        return {}
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    except Exception:
        return {}
    try:
        payload = json.loads(raw)
    except Exception:
        return {}
    return dict(payload) if isinstance(payload, dict) else {}


def pid_alive(pid: int | None, *, pid_alive_fn: Callable[[int], bool] | None = None) -> bool:
    if pid is None:
        return False
    try:
        resolved = int(pid)
    except Exception:
        return False
    if resolved <= 0:
        return False
    if pid_alive_fn is not None:
        return bool(pid_alive_fn(resolved))
    try:
        os.kill(resolved, 0)
    except OSError:
        return False
    except Exception:
        return False
    return True


def read_worker_lease(
    pipeline_id: str,
    *,
    runtime_root: Path | None = None,
    pid_alive_fn: Callable[[int], bool] | None = None,
) -> dict[str, Any]:
    path = worker_lease_path(pipeline_id, runtime_root=runtime_root)
    payload = _read_json_file(path)
    owner_pid = payload.get("lease_owner_pid", payload.get("owner_pid"))
    try:
        owner_pid = int(owner_pid) if owner_pid is not None else None
    except Exception:
        owner_pid = None
    lease_live = pid_alive(owner_pid, pid_alive_fn=pid_alive_fn)
    return {
        "pipeline_id": str(pipeline_id or "").strip(),
        "present": path.exists(),
        "path": str(path),
        "lease_owner_pid": owner_pid,
        "lease_live": lease_live,
        "claimed_at": int(payload.get("claimed_at") or 0),
        "generation": int(payload.get("generation") or 0),
        "runtime_root": str(_normalize_runtime_root(runtime_root)),
        "scope_key": _lease_scope_key(pipeline_id, runtime_root),
    }


def write_worker_lease(
    pipeline_id: str,
    *,
    runtime_root: Path | None = None,
    lease_owner_pid: int | None = None,
    generation: int | None = None,
    now_fn: Callable[[], float] = time.time,
) -> dict[str, Any]:
    path = worker_lease_path(pipeline_id, runtime_root=runtime_root)
    existing = _read_json_file(path)
    resolved_pid = lease_owner_pid
    if resolved_pid is None:
        try:
            resolved_pid = int(os.getpid())
        except Exception:
            resolved_pid = None
    next_generation = int(generation if generation is not None else int(existing.get("generation") or 0) + 1)
    payload = {
        "pipeline_id": str(pipeline_id or "").strip(),
        "runtime_root": str(_normalize_runtime_root(runtime_root)),
        "lease_owner_pid": resolved_pid,
        "claimed_at": int(now_fn()),
        "generation": max(1, next_generation),
    }
    _atomic_write_json(path, payload)
    payload["path"] = str(path)
    payload["lease_live"] = pid_alive(resolved_pid)
    return payload


def release_worker_lease(
    pipeline_id: str,
    *,
    runtime_root: Path | None = None,
    expected_owner_pid: int | None = None,
) -> bool:
    path = worker_lease_path(pipeline_id, runtime_root=runtime_root)
    try:
        if not path.exists():
            return False
    except OSError:
        return False
    if expected_owner_pid is not None:
        payload = _read_json_file(path)
        try:
            owner = int(payload.get("lease_owner_pid") or 0)
        except Exception:
            owner = 0
        try:
            expected = int(expected_owner_pid)
        except Exception:
            return False
        if owner != expected:
            return False
    try:
        path.unlink(missing_ok=True)
        return True
    except OSError:
        return False
    except Exception:
        return False


def _try_create_lease_file(path: Path, payload: dict[str, Any]) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = getattr(os, "O_CREAT", 0) | getattr(os, "O_EXCL", 0) | getattr(os, "O_WRONLY", 0)
    try:
        fd = os.open(str(path), flags)
    except FileExistsError:
        return False
    except Exception:
        return False
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=True, indent=2)
        return True
    except Exception:
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass
        return False


def acquire_worker_lease(
    pipeline_id: str,
    *,
    runtime_root: Path | None = None,
    candidate_owner_pid: int | None = None,
    now_fn: Callable[[], float] = time.time,
    pid_alive_fn: Callable[[int], bool] | None = None,
) -> dict[str, Any]:
    scope_key = _lease_scope_key(pipeline_id, runtime_root)
    path = worker_lease_path(pipeline_id, runtime_root=runtime_root)
    with _lease_lock(scope_key):
        existing = read_worker_lease(pipeline_id, runtime_root=runtime_root, pid_alive_fn=pid_alive_fn)
        owner_pid = existing.get("lease_owner_pid")
        if existing.get("present") and existing.get("lease_live"):
            if candidate_owner_pid is not None and int(owner_pid or 0) == int(candidate_owner_pid):
                return {
                    "ok": True,
                    "status": "already_owned",
                    "pipeline_id": str(pipeline_id or "").strip(),
                    "lease": existing,
                }
            return {
                "ok": False,
                "status": "duplicate_ownership",
                "pipeline_id": str(pipeline_id or "").strip(),
                "lease": existing,
                "conflicting_owner_pid": owner_pid,
            }

        if existing.get("present") and not existing.get("lease_live"):
            try:
                path.unlink(missing_ok=True)
            except Exception:
                pass

        resolved_pid = candidate_owner_pid
        if resolved_pid is None:
            try:
                resolved_pid = int(os.getpid())
            except Exception:
                resolved_pid = None
        generation = int(existing.get("generation") or 0) + 1
        payload = {
            "pipeline_id": str(pipeline_id or "").strip(),
            "runtime_root": str(_normalize_runtime_root(runtime_root)),
            "lease_owner_pid": resolved_pid,
            "claimed_at": int(now_fn()),
            "generation": max(1, generation),
        }
        if not _try_create_lease_file(path, payload):
            reread = read_worker_lease(pipeline_id, runtime_root=runtime_root, pid_alive_fn=pid_alive_fn)
            if reread.get("lease_live"):
                return {
                    "ok": True,
                    "status": "already_owned",
                    "pipeline_id": str(pipeline_id or "").strip(),
                    "lease": reread,
                }
            return {
                "ok": False,
                "status": "duplicate_ownership",
                "pipeline_id": str(pipeline_id or "").strip(),
                "lease": reread,
                "conflicting_owner_pid": reread.get("lease_owner_pid"),
            }
        payload["path"] = str(path)
        payload["lease_live"] = pid_alive(resolved_pid, pid_alive_fn=pid_alive_fn)
        return {
            "ok": True,
            "status": "acquired",
            "pipeline_id": str(pipeline_id or "").strip(),
            "lease": payload,
        }


def write_worker_heartbeat(
    pipeline_id: str,
    *,
    runtime_root: Path | None = None,
    status: str = "running",
    detail: str = "",
    pid: int | None = None,
    now_fn: Callable[[], float] = time.time,
) -> dict[str, Any]:
    path = worker_heartbeat_path(pipeline_id, runtime_root=runtime_root)
    resolved_pid = pid
    if resolved_pid is None:
        try:
            resolved_pid = int(os.getpid())
        except Exception:
            resolved_pid = None
    lease = read_worker_lease(pipeline_id, runtime_root=runtime_root)
    try:
        lease_owner_int = int(lease.get("lease_owner_pid") or 0)
    except Exception:
        lease_owner_int = 0
    try:
        resolved_int = int(resolved_pid or 0)
    except Exception:
        resolved_int = 0
    foreign_live_lease = bool(lease.get("lease_live")) and lease_owner_int > 0 and lease_owner_int != resolved_int
    payload = {
        "pipeline_id": str(pipeline_id or "").strip(),
        "status": str(status or "running").strip() or "running",
        "detail": str(detail or "").strip(),
        "updated_at": int(now_fn()),
        "pid": resolved_pid,
        "runtime_root": str(_normalize_runtime_root(runtime_root)),
        "lease_owner_pid": lease_owner_int if foreign_live_lease else resolved_pid,
    }
    _atomic_write_json(path, payload)
    if not foreign_live_lease and (
        not lease.get("lease_live") or lease_owner_int != resolved_int
    ):
        write_worker_lease(
            pipeline_id,
            runtime_root=runtime_root,
            lease_owner_pid=resolved_pid,
            generation=int(lease.get("generation") or 0),
            now_fn=now_fn,
        )
    payload["path"] = str(path)
    return payload


def read_worker_heartbeat(
    pipeline_id: str,
    *,
    runtime_root: Path | None = None,
    stale_after_sec: int = DEFAULT_HEARTBEAT_STALE_SEC,
    now_fn: Callable[[], float] = time.time,
    pid_alive_fn: Callable[[int], bool] | None = None,
) -> dict[str, Any]:
    path = worker_heartbeat_path(pipeline_id, runtime_root=runtime_root)
    lease = read_worker_lease(pipeline_id, runtime_root=runtime_root, pid_alive_fn=pid_alive_fn)
    if not path.exists():
        return {
            "pipeline_id": str(pipeline_id or "").strip(),
            "present": False,
            "fresh": False,
            "status": "missing",
            "detail": "privileged_worker_heartbeat_missing",
            "updated_at": 0,
            "age_sec": None,
            "stale_after_sec": max(1, int(stale_after_sec)),
            "path": str(path),
            "lease": lease,
            "lease_owner_pid": lease.get("lease_owner_pid"),
            "lease_live": bool(lease.get("lease_live")),
            "supervised_ok": False,
        }

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {
            "pipeline_id": str(pipeline_id or "").strip(),
            "present": True,
            "fresh": False,
            "status": "unreadable",
            "detail": str(exc),
            "updated_at": 0,
            "age_sec": None,
            "stale_after_sec": max(1, int(stale_after_sec)),
            "path": str(path),
            "lease": lease,
            "lease_owner_pid": lease.get("lease_owner_pid"),
            "lease_live": bool(lease.get("lease_live")),
            "supervised_ok": False,
        }

    if not isinstance(payload, dict):
        payload = {}

    updated_at = int(payload.get("updated_at") or 0)
    age_sec = max(0, int(now_fn()) - updated_at) if updated_at > 0 else None
    fresh = age_sec is not None and age_sec <= max(1, int(stale_after_sec))
    status = str(payload.get("status") or "unknown").strip() or "unknown"
    heartbeat_pid = payload.get("pid")
    try:
        heartbeat_pid = int(heartbeat_pid) if heartbeat_pid is not None else None
    except Exception:
        heartbeat_pid = None
    lease_owner_pid = lease.get("lease_owner_pid")
    lease_live = bool(lease.get("lease_live"))
    pid_matches_lease = (
        heartbeat_pid is not None
        and lease_owner_pid is not None
        and int(heartbeat_pid) == int(lease_owner_pid)
    )
    supervised_ok = fresh and status in {"running", "idle", "ok"} and lease_live and pid_matches_lease
    return {
        "pipeline_id": str(pipeline_id or "").strip(),
        "present": True,
        "fresh": fresh,
        "supervised_ok": supervised_ok,
        "status": status,
        "detail": str(payload.get("detail") or "").strip(),
        "updated_at": updated_at,
        "age_sec": age_sec,
        "stale_after_sec": max(1, int(stale_after_sec)),
        "pid": heartbeat_pid,
        "path": str(path),
        "lease": lease,
        "lease_owner_pid": lease_owner_pid,
        "lease_live": lease_live,
        "pid_matches_lease": pid_matches_lease,
    }


def _duplicate_ownership_result(
    pipeline_id: str,
    *,
    heartbeat: dict[str, Any],
    lease: dict[str, Any],
    conflicting_owner_pid: int | None = None,
) -> dict[str, Any]:
    owner = conflicting_owner_pid
    if owner is None:
        owner = lease.get("lease_owner_pid") or heartbeat.get("lease_owner_pid")
    return {
        "ok": False,
        "status": "duplicate_ownership",
        "pipeline_id": str(pipeline_id or "").strip(),
        "conflicting_owner_pid": owner,
        "heartbeat": heartbeat,
        "lease": lease,
    }


def ensure_pipeline_worker_running(
    pipeline_id: str,
    *,
    worker_script: Path,
    venv_python: Path,
    runtime_root: Path | None = None,
    data_sources_root: Path | None = None,
    subprocess_module=None,
    os_name: str | None = None,
    pid_alive_fn: Callable[[int], bool] | None = None,
) -> dict[str, Any]:
    scope_key = _lease_scope_key(pipeline_id, runtime_root)
    with _lease_lock(scope_key):
        heartbeat = read_worker_heartbeat(
            pipeline_id,
            runtime_root=runtime_root,
            pid_alive_fn=pid_alive_fn,
        )
        lease = dict(heartbeat.get("lease") or read_worker_lease(pipeline_id, runtime_root=runtime_root, pid_alive_fn=pid_alive_fn))
        if heartbeat.get("supervised_ok"):
            return {
                "ok": True,
                "status": "already_running",
                "pipeline_id": str(pipeline_id or "").strip(),
                "heartbeat": heartbeat,
                "lease": lease,
            }
        if lease.get("lease_live"):
            return _duplicate_ownership_result(
                pipeline_id,
                heartbeat=heartbeat,
                lease=lease,
            )

        worker_script = Path(worker_script)
        venv_python = Path(venv_python)
        if not worker_script.exists():
            return {
                "ok": False,
                "status": "worker_script_missing",
                "pipeline_id": str(pipeline_id or "").strip(),
                "detail": str(worker_script),
                "heartbeat": heartbeat,
                "lease": lease,
            }
        if not venv_python.exists():
            return {
                "ok": False,
                "status": "venv_python_missing",
                "pipeline_id": str(pipeline_id or "").strip(),
                "detail": str(venv_python),
                "heartbeat": heartbeat,
                "lease": lease,
            }

        import subprocess as subprocess_fallback

        subprocess_module = subprocess_module or subprocess_fallback
        os_name = os_name or os.name
        try:
            script_path = Path(worker_script).resolve()
        except OSError:
            script_path = Path(worker_script)
        # scripts/pipeline_worker.py → repo root; never rely on fragile multi-parent chains mid-exception.
        if script_path.name == "pipeline_worker.py" and script_path.parent.name == "scripts":
            base_dir = script_path.parent.parent
        else:
            base_dir = script_path.parent
        try:
            data_root = Path(data_sources_root) if data_sources_root is not None else (base_dir / "data_sources")
            data_root_str = str(data_root)
            runtime_root_str = str(_normalize_runtime_root(runtime_root))
            venv_str = str(venv_python)
            script_str = str(script_path)
        except Exception as exc:
            return {
                "ok": False,
                "status": "start_failed",
                "pipeline_id": str(pipeline_id or "").strip(),
                "detail": f"path_resolve_failed:{type(exc).__name__}",
                "heartbeat": heartbeat,
                "lease": lease,
            }
        args = [
            venv_str,
            script_str,
            "--pipeline",
            str(pipeline_id or "").strip(),
            "--runtime-root",
            runtime_root_str,
            "--data-sources-root",
            data_root_str,
        ]
        lease_acquire = acquire_worker_lease(
            pipeline_id,
            runtime_root=runtime_root,
            candidate_owner_pid=0,
            pid_alive_fn=pid_alive_fn,
        )
        if lease_acquire.get("status") == "duplicate_ownership":
            return _duplicate_ownership_result(
                pipeline_id,
                heartbeat=heartbeat,
                lease=dict(lease_acquire.get("lease") or {}),
                conflicting_owner_pid=lease_acquire.get("conflicting_owner_pid"),
            )
        spawn_err_path = worker_spawn_error_log_path(pipeline_id, runtime_root=runtime_root)
        try:
            if os_name == "nt":
                creationflags = getattr(subprocess_module, "CREATE_NEW_PROCESS_GROUP", 0)
                proc = subprocess_module.Popen(
                    args,
                    cwd=str(base_dir),
                    stdout=subprocess_module.DEVNULL,
                    stderr=subprocess_module.DEVNULL,
                    creationflags=creationflags,
                )
            else:
                proc = subprocess_module.Popen(
                    args,
                    cwd=str(base_dir),
                    stdout=subprocess_module.DEVNULL,
                    stderr=subprocess_module.DEVNULL,
                    start_new_session=True,
                )
            release_worker_lease(pipeline_id, runtime_root=runtime_root, expected_owner_pid=0)
            launcher_pid = int(getattr(proc, "pid", 0) or 0) or None
            deadline = time.time() + 15.0
            verified_heartbeat: dict[str, Any] = {}
            child_pid: int | None = None
            while time.time() < deadline:
                verified_heartbeat = read_worker_heartbeat(
                    pipeline_id,
                    runtime_root=runtime_root,
                    pid_alive_fn=pid_alive_fn,
                )
                if bool(verified_heartbeat.get("supervised_ok")):
                    try:
                        child_pid = int(verified_heartbeat.get("pid") or 0) or None
                    except Exception:
                        child_pid = None
                    if child_pid:
                        break
                if launcher_pid is not None and proc.poll() is not None:
                    err_tail = ""
                    try:
                        worker_error_path = spawn_err_path.parent / "worker.error.log"
                        if worker_error_path.exists():
                            err_tail = worker_error_path.read_text(encoding="utf-8")[-1000:]
                    except Exception:
                        err_tail = ""
                    release_worker_lease(pipeline_id, runtime_root=runtime_root)
                    return {
                        "ok": False,
                        "status": "start_failed",
                        "pipeline_id": str(pipeline_id or "").strip(),
                        "detail": "child_exited_before_supervision",
                        "spawn_error_tail": err_tail,
                        "child_pid": launcher_pid,
                        "heartbeat": verified_heartbeat,
                        "lease": read_worker_lease(
                            pipeline_id,
                            runtime_root=runtime_root,
                            pid_alive_fn=pid_alive_fn,
                        ),
                    }
                time.sleep(0.25)
            if not child_pid or not bool(verified_heartbeat.get("supervised_ok")):
                release_worker_lease(pipeline_id, runtime_root=runtime_root)
                return {
                    "ok": False,
                    "status": "start_failed",
                    "pipeline_id": str(pipeline_id or "").strip(),
                    "detail": "worker_supervision_timeout",
                    "child_pid": launcher_pid,
                    "heartbeat": verified_heartbeat or read_worker_heartbeat(
                        pipeline_id,
                        runtime_root=runtime_root,
                        pid_alive_fn=pid_alive_fn,
                    ),
                    "lease": read_worker_lease(
                        pipeline_id,
                        runtime_root=runtime_root,
                        pid_alive_fn=pid_alive_fn,
                    ),
                }
            lease_payload = read_worker_lease(
                pipeline_id,
                runtime_root=runtime_root,
                pid_alive_fn=pid_alive_fn,
            )
            return {
                "ok": True,
                "status": "start_requested",
                "pipeline_id": str(pipeline_id or "").strip(),
                "child_pid": child_pid,
                "launcher_pid": launcher_pid,
                "lease_owner_pid": lease_payload.get("lease_owner_pid"),
                "supervision_verified": True,
                "heartbeat": verified_heartbeat,
                "lease": lease_payload,
            }
        except Exception as exc:
            release_worker_lease(pipeline_id, runtime_root=runtime_root)
            return {
                "ok": False,
                "status": "start_failed",
                "pipeline_id": str(pipeline_id or "").strip(),
                "detail": str(exc),
                "heartbeat": heartbeat,
                "lease": lease,
            }



def ensure_pipeline_workers_for_ids(
    pipeline_ids: list[str],
    *,
    worker_script: Path,
    venv_python: Path,
    runtime_root: Path | None = None,
    data_sources_root: Path | None = None,
    subprocess_module=None,
    os_name: str | None = None,
    pid_alive_fn: Callable[[int], bool] | None = None,
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for pipeline_id in pipeline_ids:
        clean_id = str(pipeline_id or "").strip()
        if not clean_id:
            continue
        # One pipeline must not abort ensure for all others or kill the maintenance cycle.
        try:
            results.append(
                ensure_pipeline_worker_running(
                    clean_id,
                    worker_script=worker_script,
                    venv_python=venv_python,
                    runtime_root=runtime_root,
                    data_sources_root=data_sources_root,
                    subprocess_module=subprocess_module,
                    os_name=os_name,
                    pid_alive_fn=pid_alive_fn,
                )
            )
        except Exception as exc:
            try:
                detail = f"{type(exc).__name__}: {exc}"
            except Exception:
                detail = type(exc).__name__
            results.append(
                {
                    "ok": False,
                    "status": "start_failed",
                    "pipeline_id": clean_id,
                    "detail": detail,
                    "heartbeat": {},
                    "lease": {},
                }
            )
    started = [item for item in results if item.get("status") == "start_requested"]
    running = [item for item in results if item.get("status") == "already_running"]
    duplicate = [item for item in results if item.get("status") == "duplicate_ownership"]
    failed = [item for item in results if not item.get("ok")]
    if failed:
        aggregate = "partial" if running or started or duplicate else "failed"
    elif duplicate:
        aggregate = "duplicate_ownership"
    elif started:
        aggregate = "started"
    else:
        aggregate = "ok"
    return {
        "ok": not failed,
        "status": aggregate,
        "worker_count": len(results),
        "started_count": len(started),
        "running_count": len(running),
        "duplicate_count": len(duplicate),
        "failed_count": len(failed),
        "workers": results,
    }


def summarize_pipeline_workers(
    pipeline_ids: list[str],
    *,
    runtime_root: Path | None = None,
    stale_after_sec: int = DEFAULT_HEARTBEAT_STALE_SEC,
    now_fn: Callable[[], float] = time.time,
    pid_alive_fn: Callable[[int], bool] | None = None,
) -> dict[str, Any]:
    workers = [
        read_worker_heartbeat(
            pipeline_id,
            runtime_root=runtime_root,
            stale_after_sec=stale_after_sec,
            now_fn=now_fn,
            pid_alive_fn=pid_alive_fn,
        )
        for pipeline_id in pipeline_ids
        if str(pipeline_id or "").strip()
    ]
    supervised = [item for item in workers if bool(item.get("supervised_ok"))]
    stale = [item for item in workers if item.get("present") and not item.get("fresh")]
    missing = [item for item in workers if not item.get("present")]
    duplicate = [
        item
        for item in workers
        if item.get("lease_live") and not bool(item.get("supervised_ok")) and item.get("present")
    ]
    if not workers:
        aggregate_status = "none"
    elif duplicate:
        aggregate_status = "duplicate_ownership"
    elif len(supervised) == len(workers):
        aggregate_status = "ok"
    elif supervised:
        aggregate_status = "partial"
    elif stale:
        aggregate_status = "stale"
    else:
        aggregate_status = "missing"
    return {
        "status": aggregate_status,
        "worker_count": len(workers),
        "supervised_count": len(supervised),
        "stale_count": len(stale),
        "missing_count": len(missing),
        "duplicate_count": len(duplicate),
        "stale_after_sec": max(1, int(stale_after_sec)),
        "workers": workers,
    }


def _cmdline_declares_pipeline(cmdline: list[str], pipeline_id: str) -> bool:
    normalized_id = str(pipeline_id or "").strip()
    if not normalized_id:
        return False
    args = [str(arg or "") for arg in cmdline]
    for index, arg in enumerate(args):
        if arg == "--pipeline" and index + 1 < len(args) and str(args[index + 1]).strip() == normalized_id:
            return True
    return False


def pipeline_worker_processes_for_id(
    pipeline_id: str,
    *,
    worker_script: Path | None = None,
) -> list[dict[str, Any]]:
    from tools.runtime_processes import logical_service_processes

    script = worker_script or Path(__file__).resolve().parents[1] / "scripts" / "pipeline_worker.py"
    matches: list[dict[str, Any]] = []
    for item in logical_service_processes(script):
        cmdline = [str(part or "") for part in list(item.get("cmdline") or [])]
        if _cmdline_declares_pipeline(cmdline, pipeline_id):
            matches.append(dict(item))
    return matches


def reconcile_duplicate_pipeline_worker_processes(
    pipeline_id: str,
    *,
    keeper_pid: int | None,
    worker_script: Path | None = None,
    terminate_pid_fn: Callable[[int], bool] | None = None,
    os_name: str | None = None,
) -> dict[str, Any]:
    try:
        keeper = int(keeper_pid or 0)
    except Exception:
        keeper = 0
    processes = pipeline_worker_processes_for_id(pipeline_id, worker_script=worker_script)
    terminated: list[int] = []
    terminator = terminate_pid_fn or (lambda pid: _default_terminate_pid(pid, os_name=os_name))
    for item in processes:
        try:
            pid = int(item.get("pid") or 0)
        except Exception:
            continue
        if pid <= 0 or (keeper > 0 and pid == keeper):
            continue
        if terminator(pid):
            terminated.append(pid)
    return {
        "pipeline_id": str(pipeline_id or "").strip(),
        "process_count": len(processes),
        "keeper_pid": keeper or None,
        "terminated_pids": terminated,
        "terminated_count": len(terminated),
    }


def _default_terminate_pid(pid: int, *, os_name: str | None = None) -> bool:
    try:
        resolved = int(pid)
    except Exception:
        return False
    if resolved <= 0:
        return False
    platform = os_name or os.name
    if platform == "nt":
        proc = subprocess.run(
            ["taskkill", "/PID", str(resolved), "/T", "/F"],
            capture_output=True,
            text=True,
        )
        return int(proc.returncode or 0) == 0
    try:
        os.kill(resolved, signal.SIGTERM)
        return True
    except Exception:
        return False


def _cleanup_worker_artifact_tmp_files(pipeline_id: str, *, runtime_root: Path | None = None) -> list[str]:
    pipeline_dir = worker_heartbeat_path(pipeline_id, runtime_root=runtime_root).parent
    removed: list[str] = []
    if not pipeline_dir.exists():
        return removed
    for candidate in sorted(pipeline_dir.glob("worker.heartbeat.*.tmp")):
        try:
            candidate.unlink(missing_ok=True)
            removed.append(str(candidate))
        except Exception:
            continue
    return removed


def _remove_worker_heartbeat(pipeline_id: str, *, runtime_root: Path | None = None) -> bool:
    path = worker_heartbeat_path(pipeline_id, runtime_root=runtime_root)
    try:
        path.unlink(missing_ok=True)
        return not path.exists()
    except Exception:
        return False


def reconcile_pipeline_worker_scope(
    pipeline_id: str,
    *,
    runtime_root: Path | None = None,
    stale_after_sec: int = DEFAULT_HEARTBEAT_STALE_SEC,
    reclaim_stale_live: bool = True,
    now_fn: Callable[[], float] = time.time,
    pid_alive_fn: Callable[[int], bool] | None = None,
    terminate_pid_fn: Callable[[int], bool] | None = None,
    os_name: str | None = None,
) -> dict[str, Any]:
    """Clear dead leases and optionally reclaim live-but-unsupervised worker ownership."""
    scope_key = _lease_scope_key(pipeline_id, runtime_root)
    with _lease_lock(scope_key):
        heartbeat = read_worker_heartbeat(
            pipeline_id,
            runtime_root=runtime_root,
            stale_after_sec=stale_after_sec,
            now_fn=now_fn,
            pid_alive_fn=pid_alive_fn,
        )
        lease = dict(heartbeat.get("lease") or read_worker_lease(pipeline_id, runtime_root=runtime_root, pid_alive_fn=pid_alive_fn))
        owner_pid = lease.get("lease_owner_pid") or heartbeat.get("pid")
        try:
            owner_pid = int(owner_pid) if owner_pid is not None else None
        except Exception:
            owner_pid = None
        lease_live = bool(lease.get("lease_live"))
        supervised_ok = bool(heartbeat.get("supervised_ok"))
        tmp_removed = _cleanup_worker_artifact_tmp_files(pipeline_id, runtime_root=runtime_root)
        actions: list[str] = []

        keeper_pid = owner_pid or heartbeat.get("pid")
        duplicate_reconcile = reconcile_duplicate_pipeline_worker_processes(
            pipeline_id,
            keeper_pid=keeper_pid,
            terminate_pid_fn=terminate_pid_fn,
            os_name=os_name,
        )
        if int(duplicate_reconcile.get("terminated_count") or 0) > 0:
            actions.append("terminated_duplicate_worker_processes")
            heartbeat = read_worker_heartbeat(
                pipeline_id,
                runtime_root=runtime_root,
                stale_after_sec=stale_after_sec,
                now_fn=now_fn,
                pid_alive_fn=pid_alive_fn,
            )
            lease = dict(heartbeat.get("lease") or read_worker_lease(pipeline_id, runtime_root=runtime_root, pid_alive_fn=pid_alive_fn))
            owner_pid = lease.get("lease_owner_pid") or heartbeat.get("pid")
            try:
                owner_pid = int(owner_pid) if owner_pid is not None else None
            except Exception:
                owner_pid = None
            lease_live = bool(lease.get("lease_live"))
            supervised_ok = bool(heartbeat.get("supervised_ok"))

        heartbeat_pid = heartbeat.get("pid")
        try:
            heartbeat_pid = int(heartbeat_pid) if heartbeat_pid is not None else None
        except Exception:
            heartbeat_pid = None
        lease_owner = lease.get("lease_owner_pid")
        try:
            lease_owner = int(lease_owner) if lease_owner is not None else None
        except Exception:
            lease_owner = None

        if supervised_ok:
            return {
                "ok": True,
                "status": "no_action",
                "pipeline_id": str(pipeline_id or "").strip(),
                "actions": actions,
                "tmp_removed": tmp_removed,
                "heartbeat": heartbeat,
                "lease": lease,
            }

        if (
            reclaim_stale_live
            and heartbeat_pid
            and lease_owner
            and heartbeat_pid != lease_owner
            and pid_alive(heartbeat_pid, pid_alive_fn=pid_alive_fn)
        ):
            terminator = terminate_pid_fn or (lambda pid: _default_terminate_pid(pid, os_name=os_name))
            terminated = bool(terminator(int(heartbeat_pid)))
            if terminated:
                actions.append("terminated_foreign_heartbeat_owner")
            release_worker_lease(pipeline_id, runtime_root=runtime_root)
            actions.append("released_mismatched_lease")
            _remove_worker_heartbeat(pipeline_id, runtime_root=runtime_root)
            actions.append("removed_mismatched_heartbeat")
            return {
                "ok": terminated,
                "status": "orphan_reclaimed" if terminated else "orphan_reclaim_partial",
                "pipeline_id": str(pipeline_id or "").strip(),
                "actions": actions,
                "terminated_owner_pid": heartbeat_pid,
                "tmp_removed": tmp_removed,
                "heartbeat": heartbeat,
                "lease": lease,
            }

        if reclaim_stale_live and lease_live and not supervised_ok:
            terminator = terminate_pid_fn or (lambda pid: _default_terminate_pid(pid, os_name=os_name))
            terminated = bool(terminator(int(owner_pid or 0))) if owner_pid else False
            if terminated:
                actions.append("terminated_unsupervised_owner")
            release_worker_lease(pipeline_id, runtime_root=runtime_root, expected_owner_pid=owner_pid)
            actions.append("released_lease")
            _remove_worker_heartbeat(pipeline_id, runtime_root=runtime_root)
            actions.append("removed_stale_heartbeat")
            return {
                "ok": terminated or not owner_pid,
                "status": "orphan_reclaimed" if terminated else "orphan_reclaim_partial",
                "pipeline_id": str(pipeline_id or "").strip(),
                "actions": actions,
                "terminated_owner_pid": owner_pid,
                "tmp_removed": tmp_removed,
                "heartbeat": heartbeat,
                "lease": lease,
            }

        if lease.get("present") and not lease_live:
            release_worker_lease(pipeline_id, runtime_root=runtime_root)
            actions.append("released_dead_lease")
        heartbeat_pid = heartbeat.get("pid")
        try:
            heartbeat_pid = int(heartbeat_pid) if heartbeat_pid is not None else None
        except Exception:
            heartbeat_pid = None
        heartbeat_owner_alive = pid_alive(heartbeat_pid, pid_alive_fn=pid_alive_fn) if heartbeat_pid else False
        heartbeat_status = str(heartbeat.get("status") or "").strip().lower()
        if heartbeat.get("present") and (
            not heartbeat_owner_alive
            or (
                heartbeat_status == "error"
                and not lease_live
                and heartbeat_pid is not None
                and lease_owner is not None
                and heartbeat_pid != lease_owner
            )
        ):
            _remove_worker_heartbeat(pipeline_id, runtime_root=runtime_root)
            actions.append("removed_stale_heartbeat")
        if not actions:
            return {
                "ok": True,
                "status": "no_action",
                "pipeline_id": str(pipeline_id or "").strip(),
                "actions": actions,
                "tmp_removed": tmp_removed,
                "heartbeat": heartbeat,
                "lease": lease,
            }
        return {
            "ok": True,
            "status": "dead_lease_cleared",
            "pipeline_id": str(pipeline_id or "").strip(),
            "actions": actions,
            "tmp_removed": tmp_removed,
            "heartbeat": heartbeat,
            "lease": lease,
        }


def reconcile_pipeline_workers_for_ids(
    pipeline_ids: list[str],
    *,
    runtime_root: Path | None = None,
    stale_after_sec: int = DEFAULT_HEARTBEAT_STALE_SEC,
    reclaim_stale_live: bool = True,
    now_fn: Callable[[], float] = time.time,
    pid_alive_fn: Callable[[int], bool] | None = None,
    terminate_pid_fn: Callable[[int], bool] | None = None,
    os_name: str | None = None,
) -> dict[str, Any]:
    results = [
        reconcile_pipeline_worker_scope(
            pipeline_id,
            runtime_root=runtime_root,
            stale_after_sec=stale_after_sec,
            reclaim_stale_live=reclaim_stale_live,
            now_fn=now_fn,
            pid_alive_fn=pid_alive_fn,
            terminate_pid_fn=terminate_pid_fn,
            os_name=os_name,
        )
        for pipeline_id in pipeline_ids
        if str(pipeline_id or "").strip()
    ]
    reclaimed = [item for item in results if item.get("status") == "orphan_reclaimed"]
    cleared = [item for item in results if item.get("status") == "dead_lease_cleared"]
    partial = [item for item in results if item.get("status") == "orphan_reclaim_partial"]
    no_action = [item for item in results if item.get("status") == "no_action"]
    if reclaimed:
        aggregate = "orphan_reclaimed"
    elif cleared:
        aggregate = "dead_lease_cleared"
    elif partial:
        aggregate = "orphan_reclaim_partial"
    else:
        aggregate = "no_action"
    return {
        "ok": all(bool(item.get("ok", True)) for item in results),
        "status": aggregate,
        "worker_count": len(results),
        "reclaimed_count": len(reclaimed),
        "cleared_count": len(cleared),
        "partial_count": len(partial),
        "no_action_count": len(no_action),
        "workers": results,
    }