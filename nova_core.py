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
import io
import json
import os
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
from typing import Optional, Tuple
from urllib.parse import urlparse, parse_qs, unquote, urljoin, quote
from conversation_manager import ConversationSession
from supervisor import Supervisor
from capabilities import explain_missing, describe_capabilities
from task_engine import analyze_request
from action_planner import decide_actions
from env_inspector import inspect_environment, format_report
import requests
import psutil
from tools import ToolContext, ToolInvocationError, build_default_registry
try:
    import memory as memory_mod
except Exception:
    memory_mod = None

# Active session user id (thread-local so concurrent HTTP requests cannot bleed identity)
_ACTIVE_USER_LOCAL = threading.local()

def set_active_user(name: Optional[str]):
    if not name:
        _ACTIVE_USER_LOCAL.value = None
    else:
        _ACTIVE_USER_LOCAL.value = str(name).strip()

def get_active_user() -> Optional[str]:
    v = getattr(_ACTIVE_USER_LOCAL, "value", None)
    return str(v).strip() if v else None

# -------------------------
# Voice deps are optional
# -------------------------
VOICE_OK = True
VOICE_IMPORT_ERR = ""
try:
    import sounddevice as sd
    import scipy.io.wavfile as wav
    from faster_whisper import WhisperModel
except Exception as e:
    VOICE_OK = False
    VOICE_IMPORT_ERR = str(e)
    sd = None
    wav = None
    WhisperModel = None




# =========================
# Config / Policy
# =========================
import sys

# Robust BASE_DIR detection
if getattr(sys, "frozen", False):
    # Running as compiled executable
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    # Running as normal Python script
    BASE_DIR = Path(__file__).resolve().parent

RUNTIME_DIR = BASE_DIR / "runtime"
LOG_DIR = BASE_DIR / "logs"
MEMORY_DIR = BASE_DIR / "memory"
ACTION_LEDGER_DIR = RUNTIME_DIR / "actions"
MEMORY_EVENTS_LOG = RUNTIME_DIR / "memory_events.jsonl"
HEALTH_LOG = RUNTIME_DIR / "health.log"
IDENTITY_FILE = MEMORY_DIR / "identity.json"
LEARNED_FACTS_FILE = MEMORY_DIR / "learned_facts.json"
BEHAVIOR_METRICS_FILE = RUNTIME_DIR / "behavior_metrics.json"
SELF_REFLECTION_LOG = RUNTIME_DIR / "self_reflection.jsonl"
POLICY_PATH = BASE_DIR / "policy.json"
PYTHON = str(BASE_DIR / ".venv" / "Scripts" / "python.exe")
OLLAMA_BASE = "http://127.0.0.1:11434"

SAMPLE_RATE = 16000
CHANNELS = 1

# UX tuning
RECORD_SECONDS = 3
OLLAMA_BOOT_RETRIES = 15
OLLAMA_REQ_TIMEOUT = 1800

# Knowledge packs (B-mode)
KNOWLEDGE_ROOT = BASE_DIR / "knowledge"
PEIMS_KNOWLEDGE_DIR = KNOWLEDGE_ROOT / "peims"
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
WEB_RESEARCH_LAST_QUERY: str = ""
WEB_RESEARCH_LAST_RESULTS: list[tuple[float, str, str]] = []
WEB_RESEARCH_CURSOR: int = 0
TOOL_REGISTRY = build_default_registry()

BEHAVIOR_METRICS: dict = {
    "deterministic_hit": 0,
    "tool_route": 0,
    "llm_fallback": 0,
    "low_confidence_block": 0,
    "correction_learned": 0,
    "correction_applied": 0,
    "self_correction_applied": 0,
    "conflict_detected": 0,
    "top_repeated_failure_class": "",
    "top_repeated_correction_class": "",
    "routing_stable": True,
    "unsupported_claims_blocked": False,
    "last_reflection_turn": 0,
    "last_reflection_at": "",
    "last_event": "",
    "updated_at": "",
}

TURN_SUPERVISOR = Supervisor()


def _save_behavior_metrics() -> None:
    try:
        RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        tmp = BEHAVIOR_METRICS_FILE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(BEHAVIOR_METRICS, ensure_ascii=True, indent=2), encoding="utf-8")
        tmp.replace(BEHAVIOR_METRICS_FILE)
    except Exception:
        pass


def behavior_record_event(event: str) -> None:
    e = (event or "").strip()
    if not e:
        return
    if e in BEHAVIOR_METRICS and isinstance(BEHAVIOR_METRICS.get(e), int):
        BEHAVIOR_METRICS[e] = int(BEHAVIOR_METRICS.get(e, 0)) + 1
    BEHAVIOR_METRICS["last_event"] = e
    BEHAVIOR_METRICS["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    _save_behavior_metrics()


def behavior_get_metrics() -> dict:
    return dict(BEHAVIOR_METRICS)


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
    }
    if isinstance(extra_payload, dict):
        for key, value in extra_payload.items():
            payload[key] = value
    _append_self_reflection(payload)
    if count_total % 10 == 0:
        record_health_snapshot(session_id=str(payload.get("session_id") or "default"), reflection=payload, session_end=False)
    BEHAVIOR_METRICS["top_repeated_failure_class"] = payload["top_repeated_failure_class"]
    BEHAVIOR_METRICS["top_repeated_correction_class"] = payload["top_repeated_correction_class"]
    BEHAVIOR_METRICS["routing_stable"] = bool(payload["routing_stable"])
    BEHAVIOR_METRICS["unsupported_claims_blocked"] = bool(payload["unsupported_claims_blocked"])
    BEHAVIOR_METRICS["last_reflection_turn"] = count_total
    BEHAVIOR_METRICS["last_reflection_at"] = payload["ts"]
    _save_behavior_metrics()
    return payload


def build_turn_reflection(
    session_state: ConversationSession,
    *,
    entry_point: str,
    session_id: str,
    current_decision: dict,
) -> dict:
    reflection = TURN_SUPERVISOR.process_turn(
        entry_point=entry_point,
        session_id=session_id,
        session_summary=session_state.reflection_summary(),
        current_decision=current_decision,
        recent_records=_recent_action_ledger_records(limit=10),
        recent_reflections=_recent_self_reflection_rows(limit=3),
    )
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
        next_state = (rule_result or {}).get("next_state")
        if not isinstance(next_state, dict):
            next_state = _make_conversation_state("location_recall")
        return True, _location_reply(), next_state

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


def _intent_trace_preview(text: str, *, limit: int = 120) -> str:
    compact = re.sub(r"\s+", " ", str(text or "").strip())
    if len(compact) <= limit:
        return compact
    return compact[: max(0, limit - 3)] + "..."


def _emit_supervisor_intent_trace(intent_result: dict, *, user_text: str = "") -> None:
    intent = str((intent_result or {}).get("intent") or "intent").strip().lower() or "intent"
    rule = str((intent_result or {}).get("rule_name") or "").strip()
    reason = ""

    if intent == "store_fact":
        reason = str((intent_result or {}).get("fact_text") or user_text).strip()
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
) -> tuple[bool, str]:
    intent = str((intent_result or {}).get("intent") or "").strip().lower()
    if not intent:
        return False, ""

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
        return True, "Got it - correcting that."

    if intent == "store_fact":
        fact_text = str((intent_result or {}).get("fact_text") or user_text).strip()
        if fact_text and mem_enabled():
            mem_add("user_fact", input_source, fact_text)
            return True, "Stored."
        if fact_text:
            return True, "Noted."
        return True, "I need the fact to store."

    if intent == "session_summary":
        return True, _session_recap_reply(list(turns or []), user_text)

    return False, ""


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
        "your name is nova",
        "your name is not",
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
    cues = ["developer", "gus", "nickname", "nick name", "his full name"]
    return any(c in low for c in cues)


