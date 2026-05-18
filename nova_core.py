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
from capabilities import explain_missing, describe_capabilities, describe_runtime_identity
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
from services.nova_memory_learning import load_json_dict_with_tmp_fallback as service_load_json_dict_with_tmp_fallback
from services.nova_memory_learning import mem_stats_payload as service_mem_stats_payload
from services.memory_health import build_memory_health_payload as service_build_memory_health_payload
from services.nova_prompt_replies import attach_learning_invitation as service_attach_learning_invitation
from services.nova_prompt_replies import last_question_recall_reply as service_last_question_recall_reply
from services.nova_prompt_replies import open_probe_reply as service_open_probe_reply
from services.nova_prompt_replies import session_fact_recall_reply as service_session_fact_recall_reply
from services.nova_prompt_replies import truthful_limit_outcome as service_truthful_limit_outcome
from services.nova_prompt_replies import truthful_limit_reply as service_truthful_limit_reply
from services.nova_pipeline_tools import handle_pipeline_command as service_handle_pipeline_command
from services.nova_profile_followups import developer_identity_followup_reply as service_developer_identity_followup_reply
from services.nova_profile_followups import developer_profile_reply as service_developer_profile_reply
from services.nova_profile_followups import infer_profile_conversation_state as service_infer_profile_conversation_state
from services.nova_profile_followups import identity_profile_source_boundary_reply as service_identity_profile_source_boundary_reply
from services.nova_query_classifiers import is_action_history_query as service_is_action_history_query
from services.nova_query_classifiers import is_assistant_name_query as service_is_assistant_name_query
from services.nova_query_classifiers import is_capability_query as service_is_capability_query
from services.nova_query_classifiers import is_developer_full_name_query as service_is_developer_full_name_query
from services.nova_query_classifiers import is_factual_identity_or_policy_query as service_is_factual_identity_or_policy_query
from services.nova_query_classifiers import is_identity_or_developer_query as service_is_identity_or_developer_query
from services.nova_query_classifiers import is_name_origin_question as service_is_name_origin_question
from services.nova_query_classifiers import is_policy_domain_query as service_is_policy_domain_query
from services.nova_query_classifiers import is_self_identity_web_challenge as service_is_self_identity_web_challenge
from services.nova_pulse import render_nova_pulse as service_render_nova_pulse
from services.nova_pulse import tool_nova_pulse as service_tool_nova_pulse
from services.nova_pulse import write_pulse_snapshot as service_write_pulse_snapshot
from services.nova_self_status import build_self_status_payload as service_build_self_status_payload
from services.nova_self_status import build_repo_change_snapshot as service_build_repo_change_snapshot
from services.nova_self_status import read_recent_ops_events as service_read_recent_ops_events
from services.nova_self_status import render_self_status as service_render_self_status
from services.nova_grounded_self_report import GROUNDED_SELF_REPORT_SERVICE
from services.control_work_trees import CONTROL_WORK_TREES_SERVICE
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
from services.nova_action_ledger_helpers import count_unsupported_claim_blocks_recently as service_count_unsupported_claim_blocks_recently
from services.nova_action_ledger_helpers import detect_repeated_tool_intent_without_execution as service_detect_repeated_tool_intent_without_execution
from services.nova_action_ledger_helpers import recent_action_ledger_records as service_recent_action_ledger_records
from services.nova_action_ledger_helpers import record_completed_tool_execution as service_record_completed_tool_execution
from services.nova_action_ledger_helpers import record_requested_tool_clarification as service_record_requested_tool_clarification
from services.nova_action_ledger_helpers import record_used_routing_override as service_record_used_routing_override
from services.nova_action_ledger_helpers import routing_stable_recently as service_routing_stable_recently
from services.nova_action_ledger_helpers import sample_intents_last as service_sample_intents_last
from services.nova_action_ledger_helpers import top_repeated_correction_class as service_top_repeated_correction_class
from services.nova_action_ledger_helpers import unsupported_claims_blocked_recently as service_unsupported_claims_blocked_recently
from services.nova_identity_history import classify_name_origin_outcome as service_classify_name_origin_outcome
from services.nova_identity_history import execute_identity_history_outcome as service_execute_identity_history_outcome
from services.nova_knowledge_packs import build_local_topic_digest_answer as service_build_local_topic_digest_answer
from services.nova_location_weather import device_location_status_payload as service_device_location_status_payload
from services.nova_location_weather import clear_runtime_device_location as service_clear_runtime_device_location
from services.nova_location_weather import coords_for_location_hint as service_coords_for_location_hint
from services.nova_location_weather import coords_from_saved_location as service_coords_from_saved_location
from services.nova_location_weather import extract_location_fact as service_extract_location_fact
from services.nova_location_weather import extract_weather_source_host as service_extract_weather_source_host
from services.nova_location_weather import get_saved_location_text as service_get_saved_location_text
from services.nova_location_weather import is_location_name_query as service_is_location_name_query
from services.nova_location_weather import is_location_recall_query as service_is_location_recall_query
from services.nova_location_weather import is_saved_location_weather_query as service_is_saved_location_weather_query
from services.nova_location_weather import is_weather_meta_followup as service_is_weather_meta_followup
from services.nova_location_weather import is_weather_status_followup as service_is_weather_status_followup
from services.nova_location_weather import live_device_location_summary as service_live_device_location_summary
from services.nova_location_weather import location_name_reply as service_location_name_reply
from services.nova_location_weather import location_recall_reply as service_location_recall_reply
from services.nova_location_weather import make_weather_result_state as service_make_weather_result_state
from services.nova_location_weather import mentions_location_phrase as service_mentions_location_phrase
from services.nova_location_weather import parse_lat_lon as service_parse_lat_lon
from services.nova_location_weather import resolve_current_device_coords as service_resolve_current_device_coords
from services.nova_location_weather import resolve_windows_device_coords as service_resolve_windows_device_coords
from services.nova_location_weather import runtime_device_backend_provider as service_runtime_device_backend_provider
from services.nova_location_weather import runtime_device_location_payload as service_runtime_device_location_payload
from services.nova_location_weather import set_location_text as service_set_location_text
from services.nova_location_weather import set_runtime_device_location as service_set_runtime_device_location
from services.nova_location_weather import store_declarative_fact_outcome as service_store_declarative_fact_outcome
from services.nova_location_weather import store_declarative_fact_reply as service_store_declarative_fact_reply
from services.nova_location_weather import store_location_fact_reply as service_store_location_fact_reply
from services.nova_location_weather import tool_weather as service_tool_weather
from services.nova_location_weather import weather_for_saved_location as service_weather_for_saved_location
from services.nova_location_weather import weather_location_label as service_weather_location_label
from services.nova_location_weather import weather_meta_reply as service_weather_meta_reply
from services.nova_location_weather import weather_status_reply as service_weather_status_reply
from services.nova_patching import behavioral_check as service_behavioral_check
from services.nova_patching import interactive_preview_review as service_interactive_preview_review
from services.nova_patching import teach_autoapply_proposal as service_teach_autoapply_proposal
from services.nova_patching import teach_propose_patch as service_teach_propose_patch
from services.nova_developer_profile import learn_contextual_developer_facts as service_learn_contextual_developer_facts
from services.nova_identity_preferences import extract_animal_preferences as service_extract_animal_preferences
from services.nova_identity_preferences import extract_animal_preferences_from_memory as service_extract_animal_preferences_from_memory
from services.nova_identity_preferences import extract_animal_preferences_from_text as service_extract_animal_preferences_from_text
from services.nova_identity_preferences import extract_color_preferences as service_extract_color_preferences
from services.nova_identity_preferences import extract_color_preferences_from_memory as service_extract_color_preferences_from_memory
from services.nova_identity_preferences import extract_color_preferences_from_text as service_extract_color_preferences_from_text
from services.nova_identity_preferences import extract_last_user_question as service_extract_last_user_question
from services.nova_identity_preferences import is_color_animal_match_question as service_is_color_animal_match_question
from services.nova_identity_preferences import is_color_lookup_request as service_is_color_lookup_request
from services.nova_identity_preferences import pick_color_for_animals as service_pick_color_for_animals
from services.nova_identity_answers import assistant_name_reply as service_assistant_name_reply
from services.nova_identity_answers import developer_full_name_reply as service_developer_full_name_reply
from services.nova_identity_answers import self_identity_web_challenge_reply as service_self_identity_web_challenge_reply
from services.nova_keyword_tools import handle_keywords as service_handle_keywords
from services.nova_keyword_tools import is_brief_command_form as service_is_brief_command_form
from services.nova_profile_followups import identity_profile_followup_reply as service_identity_profile_followup_reply
from services.nova_retrieval_followups import execute_retrieval_followup_outcome as service_execute_retrieval_followup_outcome
from services.nova_reply_contracts import classify_weather_lookup_outcome as service_classify_weather_lookup_outcome
from services.nova_reply_contracts import classify_correction_outcome as service_classify_correction_outcome
from services.nova_reply_contracts import classify_store_fact_outcome as service_classify_store_fact_outcome
from services.nova_reply_contracts import attach_reply_outcome as service_attach_reply_outcome
from services.nova_reply_contracts import classify_set_location_outcome as service_classify_set_location_outcome
from services.nova_reply_contracts import execute_weather_lookup_outcome as service_execute_weather_lookup_outcome
from services.nova_reply_contracts import render_reply as service_render_reply_contract
from services.nova_reply_sanitizer import sanitize_llm_reply as service_sanitize_llm_reply
from services.nova_routing_support import classify_supervisor_bypass as service_classify_supervisor_bypass
from services.nova_routing_support import finalize_routing_decision as service_finalize_routing_decision
from services.nova_routing_support import llm_classify_routing_intent as service_llm_classify_routing_intent
from services.nova_routing_support import looks_like_open_fallback_turn as service_looks_like_open_fallback_turn
from services.nova_tool_policy import web_fetch as service_web_fetch
from services import nova_conversation_followups as service_conversation_followups
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
from services.nova_patching import patch_preview_summaries as service_patch_preview_summaries
from services.nova_patching import patch_status_payload as service_patch_status_payload
from services.nova_patching import overlay_change_candidates as service_overlay_change_candidates
from services.nova_patching import snapshot_should_skip_relpath as service_snapshot_should_skip_relpath
from services.nova_pulse import build_pulse_payload as service_build_pulse_payload
from services.nova_reflection_health import maybe_log_self_reflection as service_maybe_log_self_reflection
from services.nova_research_contracts import classify_web_research_outcome as service_classify_web_research_outcome
from services.nova_search_endpoint import is_local_search_endpoint as service_is_local_search_endpoint
from services.nova_search_endpoint import normalize_search_endpoint as service_normalize_search_endpoint
from services.nova_search_endpoint import probe_search_endpoint as service_probe_search_endpoint
from services.nova_search_endpoint import search_endpoint_candidates as service_search_endpoint_candidates
from services.nova_turn_heuristics import classify_turn_acts as service_classify_turn_acts
from services.nova_turn_heuristics import build_greeting_reply as service_build_greeting_reply
from services.nova_turn_heuristics import is_declarative_info as service_is_declarative_info
from services.nova_turn_helpers import extract_memory_teach_text as service_extract_memory_teach_text
from services.nova_turn_helpers import is_location_request as service_is_location_request
from services.nova_turn_helpers import location_reply as service_location_reply
from services.nova_turn_helpers import retrieval_status_reply as service_retrieval_status_reply
from services.nova_turn_helpers import uses_prior_reference as service_uses_prior_reference
from services.nova_command_handlers import handle_commands as service_handle_commands
from services.nova_correction_parsing import extract_authoritative_correction_text as service_extract_authoritative_correction_text
from services.nova_correction_parsing import is_negative_feedback as service_is_negative_feedback
from services.nova_correction_parsing import looks_like_correction_cancel as service_looks_like_correction_cancel
from services.nova_correction_parsing import looks_like_correction_turn as service_looks_like_correction_turn
from services.nova_correction_parsing import looks_like_pending_replacement_text as service_looks_like_pending_replacement_text
from services.nova_correction_parsing import normalize_correction_for_storage as service_normalize_correction_for_storage
from services.nova_correction_parsing import parse_correction as service_parse_correction
from services.nova_correction_parsing import safe_eval_arithmetic_expression as service_safe_eval_arithmetic_expression
from services.nova_ollama_chat import ollama_chat as service_ollama_chat
from services.ollama_health import build_ollama_health_payload as service_build_ollama_health_payload
from services.nova_reply_guards import apply_claim_gate as service_apply_claim_gate
from services.nova_reply_guards import content_tokens as service_content_tokens
from services.nova_reply_guards import is_risky_claim_sentence as service_is_risky_claim_sentence
from services.nova_reply_guards import sentence_supported_by_evidence as service_sentence_supported_by_evidence
from services.nova_reply_guards import self_correct_reply as service_self_correct_reply
from services.nova_session_followups import build_session_fact_sheet as service_build_session_fact_sheet
from services.nova_session_followups import session_recap_reply as service_session_recap_reply
from services.nova_teaching import apply_reply_overrides as service_apply_reply_overrides
from services.nova_truth_hierarchy import hard_answer as service_hard_answer
from services.nova_truth_hierarchy import truth_hierarchy_answer as service_truth_hierarchy_answer
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
from services.nova_web_tools import looks_like_code_discovery_query as service_looks_like_code_discovery_query
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
from services.nova_followup_dispatch import consume_conversation_followup_from_runtime as service_consume_conversation_followup_from_runtime
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
from services.release_validation import record_release_validation_outcome as service_record_release_validation_outcome
from services.release_validation import render_release_outcome_recording as service_render_release_outcome_recording
from services.release_validation import render_release_validation_report as service_render_release_validation_report
from services.release_validation import run_release_validation as service_run_release_validation
from services.nova_memory_events import append_memory_event as service_append_memory_event
from services.nova_memory_events import record_memory_event as service_record_memory_event
from services.nova_memory_learning import learn_from_user_correction as service_learn_from_user_correction
from services.nova_memory_learning import mem_add as service_mem_add
from services.nova_patching import patch_apply as service_patch_apply
from services.data_pipeline_registry import get_pipeline_schema_probe as service_get_pipeline_schema_probe
from services.data_pipeline_registry import get_pipeline_status as service_get_pipeline_status
from services.data_pipeline_registry import list_pipeline_summaries as service_list_pipeline_summaries
from services.data_pipeline_registry import plan_pipeline_report as service_plan_pipeline_report
from services.data_pipeline_registry import preview_pipeline_query as service_preview_pipeline_query
from services.data_pipeline_registry import search_pipeline_vendor_dictionary as service_search_pipeline_vendor_dictionary
from services.pipeline_privileged_bridge import run_privileged_pipeline_query as service_run_privileged_pipeline_query
from services.nova_supervisor_flow import execute_registered_supervisor_rule_from_runtime as service_execute_registered_supervisor_rule_from_runtime
from services.nova_supervisor_flow import handle_supervisor_intent_from_runtime as service_handle_supervisor_intent_from_runtime
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


