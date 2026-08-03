from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any, Callable


def _safe_text(value: Any, limit: int = 500) -> str:
    return str(value or "").strip()[: max(1, int(limit or 1))]


def _safe_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _safe_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _safe_set(value: Any) -> set[str]:
    return {
        _safe_text(item, 160)
        for item in _safe_list(value)
        if _safe_text(item, 160)
    }


NOTICE_STATUSES = {"new", "seen", "answered", "resolved", "dismissed", "stale"}
CLOSED_NOTICE_STATUSES = {"resolved", "dismissed", "stale"}
RESPONSE_RESOLUTIONS = {"evidence_only", "continue_work", "task_resolved", "dismissed", "stale"}
AUTONOMY_INTERNAL_WAIT_REASONS = {
    "cooldown_active",
    "mission_steady_state_hold",
    "mission_green_cycle_hold",
    "mission_validation_required_hold",
    "operator_hold_pending",
}
def _autonomy_internal_wait_reason(reason: str) -> bool:
    text = _safe_text(reason, 120)
    return (
        text in AUTONOMY_INTERNAL_WAIT_REASONS
        or text.startswith("mission_truth_blocker:")
        or text.startswith("mission_owner_blocker:")
    )


def _operator_notice_is_internal_wait(event: dict[str, Any]) -> bool:
    if _safe_text(event.get("source"), 120) != "autonomy_maintenance":
        return False
    payload = _safe_dict(event.get("payload"))
    decision = _safe_text(payload.get("decision"), 80)
    result = _safe_text(payload.get("execution_result"), 80)
    rejection_reasons = [
        _safe_text(item, 120)
        for item in _safe_list(payload.get("rejection_reasons"))
        if _safe_text(item, 120)
    ]
    recommended = _safe_dict(payload.get("recommended_action"))
    requires_ack = bool(recommended.get("requires_ack"))
    return bool(
        decision in {"defer_with_reason", "defer"}
        and result in {"", "blocked"}
        and rejection_reasons
        and all(_autonomy_internal_wait_reason(reason) for reason in rejection_reasons)
        and not requires_ack
    )


def _operator_actionable_open_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    actionable: list[dict[str, Any]] = []
    for event in _safe_list(events):
        if not isinstance(event, dict):
            continue
        if _safe_status(event.get("status")) in CLOSED_NOTICE_STATUSES:
            continue
        if _operator_notice_is_internal_wait(event):
            continue
        actionable.append(event)
    return actionable
SUMMARY_PAYLOAD_KEYS = {
    "action",
    "action_type",
    "blocked_reason",
    "capability",
    "decision",
    "execution_result",
    "failed_tools",
    "missing_tools",
    "operator_reason",
    "reason",
    "recommended_tool",
    "request_kind",
    "source_type",
    "suggested_tools",
    "work_class",
}


def _safe_status(value: Any, default: str = "new") -> str:
    status = _safe_text(value, 40).lower()
    return status if status in NOTICE_STATUSES else default


def _compact(value: Any, *, depth: int = 0) -> Any:
    if depth >= 4:
        return _safe_text(value, 160)
    if isinstance(value, dict):
        return {str(key): _compact(item, depth=depth + 1) for key, item in list(value.items())[:40]}
    if isinstance(value, list):
        return [_compact(item, depth=depth + 1) for item in value[:40]]
    if isinstance(value, tuple):
        return [_compact(item, depth=depth + 1) for item in list(value)[:40]]
    if isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        return round(value, 4)
    if value is None:
        return None
    return _safe_text(value, 500)