def _developer_full_name_reply() -> str:
    full_name = get_learned_fact("developer_name", "Gustavo")
    nickname = get_learned_fact("developer_nickname", "Gus")
    if nickname and nickname.lower() != full_name.lower():
        return f"My developer's full name is {full_name}. {nickname} is his nickname."
    return f"My developer's full name is {full_name}."


def _is_location_request(user_text: str) -> bool:
    t = _normalize_turn_text(user_text)
    triggers = [
        "where is nova", "where are you", "your location", "what is your location",
        "what is your current location", "what is your current physical location",
        "where are you located", "where is nova located",
    ]
    return any(x in t for x in triggers)


def _location_reply() -> str:
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
    low = (text or "").strip().lower()
    cues = [
        "deep search",
        "dig up",
        "find out what else",
        "more information",
        "more info",
        "search more",
    ]
    return any(c in low for c in cues)


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
    data = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        data = {}

    data["allowed_root"] = str(Path(data.get("allowed_root", str(BASE_DIR))).resolve())

    tools = data.get("tools_enabled") if isinstance(data.get("tools_enabled"), dict) else {}
    tools.setdefault("screen", False)
    tools.setdefault("camera", False)
    tools.setdefault("files", False)
    tools.setdefault("health", False)
    tools.setdefault("web", False)
    data["tools_enabled"] = tools

    models = data.get("models") if isinstance(data.get("models"), dict) else {}
    models.setdefault("chat", "llama3.1:8b")
    models.setdefault("vision", "qwen2.5vl:7b")
    models.setdefault("stt_size", "base")
    data["models"] = models

    memory = data.get("memory") if isinstance(data.get("memory"), dict) else {}
    memory.setdefault("enabled", False)
    memory.setdefault("mode", "B")
    memory.setdefault("scope", "private")
    memory.setdefault("top_k", 5)
    memory.setdefault("context_top_k", 3)
    memory.setdefault("min_score", 0.25)
    memory.setdefault("store_min_chars", 12)
    memory.setdefault("exclude_sources", [])
    memory.setdefault("store_include_patterns", [])
    memory.setdefault("store_exclude_patterns", [])
    data["memory"] = memory

    web = data.get("web") if isinstance(data.get("web"), dict) else {}
    web.setdefault("enabled", False)
    web.setdefault("search_provider", "html")
    web.setdefault("search_api_endpoint", "")
    web.setdefault("allow_domains", [])
    web.setdefault("max_bytes", 20_000_000)
    web.setdefault("research_domains_limit", 4)
    web.setdefault("research_pages_per_domain", 8)
    web.setdefault("research_scan_pages_per_domain", 12)
    web.setdefault("research_max_depth", 1)
    web.setdefault("research_seeds_per_domain", 8)
    web.setdefault("research_max_results", 8)
    web.setdefault("research_min_score", 3.0)
    data["web"] = web

    patch = data.get("patch") if isinstance(data.get("patch"), dict) else {}
    patch.setdefault("enabled", True)
    patch.setdefault("allow_force", False)
    patch.setdefault("strict_manifest", True)
    data["patch"] = patch

    return data


def _load_policy_raw() -> dict:
    try:
        # Use normalized policy view so mutating actions never drop required keys.
        return load_policy()
    except Exception:
        return {}


