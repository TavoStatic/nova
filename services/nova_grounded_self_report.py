"""Ground live self-report replies in runtime status and Work Tree truth."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


NO_ACTIVE_STUCK_POINT_LINE = "I do not see an active stuck point in live control status right now."
LIVE_STATUS_SOURCE_LINE = "Source: live control status and Work Tree."


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _truthy(value: Any) -> bool:
    return value is True or str(value).strip().lower() in {"true", "yes", "ok", "ready", "running"}


def _text(value: Any, default: str = "unknown") -> str:
    if value is None:
        return default
    rendered = str(value).strip()
    return rendered if rendered else default


@dataclass(frozen=True)
class TroubleItem:
    kind: str
    message: str
    source: str


class NovaGroundedSelfReportService:
    """Build deterministic self-status replies from live status surfaces."""

    def build_payload(
        self,
        status_payload: dict[str, Any] | None,
        work_trees_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        status = _as_dict(status_payload)
        work_trees = _as_dict(work_trees_payload)
        release = _as_dict(status.get("release_status"))
        memory = _as_dict(status.get("memory_health"))
        ollama = _as_dict(status.get("ollama_health"))
        cleared_source_keys = self._cleared_work_tree_source_keys(status)
        work_item = self._first_open_work_item(work_trees, cleared_source_keys=cleared_source_keys)

        health_score = status.get("health_score")
        alerts = [str(item).strip() for item in _as_list(status.get("alerts")) if str(item).strip()]
        work_tree_truth = _text(status.get("work_tree_truth_status"), "")
        open_task_count = status.get("work_tree_open_task_count")
        filtered_open_count = self._filtered_open_task_count(work_trees, cleared_source_keys=cleared_source_keys)
        if filtered_open_count is not None:
            open_task_count = filtered_open_count
            if filtered_open_count == 0 and not work_item and work_tree_truth in {"open", "operator_hold", "blocked_observing"}:
                work_tree_truth = "clear"
        release_readiness = _text(
            release.get("release_readiness")
            or release.get("latest_readiness_state")
            or release.get("latest_state"),
            "",
        )
        latest_source_status = _text(
            release.get("latest_source_status")
            or release.get("source_status")
            or release.get("latest_readiness_state"),
            "",
        )
        latest_artifact_stale = release.get("latest_artifact_stale")

        status_for_trouble = dict(status)
        status_for_trouble["work_tree_truth_status"] = work_tree_truth
        status_for_trouble["work_tree_open_task_count"] = open_task_count
        trouble_items = self._trouble_items(
            status=status_for_trouble,
            release=release,
            memory=memory,
            ollama=ollama,
            alerts=alerts,
            work_item=work_item,
        )

        return {
            "health_score": health_score,
            "alerts": alerts,
            "work_tree_truth_status": work_tree_truth or "unknown",
            "work_tree_open_task_count": open_task_count,
            "work_item": work_item,
            "release": {
                "readiness": release_readiness or "unknown",
                "latest_source_status": latest_source_status or "unknown",
                "latest_artifact_stale": latest_artifact_stale,
                "artifact": _text(
                    release.get("latest_artifact")
                    or release.get("latest_artifact_name")
                    or release.get("latest_artifact_path"),
                    "",
                ),
            },
            "ollama": {
                "chat_ready": status.get("ollama_chat_ready", ollama.get("chat_ready")),
                "status": _text(ollama.get("status") or status.get("ollama_status"), ""),
                "model": _text(status.get("ollama_model") or ollama.get("model"), ""),
            },
            "memory": {
                "status": _text(memory.get("status") or status.get("memory_health_status"), ""),
                "enabled": status.get("memory_enabled"),
            },
            "runtime": {
                "core": self._service_state(status.get("core")),
                "guard": self._service_state(status.get("guard")),
                "webui": self._service_state(status.get("webui")),
            },
            "trouble_items": [item.__dict__ for item in trouble_items],
        }

    def render(self, mode: str, payload: dict[str, Any]) -> str:
        mode = mode if mode in {"health", "trouble", "internals"} else "internals"
        if mode == "health":
            return self._render_health(payload)
        if mode == "trouble":
            return self._render_trouble(payload)
        return self._render_internals(payload)

    def build_operator_attention(self, payload: dict[str, Any]) -> dict[str, Any]:
        items = [_as_dict(item) for item in _as_list(payload.get("trouble_items")) if isinstance(item, dict)]
        summary = self._trouble_summary(payload)
        active = bool(summary)
        kinds = [str(item.get("kind") or "").strip() for item in items if str(item.get("kind") or "").strip()]
        if not active:
            return {
                "active": False,
                "level": "clear",
                "message": "I do not need operator help from live status right now.",
                "source": "live_control_status_and_work_tree",
                "items": [],
            }
        work_tree_status = _text(payload.get("work_tree_truth_status"), "")
        if work_tree_status == "operator_hold":
            level = "operator_hold"
        elif "work_tree" in kinds:
            level = "work_tree_attention"
        else:
            level = "attention"
        if "release" in kinds and level not in {"operator_hold", "work_tree_attention"}:
            level = "release_attention"
        return {
            "active": True,
            "level": level,
            "message": f"I need help with: {summary}",
            "source": "live_control_status_and_work_tree",
            "items": items[:5],
        }

    def render_source_unavailable(self, mode: str, error: str) -> str:
        label = "health" if mode == "health" else "internal status"
        return (
            f"I recognized this as a live {label} question, but I could not read live "
            f"control status: {_text(error, 'unknown error')}. I should not invent a clean status."
        )

    def _trouble_items(
        self,
        *,
        status: dict[str, Any],
        release: dict[str, Any],
        memory: dict[str, Any],
        ollama: dict[str, Any],
        alerts: list[str],
        work_item: dict[str, Any],
    ) -> list[TroubleItem]:
        items: list[TroubleItem] = []
        for alert in alerts:
            items.append(TroubleItem("alert", f"Control status alert: {alert}", "control_status.alerts"))

        work_tree_truth = _text(status.get("work_tree_truth_status"), "")
        open_task_count = status.get("work_tree_open_task_count")
        if work_tree_truth and work_tree_truth not in {"clear", "ok", "healthy", "unknown"}:
            detail = f"Work Tree is {work_tree_truth}"
            if open_task_count not in (None, ""):
                detail += f" with {open_task_count} open task(s)"
            if work_item:
                detail += f"; current branch: {work_item.get('title', 'unknown')}"
                task = work_item.get("current_task")
                if task:
                    detail += f"; task: {task}"
            items.append(TroubleItem("work_tree", detail, "control_status.work_tree_truth_status"))

        release_readiness = _text(
            release.get("release_readiness")
            or release.get("latest_readiness_state")
            or release.get("latest_state"),
            "",
        )
        source_status = _text(
            release.get("latest_source_status")
            or release.get("source_status")
            or release.get("latest_readiness_state"),
            "",
        )
        artifact_stale = release.get("latest_artifact_stale")
        if artifact_stale is True or source_status in {"source-changed-after-build", "changed-after-build", "stale"}:
            items.append(
                TroubleItem(
                    "release",
                    "Release package is stale behind live source and needs rebuild verification.",
                    "control_status.release_status",
                )
            )
        elif release_readiness == "needs-promotion":
            record_complete = bool(release.get("latest_validation_record_complete"))
            record_result = _text(release.get("latest_validation_record_result"), "")
            missing_fields = release.get("latest_validation_record_missing_fields")
            missing_count = len(missing_fields) if isinstance(missing_fields, list) else 0
            if record_complete:
                detail = f"Release validation record is complete with result {record_result}; promotion ledger entry is still missing."
            else:
                detail = f"Release package is verified but validation outcome is incomplete; missing validation fields: {missing_count}."
            items.append(
                TroubleItem(
                    "release",
                    detail,
                    "control_status.release_status",
                )
            )
        elif release_readiness and release_readiness not in {"ready", "ready-with-notes", "current", "ok", "unknown"}:
            items.append(
                TroubleItem(
                    "release",
                    f"Release readiness is {release_readiness}.",
                    "control_status.release_status",
                )
            )

        chat_ready = status.get("ollama_chat_ready", ollama.get("chat_ready"))
        ollama_status = _text(ollama.get("status") or status.get("ollama_status"), "")
        if chat_ready is False or (ollama_status and ollama_status not in {"ok", "ready", "running", "unknown"}):
            state = "not chat-ready" if chat_ready is False else ollama_status
            items.append(TroubleItem("ollama", f"Ollama is {state}.", "control_status.ollama"))

        memory_status = _text(memory.get("status") or status.get("memory_health_status"), "")
        if memory_status and memory_status not in {"ok", "ready", "healthy", "unknown"}:
            items.append(TroubleItem("memory", f"Memory health is {memory_status}.", "control_status.memory"))

        for name in ("core", "guard", "webui"):
            service_state = self._service_state(status.get(name))
            if service_state and service_state not in {"ok", "ready", "running", "unknown"}:
                items.append(TroubleItem("runtime", f"{name} is {service_state}.", f"control_status.{name}"))

        return items

    def _cleared_work_tree_source_keys(self, status: dict[str, Any]) -> set[str]:
        cleared: set[str] = set()
        for component in ("guard", "core", "webui"):
            if self._component_running(status.get(component)) is True:
                cleared.add(f"runtime_failure:runtime_core:process_not_running:{component}")
        heartbeat_age = status.get("core_heartbeat_age_sec", status.get("heartbeat_age_sec"))
        try:
            heartbeat_age_int = int(heartbeat_age)
        except Exception:
            heartbeat_age_int = None
        if heartbeat_age_int is not None and heartbeat_age_int <= 30:
            cleared.add("runtime_failure:runtime_core:heartbeat_stale:core_heartbeat")
        if status.get("maintenance_scheduler_active") is True:
            cleared.add("maintenance_pressure:scheduler_registry:maintenance_scheduler_inactive:autonomy_maintenance")
        failures = status.get("runtime_failures") if isinstance(status.get("runtime_failures"), dict) else {}
        for service, row in failures.items():
            if not isinstance(row, dict):
                continue
            level = str(row.get("level") or "").strip().lower()
            service_name = str(service or row.get("service") or "").strip().lower()
            if service_name and level in {"", "good", "ok", "info"}:
                cleared.add(f"runtime_failure:runtime_failures:runtime_failure_reason:{service_name}")
        return cleared

    def _component_running(self, value: Any) -> bool | None:
        if not isinstance(value, dict):
            return None
        if "running" in value:
            return bool(value.get("running"))
        status = str(value.get("status") or value.get("state") or "").strip().lower()
        if status in {"running", "ok", "healthy", "up", "online"}:
            return True
        if status in {"stopped", "failed", "down", "offline", "missing"}:
            return False
        return None

    def _node_is_cleared(self, node: dict[str, Any], cleared_source_keys: set[str]) -> bool:
        source_key = str(node.get("source_key") or "").strip()
        return bool(source_key and source_key in cleared_source_keys)

    def _filtered_open_task_count(self, payload: dict[str, Any], *, cleared_source_keys: set[str]) -> int | None:
        if not cleared_source_keys or not isinstance(payload, dict):
            return None
        count = 0
        saw_node = False
        for tree in _as_list(payload.get("trees")):
            tree_dict = _as_dict(tree)
            for node in _as_list(tree_dict.get("nodes")):
                node_dict = _as_dict(node)
                if not node_dict or self._node_is_cleared(node_dict, cleared_source_keys):
                    continue
                status = _text(node_dict.get("status"), "")
                if status in {"complete", "archived"}:
                    continue
                open_tasks = node_dict.get("open_task_count", node_dict.get("tasks_open"))
                if isinstance(open_tasks, int):
                    count += max(0, open_tasks)
                    saw_node = True
                elif status in {"ready", "active", "blocked", "stalled"}:
                    count += 1
                    saw_node = True
        return count if saw_node or cleared_source_keys else None

    def _first_open_work_item(self, payload: dict[str, Any], *, cleared_source_keys: set[str] | None = None) -> dict[str, Any]:
        cleared = set(cleared_source_keys or set())
        candidates: list[dict[str, Any]] = []
        for tree in _as_list(payload.get("trees")):
            tree_dict = _as_dict(tree)
            for node in _as_list(tree_dict.get("nodes")):
                node_dict = _as_dict(node)
                if not node_dict:
                    continue
                if self._node_is_cleared(node_dict, cleared):
                    continue
                open_tasks = node_dict.get("open_task_count", node_dict.get("tasks_open"))
                node_status = _text(node_dict.get("status"), "")
                resolution_state = _text(node_dict.get("resolution_state"), "")
                if (
                    node_status in {"complete", "completed", "resolved", "retired", "archived"}
                    or resolution_state in {"complete", "completed", "resolved", "retired", "archived"}
                ):
                    continue
                resolution = resolution_state or node_status
                current_task = _as_dict(node_dict.get("current_task"))
                has_open_task = bool(current_task) or (isinstance(open_tasks, int) and open_tasks > 0)
                if has_open_task or resolution in {"open", "observing", "blocked", "operator_hold", "active"}:
                    candidates.append(
                        {
                            "title": _text(node_dict.get("title") or node_dict.get("label"), ""),
                            "status": resolution or "unknown",
                            "current_task": _text(
                                current_task.get("title") or current_task.get("description"),
                                "",
                            ),
                        }
                    )
        return candidates[0] if candidates else {}

    def _service_state(self, value: Any) -> str:
        if isinstance(value, dict):
            if "status" in value:
                return _text(value.get("status"), "")
            if "state" in value:
                return _text(value.get("state"), "")
            if "running" in value:
                return "running" if _truthy(value.get("running")) else "stopped"
            if "ok" in value:
                return "ok" if _truthy(value.get("ok")) else "not_ok"
        return _text(value, "")

    def _render_health(self, payload: dict[str, Any]) -> str:
        score = payload.get("health_score")
        health_line = f"Live health score is {score}/100." if score is not None else "Live health score is unknown."
        truth = self._work_tree_line(payload)
        trouble = self._trouble_summary(payload)
        alerts = self._alert_line(payload)
        lines = [health_line, truth]
        if alerts:
            lines.append(alerts)
        if trouble:
            lines.append(f"What needs attention: {trouble}")
        else:
            lines.append(NO_ACTIVE_STUCK_POINT_LINE)
        lines.append(LIVE_STATUS_SOURCE_LINE)
        return "\n".join(line for line in lines if line)

    def _render_trouble(self, payload: dict[str, Any]) -> str:
        trouble = self._trouble_summary(payload)
        lines = []
        if trouble:
            lines.append(f"Today I am mainly stuck on: {trouble}")
        else:
            lines.append(NO_ACTIVE_STUCK_POINT_LINE)
        lines.append(self._work_tree_line(payload))
        release = _as_dict(payload.get("release"))
        readiness = release.get("readiness")
        if readiness and readiness != "unknown":
            lines.append(f"Release readiness: {readiness}.")
        alerts = self._alert_line(payload)
        if alerts:
            lines.append(alerts)
        lines.append(LIVE_STATUS_SOURCE_LINE)
        return "\n".join(line for line in lines if line)

    def _render_internals(self, payload: dict[str, Any]) -> str:
        score = payload.get("health_score")
        score_line = f"health_score {score}/100" if score is not None else "health_score unknown"
        runtime = _as_dict(payload.get("runtime"))
        release = _as_dict(payload.get("release"))
        ollama = _as_dict(payload.get("ollama"))
        memory = _as_dict(payload.get("memory"))
        lines = [
            f"Live internals: {score_line}; {self._work_tree_line(payload)}",
            (
                "Runtime: "
                f"core={runtime.get('core', 'unknown')}, "
                f"guard={runtime.get('guard', 'unknown')}, "
                f"webui={runtime.get('webui', 'unknown')}."
            ),
            (
                "Ollama: "
                f"chat_ready={ollama.get('chat_ready', 'unknown')}, "
                f"status={ollama.get('status', 'unknown')}, "
                f"model={ollama.get('model', 'unknown')}."
            ),
            f"Memory: status={memory.get('status', 'unknown')}, enabled={memory.get('enabled', 'unknown')}.",
            (
                "Release: "
                f"readiness={release.get('readiness', 'unknown')}, "
                f"source={release.get('latest_source_status', 'unknown')}, "
                f"artifact_stale={release.get('latest_artifact_stale', 'unknown')}."
            ),
        ]
        trouble = self._trouble_summary(payload)
        if trouble:
            lines.append(f"What needs attention: {trouble}")
        alerts = self._alert_line(payload)
        if alerts:
            lines.append(alerts)
        lines.append(LIVE_STATUS_SOURCE_LINE)
        return "\n".join(line for line in lines if line)

    def _work_tree_line(self, payload: dict[str, Any]) -> str:
        status = _text(payload.get("work_tree_truth_status"), "unknown")
        count = payload.get("work_tree_open_task_count")
        if count not in (None, ""):
            line = f"Work Tree is {status} with {count} open task(s)."
        else:
            line = f"Work Tree is {status}."
        work_item = _as_dict(payload.get("work_item"))
        if work_item:
            title = work_item.get("title")
            task = work_item.get("current_task")
            if title:
                line += f" Current branch: {title}."
            if task:
                line += f" Current task: {task}."
        return line

    def _trouble_summary(self, payload: dict[str, Any]) -> str:
        items = [_as_dict(item).get("message", "") for item in _as_list(payload.get("trouble_items"))]
        items = [str(item).strip() for item in items if str(item).strip()]
        return "; ".join(items[:3])

    def _alert_line(self, payload: dict[str, Any]) -> str:
        alerts = [str(item).strip() for item in _as_list(payload.get("alerts")) if str(item).strip()]
        if not alerts:
            return ""
        return "Alerts: " + "; ".join(alerts[:3]) + "."


GROUNDED_SELF_REPORT_SERVICE = NovaGroundedSelfReportService()
