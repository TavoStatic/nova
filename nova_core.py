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
from services.nova_memory_learning import mem_get_recent_learned as service_mem_get_recent_learned
from services.nova_memory_learning import mem_stats_payload as service_mem_stats_payload
from services.nova_profile_followups import developer_identity_followup_reply as service_developer_identity_followup_reply
from services.nova_profile_followups import developer_profile_reply as service_developer_profile_reply
from services.nova_profile_followups import infer_profile_conversation_state as service_infer_profile_conversation_state
from services.nova_pulse import _patch_activity_summary as service_patch_activity_summary
from services.nova_pulse import _promotion_audit_summary as service_promotion_audit_summary
from services.nova_pulse import render_nova_pulse as service_render_nova_pulse
from services.nova_tool_dispatch import execute_planned_action as service_execute_planned_action
from services.nova_action_ledger_helpers import action_ledger_add_step as service_action_ledger_add_step
from services.nova_action_ledger_helpers import detect_repeated_tool_intent_without_execution as service_detect_repeated_tool_intent_without_execution
from services.nova_identity_history import execute_identity_history_outcome as service_execute_identity_history_outcome
from services.nova_knowledge_packs import build_local_topic_digest_answer as service_build_local_topic_digest_answer
from services.nova_location_weather import tool_weather as service_tool_weather
from services.nova_location_weather import device_location_status_payload as service_device_location_status_payload
from services.nova_location_weather import resolve_windows_device_coords as service_resolve_windows_device_coords
from services.nova_patching import behavioral_check as service_behavioral_check
from services.nova_patching import interactive_preview_review as service_interactive_preview_review
from services.nova_patching import teach_autoapply_proposal as service_teach_autoapply_proposal
from services.nova_patching import teach_propose_patch as service_teach_propose_patch
from services.nova_developer_profile import learn_contextual_developer_facts as service_learn_contextual_developer_facts
from services.nova_profile_followups import identity_profile_followup_reply as service_identity_profile_followup_reply
from services.nova_retrieval_followups import execute_retrieval_followup_outcome as service_execute_retrieval_followup_outcome
from services.nova_reply_contracts import classify_weather_lookup_outcome as service_classify_weather_lookup_outcome
from services.nova_reply_contracts import classify_correction_outcome as service_classify_correction_outcome
from services.nova_reply_contracts import classify_store_fact_outcome as service_classify_store_fact_outcome
from services.nova_reply_sanitizer import sanitize_llm_reply as service_sanitize_llm_reply
from services.nova_routing_support import finalize_routing_decision as service_finalize_routing_decision
from services.nova_routing_support import llm_classify_routing_intent as service_llm_classify_routing_intent
from services.nova_routing_support import looks_like_open_fallback_turn as service_looks_like_open_fallback_turn
from services.nova_tool_policy import web_fetch as service_web_fetch
from services.nova_web_tools import fetch_sitemap_urls as service_fetch_sitemap_urls
from services.nova_web_tools import scan_candidate_urls_for_query as service_scan_candidate_urls_for_query
from services.nova_action_ledger import finalize_action_ledger_record as service_finalize_action_ledger_record
from services.nova_knowledge_packs import kb_search as service_kb_search
from services.patch_control import PATCH_CONTROL_SERVICE
from services.nova_memory_learning import mem_audit as service_mem_audit
from services.nova_memory_learning import mem_recall as service_mem_recall
from services.nova_patching import patch_preview as service_patch_preview
from services.nova_patching import patch_preview_summaries as service_patch_preview_summaries
from services.nova_patching import patch_status_payload as service_patch_status_payload
from services.nova_pulse import build_pulse_payload as service_build_pulse_payload
from services.nova_reflection_health import maybe_log_self_reflection as service_maybe_log_self_reflection
from services.nova_search_endpoint import probe_search_endpoint as service_probe_search_endpoint
from services.nova_turn_heuristics import is_declarative_info as service_is_declarative_info
from services.nova_command_handlers import handle_commands as service_handle_commands
from services.nova_correction_parsing import safe_eval_arithmetic_expression as service_safe_eval_arithmetic_expression
from services.nova_ollama_chat import ollama_chat as service_ollama_chat
from services.nova_reply_guards import sentence_supported_by_evidence as service_sentence_supported_by_evidence
from services.nova_session_followups import build_session_fact_sheet as service_build_session_fact_sheet
from services.nova_truth_hierarchy import hard_answer as service_hard_answer
from services.nova_truth_hierarchy import truth_hierarchy_answer as service_truth_hierarchy_answer
from services.nova_web_tools import tool_stackexchange_search as service_tool_stackexchange_search
from services.nova_web_tools import tool_web_gather as service_tool_web_gather
from services.nova_web_tools import tool_web_research as service_tool_web_research
from services.nova_web_tools import tool_web_search as service_tool_web_search
from services.nova_web_tools import tool_wikipedia_lookup as service_tool_wikipedia_lookup
from services.nova_cli_loop import run_loop as service_run_loop
from services.nova_followup_dispatch import consume_conversation_followup as service_consume_conversation_followup
from services.nova_memory_learning import learn_from_user_correction as service_learn_from_user_correction
from services.nova_memory_learning import mem_add as service_mem_add
from services.nova_patching import patch_apply as service_patch_apply
from services.nova_supervisor_flow import execute_registered_supervisor_rule as service_execute_registered_supervisor_rule
from services.nova_supervisor_flow import handle_supervisor_intent as service_handle_supervisor_intent
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


