from __future__ import annotations

from pathlib import Path


class RuntimeArtifactsService:
    """Own runtime artifact inventory and detail payload construction."""

    @staticmethod
    def artifact_definitions(*, runtime_dir: Path, guard_boot_history_path: Path, control_audit_log: Path, guard_log_path: Path) -> list[tuple[str, Path, str]]:
        return [
            ("core_state.json", Path(runtime_dir) / "core_state.json", "json"),
            ("core.heartbeat", Path(runtime_dir) / "core.heartbeat", "signal"),
            ("guard.lock", Path(runtime_dir) / "guard.lock", "lock"),
            ("guard.stop", Path(runtime_dir) / "guard.stop", "signal"),
            ("guard_boot_history.json", Path(guard_boot_history_path), "json"),
            ("control_action_audit.jsonl", Path(control_audit_log), "log"),
            ("guard.log", Path(guard_log_path), "log"),
        ]

    @staticmethod
    def artifact_service(name: str) -> str:
        artifact_name = str(name or "").strip().lower()
        if artifact_name in {"core_state.json", "core.heartbeat"}:
            return "core"
        if artifact_name in {"guard.lock", "guard.stop", "guard_boot_history.json", "guard.log"}:
            return "guard"
        if artifact_name == "control_action_audit.jsonl":
            return "control"
        return "runtime"

    @staticmethod
    def artifact_status(name: str, path: Path, *, file_age_seconds_fn) -> str:
        if not Path(path).exists():
            return "missing"
        if name == "core.heartbeat":
            age = file_age_seconds_fn(path)
            if age is None:
                return "present"
            return "running" if age <= 5 else "stale"
        if name == "guard.stop":
            return "present"
        return "present"

    def artifact_summary(self, name: str, path: Path, *, safe_json_file_fn, tail_file_fn, safe_tail_lines_fn, file_age_seconds_fn, json_module) -> tuple[str, str]:
        path = Path(path)
        if not path.exists():
            return "artifact missing", ""

        if name == "core_state.json":
            data = safe_json_file_fn(path)
            if isinstance(data, dict):
                pid = data.get("pid")
                create_time = data.get("create_time")
                summary = f"pid={pid if pid is not None else '-'} | create_time={create_time if create_time is not None else '-'}"
                excerpt = json_module.dumps(data, indent=2)[:360]
                return summary, excerpt
            return "state file present", tail_file_fn(path, max_lines=8)

        if name == "guard.lock":
            data = safe_json_file_fn(path)
            if isinstance(data, dict):
                pid = data.get("pid")
                command = data.get("command") if isinstance(data.get("command"), dict) else {}
                summary = f"pid={pid if pid is not None else '-'} | script={command.get('script') or '-'}"
                excerpt = json_module.dumps(data, indent=2)[:360]
                return summary, excerpt
            return "guard lock present", tail_file_fn(path, max_lines=8)

        if name == "guard_boot_history.json":
            data = safe_json_file_fn(path)
            if isinstance(data, list) and data:
                latest = data[-1] if isinstance(data[-1], dict) else {}
                summary = (
                    f"entries={len(data)} | latest={'success' if latest.get('success') else 'failure'}"
                    f" | reason={latest.get('reason') or 'n/a'}"
                )
                excerpt = json_module.dumps(latest, indent=2)[:360]
                return summary, excerpt
            return "boot history present", tail_file_fn(path, max_lines=8)

        if name == "control_action_audit.jsonl":
            lines = safe_tail_lines_fn(path, 4)
            if lines:
                try:
                    latest = json_module.loads(lines[-1])
                except Exception:
                    latest = {}
                if isinstance(latest, dict) and latest:
                    summary = f"last_action={latest.get('action') or '-'} | result={latest.get('result') or '-'}"
                    return summary, "\n".join(lines[-4:])[:360]
            return "control audit log present", tail_file_fn(path, max_lines=8)

        if name == "guard.log":
            lines = safe_tail_lines_fn(path, 4)
            last_line = lines[-1] if lines else ""
            summary = last_line[-160:] if last_line else "guard log present"
            return summary, "\n".join(lines[-4:])[:360]

        if name == "core.heartbeat":
            age = file_age_seconds_fn(path)
            summary = f"heartbeat age={age}s" if age is not None else "heartbeat present"
            return summary, f"mtime_age_sec={age if age is not None else 'unknown'}"

        if name == "guard.stop":
            age = file_age_seconds_fn(path)
            summary = "guard stop flag present"
            return summary, f"mtime_age_sec={age if age is not None else 'unknown'}"

        return "artifact present", tail_file_fn(path, max_lines=8)

    def artifact_content(self, name: str, path: Path, *, max_lines: int, max_chars: int, safe_tail_lines_fn, tail_file_fn, file_age_seconds_fn, json_module) -> str:
        path = Path(path)
        if not path.exists():
            return f"Artifact is not present: {path}"

        text = ""
        try:
            if name.endswith(".json") or name.endswith(".jsonl"):
                if name == "control_action_audit.jsonl":
                    text = "\n".join(safe_tail_lines_fn(path, max_lines=max(1, int(max_lines))))
                else:
                    raw = path.read_text(encoding="utf-8", errors="ignore")
                    parsed = json_module.loads(raw)
                    text = json_module.dumps(parsed, ensure_ascii=True, indent=2)
            elif name in {"guard.log"}:
                text = tail_file_fn(path, max_lines=max(1, int(max_lines)))
            else:
                text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception as exc:
            text = f"Unable to read {name}: {exc}"

        clean = str(text or "").strip()
        if not clean:
            age = file_age_seconds_fn(path)
            clean = f"{name} is present but empty. mtime_age_sec={age if age is not None else 'unknown'}"
        return clean[: max(200, int(max_chars))]

    def detail_payload(
        self,
        name: str,
        *,
        definitions: list[tuple[str, Path, str]],
        runtime_timeline_payload_fn,
        artifact_summary_fn,
        artifact_status_fn,
        artifact_content_fn,
        file_age_seconds_fn,
        max_lines: int = 120,
    ) -> dict:
        artifact_name = str(name or "").strip()
        artifact_map = {item_name: (path, kind) for item_name, path, kind in definitions}
        resolved = artifact_map.get(artifact_name)
        if not resolved:
            return {"ok": False, "error": "runtime_artifact_unknown", "name": artifact_name}

        path, kind = resolved
        summary, excerpt = artifact_summary_fn(artifact_name, path)
        service = self.artifact_service(artifact_name)
        related_events = []
        for event in list((runtime_timeline_payload_fn(limit=24).get("events") or [])):
            event_service = str(event.get("service") or "").strip().lower()
            if event_service != service and not (service == "control" and event_service in {"control", "patch", "sessions"}):
                continue
            related_events.append({
                "ts": int(event.get("ts") or 0),
                "title": str(event.get("title") or ""),
                "detail": str(event.get("detail") or ""),
                "level": str(event.get("level") or "info"),
            })
            if len(related_events) >= 4:
                break

        return {
            "ok": True,
            "name": artifact_name,
            "kind": kind,
            "service": service,
            "path": str(path),
            "present": Path(path).exists(),
            "status": artifact_status_fn(artifact_name, path),
            "age_sec": file_age_seconds_fn(path),
            "summary": summary,
            "excerpt": excerpt,
            "content": artifact_content_fn(artifact_name, path, max_lines=max_lines),
            "related_events": related_events,
        }

    def payload(self, definitions: list[tuple[str, Path, str]], *, artifact_summary_fn, artifact_status_fn, file_age_seconds_fn) -> dict:
        items = []
        for name, path, kind in definitions:
            summary, excerpt = artifact_summary_fn(name, path)
            items.append({
                "name": name,
                "kind": kind,
                "service": self.artifact_service(name),
                "path": str(path),
                "present": Path(path).exists(),
                "status": artifact_status_fn(name, path),
                "age_sec": file_age_seconds_fn(path),
                "summary": summary,
                "excerpt": excerpt,
            })
        return {"count": len(items), "items": items}


RUNTIME_ARTIFACTS_SERVICE = RuntimeArtifactsService()