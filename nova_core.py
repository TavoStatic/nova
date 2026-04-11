# Nova Core (stable) - Voice + Typed chat, tools, local knowledge packs, safe web fetch, safe self-patching
# Target: Windows + Ollama + Faster-Whisper + Piper TTS
#
# Design goals:
# - Deterministic safety: never hallucinate tool output or machine actions.
# - Mixed input: press ENTER for voice, or type a message/command.
# - Piper TTS runs as a subprocess per utterance (reliable).
# - Optional knowledge packs (B-mode, lightweight lexical search).
# - Optional self-patching (zip overlay + snapshot + rollback + compile test).
# - Optional web fetch tool (allowlist + max bytes) that NEVER crashes core.

from __future__ import annotations

import argparse
import importlib
import asyncio
import ast
import importlib.util
import io
import json
import os
import math
import queue
import re
import socket
import subprocess
import threading
import time
import zipfile
import hashlib
import mimetypes
import html
import tempfile
import difflib
from pathlib import Path
from typing import Any, Optional, Tuple
from urllib.parse import urlparse, parse_qs, unquote, urljoin, quote
from conversation_manager import ConversationSession
from subconscious_config import SUBCONSCIOUS_CHARTER
from supervisor import Supervisor
from capabilities import explain_missing, describe_capabilities
from task_engine import analyze_request
from action_planner import decide_actions
from env_inspector import inspect_environment, format_report
import requests
import psutil
from tools import ToolContext, ToolInvocationError, build_default_registry
from services.behavior_metrics import BehaviorMetricsStore
from services.policy_manager import PolicyManager
from services.web_research_session import WebResearchSessionStore
from services.identity_memory import IdentityMemoryService
from services.tool_registry import ToolRegistryService
from services.tool_execution import ToolExecutionService
from services.memory_adapter import MemoryAdapterService
from services.session_state import SessionStateService, SubconsciousState
from services.fulfillment_flow import FulfillmentFlowService
from services.subconscious_runtime import SUBCONSCIOUS_SERVICE
from services.subconscious_reporting import build_robust_weakness_summary, build_training_backlog_summary
from services.nova_fulfillment_routing import evaluate_fulfillment_route_viability
from services.nova_route_probing import build_probe_turn_routes
from services.nova_route_probing import evaluate_deterministic_route_viability
from services.nova_service_builders import build_fulfillment_flow_service
from services.nova_service_builders import build_identity_memory_service
from services.nova_service_builders import build_policy_manager
from services.nova_turn_direction import analyze_routing_text
from services.nova_turn_direction import determine_turn_direction
from services.nova_turn_direction import is_explicit_command_like
from services.nova_runtime_context import ACTION_LEDGER_DIR
from services.nova_runtime_context import AUTONOMY_MAINTENANCE_FILE
from services.nova_runtime_context import BASE_DIR
from services.nova_runtime_context import BEHAVIOR_METRICS_FILE
from services.nova_runtime_context import DEVICE_LOCATION_FILE
from services.nova_runtime_context import GENERATED_DEFINITIONS_DIR
from services.nova_runtime_context import HEALTH_LOG
from services.nova_runtime_context import IDENTITY_FILE
from services.nova_runtime_context import LEARNED_FACTS_FILE
from services.nova_runtime_context import LOG_DIR
from services.nova_runtime_context import MEMORY_DIR
from services.nova_runtime_context import MEMORY_EVENTS_LOG
from services.nova_runtime_context import PENDING_REVIEW_DIR
from services.nova_runtime_context import POLICY_PATH
from services.nova_runtime_context import PROMOTED_DEFINITIONS_DIR
from services.nova_runtime_context import PROMOTION_AUDIT_LOG
from services.nova_runtime_context import PULSE_SNAPSHOT_FILE
from services.nova_runtime_context import PYTHON
from services.nova_runtime_context import QUARANTINE_DIR
from services.nova_runtime_context import RUNTIME_DIR
from services.nova_runtime_context import SELF_REFLECTION_LOG
from services.nova_runtime_context import TEST_SESSIONS_DIR
from services.nova_runtime_context import UPDATE_NOW_PENDING_FILE
from services.nova_runtime_context import get_active_user
from services.nova_runtime_context import set_active_user
try:
    import memory as memory_mod
except Exception:
    memory_mod = None

# -------------------------
# Voice deps are optional
# -------------------------
VOICE_OK = False
VOICE_READY = False
VOICE_IMPORT_ERR = ""
sd = None
wav = None
WhisperModel = None


def _ensure_voice_deps() -> bool:
    """Import voice dependencies only when voice features are actually used."""
    global VOICE_OK, VOICE_READY, VOICE_IMPORT_ERR, sd, wav, WhisperModel

    if VOICE_READY:
        return VOICE_OK

    VOICE_READY = True
    try:
        import sounddevice as _sd
        import scipy.io.wavfile as _wav
        from faster_whisper import WhisperModel as _WhisperModel

        sd = _sd
        wav = _wav
        WhisperModel = _WhisperModel
        VOICE_OK = True
        VOICE_IMPORT_ERR = ""
    except Exception as e:
        VOICE_OK = False
        VOICE_IMPORT_ERR = str(e)
        sd = None
        wav = None
        WhisperModel = None

    return VOICE_OK

import sys


# =========================
# Config / Policy
# =========================
OLLAMA_BASE = "http://127.0.0.1:11434"

SAMPLE_RATE = 16000
CHANNELS = 1

# UX tuning
RECORD_SECONDS = 3
OLLAMA_BOOT_RETRIES = 15
OLLAMA_REQ_TIMEOUT = 1800

# Knowledge packs (B-mode)
KNOWLEDGE_ROOT = BASE_DIR / "knowledge"
PACKS_DIR = KNOWLEDGE_ROOT / "packs"
ACTIVE_PACK_FILE = KNOWLEDGE_ROOT / "active_pack.txt"
KB_MAX_FILES = 3
KB_MAX_CHARS = 2000
CHAT_CONTEXT_TURNS = 6

KNOWN_COLORS = {
    "red", "blue", "green", "yellow", "orange", "purple", "violet", "indigo",
    "pink", "brown", "black", "white", "gray", "grey", "silver", "gold",
    "teal", "cyan", "magenta", "maroon", "navy", "lime", "olive", "beige",
    "turquoise", "lavender", "coral", "burgundy", "tan", "mint", "aqua",
}

KNOWN_ANIMALS = {
    "dog", "dogs", "cat", "cats", "bird", "birds", "fish", "horse", "horses",
    "rabbit", "rabbits", "hamster", "hamsters", "turtle", "turtles", "snake", "snakes",
    "lizard", "lizards", "parrot", "parrots", "eagle", "eagles", "hawk", "hawks",
}

# Web cache folder
WEB_CACHE_DIR = KNOWLEDGE_ROOT / "web"

# Self patching
UPDATES_DIR = BASE_DIR / "updates"
SNAPSHOTS_DIR = UPDATES_DIR / "snapshots"
PATCH_LOG = UPDATES_DIR / "patch.log"
PATCH_REVISION_FILE = UPDATES_DIR / "revision.json"
PATCH_MANIFEST_NAME = "nova_patch.json"
POLICY_AUDIT_LOG = RUNTIME_DIR / "policy_changes.jsonl"

# Session-scoped web research continuation cache.
WEB_RESEARCH_SESSION = WebResearchSessionStore()


TOOL_REGISTRY = build_default_registry()

# Tool registry service with event logging and manifest management
TOOL_MANIFEST_FILE = BASE_DIR / "TOOL_MANIFEST.json"
TOOL_EVENTS_FILE = RUNTIME_DIR / "tool_events.jsonl"
TOOL_REGISTRY_SERVICE = ToolRegistryService(TOOL_REGISTRY, TOOL_MANIFEST_FILE, TOOL_EVENTS_FILE)

BEHAVIOR_METRICS_STORE = BehaviorMetricsStore(BEHAVIOR_METRICS_FILE)
BEHAVIOR_METRICS: dict = BEHAVIOR_METRICS_STORE.metrics

def _policy_manager() -> PolicyManager:
    return build_policy_manager(POLICY_PATH, POLICY_AUDIT_LOG, BASE_DIR)

# Identity and memory service for clean-slate session enforcement
def _identity_memory_service() -> IdentityMemoryService:
    """Dynamic service creation with test-time path override support."""
    service = build_identity_memory_service(
        normalize_text_fn=_normalize_turn_text,
        location_query_fn=_is_location_recall_query,
        location_name_fn=_is_location_name_query,
        saved_location_weather_fn=_is_saved_location_weather_query,
        peims_query_fn=_is_peims_broad_query,
        declarative_info_fn=_is_declarative_info,
    )
    return service

TURN_SUPERVISOR = Supervisor()


def _identity_memory_text_allowed(kind: str, text: str) -> bool:
    return _identity_memory_service().is_identity_memory_text_allowed(kind, text)


def _session_identity_only_mode(session_id: str) -> bool:
    normalized = re.sub(r"\s+", " ", str(session_id or "").strip().lower())
    if not normalized:
        return False
    return "clean_slate" in normalized or "clean slate" in normalized


def _looks_like_identity_only_location_text(user_text: str) -> bool:
    return _identity_memory_service().looks_like_identity_only_location_text(user_text)


def _identity_only_block_kind(user_text: str, *, intent_result: Optional[dict] = None) -> str:
    return _identity_memory_service().get_identity_only_block_kind(user_text, intent_result=intent_result)


def _identity_only_block_reply(block_kind: str) -> str:
    return _identity_memory_service().get_identity_only_block_reply(block_kind)


def _save_behavior_metrics() -> None:
    BEHAVIOR_METRICS_STORE.save()


_FULFILLMENT_FLOW_SERVICE: Optional[FulfillmentFlowService] = None


def _fulfillment_flow_service() -> FulfillmentFlowService:
    global _FULFILLMENT_FLOW_SERVICE
    if _FULFILLMENT_FLOW_SERVICE is None:
        _FULFILLMENT_FLOW_SERVICE = build_fulfillment_flow_service(
            probe_turn_routes_fn=_probe_turn_routes,
            update_subconscious_state_fn=SUBCONSCIOUS_SERVICE.update_state,
            session_state_service=SessionStateService,
        )
    return _FULFILLMENT_FLOW_SERVICE


def _fulfillment_route_viability(
    user_text: str,
    session: object,
    recent_turns: list[tuple[str, str]],
    *,
    pending_action: Optional[dict] = None,
) -> dict:
    return evaluate_fulfillment_route_viability(
        user_text,
        session,
        recent_turns,
        pending_action=pending_action,
        get_fulfillment_state_fn=SessionStateService.get_fulfillment_state,
        looks_like_affirmative_followup_fn=_looks_like_affirmative_followup,
    )


def _deterministic_route_viability(
    user_text: str,
    session: object,
    recent_turns: list[tuple[str, str]],
    *,
    pending_action: Optional[dict] = None,
) -> dict:
    try:
        from planner_decision import decide_turn
    except Exception:
        decide_turn = None

    return evaluate_deterministic_route_viability(
        user_text,
        session,
        recent_turns,
        pending_action=pending_action,
        evaluate_rules_fn=TURN_SUPERVISOR.evaluate_rules,
        supervisor_result_has_route_fn=_supervisor_result_has_route,
        planner_decide_turn_fn=decide_turn,
    )


def _probe_turn_routes(
    user_text: str,
    session: object,
    recent_turns: list[tuple[str, str]],
    pending_action: Optional[dict] = None,
) -> dict:
    deterministic = _deterministic_route_viability(
        user_text,
        session,
        recent_turns,
        pending_action=pending_action,
    )
    supervisor_owned = deterministic.get("owned_result") if isinstance(deterministic.get("owned_result"), dict) else {}
    supervisor_viable = bool(deterministic.get("viable"))

    fulfillment = _fulfillment_route_viability(
        user_text,
        session,
        recent_turns,
        pending_action=pending_action,
    )
    return build_probe_turn_routes(user_text, deterministic, fulfillment)


def behavior_record_event(event: str) -> None:
    BEHAVIOR_METRICS_STORE.record_event(event)


def behavior_get_metrics() -> dict:
    return BEHAVIOR_METRICS_STORE.snapshot()


def _infer_turn_intent(user_input: str) -> str:
    t = (user_input or "").strip().lower()
    if not t:
        return "empty"
    if "weather" in t:
        return "weather_lookup"
    if t.startswith("web research ") or "deep research" in t or "all the information" in t:
        return "web_research"
    if t.startswith("web search ") or t.startswith("search "):
        return "web_search"
    if t.startswith("web gather "):
        return "web_gather"
    if t.startswith("web ") or "http://" in t or "https://" in t:
        return "web_fetch"
    if "my name is" in t or "your name is" in t or "full name" in t:
        return "identity_update_or_query"
    if _is_negative_feedback(t):
        return "correction_feedback"
    return "chat"


def action_ledger_add_step(
    record: Optional[dict],
    stage: str,
    outcome: str,
    detail: str = "",
    **data,
) -> None:
    if not isinstance(record, dict):
        return
    trace = record.get("route_trace")
    if not isinstance(trace, list):
        trace = []
        record["route_trace"] = trace

    step = {
        "stage": str(stage or "unknown").strip() or "unknown",
        "outcome": str(outcome or "unknown").strip() or "unknown",
    }
    clean_detail = str(detail or "").strip()
    if clean_detail:
        step["detail"] = clean_detail[:220]

    clean_data = {}
    for key, value in data.items():
        if value is None:
            continue
        if isinstance(value, str):
            if value.strip():
                clean_data[str(key)] = value[:220]
            continue
        if isinstance(value, bool):
            clean_data[str(key)] = value
            continue
        if isinstance(value, int):
            clean_data[str(key)] = value
            continue
        if isinstance(value, float):
            clean_data[str(key)] = round(value, 4)
            continue
        if isinstance(value, (list, tuple)):
            items = []
            for item in list(value)[:8]:
                if isinstance(item, (str, int, float, bool)):
                    items.append(item if not isinstance(item, str) else item[:120])
            if items:
                clean_data[str(key)] = items
            continue
        if isinstance(value, dict):
            items = {}
            for sub_key, sub_value in list(value.items())[:8]:
                if isinstance(sub_value, (str, int, float, bool)):
                    items[str(sub_key)] = sub_value if not isinstance(sub_value, str) else sub_value[:120]
            if items:
                clean_data[str(key)] = items

    if clean_data:
        step["data"] = clean_data
    trace.append(step)


def action_ledger_route_summary(record_or_trace: Optional[object]) -> str:
    if isinstance(record_or_trace, dict):
        trace = record_or_trace.get("route_trace")
    else:
        trace = record_or_trace
    if not isinstance(trace, list):
        return ""

    parts = []
    for raw_step in trace:
        if not isinstance(raw_step, dict):
            continue
        stage = str(raw_step.get("stage") or "").strip()
        outcome = str(raw_step.get("outcome") or "").strip()
        if not stage:
            continue
        parts.append(f"{stage}:{outcome or 'unknown'}")
    return " -> ".join(parts[:16])[:600]


TOOL_INTENT_LABELS: dict[str, str] = {
    "weather_lookup": "Weather route",
    "web_fetch": "Web fetch route",
    "web_search": "Web search route",
    "web_gather": "Web gather route",
    "web_research": "Web research route",
    "wikipedia_lookup": "Wikipedia route",
    "stackexchange_search": "StackExchange route",
}


def _recent_action_ledger_records(limit: int = 20) -> list[dict]:
    try:
        if not ACTION_LEDGER_DIR.exists():
            return []
        files = sorted(ACTION_LEDGER_DIR.glob("*.json"))[-max(1, int(limit)):]
        records = []
        for path in files:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if isinstance(payload, dict):
                records.append(payload)
        return records
    except Exception:
        return []


def _record_completed_tool_execution(record: dict) -> bool:
    if not isinstance(record, dict):
        return False
    trace = record.get("route_trace")
    if not isinstance(trace, list):
        return False
    for step in trace:
        if not isinstance(step, dict):
            continue
        stage = str(step.get("stage") or "").strip()
        outcome = str(step.get("outcome") or "").strip()
        if stage == "tool_execution" and outcome == "ok":
            return True
        if stage in {"keyword_tool", "command"} and outcome == "matched" and str(record.get("tool_result") or "").strip():
            return True
    return False


def _record_requested_tool_clarification(record: dict) -> bool:
    if not isinstance(record, dict):
        return False
    if str(record.get("planner_decision") or "").strip() == "ask_clarify":
        return True
    trace = record.get("route_trace")
    if not isinstance(trace, list):
        return False
    for step in trace:
        if not isinstance(step, dict):
            continue
        stage = str(step.get("stage") or "").strip()
        outcome = str(step.get("outcome") or "").strip()
        if stage == "action_planner" and outcome == "ask_clarify":
            return True
        if stage == "pending_action" and outcome == "awaiting_location":
            return True
        if stage == "finalize" and outcome == "ask_clarify":
            return True
    return False


def _detect_repeated_tool_intent_without_execution(records: Optional[list[dict]] = None, limit: int = 20) -> dict:
    recent = records if isinstance(records, list) else _recent_action_ledger_records(limit=limit)
    counts: dict[str, dict[str, int]] = {}
    for rec in recent:
        if not isinstance(rec, dict):
            continue
        intent = str(rec.get("intent") or "").strip()
        if intent not in TOOL_INTENT_LABELS:
            continue
        if _record_requested_tool_clarification(rec):
            continue
        bucket = counts.setdefault(intent, {"selected": 0, "completed": 0})
        bucket["selected"] += 1
        if _record_completed_tool_execution(rec):
            bucket["completed"] += 1

    best_intent = ""
    best_gap = 0
    best_selected = 0
    best_completed = 0
    for intent, bucket in counts.items():
        selected = int(bucket.get("selected", 0) or 0)
        completed = int(bucket.get("completed", 0) or 0)
        gap = selected - completed
        if selected >= 2 and gap > best_gap:
            best_intent = intent
            best_gap = gap
            best_selected = selected
            best_completed = completed

    if not best_intent:
        return {"class": "", "intent": "", "selected": 0, "completed": 0, "summary": ""}

    label = TOOL_INTENT_LABELS.get(best_intent, best_intent)
    return {
        "class": "repeated_tool_intent_without_execution",
        "intent": best_intent,
        "selected": best_selected,
        "completed": best_completed,
        "summary": f"{label} selected {best_selected} times, execution completed {best_completed} times.",
    }


def _top_repeated_correction_class(records: Optional[list[dict]] = None, limit: int = 20) -> dict:
    recent = records if isinstance(records, list) else _recent_action_ledger_records(limit=limit)
    counts: dict[str, int] = {}
    for rec in recent:
        trace = rec.get("route_trace") if isinstance(rec, dict) else None
        if not isinstance(trace, list):
            continue
        for step in trace:
            if not isinstance(step, dict):
                continue
            stage = str(step.get("stage") or "").strip()
            outcome = str(step.get("outcome") or "").strip()
            detail = str(step.get("detail") or "").strip()
            if stage == "llm_postprocess" and outcome == "self_corrected" and detail:
                counts[detail] = int(counts.get(detail, 0)) + 1
            elif stage == "claim_gate" and outcome == "adjusted":
                key = detail or "claim_gate_adjusted"
                counts[key] = int(counts.get(key, 0)) + 1

    if not counts:
        return {"class": "", "count": 0}
    reason, count = max(counts.items(), key=lambda item: item[1])
    return {"class": reason, "count": int(count)}


def _count_unsupported_claim_blocks_recently(records: Optional[list[dict]] = None, limit: int = 20) -> int:
    recent = records if isinstance(records, list) else _recent_action_ledger_records(limit=limit)
    count = 0
    for rec in recent:
        trace = rec.get("route_trace") if isinstance(rec, dict) else None
        if not isinstance(trace, list):
            continue
        for step in trace:
            if not isinstance(step, dict):
                continue
            stage = str(step.get("stage") or "").strip()
            outcome = str(step.get("outcome") or "").strip()
            detail = str(step.get("detail") or "").strip().lower()
            if stage == "claim_gate" and outcome == "adjusted":
                count += 1
            if stage == "llm_postprocess" and outcome == "self_corrected" and detail == "autonomy_guard":
                count += 1
    return count


def _unsupported_claims_blocked_recently(records: Optional[list[dict]] = None, limit: int = 20) -> bool:
    return _count_unsupported_claim_blocks_recently(records=records, limit=limit) > 0


def _count_routing_overrides_recently(records: Optional[list[dict]] = None, limit: int = 20) -> int:
    recent = records if isinstance(records, list) else _recent_action_ledger_records(limit=limit)
    count = 0
    for rec in recent:
        trace = rec.get("route_trace") if isinstance(rec, dict) else None
        if not isinstance(trace, list):
            continue
        for step in trace:
            if not isinstance(step, dict):
                continue
            stage = str(step.get("stage") or "").strip()
            outcome = str(step.get("outcome") or "").strip()
            if stage == "routing_override" and outcome == "enabled":
                count += 1
                break
    return count


def _record_used_routing_override(record: Optional[dict]) -> bool:
    trace = record.get("route_trace") if isinstance(record, dict) else None
    if not isinstance(trace, list):
        return False
    for step in trace:
        if not isinstance(step, dict):
            continue
        stage = str(step.get("stage") or "").strip()
        outcome = str(step.get("outcome") or "").strip()
        if stage == "routing_override" and outcome == "enabled":
            return True
    return False


def _routing_stable_recently(records: Optional[list[dict]] = None, limit: int = 20) -> bool:
    failure = _detect_repeated_tool_intent_without_execution(records=records, limit=limit)
    return not bool(failure.get("summary"))


def _sample_intents_last(records: Optional[list[dict]] = None, count: int = 5) -> list[str]:
    recent = records if isinstance(records, list) else _recent_action_ledger_records(limit=max(1, int(count)))
    intents: list[str] = []
    for rec in recent[-max(1, int(count)):]:
        if not isinstance(rec, dict):
            continue
        intent = str(rec.get("intent") or "").strip()
        intents.append(intent or "unknown")
    return intents


def _append_self_reflection(payload: dict) -> None:
    try:
        SELF_REFLECTION_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(SELF_REFLECTION_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=True) + "\n")
    except Exception:
        pass


def _append_health_snapshot(payload: dict) -> None:
    try:
        HEALTH_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(HEALTH_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=True) + "\n")
    except Exception:
        pass


def record_health_snapshot(*, session_id: str, reflection: Optional[dict], session_end: bool = False) -> None:
    if not isinstance(reflection, dict):
        return
    payload = {
        "session_id": str(session_id or "default").strip() or "default",
        "end_time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "probe_summary": str(reflection.get("probe_summary") or "All green"),
        "flagged_probes": list(reflection.get("probe_results") or []),
        "drift_issues": len(list(reflection.get("probe_results") or [])),
        "entry_point": str(reflection.get("entry_point") or ""),
        "session_end": bool(session_end),
        "suggestions": list(reflection.get("suggestions") or []),
    }
    _append_health_snapshot(payload)


def _recent_self_reflection_rows(limit: int = 3) -> list[dict]:
    try:
        if not SELF_REFLECTION_LOG.exists():
            return []
        rows: list[dict] = []
        for line in SELF_REFLECTION_LOG.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except Exception:
                continue
            if isinstance(payload, dict):
                rows.append(payload)
        return rows[-max(1, int(limit)):]
    except Exception:
        return []


def maybe_log_self_reflection(*, limit: int = 20, every: int = 5, records: Optional[list[dict]] = None, total_records: Optional[int] = None, extra_payload: Optional[dict] = None) -> dict:
    recent = records if isinstance(records, list) else _recent_action_ledger_records(limit=limit)
    if total_records is None:
        total_records = len(_recent_action_ledger_records(limit=1000000))
    count_total = int(total_records or 0)
    if count_total <= 0 or count_total % max(1, int(every)) != 0:
        return {}

    failure = _detect_repeated_tool_intent_without_execution(records=recent, limit=limit)
    correction = _top_repeated_correction_class(records=recent, limit=limit)
    routing_stable = _routing_stable_recently(records=recent, limit=limit)
    claims_blocked = _count_unsupported_claim_blocks_recently(records=recent, limit=limit)
    routing_overrides = _count_routing_overrides_recently(records=recent, limit=limit)
    latest_record = recent[-1] if recent else {}
    continuation_count = sum(1 for rec in recent if isinstance(rec, dict) and bool(rec.get("continuation_used", False)))
    retrieval_continuations = sum(
        1
        for rec in recent
        if isinstance(rec, dict)
        and bool(rec.get("continuation_used", False))
        and str(rec.get("active_subject") or "").startswith("retrieval")
    )
    provider_hits_last_window: dict[str, int] = {}
    for rec in recent:
        if not isinstance(rec, dict):
            continue
        provider = str(rec.get("provider_used") or _provider_name_from_tool(rec.get("tool") or "")).strip().lower()
        if not provider:
            continue
        provider_hits_last_window[provider] = int(provider_hits_last_window.get(provider, 0) or 0) + 1
    payload = {
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "turn_count": count_total,
        "top_repeated_failure_class": str(failure.get("summary") or "none"),
        "top_repeated_correction_class": str(correction.get("class") or "none"),
        "failure_top": {
            "class": str(failure.get("class") or "none"),
            "intent": str(failure.get("intent") or ""),
            "count": max(0, int(failure.get("selected", 0) or 0) - int(failure.get("completed", 0) or 0)),
            "selected": int(failure.get("selected", 0) or 0),
            "completed": int(failure.get("completed", 0) or 0),
            "summary": str(failure.get("summary") or "none"),
        },
        "correction_top": {
            "class": str(correction.get("class") or "none"),
            "count": int(correction.get("count", 0) or 0),
        },
        "routing_stable": bool(routing_stable),
        "unsupported_claims_blocked": bool(claims_blocked),
        "claims_blocked": int(claims_blocked),
        "routing_overrides": int(routing_overrides),
        "routing_override_used_latest_turn": bool(_record_used_routing_override(latest_record)),
        "active_subject": str(latest_record.get("active_subject") or ""),
        "continuation_used": bool(latest_record.get("continuation_used", False)),
        "continuations_last_window": int(continuation_count),
        "retrieval_continuations": int(retrieval_continuations),
        "sample_intents_last5": _sample_intents_last(recent, count=5),
        "provider_hits_last_window": provider_hits_last_window,
        "last_provider_used": str(latest_record.get("provider_used") or _provider_name_from_tool(latest_record.get("tool") or "")).strip(),
    }
    if isinstance(extra_payload, dict):
        for key, value in extra_payload.items():
            payload[key] = value
    _append_self_reflection(payload)
    if count_total % 10 == 0:
        record_health_snapshot(session_id=str(payload.get("session_id") or "default"), reflection=payload, session_end=False)
    BEHAVIOR_METRICS_STORE.update_from_reflection(payload, count_total)
    return payload


def build_turn_reflection(
    session_state: ConversationSession,
    *,
    entry_point: str,
    session_id: str,
    current_decision: dict,
) -> dict:
    session_summary = session_state.reflection_summary()
    session_summary["subconscious_snapshot"] = SUBCONSCIOUS_SERVICE.get_snapshot(session_state)
    reflection = TURN_SUPERVISOR.process_turn(
        entry_point=entry_point,
        session_id=session_id,
        session_summary=session_summary,
        current_decision=current_decision,
        recent_records=_recent_action_ledger_records(limit=10),
        recent_reflections=_recent_self_reflection_rows(limit=3),
    )
    subconscious_training_backlog = build_training_backlog_summary(session_summary["subconscious_snapshot"])
    if isinstance(subconscious_training_backlog, dict):
        reflection["subconscious_training_backlog"] = subconscious_training_backlog
    subconscious_robust_weakness = build_robust_weakness_summary(getattr(session_state, "subconscious_live_family_summary", None))
    if isinstance(subconscious_robust_weakness, dict):
        reflection["subconscious_robust_weakness"] = subconscious_robust_weakness
    subconscious_replan_reasons = list((session_summary["subconscious_snapshot"] or {}).get("replan_reasons") or [])
    if subconscious_replan_reasons:
        reflection["subconscious_replan_reasons"] = subconscious_replan_reasons
    reflection["session_id"] = str(session_id or "default").strip() or "default"
    reflection["entry_point"] = str(entry_point or "unknown").strip().lower() or "unknown"
    session_state.set_last_reflection(reflection)
    return reflection


def _execute_registered_supervisor_rule(
    rule_result: dict,
    text: str,
    current_state: Optional[dict],
    *,
    turns: Optional[list[tuple[str, str]]] = None,
    input_source: str = "typed",
    allowed_actions: Optional[set[str]] = None,
) -> tuple[bool, str, Optional[dict]]:
    action = str((rule_result or {}).get("action") or "").strip().lower()
    if not action:
        return False, "", current_state
    if allowed_actions is not None and action not in allowed_actions:
        return False, "", current_state

    if action == "name_origin_store":
        store_text = str((rule_result or {}).get("store_text") or text).strip()
        if not store_text:
            return False, "", current_state
        return True, remember_name_origin(store_text), current_state

    if action == "self_location":
        next_state = (rule_result or {}).get("next_state") if isinstance((rule_result or {}).get("next_state"), dict) else _make_conversation_state("location_recall")
        return True, _location_reply(), next_state

    if action == "location_recall":
        next_state = (rule_result or {}).get("next_state") if isinstance((rule_result or {}).get("next_state"), dict) else _make_conversation_state("location_recall")
        if _is_location_name_query(text):
            return True, _location_name_reply(), next_state
        return True, _location_recall_reply(), next_state

    if action == "location_name":
        next_state = current_state if isinstance(current_state, dict) else _make_conversation_state("location_recall")
        return True, _location_name_reply(), next_state

    if action == "weather_current_location":
        next_state = (rule_result or {}).get("next_state")
        if not isinstance(next_state, dict):
            next_state = _make_conversation_state("location_recall")
        outcome = _classify_weather_lookup_outcome({
            "weather_mode": "current_location",
            "next_state": next_state,
        })
        _attach_reply_outcome(rule_result, outcome)
        tool_result = execute_planned_action("weather_current_location")
        return True, render_reply({**outcome, "tool_result": str(tool_result or "")}), next_state

    if action == "apply_correction":
        correction_text = str((rule_result or {}).get("user_correction_text") or text).strip()
        pending_target = ""
        pending_followup = isinstance(current_state, dict) and str(current_state.get("kind") or "") == "correction_pending"
        if pending_followup:
            pending_target = str(current_state.get("target") or "").strip()
        last_assistant = pending_target or _last_assistant_turn_text(turns)
        parsed = _parse_correction(correction_text)
        authoritative = _extract_authoritative_correction_text(correction_text)
        correction_value = parsed or authoritative

        _store_supervisor_correction_record(
            correction_text,
            input_source=input_source,
            last_assistant=last_assistant,
            parsed_correction=(correction_value or ""),
        )

        learned_fact, learned_msg = learn_from_user_correction(correction_text)
        if learned_fact:
            outcome = _classify_correction_outcome(
                correction_text=correction_text,
                correction_value=correction_value,
                last_assistant=last_assistant,
                pending_followup=pending_followup,
                learned_fact=True,
                learned_message=learned_msg,
            )
            _attach_reply_outcome(rule_result, outcome)
            return True, render_reply(outcome), None

        if correction_value and last_assistant and mem_enabled():
            corr_store = _normalize_correction_for_storage(correction_value)
            _teach_store_example(last_assistant, corr_store, user=get_active_user() or None)
            outcome = _classify_correction_outcome(
                correction_text=correction_text,
                correction_value=correction_value,
                last_assistant=last_assistant,
                pending_followup=pending_followup,
                replacement_applied=True,
            )
            _attach_reply_outcome(rule_result, outcome)
            return True, render_reply(outcome), None

        if pending_followup and _looks_like_correction_cancel(correction_text):
            reply_text = "Understood. I canceled that replacement request and did not learn anything from it."
            outcome = {
                "intent": "apply_correction",
                "kind": "correction_cancelled",
                "correction_kind": "cancel_pending_replacement",
                "reply_contract": "correction.cancelled",
                "reply_text": reply_text,
                "state_delta": {},
            }
            _attach_reply_outcome(rule_result, outcome)
            return True, reply_text, None

        if pending_followup and not correction_value and _looks_like_pending_replacement_text(correction_text):
            if last_assistant and mem_enabled():
                corr_store = _normalize_correction_for_storage(correction_text)
                _teach_store_example(last_assistant, corr_store, user=get_active_user() or None)
                outcome = _classify_correction_outcome(
                    correction_text=correction_text,
                    correction_value=correction_text,
                    last_assistant=last_assistant,
                    pending_followup=True,
                    replacement_applied=True,
                )
                _attach_reply_outcome(rule_result, outcome)
                return True, render_reply(outcome), None

        if pending_followup and not correction_value and correction_text and "?" not in correction_text:
            reply_text = "I still need the exact replacement wording you want me to use."
            outcome = {
                "intent": "apply_correction",
                "kind": "pending_replacement_reminder",
                "correction_kind": "awaiting_replacement_text",
                "reply_contract": "correction.pending_replacement",
                "reply_text": reply_text,
                "state_delta": {},
            }
            _attach_reply_outcome(rule_result, outcome)
            return True, reply_text, current_state

        if last_assistant:
            next_state = _make_conversation_state("correction_pending", target=last_assistant)
            outcome = _classify_correction_outcome(
                correction_text=correction_text,
                correction_value=correction_value,
                last_assistant=last_assistant,
                pending_followup=pending_followup,
                replacement_pending=True,
            )
            _attach_reply_outcome(rule_result, outcome)
            return True, render_reply(outcome), next_state

        outcome = _classify_correction_outcome(
            correction_text=correction_text,
            correction_value=correction_value,
            last_assistant=last_assistant,
            pending_followup=pending_followup,
        )
        _attach_reply_outcome(rule_result, outcome)
        return True, render_reply(outcome), None

    if action == "retrieval_followup":
        if not isinstance(current_state, dict) or str(current_state.get("kind") or "") != "retrieval":
            return False, "", current_state
        reply, next_state, outcome = _execute_retrieval_followup_outcome(current_state, text)
        _attach_reply_outcome(rule_result, outcome)
        return True, reply, next_state

    if action == "identity_history_family":
        reply, next_state, outcome = _execute_identity_history_outcome(
            rule_result,
            current_state,
            text,
            turns=turns,
        )
        _attach_reply_outcome(rule_result, outcome)
        return True, reply, next_state

    if action == "open_probe_family":
        reply_text, outcome_kind = _open_probe_reply(text, turns=turns)
        outcome = {
            "intent": "open_probe_family",
            "kind": outcome_kind,
            "reply_contract": f"open_probe.{outcome_kind}",
            "reply_text": reply_text,
            "state_delta": {},
        }
        _attach_reply_outcome(rule_result, outcome)
        return True, reply_text, current_state

    if action == "last_question_recall":
        reply_text, outcome_kind = _last_question_recall_reply(text, turns=turns)
        outcome = {
            "intent": "last_question_recall",
            "kind": outcome_kind,
            "reply_contract": f"last_question.{outcome_kind}",
            "reply_text": reply_text,
            "state_delta": {},
        }
        _attach_reply_outcome(rule_result, outcome)
        return True, reply_text, current_state

    if action == "session_fact_recall":
        reply_text, outcome_kind = _session_fact_recall_reply(rule_result)
        outcome = {
            "intent": "session_fact_recall",
            "kind": outcome_kind,
            "reply_contract": f"session_fact.{outcome_kind}",
            "reply_text": reply_text,
            "state_delta": {},
        }
        _attach_reply_outcome(rule_result, outcome)
        return True, reply_text, current_state

    if action == "rules_list":
        outcome = {
            "intent": "rules_list",
            "kind": "list",
            "reply_contract": "rules.list",
            "reply_text": _rules_reply(),
            "state_delta": {},
        }
        _attach_reply_outcome(rule_result, outcome)
        return True, str(outcome.get("reply_text") or ""), current_state

    if action == "developer_location":
        next_state = current_state if isinstance(current_state, dict) else _make_conversation_state("identity_profile", subject="developer")
        return True, _developer_location_reply(), next_state

    if action == "developer_identity_followup":
        next_state = current_state if isinstance(current_state, dict) else _make_conversation_state("developer_identity", subject="developer")
        return True, _developer_identity_followup_reply(turns=turns, name_focus=bool((rule_result or {}).get("name_focus", False))), next_state

    if action == "identity_profile_followup":
        subject = str((rule_result or {}).get("subject") or "self").strip() or "self"
        next_state = current_state if isinstance(current_state, dict) else _make_conversation_state("identity_profile", subject=subject)
        return True, _identity_profile_followup_reply(subject, turns=turns), next_state

    return False, "", current_state


def _last_assistant_turn_text(turns: Optional[list[tuple[str, str]]]) -> str:
    for role, text in reversed(list(turns or [])):
        if str(role or "").strip().lower() == "assistant":
            return str(text or "").strip()
    return ""


def _looks_like_affirmative_followup(text: str) -> bool:
    normalized = _normalize_turn_text(text).strip(" .,!?")
    if not normalized:
        return False
    return (
        normalized in {"yes", "yeah", "yea", "sure", "okay", "ok", "please", "do that", "go ahead"}
        or normalized.startswith("yes ")
        or normalized.startswith("yeah ")
        or normalized.startswith("yea ")
        or normalized.startswith("please ")
        or "do that" in normalized
    )


def _looks_like_shared_location_reference(text: str) -> bool:
    normalized = _normalize_turn_text(text).strip(" .,!?")
    if not normalized:
        return False
    return (
        normalized in {"our location", "our location nova", "same location", "shared location"}
        or (("your" in normalized or "our" in normalized) and "location" in normalized)
        or "that location" in normalized
        or normalized in {"there", "same place"}
    )


def _intent_trace_preview(text: str, *, limit: int = 120) -> str:
    compact = re.sub(r"\s+", " ", str(text or "").strip())
    if len(compact) <= limit:
        return compact
    return compact[: max(0, limit - 3)] + "..."


def _supervisor_result_has_route(rule_result: Optional[dict]) -> bool:
    payload = rule_result if isinstance(rule_result, dict) else {}
    return bool(payload.get("handled")) or bool(str(payload.get("action") or "").strip())


def _dev_mode_enabled() -> bool:
    raw = str(os.environ.get("NOVA_DEV_MODE") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


_ALLOWED_SUPERVISOR_BYPASSES: tuple[dict[str, object], ...] = (
    {
        "category": "fallback.meta_confusion",
        "phrases": {
        },
    },
    {
        # These are intentionally open-ended prompts that currently remain model-owned.
        "category": "intentional_fallback.general_qa",
        "phrases": {
            "can you debug this bug in my code",
            "explain photosynthesis briefly",
            "why",
        },
    },
)


def _looks_like_open_fallback_turn(text: str) -> bool:
    candidate = str(text or "").strip()
    if not candidate:
        return False
    if _is_explicit_command_like(candidate):
        return False
    if _is_location_request(candidate):
        return False
    normalized = _normalize_turn_text(candidate)
    if normalized in {
        "weather",
        "weather now",
        "weather current",
        "weather today",
        "current weather",
        "what's the weather",
        "what is the weather",
        "what is the weather now",
        "what's the weather now",
    }:
        return False
    if _is_peims_broad_query(candidate) or _is_local_knowledge_topic_query(candidate):
        return False
    if re.match(r"^(hi|hello|hey)\b", normalized, flags=re.I):
        return True
    if candidate.endswith("?"):
        return True
    if len(normalized.split()) >= 3:
        return True
    return normalized.startswith((
        "how ",
        "why ",
        "what ",
        "who ",
        "can you ",
        "could you ",
        "would you ",
        "tell me ",
        "explain ",
        "help ",
        "show me ",
        "compare ",
        "recap ",
        "summarize ",
    ))


def _normalize_bypass_phrase(text: str) -> str:
    return _normalize_turn_text(text).strip(" .,!?:;\t\r\n")


def _classify_supervisor_bypass(text: str) -> dict:
    normalized = _normalize_bypass_phrase(text)
    if not normalized:
        return {"allowed": False, "category": "unlisted", "reason": "empty"}
    for item in _ALLOWED_SUPERVISOR_BYPASSES:
        phrases = item.get("phrases")
        if isinstance(phrases, set) and normalized in phrases:
            return {
                "allowed": True,
                "category": str(item.get("category") or "fallback.allowlisted"),
                "reason": "allowlisted_bypass",
                "normalized_input": normalized,
            }
    if _looks_like_open_fallback_turn(text):
        return {
            "allowed": False,
            "category": "intentional_fallback.open_fulfillment_or_model",
            "reason": "open_fallback_candidate",
            "normalized_input": normalized,
        }
    return {
        "allowed": False,
        "category": "unlisted",
        "reason": "not_allowlisted",
        "normalized_input": normalized,
    }


def _supervisor_candidate_trace(rule_result: Optional[dict]) -> list[dict]:
    candidates = []
    for raw in list((rule_result or {}).get("candidates") or [])[:12]:
        if not isinstance(raw, dict):
            continue
        item = {
            "rule_name": str(raw.get("rule_name") or "").strip(),
            "priority": int(raw.get("priority", 100)),
            "handled": bool(raw.get("handled")),
        }
        action = str(raw.get("action") or "").strip()
        if action:
            item["action"] = action
        intent = str(raw.get("intent") or "").strip()
        if intent:
            item["intent"] = intent
        if bool(raw.get("rewrite")):
            item["rewrite"] = True
        if bool(raw.get("state_update")):
            item["state_update"] = True
        rule_error = str(raw.get("rule_error") or "").strip()
        if rule_error:
            item["rule_error"] = rule_error[:160]
        candidates.append(item)
    return candidates


def _supervisor_phase_record(rule_result: Optional[dict], *, phase: str) -> dict:
    payload = rule_result if isinstance(rule_result, dict) else {}
    return {
        "phase": str(phase or "unknown").strip().lower() or "unknown",
        "handled": bool(_supervisor_result_has_route(payload)),
        "rule_name": str(payload.get("matched_rule_name") or payload.get("rule_name") or "").strip(),
        "intent": str(payload.get("intent") or "").strip(),
        "action": str(payload.get("action") or "").strip(),
        "priority": int(payload.get("priority", 100)) if str(payload.get("priority") or "").strip() else None,
        "candidates": _supervisor_candidate_trace(payload),
    }


def _build_routing_decision(
    text: str,
    *,
    entry_point: str,
    intent_result: Optional[dict] = None,
    handle_result: Optional[dict] = None,
    final_owner: str = "pending",
    allowed_bypass: bool = False,
    allowed_bypass_category: str = "",
    bypass_reason: str = "",
    reply_contract: str = "",
    reply_outcome: Optional[dict] = None,
    turn_acts: Optional[list[str]] = None,
) -> dict:
    outcome = reply_outcome if isinstance(reply_outcome, dict) else {}
    acts = [str(item).strip() for item in list(turn_acts or []) if str(item).strip()]
    return {
        "input_preview": _intent_trace_preview(text),
        "entry_point": str(entry_point or "unknown").strip().lower() or "unknown",
        "intent_phase": _supervisor_phase_record(intent_result, phase="intent"),
        "handle_phase": _supervisor_phase_record(handle_result, phase="handle"),
        "final_owner": str(final_owner or "pending").strip().lower() or "pending",
        "allowed_bypass": bool(allowed_bypass),
        "allowed_bypass_category": str(allowed_bypass_category or "").strip(),
        "bypass_reason": str(bypass_reason or "").strip(),
        "reply_contract": str(reply_contract or "").strip(),
        "reply_outcome_kind": str(outcome.get("kind") or "").strip(),
        "turn_acts": acts,
    }


def _finalize_routing_decision(
    routing_decision: Optional[dict],
    *,
    planner_decision: str = "",
    reply_contract: str = "",
    reply_outcome: Optional[dict] = None,
    turn_acts: Optional[list[str]] = None,
) -> dict:
    payload = dict(routing_decision or {})
    if not payload:
        return {}
    intent_phase = payload.get("intent_phase") if isinstance(payload.get("intent_phase"), dict) else {}
    handle_phase = payload.get("handle_phase") if isinstance(payload.get("handle_phase"), dict) else {}
    final_owner = str(payload.get("final_owner") or "").strip().lower()
    if final_owner in {"", "pending"}:
        if bool(intent_phase.get("handled")):
            final_owner = "supervisor_intent"
        elif bool(handle_phase.get("handled")):
            final_owner = "supervisor_handle"
        elif str(planner_decision or "").strip().lower() in {
            "llm_fallback",
            "respond",
            "run_tool",
            "command",
            "ask_clarify",
            "grounded_lookup",
            "truth_hierarchy",
            "blocked_low_confidence",
            "policy_block",
            "conversation_followup",
        }:
            final_owner = "fallback"
        else:
            final_owner = "core_legacy"
    payload["final_owner"] = final_owner
    if reply_contract:
        payload["reply_contract"] = str(reply_contract).strip()
    outcome = reply_outcome if isinstance(reply_outcome, dict) else {}
    if outcome:
        payload["reply_outcome_kind"] = str(outcome.get("kind") or payload.get("reply_outcome_kind") or "").strip()
    acts = turn_acts if isinstance(turn_acts, list) else payload.get("turn_acts")
    payload["turn_acts"] = [str(item).strip() for item in acts if str(item).strip()] if isinstance(acts, list) else []
    return payload


def _supervisor_bypass_warning(text: str, *, entry_point: str, routing_decision: Optional[dict] = None) -> str:
    where = str(entry_point or "unknown").strip().lower() or "unknown"
    category = str((routing_decision or {}).get("allowed_bypass_category") or "").strip()
    if where == "http" and category.startswith("intentional_fallback."):
        warning = (
            "[INFO] Open fallback - learning invitation active"
            f" [{where}] {_intent_trace_preview(text)}"
        )
    else:
        warning = (
            "[WARN] Turn bypassed supervisor intent phase — this will be an error soon"
            f" [{where}] {_intent_trace_preview(text)}"
        )
    if category:
        warning += f" [{category}]"
    return warning


def _handle_supervisor_bypass(text: str, *, entry_point: str, routing_decision: Optional[dict] = None) -> str:
    classification = _classify_supervisor_bypass(text)
    if isinstance(routing_decision, dict):
        routing_decision["allowed_bypass"] = bool(classification.get("allowed"))
        routing_decision["allowed_bypass_category"] = str(classification.get("category") or "").strip()
        routing_decision["bypass_reason"] = str(classification.get("reason") or "").strip()
        routing_decision["final_owner"] = "fallback"
    warning = _supervisor_bypass_warning(text, entry_point=entry_point, routing_decision=routing_decision)
    if _dev_mode_enabled() and not bool(classification.get("allowed")):
        detail = routing_decision if isinstance(routing_decision, dict) else classification
        raise RuntimeError(f"Bypass detected: {_intent_trace_preview(text)} :: {json.dumps(detail, ensure_ascii=True, sort_keys=True)}")
    return warning


def _should_warn_supervisor_bypass(text: str) -> bool:
    candidate = str(text or "").strip()
    if not candidate:
        return False
    if _looks_like_open_fallback_turn(candidate):
        return False
    if _is_explicit_command_like(candidate):
        return False
    if _is_location_request(candidate):
        return False
    normalized = _normalize_turn_text(candidate)
    if normalized in {
        "weather",
        "weather now",
        "weather current",
        "weather today",
        "current weather",
        "what's the weather",
        "what is the weather",
        "what is the weather now",
        "what's the weather now",
    }:
        return False
    if _is_peims_broad_query(candidate) or _is_local_knowledge_topic_query(candidate):
        return False
    return True


def _should_clarify_unlabeled_numeric_turn(
    text: str,
    *,
    pending_action: Optional[dict] = None,
    current_state: Optional[dict] = None,
) -> bool:
    raw = str(text or "").strip()
    if not re.fullmatch(r"\d{5}", raw):
        return False
    state = current_state if isinstance(current_state, dict) else {}
    if str(state.get("kind") or "").strip() in {"numeric_reference", "numeric_reference_clarify"} and str(state.get("value") or "").strip() == raw:
        return False
    action = pending_action if isinstance(pending_action, dict) else {}
    if (
        str(action.get("kind") or "") == "weather_lookup"
        and str(action.get("status") or "") == "awaiting_location"
    ):
        return False
    try:
        return bool(str(get_saved_location_text() or "").strip())
    except Exception:
        return True


def _runtime_set_location_intent(
    text: str,
    *,
    pending_action: Optional[dict] = None,
) -> Optional[dict[str, object]]:
    raw = str(text or "").strip()
    if not re.fullmatch(r"\d{5}", raw):
        return None
    action = pending_action if isinstance(pending_action, dict) else {}
    if (
        str(action.get("kind") or "") == "weather_lookup"
        and str(action.get("status") or "") == "awaiting_location"
    ):
        return None
    try:
        if str(get_saved_location_text() or "").strip():
            return None
    except Exception:
        pass
    return {
        "handled": True,
        "intent": "set_location",
        "rule_name": "set_location_zip",
        "matched_rule_name": "set_location_zip",
        "location_value": raw,
        "location_kind": "zip",
        "location_ack_kind": "fact_only",
    }


_ROUTING_INTENT_PROMPT = """\
Classify the user message into exactly one routing intent. Reply with the label only — no explanation.

Labels:
weather_lookup   – user wants current conditions, temperature, rain, forecast, or whether to dress for outdoors
web_research     – user wants online research on a topic
web_search       – user wants a quick web search
store_fact       – user is telling a personal fact to remember
set_location     – user is providing their location or zip code
general_chat     – everything else

User message: {text}
Label:"""


def _llm_classify_routing_intent(
    text: str,
    turns: Optional[list[tuple[str, str]]] = None,
) -> Optional[dict[str, object]]:
    """Ask the LLM to classify routing intent for turns that rule-based routing misses.

    This is the replacement for keyword-trigger routing: the LLM understands
    'should I bring a jacket?' the same way it understands 'what's the weather?'.
    Returns a supervisor-compatible dict or None (falls through to general chat).
    """
    raw = str(text or "").strip()
    if not raw:
        return None
    if not _live_ollama_calls_allowed():
        return None
    try:
        prompt = _ROUTING_INTENT_PROMPT.format(text=raw[:500])
        payload = {
            "model": chat_model(),
            "stream": False,
            "options": {"temperature": 0.0, "top_p": 1.0, "num_predict": 8},
            "messages": [{"role": "user", "content": prompt}],
        }
        r = requests.post(
            f"{OLLAMA_BASE}/api/chat",
            json=payload,
            timeout=8,
        )
        r.raise_for_status()
        label = str(r.json().get("message", {}).get("content") or "").strip().lower()
        label = re.sub(r"[^a-z_]", "", (label.split() or [""])[0])
    except Exception:
        return None

    if label == "weather_lookup":
        saved_location = ""
        try:
            saved_location = str(get_saved_location_text() or "").strip()
        except Exception:
            pass
        if saved_location:
            return {
                "handled": True,
                "intent": "weather_lookup",
                "rule_name": "weather_lookup",
                "matched_rule_name": "weather_lookup",
                "weather_mode": "current_location",
                "location_value": saved_location,
            }
        return {
            "handled": True,
            "intent": "weather_lookup",
            "rule_name": "weather_lookup",
            "matched_rule_name": "weather_lookup",
            "weather_mode": "clarify",
        }

    # Future intents (web_research, store_fact, set_location) can be wired
    # here without keyword lists once their action paths are validated.
    return None


def _unlabeled_numeric_turn_reply(text: str) -> str:
    value = str(text or "").strip()
    return f"What does {value} refer to?"


def _numeric_reference_guess_reply(value: str) -> str:
    clean = str(value or "").strip()
    return f"I don't know what {clean} refers to yet. Tell me what it refers to."


def _numeric_reference_binding_reply(value: str, referent: str) -> str:
    clean_value = str(value or "").strip()
    clean_referent = str(referent or "").strip().rstrip(".!?")
    return f"Understood. In this chat, {clean_value} refers to {clean_referent}."


def _emit_supervisor_intent_trace(intent_result: dict, *, user_text: str = "") -> None:
    intent = str((intent_result or {}).get("intent") or "intent").strip().lower() or "intent"
    rule = str((intent_result or {}).get("matched_rule_name") or (intent_result or {}).get("rule_name") or "").strip()
    reason = ""

    if intent == "store_fact":
        reason = str((intent_result or {}).get("fact_text") or user_text).strip()
    elif intent == "set_location":
        reason = str((intent_result or {}).get("location_value") or user_text).strip()
    elif intent == "apply_correction":
        reason = str((intent_result or {}).get("user_correction_text") or user_text).strip()
    elif intent == "session_summary":
        reason = str((intent_result or {}).get("target") or "current_session_only").strip()
    else:
        reason = str(user_text or "").strip()

    label = rule or "supervisor"
    detail = _intent_trace_preview(reason)
    if detail:
        print(f"[INTENT] {intent} :: {label} :: {detail}", flush=True)
        return
    print(f"[INTENT] {intent} :: {label}", flush=True)


def _store_supervisor_correction_record(
    correction_text: str,
    *,
    input_source: str,
    last_assistant: str = "",
    parsed_correction: str = "",
) -> None:
    if not correction_text or not mem_enabled():
        return
    record = {
        "text": correction_text,
        "parsed_correction": parsed_correction,
        "last_assistant": last_assistant,
        "ts": int(time.time()),
    }
    mem_add("user_correction", input_source, json.dumps(record, ensure_ascii=False))


def _handle_supervisor_intent(
    intent_result: dict,
    user_text: str,
    *,
    turns: Optional[list[tuple[str, str]]] = None,
    input_source: str = "typed",
    entry_point: str = "",
) -> tuple[bool, str, Optional[dict], Optional[dict]]:
    intent = str((intent_result or {}).get("intent") or "").strip().lower()
    if not intent:
        return False, "", None, None

    normalized_entry_point = str(entry_point or "").strip().lower()

    if intent == "web_research_family":
        outcome = _classify_web_research_outcome(intent_result, user_text, turns=turns)
        tool_name = str(outcome.get("tool_name") or "web_research").strip().lower() or "web_research"
        query = str(outcome.get("query") or "").strip()
        tool_args = [query] if query else []
        tool_result = execute_planned_action(tool_name, tool_args)
        outcome["tool_result"] = str(tool_result or "")
        next_state = _make_retrieval_conversation_state(tool_name, query, outcome["tool_result"])
        return True, render_reply(outcome), next_state, {
            "reply_contract": str(outcome.get("reply_contract") or ""),
            "reply_outcome": outcome,
        }

    if intent == "store_fact":
        fact_text = str((intent_result or {}).get("fact_text") or user_text).strip()
        memory_kind = str((intent_result or {}).get("memory_kind") or "user_fact").strip() or "user_fact"
        storage_performed = False
        if fact_text and mem_enabled():
            try:
                mem_add(memory_kind, input_source, fact_text)
                storage_performed = True
            except Exception:
                storage_performed = False
        outcome = _classify_store_fact_outcome(intent_result, user_text, source="intent", storage_performed=storage_performed)
        return True, render_reply(outcome), None, {
            "reply_contract": str(outcome.get("reply_contract") or ""),
            "reply_outcome": outcome,
        }

    if intent == "weather_lookup":
        weather_mode = str((intent_result or {}).get("weather_mode") or "clarify").strip().lower() or "clarify"
        if weather_mode == "clarify" and _weather_current_location_available():
            intent_result = dict(intent_result or {})
            intent_result["weather_mode"] = "current_location"
        outcome = _classify_weather_lookup_outcome(intent_result)
        reply_text, next_state, reply_outcome = _execute_weather_lookup_outcome(outcome)
        return True, reply_text, next_state, {
            "reply_contract": str(reply_outcome.get("reply_contract") or ""),
            "reply_outcome": reply_outcome,
            "pending_action": reply_outcome.get("pending_action"),
        }

    if intent == "set_location":
        location_value = str((intent_result or {}).get("location_value") or user_text).strip()
        if location_value:
            try:
                set_location_text(location_value, input_source=input_source)
            except Exception:
                pass
        outcome = _classify_set_location_outcome(intent_result, user_text)
        return True, render_reply(outcome), _make_conversation_state("location_recall"), {
            "reply_contract": str(outcome.get("reply_contract") or ""),
            "reply_outcome": outcome,
        }

    if intent == "apply_correction":
        correction_text = str((intent_result or {}).get("user_correction_text") or user_text).strip()
        parsed = _parse_correction(correction_text)
        last_assistant = _last_assistant_turn_text(turns)
        _store_supervisor_correction_record(
            correction_text,
            input_source=input_source,
            last_assistant=last_assistant,
            parsed_correction=parsed or "",
        )
        if parsed and last_assistant and mem_enabled():
            _teach_store_example(last_assistant, parsed, user=get_active_user() or None)
            outcome = _classify_correction_outcome(
                correction_text=correction_text,
                correction_value=parsed,
                last_assistant=last_assistant,
                pending_followup=False,
                replacement_applied=True,
            )
        else:
            outcome = {
                "intent": "apply_correction",
                "kind": "intent_ack",
                "correction_kind": "simple_negation",
                "reply_contract": "correction.intent_ack",
                "correction_text": correction_text,
                "correction_value": str(parsed or "").strip(),
                "learned_message": "",
                "target_text": str(last_assistant or "").strip(),
                "pending_followup": False,
                "state_delta": {},
            }
        return True, render_reply(outcome), None, {
            "reply_contract": str(outcome.get("reply_contract") or ""),
            "reply_outcome": outcome,
        }

    if intent == "smalltalk":
        reply = _quick_smalltalk_reply(user_text, active_user=get_active_user())
        if reply:
            return True, reply, None, None
        return False, "", None, None

    if intent == "capability_query":
        return True, describe_capabilities(), None, None

    if intent == "policy_domain_query":
        web = policy_web()
        domains = list(web.get("allow_domains") or [])
        enabled = bool(web.get("enabled", False))
        lines = [f"Policy web access enabled: {enabled}"]
        if domains:
            lines.append("Allowed domains: " + ", ".join(domains))
        else:
            lines.append("Allowed domains: none configured")
        return True, "\n".join(lines), None, None

    if intent == "assistant_name":
        return True, _assistant_name_reply(user_text), None, None

    if intent == "self_identity_web_challenge":
        return True, _self_identity_web_challenge_reply(), None, None

    if intent == "name_origin":
        outcome = _classify_name_origin_outcome(intent_result)
        return True, render_reply(outcome), None, {
            "reply_contract": str(outcome.get("reply_contract") or ""),
            "reply_outcome": outcome,
        }

    if intent == "developer_full_name":
        return True, _developer_full_name_reply(), _make_conversation_state("identity_profile", subject="developer"), None

    if intent == "creator_identity":
        creator_reply = hard_answer(user_text) or _developer_profile_reply(turns=turns, user_text=user_text)
        return True, creator_reply, _make_conversation_state("identity_profile", subject="developer"), None

    if intent == "developer_profile":
        return True, _developer_profile_reply(turns=turns, user_text=user_text), _make_conversation_state("identity_profile", subject="developer"), None

    if intent == "session_summary":
        return True, _session_recap_reply(list(turns or []), user_text), None, None

    return False, "", None, None


def _resolve_set_location_semantics(intent_result: dict, user_text: str = "") -> dict[str, str]:
    payload = intent_result if isinstance(intent_result, dict) else {}
    location_value = str(payload.get("location_value") or user_text).strip()
    location_kind = str(payload.get("location_kind") or "").strip().lower()
    if location_kind not in {"zip", "place"}:
        location_kind = "zip" if re.fullmatch(r"\d{5}", location_value) else "place"
    ack_kind = str(payload.get("location_ack_kind") or "").strip().lower()
    if ack_kind not in {"fact_only", "confirmed_location"}:
        ack_kind = "fact_only" if location_kind == "zip" else "confirmed_location"
    return {
        "location_value": location_value,
        "location_kind": location_kind,
        "location_ack_kind": ack_kind,
    }


REPLY_TEMPLATES: dict[str, str] = {
    "set_location.missing_value": "I need a location value to store.",
    "set_location.observed_zip": "Got it - {location_value} is a ZIP code.",
    "set_location.explicit_location": "Got it - using {location_value} as your location.",
    "correction.recorded": "Got it - I recorded that correction.",
    "correction.pending_replacement": "You're right. I recorded that correction. Send the exact corrected answer if you want me to store the replacement answer.",
    "correction.replacement_applied": "Understood. I corrected that and will use your version going forward.",
    "correction.intent_ack": "Got it - correcting that.",
    "correction.identity_correction": "{learned_message}",
    "store_fact.missing_value": "I need the fact to store.",
    "store_fact.explicit_store": "Learned: {fact_text}",
    "store_fact.prompted_store": "Learned: {fact_text}",
    "store_fact.correctional_store": "Learned correction: {fact_text}",
    "store_fact.declarative_ack": "Noted.",
    "weather_lookup.clarify": "What location should I use for the weather lookup?",
    "weather_lookup.current_location": "{tool_result}",
    "weather_lookup.explicit_location": "{tool_result}",
    "web_research_family.research_prompt": "{tool_result}",
    "web_research_family.deep_search": "{tool_result}",
    "name_origin.story_known": "{reply_text}",
    "name_origin.story_missing": "{reply_text}",
    "name_origin.full_story": "{reply_text}",
    "identity_history.name_origin": "{reply_text}",
    "identity_history.creator_question": "{reply_text}",
    "identity_history.history_recall": "{reply_text}",
    "last_question.recall": "{reply_text}",
    "last_question.empty": "{reply_text}",
    "rules.list": "{reply_text}",
    "open_probe.clarification": "{reply_text}",
    "open_probe.safe_fallback": "{reply_text}",
    "turn.truthful_limit": "{reply_text}",
    "retrieval_followup.selected_result": "{reply_text}",
    "retrieval_followup.continued_results": "{reply_text}",
    "retrieval_followup.meta_summary": "{reply_text}",
    "retrieval_followup.guidance": "{reply_text}",
}


def render_reply(outcome: Optional[dict]) -> str:
    payload = outcome if isinstance(outcome, dict) else {}
    contract = str(payload.get("reply_contract") or "").strip()
    if not contract:
        return "Internal reply error - missing contract."
    template = REPLY_TEMPLATES.get(contract)
    if not template:
        return "Internal reply error - missing template."
    try:
        return template.format(**payload)
    except Exception:
        return "Internal reply error - invalid template data."


def _attach_reply_outcome(result_payload: Optional[dict], outcome: Optional[dict]) -> None:
    if not isinstance(result_payload, dict) or not isinstance(outcome, dict):
        return
    result_payload["reply_contract"] = str(outcome.get("reply_contract") or "")
    result_payload["reply_outcome"] = dict(outcome)


def _classify_set_location_outcome(intent_result: dict, user_text: str = "") -> dict[str, object]:
    semantics = _resolve_set_location_semantics(intent_result, user_text)
    payload = intent_result if isinstance(intent_result, dict) else {}
    location_value = str(semantics.get("location_value") or "").strip()
    if not location_value:
        return {
            "intent": "set_location",
            "kind": "missing_value",
            "reply_contract": "set_location.missing_value",
            "location_value": "",
            "location_kind": str(semantics.get("location_kind") or "").strip().lower(),
            "location_ack_kind": str(semantics.get("location_ack_kind") or "").strip().lower(),
            "user_commitment": "none",
            "state_delta": {},
        }

    location_kind = str(semantics.get("location_kind") or "place").strip().lower()
    ack_kind = str(semantics.get("location_ack_kind") or "confirmed_location").strip().lower()
    rule_name = str(payload.get("rule_name") or "").strip().lower()
    user_commitment = "implied" if rule_name == "set_location_zip" else "explicit"
    outcome_kind = "observed_zip" if location_kind == "zip" or ack_kind == "fact_only" else "explicit_location"
    return {
        "intent": "set_location",
        "kind": outcome_kind,
        "reply_contract": f"set_location.{outcome_kind}",
        "location_value": location_value,
        "location_kind": location_kind,
        "location_ack_kind": ack_kind,
        "user_commitment": user_commitment,
        "state_delta": {"location": location_value},
    }


def _classify_correction_outcome(
    *,
    correction_text: str,
    correction_value: str,
    last_assistant: str,
    pending_followup: bool,
    learned_fact: bool = False,
    learned_message: str = "",
    replacement_applied: bool = False,
    replacement_pending: bool = False,
) -> dict[str, object]:
    normalized_value = str(correction_value or "").strip()
    if learned_fact:
        correction_kind = "identity_correction"
        kind = "identity_correction"
        reply_contract = "correction.identity_correction"
    elif replacement_applied:
        correction_kind = "fact_replacement"
        kind = "followup_replacement" if pending_followup else "explicit_replacement"
        reply_contract = "correction.replacement_applied"
    elif replacement_pending:
        correction_kind = "simple_negation"
        kind = "pending_replacement"
        reply_contract = "correction.pending_replacement"
    elif last_assistant:
        correction_kind = "simple_negation"
        kind = "pending_replacement"
        reply_contract = "correction.pending_replacement"
    else:
        correction_kind = "simple_negation"
        kind = "recorded_only"
        reply_contract = "correction.recorded"
    return {
        "intent": "apply_correction",
        "kind": kind,
        "correction_kind": correction_kind,
        "reply_contract": reply_contract,
        "correction_text": str(correction_text or "").strip(),
        "correction_value": normalized_value,
        "learned_message": str(learned_message or "").strip(),
        "target_text": str(last_assistant or "").strip(),
        "pending_followup": bool(pending_followup),
        "state_delta": {"kind": "correction_pending", "target": str(last_assistant or "").strip()} if kind == "pending_replacement" and last_assistant else {},
    }


def _classify_store_fact_outcome(
    intent_result: dict,
    user_text: str = "",
    *,
    source: str = "intent",
    storage_performed: bool = False,
) -> dict[str, object]:
    payload = intent_result if isinstance(intent_result, dict) else {}
    fact_text = str(payload.get("fact_text") or user_text).strip()
    requested_kind = str(payload.get("store_fact_kind") or "").strip().lower()
    if requested_kind not in {"explicit_store", "prompted_store", "correctional_store", "declarative_ack"}:
        requested_kind = "declarative_ack" if source == "declarative" else "explicit_store"
    user_commitment = str(payload.get("user_commitment") or "").strip().lower()
    if user_commitment not in {"explicit", "implied", "none"}:
        user_commitment = "implied" if source == "declarative" else "explicit"
    if not fact_text:
        return {
            "intent": "store_fact",
            "kind": "missing_value",
            "reply_contract": "store_fact.missing_value",
            "fact_text": "",
            "user_commitment": "none",
            "storage_performed": False,
            "memory_kind": str(payload.get("memory_kind") or "user_fact").strip() or "user_fact",
            "state_delta": {},
        }

    outcome_kind = requested_kind
    reply_contract = f"store_fact.{outcome_kind}"
    if outcome_kind != "declarative_ack" and not storage_performed:
        outcome_kind = "declarative_ack"
        reply_contract = "store_fact.declarative_ack"

    return {
        "intent": "store_fact",
        "kind": outcome_kind,
        "reply_contract": reply_contract,
        "fact_text": fact_text,
        "user_commitment": user_commitment,
        "storage_performed": bool(storage_performed),
        "memory_kind": str(payload.get("memory_kind") or ("fact" if source == "declarative" else "user_fact")).strip() or ("fact" if source == "declarative" else "user_fact"),
        "state_delta": {},
    }


def _classify_weather_lookup_outcome(intent_result: dict) -> dict[str, object]:
    payload = intent_result if isinstance(intent_result, dict) else {}
    weather_mode = str(payload.get("weather_mode") or "clarify").strip().lower() or "clarify"
    next_state = payload.get("next_state") if isinstance(payload.get("next_state"), dict) else None
    location_value = str(payload.get("location_value") or "").strip()
    if weather_mode == "current_location":
        return {
            "intent": "weather_lookup",
            "kind": "current_location",
            "reply_contract": "weather_lookup.current_location",
            "weather_mode": weather_mode,
            "location_value": location_value,
            "requires_tool": True,
            "pending_action": None,
            "next_state": next_state,
            "state_delta": next_state or {},
        }
    if weather_mode == "explicit_location" and location_value:
        return {
            "intent": "weather_lookup",
            "kind": "explicit_location",
            "reply_contract": "weather_lookup.explicit_location",
            "weather_mode": weather_mode,
            "location_value": location_value,
            "requires_tool": True,
            "pending_action": None,
            "next_state": next_state,
            "state_delta": next_state or {},
        }
    return {
        "intent": "weather_lookup",
        "kind": "clarify",
        "reply_contract": "weather_lookup.clarify",
        "weather_mode": "clarify",
        "location_value": "",
        "requires_tool": False,
        "pending_action": make_pending_weather_action(),
        "next_state": next_state,
        "state_delta": next_state or {},
    }


def _execute_weather_lookup_outcome(weather_outcome: dict[str, object]) -> tuple[str, Optional[dict], dict[str, object]]:
    outcome = dict(weather_outcome or {})
    weather_mode = str(outcome.get("weather_mode") or "clarify").strip().lower() or "clarify"
    next_state = outcome.get("next_state") if isinstance(outcome.get("next_state"), dict) else None
    if weather_mode == "clarify":
        return render_reply(outcome), next_state, outcome

    if weather_mode == "current_location":
        location_value = str(outcome.get("location_value") or "").strip()
        if location_value:
            tool_result = execute_planned_action("weather_location", [location_value])
        else:
            tool_result = execute_planned_action("weather_current_location")
        next_state = _make_weather_result_state(
            weather_mode=weather_mode,
            location_value=location_value,
            tool_result=str(tool_result or ""),
        )
        outcome["next_state"] = next_state
        outcome["state_delta"] = next_state
        outcome["tool_result"] = str(tool_result or "")
        return render_reply(outcome), next_state, outcome

    if weather_mode == "explicit_location":
        location_value = str(outcome.get("location_value") or "").strip()
        if not location_value:
            fallback = _classify_weather_lookup_outcome({"weather_mode": "clarify", "next_state": next_state})
            return render_reply(fallback), next_state, fallback
        tool_result = execute_planned_action("weather_location", [location_value])
        next_state = _make_weather_result_state(
            weather_mode=weather_mode,
            location_value=location_value,
            tool_result=str(tool_result or ""),
        )
        outcome["next_state"] = next_state
        outcome["state_delta"] = next_state
        outcome["tool_result"] = str(tool_result or "")
        return render_reply(outcome), next_state, outcome

    fallback = _classify_weather_lookup_outcome({"weather_mode": "clarify", "next_state": next_state})
    return render_reply(fallback), next_state, fallback


def _classify_name_origin_outcome(intent_result: dict) -> dict[str, object]:
    payload = intent_result if isinstance(intent_result, dict) else {}
    query_kind = str(payload.get("name_origin_query_kind") or "source_recall").strip().lower() or "source_recall"
    assistant_name = str(get_learned_fact("assistant_name", "Nova") or "Nova").strip() or "Nova"
    developer_name = str(get_learned_fact("developer_name", "Gustavo Uribe") or "Gustavo Uribe").strip() or "Gustavo Uribe"
    developer_nickname = str(get_learned_fact("developer_nickname", "Gus") or developer_name).strip() or developer_name
    story = get_name_origin_story().strip()
    if story:
        if query_kind == "why_called":
            low_story = story.lower()
            if "was given its name" in low_story and "creator" in low_story:
                reply_text = story
            else:
                reply_text = f"{assistant_name} was given its name by its creator, {developer_nickname}. {story}"
        else:
            reply_text = story
        contract = "name_origin.full_story" if query_kind == "full_story" else "name_origin.story_known"
        outcome_kind = "full_story" if query_kind == "full_story" else "story_known"
    else:
        if query_kind == "full_story":
            reply_text = "I do not have a saved full name-origin story yet. You can teach me with: remember this ..."
        else:
            reply_text = "I do not have a saved name-origin story yet. You can teach me with: remember this ..."
        contract = "name_origin.story_missing"
        outcome_kind = "story_missing"
    return {
        "intent": "name_origin",
        "kind": outcome_kind,
        "query_kind": query_kind,
        "reply_contract": contract,
        "reply_text": reply_text,
        "story_known": bool(story),
        "story_text": story,
        "state_delta": {},
    }


def _execute_identity_history_outcome(
    rule_result: dict,
    current_state: Optional[dict],
    text: str,
    *,
    turns: Optional[list[tuple[str, str]]] = None,
) -> tuple[str, Optional[dict], dict[str, object]]:
    payload = rule_result if isinstance(rule_result, dict) else {}
    outcome_kind = str(payload.get("identity_history_kind") or "history_recall").strip().lower() or "history_recall"
    subject = str(payload.get("subject") or (current_state or {}).get("subject") or "developer").strip() or "developer"
    state_kind = str((current_state or {}).get("kind") or "").strip()
    normalized_text = _normalize_turn_text(text)

    if isinstance(current_state, dict):
        next_state = current_state
    elif subject == "developer" and _speaker_matches_developer():
        next_state = _make_conversation_state("developer_identity", subject="developer")
    else:
        next_state = _make_conversation_state("identity_profile", subject=subject)

    if outcome_kind == "creator_question":
        reply_text = hard_answer(text) or _developer_profile_reply(turns=turns, user_text=text)
        next_state = _make_conversation_state("identity_profile", subject="developer")
        subject = "developer"
    elif outcome_kind == "name_origin":
        if state_kind == "developer_identity" or (subject == "developer" and _speaker_matches_developer()):
            reply_text = _developer_identity_followup_reply(turns=turns, name_focus=True)
            next_state = _make_conversation_state("developer_identity", subject="developer")
            subject = "developer"
        elif state_kind == "identity_profile":
            reply_text = _identity_name_followup_reply(subject)
        else:
            name_origin_outcome = _classify_name_origin_outcome({
                "name_origin_query_kind": str(payload.get("name_origin_query_kind") or "source_recall"),
            })
            reply_text = render_reply(name_origin_outcome)
    else:
        build_history_prompt = any(
            phrase in normalized_text
            for phrase in (
                "how did he develop you",
                "how did he developed you",
                "how did he build you",
                "how was he able to develop you",
            )
        )
        if build_history_prompt:
            reply_text = _developer_profile_reply(turns=turns, user_text=text)
            next_state = _make_conversation_state("identity_profile", subject="developer")
            subject = "developer"
        elif state_kind == "developer_identity" or (subject == "developer" and _speaker_matches_developer()):
            reply_text = _developer_identity_followup_reply(turns=turns, name_focus=False)
            next_state = _make_conversation_state("developer_identity", subject="developer")
            subject = "developer"
        else:
            reply_text = _identity_profile_followup_reply(subject, turns=turns)

    outcome = {
        "intent": "identity_history_family",
        "kind": outcome_kind,
        "reply_contract": f"identity_history.{outcome_kind}",
        "reply_text": str(reply_text or "").strip(),
        "subject": subject,
        "state_delta": dict(next_state or {}) if isinstance(next_state, dict) else {},
    }
    return outcome["reply_text"], next_state, outcome


def _open_probe_reply(text: str, turns: Optional[list[tuple[str, str]]] = None) -> tuple[str, str]:
    normalized = _normalize_turn_text(text)
    normalized_key = re.sub(r"[^a-z0-9 ]+", " ", normalized)
    normalized_key = re.sub(r"\s+", " ", normalized_key).strip()
    if normalized_key in {"can you help me a little here", "can you help me here"}:
        return (
            "What kind of help do you want?",
            "safe_fallback",
        )
    if normalized_key in {"what do you think then", "what now", "what next", "okay so what next", "where does that leave us"}:
        return (
            "I don't have enough context to answer that yet. Tell me the topic or decision you want help with, and I'll stay on it.",
            "safe_fallback",
        )
    if any(cue in normalized for cue in ("what are you talking about", "what are you talking", "what ?", "what?")):
        last_assistant = ""
        for role, txt in reversed(list(turns or [])):
            if str(role or "").strip().lower() == "assistant":
                last_assistant = str(txt or "").strip()
                break
        if last_assistant and any(token in last_assistant.lower() for token in ("allowlisted references", "web lookup", "web research")):
            return (
                "You're right. That response drifted into web lookup when you were asking a direct chat question. Ask it again and I'll answer it directly.",
                "clarification",
            )
        return (
            "You're right. I should stay with the current chat instead of jumping to web lookup for that kind of question.",
            "clarification",
        )
    return (
        _truthful_limit_reply(text),
        "safe_fallback",
    )


def _truthful_limit_reply(
    text: str = "",
    *,
    limitation: str = "cannot_verify",
    include_next_step: bool = True,
) -> str:
    normalized = _normalize_turn_text(text)
    limitation_kind = str(limitation or "cannot_verify").strip().lower() or "cannot_verify"
    if limitation_kind == "cannot_do":
        base = "I can't do that with the tools or permissions I have available right now, and I don't want to pretend I can."
    else:
        base = "I don't know that based on what I can verify right now, and I don't want to make it up."

    learning_invitation = "If you know the answer or want to correct me, tell me and I'll store it so I do better next time."

    if not include_next_step:
        return base + " " + learning_invitation
    if _looks_like_mixed_info_request_turn(normalized):
        return base + " Please split the request or tell me which part you want me to handle first. " + learning_invitation
    if _is_explicit_request(normalized) or "?" in normalized:
        return base + " If you want, I can ask a clarifying question or use a grounded source or tool if one is available. " + learning_invitation
    return base + " If you want, I can stay on the current thread, ask a clarifying question, or use a grounded source or tool if one is available. " + learning_invitation


def _attach_learning_invitation(reply_text: str, *, truthful_limit: bool = False) -> str:
    reply = str(reply_text or "").strip()
    if not reply:
        return reply

    normalized = _normalize_turn_text(reply)
    if "correct me" in normalized and ("store it" in normalized or "do better next time" in normalized):
        return reply

    if not truthful_limit:
        return reply

    suffix = "If you know the answer or want to correct me, tell me and I'll store it so I do better next time."
    return reply + " " + suffix


def _truthful_limit_outcome(
    text: str = "",
    *,
    limitation: str = "cannot_verify",
) -> dict[str, str]:
    return {
        "intent": "truthful_limit",
        "kind": str(limitation or "cannot_verify").strip().lower() or "cannot_verify",
        "reply_contract": "turn.truthful_limit",
        "reply_text": _truthful_limit_reply(text, limitation=limitation),
    }


def _last_question_recall_reply(text: str, turns: Optional[list[tuple[str, str]]] = None) -> tuple[str, str]:
    last_question = _extract_last_user_question(list(turns or []), text)
    if last_question:
        return f"Your last question before this one was: {last_question}", "recall"
    return "I don't have an earlier question in this active chat session.", "empty"


def _session_fact_recall_reply(rule_result: dict) -> tuple[str, str]:
    target = str((rule_result or {}).get("fact_target") or "").strip().lower()
    value = str((rule_result or {}).get("fact_value") or "").strip()
    if value:
        return value.rstrip(".!?"), target or "fact"
    return "I do not have that fact in this active chat session.", "empty"


def _execute_retrieval_followup_outcome(state: dict, text: str) -> tuple[str, Optional[dict], dict[str, object]]:
    current_state = state if isinstance(state, dict) else {}
    urls = current_state.get("urls") if isinstance(current_state.get("urls"), list) else []
    query = str(current_state.get("query") or "").strip()
    source = str(current_state.get("subject") or "retrieval").strip().lower()
    result_count = max(0, int(current_state.get("result_count", 0) or 0))
    index = _extract_retrieval_result_index(text)

    if _is_retrieval_meta_question(text):
        reply_text = _retrieval_meta_reply(current_state)
        outcome = {
            "intent": "retrieval_followup",
            "kind": "meta_summary",
            "reply_contract": "retrieval_followup.meta_summary",
            "reply_text": reply_text,
            "query": query,
            "result_count": result_count,
            "selected_index": None,
            "state_delta": current_state,
        }
        return render_reply(outcome), current_state, outcome

    if index is not None and 1 <= index <= len(urls):
        selected_url = str(urls[index - 1])
        result = tool_web_gather(selected_url)
        next_state = _make_retrieval_conversation_state("web_gather", selected_url, result) or current_state
        outcome = {
            "intent": "retrieval_followup",
            "kind": "selected_result",
            "reply_contract": "retrieval_followup.selected_result",
            "reply_text": str(result or ""),
            "query": query,
            "result_count": result_count,
            "selected_index": index,
            "selected_url": selected_url,
            "state_delta": next_state,
        }
        return render_reply(outcome), next_state, outcome

    if source == "web_research" and _looks_like_retrieval_followup(text):
        result = tool_web_research("", continue_mode=True)
        if result and not result.lower().startswith("no active web research session"):
            next_state = _make_retrieval_conversation_state("web_research", WEB_RESEARCH_SESSION.query, result) or current_state
            outcome = {
                "intent": "retrieval_followup",
                "kind": "continued_results",
                "reply_contract": "retrieval_followup.continued_results",
                "reply_text": str(result or ""),
                "query": str(WEB_RESEARCH_SESSION.query or query).strip(),
                "result_count": WEB_RESEARCH_SESSION.result_count() if WEB_RESEARCH_SESSION.has_results() else result_count,
                "selected_index": None,
                "state_delta": next_state,
            }
            return render_reply(outcome), next_state, outcome

    parts = []
    if query:
        parts.append(f"Continuing from your last retrieval for '{query}'.")
    else:
        parts.append("Continuing from your last retrieval thread.")
    if result_count > 0:
        parts.append(f"I have {result_count} source(s) in the current retrieval context.")
    if urls:
        parts.append("You can ask me about the first result, the second source, or tell me to gather one directly.")
    else:
        parts.append("If you want, I can run a more specific search or gather a particular source.")
    reply_text = " ".join(parts)
    outcome = {
        "intent": "retrieval_followup",
        "kind": "guidance",
        "reply_contract": "retrieval_followup.guidance",
        "reply_text": reply_text,
        "query": query,
        "result_count": result_count,
        "selected_index": index,
        "state_delta": current_state,
    }
    return render_reply(outcome), current_state, outcome


def _classify_web_research_outcome(
    intent_result: dict,
    user_text: str = "",
    *,
    turns: Optional[list[tuple[str, str]]] = None,
) -> dict[str, object]:
    payload = intent_result if isinstance(intent_result, dict) else {}
    request_kind = str(payload.get("web_request_kind") or "research_prompt").strip().lower() or "research_prompt"
    tool_name = str(payload.get("tool_name") or "web_research").strip().lower() or "web_research"
    provider_candidates = payload.get("provider_candidates") if isinstance(payload.get("provider_candidates"), list) else []
    provider_family = str(payload.get("provider_family") or "general_web").strip().lower() or "general_web"
    query = str(payload.get("query") or "").strip()
    if request_kind == "deep_search" and not query:
        query = _infer_research_query_from_turns(list(turns or []))
    if not query:
        query = str(user_text or "").strip()
    resolved = _resolve_research_provider(provider_candidates, default_tool=tool_name)
    tool_name = str(resolved.get("tool_name") or tool_name).strip().lower() or tool_name
    provider_used = str(resolved.get("provider") or _provider_name_from_tool(tool_name)).strip().lower() or _provider_name_from_tool(tool_name)
    return {
        "intent": "web_research_family",
        "kind": request_kind,
        "reply_contract": f"web_research_family.{request_kind}",
        "tool_name": tool_name,
        "provider_candidates": list(provider_candidates or []),
        "provider_family": provider_family,
        "provider_used": provider_used,
        "query": query,
        "requires_tool": True,
        "state_delta": {},
    }


def start_action_ledger_record(
    user_input: str,
    *,
    channel: str = "cli",
    session_id: str = "",
    input_source: str = "typed",
    active_subject: str = "",
) -> dict:
    record = {
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "channel": str(channel or "cli").strip().lower() or "cli",
        "session_id": str(session_id or "").strip(),
        "input_source": str(input_source or "typed").strip().lower() or "typed",
        "user_input": str(user_input or "").strip(),
        "intent": _infer_turn_intent(user_input),
        "planner_decision": "",
        "tool": "",
        "tool_args": {},
        "tool_result": "",
        "final_answer": "",
        "reply_contract": "",
        "reply_outcome": {},
        "turn_acts": [],
        "grounded": False,
        "active_subject": str(active_subject or "").strip(),
        "continuation_used": False,
        "route_trace": [],
    }
    action_ledger_add_step(
        record,
        "input",
        "received",
        channel=str(channel or "cli"),
        input_source=str(input_source or "typed"),
        intent=record.get("intent") or "",
    )
    return record


def write_action_ledger_record(record: dict) -> Optional[Path]:
    try:
        ACTION_LEDGER_DIR.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y-%m-%d_%H-%M-%S")
        ms = int((time.time() % 1) * 1000)
        digest = hashlib.sha1(
            str(record.get("user_input", "")).encode("utf-8", errors="ignore")
            + str(time.time_ns()).encode("ascii", errors="ignore")
        ).hexdigest()[:8]
        out = ACTION_LEDGER_DIR / f"{ts}_{ms:03d}_{digest}.json"
        out.write_text(json.dumps(record, ensure_ascii=True, indent=2), encoding="utf-8")
        return out
    except Exception:
        return None


def _append_memory_event(payload: dict) -> None:
    try:
        MEMORY_EVENTS_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(MEMORY_EVENTS_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=True) + "\n")
    except Exception:
        pass


def _record_memory_event(
    action: str,
    status: str,
    *,
    user: Optional[str] = None,
    scope: str = "private",
    backend: str = "",
    kind: str = "",
    source: str = "",
    query: str = "",
    reason: str = "",
    error: str = "",
    result_count: Optional[int] = None,
    duration_ms: Optional[int] = None,
    mode: str = "",
) -> None:
    payload = {
        "event": "memory_operation",
        "action": str(action or "").strip() or "unknown",
        "status": str(status or "").strip() or "unknown",
        "user": str(user or "").strip(),
        "scope": str(scope or "private").strip() or "private",
        "backend": str(backend or "").strip(),
        "kind": str(kind or "").strip(),
        "source": str(source or "").strip(),
        "query_preview": " ".join(str(query or "").split())[:120],
        "reason": str(reason or "").strip(),
        "error": str(error or "").strip()[:300],
        "mode": str(mode or "").strip(),
        "ts": int(time.time()),
    }
    if result_count is not None:
        payload["result_count"] = int(result_count)
    if duration_ms is not None:
        payload["duration_ms"] = int(duration_ms)
    _append_memory_event(payload)


def finalize_action_ledger_record(
    record: dict,
    *,
    final_answer: str,
    planner_decision: str = "",
    tool: str = "",
    tool_args: Optional[dict] = None,
    tool_result: str = "",
    grounded: Optional[bool] = None,
    intent: str = "",
    active_subject: str = "",
    continuation_used: Optional[bool] = None,
    reply_contract: str = "",
    reply_outcome: Optional[dict] = None,
    routing_decision: Optional[dict] = None,
    reflection_payload: Optional[dict] = None,
) -> Optional[Path]:
    rec = dict(record or {})
    if not isinstance(rec.get("route_trace"), list):
        rec["route_trace"] = []
    if intent:
        rec["intent"] = str(intent).strip()
    rec["planner_decision"] = str(planner_decision or rec.get("planner_decision") or "deterministic").strip()
    rec["tool"] = str(tool or rec.get("tool") or "").strip()
    args = tool_args if isinstance(tool_args, dict) else rec.get("tool_args")
    rec["tool_args"] = args if isinstance(args, dict) else {}
    rec["tool_result"] = str(tool_result or rec.get("tool_result") or "")
    rec["final_answer"] = str(final_answer or "")
    rec["reply_contract"] = str(reply_contract or rec.get("reply_contract") or "").strip()
    outcome_payload = reply_outcome if isinstance(reply_outcome, dict) else rec.get("reply_outcome")
    rec["reply_outcome"] = dict(outcome_payload) if isinstance(outcome_payload, dict) else {}
    rec["provider_used"] = str((rec.get("reply_outcome") or {}).get("provider_used") or rec.get("provider_used") or _provider_name_from_tool(rec.get("tool") or "")).strip()
    provider_candidates = (rec.get("reply_outcome") or {}).get("provider_candidates") if isinstance(rec.get("reply_outcome"), dict) else rec.get("provider_candidates")
    rec["provider_candidates"] = list(provider_candidates or []) if isinstance(provider_candidates or [], list) else []
    rec["provider_family"] = str((rec.get("reply_outcome") or {}).get("provider_family") or rec.get("provider_family") or rec["provider_used"] or "").strip()
    acts = rec.get("turn_acts")
    rec["turn_acts"] = [str(item).strip() for item in acts if str(item).strip()] if isinstance(acts, list) else []
    finalized_routing_decision = _finalize_routing_decision(
        routing_decision if isinstance(routing_decision, dict) else rec.get("routing_decision"),
        planner_decision=rec.get("planner_decision") or "",
        reply_contract=rec.get("reply_contract") or "",
        reply_outcome=rec.get("reply_outcome") if isinstance(rec.get("reply_outcome"), dict) else {},
    )
    if finalized_routing_decision:
        rec["routing_decision"] = finalized_routing_decision
    rec["active_subject"] = str(active_subject or rec.get("active_subject") or "").strip()
    rec["continuation_used"] = bool(rec.get("continuation_used", False)) if continuation_used is None else bool(continuation_used)
    if grounded is None:
        fa = rec["final_answer"].lower()
        tr = rec["tool_result"].strip()
        rec["grounded"] = bool(tr) or "[source:" in fa or "[tool:" in fa
    else:
        rec["grounded"] = bool(grounded)
    if not rec.get("route_trace"):
        action_ledger_add_step(rec, "planner", rec.get("planner_decision") or "deterministic")
    if not any(str((step or {}).get("stage") or "") == "finalize" for step in rec.get("route_trace") or [] if isinstance(step, dict)):
        action_ledger_add_step(
            rec,
            "finalize",
            rec.get("planner_decision") or "deterministic",
            grounded=bool(rec.get("grounded")),
            tool=rec.get("tool") or "",
        )
    rec["route_summary"] = action_ledger_route_summary(rec)
    path = write_action_ledger_record(rec)
    if path is not None:
        all_records = _recent_action_ledger_records(limit=1000000)
        recent_for_reflection = all_records[-20:]
        maybe_log_self_reflection(limit=20, every=1, records=recent_for_reflection, total_records=len(all_records), extra_payload=reflection_payload)
    return path


def _is_factual_identity_or_policy_query(text: str) -> bool:
    t = (text or "").strip().lower()
    if not t:
        return False
    cues = [
        "what is", "why is", "who is", "full name", "rules", "policy", "requirements",
        "attendance", "peims", "tsds", "tea",
    ]
    return any(c in t for c in cues)


def _is_capability_query(text: str) -> bool:
    t = (text or "").strip().lower()
    if not t:
        return False
    cues = [
        "what can you do",
        "what do you do",
        "what do you do nova",
        "what do you do?",
        "your abilities",
        "your ability",
        "what do you help with",
        "what do you do here",
        "what are you capable",
        "know what your capable",
        "know what you're capable",
        "capabilities",
    ]
    return any(c in t for c in cues)


def _is_policy_domain_query(text: str) -> bool:
    t = (text or "").strip().lower()
    if not t:
        return False
    cues = [
        "domain access",
        "allowed domains",
        "what domains",
        "policy",
        "web access",
        "which domains",
    ]
    return any(c in t for c in cues)


def _is_action_history_query(text: str) -> bool:
    t = (text or "").strip().lower()
    if not t:
        return False
    cues = [
        "what did you just do",
        "what did you do",
        "last action",
        "last tool",
        "what did you just run",
    ]
    return any(c in t for c in cues)


def _is_identity_or_developer_query(text: str) -> bool:
    t = (text or "").strip().lower()
    t = re.sub(r"\byor\b", "your", t)
    if not t:
        return False
    cues = [
        "your name",
        "who are you",
        "developer",
        "creator",
        "full name",
        "name origin",
        "why are you called",
        "why is your name",
        "did you learn about your name",
        "do you remember me",
        "do you know me",
        "what is my name",
        "what's my name",
        "know my name",
        "just knowing my name",
        "what do you know about me",
        "what else do you know about me",
        "what do you remember about me",
    ]
    return any(c in t for c in cues)


def _is_name_origin_question(text: str) -> bool:
    low = (text or "").strip().lower()
    cues = [
        "where your name comes from",
        "where does your name come from",
        "story behind your name",
        "story behing your name",
        "why are you called nova",
        "why nova",
        "do you know where your name comes from",
        "what does your name mean",
    ]
    return any(c in low for c in cues)


def _is_assistant_name_query(text: str) -> bool:
    low = (text or "").strip().lower()
    low = re.sub(r"\byor\b", "your", low)
    cues = [
        "what is your name",
        "what's your name",
        "are you sure that is your name",
        "your name is not",
        "is your name",
    ]
    if any(c in low for c in cues):
        return True
    if re.search(r"\bare\s+\w*ou\s+sure\b.*\bname\b", low):
        return True
    return False


def _is_self_identity_web_challenge(text: str) -> bool:
    low = (text or "").strip().lower()
    low = re.sub(r"\byor\b", "your", low)
    if "web" not in low:
        return False
    identity_cues = (
        "your name",
        "who you are",
        "who are you",
    )
    challenge_cues = (
        "why should i",
        "why would i",
        "why do i need",
        "why use the web",
        "try to use the web",
    )
    return any(cue in low for cue in identity_cues) and any(cue in low for cue in challenge_cues)


def _self_identity_web_challenge_reply() -> str:
    assistant_name = get_learned_fact("assistant_name", "Nova")
    return f"You should not need web research for my name. I already know my name is {assistant_name}, so that should be answered directly from my verified identity facts."


def _assistant_name_reply(text: str) -> str:
    assistant_name = get_learned_fact("assistant_name", "Nova")
    low = (text or "").strip().lower()
    if "your name is nova" in low:
        return f"Correct. My name is {assistant_name}."
    return f"My name is {assistant_name}."


def _is_developer_full_name_query(text: str) -> bool:
    low = (text or "").strip().lower()
    if "full name" not in low:
        return False
    query_cues = ["what is", "what's", "tell me", "do you know", "can you tell me"]
    if "?" not in text and not any(cue in low for cue in query_cues):
        return False
    cues = ["developer", "gus", "nickname", "nick name", "his full name"]
    return any(c in low for c in cues)


def _developer_full_name_reply() -> str:
    full_name = get_learned_fact("developer_name", "Gustavo")
    if str(full_name or "").strip().lower() == "gustavo":
        full_name = "Gustavo Uribe"
    nickname = get_learned_fact("developer_nickname", "Gus")
    if nickname and nickname.lower() != full_name.lower():
        return f"My developer's full name is {full_name}. {nickname} is his nickname."
    return f"My developer's full name is {full_name}."


def _is_location_request(user_text: str) -> bool:
    normalized = _normalize_turn_text(user_text)
    if not normalized:
        return False
    return any(cue in normalized for cue in (
        "where is nova",
        "where are you",
        "your location",
        "what is your location",
        "what is your current location",
        "what is your current physical location",
        "where are you located",
        "where is nova located",
    ))


def _location_reply() -> str:
    live = runtime_device_location_payload()
    if live.get("available") and not live.get("stale"):
        accuracy = live.get("accuracy_m")
        accuracy_note = f" Accuracy about {int(round(float(accuracy)))}m." if accuracy is not None else ""
        return f"My current device location is {live.get('coords_text')}.{accuracy_note}"
    preview = get_saved_location_text()
    if preview:
        return f"My location is {preview}."
    return "I don't have a stored location yet. You can tell me: 'My location is ...'"


def _is_session_recap_request(text: str) -> bool:
    low = (text or "").strip().lower()
    cues = [
        "recap",
        "what were we talking about",
        "what we just talked about",
        "previous chat lines",
        "entire chat session",
        "go back to our previous chat",
        "follow the chat",
    ]
    return any(c in low for c in cues)


def _session_recap_reply(turns: list[tuple[str, str]], current_text: str) -> str:
    current_low = (current_text or "").strip().lower()
    topics: list[str] = []

    for role, txt in turns:
        if role != "user":
            continue
        clean = re.sub(r"\s+", " ", (txt or "").strip())
        if not clean:
            continue
        low = clean.lower()
        if low == current_low:
            continue
        if _is_session_recap_request(clean):
            continue
        if len(clean) > 180:
            clean = clean[:177] + "..."
        topics.append(clean)

    if not topics:
        return "I do not have enough prior user turns in this session to recap yet."

    recent = topics[-6:]
    lines = ["Recap of this session so far:"]
    for index, topic in enumerate(recent, start=1):
        lines.append(f"{index}. {topic}")
    return "\n".join(lines)


def _is_deep_search_followup_request(text: str) -> bool:
    del text
    return False


def _infer_research_query_from_turns(turns: list[tuple[str, str]]) -> str:
    for role, txt in reversed(turns):
        if role != "user":
            continue
        low = (txt or "").strip().lower()
        if not low:
            continue
        if _is_deep_search_followup_request(low) or _is_session_recap_request(low):
            continue
        if "peims" in low and "attendance" in low:
            return "PEIMS attendance reporting rules Texas TEA ADA excused unexcused absences"
        return txt
    return ""


def _latest_action_ledger_record() -> dict:
    try:
        if not ACTION_LEDGER_DIR.exists():
            return {}
        files = sorted(ACTION_LEDGER_DIR.glob("*.json"))
        if not files:
            return {}
        data = json.loads(files[-1].read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _action_history_reply() -> str:
    rec = _latest_action_ledger_record()
    if not rec:
        return "No action ledger record exists yet in this runtime."
    tool = str(rec.get("tool") or "").strip() or "none"
    decision = str(rec.get("planner_decision") or "").strip() or "unknown"
    intent = str(rec.get("intent") or "").strip() or "unknown"
    grounded = bool(rec.get("grounded"))
    final_answer = str(rec.get("final_answer") or "").strip()
    route_summary = action_ledger_route_summary(rec)
    if len(final_answer) > 220:
        final_answer = final_answer[:217] + "..."
    return (
        "Last action record: "
        f"intent={intent}; decision={decision}; tool={tool}; grounded={grounded}. "
        f"route={route_summary or '[none]'}. "
        f"final_answer={final_answer or '[none]'}"
    )


def truth_hierarchy_answer(user_text: str) -> tuple[bool, str, str, bool]:
    """Return deterministic answer for strict-truth query classes.

    Source precedence for these classes:
    1) verified tool/action ledger
    2) structured learned facts / deterministic identity rules
    3) capability registry
    4) policy configuration
    """
    t = (user_text or "").strip()
    if not t:
        return False, "", "", False

    if _is_action_history_query(t):
        return True, _action_history_reply(), "action_ledger", True

    if _is_identity_or_developer_query(t):
        hard = hard_answer(t)
        if hard:
            return True, hard, "learned_facts", True
        story = get_name_origin_story().strip()
        if "did you learn about your name" in t.lower() and story:
            return True, story, "learned_facts", True
        return False, "", "", False

    if _is_capability_query(t):
        return True, describe_capabilities(), "capability_registry", True

    if _is_policy_domain_query(t):
        web = policy_web()
        domains = list(web.get("allow_domains") or [])
        enabled = bool(web.get("enabled", False))
        lines = [f"Policy web access enabled: {enabled}"]
        if domains:
            lines.append("Allowed domains: " + ", ".join(domains))
        else:
            lines.append("Allowed domains: none configured")
        return True, "\n".join(lines), "policy_json", True

    return False, "", "", False


def _self_correct_reply(user_text: str, reply: str) -> tuple[str, bool, str]:
    out = (reply or "").strip()
    if not out:
        return out, False, ""

    # Capability questions must resolve to the deterministic capability model.
    if _is_capability_query(user_text):
        target = describe_capabilities().strip()
        if target and re.sub(r"\s+", " ", out).lower() != re.sub(r"\s+", " ", target).lower():
            return target, True, "capability_alignment"

    # Guard against autonomy claims outside Nova's controlled execution model.
    low = out.lower()
    bad_autonomy = [
        "enhance myself on my own",
        "enhance myself autonomously",
        "i can enhance myself",
        "i will enhance myself",
        "self-sustenance",
    ]
    if any(b in low for b in bad_autonomy):
        corrected = (
            "I cannot self-enhance on my own. I can only improve through your explicit guidance, "
            "validated tool runs, and saved corrections."
        )
        return corrected, True, "autonomy_guard"

    return out, False, ""


def should_block_low_confidence(user_text: str, retrieved_context: str = "", tool_context: str = "") -> bool:
    # Only gate factual questions, not smalltalk/open-ended creative prompts.
    if not _is_factual_identity_or_policy_query(user_text):
        return False
    has_ctx = bool((retrieved_context or "").strip())
    has_tool = bool((tool_context or "").strip())
    return not (has_ctx or has_tool)


def detect_identity_conflict() -> bool:
    learned = load_learned_facts()
    assistant_name = str(learned.get("assistant_name") or "").strip().lower()
    story = get_name_origin_story().strip().lower()
    if not assistant_name or not story:
        return False
    # Flag obvious contradictions between learned assistant name and story mentions.
    if "my name is" in story and assistant_name not in story:
        return True
    return False


def ok(msg): print(f"[OK]   {msg}", flush=True)
def warn(msg): print(f"[WARN] {msg}", flush=True)
def bad(msg): print(f"[FAIL] {msg}", flush=True)


def load_policy() -> dict:
    return _policy_manager().load_policy()


def _load_policy_raw() -> dict:
    return _policy_manager()._load_raw()


def _save_policy_raw(data: dict) -> None:
    _policy_manager()._save_raw(data)


def _record_policy_change(action: str, target: str, result: str, details: str = "") -> None:
    _policy_manager().record_change(action, target, result, details, get_active_user())


def policy_models():
    return _policy_manager().get_models()


def policy_memory():
    return _policy_manager().get_memory()


def policy_tools_enabled():
    return _policy_manager().get_tools_enabled()


def _memory_adapter_service() -> MemoryAdapterService:
    return MemoryAdapterService(
        policy_memory_getter=policy_memory,
        active_user_getter=get_active_user,
    )


def _tool_execution_service() -> ToolExecutionService:
    return ToolExecutionService(
        policy_loader=load_policy,
        active_user_getter=get_active_user,
        base_dir=BASE_DIR,
        registry_service=TOOL_REGISTRY_SERVICE,
    )


def build_tool_context(*, is_admin: bool = False, extra: Optional[dict] = None) -> ToolContext:
    return _tool_execution_service().build_tool_context(is_admin=is_admin, extra=extra)


def _tool_error_message(tool_name: str, reason: str) -> str:
    return _tool_execution_service().tool_error_message(tool_name, reason)


def execute_registered_tool(tool_name: str, args: dict, *, is_admin: bool = False, extra: Optional[dict] = None) -> str:
    return _tool_execution_service().execute_registered_tool(
        tool_name,
        args,
        is_admin=is_admin,
        extra=extra,
    )
    
def _research_handlers() -> dict[str, object]:
    return {
        "web_fetch": tool_web_fetch,
        "web_search": tool_web_search,
        "web_research": tool_web_research,
        "web_gather": tool_web_gather,
        "wikipedia_lookup": tool_wikipedia_lookup,
        "stackexchange_search": tool_stackexchange_search,
    }

def execute_research_action(action: str, value: str) -> str:
    return execute_registered_tool(
        "research",
        {"action": str(action or "").strip(), "value": str(value or "").strip()},
        extra={"research_handlers": _research_handlers()},
    )


def _patch_handlers() -> dict[str, object]:
    return {
        "preview": patch_preview,
        "list_previews": lambda _value="": list_previews(),
        "show": show_preview,
        "approve": approve_preview,
        "reject": reject_preview,
        "apply": patch_apply,
        "rollback": lambda _value="": patch_rollback(_value or None),
    }


def execute_patch_action(action: str, value: str = "", *, force: bool = False, is_admin: bool = True) -> str:
    return execute_registered_tool(
        "patch",
        {"action": str(action or "").strip(), "value": str(value or "").strip(), "force": bool(force)},
        is_admin=is_admin,
        extra={"patch_handlers": _patch_handlers()},
    )


def policy_web():
    return _policy_manager().get_web()


def policy_patch():
    return _policy_manager().get_patch()


def web_enabled() -> bool:
    return _policy_manager().is_web_enabled()


def _host_allowed(host: str, allow_domains: list[str]) -> bool:
    return _policy_manager().host_allowed(host, allow_domains)


def web_fetch(url: str, save_dir: Path) -> dict:
    """
    Fetch a URL (http/https only) if host is allowlisted.
    Saves to save_dir with deterministic filename.
    Never raises; always returns {"ok": bool, ...}.
    """
    if not web_enabled():
        return {"ok": False, "error": "Web tool disabled by policy."}

    cfg = policy_web()
    allow_domains = cfg.get("allow_domains") or []
    max_bytes = int(cfg.get("max_bytes") or 20_000_000)

    u = urlparse(url.strip())
    if u.scheme not in ("http", "https"):
        return {"ok": False, "error": "Only http/https URLs are allowed."}
    host = u.hostname or ""
    if not _host_allowed(host, allow_domains):
        return {"ok": False, "error": f"Domain not allowed: {host}"}

    save_dir.mkdir(parents=True, exist_ok=True)

    h = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    ts = time.strftime("%Y%m%d_%H%M%S")
    base = f"{ts}_{host}_{h}"

    try:
        r = requests.get(url, stream=True, timeout=60, headers={"User-Agent": "Nova/1.0"})
    except requests.exceptions.RequestException as e:
        return {"ok": False, "error": f"Request failed: {e}"}

    try:
        r.raise_for_status()
        ctype = (r.headers.get("Content-Type") or "").split(";")[0].strip().lower()

        if ctype == "application/pdf":
            ext = ".pdf"
        elif ctype in ("text/html", "application/xhtml+xml"):
            ext = ".html"
        elif ctype.startswith("text/"):
            ext = ".txt"
        else:
            ext = mimetypes.guess_extension(ctype) or ".bin"

        out_path = save_dir / (base + ext)

        total = 0
        with open(out_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=65536):
                if not chunk:
                    continue
                total += len(chunk)
                if total > max_bytes:
                    out_path.unlink(missing_ok=True)
                    return {"ok": False, "error": f"File too large (>{max_bytes} bytes)."}
                f.write(chunk)

        return {"ok": True, "url": url, "path": str(out_path), "content_type": ctype, "bytes": total}

    except requests.exceptions.RequestException as e:
        return {"ok": False, "error": f"HTTP error: {e}"}
    except Exception as e:
        return {"ok": False, "error": f"Unexpected error: {e}"}
    finally:
        try:
            r.close()
        except Exception:
            pass


def _web_allowlist_message(context: str = "") -> str:
    """Return a friendly message explaining web allowlist restrictions and list allowed domains."""
    cfg = policy_web()
    allow_domains = cfg.get("allow_domains") or []
    if not allow_domains:
        base = "I attempted to access the web, but web access is restricted by policy and no allowlisted domains are configured."
        return base

    lines = [f"I attempted to access the web{(' for ' + context) if context else ''}, but my web tool only allows specific sources:"]
    for d in allow_domains:
        lines.append(f"- {d}")

    # suggest common weather API if present in allowlist otherwise suggest a known source
    preferred = None
    for candidate in ("api.weather.gov", "noaa.gov", "weather.gov"):
        for d in allow_domains:
            if candidate in d:
                preferred = candidate
                break
        if preferred:
            break

    if preferred:
        lines.append(f"If you'd like, I can try again using {preferred}.")
    else:
        lines.append("If you'd like, tell me which of the allowlisted domains to try, or provide an allowed URL to fetch.")
    lines.append("To add a new allowed domain, use: policy allow <domain>")

    return "\n".join(lines)


def _weather_source_host() -> Optional[str]:
    allow_domains = [str(d).strip().lower() for d in (policy_web().get("allow_domains") or []) if str(d).strip()]
    for preferred in ("api.weather.gov", "wttr.in"):
        for d in allow_domains:
            if d == preferred or d.endswith("." + preferred):
                return preferred
    return None


def _weather_unavailable_message() -> str:
    return (
        "I can access websites, but I don't yet have a reliable structured weather source configured. "
        "I cannot honestly claim weather results from raw weather.com pages. "
        "Add a source like 'policy allow api.weather.gov' and then use 'weather <location-or-lat,lon>'."
    )


def weather_response_style() -> str:
    try:
        s = str((policy_web().get("weather_response_style") or "concise")).strip().lower()
        if s in {"concise", "tool"}:
            return s
    except Exception:
        pass
    return "concise"


def _format_weather_output(label: str, summary: str) -> str:
    # Normalize whitespace and strip any existing weather-style prefixes so output is never stacked.
    s = re.sub(r"\s+", " ", (summary or "").strip())
    s = re.sub(r"^(?:weather|forecast)\s+for\s+[^:]+:\s*", "", s, flags=re.I)
    l = (label or "").strip() or "this location"

    # Normalize common deterministic location aliases to cleaner display names.
    aliases = {
        "brownsville": "Brownsville, TX",
        "brownsville tx": "Brownsville, TX",
        "brownsville, tx": "Brownsville, TX",
    }
    n = re.sub(r"\s+", " ", l.lower()).strip()
    l = aliases.get(n, l)

    style = weather_response_style()
    if style == "tool":
        return f"Forecast for {l}: {s}"
    return f"{l}: {s}"


DEVICE_LOCATION_MAX_AGE_SEC = 300.0


def _runtime_device_backend_provider() -> dict:
    platform_supported = os.name == "nt"
    winsdk_installed = False
    if platform_supported:
        try:
            winsdk_installed = bool(
                importlib.util.find_spec("winsdk.windows.devices.geolocation")
                or importlib.util.find_spec("winsdk")
            )
        except Exception:
            winsdk_installed = False
    available = platform_supported and winsdk_installed
    if available:
        message = "Windows geolocation fallback is ready."
    elif platform_supported:
        message = "Windows geolocation fallback requires the winsdk package."
    else:
        message = "Windows geolocation fallback is only available on Windows hosts."
    return {
        "name": "windows_geolocator",
        "platform_supported": platform_supported,
        "winsdk_installed": winsdk_installed,
        "available": available,
        "message": message,
    }


def _coerce_bounded_float(value, *, minimum: float, maximum: float) -> Optional[float]:
    try:
        number = float(value)
    except Exception:
        return None
    if not math.isfinite(number):
        return None
    if number < minimum or number > maximum:
        return None
    return number


def _coerce_optional_metric(value) -> Optional[float]:
    try:
        if value in {None, ""}:
            return None
        number = float(value)
    except Exception:
        return None
    if not math.isfinite(number):
        return None
    return number


def _normalize_source_timestamp(value) -> float:
    now = time.time()
    try:
        number = float(value)
    except Exception:
        return now
    if not math.isfinite(number) or number <= 0:
        return now
    if number > 1_000_000_000_000:
        number /= 1000.0
    return min(number, now)


def _format_runtime_coords(lat: float, lon: float) -> str:
    return f"{lat:.5f},{lon:.5f}"


def _device_location_status_payload(snapshot: Optional[dict], *, max_age_sec: float = DEVICE_LOCATION_MAX_AGE_SEC) -> dict:
    backend_provider = _runtime_device_backend_provider()
    if not isinstance(snapshot, dict):
        return {
            "available": False,
            "status": "unavailable",
            "stale": False,
            "message": "No live device location fix is available.",
            "backend_provider": backend_provider,
        }

    lat = _coerce_bounded_float(snapshot.get("lat"), minimum=-90.0, maximum=90.0)
    lon = _coerce_bounded_float(snapshot.get("lon"), minimum=-180.0, maximum=180.0)
    if lat is None or lon is None:
        return {
            "available": False,
            "status": "invalid",
            "stale": False,
            "message": "Live device location data is invalid.",
            "backend_provider": backend_provider,
        }

    captured_ts = _normalize_source_timestamp(snapshot.get("captured_ts"))
    age_sec = max(0.0, time.time() - captured_ts)
    stale = age_sec > max(0.0, float(max_age_sec))
    accuracy_m = _coerce_optional_metric(snapshot.get("accuracy_m"))
    speed_mps = _coerce_optional_metric(snapshot.get("speed_mps"))
    heading_deg = _coerce_optional_metric(snapshot.get("heading_deg"))
    altitude_m = _coerce_optional_metric(snapshot.get("altitude_m"))
    coords_text = _format_runtime_coords(lat, lon)
    source = str(snapshot.get("source") or "unknown").strip().lower() or "unknown"

    payload = {
        "available": True,
        "status": "stale" if stale else "live",
        "stale": stale,
        "message": "Live device location is active." if not stale else "Live device location is stale.",
        "lat": lat,
        "lon": lon,
        "coords_text": coords_text,
        "source": source,
        "permission_state": str(snapshot.get("permission_state") or "").strip().lower(),
        "captured_ts": captured_ts,
        "captured_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(captured_ts)),
        "age_sec": round(age_sec, 1),
        "backend_provider": backend_provider,
    }
    if accuracy_m is not None:
        payload["accuracy_m"] = round(max(0.0, accuracy_m), 1)
    if speed_mps is not None:
        payload["speed_mps"] = round(max(0.0, speed_mps), 2)
    if heading_deg is not None:
        payload["heading_deg"] = round(heading_deg % 360.0, 1)
    if altitude_m is not None:
        payload["altitude_m"] = round(altitude_m, 1)
    return payload


def runtime_device_location_payload(*, max_age_sec: float = DEVICE_LOCATION_MAX_AGE_SEC) -> dict:
    try:
        if not DEVICE_LOCATION_FILE.exists():
            return _device_location_status_payload(None, max_age_sec=max_age_sec)
        raw = json.loads(DEVICE_LOCATION_FILE.read_text(encoding="utf-8") or "{}")
    except Exception:
        return {
            "available": False,
            "status": "error",
            "stale": False,
            "message": "Failed to read live device location state.",
            "backend_provider": _runtime_device_backend_provider(),
        }
    return _device_location_status_payload(raw, max_age_sec=max_age_sec)


def set_runtime_device_location(payload: dict) -> tuple[bool, str, dict]:
    data = payload if isinstance(payload, dict) else {}
    lat = _coerce_bounded_float(data.get("lat"), minimum=-90.0, maximum=90.0)
    lon = _coerce_bounded_float(data.get("lon"), minimum=-180.0, maximum=180.0)
    if lat is None or lon is None:
        return False, "device_location_invalid", runtime_device_location_payload()

    snapshot = {
        "lat": lat,
        "lon": lon,
        "accuracy_m": _coerce_optional_metric(data.get("accuracy_m")),
        "speed_mps": _coerce_optional_metric(data.get("speed_mps")),
        "heading_deg": _coerce_optional_metric(data.get("heading_deg")),
        "altitude_m": _coerce_optional_metric(data.get("altitude_m")),
        "source": str(data.get("source") or "browser_watch").strip().lower() or "browser_watch",
        "permission_state": str(data.get("permission_state") or "").strip().lower(),
        "captured_ts": _normalize_source_timestamp(data.get("captured_ts")),
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    try:
        DEVICE_LOCATION_FILE.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(DEVICE_LOCATION_FILE, snapshot)
    except Exception:
        return False, "device_location_write_failed", runtime_device_location_payload()
    return True, "device_location_updated", runtime_device_location_payload()


def clear_runtime_device_location() -> dict:
    try:
        DEVICE_LOCATION_FILE.unlink(missing_ok=True)
    except Exception:
        pass
    return runtime_device_location_payload()


def _resolve_windows_device_coords(timeout_sec: float = 8.0) -> Optional[dict]:
    provider = _runtime_device_backend_provider()
    if not provider.get("available"):
        return None
    try:
        wdg = importlib.import_module("winsdk.windows.devices.geolocation")
    except Exception:
        return None

    async def _read_position() -> Optional[dict]:
        locator = wdg.Geolocator()
        try:
            locator.desired_accuracy = wdg.PositionAccuracy.HIGH
        except Exception:
            pass
        try:
            position = await asyncio.wait_for(locator.get_geoposition_async(), timeout=float(timeout_sec))
        except Exception:
            return None
        try:
            point = position.coordinate.point.position
            return {
                "lat": float(point.latitude),
                "lon": float(point.longitude),
                "accuracy_m": _coerce_optional_metric(getattr(position.coordinate, "accuracy", None)),
                "speed_mps": _coerce_optional_metric(getattr(position.coordinate, "speed", None)),
                "heading_deg": _coerce_optional_metric(getattr(position.coordinate, "heading", None)),
                "altitude_m": _coerce_optional_metric(getattr(point, "altitude", None)),
                "source": "windows_geolocator",
                "permission_state": "granted",
                "captured_ts": time.time(),
            }
        except Exception:
            return None

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_read_position())
    except Exception:
        return None
    finally:
        try:
            loop.close()
        except Exception:
            pass


def resolve_current_device_coords(*, max_age_sec: float = DEVICE_LOCATION_MAX_AGE_SEC) -> Optional[tuple[float, float]]:
    live = runtime_device_location_payload(max_age_sec=max_age_sec)
    if live.get("available") and not live.get("stale"):
        return (float(live.get("lat")), float(live.get("lon")))

    windows_fix = _resolve_windows_device_coords()
    if isinstance(windows_fix, dict):
        ok, _msg, updated = set_runtime_device_location(windows_fix)
        if ok and updated.get("available"):
            return (float(updated.get("lat")), float(updated.get("lon")))
    return None


def _mentions_location_phrase(text: str) -> bool:
    low = (text or "").lower()
    return any(p in low for p in [
        "location",
        "locaiton",  # common typo seen in transcript
        "physical location",
        "physical locaiton",
    ])


BROWNSVILLE_LAT = 25.9017
BROWNSVILLE_LON = -97.4975
_LOCATION_HINT_COORDS = {
    "78521": (BROWNSVILLE_LAT, BROWNSVILLE_LON),
}
_LOCATION_HINT_LABELS = {
    "78521": "Brownsville, TX",
}


def _parse_lat_lon(text: str) -> Optional[tuple[float, float]]:
    m = re.search(r"(-?\d{1,2}(?:\.\d+)?)\s*,\s*(-?\d{1,3}(?:\.\d+)?)", (text or ""))
    if not m:
        return None
    try:
        lat = float(m.group(1))
        lon = float(m.group(2))
    except Exception:
        return None
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return None
    return (lat, lon)


def _coords_for_location_hint(location: str) -> Optional[tuple[float, float]]:
    loc = (location or "").strip().lower()
    if not loc:
        return None
    parsed = _parse_lat_lon(loc)
    if parsed:
        return parsed

    if loc in _LOCATION_HINT_COORDS:
        return _LOCATION_HINT_COORDS[loc]

    if "brownsville" in loc:
        return (BROWNSVILLE_LAT, BROWNSVILLE_LON)

    return None


def _coords_from_saved_location() -> Optional[tuple[float, float]]:
    # Prefer explicit operator-set coordinates stored in core state.
    try:
        st = read_core_state(DEFAULT_STATEFILE)
        c = st.get("location_coords") if isinstance(st, dict) else None
        if isinstance(c, dict):
            lat = float(c.get("lat"))
            lon = float(c.get("lon"))
            if -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0:
                return (lat, lon)
    except Exception:
        pass

    try:
        audit_out = mem_audit("location coordinates lat lon")
        j = json.loads(audit_out) if audit_out else {}
        results = j.get("results") if isinstance(j, dict) else []
        for r in results:
            preview = (r.get("preview") or "").strip()
            parsed = _parse_lat_lon(preview)
            if parsed:
                return parsed
    except Exception:
        return None

    try:
        saved_text = get_saved_location_text()
        if saved_text:
            return _coords_for_location_hint(saved_text)
    except Exception:
        return None
    return None


def get_saved_location_text() -> str:
    try:
        st = read_core_state(DEFAULT_STATEFILE)
        raw = st.get("location_text") if isinstance(st, dict) else ""
        cleaned = _normalize_location_preview(str(raw or ""))
        if cleaned:
            return cleaned
    except Exception:
        pass

    try:
        audit_out = mem_audit("location")
        j = json.loads(audit_out) if audit_out else {}
        results = j.get("results") if isinstance(j, dict) else []
        for row in results:
            preview = _normalize_location_preview((row.get("preview") or "").strip())
            low = preview.lower()
            if not preview:
                continue
            if low.startswith("name:"):
                continue
            if "coordinates" in low:
                continue
            if _parse_lat_lon(preview):
                continue
            return preview
    except Exception:
        pass
    return ""


def set_location_text(value: str, input_source: str = "typed") -> str:
    cleaned = _normalize_location_preview(value)
    if not cleaned:
        return "Usage: my location is <place>"

    try:
        set_core_state(DEFAULT_STATEFILE, "location_text", cleaned)
    except Exception:
        pass

    try:
        mem_add("profile", input_source, f"location: {cleaned}")
    except Exception:
        pass

    try:
        mem_add("user_fact", input_source, f"My location is {cleaned}")
    except Exception:
        pass

    try:
        coords = _coords_for_location_hint(cleaned)
        if coords:
            lat, lon = coords
            set_core_state(DEFAULT_STATEFILE, "location_coords", {"lat": lat, "lon": lon})
    except Exception:
        pass

    return f"Saved current location: {cleaned}"


def _extract_location_fact(text: str) -> str:
    raw = (text or "").strip()
    if not raw or "?" in raw:
        return ""

    patterns = [
        r"^\s*(?:my|your)(?:\s+(?:current|physical))?\s+location\s+is\s+(.+?)\s*[.!?]*$",
        r"^\s*i\s+am\s+located\s+in\s+(.+?)\s*[.!?]*$",
        r"^\s*you\s+are\s+located\s+in\s+(.+?)\s*[.!?]*$",
    ]
    for pattern in patterns:
        m = re.match(pattern, raw, flags=re.I)
        if m:
            return _normalize_location_preview(m.group(1))
    return ""


def _store_location_fact_reply(
    text: str,
    *,
    input_source: str = "typed",
    pending_action: Optional[dict] = None,
) -> str:
    action = pending_action if isinstance(pending_action, dict) else {}
    if (
        str(action.get("kind") or "") == "weather_lookup"
        and str(action.get("status") or "") == "awaiting_location"
    ):
        return ""

    location_value = _extract_location_fact(text)
    if not location_value:
        return ""

    try:
        set_location_text(location_value, input_source=input_source)
    except Exception:
        return ""
    return "Noted."


def _store_declarative_fact_reply(text: str, *, input_source: str = "typed") -> str:
    outcome = _store_declarative_fact_outcome(text, input_source=input_source)
    if not isinstance(outcome, dict):
        return ""
    return render_reply(outcome)


def _store_declarative_fact_outcome(text: str, *, input_source: str = "typed") -> Optional[dict[str, object]]:
    fact_text = str(text or "").strip()
    if not fact_text or not _is_declarative_info(fact_text):
        return None

    storage_performed = False
    try:
        if mem_should_store(fact_text):
            mem_add("fact", input_source, fact_text)
            storage_performed = True
    except Exception:
        storage_performed = False

    return _classify_store_fact_outcome(
        {
            "fact_text": fact_text,
            "store_fact_kind": "declarative_ack",
            "user_commitment": "implied",
            "memory_kind": "fact",
        },
        fact_text,
        source="declarative",
        storage_performed=storage_performed,
    )


def _is_saved_location_weather_query(text: str) -> bool:
    normalized = _normalize_turn_text(text).strip(" .,!?")
    if not normalized:
        return False
    return normalized in {
        "weather",
        "weather now",
        "weather current",
        "weather today",
        "current weather",
        "what's the weather",
        "what is the weather",
        "what is the weather now",
        "what's the weather now",
    }


def _weather_for_saved_location() -> str:
    saved_location = str(get_saved_location_text() or "").strip()
    if not saved_location:
        return ""
    try:
        return str(tool_weather(saved_location) or "")
    except Exception:
        return ""


def _extract_weather_source_host(tool_result: str) -> str:
    text = str(tool_result or "").strip()
    if not text:
        return ""
    match = re.search(r"\[source:\s*([^\]]+)\]", text, flags=re.I)
    if not match:
        return ""
    return str(match.group(1) or "").strip().lower()


def _weather_location_label(weather_mode: str, location_value: str = "") -> str:
    mode = str(weather_mode or "").strip().lower()
    explicit_value = str(location_value or "").strip()
    if mode == "explicit_location" and explicit_value:
        return explicit_value
    saved_location = str(get_saved_location_text() or "").strip()
    if saved_location:
        return saved_location
    coords = _coords_from_saved_location()
    if coords:
        return f"{coords[0]},{coords[1]}"
    return explicit_value


def _make_weather_result_state(*, weather_mode: str, location_value: str = "", tool_result: str = "") -> dict:
    return _make_conversation_state(
        "weather_result",
        subject="weather",
        weather_mode=str(weather_mode or "").strip().lower(),
        location_value=_weather_location_label(weather_mode, location_value),
        source_host=_extract_weather_source_host(tool_result) or str(_weather_source_host() or "").strip().lower(),
        tool_result=str(tool_result or "").strip(),
    )


def _is_weather_meta_followup(text: str) -> bool:
    normalized = _normalize_turn_text(text)
    if not normalized or "weather" not in normalized:
        return False
    return any(phrase in normalized for phrase in (
        "how did you get the weather",
        "how did you get that weather",
        "how did you get the weather information",
        "where did you get the weather",
        "where did you get that weather",
        "what source did you use for the weather",
        "weather tool",
    ))


def _is_weather_status_followup(text: str) -> bool:
    normalized = _normalize_turn_text(text)
    if not normalized or "weather" not in normalized:
        return False
    return any(phrase in normalized for phrase in (
        "what happened to my weather",
        "what happened to the weather",
        "what happened to that weather",
        "what happened to my weather information",
        "what happened to the weather information",
        "did you get the weather",
        "did you get my weather",
    ))


def _weather_meta_reply(state: dict) -> str:
    source_host = str(state.get("source_host") or "").strip()
    location_value = str(state.get("location_value") or "").strip()
    if source_host and location_value:
        return f"I got that weather information from the weather tool using {source_host} for {location_value}."
    if source_host:
        return f"I got that weather information from the weather tool using {source_host}."
    if location_value:
        return f"I got that weather information from the weather tool for {location_value}."
    return "I got that weather information from the weather tool."


def _weather_status_reply(state: dict) -> str:
    location_value = str(state.get("location_value") or "").strip()
    tool_result = str(state.get("tool_result") or "").strip()
    if tool_result and location_value:
        return f"The last weather lookup I handled was for {location_value}. Result: {tool_result}"
    if tool_result:
        return f"The last weather lookup I handled returned: {tool_result}"
    if location_value:
        return f"The last weather lookup I handled was for {location_value}, but I do not have the final result cached here."
    return "I do not have a completed weather result cached for this thread yet."


def _is_location_recall_query(text: str) -> bool:
    t = (text or "").strip().lower()
    if not t:
        return False
    cues = [
        "where am i",
        "where am i located",
        "what's my location",
        "recall my location",
        "remember my location",
        "what is my location",
        "where is my location",
        "do you know my location",
        "can you recall my location",
        "can you remember my location",
    ]
    return any(c in t for c in cues)


def _location_recall_reply() -> str:
    preview = get_saved_location_text()
    if preview:
        expanded = _LOCATION_HINT_LABELS.get(str(preview or "").strip().lower())
        if expanded and expanded.lower() not in str(preview or "").strip().lower():
            return f"Your saved location is {preview} ({expanded})."
        return f"Your saved location is {preview}."
    return "I don't have a stored location yet. You can tell me: 'My location is ...'"


def _is_location_name_query(text: str) -> bool:
    normalized = _normalize_turn_text(text).strip(" .,!?")
    if not normalized:
        return False
    explicit_cues = [
        "give me the name to that location",
        "give me the name of that location",
        "whats the name of that location",
        "what's the name of that location",
        "what is the name of that location",
        "what location is that",
        "which location is that",
        "what city is that zip",
        "what city is that location",
        "name of that location",
        "name to that location",
    ]
    if any(cue in normalized for cue in explicit_cues):
        return True
    return "location" in normalized and "name" in normalized and _uses_prior_reference(normalized)


def _location_name_reply() -> str:
    preview = get_saved_location_text()
    if not preview:
        return "I don't have a stored location yet. You can tell me: 'My location is ...'"
    expanded = _LOCATION_HINT_LABELS.get(str(preview or "").strip().lower())
    if expanded:
        return f"That location is {expanded}."
    return f"The location I have saved is {preview}."


def _handle_location_conversation_turn(
    state: Optional[dict],
    text: str,
    turns: Optional[list[tuple[str, str]]] = None,
) -> tuple[bool, str, Optional[dict], str]:
    next_state = state if isinstance(state, dict) else _make_conversation_state("location_recall")
    if _is_location_name_query(text):
        return True, _location_name_reply(), next_state, "location_name"
    if _is_location_recall_query(text):
        return True, _location_recall_reply(), _make_conversation_state("location_recall"), "location_recall"
    if _looks_like_contextual_followup(text) and (
        _is_location_recall_state(state) or _looks_like_location_recall_followup(list(turns or []), text)
    ):
        return True, _location_recall_reply(), _make_conversation_state("location_recall"), "location_recall"
    return False, "", next_state, ""


def _make_conversation_state(kind: str, **data) -> dict:
    state = {"kind": str(kind or "").strip()}
    for key, value in data.items():
        state[str(key)] = value
    return state


def _conversation_active_subject(state: Optional[dict]) -> str:
    if not isinstance(state, dict):
        return ""
    kind = str(state.get("kind") or "").strip()
    subject = str(state.get("subject") or "").strip()
    if kind and subject:
        return f"{kind}:{subject}"
    return kind


_TURN_TEXT_TOKEN_FIXES = {
    "yor": "your",
    "hou": "you",
    "locaiton": "location",
    "retreiving": "retrieving",
    "tring": "trying",
    "behing": "behind",
    "teh": "the",
}


_TURN_TEXT_ROUTING_VOCAB = {
    "a", "all", "allowlisted", "am", "and", "answer", "anything", "are", "assistant", "can",
    "chat", "continue", "creator", "current", "data", "developer", "do", "does", "else",
    "fetch", "find", "for", "gather", "grounded", "hello", "help", "hi", "how", "i", "info",
    "information", "is", "it", "kind", "know", "last", "local", "location", "me", "more",
    "name", "next", "not", "nova", "of", "on", "online", "physical", "please", "profile",
    "question", "recap", "remember", "research", "resource", "resources", "result", "results",
    "retrieve", "retrieving", "search", "session", "should", "source", "sources", "sure", "tell",
    "that", "the", "then", "this", "topic", "trying", "tsds", "use", "web", "what", "where",
    "which", "who", "why", "you", "your",
}


def _normalize_turn_token(token: str) -> str:
    core = str(token or "").strip().lower()
    if not core:
        return core
    if core in _TURN_TEXT_TOKEN_FIXES:
        return _TURN_TEXT_TOKEN_FIXES[core]
    if len(core) < 4 or core in _TURN_TEXT_ROUTING_VOCAB:
        return core
    matches = difflib.get_close_matches(core, sorted(_TURN_TEXT_ROUTING_VOCAB), n=1, cutoff=0.89)
    if matches and abs(len(matches[0]) - len(core)) <= 2:
        return matches[0]
    return core


def _normalize_turn_text(text: str) -> str:
    raw = re.sub(r"\s+", " ", (text or "").strip().lower())
    if not raw:
        return ""

    normalized_chunks: list[str] = []
    for chunk in raw.split(" "):
        if not chunk or any(marker in chunk for marker in ("://", "/", "@")):
            normalized_chunks.append(chunk)
            continue
        match = re.match(r"^([^a-z']*)([a-z']+)([^a-z']*)$", chunk)
        if not match:
            normalized_chunks.append(chunk)
            continue
        prefix, core, suffix = match.groups()
        normalized_chunks.append(prefix + _normalize_turn_token(core) + suffix)
    return " ".join(normalized_chunks)


def _looks_like_contextual_followup(text: str) -> bool:
    normalized = _normalize_turn_text(text).strip(" .,!?")
    if not normalized:
        return False
    if normalized in {
        "what did you find",
        "well what did you find",
        "what else",
        "anything else",
        "go on",
        "continue",
        "ok and then",
        "and then",
        "and",
    }:
        return True
    return len(normalized.split()) <= 4 and _uses_prior_reference(normalized)


def _looks_like_contextual_continuation(text: str) -> bool:
    normalized = _normalize_turn_text(text).strip(" .,!?")
    return normalized in {
        "what did you find",
        "well what did you find",
        "what else",
        "anything else",
        "go on",
        "continue",
        "ok and then",
        "and then",
        "and",
    }


def _looks_like_profile_followup(text: str) -> bool:
    normalized = _normalize_turn_text(text).strip(" .,!?")
    if not normalized:
        return False
    if normalized in {
        "what else",
        "anything else",
        "what more",
        "anything more",
        "go on",
        "continue",
        "and then",
        "ok and then",
        "tell me more",
    }:
        return True
    return False


def _is_retrieval_meta_question(text: str) -> bool:
    normalized = _normalize_turn_text(text)
    if not normalized:
        return False
    return any(phrase in normalized for phrase in (
        "what type of resources",
        "what resources are you trying to fetch",
        "what kind of resources",
        "what sources are you trying to fetch",
        "what are you trying to fetch",
    ))


def _retrieval_meta_reply(state: dict) -> str:
    query = str(state.get("query") or "").strip()
    urls = state.get("urls") if isinstance(state.get("urls"), list) else []
    hosts: list[str] = []
    for url in urls:
        host = (urlparse(str(url)).hostname or "").strip().lower()
        if host and host not in hosts:
            hosts.append(host)
    parts = ["I was trying to fetch allowlisted web sources related to your last question"]
    if query:
        parts[0] += f" about '{query}'"
    parts[0] += "."
    if hosts:
        if len(hosts) == 1:
            parts.append(f"Right now the active source host is {hosts[0]}.")
        else:
            parts.append("Right now the active source hosts are " + ", ".join(hosts[:-1]) + f", and {hosts[-1]}.")
    else:
        parts.append("I was looking for grounded web sources rather than local knowledge files.")
    parts.append("If you want, I can gather one of the listed sources or answer the original question directly from the current chat context.")
    return " ".join(parts)


def _non_retrieval_resource_meta_reply() -> str:
    return (
        "I'm not trying to fetch web resources for this question right now. "
        "I should stay with the current chat and the verified facts I already have unless you explicitly ask me to do web research."
    )


def _extract_retrieval_result_index(text: str) -> Optional[int]:
    normalized = _normalize_turn_text(text)
    if not normalized:
        return None

    match = re.search(r"\b(?:result|source|link|item)\s*(\d{1,2})\b", normalized)
    if match:
        try:
            return max(1, int(match.group(1)))
        except Exception:
            return None

    ordinal_map = {
        "first": 1,
        "second": 2,
        "third": 3,
        "fourth": 4,
        "fifth": 5,
    }
    for word, index in ordinal_map.items():
        if re.search(rf"\b{word}\b", normalized):
            return index
    return None


def _looks_like_retrieval_followup(text: str) -> bool:
    normalized = _normalize_turn_text(text).strip(" .,!?")
    if not normalized:
        return False
    if _extract_retrieval_result_index(normalized) is not None:
        return True
    triggers = {
        "what else",
        "anything else",
        "go on",
        "continue",
        "tell me more",
        "more results",
        "another result",
        "another source",
        "next",
        "next result",
        "next source",
        "more sources",
        "and then",
    }
    if normalized in triggers:
        return True
    return any(token in normalized for token in ("more result", "another source", "another result", "next source", "next result"))


def _is_retrieval_tool(tool_name: str) -> bool:
    return str(tool_name or "").strip().lower() in {
        "web_search",
        "web_research",
        "web_gather",
        "web_fetch",
        "search",
        "wikipedia_lookup",
        "stackexchange_search",
    }


def _retrieval_query_from_text(tool_name: str, text: str) -> str:
    raw = str(text or "").strip()
    low = raw.lower()
    tool = str(tool_name or "").strip().lower()

    if tool == "web_research":
        if low in {"web continue", "continue web", "continue web research"}:
            return WEB_RESEARCH_SESSION.query
        if low.startswith("web research "):
            return raw.split(maxsplit=2)[2].strip() if len(raw.split(maxsplit=2)) >= 3 else ""
    if tool == "web_search":
        if low.startswith("web search "):
            return raw.split(maxsplit=2)[2].strip() if len(raw.split(maxsplit=2)) >= 3 else ""
        if low.startswith("findweb ") or low.startswith("search "):
            return raw.split(maxsplit=1)[1].strip() if len(raw.split(maxsplit=1)) >= 2 else ""
    if tool == "web_gather":
        if low.startswith("web gather "):
            return raw.split(maxsplit=2)[2].strip() if len(raw.split(maxsplit=2)) >= 3 else ""
    if tool == "web_fetch":
        if low.startswith("web "):
            return raw.split(maxsplit=1)[1].strip() if len(raw.split(maxsplit=1)) >= 2 else ""
    if tool == "wikipedia_lookup":
        if low.startswith("wikipedia "):
            return raw.split(maxsplit=1)[1].strip() if len(raw.split(maxsplit=1)) >= 2 else ""
        if low.startswith("wiki "):
            return raw.split(maxsplit=1)[1].strip() if len(raw.split(maxsplit=1)) >= 2 else ""
    if tool == "stackexchange_search":
        if low.startswith("stackexchange "):
            return raw[len("stackexchange "):].strip()
        if low.startswith("stack overflow "):
            return raw[len("stack overflow "):].strip()
    return raw


def _provider_name_from_tool(tool_name: str) -> str:
    mapping = {
        "wikipedia_lookup": "wikipedia",
        "stackexchange_search": "stackexchange",
        "web_research": "general_web",
        "web_search": "general_web",
        "web_fetch": "general_web",
        "web_gather": "general_web",
    }
    return str(mapping.get(str(tool_name or "").strip().lower(), "")).strip()


def _make_retrieval_conversation_state(tool_name: str, query: str, tool_output: str) -> Optional[dict]:
    if not _is_retrieval_tool(tool_name):
        return None

    output = str(tool_output or "")
    if not output.strip():
        return None

    urls = _extract_urls(output)[:8]
    result_count = len(urls)
    normalized_tool = str(tool_name or "").strip().lower()
    effective_query = str(query or "").strip()

    if normalized_tool == "web_research":
        if WEB_RESEARCH_SESSION.has_results():
            result_count = WEB_RESEARCH_SESSION.result_count()
        if not effective_query:
            effective_query = WEB_RESEARCH_SESSION.query

    if not urls and normalized_tool not in {"web_research", "web_gather", "web_fetch"}:
        return None

    state = _make_conversation_state(
        "retrieval",
        subject=normalized_tool or "retrieval",
        query=effective_query,
        result_count=max(result_count, 0),
        urls=urls,
    )
    if urls:
        state["top_url"] = urls[0]
    return state


def _load_generated_queue_payload(limit: int = 12) -> dict:
    try:
        import nova_http

        payload = nova_http._generated_work_queue(int(limit or 12))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _make_queue_status_conversation_state(tool_output: str) -> Optional[dict]:
    if not str(tool_output or "").strip():
        return None

    queue = _load_generated_queue_payload(12)
    if not queue:
        return None

    next_item = queue.get("next_item") if isinstance(queue.get("next_item"), dict) else {}
    highest = next_item.get("highest_priority") if isinstance(next_item.get("highest_priority"), dict) else {}
    return _make_conversation_state(
        "queue_status",
        subject="generated_work_queue",
        count=int(queue.get("count", 0) or 0),
        open_count=int(queue.get("open_count", 0) or 0),
        green_count=int(queue.get("green_count", 0) or 0),
        drift_count=int(queue.get("drift_count", 0) or 0),
        warning_count=int(queue.get("warning_count", 0) or 0),
        never_run_count=int(queue.get("never_run_count", 0) or 0),
        next_item=dict(next_item),
        next_file=str(next_item.get("file") or "").strip(),
        next_family=str(next_item.get("family_id") or "").strip(),
        next_status=str(next_item.get("latest_status") or "").strip(),
        next_reason=str(next_item.get("opportunity_reason") or "").strip(),
        next_report_path=str(next_item.get("latest_report_path") or "").strip(),
        next_signal=str(highest.get("signal") or "").strip(),
        next_urgency=str(highest.get("urgency") or "").strip(),
        next_seam=str(highest.get("seam") or "").strip(),
    )


def _make_tool_conversation_state(tool_name: str, query: str, tool_output: str) -> Optional[dict]:
    next_state = _make_retrieval_conversation_state(tool_name, query, tool_output)
    if next_state is not None:
        return next_state
    if str(tool_name or "").strip().lower() == "queue_status":
        return _make_queue_status_conversation_state(tool_output)
    return None


def _infer_post_reply_conversation_state(
    routed_text: str,
    *,
    planner_decision: str,
    tool: str = "",
    tool_args: Optional[dict] = None,
    tool_result: str = "",
    turns: Optional[list[tuple[str, str]]] = None,
    fallback_state: Optional[dict] = None,
) -> Optional[dict]:
    next_state = None
    if planner_decision == "run_tool":
        args_dict = tool_args if isinstance(tool_args, dict) else {}
        action_args = args_dict.get("args") if isinstance(args_dict.get("args"), list) else []
        action_query = str(action_args[0] if action_args else routed_text)
        next_state = _make_tool_conversation_state(tool, action_query, tool_result)
    if next_state is None:
        inferred_profile_state = _infer_profile_conversation_state(routed_text)
        if inferred_profile_state is not None:
            next_state = inferred_profile_state
        elif _is_location_recall_query(routed_text) or _looks_like_location_recall_followup(turns or [], routed_text):
            next_state = _make_conversation_state("location_recall")
    return next_state if isinstance(next_state, dict) else (fallback_state if isinstance(fallback_state, dict) else None)


def _retrieval_followup_reply(state: dict, text: str) -> tuple[str, Optional[dict]]:
    urls = state.get("urls") if isinstance(state.get("urls"), list) else []
    query = str(state.get("query") or "").strip()
    source = str(state.get("subject") or "retrieval").strip().lower()
    result_count = max(0, int(state.get("result_count", 0) or 0))
    index = _extract_retrieval_result_index(text)

    if index is not None and 1 <= index <= len(urls):
        result = tool_web_gather(str(urls[index - 1]))
        return result, (_make_retrieval_conversation_state("web_gather", str(urls[index - 1]), result) or state)

    if source == "web_research" and _looks_like_retrieval_followup(text):
        result = tool_web_research("", continue_mode=True)
        if result and not result.lower().startswith("no active web research session"):
            return result, (_make_retrieval_conversation_state("web_research", WEB_RESEARCH_SESSION.query, result) or state)

    parts = []
    if query:
        parts.append(f"Continuing from your last retrieval for '{query}'.")
    else:
        parts.append("Continuing from your last retrieval thread.")
    if result_count > 0:
        parts.append(f"I have {result_count} source(s) in the current retrieval context.")
    if urls:
        parts.append("You can ask me about the first result, the second source, or tell me to gather one directly.")
    else:
        parts.append("If you want, I can run a more specific search or gather a particular source.")
    return " ".join(parts), state


def _is_queue_status_reason_followup(text: str) -> bool:
    normalized = _normalize_turn_text(text).strip(" .,!?")
    if not normalized:
        return False
    return any(
        phrase in normalized
        for phrase in (
            "why is that the next item in the queue",
            "why is that next in the queue",
            "why is that next",
            "why is that the next item",
            "why is that next item",
            "why that item",
            "why this item",
        )
    )


def _queue_status_reason_reply(state: dict) -> str:
    next_file = str(state.get("next_file") or "").strip()
    next_status = str(state.get("next_status") or "unknown").strip() or "unknown"
    next_reason = str(state.get("next_reason") or "unknown").strip() or "unknown"
    next_signal = str(state.get("next_signal") or "").strip()
    next_urgency = str(state.get("next_urgency") or "").strip()
    next_seam = str(state.get("next_seam") or "").strip()
    next_family = str(state.get("next_family") or "").strip()

    if not next_file:
        return "There is no next open queue item right now because the generated work queue is clear."

    parts = [f"{next_file} is next because it is still open with status {next_status} and reason {next_reason}."]
    if next_signal:
        signal_text = f"Its highest-priority signal is {next_signal}"
        if next_urgency:
            signal_text += f" at {next_urgency} urgency"
        if next_seam:
            signal_text += f" on seam {next_seam}"
        parts.append(signal_text + ".")
    if next_family:
        parts.append(f"It currently leads the {next_family} family among open generated queue items.")
    return " ".join(parts)


def _is_queue_status_report_followup(text: str) -> bool:
    normalized = _normalize_turn_text(text).strip(" .,!?")
    if not normalized:
        return False
    return any(
        phrase in normalized
        for phrase in (
            "show me the report path",
            "what is the report path",
            "where is the report",
            "where is the latest report",
            "show me the latest report",
        )
    )


def _queue_status_report_reply(state: dict) -> str:
    next_file = str(state.get("next_file") or "").strip()
    report_path = str(state.get("next_report_path") or "").strip()
    if not report_path:
        if next_file:
            return f"I don't have a saved report path yet for {next_file}."
        return "I don't have a saved report path because there is no current open queue item."
    if next_file:
        return f"The latest report for {next_file} is at {report_path}"
    return f"The latest queue report path is {report_path}"


def _is_queue_status_seam_followup(text: str) -> bool:
    normalized = _normalize_turn_text(text).strip(" .,!?")
    if not normalized:
        return False
    return any(
        phrase in normalized
        for phrase in (
            "what seam is it failing on",
            "what seam is it on",
            "which seam is failing",
            "what seam",
        )
    )


def _queue_status_seam_reply(state: dict) -> str:
    next_file = str(state.get("next_file") or "").strip()
    next_seam = str(state.get("next_seam") or "").strip()
    next_signal = str(state.get("next_signal") or "").strip()
    if not next_seam:
        if next_file:
            return f"I don't have a recorded seam yet for {next_file}."
        return "I don't have a recorded seam because there is no current open queue item."
    if next_signal:
        return f"{next_file or 'That queue item'} is currently failing on seam {next_seam} with signal {next_signal}."
    return f"{next_file or 'That queue item'} is currently failing on seam {next_seam}."


def _is_location_recall_state(state: Optional[dict]) -> bool:
    return isinstance(state, dict) and str(state.get("kind") or "") == "location_recall"


def _looks_like_location_recall_followup(session_turns: list[tuple[str, str]], text: str) -> bool:
    if _looks_like_contextual_continuation(text):
        recent = session_turns[-6:] if isinstance(session_turns, list) else []
        for role, content in reversed(recent):
            low = str(content or "").strip().lower()
            if not low:
                continue
            if low.startswith("your saved location is") or low.startswith("i don't have a stored location yet"):
                return True
    t = re.sub(r"\s+", " ", (text or "").strip().lower())
    t = re.sub(r"\s*\?+$", "", t).strip()
    if t not in {"what did you find", "well what did you find"}:
        return False
    recent = session_turns[-6:] if isinstance(session_turns, list) else []
    for role, content in reversed(recent):
        low = str(content or "").strip().lower()
        if not low:
            continue
        if "location" in low and any(cue in low for cue in ("recall", "remember", "saved", "stored", "current physical location")):
            return True
        if low.startswith("your saved location is") or low.startswith("i don't have a stored location yet"):
            return True
    return False


def _retrieval_status_reply(text: str) -> str:
    t = (text or "").strip().lower()
    if t in {"retrieving data", "retreiving data", "retrieving info", "retrieving information"}:
        return "What data do you want me to retrieve?"
    return ""


def _is_web_research_override_request(text: str) -> bool:
    low = _normalize_turn_text(text)
    if not low:
        return False
    phrases = (
        "just use the web",
        "use the web for this",
        "only need web",
        "all you need is the web",
        "all you need is web",
        "need is the web",
        "no database",
        "dont use the database",
        "don't use the database",
        "use web instead",
        "search online instead",
    )
    return any(phrase in low for phrase in phrases)


def set_location_coords(value: str) -> str:
    parsed = _parse_lat_lon(value)
    if not parsed:
        return "Usage: location coords <lat,lon>"
    lat, lon = parsed
    try:
        set_core_state(DEFAULT_STATEFILE, "location_coords", {"lat": lat, "lon": lon})
    except Exception:
        return "Failed to save current location coordinates."
    return f"Saved current location coordinates: {lat},{lon}"


def get_weather_for_location(lat: float, lon: float) -> str:
    headers = {
        "User-Agent": "Nova/1.0 (local assistant)",
        "Accept": "application/geo+json",
    }

    point_url = f"https://api.weather.gov/points/{lat},{lon}"
    r1 = requests.get(point_url, headers=headers, timeout=20)
    r1.raise_for_status()
    point_data = r1.json()
    forecast_url = ((point_data.get("properties") or {}).get("forecast") or "").strip()
    if not forecast_url:
        return "I reached the weather service, but no forecast URL was returned for that location."

    r2 = requests.get(forecast_url, headers=headers, timeout=20)
    r2.raise_for_status()
    forecast_data = r2.json()

    periods = ((forecast_data.get("properties") or {}).get("periods") or [])
    if not periods:
        return "I reached the weather service, but no forecast periods were returned."

    now = periods[0]
    return (
        f"{now.get('name', 'Current')}: {now.get('temperature', '?')}°{now.get('temperatureUnit', 'F')}, "
        f"{now.get('shortForecast', 'unknown')}. Wind {now.get('windSpeed', '?')} {now.get('windDirection', '?')}. "
        f"[source: api.weather.gov]"
    )


def _need_confirmed_location_message() -> str:
    return "I have a weather tool now, but I still need a confirmed location or coordinates for the current device."


def tool_weather(location: str) -> str:
    if not policy_tools_enabled().get("web", False) or not web_enabled():
        return "Weather lookup unavailable: web tool is disabled by policy."

    source = _weather_source_host()
    if not source:
        return _weather_unavailable_message()

    loc = (location or "").strip()

    if source == "api.weather.gov":
        coords = _coords_for_location_hint(loc)
        if not coords:
            return _need_confirmed_location_message()
        lat, lon = coords
        try:
            summary = get_weather_for_location(lat, lon)
            label = loc if loc else f"{lat},{lon}"
            return _format_weather_output(label, summary)
        except Exception as e:
            return f"Weather lookup failed: {e}"

    if not loc:
        return "Usage: weather <location-or-lat,lon>"

    if source == "wttr.in":
        url = f"https://wttr.in/{quote(loc)}?format=j1"
        try:
            r = requests.get(url, headers={"User-Agent": "Nova/1.0"}, timeout=25)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            return f"Weather lookup failed: {e}"

        try:
            cur = ((data.get("current_condition") or [{}])[0])
            desc = (((cur.get("weatherDesc") or [{}])[0]).get("value") or "unknown").strip()
            temp_f = (cur.get("temp_F") or "?").strip()
            feels_f = (cur.get("FeelsLikeF") or "?").strip()
            humidity = (cur.get("humidity") or "?").strip()
            wind_mph = (cur.get("windspeedMiles") or "?").strip()

            return _format_weather_output(
                loc,
                f"{desc}, {temp_f}F (feels like {feels_f}F), humidity {humidity}%, wind {wind_mph} mph. [source: wttr.in]",
            )
        except Exception:
            return "Weather lookup succeeded but returned an unexpected payload format."

    return _need_confirmed_location_message()

def allowed_root() -> Path:
    p = load_policy()
    return Path(p["allowed_root"]).resolve()


def chat_model() -> str:
    m = policy_models()
    return m.get("chat", "llama3.1:8b")


def whisper_size() -> str:
    m = policy_models()
    return m.get("stt_size", "small")


# =========================
# Guard/Core liveness contract
# =========================
DEFAULT_HEARTBEAT = RUNTIME_DIR / "core.heartbeat"
DEFAULT_STATEFILE = RUNTIME_DIR / "core_state.json"


def atomic_write_json(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def touch(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(time.time()), encoding="utf-8")


def write_core_identity(statefile: Path):
    pid = os.getpid()
    ct = psutil.Process(pid).create_time()
    atomic_write_json(statefile, {
        "pid": int(pid),
        "create_time": float(ct),
        "ts": time.time(),
        "note": "canonical (written by core)"
    })


def read_core_state(statefile: Path) -> dict:
    try:
        if not statefile.exists():
            return {}
        return json.loads(statefile.read_text(encoding="utf-8") or "{}")
    except Exception:
        return {}


def set_core_state(statefile: Path, key: str, value) -> None:
    try:
        st = read_core_state(statefile)
        st[key] = value
        atomic_write_json(statefile, st)
    except Exception:
        pass


def start_heartbeat(heartbeat_file: Path, interval_sec: float = 1.0):
    stop_evt = threading.Event()

    def _loop():
        while not stop_evt.is_set():
            try:
                touch(heartbeat_file)
            except Exception:
                pass
            stop_evt.wait(interval_sec)

    t = threading.Thread(target=_loop, name="core-heartbeat", daemon=True)
    t.start()
    return stop_evt


# =========================
# Subprocess TTS (Piper oneshot)
# =========================
class SubprocessTTS:
    """Piper oneshot wrapper: python tts_piper.py "text"""

    def __init__(self, python_exe: str, oneshot_script: Path, timeout_sec: float = 25.0):
        self.python_exe = python_exe
        self.oneshot_script = oneshot_script
        self.timeout_sec = float(timeout_sec)
        self.q = queue.Queue()
        self.stop_evt = threading.Event()
        self.t = threading.Thread(target=self._run, name="tts-worker", daemon=True)

    def start(self):
        self.t.start()

    def stop(self):
        self.stop_evt.set()
        self.q.put(None)

    def say(self, text: str):
        if text:
            self.q.put(str(text))

    def _run(self):
        while not self.stop_evt.is_set():
            item = self.q.get()
            if item is None:
                break

            try:
                creationflags = 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW
                p = subprocess.Popen(
                    [self.python_exe, str(self.oneshot_script), item],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    creationflags=creationflags,
                )
                try:
                    _, err = p.communicate(timeout=self.timeout_sec)
                except subprocess.TimeoutExpired:
                    p.kill()
                    warn("TTS timed out; killed piper subprocess.")
                    continue

                if p.returncode != 0:
                    msg = (err or b"").decode("utf-8", errors="ignore").strip()
                    warn(f"TTS failed rc={p.returncode}: {msg}")

            except Exception as e:
                warn(f"TTS error: {e}")


def speak_chunked(tts: SubprocessTTS, text: str, max_len: int = 220):
    text = (text or "").strip()
    if not text:
        return
    parts = re.split(r'(?<=[.!?])\s+', text)
    buf = ""
    for p in parts:
        if len(buf) + len(p) + 1 <= max_len:
            buf = (buf + " " + p).strip()
        else:
            if buf:
                tts.say(buf)
            buf = p.strip()
    if buf:
        tts.say(buf)


# =========================
# Memory hooks (optional)
# =========================
def mem_enabled() -> bool:
    return _memory_adapter_service().mem_enabled()


def mem_top_k() -> int:
    return _memory_adapter_service().mem_top_k()


def mem_scope() -> str:
    return _memory_adapter_service().mem_scope()


def mem_context_top_k() -> int:
    return _memory_adapter_service().mem_context_top_k()


def mem_min_score() -> float:
    return _memory_adapter_service().mem_min_score()


def mem_exclude_sources() -> list[str]:
    return _memory_adapter_service().mem_exclude_sources()


def mem_store_min_chars() -> int:
    return _memory_adapter_service().mem_store_min_chars()


def mem_store_exclude_patterns() -> list[str]:
    return _memory_adapter_service().mem_store_exclude_patterns()


def mem_store_include_patterns() -> list[str]:
    return _memory_adapter_service().mem_store_include_patterns()


def _default_local_user_id() -> str:
    return _memory_adapter_service().default_local_user_id()


def _memory_write_user() -> str | None:
    scope = mem_scope()
    active_user = (get_active_user() or "").strip()
    if scope == "shared":
        return ""
    if active_user:
        return active_user
    if scope == "hybrid":
        return ""
    fallback_user = _default_local_user_id()
    return fallback_user or None


def _memory_should_keep_text(text: str) -> tuple[bool, str]:
    return _memory_adapter_service().memory_should_keep_text(text)


def mem_should_store(text: str) -> bool:
    return _memory_adapter_service().mem_should_store(text)


def _memory_runtime_user() -> str | None:
    user = (get_active_user() or "").strip()
    if mem_scope() == "private" and not user:
        user = _default_local_user_id()
    if mem_scope() == "private" and not user:
        return None
    return user or None


def _format_memory_recall_hits(hits) -> str:
    return _memory_adapter_service().format_memory_recall_hits(hits)


def mem_stats_payload(emit_event: bool = True) -> dict:
    if not mem_enabled() or memory_mod is None:
        return {"ok": False, "error": "memory_disabled"}
    started = time.time()
    try:
        user = _memory_runtime_user()
        data = memory_mod.stats(scope=mem_scope(), user=user)
        if isinstance(data, dict):
            out = dict(data)
            out["ok"] = True
            if emit_event:
                _record_memory_event(
                    "stats",
                    "ok",
                    user=user,
                    scope=mem_scope(),
                    backend="in_process",
                    result_count=int(out.get("total", 0) or 0),
                    duration_ms=int((time.time() - started) * 1000),
                )
            return out
        if emit_event:
            _record_memory_event(
                "stats",
                "error",
                user=user,
                scope=mem_scope(),
                backend="in_process",
                error="invalid_memory_stats",
                duration_ms=int((time.time() - started) * 1000),
            )
        return {"ok": False, "error": "invalid_memory_stats"}
    except Exception as e:
        if emit_event:
            _record_memory_event(
                "stats",
                "error",
                user=_memory_runtime_user(),
                scope=mem_scope(),
                backend="in_process",
                error=str(e),
                duration_ms=int((time.time() - started) * 1000),
            )
        return {"ok": False, "error": str(e)}


def mem_add(kind: str, source: str, text: str):
    if not mem_enabled():
        return
    started = time.time()
    try:
        if not _identity_memory_text_allowed(kind, text):
            _record_memory_event(
                "add",
                "skipped",
                scope=mem_scope(),
                kind=kind,
                source=source,
                reason="identity_only_mode",
                duration_ms=int((time.time() - started) * 1000),
            )
            return
        # Avoid storing assistant outputs and obvious questions
        if source and str(source).lower() in {"assistant", "nova"}:
            _record_memory_event(
                "add",
                "skipped",
                scope=mem_scope(),
                kind=kind,
                source=source,
                reason="assistant_source",
                duration_ms=int((time.time() - started) * 1000),
            )
            return
        bypass_filter = str(kind or "").strip().lower() == "test" or str(source or "").strip().lower() in {"test", "unittest"}
        keep, _reason = _memory_should_keep_text(text)
        if bypass_filter:
            keep, _reason = True, "test_bypass"
        if not keep:
            _record_memory_event(
                "add",
                "skipped",
                scope=mem_scope(),
                kind=kind,
                source=source,
                reason=_reason or "filtered_text",
                duration_ms=int((time.time() - started) * 1000),
            )
            return

        # Duplicate check: run memory audit for same user and skip if near-duplicate exists
        user = _memory_write_user()
        if user is None:
            _record_memory_event(
                "add",
                "skipped",
                scope=mem_scope(),
                kind=kind,
                source=source,
                reason="missing_user",
                duration_ms=int((time.time() - started) * 1000),
            )
            return
        if memory_mod is not None:
            try:
                j = memory_mod.recall_explain(
                    text,
                    top_k=1,
                    min_score=mem_min_score(),
                    user=user,
                    scope=mem_scope(),
                )
                res = (j or {}).get("results") or []
                if res:
                    top = res[0]
                    score = float(top.get("score") or 0.0)
                    preview = (top.get("preview") or "").strip()
                    def _norm(s: str) -> str:
                        return re.sub(r"\W+", " ", (s or "").lower()).strip()
                    if score >= 0.85 or _norm(preview) == _norm(text):
                        _record_memory_event(
                            "add",
                            "skipped",
                            user=user,
                            scope=mem_scope(),
                            backend="in_process",
                            kind=kind,
                            source=source,
                            reason="duplicate",
                            result_count=len(res),
                            duration_ms=int((time.time() - started) * 1000),
                        )
                        return
                memory_mod.add_memory(kind, source, text, user=user or "", scope=mem_scope())
                _record_memory_event(
                    "add",
                    "ok",
                    user=user,
                    scope=mem_scope(),
                    backend="in_process",
                    kind=kind,
                    source=source,
                    duration_ms=int((time.time() - started) * 1000),
                )
                return
            except Exception:
                pass

        cmd = [PYTHON, str(BASE_DIR / "memory.py"), "add", "--kind", kind, "--source", source, "--text", text]
        cmd += ["--scope", mem_scope()]
        if user:
            cmd += ["--user", str(user)]
        subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
        _record_memory_event(
            "add",
            "ok",
            user=user,
            scope=mem_scope(),
            backend="subprocess",
            kind=kind,
            source=source,
            duration_ms=int((time.time() - started) * 1000),
        )
    except Exception:
        _record_memory_event(
            "add",
            "error",
            user=_memory_write_user() or _memory_runtime_user(),
            scope=mem_scope(),
            kind=kind,
            source=source,
            error="mem_add_failed",
            duration_ms=int((time.time() - started) * 1000),
        )


def mem_recall(query: str) -> str:
    if not mem_enabled():
        return ""

    if len((query or "").strip()) < 8:
        return ""

    started = time.time()
    try:
        user = _memory_runtime_user()
        if memory_mod is not None:
            hits = memory_mod.recall(
                query,
                top_k=mem_context_top_k(),
                min_score=mem_min_score(),
                exclude_sources=mem_exclude_sources(),
                user=user,
                scope=mem_scope(),
            )
            out = _format_memory_recall_hits(hits)
            _record_memory_event(
                "recall",
                "ok",
                user=user,
                scope=mem_scope(),
                backend="in_process",
                query=query,
                result_count=len(hits or []),
                duration_ms=int((time.time() - started) * 1000),
            )
            return out

        cmd = [
            PYTHON, str(BASE_DIR / "memory.py"), "recall",
            "--query", query,
            "--topk", str(mem_context_top_k()),
            "--minscore", str(mem_min_score()),
            "--scope", mem_scope(),
        ]
        if user:
            cmd += ["--user", str(user)]
        for s in mem_exclude_sources():
            cmd += ["--exclude-source", s]

        r = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
        out = (r.stdout or "").strip()
        if not out or "No memories" in out:
            _record_memory_event(
                "recall",
                "ok",
                user=user,
                scope=mem_scope(),
                backend="subprocess",
                query=query,
                result_count=0,
                duration_ms=int((time.time() - started) * 1000),
            )
            return ""
        parts = re.split(r"\n--- score=.*?---\n", "\n" + out + "\n")
        parsed = [(0.0, 0, "", "", "", p.strip()) for p in parts if (p or "").strip()]
        rendered = _format_memory_recall_hits(parsed)
        _record_memory_event(
            "recall",
            "ok",
            user=user,
            scope=mem_scope(),
            backend="subprocess",
            query=query,
            result_count=len(parsed),
            duration_ms=int((time.time() - started) * 1000),
        )
        return rendered
    except Exception:
        _record_memory_event(
            "recall",
            "error",
            user=_memory_runtime_user(),
            scope=mem_scope(),
            query=query,
            error="mem_recall_failed",
            duration_ms=int((time.time() - started) * 1000),
        )
        return ""


def _prefix_from_earlier_memory(reply_text: str) -> str:
    reply = str(reply_text or "").strip()
    if not reply:
        return reply
    if reply.lower().startswith("from earlier memory:"):
        return reply
    return f"From earlier memory: {reply}"


def _normalize_recent_learning_item(kind: str, text: str) -> str:
    raw_kind = str(kind or "").strip().lower()
    raw_text = str(text or "").strip()
    if not raw_text:
        return ""

    if raw_kind == "user_correction":
        try:
            payload = json.loads(raw_text)
        except Exception:
            payload = {}
        parsed = str(payload.get("parsed_correction") or "").strip()
        correction_text = str(payload.get("text") or raw_text).strip()
        value = parsed or correction_text
        return f"Correction: {value}" if value else ""

    clean = raw_text
    if raw_kind == "identity" and clean.lower().startswith("learned_fact:"):
        clean = clean.split(":", 1)[1].strip()
    if raw_kind in {"user_fact", "fact", "identity", "profile"}:
        return clean
    return ""


def mem_get_recent_learned(limit: int = 5) -> list[str]:
    requested = max(1, int(limit or 5))
    items: list[str] = []
    seen: set[str] = set()

    if mem_enabled() and memory_mod is not None:
        con = None
        try:
            con = memory_mod.connect()
            rows = memory_mod.select_memory_rows(con, _memory_runtime_user(), mem_scope())
            for _ts, kind, source, _user_row, text, _vec in rows:
                source_name = str(source or "").strip().lower()
                kind_name = str(kind or "").strip().lower()
                if source_name in {"assistant", "nova", "pinned"}:
                    continue
                if kind_name not in {"user_correction", "user_fact", "fact", "identity", "profile"}:
                    continue
                item = _normalize_recent_learning_item(kind_name, text)
                if not item:
                    continue
                dedupe_key = re.sub(r"\s+", " ", item).strip().lower()
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                items.append(item)
                if len(items) >= requested:
                    return items
        except Exception:
            pass
        finally:
            if con is not None:
                try:
                    con.close()
                except Exception:
                    pass

    learned = load_learned_facts()
    fallback_pairs = [
        ("assistant_name", "Assistant name"),
        ("developer_name", "Developer name"),
        ("developer_nickname", "Developer nickname"),
    ]
    for key, label in fallback_pairs:
        value = str(learned.get(key) or "").strip()
        if not value:
            continue
        item = f"{label}: {value}"
        dedupe_key = item.lower()
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        items.append(item)
        if len(items) >= requested:
            break
    return items[:requested]


def mem_stats() -> str:
    try:
        payload = mem_stats_payload()
        if payload.get("ok"):
            return json.dumps(payload, indent=2)
        if memory_mod is not None:
            return "No memory stats available."
        r = subprocess.run(
            [PYTHON, str(BASE_DIR / "memory.py"), "stats"],
            capture_output=True, text=True, timeout=1800
        )
        out = (r.stdout or "").strip()
        return out or "No memory stats available."
    except Exception as e:
        return f"Memory stats failed: {e}"


def mem_audit(query: str) -> str:
    q = (query or "").strip()
    if not q:
        return "Usage: mem audit <query>"
    started = time.time()
    try:
        user = _memory_runtime_user()
        if memory_mod is not None:
            out = memory_mod.recall_explain(
                q,
                top_k=mem_context_top_k(),
                min_score=mem_min_score(),
                exclude_sources=mem_exclude_sources(),
                user=user,
                scope=mem_scope(),
            )
            result_count = len((out or {}).get("results") or []) if isinstance(out, dict) else 0
            _record_memory_event(
                "audit",
                "ok",
                user=user,
                scope=mem_scope(),
                backend="in_process",
                query=q,
                result_count=result_count,
                mode=str((out or {}).get("mode") or "") if isinstance(out, dict) else "",
                duration_ms=int((time.time() - started) * 1000),
            )
            return json.dumps(out, indent=2)

        cmd = [
            PYTHON, str(BASE_DIR / "memory.py"), "audit",
            "--query", q,
            "--topk", str(mem_context_top_k()),
            "--minscore", str(mem_min_score()),
            "--scope", mem_scope(),
        ]
        if user:
            cmd += ["--user", str(user)]
        for s in mem_exclude_sources():
            cmd += ["--exclude-source", s]

        r = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
        out = (r.stdout or "").strip()
        _record_memory_event(
            "audit",
            "ok",
            user=user,
            scope=mem_scope(),
            backend="subprocess",
            query=q,
            duration_ms=int((time.time() - started) * 1000),
        )
        return out or "No memory audit output."
    except Exception as e:
        _record_memory_event(
            "audit",
            "error",
            user=_memory_runtime_user(),
            scope=mem_scope(),
            query=q,
            error=str(e),
            duration_ms=int((time.time() - started) * 1000),
        )
        return f"Memory audit failed: {e}"


def mem_remember_fact(text: str) -> str:
    fact = (text or "").strip().strip("\"'")
    if not fact:
        return "Usage: remember: <fact>"
    if not mem_enabled():
        return "Memory is disabled in policy."
    if len(fact) < 3:
        return "Fact is too short to store."

    mem_add("fact", "pinned", fact)
    return f"Pinned memory saved: {fact}"


def load_identity_profile() -> dict:
    try:
        if not IDENTITY_FILE.exists():
            return {}
        data = json.loads(IDENTITY_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_identity_profile(data: dict) -> None:
    try:
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        tmp = IDENTITY_FILE.with_suffix(".json.tmp")
        payload = json.dumps(data, ensure_ascii=True, indent=2)
        tmp.write_text(payload, encoding="utf-8")
        tmp.replace(IDENTITY_FILE)
    except Exception:
        pass


def _looks_invalid_person_token(value: str) -> bool:
    low = str(value or "").strip().lower()
    if not low:
        return True
    invalid = {
        "your",
        "yours",
        "you",
        "me",
        "my",
        "i",
        "nova",
        "nova's",
        "creator",
        "developer",
        "the same person",
        "same person",
    }
    return low in invalid


def _sanitize_learned_facts(data: dict) -> dict:
    facts = dict(data or {})
    developer_name = str(facts.get("developer_name") or "").strip()
    developer_nickname = str(facts.get("developer_nickname") or "").strip()

    if developer_name and _looks_invalid_person_token(developer_name):
        facts.pop("developer_name", None)
        developer_name = ""

    if developer_nickname and _looks_invalid_person_token(developer_nickname):
        facts.pop("developer_nickname", None)

    return facts


def load_learned_facts() -> dict:
    try:
        if not LEARNED_FACTS_FILE.exists():
            return {}
        data = json.loads(LEARNED_FACTS_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {}
        sanitized = _sanitize_learned_facts(data)
        if sanitized != data:
            save_learned_facts(sanitized)
        return sanitized
    except Exception:
        return {}


def save_learned_facts(data: dict) -> None:
    try:
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        tmp = LEARNED_FACTS_FILE.with_suffix(".json.tmp")
        payload = json.dumps(_sanitize_learned_facts(data), ensure_ascii=True, indent=2)
        tmp.write_text(payload, encoding="utf-8")
        tmp.replace(LEARNED_FACTS_FILE)
    except Exception:
        pass


def _clean_fact_value(raw: str, max_words: int = 4) -> str:
    t = re.sub(r"\s+", " ", (raw or "").strip()).strip(" .,:;!?\"'")
    if not t:
        return ""
    words = t.split()
    t = " ".join(words[:max_words])
    return t[:80]


def _title_name(s: str) -> str:
    out = _clean_fact_value(s)
    if not out:
        return ""
    return " ".join(w[:1].upper() + w[1:] for w in out.split())


def learn_from_user_correction(text: str) -> tuple[bool, str]:
    low = (text or "").strip().lower()
    if not low:
        return False, ""
    normalized_low = re.sub(r"\byes\s+iam\b", "yes i am", low)
    normalized_low = re.sub(r"\biam\b", "i am", normalized_low)
    low = normalized_low

    facts = load_learned_facts()
    changed = []

    m_assistant = re.search(r"\b(?:your name is|you are called|you're called)\s+([a-z][a-z '\-]{1,40})", low)
    if m_assistant:
        assistant_name = _title_name(m_assistant.group(1))
        if assistant_name:
            if facts.get("assistant_name") != assistant_name:
                facts["assistant_name"] = assistant_name
                changed.append(f"assistant_name={assistant_name}")

    # Accept quoted assistant self-reference only in explicit correction context.
    if not m_assistant and "your name" in low:
        m_assistant_quoted = re.search(r"\bmy name is\s+([a-z][a-z '\-]{1,40})", low)
        if m_assistant_quoted:
            assistant_name = _title_name(m_assistant_quoted.group(1))
            if assistant_name:
                if facts.get("assistant_name") != assistant_name:
                    facts["assistant_name"] = assistant_name
                    changed.append(f"assistant_name={assistant_name}")

    m_dev = re.search(
        r"\b(?:developer(?:'s)? name is|develper(?:'s)? name is|his full name is|developer(?:'s)? full name is|develper(?:'s)? full name is|creator(?:'s)? full name is)\s+([a-z][a-z '\-]{1,60}(?:\s+(?:jr|sr|ii|iii|iv))?)",
        low,
    )
    if m_dev:
        developer_name = _title_name(m_dev.group(1))
        if developer_name:
            if facts.get("developer_name") != developer_name:
                facts["developer_name"] = developer_name
                changed.append(f"developer_name={developer_name}")

    m_nick = re.search(r"\b(?:nick\s*name is|nickname is)\s+([a-z][a-z '\-]{1,40})", low)
    if m_nick:
        nickname = _title_name(m_nick.group(1))
        if nickname:
            if facts.get("developer_nickname") != nickname:
                facts["developer_nickname"] = nickname
                changed.append(f"developer_nickname={nickname}")

    m_self_creator = re.search(
        r"\bi am\s+([a-z][a-z '\-]{1,60}?)(?=\s+(?:the\s+)?(?:creator|developer)\b)(?:\s*,)?\s+(?:the\s+)?(?:creator|developer)(?:\s+and\s+(?:creator|developer))?(?:\s+of\s+nova)?\b",
        low,
    )
    self_creator_bound = False
    if m_self_creator:
        person_name = _title_name(m_self_creator.group(1))
        low_person_name = (person_name or "").strip().lower()
        invalid_person_markers = {
            "your",
            "yours",
            "nova's",
            "nova",
            "the same person",
            "same person",
        }
        if low_person_name in invalid_person_markers or low_person_name.startswith("the same person"):
            person_name = ""
        if person_name:
            name_parts = person_name.split()
            if len(name_parts) >= 2:
                if facts.get("developer_name") != person_name:
                    facts["developer_name"] = person_name
                    changed.append(f"developer_name={person_name}")
                nickname = facts.get("developer_nickname") or name_parts[0]
                nickname = _title_name(str(nickname))
                if nickname and facts.get("developer_nickname") != nickname:
                    facts["developer_nickname"] = nickname
                    changed.append(f"developer_nickname={nickname}")
                set_active_user(person_name)
                self_creator_bound = True
            else:
                if facts.get("developer_nickname") != person_name:
                    facts["developer_nickname"] = person_name
                    changed.append(f"developer_nickname={person_name}")
                set_active_user(person_name)
                self_creator_bound = True

    if not self_creator_bound:
        implied_creator = bool(re.search(r"\bi am\s+(?:your|nova'?s)\s+(?:creator|developer)\b", low))
        same_person_creator = (
            "same person" in low
            and any(k in low for k in ["developer", "creator"])
        )
        if implied_creator or same_person_creator:
            developer_name = str(facts.get("developer_name") or get_learned_fact("developer_name", "Gustavo Uribe")).strip()
            developer_nickname = str(facts.get("developer_nickname") or get_learned_fact("developer_nickname", "Gus")).strip()
            bind_name = developer_name or developer_nickname
            if bind_name:
                set_active_user(bind_name)
                if developer_nickname and developer_name and facts.get("developer_nickname") != developer_nickname:
                    facts["developer_nickname"] = developer_nickname
                if developer_name and facts.get("developer_name") != developer_name:
                    facts["developer_name"] = developer_name
                if "identity_binding=developer" not in changed:
                    changed.append("identity_binding=developer")

    if not changed:
        return False, ""

    facts["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    save_learned_facts(facts)

    try:
        if mem_enabled():
            for ch in changed:
                mem_add("identity", "typed", f"learned_fact: {ch}")
    except Exception:
        pass

    return True, "Understood. I learned: " + ", ".join(changed) + "."


def get_learned_fact(key: str, default: str = "") -> str:
    data = load_learned_facts()
    v = str(data.get(key) or "").strip()
    return v or default


def _speaker_matches_developer() -> bool:
    active_user = (get_active_user() or "").strip().lower()
    if not active_user:
        return False
    developer_name = get_learned_fact("developer_name", "Gustavo Uribe").strip().lower()
    developer_nickname = get_learned_fact("developer_nickname", "Gus").strip().lower()
    developer_first = developer_name.split()[0] if developer_name else ""
    return active_user in {developer_name, developer_nickname, developer_first}


def _learn_self_identity_binding(text: str) -> tuple[bool, str]:
    raw = (text or "").strip()
    low = raw.lower()
    if not raw:
        return False, ""

    m = re.match(r"^i\s+am\s+([a-z][a-z '\-]{1,40})[.!?]*$", low)
    if not m:
        return False, ""

    person_name = _title_name(m.group(1))
    if not person_name or _looks_invalid_person_token(person_name):
        return False, ""

    developer_name = get_learned_fact("developer_name", "Gustavo Uribe")
    developer_nickname = get_learned_fact("developer_nickname", "Gus")
    developer_first = developer_name.split()[0] if developer_name else ""

    if person_name.lower() in {developer_nickname.lower(), developer_first.lower()}:
        set_active_user(developer_name or person_name)
        return True, "Understood. Identity confirmed: you are my developer."

    if person_name.lower() == developer_name.lower():
        set_active_user(person_name)
        return True, "Understood. Identity confirmed: you are my developer."

    return False, ""


def _learn_contextual_self_facts(text: str, input_source: str = "typed") -> tuple[bool, str]:
    raw = (text or "").strip()
    low = raw.lower()
    if not raw:
        return False, ""

    learned: list[str] = []
    if _speaker_matches_developer():
        color_match = re.search(r"\bmy\s+fav(?:ou?rite|ortie)\s+colors?\s+are\s+(.+)$", raw, flags=re.I)
        if color_match and mem_enabled():
            colors = _extract_color_preferences_from_text(color_match.group(1))
            if colors:
                pretty = ", ".join(colors[:-1]) + (f", and {colors[-1]}" if len(colors) > 1 else colors[0])
                mem_add("identity", input_source, f"Gus favorite colors are {pretty}.")
                learned.append(f"Gus favorite colors are {pretty}")

    if not learned:
        return False, ""
    return True, "Understood. I learned: " + "; ".join(learned) + "."


def remember_name_origin(story_text: str) -> str:
    story = re.sub(r"\s+", " ", (story_text or "").strip())
    if len(story) < 30:
        return "Please provide a longer origin story so I can store it accurately."

    profile = load_identity_profile()
    profile["name_origin"] = story
    profile["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    save_identity_profile(profile)

    if mem_enabled():
        try:
            mem_add("identity", "typed", f"nova_name_origin: {story[:1400]}")
        except Exception:
            pass

    return "Stored. I will remember this as the story behind my name."


def get_name_origin_story() -> str:
    p = load_identity_profile()
    story = str(p.get("name_origin") or "").strip()
    if story:
        return story

    # Fallback to memory recall if identity file has not been set yet.
    # Only accept explicitly tagged identity lines to avoid polluted memory facts.
    try:
        recall = mem_recall("nova name origin story creator gus")
        if recall:
            for raw in str(recall).splitlines():
                s = (raw or "").strip().lstrip("-*\u2022").strip()
                if not s:
                    continue
                low = s.lower()
                if "nova_name_origin:" in low:
                    out = s.split(":", 1)[1].strip() if ":" in s else ""
                    # Ignore obviously wrong identity contamination.
                    if out and "my name is gus" not in out.lower() and "name: gus" not in out.lower():
                        return out[:2000]
    except Exception:
        pass
    return ""


def identity_context_for_prompt() -> str:
    p = load_identity_profile()
    learned = load_learned_facts()
    lines = []
    story = str(p.get("name_origin") or "").strip()
    if story:
        lines.append("Identity fact: The assistant's name origin story is user-defined.")
        lines.append(f"Name origin story: {story[:1400]}")
    assistant_name = str(learned.get("assistant_name") or "").strip()
    developer_name = str(learned.get("developer_name") or "").strip()
    developer_nickname = str(learned.get("developer_nickname") or "").strip()
    if assistant_name:
        lines.append(f"Identity fact: assistant_name={assistant_name}")
    if developer_name:
        lines.append(f"Identity fact: developer_name={developer_name}")
    if developer_nickname:
        lines.append(f"Identity fact: developer_nickname={developer_nickname}")
    if not lines:
        return ""
    return "\n".join(lines)


def extract_name_origin_teach_text(text: str) -> str:
    raw = (text or "").strip()
    if not raw:
        return ""
    low = raw.lower()

    # Preferred explicit trigger.
    if "remember this" in low and any(cue in low for cue in (
        "nova",
        "name",
        "story behind your name",
        "story behing your name",
        "gus gave you your name",
        "gus named you",
    )):
        idx = low.find("remember this")
        candidate = raw[idx:]
        candidate = re.sub(r"(?is)^\s*remember\s+this\s*[:.\-]*\s*", "", candidate).strip()
        return candidate

    # Long origin-story style input should also be treated as teach content.
    cues = [
        "symbol of new light",
        "new beginnings",
        "story behind your name",
        "nova was given",
        "in astronomy, a nova occurs",
    ]
    if any(c in low for c in cues) and len(raw) >= 120:
        return raw

    return ""


def build_learning_context_details(query: str) -> dict:
    blocks = []
    kb_block = kb_search(query)
    mem_block = mem_recall(query)

    if kb_block:
        blocks.append(kb_block)

    if mem_block:
        # Keep memory context for the LLM but avoid injecting visible markers into user-facing reply.
        blocks.append(mem_block)

    if not blocks:
        return {
            "context": "",
            "knowledge_used": False,
            "memory_used": False,
            "knowledge_chars": 0,
            "memory_chars": 0,
        }

    context = "\n\n".join(blocks)[:4000]
    return {
        "context": context,
        "knowledge_used": bool(kb_block),
        "memory_used": bool(mem_block),
        "knowledge_chars": len(kb_block or ""),
        "memory_chars": len(mem_block or ""),
    }


def build_learning_context(query: str) -> str:
    return str(build_learning_context_details(query).get("context") or "")


def _render_chat_context(turns: list[tuple[str, str]], max_chars: int = 1800) -> str:
    if not turns:
        return ""
    lines = []
    for role, text in turns[-CHAT_CONTEXT_TURNS:]:
        role_name = "User" if role == "user" else "Assistant"
        t = re.sub(r"\s+", " ", (text or "").strip())
        if not t:
            continue
        lines.append(f"{role_name}: {t[:300]}")
    if not lines:
        return ""
    out = "\n".join(lines)
    return out[:max_chars]


def build_fallback_context_details(query: str, turns: list[tuple[str, str]] | None = None) -> dict[str, Any]:
    session_turns = turns if isinstance(turns, list) else []
    learning_details = build_learning_context_details(query)
    learning_context = str(learning_details.get("context") or "")
    chat_context = _render_chat_context(session_turns)
    session_fact_sheet = _build_session_fact_sheet(session_turns)

    context_blocks: list[str] = []
    if learning_context:
        context_blocks.append(learning_context)
    if chat_context:
        context_blocks.append("CURRENT CHAT CONTEXT:\n" + chat_context)
    if session_fact_sheet:
        context_blocks.append("SESSION FACT SHEET:\n" + session_fact_sheet)

    return {
        "context": "\n\n".join(context_blocks).strip()[:6000],
        "learning_context": learning_context,
        "chat_context": chat_context,
        "session_fact_sheet": session_fact_sheet,
        "memory_used": bool(learning_details.get("memory_used")),
        "knowledge_used": bool(learning_details.get("knowledge_used")),
        "memory_chars": int(learning_details.get("memory_chars") or 0),
        "knowledge_chars": int(learning_details.get("knowledge_chars") or 0),
    }


def _build_session_fact_sheet(turns: list[tuple[str, str]], max_chars: int = 1200) -> str:
    lines = []

    assistant_name = get_learned_fact("assistant_name", "Nova").strip()
    developer_name = get_learned_fact("developer_name", "Gustavo Uribe").strip()
    developer_nickname = get_learned_fact("developer_nickname", "Gus").strip()
    active_user = (get_active_user() or "").strip()
    story = get_name_origin_story().strip()

    if assistant_name:
        lines.append(f"Assistant name: {assistant_name}")
    if developer_name:
        lines.append(f"Developer full name: {developer_name}")
    if developer_nickname:
        lines.append(f"Developer nickname: {developer_nickname}")
    if active_user:
        lines.append(f"Active speaker identity: {active_user}")
    if story:
        lines.append(f"Name origin: {story[:220]}")

    saved_location = get_saved_location_text()
    if saved_location:
        lines.append(f"Stored assistant location: {saved_location}")

    if get_learned_fact("developer_location_relation", "").strip().lower() == "same_as_assistant":
        lines.append("Verified developer location relation: same as assistant")

    user_colors = _extract_color_preferences(turns)
    if user_colors:
        lines.append("User-stated color preferences: " + ", ".join(user_colors))

    developer_colors = _extract_developer_color_preferences(turns)
    if not developer_colors:
        developer_colors = _extract_developer_color_preferences_from_memory()
    if developer_colors:
        lines.append("Developer color preferences: " + ", ".join(developer_colors))

    bilingual = _developer_is_bilingual(turns)
    if bilingual is None:
        bilingual = _developer_is_bilingual_from_memory()
    if bilingual is True:
        lines.append("Developer languages: English, Spanish")

    animals = _extract_animal_preferences(turns)
    if animals:
        lines.append("User-stated animal preferences: " + ", ".join(animals))

    if not lines:
        return ""
    return "\n".join(lines)[:max_chars]


def _content_tokens(text: str) -> list[str]:
    raw = re.findall(r"[a-z0-9]{3,}", (text or "").lower())
    ignore = {
        "that", "this", "with", "from", "have", "your", "you", "are", "was", "were", "they",
        "them", "then", "than", "what", "when", "where", "which", "would", "could", "should",
        "about", "into", "also", "just", "told", "known", "know", "remember", "recall", "said",
        "made", "make", "gave", "name", "like", "likes", "favorite", "favourite", "colors", "color",
        "developer", "creator", "nova", "gus",
    }
    out = []
    for token in raw:
        if token in ignore:
            continue
        if token not in out:
            out.append(token)
    return out


def _is_risky_claim_sentence(sentence: str) -> bool:
    low = (sentence or "").strip().lower()
    if not low:
        return False
    if any(low.startswith(p) for p in [
        "i don't know", "i do not know", "i'm not sure", "i am not sure", "uncertain", "that would be a guess",
    ]):
        return False
    risky_patterns = [
        r"\b(i remember|i recall|we'?ve had|we have had)\b",
        r"\bcreator\b|\bdeveloper\b|\bfull name\b|\bnickname\b",
        r"\bfavorite\b|\bfavourite\b|\bcolors?\b|\bbilingual\b|\blanguages?\b",
        r"\b(?:i am|i'm)\s+in\s+(?:a|the)\s+room\b|\bwith gus\b",
        r"\bsmell\b|\bcoffee\b|\bhear\b|\bsee\b",
        r"\bcurrent physical location\b|\bmy location is\b|\bI am located\b",
        r"\bdownloaded\b|\bsaved\s+to\b|\bcreated\s+(?:file|folder|directory)\b",
    ]
    return any(re.search(p, low) for p in risky_patterns)


def _sentence_supported_by_evidence(sentence: str, evidence_text: str, tool_context: str = "") -> bool:
    low = (sentence or "").strip().lower()
    evidence_low = (evidence_text or "").lower()
    tool_low = (tool_context or "").lower()
    if not low:
        return True
    if not _is_risky_claim_sentence(sentence):
        quoted_spans = [span.strip().lower() for span in re.findall(r'"([^"]{8,})"', sentence or "") if span.strip()]
        if quoted_spans:
            combined_evidence = (evidence_low + "\n" + tool_low).strip()
            for span in quoted_spans:
                if span not in combined_evidence:
                    return False
        return True

    impossible_claims = [
        r"\b(?:i am|i'm)\s+in\s+(?:a|the)\s+room\b",
        r"\bsmell\b",
        r"\bhear\b",
        r"\bi can see\b",
    ]
    if any(re.search(p, low) for p in impossible_claims):
        return False

    tool_claims = [r"\bdownloaded\b", r"\bsaved\s+to\b", r"\bcreated\s+(?:file|folder|directory)\b"]
    if any(re.search(p, low) for p in tool_claims):
        return bool(tool_low)

    tokens = _content_tokens(sentence)
    if not tokens:
        return False
    overlap = [token for token in tokens if token in evidence_low]
    if len(overlap) >= min(2, len(tokens)):
        return True
    if any(name in low and name in evidence_low for name in ["gustavo uribe", "brownsville", "english", "spanish", "silver", "blue", "red"]):
        return True
    return False


def _apply_claim_gate(reply: str, evidence_text: str = "", tool_context: str = "") -> tuple[str, bool, str]:
    raw = (reply or "").strip()
    if not raw:
        return raw, False, ""

    parts = [p.strip() for p in re.split(r'(?<=[.!?])\s+', raw) if (p or "").strip()]
    kept = []
    blocked = False
    for part in parts:
        if _sentence_supported_by_evidence(part, evidence_text, tool_context=tool_context):
            kept.append(part)
        else:
            blocked = True

    if not blocked:
        return raw, False, ""

    if kept:
        return " ".join(kept).strip(), True, "unsupported_claim_removed"

    return _truthful_limit_reply("", include_next_step=False), True, "unsupported_claim_blocked"


def _uses_prior_reference(user_text: str) -> bool:
    t = (user_text or "").strip().lower()
    if not t:
        return False
    triggers = [
        "that information", "that info", "that", "those", "it",
        "from that", "from those", "summarize that", "give me that",
        "can you give me that", "use that",
    ]
    return any(x in t for x in triggers)


def _is_declarative_info(text: str) -> bool:
    """Return True when the user is supplying info (not asking for an action).
    Matches simple patterns like: "my name is X", "my location is X", "i live in X",
    or statements that start with 'i am' and contain a noun phrase.
    """
    t = (text or "").strip()
    if not t:
        return False
    low = t.lower()
    if "?" in t:
        return False

    # Avoid swallowing request-like prompts that begin with "I am ...".
    request_markers = [
        "can you", "could you", "would you", "do you", "what ", "how ", "why ", "where ", "when ", "which ",
        "curious", "capable", "abilities", "ability", "know what", "tell me", "give me",
    ]
    if any(m in low for m in request_markers):
        return False
    # common declarative prefixes
    declarative_prefixes = [
        "my name is",
        "i am",
        "i'm",
        "my location is",
        "i live in",
        "i work at",
        "i'm from",
        "i was born",
        "i have",
        "this is",
    ]
    for p in declarative_prefixes:
        if low.startswith(p):
            # avoid treating imperative like "i am done" as info if very short
            if len(t.split()) >= 2:
                return True
    # short factual sentences without question mark
    if len(t.split()) <= 6 and any(w in low for w in ["live", "located", "from", "born", "work"]):
        return True
    return False


def _is_explicit_request(text: str) -> bool:
    """Return True when the user is asking for an action or information.
    Heuristics: questions (who/what/when/where/why/how), starts with a verb (imperative), contains polite verbs.
    """
    t = (text or "").strip()
    if not t:
        return False
    low = t.lower().strip()
    # explicit question words
    qwords = ["who", "what", "when", "where", "why", "how", "which"]
    if low.endswith("?"):
        return True
    if any(low.startswith(w + " ") for w in qwords):
        return True
    # polite request patterns
    if any(kw in low for kw in ["please", "could you", "can you", "would you", "show me", "find", "search", "do you"]):
        return True
    # imperative: starts with a verb like 'open', 'run', 'create', 'save', 'search'
    verbs = ["open", "run", "create", "save", "search", "find", "read", "show", "list", "fetch", "gather"]
    first = low.split()[0]
    if first in verbs:
        return True
    return False


def _split_turn_clauses(text: str) -> list[str]:
    raw = str(text or "").strip()
    if not raw:
        return []
    pieces: list[str] = []
    for chunk in re.split(r"[.!?;]+", raw):
        fragment = str(chunk or "").strip(" \t\r\n\"'")
        if not fragment:
            continue
        subparts = re.split(
            r"(?:,\s*|\b(?:and|but)\s+)(?=(?:can|could|would|do|does|did|what|how|why|where|when|which|please|show|tell|give|check|find|search|look|fetch|gather)\b)",
            fragment,
            flags=re.I,
        )
        for subpart in subparts:
            cleaned = str(subpart or "").strip(" \t\r\n\"'")
            if cleaned:
                pieces.append(cleaned)
    return pieces


def _is_statement_like_clause(text: str) -> bool:
    raw = str(text or "").strip()
    if not raw:
        return False
    low = raw.lower()
    if _is_explicit_request(raw) or _is_explicit_command_like(raw):
        return False
    if _is_declarative_info(raw):
        return True
    if low.startswith(("i wonder if", "i'm wondering if", "i am wondering if")):
        return False
    if len(raw.split()) < 3:
        return False
    subject_markers = ("the ", "this ", "that ", "it ", "i ", "we ", "you ", "he ", "she ", "they ")
    verb_markers = (" is ", " are ", " was ", " were ", " looks ", " look ", " seems ", " seem ", " feels ", " feel ", " stays ", " stay ", " remains ", " remain ", " has ", " have ")
    return low.startswith(subject_markers) and any(marker in low for marker in verb_markers)


def _looks_like_correction_turn(text: str) -> bool:
    raw = str(text or "").strip()
    if not raw:
        return False
    low = raw.lower()
    identity_correction_patterns = (
        r"\byour\s+name\s+is\s+[a-z]",
        r"\b(?:his|the\s+developer(?:'s)?)\s+full\s+name\s+is\s+[a-z]",
        r"\bdeveloper(?:'s)?\s+name\s+is\s+[a-z]",
        r"\bcreator(?:'s)?\s+full\s+name\s+is\s+[a-z]",
    )
    triggers = (
        "wrong",
        "no,",
        "actually",
        "that's not",
        "that is not",
        "not true",
        "incorrect",
        "mistake",
        "you lied",
        "correction:",
        "you gave me garbage",
        "garbage back",
    )
    if _is_negative_feedback(raw) or _parse_correction(raw):
        return True
    if any(trigger in low for trigger in triggers):
        return True
    return "?" not in raw and any(re.search(pattern, low) for pattern in identity_correction_patterns)


def _looks_like_continue_thread_turn(
    text: str,
    *,
    turns: Optional[list[tuple[str, str]]] = None,
    active_subject: str = "",
    pending_action: Optional[dict] = None,
) -> bool:
    raw = str(text or "").strip()
    if not raw:
        return False
    normalized_active_subject = str(active_subject or "").strip()
    pending = pending_action if isinstance(pending_action, dict) else {}
    assistant_turn = _last_assistant_turn_text(list(turns or []))
    thread_active = bool(
        normalized_active_subject
        or str(pending.get("kind") or "").strip()
        or assistant_turn
    )
    if not thread_active:
        return False
    if _looks_like_contextual_followup(raw):
        return True
    if _extract_retrieval_result_index(raw) is not None:
        return True
    if _looks_like_affirmative_followup(raw) or _looks_like_shared_location_reference(raw):
        return True
    return bool(assistant_turn) and _assistant_offered_weather_lookup(assistant_turn) and _looks_like_affirmative_followup(raw)


def _assistant_offered_weather_lookup(text: str) -> bool:
    normalized = _normalize_turn_text(text)
    if not normalized:
        return False
    return any(phrase in normalized for phrase in (
        "what location should i use for the weather lookup",
        "tell me what location to use",
        "ask for our current location",
        "check the weather for you",
    ))


def _classify_turn_acts(
    text: str,
    *,
    turns: Optional[list[tuple[str, str]]] = None,
    active_subject: str = "",
    pending_action: Optional[dict] = None,
) -> list[str]:
    raw = str(text or "").strip()
    if not raw:
        return []
    clauses = _split_turn_clauses(raw) or [raw]
    has_command = _is_explicit_command_like(raw)
    has_correct = _looks_like_correction_turn(raw)
    has_ask = any(_is_explicit_request(clause) for clause in clauses)
    has_inform = any(_is_statement_like_clause(clause) for clause in clauses)
    has_continue_thread = _looks_like_continue_thread_turn(
        raw,
        turns=turns,
        active_subject=active_subject,
        pending_action=pending_action,
    )

    acts: list[str] = []
    if has_correct:
        acts.append("correct")
    if has_command:
        acts.append("command")
    elif has_ask:
        acts.append("ask")
    if has_inform:
        acts.append("inform")
    if has_continue_thread:
        acts.append("continue_thread")
    if has_inform and (has_ask or has_command):
        acts.append("mixed")
    return acts


def _looks_like_mixed_info_request_turn(text: str) -> bool:
    return "mixed" in _classify_turn_acts(text)


def _mixed_info_request_clarify_reply(text: str) -> str:
    del text
    return (
        "I think you're both giving context and asking me to do something. "
        "Do you want me to treat the first part as context and answer the request, "
        "or focus on just one part first?"
    )


def _extract_urls(text: str) -> list[str]:
    found = re.findall(r"https?://[^\s\)\]>\"']+", text or "")
    urls = []
    seen = set()
    for u in found:
        if u in seen:
            continue
        seen.add(u)
        urls.append(u)
    return urls


def _strip_invocation_prefix(text: str) -> str:
    """Normalize inputs like 'nova, ...' so routing sees the actual request."""
    t = (text or "").strip()
    if not t:
        return t

    m = re.match(r"^nova\b[\s,:\-]*(.*)$", t, flags=re.I)
    if not m:
        return t

    rest = (m.group(1) or "").strip()
    if not rest:
        return ""

    # Only strip when it looks like direct address/invocation.
    starter = (rest.split(maxsplit=1)[0] or "").lower()
    invoke_starters = {
        "what", "which", "who", "where", "when", "why", "how",
        "can", "could", "would", "do", "does", "did", "is", "are",
        "say", "tell", "show", "find", "search", "read", "list", "give",
        "web", "screen", "camera", "health", "inspect", "capabilities",
        "patch", "kb", "mem", "teach",
    }
    if starter in invoke_starters:
        return rest

    return t


def _normalize_domain_input(value: str) -> str:
    return _policy_manager().normalize_domain_input(value)


def list_allowed_domains() -> str:
    return _policy_manager().list_allowed_domains()


def policy_allow_domain(value: str) -> str:
    return _policy_manager().allow_domain(value, get_active_user())


def policy_remove_domain(value: str) -> str:
    return _policy_manager().remove_domain(value, get_active_user())


def policy_audit(limit: int = 20) -> str:
    return _policy_manager().audit(limit)


WEB_RESEARCH_PRESETS = {
    "normal": {
        "research_domains_limit": 4,
        "research_pages_per_domain": 8,
        "research_scan_pages_per_domain": 12,
        "research_max_depth": 1,
        "research_seeds_per_domain": 8,
        "research_max_results": 8,
        "research_min_score": 3.0,
    },
    "max": {
        "research_domains_limit": 8,
        "research_pages_per_domain": 25,
        "research_scan_pages_per_domain": 60,
        "research_max_depth": 2,
        "research_seeds_per_domain": 20,
        "research_max_results": 20,
        "research_min_score": 1.5,
    },
}


def web_mode_status() -> str:
    cfg = policy_web()
    lines = ["Current web research limits:"]
    keys = [
        "research_domains_limit",
        "research_pages_per_domain",
        "research_scan_pages_per_domain",
        "research_max_depth",
        "research_seeds_per_domain",
        "research_max_results",
        "research_min_score",
    ]
    for k in keys:
        lines.append(f"- {k}: {cfg.get(k)}")
    lines.append("Use: web mode max | web mode normal")
    return "\n".join(lines)


def set_web_mode(mode: str) -> str:
    result = _policy_manager().set_web_mode(mode, get_active_user())
    if result.startswith("Web research mode set to"):
        return result + "\n" + web_mode_status()
    return result


def set_memory_scope(scope: str) -> str:
    return _policy_manager().set_memory_scope(scope, get_active_user())


def get_search_provider() -> str:
    return _policy_manager().get_search_provider()


def get_search_provider_priority() -> list[str]:
    return _policy_manager().get_search_provider_priority()


def set_search_provider(provider: str) -> str:
    return _policy_manager().set_search_provider(provider, get_active_user())


def set_search_provider_priority(priority: str | list[str]) -> str:
    return _policy_manager().set_search_provider_priority(priority, get_active_user())


def get_search_endpoint() -> str:
    return _policy_manager().get_search_endpoint()


def set_search_endpoint(endpoint: str) -> str:
    return _policy_manager().set_search_endpoint(endpoint, get_active_user())


def auto_repair_search_endpoint(endpoint: str) -> str:
    return _policy_manager().auto_repair_search_endpoint(endpoint, get_active_user())


def _resolve_research_provider(candidates: list[str], *, default_tool: str = "web_research") -> dict[str, str]:
    normalized_candidates: list[str] = []
    seen: set[str] = set()
    for item in list(candidates or []):
        token = str(item or "").strip().lower()
        if not token or token in seen:
            continue
        seen.add(token)
        normalized_candidates.append(token)
    if not normalized_candidates:
        provider = _provider_name_from_tool(default_tool) or "general_web"
        return {"provider": provider, "tool_name": default_tool}

    chosen = next((item for item in get_search_provider_priority() if item in normalized_candidates), normalized_candidates[0])
    tool_map = {
        "wikipedia": "wikipedia_lookup",
        "stackexchange": "stackexchange_search",
        "general_web": "web_research",
    }
    return {"provider": chosen, "tool_name": tool_map.get(chosen, default_tool)}


def _normalize_search_endpoint(endpoint: str) -> str:
    raw = str(endpoint or "").strip()
    if not raw:
        return "http://127.0.0.1:8080/search"
    if "://" not in raw:
        raw = "http://" + raw
    parsed = urlparse(raw)
    scheme = str(parsed.scheme or "http").strip().lower() or "http"
    host = str(parsed.hostname or "").strip()
    if not host:
        return raw
    port = f":{parsed.port}" if parsed.port else ""
    path = str(parsed.path or "/search").strip() or "/search"
    return f"{scheme}://{host}{port}{path}"


def _search_endpoint_candidates(endpoint: str) -> list[str]:
    configured = _normalize_search_endpoint(endpoint)
    candidates: list[str] = []

    def _append(value: str) -> None:
        normalized = _normalize_search_endpoint(value)
        if normalized and normalized not in candidates:
            candidates.append(normalized)

    _append(configured)
    parsed = urlparse(configured)
    host = str(parsed.hostname or "").strip().lower()
    if host not in {"127.0.0.1", "localhost"}:
        return candidates

    scheme = str(parsed.scheme or "http").strip().lower() or "http"
    path = str(parsed.path or "/search").strip() or "/search"
    current_port = int(parsed.port or (443 if scheme == "https" else 80))
    ports: list[int] = []
    for port in (current_port, 8080, 8081):
        if port not in ports:
            ports.append(port)
    hosts: list[str] = [host]
    for local_host in ("127.0.0.1", "localhost"):
        if local_host not in hosts:
            hosts.append(local_host)
    for local_host in hosts:
        for port in ports:
            _append(f"{scheme}://{local_host}:{port}{path}")
    return candidates


def _is_local_search_endpoint(endpoint: str) -> bool:
    parsed = urlparse(_normalize_search_endpoint(endpoint))
    return str(parsed.hostname or "").strip().lower() in {"127.0.0.1", "localhost"}


def probe_search_endpoint(endpoint: str = "", *, timeout: float = 2.5, persist_repair: bool = False) -> dict:
    configured = _normalize_search_endpoint(endpoint or get_search_endpoint())
    candidates = _search_endpoint_candidates(configured)
    last_note = "endpoint_unreachable"
    candidate_errors: list[dict[str, str]] = []
    for candidate in candidates:
        try:
            r = requests.get(
                candidate,
                params={"q": "health", "format": "json"},
                headers={"User-Agent": "Nova/1.0", "Accept": "application/json"},
                timeout=timeout,
            )
            r.raise_for_status()
            data = r.json()
            if not isinstance(data, dict):
                raise ValueError("non_json_response")
            note = f"status={r.status_code}"
            repair_message = ""
            repaired = False
            if candidate != configured:
                note += f" auto-detected={candidate}"
                if persist_repair and _is_local_search_endpoint(configured) and _is_local_search_endpoint(candidate):
                    repair_message = auto_repair_search_endpoint(candidate)
                    repaired = bool(repair_message)
                    if repaired:
                        note += " auto-repaired"
            return {
                "ok": True,
                "endpoint": configured,
                "resolved_endpoint": candidate,
                "note": note,
                "auto_detected": candidate != configured,
                "repaired": repaired,
                "repair_message": repair_message,
                "candidate_errors": candidate_errors,
                "checked_endpoints": candidates,
                "message": f"SearXNG probe passed for {candidate} ({note}).",
            }
        except Exception as e:
            last_note = f"error:{e}"
            candidate_errors.append({"endpoint": candidate, "note": last_note})

    configured_error = next((item for item in candidate_errors if str(item.get("endpoint") or "") == configured), None)
    checked_summary = "; ".join(
        f"{str(item.get('endpoint') or '')} => {str(item.get('note') or '')}"
        for item in candidate_errors
    )
    note = str((configured_error or {}).get("note") or last_note)
    if checked_summary:
        note = f"configured_failed={note}; checked={checked_summary}"
    return {
        "ok": False,
        "endpoint": configured,
        "resolved_endpoint": "",
        "note": note,
        "auto_detected": False,
        "candidate_errors": candidate_errors,
        "checked_endpoints": candidates,
        "message": f"SearXNG probe failed for {configured} ({note}).",
    }


def toggle_search_provider() -> str:
    current = get_search_provider()
    target = "searxng" if current == "html" else "html"
    return set_search_provider(target)


def _build_greeting_reply(user_text: str, active_user: Optional[str] = None) -> Optional[str]:
    t = (user_text or "").strip().lower()
    greet_regex = re.compile(r"^(hi|hello|hey|good morning|good afternoon|good evening)([\s!,\.]|$)")
    m = greet_regex.match(t)
    if not m:
        return None

    # If this utterance includes an actual request after the greeting, do not
    # short-circuit here; let deterministic command routing handle it.
    rest = t[m.end():].strip()
    rest = re.sub(r"^nova\b[\s,:\-]*", "", rest, flags=re.I).strip()
    request_markers = [
        "can you", "could you", "would you", "please", "give me", "check", "show", "tell me",
        "weather", "web", "search", "find", "read", "list", "inspect", "health", "help",
    ]
    if rest and any(k in rest for k in request_markers):
        return None

    who = (active_user or "").strip()
    if who and who.lower() == _default_local_user_id().lower():
        who = ""
    has_how_are_you = bool(re.search(r"\bhow\s+are\s+you\b", t))

    if has_how_are_you:
        if who:
            return f"Hey {who}. I'm doing good today. What's going on?"
        return "Hey. I'm doing good today. What's going on?"

    word = m.group(1)
    if word in {"hi", "hello"}:
        return f"Hi {who}." if who else "Hello."
    if word == "hey":
        return f"Hey {who}. What do you need?" if who else "Hey, what do you need?"
    return f"{word.capitalize()}, {who}." if who else f"{word.capitalize()}."


def _quick_smalltalk_reply(user_text: str, active_user: Optional[str] = None) -> Optional[str]:
    t = (user_text or "").strip().lower()
    if not t:
        return "Okay."

    who = str(active_user or "").strip()
    if who.lower() in {"runner", "local-user", "localuser", "unknown", "local"}:
        who = ""

    greeting = _build_greeting_reply(user_text, active_user=who)
    if greeting:
        return greeting

    normalized = re.sub(r"[^a-z0-9 ]+", " ", t)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    if normalized.startswith("how are you doing") or normalized.startswith("how is your day going") or normalized.startswith("are you doing alright today nova"):
        return f"Hey {who}. I'm doing good today. What's going on?" if who else "Hey. I'm doing good today. What's going on?"

    if "thank you" in t or t in {"thanks", "thx"}:
        return "You're welcome."

    if any(p in t for p in ["ready to get to work", "ready to work", "ready when you are"]):
        return "Ready when you are. What's the task for today?"

    if any(p in t for p in ["who is your developer", "who's your developer"]):
        return "My developer is Gustavo (Gus). He created me."

    return None


def _extract_color_preferences(session_turns: list[tuple[str, str]]) -> list[str]:
    colors = []
    seen = set()
    for role, text in session_turns:
        if role != "user":
            continue
        t = (text or "").lower().strip()

        has_preference_signal = any(s in t for s in [
            "i like", "i love", "i prefer", "favorite color", "favourite color", "like the color",
        ]) or bool(re.search(r"\bi\s+(?:\w+\s+){0,3}like\b", t))
        if not has_preference_signal:
            continue

        toks = re.findall(r"[a-z]{3,20}", t)
        found = [w for w in toks if w in KNOWN_COLORS]
        if not found:
            continue

        for c in found:
            if c in seen:
                continue
            seen.add(c)
            colors.append(c)
    return colors


def _extract_color_preferences_from_text(text: str) -> list[str]:
    toks = re.findall(r"[a-z]{3,20}", (text or "").lower())
    out = []
    seen = set()
    for t in toks:
        if t in KNOWN_COLORS and t not in seen:
            seen.add(t)
            out.append(t)
    return out


def _extract_color_preferences_from_memory() -> list[str]:
    if not mem_enabled():
        return []
    probe = mem_recall("what colors does the user like favorite color preference")
    return _extract_color_preferences_from_text(probe)


def _extract_developer_color_preferences(session_turns: list[tuple[str, str]]) -> list[str]:
    aliases = {"gus", "gustavo", "developer", "dev"}
    out = []
    seen = set()
    for role, text in session_turns:
        if role != "user":
            continue
        t = (text or "").lower().strip()
        if not any(a in t for a in aliases):
            continue
        if not any(k in t for k in ["color", "colors", "favourite", "favorite", "likes", "like", "bilingual", "english", "spanish"]):
            continue
        for w in re.findall(r"[a-z]{3,20}", t):
            if w in KNOWN_COLORS and w not in seen:
                seen.add(w)
                out.append(w)
    return out


def _developer_fact_memory_probe(query: str) -> str:
    if not mem_enabled():
        return ""

    probe = mem_recall(query)
    if probe:
        return probe

    active_user = (get_active_user() or "").strip()
    fallback_user = _default_local_user_id()
    if not active_user or not fallback_user or active_user.lower() == fallback_user.lower():
        return ""

    set_active_user(None)
    try:
        return mem_recall(query)
    finally:
        set_active_user(active_user)


def _extract_developer_color_preferences_from_memory() -> list[str]:
    if not mem_enabled():
        return []
    probe = _developer_fact_memory_probe("gustavo gus developer favorite colors color preference")
    if not probe:
        return []

    out = []
    seen = set()
    lines = [ln.strip().lower() for ln in probe.splitlines() if ln.strip()]
    candidate_lines = [
        ln for ln in lines
        if any(a in ln for a in ["gus", "gustavo", "developer"])
        and any(k in ln for k in ["color", "colors", "favorite", "favourite", "likes", "like"])
    ]
    source = "\n".join(candidate_lines) if candidate_lines else probe
    for w in re.findall(r"[a-z]{3,20}", source.lower()):
        if w in KNOWN_COLORS and w not in seen:
            seen.add(w)
            out.append(w)
    return out


def _is_developer_color_lookup_request(user_text: str) -> bool:
    t = (user_text or "").lower()
    if not any(k in t for k in ["color", "colors"]):
        return False
    return any(k in t for k in ["developer", "gus", "gustavo", "he", "his"])


def _is_developer_bilingual_request(user_text: str) -> bool:
    t = (user_text or "").lower()
    if not any(k in t for k in ["developer", "gus", "gustavo", "he", "his"]):
        return False
    return any(k in t for k in ["bilingual", "english", "spanish", "languages", "language"])


def _developer_is_bilingual(session_turns: list[tuple[str, str]]) -> Optional[bool]:
    aliases = ["developer", "gus", "gustavo"]
    for role, text in reversed(session_turns):
        if role != "user":
            continue
        t = (text or "").lower()
        if not any(a in t for a in aliases):
            continue
        if "bilingual" in t and ("english" in t or "spanish" in t):
            return True
        if "not bilingual" in t:
            return False
    return None


def _developer_is_bilingual_from_memory() -> Optional[bool]:
    if not mem_enabled():
        return None
    probe = _developer_fact_memory_probe("is gustavo bilingual english spanish developer")
    low = (probe or "").lower()
    if not low:
        return None
    if ("gus" in low or "gustavo" in low or "developer" in low) and "bilingual" in low and ("english" in low or "spanish" in low):
        return True
    if "not bilingual" in low:
        return False
    return None


def _recent_turn_mentions(turns: list[tuple[str, str]], keywords: list[str], limit: int = 6) -> bool:
    keys = [str(k or "").strip().lower() for k in keywords if str(k or "").strip()]
    if not keys:
        return False
    for role, text in reversed(turns[-max(1, int(limit)):]):
        low = (text or "").strip().lower()
        if not low:
            continue
        if any(k in low for k in keys):
            return True
    return False


def _strip_confirmation_prefix(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", (text or "").strip())
    patterns = [
        r"^(?:yes|yeah|yep|correct|exactly|true|right)\b[\s,!.:-]*",
        r"^(?:you(?:'| a)?re\s+right|your\s+correct|that(?:'| i)?s\s+right)\b[\s,!.:-]*",
        r"^(?:yes\s+)?nova\b[\s,!.:-]*",
    ]
    changed = True
    while cleaned and changed:
        changed = False
        for pattern in patterns:
            newer = re.sub(pattern, "", cleaned, flags=re.I).strip()
            if newer != cleaned:
                cleaned = newer
                changed = True
    return cleaned


def _extract_work_role_parts(raw: str) -> list[str]:
    text = _strip_confirmation_prefix(raw)
    low = text.lower()
    role_parts: list[str] = []

    if "full stack developer" in low:
        role_parts.append("full stack developer")

    work_match = re.search(r"\bworks?\s+as\s+(.+)$", text, flags=re.I)
    if work_match:
        work_text = work_match.group(1)
        work_text = re.sub(r"^[^A-Za-z0-9]+", "", work_text).strip(" .,!?:;")
        if work_text:
            role_parts.append(work_text)

    normalized_roles: list[str] = []
    seen_roles = set()
    for role in role_parts:
        cleaned = re.sub(r"\s+", " ", str(role or "").strip())
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen_roles:
            continue
        seen_roles.add(key)
        normalized_roles.append(cleaned)
    return normalized_roles


def _store_developer_role_facts(roles: list[str], input_source: str = "typed") -> tuple[bool, str]:
    if not roles or not mem_enabled():
        return False, ""
    if len(roles) == 1:
        role_sentence = f"Gus works as a {roles[0]}."
    else:
        role_sentence = f"Gus works as a {roles[0]} and {roles[1]}."
    mem_add("identity", input_source, role_sentence)
    return True, role_sentence.rstrip(".")


def _extract_developer_roles_from_memory() -> list[str]:
    if not mem_enabled():
        return []
    probe = _developer_fact_memory_probe("gus gustavo developer works as role job title")
    if not probe:
        return []
    roles: list[str] = []
    seen = set()
    for line in probe.splitlines():
        match = re.search(r"\bworks?\s+as\s+(.+?)(?:[.!?]|$)", line, flags=re.I)
        if not match:
            continue
        role_text = re.sub(r"^(?:a|an)\s+", "", match.group(1).strip(), flags=re.I)
        parts = re.split(r"\s+(?:and|&)\s+|\s*,\s*", role_text)
        for part in parts:
            cleaned = re.sub(r"\s+", " ", part).strip(" .,!?:;")
            if not cleaned:
                continue
            key = cleaned.lower()
            if key in seen:
                continue
            seen.add(key)
            roles.append(cleaned)
    return roles


def _format_fact_series(items: list[str]) -> str:
    values = [str(item or "").strip() for item in items if str(item or "").strip()]
    if not values:
        return ""
    if len(values) == 1:
        return values[0]
    if len(values) == 2:
        return f"{values[0]} and {values[1]}"
    return ", ".join(values[:-1]) + f", and {values[-1]}"


def _is_developer_profile_request(user_text: str) -> bool:
    t = (user_text or "").strip().lower()
    if not t:
        return False

    creator_cues = [
        "who is your developer", "who's your developer", "who is your creator", "who's your creator",
        "who created you", "your creator", "is gus your creator", "so gus is your creator",
        "is gustavo your creator", "is he your creator", "creator is gus", "creator is gustavo",
    ]
    if any(c in t for c in creator_cues):
        return True

    if any(c in t for c in ["how did he develop you", "how did he developed you", "how did he build you", "how was he able to develop you", "what else does he"]):
        return True

    if not any(k in t for k in ["developer", "gus", "gustavo"]):
        return False

    cues = [
        "who is", "who's", "what do you know", "what else", "tell me about",
        "about your developer", "about gus", "about gustavo", "how did", "created you",
        "developed you", "built you",
    ]
    return any(c in t for c in cues)


def _developer_profile_reply(turns: Optional[list[tuple[str, str]]] = None, user_text: str = "") -> str:
    low = (user_text or "").lower()
    session_turns = turns if isinstance(turns, list) else []

    developer_name = get_learned_fact("developer_name", "Gustavo Uribe").strip()
    developer_nickname = get_learned_fact("developer_nickname", "Gus").strip()
    roles = _extract_developer_roles_from_memory()
    colors = _extract_developer_color_preferences(session_turns)
    if not colors:
        colors = _extract_developer_color_preferences_from_memory()
    bilingual = _developer_is_bilingual(session_turns)
    if bilingual is None:
        bilingual = _developer_is_bilingual_from_memory()

    if developer_nickname and developer_nickname.lower() != developer_name.lower():
        base_fact = f"His full name is {developer_name}, and he also goes by {developer_nickname}."
    else:
        base_fact = f"His full name is {developer_name}."

    if "how did" in low or "developed you" in low or "built you" in low:
        return _prefix_from_earlier_memory(f"{base_fact} He created me. I do not have detailed build-history notes in memory yet.")

    if "who is" in low or "who's" in low or "creator" in low:
        if developer_nickname and developer_nickname.lower() != developer_name.lower():
            return _prefix_from_earlier_memory(f"My developer is {developer_name}. {developer_nickname} is his nickname. He created me.")
        return _prefix_from_earlier_memory(f"My developer is {developer_name}. He created me.")

    extra_facts: list[str] = []
    if roles:
        extra_facts.append(f"Known work roles: {_format_fact_series(roles)}.")
    if colors:
        if len(colors) == 1:
            extra_facts.append(f"Known favorite color: {colors[0]}.")
        else:
            extra_facts.append(f"Known favorite colors: {_format_fact_series(colors)}.")
    if bilingual is True:
        extra_facts.append("He is bilingual in English and Spanish.")
    elif bilingual is False:
        extra_facts.append("Known bilingual note: not bilingual.")

    lead = "Here are the verified facts I have about my developer, Gus."
    if extra_facts:
        return _prefix_from_earlier_memory(" ".join([lead, base_fact] + extra_facts))
    return _prefix_from_earlier_memory(f"{lead} {base_fact} I don't have any additional verified information about him beyond that yet.")


def _is_developer_location_request(
    user_text: str,
    state: Optional[dict] = None,
    turns: Optional[list[tuple[str, str]]] = None,
) -> bool:
    low = (user_text or "").strip().lower()
    if not low:
        return False

    explicit_cues = [
        "where is gus",
        "where is gustavo",
        "where is your developer",
        "developer current location",
        "developer's current location",
        "gus current location",
        "gustavo current location",
    ]
    if any(cue in low for cue in explicit_cues):
        return True

    developer_context = False
    if isinstance(state, dict) and str(state.get("subject") or "") == "developer":
        developer_context = True
    elif turns:
        developer_context = _recent_turn_mentions(turns, ["gus", "gustavo", "developer", "creator"])

    pronoun_cues = ["his current location", "his location", "current whereabouts", "where is he"]
    return developer_context and any(cue in low for cue in pronoun_cues)


def _developer_location_reply() -> str:
    relation = get_learned_fact("developer_location_relation", "").strip().lower()
    if relation == "same_as_assistant":
        preview = get_saved_location_text()
        if preview:
            return _prefix_from_earlier_memory(f"Based on the verified relation you gave me, Gus's location is {preview}.")
        return "You told me Gus shares my location, but I do not have my own stored location yet. You can tell me: 'My location is ...'"
    return "I'm uncertain about Gus's current location. I do not have verified current whereabouts for him."


def _developer_location_turn(
    text: str,
    *,
    state: Optional[dict] = None,
    turns: Optional[list[tuple[str, str]]] = None,
) -> tuple[str, Optional[dict]]:
    if not _is_developer_location_request(text, state=state, turns=turns):
        return "", None
    next_state = _infer_profile_conversation_state(text) or _make_conversation_state("identity_profile", subject="developer")
    return _developer_location_reply(), next_state


def _identity_profile_followup_reply(subject: str, turns: Optional[list[tuple[str, str]]] = None) -> str:
    active_user_raw = str(get_active_user() or "").strip()
    developer_name = get_learned_fact("developer_name", "Gustavo Uribe").strip()
    developer_nickname = get_learned_fact("developer_nickname", "Gus").strip()
    session_turns = turns if isinstance(turns, list) else []

    if subject == "developer" or (subject == "self" and _speaker_matches_developer()):
        facts: list[str] = []
        roles = _extract_developer_roles_from_memory()
        colors = _extract_developer_color_preferences(session_turns)
        if not colors:
            colors = _extract_developer_color_preferences_from_memory()
        bilingual = _developer_is_bilingual(session_turns)
        if bilingual is None:
            bilingual = _developer_is_bilingual_from_memory()
        story = get_name_origin_story().strip()

        if developer_name:
            facts.append(f"Developer full name: {developer_name}.")
        if developer_nickname and developer_nickname.lower() != developer_name.lower():
            facts.append(f"Developer nickname: {developer_nickname}.")
        if roles:
            facts.append(f"Known work roles: {_format_fact_series(roles)}.")
        if colors:
            facts.append(f"Known favorite colors: {_format_fact_series(colors)}.")
        if bilingual is True:
            facts.append("Known languages: English and Spanish.")
        elif bilingual is False:
            facts.append("Known language note: not bilingual.")
        if story:
            facts.append("Verified history: you gave me the name Nova.")

        if facts:
            lead = "Here are the other verified facts I have about you." if subject == "self" else "Here are the other verified facts I have about Gus."
            return lead + " " + " ".join(facts)
        return "I do not have more verified developer facts beyond the basics yet."

    facts = []
    colors = _extract_color_preferences(session_turns)
    if not colors:
        colors = _extract_color_preferences_from_memory()
    animals = _extract_animal_preferences(session_turns)
    if not animals:
        animals = _extract_animal_preferences_from_memory()

    if active_user_raw:
        facts.append(f"Verified name: {active_user_raw}.")
    if colors:
        facts.append(f"Known color preferences: {_format_fact_series(colors)}.")
    if animals:
        facts.append(f"Known animal preferences: {_format_fact_series(animals)}.")

    if facts:
        return "Here are the other verified personal facts I have. " + " ".join(facts)
    if active_user_raw:
        return f"Beyond your session identity as {active_user_raw}, I do not have other verified personal facts yet."
    return "I do not have more verified personal facts for this thread yet."


def _identity_name_followup_reply(subject: str) -> str:
    active_user_raw = str(get_active_user() or "").strip()
    developer_name = get_learned_fact("developer_name", "Gustavo Uribe").strip()
    developer_nickname = get_learned_fact("developer_nickname", "Gus").strip()
    assistant_name = get_learned_fact("assistant_name", "Nova").strip()
    story = get_name_origin_story().strip()

    if subject == "developer" or (subject == "self" and _speaker_matches_developer()):
        parts = []
        if developer_name:
            parts.append(f"Your verified full name is {developer_name}.")
        if developer_nickname and developer_nickname.lower() != developer_name.lower():
            parts.append(f"You also go by {developer_nickname}.")
        if story:
            parts.append(f"You gave me the name {assistant_name}.")
        if parts:
            return " ".join(parts)

    if active_user_raw:
        return f"The verified name I have for you in this session is {active_user_raw}."

    return "I do not have a more detailed verified name record for this thread yet."


def _rules_reply() -> str:
    return (
        "Yes. I follow strict operating rules: I do not fabricate tool actions or files, "
        "I stay within enabled policy/tool limits, and I should say uncertain when I cannot verify something."
    )


def _developer_identity_followup_reply(turns: Optional[list[tuple[str, str]]] = None, *, name_focus: bool = False) -> str:
    developer_name = get_learned_fact("developer_name", "Gustavo Uribe").strip()
    developer_nickname = get_learned_fact("developer_nickname", "Gus").strip()
    assistant_name = get_learned_fact("assistant_name", "Nova").strip()
    story = get_name_origin_story().strip()
    session_turns = turns if isinstance(turns, list) else []
    roles = _extract_developer_roles_from_memory()
    colors = _extract_developer_color_preferences(session_turns)
    if not colors:
        colors = _extract_developer_color_preferences_from_memory()
    bilingual = _developer_is_bilingual(session_turns)
    if bilingual is None:
        bilingual = _developer_is_bilingual_from_memory()

    parts: list[str] = []
    if developer_name:
        parts.append(f"Your verified full name is {developer_name}.")
    if developer_nickname and developer_nickname.lower() != developer_name.lower():
        parts.append(f"You also go by {developer_nickname}.")
    if story:
        parts.append(f"You are the creator who gave me the name {assistant_name}. {story}")
    elif assistant_name:
        parts.append(f"You are confirmed as the creator tied to the name {assistant_name}.")

    if not name_focus:
        if roles:
            parts.append(f"Known work roles: {_format_fact_series(roles)}.")
        if colors:
            parts.append(f"Known favorite colors: {_format_fact_series(colors)}.")
        if bilingual is True:
            parts.append("Known languages: English and Spanish.")
        elif bilingual is False:
            parts.append("Known language note: not bilingual.")

    if parts:
        if name_focus:
            return "About your name and identity: " + " ".join(parts)
        return "Here are the richer verified developer facts I have about you. " + " ".join(parts)

    return "I have your name and creator role confirmed, but no deeper verified details yet."


def _infer_profile_conversation_state(text: str) -> Optional[dict]:
    low = _normalize_turn_text(text)
    if not low:
        return None
    rule_result = TURN_SUPERVISOR.evaluate_rules(text, phase="state")
    state_update = rule_result.get("state_update") if isinstance(rule_result, dict) else None
    if isinstance(state_update, dict):
        return state_update
    developer_confirmed = _speaker_matches_developer()
    developer_cues = (
        _is_developer_color_lookup_request(text)
        or _is_developer_bilingual_request(text)
        or "what do you know about gus" in low
        or "what else do you know about gus" in low
        or "who is your creator" in low
        or "who made you" in low
        or "creator" in low
    )
    self_cues = (
        _is_color_lookup_request(text)
        or "what animals do i like" in low
        or "which animals do i like" in low
        or "what do you know about me" in low
        or "what else do you know about me" in low
        or "what do you remember about me" in low
        or "do you remember me" in low
        or "what is my name" in low
        or "do you know my name" in low
    )
    if developer_confirmed and (developer_cues or self_cues):
        return _make_conversation_state("developer_identity", subject="developer")
    if developer_cues:
        return _make_conversation_state("identity_profile", subject="developer")
    if self_cues:
        return _make_conversation_state("identity_profile", subject="self")
    return None


def _is_developer_work_guess_query(text: str) -> bool:
    low = _normalize_turn_text(text)
    if not low or "?" not in str(text or ""):
        return False
    targets_developer = any(token in low for token in ("gus", "gustavo", "developer", "creator", "he do"))
    work_intent = any(token in low for token in ("type of work", "kind of work", "what does", "job", "occupation", "work does"))
    return targets_developer and work_intent


def _developer_work_guess_reply(text: str) -> str:
    if not _is_developer_work_guess_query(text):
        return ""
    return (
        "Based on the context so far, my grounded guess is that Gus works in software or technical data systems. "
        "If you confirm or correct that, I will store the verified role."
    )


def _developer_work_guess_turn(text: str) -> tuple[str, Optional[dict]]:
    reply = _developer_work_guess_reply(text)
    if not reply:
        return "", None
    return reply, _make_conversation_state("developer_role_guess", subject="Gus")


def _consume_conversation_followup(state: Optional[dict], text: str, input_source: str = "typed", turns: Optional[list[tuple[str, str]]] = None) -> tuple[bool, str, Optional[dict]]:
    if not isinstance(state, dict):
        return False, "", state

    rule_result = TURN_SUPERVISOR.evaluate_rules(text, manager=state, turns=turns, phase="handle")
    handled_rule, rule_reply, rule_state = _execute_registered_supervisor_rule(
        rule_result,
        text,
        state,
        turns=turns,
        input_source=input_source,
    )
    if handled_rule:
        return True, rule_reply, rule_state

    kind = str(state.get("kind") or "")
    if kind == "retrieval":
        if _is_retrieval_meta_question(text):
            return True, _retrieval_meta_reply(state), state
        if _looks_like_retrieval_followup(text):
            reply, next_state = _retrieval_followup_reply(state, text)
            return True, reply, next_state
        return False, "", state

    if kind == "queue_status":
        if _is_queue_status_reason_followup(text):
            return True, _queue_status_reason_reply(state), state
        if _is_queue_status_report_followup(text):
            return True, _queue_status_report_reply(state), state
        if _is_queue_status_seam_followup(text):
            return True, _queue_status_seam_reply(state), state
        return False, "", state

    if kind == "location_recall":
        handled_location, location_reply, location_state, _location_intent = _handle_location_conversation_turn(
            state,
            text,
            turns=turns,
        )
        if handled_location:
            return True, location_reply, location_state
        return False, "", state

    if kind == "weather_result":
        if _is_weather_meta_followup(text):
            return True, _weather_meta_reply(state), state
        if _is_weather_status_followup(text):
            return True, _weather_status_reply(state), state
        return False, "", state

    if kind == "numeric_reference_clarify":
        value = str(state.get("value") or "").strip()
        normalized = _normalize_turn_text(text)
        raw = str(text or "").strip()
        if not raw:
            return False, "", state
        if raw == value or "?" in raw or any(phrase in normalized for phrase in ("what do you think", "what is it", "what do you guess", "guess")):
            return True, _numeric_reference_guess_reply(value), state
        referent = raw.rstrip(".!? ")
        if not referent:
            return False, "", state
        return True, _numeric_reference_binding_reply(value, referent), _make_conversation_state("numeric_reference", value=value, referent=referent)

    if kind == "numeric_reference":
        value = str(state.get("value") or "").strip()
        referent = str(state.get("referent") or "").strip()
        raw = str(text or "").strip()
        if raw == value and referent:
            return True, _numeric_reference_binding_reply(value, referent), state
        return False, "", state

    if kind == "developer_role_guess":
        if "?" in (text or ""):
            return False, "", None
        roles = _extract_work_role_parts(text)
        learned, learned_text = _store_developer_role_facts(roles, input_source=input_source)
        if learned:
            return True, "Understood. I learned: " + learned_text + ".", None
        if _strip_confirmation_prefix(text):
            return True, "I still need the actual role or job title to store, not just a confirmation.", state
        return False, "", state

    if kind == "developer_identity":
        low = _normalize_turn_text(text)
        if "my name" in low or ("name" in low and any(token in low for token in ("tell me more", "more about", "go on", "continue"))):
            return True, _developer_identity_followup_reply(turns=turns, name_focus=True), state
        if _looks_like_profile_followup(text):
            return True, _developer_identity_followup_reply(turns=turns, name_focus=False), state
        return False, "", state

    if kind == "identity_profile":
        low = _normalize_turn_text(text)
        if _is_retrieval_meta_question(text):
            return True, _non_retrieval_resource_meta_reply(), state
        if str(state.get("subject") or "") == "developer":
            if _is_developer_location_request(text, state=state, turns=turns):
                return True, _developer_location_reply(), state
        if "my name" in low or "name" in low and any(token in low for token in ("tell me more", "more about", "go on", "continue")):
            subject = str(state.get("subject") or "self")
            return True, _identity_name_followup_reply(subject), state
        if _looks_like_profile_followup(text):
            subject = str(state.get("subject") or "self")
            return True, _identity_profile_followup_reply(subject, turns=turns), state
        return False, "", state

    return False, "", state


def _learn_contextual_developer_facts(turns: list[tuple[str, str]], text: str, input_source: str = "typed") -> tuple[bool, str]:
    raw = (text or "").strip()
    low = _normalize_turn_text(raw)
    if not raw:
        return False, ""

    relevant_context = _recent_turn_mentions(turns, ["gus", "gustavo", "developer", "creator"])
    if not relevant_context and not any(k in low for k in ["gus", "gustavo", "developer", "creator"]):
        return False, ""

    learned: list[str] = []

    color_match = re.search(r"\b(?:favorite|favourite)\s+colors?\s+are\s+(.+)$", raw, flags=re.I)
    if color_match and mem_enabled():
        colors_text = re.sub(r"\s+and\s+he(?:'s|\s+is)\b.*$", "", color_match.group(1), flags=re.I).strip(" .,:;")
        colors = _extract_color_preferences_from_text(colors_text)
        if colors:
            pretty = ", ".join(colors[:-1]) + (f", and {colors[-1]}" if len(colors) > 1 else colors[0])
            mem_add("identity", input_source, f"Gus favorite colors are {pretty}.")
            learned.append(f"Gus favorite colors are {pretty}")

    if "bilingual" in low and "english" in low and "spanish" in low and mem_enabled():
        mem_add("identity", input_source, "Gus is bilingual in English and Spanish.")
        learned.append("Gus is bilingual in English and Spanish")

    role_parts = _extract_work_role_parts(raw)
    learned_role, learned_role_text = _store_developer_role_facts(role_parts, input_source=input_source)
    if learned_role:
        learned.append(learned_role_text)

    same_location_cues = (
        "same as yours",
        "same as your location",
        "same location as yours",
        "same location as you",
    )
    references_developer_location = "location" in low and (
        relevant_context or any(k in low for k in ["gus", "gustavo", "developer", "creator"])
    )
    if references_developer_location and any(cue in low for cue in same_location_cues):
        facts = load_learned_facts()
        if str(facts.get("developer_location_relation") or "").strip().lower() != "same_as_assistant":
            facts["developer_location_relation"] = "same_as_assistant"
            facts["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            save_learned_facts(facts)
            if mem_enabled():
                mem_add("identity", input_source, "Gus location is the same as Nova's location.")
            learned.append("Gus shares my location")

    if not learned:
        return False, ""

    return True, "Understood. I learned: " + "; ".join(learned) + "."


def _extract_memory_teach_text(text: str) -> str:
    raw = (text or "").strip()
    if not raw:
        return ""
    low = raw.lower()
    cues = ["remember that", "remember this", "can you remember", "think you can remember"]
    if not any(c in low for c in cues):
        return ""

    cleaned = re.sub(r"(?is)\b(?:can\s+you\s+remember\s+that|think\s+you\s+can\s+remember\s+that|remember\s+that|remember\s+this)\b\s*\??", "", raw).strip(" .,!?")
    if not cleaned:
        return ""
    keep, _reason = _memory_should_keep_text(cleaned)
    return cleaned if keep else ""


def _extract_last_user_question(turns: list[tuple[str, str]], current_text: str) -> str:
    target = (current_text or "").strip().lower()
    for role, text in reversed(turns[:-1]):
        if role != "user":
            continue
        candidate = (text or "").strip()
        if not candidate:
            continue
        low = candidate.lower()
        if low == target:
            continue
        if (
            "?" in candidate
            or low.startswith(("what ", "who ", "why ", "how ", "when ", "where ", "which ", "do ", "does ", "did ", "can ", "could ", "would ", "will ", "are ", "is "))
            or _is_identity_or_developer_query(candidate)
            or _is_color_lookup_request(candidate)
            or _is_developer_color_lookup_request(candidate)
            or _is_developer_bilingual_request(candidate)
        ):
            return candidate
    return ""


def _analyze_routing_text(turns: list[tuple[str, str]], text: str) -> tuple[str, str]:
    return analyze_routing_text(
        turns,
        text,
        evaluate_rules_fn=lambda user_text, **kwargs: TURN_SUPERVISOR.evaluate_rules(user_text, **kwargs),
    )


def _is_explicit_command_like(text: str) -> bool:
    return is_explicit_command_like(text)


def _determine_turn_direction(
    turns: list[tuple[str, str]],
    text: str,
    *,
    active_subject: str = "",
    pending_action: Optional[dict] = None,
) -> dict:
    return determine_turn_direction(
        turns,
        text,
        active_subject=active_subject,
        pending_action=pending_action,
        analyze_routing_text_fn=_analyze_routing_text,
        classify_turn_acts_fn=_classify_turn_acts,
        extract_memory_teach_text_fn=_extract_memory_teach_text,
        is_identity_or_developer_query_fn=_is_identity_or_developer_query,
        is_developer_color_lookup_request_fn=_is_developer_color_lookup_request,
        is_developer_bilingual_request_fn=_is_developer_bilingual_request,
        is_color_lookup_request_fn=_is_color_lookup_request,
        build_greeting_reply_fn=_build_greeting_reply,
        is_explicit_command_like_fn=_is_explicit_command_like,
    )


def _extract_animal_preferences(session_turns: list[tuple[str, str]]) -> list[str]:
    animals = []
    seen = set()
    for role, text in session_turns:
        if role != "user":
            continue
        t = (text or "").lower().strip()
        has_signal = any(s in t for s in ["i like", "i love", "i prefer", "favorite animal", "favourite animal"]) \
            or bool(re.search(r"\bi\s+(?:\w+\s+){0,3}like\b", t))
        if not has_signal:
            continue
        toks = re.findall(r"[a-z]{3,20}", t)
        for w in toks:
            if w not in KNOWN_ANIMALS:
                continue
            norm = "birds" if w in {"bird", "birds"} else ("dogs" if w in {"dog", "dogs"} else w)
            if norm in seen:
                continue
            seen.add(norm)
            animals.append(norm)
    return animals


def _extract_animal_preferences_from_text(text: str) -> list[str]:
    toks = re.findall(r"[a-z]{3,20}", (text or "").lower())
    out = []
    seen = set()
    for w in toks:
        if w not in KNOWN_ANIMALS:
            continue
        norm = "birds" if w in {"bird", "birds"} else ("dogs" if w in {"dog", "dogs"} else w)
        if norm in seen:
            continue
        seen.add(norm)
        out.append(norm)
    return out


def _extract_animal_preferences_from_memory() -> list[str]:
    if not mem_enabled():
        return []
    probe = mem_recall("what animals does the user like favorite animal preference")
    return _extract_animal_preferences_from_text(probe)


def _is_color_animal_match_question(user_text: str) -> bool:
    t = (user_text or "").lower()
    return ("what color" in t or "which color" in t) and ("animal" in t or "animals" in t) and any(
        k in t for k in ["match", "best", "goes", "fit", "fits"]
    )


def _pick_color_for_animals(colors: list[str], animals: list[str]) -> str:
    if not colors:
        return ""
    if len(colors) == 1:
        return colors[0]

    score = {c: 0 for c in colors}
    for c in colors:
        cl = c.lower()
        for a in animals:
            al = a.lower()
            if al in {"birds", "parrots", "eagles", "hawks"} and cl in {"red", "blue", "green", "yellow", "orange"}:
                score[c] += 2
            if al in {"dogs", "cats", "horses"} and cl in {"brown", "black", "white", "gray", "grey", "silver", "gold"}:
                score[c] += 1
    best = sorted(colors, key=lambda c: score.get(c, 0), reverse=True)
    return best[0]


def _is_color_lookup_request(user_text: str) -> bool:
    t = (user_text or "").lower()
    direct = [
        "what color do i like",
        "what colors do i like",
        "which color do i like",
        "which colors do i like",
        "color i like",
        "colors i like",
    ]
    if any(x in t for x in direct):
        return True
    if "go back" in t and "color" in t:
        return True
    if "past chat" in t and "color" in t:
        return True
    return False


# =========================
# Guard rails (files)
# =========================
def is_within_allowed(p: Path) -> bool:
    try:
        p.resolve().relative_to(allowed_root())
        return True
    except Exception:
        return False


def safe_path(user_path: str) -> Path:
    p = Path(user_path)
    if not p.is_absolute():
        p = (allowed_root() / p)
    p = p.resolve()
    if not is_within_allowed(p):
        raise PermissionError(f"Denied: outside allowed root: {allowed_root()}")
    return p


# =========================
# Ollama helpers
# =========================
def tcp_listening(host="127.0.0.1", port=11434, timeout=1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _live_ollama_calls_allowed() -> bool:
    argv_text = " ".join(str(arg or "") for arg in list(sys.argv or []))
    if "unittest" not in argv_text.lower():
        return True
    return str(os.environ.get("NOVA_ALLOW_LIVE_OLLAMA_TESTS") or "").strip().lower() in {"1", "true", "yes", "on"}


def ollama_api_up(timeout=2.0) -> bool:
    if not _live_ollama_calls_allowed():
        return False
    try:
        r = requests.get(f"{OLLAMA_BASE}/api/tags", timeout=timeout)
        return r.status_code == 200
    except Exception:
        return False


def start_ollama_serve_detached() -> bool:
    try:
        DETACHED = 0x00000008
        NEW_GROUP = 0x00000200
        subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=DETACHED | NEW_GROUP,
        )
        return True
    except Exception:
        return False


def kill_ollama() -> None:
    subprocess.run(["taskkill", "/F", "/IM", "ollama.exe"], capture_output=True, text=True)


def ensure_ollama_boot():
    if not _live_ollama_calls_allowed():
        return False
    if not tcp_listening():
        warn("Ollama not listening on 11434. Starting ollama serve...")
        start_ollama_serve_detached()

    if tcp_listening() and not ollama_api_up():
        warn("Ollama port open but API not responding. Restarting...")
        kill_ollama()
        time.sleep(1.2)
        start_ollama_serve_detached()

    for _ in range(OLLAMA_BOOT_RETRIES):
        if ollama_api_up():
            ok("Ollama API up")
            return True
        time.sleep(1)

    bad("Ollama API still down.")
    return False


def ensure_ollama():
    if not _live_ollama_calls_allowed():
        return
    if not tcp_listening():
        start_ollama_serve_detached()
    if tcp_listening() and not ollama_api_up():
        kill_ollama()
        time.sleep(1.0)
        start_ollama_serve_detached()
    for _ in range(10):
        if ollama_api_up():
            return
        time.sleep(0.5)


# =========================
# Knowledge packs (B-mode)
# =========================
def _tokenize(q: str):
    q = (q or "").lower()
    toks = re.findall(r"[a-z0-9]{3,}", q)
    if "peims" in q and "peims" not in toks:
        toks.append("peims")
    return list(dict.fromkeys(toks))[:25]


def kb_active_pack() -> Optional[str]:
    try:
        if ACTIVE_PACK_FILE.exists():
            name = ACTIVE_PACK_FILE.read_text(encoding="utf-8").strip()
            return name or None
    except Exception:
        pass
    return None


def kb_set_active(name: Optional[str]) -> str:
    KNOWLEDGE_ROOT.mkdir(parents=True, exist_ok=True)
    if not name:
        if ACTIVE_PACK_FILE.exists():
            ACTIVE_PACK_FILE.unlink(missing_ok=True)
        return "Knowledge pack disabled."
    (PACKS_DIR / name).mkdir(parents=True, exist_ok=True)
    ACTIVE_PACK_FILE.write_text(name, encoding="utf-8")
    return f"Active knowledge pack: {name}"


def kb_list_packs() -> str:
    PACKS_DIR.mkdir(parents=True, exist_ok=True)
    packs = [p.name for p in PACKS_DIR.iterdir() if p.is_dir()]
    packs.sort(key=str.lower)
    active = kb_active_pack()
    lines = []
    for p in packs:
        mark = "*" if active and p.lower() == active.lower() else " "
        lines.append(f"{mark} {p}")
    if not lines:
        return "No knowledge packs yet. (You can add one with: kb add <zip_path> <pack_name>)"
    return "Knowledge packs:\n" + "\n".join(lines)


def kb_add_zip(zip_path: str, pack_name: str) -> str:
    zpath = safe_path(zip_path) if not Path(zip_path).is_absolute() else Path(zip_path)
    if not zpath.exists() or not zpath.is_file():
        return f"Not a file: {zpath}"

    dest = PACKS_DIR / pack_name
    dest.mkdir(parents=True, exist_ok=True)

    exts = {".txt", ".md"}
    extracted = 0
    with zipfile.ZipFile(zpath, "r") as z:
        for member in z.infolist():
            if member.is_dir():
                continue
            name = Path(member.filename).name
            if Path(name).suffix.lower() not in exts:
                continue
            out = dest / name
            out.write_bytes(z.read(member))
            extracted += 1

    if extracted == 0:
        return "No .txt/.md files found in zip. (For now, keep packs as txt/md; we can add PDF parsing later.)"
    return f"Added {extracted} file(s) to knowledge pack: {pack_name}"


def _active_knowledge_root() -> Optional[Path]:
    pack = kb_active_pack()
    if not pack:
        return None
    root = PACKS_DIR / pack
    if not root.exists() or not root.is_dir():
        return None
    return root


def kb_search(query: str, max_files: int = KB_MAX_FILES, max_chars: int = KB_MAX_CHARS) -> str:
    pack = kb_active_pack()
    if not pack:
        return ""
    root = PACKS_DIR / pack
    if not root.exists():
        return ""

    toks = _tokenize(query)
    if not toks:
        return ""

    candidates = []
    exts = {".txt", ".md"}

    for p in root.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in exts:
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        low = text.lower()
        score = 0
        for t in toks:
            score += low.count(t)

        if score > 0:
            candidates.append((score, p, text))

    if not candidates:
        return ""

    candidates.sort(key=lambda x: x[0], reverse=True)
    picked = candidates[:max_files]

    blocks = []
    used = 0
    for score, path, text in picked:
        low = text.lower()
        idx = None
        for t in toks:
            j = low.find(t)
            if j != -1:
                idx = j
                break
        if idx is None:
            idx = 0

        start = max(0, idx - 250)
        end = min(len(text), idx + 950)
        snippet = text[start:end].strip().replace("\r\n", "\n")

        chunk = f"[FILE] {path.name} (score={score})\n{snippet}\n"
        if used + len(chunk) > max_chars:
            break
        blocks.append(chunk)
        used += len(chunk)

    if not blocks:
        return ""
    return f"REFERENCE (knowledge pack: {pack}):\n\n" + "\n---\n".join(blocks)


def _read_text_safely(path: Path) -> str:
    try:
        raw = path.read_bytes()
    except Exception:
        return ""

    for enc in ("utf-8", "utf-16", "utf-16-le", "utf-16-be"):
        try:
            txt = raw.decode(enc)
            if "\x00" in txt:
                continue
            if txt.strip():
                return txt
        except Exception:
            continue
    return ""


def _extract_key_lines(text: str, max_lines: int = 2) -> list[str]:
    out: list[str] = []
    for raw in (text or "").splitlines():
        s = re.sub(r"\s+", " ", (raw or "").strip().lstrip("-*•")).strip()
        if len(s) < 20:
            continue
        if s.lower().startswith("source:"):
            continue
        out.append(s.rstrip("."))
        if len(out) >= max(1, int(max_lines)):
            break
    return out


def _topic_tokens(text: str) -> list[str]:
    low = (text or "").lower()
    toks = re.findall(r"[a-z0-9]{3,}", low)
    stop = {
        "what", "when", "where", "which", "about", "could", "would", "should",
        "there", "their", "have", "your", "with", "from", "that", "this",
        "please", "tell", "more", "info", "information", "topic",
    }
    out: list[str] = []
    for tok in toks:
        if tok in stop:
            continue
        if tok not in out:
            out.append(tok)
    return out[:12]


def _extract_matching_lines(text: str, tokens: list[str], max_lines: int = 3) -> list[str]:
    if not tokens:
        return _extract_key_lines(text, max_lines=max_lines)
    out: list[str] = []
    for raw in (text or "").splitlines():
        s = re.sub(r"\s+", " ", (raw or "").strip().lstrip("-*•")).strip()
        if not s or len(s) < 14:
            continue
        low = s.lower()
        score = sum(1 for tok in tokens if tok in low)
        if score <= 0:
            continue
        out.append(s.rstrip("."))
        if len(out) >= max(1, int(max_lines)):
            break
    if out:
        return out
    return _extract_key_lines(text, max_lines=max_lines)


def _build_local_topic_digest_answer(query_text: str, max_files: int = 4, max_points: int = 10) -> str:
    q = (query_text or "").strip()
    if not q:
        return ""

    root = _active_knowledge_root()
    if root is None:
        return ""

    tokens = _topic_tokens(q)
    candidates = [p for p in root.glob("**/*.txt") if p.is_file()]
    if not candidates:
        return ""

    scored: list[tuple[int, Path, str]] = []
    for path in candidates:
        txt = _read_text_safely(path)
        if not txt:
            continue
        hay = (path.name + " " + txt[:5000]).lower()
        score = sum(2 if tok in path.name.lower() else 1 for tok in tokens if tok in hay)
        if score > 0:
            scored.append((score, path, txt))

    if not scored:
        return ""

    scored.sort(key=lambda item: item[0], reverse=True)
    top = scored[: max(1, int(max_files))]

    try:
        pack_name = root.relative_to(PACKS_DIR).as_posix()
    except Exception:
        pack_name = root.name

    lines = [f"I found relevant details in the active knowledge pack ({pack_name}):"]
    points = 0
    cited: set[str] = set()
    for _score, path, txt in top:
        key_lines = _extract_matching_lines(txt, tokens, max_lines=3)
        for key_line in key_lines:
            lines.append(f"- {key_line}.")
            points += 1
            cited.add(str(path.relative_to(BASE_DIR)).replace("\\", "/"))
            if points >= max(1, int(max_points)):
                break
        if points >= max(1, int(max_points)):
            break

    if points == 0:
        return ""

    for cited_path in sorted(cited):
        lines.append(f"[source: {cited_path}]")
    return "\n".join(lines)


def _is_local_knowledge_topic_query(text: str) -> bool:
    del text
    return False


def _is_peims_broad_query(text: str) -> bool:
    del text
    return False




# =========================
# Self patching (zip overlay + snapshot + rollback)
# =========================
def _log_patch(msg: str):
    UPDATES_DIR.mkdir(parents=True, exist_ok=True)
    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} | {msg}\n"
    PATCH_LOG.write_text(PATCH_LOG.read_text(encoding="utf-8") + line if PATCH_LOG.exists() else line, encoding="utf-8")


def _read_patch_revision() -> int:
    try:
        if not PATCH_REVISION_FILE.exists():
            return 0
        data = json.loads(PATCH_REVISION_FILE.read_text(encoding="utf-8"))
        return int(data.get("revision", 0) or 0)
    except Exception:
        return 0


def _write_patch_revision(revision: int, source: str):
    UPDATES_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "revision": int(revision),
        "source": source,
        "ts": time.time(),
    }
    PATCH_REVISION_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _snapshot_meta_path(snapshot_zip: Path) -> Path:
    return snapshot_zip.with_suffix(snapshot_zip.suffix + ".json")


def _write_snapshot_meta(snapshot_zip: Path, base_revision: int) -> None:
    meta = {
        "snapshot": snapshot_zip.name,
        "base_revision": int(base_revision),
        "ts": time.time(),
    }
    _snapshot_meta_path(snapshot_zip).write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def _detached_domain_reply(domain_name: str, suggested_query: str) -> str:
    pack = kb_active_pack()
    base = f"I don't have bundled {domain_name} guidance in this public repo."
    if pack:
        return f"{base} Try web research, or switch to a knowledge pack that contains {domain_name} material. Active knowledge pack: {pack}."
    return f"{base} Try: {suggested_query} or load a knowledge pack with kb add <zip_path> <pack_name>."


def _read_snapshot_meta(snapshot_zip: Path) -> Optional[dict]:
    p = _snapshot_meta_path(snapshot_zip)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _snapshot_current() -> Path:
    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    snap = SNAPSHOTS_DIR / f"snapshot_{ts}.zip"
    skip_dirs = {".venv", "runtime", "logs", "models", "updates", "__pycache__", "knowledge"}
    with zipfile.ZipFile(snap, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for p in BASE_DIR.rglob("*"):
            if p.is_dir():
                continue
            rel = p.relative_to(BASE_DIR)
            if rel.parts and rel.parts[0] in skip_dirs:
                continue
            if "__pycache__" in rel.parts:
                continue
            z.write(p, arcname=str(rel))
    _write_snapshot_meta(snap, _read_patch_revision())
    _log_patch(f"SNAPSHOT {snap.name}")
    return snap


def _overlay_zip(zip_path: Path) -> int:
    allowed_ext = {".py", ".json", ".md", ".txt", ".ps1", ".cmd"}
    blocked_prefix = {".git/", ".venv/", "runtime/", "logs/", "models/"}

    count = 0
    with zipfile.ZipFile(zip_path, "r") as z:
        for info in z.infolist():
            if info.is_dir():
                continue
            name = info.filename.replace("\\", "/").lstrip("/")
            if name == PATCH_MANIFEST_NAME:
                continue
            if any(name.startswith(bp) for bp in blocked_prefix):
                continue
            ext = Path(name).suffix.lower()
            if ext not in allowed_ext:
                continue
            out = BASE_DIR / name
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(z.read(info))
            count += 1

    return count


def _py_compile_check() -> Tuple[bool, str]:
    try:
        r = subprocess.run(
            [PYTHON, "-m", "compileall", str(BASE_DIR)],
            capture_output=True, text=True, timeout=1800
        )
        out = (r.stdout or "") + ("\n" + r.stderr if r.stderr else "")
        ok_ = (r.returncode == 0)
        return ok_, out.strip()
    except Exception as e:
        return False, str(e)


def _last_nonempty_line(text: str) -> str:
    for line in reversed(str(text or "").splitlines()):
        clean = str(line or "").strip()
        if clean:
            return clean
    return ""


def _read_patch_manifest(zip_path: Path) -> tuple[Optional[dict], Optional[str]]:
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            if PATCH_MANIFEST_NAME not in zf.namelist():
                return None, None
            raw = zf.read(PATCH_MANIFEST_NAME)
    except zipfile.BadZipFile:
        return None, "invalid patch zip."
    except Exception as e:
        return None, f"failed to read {PATCH_MANIFEST_NAME}: {e}"

    try:
        manifest = json.loads(raw.decode("utf-8"))
    except UnicodeDecodeError:
        return None, f"{PATCH_MANIFEST_NAME} must be UTF-8 JSON."
    except json.JSONDecodeError:
        return None, f"{PATCH_MANIFEST_NAME} is not valid JSON."

    if not isinstance(manifest, dict):
        return None, f"{PATCH_MANIFEST_NAME} must contain a JSON object."

    return manifest, None


def _behavioral_check_command(base_dir: Optional[Path] = None) -> list[str]:
    del base_dir
    return [PYTHON, "-m", "unittest", "discover", "-s", "tests", "-f"]


def _behavioral_check(*, base_dir: Optional[Path] = None, timeout_sec: Optional[int] = None) -> dict:
    workspace = Path(base_dir or BASE_DIR)
    tests_dir = workspace / "tests"
    timeout_value = timeout_sec
    if timeout_value is None:
        timeout_value = int(policy_patch().get("behavioral_check_timeout_sec", 600) or 600)
    timeout_value = max(1, int(timeout_value))
    command = _behavioral_check_command(workspace)

    if not tests_dir.exists():
        return {
            "ok": True,
            "ran": False,
            "skipped": True,
            "summary": "behavioral check skipped: tests directory not found",
            "output": "",
            "command": list(command),
            "cwd": str(workspace),
            "timeout_sec": timeout_value,
        }

    try:
        proc = subprocess.run(
            command,
            cwd=str(workspace),
            capture_output=True,
            text=True,
            timeout=timeout_value,
        )
        output = ((proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")).strip()
        summary = _last_nonempty_line(output) or f"exit:{proc.returncode}"
        return {
            "ok": proc.returncode == 0,
            "ran": True,
            "skipped": False,
            "summary": summary,
            "output": output,
            "command": list(command),
            "cwd": str(workspace),
            "timeout_sec": timeout_value,
        }
    except subprocess.TimeoutExpired as e:
        output = ((e.stdout or "") + ("\n" + e.stderr if e.stderr else "")).strip()
        return {
            "ok": False,
            "ran": True,
            "skipped": False,
            "summary": f"behavioral check timed out after {timeout_value}s",
            "output": output,
            "command": list(command),
            "cwd": str(workspace),
            "timeout_sec": timeout_value,
        }
    except Exception as e:
        return {
            "ok": False,
            "ran": False,
            "skipped": False,
            "summary": f"behavioral check failed to start: {e}",
            "output": str(e),
            "command": list(command),
            "cwd": str(workspace),
            "timeout_sec": timeout_value,
        }


def _read_patch_log_tail_line() -> str:
    try:
        if not PATCH_LOG.exists():
            return ""
        return _last_nonempty_line(PATCH_LOG.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return ""


def _preview_status_from_report(path: Path) -> str:
    try:
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.lower().startswith("status:"):
                return str(line.split(":", 1)[1] or "").strip()
    except Exception:
        return ""
    return ""


def patch_preview_summaries(limit: int = 40) -> list[dict]:
    try:
        previews = UPDATES_DIR / "previews"
        if not previews.exists():
            return []
        files = sorted(previews.glob("*.txt"), key=lambda p: p.stat().st_mtime, reverse=True)
        approvals = _read_approvals()
        approval_map = {}
        for item in approvals:
            if not isinstance(item, dict):
                continue
            preview = str(item.get("preview") or "").strip()
            if preview:
                approval_map[preview] = item
                approval_map[Path(preview).name] = item
        summaries = []
        for preview in files[: max(0, int(limit or 0))]:
            approval = approval_map.get(str(preview)) or approval_map.get(preview.name) or {}
            summaries.append({
                "name": preview.name,
                "path": str(preview),
                "status": _preview_status_from_report(preview),
                "decision": str(approval.get("decision") or "pending"),
                "mtime": int(preview.stat().st_mtime),
            })
        return summaries
    except Exception:
        return []


def patch_status_payload() -> dict:
    try:
        cfg = policy_patch()
        previews_dir = UPDATES_DIR / "previews"
        files = sorted(previews_dir.glob("*.txt"), key=lambda p: p.stat().st_mtime, reverse=True) if previews_dir.exists() else []
        approvals = _read_approvals()
        approval_map = {}
        for item in approvals:
            if not isinstance(item, dict):
                continue
            preview = str(item.get("preview") or "").strip()
            if preview:
                approval_map[preview] = item
                approval_map[Path(preview).name] = item

        previews_pending = 0
        previews_approved = 0
        previews_rejected = 0
        previews_eligible = 0
        previews_approved_eligible = 0
        last_preview_name = ""
        last_preview_status = ""
        last_preview_decision = ""
        if files:
            last_preview_name = files[0].name
            last_preview_status = _preview_status_from_report(files[0])
            last_preview_decision = str((approval_map.get(str(files[0])) or approval_map.get(files[0].name) or {}).get("decision") or "pending")
        for preview in files:
            decision = str((approval_map.get(str(preview)) or approval_map.get(preview.name) or {}).get("decision") or "pending").strip().lower()
            status_text = _preview_status_from_report(preview)
            if status_text.lower().startswith("eligible"):
                previews_eligible += 1
            if decision == "approved":
                previews_approved += 1
                if status_text.lower().startswith("eligible"):
                    previews_approved_eligible += 1
            elif decision == "rejected":
                previews_rejected += 1
            else:
                previews_pending += 1

        tests_available = (BASE_DIR / "tests").exists()
        behavioral_check = bool(cfg.get("behavioral_check", True))
        pipeline_ready = bool(cfg.get("enabled", True)) and bool(cfg.get("strict_manifest", True)) and behavioral_check and bool(tests_available)
        return {
            "ok": True,
            "enabled": bool(cfg.get("enabled", True)),
            "strict_manifest": bool(cfg.get("strict_manifest", True)),
            "allow_force": bool(cfg.get("allow_force", False)),
            "behavioral_check": behavioral_check,
            "behavioral_check_timeout_sec": int(cfg.get("behavioral_check_timeout_sec", 600) or 600),
            "tests_available": bool(tests_available),
            "pipeline_ready": pipeline_ready,
            "current_revision": _read_patch_revision(),
            "previews_total": len(files),
            "previews_pending": previews_pending,
            "previews_approved": previews_approved,
            "previews_rejected": previews_rejected,
            "previews_eligible": previews_eligible,
            "previews_approved_eligible": previews_approved_eligible,
            "last_preview_name": last_preview_name,
            "last_preview_status": last_preview_status,
            "last_preview_decision": last_preview_decision,
            "last_patch_log_line": _read_patch_log_tail_line(),
            "previews": patch_preview_summaries(40),
            "ready_for_validated_apply": pipeline_ready and previews_approved_eligible > 0,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _patch_reject_message(
    reason: str,
    *,
    strict_manifest: bool,
    current_revision: int,
    incoming_revision: Optional[int],
    required_base_revision: Optional[int],
) -> str:
    incoming_text = str(incoming_revision) if incoming_revision is not None else "missing"
    required_base_text = str(required_base_revision) if required_base_revision is not None else "not specified"
    strict_text = "on" if strict_manifest else "off"
    return (
        f"Patch rejected: {reason}\n"
        f"- incoming revision: {incoming_text}\n"
        f"- current revision: {current_revision}\n"
        f"- required base: {required_base_text}\n"
        f"- current base: {current_revision}\n"
        f"- strict mode: {strict_text}"
    )


def patch_apply(zip_path: str, force: bool = False) -> str:
    z = safe_path(zip_path) if not Path(zip_path).is_absolute() else Path(zip_path)
    if not z.exists() or not z.is_file():
        return f"Not a file: {z}"

    # Run a preview check first to avoid blind applies and write a preview report.
    try:
        preview_out = patch_preview(str(z), write_report=True)
        # Only proceed automatically if preview indicates eligible or force=True
        if not force and "Status: eligible" not in preview_out:
            # Try to return a structured rejection message consistent with previous behavior
            strict_manifest = bool(policy_patch().get("strict_manifest", True))
            current_revision = _read_patch_revision()
            manifest, manifest_err = _read_patch_manifest(z)
            if manifest_err:
                _log_patch(f"APPLY_REJECT invalid_manifest {z.name} err={manifest_err}")
                return _patch_reject_message(
                    manifest_err,
                    strict_manifest=strict_manifest,
                    current_revision=current_revision,
                    incoming_revision=None,
                    required_base_revision=None,
                )

            # parse incoming revision and min_base if present
            try:
                incoming_rev = int(manifest.get("patch_revision", 0) or 0)
            except Exception:
                incoming_rev = None
            try:
                min_base = int(manifest.get("min_base_revision", 0) or 0)
            except Exception:
                min_base = None

            if incoming_rev is not None and incoming_rev <= current_revision:
                _log_patch(f"APPLY_REJECT downgrade current={current_revision} next={incoming_rev} zip={z.name}")
                return _patch_reject_message(
                    "non-forward revision (downgrade blocked).",
                    strict_manifest=strict_manifest,
                    current_revision=current_revision,
                    incoming_revision=incoming_rev,
                    required_base_revision=min_base,
                )

            if min_base is not None and current_revision < min_base:
                _log_patch(f"APPLY_REJECT base_too_old current={current_revision} min_base={min_base} zip={z.name}")
                return _patch_reject_message(
                    "incompatible base state.",
                    strict_manifest=strict_manifest,
                    current_revision=current_revision,
                    incoming_revision=incoming_rev,
                    required_base_revision=min_base,
                )

            # Fallback: return preview output
            # If preview was written to disk, require an explicit local approval
            m = re.search(r"Preview written:\s*(.+)$", preview_out, flags=re.M)
            if m:
                preview_path = m.group(1).strip()
                # check approvals
                approved = False
                for a in _read_approvals():
                    if str(preview_path) == str(a.get("preview")) and a.get("decision") == "approved":
                        approved = True
                        break
                if not approved:
                    return (f"Patch rejected: preview check failed. A preview was generated at {preview_path} and requires local approval before applying.\n\nPreview output:\n{preview_out}\n\n"
                            "Approve with: patch approve <preview_filename>\nOr re-run with --force to override.")

            return (f"Patch rejected: preview check failed.\n\nPreview output:\n{preview_out}\n\n"
                    "If you really want to apply anyway, re-run with: patch apply <zip_path> --force")
    except Exception:
        # If preview fails unexpectedly, block apply unless forced
        if not force:
            return "Patch preview failed; aborting apply. Use --force to override."

    strict_manifest = bool(policy_patch().get("strict_manifest", True))
    current_revision = _read_patch_revision()
    manifest, manifest_err = _read_patch_manifest(z)
    if manifest_err:
        _log_patch(f"APPLY_REJECT invalid_manifest {z.name} err={manifest_err}")
        return _patch_reject_message(
            manifest_err,
            strict_manifest=strict_manifest,
            current_revision=current_revision,
            incoming_revision=None,
            required_base_revision=None,
        )

    next_revision = None
    if manifest is None:
        if strict_manifest:
            _log_patch(f"APPLY_REJECT missing_manifest {z.name}")
            return _patch_reject_message(
                f"missing {PATCH_MANIFEST_NAME}. Include patch_revision > current revision.",
                strict_manifest=strict_manifest,
                current_revision=current_revision,
                incoming_revision=None,
                required_base_revision=None,
            )
    else:
        try:
            next_revision = int(manifest.get("patch_revision", 0) or 0)
        except Exception:
            _log_patch(f"APPLY_REJECT bad_revision {z.name}")
            return _patch_reject_message(
                "manifest field 'patch_revision' must be an integer.",
                strict_manifest=strict_manifest,
                current_revision=current_revision,
                incoming_revision=None,
                required_base_revision=None,
            )

        try:
            min_base = int(manifest.get("min_base_revision", 0) or 0)
        except Exception:
            _log_patch(f"APPLY_REJECT bad_min_base {z.name}")
            return _patch_reject_message(
                "manifest field 'min_base_revision' must be an integer when provided.",
                strict_manifest=strict_manifest,
                current_revision=current_revision,
                incoming_revision=next_revision,
                required_base_revision=None,
            )

        if next_revision <= current_revision:
            _log_patch(f"APPLY_REJECT downgrade current={current_revision} next={next_revision} zip={z.name}")
            return _patch_reject_message(
                "non-forward revision (downgrade blocked).",
                strict_manifest=strict_manifest,
                current_revision=current_revision,
                incoming_revision=next_revision,
                required_base_revision=min_base,
            )
        if current_revision < min_base:
            _log_patch(f"APPLY_REJECT base_too_old current={current_revision} min_base={min_base} zip={z.name}")
            return _patch_reject_message(
                "incompatible base state.",
                strict_manifest=strict_manifest,
                current_revision=current_revision,
                incoming_revision=next_revision,
                required_base_revision=min_base,
            )

    snap = _snapshot_current()
    _log_patch(f"APPLY {z.name} current_rev={current_revision} next_rev={next_revision if next_revision is not None else 'unversioned'}")

    n = _overlay_zip(z)
    if n == 0:
        _log_patch("APPLY no files overlayed")
        return "Patch zip contained no eligible files to apply."

    ok_compile, out = _py_compile_check()
    if not ok_compile:
        _log_patch("COMPILE_FAIL -> rollback")
        patch_rollback(str(snap))
        return "Patch applied, but compile check failed. Rolled back.\n\nCompile output:\n" + out[-3500:]

    patch_cfg = policy_patch()
    behavioral_enabled = bool(patch_cfg.get("behavioral_check", True))
    behavior_result = {
        "ok": True,
        "ran": False,
        "skipped": True,
        "summary": "behavioral check disabled by policy",
        "output": "",
    }
    if behavioral_enabled:
        behavior_result = _behavioral_check(
            timeout_sec=int(patch_cfg.get("behavioral_check_timeout_sec", 600) or 600),
        )
        if not bool(behavior_result.get("ok")):
            summary = str(behavior_result.get("summary") or "behavioral check failed")
            _log_patch(f"BEHAVIOR_FAIL {summary} -> rollback")
            patch_rollback(str(snap))
            output = str(behavior_result.get("output") or "").strip()
            msg = "Patch applied, but behavioral check failed. Rolled back.\n\nBehavioral summary:\n" + summary
            if output:
                msg += "\n\nBehavioral output:\n" + output[-3500:]
            return msg
        if bool(behavior_result.get("skipped")):
            _log_patch(f"BEHAVIOR_SKIP {str(behavior_result.get('summary') or '').strip()}")
        else:
            _log_patch(f"BEHAVIOR_OK {str(behavior_result.get('summary') or '').strip()}")
    else:
        _log_patch("BEHAVIOR_SKIP disabled_by_policy")

    if next_revision is not None:
        _write_patch_revision(next_revision, source=z.name)

    _log_patch(f"APPLY_OK files={n}")
    rev_msg = f" Revision: {next_revision}." if next_revision is not None else ""
    behavior_msg = ""
    if behavioral_enabled:
        behavior_msg = f" Behavioral check OK ({str(behavior_result.get('summary') or 'passed')})."
    else:
        behavior_msg = " Behavioral check skipped by policy."
    return f"Patch applied: {n} file(s). Compile check OK.{behavior_msg} Snapshot: {snap.name}.{rev_msg}"


def patch_rollback(snapshot_zip: Optional[str] = None) -> str:
    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    snaps = sorted(SNAPSHOTS_DIR.glob("snapshot_*.zip"), key=lambda p: p.name, reverse=True)
    if snapshot_zip:
        snap = Path(snapshot_zip)
        if not snap.is_absolute():
            snap = SNAPSHOTS_DIR / snapshot_zip
    else:
        snap = snaps[0] if snaps else None

    if not snap or not snap.exists():
        return "No snapshot found to rollback."

    _log_patch(f"ROLLBACK {snap.name}")

    with zipfile.ZipFile(snap, "r") as z:
        for info in z.infolist():
            if info.is_dir():
                continue
            out = BASE_DIR / info.filename
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(z.read(info))

    meta = _read_snapshot_meta(snap)
    if meta and "revision" in meta:
        try:
            _write_patch_revision(int(meta.get("revision", 0) or 0), source=f"rollback:{snap.name}")
        except Exception:
            pass

    ok_compile, out = _py_compile_check()
    if not ok_compile:
        return "Rollback completed, but compile check still failing.\n\nCompile output:\n" + out[-3500:]
    return f"Rollback completed from snapshot: {snap.name}"


def patch_preview(zip_path: str, write_report: bool = False) -> str:
    """Preview a patch zip against the current repo.
    - lists manifest info (patch_revision, min_base_revision)
    - lists added / changed / skipped files
    - provides a short diff summary for text files
    If `write_report` is True, writes a preview text into UPDATES_DIR/previews/.
    """
    z = safe_path(zip_path) if not Path(zip_path).is_absolute() else Path(zip_path)
    if not z.exists() or not z.is_file():
        return f"Not found: {z}"

    manifest, manifest_err = _read_patch_manifest(z)
    if manifest_err:
        manifest = None

    current_revision = _read_patch_revision()
    patch_rev = None
    min_base = None
    try:
        if manifest:
            patch_rev = int(manifest.get("patch_revision", 0) or 0)
            min_base = int(manifest.get("min_base_revision", 0) or 0)
    except Exception:
        pass

    # decide skipped prefixes and text extensions
    skip_prefixes = (".git/", "runtime/", "logs/", "updates/", "piper/", "models/", "pkgconfig/")
    text_ext = {".py", ".md", ".txt", ".json", ".rst", ".yaml", ".yml", ".ini", ".cfg", ".html", ".css", ".js", ".csv"}

    added = []
    changed = []
    skipped = []
    diffs = {}

    with tempfile.TemporaryDirectory() as td:
        with zipfile.ZipFile(z, "r") as zz:
            members = [m for m in zz.infolist() if not m.is_dir()]
            for m in members:
                fn = m.filename.replace("\\", "/")
                # skip obvious runtime artifacts
                if any(fn.startswith(p) for p in skip_prefixes):
                    skipped.append(fn)
                    continue

                # target path in repo
                target = BASE_DIR / fn

                # extract member to tempdir
                try:
                    zz.extract(m, path=td)
                except Exception:
                    skipped.append(fn)
                    continue

                src = Path(td) / fn
                if not src.exists():
                    skipped.append(fn)
                    continue

                if target.exists():
                    # compare
                    try:
                        if src.suffix.lower() in text_ext:
                            a = target.read_text(encoding="utf-8", errors="ignore").splitlines()
                            b = src.read_text(encoding="utf-8", errors="ignore").splitlines()
                            if a != b:
                                changed.append(fn)
                                ud = difflib.unified_diff(a, b, fromfile=str(target), tofile=str(z.name + ":" + fn), lineterm="")
                                diffs[fn] = "\n".join(list(ud)[:400])
                        else:
                            # binary or unknown - mark changed if bytes differ
                            if target.read_bytes() != src.read_bytes():
                                changed.append(fn)
                    except Exception:
                        changed.append(fn)
                else:
                    added.append(fn)

    # prepare summary
    status = "eligible"
    if patch_rev is not None:
        if patch_rev <= current_revision:
            status = "rejected: non-forward revision"
        elif min_base is not None and current_revision < min_base:
            status = "rejected: incompatible base revision"

    lines = []
    lines.append("Patch Preview")
    lines.append("-------------")
    lines.append(f"Zip: {z.name}")
    lines.append(f"Patch revision: {patch_rev if patch_rev is not None else 'unknown'}")
    lines.append(f"Min base revision: {min_base if min_base is not None else 'not specified'}")
    lines.append(f"Current revision: {current_revision}")
    lines.append(f"Status: {status}")
    lines.append("")

    if changed:
        lines.append("Changed files:")
        for c in changed:
            lines.append(f"- {c}")
        lines.append("")

    if added:
        lines.append("Added files:")
        for a in added:
            lines.append(f"- {a}")
        lines.append("")

    if skipped:
        lines.append("Skipped files:")
        for s in skipped[:50]:
            lines.append(f"- {s}")
        if len(skipped) > 50:
            lines.append(f"- ... and {len(skipped)-50} more")
        lines.append("")

    lines.append("Diff summary:")
    if diffs:
        for fn, d in diffs.items():
            lines.append(f"- {fn}: modified")
            lines.append("```")
            lines.append(d)
            lines.append("```")
    else:
        lines.append("- No text diffs available or all changes are binary/non-text")

    out = "\n".join(lines)

    if write_report:
        try:
            previews = UPDATES_DIR / "previews"
            previews.mkdir(parents=True, exist_ok=True)
            ts = time.strftime("%Y%m%d_%H%M%S")
            fn = previews / f"preview_{ts}_{z.name}.txt"
            fn.write_text(out, encoding="utf-8")
            out = out + f"\n\nPreview written: {fn}"
        except Exception:
            pass

    return out


# -------------------------
# Preview approval helpers
# -------------------------
def _approvals_file() -> Path:
    p = UPDATES_DIR / "approvals.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _read_approvals() -> list[dict]:
    p = _approvals_file()
    if not p.exists():
        return []
    out = []
    try:
        with open(p, "r", encoding="utf-8") as f:
            for ln in f:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    out.append(json.loads(ln))
                except Exception:
                    continue
    except Exception:
        return []
    return out


def _record_approval(preview_path: str, decision: str, user: Optional[str] = None, note: str = "") -> bool:
    rec = {
        "ts": int(time.time()),
        "preview": str(preview_path),
        "decision": decision,
        "user": user or (get_active_user() or "unknown"),
        "note": note,
    }
    try:
        with open(_approvals_file(), "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return True
    except Exception:
        return False


def list_previews() -> str:
    previews = UPDATES_DIR / "previews"
    if not previews.exists():
        return "No previews found."
    files = sorted(previews.glob("*.txt"), key=lambda p: p.stat().st_mtime, reverse=True)
    approvals = _read_approvals()
    mapping = {a.get("preview"): a for a in approvals}
    lines = []
    for p in files:
        status = "pending"
        ap = mapping.get(str(p)) or mapping.get(p.name)
        if ap:
            status = ap.get("decision", "pending")
        lines.append(f"- {p.name}  [{status}]")
    return "\n".join(lines)


def show_preview(path_or_name: str) -> str:
    previews = UPDATES_DIR / "previews"
    p = Path(path_or_name)
    if not p.is_absolute():
        p = previews / path_or_name
    if not p.exists():
        return f"Preview not found: {p}"
    try:
        return p.read_text(encoding="utf-8")
    except Exception as e:
        return f"Failed to read preview: {e}"


def approve_preview(path_or_name: str, note: str = "") -> str:
    previews = UPDATES_DIR / "previews"
    p = Path(path_or_name)
    if not p.is_absolute():
        p = previews / path_or_name
    if not p.exists():
        return f"Preview not found: {p}"
    ok = _record_approval(str(p), "approved", user=get_active_user(), note=note)
    return "Approved." if ok else "Failed to record approval."


def reject_preview(path_or_name: str, note: str = "") -> str:
    previews = UPDATES_DIR / "previews"
    p = Path(path_or_name)
    if not p.is_absolute():
        p = previews / path_or_name
    if not p.exists():
        return f"Preview not found: {p}"
    ok = _record_approval(str(p), "rejected", user=get_active_user(), note=note)
    return "Rejected." if ok else "Failed to record rejection."


def interactive_preview_review(preview_path: str) -> str:
    """TTY-only interactive review loop for a preview file.
    Options: approve, reject, view, cancel
    Records decision to approvals log.
    Returns a short status message.
    """
    try:
        import sys
        p = Path(preview_path)
        if not p.exists():
            return f"Preview not found: {p}"
        # show concise header
        header = p.name
        # read first ~2000 chars of preview for quick summary
        text = p.read_text(encoding="utf-8")
        summary = "\n".join(text.splitlines()[:40])
        print("\nProposal review:\n", flush=True)
        print(f"Name: {header}")
        # try to extract patch revision line
        mrev = re.search(r"Patch revision:\s*(.+)$", text, flags=re.M)
        if mrev:
            print(f"Revision: {mrev.group(1).strip()}")
        # list changed/added counts
        changed = re.findall(r"^Changed files:\s*$", text, flags=re.M)
        # print short summary
        print("Files / diff preview (first lines):")
        print(summary)

        while True:
            try:
                resp = input('\nDecision? (approve/reject/view/cancel): ').strip().lower()
            except EOFError:
                return "No interactive input; review aborted."
            if resp in {"approve", "a"}:
                ok = _record_approval(str(p), "approved", user=get_active_user())
                return "Approved." if ok else "Failed to record approval."
            if resp in {"reject", "r"}:
                ok = _record_approval(str(p), "rejected", user=get_active_user())
                return "Rejected." if ok else "Failed to record rejection."
            if resp in {"view", "v"}:
                print('\n---- Full preview ----\n')
                print(text)
                print('\n---- End preview ----\n')
                continue
            if resp in {"cancel", "c", "quit", "q"}:
                return "Review canceled."
            print("Unknown response. Enter 'approve', 'reject', 'view', or 'cancel'.")
    except Exception as e:
        return f"Interactive review failed: {e}"


def _interactive_patch_review_enabled() -> bool:
    raw = str(os.environ.get("NOVA_INTERACTIVE_PATCH_REVIEW") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


# =========================
# Deterministic answers & hallucination filters
# =========================
def hard_answer(user_text: str) -> Optional[str]:
    t = (user_text or "").strip().lower()
    t = re.sub(r"\byor\b", "your", t)

    arithmetic_reply = _arithmetic_expression_reply(user_text)
    if arithmetic_reply:
        return arithmetic_reply

    assistant_name = get_learned_fact("assistant_name", "Nova")
    developer_name = get_learned_fact("developer_name", "Gustavo")
    if str(developer_name or "").strip().lower() == "gustavo":
        developer_name = "Gustavo Uribe"
    developer_nickname = get_learned_fact("developer_nickname", "Gus")
    active_user_raw = (get_active_user() or "").strip()
    active_user = active_user_raw.lower()

    if (
        re.search(r"\b(what\s+is|what'?s)\s+your\s+name\b", t)
        or re.search(r"\bwho\s+are\s+you\b", t)
        or re.search(r"\bare\s+\w*ou\s+sure\b.*\bname\b", t)
    ):
        return f"My name is {assistant_name}."

    if _is_self_identity_web_challenge(t):
        return _self_identity_web_challenge_reply()

    if bool(re.fullmatch(r"how\s+are\s+you\??", t)):
        return "I'm doing well, thanks for asking."

    if any(q in t for q in ["do you remember me", "do you know me"]):
        if _speaker_matches_developer():
            if developer_nickname and developer_nickname.lower() != developer_name.lower():
                return f"Yes. I remember you as {developer_name}, and you also go by {developer_nickname}."
            return f"Yes. I remember you as {developer_name}."
        if active_user_raw:
            return f"I remember your current session identity as {active_user_raw}. I do not have more verified personal facts yet."
        return "Uncertain. I do not have a verified user identity bound for this session yet."

    if re.search(r"\b(what\s+is|what'?s)\s+my\s+name\b", t) or "do you know my name" in t:
        if _speaker_matches_developer():
            return f"Your name is {developer_name}."
        if active_user_raw:
            return f"The only verified name I have for you in this session is {active_user_raw}."
        return "Uncertain. I do not have a verified name for you yet."

    why_name_query = (
        (("why are you called" in t) and "nova" in t)
        or (("why is your name" in t) and "nova" in t)
        or bool(re.search(r"\bwhy\s+your\s+called\s+nova\b", t))
        or bool(re.search(r"\bwhy\s+.*\bcalled\s+nova\b", t))
    )
    if why_name_query:
        story = get_name_origin_story().strip()
        if story:
            low_story = story.lower()
            if "was given its name" in low_story and "creator" in low_story:
                return story
            return f"{assistant_name} was given its name by its creator, {developer_nickname}. {story}"
        return "I do not have a saved name-origin story yet. You can teach me with: remember this ..."

    full_story_query = (
        "full story behind your name" in t
        or "tell me the full story behind your name" in t
        or ("full story" in t and "name" in t)
    )
    if full_story_query:
        story = get_name_origin_story().strip()
        if story:
            return story
        return "I do not have a saved full name-origin story yet. You can teach me with: remember this ..."

    if (
        "if you could name yourself" in t
        or "what name would you give yourself" in t
        or "if you had to rename yourself" in t
    ):
        return f"I would keep the name {assistant_name}."

    if "would you like to know the story behind your name" in t:
        return "Yes. Please share it, and I will remember it."

    if "where your name comes from" in t or "where your name came from" in t:
        story = get_name_origin_story().strip()
        if story:
            return story
        return "I do not have a saved name-origin story yet. You can teach me with: remember this ..."

    if "who gave you that name" in t or "who gave you your name" in t:
        return _prefix_from_earlier_memory(f"My name was given by my developer, {developer_name} ({developer_nickname}).")

    creator_query = (
        bool(re.search(r"\bwho\s+is\s+your\s+creator\b", t))
        or bool(re.search(r"\bwho\s+made\s+you\b", t))
        or bool(re.search(r"\bwho\s+created\s+you\b", t))
        or bool(re.search(r"\bso\s+gus\s+is\s+your\s+creator\b", t))
        or bool(re.search(r"\bis\s+(?:gus|gustavo)\s+your\s+creator\b", t))
    )
    if creator_query:
        if developer_nickname and developer_nickname.lower() != developer_name.lower():
            return _prefix_from_earlier_memory(f"My creator is {developer_name}. He created me. {developer_nickname} is his nickname.")
        return _prefix_from_earlier_memory(f"My creator is {developer_name}. He created me.")

    if any(q in t for q in ["what do you know about me", "what else do you know about me", "what do you remember about me"]):
        facts = []
        if _speaker_matches_developer():
            facts.append(f"You are {developer_name}.")
            if developer_nickname and developer_nickname.lower() != developer_name.lower():
                facts.append(f"You also go by {developer_nickname}.")
            colors = _extract_developer_color_preferences_from_memory()
            if colors:
                if len(colors) == 1:
                    facts.append(f"Your known favorite color is {colors[0]}.")
                else:
                    facts.append("Your known favorite colors are " + ", ".join(colors[:-1]) + f", and {colors[-1]}.")
            story = get_name_origin_story().strip()
            if story:
                facts.append("You gave me the name Nova.")
            if facts:
                return " ".join(facts)
        if active_user_raw:
            return f"I have one verified personal fact for this session: your name is {active_user_raw}. I do not have enough other structured personal facts yet."
        return "Uncertain. I do not have enough structured personal facts yet."

    if (
        "just knowing my name" in t
        or ("find out more" in t and "my name" in t)
        or ("know more about me" in t and "my name" in t)
    ):
        if _speaker_matches_developer():
            return (
                f"No. Knowing your name alone does not justify inventing more personal facts about you. "
                f"I should only state verified facts I actually learned, such as that you are {developer_name}."
            )
        if active_user_raw:
            return (
                f"No. Knowing the name {active_user_raw} alone is not enough for me to claim more personal facts. "
                "I should only use verified facts you explicitly gave me."
            )
        return "No. A name alone is not enough for me to claim personal facts. I should only use verified facts you explicitly gave me."

    my_full_name_query = (
        "my full name" in t
        or bool(re.search(r"\bif i am\s+gus\b.*\bfull name\b", t))
    )
    if my_full_name_query:
        developer_name_low = developer_name.lower()
        developer_nickname_low = developer_nickname.lower()
        if developer_name and (
            "i am gus" in t
            or (active_user and active_user in {developer_nickname_low, developer_name_low})
            or (developer_nickname_low and developer_nickname_low in t)
        ):
            return f"Your full name is {developer_name}."

    if "full name" in t and any(k in t for k in ["developer", "creator", "his", "gus", "nickname"]):
        if developer_nickname and developer_nickname.lower() != developer_name.lower():
            return _prefix_from_earlier_memory(f"My developer's full name is {developer_name}. {developer_nickname} is his nickname.")
        return _prefix_from_earlier_memory(f"My developer's full name is {developer_name}.")

    if any(k in t for k in ["what are your abilities", "what are you capable", "know what your capable", "know what you're capable", "what can you do"]):
        return describe_capabilities()

    if t in {
        "what have you learned from me",
        "what have you learned from me?",
        "what did you learn from me",
        "what did you learn from me?",
        "show me what you've learned",
        "show me what you have learned",
    }:
        learned_items = mem_get_recent_learned(5)
        if not learned_items:
            return "I haven't learned anything specific from you recently."
        return "Here's what I've learned from you recently:\n- " + "\n- ".join(learned_items)

    if t in {"can you code", "can you code?", "do you code", "do you code?"}:
        return ("Yes. I can write code, debug it, and explain it. "
                "I just can’t scan your machine or execute system actions unless you trigger an explicit tool command.")

    if "scan my machine" in t or "scan my computer" in t or "run a scan" in t or "nmap" in t:
        return ("No. I can’t scan your machine or run tools like nmap by myself. "
                "Tell me what you want checked and I’ll give you safe commands to run, then paste the output and I’ll interpret it.")

    return None


def sanitize_llm_reply(reply: str, tool_context: str = "") -> str:
    r = (reply or "").strip()
    low = r.lower()

    # Block obviously fabricated system-scan language.
    scan_patterns = [
        r"starting nmap",
        r"nmap scan report",
        r"c:\\>nmap",
        r"host is up",
        r"port\s+state\s+service",
        r"i'm running a system scan",
        r"scan report for",
    ]
    for p in scan_patterns:
        if re.search(p, low):
            return ("I didn’t run any scans or system commands. I won’t fabricate scan outputs. "
                    "If you want a scan, run the tool and paste the real output and I’ll interpret it.")

    # Prevent ungrounded weather success claims when no structured weather output exists.
    if re.search(r"\bi\s+(?:fetched|retrieved|got)\s+(?:the\s+)?weather", low):
        tc = (tool_context or "").lower()
        if "weather for" not in tc and "source: wttr.in" not in tc:
            return _weather_unavailable_message()

    weather_promise_patterns = [
        r"i(?:'| wi)?ll try to find out(?: the weather)?",
        r"let me check(?: the weather)?",
        r"i can try to find out(?: the weather)?",
        r"i(?:'| wi)?ll check(?: the weather)?",
        r"i(?:'| a)m going to check(?: the weather)?",
    ]
    if any(k in low for k in ("weather", "rain", "forecast")):
        tc = (tool_context or "").lower()
        if "weather for" not in tc and "source: wttr.in" not in tc:
            for pattern in weather_promise_patterns:
                if re.search(pattern, low):
                    return "I haven't actually run the weather tool yet. Tell me what location to use, or ask for our current location if I already have it saved."

    # Enforce explicit TOOL citation when assistant appears to reference tool-produced artifacts.
    strong_patterns = [
        r"\bsaved\s+to\b",
        r"\bdownloaded\b",
        r"\bpatch\s+appl(?:y|ied)\b",
        r"\bsnapshot(?:_[\w\-]+)?\b",
        r"\b(?:created|wrote)\s+(?:file|folder|directory)\b",
        r"\b(?:/|\\)[\w\-\.\/]+\.[a-z0-9]{1,6}\b",
    ]

    def _needs_citation(text_lower: str) -> bool:
        return any(re.search(p, text_lower) for p in strong_patterns)

    if _needs_citation(low):
        if "[tool:" not in low and "[tool:" not in r.lower():
            return ("I can’t claim tool outputs unless I include an explicit TOOL citation. "
                    "Please run the tool and paste its output or enable tool access; I won't fabricate results.")

    # Verify any [TOOL:...] citations are grounded in the provided tool context.
    cited = re.findall(r"\[TOOL:([a-zA-Z0-9_\-]+)\]", r)
    if cited:
        tc = (tool_context or "").lower()
        bad_found = False
        for name in cited:
            token = f"[tool:{name.lower()}]"
            if token not in tc:
                bad_found = True
        if bad_found:
            cleaned = re.sub(r"\[TOOL:[^\]]+\]", "", r).strip()
            cleaned = re.sub(r"\s+", " ", cleaned).strip()
            if cleaned:
                return cleaned
            return ("I can’t claim tool outputs unless they come from a real tool run in this chat. "
                    "I won’t fabricate TOOL citations.")

    # --- Additional UX rules to strip auto-offer phrases, unsolicited links, and ungrounded capability claims ---
    # Remove sentences that offer help unsolicitedly (unless we have tool context)
    offer_patterns = [
        r"how can i (help|assist)",
        r"would you like me to",
        r"do you want me to",
        r"\bi can (help|assist)\b",
        r"i(?:'| i)?ll start (?:research|researching)",
        r"i will start (?:research|researching)",
        r"i(?:'| i)?ll research",
        r"i will research",
        # remove terse "retrieving ..." or similar interim-status sentences when no tool ran
        r"\bretriev(?:ing|e)?\b",
    ]

    def _sentence_filter(text: str) -> str:
        parts = re.split(r'(?<=[.!?])\s+', text)
        out = []
        for s in parts:
            low_s = s.lower()
            skip = False
            for p in offer_patterns:
                if re.search(p, low_s):
                    # if tool_context contains some tool token, keep; else skip
                    if not (tool_context or ""):  # no tool context
                        skip = True
                        break
            if not skip:
                out.append(s)
        return " ".join(out).strip()

    # Remove sentences that promise future research or actions unless a tool ran
    research_patterns = [
        r"i\s*(?:'| i)?ll (?:research|look into|investigate|start researching|go research)",
        r"i will (?:research|look into|investigate|start researching|go research)",
        r"i(?:'| i)?m going to (?:research|look into|investigate)",
    ]

    def _remove_research_promises(text: str) -> str:
        parts = re.split(r'(?<=[.!?])\s+', text)
        out = []
        for s in parts:
            low_s = s.lower()
            skip = False
            for p in research_patterns:
                if re.search(p, low_s):
                    if not (tool_context or ""):
                        skip = True
                        break
            if not skip:
                out.append(s)
        return " ".join(out).strip()

    filtered = _sentence_filter(r)
    filtered = _remove_research_promises(filtered)

    # Remove raw URLs unless a TOOL citation is present or user requested sources
    if re.search(r"https?://", filtered) and not (tool_context or ""):
        # strip URLs
        filtered = re.sub(r"https?://\S+", "[link removed]", filtered)

    # If the assistant claims 'I can <action>' for capabilities, replace with known capabilities list
    cap_match = re.search(r"\bi can (fetch|browse|search|lookup|open|download|run|apply|patch|install|scan)\b", filtered or "", flags=re.I)
    if cap_match:
        caps = describe_capabilities()
        return caps

    filtered = filtered.strip()
    if not filtered:
        # fallback to short acknowledgement
        return "Okay."

    return filtered


def _strip_mem_leak(reply: str, mem_block: str) -> str:
    """Remove raw memory dump snippets from a model reply for user-facing output.
    If mem_block appears verbatim in reply, strip it. Also remove any leading
    'MEMORY RECALL' markers and lines that look like audit dumps.
    """
    out = (reply or "")
    try:
        if mem_block:
            out = out.replace(mem_block, "")
        # remove visible MEMORY RECALL header lines (standalone or inline)
        out = re.sub(r"(?i)memory\s*recall:\s*", "", out)
        # remove audit style separators and score lines
        out = re.sub(r"(?m)^--- score=.*?---\s*$", "", out)
        # collapse multiple blank lines
        out = re.sub(r"\n{3,}", "\n\n", out)
        return out.strip()
    except Exception:
        return reply


def format_tool_citation(tool: str, tool_output: str) -> str:
    """
    Return a TOOL citation line when a tool output contains a saved path.
    Keeps citation formatting centralized so other code can reuse it.
    """
    try:
        if not isinstance(tool_output, str):
            return ""
        m = re.search(r"Saved:\s*(\S+)", tool_output)
        if m:
            return f"[TOOL:{tool}] {m.group(1)}\n"
    except Exception:
        pass
    return ""


def _ensure_reply(reply: Optional[str]) -> str:
    """Guarantee a non-empty user-facing reply."""
    try:
        r = (reply or "")
        if not r or not r.strip():
            return "Okay."
        return r
    except Exception:
        return "Okay."


def _normalize_location_preview(preview: str) -> str:
    """Normalize stored location previews into a clean canonical sentence fragment."""
    if not preview:
        return preview
    p = preview.strip()
    # remove common leading phrases
    p = re.sub(r'^(?:my|your)(?: full| current| physical)? location is\s*:?', '', p, flags=re.I).strip()
    p = re.sub(r'^you are located in\s*', '', p, flags=re.I).strip()
    p = re.sub(r'^i am located in\s*', '', p, flags=re.I).strip()
    p = re.sub(r'^location\s*:\s*', '', p, flags=re.I).strip()
    # remove duplicate leading 'my' artifacts
    p = re.sub(r'^my\s+', '', p, flags=re.I).strip()
    p = re.sub(r'^your\s+', '', p, flags=re.I).strip()
    # collapse whitespace and stray punctuation
    p = re.sub(r'\s+', ' ', p).strip()
    p = p.rstrip('.')
    p = p.strip()
    return p


def _clamp_language_mix(value: Any) -> int:
    try:
        return max(0, min(100, int(value)))
    except Exception:
        return 0


def _estimate_spanish_ratio(text: str) -> float:
    """Estimate Spanish content from Unicode character profile only — no keyword lists."""
    raw = str(text or "")
    if not raw.strip():
        return 0.0
    # Spanish-specific characters not naturally present in standard English text.
    # Using character-level evidence avoids keyword-trigger brittleness.
    spanish_chars = set("áéíóúüñÁÉÍÓÚÜÑ¿¡")
    letter_count = sum(1 for c in raw if c.isalpha())
    if letter_count == 0:
        return 0.0
    accent_count = sum(1 for c in raw if c in spanish_chars)
    # Accented chars are a strong signal; scale so ~12% accent ratio → 1.0
    return min(1.0, float(accent_count) / max(1, letter_count) * 8.0)


def _auto_adjust_language_mix(current_mix: int, user_text: str) -> int:
    current = _clamp_language_mix(current_mix)
    observed = int(round(_estimate_spanish_ratio(user_text) * 100.0))
    # No guardrails: always nudge toward observed user language blend.
    return _clamp_language_mix(int(round((current * 0.7) + (observed * 0.3))))


def _language_mix_instruction(spanish_pct: int) -> str:
    mix = _clamp_language_mix(spanish_pct)
    if mix <= 0:
        return (
            "Language preference:\n"
            "- Default to English.\n"
            "- Keep the response natural and concise."
        )

    eng_pct = 100 - mix
    return (
        "Language preference:\n"
        "- Default to English, but adapt to user style.\n"
        f"- Target approx {eng_pct}% English and {mix}% Spanish (natural Spanglish).\n"
        "- Keep technical terms in English unless the user clearly prefers Spanish wording."
    )


# =========================
# Ollama chat
# =========================
def ollama_chat(text: str, retrieved_context: str = "", language_mix_spanish_pct: int = 0) -> str:
    """
    Deterministic chat wrapper: strict non-hallucination rules and low temperature.
    This function avoids injecting memory and enforces a constrained system prompt.
    """
    if not _live_ollama_calls_allowed():
        return "(error: LLM service unavailable)"

    # Ensure the Ollama service is available (boot-time should have called ensure_ollama_boot)
    try:
        ensure_ollama()
    except Exception:
        # proceed; requests will surface an error which we retry below
        pass

    # Build a strict system message that prevents fabricated actions and enforces
    # a specific TOOL citation format when referencing tool-produced outputs.
    casual_prompt = (
        "You are Nova, a friendly conversational assistant running locally on Windows.\n"
        "Tone and behavior rules:\n"
        "- Speak naturally and briefly like a person in the room; prefer short acknowledgements for casual statements.\n"
        "- Do NOT repeatedly offer assistance or suggest actions unless the user explicitly asks for help. Avoid endings like 'Would you like me to...' in casual chat.\n"
        "- Avoid formal task-oriented phrasing for ordinary conversation; use gentle acknowledgements (e.g., 'Got it.', 'She sounds tired.', 'Nice.').\n"
        "- Never claim you performed actions on the PC (open, unzip, delete, move, install, browse, click, run commands) unless a tool was actually executed and its real output is available.\n"
        "- Do NOT provide external links or URLs unless the user asks specifically for a link or sources. If asked for a source, provide one and include a TOOL citation only when the output is grounded.\n"
        "- Never invent links, file paths, filenames, or results. If unsure, say you are unsure.\n"
        "- Only ask clarifying questions sparingly and only when necessary to complete a requested task; do not ask follow-ups for simple observational statements.\n"
        "- Keep answers concise and verifiable.\n"
        "- IMPORTANT: If you reference results produced by tools (files saved, snapshots, patches, downloads, paths, etc.), include an exact citation line in this format: '[TOOL:<tool_name>] <short description or path>'.\n"
        "  Example citations:\n"
        "    [TOOL:web_fetch] runtime/web/20260101_example.html\n"
        "    [TOOL:patch_apply] Patch applied: 3 files\n"
        "- Do NOT fabricate any such citation — if you do not have a real tool output, say you don't have the output and provide the command the user should run to get it.\n"
    )

    assist_prompt = (
        "You are Nova, a helpful assistant running locally on Windows.\n"
        "Tone and behavior rules:\n"
        "- Be helpful and offer assistance when helpful, but avoid fabricating actions or results.\n"
        "- If the user is vague and a follow-up is needed to complete a requested task, ask one concise clarifying question.\n"
        "- For task-oriented requests, prioritize clear, actionable steps.\n"
        "- Never claim you performed actions on the PC (open, unzip, delete, move, install, browse, click, run commands) unless a tool was actually executed and its real output is available.\n"
        "- Do NOT provide external links unless the user requests sources; when providing tool outputs include TOOL citations.\n"
        "- Keep answers concrete and verifiable.\n"
        "- IMPORTANT: If you reference results produced by tools (files saved, snapshots, patches, downloads, paths, etc.), include an exact citation line in this format: '[TOOL:<tool_name>] <short description or path>'.\n"
        "  Example citations:\n"
        "    [TOOL:web_fetch] runtime/web/20260101_example.html\n"
        "    [TOOL:patch_apply] Patch applied: 3 files\n"
        "- Do NOT fabricate any such citation — if you do not have a real tool output, say you don't have the output and provide the command the user should run to get it.\n"
    )

    # Choose prompt variant via CASUAL_MODE env var (default: casual)
    if os.environ.get("CASUAL_MODE", "1").lower() in {"1", "true", "yes"}:
        system_msg = casual_prompt
    else:
        system_msg = assist_prompt

    identity_ctx = identity_context_for_prompt()
    if identity_ctx:
        system_msg = f"{system_msg}\n\nPersistent identity memory:\n{identity_ctx}"

    system_msg = f"{system_msg}\n\n{_language_mix_instruction(language_mix_spanish_pct)}"

    # Build user content with optional retrieved context
    user_content = text
    if retrieved_context:
        user_content = (
            f"{text}\n\n"
            "Retrieved context (use only if relevant; if uncertain, say uncertain):\n"
            "<<<CONTEXT\n"
            f"{retrieved_context[:6000]}\n"
            ">>>"
        )

    payload = {
        "model": chat_model(),
        "stream": False,
        "options": {"temperature": 0.2, "top_p": 0.9, "repeat_penalty": 1.1},
        "messages": [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_content},
        ],
    }

    # Primary call with one deterministic retry after a service restart
    try:
        r = requests.post(f"{OLLAMA_BASE}/api/chat", json=payload, timeout=OLLAMA_REQ_TIMEOUT)
        r.raise_for_status()
        try:
            return r.json()["message"]["content"].strip()
        except Exception:
            return None
    except Exception:
        warn("Ollama chat failed; attempting one restart and retry.")
        try:
            kill_ollama()
            time.sleep(1.2)
            start_ollama_serve_detached()
            time.sleep(1.2)
            r = requests.post(f"{OLLAMA_BASE}/api/chat", json=payload, timeout=OLLAMA_REQ_TIMEOUT)
            r.raise_for_status()
            try:
                return r.json()["message"]["content"].strip()
            except Exception:
                return None
        except Exception as e:
            warn(f"Ollama chat final attempt failed: {e}")
            return "(error: LLM service unavailable)"


def _teach_store_example(original: str, correction: str, user: Optional[str] = None) -> str:
    """Store a teach example both in memory and as a local examples file for patch proposals."""
    try:
        user = user or get_active_user() or ""
        ex = {"orig": original, "corr": correction, "user": user, "ts": int(time.time())}
        # store in memory for runtime learning
        mem_add("teach", "user_teach", json.dumps(ex))

        # also append to local examples file for patch proposals
        teach_dir = UPDATES_DIR / "teaching"
        teach_dir.mkdir(parents=True, exist_ok=True)
        fn = teach_dir / "examples.jsonl"
        with open(fn, "a", encoding="utf-8") as f:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")
        return "OK"
    except Exception as e:
        return f"Failed to store teach example: {e}"


def _parse_correction(text: str) -> Optional[str]:
    """Parse a freeform correction and return the corrected reply if found."""
    if not text:
        return None
    t = text.strip()
    # common patterns
    patterns = [
        r"^(?:no|nah|nope|that's wrong|wrong|not quite|don't)\b.*(?:say|respond|reply|use)\s+[\"'](.+?)[\"'](?:\s*instead)?$",
        r"^(?:say|respond|reply|use)\s+[\"'](.+?)[\"']\s*(?:instead)?$",
        r".*instead[,:\s]+[\"']?(.+?)[\"']?$",
    ]
    for pat in patterns:
        m = re.match(pat, t, flags=re.I)
        if m:
            corr = m.group(1).strip()
            if corr:
                return corr
    return None


def _looks_like_correction_cancel(text: str) -> bool:
    low = _normalize_turn_text(text)
    if not low:
        return False
    cues = (
        "dont have to replace",
        "don't have to replace",
        "no need to replace",
        "you dont have to replace",
        "you don't have to replace",
        "i was just small talk",
        "it was just small talk",
        "just small talk",
        "leave it alone",
        "never mind that correction",
        "nevermind that correction",
    )
    return any(cue in low for cue in cues)


def _looks_like_pending_replacement_text(text: str) -> bool:
    raw = str(text or "").strip()
    if not raw or "?" in raw:
        return False
    if bool(re.fullmatch(r"['\"].+['\"]", raw)):
        return True
    normalized = _normalize_turn_text(raw)
    words = [word for word in normalized.split() if word]
    if not words:
        return False
    return len(words) <= 4


def _safe_eval_arithmetic_expression(expr: str) -> Optional[float]:
    text = str(expr or "").strip()
    if not text:
        return None
    try:
        node = ast.parse(text, mode="eval")
    except Exception:
        return None

    def _eval(n: ast.AST) -> float:
        if isinstance(n, ast.Expression):
            return _eval(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
            return float(n.value)
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.UAdd, ast.USub)):
            value = _eval(n.operand)
            return value if isinstance(n.op, ast.UAdd) else -value
        if isinstance(n, ast.BinOp) and isinstance(n.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)):
            left = _eval(n.left)
            right = _eval(n.right)
            if isinstance(n.op, ast.Add):
                return left + right
            if isinstance(n.op, ast.Sub):
                return left - right
            if isinstance(n.op, ast.Mult):
                return left * right
            if right == 0:
                raise ZeroDivisionError()
            return left / right
        raise ValueError("unsupported_expression")

    try:
        return _eval(node)
    except Exception:
        return None


def _arithmetic_expression_reply(user_text: str) -> Optional[str]:
    raw = str(user_text or "").strip()
    if not raw:
        return None
    match = re.search(r"(?<!\d)(\d+(?:\s*[+\-*/]\s*\d+){1,8})\s*=?(?!\d)", raw)
    if not match:
        return None
    expr = str(match.group(1) or "").strip()
    value = _safe_eval_arithmetic_expression(expr)
    if value is None:
        return None
    if float(value).is_integer():
        rendered = str(int(value))
    else:
        rendered = str(round(float(value), 6)).rstrip("0").rstrip(".")
    return rendered


def _is_negative_feedback(text: str) -> bool:
    t = (text or "").strip().lower()
    cues = [
        "you are wrong",
        "you're wrong",
        "that is wrong",
        "you gave me garbage",
        "that is garbage",
        "not correct",
        "not right",
        "that is not true",
        "you made that up",
        "what happen",
        "what happened",
    ]
    return any(c in t for c in cues)


def _extract_authoritative_correction_text(text: str) -> Optional[str]:
    t = (text or "").strip()
    if not t:
        return None

    # First, try explicit correction forms.
    c = _parse_correction(t)
    if c:
        return c

    low = t.lower()
    if "?" in t and len(t) < 220:
        return None

    # Long declarative statements are likely intended corrections/ground truth.
    if len(t) >= 80:
        # Drop conversational lead-ins.
        cleaned = re.sub(r"(?is)^\s*(you're right about something|you are right about something|listen|look)\s*[,:.-]*\s*", "", t).strip()
        return cleaned or None

    # Short, direct declarative corrections should also be accepted.
    short_decl_patterns = [
        r"^\s*my\s+name\s+is\s+.+",
        r"^\s*your\s+name\s+is\s+.+",
        r"^\s*please\s+use\s+.+",
    ]
    if any(re.match(p, low) for p in short_decl_patterns):
        return t

    return None


def _normalize_correction_for_storage(correction: str) -> str:
    c = re.sub(r"\s+", " ", (correction or "").strip())
    if not c:
        return c

    # Keep only the key identity sentence when user includes extra coaching text.
    m_name = re.search(r"(?i)\bmy\s+name\s+is\s+[^.?!]+", c)
    if m_name:
        out = m_name.group(0).strip().rstrip(".?!") + "."
        return out

    # Keep the first sentence as a concise reusable correction.
    parts = re.split(r"(?<=[.!?])\s+", c)
    return (parts[0] if parts else c).strip()


def _is_identity_stable_reply(reply: str) -> bool:
    low = (reply or "").strip().lower()
    if not low:
        return False
    cues = [
        "my name is",
        "my developer's full name",
        "was given its name by",
        "i do not have a saved name-origin story",
    ]
    return any(c in low for c in cues)


def _apply_reply_overrides(reply: str) -> str:
    """Check stored teach examples and return an overridden reply if a matching original is found."""
    try:
        teach_dir = UPDATES_DIR / "teaching"
        fn = teach_dir / "examples.jsonl"
        if not fn.exists():
            return reply
        def _norm(s: str) -> str:
            return re.sub(r"\s+", " ", (s or "").strip())

        def _loose_norm(s: str) -> str:
            base = _norm(s).lower()
            base = re.sub(r"[^a-z0-9 ]+", " ", base)
            return re.sub(r"\s+", " ", base).strip()

        target = _norm(reply)
        target_loose = _loose_norm(reply)
        best_ratio = 0.0
        best_corr = ""

        with open(fn, "r", encoding="utf-8") as f:
            for ln in f:
                try:
                    j = json.loads(ln)
                    orig = _norm(j.get("orig") or "")
                    corr = j.get("corr") or ""
                    if orig and orig == target:
                        return corr
                    orig_loose = _loose_norm(orig)
                    if orig_loose and orig_loose == target_loose:
                        return corr
                    if orig_loose and target_loose:
                        ratio = difflib.SequenceMatcher(None, target_loose, orig_loose).ratio()
                        if ratio > best_ratio:
                            best_ratio = ratio
                            best_corr = corr
                except Exception:
                    continue
        if best_ratio >= 0.94 and best_corr:
            return best_corr
    except Exception:
        pass
    return reply


def _teach_list_examples() -> str:
    try:
        teach_dir = UPDATES_DIR / "teaching"
        fn = teach_dir / "examples.jsonl"
        if not fn.exists():
            return "No teach examples stored. Use: teach remember <orig> => <correction>"
        lines = []
        with open(fn, "r", encoding="utf-8") as f:
            for ln in f:
                try:
                    j = json.loads(ln)
                    lines.append(f"- [{j.get('user')}] {j.get('orig')} => {j.get('corr')}")
                except Exception:
                    continue
        return "\n".join(lines) if lines else "No teach examples found."
    except Exception as e:
        return f"Failed to read teach examples: {e}"


def _teach_propose_patch(description: str) -> str:
    try:
        teach_dir = UPDATES_DIR / "teaching"
        fn = teach_dir / "examples.jsonl"
        if not fn.exists():
            return "No teach examples to propose. Use: teach remember <orig> => <correction>"

        ts = time.strftime("%Y%m%d_%H%M%S")
        out_zip = UPDATES_DIR / f"teach_proposal_{ts}.zip"
        current_revision = _read_patch_revision()
        manifest = {
            "name": f"teach_proposal_{ts}",
            "notes": description or "Teach examples proposal",
            "patch_revision": current_revision + 1,
            "min_base_revision": current_revision,
        }
        tmp_manifest = UPDATES_DIR / f"teach_manifest_{ts}.json"
        tmp_manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

        with zipfile.ZipFile(out_zip, "w", compression=zipfile.ZIP_DEFLATED) as z:
            z.write(fn, arcname="examples.jsonl")
            z.write(tmp_manifest, arcname=PATCH_MANIFEST_NAME)

        try:
            tmp_manifest.unlink()
        except Exception:
            pass

        # generate preview report for this proposal
        try:
            preview_out = patch_preview(str(out_zip), write_report=True)
        except Exception:
            preview_out = "Preview generation failed."

        # Only enter the blocking local review loop when explicitly enabled.
        try:
            import sys
            if _interactive_patch_review_enabled() and sys.stdin and hasattr(sys.stdin, "isatty") and sys.stdin.isatty():
                # extract preview filename if present
                m = re.search(r"Preview written:\s*(.+)$", preview_out or "", flags=re.M)
                preview_path = m.group(1).strip() if m else None
                if preview_path:
                    decision_msg = interactive_preview_review(preview_path)
                else:
                    decision_msg = "Preview saved but path not found. Use 'patch list-previews' to locate it."
            else:
                decision_msg = ""
        except Exception:
            decision_msg = ""

        base_msg = f"Created proposal: {out_zip} — apply with: patch apply {out_zip}"
        if decision_msg:
            return base_msg + "\n" + decision_msg
        return base_msg
    except Exception as e:
        return f"Failed to create teach proposal: {e}"


def _teach_autoapply_proposal(zip_path: str, apply_live: bool = False) -> str:
    """Test a proposal zip in a staging copy of the repo first.
    If tests pass in staging and `apply_live` is True, apply the patch to the live repo via patch_apply().
    By default (`apply_live=False`) this runs staging and returns the test output and the suggested apply command
    without modifying the live repository.
    """
    try:
        z = Path(zip_path)
        if not z.exists():
            return f"Not found: {z}"

        # Generate and save a preview report for this proposal
        try:
            preview_out = patch_preview(str(z), write_report=True)
        except Exception as e:
            # Save failure reason to previews
            try:
                previews = UPDATES_DIR / "previews"
                previews.mkdir(parents=True, exist_ok=True)
                tsf = time.strftime("%Y%m%d_%H%M%S")
                fail_fn = previews / f"preview_fail_{tsf}_{z.name}.txt"
                fail_fn.write_text(f"Preview generation failed: {e}", encoding="utf-8")
            except Exception:
                pass
            return f"Preview generation failed: {e}"

        # If preview indicates rejected status, save and abort autoapply
        if "Status: eligible" not in (preview_out or ""):
            return f"Preview indicates proposal is not eligible for autoapply. Preview saved.\n\n{preview_out}"

        ts = time.strftime("%Y%m%d_%H%M%S")
        staging = UPDATES_DIR / f"staging_{ts}"
        # copy repo to staging
        import shutil
        staging.mkdir(parents=True, exist_ok=True)
        # copytree requires empty target; copy contents instead
        for item in BASE_DIR.iterdir():
            if item.name in {"runtime", "logs", "updates", "piper", "models"}:
                # skip large runtime artifacts
                continue
            dest = staging / item.name
            if item.is_dir():
                shutil.copytree(item, dest)
            else:
                shutil.copy2(item, dest)

        # extract zip into staging (overlay)
        with zipfile.ZipFile(z, "r") as zz:
            zz.extractall(path=staging)

        # run the same behavioral validation gate in staging before any live apply.
        behavior_result = _behavioral_check(base_dir=staging)
        if not bool(behavior_result.get("ok")):
            # cleanup staging
            try:
                shutil.rmtree(staging)
            except Exception:
                pass
            out = str(behavior_result.get("output") or "")
            summary = str(behavior_result.get("summary") or "behavioral check failed")
            return f"Behavioral check failed in staging:\n{summary}\n\n{out}"

        # tests passed; either apply to live repo or return suggested command
        if apply_live:
            apply_out = patch_apply(str(z))

            # cleanup staging
            try:
                shutil.rmtree(staging)
            except Exception:
                pass

            return f"Staging tests passed. patch_apply result:\n{apply_out}"
        else:
            # cleanup staging
            try:
                shutil.rmtree(staging)
            except Exception:
                pass

            return (
                f"Staging behavioral check passed ({str(behavior_result.get('summary') or 'passed')}). To apply this proposal to the live repo run:\n"
                f"  teach autoapply apply {zip_path}\n"
                "Or run the suggested patch apply command directly: patch apply <zip_path>"
            )
    except Exception as e:
        return f"Autoapply failed: {e}"

    user_content = text
    if retrieved_context:
        user_content = (
            f"{text}\n\n"
            "Retrieved context (use only if relevant; if uncertain, say uncertain):\n"
            "<<<CONTEXT\n"
            f"{retrieved_context[:6000]}\n"
            ">>>"
        )

    payload = {
        "model": chat_model(),
        "stream": False,
        "options": {"temperature": 0.2, "top_p": 0.9, "repeat_penalty": 1.1},
        "messages": [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_content},
        ],
    }

    # Primary call with one deterministic retry after a service restart
    try:
        r = requests.post(f"{OLLAMA_BASE}/api/chat", json=payload, timeout=OLLAMA_REQ_TIMEOUT)
        r.raise_for_status()
        return r.json()["message"]["content"].strip()
    except Exception:
        warn("Ollama chat failed; attempting one restart and retry.")
        try:
            kill_ollama()
            time.sleep(1.2)
            start_ollama_serve_detached()
            time.sleep(1.2)
            r = requests.post(f"{OLLAMA_BASE}/api/chat", json=payload, timeout=OLLAMA_REQ_TIMEOUT)
            r.raise_for_status()
            return r.json()["message"]["content"].strip()
        except Exception as e:
            warn(f"Ollama chat final attempt failed: {e}")
            return "(error: LLM service unavailable)"


# =========================
# Voice (STT)
# =========================
def record_seconds(seconds=3):
    if not _ensure_voice_deps() or sd is None:
        raise RuntimeError(f"Voice is disabled (import error: {VOICE_IMPORT_ERR})")
    print(f"Nova: recording for {seconds} seconds... (talk now)", flush=True)
    audio = sd.rec(
        int(seconds * SAMPLE_RATE),
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype="int16",
    )
    sd.wait()
    return audio


def transcribe(model, audio_int16):
    if not _ensure_voice_deps() or wav is None:
        raise RuntimeError(f"Voice is disabled (import error: {VOICE_IMPORT_ERR})")
    buf = io.BytesIO()
    wav.write(buf, SAMPLE_RATE, audio_int16)
    buf.seek(0)
    segments, _ = model.transcribe(buf)
    return " ".join(seg.text.strip() for seg in segments).strip()


# =========================
# Tools
# =========================
def run_tool_py(script: str, args=None) -> str:
    args = args or []
    p = subprocess.run([PYTHON, script] + args, capture_output=True, text=True)
    out = (p.stdout or "")
    if p.stderr:
        out += ("\n" + p.stderr)
    return out.strip()


def tool_screen():
    return execute_registered_tool("vision", {"action": "screen"})


def tool_camera(prompt: str):
    return execute_registered_tool("vision", {"action": "camera", "prompt": prompt})


def tool_ls(subfolder=""):
    payload = {"action": "ls"}
    if subfolder:
        payload["path"] = subfolder
    return execute_registered_tool("filesystem", payload)


def tool_read(path: str):
    return execute_registered_tool("filesystem", {"action": "read", "path": path})


def tool_find(keyword: str, subfolder=""):
    payload = {"action": "find", "keyword": keyword}
    if subfolder:
        payload["path"] = subfolder
    out = execute_registered_tool("filesystem", payload)
    if not out or out == "No matches found.":
        return out or "No matches found."
    return "Matches:\n" + out


def tool_health():
    return execute_registered_tool("system", {"action": "health_check"})


def tool_system_check():
    return execute_registered_tool("system", {"action": "system_check"})


def tool_queue_status():
    return execute_registered_tool("system", {"action": "queue_status"})


def tool_phase2_audit():
    import kidney
    import nova_safety_envelope

    sections = [
        "Post-Phase-2 audit:",
        str(tool_system_check() or ""),
        str(kidney.render_status() or ""),
        str(nova_safety_envelope.render_status() or ""),
    ]
    return "\n\n".join(section for section in sections if str(section or "").strip())


def _load_json_file(path: Path, default: Any) -> Any:
    try:
        if not path.exists():
            return default
        data = json.loads(path.read_text(encoding="utf-8") or "null")
        return default if data is None else data
    except Exception:
        return default


def _count_definition_files(root: Path) -> int:
    manifest_names = {"generated_manifest.json", "latest_manifest.json"}
    try:
        if not root.exists():
            return 0
        return sum(1 for path in root.glob("*.json") if path.is_file() and path.name not in manifest_names)
    except Exception:
        return 0


def _promotion_audit_summary() -> dict:
    latest_by_file = {}
    if PROMOTION_AUDIT_LOG.exists():
        try:
            with PROMOTION_AUDIT_LOG.open("r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except Exception:
                        continue
                    if not isinstance(row, dict):
                        continue
                    file_name = str(row.get("file") or "").strip()
                    if not file_name:
                        continue
                    latest_by_file[file_name] = row
        except Exception:
            latest_by_file = {}

    status_counts = {}
    latest_ts = ""
    for row in latest_by_file.values():
        status = str(row.get("status") or "unknown").strip() or "unknown"
        status_counts[status] = int(status_counts.get(status, 0) or 0) + 1
        row_ts = str(row.get("ts") or "").strip()
        if row_ts > latest_ts:
            latest_ts = row_ts

    return {
        "generated_total": _count_definition_files(GENERATED_DEFINITIONS_DIR),
        "promoted_total": _count_definition_files(PROMOTED_DEFINITIONS_DIR),
        "pending_review_total": _count_definition_files(PENDING_REVIEW_DIR),
        "quarantine_total": _count_definition_files(QUARANTINE_DIR),
        "latest_audited_files": len(latest_by_file),
        "latest_audit_ts": latest_ts,
        "status_counts": status_counts,
    }


def _parse_log_timestamp(ts_text: str) -> float:
    try:
        return time.mktime(time.strptime(str(ts_text or "").strip(), "%Y-%m-%d %H:%M:%S"))
    except Exception:
        return 0.0


def _patch_activity_summary(window_hours: int = 24) -> dict:
    summary = {
        "apply_count": 0,
        "apply_ok_count": 0,
        "rollback_count": 0,
        "behavior_fail_count": 0,
        "last_line": _read_patch_log_tail_line(),
    }
    if not PATCH_LOG.exists():
        return summary

    window_seconds = max(1, int(window_hours or 24)) * 3600
    cutoff = time.time() - window_seconds
    try:
        with PATCH_LOG.open("r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line or "|" not in line:
                    continue
                ts_text, event = line.split("|", 1)
                event = event.strip()
                event_ts = _parse_log_timestamp(ts_text)
                if event_ts and event_ts < cutoff:
                    continue
                if event.startswith("APPLY_OK"):
                    summary["apply_ok_count"] += 1
                elif event.startswith("APPLY "):
                    summary["apply_count"] += 1
                elif event.startswith("ROLLBACK"):
                    summary["rollback_count"] += 1
                elif event.startswith("BEHAVIOR_FAIL"):
                    summary["behavior_fail_count"] += 1
    except Exception:
        return summary
    return summary


def _preview_name_to_zip_path(preview_name: str) -> Optional[Path]:
    name = str(preview_name or "").strip()
    if not name:
        return None
    match = re.match(r"^preview_\d{8}_\d{6}_(.+)\.txt$", name)
    if not match:
        return None
    zip_name = str(match.group(1) or "").strip()
    if not zip_name:
        return None
    path = UPDATES_DIR / zip_name
    return path if path.exists() else None


def _latest_approved_update_zip(patch_payload: Optional[dict] = None) -> Optional[Path]:
    payload = patch_payload if isinstance(patch_payload, dict) else patch_status_payload()
    previews = payload.get("previews") if isinstance(payload, dict) else None
    if not isinstance(previews, list):
        return None
    for item in previews:
        if not isinstance(item, dict):
            continue
        decision = str(item.get("decision") or "").strip().lower()
        status = str(item.get("status") or "").strip().lower()
        if decision != "approved" or not status.startswith("eligible"):
            continue
        path = _preview_name_to_zip_path(str(item.get("name") or ""))
        if path is not None:
            return path
    return None


def _pulse_level(ollama_up: bool, routing_stable: bool, fallback_score: float, rollback_count: int) -> str:
    if not ollama_up:
        return "deterministic-only"
    if not routing_stable or fallback_score >= 0.9 or rollback_count > 0:
        return "guarded"
    return "operational"


def _pulse_mood(ollama_up: bool, routing_stable: bool, promoted_delta: int, fallback_score: float, rollback_count: int) -> str:
    if not ollama_up:
        return "LLM link is down, so I am holding to deterministic paths only."
    if rollback_count > 0 or fallback_score >= 0.9:
        return "Stable, but I am watching rollback pressure and fallback drift closely."
    if not routing_stable:
        return "Routing is unsettled, so I am staying conservative."
    if promoted_delta > 0:
        return "Learning is moving forward cleanly."
    return "Quiet and steady."


def build_pulse_payload() -> dict:
    audit = _promotion_audit_summary()
    behavior = _load_json_file(BEHAVIOR_METRICS_FILE, {})
    autonomy = _load_json_file(AUTONOMY_MAINTENANCE_FILE, {})
    prior = _load_json_file(PULSE_SNAPSHOT_FILE, {})
    patch = patch_status_payload()
    patch_activity = _patch_activity_summary(window_hours=24)
    ollama_up = bool(ollama_api_up())
    routing_stable = bool(behavior.get("routing_stable", False))
    fallback_score = float(autonomy.get("last_fallback_overuse_score") or 0.0)
    promoted_total = int(audit.get("promoted_total", 0) or 0)
    prior_promoted_total = int(prior.get("promoted_total", 0) or 0)
    promoted_delta = promoted_total - prior_promoted_total if prior_promoted_total else 0
    approved_update_zip = _latest_approved_update_zip(patch)

    memory_payload = mem_stats_payload(emit_event=False)
    kidney_summary = {}
    safety_cfg = {}
    try:
        import kidney

        kidney_summary = kidney.run_kidney(dry_run=True)
    except Exception:
        kidney_summary = {}
    try:
        import nova_safety_envelope

        safety_cfg = nova_safety_envelope.policy_safety_envelope()
    except Exception:
        safety_cfg = {}

    payload = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "promoted_total": promoted_total,
        "promoted_delta": max(0, int(promoted_delta)),
        "generated_total": int(audit.get("generated_total", 0) or 0),
        "pending_review_total": int(audit.get("pending_review_total", 0) or 0),
        "quarantine_total": int(audit.get("quarantine_total", 0) or 0),
        "latest_audited_files": int(audit.get("latest_audited_files", 0) or 0),
        "latest_audit_ts": str(audit.get("latest_audit_ts") or "unknown"),
        "audit_status_counts": dict(audit.get("status_counts") or {}),
        "routing_stable": routing_stable,
        "tool_route_count": int(behavior.get("tool_route", 0) or 0),
        "llm_fallback_count": int(behavior.get("llm_fallback", 0) or 0),
        "last_reflection_at": str(behavior.get("last_reflection_at") or "unknown"),
        "last_fallback_overuse_score": fallback_score,
        "last_regression_status": str(autonomy.get("last_regression_status") or "unknown"),
        "patch_revision": int(patch.get("current_revision", 0) or 0),
        "approved_eligible_previews": int(patch.get("previews_approved_eligible", 0) or 0),
        "ready_for_validated_apply": bool(patch.get("ready_for_validated_apply", False)),
        "patch_activity": patch_activity,
        "patch_last_line": str(patch.get("last_patch_log_line") or patch_activity.get("last_line") or "none"),
        "ollama_up": ollama_up,
        "memory_ok": bool(memory_payload.get("ok", False)),
        "memory_total": int(memory_payload.get("total", 0) or 0) if memory_payload.get("ok") else 0,
        "kidney_mode": str(kidney_summary.get("mode") or "unknown"),
        "kidney_candidates": int(kidney_summary.get("candidate_count", 0) or 0),
        "kidney_archive_count": int(kidney_summary.get("archive_count", 0) or 0),
        "kidney_delete_count": int(kidney_summary.get("delete_count", 0) or 0),
        "safety_enabled": bool(safety_cfg.get("enabled", True)) if isinstance(safety_cfg, dict) else True,
        "safety_mode": str(safety_cfg.get("mode") or "unknown") if isinstance(safety_cfg, dict) else "unknown",
        "update_zip_path": str(approved_update_zip) if approved_update_zip is not None else "",
    }
    payload["autonomy_level"] = _pulse_level(
        payload["ollama_up"],
        payload["routing_stable"],
        payload["last_fallback_overuse_score"],
        int((payload.get("patch_activity") or {}).get("rollback_count", 0) or 0),
    )
    payload["mood"] = _pulse_mood(
        payload["ollama_up"],
        payload["routing_stable"],
        payload["promoted_delta"],
        payload["last_fallback_overuse_score"],
        int((payload.get("patch_activity") or {}).get("rollback_count", 0) or 0),
    )
    return payload


def _write_pulse_snapshot(payload: dict) -> None:
    snapshot = {
        "generated_at": str(payload.get("generated_at") or ""),
        "promoted_total": int(payload.get("promoted_total", 0) or 0),
        "patch_revision": int(payload.get("patch_revision", 0) or 0),
        "llm_fallback_count": int(payload.get("llm_fallback_count", 0) or 0),
        "tool_route_count": int(payload.get("tool_route_count", 0) or 0),
    }
    try:
        PULSE_SNAPSHOT_FILE.parent.mkdir(parents=True, exist_ok=True)
        PULSE_SNAPSHOT_FILE.write_text(json.dumps(snapshot, ensure_ascii=True, indent=2), encoding="utf-8")
    except Exception:
        return


def render_nova_pulse(payload: Optional[dict] = None) -> str:
    data = payload if isinstance(payload, dict) else build_pulse_payload()
    patch_activity = data.get("patch_activity") if isinstance(data.get("patch_activity"), dict) else {}
    status_counts = data.get("audit_status_counts") if isinstance(data.get("audit_status_counts"), dict) else {}
    if status_counts:
        audit_status_text = ", ".join(f"{name}={status_counts[name]}" for name in sorted(status_counts))
    else:
        audit_status_text = "none"

    lines = [
        f"Nova Pulse - {data.get('generated_at')}",
        "Core evolution:",
        f"- promoted definitions: {int(data.get('promoted_total', 0) or 0)} (+{int(data.get('promoted_delta', 0) or 0)} since last pulse)",
        f"- generated definitions: {int(data.get('generated_total', 0) or 0)}",
        f"- pending review: {int(data.get('pending_review_total', 0) or 0)}",
        f"- quarantine: {int(data.get('quarantine_total', 0) or 0)}",
        f"- latest audited files: {int(data.get('latest_audited_files', 0) or 0)} at {data.get('latest_audit_ts')}",
        f"- audit statuses: {audit_status_text}",
        "Updates:",
        f"- patch revision: {int(data.get('patch_revision', 0) or 0)}",
        f"- ready for validated apply: {'yes' if data.get('ready_for_validated_apply') else 'no'}",
        f"- approved eligible previews: {int(data.get('approved_eligible_previews', 0) or 0)}",
        f"- patch activity last 24h: applies={int(patch_activity.get('apply_count', 0) or 0)}, apply_ok={int(patch_activity.get('apply_ok_count', 0) or 0)}, rollbacks={int(patch_activity.get('rollback_count', 0) or 0)}, behavior_failures={int(patch_activity.get('behavior_fail_count', 0) or 0)}",
        f"- patch log tail: {data.get('patch_last_line')}",
        "Support systems:",
        f"- Ollama API: {'online' if data.get('ollama_up') else 'offline'}",
        f"- memory: {'ok' if data.get('memory_ok') else 'unavailable'} (total={int(data.get('memory_total', 0) or 0)})",
        f"- kidney: mode={data.get('kidney_mode')} candidates={int(data.get('kidney_candidates', 0) or 0)} archive={int(data.get('kidney_archive_count', 0) or 0)} delete={int(data.get('kidney_delete_count', 0) or 0)}",
        f"- safety envelope: enabled={bool(data.get('safety_enabled'))} mode={data.get('safety_mode')}",
        "Autonomy:",
        f"- level: {data.get('autonomy_level')}",
        f"- routing stable: {'yes' if data.get('routing_stable') else 'no'}",
        f"- tool routes vs llm fallbacks: {int(data.get('tool_route_count', 0) or 0)} / {int(data.get('llm_fallback_count', 0) or 0)}",
        f"- last fallback overuse score: {float(data.get('last_fallback_overuse_score', 0.0) or 0.0):.2f}",
        f"- last regression status: {data.get('last_regression_status')}",
        f"- last reflection: {data.get('last_reflection_at')}",
        "Assessment:",
        f"- {data.get('mood')}",
    ]
    update_zip_path = str(data.get("update_zip_path") or "").strip()
    if update_zip_path:
        lines.append('Type "update now" if you want me to apply the latest approved validated update.')
    else:
        lines.append("No approved validated update is queued right now.")
    return "\n".join(lines)


def tool_nova_pulse():
    payload = build_pulse_payload()
    _write_pulse_snapshot(payload)
    return render_nova_pulse(payload)


def _read_update_now_pending() -> dict:
    return _load_json_file(UPDATE_NOW_PENDING_FILE, {}) if UPDATE_NOW_PENDING_FILE.exists() else {}


def _write_update_now_pending(payload: dict) -> None:
    try:
        UPDATE_NOW_PENDING_FILE.parent.mkdir(parents=True, exist_ok=True)
        UPDATE_NOW_PENDING_FILE.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
    except Exception:
        return


def _clear_update_now_pending() -> None:
    try:
        if UPDATE_NOW_PENDING_FILE.exists():
            UPDATE_NOW_PENDING_FILE.unlink()
    except Exception:
        return


def update_now_pending_payload() -> dict:
    data = _read_update_now_pending()
    if not isinstance(data, dict) or not data:
        return {"ok": False, "pending": False}
    return {
        "ok": True,
        "pending": True,
        "created_at": str(data.get("created_at") or ""),
        "token": str(data.get("token") or ""),
        "zip_path": str(data.get("zip_path") or ""),
        "preview_status": str(data.get("preview_status") or ""),
    }


def _build_update_now_token(zip_path: Path) -> str:
    seed = f"{str(zip_path)}|{time.time()}|{os.getpid()}"
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:8]


def _extract_preview_status(preview_text: str) -> str:
    m = re.search(r"^Status:\s*(.+)$", str(preview_text or ""), flags=re.M)
    return str(m.group(1) or "").strip() if m else "unknown"


def _extract_preview_zip(preview_text: str) -> str:
    m = re.search(r"^Zip:\s*(.+)$", str(preview_text or ""), flags=re.M)
    return str(m.group(1) or "").strip() if m else ""


def tool_update_now():
    patch_payload = patch_status_payload()
    zip_path = _latest_approved_update_zip(patch_payload)
    if zip_path is None:
        _clear_update_now_pending()
        return "No approved validated update is queued right now. Run pulse to inspect the current update pipeline."
    preview_text = patch_preview(str(zip_path), write_report=False)
    preview_status = _extract_preview_status(preview_text)
    if not str(preview_status or "").lower().startswith("eligible"):
        _clear_update_now_pending()
        return (
            "Update candidate is not eligible after dry-run preview.\n"
            f"- zip: {zip_path}\n"
            f"- status: {preview_status or 'unknown'}\n"
            "Update not applied."
        )

    token = _build_update_now_token(zip_path)
    _write_update_now_pending({
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "token": token,
        "zip_path": str(zip_path),
        "preview_status": preview_status,
        "preview_zip": _extract_preview_zip(preview_text),
    })
    return (
        "Update dry-run ready.\n"
        f"- zip: {zip_path}\n"
        f"- status: {preview_status}\n"
        f"Confirm with: update now confirm {token}\n"
        "Cancel with: update now cancel"
    )


def tool_update_now_confirm(token: str = ""):
    pending = _read_update_now_pending()
    if not isinstance(pending, dict) or not pending:
        return "No pending update confirmation. Start with: update now"

    expected_token = str(pending.get("token") or "").strip()
    provided_token = str(token or "").strip()
    if not provided_token:
        return f"Confirmation token required. Run: update now confirm {expected_token}"
    if expected_token and provided_token != expected_token:
        return "Confirmation token mismatch. Run update now again to refresh the token."

    zip_path_text = str(pending.get("zip_path") or "").strip()
    if not zip_path_text:
        _clear_update_now_pending()
        return "Pending update payload is invalid. Run update now to regenerate the dry-run confirmation."
    zip_path = Path(zip_path_text)
    if not zip_path.exists():
        _clear_update_now_pending()
        return f"Update package is missing: {zip_path}. Run update now to regenerate the dry-run confirmation."

    patch_payload = patch_status_payload()
    latest_zip = _latest_approved_update_zip(patch_payload)
    if latest_zip is None or str(latest_zip) != str(zip_path):
        _clear_update_now_pending()
        return "Approved update candidate changed. Run update now again before confirming."

    out = execute_patch_action("apply", str(zip_path), is_admin=True)
    if str(out or "").lower().startswith("patch applied:"):
        _clear_update_now_pending()
    return out


def tool_update_now_cancel():
    had_pending = bool(_read_update_now_pending())
    _clear_update_now_pending()
    if had_pending:
        return "Canceled pending update confirmation."
    return "No pending update confirmation was active."


def execute_planned_action(tool: str, args=None):
    tool_name = str(tool or "").strip()
    tool_args = list(args) if isinstance(args, (list, tuple)) else ([] if args in {None, ""} else [args])

    if tool_name == "weather_current_location":
        current_coords = resolve_current_device_coords()
        if current_coords:
            return str(tool_weather(f"{current_coords[0]},{current_coords[1]}") or "")
        saved_location = str(get_saved_location_text() or "").strip()
        if saved_location:
            return str(tool_weather(saved_location) or "")
        coords = _coords_from_saved_location()
        if coords:
            return str(tool_weather(f"{coords[0]},{coords[1]}") or "")
        return _need_confirmed_location_message()

    if tool_name == "weather_location":
        location_value = str(tool_args[0] if tool_args else "").strip()
        return str(tool_weather(location_value) or "")

    if tool_name == "location_coords":
        location_value = str(tool_args[0] if tool_args else "").strip()
        return set_location_coords(location_value)

    tool_map = {
        "patch_apply": patch_apply,
        "patch_rollback": patch_rollback,
        "camera": tool_camera,
        "screen": tool_screen,
        "web_fetch": tool_web_fetch,
        "web_search": tool_web_search,
        "web_research": tool_web_research,
        "web_gather": tool_web_gather,
        "wikipedia_lookup": tool_wikipedia_lookup,
        "stackexchange_search": tool_stackexchange_search,
        "read": tool_read,
        "ls": tool_ls,
        "find": tool_find,
        "health": tool_health,
        "system_check": tool_system_check,
        "queue_status": tool_queue_status,
        "phase2_audit": tool_phase2_audit,
        "pulse": tool_nova_pulse,
        "update_now": tool_update_now,
        "update_now_confirm": tool_update_now_confirm,
        "update_now_cancel": tool_update_now_cancel,
    }
    fn = tool_map.get(tool_name)
    if not fn:
        return {"ok": False, "error": f"Unknown planned tool: {tool_name}"}

    try:
        return fn(*tool_args) if tool_args else fn()
    except Exception as e:
        return {"ok": False, "error": f"Tool error: {e}"}


def make_pending_weather_action() -> dict:
    saved_location = str(get_saved_location_text() or "").strip()
    return {
        "kind": "weather_lookup",
        "status": "awaiting_location",
        "saved_location_available": bool(saved_location),
        "preferred_tool": "weather_current_location" if saved_location else "weather_location",
    }


def _weather_current_location_available() -> bool:
    if resolve_current_device_coords():
        return True
    if str(get_saved_location_text() or "").strip():
        return True
    return bool(_coords_from_saved_location())


def web_search(query: str, save_dir: Path, max_results: int = 5) -> dict:
    save_dir.mkdir(parents=True, exist_ok=True)
    try:
        url = "https://html.duckduckgo.com/html/"
        r = requests.post(url, data={"q": query}, timeout=30, headers={"User-Agent": "Nova/1.0"})
    except requests.RequestException as e:
        return {"ok": False, "error": f"Search request failed: {e}"}

    try:
        r.raise_for_status()
        text = r.text or ""

        # crude parse for DuckDuckGo result links/titles (no external parser)
        entries = []
        for m in re.finditer(r'<a[^>]+class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', text, re.I | re.S):
            href = m.group(1)
            title_html = m.group(2)
            title = re.sub(r'<.*?>', '', title_html).strip()
            entries.append((title, href))
            if len(entries) >= int(max_results):
                break

        ts = time.strftime("%Y%m%d_%H%M%S")
        h = hashlib.sha256(query.encode("utf-8")).hexdigest()[:12]
        out_path = save_dir / f"search_{ts}_{h}.txt"

        with open(out_path, "w", encoding="utf-8") as f:
            f.write(f"Search results for: {query}\n\n")
            for i, (title, href) in enumerate(entries, start=1):
                f.write(f"{i}. {title}\n   {href}\n\n")

        size = out_path.stat().st_size
        return {"ok": True, "query": query, "path": str(out_path), "bytes": int(size)}

    except Exception as e:
        return {"ok": False, "error": f"Parsing error: {e}"}


def tool_search(query: str):
    missing = explain_missing("web_fetch", ["web_access"])
    if missing:
        return missing

    if not policy_tools_enabled().get("web", False):
        return "Web tool disabled by policy."

    out = web_search(query, WEB_CACHE_DIR, max_results=5)
    if not out.get("ok"):
        return f"[FAIL] {out.get('error', 'unknown error')}"
    return f"[OK] Saved: {out['path']} (text, {out['bytes']} bytes)"


def _decode_search_href(href: str) -> str:
    href = (href or "").strip()
    if not href:
        return ""

    # DuckDuckGo style redirect: /l/?uddg=<encoded_url>
    if href.startswith("/l/?"):
        q = parse_qs(urlparse("https://duckduckgo.com" + href).query)
        u = (q.get("uddg") or [""])[0]
        return unquote(u)

    if href.startswith("http://") or href.startswith("https://"):
        return href

    return ""


def _extract_text_from_path(path: Path, max_chars: int = 2000) -> str:
    try:
        suffix = path.suffix.lower()
        if suffix in {".txt", ".md", ".log"}:
            t = path.read_text(encoding="utf-8", errors="ignore")
            return re.sub(r"\s+", " ", t).strip()[:max_chars]

        if suffix in {".html", ".htm"}:
            raw = path.read_text(encoding="utf-8", errors="ignore")
            raw = re.sub(r"(?is)<script.*?>.*?</script>", " ", raw)
            raw = re.sub(r"(?is)<style.*?>.*?</style>", " ", raw)
            raw = re.sub(r"(?is)<[^>]+>", " ", raw)
            raw = html.unescape(raw)
            return re.sub(r"\s+", " ", raw).strip()[:max_chars]

        return ""
    except Exception:
        return ""


def _extract_text_from_html_content(raw_html: str, max_chars: int = 2000) -> str:
    raw = raw_html or ""
    raw = re.sub(r"(?is)<script.*?>.*?</script>", " ", raw)
    raw = re.sub(r"(?is)<style.*?>.*?</style>", " ", raw)
    raw = re.sub(r"(?is)<[^>]+>", " ", raw)
    raw = html.unescape(raw)
    return re.sub(r"\s+", " ", raw).strip()[:max_chars]


def _extract_same_host_links(raw_html: str, base_url: str, host: str) -> list[str]:
    links = []
    seen = set()
    hrefs = re.findall(r'href=["\']([^"\']+)["\']', raw_html or "", flags=re.I)
    for href in hrefs:
        href = (href or "").strip()
        if not href or href.startswith("#"):
            continue
        if href.startswith("javascript:") or href.startswith("mailto:"):
            continue

        abs_url = urljoin(base_url, href)
        p = urlparse(abs_url)
        if p.scheme not in ("http", "https"):
            continue
        if not p.hostname:
            continue
        if p.hostname.lower() != host.lower():
            continue

        clean = f"{p.scheme}://{p.netloc}{p.path}"
        if p.query:
            clean += f"?{p.query}"
        if clean in seen:
            continue
        seen.add(clean)
        links.append(clean)
    return links


def _expand_research_terms(tokens: list[str]) -> list[str]:
    terms = set(t for t in tokens if t)
    if "peims" in terms:
        terms.update({"tsds", "submission", "interchange", "student", "reporting"})
    if "attendance" in terms:
        terms.update({"ada", "attendance", "reporting"})
    if "timeline" in terms:
        terms.update({"calendar", "deadline", "dates"})
    if "reporting" in terms:
        terms.update({"submission", "report"})
    return list(terms)


def _score_research_hit(url: str, text: str, terms: list[str], primary_tokens: Optional[list[str]] = None) -> float:
    low_url = (url or "").lower()
    low_text = (text or "").lower()
    primary_tokens = [t for t in (primary_tokens or []) if t]
    p = urlparse(url or "")

    unique_text_hits = sum(1 for t in terms if t in low_text)
    unique_url_hits = sum(1 for t in terms if t in low_url)
    total_text_hits = sum(low_text.count(t) for t in terms)
    total_url_hits = sum(low_url.count(t) for t in terms)

    # Domain-specific boosts for likely data/reporting pages.
    boost_patterns = ["peims", "tsds", "attendance", "ada", "submission", "calendar", "timeline", "report", "student-data"]
    path_boost = sum(1 for p in boost_patterns if p in low_url)

    score = (
        unique_text_hits * 4.0
        + unique_url_hits * 6.0
        + min(30.0, float(total_text_hits) * 0.25)
        + min(20.0, float(total_url_hits) * 0.75)
        + path_boost * 1.5
    )

    # Penalize generic pages when none of the user's original query tokens are present.
    if primary_tokens and not any(t in low_text or t in low_url for t in primary_tokens):
        score -= 8.0

    # Strongly de-prioritize homepage if it doesn't contain primary intent terms.
    if (p.path or "/") in {"", "/"} and primary_tokens and not any(t in low_text or t in low_url for t in primary_tokens):
        score -= 12.0

    return score


def _crawl_domain_for_query(start_url: str, query_tokens: list[str], max_pages: int, max_depth: int) -> list[tuple[float, str, str]]:
    parsed = urlparse(start_url)
    host = parsed.hostname or ""
    if not host:
        return []

    terms = _expand_research_terms(query_tokens)
    q = [(start_url, 0)]
    seen = {start_url}
    fetched = 0
    hits = []

    while q and fetched < max_pages:
        url, depth = q.pop(0)

        try:
            r = requests.get(url, headers={"User-Agent": "Nova/1.0"}, timeout=25)
            r.raise_for_status()
        except Exception:
            continue

        fetched += 1
        ctype = (r.headers.get("Content-Type") or "").lower()
        if "html" not in ctype:
            continue

        raw = r.text
        text = _extract_text_from_html_content(raw, max_chars=5000)
        score = _score_research_hit(url, text, terms, primary_tokens=query_tokens)
        if score >= 3.0:
            snippet = text[:900]
            hits.append((score, url, snippet))

        if depth >= max_depth:
            continue

        for nxt in _extract_same_host_links(raw, url, host):
            if nxt in seen:
                continue
            seen.add(nxt)
            q.append((nxt, depth + 1))

    return hits


def _scan_candidate_urls_for_query(urls: list[str], query_tokens: list[str], max_pages: int, min_score: float = 3.0) -> list[tuple[float, str, str]]:
    terms = _expand_research_terms(query_tokens)

    def _url_candidate_score(u: str) -> float:
        low = (u or "").lower()
        p = urlparse(u)
        score = 0.0
        for t in terms:
            score += low.count(t) * 2.0
        for k in ("peims", "tsds", "attendance", "ada", "submission", "calendar", "timeline", "report", "student-data"):
            if k in low:
                score += 3.0
        # Prefer content pages over domain root index pages.
        if (p.path or "/") in {"", "/"}:
            score -= 2.0
        # De-prioritize non-html document links during candidate scan.
        if re.search(r"\.(pdf|docx?|xlsx?|pptx?)($|\?)", low):
            score -= 4.0
        return score

    ranked_urls = sorted(urls, key=_url_candidate_score, reverse=True)

    hits = []
    scanned = 0

    for url in ranked_urls:
        if scanned >= max_pages:
            break
        try:
            r = requests.get(url, headers={"User-Agent": "Nova/1.0"}, timeout=20)
            r.raise_for_status()
        except Exception:
            continue

        ctype = (r.headers.get("Content-Type") or "").lower()
        scanned += 1

        if "html" in ctype:
            text = _extract_text_from_html_content(r.text, max_chars=5000)
            score = _score_research_hit(url, text, terms, primary_tokens=query_tokens)
            if score >= min_score:
                hits.append((score, url, text[:900]))
        else:
            # Keep high-relevance document links (pdf/doc/xls/etc.) as sources.
            score = _score_research_hit(url, "", terms, primary_tokens=query_tokens)
            if score >= min_score:
                snippet = f"Non-HTML source ({ctype or 'unknown'}). Use web gather <url> to fetch and inspect."
                hits.append((score, url, snippet))

    return hits


def _fetch_sitemap_urls(domain: str, limit: int = 80) -> list[str]:
    urls = []
    seen = set()
    seen_sitemaps = set()
    queue = [f"https://{domain}/sitemap.xml", f"https://{domain}/sitemap_index.xml"]

    while queue and len(urls) < limit:
        sm = queue.pop(0)
        if sm in seen_sitemaps:
            continue
        seen_sitemaps.add(sm)

        try:
            r = requests.get(sm, headers={"User-Agent": "Nova/1.0"}, timeout=20)
            if r.status_code != 200:
                continue
            body = r.text
            locs = re.findall(r"<loc>\s*(.*?)\s*</loc>", body, flags=re.I)
            for u in locs:
                u = html.unescape((u or "").strip())
                p = urlparse(u)
                if p.scheme not in ("http", "https"):
                    continue
                if not p.hostname:
                    continue
                if not _host_allowed(p.hostname, [domain]):
                    continue

                clean = f"{p.scheme}://{p.netloc}{p.path}"
                if p.query:
                    clean += f"?{p.query}"

                # Nested sitemap index entries often point to other XML sitemap files,
                # including forms like sitemap.xml?page=2.
                if Path(p.path).suffix.lower() == ".xml":
                    if clean not in seen_sitemaps:
                        queue.append(clean)
                    continue

                if clean in seen:
                    continue
                seen.add(clean)
                urls.append(clean)
                if len(urls) >= limit:
                    break
        except Exception:
            continue

    return urls


def _seed_urls_for_domain(domain: str, query_tokens: list[str], max_seed: int = 30) -> list[str]:
    seeds = [f"https://{domain}/"]
    candidates = _fetch_sitemap_urls(domain, limit=max_seed * 3)
    if not candidates:
        return seeds

    terms = _expand_research_terms(query_tokens)
    scored = []
    for u in candidates:
        low = u.lower()
        score = sum(low.count(t) for t in terms)
        for p in ("peims", "tsds", "attendance", "ada", "submission", "calendar", "timeline", "report"):
            if p in low:
                score += 2
        if score > 0:
            scored.append((score, u))

    scored.sort(key=lambda x: x[0], reverse=True)
    for _, u in scored[:max_seed]:
        if u not in seeds:
            seeds.append(u)

    # Fill remaining seed slots with earliest sitemap URLs even if token score is zero,
    # so we still traverse deeper pages when URL text doesn't contain query tokens.
    if len(seeds) < (max_seed + 1):
        for u in candidates:
            if u in seeds:
                continue
            seeds.append(u)
            if len(seeds) >= (max_seed + 1):
                break
    return seeds



def tool_web_fetch(url: str):
    missing = explain_missing("web_fetch", ["web_access"])
    if missing:
        return missing

    if not policy_tools_enabled().get("web", False):
        return "Web tool disabled by policy."

    out = web_fetch(url, WEB_CACHE_DIR)
    if not out.get("ok"):
        err = out.get("error", "unknown error")
        if isinstance(err, str) and "not allowed" in err.lower():
            return _web_allowlist_message(url)
        return f"[FAIL] {err}"

    return f"[OK] Saved: {out['path']} ({out['content_type']}, {out['bytes']} bytes)"


def _provider_request_headers(token: str = "") -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "User-Agent": "Nova/1.0",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
        headers["X-GitHub-Api-Version"] = "2022-11-28"
    return headers


def _clean_html_text(value: str) -> str:
    text = html.unescape(str(value or "").strip())
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text)).strip()


def _looks_like_code_discovery_query(text: str) -> bool:
    low = str(text or "").strip().lower()
    if not low:
        return False
    code_markers = (
        "github",
        "repo",
        "repository",
        "source code",
        "implementation",
        "example repo",
        "code example",
        "sample project",
        "issue",
        "pull request",
        "public repo",
        "open source",
        "function ",
        "class ",
    )
    return any(marker in low for marker in code_markers)


def tool_wikipedia_lookup(query: str):
    missing = explain_missing("web_fetch", ["web_access"])
    if missing:
        return missing

    if not policy_tools_enabled().get("web", False):
        return "Web tool disabled by policy."
    if not web_enabled():
        return "Web tool disabled by policy."

    q = str(query or "").strip()
    if not q:
        return "Usage: wikipedia <topic>"

    try:
        search_resp = requests.get(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "query",
                "list": "search",
                "srsearch": q,
                "format": "json",
                "utf8": 1,
                "srlimit": 3,
            },
            headers=_provider_request_headers(),
            timeout=20,
        )
        search_resp.raise_for_status()
        search_data = search_resp.json()
    except Exception as exc:
        return f"[FAIL] Wikipedia lookup unavailable: {exc}"

    matches = ((search_data.get("query") or {}).get("search") or []) if isinstance(search_data, dict) else []
    if not matches:
        return f"No Wikipedia results found for: {q}"

    title = str((matches[0] or {}).get("title") or q).strip() or q
    summary_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{quote(title.replace(' ', '_'), safe=':_()')}"
    try:
        summary_resp = requests.get(summary_url, headers=_provider_request_headers(), timeout=20)
        summary_resp.raise_for_status()
        summary_data = summary_resp.json()
    except Exception as exc:
        return f"[FAIL] Wikipedia summary unavailable: {exc}"

    display_title = str(summary_data.get("title") or title).strip() or title
    extract = str(summary_data.get("extract") or "").strip()
    page_url = str((((summary_data.get("content_urls") or {}).get("desktop") or {}).get("page") or "")).strip()
    if not page_url:
        page_url = f"https://en.wikipedia.org/wiki/{quote(display_title.replace(' ', '_'))}"

    lines = [f"Wikipedia summary for: {display_title}", page_url]
    if extract:
        lines.append(extract)

    related = []
    for item in matches[1:3]:
        related_title = str((item or {}).get("title") or "").strip()
        if not related_title:
            continue
        related.append((related_title, f"https://en.wikipedia.org/wiki/{quote(related_title.replace(' ', '_'))}"))
    if related:
        lines.append("Related pages:")
        for idx, (related_title, related_url) in enumerate(related, start=1):
            lines.append(f"{idx}. {related_title}")
            lines.append(f"   {related_url}")
    return "\n".join(lines)


def tool_stackexchange_search(query: str):
    missing = explain_missing("web_fetch", ["web_access"])
    if missing:
        return missing

    if not policy_tools_enabled().get("web", False):
        return "Web tool disabled by policy."
    if not web_enabled():
        return "Web tool disabled by policy."

    q = str(query or "").strip()
    if not q:
        return "Usage: stackexchange <query>"

    cfg = policy_web()
    endpoint = str(cfg.get("stackexchange_api_endpoint") or "https://api.stackexchange.com/2.3/search/advanced").strip()
    site = str(cfg.get("stackexchange_site") or "stackoverflow").strip() or "stackoverflow"
    key_env = str(cfg.get("stackexchange_api_key_env") or "STACKEXCHANGE_API_KEY").strip() or "STACKEXCHANGE_API_KEY"
    api_key = str(os.environ.get(key_env) or "").strip()
    params = {
        "order": "desc",
        "sort": "relevance",
        "site": site,
        "q": q,
        "pagesize": 5,
        "accepted": "True",
    }
    if api_key:
        params["key"] = api_key
    try:
        resp = requests.get(endpoint, params=params, headers=_provider_request_headers(), timeout=20)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        return f"[FAIL] StackExchange search unavailable: {exc}"

    items = data.get("items") if isinstance(data, dict) else []
    if not items:
        return f"No StackExchange results found for: {q}"

    lines = [f"StackExchange results for: {q} (site={site})"]
    for idx, item in enumerate(items[:5], start=1):
        title = _clean_html_text(item.get("title") or "")
        link = str(item.get("link") or "").strip()
        score = int(item.get("score") or 0)
        answer_count = int(item.get("answer_count") or 0)
        answered = bool(item.get("is_answered"))
        tags = [str(tag or "").strip() for tag in (item.get("tags") or []) if str(tag or "").strip()][:4]
        if title:
            lines.append(f"{idx}. {title}")
        if link:
            lines.append(f"   {link}")
        meta = [f"score={score}", f"answers={answer_count}", f"answered={answered}"]
        if tags:
            meta.append("tags=" + ", ".join(tags))
        lines.append(f"   {' | '.join(meta)}")
    return "\n".join(lines)

def tool_web_search(query: str):
    missing = explain_missing("web_fetch", ["web_access"])
    if missing:
        return missing

    if not policy_tools_enabled().get("web", False):
        return "Web tool disabled by policy."
    if not web_enabled():
        return "Web tool disabled by policy."

    cfg = policy_web()
    allow_domains = cfg.get("allow_domains") or []
    if not allow_domains:
        return "Web search unavailable: no allow_domains configured in policy."

    q = (query or "").strip()
    if not q:
        return "Usage: web search <query>"

    def _search_via_api(query_text: str, domains: list[str], max_results: int = 5) -> tuple[list[tuple[str, str]], Optional[str]]:
        provider = str(cfg.get("search_provider") or "").strip().lower()
        if provider not in {"brave", "searxng"}:
            return ([], None)

        scoped_query = query_text + " " + " ".join(f"site:{d}" for d in domains[:8])

        if provider == "brave":
            key_env = str(cfg.get("search_api_key_env") or "BRAVE_SEARCH_API_KEY").strip() or "BRAVE_SEARCH_API_KEY"
            api_key = (os.environ.get(key_env) or "").strip()
            if not api_key:
                return ([], f"missing_api_key_env:{key_env}")

            endpoint = str(cfg.get("search_api_endpoint") or "https://api.search.brave.com/res/v1/web/search").strip()
            try:
                r = requests.get(
                    endpoint,
                    params={"q": scoped_query, "count": max(1, min(20, int(max_results)))},
                    headers={
                        "Accept": "application/json",
                        "X-Subscription-Token": api_key,
                        "User-Agent": "Nova/1.0",
                    },
                    timeout=30,
                )
                r.raise_for_status()
                data = r.json()
            except Exception as e:
                return ([], f"api_error:{e}")

            items = []
            for it in ((data.get("web") or {}).get("results") or []):
                url = str(it.get("url") or "").strip()
                title = str(it.get("title") or "").strip() or url
                if not url:
                    continue
                host = urlparse(url).hostname or ""
                if not _host_allowed(host, domains):
                    continue
                items.append((title, url))
                if len(items) >= max_results:
                    break
            return (items, None)

        # searxng provider: self-hosted instance, no API key required.
        endpoint_probe = probe_search_endpoint(str(cfg.get("search_api_endpoint") or "http://127.0.0.1:8080/search").strip(), timeout=5.0, persist_repair=True)
        if not bool(endpoint_probe.get("ok")):
            return ([], f"api_error:{endpoint_probe.get('note')}")
        endpoint = str(endpoint_probe.get("resolved_endpoint") or endpoint_probe.get("endpoint") or "http://127.0.0.1:8080/search").strip()
        try:
            r = requests.get(
                endpoint,
                params={"q": scoped_query, "format": "json"},
                headers={"Accept": "application/json", "User-Agent": "Nova/1.0"},
                timeout=30,
            )
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            return ([], f"api_error:{e}")

        items = []
        for it in (data.get("results") or []):
            url = str(it.get("url") or "").strip()
            title = str(it.get("title") or "").strip() or url
            if not url:
                continue
            host = urlparse(url).hostname or ""
            if not _host_allowed(host, domains):
                continue
            items.append((title, url))
            if len(items) >= max_results:
                break
        return (items, None)

    def _local_search_backend_message(api_err: object) -> str:
        endpoint = str(cfg.get("search_api_endpoint") or "http://127.0.0.1:8080/search").strip()
        err_text = str(api_err or "").strip()
        endpoint_low = endpoint.lower()
        is_local = any(host in endpoint_low for host in ("127.0.0.1", "localhost"))
        if not is_local:
            return ""
        if any(token in err_text.lower() for token in ("404", "not found", "connection refused", "failed to establish a new connection", "max retries exceeded")):
            return (
                "[FAIL] Local web search backend is unavailable. The configured searxng service at "
                f"{endpoint} did not respond correctly. If it runs in Docker, start that service first. "
                "For now, try 'web research <query>' or fetch a specific URL with 'web <url>'."
            )
        return ""

    def _search_via_html(query_text: str, domains: list[str], max_results: int = 5) -> tuple[list[tuple[str, str]], Optional[str]]:
        scoped_query = query_text + " " + " ".join(f"site:{d}" for d in domains[:6])
        try:
            r = requests.get(
                "https://duckduckgo.com/html/",
                params={"q": scoped_query},
                headers={"User-Agent": "Nova/1.0"},
                timeout=30,
            )
            r.raise_for_status()
            page = r.text
        except Exception as e:
            return ([], f"html_error:{e}")

        hrefs = re.findall(r'href=["\']([^"\']+)["\']', page, flags=re.I)
        direct_urls = re.findall(r"https?://[^\s\"'<>]+", page)
        seen = set()
        urls = []
        for h in hrefs:
            u = _decode_search_href(h)
            if not u:
                continue
            host = urlparse(u).hostname or ""
            if not _host_allowed(host, domains):
                continue
            if u in seen:
                continue
            seen.add(u)
            urls.append((u, u))
            if len(urls) >= max_results:
                break

        if len(urls) < max_results:
            for u in direct_urls:
                host = urlparse(u).hostname or ""
                if not _host_allowed(host, domains):
                    continue
                if u in seen:
                    continue
                seen.add(u)
                urls.append((u, u))
                if len(urls) >= max_results:
                    break
        return (urls, None)

    provider = str(cfg.get("search_provider") or "").strip().lower()
    rows, api_err = _search_via_api(q, allow_domains, max_results=5)
    provider_used = f"api:{provider}" if rows else "html"
    if not rows:
        rows, html_err = _search_via_html(q, allow_domains, max_results=5)
        if not rows and api_err:
            backend_msg = _local_search_backend_message(api_err)
            if backend_msg:
                return backend_msg
            if "404" in str(api_err).lower() or "not found" in str(api_err).lower():
                return (
                    "[FAIL] Web search service returned 404. Try a different phrase, use 'web research <query>', "
                    "or fetch a specific URL with 'web <url>'."
                )
            return f"[FAIL] Web search unavailable. API reason={api_err}; HTML fallback failed={html_err}"

    if not rows:
        msg = "No allowlisted web results found for that query."
        # Offer a helpful allowlist explanation
        msg += "\n\n" + _web_allowlist_message(query)
        return msg

    lines = [f"Web results (allowlisted, provider={provider_used}):"]
    for i, (title, u) in enumerate(rows, start=1):
        if title and title != u:
            lines.append(f"{i}. {title}")
            lines.append(f"   {u}")
        else:
            lines.append(f"{i}. {u}")
    lines.append("Tip: run 'web gather <url>' to fetch and summarize one result.")
    return "\n".join(lines)


def tool_web_gather(url: str):
    missing = explain_missing("web_fetch", ["web_access"])
    if missing:
        return missing

    if not policy_tools_enabled().get("web", False):
        return "Web tool disabled by policy."

    out = web_fetch(url, WEB_CACHE_DIR)
    if not out.get("ok"):
        err = out.get("error", "unknown error")
        if isinstance(err, str) and "not allowed" in err.lower():
            return _web_allowlist_message(url)
        return f"[FAIL] {err}"

    p = Path(out["path"])
    snippet = _extract_text_from_path(p, max_chars=2200)
    if snippet:
        return (
            f"[OK] Saved: {out['path']} ({out['content_type']}, {out['bytes']} bytes)\n"
            f"Summary snippet:\n{snippet}"
        )

    ctype = str(out.get("content_type") or "").lower()
    if "html" in ctype:
        return (
            f"[OK] Saved: {out['path']} ({out['content_type']}, {out['bytes']} bytes)\n"
            "I could access the page, but I couldn't extract readable content. "
            "It may be JavaScript-heavy/dynamic, and I do not run a browser renderer in this path."
        )

    return f"[OK] Saved: {out['path']} ({out['content_type']}, {out['bytes']} bytes)"


def tool_web_research(query: str, continue_mode: bool = False):
    missing = explain_missing("web_fetch", ["web_access"])
    if missing:
        return missing

    if not policy_tools_enabled().get("web", False):
        return "Web tool disabled by policy."
    if not web_enabled():
        return "Web tool disabled by policy."

    cfg = policy_web()
    allow_domains = cfg.get("allow_domains") or []
    if not allow_domains:
        return "Web research unavailable: no allow_domains configured in policy."

    q = (query or "").strip()
    if continue_mode:
        if not WEB_RESEARCH_SESSION.has_results():
            return "No active web research session. Start with: web research <query>"

        max_results = max(1, min(40, int((policy_web().get("research_max_results") or 8))))
        page = WEB_RESEARCH_SESSION.next_page(max_results)
        if page is None:
            return "No active web research session. Start with: web research <query>"
        if not page.rows and page.start >= page.total:
            return "No more cached research results. Start a new search with: web research <query>"

        lines = [f"Web research results (continued) for: {WEB_RESEARCH_SESSION.query}"]
        rank = page.start
        for score, url, snippet in page.rows:
            rank += 1
            lines.append(f"{rank}. [{score:.1f}] {url}")
            if snippet:
                lines.append(f"   {snippet[:220]}")

        remaining = WEB_RESEARCH_SESSION.remaining_count()
        if remaining > 0:
            lines.append(f"{remaining} more result(s) available. Type 'web continue' to keep going.")
        else:
            lines.append("End of cached research results.")

        lines.append("Tip: run 'web gather <url>' for any source above to fetch and summarize it fully.")
        return "\n".join(lines)

    if not q:
        return "Usage: web research <query>"

    toks = _tokenize(q)
    if not toks:
        return "Query too short for web research."

    domains_limit = max(1, min(12, int(cfg.get("research_domains_limit") or 4)))
    pages_per_domain = max(2, min(50, int(cfg.get("research_pages_per_domain") or 8)))
    max_depth = max(0, min(3, int(cfg.get("research_max_depth") or 1)))
    max_results = max(1, min(40, int(cfg.get("research_max_results") or 8)))
    seeds_per_domain = max(1, min(40, int(cfg.get("research_seeds_per_domain") or 8)))
    scan_pages_per_domain = max(2, min(200, int(cfg.get("research_scan_pages_per_domain") or 12)))
    min_score = max(0.0, min(10.0, float(cfg.get("research_min_score") or 3.0)))

    domains = allow_domains[:max(1, min(domains_limit, len(allow_domains)))]
    all_hits = []
    for d in domains:
        sitemap_urls = _fetch_sitemap_urls(d, limit=max(200, scan_pages_per_domain * 25))
        if sitemap_urls:
            all_hits.extend(_scan_candidate_urls_for_query(sitemap_urls, toks, max_pages=max(2, scan_pages_per_domain), min_score=min_score))

        seeds = _seed_urls_for_domain(d, toks, max_seed=max(1, seeds_per_domain))
        for start in seeds:
            all_hits.extend(_crawl_domain_for_query(start, toks, max_pages=max(2, pages_per_domain), max_depth=max(0, max_depth)))

    if not all_hits:
        return "No relevant pages found across allowlisted domains for that query."

    all_hits.sort(key=lambda x: x[0], reverse=True)
    used = set()
    ordered = []
    for score, url, snippet in all_hits:
        if url in used:
            continue
        used.add(url)
        ordered.append((score, url, snippet))

    WEB_RESEARCH_SESSION.set_results(q, ordered)

    max_results = max(1, min(40, int((cfg.get("research_max_results") or 8))))
    page = WEB_RESEARCH_SESSION.next_page(max_results)
    if page is None:
        return "No relevant pages found across allowlisted domains for that query."

    lines = [f"Web research results (allowlisted crawl) for: {q}"]
    rank = page.start
    for score, url, snippet in page.rows:
        rank += 1
        lines.append(f"{rank}. [{score:.1f}] {url}")
        if snippet:
            lines.append(f"   {snippet[:220]}")

    remaining = WEB_RESEARCH_SESSION.remaining_count()
    if remaining > 0:
        lines.append(f"{remaining} more result(s) available. Type 'web continue' to keep going.")
    else:
        lines.append("No more results pending for this query.")

    lines.append("Tip: run 'web gather <url>' for any source above to fetch and summarize it fully.")
    return "\n".join(lines)


def handle_keywords(text: str):
    raw = str(text or "").strip()
    low = raw.lower()

    if low in {"screen", "look at my screen"}:
        return ("tool", "screen", tool_screen())

    if low.startswith("camera"):
        prompt = text[len("camera"):].strip() or "what do you see"
        return ("tool", "camera", tool_camera(prompt))

    if low == "ls" or _is_brief_command_form(raw, "ls", max_tokens=2):
        parts = raw.split(maxsplit=1)
        sub = parts[1] if len(parts) > 1 else ""
        return ("tool", "ls", tool_ls(sub))

    if _is_brief_command_form(raw, "read", max_tokens=2):
        path = raw.split(maxsplit=1)[1]
        return ("tool", "read", tool_read(path))

    if _is_brief_command_form(raw, "find", max_tokens=3):
        parts = raw.split(maxsplit=2)
        keyword = parts[1] if len(parts) > 1 else ""
        folder = parts[2] if len(parts) > 2 else ""
        return ("tool", "find", tool_find(keyword, folder))

    if low in {"health", "status"}:
        return ("tool", "health", tool_health())

    return None


def _is_brief_command_form(text: str, command: str, max_tokens: int) -> bool:
    raw = str(text or "").strip()
    low = raw.lower()
    if not low.startswith(f"{command} "):
        return False
    if raw.endswith("?"):
        return False
    tail = raw[len(command):].strip()
    if not tail:
        return False
    tokens = tail.split()
    if len(tokens) < 1 or len(tokens) + 1 > max_tokens:
        return False
    if any(mark in raw for mark in (",", ";", ":")):
        return False
    return True


# =========================
# Commands (typed) for kb / patch
# =========================
def handle_commands(
    user_text: str,
    session_turns: Optional[list[tuple[str, str]]] = None,
    session: Optional[ConversationSession] = None,
) -> Optional[str]:
    t = _strip_invocation_prefix((user_text or "").strip())
    low = t.lower()

    if low in {"chat context", "show chat context", "context", "chatctx"}:
        rendered = _render_chat_context(session_turns or [])
        if not rendered:
            return "No chat context is available yet in this session."
        return "Current chat context:\n" + rendered

    if low in {"queue", "queue status", "work queue", "show queue", "standing work queue"}:
        return str(execute_planned_action("queue_status") or "")

    if low in {"pulse", "nova pulse", "show pulse", "system pulse"}:
        return str(execute_planned_action("pulse") or "")

    if low in {"update now", "apply update now", "apply updates now"}:
        return str(execute_planned_action("update_now") or "")

    if low.startswith("update now confirm"):
        token = t.split(maxsplit=3)[3].strip() if len(t.split(maxsplit=3)) >= 4 else ""
        args = [token] if token else []
        return str(execute_planned_action("update_now_confirm", args) or "")

    if low in {"update now cancel", "cancel update now"}:
        return str(execute_planned_action("update_now_cancel") or "")

    if "domanins" in low and any(k in low for k in ["domain", "domanins", "allow", "policy", "list", "show"]):
        return "It looks like you meant \"domains\".\n" + list_allowed_domains()

    if low in {"domains", "list domains", "show domains", "list the domains", "allowed domains", "allow domains", "policy domains"}:
        return list_allowed_domains()

    if low.startswith("policy allow "):
        value = t.split(maxsplit=2)[2] if len(t.split(maxsplit=2)) >= 3 else ""
        return policy_allow_domain(value)

    if low.startswith("policy remove "):
        value = t.split(maxsplit=2)[2] if len(t.split(maxsplit=2)) >= 3 else ""
        return policy_remove_domain(value)

    if low.startswith("policy audit"):
        parts = t.split()
        n = 20
        if len(parts) >= 3:
            try:
                n = int(parts[2])
            except Exception:
                n = 20
        return policy_audit(n)

    if low in {"web mode", "web limits", "web research limits"}:
        return web_mode_status()

    if low.startswith("web mode "):
        mode = t.split(maxsplit=2)[2] if len(t.split(maxsplit=2)) >= 3 else ""
        return set_web_mode(mode)

    if low.startswith("location coords ") or low.startswith("set location coords "):
        value = t.split(maxsplit=2)[2] if len(t.split(maxsplit=2)) >= 3 else ""
        return set_location_coords(value)

    if low in {"weather", "check weather", "weather current location", "weather current"}:
        return str(execute_planned_action("weather_current_location") or "")

    if low.startswith("weather ") or low.startswith("check weather "):
        parts = t.split(maxsplit=2)
        location_value = parts[2] if len(parts) >= 3 else (parts[1] if len(parts) >= 2 else "")
        return str(execute_planned_action("weather_location", [location_value]) or "")

    normalized = _normalize_turn_text(t)
    if normalized in {"use your physical location", "use your location nova", "use your location"}:
        return str(execute_planned_action("weather_current_location") or "")

    if _is_saved_location_weather_query(normalized) or (
        "weather" in normalized and any(phrase in normalized for phrase in (
            "give me",
            "can you give me",
            "what is",
            "what's",
            "forecast",
            "current",
            "today",
            "now",
        ))
    ):
        live = runtime_device_location_payload()
        if (live.get("available") and not live.get("stale")) or get_saved_location_text() or _coords_from_saved_location():
            return str(execute_planned_action("weather_current_location") or "")
        return _need_confirmed_location_message() + " My location is unknown until live tracking is active, or you tell me or save coordinates."

    if _is_location_request(normalized):
        return _location_reply()

    if low.startswith("remember:"):
        return mem_remember_fact(t.split(":", 1)[1])

    if low in {"what can you do", "capabilities", "show capabilities"}:
        return describe_capabilities()

    if low in {"mem stats", "memory stats"}:
        return mem_stats()

    if low in {"mix", "mix status", "language status", "spanglish status"}:
        current = int(getattr(session, "language_mix_spanish_pct", 0) or 0)
        return f"Language mix status: English default with Spanish mix at {current}%"

    if low.startswith("set mix "):
        m = re.search(r"set\s+mix\s+(\d{1,3})", low)
        if not m:
            return "Usage: set mix <0-100>"
        value = _clamp_language_mix(int(m.group(1)))
        if session is not None:
            session.set_language_mix_spanish_pct(value)
        return f"Language mix updated: Spanish {value}% (English {100 - value}%)"

    if low in {"more spanish", "more espanol", "mas espanol"}:
        current = int(getattr(session, "language_mix_spanish_pct", 0) or 0)
        value = _clamp_language_mix(current + 20)
        if session is not None:
            session.set_language_mix_spanish_pct(value)
        return f"Language mix nudged toward Spanish: {value}%"

    if low in {"more english", "menos espanol"}:
        current = int(getattr(session, "language_mix_spanish_pct", 0) or 0)
        value = _clamp_language_mix(current - 20)
        if session is not None:
            session.set_language_mix_spanish_pct(value)
        return f"Language mix nudged toward English: Spanish {value}%"

    if low in {"english default", "default english", "english only"}:
        if session is not None:
            session.set_language_mix_spanish_pct(0)
        return "English is now the default response language for this session."

    if low.startswith("mem audit ") or low.startswith("memory audit "):
        q = t.split(maxsplit=2)[2] if len(t.split(maxsplit=2)) >= 3 else ""
        return mem_audit(q)

    if low == "kb" or low == "kb help":
        return ("KB commands:\n"
                "  kb list\n"
                "  kb use <pack>\n"
                "  kb off\n"
                "  kb add <zip_path> <pack_name>\n")

    if low == "kb list":
        return kb_list_packs()

    if low.startswith("kb use "):
        name = t.split(maxsplit=2)[2].strip()
        return kb_set_active(name)

    if low == "kb off":
        return kb_set_active(None)

    if low.startswith("kb add "):
        parts = t.split(maxsplit=3)
        if len(parts) < 4:
            return "Usage: kb add <zip_path> <pack_name>"
        return kb_add_zip(parts[2], parts[3])

    if low == "patch" or low == "patch help":
        return ("Patch commands:\n"
            "  patch preview <zip_path>  # preview proposal without applying\n"
            "  patch apply <zip_path> [--force]\n"
            "      # preview runs automatically; use --force to bypass preview check\n"
            "  patch rollback   (roll back to last snapshot)\n"
            )
    if low.startswith("patch apply "):
        raw = t.split(maxsplit=2)[2].strip() if len(t.split(maxsplit=2)) >= 3 else ""
        # detect --force flag
        force = False
        if "--force" in raw:
            force = True
            raw = raw.replace("--force", "").strip()
        return execute_patch_action("apply", raw, force=force, is_admin=True)

    if low.startswith("patch preview "):
        p = t.split(maxsplit=2)[2].strip() if len(t.split(maxsplit=2)) >= 3 else ""
        return execute_patch_action("preview", p, is_admin=True)

    if low == "patch list-previews":
        return execute_patch_action("list_previews", is_admin=True)

    if low.startswith("patch show "):
        p = t.split(maxsplit=2)[2].strip() if len(t.split(maxsplit=2)) >= 3 else ""
        return execute_patch_action("show", p, is_admin=True)

    if low.startswith("patch approve "):
        p = t.split(maxsplit=2)[2].strip() if len(t.split(maxsplit=2)) >= 3 else ""
        return execute_patch_action("approve", p, is_admin=True)

    if low.startswith("patch reject "):
        p = t.split(maxsplit=2)[2].strip() if len(t.split(maxsplit=2)) >= 3 else ""
        return execute_patch_action("reject", p, is_admin=True)

    if low == "patch rollback":
        return execute_patch_action("rollback", is_admin=True)

    if low == "kidney" or low == "kidney help":
        return (
            "Kidney commands:\n"
            "  kidney status\n"
            "  kidney now\n"
            "  kidney dry-run\n"
            "  kidney protect <pattern>\n"
        )

    if low == "kidney status":
        import kidney

        return kidney.render_status()

    if low in {
        "phase2",
        "phase2 status",
        "phase 2 status",
        "phase2 audit",
        "phase 2 audit",
        "post phase 2 audit",
        "post-phase-2 audit",
    }:
        return str(execute_planned_action("phase2_audit") or "")

    if low == "kidney now":
        import kidney

        return kidney.render_run(dry_run=False)

    if low == "kidney dry-run":
        import kidney

        return kidney.render_run(dry_run=True)

    if low.startswith("kidney protect "):
        import kidney

        pattern = t.split(maxsplit=2)[2].strip() if len(t.split(maxsplit=2)) >= 3 else ""
        return kidney.add_protect_pattern(pattern)

    # Teach workflow: remember examples and propose patches
    if low.startswith("teach "):
        parts = t.split(maxsplit=1)
        sub = parts[1].strip() if len(parts) > 1 else ""
        if sub.startswith("remember "):
            # format: teach remember <orig> => <correction>
            body = sub[len("remember "):].strip()
            if "=>" in body:
                orig, corr = body.split("=>", 1)
                orig = orig.strip().strip("\"'")
                corr = corr.strip().strip("\"'")
                return _teach_store_example(orig, corr)
            return "Usage: teach remember <original text> => <correction text>"

        if sub == "list":
            return _teach_list_examples()

        if sub.startswith("propose"):
            desc = sub[len("propose"):].strip()
            return _teach_propose_patch(desc)

        if sub.startswith("autoapply "):
            body = sub[len("autoapply "):].strip()
            # support: "autoapply <zip>" (dry-run/staging only)
            # and: "autoapply apply <zip>" or "autoapply <zip> --apply" to actually apply
            apply_live = False
            zp = body
            if body.startswith("apply "):
                apply_live = True
                zp = body[len("apply "):].strip()
            elif "--apply" in body:
                apply_live = True
                zp = body.replace("--apply", "").strip()
            return _teach_autoapply_proposal(zp, apply_live=apply_live)

        if sub.startswith("apply "):
            zp = sub[len("apply "):].strip()
            # direct apply (no staging tests) — still uses patch_apply
            return execute_patch_action("apply", zp, is_admin=True)

        return ("Teach commands:\n"
            "  teach remember <orig> => <correction>\n"
            "  teach list\n"
            "  teach propose <description>\n"
            "  teach autoapply <zip>              # run staging tests (safe)\n"
            "  teach autoapply apply <zip>       # run staging tests and APPLY if tests pass\n"
            "  teach autoapply <zip> --apply     # same as above\n"
    )
    if low == "inspect":
        data = inspect_environment()
        return format_report(data)

    # casual_mode control: casual_mode status|on|off|toggle
    if low.startswith("casual_mode") or low.startswith("casual mode"):
        parts = low.replace("casual mode", "casual_mode").split()
        cmd = parts[1] if len(parts) > 1 else "status"
        statefile = DEFAULT_STATEFILE
        try:
            if cmd in {"on", "1", "true"}:
                os.environ["CASUAL_MODE"] = "1"
                set_core_state(statefile, "casual_mode", True)
                return "casual_mode enabled"
            if cmd in {"off", "0", "false"}:
                os.environ["CASUAL_MODE"] = "0"
                set_core_state(statefile, "casual_mode", False)
                return "casual_mode disabled"
            if cmd == "toggle":
                cur = os.environ.get("CASUAL_MODE", "1").lower() in {"1", "true"}
                nxt = not cur
                os.environ["CASUAL_MODE"] = "1" if nxt else "0"
                set_core_state(statefile, "casual_mode", bool(nxt))
                return f"casual_mode set to {os.environ['CASUAL_MODE']}"
            # status
            cur = os.environ.get("CASUAL_MODE", "1")
            return f"casual_mode={cur}"
        except Exception as e:
            return f"Failed to set casual_mode: {e}"

    if low in {"behavior stats", "behavior metrics", "behavior"}:
        return json.dumps(behavior_get_metrics(), ensure_ascii=True, indent=2)

    if low in {"learning state", "learning status", "self correction status", "what are you learning"}:
        m = behavior_get_metrics()
        return (
            "Learning state:\n"
            f"- correction_learned: {int(m.get('correction_learned', 0))}\n"
            f"- correction_applied: {int(m.get('correction_applied', 0))}\n"
            f"- self_correction_applied: {int(m.get('self_correction_applied', 0))}\n"
            f"- deterministic_hit: {int(m.get('deterministic_hit', 0))}\n"
            f"- llm_fallback: {int(m.get('llm_fallback', 0))}\n"
            f"- top_repeated_failure_class: {m.get('top_repeated_failure_class', '') or 'none'}\n"
            f"- top_repeated_correction_class: {m.get('top_repeated_correction_class', '') or 'none'}\n"
            f"- routing_stable: {bool(m.get('routing_stable', True))}\n"
            f"- unsupported_claims_blocked: {bool(m.get('unsupported_claims_blocked', False))}\n"
            f"- last_event: {m.get('last_event', '')}"
        )

    return None


# =========================
# Main loop
# =========================
def run_loop(tts):
    whisper = None
    if _ensure_voice_deps() and WhisperModel is not None:
        print("Nova Core: loading Whisper (CPU mode)...", flush=True)
        whisper = WhisperModel(whisper_size(), device="cpu", compute_type="int8")
    else:
        warn(f"Voice mode disabled; typed chat still works. (Reason: {VOICE_IMPORT_ERR})")

    print("\nNova Core is ready.", flush=True)
    print("Commands: screen | camera <prompt> | web <url> | web search <query> | web research <query> | web gather <url> | weather <location-or-lat,lon> | check weather <location> | weather current location | location coords <lat,lon> | domains | policy allow <domain> | chat context | queue status | ls [folder] | read <file> | find <kw> [folder] | health | capabilities | inspect", flush=True)
    print("Press ENTER for voice. Or type a message/command and press ENTER. Type 'q' to quit.\n", flush=True)

    recent_tool_context = ""
    recent_web_urls: list[str] = []
    session_turns: list[tuple[str, str]] = []
    session_state = ConversationSession()
    pending_action_ledger: Optional[dict] = None
    pending_action: Optional[dict] = session_state.pending_action
    conversation_state: Optional[dict] = session_state.conversation_state
    prefer_web_for_data_queries = session_state.prefer_web_for_data_queries
    language_mix_spanish_pct = int(session_state.language_mix_spanish_pct or 0)

    def _set_pending_action(value: Optional[dict]) -> None:
        nonlocal pending_action
        pending_action = value if isinstance(value, dict) else None
        session_state.set_pending_action(pending_action)

    def _set_conversation_state(value: Optional[dict]) -> None:
        nonlocal conversation_state
        conversation_state = value if isinstance(value, dict) else None
        session_state.set_conversation_state(conversation_state)

    def _set_prefer_web_for_data_queries(value: bool) -> None:
        nonlocal prefer_web_for_data_queries
        prefer_web_for_data_queries = bool(value)
        session_state.set_prefer_web_for_data_queries(prefer_web_for_data_queries)

    def _set_language_mix_spanish_pct(value: int) -> None:
        nonlocal language_mix_spanish_pct
        language_mix_spanish_pct = _clamp_language_mix(value)
        session_state.set_language_mix_spanish_pct(language_mix_spanish_pct)

    def _sync_pending_conversation_tracking() -> None:
        if not pending_action_ledger:
            return
        subject = session_state.active_subject()
        pending_action_ledger["active_subject"] = subject
        record = pending_action_ledger.get("record")
        if isinstance(record, dict):
            record["active_subject"] = subject
            record["continuation_used"] = bool(pending_action_ledger.get("continuation_used", False))

    def _trace(stage: str, outcome: str, detail: str = "", **data) -> None:
        if not pending_action_ledger:
            return
        action_ledger_add_step(pending_action_ledger.get("record"), stage, outcome, detail, **data)

    def _flush_pending_action_ledger() -> None:
        nonlocal pending_action_ledger
        if not pending_action_ledger:
            return
        try:
            start_idx = int(pending_action_ledger.get("start_idx", len(session_turns)))
        except Exception:
            start_idx = len(session_turns)

        final_answer = ""
        for role, txt in session_turns[start_idx:]:
            if role == "assistant":
                final_answer = txt

        if not final_answer:
            final_answer = str(pending_action_ledger.get("tool_result") or "")

        finalize_action_ledger_record(
            pending_action_ledger.get("record") or {},
            final_answer=final_answer,
            planner_decision=str(pending_action_ledger.get("planner_decision") or "deterministic"),
            tool=str(pending_action_ledger.get("tool") or ""),
            tool_args=pending_action_ledger.get("tool_args") if isinstance(pending_action_ledger.get("tool_args"), dict) else {},
            tool_result=str(pending_action_ledger.get("tool_result") or ""),
            grounded=pending_action_ledger.get("grounded") if isinstance(pending_action_ledger.get("grounded"), bool) else None,
            intent=str(pending_action_ledger.get("intent") or ""),
            active_subject=str(pending_action_ledger.get("active_subject") or ""),
            continuation_used=bool(pending_action_ledger.get("continuation_used", False)),
            reply_contract=str(pending_action_ledger.get("reply_contract") or ""),
            reply_outcome=pending_action_ledger.get("reply_outcome") if isinstance(pending_action_ledger.get("reply_outcome"), dict) else {},
            routing_decision=pending_action_ledger.get("routing_decision") if isinstance(pending_action_ledger.get("routing_decision"), dict) else {},
            reflection_payload=build_turn_reflection(
                session_state,
                entry_point="cli",
                session_id="cli",
                current_decision={
                    "user_input": str((pending_action_ledger.get("record") or {}).get("user_input") or ""),
                    "planner_decision": str(pending_action_ledger.get("planner_decision") or "deterministic"),
                    "tool": str(pending_action_ledger.get("tool") or ""),
                    "tool_result": str(pending_action_ledger.get("tool_result") or ""),
                    "final_answer": final_answer,
                    "reply_contract": str(pending_action_ledger.get("reply_contract") or ""),
                    "reply_outcome": pending_action_ledger.get("reply_outcome") if isinstance(pending_action_ledger.get("reply_outcome"), dict) else {},
                    "turn_acts": list(pending_action_ledger.get("turn_acts") or []),
                    "grounded": pending_action_ledger.get("grounded") if isinstance(pending_action_ledger.get("grounded"), bool) else None,
                    "active_subject": str(pending_action_ledger.get("active_subject") or session_state.active_subject() or ""),
                    "continuation_used": bool(pending_action_ledger.get("continuation_used", False)),
                    "pending_action": session_state.pending_action,
                    "routing_decision": _finalize_routing_decision(
                        pending_action_ledger.get("routing_decision") if isinstance(pending_action_ledger.get("routing_decision"), dict) else {},
                        planner_decision=str(pending_action_ledger.get("planner_decision") or "deterministic"),
                        reply_contract=str(pending_action_ledger.get("reply_contract") or ""),
                        reply_outcome=pending_action_ledger.get("reply_outcome") if isinstance(pending_action_ledger.get("reply_outcome"), dict) else {},
                        turn_acts=list(pending_action_ledger.get("turn_acts") or []),
                    ),
                    "route_summary": action_ledger_route_summary((pending_action_ledger.get("record") or {}).get("route_trace")),
                },
            ),
        )
        pending_action_ledger = None

    while True:
        _flush_pending_action_ledger()
        session_state.reset_turn_flags()
        raw = input("> ").strip()
        input_source = "typed"

        if raw.lower() == "q":
            break

        if raw:
            user_text = raw
            m_idx = re.match(r"^\s*web\s+gather\s+(\d+)\s*$", user_text, flags=re.I)
            if m_idx and recent_web_urls:
                idx = int(m_idx.group(1))
                if 1 <= idx <= len(recent_web_urls):
                    user_text = f"web gather {recent_web_urls[idx - 1]}"
            user_text = _strip_invocation_prefix(user_text)
            print(f"You (typed): {user_text}", flush=True)
        else:
            input_source = "voice"
            if not whisper:
                print("Nova: voice is disabled on this machine right now. Type your message instead.\n", flush=True)
                continue
            audio = record_seconds(RECORD_SECONDS)
            print("Nova: transcribing...", flush=True)
            user_text = transcribe(whisper, audio)
            if not user_text:
                print("Nova: (heard nothing)\n", flush=True)
                continue
            user_text = _strip_invocation_prefix(user_text)
            print(f"You: {user_text}", flush=True)

        session_turns.append(("user", user_text))
        pending_action_ledger = {
            "record": start_action_ledger_record(
                user_text,
                channel="cli",
                session_id=get_active_user() or "",
                input_source=input_source,
                active_subject=session_state.active_subject(),
            ),
            "start_idx": len(session_turns),
            "intent": _infer_turn_intent(user_text),
            "planner_decision": "deterministic",
            "tool": "",
            "tool_args": {},
            "tool_result": "",
            "grounded": None,
            "active_subject": session_state.active_subject(),
            "continuation_used": False,
        }

        routed_user_text = user_text
        turn_direction = {
            "primary": "general_chat",
            "effective_query": user_text,
            "analysis_reason": "",
            "turn_acts": [],
            "identity_focused": False,
            "bypass_pattern_routes": False,
        }
        try:
            turn_direction = _determine_turn_direction(
                session_turns,
                user_text,
                active_subject=session_state.active_subject(),
                pending_action=pending_action,
            )
            routed_user_text = str(turn_direction.get("effective_query") or user_text)
            _set_language_mix_spanish_pct(_auto_adjust_language_mix(language_mix_spanish_pct, routed_user_text))
            turn_acts = [str(item).strip() for item in list(turn_direction.get("turn_acts") or []) if str(item).strip()]
            if pending_action_ledger is not None:
                pending_action_ledger["turn_acts"] = turn_acts
                record = pending_action_ledger.get("record")
                if isinstance(record, dict):
                    record["turn_acts"] = list(turn_acts)
            _trace(
                "direction_analysis",
                str(turn_direction.get("primary") or "general_chat"),
                str(turn_direction.get("analysis_reason") or "")[:120],
                effective_query=routed_user_text[:180],
                turn_acts=",".join(turn_acts),
                identity_focused=bool(turn_direction.get("identity_focused")),
                bypass_pattern_routes=bool(turn_direction.get("bypass_pattern_routes")),
            )
        except Exception:
            routed_user_text = user_text
            turn_acts = []

        intent_rule = TURN_SUPERVISOR.evaluate_rules(
            routed_user_text,
            manager=session_state,
            turns=session_turns,
            phase="intent",
            entry_point="cli",
        )
        if not _supervisor_result_has_route(intent_rule):
            runtime_intent = _runtime_set_location_intent(routed_user_text, pending_action=pending_action)
            if isinstance(runtime_intent, dict):
                intent_rule = runtime_intent
        if not _supervisor_result_has_route(intent_rule):
            llm_intent = _llm_classify_routing_intent(routed_user_text, turns=session_turns)
            if isinstance(llm_intent, dict) and _supervisor_result_has_route(llm_intent):
                intent_rule = llm_intent
                _trace("llm_routing", "matched", intent=str(intent_rule.get("intent") or ""))
        if not _supervisor_result_has_route(intent_rule) and _should_clarify_unlabeled_numeric_turn(
            routed_user_text,
            pending_action=pending_action,
            current_state=conversation_state,
        ):
            final = _ensure_reply(_unlabeled_numeric_turn_reply(routed_user_text))
            _set_conversation_state(_make_conversation_state("numeric_reference_clarify", value=str(routed_user_text or "").strip()))
            _sync_pending_conversation_tracking()
            if pending_action_ledger is not None:
                pending_action_ledger["planner_decision"] = "ask_clarify"
                pending_action_ledger["grounded"] = False
            _trace("numeric_clarify", "blocked")
            print(f"Nova: {final}\n", flush=True)
            session_turns.append(("assistant", final))
            speak_chunked(tts, final)
            continue
        if "mixed" in turn_acts:
            final = _ensure_reply(_mixed_info_request_clarify_reply(routed_user_text))
            if pending_action_ledger is not None:
                pending_action_ledger["planner_decision"] = "ask_clarify"
                pending_action_ledger["grounded"] = False
                pending_action_ledger["reply_contract"] = "turn.clarify_mixed_intent"
                pending_action_ledger["reply_outcome"] = {
                    "intent": "clarify_mixed_turn",
                    "kind": "mixed_info_request",
                    "reply_contract": "turn.clarify_mixed_intent",
                }
            _trace("mixed_turn_clarify", "blocked")
            print(f"Nova: {final}\n", flush=True)
            session_turns.append(("assistant", final))
            speak_chunked(tts, final)
            continue
        # DO NOT add new deterministic phrase routing here.
        # Add a supervisor rule plus shared core action execution instead.
        # See docs/SUPERVISOR_CONTRACT.md.
        handled_intent, intent_msg, intent_state, intent_effects = _handle_supervisor_intent(
            intent_rule,
            routed_user_text,
            turns=session_turns,
            input_source=input_source,
            entry_point="cli",
        )
        if pending_action_ledger is not None:
            pending_action_ledger["routing_decision"] = _build_routing_decision(
                routed_user_text,
                entry_point="cli",
                intent_result=intent_rule,
                handle_result=None,
                reply_contract=str(intent_effects.get("reply_contract") or "") if isinstance(intent_effects, dict) else "",
                reply_outcome=dict(intent_effects.get("reply_outcome") or {}) if isinstance(intent_effects, dict) and isinstance(intent_effects.get("reply_outcome"), dict) else {},
                turn_acts=turn_acts,
            )
        if handled_intent:
            weather_mode = str(intent_rule.get("weather_mode") or "").strip().lower()
            intent_name = str(intent_rule.get("intent") or "").strip().lower()
            _emit_supervisor_intent_trace(intent_rule, user_text=routed_user_text)
            final = _ensure_reply(intent_msg)
            if isinstance(intent_effects, dict) and "pending_action" in intent_effects:
                _set_pending_action(intent_effects.get("pending_action"))
            if isinstance(intent_effects, dict):
                pending_action_ledger["reply_contract"] = str(intent_effects.get("reply_contract") or "")
                pending_action_ledger["reply_outcome"] = dict(intent_effects.get("reply_outcome") or {}) if isinstance(intent_effects.get("reply_outcome"), dict) else {}
            if pending_action_ledger is not None and intent_name == "web_research_family":
                reply_outcome = pending_action_ledger.get("reply_outcome") if isinstance(pending_action_ledger.get("reply_outcome"), dict) else {}
                tool_name = str((reply_outcome or {}).get("tool_name") or intent_rule.get("tool_name") or "web_research").strip().lower() or "web_research"
                query = str((reply_outcome or {}).get("query") or intent_rule.get("query") or routed_user_text).strip()
                pending_action_ledger["planner_decision"] = "run_tool"
                pending_action_ledger["tool"] = tool_name
                pending_action_ledger["tool_args"] = {"args": [query]} if query else {"args": []}
                pending_action_ledger["tool_result"] = str(final or "")
                pending_action_ledger["grounded"] = bool(str(final or "").strip())
                _trace("action_planner", "run_tool", tool=tool_name)
                _trace("tool_execution", "ok", tool=tool_name, grounded=bool(str(final or "").strip()))
            elif pending_action_ledger is not None and intent_name == "weather_lookup" and weather_mode in {"current_location", "explicit_location"}:
                tool_name = "weather_current_location" if weather_mode == "current_location" else "weather_location"
                pending_action_ledger["planner_decision"] = "run_tool"
                pending_action_ledger["tool"] = tool_name
                if tool_name == "weather_location":
                    pending_action_ledger["tool_args"] = {"args": [str(intent_rule.get("location_value") or "").strip()]}
                pending_action_ledger["tool_result"] = str(final or "")
                pending_action_ledger["grounded"] = bool(str(final or "").strip())
                _trace("action_planner", "run_tool", tool=tool_name)
                _trace("tool_execution", "ok", tool=tool_name, grounded=bool(str(final or "").strip()))
            elif pending_action_ledger is not None and intent_name == "weather_lookup" and weather_mode == "clarify":
                pending_action_ledger["planner_decision"] = "ask_clarify"
                pending_action_ledger["grounded"] = False
                _trace("action_planner", "ask_clarify")
                _trace("pending_action", "awaiting_location", tool="weather")
            if isinstance(intent_state, dict):
                _set_conversation_state(intent_state)
                _sync_pending_conversation_tracking()
            _trace(
                "supervisor_intent",
                "handled",
                str(intent_rule.get("intent") or "intent"),
                rule=str(intent_rule.get("rule_name") or ""),
            )
            print(f"Nova: {final}\n", flush=True)
            session_turns.append(("assistant", final))
            speak_chunked(tts, final)
            continue
        warn_supervisor_bypass = not _supervisor_result_has_route(intent_rule) and _should_warn_supervisor_bypass(routed_user_text)

        try:
            identity_learned, identity_msg = _learn_self_identity_binding(user_text)
            if identity_learned:
                _trace("identity_binding", "stored", "bound simple self-identification to known developer")
                final = _ensure_reply(identity_msg)
                print(f"Nova: {final}\n", flush=True)
                session_turns.append(("assistant", final))
                speak_chunked(tts, final)
                continue
        except Exception:
            pass

        # Capture explicit/long name-origin teaching content deterministically.
        try:
            teach_text = extract_name_origin_teach_text(user_text)
            if teach_text:
                _trace("name_origin", "stored", "captured deterministic name-origin teaching content")
                msg = remember_name_origin(teach_text)
                final = _ensure_reply(msg)
                print(f"Nova: {final}\n", flush=True)
                session_turns.append(("assistant", final))
                speak_chunked(tts, final)
                continue
        except Exception:
            pass

        try:
            learned_profile, learned_profile_msg = _learn_contextual_developer_facts(session_turns, user_text, input_source=input_source)
            if learned_profile:
                _trace("developer_profile", "stored", "captured contextual developer facts")
                _set_conversation_state(
                    _infer_profile_conversation_state(user_text)
                    or _make_conversation_state("identity_profile", subject="developer")
                )
                _sync_pending_conversation_tracking()
                final = _ensure_reply(learned_profile_msg)
                print(f"Nova: {final}\n", flush=True)
                session_turns.append(("assistant", final))
                speak_chunked(tts, final)
                continue
        except Exception:
            pass

        try:
            learned_self, learned_self_msg = _learn_contextual_self_facts(user_text, input_source=input_source)
            if learned_self:
                _trace("self_profile", "stored", "captured contextual self facts for bound identity")
                final = _ensure_reply(learned_self_msg)
                print(f"Nova: {final}\n", flush=True)
                session_turns.append(("assistant", final))
                speak_chunked(tts, final)
                continue
        except Exception:
            pass

        general_rule = TURN_SUPERVISOR.evaluate_rules(
            user_text,
            manager=session_state,
            turns=session_turns,
            phase="handle",
            entry_point="cli",
        )
        # DO NOT add new deterministic branching in this loop.
        # New turn ownership must start in supervisor and flow through shared action execution.
        # See docs/SUPERVISOR_CONTRACT.md.
        handled_rule, rule_msg, rule_state = _execute_registered_supervisor_rule(
            general_rule,
            user_text,
            conversation_state,
            turns=session_turns,
            input_source=input_source,
            allowed_actions={"name_origin_store", "self_location", "location_recall", "location_name", "weather_current_location", "apply_correction", "retrieval_followup", "identity_history_family", "open_probe_family", "session_fact_recall", "last_question_recall", "rules_list", "developer_identity_followup", "identity_profile_followup", "developer_location"},
        )
        if pending_action_ledger is not None:
            pending_action_ledger["routing_decision"] = _build_routing_decision(
                routed_user_text,
                entry_point="cli",
                intent_result=intent_rule,
                handle_result=general_rule,
                reply_contract=str(general_rule.get("reply_contract") or "") if isinstance(general_rule, dict) else "",
                reply_outcome=dict(general_rule.get("reply_outcome") or {}) if isinstance(general_rule, dict) and isinstance(general_rule.get("reply_outcome"), dict) else {},
                turn_acts=turn_acts,
            )
        if handled_rule:
            try:
                final = _apply_reply_overrides(rule_msg)
            except Exception:
                final = rule_msg
            final = _ensure_reply(final)
            if pending_action_ledger is not None:
                pending_action_ledger["reply_contract"] = str(general_rule.get("reply_contract") or "")
                pending_action_ledger["reply_outcome"] = dict(general_rule.get("reply_outcome") or {}) if isinstance(general_rule.get("reply_outcome"), dict) else {}
            _set_conversation_state(rule_state)
            if bool(general_rule.get("continuation")):
                session_state.mark_continuation_used()
                if pending_action_ledger is not None:
                    pending_action_ledger["continuation_used"] = True
            _trace(
                str(general_rule.get("ledger_stage") or "registered_rule"),
                "matched",
                str(general_rule.get("rule_name") or "registered_rule"),
                rule=str(general_rule.get("rule_name") or ""),
            )
            SUBCONSCIOUS_SERVICE.update_state(
                session_state,
                _probe_turn_routes(
                    routed_user_text,
                    session_state,
                    session_turns,
                    pending_action=pending_action,
                ),
                chosen_route="supervisor_owned",
            )
            _sync_pending_conversation_tracking()
            print(f"Nova: {final}\n", flush=True)
            session_turns.append(("assistant", final))
            speak_chunked(tts, final)
            continue

        fulfillment_result = _fulfillment_flow_service().maybe_run_fulfillment_flow(
            routed_user_text,
            session_state,
            session_turns,
            pending_action=pending_action,
        )
        if isinstance(fulfillment_result, dict):
            final = _ensure_reply(str(fulfillment_result.get("reply") or ""))
            if final:
                if pending_action_ledger is not None:
                    pending_action_ledger["planner_decision"] = str(fulfillment_result.get("planner_decision") or "fulfillment")
                    pending_action_ledger["grounded"] = bool(fulfillment_result.get("grounded", True))
                _trace(
                    "fulfillment_flow",
                    "handled",
                    str(fulfillment_result.get("planner_decision") or "fulfillment"),
                )
                print(f"Nova: {final}\n", flush=True)
                session_turns.append(("assistant", final))
                speak_chunked(tts, final)
                continue

        try:
            handled_followup, followup_msg, next_state = _consume_conversation_followup(
                conversation_state,
                routed_user_text,
                input_source=input_source,
                turns=session_turns,
            )
            if handled_followup:
                _trace("conversation_followup", "used", active_subject=_conversation_active_subject(conversation_state))
                _set_conversation_state(next_state)
                session_state.mark_continuation_used()
                if pending_action_ledger is not None:
                    pending_action_ledger["planner_decision"] = "conversation_followup"
                    pending_action_ledger["grounded"] = True
                    pending_action_ledger["continuation_used"] = True
                _sync_pending_conversation_tracking()
                final = _ensure_reply(followup_msg)
                if isinstance(final, str) and final.strip() and isinstance(conversation_state, dict) and str(conversation_state.get("kind") or "") == "retrieval":
                    recent_tool_context = final.strip()[:2500]
                    recent_web_urls = _extract_urls(final)
                print(f"Nova: {final}\n", flush=True)
                session_turns.append(("assistant", final))
                speak_chunked(tts, final)
                continue
            _set_conversation_state(next_state)
            _sync_pending_conversation_tracking()
        except Exception:
            pass

        # Quick greeting fast-path (avoid LLM for simple salutations)
        try:
            msg = _quick_smalltalk_reply(routed_user_text, active_user=get_active_user() or "")
            if msg:
                _trace("fast_smalltalk", "matched")
                if pending_action_ledger is not None:
                    pending_action_ledger["planner_decision"] = "deterministic"
                    pending_action_ledger["grounded"] = False

                # Apply any stored reply overrides before sending
                try:
                    final = _apply_reply_overrides(msg)
                except Exception:
                    final = msg
                final = _ensure_reply(final)
                print(f"Nova: {final}\n", flush=True)
                session_turns.append(("assistant", final))
                speak_chunked(tts, final)
                continue
        except Exception:
            pass

        # Memory summary / operator query: handle without sending to LLM
        try:
            low_q = (routed_user_text or "").strip().lower()
            if low_q.startswith("what else do you remember") or low_q.startswith("what do you remember") or "what else do you remember" in low_q:
                stats = mem_stats()
                brief = "I remember a few things about our conversations and some saved facts."
                # include a short stats line if available
                if stats and "No memory" not in stats:
                    brief += " " + (stats.splitlines()[0] if stats else "")
                brief += " You can ask me to audit specific items, e.g. 'mem audit location'."
                final = _ensure_reply(brief)
                session_turns.append(("assistant", final))
                print(f"Nova: {final}\n", flush=True)
                speak_chunked(tts, final)
                continue
        except Exception:
            pass

        # Small status fragments should ask for a concrete target, not improvise memory retrieval.
        try:
            status_msg = _retrieval_status_reply(routed_user_text)
            if status_msg:
                _set_conversation_state(_make_conversation_state("awaiting_retrieval_target"))
                _sync_pending_conversation_tracking()
                final = _ensure_reply(status_msg)
                session_turns.append(("assistant", final))
                print(f"Nova: {final}\n", flush=True)
                speak_chunked(tts, final)
                continue
        except Exception:
            pass

        # Natural 'remember X' intent: ask a friendly follow-up
        try:
            m = re.match(r"^remember\s+(.+)$", (routed_user_text or "").strip(), flags=re.I)
            if m:
                subj = m.group(1).strip().strip('.!?,')
                if subj:
                    q = f"What would you like me to remember about {subj}?"
                    final = _ensure_reply(q)
                    session_turns.append(("assistant", final))
                    print(f"Nova: {final}\n", flush=True)
                    speak_chunked(tts, final)
                    continue
        except Exception:
            pass

        # Auto-capture simple identity phrases and store to memory so Nova can tie
        # future conversation to the correct user. Matches: "my name is X", "i am X", "i'm X", "this is X".
        try:
            # Only capture explicit identity phrases to avoid false positives.
            id_m = None
            if id_m:
                name = id_m.group(1).strip().strip(".!,")
                if name:
                    mem_add("profile", input_source, f"name: {name}")
                    set_active_user(name)
                    ack = f"Nice to meet you, {name}. I'll remember that and use that identity for this session."
                    print(f"Nova: {ack}\n", flush=True)
                    session_turns.append(("assistant", ack))
                    speak_chunked(tts, ack)
                    continue
        except Exception:
            pass

        # Quick replies for explicit location queries using stored memory
        try:
            low_q = (routed_user_text or "").strip().lower()

            handled_location, msg, next_location_state, _location_intent = _handle_location_conversation_turn(
                conversation_state,
                routed_user_text,
                turns=session_turns,
            )
            if handled_location:
                try:
                    final = _apply_reply_overrides(msg)
                except Exception:
                    final = msg
                final = _ensure_reply(final)
                if isinstance(next_location_state, dict):
                    _set_conversation_state(next_location_state)
                    _sync_pending_conversation_tracking()
                print(f"Nova: {final}\n", flush=True)
                session_turns.append(("assistant", final))
                speak_chunked(tts, final)
                continue

            # Follow-up/expansion triggers (ask for more info about location)
            expand_triggers = ["what else", "other information", "anything else", "more about", "what other", "anything more"]
            if "location" in low_q and any(t in low_q for t in expand_triggers):
                try:
                    audit_out = mem_audit("location")
                    j = json.loads(audit_out) if audit_out else {}
                    results = j.get("results") if isinstance(j, dict) else []
                    previews = []
                    seen = set()
                    for r in results:
                        p = (r.get("preview") or "").strip()
                        n = re.sub(r"\W+", " ", p.lower()).strip()
                        if not p or n in seen:
                            continue
                        seen.add(n)
                        previews.append(p)

                    if not previews:
                        msg = "I don't have a stored location yet. You can tell me: 'My location is ...'"
                    elif len(previews) == 1:
                        msg = f"I only have one stored location fact right now: {_normalize_location_preview(previews[0])}"
                    else:
                        # summarize up to 3 entries
                        summary = "; ".join(_normalize_location_preview(p) for p in previews[:3])
                        msg = f"I have multiple stored location facts: {summary}"
                except Exception:
                    msg = "I don't have a stored location yet. You can tell me: 'My location is ...'"

                try:
                    final = _apply_reply_overrides(msg)
                except Exception:
                    final = msg
                final = _ensure_reply(final)
                _set_conversation_state(_make_conversation_state("location_recall"))
                _sync_pending_conversation_tracking()
                print(f"Nova: {final}\n", flush=True)
                session_turns.append(("assistant", final))
                speak_chunked(tts, final)
                continue

            # Primary direct-location triggers: only match if input starts with a direct phrasing
            loc_triggers = [
                "what is your location",
                "where are you located",
                "where are you",
                "what is your location nova",
            ]
            if any(low_q.startswith(t) for t in loc_triggers):
                try:
                    preview = get_saved_location_text()
                    if preview:
                        msg = f"My location is {preview}."
                    else:
                        msg = "I don't have a stored location yet. You can tell me: 'My location is ...'"
                except Exception:
                    msg = "I don't have a stored location yet. You can tell me: 'My location is ...'"

                try:
                    final = _apply_reply_overrides(msg)
                except Exception:
                    final = msg
                final = _ensure_reply(final)
                print(f"Nova: {final}\n", flush=True)
                session_turns.append(("assistant", final))
                speak_chunked(tts, final)
                continue
        except Exception:
            pass

        try:
            developer_guess, next_state = _developer_work_guess_turn(routed_user_text)
            if developer_guess:
                final = _ensure_reply(developer_guess)
                _set_conversation_state(next_state)
                _sync_pending_conversation_tracking()
                print(f"Nova: {final}\n", flush=True)
                session_turns.append(("assistant", final))
                speak_chunked(tts, final)
                continue
        except Exception:
            pass

        try:
            location_ack = _store_location_fact_reply(
                user_text,
                input_source=input_source,
                pending_action=pending_action,
            )
            if location_ack:
                _set_conversation_state(_make_conversation_state("location_recall"))
                _sync_pending_conversation_tracking()
                final = _ensure_reply(location_ack)
                print(f"Nova: {final}\n", flush=True)
                session_turns.append(("assistant", final))
                speak_chunked(tts, final)
                continue
        except Exception:
            pass

        try:
            if (
                isinstance(conversation_state, dict)
                and str(conversation_state.get("kind") or "") == "location_recall"
                and _is_saved_location_weather_query(routed_user_text)
            ):
                weather_reply = _weather_for_saved_location()
                if weather_reply:
                    _set_conversation_state(_make_conversation_state("location_recall"))
                    _sync_pending_conversation_tracking()
                    final = _ensure_reply(weather_reply)
                    print(f"Nova: {final}\n", flush=True)
                    session_turns.append(("assistant", final))
                    speak_chunked(tts, final)
                    continue
        except Exception:
            pass

        # Treat declarative info (not requests) as facts to store and acknowledge.
        try:
            declarative_outcome = _store_declarative_fact_outcome(user_text, input_source=input_source)
            if isinstance(declarative_outcome, dict):
                ack = render_reply(declarative_outcome)
                if pending_action_ledger is not None:
                    pending_action_ledger["reply_contract"] = str(declarative_outcome.get("reply_contract") or "")
                    pending_action_ledger["reply_outcome"] = dict(declarative_outcome)
                print(f"Nova: {ack}\n", flush=True)
                session_turns.append(("assistant", ack))
                speak_chunked(tts, ack)
                continue
        except Exception:
            pass

        # Reason-first action selection: let the planner choose clarify vs tool
        # before legacy command/keyword handlers execute side effects.
        if warn_supervisor_bypass:
            safe_reply, safe_kind = _open_probe_reply(routed_user_text, turns=session_turns)
            safe_outcome = {
                "intent": "open_probe_family",
                "kind": safe_kind,
                "reply_contract": f"open_probe.{safe_kind}",
                "reply_text": safe_reply,
                "state_delta": {},
            }
            if pending_action_ledger is not None:
                pending_action_ledger["planner_decision"] = "deterministic"
                pending_action_ledger["grounded"] = False
                pending_action_ledger["reply_contract"] = str(safe_outcome.get("reply_contract") or "")
                pending_action_ledger["reply_outcome"] = dict(safe_outcome)
                routing_decision = pending_action_ledger.get("routing_decision")
                if isinstance(routing_decision, dict):
                    routing_decision["final_owner"] = "supervisor_handle"
            _trace("open_probe", "matched", safe_kind)
            final = _ensure_reply(safe_reply)
            print(f"Nova: {final}\n", flush=True)
            session_turns.append(("assistant", final))
            speak_chunked(tts, final)
            continue
        try:
            actions = [] if turn_direction.get("bypass_pattern_routes") else decide_actions(
                routed_user_text,
                config={
                    "session_turns": session_turns,
                    "pending_action": pending_action,
                    "prefer_web_for_data_queries": prefer_web_for_data_queries,
                },
            )
        except Exception:
            actions = []

        if actions:
            act = actions[0]
            atype = act.get("type")
            if atype == "ask_clarify":
                if pending_action_ledger is not None:
                    pending_action_ledger["planner_decision"] = "ask_clarify"
                _trace("action_planner", "ask_clarify")
                q = act.get("question") or act.get("note") or "Can you clarify?"
                if "weather lookup" in (q or "").lower():
                    _set_pending_action(make_pending_weather_action())
                    _trace("pending_action", "awaiting_location", tool="weather")
                try:
                    final = _apply_reply_overrides(q)
                except Exception:
                    final = q
                print(f"Nova: {final}\n", flush=True)
                session_turns.append(("assistant", final))
                speak_chunked(tts, final)
                continue

            if atype == "respond":
                if pending_action_ledger is not None:
                    pending_action_ledger["planner_decision"] = "respond"
                    pending_action_ledger["grounded"] = False
                _trace("action_planner", "respond")
                msg = act.get("note") or act.get("message") or "Tell me a bit more about what you want me to inspect."
                try:
                    final = _apply_reply_overrides(msg)
                except Exception:
                    final = msg
                print(f"Nova: {final}\n", flush=True)
                session_turns.append(("assistant", final))
                speak_chunked(tts, final)
                continue

            if atype == "route_command":
                _trace("action_planner", "route_command")
                cmd_out = handle_commands(routed_user_text, session_turns=session_turns, session=session_state)
                if cmd_out:
                    _trace("command", "matched", tool="weather" if "api.weather.gov" in str(cmd_out).lower() else "")
                    if pending_action_ledger is not None:
                        pending_action_ledger["planner_decision"] = "command"
                        pending_action_ledger["tool_result"] = ""
                        low_cmd = str(cmd_out).lower()
                        if "api.weather.gov" in low_cmd:
                            pending_action_ledger["tool"] = "weather"
                            pending_action_ledger["tool_args"] = {"raw": user_text}
                            pending_action_ledger["tool_result"] = str(cmd_out)
                            pending_action_ledger["grounded"] = True
                    print(f"Nova: {cmd_out}\n", flush=True)
                    session_turns.append(("assistant", cmd_out))
                    speak_chunked(tts, cmd_out)
                    continue
                _trace("command", "not_matched")

            if atype == "route_keyword":
                _trace("action_planner", "route_keyword")
                routed = handle_keywords(routed_user_text)
                if routed:
                    behavior_record_event("tool_route")
                    _, routed_tool, out = routed
                    _trace("keyword_tool", "matched", tool=str(routed_tool or ""), grounded=bool(str(out or "").strip()))
                    if pending_action_ledger is not None:
                        pending_action_ledger["planner_decision"] = "run_tool"
                        pending_action_ledger["tool"] = str(routed_tool or "")
                        pending_action_ledger["tool_args"] = {"raw": user_text}
                        pending_action_ledger["tool_result"] = str(out or "")
                        pending_action_ledger["grounded"] = bool(str(out or "").strip())
                    print(f"Nova (tool output):\n{out}\n", flush=True)
                    if isinstance(out, str) and out.strip():
                        recent_tool_context = out.strip()[:2500]
                        recent_web_urls = _extract_urls(out)
                        next_tool_state = _make_tool_conversation_state(str(routed_tool or ""), _retrieval_query_from_text(str(routed_tool or ""), routed_user_text), out)
                        if next_tool_state is not None:
                            if str(next_tool_state.get("kind") or "") == "retrieval":
                                session_state.set_retrieval_state(next_tool_state)
                            else:
                                _set_conversation_state(next_tool_state)
                            conversation_state = session_state.conversation_state
                            _sync_pending_conversation_tracking()
                        session_turns.append(("assistant", out.strip()[:350]))
                    tts.say("Done.")
                    continue
                _trace("keyword_tool", "not_matched")

            if atype == "run_tool":
                behavior_record_event("tool_route")
                tool = act.get("tool")
                args = act.get("args") or []
                _trace("action_planner", "run_tool", tool=str(tool or ""))
                if pending_action_ledger is not None:
                    pending_action_ledger["planner_decision"] = "run_tool"
                    pending_action_ledger["tool"] = str(tool or "")
                    pending_action_ledger["tool_args"] = {"args": list(args) if isinstance(args, (list, tuple)) else args}

                out = execute_planned_action(str(tool or ""), args)
                if str(tool or "") in {"weather_current_location", "weather_location"}:
                    _set_pending_action(None)

                if out is None or (isinstance(out, str) and not out.strip()):
                    _trace("tool_execution", "empty_result", tool=str(tool or ""))
                    if pending_action_ledger is not None:
                        pending_action_ledger["tool_result"] = ""
                        pending_action_ledger["grounded"] = False
                    final_msg = _web_allowlist_message("requested resource") if str(tool or "").startswith("web") else f"The {tool} tool did not return a result. No data was available."
                    try:
                        final_msg = _apply_reply_overrides(final_msg)
                    except Exception:
                        pass
                    print(f"Nova: {final_msg}\n", flush=True)
                    session_turns.append(("assistant", final_msg))
                    speak_chunked(tts, final_msg)
                    continue

                if isinstance(out, dict) and not out.get("ok", True):
                    _trace("tool_execution", "error", tool=str(tool or ""), error=str(out.get("error") or "unknown error"))
                    if pending_action_ledger is not None:
                        pending_action_ledger["tool_result"] = json.dumps(out, ensure_ascii=True)
                        pending_action_ledger["grounded"] = False
                    err = out.get("error", "unknown error")
                    if isinstance(err, str) and ("not allowed" in err.lower() or "domain not allowed" in err.lower()):
                        final_msg = _web_allowlist_message(args[0] if args else "")
                    else:
                        final_msg = f"Tool {tool} failed: {err}"
                    try:
                        final_msg = _apply_reply_overrides(final_msg)
                    except Exception:
                        pass
                    print(f"Nova: {final_msg}\n", flush=True)
                    session_turns.append(("assistant", final_msg))
                    speak_chunked(tts, final_msg)
                    continue

                citation = format_tool_citation(str(tool or ""), out)
                _trace("tool_execution", "ok", tool=str(tool or ""), grounded=bool(str(out or "").strip()))
                if pending_action_ledger is not None:
                    pending_action_ledger["tool_result"] = str(out or "")
                    pending_action_ledger["grounded"] = bool(str(out or "").strip())
                if citation:
                    print(f"Nova (tool output):\n{citation}{out}\n", flush=True)
                else:
                    print(f"Nova (tool output):\n{out}\n", flush=True)

                if isinstance(out, str) and out.strip():
                    recent_tool_context = out.strip()[:2500]
                    recent_web_urls = _extract_urls(out)
                    query_text = args[0] if isinstance(args, (list, tuple)) and args else user_text
                    next_tool_state = _make_tool_conversation_state(str(tool or ""), str(query_text or ""), out)
                    if next_tool_state is not None:
                        if str(next_tool_state.get("kind") or "") == "retrieval":
                            session_state.set_retrieval_state(next_tool_state)
                        else:
                            _set_conversation_state(next_tool_state)
                        conversation_state = session_state.conversation_state
                        _sync_pending_conversation_tracking()
                    session_turns.append(("assistant", out.strip()[:350]))

                tts.say("Done.")
                continue

        handled_truth, truth_reply, truth_source, truth_grounded = truth_hierarchy_answer(routed_user_text)
        if handled_truth:
            behavior_record_event("deterministic_hit")
            _trace("truth_hierarchy", "matched", tool=str(truth_source or ""), grounded=bool(truth_grounded))
            if pending_action_ledger is not None:
                pending_action_ledger["planner_decision"] = "truth_hierarchy"
                pending_action_ledger["tool"] = str(truth_source or "")
                pending_action_ledger["tool_args"] = {"query": user_text}
                pending_action_ledger["tool_result"] = str(truth_reply or "")
                pending_action_ledger["grounded"] = bool(truth_grounded)
            final = _ensure_reply(truth_reply)
            next_profile_state = _infer_profile_conversation_state(routed_user_text)
            if next_profile_state is not None:
                _set_conversation_state(next_profile_state)
                _sync_pending_conversation_tracking()
            print(f"Nova: {final}\n", flush=True)
            session_turns.append(("assistant", final))
            speak_chunked(tts, final)
            continue
        _trace("truth_hierarchy", "not_matched")

        ha = hard_answer(routed_user_text)
        if ha:
            if detect_identity_conflict():
                behavior_record_event("conflict_detected")
                _trace("identity_conflict", "detected")
            behavior_record_event("deterministic_hit")
            _trace("hard_answer", "matched", grounded=True)
            if pending_action_ledger is not None:
                pending_action_ledger["planner_decision"] = "deterministic"
                pending_action_ledger["grounded"] = True
            if _is_identity_stable_reply(ha):
                final = ha
            else:
                try:
                    final = _apply_reply_overrides(ha)
                except Exception:
                    final = ha
            next_profile_state = _infer_profile_conversation_state(routed_user_text)
            if next_profile_state is not None:
                _set_conversation_state(next_profile_state)
                _sync_pending_conversation_tracking()
            print(f"Nova: {final}\n", flush=True)
            session_turns.append(("assistant", final))
            speak_chunked(tts, final)
            continue
        _trace("hard_answer", "not_matched")

        if _is_local_knowledge_topic_query(routed_user_text):
            local_topic = _build_local_topic_digest_answer(routed_user_text)
            if local_topic:
                behavior_record_event("deterministic_hit")
                _trace("grounded_lookup", "matched", tool="local_knowledge")
                if pending_action_ledger is not None:
                    pending_action_ledger["planner_decision"] = "grounded_lookup"
                    pending_action_ledger["tool"] = "local_knowledge"
                    pending_action_ledger["tool_args"] = {"query": user_text}
                    pending_action_ledger["tool_result"] = local_topic
                    pending_action_ledger["grounded"] = True
                print(f"Nova: {local_topic}\n", flush=True)
                session_turns.append(("assistant", local_topic))
                speak_chunked(tts, local_topic)
                continue
            _trace("grounded_lookup", "missed", tool="local_knowledge")

        if _is_color_lookup_request(routed_user_text):
            prefs = _extract_color_preferences(session_turns)
            if not prefs:
                prefs = _extract_color_preferences_from_memory()
            if prefs:
                if len(prefs) == 1:
                    msg = f"You told me you like the color {prefs[0]}."
                else:
                    msg = "You told me you like these colors: " + ", ".join(prefs[:-1]) + f", and {prefs[-1]}."
            else:
                msg = "You haven't told me a color preference in this current chat yet."
            try:
                final = _apply_reply_overrides(msg)
            except Exception:
                final = msg
            _set_conversation_state(_infer_profile_conversation_state(routed_user_text) or _make_conversation_state("identity_profile", subject="self"))
            _sync_pending_conversation_tracking()
            print(f"Nova: {final}\n", flush=True)
            session_turns.append(("assistant", final))
            speak_chunked(tts, final)
            continue

        if _is_developer_color_lookup_request(routed_user_text):
            prefs = _extract_developer_color_preferences(session_turns)
            if not prefs:
                prefs = _extract_developer_color_preferences_from_memory()
            if prefs:
                if len(prefs) == 1:
                    msg = f"From what you've told me, Gus likes {prefs[0]}."
                else:
                    msg = "From what you've told me, Gus likes these colors: " + ", ".join(prefs[:-1]) + f", and {prefs[-1]}."
            else:
                msg = "I don't have Gus's color preferences yet."
            try:
                final = _apply_reply_overrides(msg)
            except Exception:
                final = msg
            _set_conversation_state(_infer_profile_conversation_state(routed_user_text) or _make_conversation_state("identity_profile", subject="developer"))
            _sync_pending_conversation_tracking()
            print(f"Nova: {final}\n", flush=True)
            session_turns.append(("assistant", final))
            speak_chunked(tts, final)
            continue

        if _is_developer_bilingual_request(routed_user_text):
            known = _developer_is_bilingual(session_turns)
            if known is None:
                known = _developer_is_bilingual_from_memory()
            if known is True:
                msg = "Yes. From what you've told me, Gus is bilingual in English and Spanish."
            elif known is False:
                msg = "From what I have, Gus is not bilingual."
            else:
                msg = "I don't have confirmed language details for Gus yet."
            try:
                final = _apply_reply_overrides(msg)
            except Exception:
                final = msg
            _set_conversation_state(_infer_profile_conversation_state(routed_user_text) or _make_conversation_state("identity_profile", subject="developer"))
            _sync_pending_conversation_tracking()
            print(f"Nova: {final}\n", flush=True)
            session_turns.append(("assistant", final))
            speak_chunked(tts, final)
            continue

        if _is_developer_profile_request(routed_user_text):
            msg = _developer_profile_reply(session_turns, routed_user_text)
            try:
                final = _apply_reply_overrides(msg)
            except Exception:
                final = msg
            _set_conversation_state(_infer_profile_conversation_state(routed_user_text) or _make_conversation_state("identity_profile", subject="developer"))
            _sync_pending_conversation_tracking()
            print(f"Nova: {final}\n", flush=True)
            session_turns.append(("assistant", final))
            speak_chunked(tts, final)
            continue

        msg, next_state = _developer_location_turn(
            routed_user_text,
            state=conversation_state,
            turns=session_turns,
        )
        if msg:
            try:
                final = _apply_reply_overrides(msg)
            except Exception:
                final = msg
            _set_conversation_state(next_state)
            _sync_pending_conversation_tracking()
            print(f"Nova: {final}\n", flush=True)
            session_turns.append(("assistant", final))
            speak_chunked(tts, final)
            continue

        low_user = (routed_user_text or "").lower()
        if "what animals do i like" in low_user or "which animals do i like" in low_user:
            animals = _extract_animal_preferences(session_turns)
            if not animals:
                animals = _extract_animal_preferences_from_memory()
            if animals:
                if len(animals) == 1:
                    msg = f"You told me you like {animals[0]}."
                else:
                    msg = "You told me you like: " + ", ".join(animals[:-1]) + f", and {animals[-1]}."
            else:
                msg = "You haven't told me animal preferences yet in this chat, and I can't find them in saved memory."
            try:
                final = _apply_reply_overrides(msg)
            except Exception:
                final = msg
            _set_conversation_state(_infer_profile_conversation_state(routed_user_text) or _make_conversation_state("identity_profile", subject="self"))
            _sync_pending_conversation_tracking()
            print(f"Nova: {final}\n", flush=True)
            session_turns.append(("assistant", final))
            speak_chunked(tts, final)
            continue

        if _is_color_animal_match_question(routed_user_text):
            colors = _extract_color_preferences(session_turns)
            if not colors:
                colors = _extract_color_preferences_from_memory()
            animals = _extract_animal_preferences(session_turns)
            if not animals:
                animals = _extract_animal_preferences_from_memory()

            if not colors:
                msg = "I can't pick a best color yet because I don't have your color preferences."
            elif not animals:
                msg = "I can't pick a best color for animals yet because I don't have your animal preferences."
            else:
                best = _pick_color_for_animals(colors, animals)
                msg = f"Direct answer: {best} matches best with the animals you like ({', '.join(animals)})."
                if len(colors) > 1:
                    msg += f" I considered your options: {', '.join(colors)}."

            print(f"Nova: {msg}\n", flush=True)
            session_turns.append(("assistant", msg))
            speak_chunked(tts, msg)
            continue

        last_assistant_text = _last_assistant_turn_text(session_turns[:-1])
        pending_weather_followup = (
            isinstance(pending_action, dict)
            and str(pending_action.get("kind") or "") == "weather_lookup"
            and str(pending_action.get("status") or "") == "awaiting_location"
            and bool(pending_action.get("saved_location_available"))
        )
        pending_weather_cli_fallback = pending_weather_followup and (
            _looks_like_affirmative_followup(routed_user_text)
            or _looks_like_shared_location_reference(routed_user_text)
        )
        if pending_weather_cli_fallback or (
            _looks_like_affirmative_followup((routed_user_text or "").lower())
            and _assistant_offered_weather_lookup(last_assistant_text)
        ):
            if pending_action_ledger is not None:
                pending_action_ledger["planner_decision"] = "llm_fallback"
                pending_action_ledger["grounded"] = False
            if pending_weather_followup:
                _set_pending_action(None)
                _sync_pending_conversation_tracking()
            msg = "I can try to check the weather for you, but I need a specific weather source or tool available here first."
            final = _ensure_reply(msg)
            print(f"Nova: {final}\n", flush=True)
            session_turns.append(("assistant", final))
            speak_chunked(tts, final)
            continue

        task = analyze_request(
            routed_user_text,
            config={"prefer_web_for_data_queries": prefer_web_for_data_queries},
        )
        if not getattr(task, "allow_llm", False):
            _trace("policy_gate", "blocked", detail=str(getattr(task, "message", "") or "")[:160])
            if pending_action_ledger is not None:
                pending_action_ledger["planner_decision"] = "policy_block"
                pending_action_ledger["grounded"] = True
            msg = getattr(task, "message", "")
            try:
                final = _apply_reply_overrides(msg)
            except Exception:
                final = msg
            print(f"Nova: {final}\n", flush=True)
            session_turns.append(("assistant", final))
            speak_chunked(tts, final)
            continue
        _trace("policy_gate", "allowed")

        fallback_context = build_fallback_context_details(routed_user_text, session_turns)
        retrieved_context = str(fallback_context.get("context") or "")
        _trace(
            "memory_context",
            "used" if str(fallback_context.get("learning_context") or "") else "empty",
            memory_used=bool(fallback_context.get("memory_used")),
            knowledge_used=bool(fallback_context.get("knowledge_used")),
            memory_chars=int(fallback_context.get("memory_chars") or 0),
            knowledge_chars=int(fallback_context.get("knowledge_chars") or 0),
        )
        chat_ctx = str(fallback_context.get("chat_context") or "")
        if chat_ctx:
            _trace("chat_context", "used", chars=len(chat_ctx))
        session_fact_sheet = str(fallback_context.get("session_fact_sheet") or "")
        if session_fact_sheet:
            _trace("session_fact_sheet", "used", chars=len(session_fact_sheet))
        if recent_tool_context and _uses_prior_reference(routed_user_text):
            retrieved_context = (retrieved_context + "\n\nRECENT TOOL OUTPUT:\n" + recent_tool_context).strip()[:6000]
            _trace("recent_tool_context", "used", chars=len(recent_tool_context))

        if should_block_low_confidence(routed_user_text, retrieved_context=retrieved_context, tool_context=recent_tool_context):
            behavior_record_event("low_confidence_block")
            _trace("low_confidence_gate", "blocked")
            truthful_outcome = _truthful_limit_outcome(routed_user_text)
            if pending_action_ledger is not None:
                pending_action_ledger["planner_decision"] = "blocked_low_confidence"
                pending_action_ledger["grounded"] = False
                pending_action_ledger["reply_contract"] = str(truthful_outcome.get("reply_contract") or "")
                pending_action_ledger["reply_outcome"] = dict(truthful_outcome)
            msg = str(truthful_outcome.get("reply_text") or _truthful_limit_reply(routed_user_text))
            final = _ensure_reply(msg)
            print(f"Nova: {final}\n", flush=True)
            session_turns.append(("assistant", final))
            speak_chunked(tts, final)
            continue

        behavior_record_event("llm_fallback")
        _trace("llm_fallback", "invoked", retrieved_chars=len(retrieved_context))
        if pending_action_ledger is not None:
            pending_action_ledger["planner_decision"] = "llm_fallback"
        reply = ollama_chat(
            routed_user_text,
            retrieved_context=retrieved_context,
            language_mix_spanish_pct=language_mix_spanish_pct,
        )
        reply = sanitize_llm_reply(reply, tool_context=recent_tool_context)

        if mem_enabled():
            if mem_should_store(user_text):
                mem_add("chat_user", input_source, user_text)
            # Do not automatically store assistant replies to avoid clutter and duplicates.

        # remove any raw memory dumps leaking into the assistant reply before showing
        clean_reply = _strip_mem_leak(reply, retrieved_context)
        corrected_reply, was_corrected, correction_reason = _self_correct_reply(routed_user_text, clean_reply)
        if was_corrected:
            behavior_record_event("correction_applied")
            behavior_record_event("self_correction_applied")
            _trace("llm_postprocess", "self_corrected", detail=str(correction_reason or "")[:120])
            try:
                # Persist a compact teach pair so similar drift gets corrected faster next time.
                _teach_store_example(clean_reply, corrected_reply, user=get_active_user() or None)
            except Exception:
                pass
            if pending_action_ledger is not None:
                pending_action_ledger["planner_decision"] = "llm_self_corrected"
                pending_action_ledger["grounded"] = True
            clean_reply = corrected_reply
        claim_gated_reply, claim_gate_changed, claim_gate_reason = _apply_claim_gate(
            clean_reply,
            evidence_text=retrieved_context,
            tool_context=recent_tool_context,
        )
        if claim_gate_changed:
            _trace("claim_gate", "adjusted", claim_gate_reason)
            clean_reply = claim_gated_reply
            if claim_gate_reason == "unsupported_claim_blocked" and pending_action_ledger is not None:
                truthful_outcome = _truthful_limit_outcome(routed_user_text)
                pending_action_ledger["grounded"] = False
                pending_action_ledger["reply_contract"] = str(truthful_outcome.get("reply_contract") or "")
                pending_action_ledger["reply_outcome"] = dict(truthful_outcome)
        reply_contract = str(pending_action_ledger.get("reply_contract") or "").strip() if isinstance(pending_action_ledger, dict) else ""
        # Shorten replies for ordinary conversation: if the user did not explicitly request an action,
        # prefer a concise reply (first 1-2 sentences). Keep full replies for explicit requests.
        try:
            if not _is_explicit_request(routed_user_text):
                # take up to first 2 sentences
                sents = re.split(r'(?<=[.!?])\s+', (clean_reply or "").strip())
                short = " ".join([s for s in sents if s])[:600]
                if short:
                    # prefer the short form unless it's obviously truncating a tool citation
                    clean_reply = short
        except Exception:
            pass
        try:
            final = _apply_reply_overrides(clean_reply)
        except Exception:
            final = clean_reply
        final = _ensure_reply(final)
        print(f"Nova: {final}\n", flush=True)
        session_turns.append(("assistant", final))
        speak_chunked(tts, final)

    _flush_pending_action_ledger()

# =========================
# Entrypoint
# =========================
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", nargs="?", default="run", choices=["run"])
    ap.add_argument("--heartbeat", default=str(DEFAULT_HEARTBEAT))
    ap.add_argument("--statefile", default=str(DEFAULT_STATEFILE))
    args = ap.parse_args()

    hb = Path(args.heartbeat)
    st = Path(args.statefile)

    write_core_identity(st)
    hb_stop = start_heartbeat(hb, interval_sec=1.0)

    tts = SubprocessTTS(PYTHON, BASE_DIR / "tts_piper.py", timeout_sec=25.0)
    tts.start()
    tts.say("Nova online.")

    ensure_ollama_boot()

    try:
        run_loop(tts)
    finally:
        hb_stop.set()
        tts.stop()


if __name__ == "__main__":
    main()
