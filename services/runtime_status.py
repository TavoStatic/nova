from __future__ import annotations

import json
from pathlib import Path


class RuntimeStatusService:
    """Own runtime readiness and failure-reason summaries outside the HTTP layer."""

    @staticmethod
    def guard_status_payload(
        *,
        runtime_dir: Path,
        guard_py: Path,
        include_fallback_scan: bool,
        pid_exists_fn,
        cached_logical_service_processes_fn,
        logical_service_processes_fn,
        prune_orphaned_guard_artifacts_fn,
        select_logical_process_fn,
        process_scan_cache_ttl_seconds: float,
    ) -> dict:
        pid_file = runtime_dir / "guard_pid.json"
        lock_file = runtime_dir / "guard.lock"
        stop_file = runtime_dir / "guard.stop"
        running = False
        pid = None
        create_time = None
        pid_live = False
        lock_exists = lock_file.exists()
        pid_file_exists = pid_file.exists()
        stop_exists = stop_file.exists()
        if pid_file.exists():
            try:
                data = json.loads(pid_file.read_text(encoding="utf-8"))
                pid = int(data.get("pid", 0) or 0)
                ct = data.get("create_time")
                if isinstance(ct, (int, float)):
                    create_time = float(ct)
                if pid > 0:
                    pid_live = bool(pid_exists_fn(pid))
                    running = pid_live
            except Exception:
                pass

        use_cached_fallback = include_fallback_scan and not lock_exists and not pid_file_exists and not stop_exists and not pid_live
        if not include_fallback_scan and not lock_exists and not pid_file_exists and not stop_exists and not pid_live:
            logical_processes = []
        elif use_cached_fallback:
            logical_processes = cached_logical_service_processes_fn(
                guard_py,
                cache_key="guard-steady-state",
                max_age_seconds=process_scan_cache_ttl_seconds,
            )
        else:
            logical_processes = logical_service_processes_fn(guard_py, root_pid=pid if pid_live else None)

        prune_orphaned_guard_artifacts_fn(logical_processes, pid, pid_live)
        lock_exists = lock_file.exists()
        pid_file_exists = pid_file.exists()
        selected = select_logical_process_fn(logical_processes, pid=pid, create_time=create_time)
        if selected is not None:
            pid = int(selected.get("pid") or 0) or pid
            create_time = float(selected.get("create_time") or 0.0) or create_time
            running = True

        status = "stopped"
        if selected is not None:
            status = "running"
        elif isinstance(pid, int) and pid > 0 and pid_live:
            status = "stale_identity"
        elif stop_exists:
            status = "stopping"
        elif logical_processes:
            status = "starting"
        elif lock_exists or pid_file_exists:
            status = "boot_timeout"

        return {
            "running": running,
            "status": status,
            "pid": pid,
            "create_time": create_time,
            "process_count": len(logical_processes),
            "lock_exists": lock_exists,
            "stop_flag": stop_file.exists(),
        }

    @staticmethod
    def core_status_payload(
        *,
        runtime_dir: Path,
        core_py: Path,
        pid_exists_fn,
        heartbeat_age_seconds_fn,
        logical_service_processes_fn,
        prune_orphaned_core_artifacts_fn,
        select_logical_process_fn,
    ) -> dict:
        state_path = runtime_dir / "core_state.json"
        hb_age = heartbeat_age_seconds_fn()
        pid = None
        running = False
        create_time = None
        pid_live = False
        try:
            if state_path.exists():
                st = json.loads(state_path.read_text(encoding="utf-8") or "{}")
                pid_raw = st.get("pid")
                if isinstance(pid_raw, int) and pid_raw > 0:
                    pid = pid_raw
                elif isinstance(pid_raw, str) and pid_raw.isdigit():
                    pid = int(pid_raw)
                ct_raw = st.get("create_time")
                if isinstance(ct_raw, (int, float)):
                    create_time = float(ct_raw)
        except Exception:
            pass

        if isinstance(pid, int) and pid > 0:
            pid_live = bool(pid_exists_fn(pid))
            running = pid_live

        logical_processes = logical_service_processes_fn(core_py, root_pid=pid if pid_live else None)
        prune_orphaned_core_artifacts_fn(logical_processes, pid, pid_live, hb_age)
        hb_age = heartbeat_age_seconds_fn()

        selected = select_logical_process_fn(logical_processes, pid=pid, create_time=create_time)
        if selected is not None and isinstance(pid, int) and pid > 0 and not pid_live:
            selected_pid = int(selected.get("pid") or 0)
            selected_create_time = float(selected.get("create_time") or 0.0)
            pid_matches_state = selected_pid == pid
            create_time_matches_state = create_time is not None and abs(selected_create_time - float(create_time)) < 1.0
            if not pid_matches_state and not create_time_matches_state:
                selected = None
        if selected is not None:
            pid = int(selected.get("pid") or 0) or pid
            create_time = float(selected.get("create_time") or 0.0) or create_time
            running = True

        if not running and isinstance(hb_age, int) and hb_age <= 5:
            running = True

        status = "stopped"
        if selected is not None:
            status = "running"
        elif isinstance(hb_age, int) and hb_age <= 5:
            status = "heartbeat_only"
        elif isinstance(pid, int) and pid > 0 and pid_live:
            status = "stale_identity"
        elif state_path.exists() and isinstance(hb_age, int) and hb_age > 5:
            status = "heartbeat_stale"
        elif logical_processes:
            status = "boot_timeout"

        return {
            "running": bool(running),
            "status": status,
            "pid": pid,
            "create_time": create_time,
            "heartbeat_age_sec": hb_age,
            "process_count": len(logical_processes),
            "state_exists": state_path.exists(),
        }

    @staticmethod
    def http_status_payload(*, getpid_fn, process_fn) -> dict:
        pid = getpid_fn()
        create_time = None
        try:
            create_time = float(process_fn(pid).create_time() or 0.0) or None
        except Exception:
            create_time = None
        return {
            "running": True,
            "status": "running",
            "pid": pid,
            "create_time": create_time,
            "process_count": 1,
        }

    @staticmethod
    def runtime_summary_payload(guard: dict | None = None, core: dict | None = None, webui: dict | None = None) -> dict:
        guard_payload = dict(guard or {})
        core_payload = dict(core or {})
        webui_payload = dict(webui or {})
        return {
            "guard": {
                "status": str(guard_payload.get("status") or ("running" if guard_payload.get("running") else "stopped")),
                "pid": guard_payload.get("pid"),
                "create_time": guard_payload.get("create_time"),
                "process_count": int(guard_payload.get("process_count") or 0),
                "lock_exists": bool(guard_payload.get("lock_exists")),
                "stop_flag": bool(guard_payload.get("stop_flag")),
            },
            "core": {
                "status": str(core_payload.get("status") or ("running" if core_payload.get("running") else "stopped")),
                "pid": core_payload.get("pid"),
                "create_time": core_payload.get("create_time"),
                "process_count": int(core_payload.get("process_count") or 0),
                "heartbeat_age_sec": core_payload.get("heartbeat_age_sec"),
                "state_exists": bool(core_payload.get("state_exists")),
            },
            "webui": {
                "status": str(webui_payload.get("status") or ("running" if webui_payload.get("running") else "stopped")),
                "pid": webui_payload.get("pid"),
                "create_time": webui_payload.get("create_time"),
                "process_count": int(webui_payload.get("process_count") or 0),
            },
        }

    @staticmethod
    def action_readiness_payload(guard: dict, core: dict, webui: dict) -> dict:
        guard_status = str(guard.get("status") or "stopped")
        core_status = str(core.get("status") or "stopped")
        webui_status = str(webui.get("status") or "stopped")
        core_detected = bool(core.get("running") or core.get("pid") or core.get("state_exists") or core_status in {"heartbeat_only", "heartbeat_stale", "boot_timeout", "stale_identity"})

        return {
            "guard_start": {
                "enabled": not bool(guard.get("running")) or bool(guard.get("stop_flag")),
                "reason": "Guard already running." if bool(guard.get("running")) and not bool(guard.get("stop_flag")) else "Start guard supervision and clear any stale stop flag.",
            },
            "guard_stop": {
                "enabled": bool(guard.get("running") or guard.get("stop_flag") or core_detected),
                "reason": "Request guard/core shutdown through the deterministic stop path." if bool(guard.get("running") or guard.get("stop_flag") or core_detected) else "Guard and core are already stopped.",
            },
            "guard_restart": {
                "enabled": True,
                "reason": "Restart guard supervision and recover the core under a fresh supervisor cycle." if bool(guard.get("running") or core_detected) else "Guard is stopped; restart will start a fresh guard.",
            },
            "nova_start": {
                "enabled": core_status not in {"running", "heartbeat_only"},
                "reason": "Core already appears healthy." if core_status in {"running", "heartbeat_only"} else "Start or recover the core via guard supervision.",
            },
            "core_stop": {
                "enabled": core_detected,
                "reason": "Stop the owned core process directly; guard may restart it if still running." if core_detected else "Core is not running.",
            },
            "core_restart": {
                "enabled": True,
                "reason": "Restart the core; if guard is running it will supervise recovery." if core_detected else "Core is stopped; restart will request a new supervised start.",
            },
            "webui_restart": {
                "enabled": webui_status == "running",
                "reason": "Restart the HTTP control plane in place; the page will disconnect briefly." if webui_status == "running" else "Web UI is not running.",
            },
        }

    @staticmethod
    def latest_runtime_event_for_service(timeline_payload: dict | None, service: str) -> dict:
        events = list((timeline_payload or {}).get("events") or [])
        service_name = str(service or "").strip().lower()
        for event in events:
            if str(event.get("service") or "").strip().lower() != service_name:
                continue
            if str(event.get("level") or "").strip().lower() in {"danger", "warn", "good", "info"}:
                return dict(event)
        return {}

    def failure_reason_for_service(self, service: str, payload: dict, timeline_payload: dict | None = None) -> dict:
        status = str(payload.get("status") or ("running" if payload.get("running") else "stopped")).strip().lower()
        latest_event = self.latest_runtime_event_for_service(timeline_payload, service)
        title = service.title()
        level = "good"
        summary = "Healthy"
        detail = "No active failure detected."

        if service == "guard":
            if status == "boot_timeout":
                level = "danger"
                summary = "Guard lock remains without a live guard process."
            elif status == "stopping":
                level = "warn"
                summary = "Guard is stopping or a stop request is active."
            elif status == "starting":
                level = "warn"
                summary = "Guard start has been requested and runtime confirmation is pending."
            elif status == "stale_identity":
                level = "danger"
                summary = "Guard PID exists but no longer matches the expected runtime identity."
            elif status == "stopped":
                level = "warn"
                summary = "Guard is not running."
        elif service == "core":
            if status == "heartbeat_stale":
                level = "danger"
                summary = "Core state exists but heartbeat freshness has been lost."
            elif status == "boot_timeout":
                level = "danger"
                summary = "Core process exists without reaching a healthy boot state in time."
            elif status == "heartbeat_only":
                level = "warn"
                summary = "Heartbeat is fresh but the logical process/state match is incomplete."
            elif status == "stale_identity":
                level = "danger"
                summary = "Core state PID is live but does not match the current logical service identity."
            elif status == "stopped":
                level = "warn"
                summary = "Core is not running."
        elif service == "webui":
            if status == "starting":
                level = "warn"
                summary = "Web UI process is still starting."
            elif status == "stopped":
                level = "warn"
                summary = "Web UI is not running."

        if latest_event:
            event_detail = str(latest_event.get("detail") or "").strip()
            if event_detail:
                detail = event_detail
            if level == "good" and str(latest_event.get("level") or "").strip().lower() in {"warn", "danger"}:
                level = str(latest_event.get("level") or level)
                summary = str(latest_event.get("title") or summary)

        return {
            "service": service,
            "label": title,
            "status": status,
            "level": level,
            "summary": summary,
            "detail": detail,
        }

    def runtime_failure_reasons_payload(self, guard: dict, core: dict, webui: dict, timeline_payload: dict | None = None) -> dict:
        return {
            "guard": self.failure_reason_for_service("guard", guard or {}, timeline_payload),
            "core": self.failure_reason_for_service("core", core or {}, timeline_payload),
            "webui": self.failure_reason_for_service("webui", webui or {}, timeline_payload),
        }


RUNTIME_STATUS_SERVICE = RuntimeStatusService()