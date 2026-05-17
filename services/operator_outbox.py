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
    def read_events(path: Path, *, after_id: str = "", limit: int = 20) -> list[dict[str, Any]]:
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
                    rows.append(item)
        except Exception:
            return []

        after = str(after_id or "").strip()
        if after:
            rows = [row for row in rows if str(row.get("id") or "") > after]
        return rows[-max(1, int(limit or 1)) :]

    def summary(self, path: Path, *, limit: int = 5) -> dict[str, Any]:
        events = self.read_events(path, limit=limit)
        latest = events[-1] if events else {}
        return {
            "ok": True,
            "count": len(events),
            "latest_id": str(latest.get("id") or ""),
            "latest": latest,
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
        existing = self.read_events(path, limit=max_events)
        if dedupe:
            for row in reversed(existing):
                if str(row.get("dedupe_key") or "") != dedupe:
                    continue
                try:
                    age = now_value - float(row.get("ts_epoch") or 0.0)
                except Exception:
                    age = 0.0
                if age <= max(0, int(dedupe_window_sec or 0)):
                    return {"ok": True, "deduped": True, "event": row}
                break

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
            "payload": _compact(payload or {}),
        }

        rows = existing[-max(0, int(max_events or 1) - 1) :] + [event]
        outbox_path = Path(path)
        outbox_path.parent.mkdir(parents=True, exist_ok=True)
        outbox_path.write_text(
            "\n".join(json.dumps(row, ensure_ascii=True, sort_keys=True) for row in rows) + "\n",
            encoding="utf-8",
        )
        return {"ok": True, "deduped": False, "event": event}

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
                        "payload": {"tree": tree, "next_step": next_step, "request_kind": "tool_assignment"},
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
                        "payload": {"tree": tree, "next_step": next_step, "request_kind": "tool_readiness"},
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
                        "payload": {"tree": tree, "next_step": next_step, "request_kind": "tool_policy"},
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
                        "payload": {"tree": tree, "next_step": next_step, "request_kind": "maintenance_tool_dispatch"},
                    }
                )

            for node in [
                dict(item)
                for item in _safe_list(tree.get("nodes"))
                if isinstance(item, dict)
            ]:
                if len(notices) >= max(1, int(limit or 1)):
                    break
                if _safe_text(node.get("status"), 80).lower() != "blocked":
                    continue
                current_task = _safe_dict(node.get("current_task"))
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
                node_branch_id = _safe_text(node.get("id"), 120)
                node_title = _safe_text(node.get("title"), 220)
                node_task_id = _safe_text(current_task.get("task_id"), 120)
                node_task_title = _safe_text(current_task.get("title"), 260)
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
                        "dedupe_key": f"work_tree|blocked_task|{tree_id}|{node_branch_id}|{node_task_id}|{reason}",
                        "payload": {
                            "tree_id": tree_id,
                            "tree_title": tree_title,
                            "branch_id": node_branch_id,
                            "branch_title": node_title,
                            "task": current_task,
                            "blocked_reason": reason,
                            "request_kind": kind,
                            "source_type": _safe_text(node.get("source_type"), 120),
                            "work_class": _safe_text(node.get("work_class"), 120),
                            "actionability": _safe_text(node.get("actionability"), 80),
                            "resolution_state": _safe_text(node.get("resolution_state"), 80),
                            "source_payload": _safe_dict(node.get("source_payload")),
                        },
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
