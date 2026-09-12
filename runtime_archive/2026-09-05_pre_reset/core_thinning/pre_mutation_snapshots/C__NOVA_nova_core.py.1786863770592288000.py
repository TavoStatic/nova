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

"""
Nova Core — interactive CLI/voice loop, tool registry, Ollama chat.

NOVA_DOC:
  category: subsystem
  authority: active_authority
  last_session: 2026-08-05
  last_agent: claude-cowork
  session_state: current
  next_step: none
  open: none
"""

from __future__ import annotations

import argparse
import importlib
import asyncio
import ast
import importlib.util
import json
import os
import math
import re
import socket
import subprocess
import threading
import time
import zipfile
import mimetypes
import tempfile
from pathlib import Path
from typing import Any, Optional, Tuple
from conversation_manager import ConversationSession
from subconscious_config import SUBCONSCIOUS_CHARTER
from supervisor import Supervisor
from capabilities import explain_missing, load_capabilities
from action_planner import decide_actions
from env_inspector import inspect_environment, format_report
import requests
import psutil
from tools import ToolContext, ToolInvocationError, build_default_registry
from tools.registry import build_core_tool_exports as service_build_core_tool_exports
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
from services.memory_production import apply_user_memory_learning as service_apply_user_memory_learning
from services.memory_production import build_memory_read_plan
from services.memory_production import build_memory_recall_plan
from services.nova_context_assembly import build_fallback_context_details as service_build_fallback_context_details
from services.nova_context_assembly import build_learning_context_details as service_build_learning_context_details
from services.nova_context_assembly import render_chat_context as service_render_chat_context
from services.nova_context_assembly import render_session_state_context as service_render_session_state_context
from services.nova_memory_learning import learn_from_user_correction as service_learn_from_user_correction
from services.nova_memory_learning import mem_get_recent_learned as service_mem_get_recent_learned
from services.nova_memory_learning import identity_context_for_prompt as service_identity_context_for_prompt
from services.nova_operational_identity import operational_identity_context_for_prompt as service_operational_identity_context_for_prompt
from services.nova_memory_learning import load_json_dict_with_tmp_fallback as service_load_json_dict_with_tmp_fallback
from services.nova_memory_learning import mem_stats_payload as service_mem_stats_payload
from services.memory_health import build_memory_health_payload as service_build_memory_health_payload
from services.memory_retention import apply_memory_hygiene as service_apply_memory_hygiene
from services.memory_retention import render_memory_hygiene_result as service_render_memory_hygiene_result
from services.nova_pipeline_tools import handle_pipeline_command as service_handle_pipeline_command
from services.nova_pulse import render_nova_pulse as service_render_nova_pulse
from services.nova_pulse import tool_nova_pulse as service_tool_nova_pulse
from services.nova_pulse import write_pulse_snapshot as service_write_pulse_snapshot
from services.nova_self_status import build_self_status_payload as service_build_self_status_payload
from services.nova_self_status import build_repo_change_snapshot as service_build_repo_change_snapshot
from services.nova_self_status import read_recent_ops_events as service_read_recent_ops_events
from services.nova_self_status import render_self_status as service_render_self_status
from services.control_work_trees import CONTROL_WORK_TREES_SERVICE
from services.work_tree_pressure_snapshot import build_work_tree_pressure_snapshot
from services.release_status import RELEASE_STATUS_SERVICE
from services.core_health_brief import build_core_health_brief as service_build_core_health_brief
from services.core_health_brief import feed_core_health_brief_to_work_tree as service_feed_core_health_brief_to_work_tree
from services.core_health_brief import render_core_health_brief as service_render_core_health_brief
from services.core_health_brief import write_core_health_brief as service_write_core_health_brief
from services.core_steward import build_core_steward_payload as service_build_core_steward_payload
from services.core_thinning import build_core_thinning_brief as service_build_core_thinning_brief
from services.core_thinning import execute_core_thinning_order as service_execute_core_thinning_order
from services.core_thinning import feed_core_thinning_brief_to_work_tree as service_feed_core_thinning_brief_to_work_tree
from services.core_thinning import render_core_thinning_brief as service_render_core_thinning_brief
from services.nova_tool_dispatch import execute_planned_action_from_runtime as service_execute_planned_action_from_runtime
from services.nova_action_ledger_helpers import action_ledger_add_step as service_action_ledger_add_step
from services.nova_action_ledger_helpers import action_ledger_route_summary as service_action_ledger_route_summary
from services.nova_action_ledger_helpers import count_routing_overrides_recently as service_count_routing_overrides_recently
from services.nova_action_ledger_helpers import detect_repeated_tool_intent_without_execution as service_detect_repeated_tool_intent_without_execution
from services.nova_action_ledger_helpers import recent_action_ledger_records as service_recent_action_ledger_records
from services.nova_action_ledger_helpers import record_completed_tool_execution as service_record_completed_tool_execution
from services.nova_action_ledger_helpers import record_requested_tool_clarification as service_record_requested_tool_clarification
from services.nova_action_ledger_helpers import record_used_routing_override as service_record_used_routing_override
from services.nova_action_ledger_helpers import routing_stable_recently as service_routing_stable_recently
from services.nova_action_ledger_helpers import sample_intents_last as service_sample_intents_last
from services.nova_action_ledger_helpers import top_repeated_correction_class as service_top_repeated_correction_class
from services.nova_knowledge_packs import build_local_topic_digest_answer as service_build_local_topic_digest_answer
from services.nova_location_weather import device_location_status_payload as service_device_location_status_payload
from services.nova_location_weather import clear_runtime_device_location as service_clear_runtime_device_location
from services.nova_location_weather import coords_for_location_hint as service_coords_for_location_hint
from services.nova_location_weather import coords_from_saved_location as service_coords_from_saved_location
from services.nova_location_weather import format_weather_output as service_format_weather_output
from services.nova_location_weather import get_weather_for_location as service_get_weather_for_location
from services.nova_location_weather import get_saved_location_text as service_get_saved_location_text
from services.nova_location_weather import need_confirmed_location_message as service_need_confirmed_location_message
from services.nova_location_weather import parse_lat_lon as service_parse_lat_lon
from services.nova_location_weather import resolve_current_device_coords as service_resolve_current_device_coords
from services.nova_location_weather import resolve_windows_device_coords as service_resolve_windows_device_coords
from services.nova_location_weather import runtime_device_backend_provider as service_runtime_device_backend_provider
from services.nova_location_weather import runtime_device_location_payload as service_runtime_device_location_payload
from services.nova_location_weather import set_location_coords as service_set_location_coords
from services.nova_location_weather import set_runtime_device_location as service_set_runtime_device_location
from services.nova_location_weather import tool_weather as service_tool_weather
from services.nova_location_weather import weather_response_style as service_weather_response_style
from services.nova_location_weather import weather_source_host as service_weather_source_host
from services.nova_location_weather import weather_unavailable_message as service_weather_unavailable_message
from services.nova_patching import behavioral_check as service_behavioral_check
from services.nova_patching import interactive_preview_review as service_interactive_preview_review
from services.nova_patching import teach_autoapply_proposal as service_teach_autoapply_proposal
from services.nova_patching import teach_propose_patch as service_teach_propose_patch
from services.nova_routing_support import finalize_routing_decision as service_finalize_routing_decision
from services.nova_routing_support import llm_classify_routing_intent as service_llm_classify_routing_intent
from services.nova_intent_understanding import classify_turn_intent as service_classify_turn_intent
from services.nova_intent_understanding import select_response_strategy as service_select_response_strategy
from services.nova_intent_understanding import record_intent_outcome as service_record_intent_outcome
from services.work_tree_signal_ingestion import WorkTreeSignalIngestionService as _WorkTreeSignalIngestionService
from services.nova_routing_helpers import strip_invocation_prefix as service_strip_invocation_prefix
from services.nova_tool_policy import web_fetch as service_web_fetch
from services.nova_tool_policy import web_allowlist_message as service_web_allowlist_message
from services.nova_web_tools import fetch_sitemap_urls as service_fetch_sitemap_urls
from services.nova_web_tools import scan_candidate_urls_for_query as service_scan_candidate_urls_for_query
from services.nova_action_ledger import finalize_action_ledger_record_from_runtime as service_finalize_action_ledger_record_from_runtime
from services.nova_action_ledger import start_action_ledger_record as service_start_action_ledger_record
from services.nova_action_ledger import write_action_ledger_record as service_write_action_ledger_record
from services.nova_knowledge_packs import kb_search as service_kb_search
from services.patch_control import PATCH_CONTROL_SERVICE
from services.nova_memory_learning import mem_audit as service_mem_audit
from services.nova_memory_learning import mem_recall as service_mem_recall
from services.nova_patching import patch_preview as service_patch_preview
from services.nova_patching import patch_rollback as service_patch_rollback
from services.nova_patching import patch_preview_summaries as service_patch_preview_summaries
from services.nova_patching import patch_status_payload as service_patch_status_payload
from services.nova_patching import overlay_change_candidates as service_overlay_change_candidates
from services.nova_patching import snapshot_should_skip_relpath as service_snapshot_should_skip_relpath
from services.nova_pulse import build_pulse_payload as service_build_pulse_payload
from services.nova_reflection_health import maybe_log_self_reflection as service_maybe_log_self_reflection
from services.nova_search_endpoint import is_local_search_endpoint as service_is_local_search_endpoint
from services.nova_search_endpoint import normalize_search_endpoint as service_normalize_search_endpoint
from services.nova_search_endpoint import probe_search_endpoint as service_probe_search_endpoint
from services.nova_search_endpoint import search_endpoint_candidates as service_search_endpoint_candidates
from services.nova_ollama_chat import ollama_chat as service_ollama_chat
from services.ollama_health import build_ollama_health_payload as service_build_ollama_health_payload
from services.nova_update_now import build_update_now_token as service_build_update_now_token
from services.nova_update_now import clear_update_now_pending as service_clear_update_now_pending
from services.nova_update_now import read_update_now_pending as service_read_update_now_pending
from services.nova_update_now import tool_update_now as service_tool_update_now
from services.nova_update_now import tool_update_now_cancel as service_tool_update_now_cancel
from services.nova_update_now import tool_update_now_confirm as service_tool_update_now_confirm
from services.nova_update_now import update_now_pending_payload as service_update_now_pending_payload
from services.nova_update_now import write_update_now_pending as service_write_update_now_pending
from services.nova_web_tools import _clean_html_text as service_clean_html_text
from services.nova_web_tools import _provider_request_headers as service_provider_request_headers
from services.nova_web_tools import crawl_domain_for_query as service_crawl_domain_for_query
from services.nova_web_tools import decode_search_href as service_decode_search_href
from services.nova_web_tools import expand_research_terms as service_expand_research_terms
from services.nova_web_tools import extract_same_host_links as service_extract_same_host_links
from services.nova_web_tools import extract_text_from_html_content as service_extract_text_from_html_content
from services.nova_web_tools import extract_text_from_path as service_extract_text_from_path
from services.nova_web_tools import extract_urls as service_extract_urls
from services.nova_web_tools import score_research_hit as service_score_research_hit
from services.nova_web_tools import seed_urls_for_domain as service_seed_urls_for_domain
from services.nova_web_tools import tool_stackexchange_search as service_tool_stackexchange_search
from services.nova_web_tools import tool_web_fetch as service_tool_web_fetch
from services.nova_web_tools import tool_web_gather as service_tool_web_gather
from services.nova_web_tools import tool_search as service_tool_search
from services.nova_web_tools import tool_web_research as service_tool_web_research
from services.nova_web_tools import tool_web_search as service_tool_web_search
from services.nova_web_tools import tool_wikipedia_lookup as service_tool_wikipedia_lookup
from services.nova_web_tools import web_search as service_web_search
from services.nova_cli_loop import run_loop as service_run_loop
from services.memory_bootstrap_judgment import build_memory_bootstrap_judgment as service_build_memory_bootstrap_judgment
from services.memory_bootstrap_judgment import render_memory_bootstrap_judgment as service_render_memory_bootstrap_judgment
from services.memory_bootstrap_origin import confirm_origin_contract as service_confirm_origin_contract
from services.memory_bootstrap_origin import load_origin_contract as service_load_origin_contract
from services.memory_identity_bootstrap import apply_identity_bootstrap as service_apply_identity_bootstrap
from services.memory_identity_bootstrap import render_identity_bootstrap_result as service_render_identity_bootstrap_result
from services.subconscious_review_judgment import build_subconscious_review_judgment as service_build_subconscious_review_judgment
from services.subconscious_review_judgment import render_subconscious_review_judgment as service_render_subconscious_review_judgment
from services.release_promotion_judgment import build_release_promotion_judgment as service_build_release_promotion_judgment
from services.release_promotion_judgment import render_release_promotion_judgment as service_render_release_promotion_judgment
from services.source_root_judgment import build_source_root_judgment as service_build_source_root_judgment
from services.source_root_judgment import publish_source_root_operator_notice as service_publish_source_root_operator_notice
from services.source_root_judgment import render_source_root_judgment as service_render_source_root_judgment
from services.release_validation import record_release_validation_outcome as service_record_release_validation_outcome
from services.release_validation import render_release_outcome_recording as service_render_release_outcome_recording
from services.release_validation import render_release_validation_report as service_render_release_validation_report
from services.release_validation import run_release_validation as service_run_release_validation
from services.installer_validation import render_installer_validation_report as service_render_installer_validation_report
from services.installer_validation import run_installer_validation as service_run_installer_validation
from services.nova_memory_events import append_memory_event as service_append_memory_event
from services.nova_memory_events import record_memory_event as service_record_memory_event
from services.nova_memory_learning import mem_add as service_mem_add
from services.nova_patching import patch_apply as service_patch_apply
from services.data_pipeline_registry import get_pipeline_schema_probe as service_get_pipeline_schema_probe
from services.data_pipeline_registry import get_pipeline_status as service_get_pipeline_status
from services.data_pipeline_registry import list_pipeline_summaries as service_list_pipeline_summaries
from services.data_pipeline_registry import plan_pipeline_report as service_plan_pipeline_report
from services.data_pipeline_registry import preview_pipeline_query as service_preview_pipeline_query
from services.data_pipeline_registry import search_pipeline_vendor_dictionary as service_search_pipeline_vendor_dictionary
from services.pipeline_privileged_bridge import run_privileged_pipeline_query as service_run_privileged_pipeline_query
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
from services.nova_runtime_context import MEMORY_BOOTSTRAP_ORIGIN_FILE
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
from services.nova_runtime_context import runtime_scope_name
from services.nova_runtime_context import set_active_user
from services.nova_voice_runtime import SubprocessTTS as ServiceSubprocessTTS
from services.nova_voice_runtime import ensure_voice_deps as service_ensure_voice_deps
from services.nova_voice_runtime import record_seconds as service_record_seconds
from services.nova_voice_runtime import speak_chunked as service_speak_chunked
from services.nova_voice_runtime import transcribe as service_transcribe
from services.nova_voice_runtime import voice_status_payload as service_voice_status_payload
from services.generated_work_queue_snapshot import generated_work_queue_payload as service_generated_work_queue_payload
from services.nova_vision_runtime import vision_status_payload as service_vision_status_payload
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
    return service_ensure_voice_deps(globals())


