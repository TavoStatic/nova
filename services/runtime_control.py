from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from pathlib import Path

import psutil


class RuntimeControlService:
    """Own runtime lifecycle control helpers outside the HTTP layer."""

    @staticmethod
    def runtime_artifact_show_action(payload: dict, *, runtime_artifact_detail_payload_fn) -> tuple[bool, str, dict, str]:
        target = str(payload.get("artifact") or payload.get("name") or "").strip()
        detail = runtime_artifact_detail_payload_fn(target, max_lines=int(payload.get("lines") or 120))
        ok = bool(detail.get("ok"))
        msg = "runtime_artifact_show_ok" if ok else str(detail.get("error") or "runtime_artifact_show_failed")
        return ok, msg, {"artifact": detail}, f"{msg}:{target}"

    @staticmethod
    def guard_status_action(*, guard_status_payload_fn) -> tuple[bool, str, dict, str]:
        msg = "guard_status_ok"
        return True, msg, {"guard": guard_status_payload_fn()}, msg

    @staticmethod
    def guard_start_action(*, start_guard_fn, guard_status_payload_fn) -> tuple[bool, str, dict, str]:
        ok, msg = start_guard_fn()
        return ok, msg, {"guard": guard_status_payload_fn()}, msg

    @staticmethod
    def guard_stop_action(*, stop_guard_fn, guard_status_payload_fn) -> tuple[bool, str, dict, str]:
        ok, msg = stop_guard_fn()
        return ok, msg, {"guard": guard_status_payload_fn()}, msg

    @staticmethod
    def guard_restart_action(*, restart_guard_fn, guard_status_payload_fn, core_status_payload_fn) -> tuple[bool, str, dict, str]:
        ok, msg = restart_guard_fn()
        return ok, msg, {"guard": guard_status_payload_fn(), "core": core_status_payload_fn()}, msg

    @staticmethod
    def nova_start_action(*, start_nova_core_fn, core_status_payload_fn) -> tuple[bool, str, dict, str]:
        ok, msg = start_nova_core_fn()
        return ok, msg, {"core": core_status_payload_fn()}, msg

    @staticmethod
    def core_stop_action(*, stop_core_owned_process_fn, guard_status_payload_fn, core_status_payload_fn) -> tuple[bool, str, dict, str]:
        ok, msg = stop_core_owned_process_fn()
        return ok, msg, {"guard": guard_status_payload_fn(), "core": core_status_payload_fn()}, msg

    @staticmethod
    def core_restart_action(*, restart_core_fn, guard_status_payload_fn, core_status_payload_fn) -> tuple[bool, str, dict, str]:
        ok, msg = restart_core_fn()
        return ok, msg, {"guard": guard_status_payload_fn(), "core": core_status_payload_fn()}, msg

    @staticmethod
    def webui_restart_action(*, restart_webui_fn, http_status_payload_fn) -> tuple[bool, str, dict, str]:
        ok, msg = restart_webui_fn()
        return ok, msg, {"webui": http_status_payload_fn()}, msg

    @staticmethod
    def autonomy_maintenance_start_action(
        *,
        start_autonomy_maintenance_worker_fn,
        autonomy_maintenance_summary_fn,
    ) -> tuple[bool, str, dict, str]:
        ok, msg = start_autonomy_maintenance_worker_fn()
        return ok, msg, {"autonomy_maintenance": autonomy_maintenance_summary_fn()}, msg

    @staticmethod
    def autonomy_maintenance_stop_action(
        *,
        stop_autonomy_maintenance_worker_fn,
        autonomy_maintenance_summary_fn,
    ) -> tuple[bool, str, dict, str]:
        ok, msg = stop_autonomy_maintenance_worker_fn()
        return ok, msg, {"autonomy_maintenance": autonomy_maintenance_summary_fn()}, msg

    @staticmethod
    def _coerce_identity_pid(value) -> int | None:
        if isinstance(value, int) and value > 0:
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
        return None

    def autonomy_maintenance_identity_from_state(self, *, state_path: Path) -> tuple[int | None, float | None, dict]:
        try:
            payload = json.loads(Path(state_path).read_text(encoding="utf-8") or "{}")
        except Exception:
            return None, None, {}
        runtime_worker = dict(payload.get("runtime_worker") or {}) if isinstance(payload.get("runtime_worker"), dict) else {}
        pid = self._coerce_identity_pid(runtime_worker.get("pid"))
        create_time_raw = runtime_worker.get("create_time")
        create_time = float(create_time_raw) if isinstance(create_time_raw, (int, float)) else None
        return pid, create_time, runtime_worker

    @staticmethod
    def detached_creation_flags(*, os_name: str = os.name, subprocess_module=subprocess) -> int:
        if os_name != "nt":
            return 0
        return (
            subprocess_module.DETACHED_PROCESS
            | subprocess_module.CREATE_NEW_PROCESS_GROUP
            | subprocess_module.CREATE_NO_WINDOW
        )

    def start_guard(
        self,
        *,
        venv_python: Path,
        guard_py: Path,
        runtime_dir: Path,
        base_dir: Path,
        guard_status_fn,
        subprocess_module=subprocess,
        os_name: str = os.name,
    ) -> tuple[bool, str]:
        if not Path(venv_python).exists():
            return False, f"venv_python_missing:{venv_python}"
        if not Path(guard_py).exists():
            return False, f"guard_script_missing:{guard_py}"

        stop_file = Path(runtime_dir) / "guard.stop"
        try:
            if stop_file.exists():
                stop_file.unlink()
        except Exception:
            pass

        status = guard_status_fn()
        if status.get("running"):
            return True, "guard_already_running"

        try:
            flags = self.detached_creation_flags(os_name=os_name, subprocess_module=subprocess_module)
            subprocess_module.Popen(
                [str(venv_python), str(guard_py)],
                cwd=str(base_dir),
                stdout=subprocess_module.DEVNULL,
                stderr=subprocess_module.DEVNULL,
                creationflags=flags,
            )
            return True, "guard_start_requested"
        except Exception as exc:
            return False, f"guard_start_failed:{exc}"

    def start_autonomy_maintenance_worker(
        self,
        *,
        venv_python: Path,
        maintenance_py: Path,
        state_path: Path,
        base_dir: Path,
        interval_sec: int,
        runtime_processes_module,
        subprocess_module=subprocess,
        os_name: str = os.name,
    ) -> tuple[bool, str]:
        if not Path(venv_python).exists():
            return False, f"venv_python_missing:{venv_python}"
        if not Path(maintenance_py).exists():
            return False, f"autonomy_maintenance_script_missing:{maintenance_py}"

        pid, create_time, _worker_state = self.autonomy_maintenance_identity_from_state(state_path=state_path)
        logical = runtime_processes_module.logical_service_processes(maintenance_py)
        selected = runtime_processes_module.select_logical_process(logical, pid=pid, create_time=create_time)
        if selected is not None:
            return True, "autonomy_maintenance_already_running"

        try:
            flags = self.detached_creation_flags(os_name=os_name, subprocess_module=subprocess_module)
            subprocess_module.Popen(
                [str(venv_python), str(maintenance_py), "--loop", "--interval-sec", str(max(1, int(interval_sec or 300)))],
                cwd=str(base_dir),
                stdout=subprocess_module.DEVNULL,
                stderr=subprocess_module.DEVNULL,
                creationflags=flags,
            )
            return True, "autonomy_maintenance_start_requested"
        except Exception as exc:
            return False, f"autonomy_maintenance_start_failed:{exc}"

    @staticmethod
    def start_nova_core(*, core_py: Path, core_status_fn, start_guard_fn) -> tuple[bool, str]:
        if not Path(core_py).exists():
            return False, f"core_script_missing:{core_py}"
        status = core_status_fn()
        if status.get("running"):
            return True, "nova_core_already_running"

        ok, msg = start_guard_fn()
        if not ok:
            return False, f"nova_core_start_failed:{msg}"
        if msg in {"guard_start_requested", "guard_already_running"}:
            return True, "nova_core_start_requested_via_guard"
        return True, f"nova_core_start_via_guard:{msg}"

    @staticmethod
    def stop_guard(*, venv_python: Path, stop_guard_py: Path, base_dir: Path, subprocess_run=subprocess.run) -> tuple[bool, str]:
        if not Path(venv_python).exists() or not Path(stop_guard_py).exists():
            return False, "stop_guard_script_missing"
        try:
            proc = subprocess_run(
                [str(venv_python), str(stop_guard_py)],
                cwd=str(base_dir),
                capture_output=True,
                text=True,
                timeout=25,
            )
            out = str(proc.stdout or "").strip()
            err = str(proc.stderr or "").strip()
            if proc.returncode == 0:
                return True, out or "guard_stop_requested"
            msg = out or err or f"exit:{proc.returncode}"
            return False, f"guard_stop_failed:{msg}"
        except Exception as exc:
            return False, f"guard_stop_failed:{exc}"

    def schedule_detached_start(
        self,
        command: list[str],
        *,
        venv_python: Path,
        base_dir: Path,
        delay_seconds: float = 1.5,
        cwd: Path | None = None,
        subprocess_module=subprocess,
        os_name: str = os.name,
    ) -> tuple[bool, str]:
        if not Path(venv_python).exists():
            return False, f"venv_python_missing:{venv_python}"
        work_dir = str(cwd or base_dir)
        flags = self.detached_creation_flags(os_name=os_name, subprocess_module=subprocess_module)
        launcher_code = (
            "import subprocess,time;"
            f"time.sleep({max(0.0, float(delay_seconds))});"
            f"subprocess.Popen({list(command)!r}, cwd={work_dir!r}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags={int(flags)})"
        )
        try:
            subprocess_module.Popen(
                [str(venv_python), "-c", launcher_code],
                cwd=work_dir,
                stdout=subprocess_module.DEVNULL,
                stderr=subprocess_module.DEVNULL,
                creationflags=flags,
            )
            return True, "delayed_start_scheduled"
        except Exception as exc:
            return False, f"delayed_start_failed:{exc}"

    @staticmethod
    def core_identity_from_runtime(*, runtime_dir: Path, runtime_processes_module) -> tuple[int | None, float | None]:
        pid, create_time, _data = runtime_processes_module.read_identity_file(Path(runtime_dir) / "core_state.json")
        return pid, create_time

    def stop_core_owned_process(
        self,
        *,
        runtime_dir: Path,
        core_py: Path,
        runtime_processes_module,
        psutil_module=psutil,
    ) -> tuple[bool, str]:
        pid, create_time = self.core_identity_from_runtime(runtime_dir=runtime_dir, runtime_processes_module=runtime_processes_module)
        if not pid:
            return False, "core_pid_missing"

        logical = runtime_processes_module.logical_service_processes(core_py)
        selected = runtime_processes_module.select_logical_process(logical, pid=pid, create_time=create_time)
        if selected is None:
            if psutil_module.pid_exists(pid):
                return False, f"core_stale_identity:{pid}"
            return False, f"core_not_running:{pid}"

        resolved_pid = int(selected.get("pid") or pid)
        try:
            process = psutil_module.Process(resolved_pid)
            process.terminate()
            try:
                process.wait(timeout=8)
                return True, f"core_stop_requested:{resolved_pid}"
            except psutil_module.TimeoutExpired:
                process.kill()
                return True, f"core_kill_requested:{resolved_pid}"
        except Exception as exc:
            return False, f"core_stop_failed:{resolved_pid}:{exc}"

    def stop_autonomy_maintenance_worker(
        self,
        *,
        state_path: Path,
        maintenance_py: Path,
        runtime_processes_module,
        psutil_module=psutil,
    ) -> tuple[bool, str]:
        pid, create_time, _worker_state = self.autonomy_maintenance_identity_from_state(state_path=state_path)
        logical = runtime_processes_module.logical_service_processes(maintenance_py)
        selected = runtime_processes_module.select_logical_process(logical, pid=pid, create_time=create_time)
        if selected is None:
            if pid and psutil_module.pid_exists(pid):
                return False, f"autonomy_maintenance_stale_identity:{pid}"
            return False, "autonomy_maintenance_not_running"

        resolved_pid = int(selected.get("pid") or pid or 0)
        try:
            process = psutil_module.Process(resolved_pid)
            process.terminate()
            try:
                process.wait(timeout=8)
                return True, f"autonomy_maintenance_stop_requested:{resolved_pid}"
            except psutil_module.TimeoutExpired:
                process.kill()
                return True, f"autonomy_maintenance_kill_requested:{resolved_pid}"
        except Exception as exc:
            return False, f"autonomy_maintenance_stop_failed:{resolved_pid}:{exc}"

    @staticmethod
    def restart_guard(
        *,
        venv_python: Path,
        guard_py: Path,
        base_dir: Path,
        guard_status_fn,
        core_status_fn,
        stop_guard_fn,
        schedule_detached_start_fn,
        start_guard_fn,
    ) -> tuple[bool, str]:
        guard_status = guard_status_fn(include_fallback_scan=False)
        core_status = core_status_fn()
        should_stop_first = bool(
            guard_status.get("running")
            or core_status.get("running")
            or core_status.get("state_exists")
            or guard_status.get("lock_exists")
        )
        if should_stop_first:
            ok, msg = stop_guard_fn()
            if not ok:
                return False, msg
            scheduled, scheduled_msg = schedule_detached_start_fn(
                [str(venv_python), str(guard_py)],
                delay_seconds=2.0,
                cwd=base_dir,
            )
            if not scheduled:
                return False, scheduled_msg
            return True, f"guard_restart_requested:{msg}"

        ok, msg = start_guard_fn()
        return ok, f"guard_restart_requested:{msg}" if ok else msg

    @staticmethod
    def restart_core(*, guard_status_fn, stop_core_owned_process_fn, start_guard_fn) -> tuple[bool, str]:
        guard_status = guard_status_fn()
        stop_ok, stop_msg = stop_core_owned_process_fn()
        if not stop_ok and not any(token in str(stop_msg or "") for token in ["core_pid_missing", "core_not_running"]):
            return False, stop_msg

        if guard_status.get("running"):
            return True, f"core_restart_requested_via_guard:{stop_msg}"

        start_ok, start_msg = start_guard_fn()
        if not start_ok:
            return False, start_msg
        return True, f"core_restart_requested:{stop_msg}:{start_msg}"

    @staticmethod
    def shutdown_http_server_later(
        http_server,
        delay_seconds: float = 0.25,
        *,
        threading_module=threading,
        time_module=time,
    ) -> tuple[bool, str]:
        if http_server is None:
            return False, "http_server_unavailable"

        def _shutdown() -> None:
            time_module.sleep(max(0.0, float(delay_seconds)))
            try:
                http_server.shutdown()
            except Exception:
                pass

        threading_module.Thread(target=_shutdown, daemon=True).start()
        return True, "http_shutdown_requested"

    @staticmethod
    def restart_webui(
        *,
        venv_python: Path,
        http_py: Path,
        bind_host: str,
        bind_port: int,
        base_dir: Path,
        schedule_detached_start_fn,
        shutdown_http_server_later_fn,
    ) -> tuple[bool, str]:
        command = [str(venv_python), str(http_py), "--host", str(bind_host), "--port", str(bind_port)]
        scheduled, scheduled_msg = schedule_detached_start_fn(command, delay_seconds=1.5, cwd=base_dir)
        if not scheduled:
            return False, scheduled_msg
        stopped, stopped_msg = shutdown_http_server_later_fn(0.25)
        if not stopped:
            return False, stopped_msg
        return True, "webui_restart_requested"


RUNTIME_CONTROL_SERVICE = RuntimeControlService()