def behavior_set_flag(name: str, value: object = True, **details) -> None:
    normalized = str(name or "").strip()
    if not normalized:
        return
    try:
        BEHAVIOR_METRICS_STORE.metrics[normalized] = value
        if details:
            flag_details = dict(BEHAVIOR_METRICS_STORE.metrics.get("flag_details") or {})
            flag_details[normalized] = dict(details)
            BEHAVIOR_METRICS_STORE.metrics["flag_details"] = flag_details
        BEHAVIOR_METRICS_STORE.metrics["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        BEHAVIOR_METRICS_STORE.save()
    except Exception:
        pass


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
    return service_action_ledger_add_step(record, stage, outcome, detail, **data)



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
        if stage in {"timing", "timing_breakdown"}:
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
    return service_detect_repeated_tool_intent_without_execution(
        ACTION_LEDGER_DIR,
        records=records,
        limit=limit,
        tool_intent_labels=TOOL_INTENT_LABELS,
    )


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
    return service_maybe_log_self_reflection(
        limit=limit,
        every=every,
        records=records,
        total_records=total_records,
        extra_payload=extra_payload,
        recent_action_ledger_records_fn=_recent_action_ledger_records,
        detect_repeated_tool_intent_without_execution_fn=_detect_repeated_tool_intent_without_execution,
        top_repeated_correction_class_fn=_top_repeated_correction_class,
        routing_stable_recently_fn=_routing_stable_recently,
        count_unsupported_claim_blocks_recently_fn=_count_unsupported_claim_blocks_recently,
        count_routing_overrides_recently_fn=_count_routing_overrides_recently,
        record_used_routing_override_fn=_record_used_routing_override,
        sample_intents_last_fn=_sample_intents_last,
        provider_name_from_tool_fn=_provider_name_from_tool,
        append_self_reflection_fn=_append_self_reflection,
        record_health_snapshot_fn=record_health_snapshot,
        behavior_metrics_update_from_reflection_fn=BEHAVIOR_METRICS_STORE.update_from_reflection,
    )



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
    return service_execute_registered_supervisor_rule(
        rule_result,
        text,
        current_state,
        turns=turns,
        input_source=input_source,
        allowed_actions=allowed_actions,
        remember_name_origin_fn=remember_name_origin,
        make_conversation_state_fn=_make_conversation_state,
        location_reply_fn=_location_reply,
        is_location_name_query_fn=_is_location_name_query,
        location_name_reply_fn=_location_name_reply,
        location_recall_reply_fn=_location_recall_reply,
        classify_weather_lookup_outcome_fn=_classify_weather_lookup_outcome,
        attach_reply_outcome_fn=_attach_reply_outcome,
        execute_planned_action_fn=execute_planned_action,
        render_reply_fn=render_reply,
        last_assistant_turn_text_fn=_last_assistant_turn_text,
        parse_correction_fn=_parse_correction,
        extract_authoritative_correction_text_fn=_extract_authoritative_correction_text,
        store_supervisor_correction_record_fn=_store_supervisor_correction_record,
        learn_from_user_correction_fn=learn_from_user_correction,
        classify_correction_outcome_fn=_classify_correction_outcome,
        mem_enabled_fn=mem_enabled,
        normalize_correction_for_storage_fn=_normalize_correction_for_storage,
        teach_store_example_fn=_teach_store_example,
        get_active_user_fn=get_active_user,
        looks_like_correction_cancel_fn=_looks_like_correction_cancel,
        looks_like_pending_replacement_text_fn=_looks_like_pending_replacement_text,
        execute_retrieval_followup_outcome_fn=_execute_retrieval_followup_outcome,
        execute_identity_history_outcome_fn=_execute_identity_history_outcome,
        open_probe_reply_fn=_open_probe_reply,
        last_question_recall_reply_fn=_last_question_recall_reply,
        session_fact_recall_reply_fn=_session_fact_recall_reply,
        rules_reply_fn=_rules_reply,
        developer_location_reply_fn=_developer_location_reply,
        developer_identity_followup_reply_fn=_developer_identity_followup_reply,
        identity_profile_followup_reply_fn=_identity_profile_followup_reply,
    )



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
    return service_looks_like_open_fallback_turn(
        text,
        is_explicit_command_like_fn=_is_explicit_command_like,
        is_location_request_fn=_is_location_request,
        normalize_turn_text_fn=_normalize_turn_text,
        is_student_data_broad_query_fn=_is_peims_broad_query,
        is_local_knowledge_topic_query_fn=_is_local_knowledge_topic_query,
    )


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
    return service_finalize_routing_decision(
        routing_decision,
        planner_decision=planner_decision,
        reply_contract=reply_contract,
        reply_outcome=reply_outcome,
        turn_acts=turn_acts,
    )


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
    return service_llm_classify_routing_intent(
        text,
        turns,
        live_ollama_calls_allowed_fn=_live_ollama_calls_allowed,
        chat_model_fn=chat_model,
        ollama_base=OLLAMA_BASE,
        get_saved_location_text_fn=get_saved_location_text,
    )


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
    return service_handle_supervisor_intent(
        intent_result,
        user_text,
        turns=turns,
        input_source=input_source,
        entry_point=entry_point,
        classify_web_research_outcome_fn=_classify_web_research_outcome,
        execute_planned_action_fn=execute_planned_action,
        make_retrieval_conversation_state_fn=_make_retrieval_conversation_state,
        render_reply_fn=render_reply,
        mem_enabled_fn=mem_enabled,
        mem_add_fn=mem_add,
        classify_store_fact_outcome_fn=_classify_store_fact_outcome,
        classify_set_location_outcome_fn=_classify_set_location_outcome,
        weather_current_location_available_fn=_weather_current_location_available,
        classify_weather_lookup_outcome_fn=_classify_weather_lookup_outcome,
        execute_weather_lookup_outcome_fn=_execute_weather_lookup_outcome,
        set_location_text_fn=set_location_text,
        make_conversation_state_fn=_make_conversation_state,
        parse_correction_fn=_parse_correction,
        last_assistant_turn_text_fn=_last_assistant_turn_text,
        store_supervisor_correction_record_fn=_store_supervisor_correction_record,
        teach_store_example_fn=_teach_store_example,
        get_active_user_fn=get_active_user,
        classify_correction_outcome_fn=_classify_correction_outcome,
        quick_smalltalk_reply_fn=_quick_smalltalk_reply,
        describe_capabilities_fn=describe_capabilities,
        policy_web_fn=policy_web,
        assistant_name_reply_fn=_assistant_name_reply,
        self_identity_web_challenge_reply_fn=_self_identity_web_challenge_reply,
        classify_name_origin_outcome_fn=_classify_name_origin_outcome,
        developer_full_name_reply_fn=_developer_full_name_reply,
        hard_answer_fn=hard_answer,
        developer_profile_reply_fn=_developer_profile_reply,
        session_recap_reply_fn=_session_recap_reply,
    )



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
    return service_classify_correction_outcome(
        correction_text=correction_text,
        correction_value=correction_value,
        last_assistant=last_assistant,
        pending_followup=pending_followup,
        learned_fact=learned_fact,
        learned_message=learned_message,
        replacement_applied=replacement_applied,
        replacement_pending=replacement_pending,
    )


def _classify_store_fact_outcome(
    intent_result: dict,
    user_text: str = "",
    *,
    source: str = "intent",
    storage_performed: bool = False,
) -> dict[str, object]:
    return service_classify_store_fact_outcome(
        intent_result,
        user_text,
        source=source,
        storage_performed=storage_performed,
    )


def _classify_weather_lookup_outcome(intent_result: dict) -> dict[str, object]:
    return service_classify_weather_lookup_outcome(
        intent_result,
        make_pending_weather_action_fn=make_pending_weather_action,
    )


def _execute_weather_lookup_outcome(weather_outcome: dict[str, object]) -> tuple[str, Optional[dict], dict[str, object]]:
    outcome = dict(weather_outcome or {})
    weather_mode = str(outcome.get("weather_mode") or "clarify").strip().lower() or "clarify"
    next_state = outcome.get("next_state") if isinstance(outcome.get("next_state"), dict) else None
    if weather_mode == "clarify":
        return render_reply(outcome), next_state, outcome

    if weather_mode == "current_location":
        tool_result = execute_planned_action("weather_current_location")
        next_state = _make_weather_result_state(weather_mode=weather_mode, tool_result=str(tool_result or ""))
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
    return service_execute_identity_history_outcome(
        rule_result,
        current_state,
        text,
        turns=turns,
        normalize_turn_text_fn=_normalize_turn_text,
        speaker_matches_developer_fn=_speaker_matches_developer,
        make_conversation_state_fn=_make_conversation_state,
        hard_answer_fn=hard_answer,
        developer_profile_reply_fn=_developer_profile_reply,
        developer_identity_followup_reply_fn=_developer_identity_followup_reply,
        identity_name_followup_reply_fn=_identity_name_followup_reply,
        identity_profile_followup_reply_fn=_identity_profile_followup_reply,
        classify_name_origin_outcome_fn=_classify_name_origin_outcome,
        render_reply_fn=render_reply,
    )



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
    return service_execute_retrieval_followup_outcome(
        state,
        text,
        extract_retrieval_result_index_fn=_extract_retrieval_result_index,
        is_retrieval_meta_question_fn=_is_retrieval_meta_question,
        retrieval_meta_reply_fn=_retrieval_meta_reply,
        tool_web_gather_fn=tool_web_gather,
        make_retrieval_conversation_state_fn=_make_retrieval_conversation_state,
        looks_like_retrieval_followup_fn=_looks_like_retrieval_followup,
        tool_web_research_continue_fn=lambda: tool_web_research("", continue_mode=True),
        web_research_query_fn=lambda: str(getattr(WEB_RESEARCH_SESSION, 'query', '') or ''),
        web_research_result_count_fn=WEB_RESEARCH_SESSION.result_count,
        web_research_has_results_fn=WEB_RESEARCH_SESSION.has_results,
        render_reply_fn=render_reply,
    )



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
    lane: str = "",
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
        "lane": str(lane or "").strip(),
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
    return service_finalize_action_ledger_record(
        record,
        final_answer=final_answer,
        planner_decision=planner_decision,
        tool=tool,
        tool_args=tool_args,
        tool_result=tool_result,
        grounded=grounded,
        intent=intent,
        active_subject=active_subject,
        continuation_used=continuation_used,
        reply_contract=reply_contract,
        reply_outcome=reply_outcome,
        routing_decision=routing_decision,
        reflection_payload=reflection_payload,
        provider_name_from_tool_fn=_provider_name_from_tool,
        finalize_routing_decision_fn=_finalize_routing_decision,
        action_ledger_add_step_fn=action_ledger_add_step,
        action_ledger_route_summary_fn=action_ledger_route_summary,
        write_action_ledger_record_fn=write_action_ledger_record,
        recent_action_ledger_records_fn=_recent_action_ledger_records,
        maybe_log_self_reflection_fn=maybe_log_self_reflection,
    )



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
    return service_truth_hierarchy_answer(
        user_text,
        is_action_history_query_fn=_is_action_history_query,
        action_history_reply_fn=_action_history_reply,
        is_identity_or_developer_query_fn=_is_identity_or_developer_query,
        hard_answer_fn=hard_answer,
        get_name_origin_story_fn=get_name_origin_story,
        is_capability_query_fn=_is_capability_query,
        describe_capabilities_fn=describe_capabilities,
        is_policy_domain_query_fn=_is_policy_domain_query,
        policy_web_fn=policy_web,
    )


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
    return service_web_fetch(
        url,
        save_dir,
        web_enabled_fn=web_enabled,
        policy_web_fn=policy_web,
        host_allowed_fn=_host_allowed,
    )



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
    return service_device_location_status_payload(
        snapshot,
        max_age_sec=max_age_sec,
        runtime_device_backend_provider_fn=_runtime_device_backend_provider,
    )


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
    return service_resolve_windows_device_coords(
        timeout_sec,
        runtime_device_backend_provider_fn=_runtime_device_backend_provider,
    )


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
    if "saved location" in normalized and (
        "use the saved location" in normalized
        or "using the saved location" in normalized
        or normalized.startswith("yes ")
        or normalized in {"yes", "yeah", "yep", "ok", "okay", "sure", "please do", "go ahead"}
    ):
        return True
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


def tool_weather(location: str):
    return service_tool_weather(
        location,
        policy_tools_enabled_fn=policy_tools_enabled,
        web_enabled_fn=web_enabled,
        weather_source_host_fn=_weather_source_host,
        weather_unavailable_message_fn=_weather_unavailable_message,
        coords_for_location_hint_fn=_coords_for_location_hint,
        need_confirmed_location_message_fn=_need_confirmed_location_message,
        get_weather_for_location_fn=get_weather_for_location,
        format_weather_output_fn=_format_weather_output,
    )


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
    return service_mem_stats_payload(
        emit_event=emit_event,
        mem_enabled_fn=mem_enabled,
        memory_mod=memory_mod,
        memory_runtime_user_fn=_memory_runtime_user,
        mem_scope_fn=mem_scope,
        record_memory_event_fn=_record_memory_event,
    )



def mem_add(kind: str, source: str, text: str):
    return service_mem_add(
        kind,
        source,
        text,
        mem_enabled_fn=mem_enabled,
        identity_memory_text_allowed_fn=_identity_memory_text_allowed,
        record_memory_event_fn=_record_memory_event,
        mem_scope_fn=mem_scope,
        memory_should_keep_text_fn=_memory_should_keep_text,
        memory_write_user_fn=_memory_write_user,
        memory_mod=memory_mod,
        mem_min_score_fn=mem_min_score,
        python_path=str(PYTHON),
        base_dir=BASE_DIR,
    )



def mem_recall(query: str) -> str:
    return service_mem_recall(
        query,
        mem_enabled_fn=mem_enabled,
        memory_runtime_user_fn=_memory_runtime_user,
        memory_mod=memory_mod,
        mem_context_top_k_fn=mem_context_top_k,
        mem_min_score_fn=mem_min_score,
        mem_exclude_sources_fn=mem_exclude_sources,
        mem_scope_fn=mem_scope,
        format_memory_recall_hits_fn=_format_memory_recall_hits,
        record_memory_event_fn=_record_memory_event,
        python_path=str(PYTHON),
        base_dir=BASE_DIR,
    )



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
    return service_mem_get_recent_learned(
        limit,
        mem_enabled_fn=mem_enabled,
        memory_mod=memory_mod,
        memory_runtime_user_fn=_memory_runtime_user,
        mem_scope_fn=mem_scope,
        normalize_recent_learning_item_fn=_normalize_recent_learning_item,
        load_learned_facts_fn=load_learned_facts,
        record_memory_event_fn=_record_memory_event,
    )



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
    return service_mem_audit(
        query,
        memory_runtime_user_fn=_memory_runtime_user,
        memory_mod=memory_mod,
        mem_context_top_k_fn=mem_context_top_k,
        mem_min_score_fn=mem_min_score,
        mem_exclude_sources_fn=mem_exclude_sources,
        mem_scope_fn=mem_scope,
        record_memory_event_fn=_record_memory_event,
        python_path=str(PYTHON),
        base_dir=BASE_DIR,
    )



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
    return service_learn_from_user_correction(
        text,
        load_learned_facts_fn=load_learned_facts,
        get_learned_fact_fn=get_learned_fact,
        save_learned_facts_fn=save_learned_facts,
        set_active_user_fn=set_active_user,
        mem_enabled_fn=mem_enabled,
        mem_add_fn=mem_add,
    )



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
    return service_build_session_fact_sheet(
        turns,
        max_chars=max_chars,
        get_learned_fact_fn=get_learned_fact,
        get_active_user_fn=get_active_user,
        get_name_origin_story_fn=get_name_origin_story,
        get_saved_location_text_fn=get_saved_location_text,
        extract_color_preferences_fn=_extract_color_preferences,
        extract_developer_color_preferences_fn=_extract_developer_color_preferences,
        extract_developer_color_preferences_from_memory_fn=_extract_developer_color_preferences_from_memory,
        developer_is_bilingual_fn=_developer_is_bilingual,
        developer_is_bilingual_from_memory_fn=_developer_is_bilingual_from_memory,
        extract_animal_preferences_fn=_extract_animal_preferences,
    )



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
    return service_sentence_supported_by_evidence(
        sentence,
        evidence_text,
        tool_context,
        is_risky_claim_sentence_fn=_is_risky_claim_sentence,
        content_tokens_fn=_content_tokens,
    )


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
    return service_is_declarative_info(text)


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
    return service_probe_search_endpoint(
        endpoint,
        timeout=timeout,
        persist_repair=persist_repair,
        get_search_endpoint_fn=get_search_endpoint,
        auto_repair_search_endpoint_fn=auto_repair_search_endpoint,
        requests_get_fn=requests.get,
    )



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
    return service_developer_profile_reply(
        turns,
        user_text,
        get_learned_fact_fn=get_learned_fact,
        extract_developer_roles_from_memory_fn=_extract_developer_roles_from_memory,
        extract_developer_color_preferences_fn=_extract_developer_color_preferences,
        extract_developer_color_preferences_from_memory_fn=_extract_developer_color_preferences_from_memory,
        developer_is_bilingual_fn=_developer_is_bilingual,
        developer_is_bilingual_from_memory_fn=_developer_is_bilingual_from_memory,
        prefix_from_earlier_memory_fn=_prefix_from_earlier_memory,
        format_fact_series_fn=_format_fact_series,
    )



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
    return service_identity_profile_followup_reply(
        subject,
        turns=turns,
        get_active_user_fn=get_active_user,
        get_learned_fact_fn=get_learned_fact,
        speaker_matches_developer_fn=_speaker_matches_developer,
        extract_developer_roles_from_memory_fn=_extract_developer_roles_from_memory,
        extract_developer_color_preferences_fn=_extract_developer_color_preferences,
        extract_developer_color_preferences_from_memory_fn=_extract_developer_color_preferences_from_memory,
        developer_is_bilingual_fn=_developer_is_bilingual,
        developer_is_bilingual_from_memory_fn=_developer_is_bilingual_from_memory,
        get_name_origin_story_fn=get_name_origin_story,
        extract_color_preferences_fn=_extract_color_preferences,
        extract_color_preferences_from_memory_fn=_extract_color_preferences_from_memory,
        extract_animal_preferences_fn=_extract_animal_preferences,
        extract_animal_preferences_from_memory_fn=_extract_animal_preferences_from_memory,
        format_fact_series_fn=_format_fact_series,
    )



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
    return service_developer_identity_followup_reply(
        turns,
        name_focus=name_focus,
        get_learned_fact_fn=get_learned_fact,
        get_name_origin_story_fn=get_name_origin_story,
        extract_developer_roles_from_memory_fn=_extract_developer_roles_from_memory,
        extract_developer_color_preferences_fn=_extract_developer_color_preferences,
        extract_developer_color_preferences_from_memory_fn=_extract_developer_color_preferences_from_memory,
        developer_is_bilingual_fn=_developer_is_bilingual,
        developer_is_bilingual_from_memory_fn=_developer_is_bilingual_from_memory,
        format_fact_series_fn=_format_fact_series,
    )


def _infer_profile_conversation_state(text: str) -> Optional[dict]:
    return service_infer_profile_conversation_state(
        text,
        normalize_turn_text_fn=_normalize_turn_text,
        evaluate_rule_state_fn=lambda candidate: TURN_SUPERVISOR.evaluate_rules(candidate, phase="state"),
        speaker_matches_developer_fn=_speaker_matches_developer,
        is_developer_color_lookup_request_fn=_is_developer_color_lookup_request,
        is_developer_bilingual_request_fn=_is_developer_bilingual_request,
        is_color_lookup_request_fn=_is_color_lookup_request,
        make_conversation_state_fn=_make_conversation_state,
    )


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
    return service_consume_conversation_followup(
        state,
        text,
        input_source=input_source,
        turns=turns,
        evaluate_rules_fn=lambda text, manager, turns=None, phase="handle": TURN_SUPERVISOR.evaluate_rules(
            text,
            manager=manager,
            turns=turns,
            phase=phase,
        ),
        execute_registered_supervisor_rule_fn=_execute_registered_supervisor_rule,
        is_retrieval_meta_question_fn=_is_retrieval_meta_question,
        retrieval_meta_reply_fn=_retrieval_meta_reply,
        looks_like_retrieval_followup_fn=_looks_like_retrieval_followup,
        retrieval_followup_reply_fn=_retrieval_followup_reply,
        is_queue_status_reason_followup_fn=_is_queue_status_reason_followup,
        queue_status_reason_reply_fn=_queue_status_reason_reply,
        is_queue_status_report_followup_fn=_is_queue_status_report_followup,
        queue_status_report_reply_fn=_queue_status_report_reply,
        is_queue_status_seam_followup_fn=_is_queue_status_seam_followup,
        queue_status_seam_reply_fn=_queue_status_seam_reply,
        handle_location_conversation_turn_fn=_handle_location_conversation_turn,
        is_weather_meta_followup_fn=_is_weather_meta_followup,
        weather_meta_reply_fn=_weather_meta_reply,
        is_weather_status_followup_fn=_is_weather_status_followup,
        weather_status_reply_fn=_weather_status_reply,
        normalize_turn_text_fn=_normalize_turn_text,
        numeric_reference_guess_reply_fn=_numeric_reference_guess_reply,
        numeric_reference_binding_reply_fn=_numeric_reference_binding_reply,
        make_conversation_state_fn=_make_conversation_state,
        extract_work_role_parts_fn=_extract_work_role_parts,
        store_developer_role_facts_fn=_store_developer_role_facts,
        strip_confirmation_prefix_fn=_strip_confirmation_prefix,
        looks_like_profile_followup_fn=_looks_like_profile_followup,
        developer_identity_followup_reply_fn=_developer_identity_followup_reply,
        non_retrieval_resource_meta_reply_fn=_non_retrieval_resource_meta_reply,
        is_developer_location_request_fn=_is_developer_location_request,
        developer_location_reply_fn=_developer_location_reply,
        identity_name_followup_reply_fn=_identity_name_followup_reply,
        identity_profile_followup_reply_fn=_identity_profile_followup_reply,
    )



def _learn_contextual_developer_facts(turns: list[tuple[str, str]], text: str, input_source: str = "typed") -> tuple[bool, str]:
    return service_learn_contextual_developer_facts(
        turns,
        text,
        input_source=input_source,
        normalize_turn_text_fn=_normalize_turn_text,
        recent_turn_mentions_fn=_recent_turn_mentions,
        mem_enabled_fn=mem_enabled,
        mem_add_fn=mem_add,
        extract_color_preferences_from_text_fn=_extract_color_preferences_from_text,
        extract_work_role_parts_fn=_extract_work_role_parts,
        store_developer_role_facts_fn=_store_developer_role_facts,
        load_learned_facts_fn=load_learned_facts,
        save_learned_facts_fn=save_learned_facts,
        timestamp_fn=lambda: time.strftime("%Y-%m-%d %H:%M:%S"),
    )


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
    return service_kb_search(
        query,
        packs_dir=PACKS_DIR,
        kb_active_pack_fn=kb_active_pack,
        tokenize_fn=_tokenize,
        max_files=max_files,
        max_chars=max_chars,
    )



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
    return service_build_local_topic_digest_answer(
        query_text,
        packs_dir=PACKS_DIR,
        base_dir=BASE_DIR,
        active_knowledge_root_fn=_active_knowledge_root,
        topic_tokens_fn=_topic_tokens,
        read_text_safely_fn=_read_text_safely,
        extract_matching_lines_fn=_extract_matching_lines,
        max_files=max_files,
        max_points=max_points,
    )



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
    return service_behavioral_check(
        base_dir=Path(base_dir or BASE_DIR),
        timeout_sec=timeout_sec,
        policy_patch_fn=policy_patch,
        behavioral_check_command_fn=_behavioral_check_command,
    )



def _read_patch_log_tail_line() -> str:
    try:
        if not PATCH_LOG.exists():
            return ""
        return _last_nonempty_line(PATCH_LOG.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return ""


def patch_preview_summaries(limit: int = 40) -> list[dict]:
    return service_patch_preview_summaries(
        updates_dir=UPDATES_DIR,
        read_approvals_fn=_read_approvals,
        limit=limit,
    )


def patch_status_payload() -> dict:
    return service_patch_status_payload(
        base_dir=BASE_DIR,
        updates_dir=UPDATES_DIR,
        read_approvals_fn=_read_approvals,
        read_patch_revision_fn=_read_patch_revision,
        read_patch_log_tail_line_fn=_read_patch_log_tail_line,
        policy_patch_fn=policy_patch,
        patch_preview_summaries_fn=patch_preview_summaries,
    )


def _patch_control_state(*, include_readiness: bool = True) -> dict:
    patch = patch_status_payload()
    previews = list(patch.get("previews") or []) if isinstance(patch.get("previews"), list) else []
    if not previews:
        previews = list(patch_preview_summaries(40) or [])
    readiness = None
    if include_readiness:
        readiness = PATCH_CONTROL_SERVICE.patch_action_readiness_payload(
            patch,
            preview_summaries_fn=patch_preview_summaries,
            show_preview_fn=show_preview,
            updates_dir=UPDATES_DIR,
        )
    return PATCH_CONTROL_SERVICE.patch_control_state(
        patch,
        previews,
        include_readiness=include_readiness,
        readiness_payload=readiness,
    )



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
    return service_patch_apply(
        zip_path,
        force=force,
        safe_path_fn=safe_path,
        policy_patch_fn=policy_patch,
        read_patch_revision_fn=_read_patch_revision,
        read_patch_manifest_fn=_read_patch_manifest,
        log_patch_fn=_log_patch,
        patch_reject_message_fn=_patch_reject_message,
        read_approvals_fn=_read_approvals,
        patch_preview_fn=patch_preview,
        snapshot_current_fn=_snapshot_current,
        overlay_zip_fn=_overlay_zip,
        py_compile_check_fn=_py_compile_check,
        patch_rollback_fn=patch_rollback,
        behavioral_check_fn=_behavioral_check,
        write_patch_revision_fn=_write_patch_revision,
        patch_manifest_name=PATCH_MANIFEST_NAME,
        base_dir=BASE_DIR,
    )



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
    return service_patch_preview(
        zip_path,
        write_report=write_report,
        safe_path_fn=safe_path,
        base_dir=BASE_DIR,
        updates_dir=UPDATES_DIR,
        read_patch_manifest_fn=_read_patch_manifest,
        read_patch_revision_fn=_read_patch_revision,
    )



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


def tool_patch_preview_apply(preview: str) -> dict:
    preview_name = str(preview or "").strip()
    patch_summary = patch_status_payload()
    preview_limit = max(200, int(patch_summary.get("previews_total", 0) or 0))
    preview_rows = list(patch_preview_summaries(preview_limit) or [])
    ok, msg, extra, detail = PATCH_CONTROL_SERVICE.patch_preview_apply(
        {"preview": preview_name},
        preview_target_fn=lambda payload: PATCH_CONTROL_SERVICE.patch_preview_target(payload, preview_rows),
        preview_entry_fn=lambda target: PATCH_CONTROL_SERVICE.patch_preview_entry(target, preview_rows),
        patch_control_state_fn=_patch_control_state,
        show_preview_fn=show_preview,
        updates_dir=UPDATES_DIR,
        patch_apply_fn=patch_apply,
    )
    result = {
        "ok": bool(ok),
        "message": str(msg or ""),
        "detail": str(detail or ""),
    }
    if isinstance(extra, dict):
        result.update(extra)
    if not ok:
        result["error"] = str((extra or {}).get("text") or detail or msg or "patch_preview_apply_failed")
    return result


def tool_patch_preview_approve(preview: str) -> dict:
    preview_name = str(preview or "").strip()
    patch_summary = patch_status_payload()
    preview_limit = max(200, int(patch_summary.get("previews_total", 0) or 0))
    preview_rows = list(patch_preview_summaries(preview_limit) or [])
    ok, msg, extra, detail = PATCH_CONTROL_SERVICE.patch_preview_decision(
        "approve",
        {
            "preview": preview_name,
            "note": "autonomy maintenance: governed work tree approval for base-compatible patch preview",
        },
        preview_target_fn=lambda payload: PATCH_CONTROL_SERVICE.patch_preview_target(payload, preview_rows),
        patch_control_state_fn=_patch_control_state,
        decision_fn=lambda target, note: approve_preview(target, note or "autonomy maintenance approved preview"),
    )
    result = {
        "ok": bool(ok),
        "message": str(msg or ""),
        "detail": str(detail or ""),
    }
    if isinstance(extra, dict):
        result.update(extra)
    if not ok:
        result["error"] = str((extra or {}).get("text") or detail or msg or "patch_preview_approve_failed")
    return result


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
    return service_interactive_preview_review(
        preview_path,
        record_approval_fn=_record_approval,
        get_active_user_fn=get_active_user,
    )



def _interactive_patch_review_enabled() -> bool:
    raw = str(os.environ.get("NOVA_INTERACTIVE_PATCH_REVIEW") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


# =========================
# Deterministic answers & hallucination filters
# =========================
def hard_answer(user_text: str) -> Optional[str]:
    return service_hard_answer(
        user_text,
        arithmetic_expression_reply_fn=_arithmetic_expression_reply,
        get_learned_fact_fn=get_learned_fact,
        get_active_user_fn=get_active_user,
        speaker_matches_developer_fn=_speaker_matches_developer,
        self_identity_web_challenge_reply_fn=_self_identity_web_challenge_reply,
        get_name_origin_story_fn=get_name_origin_story,
        prefix_from_earlier_memory_fn=_prefix_from_earlier_memory,
        extract_developer_color_preferences_from_memory_fn=_extract_developer_color_preferences_from_memory,
        describe_capabilities_fn=describe_capabilities,
        mem_get_recent_learned_fn=mem_get_recent_learned,
    )



def sanitize_llm_reply(reply: str, tool_context: str = "") -> str:
    return service_sanitize_llm_reply(
        reply,
        tool_context,
        weather_unavailable_message_fn=_weather_unavailable_message,
        describe_capabilities_fn=describe_capabilities,
    )


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
    return service_ollama_chat(
        text,
        retrieved_context=retrieved_context,
        language_mix_spanish_pct=language_mix_spanish_pct,
        live_ollama_calls_allowed_fn=_live_ollama_calls_allowed,
        ensure_ollama_fn=ensure_ollama,
        identity_context_for_prompt_fn=identity_context_for_prompt,
        language_mix_instruction_fn=_language_mix_instruction,
        chat_model_fn=chat_model,
        requests_post_fn=requests.post,
        ollama_base=OLLAMA_BASE,
        ollama_req_timeout=OLLAMA_REQ_TIMEOUT,
        warn_fn=warn,
        kill_ollama_fn=kill_ollama,
        start_ollama_serve_detached_fn=start_ollama_serve_detached,
        sleep_fn=time.sleep,
        env=os.environ,
    )



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
    return service_safe_eval_arithmetic_expression(expr)


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
    return service_teach_propose_patch(
        description,
        updates_dir=UPDATES_DIR,
        read_patch_revision_fn=_read_patch_revision,
        patch_manifest_name=PATCH_MANIFEST_NAME,
        patch_preview_fn=patch_preview,
        interactive_patch_review_enabled_fn=_interactive_patch_review_enabled,
        interactive_preview_review_fn=interactive_preview_review,
    )


def _teach_autoapply_proposal(zip_path: str, apply_live: bool = False) -> str:
    return service_teach_autoapply_proposal(
        zip_path,
        apply_live=apply_live,
        updates_dir=UPDATES_DIR,
        base_dir=BASE_DIR,
        patch_preview_fn=patch_preview,
        behavioral_check_fn=_behavioral_check,
        patch_apply_fn=patch_apply,
    )


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
    return service_promotion_audit_summary(
        promotion_audit_log=PROMOTION_AUDIT_LOG,
        generated_definitions_dir=GENERATED_DEFINITIONS_DIR,
        promoted_definitions_dir=PROMOTED_DEFINITIONS_DIR,
        pending_review_dir=PENDING_REVIEW_DIR,
        quarantine_dir=QUARANTINE_DIR,
    )


def _patch_activity_summary(window_hours: int = 24) -> dict:
    return service_patch_activity_summary(
        patch_log=PATCH_LOG,
        read_patch_log_tail_line_fn=_read_patch_log_tail_line,
        window_hours=window_hours,
    )


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
    return service_build_pulse_payload(
        promotion_audit_log=PROMOTION_AUDIT_LOG,
        generated_definitions_dir=GENERATED_DEFINITIONS_DIR,
        promoted_definitions_dir=PROMOTED_DEFINITIONS_DIR,
        pending_review_dir=PENDING_REVIEW_DIR,
        quarantine_dir=QUARANTINE_DIR,
        behavior_metrics_file=BEHAVIOR_METRICS_FILE,
        autonomy_maintenance_file=AUTONOMY_MAINTENANCE_FILE,
        pulse_snapshot_file=PULSE_SNAPSHOT_FILE,
        patch_log=PATCH_LOG,
        load_json_file_fn=_load_json_file,
        patch_status_payload_fn=patch_status_payload,
        read_patch_log_tail_line_fn=_read_patch_log_tail_line,
        ollama_api_up_fn=ollama_api_up,
        mem_stats_payload_fn=mem_stats_payload,
        kidney_summary_fn=lambda: __import__('kidney').run_kidney(dry_run=True),
        safety_policy_fn=lambda: __import__('nova_safety_envelope').policy_safety_envelope(),
        latest_approved_update_zip_fn=_latest_approved_update_zip,
    )



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
    return service_render_nova_pulse(
        payload,
        build_pulse_payload_fn=build_pulse_payload,
    )



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
    planned_tool_map = {
        "find": tool_find,
        "ls": tool_ls,
        "queue_status": tool_queue_status,
        "phase2_audit": tool_phase2_audit,
        "pulse": tool_nova_pulse,
        "patch_preview_approve": tool_patch_preview_approve,
        "patch_apply": patch_apply,
        "patch_preview_apply": tool_patch_preview_apply,
        "patch_rollback": patch_rollback,
        "read": tool_read,
        "system_check": tool_system_check,
        "update_now": tool_update_now,
        "update_now_confirm": tool_update_now_confirm,
        "update_now_cancel": tool_update_now_cancel,
        "web_search": tool_web_search,
        "web_research": tool_web_research,
        "web_gather": tool_web_gather,
        "wikipedia_lookup": tool_wikipedia_lookup,
        "stackexchange_search": tool_stackexchange_search,
        "health": tool_health,
    }
    return service_execute_planned_action(
        tool,
        args,
        resolve_current_device_coords_fn=resolve_current_device_coords,
        tool_weather_fn=tool_weather,
        get_saved_location_text_fn=get_saved_location_text,
        coords_from_saved_location_fn=_coords_from_saved_location,
        need_confirmed_location_message_fn=_need_confirmed_location_message,
        set_location_coords_fn=set_location_coords,
        tool_map=planned_tool_map,
    )



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
    return service_scan_candidate_urls_for_query(
        urls,
        query_tokens,
        max_pages,
        min_score=min_score,
        requests_get_fn=requests.get,
        expand_research_terms_fn=_expand_research_terms,
        extract_text_from_html_content_fn=_extract_text_from_html_content,
        score_research_hit_fn=_score_research_hit,
    )



def _fetch_sitemap_urls(domain: str, limit: int = 80) -> list[str]:
    return service_fetch_sitemap_urls(
        domain,
        limit=limit,
        requests_get_fn=requests.get,
        host_allowed_fn=_host_allowed,
    )



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
    return service_tool_wikipedia_lookup(
        query,
        explain_missing_fn=explain_missing,
        policy_tools_enabled_fn=policy_tools_enabled,
        web_enabled_fn=web_enabled,
        requests_get_fn=requests.get,
    )



def tool_stackexchange_search(query: str):
    return service_tool_stackexchange_search(
        query,
        explain_missing_fn=explain_missing,
        policy_tools_enabled_fn=policy_tools_enabled,
        web_enabled_fn=web_enabled,
        policy_web_fn=policy_web,
        requests_get_fn=requests.get,
        env=os.environ,
    )


def tool_web_search(query: str):
    return service_tool_web_search(
        query,
        explain_missing_fn=explain_missing,
        policy_tools_enabled_fn=policy_tools_enabled,
        web_enabled_fn=web_enabled,
        policy_web_fn=policy_web,
        host_allowed_fn=_host_allowed,
        decode_search_href_fn=_decode_search_href,
        probe_search_endpoint_fn=probe_search_endpoint,
        web_allowlist_message_fn=_web_allowlist_message,
        requests_get_fn=requests.get,
    )



def tool_web_gather(url: str):
    return service_tool_web_gather(
        url,
        explain_missing_fn=explain_missing,
        policy_tools_enabled_fn=policy_tools_enabled,
        web_fetch_fn=lambda target_url: web_fetch(target_url, WEB_CACHE_DIR),
        web_allowlist_message_fn=_web_allowlist_message,
        extract_text_from_path_fn=_extract_text_from_path,
    )



def tool_web_research(query: str, continue_mode: bool = False):
    return service_tool_web_research(
        query,
        continue_mode=continue_mode,
        explain_missing_fn=explain_missing,
        policy_tools_enabled_fn=policy_tools_enabled,
        web_enabled_fn=web_enabled,
        policy_web_fn=policy_web,
        tokenize_fn=_tokenize,
        fetch_sitemap_urls_fn=_fetch_sitemap_urls,
        scan_candidate_urls_for_query_fn=_scan_candidate_urls_for_query,
        seed_urls_for_domain_fn=_seed_urls_for_domain,
        crawl_domain_for_query_fn=_crawl_domain_for_query,
        session_store=WEB_RESEARCH_SESSION,
    )



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
    return service_handle_commands(
        user_text,
        session_turns=session_turns,
        session=session,
        core=sys.modules[__name__],
    )



# =========================
# Main loop
# =========================
def run_loop(tts):
    return service_run_loop(tts, core=sys.modules[__name__])


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
