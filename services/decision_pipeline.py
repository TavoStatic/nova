from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


StageHandler = Callable[[dict[str, Any]], dict[str, Any]]


def _clean_trace_data(raw: dict[str, Any]) -> dict[str, Any]:
    clean: dict[str, Any] = {}
    for key, value in raw.items():
        if value is None:
            continue
        if isinstance(value, str):
            if value.strip():
                clean[str(key)] = value[:220]
            continue
        if isinstance(value, (bool, int)):
            clean[str(key)] = value
            continue
        if isinstance(value, float):
            clean[str(key)] = round(value, 4)
            continue
        if isinstance(value, (list, tuple)):
            items: list[Any] = []
            for item in list(value)[:8]:
                if isinstance(item, str):
                    if item.strip():
                        items.append(item[:120])
                elif isinstance(item, (bool, int, float)):
                    items.append(item)
            if items:
                clean[str(key)] = items
            continue
        if isinstance(value, dict):
            nested: dict[str, Any] = {}
            for nested_key, nested_value in list(value.items())[:8]:
                if isinstance(nested_value, str):
                    if nested_value.strip():
                        nested[str(nested_key)] = nested_value[:120]
                elif isinstance(nested_value, (bool, int, float)):
                    nested[str(nested_key)] = nested_value
            if nested:
                clean[str(key)] = nested
    return clean


def make_trace_entry(stage: str, result: str, detail: str = "", **data: Any) -> dict[str, Any]:
    entry = {
        "stage": str(stage or "unknown").strip() or "unknown",
        "result": str(result or "unknown").strip() or "unknown",
    }
    clean_detail = str(detail or "").strip()
    if clean_detail:
        entry["detail"] = clean_detail[:220]
    clean_data = _clean_trace_data(data)
    if clean_data:
        entry["data"] = clean_data
    return entry


@dataclass(order=True)
class RegisteredStage:
    priority: int
    name: str = field(compare=False)
    handler: StageHandler = field(compare=False)


class StageRegistry:
    def __init__(self) -> None:
        self._stages: list[RegisteredStage] = []

    def register(self, name: str, *, priority: int, handler: StageHandler) -> None:
        stage_name = str(name or "").strip()
        if not stage_name:
            raise ValueError("Stage name is required")
        self._stages = [stage for stage in self._stages if stage.name != stage_name]
        self._stages.append(RegisteredStage(priority=int(priority), name=stage_name, handler=handler))

    def ordered(self) -> list[RegisteredStage]:
        return sorted(self._stages)


def run_registered_stages(registry: StageRegistry, context: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = context if isinstance(context, dict) else {}
    ordered = registry.ordered()
    decision_trace: list[dict[str, Any]] = []

    for index, stage in enumerate(ordered):
        outcome = stage.handler(payload)
        result_payload = outcome if isinstance(outcome, dict) else {}
        handled = bool(result_payload.get("handled"))
        result = str(result_payload.get("result") or ("handled" if handled else "pass")).strip() or ("handled" if handled else "pass")
        detail = str(result_payload.get("detail") or "")
        trace_data = result_payload.get("data") if isinstance(result_payload.get("data"), dict) else {}
        decision_trace.append(make_trace_entry(stage.name, result, detail, **trace_data))

        if not handled:
            continue

        for skipped_stage in ordered[index + 1:]:
            decision_trace.append(make_trace_entry(skipped_stage.name, "skipped", handled_by=stage.name))

        meta = dict(result_payload.get("meta") or {})
        meta["decision_trace"] = list(decision_trace)
        meta["decision_stage"] = stage.name
        return {
            "handled": True,
            "reply": str(result_payload.get("reply") or ""),
            "meta": meta,
            "decision_trace": decision_trace,
            "decision_stage": stage.name,
        }

    return {
        "handled": False,
        "decision_trace": decision_trace,
        "decision_stage": "",
    }