voice_status_payload = lambda: service_voice_status_payload(globals())

vision_status_payload = lambda *, policy=None, ollama_health=None: service_vision_status_payload(
    policy=policy if isinstance(policy, dict) else load_policy(),
    ollama_health=ollama_health if isinstance(ollama_health, dict) else ollama_health_payload(),
)


def record_seconds(seconds: int = 3):
    return service_record_seconds(
        seconds,
        ensure_voice_deps_fn=_ensure_voice_deps,
        runtime_scope=globals(),
        sample_rate=SAMPLE_RATE,
        channels=CHANNELS,
        preferred_input_device=VOICE_INPUT_DEVICE,
    )


def transcribe(model, audio_int16) -> str:
    return service_transcribe(
        model,
        audio_int16,
        ensure_voice_deps_fn=_ensure_voice_deps,
        runtime_scope=globals(),
        sample_rate=SAMPLE_RATE,
    )

import sys


# =========================
# Config / Policy
# =========================
OLLAMA_BASE = "http://127.0.0.1:11434"

SAMPLE_RATE = 16000
CHANNELS = 1
VOICE_INPUT_DEVICE = str(os.environ.get("NOVA_VOICE_INPUT_DEVICE", "auto") or "auto").strip()

# UX tuning
RECORD_SECONDS = int(os.environ.get("NOVA_VOICE_MAX_SECONDS", "10") or 10)
OLLAMA_BOOT_RETRIES = 15
OLLAMA_REQ_TIMEOUT = 1800
OLLAMA_WARM_TIMEOUT = 45.0

# Knowledge packs (B-mode)
KNOWLEDGE_ROOT = BASE_DIR / "knowledge"
PACKS_DIR = KNOWLEDGE_ROOT / "packs"
ACTIVE_PACK_FILE = KNOWLEDGE_ROOT / "active_pack.txt"
KB_MAX_FILES = 3
KB_MAX_CHARS = 2000
CHAT_CONTEXT_TURNS = 6

