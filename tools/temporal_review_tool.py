from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .base_tool import NovaTool, ToolContext, ToolInvocationError
from services.nova_calendar_ingestion import parse_ics_file, parse_ics_text
from services.nova_temporal_service import NovaTemporalService, TemporalEvent, TemporalPressure, build_temporal_pressure


def _safe_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _maybe_json(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text or not text.startswith(("{", "[")):
        return value
    try:
        return json.loads(text)
    except Exception:
        return value


def _load_input_payload(args: dict[str, Any]) -> Any:
    for key in ("pressure", "temporal_pressure", "event", "payload", "input"):
        if key in args:
            value = args.get(key)
            if value is None or value == "":
                continue
            if isinstance(value, str):
                value = _maybe_json(value)
            return value

    path_value = str(args.get("path") or args.get("file") or "").strip()
    if not path_value:
        return {}
    path = Path(path_value)
    if not path.exists():
        raise ToolInvocationError("temporal_input_not_found")
    if path.suffix.lower() == ".ics":
        return parse_ics_file(path)
    text = path.read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except Exception:
        return parse_ics_text(text) if "BEGIN:VEVENT" in text else {"title": path.stem, "note": text}


def _pressure_from_input(item: Any) -> TemporalPressure:
    if isinstance(item, TemporalPressure):
        return item
    if isinstance(item, TemporalEvent):
        return build_temporal_pressure(item)
    if isinstance(item, dict):
        nested = item.get("pressure") if isinstance(item.get("pressure"), dict) else item.get("temporal_pressure")
        if isinstance(nested, dict):
            event_data = nested.get("event") if isinstance(nested.get("event"), dict) else {}
            if event_data:
                return build_temporal_pressure(event_data)
        return build_temporal_pressure(item)
    if isinstance(item, list):
        first = next((value for value in item if isinstance(value, (dict, TemporalEvent, TemporalPressure))), None)
        if first is None:
            return build_temporal_pressure({})
        return _pressure_from_input(first)
    return build_temporal_pressure({})


class TemporalReviewTool(NovaTool):
    name = "temporal_review"
    description = "Review temporal pressure and route it to work-tree, outbox, or silent scheduling"
    category = "planning"
    safe = True
    requires_admin = False
    locality = "local"
    mutating = False
    scope = "user"

    def check_policy(self, args: dict[str, Any], context: ToolContext) -> tuple[bool, str]:
        ok, reason = super().check_policy(args, context)
        if not ok:
            return ok, reason
        tools = context.policy.get("tools_enabled") if isinstance(context.policy, dict) else {}
        if isinstance(tools, dict) and "temporal_review" in tools and not bool(tools.get("temporal_review")):
            return False, "temporal_review_tool_disabled"
        return True, ""

    def run(self, args: dict[str, Any], context: ToolContext) -> str:
        action = str(args.get("action") or "review").strip().lower()
        if action not in {"review", "assess", "route"}:
            raise ToolInvocationError("unknown_temporal_action")

        payload = _load_input_payload(args or {})
        service = NovaTemporalService()

        if payload in ({}, [], None, ""):
            return json.dumps({"tool": self.name, "status": "no_temporal_input"}, ensure_ascii=True, sort_keys=True)

        if isinstance(payload, list):
            pressures = [_pressure_from_input(item) for item in payload if item is not None]
            if not pressures:
                return json.dumps({"tool": self.name, "status": "no_temporal_input"}, ensure_ascii=True, sort_keys=True)
            results = [dict(service.route_pressure(pressure), pressure=pressure.to_dict()) for pressure in pressures]
            return json.dumps({"tool": self.name, "status": "ok", "results": results}, ensure_ascii=True, sort_keys=True)

        pressure = _pressure_from_input(payload)
        routed = service.route_pressure(pressure)
        result = {
            "tool": self.name,
            "status": "ok",
            "pressure": pressure.to_dict(),
            "decision": routed,
            "context": _safe_dict(context.extra),
        }
        return json.dumps(result, ensure_ascii=True, sort_keys=True)