def _save_policy_raw(data: dict) -> None:
    POLICY_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _record_policy_change(action: str, target: str, result: str, details: str = "") -> None:
    entry = {
        "ts": int(time.time()),
        "user": get_active_user() or "unknown",
        "action": str(action or "").strip(),
        "target": str(target or "").strip(),
        "result": str(result or "").strip(),
        "details": str(details or "").strip(),
    }
    try:
        POLICY_AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(POLICY_AUDIT_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


def policy_models():
    p = load_policy()
    return p.get("models") or {}


def policy_memory():
    p = load_policy()
    return p.get("memory") or {}


def policy_tools_enabled():
    p = load_policy()
    return p.get("tools_enabled") or {}


def build_tool_context(*, is_admin: bool = False, extra: Optional[dict] = None) -> ToolContext:
    policy = load_policy()
    extras = dict(extra or {})
    return ToolContext(
        user_id=get_active_user() or "",
        session_id="",
        policy=policy,
        allowed_root=str(Path(policy.get("allowed_root") or str(BASE_DIR)).resolve()),
        is_admin=bool(is_admin),
        extra=extras,
    )


def _tool_error_message(tool_name: str, reason: str) -> str:
    r = str(reason or "tool_failed").strip()
    mapping = {
        "screen_tool_disabled": "Screen tool disabled by policy.",
        "camera_tool_disabled": "Camera tool disabled by policy.",
        "files_tool_disabled": "File tools disabled by policy.",
        "health_tool_disabled": "Health tool disabled by policy.",
        "patch_tool_disabled": "Patch tool disabled by policy.",
        "patch_force_disabled": "Forced patch apply is disabled by policy.",
        "admin_required": f"{tool_name} is restricted to admin-approved execution.",
    }
    return mapping.get(r, r)


def execute_registered_tool(tool_name: str, args: dict, *, is_admin: bool = False, extra: Optional[dict] = None) -> str:
    ctx = build_tool_context(is_admin=is_admin, extra=extra)
    try:
        result = TOOL_REGISTRY.run_tool(tool_name, args or {}, ctx)
    except ToolInvocationError as e:
        return _tool_error_message(tool_name, str(e))
    except Exception as e:
        return f"{tool_name} tool failed: {e}"
    return str(result or "").strip()
    
def _research_handlers() -> dict[str, object]:
    return {
        "web_fetch": tool_web,
        "web_search": tool_web_search,
        "web_research": tool_web_research,
        "web_gather": tool_web_gather,
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
    p = load_policy()
    return (p.get("web") or {})


def policy_patch():
    p = load_policy()
    return (p.get("patch") or {})


def web_enabled() -> bool:
    p = load_policy()
    return bool((p.get("tools_enabled") or {}).get("web")) and bool((p.get("web") or {}).get("enabled"))


def _host_allowed(host: str, allow_domains: list[str]) -> bool:
    host = (host or "").lower()
    for d in allow_domains:
        d = (d or "").lower().strip()
        if not d:
            continue
        if host == d or host.endswith("." + d):
            return True
    return False


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
    awaiting_weather_location = (
        isinstance(pending_action, dict)
        and str(pending_action.get("kind") or "") == "weather_lookup"
        and str(pending_action.get("status") or "") == "awaiting_location"
    )
    if awaiting_weather_location:
        return ""
    location_fact = _extract_location_fact(text)
    if not location_fact:
        return ""
    set_location_text(location_fact, input_source=input_source)
    return "Noted."


def _store_declarative_fact_reply(text: str, *, input_source: str = "typed") -> str:
    if not _is_declarative_info(text):
        return ""
    if mem_should_store(text):
        mem_add("fact", input_source, text)
    return "Noted."


def _weather_for_saved_location() -> str:
    saved_text = get_saved_location_text()
    if saved_text:
        return tool_weather(saved_text)

    coords = _coords_from_saved_location()
    if coords:
        lat, lon = coords
        return tool_weather(f"{lat},{lon}")

    return _need_confirmed_location_message() + " You can tell me: 'My location is ...'"


def _is_location_recall_query(text: str) -> bool:
    t = (text or "").strip().lower()
    if not t:
        return False
    cues = [
        "recall my location",
        "remember my location",
        "what is my location",
        "do you know my location",
        "can you recall my location",
        "can you remember my location",
    ]
    return any(c in t for c in cues)


def _location_recall_reply() -> str:
    preview = get_saved_location_text()
    if preview:
        return f"Your saved location is {preview}."
    return "I don't have a stored location yet. You can tell me: 'My location is ...'"


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
    return len(normalized.split()) <= 5 and _uses_prior_reference(normalized)


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
    return str(tool_name or "").strip().lower() in {"web_search", "web_research", "web_gather", "web_fetch", "search"}


def _retrieval_query_from_text(tool_name: str, text: str) -> str:
    raw = str(text or "").strip()
    low = raw.lower()
    tool = str(tool_name or "").strip().lower()

    if tool == "web_research":
        if low in {"web continue", "continue web", "continue web research"}:
            return WEB_RESEARCH_LAST_QUERY
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
    return raw


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
        if WEB_RESEARCH_LAST_RESULTS:
            result_count = len(WEB_RESEARCH_LAST_RESULTS)
        if not effective_query:
            effective_query = WEB_RESEARCH_LAST_QUERY

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
        next_state = _make_retrieval_conversation_state(tool, action_query, tool_result)
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
            return result, (_make_retrieval_conversation_state("web_research", WEB_RESEARCH_LAST_QUERY, result) or state)

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


def _is_location_recall_state(state: Optional[dict]) -> bool:
    return isinstance(state, dict) and str(state.get("kind") or "") == "location_recall"


def _looks_like_location_recall_followup(session_turns: list[tuple[str, str]], text: str) -> bool:
    if _looks_like_contextual_followup(text):
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
    coords = _parse_lat_lon(value)
    if not coords:
        return "Usage: location coords <lat>,<lon>"

    lat, lon = coords
    try:
        set_core_state(DEFAULT_STATEFILE, "location_coords", {"lat": lat, "lon": lon})
    except Exception:
        pass

    # Also store in memory for continuity across tooling.
    try:
        mem_add("profile", "location_coords", f"location coordinates: {lat},{lon}")
    except Exception:
        pass

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
    return "I have a weather tool now, but I still need a confirmed location or coordinates."


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
    return bool(policy_memory().get("enabled", False))


def mem_top_k() -> int:
    try:
        return int(policy_memory().get("top_k", 5))
    except Exception:
        return 5


def mem_scope() -> str:
    raw = str(policy_memory().get("scope", "private") or "private").strip().lower()
    if raw not in {"private", "shared", "hybrid"}:
        return "private"
    return raw


def mem_context_top_k() -> int:
    try:
        v = int(policy_memory().get("context_top_k", 3))
        return max(1, min(v, 10))
    except Exception:
        return 3


def mem_min_score() -> float:
    try:
        return float(policy_memory().get("min_score", 0.25))
    except Exception:
        return 0.25


def mem_exclude_sources() -> list[str]:
    xs = policy_memory().get("exclude_sources") or []
    return [str(x) for x in xs if x]


def mem_store_min_chars() -> int:
    try:
        return int(policy_memory().get("store_min_chars", 12))
    except Exception:
        return 12


def mem_store_exclude_patterns() -> list[str]:
    xs = policy_memory().get("store_exclude_patterns") or []
    out = []
    for x in xs:
        s = str(x or "").strip()
        if s:
            out.append(s)
    return out


def mem_store_include_patterns() -> list[str]:
    xs = policy_memory().get("store_include_patterns") or []
    out = []
    for x in xs:
        s = str(x or "").strip()
        if s:
            out.append(s)
    return out


def _default_local_user_id() -> str:
    raw = (
        os.environ.get("NOVA_USER_ID")
        or os.environ.get("NOVA_CHAT_USER")
        or os.environ.get("USERNAME")
        or ""
    )
    return re.sub(r"[^A-Za-z0-9._-]", "", str(raw).strip())[:64]


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
    t = (text or "").strip()
    if not t:
        return False, "empty"

    low = t.lower()
    if len(t) < mem_store_min_chars():
        return False, "too_short"

    # Never store questions as memory facts.
    q_starts = (
        "what ", "where ", "who ", "why ", "how ", "when ", "which ",
        "do ", "did ", "can ", "could ", "would ", "is ", "are ", "should ",
    )
    if low.endswith("?") or any(low.startswith(q) for q in q_starts):
        return False, "question"

    # Drop common conversational noise.
    low_value = {
        "ok", "okay", "k", "kk", "yes", "no", "thanks", "thank you",
        "done", "cool", "nice", "great", "sounds good", "got it", "understood",
    }
    if low in low_value:
        return False, "ack"

    noise_prefixes = (
        "tip:", "nova:", "assistant:", "user:", "i couldn't find grounded sources",
        "please try:", "network error:", "loading", "checking",
    )
    if any(low.startswith(p) for p in noise_prefixes):
        return False, "ui_noise"

    # Operator-controlled include/exclude patterns.
    for pat in mem_store_exclude_patterns():
        try:
            if re.search(pat, t, flags=re.I):
                return False, "policy_exclude"
        except re.error:
            if pat.lower() in low:
                return False, "policy_exclude"

    for pat in mem_store_include_patterns():
        try:
            if re.search(pat, t, flags=re.I):
                return True, "policy_include"
        except re.error:
            if pat.lower() in low:
                return True, "policy_include"

    # Prefer durable facts/preferences over transient chat.
    durable_markers = (
        "my name is", "i am", "i'm", "i live in", "my location is", "i work",
        "my favorite", "i like ", "developer", "gus", "gustavo", "peims",
        "always", "never", "remember this", "learned_fact:",
    )
    has_number = bool(re.search(r"\b\d{2,}\b", t))
    if any(m in low for m in durable_markers) or has_number:
        return True, "durable_fact"

    # Keep only medium/long declarative statements by default.
    if len(t.split()) >= 8:
        return True, "long_statement"

    return False, "low_signal"


def mem_should_store(text: str) -> bool:
    keep, _reason = _memory_should_keep_text(text)
    return keep


def _memory_runtime_user() -> str | None:
    user = (get_active_user() or "").strip()
    if mem_scope() == "private" and not user:
        user = _default_local_user_id()
    if mem_scope() == "private" and not user:
        return None
    return user or None


def _format_memory_recall_hits(hits) -> str:
    bullets = []
    seen = set()
    norm = lambda s: re.sub(r"\W+", " ", (s or "").lower()).strip()
    for _score, _ts, _kind, _source, _user_row, text in (hits or []):
        p = (text or "").strip()
        if not p:
            continue
        one = re.sub(r"\s+", " ", p).strip()
        n = norm(one)
        if n in seen:
            continue
        seen.add(n)
        bullets.append(f"- {one[:260]}")
    bullets = bullets[:max(1, int(mem_context_top_k()))]
    return "\n".join(bullets)[:2000] if bullets else ""


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
        keep, _reason = _memory_should_keep_text(text)
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
    if "remember this" in low:
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

    return "I’m not sure based on the evidence I have in this session.", True, "unsupported_claim_blocked"


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
    s = (value or "").strip().lower()
    if not s:
        return ""

    if not re.match(r"^[a-z][a-z0-9+.-]*://", s):
        s = "https://" + s

    try:
        p = urlparse(s)
        host = (p.hostname or "").strip().lower()
    except Exception:
        return ""

    if not host:
        return ""

    # Basic host validation: labels with letters/numbers/hyphen, separated by dots.
    if not re.match(r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)(?:\.(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?))*$", host):
        return ""

    return host


def list_allowed_domains() -> str:
    allow_domains = list(policy_web().get("allow_domains") or [])
    if not allow_domains:
        return "No allowed domains are configured in policy.json."

    lines = ["Here are the domains I currently allow:"]
    for d in allow_domains:
        lines.append(f"- {d}")
    return "\n".join(lines)


def policy_allow_domain(value: str) -> str:
    host = _normalize_domain_input(value)
    if not host:
        _record_policy_change("allow_domain", value, "failed", "invalid_domain_input")
        return "Usage: policy allow <domain-or-url>"

    data = _load_policy_raw()
    web = data.get("web") if isinstance(data.get("web"), dict) else {}
    allow_domains = list(web.get("allow_domains") or [])

    existing = {str(x).strip().lower() for x in allow_domains if str(x).strip()}
    if host in existing:
        _record_policy_change("allow_domain", host, "skipped", "already_allowed")
        return f"Domain already allowed: {host}"

    allow_domains.append(host)
    web["allow_domains"] = allow_domains
    data["web"] = web
    _save_policy_raw(data)
    _record_policy_change("allow_domain", host, "success", "added_to_allow_domains")

    return f"Added allowed domain: {host}\n{list_allowed_domains()}"


def policy_remove_domain(value: str) -> str:
    host = _normalize_domain_input(value)
    if not host:
        _record_policy_change("remove_domain", value, "failed", "invalid_domain_input")
        return "Usage: policy remove <domain-or-url>"

    data = _load_policy_raw()
    web = data.get("web") if isinstance(data.get("web"), dict) else {}
    allow_domains = list(web.get("allow_domains") or [])

    kept = []
    removed = False
    for d in allow_domains:
        dd = str(d).strip()
        if dd.lower() == host:
            removed = True
            continue
        kept.append(dd)

    if not removed:
        _record_policy_change("remove_domain", host, "skipped", "not_found")
        return f"Domain not found in allowlist: {host}"

    web["allow_domains"] = kept
    data["web"] = web
    _save_policy_raw(data)
    _record_policy_change("remove_domain", host, "success", "removed_from_allow_domains")
    return f"Removed allowed domain: {host}\n{list_allowed_domains()}"


def policy_audit(limit: int = 20) -> str:
    n = max(1, min(200, int(limit or 20)))
    if not POLICY_AUDIT_LOG.exists():
        return "No policy audit entries yet."

    try:
        lines = [ln for ln in POLICY_AUDIT_LOG.read_text(encoding="utf-8").splitlines() if ln.strip()]
    except Exception as e:
        return f"Failed to read policy audit log: {e}"

    if not lines:
        return "No policy audit entries yet."

    rows = []
    for ln in lines[-n:]:
        try:
            rows.append(json.loads(ln))
        except Exception:
            continue
    if not rows:
        return "No parseable policy audit entries found."

    out = [f"Recent policy changes (last {len(rows)}):"]
    for r in rows:
        ts = int(r.get("ts") or 0)
        tstr = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts)) if ts else "unknown-time"
        user = str(r.get("user") or "unknown")
        action = str(r.get("action") or "")
        target = str(r.get("target") or "")
        result = str(r.get("result") or "")
        details = str(r.get("details") or "")
        out.append(f"- {tstr} user={user} action={action} target={target} result={result} details={details}")

    return "\n".join(out)


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
    m = (mode or "").strip().lower()
    if m in {"balanced", "default"}:
        m = "normal"
    if m in {"deep", "full", "maxinput"}:
        m = "max"

    if m not in WEB_RESEARCH_PRESETS:
        return "Usage: web mode <normal|max>"

    data = _load_policy_raw()
    web = data.get("web") if isinstance(data.get("web"), dict) else {}
    for k, v in WEB_RESEARCH_PRESETS[m].items():
        web[k] = v
    data["web"] = web
    _save_policy_raw(data)
    _record_policy_change("web_mode", m, "success", "updated_research_limits")
    return f"Web research mode set to {m}.\n" + web_mode_status()