class OperatorOutboxService:
    """Durable Nova-to-operator notice lane.

    This is not a conversational router. It records internal runtime pressure
    that already exists, so UI surfaces can hear Nova without waiting for a
    user turn.
    """

    @staticmethod
    def _normalize_event(item: dict[str, Any]) -> dict[str, Any]:
        event = dict(item)
        event["status"] = _safe_status(event.get("status"))
        responses = [
            dict(row)
            for row in _safe_list(event.get("responses"))
            if isinstance(row, dict)
        ]
        event["responses"] = responses
        event["response_count"] = len(responses)
        if not event.get("updated_ts_epoch"):
            event["updated_ts_epoch"] = event.get("ts_epoch")
        if not event.get("updated_ts"):
            event["updated_ts"] = event.get("ts")
        return event

    @staticmethod
    def _small_list(value: Any, *, limit: int = 8) -> list[str]:
        return [
            _safe_text(item, 160)
            for item in _safe_list(value)[: max(1, int(limit or 1))]
            if _safe_text(item, 160)
        ]

    @staticmethod
    def _task_projection(task: Any) -> dict[str, Any]:
        task_payload = _safe_dict(task)
        result = {
            "task_id": _safe_text(task_payload.get("task_id"), 120),
            "title": _safe_text(task_payload.get("title"), 260),
            "status": _safe_text(task_payload.get("status"), 80),
        }
        meta = _safe_dict(task_payload.get("meta"))
        blocked_reason = _safe_text(meta.get("blocked_reason") or meta.get("block_reason"), 220)
        if blocked_reason:
            result["meta"] = {"blocked_reason": blocked_reason}
        return {key: value for key, value in result.items() if value not in ("", {}, [])}

    @classmethod
    def _next_step_projection(cls, next_step: Any) -> dict[str, Any]:
        step = _safe_dict(next_step)
        result: dict[str, Any] = {}
        for key in ("action", "branch_id", "branch_title", "task_id", "task_title", "recommended_tool", "reason"):
            text = _safe_text(step.get(key), 260 if key.endswith("title") else 160)
            if text:
                result[key] = text
        for key in ("suggested_tools", "missing_tools"):
            values = cls._small_list(step.get(key), limit=8)
            if values:
                result[key] = values
        return result

    @classmethod
    def _work_tree_notice_payload(
        cls,
        *,
        tree_id: str,
        tree_title: str,
        branch_id: str,
        branch_title: str,
        task_id: str,
        task_title: str,
        request_kind: str,
        next_step: Any = None,
        task: Any = None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "tree_id": _safe_text(tree_id, 120),
            "tree_title": _safe_text(tree_title, 220),
            "branch_id": _safe_text(branch_id, 120),
            "branch_title": _safe_text(branch_title, 220),
            "task_id": _safe_text(task_id, 120),
            "task_title": _safe_text(task_title, 260),
            "request_kind": _safe_text(request_kind, 120),
        }
        step = cls._next_step_projection(next_step)
        if step:
            payload["next_step"] = step
        task_payload = cls._task_projection(task)
        if task_payload:
            payload["task"] = task_payload
        for key, value in _safe_dict(extra).items():
            if isinstance(value, list):
                cleaned = cls._small_list(value)
                if cleaned:
                    payload[str(key)] = cleaned
            elif isinstance(value, dict):
                compacted = _compact(value, depth=2)
                if compacted:
                    payload[str(key)] = compacted
            else:
                text = _safe_text(value, 260)
                if text:
                    payload[str(key)] = text
        return {key: value for key, value in payload.items() if value not in ("", {}, [])}

    def _summary_payload(self, event: dict[str, Any]) -> dict[str, Any]:
        payload = _safe_dict(event.get("payload"))
        target = self.work_tree_target_from_event(event)
        tree_payload = _safe_dict(payload.get("tree"))
        next_step = _safe_dict(payload.get("next_step")) or _safe_dict(tree_payload.get("next_step"))
        task_payload = _safe_dict(payload.get("task"))
        result: dict[str, Any] = {
            key: value
            for key, value in target.items()
            if value
        }
        if task_payload and "task_id" not in result:
            task_id = _safe_text(task_payload.get("task_id"), 120)
            if task_id:
                result["task_id"] = task_id
        if task_payload and "task_title" not in result:
            task_title = _safe_text(task_payload.get("title"), 260)
            if task_title:
                result["task_title"] = task_title
        for key in sorted(SUMMARY_PAYLOAD_KEYS):
            value = payload.get(key)
            if value is None and key in {"action", "recommended_tool", "reason", "suggested_tools", "missing_tools"}:
                value = next_step.get(key)
            if isinstance(value, list):
                values = self._small_list(value, limit=8)
                if values:
                    result[key] = values
            elif isinstance(value, dict):
                compacted = _compact(value, depth=2)
                if compacted:
                    result[key] = compacted
            else:
                text = _safe_text(value, 260)
                if text:
                    result[key] = text
        step = self._next_step_projection(next_step)
        if step:
            result["next_step"] = step
        task = self._task_projection(task_payload)
        if task:
            result["task"] = task
        return result

    @staticmethod
    def _summary_response(response: dict[str, Any]) -> dict[str, Any]:
        return {
            key: value
            for key, value in {
                "id": _safe_text(response.get("id"), 120),
                "ts": _safe_text(response.get("ts"), 80),
                "ts_epoch": response.get("ts_epoch"),
                "responder": _safe_text(response.get("responder"), 80),
                "resolution": _safe_text(response.get("resolution"), 80),
                "message": _safe_text(response.get("message"), 500),
            }.items()
            if value not in ("", None)
        }

    def _summary_event(self, event: dict[str, Any]) -> dict[str, Any]:
        normalized = self._normalize_event(event)
        payload = self._summary_payload(normalized)
        target = self.work_tree_target_from_event(normalized)
        responses = [
            self._summary_response(dict(row))
            for row in _safe_list(normalized.get("responses"))[-3:]
            if isinstance(row, dict)
        ]
        result: dict[str, Any] = {
            "id": _safe_text(normalized.get("id"), 120),
            "ts_epoch": normalized.get("ts_epoch"),
            "ts": _safe_text(normalized.get("ts"), 80),
            "updated_ts_epoch": normalized.get("updated_ts_epoch"),
            "updated_ts": _safe_text(normalized.get("updated_ts"), 80),
            "source": _safe_text(normalized.get("source"), 120),
            "audience": _safe_text(normalized.get("audience"), 80),
            "severity": _safe_text(normalized.get("severity"), 40),
            "title": _safe_text(normalized.get("title"), 180),
            "message": _safe_text(normalized.get("message"), 1000),
            "dedupe_key": _safe_text(normalized.get("dedupe_key"), 220),
            "status": _safe_status(normalized.get("status")),
            "response_count": int(normalized.get("response_count", 0) or 0),
        }
        status_note = _safe_text(normalized.get("status_note"), 220)
        if status_note:
            result["status_note"] = status_note
        if payload:
            result["payload"] = payload
        compact_target = {key: value for key, value in target.items() if value}
        if compact_target:
            result["work_tree_target"] = compact_target
        if responses:
            result["responses"] = responses
        return {key: value for key, value in result.items() if value not in ("", None, {}, [])}

    def _load_events(self, path: Path) -> list[dict[str, Any]]:
        outbox_path = Path(path)
        if not outbox_path.exists():
            return []
        rows: list[dict[str, Any]] = []
        try:
            for line in outbox_path.read_text(encoding="utf-8", errors="ignore").splitlines():
                if not line.strip():
                    continue
                try:
                    item = json.loads(line)
                except Exception:
                    continue
                if isinstance(item, dict) and str(item.get("id") or "").strip():
                    rows.append(self._normalize_event(item))
        except Exception:
            return []
        return rows

    @staticmethod
    def _write_events(path: Path, rows: list[dict[str, Any]]) -> None:
        outbox_path = Path(path)
        outbox_path.parent.mkdir(parents=True, exist_ok=True)
        outbox_path.write_text(
            "\n".join(json.dumps(row, ensure_ascii=True, sort_keys=True) for row in rows) + "\n",
            encoding="utf-8",
        )

    def read_events(self, path: Path, *, after_id: str = "", limit: int = 20) -> list[dict[str, Any]]:
        rows = self._load_events(path)
        after = str(after_id or "").strip()
        if after:
            rows = [row for row in rows if str(row.get("id") or "") > after]
        return rows[-max(1, int(limit or 1)) :]

    def summary(self, path: Path, *, limit: int = 5) -> dict[str, Any]:
        all_events = self._load_events(path)
        result_limit = max(1, int(limit or 1))
        raw_events = all_events[-result_limit:]
        events = [self._summary_event(event) for event in raw_events]
        latest_raw = raw_events[-1] if raw_events else {}
        latest = events[-1] if events else {}
        status_counts: dict[str, int] = {}
        for event in all_events:
            status = _safe_status(event.get("status"))
            status_counts[status] = status_counts.get(status, 0) + 1
        open_events = [
            event for event in all_events
            if _safe_status(event.get("status")) not in CLOSED_NOTICE_STATUSES
        ]
        actionable_open_events = _operator_actionable_open_events(all_events)
        raw_visible_open_events = open_events[-result_limit:]
        visible_open_events = [self._summary_event(event) for event in raw_visible_open_events]
        latest_open_raw = open_events[-1] if open_events else {}
        latest_open = self._summary_event(latest_open_raw) if latest_open_raw else {}
        latest_actionable_raw = actionable_open_events[-1] if actionable_open_events else {}
        latest_actionable = (
            self._summary_event(latest_actionable_raw) if latest_actionable_raw else {}
        )
        return {
            "ok": True,
            "count": len(events),
            "total_count": len(all_events),
            "open_count": len(open_events),
            "operator_actionable_open_count": len(actionable_open_events),
            "status_counts": status_counts,
            "latest_id": str(latest_raw.get("id") or latest.get("id") or ""),
            "latest": latest,
            "latest_open_id": str(latest_open_raw.get("id") or latest_open.get("id") or ""),
            "latest_open": latest_open,
            "operator_actionable_latest_open_id": str(
                latest_actionable_raw.get("id") or latest_actionable.get("id") or ""
            ),
            "operator_actionable_latest_open": latest_actionable,
            "open_events": visible_open_events,
            "events": events,
        }

    def append_notice(
        self,
        path: Path,
        *,
        source: str,
        severity: str,
        title: str,
        message: str,
        dedupe_key: str = "",
        audience: str = "operator",
        payload: dict[str, Any] | None = None,
        dedupe_window_sec: int = 1800,
        max_events: int = 200,
        now_fn: Callable[[], float] | None = None,
        uuid_fn: Callable[[], str] | None = None,
    ) -> dict[str, Any]:
        clean_message = _safe_text(message, 1000)
        clean_title = _safe_text(title, 180)
        if not clean_message and not clean_title:
            return {"ok": False, "reason": "empty_notice"}

        now_value = float((now_fn or time.time)())
        dedupe = _safe_text(dedupe_key, 220)
        existing = self._load_events(path)
        if dedupe:
            for index in range(len(existing) - 1, -1, -1):
                row = existing[index]
                if str(row.get("dedupe_key") or "") != dedupe:
                    continue
                if _safe_status(row.get("status")) in CLOSED_NOTICE_STATUSES:
                    break
                row["source"] = _safe_text(source, 120)
                row["audience"] = _safe_text(audience or "operator", 80)
                row["severity"] = _safe_text(severity or "info", 40)
                row["title"] = clean_title
                row["message"] = clean_message
                row["payload"] = _compact(payload or {})
                row["updated_ts_epoch"] = now_value
                row["updated_ts"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now_value))
                row["repeat_count"] = int(row.get("repeat_count", 0) or 0) + 1
                row["last_repeat_ts_epoch"] = now_value
                row["last_repeat_ts"] = row["updated_ts"]
                existing[index] = row
                self._write_events(path, existing[-max(1, int(max_events or 1)) :])
                return {"ok": True, "deduped": True, "updated": True, "event": row}

        event_id = f"{int(now_value * 1000):013d}-{_safe_text((uuid_fn or (lambda: uuid.uuid4().hex))(), 12)}"
        event = {
            "id": event_id,
            "ts_epoch": now_value,
            "ts": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now_value)),
            "source": _safe_text(source, 120),
            "audience": _safe_text(audience or "operator", 80),
            "severity": _safe_text(severity or "info", 40),
            "title": clean_title,
            "message": clean_message,
            "dedupe_key": dedupe,
            "status": "new",
            "responses": [],
            "response_count": 0,
            "updated_ts_epoch": now_value,
            "updated_ts": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now_value)),
            "payload": _compact(payload or {}),
        }

        rows = existing[-max(0, int(max_events or 1) - 1) :] + [event]
        self._write_events(path, rows)
        return {"ok": True, "deduped": False, "event": event}

    @staticmethod
    def blocked_work_dedupe_key(*, tree_id: str, branch_id: str, blocked_reason: str) -> str:
        return (
            f"work_tree|blocked_task|{_safe_text(tree_id, 120)}|"
            f"{_safe_text(branch_id, 120)}|{_safe_text(blocked_reason, 220) or 'blocked'}"
        )

    @staticmethod
    def work_tree_target_from_event(event: dict[str, Any]) -> dict[str, str]:
        payload = _safe_dict(event.get("payload"))
        tree_payload = _safe_dict(payload.get("tree"))
        next_step = _safe_dict(payload.get("next_step")) or _safe_dict(tree_payload.get("next_step"))
        task_payload = _safe_dict(payload.get("task"))
        return {
            "tree_id": _safe_text(payload.get("tree_id") or tree_payload.get("tree_id"), 120),
            "tree_title": _safe_text(payload.get("tree_title") or tree_payload.get("title"), 220),
            "branch_id": _safe_text(payload.get("branch_id") or tree_payload.get("branch_id") or next_step.get("branch_id"), 120),
            "branch_title": _safe_text(payload.get("branch_title") or tree_payload.get("branch_title") or next_step.get("branch_title"), 220),
            "task_id": _safe_text(
                payload.get("task_id")
                or tree_payload.get("task_id")
                or task_payload.get("task_id")
                or next_step.get("task_id"),
                120,
            ),
            "task_title": _safe_text(
                payload.get("task_title")
                or tree_payload.get("task_title")
                or task_payload.get("title")
                or next_step.get("task_title"),
                260,
            ),
            "request_kind": _safe_text(payload.get("request_kind"), 120),
            "blocked_reason": _safe_text(payload.get("blocked_reason"), 220),
        }

    def _record_response_in_work_tree(
        self,
        event: dict[str, Any],
        response: dict[str, Any],
        *,
        resolution: str,
        work_tree_module: Any = None,
    ) -> dict[str, Any]:
        target = self.work_tree_target_from_event(event)
        branch_id = target.get("branch_id", "")
        task_id = target.get("task_id", "")
        if not branch_id or not task_id:
            if resolution in {"continue_work", "task_resolved"}:
                return {
                    "ok": False,
                    "applied": False,
                    "reason": f"{resolution}_requires_work_tree_target",
                    "target": target,
                }
            return {"ok": True, "applied": False, "reason": "no_work_tree_target", "target": target}

        if work_tree_module is None:
            import work_tree as work_tree_module  # local import avoids coupling service load to Work Tree

        reload_fn = getattr(work_tree_module, "reload_persisted_state", None)
        if callable(reload_fn):
            reload_fn()

        try:
            evidence_id = work_tree_module.record_task_evidence(
                branch_id=branch_id,
                task_id=task_id,
                tool_name="operator_response",
                tool_args=[str(event.get("id") or "")],
                result={
                    "event_id": str(event.get("id") or ""),
                    "title": str(event.get("title") or ""),
                    "message": str(event.get("message") or ""),
                    "operator_response": str(response.get("message") or ""),
                    "resolution": resolution,
                    "target": target,
                },
            )
        except Exception as exc:
            return {"ok": False, "applied": False, "reason": f"work_tree_evidence_failed:{exc}", "target": target}

        task_completed = False
        if resolution in {"continue_work", "task_resolved"}:
            try:
                work_tree_module.mark_task_complete(task_id)
                task_completed = True
            except Exception as exc:
                return {
                    "ok": False,
                    "applied": True,
                    "evidence_id": evidence_id,
                    "reason": f"work_tree_task_completion_failed:{exc}",
                    "target": target,
                }

        return {
            "ok": True,
            "applied": True,
            "evidence_id": evidence_id,
            "task_completed": task_completed,
            "target": target,
        }

    def set_notice_status(
        self,
        path: Path,
        *,
        event_id: str,
        status: str,
        note: str = "",
        now_fn: Callable[[], float] | None = None,
    ) -> dict[str, Any]:
        clean_event_id = _safe_text(event_id, 160)
        next_status = _safe_status(status, default="")
        if not clean_event_id:
            return {"ok": False, "reason": "event_id_required"}
        if not next_status:
            return {"ok": False, "reason": "invalid_status"}

        rows = self._load_events(path)
        now_value = float((now_fn or time.time)())
        for index, event in enumerate(rows):
            if str(event.get("id") or "") != clean_event_id:
                continue
            event["status"] = next_status
            event["updated_ts_epoch"] = now_value
            event["updated_ts"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now_value))
            clean_note = _safe_text(note, 1000)
            if clean_note:
                event["status_note"] = clean_note
            rows[index] = event
            self._write_events(path, rows)
            return {"ok": True, "event": event}

        return {"ok": False, "reason": "event_not_found"}

    def reconcile_work_tree_notices(
        self,
        path: Path,
        *,
        active_notices: list[dict[str, Any]] | None = None,
        now_fn: Callable[[], float] | None = None,
    ) -> dict[str, Any]:
        """Close work-tree notices whose current Work Tree pressure disappeared."""
        active_keys = {
            _safe_text(notice.get("dedupe_key"), 220)
            for notice in _safe_list(active_notices)
            if isinstance(notice, dict) and _safe_text(notice.get("dedupe_key"), 220)
        }
        rows = self._load_events(path)
        if not rows:
            return {"ok": True, "staled_count": 0, "active_notice_count": len(active_keys)}

        now_value = float((now_fn or time.time)())
        staled = 0
        latest_active_index_by_key: dict[str, int] = {}
        for index, event in enumerate(rows):
            if _safe_status(event.get("status")) in CLOSED_NOTICE_STATUSES:
                continue
            if _safe_text(event.get("source"), 120) != "work_tree":
                continue
            dedupe = _safe_text(event.get("dedupe_key"), 220)
            if dedupe.startswith("work_tree|") and dedupe in active_keys:
                latest_active_index_by_key[dedupe] = index

        for index, event in enumerate(rows):
            if _safe_status(event.get("status")) in CLOSED_NOTICE_STATUSES:
                continue
            if _safe_text(event.get("source"), 120) != "work_tree":
                continue
            dedupe = _safe_text(event.get("dedupe_key"), 220)
            if not dedupe.startswith("work_tree|"):
                continue
            if dedupe in active_keys:
                if latest_active_index_by_key.get(dedupe) == index:
                    continue
                event["status"] = "stale"
                event["status_note"] = "work_tree_pressure_superseded"
                event["updated_ts_epoch"] = now_value
                event["updated_ts"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now_value))
                staled += 1
                continue
            event["status"] = "stale"
            event["status_note"] = "work_tree_pressure_cleared"
            event["updated_ts_epoch"] = now_value
            event["updated_ts"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now_value))
            staled += 1

        if staled:
            self._write_events(path, rows)
        return {"ok": True, "staled_count": staled, "active_notice_count": len(active_keys)}

    @staticmethod
    def _branch_exists(work_tree_module: Any, branch_id: str) -> bool | None:
        clean_branch_id = _safe_text(branch_id, 120)
        if not clean_branch_id:
            return None
        module = work_tree_module
        if module is None:
            try:
                import work_tree as module
            except Exception:
                return None
        get_branch = getattr(module, "get_branch", None)
        if not callable(get_branch):
            return None
        try:
            return get_branch(clean_branch_id) is not None
        except Exception:
            return None

    def reconcile_source_root_judgment_notices(
        self,
        path: Path,
        *,
        work_tree_state: dict[str, Any] | None = None,
        work_tree_module: Any = None,
        now_fn: Callable[[], float] | None = None,
    ) -> dict[str, Any]:
        """Close source-root notices once their owning Work Tree branch is closed."""
        branch_closed: dict[str, bool] = {}
        for tree in [
            dict(item)
            for item in _safe_list((_safe_dict(work_tree_state)).get("trees"))
            if isinstance(item, dict)
        ]:
            for node in [
                dict(item)
                for item in _safe_list(tree.get("nodes"))
                if isinstance(item, dict)
            ]:
                branch_id = _safe_text(node.get("id"), 120)
                if not branch_id:
                    continue
                status = _safe_text(node.get("status"), 80).lower()
                resolution_state = _safe_text(node.get("resolution_state"), 80).lower()
                branch_closed[branch_id] = status in {"complete", "archived"} or resolution_state in {"resolved", "retired"}

        rows = self._load_events(path)
        if not rows:
            return {"ok": True, "staled_count": 0, "known_branch_count": len(branch_closed)}

        now_value = float((now_fn or time.time)())
        staled = 0
        for event in rows:
            if _safe_status(event.get("status")) in CLOSED_NOTICE_STATUSES:
                continue
            if _safe_text(event.get("source"), 120) != "source_root_judgment":
                continue
            branch_id = self.work_tree_target_from_event(event).get("branch_id", "")
            if not branch_id:
                continue
            should_stale = False
            status_note = "source_root_pressure_cleared"
            if branch_closed.get(branch_id) is True:
                should_stale = True
            elif branch_id not in branch_closed:
                branch_exists = self._branch_exists(work_tree_module, branch_id)
                if branch_exists is False:
                    should_stale = True
                    status_note = "source_root_branch_missing"
            if not should_stale:
                continue
            event["status"] = "stale"
            event["status_note"] = status_note
            event["updated_ts_epoch"] = now_value
            event["updated_ts"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now_value))
            staled += 1

        if staled:
            self._write_events(path, rows)
        return {"ok": True, "staled_count": staled, "known_branch_count": len(branch_closed)}

    def reconcile_stale_open_notices(
        self,
        path: Path,
        *,
        max_age_days: int = 7,
        now_fn: Callable[[], float] | None = None,
    ) -> dict[str, Any]:
        """Close open notices that aged out without operator interaction."""
        rows = self._load_events(path)
        if not rows:
            return {"ok": True, "staled_count": 0, "max_age_days": max(1, int(max_age_days or 1))}

        now_value = float((now_fn or time.time)())
        max_age_sec = max(1, int(max_age_days or 1)) * 86400
        staled = 0
        for event in rows:
            if _safe_status(event.get("status")) not in {"new", "seen"}:
                continue
            ts = float(event.get("updated_ts_epoch") or event.get("ts_epoch") or 0)
            if ts <= 0 or (now_value - ts) < max_age_sec:
                continue
            event["status"] = "stale"
            event["status_note"] = "notice_aged_out"
            event["updated_ts_epoch"] = now_value
            event["updated_ts"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now_value))
            staled += 1

        if staled:
            self._write_events(path, rows)
        return {"ok": True, "staled_count": staled, "max_age_days": max(1, int(max_age_days or 1))}

    def reconcile_duplicate_source_notices(
        self,
        path: Path,
        *,
        now_fn: Callable[[], float] | None = None,
    ) -> dict[str, Any]:
        """Keep only the newest open notice per source and request_kind."""
        rows = self._load_events(path)
        if not rows:
            return {"ok": True, "staled_count": 0}

        now_value = float((now_fn or time.time)())
        latest_open_index_by_key: dict[tuple[str, str], int] = {}
        for index, event in enumerate(rows):
            if _safe_status(event.get("status")) in CLOSED_NOTICE_STATUSES:
                continue
            source = _safe_text(event.get("source"), 120)
            if not source:
                continue
            payload = _safe_dict(event.get("payload"))
            request_kind = _safe_text(payload.get("request_kind"), 120) or "unspecified"
            ts = float(event.get("updated_ts_epoch") or event.get("ts_epoch") or 0)
            key = (source, request_kind)
            previous_index = latest_open_index_by_key.get(key)
            if previous_index is None:
                latest_open_index_by_key[key] = index
                continue
            previous_ts = float(
                rows[previous_index].get("updated_ts_epoch") or rows[previous_index].get("ts_epoch") or 0
            )
            if ts >= previous_ts:
                latest_open_index_by_key[key] = index

        staled = 0
        for index, event in enumerate(rows):
            if _safe_status(event.get("status")) in CLOSED_NOTICE_STATUSES:
                continue
            source = _safe_text(event.get("source"), 120)
            if not source:
                continue
            payload = _safe_dict(event.get("payload"))
            request_kind = _safe_text(payload.get("request_kind"), 120) or "unspecified"
            if latest_open_index_by_key.get((source, request_kind)) != index:
                event["status"] = "stale"
                event["status_note"] = "duplicate_source_notice_superseded"
                event["updated_ts_epoch"] = now_value
                event["updated_ts"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now_value))
                staled += 1

        if staled:
            self._write_events(path, rows)
        return {"ok": True, "staled_count": staled}

    def reconcile_autonomy_notices(
        self,
        path: Path,
        *,
        active_notices: list[dict[str, Any]] | None = None,
        now_fn: Callable[[], float] | None = None,
    ) -> dict[str, Any]:
        """Close autonomy notices whose current autonomy decision no longer supports them."""
        active_keys = {
            _safe_text(notice.get("dedupe_key"), 220)
            for notice in _safe_list(active_notices)
            if isinstance(notice, dict) and _safe_text(notice.get("dedupe_key"), 220)
        }
        rows = self._load_events(path)
        if not rows:
            return {"ok": True, "staled_count": 0, "active_notice_count": len(active_keys)}

        now_value = float((now_fn or time.time)())
        staled = 0
        for event in rows:
            if _safe_status(event.get("status")) in CLOSED_NOTICE_STATUSES:
                continue
            if _safe_text(event.get("source"), 120) != "autonomy_maintenance":
                continue
            dedupe = _safe_text(event.get("dedupe_key"), 220)
            if dedupe and dedupe in active_keys:
                continue
            event["status"] = "stale"
            event["status_note"] = "autonomy_pressure_cleared"
            event["updated_ts_epoch"] = now_value
            event["updated_ts"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now_value))
            staled += 1

        if staled:
            self._write_events(path, rows)
        return {"ok": True, "staled_count": staled, "active_notice_count": len(active_keys)}

    def reconcile_os_capability_notices(
        self,
        path: Path,
        *,
        capability: str,
        cleared_reasons: list[str] | tuple[str, ...] | set[str] | None = None,
        now_fn: Callable[[], float] | None = None,
    ) -> dict[str, Any]:
        """Close OS capability notices proven stale by a later clean capability run."""
        clean_capability = _safe_text(capability, 120)
        reasons = {
            _safe_text(item, 120)
            for item in _safe_list(list(cleared_reasons or []))
            if _safe_text(item, 120)
        } or {"contract_stale", "capability_evidence_not_ok"}
        if not clean_capability:
            return {"ok": False, "reason": "capability_required", "staled_count": 0}

        rows = self._load_events(path)
        if not rows:
            return {"ok": True, "staled_count": 0, "cleared_reasons": sorted(reasons)}

        now_value = float((now_fn or time.time)())
        staled = 0
        for event in rows:
            if _safe_status(event.get("status")) in CLOSED_NOTICE_STATUSES:
                continue
            if _safe_text(event.get("source"), 120) != "os_capability":
                continue
            payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
            if _safe_text(payload.get("capability"), 120) != clean_capability:
                continue
            blocked_reason = _safe_text(payload.get("blocked_reason"), 120)
            if blocked_reason not in reasons:
                continue
            event["status"] = "stale"
            event["status_note"] = "os_capability_pressure_cleared"
            event["updated_ts_epoch"] = now_value
            event["updated_ts"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now_value))
            staled += 1

        if staled:
            self._write_events(path, rows)
        return {"ok": True, "staled_count": staled, "cleared_reasons": sorted(reasons)}

    def respond_to_notice(
        self,
        path: Path,
        *,
        event_id: str,
        message: str,
        responder: str = "operator",
        resolution: str = "evidence_only",
        response_payload: dict[str, Any] | None = None,
        work_tree_module: Any = None,
        now_fn: Callable[[], float] | None = None,
        uuid_fn: Callable[[], str] | None = None,
    ) -> dict[str, Any]:
        clean_event_id = _safe_text(event_id, 160)
        clean_message = _safe_text(message, 4000)
        clean_resolution = _safe_text(resolution, 80).lower() or "evidence_only"
        if clean_resolution not in RESPONSE_RESOLUTIONS:
            return {"ok": False, "reason": "invalid_resolution"}
        if not clean_event_id:
            return {"ok": False, "reason": "event_id_required"}
        if not clean_message:
            return {"ok": False, "reason": "response_message_required"}

        rows = self._load_events(path)
        now_value = float((now_fn or time.time)())
        response_id = f"response_{int(now_value * 1000):013d}_{_safe_text((uuid_fn or (lambda: uuid.uuid4().hex))(), 10)}"
        for index, event in enumerate(rows):
            if str(event.get("id") or "") != clean_event_id:
                continue
            response = {
                "response_id": response_id,
                "ts_epoch": now_value,
                "ts": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now_value)),
                "responder": _safe_text(responder or "operator", 120),
                "message": clean_message,
                "resolution": clean_resolution,
                "payload": _compact(response_payload or {}),
            }
            work_tree_result = self._record_response_in_work_tree(
                event,
                response,
                resolution=clean_resolution,
                work_tree_module=work_tree_module,
            )
            response["work_tree_result"] = _compact(work_tree_result)
            responses = [
                dict(row)
                for row in _safe_list(event.get("responses"))
                if isinstance(row, dict)
            ]
            responses.append(response)
            event["responses"] = responses
            event["response_count"] = len(responses)
            event["updated_ts_epoch"] = now_value
            event["updated_ts"] = response["ts"]
            # continue_work / task_resolved means the operator finished their turn on
            # this notice. Always close it so open_count drops and work-tree holds
            # that only wait on outbox can clear on the next signal pass.
            # Work-tree task completion remains best-effort (may lack a linked target).
            if clean_resolution in {"continue_work", "task_resolved"}:
                event["status"] = "resolved"
            elif clean_resolution in {"dismissed", "stale"}:
                event["status"] = clean_resolution
            else:
                event["status"] = "answered"
            rows[index] = event
            self._write_events(path, rows)
            return {
                "ok": bool(work_tree_result.get("ok", True)),
                "event": event,
                "response": response,
                "work_tree": work_tree_result,
            }

        return {"ok": False, "reason": "event_not_found"}

    @staticmethod
    def _work_tree_trees(work_tree_state: Any) -> list[dict[str, Any]]:
        if isinstance(work_tree_state, dict):
            return [
                dict(item)
                for item in _safe_list(work_tree_state.get("trees"))
                if isinstance(item, dict)
            ]
        return [dict(item) for item in _safe_list(work_tree_state) if isinstance(item, dict)]

    @staticmethod
    def _blocked_request_kind(reason: str, node: dict[str, Any]) -> str:
        text = " ".join(
            [
                reason,
                _safe_text(node.get("title"), 220),
                _safe_text(node.get("notes"), 400),
                _safe_text(node.get("work_class"), 120),
                _safe_text(node.get("source_type"), 120),
            ]
        ).lower()
        if any(token in text for token in ("operator", "confirmation", "origin", "human", "answer", "information", "info")):
            return "operator_information"
        if any(token in text for token in ("repair_required", "root_repair", "owner_repair", "owner-root", "root-cause", "root cause")):
            return "internal_repair"
        if "tool" in text or "wire" in text:
            return "tool_wiring"
        return "blocked_work"

    @staticmethod
    def _blocked_message(kind: str, branch_title: str, task_title: str, reason: str, source: str) -> tuple[str, str]:
        label = branch_title or task_title or "Work Tree branch"
        task = task_title or "the current blocked task"
        reason_text = reason or "blocked"
        if kind == "operator_information":
            return (
                f"Nova needs operator information: {label}",
                f"I need operator information for {label}. Current blocked task: {task}. Reason: {reason_text}. Source: {source or 'work_tree'}.",
            )
        if kind == "internal_repair":
            return (
                f"Nova needs an internal repair lane: {label}",
                f"I need an internal repair lane for {label}. Current blocked task: {task}. Reason: {reason_text}. No current Work Tree tool can move this blocked task.",
            )
        if kind == "tool_wiring":
            return (
                f"Nova needs tool wiring: {label}",
                f"I need tool wiring for {label}. Current blocked task: {task}. Reason: {reason_text}.",
            )
        return (
            f"Nova needs help with blocked Work Tree work: {label}",
            f"I am blocked on {label}. Current task: {task}. Reason: {reason_text}.",
        )

    @staticmethod
    def _is_operator_control_mirror_node(node: dict[str, Any]) -> bool:
        return (
            _safe_text(node.get("source_type"), 120) == "operator_control"
            and _safe_text(node.get("work_class"), 120) in {"operator_requested", "maintenance_pressure"}
        )

    def notices_from_work_tree_state(
        self,
        work_tree_state: Any,
        *,
        executable_tools: list[str] | tuple[str, ...] | set[str] | None = None,
        limit: int = 12,
    ) -> list[dict[str, Any]]:
        """Translate Work Tree pressure into operator requests.

        This reads Work Tree state, not chat content. It names the missing
        tool, blocked policy, or information/repair request that prevents a
        branch from moving.
        """
        executable = _safe_set(list(executable_tools or []))
        notices: list[dict[str, Any]] = []
        seen: set[str] = set()

        def add(notice: dict[str, Any]) -> None:
            key = _safe_text(notice.get("dedupe_key"), 220)
            if not key or key in seen:
                return
            seen.add(key)
            notices.append(notice)

        for tree in self._work_tree_trees(work_tree_state):
            if len(notices) >= max(1, int(limit or 1)):
                break
            tree_id = _safe_text(tree.get("tree_id"), 120)
            tree_title = _safe_text(tree.get("title"), 220)
            tree_status = _safe_text(tree.get("status"), 80).lower()
            if tree_status and tree_status not in {"active", "working"}:
                continue

            next_step = _safe_dict(tree.get("next_step"))
            action = _safe_text(next_step.get("action"), 80)
            branch_id = _safe_text(next_step.get("branch_id"), 120)
            branch_title = _safe_text(next_step.get("branch_title"), 220)
            task_id = _safe_text(next_step.get("task_id"), 120)
            task_title = _safe_text(next_step.get("task_title"), 260)
            tool_name = _safe_text(next_step.get("recommended_tool"), 120)

            if action == "missing_tool_assignment":
                suggested = [
                    _safe_text(item, 80)
                    for item in _safe_list(next_step.get("suggested_tools"))[:6]
                    if _safe_text(item, 80)
                ]
                message = (
                    f"I need a governed tool assignment for {branch_title or tree_title}. "
                    f"Current task: {task_title or task_id or 'unknown task'}."
                )
                if suggested:
                    message += " Suggested tools: " + ", ".join(suggested) + "."
                add(
                    {
                        "source": "work_tree",
                        "severity": "attention",
                        "title": f"Nova needs a tool assignment: {branch_title or tree_title}",
                        "message": message,
                        "dedupe_key": f"work_tree|missing_tool_assignment|{tree_id}|{branch_id}|{task_id}",
                        "payload": self._work_tree_notice_payload(
                            tree_id=tree_id,
                            tree_title=tree_title,
                            branch_id=branch_id,
                            branch_title=branch_title,
                            task_id=task_id,
                            task_title=task_title,
                            request_kind="tool_assignment",
                            next_step=next_step,
                            extra={"suggested_tools": suggested},
                        ),
                    }
                )
            elif action == "wait_for_tools":
                missing = [
                    _safe_text(item, 80)
                    for item in _safe_list(next_step.get("missing_tools"))
                    if _safe_text(item, 80)
                ]
                add(
                    {
                        "source": "work_tree",
                        "severity": "attention",
                        "title": f"Nova needs tool readiness: {branch_title or tree_title}",
                        "message": (
                            f"I need these tool(s) made ready for {branch_title or tree_title}: "
                            f"{', '.join(missing) if missing else 'required tools'}."
                        ),
                        "dedupe_key": f"work_tree|wait_for_tools|{tree_id}|{branch_id}|{','.join(missing)}",
                        "payload": self._work_tree_notice_payload(
                            tree_id=tree_id,
                            tree_title=tree_title,
                            branch_id=branch_id,
                            branch_title=branch_title,
                            task_id=task_id,
                            task_title=task_title,
                            request_kind="tool_readiness",
                            next_step=next_step,
                            extra={"missing_tools": missing},
                        ),
                    }
                )
            elif action == "governance_blocked":
                reason = _safe_text(next_step.get("reason"), 220)
                add(
                    {
                        "source": "work_tree",
                        "severity": "attention",
                        "title": f"Nova needs tool policy corrected: {tool_name or branch_title or tree_title}",
                        "message": (
                            f"I need {tool_name or 'the selected tool'} unblocked or policy-corrected for "
                            f"{branch_title or tree_title}. Reason: {reason or 'governance_blocked'}."
                        ),
                        "dedupe_key": f"work_tree|governance_blocked|{tree_id}|{branch_id}|{tool_name}|{reason}",
                        "payload": self._work_tree_notice_payload(
                            tree_id=tree_id,
                            tree_title=tree_title,
                            branch_id=branch_id,
                            branch_title=branch_title,
                            task_id=task_id,
                            task_title=task_title,
                            request_kind="tool_policy",
                            next_step=next_step,
                            extra={"blocked_reason": reason, "recommended_tool": tool_name},
                        ),
                    }
                )
            elif action == "execute" and executable and tool_name and tool_name not in executable:
                add(
                    {
                        "source": "work_tree",
                        "severity": "attention",
                        "title": f"Nova needs maintenance tool dispatch: {tool_name}",
                        "message": (
                            f"I need the {tool_name} tool wired into autonomy maintenance for "
                            f"{branch_title or tree_title}. Current task: {task_title or task_id or 'unknown task'}."
                        ),
                        "dedupe_key": f"work_tree|maintenance_tool_dispatch|{tree_id}|{branch_id}|{task_id}|{tool_name}",
                        "payload": self._work_tree_notice_payload(
                            tree_id=tree_id,
                            tree_title=tree_title,
                            branch_id=branch_id,
                            branch_title=branch_title,
                            task_id=task_id,
                            task_title=task_title,
                            request_kind="maintenance_tool_dispatch",
                            next_step=next_step,
                            extra={"recommended_tool": tool_name},
                        ),
                    }
                )

            for node in [
                dict(item)
                for item in _safe_list(tree.get("nodes"))
                if isinstance(item, dict)
            ]:
                if len(notices) >= max(1, int(limit or 1)):
                    break
                node_branch_id = _safe_text(node.get("id"), 120)
                node_title = _safe_text(node.get("title"), 220)
                current_task = _safe_dict(node.get("current_task"))
                node_task_id = _safe_text(current_task.get("task_id"), 120)
                node_task_title = _safe_text(current_task.get("title"), 260)
                node_status = _safe_text(node.get("status"), 80).lower()
                resolution_state = _safe_text(node.get("resolution_state"), 80).lower()
                task_status = _safe_text(current_task.get("status"), 80).lower()
                has_live_task = bool(node_task_id or node_task_title) and task_status not in {"complete", "dropped", "blocked"}
                branch_closed = node_status in {"complete", "archived"} or resolution_state in {"resolved", "retired"}
                tool_state = _safe_dict(node.get("tool_state"))
                failed_tools = [
                    _safe_text(tool, 120)
                    for tool, state in tool_state.items()
                    if _safe_text(state, 80).lower() == "failed" and _safe_text(tool, 120)
                ]
                if failed_tools and has_live_task and not branch_closed:
                    failed_label = ", ".join(failed_tools[:4])
                    add(
                        {
                            "source": "work_tree",
                            "severity": "attention",
                            "title": f"Nova needs tool failure judgment: {failed_label}",
                            "message": (
                                f"Tool failure evidence exists for {node_title or tree_title}: {failed_label}. "
                                f"Current task: {node_task_title or node_task_id or 'unknown task'}. "
                                "Nova needs judgment before treating this as retryable work."
                            ),
                            "dedupe_key": f"work_tree|tool_failed|{tree_id}|{node_branch_id}|{node_task_id}|{failed_label}",
                            "payload": self._work_tree_notice_payload(
                                tree_id=tree_id,
                                tree_title=tree_title,
                                branch_id=node_branch_id,
                                branch_title=node_title,
                                task_id=node_task_id,
                                task_title=node_task_title,
                                request_kind="tool_failure_judgment",
                                task=current_task,
                                extra={"failed_tools": failed_tools},
                            ),
                        }
                    )
                    if len(notices) >= max(1, int(limit or 1)):
                        break
                if _safe_text(node.get("status"), 80).lower() != "blocked":
                    continue
                if self._is_operator_control_mirror_node(node):
                    continue
                if not current_task:
                    continue
                task_status = _safe_text(current_task.get("status"), 80).lower()
                if task_status in {"complete", "dropped"}:
                    continue
                task_meta = _safe_dict(current_task.get("meta"))
                reason = _safe_text(
                    task_meta.get("blocked_reason")
                    or task_meta.get("block_reason")
                    or node.get("resolution_state")
                    or node.get("actionability"),
                    220,
                )
                source = "/".join(
                    item
                    for item in (
                        _safe_text(node.get("source_type"), 80),
                        _safe_text(node.get("work_class"), 80),
                    )
                    if item
                )
                kind = self._blocked_request_kind(reason, node)
                title, message = self._blocked_message(kind, node_title, node_task_title, reason, source)
                add(
                    {
                        "source": "work_tree",
                        "severity": "attention",
                        "title": title,
                        "message": message,
                        "dedupe_key": self.blocked_work_dedupe_key(
                            tree_id=tree_id,
                            branch_id=node_branch_id,
                            blocked_reason=reason,
                        ),
                        "payload": self._work_tree_notice_payload(
                            tree_id=tree_id,
                            tree_title=tree_title,
                            branch_id=node_branch_id,
                            branch_title=node_title,
                            task_id=node_task_id,
                            task_title=node_task_title,
                            request_kind=kind,
                            task=current_task,
                            extra={
                                "blocked_reason": reason,
                                "source_type": _safe_text(node.get("source_type"), 120),
                                "work_class": _safe_text(node.get("work_class"), 120),
                                "actionability": _safe_text(node.get("actionability"), 80),
                                "resolution_state": _safe_text(node.get("resolution_state"), 80),
                            },
                        ),
                    }
                )

        return notices

    def notice_from_autonomy(self, packet: dict[str, Any], execution: dict[str, Any]) -> dict[str, Any]:
        packet_data = _safe_dict(packet)
        execution_data = _safe_dict(execution)
        recommended = _safe_dict(packet_data.get("recommended_action"))
        action_type = _safe_text(
            execution_data.get("action_type") or recommended.get("action_type") or recommended.get("target_id"),
            120,
        )
        decision = _safe_text(packet_data.get("decision") or packet_data.get("decision_type"), 80)
        result = _safe_text(execution_data.get("result"), 80)
        reason = _safe_text(
            execution_data.get("gate_reason")
            or execution_data.get("message")
            or packet_data.get("reason")
            or packet_data.get("explain_text"),
            500,
        )
        rejection_reasons = [
            _safe_text(item, 120)
            for item in (_safe_list(packet_data.get("rejection_reasons")) or _safe_list(execution_data.get("refusal_reasons")))
            if _safe_text(item, 120)
        ]
        requires_ack = bool(recommended.get("requires_ack") or execution_data.get("requires_ack"))

        if (
            decision in {"defer_with_reason", "defer"}
            and result in {"", "blocked"}
            and rejection_reasons
            and all(_autonomy_internal_wait_reason(reason) for reason in rejection_reasons)
            and not requires_ack
        ):
            return {}

        should_notice = False
        if decision and decision != "recommend_action":
            should_notice = True
        if result in {"blocked", "failed", "error"}:
            should_notice = True
        if rejection_reasons:
            should_notice = True
        if requires_ack and result != "success":
            should_notice = True
        if not should_notice:
            return {}

        label = action_type or decision or "autonomy"
        details = []
        if reason:
            details.append(reason)
        if rejection_reasons:
            details.append("rejections: " + ", ".join(rejection_reasons[:4]))
        if requires_ack:
            details.append("operator acknowledgement is required")
        detail_text = "; ".join(details).strip()
        message = f"I am stuck on {label}."
        if detail_text:
            message += f" {detail_text}"

        return {
            "source": "autonomy_maintenance",
            "severity": "attention" if result != "failed" else "error",
            "title": f"Nova needs operator attention: {label}",
            "message": message,
            "dedupe_key": "|".join([label, decision, result, reason, ",".join(rejection_reasons[:4])])[:220],
            "payload": {
                "decision": decision,
                "action_type": action_type,
                "execution_result": result,
                "reason": reason,
                "rejection_reasons": rejection_reasons,
                "recommended_action": recommended,
            },
        }


OPERATOR_OUTBOX_SERVICE = OperatorOutboxService()