def voice_status_payload() -> dict:
    return service_voice_status_payload(globals())


def vision_status_payload(*, policy: dict | None = None, ollama_health: dict | None = None) -> dict:
    return service_vision_status_payload(
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
    if t in {"weather current location", "weather current"}:
        return "weather_lookup"
    if t.startswith((
        "weather for ",
        "weather in ",
        "weather at ",
        "check weather for ",
        "check weather in ",
        "check weather at ",
    )):
        return "weather_lookup"
    if t.startswith("web research "):
        return "web_research"
    if t.startswith("web search ") or "search the web" in t:
        return "web_search"
    if t.startswith("web gather "):
        return "web_gather"
    if t.startswith("web http://") or t.startswith("web https://"):
        return "web_fetch"
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


def _count_unsupported_claim_blocks_recently(records: Optional[list[dict]] = None, limit: int = 20) -> int:
    return service_count_unsupported_claim_blocks_recently(ACTION_LEDGER_DIR, records=records, limit=limit)


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
    return service_execute_registered_supervisor_rule_from_runtime(
        rule_result,
        text,
        current_state,
        turns=turns,
        input_source=input_source,
        allowed_actions=allowed_actions,
        runtime_scope=globals(),
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
    del normalized
    return False


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
    return service_classify_supervisor_bypass(
        text,
        normalize_bypass_phrase_fn=_normalize_bypass_phrase,
        allowed_supervisor_bypasses=_ALLOWED_SUPERVISOR_BYPASSES,
        looks_like_open_fallback_turn_fn=_looks_like_open_fallback_turn,
    )


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
    del text
    return False


def _should_clarify_unlabeled_numeric_turn(
    text: str,
    *,
    pending_action: Optional[dict] = None,
    current_state: Optional[dict] = None,
) -> bool:
    del text, pending_action, current_state
    return False


def _runtime_set_location_intent(
    text: str,
    *,
    pending_action: Optional[dict] = None,
) -> Optional[dict[str, object]]:
    del text, pending_action
    return None


_ROUTING_INTENT_PROMPT = ""


def _llm_classify_routing_intent(
    text: str,
    turns: Optional[list[tuple[str, str]]] = None,
    pending_action: Optional[dict] = None,
    return_none_payload: bool = False,
) -> Optional[dict[str, object]]:
    return service_llm_classify_routing_intent(
        text,
        turns,
        pending_action=pending_action,
        return_none_payload=return_none_payload,
        live_ollama_calls_allowed_fn=_live_ollama_calls_allowed,
        chat_model_fn=chat_model,
        ollama_base=OLLAMA_BASE,
        get_saved_location_text_fn=get_saved_location_text,
        requests_post_fn=requests.post,
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
    return service_handle_supervisor_intent_from_runtime(
        intent_result,
        user_text,
        turns=turns,
        input_source=input_source,
        entry_point=entry_point,
        runtime_scope=globals(),
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
    "store_fact.storage_unavailable": "Memory storage is not available for that fact.",
    "store_fact.declarative_ack": "Memory storage requires an explicit store request.",
    "weather_lookup.current_location": "{tool_result}",
    "weather_lookup.explicit_location": "{tool_result}",
    "weather_lookup.clarify": "What location should I use for the weather lookup?",
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
    return service_render_reply_contract(outcome, reply_templates=REPLY_TEMPLATES)


def _attach_reply_outcome(result_payload: Optional[dict], outcome: Optional[dict]) -> None:
    return service_attach_reply_outcome(result_payload, outcome)




def _classify_set_location_outcome(intent_result: dict, user_text: str = "") -> dict[str, object]:
    return service_classify_set_location_outcome(intent_result, user_text)


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
    return service_execute_weather_lookup_outcome(
        weather_outcome,
        render_reply_fn=render_reply,
        execute_planned_action_fn=execute_planned_action,
        make_weather_result_state_fn=_make_weather_result_state,
        classify_weather_lookup_outcome_fn=_classify_weather_lookup_outcome,
    )


def _classify_name_origin_outcome(intent_result: dict) -> dict[str, object]:
    return service_classify_name_origin_outcome(
        intent_result,
        get_learned_fact_fn=get_learned_fact,
        get_name_origin_story_fn=get_name_origin_story,
    )


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
        identity_profile_source_boundary_reply_fn=_identity_profile_source_boundary_reply,
        classify_name_origin_outcome_fn=_classify_name_origin_outcome,
        render_reply_fn=render_reply,
    )



def _open_probe_reply(text: str, turns: Optional[list[tuple[str, str]]] = None) -> tuple[str, str]:
    return service_open_probe_reply(
        text,
        turns,
        normalize_turn_text_fn=_normalize_turn_text,
        truthful_limit_reply_fn=_truthful_limit_reply,
    )


def _truthful_limit_reply(
    text: str = "",
    *,
    limitation: str = "cannot_verify",
    include_next_step: bool = True,
) -> str:
    return service_truthful_limit_reply(
        text,
        limitation=limitation,
        include_next_step=include_next_step,
        normalize_turn_text_fn=_normalize_turn_text,
        looks_like_mixed_info_request_turn_fn=_looks_like_mixed_info_request_turn,
        is_explicit_request_fn=_is_explicit_request,
    )


def _attach_learning_invitation(reply_text: str, *, truthful_limit: bool = False) -> str:
    return service_attach_learning_invitation(
        reply_text,
        truthful_limit=truthful_limit,
        normalize_turn_text_fn=_normalize_turn_text,
    )


def _truthful_limit_outcome(
    text: str = "",
    *,
    limitation: str = "cannot_verify",
) -> dict[str, str]:
    return service_truthful_limit_outcome(
        text,
        limitation=limitation,
        truthful_limit_reply_fn=_truthful_limit_reply,
    )


def _last_question_recall_reply(text: str, turns: Optional[list[tuple[str, str]]] = None) -> tuple[str, str]:
    return service_last_question_recall_reply(
        text,
        turns,
        extract_last_user_question_fn=_extract_last_user_question,
    )


def _session_fact_recall_reply(rule_result: dict) -> tuple[str, str]:
    return service_session_fact_recall_reply(rule_result)


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
    return service_classify_web_research_outcome(
        intent_result,
        user_text,
        turns=turns,
        infer_research_query_from_turns_fn=_infer_research_query_from_turns,
        resolve_research_provider_fn=_resolve_research_provider,
        provider_name_from_tool_fn=_provider_name_from_tool,
    )


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
        infer_turn_intent_fn=_infer_turn_intent,
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



def _is_factual_identity_or_policy_query(text: str) -> bool:
    return service_is_factual_identity_or_policy_query(text)


def _is_capability_query(text: str) -> bool:
    return service_is_capability_query(text)


def _is_policy_domain_query(text: str) -> bool:
    return service_is_policy_domain_query(text)


def _is_action_history_query(text: str) -> bool:
    return service_is_action_history_query(text)


def _is_identity_or_developer_query(text: str) -> bool:
    return service_is_identity_or_developer_query(text)


def _is_name_origin_question(text: str) -> bool:
    return service_is_name_origin_question(text)


def _is_assistant_name_query(text: str) -> bool:
    return service_is_assistant_name_query(text)




def _self_identity_web_challenge_reply() -> str:
    assistant_name = get_learned_fact("assistant_name", "Nova")
    return service_self_identity_web_challenge_reply(assistant_name=assistant_name)


def _assistant_name_reply(text: str) -> str:
    assistant_name = get_learned_fact("assistant_name", "Nova")
    return service_assistant_name_reply(text, assistant_name=assistant_name)


def _is_developer_full_name_query(text: str) -> bool:
    return service_is_developer_full_name_query(text)


def _developer_full_name_reply() -> str:
    full_name = get_learned_fact("developer_name", "Gustavo")
    if str(full_name or "").strip().lower() == "gustavo":
        full_name = "Gustavo Uribe"
    nickname = get_learned_fact("developer_nickname", "Gus")
    return service_developer_full_name_reply(
        developer_name=full_name,
        developer_nickname=nickname,
    )


def _is_location_request(user_text: str) -> bool:
    return service_is_location_request(user_text, normalize_turn_text_fn=_normalize_turn_text)


def _location_reply() -> str:
    return service_location_reply(
        runtime_device_location_payload_fn=runtime_device_location_payload,
        get_saved_location_text_fn=get_saved_location_text,
        resolve_current_device_coords_fn=resolve_current_device_coords,
    )


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
    return service_session_recap_reply(
        turns,
        current_text,
        is_session_recap_request_fn=_is_session_recap_request,
    )


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
    return service_self_correct_reply(
        user_text,
        reply,
        is_capability_query_fn=_is_capability_query,
        describe_capabilities_fn=describe_capabilities,
    )


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
        "Add a source like 'policy allow api.weather.gov' and then use 'weather in <location-or-lat,lon>'."
    )


def sanitize_llm_reply(reply: str, tool_context: str = "") -> str:
    return service_sanitize_llm_reply(
        reply,
        tool_context,
        weather_unavailable_message_fn=_weather_unavailable_message,
        describe_capabilities_fn=describe_capabilities,
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


def _parse_lat_lon(text: str) -> Optional[tuple[float, float]]:
    return service_parse_lat_lon(text)


def _coords_for_location_hint(location: str) -> Optional[tuple[float, float]]:
    return service_coords_for_location_hint(location)


def _coords_from_saved_location() -> Optional[tuple[float, float]]:
    return service_coords_from_saved_location(
        read_core_state_fn=read_core_state,
        default_statefile=DEFAULT_STATEFILE,
        mem_audit_fn=mem_audit,
        get_saved_location_text_fn=get_saved_location_text,
    )


def get_saved_location_text() -> str:
    return service_get_saved_location_text(
        read_core_state_fn=read_core_state,
        default_statefile=DEFAULT_STATEFILE,
        normalize_location_preview_fn=_normalize_location_preview,
        mem_audit_fn=mem_audit,
    )


def set_location_text(value: str, input_source: str = "typed") -> str:
    return service_set_location_text(
        value,
        input_source=input_source,
        normalize_location_preview_fn=_normalize_location_preview,
        set_core_state_fn=set_core_state,
        default_statefile=DEFAULT_STATEFILE,
        mem_add_fn=mem_add,
    )


def _extract_location_fact(text: str) -> str:
    return service_extract_location_fact(
        text,
        normalize_location_preview_fn=_normalize_location_preview,
    )


def _store_location_fact_reply(
    text: str,
    *,
    input_source: str = "typed",
    pending_action: Optional[dict] = None,
) -> str:
    return service_store_location_fact_reply(
        text,
        input_source=input_source,
        pending_action=pending_action,
        extract_location_fact_fn=_extract_location_fact,
        set_location_text_fn=set_location_text,
    )




def _store_declarative_fact_outcome(text: str, *, input_source: str = "typed") -> Optional[dict[str, object]]:
    return service_store_declarative_fact_outcome(
        text,
        input_source=input_source,
        is_declarative_info_fn=_is_declarative_info,
        mem_should_store_fn=mem_should_store,
        mem_add_fn=mem_add,
        classify_store_fact_outcome_fn=_classify_store_fact_outcome,
    )


def _store_declarative_fact_reply(text: str, *, input_source: str = "typed") -> str:
    return service_store_declarative_fact_reply(
        text,
        input_source=input_source,
        store_declarative_fact_outcome_fn=_store_declarative_fact_outcome,
        render_reply_fn=render_reply,
    )


def _is_saved_location_weather_query(text: str) -> bool:
    return service_is_saved_location_weather_query(text, normalize_turn_text_fn=_normalize_turn_text)


def _weather_for_saved_location() -> str:
    return service_weather_for_saved_location(
        get_saved_location_text_fn=get_saved_location_text,
        tool_weather_fn=tool_weather,
    )


def _extract_weather_source_host(tool_result: str) -> str:
    return service_extract_weather_source_host(tool_result)


def _weather_location_label(weather_mode: str, location_value: str = "") -> str:
    return service_weather_location_label(
        weather_mode,
        location_value,
        get_saved_location_text_fn=get_saved_location_text,
        coords_from_saved_location_fn=_coords_from_saved_location,
    )


def _make_weather_result_state(*, weather_mode: str, location_value: str = "", tool_result: str = "") -> dict:
    return service_make_weather_result_state(
        weather_mode=weather_mode,
        location_value=location_value,
        tool_result=tool_result,
        make_conversation_state_fn=_make_conversation_state,
        weather_location_label_fn=_weather_location_label,
        extract_weather_source_host_fn=_extract_weather_source_host,
        weather_source_host_fn=_weather_source_host,
    )


def _is_weather_meta_followup(text: str) -> bool:
    return service_is_weather_meta_followup(text, normalize_turn_text_fn=_normalize_turn_text)


def _is_weather_status_followup(text: str) -> bool:
    return service_is_weather_status_followup(text, normalize_turn_text_fn=_normalize_turn_text)


def _weather_meta_reply(state: dict) -> str:
    return service_weather_meta_reply(state)


def _weather_status_reply(state: dict) -> str:
    return service_weather_status_reply(state)


def _is_location_recall_query(text: str) -> bool:
    return service_is_location_recall_query(text)


def _location_recall_reply() -> str:
    return service_location_recall_reply(
        get_saved_location_text_fn=get_saved_location_text,
        runtime_device_location_payload_fn=runtime_device_location_payload,
        resolve_current_device_coords_fn=resolve_current_device_coords,
    )


def _is_location_name_query(text: str) -> bool:
    return service_is_location_name_query(
        text,
        normalize_turn_text_fn=_normalize_turn_text,
        uses_prior_reference_fn=_uses_prior_reference,
    )


def _location_name_reply() -> str:
    return service_location_name_reply(
        get_saved_location_text_fn=get_saved_location_text,
        runtime_device_location_payload_fn=runtime_device_location_payload,
        resolve_current_device_coords_fn=resolve_current_device_coords,
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
    return service_conversation_followups.normalize_turn_text(text)


def _looks_like_contextual_followup(text: str) -> bool:
    return service_conversation_followups.looks_like_contextual_followup(
        text,
        normalize_turn_text_fn=_normalize_turn_text,
        uses_prior_reference_fn=_uses_prior_reference,
    )


def _looks_like_contextual_continuation(text: str) -> bool:
    return service_conversation_followups.looks_like_contextual_continuation(
        text,
        normalize_turn_text_fn=_normalize_turn_text,
    )


def _looks_like_profile_followup(text: str) -> bool:
    return service_conversation_followups.looks_like_profile_followup(
        text,
        normalize_turn_text_fn=_normalize_turn_text,
    )


def _is_retrieval_meta_question(text: str) -> bool:
    return service_conversation_followups.is_retrieval_meta_question(
        text,
        normalize_turn_text_fn=_normalize_turn_text,
    )


def _retrieval_meta_reply(state: dict) -> str:
    return service_conversation_followups.retrieval_meta_reply(state)


def _non_retrieval_resource_meta_reply() -> str:
    return service_conversation_followups.non_retrieval_resource_meta_reply()


def _extract_retrieval_result_index(text: str) -> Optional[int]:
    return service_conversation_followups.extract_retrieval_result_index(
        text,
        normalize_turn_text_fn=_normalize_turn_text,
    )


def _looks_like_retrieval_followup(text: str) -> bool:
    return service_conversation_followups.looks_like_retrieval_followup(
        text,
        normalize_turn_text_fn=_normalize_turn_text,
        extract_retrieval_result_index_fn=_extract_retrieval_result_index,
    )






def _provider_name_from_tool(tool_name: str) -> str:
    return service_conversation_followups.provider_name_from_tool(tool_name)


def _make_retrieval_conversation_state(tool_name: str, query: str, tool_output: str) -> Optional[dict]:
    return service_conversation_followups.make_retrieval_conversation_state(
        tool_name,
        query,
        tool_output,
        extract_urls_fn=_extract_urls,
        make_conversation_state_fn=_make_conversation_state,
        web_research_has_results_fn=WEB_RESEARCH_SESSION.has_results,
        web_research_result_count_fn=WEB_RESEARCH_SESSION.result_count,
        web_research_query_fn=lambda: WEB_RESEARCH_SESSION.query,
    )


def _load_generated_queue_payload(limit: int = 12) -> dict:
    try:
        payload = service_generated_work_queue_payload(int(limit or 12), base_dir=BASE_DIR, runtime_dir=RUNTIME_DIR)
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _make_queue_status_conversation_state(tool_output: str) -> Optional[dict]:
    return service_conversation_followups.make_queue_status_conversation_state(
        tool_output,
        load_generated_queue_payload_fn=_load_generated_queue_payload,
        make_conversation_state_fn=_make_conversation_state,
    )


def _make_tool_conversation_state(tool_name: str, query: str, tool_output: str) -> Optional[dict]:
    return service_conversation_followups.make_tool_conversation_state(
        tool_name,
        query,
        tool_output,
        make_retrieval_conversation_state_fn=_make_retrieval_conversation_state,
        make_queue_status_conversation_state_fn=_make_queue_status_conversation_state,
    )


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
    return service_conversation_followups.infer_post_reply_conversation_state(
        routed_text,
        planner_decision=planner_decision,
        tool=tool,
        tool_args=tool_args,
        tool_result=tool_result,
        turns=turns,
        fallback_state=fallback_state,
        make_tool_conversation_state_fn=_make_tool_conversation_state,
        infer_profile_conversation_state_fn=_infer_profile_conversation_state,
        is_location_recall_query_fn=_is_location_recall_query,
        looks_like_location_recall_followup_fn=_looks_like_location_recall_followup,
        make_conversation_state_fn=_make_conversation_state,
    )


def _retrieval_followup_reply(state: dict, text: str) -> tuple[str, Optional[dict]]:
    return service_conversation_followups.retrieval_followup_reply(
        state,
        text,
        extract_retrieval_result_index_fn=_extract_retrieval_result_index,
        make_retrieval_conversation_state_fn=_make_retrieval_conversation_state,
        looks_like_retrieval_followup_fn=_looks_like_retrieval_followup,
        tool_web_gather_fn=tool_web_gather,
        tool_web_research_continue_fn=lambda: tool_web_research("", continue_mode=True),
        web_research_query_fn=lambda: WEB_RESEARCH_SESSION.query,
    )


def _is_queue_status_reason_followup(text: str) -> bool:
    return service_conversation_followups.is_queue_status_reason_followup(
        text,
        normalize_turn_text_fn=_normalize_turn_text,
    )


def _queue_status_reason_reply(state: dict) -> str:
    return service_conversation_followups.queue_status_reason_reply(state)


def _is_queue_status_report_followup(text: str) -> bool:
    return service_conversation_followups.is_queue_status_report_followup(
        text,
        normalize_turn_text_fn=_normalize_turn_text,
    )


def _queue_status_report_reply(state: dict) -> str:
    return service_conversation_followups.queue_status_report_reply(state)


def _is_queue_status_seam_followup(text: str) -> bool:
    return service_conversation_followups.is_queue_status_seam_followup(
        text,
        normalize_turn_text_fn=_normalize_turn_text,
    )


def _queue_status_seam_reply(state: dict) -> str:
    return service_conversation_followups.queue_status_seam_reply(state)




def _looks_like_location_recall_followup(session_turns: list[tuple[str, str]], text: str) -> bool:
    return service_conversation_followups.looks_like_location_recall_followup(
        session_turns,
        text,
        looks_like_contextual_continuation_fn=_looks_like_contextual_continuation,
    )


def _retrieval_status_reply(text: str) -> str:
    return service_retrieval_status_reply(text)


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
    return m.get("chat", "llama3.2:3b")


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





def get_learned_fact(key: str, default: str = "") -> str:
    data = load_learned_facts()
    v = str(data.get(key) or "").strip()
    return v or default


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
    runtime_context = _runtime_self_context_for_chat()

    context_blocks: list[str] = []
    if learning_context:
        context_blocks.append(learning_context)
    if runtime_context:
        context_blocks.append(runtime_context)
    if chat_context:
        context_blocks.append("CURRENT CHAT CONTEXT:\n" + chat_context)

    return {
        "context": "\n\n".join(context_blocks).strip()[:6000],
        "learning_context": learning_context,
        "runtime_context": runtime_context,
        "chat_context": chat_context,
        "session_fact_sheet": "",
        "memory_used": bool(learning_details.get("memory_used")),
        "knowledge_used": bool(learning_details.get("knowledge_used")),
        "memory_chars": int(learning_details.get("memory_chars") or 0),
        "knowledge_chars": int(learning_details.get("knowledge_chars") or 0),
    }


def _runtime_self_context_for_chat(max_chars: int = 1800) -> str:
    """Ambient self context for model chat; this does not own or route the turn."""
    try:
        assistant_name = str(get_learned_fact("assistant_name", "Nova") or "Nova").strip() or "Nova"
        identity_line = describe_runtime_identity(assistant_name)
    except Exception:
        identity_line = "I am Nova, a local AI runtime."

    lines = [
        "NOVA RUNTIME CONTEXT (ambient; use only if relevant to the user's turn):",
        identity_line,
    ]
    try:
        work_trees_payload = _self_report_work_trees_payload(limit=16)
        status_payload = _self_report_local_status_payload(work_trees_payload)
        report_payload = GROUNDED_SELF_REPORT_SERVICE.build_payload(status_payload, work_trees_payload)
        runtime = report_payload.get("runtime") if isinstance(report_payload.get("runtime"), dict) else {}
        release = report_payload.get("release") if isinstance(report_payload.get("release"), dict) else {}
        memory = report_payload.get("memory") if isinstance(report_payload.get("memory"), dict) else {}
        ollama = report_payload.get("ollama") if isinstance(report_payload.get("ollama"), dict) else {}
        attention = GROUNDED_SELF_REPORT_SERVICE.build_operator_attention(report_payload)
        lines.extend(
            [
                (
                    "State: "
                    f"work_tree={report_payload.get('work_tree_truth_status', 'unknown')}, "
                    f"open_tasks={report_payload.get('work_tree_open_task_count', 'unknown')}, "
                    f"runtime core={runtime.get('core', 'unknown')}, guard={runtime.get('guard', 'unknown')}, "
                    f"webui={runtime.get('webui', 'unknown')}."
                ),
                (
                    "Services: "
                    f"ollama_chat_ready={ollama.get('chat_ready', 'unknown')}, "
                    f"memory_enabled={memory.get('enabled', 'unknown')}, "
                    f"release_readiness={release.get('readiness', 'unknown')}, "
                    f"artifact_stale={release.get('latest_artifact_stale', 'unknown')}."
                ),
            ]
        )
        if isinstance(attention, dict) and bool(attention.get("active")):
            lines.append(f"Current attention: {str(attention.get('message') or '').strip()}")
    except Exception as exc:
        lines.append(f"Live state summary unavailable: {str(exc)[:160]}")
    return "\n".join(line for line in lines if str(line or "").strip())[:max_chars]


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
    return service_content_tokens(text)


def _is_risky_claim_sentence(sentence: str) -> bool:
    return service_is_risky_claim_sentence(sentence)


def _sentence_supported_by_evidence(sentence: str, evidence_text: str, tool_context: str = "") -> bool:
    return service_sentence_supported_by_evidence(
        sentence,
        evidence_text,
        tool_context,
        is_risky_claim_sentence_fn=_is_risky_claim_sentence,
        content_tokens_fn=_content_tokens,
    )


def _apply_claim_gate(reply: str, evidence_text: str = "", tool_context: str = "") -> tuple[str, bool, str]:
    return service_apply_claim_gate(
        reply,
        evidence_text,
        tool_context,
        sentence_supported_by_evidence_fn=_sentence_supported_by_evidence,
        truthful_limit_reply_fn=_truthful_limit_reply,
    )


def _uses_prior_reference(user_text: str) -> bool:
    return service_uses_prior_reference(user_text)


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
    return service_looks_like_correction_turn(text)


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
    if _looks_like_affirmative_followup(raw):
        return True
    return bool(assistant_turn) and _assistant_offered_weather_lookup(assistant_turn) and _looks_like_affirmative_followup(raw)


def _assistant_offered_weather_lookup(text: str) -> bool:
    normalized = _normalize_turn_text(text)
    if not normalized:
        return False
    return any(phrase in normalized for phrase in (
        "check the weather for you",
    ))


def _classify_turn_acts(
    text: str,
    *,
    turns: Optional[list[tuple[str, str]]] = None,
    active_subject: str = "",
    pending_action: Optional[dict] = None,
) -> list[str]:
    return service_classify_turn_acts(
        text,
        turns=turns,
        active_subject=active_subject,
        pending_action=pending_action,
        split_turn_clauses_fn=_split_turn_clauses,
        is_explicit_command_like_fn=_is_explicit_command_like,
        looks_like_correction_turn_fn=_looks_like_correction_turn,
        is_explicit_request_fn=_is_explicit_request,
        is_statement_like_clause_fn=_is_statement_like_clause,
        looks_like_continue_thread_turn_fn=_looks_like_continue_thread_turn,
    )


def _looks_like_mixed_info_request_turn(text: str) -> bool:
    return "mixed" in _classify_turn_acts(text)


def _mixed_info_request_clarify_reply(text: str) -> str:
    del text
    return ""


def _extract_urls(text: str) -> list[str]:
    return service_extract_urls(text)


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
    return service_build_greeting_reply(
        user_text,
        active_user=active_user,
        default_local_user_id_fn=_default_local_user_id,
    )


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
    return service_extract_color_preferences(session_turns, known_colors=KNOWN_COLORS)


def _extract_color_preferences_from_text(text: str) -> list[str]:
    return service_extract_color_preferences_from_text(text, known_colors=KNOWN_COLORS)


def _extract_color_preferences_from_memory() -> list[str]:
    return service_extract_color_preferences_from_memory(
        mem_enabled_fn=mem_enabled,
        mem_recall_fn=mem_recall,
        extract_color_preferences_from_text_fn=_extract_color_preferences_from_text,
    )


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
        live = service_live_device_location_summary(
            runtime_device_location_payload_fn=runtime_device_location_payload,
            resolve_current_device_coords_fn=resolve_current_device_coords,
            allow_stale=True,
        )
        if live:
            preview = str(get_saved_location_text() or "").strip()
            saved_note = f" Saved location label: {preview}." if preview else ""
            accuracy = live.get("accuracy_m")
            accuracy_note = f" Accuracy about {int(round(float(accuracy)))}m." if accuracy is not None else ""
            label = str(live.get("label") or "").strip()
            label_note = f" That is near {label}." if label else ""
            if live.get("stale"):
                return _prefix_from_earlier_memory(
                    f"Based on the verified relation you gave me, Gus's last shared device location fix is {live.get('coords_text')}.{accuracy_note} It is stale, so I won't call it current.{label_note}{saved_note}"
                )
            return _prefix_from_earlier_memory(
                f"Based on the verified relation you gave me, Gus's current location matches my current device location: {live.get('coords_text')}.{accuracy_note}{label_note}{saved_note}"
            )
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


def _identity_profile_source_boundary_reply(subject: str) -> str:
    return service_identity_profile_source_boundary_reply(
        subject,
        get_active_user_fn=get_active_user,
        get_learned_fact_fn=get_learned_fact,
        speaker_matches_developer_fn=_speaker_matches_developer,
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
    return service_consume_conversation_followup_from_runtime(
        state,
        text,
        input_source=input_source,
        turns=turns,
        runtime_scope=globals(),
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
    return service_extract_memory_teach_text(
        text,
        memory_should_keep_text_fn=_memory_should_keep_text,
    )


def _extract_last_user_question(turns: list[tuple[str, str]], current_text: str) -> str:
    return service_extract_last_user_question(
        turns,
        current_text,
        is_identity_or_developer_query_fn=_is_identity_or_developer_query,
        is_color_lookup_request_fn=_is_color_lookup_request,
        is_developer_color_lookup_request_fn=_is_developer_color_lookup_request,
        is_developer_bilingual_request_fn=_is_developer_bilingual_request,
    )


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
    return service_extract_animal_preferences(session_turns, known_animals=KNOWN_ANIMALS)


def _extract_animal_preferences_from_text(text: str) -> list[str]:
    return service_extract_animal_preferences_from_text(text, known_animals=KNOWN_ANIMALS)


def _extract_animal_preferences_from_memory() -> list[str]:
    return service_extract_animal_preferences_from_memory(
        mem_enabled_fn=mem_enabled,
        mem_recall_fn=mem_recall,
        extract_animal_preferences_from_text_fn=_extract_animal_preferences_from_text,
    )


def _is_color_animal_match_question(user_text: str) -> bool:
    return service_is_color_animal_match_question(user_text)


def _pick_color_for_animals(colors: list[str], animals: list[str]) -> str:
    return service_pick_color_for_animals(colors, animals)


def _is_color_lookup_request(user_text: str) -> bool:
    return service_is_color_lookup_request(user_text)


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


def _parse_correction(text: str) -> Optional[str]:
    return service_parse_correction(text)


def _looks_like_correction_cancel(text: str) -> bool:
    return service_looks_like_correction_cancel(text, normalize_turn_text=_normalize_turn_text)


def _looks_like_pending_replacement_text(text: str) -> bool:
    return service_looks_like_pending_replacement_text(text, normalize_turn_text=_normalize_turn_text)


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
    return service_is_negative_feedback(text)


def _extract_authoritative_correction_text(text: str) -> Optional[str]:
    return service_extract_authoritative_correction_text(text)


def _normalize_correction_for_storage(correction: str) -> str:
    return service_normalize_correction_for_storage(correction)


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
    return service_apply_reply_overrides(reply, updates_dir=UPDATES_DIR)


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


def tool_pipeline(command_text: str = "pipeline help"):
    return service_handle_pipeline_command(
        command_text,
        data_sources_root=DATA_SOURCES_ROOT,
        list_pipeline_summaries_fn=service_list_pipeline_summaries,
        get_pipeline_status_fn=service_get_pipeline_status,
        get_pipeline_schema_probe_fn=service_get_pipeline_schema_probe,
        preview_pipeline_query_fn=service_preview_pipeline_query,
        run_privileged_pipeline_query_fn=service_run_privileged_pipeline_query,
        search_pipeline_vendor_dictionary_fn=service_search_pipeline_vendor_dictionary,
        plan_pipeline_report_fn=service_plan_pipeline_report,
    )


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
        authority_context={"allowed_authority_levels": ["read_only", "read_only_expensive", "read_only_network"]},
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

def render_nova_pulse(payload: Optional[dict] = None) -> str:
    return service_render_nova_pulse(
        payload,
        build_pulse_payload_fn=build_pulse_payload,
    )


def write_pulse_snapshot(payload: dict) -> None:
    return service_write_pulse_snapshot(
        payload,
        pulse_snapshot_file=PULSE_SNAPSHOT_FILE,
    )


def tool_nova_pulse():
    return service_tool_nova_pulse(
        build_pulse_payload_fn=build_pulse_payload,
        write_pulse_snapshot_fn=write_pulse_snapshot,
        render_nova_pulse_fn=render_nova_pulse,
    )


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
    work_trees = dict(work_trees_payload or {}) if isinstance(work_trees_payload, dict) else {}
    counts = work_trees.get("counts") if isinstance(work_trees.get("counts"), dict) else {}
    open_task_count = int(counts.get("open_tasks", 0) or 0)
    pending_count = int(counts.get("pending", 0) or 0)
    working_count = int(counts.get("working", 0) or 0)
    blocked_count = int(counts.get("blocked", 0) or 0)
    operator_hold_count = 0
    self_repair_blocked_count = 0
    self_repair_observing_count = 0
    observing_count = 0
    for tree_payload in list(work_trees.get("trees") or []):
        if not isinstance(tree_payload, dict):
            continue
        for node in list(tree_payload.get("nodes") or []):
            if not isinstance(node, dict):
                continue
            status_text = str(node.get("status") or "").strip().lower()
            resolution_text = str(node.get("resolution_state") or "").strip().lower()
            source_type = str(node.get("source_type") or "").strip().lower()
            work_class = str(node.get("work_class") or "").strip().lower()
            actionability = str(node.get("actionability") or "").strip().lower()
            source_payload = node.get("source_payload") if isinstance(node.get("source_payload"), dict) else {}
            memory_origin = (
                source_payload.get("memory_bootstrap_origin")
                if isinstance(source_payload.get("memory_bootstrap_origin"), dict)
                else {}
            )
            memory_bootstrap = (
                source_payload.get("memory_bootstrap")
                if isinstance(source_payload.get("memory_bootstrap"), dict)
                else {}
            )
            memory_operator_hold = bool(
                status_text == "blocked"
                and source_type == "memory_health"
                and work_class == "governance_pressure"
                and str(memory_origin.get("status") or memory_bootstrap.get("origin_status") or "").strip().lower()
                == "pending_operator_confirmation"
            )
            operator_hold = memory_operator_hold
            if operator_hold:
                operator_hold_count += 1
            elif status_text == "blocked":
                self_repair_blocked_count += 1
            if resolution_text == "observing" and status_text not in {"complete", "archived"}:
                observing_count += 1
                if not operator_hold:
                    self_repair_observing_count += 1
    if self_repair_blocked_count > 0 or self_repair_observing_count > 0:
        status = "blocked_observing"
    elif operator_hold_count > 0:
        status = "operator_hold"
    elif open_task_count > 0 or pending_count > 0 or working_count > 0:
        status = "open"
    else:
        status = "clear"
    return {
        "status": status,
        "open_task_count": open_task_count,
        "blocked_branch_count": blocked_count,
        "operator_hold_branch_count": operator_hold_count,
        "self_repair_blocked_branch_count": self_repair_blocked_count,
        "self_repair_observing_branch_count": self_repair_observing_count,
        "observing_branch_count": observing_count,
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


def runtime_identity_reply(text: str = "") -> str:
    del text
    assistant_name = str(get_learned_fact("assistant_name", "Nova") or "Nova").strip() or "Nova"
    return describe_runtime_identity(assistant_name)


def tool_nova_self_status():
    pulse_payload = _apply_latest_regression_validation(build_pulse_payload())
    payload = service_build_self_status_payload(
        pulse_payload=pulse_payload,
        recent_ops_events=service_read_recent_ops_events(RUNTIME_DIR / "ops_journal.jsonl", limit=60),
        repo_change_snapshot=service_build_repo_change_snapshot(BASE_DIR),
    )
    return service_render_self_status(payload)


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


def tool_core_health_brief(feed: str = ""):
    brief = build_core_health_brief_payload()
    service_write_core_health_brief(RUNTIME_DIR / "core_health_brief.json", brief)

    feed_result = None
    if str(feed or "").strip().lower() in {"feed", "work_tree", "worktree", "seed"}:
        import work_tree

        feed_result = service_feed_core_health_brief_to_work_tree(brief, work_tree_module=work_tree)
    return service_render_core_health_brief(brief, feed_result=feed_result)


def tool_core_thinning(feed: str = ""):
    raw = str(feed or "").strip()
    if raw.startswith("{"):
        return service_execute_core_thinning_order(raw)

    core_path = Path(__file__).resolve()
    brief = service_build_core_thinning_brief([core_path, core_path.with_name("nova_http.py")])
    feed_result = None
    if raw.lower() in {"feed", "work_tree", "worktree", "seed"}:
        import work_tree

        feed_result = service_feed_core_thinning_brief_to_work_tree(brief, work_tree_module=work_tree)
    return service_render_core_thinning_brief(brief, feed_result=feed_result)


def tool_release_rebuild_verify(label: str = "work-tree-rebuild"):
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
    readiness = report.get("readiness") if isinstance(report.get("readiness"), dict) else {}
    steps = [
        {
            "name": str(step.get("name") or ""),
            "returncode": int(step.get("returncode", 1) or 0),
            "duration_sec": step.get("duration_sec"),
        }
        for step in list(report.get("steps") or [])
        if isinstance(step, dict)
    ]
    required = {"repo_hygiene", "smoke_runtime", "package_build", "package_verify"}
    successful = {
        str(step.get("name") or "")
        for step in steps
        if int(step.get("returncode", 1) or 0) == 0
    }
    rebuild_verified = bool(report.get("artifact")) and required.issubset(successful)
    readiness_state = str(readiness.get("latest_readiness_state") or readiness.get("state") or "")
    failure_reason = "" if rebuild_verified else str(report.get("failure_reason") or "release_rebuild_verify_failed")
    return {
        "ok": rebuild_verified,
        "artifact": str(report.get("artifact") or ""),
        "failure_reason": failure_reason,
        "readiness_state": readiness_state,
        "ready_to_ship": bool(readiness.get("latest_ready_to_ship", False)),
        "report_path": str(report.get("report_path") or ""),
        "promoted": False,
        "run_regression": False,
        "steps": steps,
    }


def _read_update_now_pending() -> dict:
    return service_read_update_now_pending(UPDATE_NOW_PENDING_FILE, load_json_file_fn=_load_json_file)


def update_now_pending_payload() -> dict:
    return service_update_now_pending_payload(
        UPDATE_NOW_PENDING_FILE,
        read_pending_fn=_read_update_now_pending,
    )


def _write_update_now_pending(payload: dict) -> None:
    return service_write_update_now_pending(UPDATE_NOW_PENDING_FILE, payload)


def _clear_update_now_pending() -> None:
    return service_clear_update_now_pending(UPDATE_NOW_PENDING_FILE)






def _build_update_now_token(zip_path: Path) -> str:
    return service_build_update_now_token(zip_path)


def tool_update_now():
    return service_tool_update_now(
        patch_status_payload_fn=patch_status_payload,
        latest_approved_update_zip_fn=_latest_approved_update_zip,
        patch_preview_fn=patch_preview,
        clear_pending_fn=_clear_update_now_pending,
        write_pending_fn=_write_update_now_pending,
        build_token_fn=_build_update_now_token,
    )


def tool_update_now_confirm(token: str = ""):
    return service_tool_update_now_confirm(
        token,
        read_pending_fn=_read_update_now_pending,
        clear_pending_fn=_clear_update_now_pending,
        patch_status_payload_fn=patch_status_payload,
        latest_approved_update_zip_fn=_latest_approved_update_zip,
        execute_patch_action_fn=execute_patch_action,
    )






def tool_update_now_cancel():
    return service_tool_update_now_cancel(
        read_pending_fn=_read_update_now_pending,
        clear_pending_fn=_clear_update_now_pending,
    )


def execute_planned_action(tool: str, args=None):
    return service_execute_planned_action_from_runtime(
        tool,
        args,
        runtime_scope=globals(),
    )


def handle_commands(user_text: str, session_turns=None, session=None):
    return service_handle_commands(
        user_text,
        session_turns=session_turns,
        session=session,
        core=sys.modules[__name__],
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






def _decode_search_href(href: str) -> str:
    return service_decode_search_href(href)


def _extract_text_from_path(path: Path, max_chars: int = 2000) -> str:
    return service_extract_text_from_path(path, max_chars)


def _extract_text_from_html_content(raw_html: str, max_chars: int = 2000) -> str:
    return service_extract_text_from_html_content(raw_html, max_chars)


def _extract_same_host_links(raw_html: str, base_url: str, host: str) -> list[str]:
    return service_extract_same_host_links(raw_html, base_url, host)


def _expand_research_terms(tokens: list[str]) -> list[str]:
    return service_expand_research_terms(tokens)


def _score_research_hit(url: str, text: str, terms: list[str], primary_tokens: Optional[list[str]] = None) -> float:
    return service_score_research_hit(url, text, terms, primary_tokens=primary_tokens)


def _crawl_domain_for_query(start_url: str, query_tokens: list[str], max_pages: int, max_depth: int) -> list[tuple[float, str, str]]:
    return service_crawl_domain_for_query(
        start_url,
        query_tokens,
        max_pages,
        max_depth,
        requests_get_fn=requests.get,
        expand_research_terms_fn=_expand_research_terms,
        extract_text_from_html_content_fn=_extract_text_from_html_content,
        score_research_hit_fn=_score_research_hit,
        extract_same_host_links_fn=_extract_same_host_links,
    )


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
    return service_seed_urls_for_domain(
        domain,
        query_tokens,
        max_seed=max_seed,
        fetch_sitemap_urls_fn=_fetch_sitemap_urls,
        expand_research_terms_fn=_expand_research_terms,
    )



def web_search(query: str, save_dir: Path = WEB_CACHE_DIR, max_results: int = 5) -> dict:
    return service_web_search(query, save_dir, requests_post_fn=requests.post, max_results=max_results)


def tool_search(query: str):
    return service_tool_search(
        query,
        explain_missing_fn=explain_missing,
        policy_tools_enabled_fn=policy_tools_enabled,
        web_search_fn=web_search,
        web_cache_dir=WEB_CACHE_DIR,
    )


def tool_web_fetch(url: str):
    return service_tool_web_fetch(
        url,
        explain_missing_fn=explain_missing,
        policy_tools_enabled_fn=policy_tools_enabled,
        web_fetch_fn=lambda target_url: web_fetch(target_url, WEB_CACHE_DIR),
        web_allowlist_message_fn=_web_allowlist_message,
    )








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
    return service_handle_keywords(
        text,
        tool_screen_fn=tool_screen,
        tool_camera_fn=tool_camera,
        tool_ls_fn=tool_ls,
        tool_read_fn=tool_read,
        tool_find_fn=tool_find,
        tool_health_fn=tool_health,
        is_brief_command_form_fn=_is_brief_command_form,
    )


def _is_brief_command_form(text: str, command: str, max_tokens: int) -> bool:
    return service_is_brief_command_form(text, command, max_tokens)


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