def set_memory_scope(scope: str) -> str:
    value = (scope or "").strip().lower()
    aliases = {
        "per-user": "private",
        "user": "private",
        "global": "shared",
        "both": "hybrid",
    }
    value = aliases.get(value, value)
    if value not in {"private", "shared", "hybrid"}:
        return "Usage: memory scope <private|shared|hybrid>"

    data = _load_policy_raw()
    memory = data.get("memory") if isinstance(data.get("memory"), dict) else {}
    prev = str(memory.get("scope") or "private").strip().lower()
    memory["scope"] = value
    data["memory"] = memory
    _save_policy_raw(data)
    _record_policy_change("memory_scope", value, "success", f"from={prev}")
    return f"Memory scope set to {value}."


def get_search_provider() -> str:
    provider = str((policy_web().get("search_provider") or "html")).strip().lower()
    if provider not in {"html", "searxng"}:
        return "html"
    return provider


def set_search_provider(provider: str) -> str:
    p = (provider or "").strip().lower()
    if p in {"search", "web", "fallback", "default"}:
        p = "html"
    if p in {"searx", "searx-ng", "sxng"}:
        p = "searxng"

    if p not in {"html", "searxng"}:
        return "Usage: search provider <html|searxng>"

    data = _load_policy_raw()
    web = data.get("web") if isinstance(data.get("web"), dict) else {}
    tools = data.get("tools_enabled") if isinstance(data.get("tools_enabled"), dict) else {}
    prev = str(web.get("search_provider") or "html").strip().lower()
    web["search_provider"] = p
    # Operator intent: selecting a search provider should activate web path.
    web["enabled"] = True
    tools["web"] = True
    data["web"] = web
    data["tools_enabled"] = tools
    _save_policy_raw(data)
    _record_policy_change("search_provider", p, "success", f"from={prev}")

    endpoint = str(web.get("search_api_endpoint") or "").strip()
    if p == "searxng":
        if not endpoint:
            return (
                "Search provider set to searxng and web enabled. "
                "Configure web.search_api_endpoint in policy.json."
            )
        if endpoint.endswith(":8080/search"):
            return (
                "Search provider set to searxng and web enabled. "
                "Current endpoint is on Nova's own port (8080) and may return 404; set a real SearXNG endpoint."
            )
        return f"Search provider set to searxng and web enabled (endpoint: {endpoint})."

    return "Search provider set to html and web enabled."


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
        return f"{base_fact} He created me. I do not have detailed build-history notes in memory yet."

    if "who is" in low or "who's" in low or "creator" in low:
        if developer_nickname and developer_nickname.lower() != developer_name.lower():
            return f"My developer is {developer_name}. {developer_nickname} is his nickname. He created me."
        return f"My developer is {developer_name}. He created me."

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
        return " ".join([lead, base_fact] + extra_facts)
    return f"{lead} {base_fact} I don't have any additional verified information about him beyond that yet."


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
            return f"Based on the verified relation you gave me, Gus's location is {preview}."
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

    if kind == "location_recall":
        if _looks_like_contextual_followup(text):
            return True, _location_recall_reply(), state
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
    raw = (text or "").strip()
    if not raw:
        return raw, ""
    rule_result = TURN_SUPERVISOR.evaluate_rules(raw, turns=turns, phase="rewrite")
    rewrite_text = str(rule_result.get("rewrite_text") or "").strip()
    if rewrite_text:
        return rewrite_text, str(rule_result.get("analysis_reason") or rule_result.get("rule_name") or "")
    return raw, ""


def _is_explicit_command_like(text: str) -> bool:
    low = (text or "").strip().lower()
    if not low:
        return False
    command_prefixes = (
        "screen",
        "camera ",
        "web ",
        "weather",
        "check weather",
        "location coords",
        "domains",
        "policy allow",
        "chat context",
        "ls",
        "read ",
        "find ",
        "health",
        "capabilities",
        "inspect",
        "behavior ",
        "learning ",
        "memory ",
        "mem ",
    )
    return any(low == p.strip() or low.startswith(p) for p in command_prefixes)


