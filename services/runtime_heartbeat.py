from __future__ import annotations

import json
import time
from pathlib import Path
from threading import Event, Thread
from typing import Callable


HEARTBEAT_INTERVAL_SECONDS = 1.0
HEARTBEAT_STALE_SECONDS = 5
HEARTBEAT_STATUS_NAME = "core_heartbeat_status.json"
HEARTBEAT_LOG_NAME = "core_heartbeat.log"


def heartbeat_status_path(heartbeat_file: Path) -> Path:
    return Path(heartbeat_file).parent / HEARTBEAT_STATUS_NAME


def heartbeat_log_path(heartbeat_file: Path) -> Path:
    return Path(heartbeat_file).parent / HEARTBEAT_LOG_NAME


def _ts() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _atomic_write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def _append_log_line(path: Path, message: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"{_ts()} | {message}\n")


def read_heartbeat_status(path: Path) -> dict:
    try:
        if not Path(path).exists():
            return {}
        data = json.loads(Path(path).read_text(encoding="utf-8") or "{}")
        return dict(data) if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_heartbeat_file(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(time.time()), encoding="utf-8")


def heartbeat_write_once(
    heartbeat_file: Path,
    *,
    interval_sec: float = HEARTBEAT_INTERVAL_SECONDS,
    status_file: Path | None = None,
    log_file: Path | None = None,
    state: dict | None = None,
    write_fn: Callable[[Path], None] = _write_heartbeat_file,
) -> dict:
    heartbeat_path = Path(heartbeat_file)
    status_path = Path(status_file) if status_file is not None else heartbeat_status_path(heartbeat_path)
    log_path = Path(log_file) if log_file is not None else heartbeat_log_path(heartbeat_path)
    previous = dict(state or read_heartbeat_status(status_path) or {})
    current = {
        "ok": bool(previous.get("ok", True)),
        "interval_sec": float(previous.get("interval_sec") or interval_sec or HEARTBEAT_INTERVAL_SECONDS),
        "last_ok_at": str(previous.get("last_ok_at") or ""),
        "last_error": str(previous.get("last_error") or ""),
        "last_error_at": str(previous.get("last_error_at") or ""),
        "recovered_at": str(previous.get("recovered_at") or ""),
        "consecutive_failures": int(previous.get("consecutive_failures", 0) or 0),
        "total_failures": int(previous.get("total_failures", 0) or 0),
    }

    try:
        write_fn(heartbeat_path)
        now = _ts()
        had_failures = current["consecutive_failures"] > 0
        current["ok"] = True
        current["last_ok_at"] = now
        if had_failures:
            _append_log_line(
                log_path,
                f"heartbeat write recovered after {current['consecutive_failures']} failure(s)",
            )
            current["recovered_at"] = now
        current["consecutive_failures"] = 0
        if had_failures or not status_path.exists():
            _atomic_write_json(status_path, current)
    except Exception as exc:
        now = _ts()
        error_text = f"{type(exc).__name__}: {exc}"
        current["ok"] = False
        current["last_error"] = error_text
        current["last_error_at"] = now
        current["consecutive_failures"] = int(current.get("consecutive_failures", 0) or 0) + 1
        current["total_failures"] = int(current.get("total_failures", 0) or 0) + 1
        if current["consecutive_failures"] == 1 or error_text != str(previous.get("last_error") or ""):
            try:
                _append_log_line(
                    log_path,
                    f"heartbeat write failed consecutive={current['consecutive_failures']} error={error_text}",
                )
            except Exception:
                pass
        try:
            _atomic_write_json(status_path, current)
        except Exception:
            pass

    return current


def start_heartbeat(
    heartbeat_file: Path,
    interval_sec: float = HEARTBEAT_INTERVAL_SECONDS,
    *,
    status_file: Path | None = None,
    log_file: Path | None = None,
) -> Event:
    stop_evt = Event()
    heartbeat_path = Path(heartbeat_file)
    status_path = Path(status_file) if status_file is not None else heartbeat_status_path(heartbeat_path)
    log_path = Path(log_file) if log_file is not None else heartbeat_log_path(heartbeat_path)
    state = read_heartbeat_status(status_path)

    def _loop() -> None:
        nonlocal state
        while not stop_evt.is_set():
            state = heartbeat_write_once(
                heartbeat_path,
                interval_sec=interval_sec,
                status_file=status_path,
                log_file=log_path,
                state=state,
            )
            stop_evt.wait(interval_sec)

    thread = Thread(target=_loop, name="core-heartbeat", daemon=True)
    thread.start()
    return stop_evt
