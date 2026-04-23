from __future__ import annotations

import os
from pathlib import Path


class RuntimeProcessStateService:
    """Own low-level logical process scanning and orphan artifact pruning."""

    @staticmethod
    def matches_script_process(cmdline: list[str], script_path: Path) -> bool:
        normalized_script = os.path.normcase(os.path.normpath(str(script_path)))
        for arg in list(cmdline or [])[1:]:
            text = str(arg or "").strip()
            if not text:
                continue
            if os.path.normcase(os.path.normpath(text)) == normalized_script:
                return True
        return False

    def snapshot_script_process(self, process, script_path: Path, *, matches_script_process_fn=None) -> dict | None:
        matcher = matches_script_process_fn or self.matches_script_process
        try:
            cmdline = process.cmdline() or []
            if not matcher(cmdline, script_path):
                return None
            return {
                "pid": int(process.pid or 0),
                "ppid": int(process.ppid() or 0),
                "create_time": float(process.create_time() or 0.0),
                "cmdline": list(cmdline),
            }
        except Exception:
            return None

    @staticmethod
    def logical_leaf_processes(matches: list[dict]) -> list[dict]:
        if not matches:
            return []

        matching_pids = {item["pid"] for item in matches if int(item.get("pid") or 0) > 0}
        parents_with_matching_children = {
            int(item.get("ppid") or 0)
            for item in matches
            if int(item.get("ppid") or 0) in matching_pids
        }
        leaves = [item for item in matches if int(item.get("pid") or 0) not in parents_with_matching_children]
        leaves.sort(key=lambda item: (float(item.get("create_time") or 0.0), int(item.get("pid") or 0)))
        return leaves

    def logical_service_processes(self, script_path: Path, *, root_pid: int | None = None, psutil_module, snapshot_script_process_fn=None, logical_leaf_processes_fn=None) -> list[dict]:
        snapshotter = snapshot_script_process_fn or self.snapshot_script_process
        leaf_selector = logical_leaf_processes_fn or self.logical_leaf_processes

        if isinstance(root_pid, int) and root_pid > 0:
            targeted_matches: list[dict] = []
            seen: set[int] = set()
            try:
                root = psutil_module.Process(root_pid)
                candidates = [root]
                try:
                    candidates.extend(root.children(recursive=True))
                except Exception:
                    pass
                for process in candidates:
                    pid = int(getattr(process, "pid", 0) or 0)
                    if pid <= 0 or pid in seen:
                        continue
                    seen.add(pid)
                    info = snapshotter(process, script_path)
                    if info is not None:
                        targeted_matches.append(info)
            except Exception:
                targeted_matches = []

            targeted_leaves = leaf_selector(targeted_matches)
            if targeted_leaves:
                return targeted_leaves

        matches: list[dict] = []
        for process in psutil_module.process_iter(["pid", "ppid", "cmdline"]):
            try:
                cmdline = process.info.get("cmdline") or []
                if not self.matches_script_process(cmdline, script_path):
                    continue
                create_time_value = process.info.get("create_time")
                if create_time_value is None:
                    create_time_value = process.create_time()
                create_time = float(create_time_value or 0.0)
                matches.append(
                    {
                        "pid": int(process.info.get("pid") or 0),
                        "ppid": int(process.info.get("ppid") or 0),
                        "create_time": create_time,
                        "cmdline": list(cmdline),
                    }
                )
            except Exception:
                continue

        return leaf_selector(matches)

    def cached_logical_service_processes(
        self,
        script_path: Path,
        *,
        root_pid: int | None = None,
        cache_key: str | None = None,
        max_age_seconds: float = 0.0,
        process_scan_cache: dict,
        monotonic_fn,
        logical_service_processes_fn,
    ) -> list[dict]:
        if isinstance(root_pid, int) and root_pid > 0:
            return logical_service_processes_fn(script_path, root_pid=root_pid)
        if not cache_key or max_age_seconds <= 0:
            return logical_service_processes_fn(script_path, root_pid=root_pid)

        now = monotonic_fn()
        cached = process_scan_cache.get(cache_key)
        if cached and now - float(cached[0]) <= float(max_age_seconds):
            return [dict(item) for item in cached[1]]

        processes = logical_service_processes_fn(script_path, root_pid=root_pid)
        process_scan_cache[cache_key] = (now, [dict(item) for item in processes])
        return processes

    @staticmethod
    def select_logical_process(processes: list[dict], *, pid: int | None = None, create_time: float | None = None) -> dict | None:
        if not processes:
            return None
        if isinstance(pid, int) and pid > 0:
            for item in processes:
                if int(item.get("pid") or 0) != pid:
                    continue
                if create_time is None:
                    return item
                if abs(float(item.get("create_time") or 0.0) - float(create_time)) < 1.0:
                    return item
        return processes[-1]

    @staticmethod
    def prune_orphaned_guard_artifacts(logical_processes: list[dict], pid: int | None, pid_live: bool, *, runtime_dir: Path, artifact_age_seconds_fn, remove_runtime_artifact_fn) -> None:
        lock_file = Path(runtime_dir) / "guard.lock"
        pid_file = Path(runtime_dir) / "guard_pid.json"
        ages = [age for age in (artifact_age_seconds_fn(lock_file), artifact_age_seconds_fn(pid_file)) if isinstance(age, int)]
        if logical_processes or (isinstance(pid, int) and pid > 0 and pid_live):
            return
        if not ages or max(ages) < 15:
            return
        remove_runtime_artifact_fn(lock_file)
        remove_runtime_artifact_fn(pid_file)

    @staticmethod
    def prune_orphaned_core_artifacts(logical_processes: list[dict], pid: int | None, pid_live: bool, heartbeat_age: int | None, *, runtime_dir: Path, artifact_age_seconds_fn, remove_runtime_artifact_fn) -> None:
        state_path = Path(runtime_dir) / "core_state.json"
        heartbeat_path = Path(runtime_dir) / "core.heartbeat"
        ages = [age for age in (artifact_age_seconds_fn(state_path), heartbeat_age) if isinstance(age, int)]
        if logical_processes or (isinstance(pid, int) and pid > 0 and pid_live):
            return
        if not ages or max(ages) < 15:
            return
        remove_runtime_artifact_fn(state_path)
        if isinstance(heartbeat_age, int) and heartbeat_age >= 15:
            remove_runtime_artifact_fn(heartbeat_path)


RUNTIME_PROCESS_STATE_SERVICE = RuntimeProcessStateService()