def _determine_turn_direction(turns: list[tuple[str, str]], text: str) -> dict:
    effective_query, analysis_reason = _analyze_routing_text(turns, text)
    low = (effective_query or "").strip().lower()
    raw_low = (text or "").strip().lower()

    primary = "general_chat"
    if _is_negative_feedback(text):
        primary = "correction_feedback"
    elif _extract_memory_teach_text(text):
        primary = "memory_teach"
    elif _is_explicit_command_like(effective_query):
        primary = "explicit_command"
    elif _is_identity_or_developer_query(effective_query) or any(
        q in low for q in ["what do you know about me", "what else do you know about me", "what do you know about gus"]
    ):
        primary = "identity_query"
    elif _is_developer_color_lookup_request(effective_query) or _is_developer_bilingual_request(effective_query):
        primary = "identity_query"
    elif _is_color_lookup_request(effective_query):
        primary = "identity_query"
    elif bool(re.match(r"^i\s+am\s+([a-z][a-z '\-]{1,40})[.!?]*$", raw_low)):
        primary = "identity_binding"
    elif _is_declarative_info(text):
        if any(k in raw_low for k in ["my favorite", "my favourite", "creator", "developer", "gus", "gustavo"]):
            primary = "identity_teach"
        else:
            primary = "generic_declarative"
    elif _build_greeting_reply(effective_query, active_user=""):
        primary = "greeting"

    identity_focused = primary in {"identity_query", "identity_binding", "identity_teach"}
    bypass_pattern_routes = identity_focused and not _is_explicit_command_like(effective_query)
    return {
        "primary": primary,
        "effective_query": effective_query,
        "analysis_reason": analysis_reason,
        "identity_focused": identity_focused,
        "bypass_pattern_routes": bypass_pattern_routes,
    }


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


def ollama_api_up(timeout=2.0) -> bool:
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

    tokens = _topic_tokens(q)
    candidates = [p for p in KNOWLEDGE_ROOT.glob("**/*.txt") if p.is_file()]
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

    lines = ["I found relevant details in local knowledge files:"]
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
    low = _normalize_turn_text(text)
    if not low:
        return False
    if not (
        low.startswith(("what", "how", "when", "why", "which", "where", "who"))
        or "tell me about" in low
        or "what do you know about" in low
    ):
        return False
    if _is_peims_broad_query(low):
        return False
    topic_tokens = ("tsds", "attendance", "snapshot", "timeline", "submission", "reporting", "validation", "leaver")
    return any(tok in low for tok in topic_tokens)


def _build_local_peims_overview_answer() -> str:
    files = sorted(PEIMS_KNOWLEDGE_DIR.glob("*.txt"))
    if not files:
        return ""

    lines = ["I found PEIMS overview details in local knowledge files:"]
    facts_added = 0
    cited = set()

    for path in files:
        key_lines = _extract_key_lines(_read_text_safely(path), max_lines=2)
        for key_line in key_lines:
            lines.append(f"- {key_line}.")
            facts_added += 1
            cited.add(f"knowledge/peims/{path.name}")
            if facts_added >= 12:
                break
        if facts_added >= 12:
            break

    if facts_added == 0:
        return ""

    for cited_path in sorted(cited):
        lines.append(f"[source: {cited_path}]")
    return "\n".join(lines)


def _is_peims_broad_query(text: str) -> bool:
    low = _normalize_turn_text(text)
    if "peims" not in low:
        return False
    if "attendance" in low and any(token in low for token in ("rules", "requirements", "reporting", "what are", "tea say")):
        return False
    cues = (
        "all of peims",
        "all peims",
        "everything about peims",
        "as much information",
        "full peims",
        "peims overview",
        "what do you know about peims",
        "tell me about peims",
        "give me anything about peims",
        "know about peims",
    )
    return any(cue in low for cue in cues)


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


def _read_patch_manifest(zip_path: Path) -> Tuple[Optional[dict], Optional[str]]:
    try:
        with zipfile.ZipFile(zip_path, "r") as z:
            names = {n.replace("\\", "/").lstrip("/") for n in z.namelist()}
            if PATCH_MANIFEST_NAME not in names:
                return None, None
            raw = z.read(PATCH_MANIFEST_NAME)
            data = json.loads(raw.decode("utf-8", errors="replace"))
            if not isinstance(data, dict):
                return None, "Patch manifest must be a JSON object."
            return data, None
    except json.JSONDecodeError as e:
        return None, f"Invalid patch manifest JSON: {e}"
    except Exception as e:
        return None, f"Unable to read patch manifest: {e}"


def _snapshot_meta_path(snapshot_zip: Path) -> Path:
    return snapshot_zip.with_suffix(snapshot_zip.suffix + ".meta.json")


def _write_snapshot_meta(snapshot_zip: Path, revision: int):
    meta = {
        "revision": int(revision),
        "snapshot": snapshot_zip.name,
        "ts": time.time(),
    }
    _snapshot_meta_path(snapshot_zip).write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


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
    blocked_prefix = {".venv/", "runtime/", "logs/", "models/"}

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

    if next_revision is not None:
        _write_patch_revision(next_revision, source=z.name)

    _log_patch(f"APPLY_OK files={n}")
    rev_msg = f" Revision: {next_revision}." if next_revision is not None else ""
    return f"Patch applied: {n} file(s). Compile check OK. Snapshot: {snap.name}.{rev_msg}"


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
    skip_prefixes = ("runtime/", "logs/", "updates/", "piper/", "models/", "pkgconfig/")
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

    assistant_name = get_learned_fact("assistant_name", "Nova")
    developer_name = get_learned_fact("developer_name", "Gustavo")
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
        return f"My name was given by my developer, {developer_name} ({developer_nickname})."

    creator_query = (
        bool(re.search(r"\bwho\s+is\s+your\s+creator\b", t))
        or bool(re.search(r"\bwho\s+made\s+you\b", t))
        or bool(re.search(r"\bwho\s+created\s+you\b", t))
        or bool(re.search(r"\bso\s+gus\s+is\s+your\s+creator\b", t))
        or bool(re.search(r"\bis\s+(?:gus|gustavo)\s+your\s+creator\b", t))
    )
    if creator_query:
        if developer_nickname and developer_nickname.lower() != developer_name.lower():
            return f"My creator is {developer_name}. He created me. {developer_nickname} is his nickname."
        return f"My creator is {developer_name}. He created me."

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
            return f"My developer's full name is {developer_name}. {developer_nickname} is his nickname."
        return f"My developer's full name is {developer_name}."

    if any(k in t for k in ["what are your abilities", "what are you capable", "know what your capable", "know what you're capable", "what can you do"]):
        return describe_capabilities()

    if "what have you learned" in t:
        learned = load_learned_facts()
        learned_items = []
        for k in ["assistant_name", "developer_name", "developer_nickname"]:
            v = str(learned.get(k) or "").strip()
            if v:
                learned_items.append(f"{k}={v}")
        if not learned_items:
            return "I have not learned new persistent identity facts recently."
        return "Recent learned facts: " + ", ".join(learned_items) + "."

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


