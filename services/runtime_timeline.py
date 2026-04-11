from __future__ import annotations

import json
import re


class RuntimeTimelineService:
    """Own runtime timeline parsing and aggregation outside the HTTP layer."""

    @staticmethod
    def coerce_epoch_seconds(value) -> int | None:
        if isinstance(value, (int, float)) and float(value) > 0:
            return int(float(value))
        text = str(value or "").strip()
        if not text:
            return None
        try:
            numeric = float(text)
        except Exception:
            return None
        return int(numeric) if numeric > 0 else None

    def runtime_event(self, action: str, ts_value, source: str, service: str, level: str, title: str, detail: str) -> dict | None:
        ts = self.coerce_epoch_seconds(ts_value)
        if ts is None:
            return None
        return {
            "id": f"{source}:{service}:{action}:{ts}",
            "ts": ts,
            "source": str(source or "runtime"),
            "service": str(service or "runtime"),
            "level": str(level or "info"),
            "title": str(title or "Runtime event"),
            "detail": str(detail or "")[:240],
            "action": str(action or ""),
        }

    @staticmethod
    def action_title(action: str) -> str:
        text = str(action or "").strip().replace("_", " ")
        return text.title() if text else "Operator Action"

    @staticmethod
    def action_service(action: str) -> str:
        text = str(action or "").strip().lower()
        if text.startswith("guard"):
            return "guard"
        if text.startswith("nova"):
            return "core"
        if text.startswith("patch"):
            return "patch"
        if text.startswith("policy") or text.startswith("search") or text.startswith("memory") or text.startswith("chat"):
            return "control"
        if text.startswith("session") or text.startswith("test"):
            return "sessions"
        return "control"

    def from_control_audit(self, control_audit_log, limit: int) -> list[dict]:
        try:
            if not control_audit_log.exists():
                return []
            lines = control_audit_log.read_text(encoding="utf-8", errors="ignore").splitlines()
        except Exception:
            return []

        events: list[dict] = []
        for line in lines[-max(limit * 4, 40):]:
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except Exception:
                continue
            action = str(entry.get("action") or "").strip()
            result = str(entry.get("result") or "").strip().lower()
            detail = str(entry.get("detail") or "").strip()
            safe_fields = entry.get("safe_fields") if isinstance(entry.get("safe_fields"), dict) else {}
            operator_mode = str(safe_fields.get("operator_mode") or "").strip().lower()
            operator_source = str(safe_fields.get("source") or "").strip().lower()
            operator_macro = str(safe_fields.get("macro") or "").strip()
            level = "danger" if result == "fail" else "good"
            title = self.action_title(action)
            if action == "operator_prompt":
                mode_label = operator_mode or ("macro" if operator_macro else (operator_source or "manual"))
                title = f"Operator Prompt [{mode_label.upper()}]"
                detail_prefix: list[str] = []
                if operator_source:
                    detail_prefix.append(f"source={operator_source}")
                if operator_macro:
                    detail_prefix.append(f"macro={operator_macro}")
                if detail_prefix:
                    detail = " | ".join(detail_prefix) + (f" | {detail}" if detail else "")
            event = self.runtime_event(
                action or "operator_action",
                entry.get("ts"),
                "operator",
                self.action_service(action),
                level,
                title,
                f"{result or 'ok'}{': ' + detail if detail else ''}",
            )
            if event is not None:
                event["result"] = result or "ok"
                if operator_mode:
                    event["operator_mode"] = operator_mode
                if operator_source:
                    event["operator_source"] = operator_source
                if operator_macro:
                    event["operator_macro"] = operator_macro
                events.append(event)
        return events[-limit:]

    def parse_guard_log_line(self, line: str, *, time_module) -> dict | None:
        match = re.match(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) \| (.*)$", str(line or "").strip())
        if not match:
            return None
        stamp_text, message = match.groups()
        try:
            ts_value = int(time_module.mktime(time_module.strptime(stamp_text, "%Y-%m-%d %H:%M:%S")))
        except Exception:
            return None

        service = "guard"
        level = "info"
        title = "Guard event"
        detail = ""

        if "Boot metrics:" in message:
            return None
        if "Starting nova_core.py" in message:
            service = "core"
            level = "warn"
            title = "Core launch requested"
            detail = message.split("because:", 1)[1].strip() if "because:" in message else message
        elif "Spawned core pid=" in message:
            service = "core"
            level = "warn"
            title = "Core process spawned"
            detail = message
        elif "Boot observation window set to" in message:
            service = "core"
            level = "warn"
            title = "Boot observation armed"
            detail = message.split("set to", 1)[1].strip() if "set to" in message else message
        elif "Boot progress: matching state" in message:
            service = "core"
            level = "good"
            title = "Core state observed"
            detail = message.split("Boot progress:", 1)[1].strip()
        elif "Boot progress: fresh heartbeat" in message:
            service = "core"
            level = "good"
            title = "Core heartbeat observed"
            detail = message.split("Boot progress:", 1)[1].strip()
        elif "Core attempt failed:" in message:
            service = "core"
            level = "danger"
            title = "Core attempt failed"
            detail = message.split("Core attempt failed:", 1)[1].strip()
        elif "Resolving core pid=" in message:
            service = "core"
            level = "warn"
            title = "Runtime cleanup started"
            detail = message.split("[GUARD]", 1)[-1].strip()
        elif "Resolution confirmed for core pid=" in message:
            service = "core"
            level = "good"
            title = "Runtime cleanup complete"
            detail = message.split("Resolution confirmed for core pid=", 1)[1].strip()
        elif "Restart wait " in message:
            service = "core"
            level = "warn"
            title = "Restart backoff armed"
            detail = message.split("Restart wait", 1)[1].strip()
        elif "Adopted running core pid=" in message:
            service = "core"
            level = "good"
            title = "Guard adopted running core"
            detail = message.split("Adopted running core pid=", 1)[1].strip()
        elif "Existing core pid=" in message and "is unhealthy" in message:
            service = "core"
            level = "danger"
            title = "Existing core marked unhealthy"
            detail = message.split("[GUARD]", 1)[-1].strip()
        elif "Core pid=" in message and "reached RUNNING state" in message:
            service = "core"
            level = "good"
            title = "Core reached running state"
            detail = message.split("[GUARD]", 1)[-1].strip()
        elif "Nova Guard online" in message:
            level = "good"
            title = "Guard online"
            detail = "Deterministic supervisor loop active."
        elif "Another guard is already running" in message:
            level = "warn"
            title = "Duplicate guard prevented"
            detail = message.split("[GUARD]", 1)[-1].strip()
        elif "Failed to acquire guard lock" in message:
            level = "danger"
            title = "Guard lock acquisition failed"
            detail = message.split("[GUARD]", 1)[-1].strip()
        elif "Stop file detected" in message:
            level = "warn"
            title = "Guard stop requested"
            detail = "Stop file detected by supervisor."
        elif "Guard stopped." in message:
            level = "warn"
            title = "Guard stopped"
            detail = "Supervisor process exited."
        else:
            return None

        return self.runtime_event(title.lower().replace(" ", "_"), ts_value, "guard", service, level, title, detail)

    def from_guard_log(self, guard_log_path, limit: int, *, safe_tail_lines_fn, time_module) -> list[dict]:
        try:
            lines = safe_tail_lines_fn(guard_log_path, max(limit * 6, 80))
        except Exception:
            return []
        events = [event for event in (self.parse_guard_log_line(line, time_module=time_module) for line in lines) if event is not None]
        return events[-limit:]

    def from_boot_history(self, boot_history_path, limit: int) -> list[dict]:
        try:
            if not boot_history_path.exists():
                return []
            history = json.loads(boot_history_path.read_text(encoding="utf-8") or "[]")
        except Exception:
            return []

        events: list[dict] = []
        for item in list(history)[-max(limit, 10):]:
            if not isinstance(item, dict):
                continue
            success = bool(item.get("success"))
            reason = str(item.get("reason") or "running").strip() or "running"
            total_observed = item.get("total_observed_s")
            window_seconds = item.get("boot_timeout_seconds")
            detail = (
                f"reason={reason} | observed={total_observed}s | boot_window={window_seconds}s"
                if total_observed is not None and window_seconds is not None
                else f"reason={reason}"
            )
            event = self.runtime_event(
                "boot_success" if success else "boot_failure",
                item.get("ts"),
                "guard",
                "core",
                "good" if success else "danger",
                "Boot observation succeeded" if success else "Boot observation failed",
                detail,
            )
            if event is not None:
                event["reason"] = reason
                events.append(event)
        return events[-limit:]

    def payload(self, *, limit: int = 24, control_audit_log, guard_log_path, boot_history_path, safe_tail_lines_fn, time_module) -> dict:
        capped_limit = max(1, min(int(limit or 24), 60))
        events = (
            self.from_control_audit(control_audit_log, capped_limit)
            + self.from_guard_log(guard_log_path, capped_limit, safe_tail_lines_fn=safe_tail_lines_fn, time_module=time_module)
            + self.from_boot_history(boot_history_path, capped_limit)
        )
        unique: dict[tuple, dict] = {}
        for event in events:
            key = (
                int(event.get("ts") or 0),
                str(event.get("source") or ""),
                str(event.get("service") or ""),
                str(event.get("title") or ""),
                str(event.get("detail") or ""),
            )
            unique[key] = event
        ordered = sorted(unique.values(), key=lambda item: (int(item.get("ts") or 0), str(item.get("title") or "")), reverse=True)
        return {
            "count": len(ordered[:capped_limit]),
            "events": ordered[:capped_limit],
        }


RUNTIME_TIMELINE_SERVICE = RuntimeTimelineService()