# Web cache folder
WEB_CACHE_DIR = KNOWLEDGE_ROOT / "web"
DATA_SOURCES_ROOT = BASE_DIR / "data_sources"

# Self patching
UPDATES_DIR = RUNTIME_DIR / "updates" if runtime_scope_name() == "validation" else BASE_DIR / "updates"
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
    )
    return service

TURN_SUPERVISOR = Supervisor()


def _identity_memory_text_allowed(kind: str, text: str) -> bool:
    return _identity_memory_service().is_identity_memory_text_allowed(kind, text)


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
    semantic_observation: Optional[dict] = None,
) -> dict:
    return evaluate_fulfillment_route_viability(
        user_text,
        session,
        recent_turns,
        pending_action=pending_action,
        get_fulfillment_state_fn=SessionStateService.get_fulfillment_state,
        semantic_observation=semantic_observation,
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
    semantic_observation: Optional[dict] = None,
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
        semantic_observation=semantic_observation,
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


def action_ledger_add_step(
    record: Optional[dict],
    stage: str,
    outcome: str,
    detail: str = "",
    **data,
) -> None:
    return service_action_ledger_add_step(record, stage, outcome, detail, **data)



def action_ledger_route_summary(record_or_trace: Optional[object]) -> str:
    return service_action_ledger_route_summary(record_or_trace)


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
    return service_recent_action_ledger_records(ACTION_LEDGER_DIR, limit=limit)






def _detect_repeated_tool_intent_without_execution(records: Optional[list[dict]] = None, limit: int = 20) -> dict:
    return service_detect_repeated_tool_intent_without_execution(
        ACTION_LEDGER_DIR,
        records=records,
        limit=limit,
        tool_intent_labels=TOOL_INTENT_LABELS,
    )


def _top_repeated_correction_class(records: Optional[list[dict]] = None, limit: int = 20) -> dict:
    return service_top_repeated_correction_class(ACTION_LEDGER_DIR, records=records, limit=limit)


def _count_routing_overrides_recently(records: Optional[list[dict]] = None, limit: int = 20) -> int:
    return service_count_routing_overrides_recently(ACTION_LEDGER_DIR, records=records, limit=limit)






def _record_used_routing_override(record: Optional[dict]) -> bool:
    return service_record_used_routing_override(record)


def _routing_stable_recently(records: Optional[list[dict]] = None, limit: int = 20) -> bool:
    return service_routing_stable_recently(
        ACTION_LEDGER_DIR,
        records=records,
        limit=limit,
        tool_intent_labels=TOOL_INTENT_LABELS,
    )


def _sample_intents_last(records: Optional[list[dict]] = None, count: int = 5) -> list[str]:
    return service_sample_intents_last(ACTION_LEDGER_DIR, records=records, count=count)


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


def _intent_trace_preview(text: str, *, limit: int = 120) -> str:
    compact = re.sub(r"\s+", " ", str(text or "").strip())
    if len(compact) <= limit:
        return compact
    return compact[: max(0, limit - 3)] + "..."


def _supervisor_result_has_route(rule_result: Optional[dict]) -> bool:
    payload = rule_result if isinstance(rule_result, dict) else {}
    return bool(payload.get("handled")) or bool(str(payload.get("action") or "").strip())


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


_ROUTING_INTENT_PROMPT = ""


_llm_classify_routing_intent = lambda text, turns=None, pending_action=None, return_none_payload=False: service_llm_classify_routing_intent(
    text,
    turns,
    pending_action=pending_action,
    return_none_payload=return_none_payload,
    live_ollama_calls_allowed_fn=_live_ollama_calls_allowed,
    chat_model_fn=chat_model,
    routing_model_fn=routing_model,
    ollama_base=OLLAMA_BASE,
    get_saved_location_text_fn=get_saved_location_text,
    requests_post_fn=requests.post,
)


classify_turn_intent = lambda text, turns=None: service_classify_turn_intent(
    text,
    turns,
    live_ollama_calls_allowed_fn=_live_ollama_calls_allowed,
    chat_model_fn=chat_model,
    ollama_base=OLLAMA_BASE,
    requests_post_fn=requests.post,
)


select_response_strategy = lambda intent, *, tool_data_available=False, data_confirms_claim=None: service_select_response_strategy(
    intent,
    tool_data_available=tool_data_available,
    data_confirms_claim=data_confirms_claim,
)


def record_intent_outcome(
    text: str,
    intent: dict,
    strategy: dict,
    *,
    outcome: str = "completed",
) -> None:
    try:
        _ingest_signal_fn = _WorkTreeSignalIngestionService().ingest_signal
    except Exception:
        _ingest_signal_fn = None
    service_record_intent_outcome(
        text,
        intent,
        strategy,
        outcome=outcome,
        mem_add_fn=mem_add if mem_enabled() else None,
        ingest_signal_fn=_ingest_signal_fn,
    )


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


def start_action_ledger_record(
    user_input: str,
    *,
    channel: str = "cli",
    session_id: str = "",
    input_source: str = "typed",
    active_subject: str = "",
) -> dict:
    return service_start_action_ledger_record(
        user_input,
        channel=channel,
        session_id=session_id,
        input_source=input_source,
        active_subject=active_subject,
        action_ledger_add_step_fn=action_ledger_add_step,
    )


def write_action_ledger_record(record: dict) -> Optional[Path]:
    return service_write_action_ledger_record(record, action_ledger_dir=ACTION_LEDGER_DIR)




def _append_memory_event(payload: dict) -> None:
    return service_append_memory_event(payload, memory_events_log=MEMORY_EVENTS_LOG)




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
    return service_record_memory_event(
        action,
        status,
        user=user,
        scope=scope,
        backend=backend,
        kind=kind,
        source=source,
        query=query,
        reason=reason,
        error=error,
        result_count=result_count,
        duration_ms=duration_ms,
        lane=lane,
        mode=mode,
        append_memory_event_fn=_append_memory_event,
    )


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
    return service_finalize_action_ledger_record_from_runtime(
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
        runtime_scope=globals(),
    )



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


def preview_is_approved(path_or_name: str) -> bool:
    previews = UPDATES_DIR / "previews"
    candidate = Path(path_or_name)
    if not candidate.is_absolute():
        candidate = previews / path_or_name
    try:
        resolved = str(candidate.resolve())
    except Exception:
        resolved = str(candidate)
    for item in _read_approvals():
        if str(item.get("decision") or "").strip().lower() != "approved":
            continue
        recorded = str(item.get("preview") or "").strip()
        if not recorded:
            continue
        if recorded == resolved or recorded == str(candidate) or recorded == candidate.name:
            return True
        try:
            if str(Path(recorded).resolve()) == resolved:
                return True
        except Exception:
            continue
    return False


def execute_patch_action(action: str, value: str = "", *, force: bool = False, is_admin: bool = False) -> str:
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
    return service_web_allowlist_message(context, policy_web_fn=policy_web)


def _weather_source_host() -> Optional[str]:
    return service_weather_source_host(policy_web_fn=policy_web)


def _weather_unavailable_message() -> str:
    return service_weather_unavailable_message()


def weather_response_style() -> str:
    return service_weather_response_style(policy_web_fn=policy_web)


def _format_weather_output(label: str, summary: str) -> str:
    return service_format_weather_output(label, summary, weather_response_style_fn=weather_response_style)


DEVICE_LOCATION_MAX_AGE_SEC = 300.0


def _runtime_device_backend_provider() -> dict:
    return service_runtime_device_backend_provider()


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
    return service_runtime_device_location_payload(
        device_location_file=DEVICE_LOCATION_FILE,
        max_age_sec=max_age_sec,
        device_location_status_payload_fn=_device_location_status_payload,
        runtime_device_backend_provider_fn=_runtime_device_backend_provider,
    )


def set_runtime_device_location(payload: dict) -> tuple[bool, str, dict]:
    return service_set_runtime_device_location(
        payload,
        device_location_file=DEVICE_LOCATION_FILE,
        atomic_write_json_fn=atomic_write_json,
        runtime_device_location_payload_fn=runtime_device_location_payload,
    )


def clear_runtime_device_location() -> dict:
    return service_clear_runtime_device_location(
        device_location_file=DEVICE_LOCATION_FILE,
        runtime_device_location_payload_fn=runtime_device_location_payload,
    )






def _resolve_windows_device_coords(timeout_sec: float = 8.0) -> Optional[dict]:
    return service_resolve_windows_device_coords(
        timeout_sec,
        runtime_device_backend_provider_fn=_runtime_device_backend_provider,
    )


def resolve_current_device_coords(*, max_age_sec: float = DEVICE_LOCATION_MAX_AGE_SEC) -> Optional[tuple[float, float]]:
    return service_resolve_current_device_coords(
        max_age_sec=max_age_sec,
        runtime_device_location_payload_fn=runtime_device_location_payload,
        resolve_windows_device_coords_fn=_resolve_windows_device_coords,
        set_runtime_device_location_fn=set_runtime_device_location,
    )




BROWNSVILLE_LAT = 25.9017
BROWNSVILLE_LON = -97.4975
_LOCATION_HINT_COORDS = {
    "78521": (BROWNSVILLE_LAT, BROWNSVILLE_LON),
}
_LOCATION_HINT_LABELS = {
    "78521": "Brownsville, TX",
}


_parse_lat_lon = service_parse_lat_lon


def _coords_for_location_hint(location: str) -> Optional[tuple[float, float]]:
    return service_coords_for_location_hint(location)


def _coords_from_saved_location() -> Optional[tuple[float, float]]:
    return service_coords_from_saved_location(
        read_core_state_fn=read_core_state,
        default_statefile=DEFAULT_STATEFILE,
    )


def get_saved_location_text() -> str:
    return service_get_saved_location_text(
        read_core_state_fn=read_core_state,
        default_statefile=DEFAULT_STATEFILE,
    )


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




def _normalize_turn_text(text: str) -> str:
    normalized = str(text or "").lower()
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def _provider_name_from_tool(tool_name: str) -> str:
    normalized = str(tool_name or "").strip().lower()
    if normalized.startswith("web_"):
        return normalized.replace("_", " ")
    return normalized


def _load_generated_queue_payload(limit: int = 12) -> dict:
    try:
        payload = service_generated_work_queue_payload(int(limit or 12), base_dir=BASE_DIR, runtime_dir=RUNTIME_DIR)
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def set_location_coords(value: str) -> str:
    return service_set_location_coords(value, set_core_state_fn=set_core_state, default_statefile=DEFAULT_STATEFILE)


def get_weather_for_location(lat: float, lon: float) -> str:
    return service_get_weather_for_location(lat, lon)


def _need_confirmed_location_message() -> str:
    return service_need_confirmed_location_message()


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
    return m.get("chat", "llama3.2:3b")


def routing_model() -> str:
    """Return the model for intent/routing classification.
    Falls back to chat_model() if no dedicated routing model is configured."""
    m = policy_models()
    return m.get("routing", chat_model())


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
# Voice runtime compatibility
# =========================
class SubprocessTTS(ServiceSubprocessTTS):
    def __init__(self, python_exe: str, oneshot_script: Path, timeout_sec: float = 25.0):
        super().__init__(python_exe, oneshot_script, timeout_sec, warn_fn=warn)






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


def _memory_kind_store_allowed(kind: str) -> tuple[bool, str]:
    return _memory_adapter_service().memory_kind_store_allowed(kind)


def _mem_recall_exclude_kinds() -> list[str]:
    return _memory_adapter_service().mem_recall_exclude_kinds()


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


def memory_health_payload(update_snapshot: bool = True) -> dict:
    db_path = Path(getattr(memory_mod, "DB_PATH", BASE_DIR / "nova_memory.sqlite")) if memory_mod is not None else BASE_DIR / "nova_memory.sqlite"
    return service_build_memory_health_payload(
        memory_db_path=db_path,
        learned_facts_file=LEARNED_FACTS_FILE,
        identity_file=IDENTITY_FILE,
        bootstrap_origin_file=MEMORY_BOOTSTRAP_ORIGIN_FILE,
        memory_events_log=MEMORY_EVENTS_LOG,
        snapshot_file=RUNTIME_DIR / "memory_health_snapshot.json",
        update_snapshot=update_snapshot,
        memory_enabled=mem_enabled(),
        memory_retention_policy=_memory_adapter_service().mem_retention_policy(),
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
        memory_kind_store_allowed_fn=_memory_kind_store_allowed,
        memory_write_user_fn=_memory_write_user,
        memory_mod=memory_mod,
        mem_min_score_fn=mem_min_score,
        python_path=str(PYTHON),
        base_dir=BASE_DIR,
    )



def mem_recall(
    query: str,
    *,
    purpose: str = "",
    conversation_state: dict | None = None,
    pending_action: dict | None = None,
) -> str:
    effective_purpose = str(purpose or "general").strip() or "general"
    return service_mem_recall(
        query,
        mem_enabled_fn=mem_enabled,
        memory_recall_plan_fn=build_memory_recall_plan,
        memory_runtime_user_fn=_memory_runtime_user,
        memory_mod=memory_mod,
        mem_context_top_k_fn=mem_context_top_k,
        mem_min_score_fn=mem_min_score,
        mem_exclude_sources_fn=mem_exclude_sources,
        mem_recall_exclude_kinds_fn=_mem_recall_exclude_kinds,
        mem_scope_fn=mem_scope,
        format_memory_recall_hits_fn=_format_memory_recall_hits,
        record_memory_event_fn=_record_memory_event,
        python_path=str(PYTHON),
        base_dir=BASE_DIR,
        purpose=effective_purpose,
        conversation_state=conversation_state,
        pending_action=pending_action,
    )


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


def apply_user_memory_learning(
    text: str,
    *,
    input_source: str = "typed",
    session=None,
    turns: list[tuple[str, str]] | None = None,
    pending_action: dict | None = None,
) -> dict:
    last_assistant = ""
    for role, content in reversed(list(turns or [])):
        if str(role or "").strip().lower() == "assistant":
            last_assistant = str(content or "")
            break
    pending_correction_target = ""
    conversation_state = None
    clear_pending_correction_target_fn = None
    if session is not None:
        pending_correction_target = str(getattr(session, "pending_correction_target", "") or "").strip()
        conversation_state = getattr(session, "conversation_state", None)
        if isinstance(conversation_state, dict):
            conversation_state = dict(conversation_state)
        if hasattr(session, "clear_pending_correction_target"):
            clear_pending_correction_target_fn = session.clear_pending_correction_target
    return service_apply_user_memory_learning(
        text,
        input_source=str(input_source or "typed").strip() or "typed",
        conversation_state=conversation_state,
        pending_correction_target=pending_correction_target,
        last_assistant=last_assistant,
        mem_enabled_fn=mem_enabled,
        mem_add_fn=mem_add,
        mem_remember_fact_fn=mem_remember_fact,
        load_learned_facts_fn=load_learned_facts,
        save_learned_facts_fn=save_learned_facts,
        get_learned_fact_fn=get_learned_fact,
        set_active_user_fn=set_active_user,
        get_active_user_fn=get_active_user,
        load_identity_profile_fn=load_identity_profile,
        save_identity_profile_fn=save_identity_profile,
        store_correction_record_fn=_store_supervisor_correction_record,
        clear_pending_correction_target_fn=clear_pending_correction_target_fn,
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
        memory_read_plan_fn=build_memory_read_plan,
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


mem_audit = lambda query: service_mem_audit(
    query,
    memory_runtime_user_fn=_memory_runtime_user,
    memory_mod=memory_mod,
    mem_context_top_k_fn=mem_context_top_k,
    mem_min_score_fn=mem_min_score,
    mem_exclude_sources_fn=mem_exclude_sources,
    mem_recall_exclude_kinds_fn=_mem_recall_exclude_kinds,
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
        data, source = service_load_json_dict_with_tmp_fallback(IDENTITY_FILE)
        if source == "tmp" and data:
            save_identity_profile(data)
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
        data, source = service_load_json_dict_with_tmp_fallback(LEARNED_FACTS_FILE)
        if not isinstance(data, dict):
            return {}
        sanitized = _sanitize_learned_facts(data)
        if sanitized != data or source == "tmp":
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


def get_learned_fact(key: str, default: str = "") -> str:
    data = load_learned_facts()
    v = str(data.get(key) or "").strip()
    return v or default


def build_learning_context_details(
    query: str,
    *,
    conversation_state: dict | None = None,
    pending_action: dict | None = None,
) -> dict:
    return service_build_learning_context_details(
        query,
        conversation_state=conversation_state,
        pending_action=pending_action,
        identity_context_for_prompt_fn=service_identity_context_for_prompt,
        operational_identity_context_for_prompt_fn=service_operational_identity_context_for_prompt,
        load_identity_profile_fn=load_identity_profile,
        load_learned_facts_fn=load_learned_facts,
        load_capabilities_fn=load_capabilities,
        kb_search_fn=kb_search,
        memory_recall_plan_fn=build_memory_recall_plan,
        mem_get_recent_learned_fn=mem_get_recent_learned,
        mem_recall_fn=mem_recall,
    )


def build_learning_context(query: str) -> str:
    return str(build_learning_context_details(query).get("context") or "")




def _render_session_state_context(
    *,
    conversation_state: dict | None = None,
    pending_action: dict | None = None,
    max_chars: int = 1600,
) -> str:
    return service_render_session_state_context(
        conversation_state=conversation_state,
        pending_action=pending_action,
        max_chars=max_chars,
    )


def build_fallback_context_details(
    query: str,
    turns: list[tuple[str, str]] | None = None,
    *,
    conversation_state: dict | None = None,
    pending_action: dict | None = None,
    include_state_context: bool = True,
    include_chat_context: bool = True,
) -> dict[str, Any]:
    return service_build_fallback_context_details(
        query,
        turns,
        conversation_state=conversation_state,
        pending_action=pending_action,
        include_state_context=include_state_context,
        include_chat_context=include_chat_context,
        build_learning_context_details_fn=build_learning_context_details,
        chat_context_turns=CHAT_CONTEXT_TURNS,
    )


def _extract_urls(text: str) -> list[str]:
    return service_extract_urls(text)


def _strip_invocation_prefix(text: str) -> str:
    return service_strip_invocation_prefix(text)


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


def get_server_side_settings() -> dict:
    return _policy_manager().get_server_side()


def set_server_side_settings(
    *,
    mode: str = "",
    frontdoor: str = "",
    frontdoor_base_url: str | None = None,
    docker_enabled: bool | None = None,
) -> str:
    return _policy_manager().set_server_side_settings(
        mode=mode,
        frontdoor=frontdoor,
        frontdoor_base_url=frontdoor_base_url,
        docker_enabled=docker_enabled,
        user=get_active_user(),
    )


def set_mission_settings(
    *,
    enabled: bool | None = None,
    mode: str = "",
    objective: str = "",
    release_stale_ready_is_pressure: bool | None = None,
    subconscious_triage_is_pressure: bool | None = None,
    generated_queue_backlog_is_pressure: bool | None = None,
) -> str:
    return _policy_manager().set_mission_settings(
        enabled=enabled,
        mode=mode,
        objective=objective,
        release_stale_ready_is_pressure=release_stale_ready_is_pressure,
        subconscious_triage_is_pressure=subconscious_triage_is_pressure,
        generated_queue_backlog_is_pressure=generated_queue_backlog_is_pressure,
        user=get_active_user(),
    )


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








def probe_search_endpoint(
    endpoint: str = "",
    *,
    timeout: float = 2.5,
    persist_repair: bool = False,
    candidate_limit: int | None = None,
) -> dict:
    return service_probe_search_endpoint(
        endpoint,
        timeout=timeout,
        persist_repair=persist_repair,
        candidate_limit=candidate_limit,
        get_search_endpoint_fn=get_search_endpoint,
        auto_repair_search_endpoint_fn=auto_repair_search_endpoint,
        requests_get_fn=requests.get,
    )



def toggle_search_provider() -> str:
    current = get_search_provider()
    target = "searxng" if current == "html" else "html"
    return set_search_provider(target)


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
    test_runner = str(os.environ.get("NOVA_TEST_RUNNER") or "").strip().lower() in {"1", "true", "yes", "on"}
    argv_low = argv_text.lower()
    pytest_active = "pytest" in argv_low or bool(os.environ.get("PYTEST_CURRENT_TEST"))
    if "unittest" not in argv_low and not pytest_active and not test_runner:
        return True
    return str(os.environ.get("NOVA_ALLOW_LIVE_OLLAMA_TESTS") or "").strip().lower() in {"1", "true", "yes", "on"}


def ollama_api_up(timeout=2.0) -> bool:
    return bool(ollama_health_payload(timeout=timeout).get("ok"))


def ollama_server_up(timeout=2.0) -> bool:
    return bool(ollama_health_payload(timeout=timeout).get("server_ok"))


def ollama_health_payload(timeout=2.0) -> dict:
    if not _live_ollama_calls_allowed():
        return service_build_ollama_health_payload(
            requests_get_fn=requests.get,
            requests_post_fn=requests.post,
            ollama_base=OLLAMA_BASE,
            chat_model=chat_model(),
            timeout=timeout,
            live_calls_allowed=False,
        )
    return service_build_ollama_health_payload(
        requests_get_fn=requests.get,
        requests_post_fn=requests.post,
        ollama_base=OLLAMA_BASE,
        chat_model=chat_model(),
        timeout=timeout,
        live_calls_allowed=True,
    )


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
        warn("Ollama not listening on 11434. Leaving startup to operator or explicit repair.")
        return False

    if tcp_listening() and not ollama_server_up():
        warn("Ollama port open but API not responding. Leaving process untouched for status/work-tree diagnosis.")

    for _ in range(OLLAMA_BOOT_RETRIES):
        if ollama_server_up():
            ok("Ollama API up")
            return True
        time.sleep(1)

    bad("Ollama API still down.")
    return False


def warm_ollama_chat_model(reason: str = "startup") -> bool:
    if not _live_ollama_calls_allowed():
        return False
    if not ollama_server_up():
        return False

    model = str(chat_model() or "").strip()
    if not model:
        return False

    payload = {
        "model": model,
        "stream": False,
        "keep_alive": "10m",
        "options": {"temperature": 0.0, "num_predict": 1},
        "messages": [
            {"role": "system", "content": "Warm the configured runtime model for the next routed chat turn."},
            {"role": "user", "content": str(reason or "startup")[:120]},
        ],
    }
    try:
        response = requests.post(f"{OLLAMA_BASE}/api/chat", json=payload, timeout=OLLAMA_WARM_TIMEOUT)
        response.raise_for_status()
        ok(f"Ollama chat model warm: {model}")
        return True
    except Exception as exc:
        warn(f"Ollama chat model warm failed: {str(exc)[:180]}")
        return False


def warm_ollama_routing_model(reason: str = "startup") -> bool:
    """Pre-load the routing model (Qwen) so the first user turn does not hit a cold-start timeout."""
    if not _live_ollama_calls_allowed():
        return False
    if not ollama_server_up():
        return False

    model = str(routing_model() or "").strip()
    if not model or model == str(chat_model() or "").strip():
        return False  # routing model is same as chat model; already warmed

    payload = {
        "model": model,
        "stream": False,
        "keep_alive": "10m",
        "options": {"temperature": 0.0, "num_predict": 1},
        "messages": [
            {"role": "system", "content": "Warm the routing model for the next intent classification turn."},
            {"role": "user", "content": str(reason or "startup")[:120]},
        ],
    }
    try:
        response = requests.post(f"{OLLAMA_BASE}/api/chat", json=payload, timeout=OLLAMA_WARM_TIMEOUT)
        response.raise_for_status()
        ok(f"Ollama routing model warm: {model}")
        return True
    except Exception as exc:
        warn(f"Ollama routing model warm failed: {str(exc)[:180]}")
        return False

def maybe_run_fulfillment_flow(
    text: str,
    session,
    turns,
    *,
    pending_action=None,
    semantic_observation: Optional[dict] = None,
) -> Optional[dict]:
    """Attempt to handle the turn through the fulfillment flow.
    Returns a result dict with reply/planner_decision/grounded, or None if not applicable."""
    try:
        return _fulfillment_flow_service().maybe_run_fulfillment_flow(
            text,
            session,
            turns,
            pending_action=pending_action,
            semantic_observation=semantic_observation,
        )
    except Exception as exc:
        error_text = str(exc)[:180]
        behavior_set_flag("fulfillment_flow_error", layer="fulfillment_flow", error=error_text)
        warn(f"Fulfillment flow failed: {error_text}")
        return None


def ensure_ollama():
    if not _live_ollama_calls_allowed():
        return False
    if not tcp_listening():
        return False
    if tcp_listening() and not ollama_server_up():
        return False
    for _ in range(10):
        if ollama_server_up():
            return True
        time.sleep(0.5)
    return False


# =========================
# Knowledge packs (B-mode)
# =========================
def _tokenize(q: str):
    q = (q or "").lower()
    toks = re.findall(r"[a-z0-9]{3,}", q)
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
        s = re.sub(r"\s+", " ", (raw or "").strip().lstrip("-*â€¢")).strip()
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
        s = re.sub(r"\s+", " ", (raw or "").strip().lstrip("-*â€¢")).strip()
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


_build_local_topic_digest_answer = lambda query_text, max_files=4, max_points=10: service_build_local_topic_digest_answer(
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


def _is_broad_data_query(text: str) -> bool:
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
    with zipfile.ZipFile(snap, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for p in BASE_DIR.rglob("*"):
            if p.is_dir():
                continue
            rel = p.relative_to(BASE_DIR)
            if service_snapshot_should_skip_relpath(rel):
                continue
            z.write(p, arcname=str(rel))
    _write_snapshot_meta(snap, _read_patch_revision())
    _log_patch(f"SNAPSHOT {snap.name}")
    return snap


def _overlay_zip(zip_path: Path) -> int:
    count = 0
    for name, payload in service_overlay_change_candidates(
        zip_path,
        base_dir=BASE_DIR,
        patch_manifest_name=PATCH_MANIFEST_NAME,
    ):
        out = BASE_DIR / name
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(payload)
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
    return service_patch_rollback(
        snapshot_zip,
        base_dir=BASE_DIR,
        snapshots_dir=SNAPSHOTS_DIR,
        log_patch_fn=_log_patch,
        read_snapshot_meta_fn=_read_snapshot_meta,
        write_patch_revision_fn=lambda revision, source: _write_patch_revision(revision, source=source),
        py_compile_check_fn=_py_compile_check,
    )


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


def _clamp_language_mix(value: Any) -> int:
    try:
        return max(0, min(100, int(value)))
    except Exception:
        return 0


def _estimate_spanish_ratio(text: str) -> float:
    """Estimate Spanish content from Unicode character profile only â€” no keyword lists."""
    raw = str(text or "")
    if not raw.strip():
        return 0.0
    # Spanish-specific characters not naturally present in standard English text.
    # Using character-level evidence avoids keyword-trigger brittleness.
    spanish_chars = set("Ã¡Ã©Ã­Ã³ÃºÃ¼Ã±ÃÃ‰ÃÃ“ÃšÃœÃ‘Â¿Â¡")
    letter_count = sum(1 for c in raw if c.isalpha())
    if letter_count == 0:
        return 0.0
    accent_count = sum(1 for c in raw if c in spanish_chars)
    # Accented chars are a strong signal; scale so ~12% accent ratio â†’ 1.0
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
def ollama_chat(text: str, retrieved_context: str = "", language_mix_spanish_pct: int = 0, reply_form: str = "") -> str:
    return service_ollama_chat(
        text,
        retrieved_context=retrieved_context,
        language_mix_spanish_pct=language_mix_spanish_pct,
        reply_form=reply_form,
        live_ollama_calls_allowed_fn=_live_ollama_calls_allowed,
        ensure_ollama_fn=ensure_ollama,
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
    """Store a teach example in the local examples file for overrides and patch proposals."""
    try:
        user = user or get_active_user() or ""
        ex = {"orig": original, "corr": correction, "user": user, "ts": int(time.time())}

        teach_dir = UPDATES_DIR / "teaching"
        teach_dir.mkdir(parents=True, exist_ok=True)
        fn = teach_dir / "examples.jsonl"
        with open(fn, "a", encoding="utf-8") as f:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")
        return "OK"
    except Exception as e:
        return f"Failed to store teach example: {e}"


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


_teach_propose_patch = lambda description: service_teach_propose_patch(
    description,
    updates_dir=UPDATES_DIR,
    read_patch_revision_fn=_read_patch_revision,
    patch_manifest_name=PATCH_MANIFEST_NAME,
    patch_preview_fn=patch_preview,
    interactive_patch_review_enabled_fn=_interactive_patch_review_enabled,
    interactive_preview_review_fn=interactive_preview_review,
)


_teach_autoapply_proposal = lambda zip_path, apply_live=False: service_teach_autoapply_proposal(
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




def speak_chunked(tts, text: str, max_len: int = 220):
    return service_speak_chunked(tts, text, max_len=max_len)


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


def tool_os_capability(request: str = "", capability: str = "", args: Optional[dict] = None):
    from services.os_capability_operator_outbox import publish_os_capability_notice
    from services.os_script_controller import OS_SCRIPT_CONTROLLER_SERVICE
    from services.nova_runtime_context import OPERATOR_OUTBOX_FILE
    from services.operator_outbox import OPERATOR_OUTBOX_SERVICE

    capability_name = str(capability or "").strip()
    capability_args = dict(args or {}) if isinstance(args, dict) else {}
    raw = str(request or "").strip()
    if raw.startswith("{"):
        try:
            parsed = json.loads(raw)
        except Exception as exc:
            return {"ok": False, "reason": "invalid_os_capability_request", "error": str(exc)}
        if isinstance(parsed, dict):
            capability_name = str(parsed.get("capability") or parsed.get("name") or capability_name).strip()
            capability_args = dict(parsed.get("args") or {}) if isinstance(parsed.get("args"), dict) else capability_args
    elif raw and not capability_name:
        capability_name = raw
    if not capability_name:
        return {"ok": False, "reason": "capability_required"}
    result = OS_SCRIPT_CONTROLLER_SERVICE.execute_capability(
        capability_name,
        capability_args,
        authority_context={
            "allowed_authority_levels": ["read_only", "read_only_expensive", "read_only_network", "evidence_write"],
            "allow_evidence_write": True,
        },
    )
    if isinstance(result, dict) and result.get("operator_outbox"):
        result = dict(result)
        result["operator_notice"] = publish_os_capability_notice(result)
    elif isinstance(result, dict) and bool(result.get("ok")) and str(result.get("status") or "") == "success":
        result = dict(result)
        result["operator_reconcile"] = OPERATOR_OUTBOX_SERVICE.reconcile_os_capability_notices(
            OPERATOR_OUTBOX_FILE,
            capability=capability_name,
            cleared_reasons={"contract_stale", "capability_evidence_not_ok"},
        )
    return result


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
        generated_work_queue_fn=_load_generated_queue_payload,
        memory_health_payload_fn=memory_health_payload,
    )


def render_nova_pulse(payload: dict | None = None) -> str:
    return service_render_nova_pulse(payload, build_pulse_payload_fn=build_pulse_payload)







def _latest_memory_health_branch() -> tuple[object | None, list[dict]]:
    try:
        import work_tree as work_tree_module

        newest = None
        for tree in work_tree_module.list_trees():
            for branch in work_tree_module.list_tree_branches(tree.tree_id):
                if str(getattr(branch, "source_type", "") or "").strip() != "memory_health":
                    continue
                if newest is None or getattr(branch, "updated_at", None) > getattr(newest, "updated_at", None):
                    newest = branch
        evidence = work_tree_module.list_branch_evidence(newest.branch_id, limit=20) if newest is not None else []
        return newest, evidence
    except Exception:
        return None, []


def _release_readiness_branch(branch_id: str = "") -> tuple[object | None, list[dict]]:
    try:
        import work_tree as work_tree_module

        branch = None
        target_id = str(branch_id or "").strip()
        if target_id:
            branch = work_tree_module.get_branch(target_id)
        if branch is None:
            newest = None
            for tree in work_tree_module.list_trees():
                for candidate in work_tree_module.list_tree_branches(tree.tree_id):
                    if str(getattr(candidate, "source_type", "") or "").strip() != "release_status":
                        continue
                    if str(getattr(candidate, "work_class", "") or "").strip() != "release_readiness_gap":
                        continue
                    if newest is None or getattr(candidate, "updated_at", None) > getattr(newest, "updated_at", None):
                        newest = candidate
            branch = newest
        evidence = work_tree_module.list_branch_evidence(branch.branch_id, limit=50) if branch is not None else []
        return branch, evidence
    except Exception:
        return None, []


def tool_memory_bootstrap_judgment():
    branch, evidence_rows = _latest_memory_health_branch()
    pulse = build_pulse_payload()
    memory_health = pulse.get("memory_health") if isinstance(pulse.get("memory_health"), dict) else {}
    branch_payload = dict(getattr(branch, "source_payload", {}) or {}) if branch is not None else {}
    judgment = service_build_memory_bootstrap_judgment(
        memory_enabled=mem_enabled(),
        memory_health=memory_health,
        identity_file=IDENTITY_FILE,
        learned_facts_file=LEARNED_FACTS_FILE,
        memory_events_log=MEMORY_EVENTS_LOG,
        branch_payload=branch_payload,
        evidence_rows=evidence_rows,
    )
    return service_render_memory_bootstrap_judgment(judgment)


def tool_memory_bootstrap_confirm(
    assistant_name: str = "",
    developer_name: str = "",
    developer_nickname: str = "",
    confirmed_by: str = "operator",
):
    values = {
        "assistant_name": str(assistant_name or "").strip(),
        "developer_name": str(developer_name or "").strip(),
        "developer_nickname": str(developer_nickname or "").strip(),
    }
    missing = [key for key, value in values.items() if not value]
    if missing:
        return (
            "Memory Bootstrap Confirm\n"
            "- status: blocked\n"
            f"- reason: missing confirmation values: {', '.join(missing)}\n"
            "- required: assistant_name, developer_name, developer_nickname"
        )
    contract = service_confirm_origin_contract(
        MEMORY_BOOTSTRAP_ORIGIN_FILE,
        values,
        confirmed_by=confirmed_by,
        evidence="operator-confirmed memory bootstrap values",
    )
    status = str(contract.get("status") or "unknown")
    authority = str(contract.get("authority") or "none")
    pending = ", ".join(str(item) for item in list(contract.get("pending_slots") or [])) or "none"
    _record_memory_event(
        "bootstrap_origin_confirm",
        "ok" if status == "ready" else "blocked",
        reason="" if status == "ready" else "pending_slots",
        result_count=len(contract.get("confirmed_slots") or []),
        lane="memory_bootstrap",
        mode=authority,
    )
    return "\n".join(
        [
            "Memory Bootstrap Confirm",
            f"- status: {status}",
            f"- authority: {authority}",
            f"- pending_slots: {pending}",
            f"- assistant_name: {values['assistant_name']}",
            f"- developer_name: {values['developer_name']}",
            f"- developer_nickname: {values['developer_nickname']}",
        ]
    )


def tool_memory_identity_bootstrap():
    origin_contract = service_load_origin_contract(MEMORY_BOOTSTRAP_ORIGIN_FILE)
    result = service_apply_identity_bootstrap(
        origin_contract=origin_contract,
        identity_file=IDENTITY_FILE,
        learned_facts_file=LEARNED_FACTS_FILE,
        load_identity_profile_fn=load_identity_profile,
        save_identity_profile_fn=save_identity_profile,
        load_learned_facts_fn=load_learned_facts,
        save_learned_facts_fn=save_learned_facts,
        mem_add_fn=mem_add,
        record_memory_event_fn=_record_memory_event,
    )
    return service_render_identity_bootstrap_result(result)


def tool_memory_hygiene(dry_run: bool = True):
    db_path = (
        Path(getattr(memory_mod, "DB_PATH", BASE_DIR / "nova_memory.sqlite"))
        if memory_mod is not None
        else BASE_DIR / "nova_memory.sqlite"
    )
    retention_policy = _memory_adapter_service().mem_retention_policy()
    result = service_apply_memory_hygiene(
        db_path,
        retention_policy=retention_policy,
        dry_run=bool(dry_run),
        audit_log_path=RUNTIME_DIR / "memory_hygiene_audit.jsonl",
    )
    _record_memory_event(
        "hygiene",
        "ok" if result.get("ok") else "error",
        lane="memory_retention",
        mode="dry_run" if bool(result.get("dry_run")) else "apply",
        result_count=int(result.get("deleted_rows", 0) or 0),
        reason=(
            f"{result.get('status') or result.get('error') or ''}; "
            f"remaining_total={int(result.get('remaining_total', 0) or 0)}"
        ).strip("; "),
    )
    return service_render_memory_hygiene_result(result)


def tool_subconscious_review_judgment(branch_id: str = ""):
    import work_tree as work_tree_module

    judgment = service_build_subconscious_review_judgment(
        branch_id=branch_id,
        work_tree_module=work_tree_module,
        probe_turn_routes_fn=_probe_turn_routes,
        session_factory=ConversationSession,
        evaluate_supervisor_rules_fn=lambda user_text, **kwargs: TURN_SUPERVISOR.evaluate_rules(user_text, **kwargs),
        supervisor_has_route_fn=_supervisor_result_has_route,
        fulfillment_viability_fn=_fulfillment_route_viability,
        supervisor_process_turn_fn=lambda **kwargs: TURN_SUPERVISOR.process_turn(**kwargs),
    )
    return service_render_subconscious_review_judgment(judgment)


def tool_source_root_judgment(branch_id: str = ""):
    import work_tree as work_tree_module

    judgment = service_build_source_root_judgment(
        branch_id=branch_id,
        work_tree_module=work_tree_module,
    )
    notice = service_publish_source_root_operator_notice(judgment)
    if isinstance(notice, dict) and bool(notice.get("published")):
        judgment["operator_notice"] = notice
    return service_render_source_root_judgment(judgment)


def tool_release_promotion_judgment(branch_id: str = ""):
    branch, evidence_rows = _release_readiness_branch(branch_id)
    release_ledger_path = RUNTIME_DIR / "exports" / "release_packages" / "release_ledger.jsonl"
    release_status = RELEASE_STATUS_SERVICE.status_payload(release_ledger_path, 8, source_root=BASE_DIR)
    branch_payload = dict(getattr(branch, "source_payload", {}) or {}) if branch is not None else {}
    judgment = service_build_release_promotion_judgment(
        release_status=release_status,
        branch_payload=branch_payload,
        evidence_rows=evidence_rows,
        branch_id=str(getattr(branch, "branch_id", "") or branch_id or ""),
    )
    return service_render_release_promotion_judgment(judgment)


def tool_release_validation_run(branch_id: str = ""):
    branch, _evidence_rows = _release_readiness_branch(branch_id)
    release_ledger_path = RUNTIME_DIR / "exports" / "release_packages" / "release_ledger.jsonl"
    release_status = RELEASE_STATUS_SERVICE.status_payload(release_ledger_path, 8, source_root=BASE_DIR)
    branch_payload = dict(getattr(branch, "source_payload", {}) or {}) if branch is not None else {}
    artifact_path = str(release_status.get("latest_artifact_path") or branch_payload.get("latest_artifact_path") or "")
    record_path = str(release_status.get("latest_validation_seed_path") or branch_payload.get("latest_validation_seed_path") or "")
    include_runtime = str(branch_payload.get("latest_validation_record_ollama_expected") or "").strip().lower() in {"yes", "true", "required"}
    report = service_run_release_validation(
        repo_root=BASE_DIR,
        artifact_path=artifact_path,
        record_path=record_path,
        artifact_version=str(release_status.get("latest_version") or branch_payload.get("latest_version") or ""),
        release_channel=str(release_status.get("latest_channel") or branch_payload.get("latest_channel") or "rc"),
        release_label=str(release_status.get("latest_label") or branch_payload.get("latest_label") or ""),
        version_source=str(branch_payload.get("version_source") or ""),
        ledger_path=str(release_status.get("ledger_path") or branch_payload.get("ledger_path") or release_ledger_path),
        include_runtime=include_runtime,
    )
    return service_render_release_validation_report(report)


def tool_release_record_validation_outcome(branch_id: str = ""):
    branch, _evidence_rows = _release_readiness_branch(branch_id)
    release_ledger_path = RUNTIME_DIR / "exports" / "release_packages" / "release_ledger.jsonl"
    release_status = RELEASE_STATUS_SERVICE.status_payload(release_ledger_path, 8, source_root=BASE_DIR)
    branch_payload = dict(getattr(branch, "source_payload", {}) or {}) if branch is not None else {}
    record_path = str(release_status.get("latest_validation_seed_path") or branch_payload.get("latest_validation_seed_path") or "")
    report = service_record_release_validation_outcome(
        repo_root=BASE_DIR,
        record_path=record_path,
        release_status=release_status,
    )
    return service_render_release_outcome_recording(report)


def tool_installer_validation_run(branch_id: str = ""):
    branch, _evidence_rows = _release_readiness_branch(branch_id)
    branch_payload = dict(getattr(branch, "source_payload", {}) or {}) if branch is not None else {}
    report = service_run_installer_validation(
        repo_root=BASE_DIR,
        package_artifact_path=str(branch_payload.get("latest_artifact_path") or ""),
    )
    return service_render_installer_validation_report(report)





def _self_report_control_status_payload() -> dict:
    url = str(os.environ.get("NOVA_SELF_REPORT_STATUS_URL") or "http://127.0.0.1:8080/api/control/status").strip()
    if not url:
        return {}
    try:
        timeout = float(os.environ.get("NOVA_SELF_REPORT_STATUS_TIMEOUT_SEC") or 5.0)
    except Exception:
        timeout = 5.0
    try:
        response = requests.get(url, timeout=max(0.2, timeout))
        if int(getattr(response, "status_code", 0) or 0) != 200:
            return {}
        payload = response.json()
        return dict(payload or {}) if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _self_report_work_trees_payload(limit: int = 32) -> dict:
    try:
        import work_tree as work_tree_module

        return CONTROL_WORK_TREES_SERVICE.payload(
            list_visual_trees_fn=work_tree_module.list_visual_trees,
            limit=limit,
        )
    except Exception as exc:
        return {
            "ok": False,
            "error": f"work_tree_payload_failed:{exc}",
            "counts": {"total": 0, "active": 0, "branches": 0, "open_tasks": 0},
            "trees": [],
        }


def _self_report_work_tree_truth(work_trees_payload: dict) -> dict:
    snapshot = build_work_tree_pressure_snapshot(work_trees_payload)
    return {
        "status": snapshot.get("status"),
        "open_task_count": snapshot.get("open_task_count"),
        "blocked_branch_count": snapshot.get("blocked_branch_count"),
        "operator_hold_branch_count": snapshot.get("operator_hold_branch_count"),
        "self_repair_blocked_branch_count": snapshot.get("self_repair_blocked_branch_count"),
        "self_repair_observing_branch_count": snapshot.get("self_repair_observing_branch_count"),
        "observing_branch_count": snapshot.get("observing_branch_count"),
    }


def _self_report_local_status_payload(work_trees_payload: dict) -> dict:
    pulse_payload = _apply_latest_regression_validation(build_pulse_payload())
    release_ledger_path = RUNTIME_DIR / "exports" / "release_packages" / "release_ledger.jsonl"
    release_status = RELEASE_STATUS_SERVICE.status_payload(release_ledger_path, 8, source_root=BASE_DIR)
    try:
        ollama_health = ollama_health_payload(timeout=1.5)
    except Exception as exc:
        ollama_health = {"ok": False, "status": "error", "info": str(exc)}
    memory_health = pulse_payload.get("memory_health") if isinstance(pulse_payload.get("memory_health"), dict) else {}
    memory_status = str(
        pulse_payload.get("memory_health_status")
        or memory_health.get("status")
        or ("ok" if pulse_payload.get("memory_ok") else "")
    )
    alerts: list[str] = []
    if not bool(ollama_health.get("ok")):
        alerts.append(f"ollama_not_ready:{ollama_health.get('status') or 'unknown'}")
    if memory_status and memory_status not in {"ok", "ready", "healthy"}:
        alerts.append(f"memory_health:{memory_status}")
    last_regression_status = str(pulse_payload.get("last_regression_status") or "").strip().upper()
    if last_regression_status.startswith("FAIL") and not bool(pulse_payload.get("last_regression_stale")):
        alerts.append(f"regression:{last_regression_status}")
    work_tree_truth = _self_report_work_tree_truth(work_trees_payload)
    return {
        "health_score": None,
        "alerts": alerts,
        "work_tree_truth_status": work_tree_truth.get("status"),
        "work_tree_open_task_count": work_tree_truth.get("open_task_count"),
        "release_status": release_status,
        "ollama_chat_ready": bool(ollama_health.get("ok")),
        "ollama_health": ollama_health,
        "memory_health": memory_health,
        "memory_health_status": memory_status,
        "memory_enabled": bool(mem_enabled()),
        "core": {"status": "running"},
        "guard": {"status": "unknown"},
        "webui": {"status": "unknown"},
    }


def _core_health_runtime_health() -> dict:
    try:
        import health as health_module

        hb_ok, hb_msg = health_module.check_heartbeat()
        st_ok, st_msg = health_module.check_state()
        ol_ok, ol_msg = health_module.check_ollama()
    except Exception as exc:
        return {
            "heartbeat": {"ok": False, "info": f"error:{exc}"},
            "core_state": {"ok": False, "info": f"error:{exc}"},
            "ollama": {"ok": False, "info": f"error:{exc}"},
        }
    return {
        "heartbeat": {"ok": bool(hb_ok), "info": str(hb_msg or "")},
        "core_state": {"ok": bool(st_ok), "info": str(st_msg or "")},
        "ollama": {"ok": bool(ol_ok), "info": str(ol_msg or "")},
    }


def _core_health_kidney_summary() -> dict:
    try:
        import kidney as kidney_module

        summary = kidney_module.run_kidney(dry_run=True)
        return dict(summary or {}) if isinstance(summary, dict) else {}
    except Exception as exc:
        return {"mode": "unknown", "candidate_count": 0, "error": str(exc)}


def _apply_latest_regression_validation(pulse_payload: dict) -> dict:
    payload = dict(pulse_payload or {})
    marker = _load_json_file(RUNTIME_DIR / "regression_status.json", {}) or {}
    if not isinstance(marker, dict):
        return payload
    marker_status = str(marker.get("status") or "").strip().upper()
    marker_date = str(marker.get("date") or "").strip()
    marker_lanes = [str(item).strip() for item in list(marker.get("lanes") or []) if str(item).strip()]
    if marker_status != "OK" or marker_date != time.strftime("%Y-%m-%d"):
        return payload
    if "unit" not in marker_lanes and "all" not in marker_lanes:
        return payload
    payload["last_regression_status"] = "OK"
    payload["last_regression_stale"] = False
    payload["last_regression_source"] = "scripts/run_regression.py"
    payload["last_regression_at"] = str(marker.get("generated_at") or "")
    return payload


def build_core_health_brief_payload() -> dict:
    try:
        import doctor as doctor_module

        preflight_checks = list(doctor_module.run_preflight() or [])
    except Exception:
        preflight_checks = []

    runtime_health = _core_health_runtime_health()
    pulse_payload = _apply_latest_regression_validation(build_pulse_payload())
    self_status = service_build_self_status_payload(
        pulse_payload=pulse_payload,
        recent_ops_events=service_read_recent_ops_events(RUNTIME_DIR / "ops_journal.jsonl", limit=60),
        repo_change_snapshot=service_build_repo_change_snapshot(BASE_DIR),
    )
    autonomy_maintenance = _load_json_file(AUTONOMY_MAINTENANCE_FILE, {}) or {}
    core_steward = service_build_core_steward_payload(
        preflight_checks=preflight_checks,
        runtime_health=runtime_health,
        pulse_payload=pulse_payload,
        autonomy_maintenance=autonomy_maintenance if isinstance(autonomy_maintenance, dict) else {},
        kidney_summary=_core_health_kidney_summary(),
    )
    core_status = "running" if bool((runtime_health.get("core_state") or {}).get("ok")) else "heartbeat_stale"
    return service_build_core_health_brief(
        core_steward=core_steward,
        self_status=self_status,
        runtime_summary={"core": {"status": core_status}},
    )


def tool_release_rebuild_verify(label: str = "work-tree-rebuild"):
    from services.governance_chain import release_rebuild_tool_payload
    from services.release_clean import run_release_clean

    safe_label = str(label or "work-tree-rebuild").strip() or "work-tree-rebuild"
    report = run_release_clean(
        root=BASE_DIR,
        label=safe_label,
        python_executable=str(PYTHON),
        run_regression=False,
        promote=False,
        timeout_sec=1800,
    )
    return release_rebuild_tool_payload(
        report if isinstance(report, dict) else {},
        label=safe_label,
        run_regression=False,
        promote=False,
    )


def _read_update_now_pending() -> dict:
    return service_read_update_now_pending(UPDATE_NOW_PENDING_FILE, load_json_file_fn=_load_json_file)


def update_now_pending_payload() -> dict:
    return service_update_now_pending_payload(
        UPDATE_NOW_PENDING_FILE,
        read_pending_fn=_read_update_now_pending,
    )

























def execute_planned_action(tool: str, args=None):
    return service_execute_planned_action_from_runtime(
        tool,
        args,
        runtime_scope=globals(),
    )


def make_pending_weather_action() -> dict:
    saved_location = str(get_saved_location_text() or "").strip()
    return {
        "kind": "weather_lookup",
        "status": "awaiting_location",
        "saved_location_available": bool(saved_location),
        "preferred_tool": "weather_location",
    }


def _weather_current_location_available() -> bool:
    if resolve_current_device_coords():
        return True
    if str(get_saved_location_text() or "").strip():
        return True
    return bool(_coords_from_saved_location())





























def web_search(query: str, save_dir: Path = WEB_CACHE_DIR, max_results: int = 5) -> dict:
    return service_web_search(query, save_dir, requests_post_fn=requests.post, max_results=max_results)


globals().update(service_build_core_tool_exports(globals()))

































# =========================
# Commands (typed) for kb / patch
# =========================



# =========================
# Main loop
# =========================
def run_loop(tts):
    return service_run_loop(tts, core=sys.modules[__name__])


# =========================
# Entrypoint
# =========================
def main():
    from tools.runtime_singleton import acquire_role_singleton, release_role_singleton

    ok, detail = acquire_role_singleton("core")
    if not ok:
        print(f"Nova core already running ({detail}). Not starting a second instance.")
        return

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
        release_role_singleton("core")


if __name__ == "__main__":
    main()