# =========================
# Ollama chat
# =========================
def ollama_chat(text: str, retrieved_context: str = "") -> str:
    """
    Deterministic chat wrapper: strict non-hallucination rules and low temperature.
    This function avoids injecting memory and enforces a constrained system prompt.
    """
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
        norm = lambda s: re.sub(r"\s+", " ", (s or "").strip())
        target = norm(reply)
        # Try semantic fuzzy match if memory embed utilities are available
        try:
            if memory_mod is not None and hasattr(memory_mod, "embed") and hasattr(memory_mod, "cosine"):
                tvec = memory_mod.embed(target)
                best = (0.0, None)
                with open(fn, "r", encoding="utf-8") as f:
                    for ln in f:
                        try:
                            j = json.loads(ln)
                            orig = norm(j.get("orig") or "")
                            corr = j.get("corr") or ""
                            if not orig:
                                continue
                            ovec = memory_mod.embed(orig)
                            sim = memory_mod.cosine(tvec, ovec)
                            if sim > best[0]:
                                best = (sim, corr)
                        except Exception:
                            continue
                # threshold for accepting a fuzzy override
                if best[0] >= 0.85 and best[1]:
                    return best[1]
        except Exception:
            pass

        # Fallback: exact normalized match
        with open(fn, "r", encoding="utf-8") as f:
            for ln in f:
                try:
                    j = json.loads(ln)
                    orig = norm(j.get("orig") or "")
                    corr = j.get("corr") or ""
                    if orig and orig == target:
                        return corr
                except Exception:
                    continue
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
        manifest = {
            "name": f"teach_proposal_{ts}",
            "desc": description or "Teach examples proposal",
            "rev": int(time.time()),
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

        # run tests in staging
        python_exe = PYTHON
        cmd = [python_exe, "-m", "unittest", "discover", "-v"]
        proc = subprocess.run(cmd, cwd=str(staging), capture_output=True, text=True, timeout=600)
        out = proc.stdout + "\n" + proc.stderr
        if proc.returncode != 0:
            # cleanup staging
            try:
                shutil.rmtree(staging)
            except Exception:
                pass
            return f"Tests failed in staging:\n{out}"

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
                "Staging tests passed. To apply this proposal to the live repo run:\n"
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
    if not VOICE_OK or sd is None:
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
    if not VOICE_OK or wav is None:
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


def execute_planned_action(tool: str, args=None):
    tool_name = str(tool or "").strip()
    tool_args = list(args) if isinstance(args, (list, tuple)) else ([] if args in {None, ""} else [args])

    if tool_name in {"web_fetch", "web_search", "web_research", "web_gather"}:
        value = tool_args[0] if tool_args else ""
        return execute_research_action(tool_name, str(value or ""))

    if tool_name == "weather_current_location":
        return _weather_for_saved_location()

    if tool_name == "weather_location":
        value = tool_args[0] if tool_args else ""
        return tool_weather(str(value or ""))

    if tool_name == "location_coords":
        value = tool_args[0] if tool_args else ""
        return set_location_coords(str(value or ""))

    tool_map = {
        "patch_apply": patch_apply,
        "patch_rollback": patch_rollback,
        "camera": tool_camera,
        "screen": tool_screen,
        "read": tool_read,
        "ls": tool_ls,
        "find": tool_find,
        "health": tool_health,
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


def tool_web(url: str):
    # capability awareness check
    missing = explain_missing("web_fetch", ["web_access"])
    if missing:
        return missing
    
    if not policy_tools_enabled().get("web", False):
        return "Web tool disabled by policy."
    out = web_fetch(url, WEB_CACHE_DIR)

    if not out.get("ok"):
        err = out.get("error", "unknown error")
        # If domain blocked by allowlist, provide helpful instructions
        if isinstance(err, str) and "not allowed" in err.lower():
            return _web_allowlist_message(url)
        return f"[FAIL] {err}"
    return f"[OK] Saved: {out['path']} ({out['content_type']}, {out['bytes']} bytes)"


def web_search(query: str, save_dir: Path, max_results: int = 5) -> dict:
    """
    Conservative web search using DuckDuckGo HTML interface.
    Saves a plain-text summary to `save_dir` and returns {ok, path, bytes}.
    This avoids JS-heavy scraping and does not require external deps.
    """
    if not web_enabled():
        return {"ok": False, "error": "Web tool disabled by policy."}

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
        endpoint = str(cfg.get("search_api_endpoint") or "http://127.0.0.1:8080/search").strip()
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
    global WEB_RESEARCH_LAST_QUERY, WEB_RESEARCH_LAST_RESULTS, WEB_RESEARCH_CURSOR

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
        if not WEB_RESEARCH_LAST_RESULTS:
            return "No active web research session. Start with: web research <query>"

        max_results = max(1, min(40, int((policy_web().get("research_max_results") or 8))))
        start = WEB_RESEARCH_CURSOR
        end = min(len(WEB_RESEARCH_LAST_RESULTS), start + max_results)
        if start >= len(WEB_RESEARCH_LAST_RESULTS):
            return "No more cached research results. Start a new search with: web research <query>"

        lines = [f"Web research results (continued) for: {WEB_RESEARCH_LAST_QUERY}"]
        rank = start
        for score, url, snippet in WEB_RESEARCH_LAST_RESULTS[start:end]:
            rank += 1
            lines.append(f"{rank}. [{score:.1f}] {url}")
            if snippet:
                lines.append(f"   {snippet[:220]}")

        WEB_RESEARCH_CURSOR = end
        if WEB_RESEARCH_CURSOR < len(WEB_RESEARCH_LAST_RESULTS):
            remaining = len(WEB_RESEARCH_LAST_RESULTS) - WEB_RESEARCH_CURSOR
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

    WEB_RESEARCH_LAST_QUERY = q
    WEB_RESEARCH_LAST_RESULTS = ordered
    WEB_RESEARCH_CURSOR = 0

    max_results = max(1, min(40, int((cfg.get("research_max_results") or 8))))
    start = WEB_RESEARCH_CURSOR
    end = min(len(WEB_RESEARCH_LAST_RESULTS), start + max_results)

    lines = [f"Web research results (allowlisted crawl) for: {q}"]
    rank = start
    for score, url, snippet in WEB_RESEARCH_LAST_RESULTS[start:end]:
        rank += 1
        lines.append(f"{rank}. [{score:.1f}] {url}")
        if snippet:
            lines.append(f"   {snippet[:220]}")

    WEB_RESEARCH_CURSOR = end
    if WEB_RESEARCH_CURSOR < len(WEB_RESEARCH_LAST_RESULTS):
        remaining = len(WEB_RESEARCH_LAST_RESULTS) - WEB_RESEARCH_CURSOR
        lines.append(f"{remaining} more result(s) available. Type 'web continue' to keep going.")
    else:
        lines.append("No more results pending for this query.")

    lines.append("Tip: run 'web gather <url>' for any source above to fetch and summarize it fully.")
    return "\n".join(lines)


def handle_keywords(text: str):
    low = text.lower().strip()

    if low in {"screen", "look at my screen"}:
        return ("tool", "screen", tool_screen())

    if low.startswith("camera"):
        prompt = text[len("camera"):].strip() or "what do you see"
        return ("tool", "camera", tool_camera(prompt))

    if low.startswith("web research "):
        q = text.split(maxsplit=2)[2].strip() if len(text.split(maxsplit=2)) >= 3 else ""
        return ("tool", "web_research", execute_research_action("web_research", q))

    if low in {"web continue", "continue web", "continue web research"}:
        return ("tool", "web_research", tool_web_research("", continue_mode=True))

    if low.startswith("web search "):
        q = text.split(maxsplit=2)[2].strip() if len(text.split(maxsplit=2)) >= 3 else ""
        return ("tool", "web_search", execute_research_action("web_search", q))

    # shorthand: `search <query>` -> conservative DuckDuckGo search (saves summary)
    if low.startswith("search "):
        q = text.split(maxsplit=1)[1].strip() if len(text.split(maxsplit=1)) >= 2 else ""
        return ("tool", "search", tool_search(q))

    # shorthand: `findweb <query>` -> quick allowlisted web search (returns URLs)
    if low.startswith("findweb "):
        q = text.split(maxsplit=1)[1].strip() if len(text.split(maxsplit=1)) >= 2 else ""
        return ("tool", "web_search", execute_research_action("web_search", q))

    if low.startswith("web gather "):
        url = text.split(maxsplit=2)[2].strip() if len(text.split(maxsplit=2)) >= 3 else ""
        return ("tool", "web_gather", execute_research_action("web_gather", url))

    if low.startswith("web "):
        url = text.split(maxsplit=1)[1].strip()
        return ("tool", "web_fetch", execute_research_action("web_fetch", url))

    if low.startswith("ls"):
        parts = text.split(maxsplit=1)
        sub = parts[1] if len(parts) > 1 else ""
        return ("tool", "ls", tool_ls(sub))

    if low.startswith("read "):
        path = text.split(maxsplit=1)[1]
        return ("tool", "read", tool_read(path))

    if low.startswith("find "):
        parts = text.split(maxsplit=2)
        keyword = parts[1] if len(parts) > 1 else ""
        folder = parts[2] if len(parts) > 2 else ""
        return ("tool", "find", tool_find(keyword, folder))

    if low in {"health", "status"}:
        return ("tool", "health", tool_health())

    return None


# =========================
# Commands (typed) for kb / patch
# =========================
def handle_commands(user_text: str, session_turns: Optional[list[tuple[str, str]]] = None) -> Optional[str]:
    t = _strip_invocation_prefix((user_text or "").strip())
    low = t.lower()

    # Natural follow-up variants such as "use your location nova" should resolve deterministically.
    if ("use your" in low or low.startswith("use ")) and _mentions_location_phrase(low):
        return _weather_for_saved_location()

    if low in {"use your physical location", "use your location", "use default location", "default location"}:
        return _weather_for_saved_location()

    # Natural weather requests should stay deterministic and not fall through to LLM.
    if "weather" in low and not low.startswith("web "):
        if "your" in low and _mentions_location_phrase(low):
            return _weather_for_saved_location()
        if "there" in low or "that location" in low:
            return _weather_for_saved_location()
        if any(p in low for p in ["give me", "check", "show", "tell me", "what is", "what's", "today", "now", "current"]):
            return _weather_for_saved_location()

    if low in {"chat context", "show chat context", "context", "chatctx"}:
        rendered = _render_chat_context(session_turns or [])
        if not rendered:
            return "No chat context is available yet in this session."
        return "Current chat context:\n" + rendered

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
        raw = t
        if low.startswith("set location coords "):
            raw = t[len("set location coords "):].strip()
        else:
            raw = t[len("location coords "):].strip()
        return set_location_coords(raw)

    if low in {"weather", "check weather", "weather current location", "weather current"}:
        return _weather_for_saved_location()

    if low.startswith("weather ") or low.startswith("check weather "):
        parts = t.split(maxsplit=2)
        loc = ""
        if low.startswith("check weather ") and len(parts) >= 3:
            loc = parts[2].strip()
        elif low.startswith("weather ") and len(parts) >= 2:
            loc = t.split(maxsplit=1)[1].strip()
        return tool_weather(loc)

    if low.startswith("remember:"):
        return mem_remember_fact(t.split(":", 1)[1])

    if low in {"what can you do", "capabilities", "show capabilities"}:
        return describe_capabilities()

    if low in {"mem stats", "memory stats"}:
        return mem_stats()

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
    if VOICE_OK and WhisperModel is not None:
        print("Nova Core: loading Whisper (CPU mode)...", flush=True)
        whisper = WhisperModel(whisper_size(), device="cpu", compute_type="int8")
    else:
        warn(f"Voice mode disabled; typed chat still works. (Reason: {VOICE_IMPORT_ERR})")

    print("\nNova Core is ready.", flush=True)
    print("Commands: screen | camera <prompt> | web <url> | web search <query> | web research <query> | web gather <url> | weather <location-or-lat,lon> | check weather <location> | weather current location | location coords <lat,lon> | domains | policy allow <domain> | chat context | ls [folder] | read <file> | find <kw> [folder] | health | capabilities | inspect", flush=True)
    print("Press ENTER for voice. Or type a message/command and press ENTER. Type 'q' to quit.\n", flush=True)

    recent_tool_context = ""
    recent_web_urls: list[str] = []
    session_turns: list[tuple[str, str]] = []
    session_state = ConversationSession()
    pending_correction_for: Optional[str] = None
    pending_action_ledger: Optional[dict] = None
    pending_action: Optional[dict] = session_state.pending_action
    conversation_state: Optional[dict] = session_state.conversation_state
    prefer_web_for_data_queries = session_state.prefer_web_for_data_queries

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
                    "grounded": pending_action_ledger.get("grounded") if isinstance(pending_action_ledger.get("grounded"), bool) else None,
                    "active_subject": str(pending_action_ledger.get("active_subject") or session_state.active_subject() or ""),
                    "continuation_used": bool(pending_action_ledger.get("continuation_used", False)),
                    "pending_action": session_state.pending_action,
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

        # If a prior answer was flagged as wrong, learn from the next authoritative user statement.
        try:
            if pending_correction_for:
                corr = _extract_authoritative_correction_text(user_text)
                if corr:
                    _trace("correction_capture", "applied", "user supplied authoritative correction")
                    corr_store = _normalize_correction_for_storage(corr)
                    _teach_store_example(pending_correction_for, corr_store, user=get_active_user() or None)
                    behavior_record_event("correction_applied")
                    ack = "Understood. I corrected that and will use your version going forward."
                    print(f"Nova: {ack}\n", flush=True)
                    session_turns.append(("assistant", ack))
                    speak_chunked(tts, ack)
                    pending_correction_for = None
                    continue
        except Exception:
            pass

        routed_user_text = user_text
        turn_direction = {
            "primary": "general_chat",
            "effective_query": user_text,
            "analysis_reason": "",
            "identity_focused": False,
            "bypass_pattern_routes": False,
        }
        try:
            turn_direction = _determine_turn_direction(session_turns, user_text)
            routed_user_text = str(turn_direction.get("effective_query") or user_text)
            _trace(
                "direction_analysis",
                str(turn_direction.get("primary") or "general_chat"),
                str(turn_direction.get("analysis_reason") or "")[:120],
                effective_query=routed_user_text[:180],
                identity_focused=bool(turn_direction.get("identity_focused")),
                bypass_pattern_routes=bool(turn_direction.get("bypass_pattern_routes")),
            )
        except Exception:
            routed_user_text = user_text

        intent_rule = TURN_SUPERVISOR.evaluate_rules(
            routed_user_text,
            manager=session_state,
            turns=session_turns,
            phase="intent",
            entry_point="cli",
        )
        handled_intent, intent_msg = _handle_supervisor_intent(
            intent_rule,
            routed_user_text,
            turns=session_turns,
            input_source=input_source,
        )
        if handled_intent:
            _emit_supervisor_intent_trace(intent_rule, user_text=routed_user_text)
            final = _ensure_reply(intent_msg)
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

        # Detect broad negative feedback and either learn immediate correction text
        # or mark the prior assistant answer as pending correction.
        try:
            if _is_negative_feedback(user_text):
                last_assistant = None
                for role, txt in reversed(session_turns[:-1]):
                    if role == "assistant":
                        last_assistant = txt
                        break
                if last_assistant:
                    corr = _extract_authoritative_correction_text(user_text)
                    if corr:
                        _trace("correction_feedback", "learned", "negative feedback included replacement")
                        corr_store = _normalize_correction_for_storage(corr)
                        _teach_store_example(last_assistant, corr_store, user=get_active_user() or None)
                        behavior_record_event("correction_learned")
                        ack = "You're right. I saved your correction and will use it next time."
                        print(f"Nova: {ack}\n", flush=True)
                        session_turns.append(("assistant", ack))
                        speak_chunked(tts, ack)
                        continue
                    pending_correction_for = last_assistant
                    _trace("correction_feedback", "pending", "awaiting exact corrected answer")
                    ack = "You're right. Give me the exact corrected answer and I will learn it now."
                    print(f"Nova: {ack}\n", flush=True)
                    session_turns.append(("assistant", ack))
                    speak_chunked(tts, ack)
                    continue
        except Exception:
            pass

        # Learn explicit user corrections as structured facts before any planner/tool routing.
        try:
            if _is_web_research_override_request(user_text):
                _set_prefer_web_for_data_queries(True)
                _trace("routing_override", "enabled", "session prefers web research for data-domain queries")
                ack = "Understood. For this session, I will prefer web research for PEIMS and similar data-domain questions instead of a database route."
                print(f"Nova: {ack}\n", flush=True)
                session_turns.append(("assistant", ack))
                speak_chunked(tts, ack)
                continue

            learned, learned_msg = learn_from_user_correction(user_text)
            if learned:
                _trace("correction_learning", "stored", "structured fact learned from user correction")
                final = _ensure_reply(learned_msg)
                print(f"Nova: {final}\n", flush=True)
                session_turns.append(("assistant", final))
                speak_chunked(tts, final)
                continue
        except Exception:
            pass

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

        try:
            memory_teach = _extract_memory_teach_text(user_text)
            if memory_teach and mem_enabled():
                _trace("declarative_memory", "stored", "captured explicit memory teaching")
                mem_add("fact", input_source, memory_teach)
                final = _ensure_reply("Yes. I stored that for future context.")
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
        handled_rule, rule_msg, rule_state = _execute_registered_supervisor_rule(
            general_rule,
            user_text,
            conversation_state,
            turns=session_turns,
            input_source=input_source,
            allowed_actions={"name_origin_store", "self_location"},
        )
        if handled_rule:
            try:
                final = _apply_reply_overrides(rule_msg)
            except Exception:
                final = rule_msg
            final = _ensure_reply(final)
            if isinstance(rule_state, dict):
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
            _sync_pending_conversation_tracking()
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

        # Interactive correction capture: if the user provides a correction like
        # "no — say 'Hi Gus' instead" or "say 'Hi Gus' instead", store it as a teach example.
        try:
            corr_text = (user_text or "").strip()
            # find last assistant message
            last_assistant = None
            for role, txt in reversed(session_turns[:-1]):
                if role == "assistant":
                    last_assistant = txt
                    break

            if last_assistant:
                corr = _parse_correction(corr_text)
                if corr:
                    _trace("teach_override", "stored", "interactive correction example captured")
                    corr_store = _normalize_correction_for_storage(corr)
                    _teach_store_example(last_assistant, corr_store, user=get_active_user() or None)
                    behavior_record_event("correction_learned")
                    ack = "Thanks — I'll prefer that reply in future. I've stored the example."
                    print(f"Nova: {ack}\n", flush=True)
                    session_turns.append(("assistant", ack))
                    speak_chunked(tts, ack)
                    pending_correction_for = None
                    continue
        except Exception:
            pass

        # Quick greeting fast-path (avoid LLM for simple salutations)
        try:
            low_q = (routed_user_text or "").strip().lower()
            msg = _build_greeting_reply(low_q, active_user=get_active_user() or "")
            if msg:

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
            id_m = re.match(r"^(?:my name is|my name's|call me|you can call me|this is)\s+(.+)$", user_text.strip(), flags=re.I)
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

            if _is_location_recall_state(conversation_state) and _looks_like_contextual_followup(routed_user_text):
                msg = _location_recall_reply()
                try:
                    final = _apply_reply_overrides(msg)
                except Exception:
                    final = msg
                final = _ensure_reply(final)
                print(f"Nova: {final}\n", flush=True)
                session_turns.append(("assistant", final))
                speak_chunked(tts, final)
                continue

            if _looks_like_location_recall_followup(session_turns, routed_user_text):
                msg = _location_recall_reply()
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

            if _is_location_recall_query(routed_user_text):
                msg = _location_recall_reply()
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

        # Treat declarative info (not requests) as facts to store and acknowledge.
        try:
            location_fact = _extract_location_fact(user_text)
            if location_fact:
                set_location_text(location_fact, input_source=input_source)
                ack = "Noted."
                print(f"Nova: {ack}\n", flush=True)
                session_turns.append(("assistant", ack))
                speak_chunked(tts, ack)
                continue
            if _is_declarative_info(user_text):
                if mem_should_store(user_text):
                    mem_add("fact", input_source, user_text)
                # Soften casual acknowledgements
                ack = "Noted."
                print(f"Nova: {ack}\n", flush=True)
                session_turns.append(("assistant", ack))
                speak_chunked(tts, ack)
                continue
        except Exception:
            pass

        # Reason-first action selection: let the planner choose clarify vs tool
        # before legacy command/keyword handlers execute side effects.
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
                cmd_out = handle_commands(routed_user_text, session_turns=session_turns)
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
                        next_retrieval_state = _make_retrieval_conversation_state(str(routed_tool or ""), _retrieval_query_from_text(str(routed_tool or ""), routed_user_text), out)
                        if next_retrieval_state is not None:
                            session_state.set_retrieval_state(next_retrieval_state)
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
                    next_retrieval_state = _make_retrieval_conversation_state(str(tool or ""), str(query_text or ""), out)
                    if next_retrieval_state is not None:
                        session_state.set_retrieval_state(next_retrieval_state)
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

        if _is_peims_broad_query(routed_user_text):
            local_overview = _build_local_peims_overview_answer()
            if local_overview:
                behavior_record_event("deterministic_hit")
                _trace("grounded_lookup", "matched", tool="local_knowledge")
                if pending_action_ledger is not None:
                    pending_action_ledger["planner_decision"] = "grounded_lookup"
                    pending_action_ledger["tool"] = "local_knowledge"
                    pending_action_ledger["tool_args"] = {"query": user_text}
                    pending_action_ledger["tool_result"] = local_overview
                    pending_action_ledger["grounded"] = True
                print(f"Nova: {local_overview}\n", flush=True)
                session_turns.append(("assistant", local_overview))
                speak_chunked(tts, local_overview)
                continue
            _trace("grounded_lookup", "missed", tool="local_knowledge")

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

        context_details = build_learning_context_details(routed_user_text)
        retrieved_context = str(context_details.get("context") or "")
        _trace(
            "memory_context",
            "used" if retrieved_context else "empty",
            memory_used=bool(context_details.get("memory_used")),
            knowledge_used=bool(context_details.get("knowledge_used")),
            memory_chars=int(context_details.get("memory_chars") or 0),
            knowledge_chars=int(context_details.get("knowledge_chars") or 0),
        )
        chat_ctx = _render_chat_context(session_turns)
        if chat_ctx:
            retrieved_context = (retrieved_context + "\n\nCURRENT CHAT CONTEXT:\n" + chat_ctx).strip()[:6000]
            _trace("chat_context", "used", chars=len(chat_ctx))
        session_fact_sheet = _build_session_fact_sheet(session_turns)
        if session_fact_sheet:
            retrieved_context = (retrieved_context + "\n\nSESSION FACT SHEET:\n" + session_fact_sheet).strip()[:6000]
            _trace("session_fact_sheet", "used", chars=len(session_fact_sheet))
        if recent_tool_context and _uses_prior_reference(routed_user_text):
            retrieved_context = (retrieved_context + "\n\nRECENT TOOL OUTPUT:\n" + recent_tool_context).strip()[:6000]
            _trace("recent_tool_context", "used", chars=len(recent_tool_context))

        if should_block_low_confidence(routed_user_text, retrieved_context=retrieved_context, tool_context=recent_tool_context):
            behavior_record_event("low_confidence_block")
            _trace("low_confidence_gate", "blocked")
            if pending_action_ledger is not None:
                pending_action_ledger["planner_decision"] = "blocked_low_confidence"
                pending_action_ledger["grounded"] = False
            msg = "Uncertain. I do not have enough grounded context to answer that reliably yet."
            final = _ensure_reply(msg)
            print(f"Nova: {final}\n", flush=True)
            session_turns.append(("assistant", final))
            speak_chunked(tts, final)
            continue

        behavior_record_event("llm_fallback")
        _trace("llm_fallback", "invoked", retrieved_chars=len(retrieved_context))
        if pending_action_ledger is not None:
            pending_action_ledger["planner_decision"] = "llm_fallback"
        reply = ollama_chat(routed_user_text, retrieved_context=retrieved_context)
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
