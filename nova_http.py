"""
Nova HTTP runtime — operator control room and Leah web UI (port 8080).

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

import hashlib
import json
import os
import re
import secrets
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Mapping, Tuple
from urllib.parse import parse_qs, urlparse

import nova_core
import psutil
import requests
import work_tree
import capabilities as capabilities_mod
import http_chat_flow
import http_session_store
from conversation_manager import ConversationManager
from services.control_assets import CONTROL_ASSETS_SERVICE
from services.control_actions import CONTROL_ACTIONS_SERVICE
from services.control_auth import CONTROL_AUTH_SERVICE
from services.control_telemetry import ControlTelemetryService
from services.control_status import CONTROL_STATUS_SERVICE
from services.control_status_cache import CONTROL_STATUS_CACHE_SERVICE
from services.control_pipelines import CONTROL_PIPELINES_SERVICE
from services.chat_identity import CHAT_IDENTITY_SERVICE
from services.control_login_frontdoor import CONTROL_LOGIN_FRONTDOOR_SERVICE
from services.control_work_trees import CONTROL_WORK_TREES_SERVICE
from services.leah_frontdoor import LeahFrontdoorService
from services.leah_conversation_continuity import LeahConversationContinuityStore
from services.leah_memory_recall import LeahMemoryRecallService
from services.leah_voice_persona_engine import LEAH_VOICE_PERSONA_ENGINE_SERVICE
from services.leah_emotional_state_model import LEAH_EMOTIONAL_STATE_MODEL_SERVICE
from services.nova_control_action_dispatcher import NOVA_CONTROL_ACTION_DISPATCHER
from services.nova_http_get_routes import HTTP_GET_ROUTES_SERVICE
from services.nova_http_frontdoor import NOVA_HTTP_FRONTDOOR_SERVICE
from services.nova_http_generated_work import HTTP_GENERATED_WORK_SERVICE
from services.nova_http_pipeline_control import HTTP_PIPELINE_CONTROL_SERVICE
from services.nova_http_policy_search import HTTP_POLICY_SEARCH_SERVICE
from services.nova_http_post_dispatch import HTTP_POST_DISPATCH_SERVICE
from services.nova_http_request_binding import HTTP_REQUEST_BINDING_SERVICE
from services.nova_http_responses import HTTP_RESPONSE_SERVICE
from services.nova_http_transport import HTTP_TRANSPORT_SERVICE
from services.operator_control import OPERATOR_CONTROL_SERVICE
from services.patch_control import PATCH_CONTROL_SERVICE
from services.nova_http_chat_runtime import HTTP_CHAT_RUNTIME_SERVICE
from services.nova_http_control_surface import HTTP_CONTROL_SURFACE_SERVICE
from services.nova_http_turn_finalization import HTTP_TURN_FINALIZATION_SERVICE
from services.nova_reply_sequence import execute_http_reply_sequence_from_runtime
from services.storage_watch import STORAGE_WATCH_SERVICE
from services.release_status import RELEASE_STATUS_SERVICE
from services.runtime_analytics import RUNTIME_ANALYTICS_SERVICE
from services.runtime_artifacts import RUNTIME_ARTIFACTS_SERVICE
from services.runtime_control import RUNTIME_CONTROL_SERVICE
from services.runtime_process_state import RUNTIME_PROCESS_STATE_SERVICE
from services.runtime_restart_provenance import RUNTIME_RESTART_PROVENANCE_SERVICE
from services.runtime_status import RUNTIME_STATUS_SERVICE
from services.runtime_timeline import RUNTIME_TIMELINE_SERVICE
from services.os_script_controller import OS_SCRIPT_CONTROLLER_SERVICE
from services.validation_artifact_truth import VALIDATION_ARTIFACT_TRUTH_SERVICE
from services.port_ownership import PORT_OWNERSHIP_SERVICE
from services.autonomy_orchestrator_ledger import AUTONOMY_ORCHESTRATOR_LEDGER_SERVICE
from services.nova_runtime_context import AUTONOMY_ORCHESTRATOR_LEDGER_FILE
from services.nova_runtime_context import OS_CAPABILITY_LEDGER_FILE
from services.nova_runtime_context import OPERATOR_OUTBOX_FILE
from services.nova_runtime_context import WORK_TREE_RUN_TRIGGER_FILE
from services.nova_runtime_context import PATCH_QUEUE_RUN_TRIGGER_FILE
from services.nova_runtime_context import TEMPORAL_CALENDAR_FILE
from services.nova_calendar_ingestion import (
    read_calendar_events,
    write_calendar_event,
    delete_calendar_event,
)
from services.nova_runtime_context import resolve_runtime_dir
from services.operator_outbox import OPERATOR_OUTBOX_SERVICE
from services.session_admin import SESSION_ADMIN_SERVICE
from services.data_pipeline_registry import get_pipeline_schema_probe as pipeline_get_schema_probe
from services.data_pipeline_registry import get_pipeline_status as pipeline_get_status
from services.data_pipeline_registry import list_pipeline_summaries as pipeline_list_summaries
from services.data_pipeline_registry import preview_pipeline_query
from services.data_pipeline_registry import run_governed_live_pipeline_query as run_pipeline_query
from services.generated_work_queue_snapshot import generated_work_queue_payload as service_generated_work_queue_payload
from services.subconscious_control import SUBCONSCIOUS_CONTROL_SERVICE
from services.test_session_control import TEST_SESSION_CONTROL_SERVICE
from services.subconscious_runtime import SUBCONSCIOUS_SERVICE
from services.runtime_console_frontdoor import RUNTIME_CONSOLE_FRONTDOOR_SERVICE
import tools.runtime_processes as runtime_processes


SESSION_TURNS: Dict[str, List[Tuple[str, str]]] = {}
SESSION_OWNERS: Dict[str, str] = {}
SESSION_STATE_MANAGER = ConversationManager()
MAX_TURNS = 40
BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
CONTROL_TEMPLATE_PATH = TEMPLATES_DIR / "control.html"
CONTROL_CSS_PATH = STATIC_DIR / "control.css"
CONTROL_JS_PATH = STATIC_DIR / "control.js"
LEAH_TEMPLATE_PATH = TEMPLATES_DIR / "leah.html"
LEAH_CSS_PATH = STATIC_DIR / "leah.css"
LEAH_JS_PATH = STATIC_DIR / "leah.js"
LEAH_FX_JS_PATH = STATIC_DIR / "leah_fx.js"
SCRIPTS_DIR = BASE_DIR / "scripts"
LOG_DIR = BASE_DIR / "logs"
RUNTIME_DIR = resolve_runtime_dir(BASE_DIR)
LEAH_UPLOADS_DIR = RUNTIME_DIR / "leah_uploads"
SESSION_STORE_PATH = RUNTIME_DIR / "http_chat_sessions.json"
MAX_STORED_SESSIONS = 120
MAX_STORED_TURNS_PER_SESSION = MAX_TURNS * 2
KNOWLEDGE_DIR = BASE_DIR / "knowledge"
DATA_SOURCES_DIR = BASE_DIR / "data_sources"
LEAH_FRONTDOOR_SERVICE = LeahFrontdoorService(
    asset_service=CONTROL_ASSETS_SERVICE,
    template_path_provider=lambda: LEAH_TEMPLATE_PATH,
    css_path_provider=lambda: LEAH_CSS_PATH,
    js_path_provider=lambda: LEAH_JS_PATH,
    fx_js_path_provider=lambda: LEAH_FX_JS_PATH,
    upload_root_provider=lambda: LEAH_UPLOADS_DIR,
    continuity_store=LeahConversationContinuityStore(),
)
LEAH_MEMORY_RECALL_SERVICE = LeahMemoryRecallService(
    mem_recall_fn=nova_core.mem_recall,
    mem_enabled_fn=nova_core.mem_enabled,
)


def _resolve_venv_python() -> Path:
    candidates = [
        BASE_DIR / ".venv" / "Scripts" / "python.exe",
        BASE_DIR / ".venv" / "bin" / "python",
    ]
    for path in candidates:
        if path.exists():
            return path
    return Path(sys.executable).resolve()


VENV_PY = _resolve_venv_python()
GUARD_PY = BASE_DIR / "nova_guard.py"
STOP_GUARD_PY = BASE_DIR / "stop_guard.py"
CORE_PY = BASE_DIR / "nova_core.py"
HTTP_PY = BASE_DIR / "nova_http.py"
AUTONOMY_MAINTENANCE_PY = BASE_DIR / "autonomy_maintenance.py"
TEST_SESSION_RUNNER_PY = SCRIPTS_DIR / "run_test_session.py"
EXPORT_DIR = RUNTIME_DIR / "exports"
RELEASE_PACKAGES_DIR = EXPORT_DIR / "release_packages"
RELEASE_LEDGER_PATH = RELEASE_PACKAGES_DIR / "release_ledger.jsonl"
CONTROL_AUDIT_LOG = RUNTIME_DIR / "control_action_audit.jsonl"
TOOL_EVENTS_LOG = RUNTIME_DIR / "tool_events.jsonl"
MEMORY_EVENTS_LOG = RUNTIME_DIR / "memory_events.jsonl"
GUARD_LOG_PATH = LOG_DIR / "guard.log"
GUARD_BOOT_HISTORY_PATH = RUNTIME_DIR / "guard_boot_history.json"
RESTART_INTENT_PATH = RUNTIME_DIR / "restart_intent.json"

CONTROL_SESSIONS: Dict[str, float] = {}
CONTROL_SESSION_TTL_SECONDS = 8 * 60 * 60
CHAT_SESSIONS: Dict[str, tuple[str, float]] = {}
CHAT_SESSION_TTL_SECONDS = 8 * 60 * 60
CHAT_PASSWORD_HASH_ITERATIONS = 120000
PROCESS_SCAN_CACHE_TTL_SECONDS = 5.0
_PROCESS_SCAN_CACHE: Dict[str, tuple[float, list[dict]]] = {}
CONTROL_STATUS_CACHE_TTL_SECONDS = 8.0
CONTROL_STATUS_SURFACES_CACHE_TTL_SECONDS = 8.0
_CONTROL_STATUS_CACHE_LOCK = threading.Lock()
_CONTROL_STATUS_SURFACES_CACHE_LOCK = threading.Lock()
_CONTROL_STATUS_CACHE: Dict[str, Any] = {"computed_at": 0.0, "payload": None}
_CONTROL_STATUS_SURFACES_CACHE: Dict[str, Any] = {"computed_at": 0.0, "payload": None}
AUTONOMY_MAINTENANCE_STATE_PATH = RUNTIME_DIR / "autonomy_maintenance_state.json"
try:
    SEARXNG_STATUS_TIMEOUT_SEC = max(5.0, float(os.environ.get("NOVA_SEARXNG_STATUS_TIMEOUT_SEC", "5.0")))
except Exception:
    SEARXNG_STATUS_TIMEOUT_SEC = 5.0
SEARXNG_STATUS_CANDIDATE_LIMIT = 2
STORAGE_WATCH_CACHE_TTL_SECONDS = 20.0
_STORAGE_WATCH_CACHE_LOCK = threading.Lock()
_STORAGE_WATCH_CACHE: Dict[str, Any] = {"computed_at": 0.0, "payload": None}


def _invalidate_control_status_cache() -> None:
    CONTROL_STATUS_CACHE_SERVICE.invalidate(_CONTROL_STATUS_CACHE, lock=_CONTROL_STATUS_CACHE_LOCK)
    CONTROL_STATUS_CACHE_SERVICE.invalidate(_CONTROL_STATUS_SURFACES_CACHE, lock=_CONTROL_STATUS_SURFACES_CACHE_LOCK)


def _load_autonomy_maintenance_state() -> dict:
    try:
        payload = json.loads(AUTONOMY_MAINTENANCE_STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        payload = {}
    return payload if isinstance(payload, dict) else {}


class _StatusRuntimeProcessesModule:
    """Bound process evidence for status assembly without changing control actions."""

    @staticmethod
    def logical_service_processes(script_path: str | Path) -> list[dict[str, Any]]:
        try:
            resolved = str(Path(script_path).resolve())
        except Exception:
            resolved = str(script_path)
        cache_key = f"status-runtime-processes:{resolved.lower()}"
        now = time.monotonic()
        cached = _PROCESS_SCAN_CACHE.get(cache_key)
        if cached and now - float(cached[0]) <= PROCESS_SCAN_CACHE_TTL_SECONDS:
            return [dict(item) for item in cached[1]]
        processes = runtime_processes.logical_service_processes(script_path)
        _PROCESS_SCAN_CACHE[cache_key] = (now, [dict(item) for item in processes])
        return processes

    @staticmethod
    def select_logical_process(
        processes: list[dict[str, Any]],
        *,
        pid: int | None = None,
        create_time: float | None = None,
    ) -> dict[str, Any] | None:
        return runtime_processes.select_logical_process(processes, pid=pid, create_time=create_time)


_STATUS_RUNTIME_PROCESSES = _StatusRuntimeProcessesModule()


def _status_runtime_processes_module() -> _StatusRuntimeProcessesModule:
    return _STATUS_RUNTIME_PROCESSES


def _autonomy_maintenance_summary() -> dict:
    payload = RUNTIME_CONTROL_SERVICE.autonomy_maintenance_summary(
        state_payload=_load_autonomy_maintenance_state(),
        maintenance_py=AUTONOMY_MAINTENANCE_PY,
        runtime_processes_module=_status_runtime_processes_module(),
        strftime_fn=time.strftime,
    )
    payload["autonomy_orchestrator_summary"] = AUTONOMY_ORCHESTRATOR_LEDGER_SERVICE.summary(
        AUTONOMY_ORCHESTRATOR_LEDGER_FILE,
        limit=80,
    )
    return payload

_METRICS_LOCK = threading.Lock()
_HTTP_REQUESTS_TOTAL = 0
_HTTP_ERRORS_TOTAL = 0
_METRICS_SERIES: List[dict] = []
_METRICS_MAX_POINTS = 240
_SESSION_LOCK = threading.Lock()
_HTTP_SERVER: ThreadingHTTPServer | None = None
_HTTP_BIND_HOST = "127.0.0.1"
_HTTP_BIND_PORT = 8080


def _record_control_action_event(action: str, result: str, detail: str = "", payload: dict | None = None) -> None:
    _control_telemetry_service().record_control_action_event(
        RUNTIME_DIR,
        CONTROL_AUDIT_LOG,
        action,
        result,
        detail,
        payload,
    )


def _safe_tail_lines(path: Path, n: int = 80) -> list[str]:
    return _control_telemetry_service().safe_tail_lines(path, tail_file_fn=_tail_file, n=n)


def _read_asset_text(path: Path) -> str:
    return CONTROL_ASSETS_SERVICE.read_asset_text(path)


def _asset_version_token(path: Path) -> str:
    return CONTROL_ASSETS_SERVICE.asset_version_token(path)


def _render_control_html() -> str:
    return CONTROL_ASSETS_SERVICE.render_control_html(CONTROL_TEMPLATE_PATH, CONTROL_CSS_PATH, CONTROL_JS_PATH)


def _render_control_login_html() -> str:
    return CONTROL_LOGIN_FRONTDOOR_SERVICE.render_html()


def _render_leah_html() -> str:
    return LEAH_FRONTDOOR_SERVICE.render_html()


def _render_runtime_console_html() -> str:
    return RUNTIME_CONSOLE_FRONTDOOR_SERVICE.render_html()


def http_route_contract() -> dict[str, tuple[str, ...]]:
    return NOVA_HTTP_FRONTDOOR_SERVICE.route_contract_from_runtime(globals())


def _control_telemetry_service() -> ControlTelemetryService:
    return ControlTelemetryService(list_capabilities_fn=capabilities_mod.list_capabilities)


def _action_ledger_summary(limit: int = 60) -> dict:
    return _control_telemetry_service().action_ledger_summary(
        nova_core.ACTION_LEDGER_DIR,
        nova_core.action_ledger_route_summary,
        limit=limit,
    )


def _provider_telemetry_payload(*, ledger_summary: dict, tool_summary: dict) -> dict:
    return _control_telemetry_service().provider_telemetry_payload(
        ledger_summary=ledger_summary,
        tool_summary=tool_summary,
        search_provider_priority_fn=nova_core.get_search_provider_priority,
        provider_name_from_tool_fn=nova_core._provider_name_from_tool,
        recent_action_ledger_records_fn=nova_core._recent_action_ledger_records,
        policy_web_fn=nova_core.policy_web,
    )


def _tool_events_summary(limit: int = 80) -> dict:
    return _control_telemetry_service().tool_events_summary(TOOL_EVENTS_LOG, limit=limit)


def _os_capability_ledger_summary(limit: int = 80) -> dict:
    return OS_SCRIPT_CONTROLLER_SERVICE.summary(OS_CAPABILITY_LEDGER_FILE, limit=limit)


def _memory_events_summary(limit: int = 80) -> dict:
    return _control_telemetry_service().memory_events_summary(MEMORY_EVENTS_LOG, limit=limit)


def _build_self_check(status: dict, policy: dict, metrics: dict) -> dict:
    return _control_telemetry_service().build_self_check(status, policy, metrics)


def _export_capabilities_snapshot() -> tuple[bool, str, dict]:
    return _control_telemetry_service().export_capabilities_snapshot(EXPORT_DIR, strftime_fn=time.strftime)


def _control_self_check_payload() -> dict:
    return _build_self_check(_control_status_payload(), _control_policy_payload(), _metrics_payload())


def _load_persisted_sessions() -> None:
    with _SESSION_LOCK:
        http_session_store.load_persisted_sessions(
            store_path=SESSION_STORE_PATH,
            session_turns=SESSION_TURNS,
            session_owners=SESSION_OWNERS,
            max_stored_turns_per_session=MAX_STORED_TURNS_PER_SESSION,
        )


def _persist_sessions() -> None:
    http_session_store.persist_sessions(
        runtime_dir=RUNTIME_DIR,
        store_path=SESSION_STORE_PATH,
        session_turns=SESSION_TURNS,
        session_owners=SESSION_OWNERS,
        max_stored_sessions=MAX_STORED_SESSIONS,
        max_stored_turns_per_session=MAX_STORED_TURNS_PER_SESSION,
    )


def _record_leah_continuity_turns(session_id: str, turns: List[Tuple[str, str]]) -> None:
    store = getattr(LEAH_FRONTDOOR_SERVICE, "_continuity_store", None)
    record_fn = getattr(store, "record_turns", None)
    if not callable(record_fn):
        return
    try:
        record_fn(session_id, turns, limit=MAX_STORED_TURNS_PER_SESSION)
    except Exception:
        return


def _recover_leah_continuity_turns(session_id: str) -> List[Tuple[str, str]]:
    store = getattr(LEAH_FRONTDOOR_SERVICE, "_continuity_store", None)
    load_fn = getattr(store, "load_turns", None)
    if not callable(load_fn):
        return []
    try:
        return list(load_fn(session_id) or [])
    except Exception:
        return []


def _append_session_turn(session_id: str, role: str, text: str) -> List[Tuple[str, str]]:
    with _SESSION_LOCK:
        turns = http_session_store.append_session_turn(
            session_id,
            role,
            text,
            session_turns=SESSION_TURNS,
            max_turns=MAX_TURNS,
            persist_callback=_persist_sessions,
        )
    _record_leah_continuity_turns(session_id, turns)
    return turns


def _get_session_turns(session_id: str) -> List[Tuple[str, str]]:
    with _SESSION_LOCK:
        turns = http_session_store.get_session_turns(session_id, session_turns=SESSION_TURNS)
        if turns:
            return turns
        recovered = _recover_leah_continuity_turns(session_id)
        if recovered:
            SESSION_TURNS[session_id] = list(recovered)
            _persist_sessions()
            return list(recovered)
        return []


def _get_last_session_turn(session_id: str) -> tuple[str, str] | None:
    with _SESSION_LOCK:
        return http_session_store.get_last_session_turn(session_id, session_turns=SESSION_TURNS)


def _session_summaries(limit: int = 60) -> List[dict]:
    with _SESSION_LOCK:
        return http_session_store.session_summaries(
            session_turns=SESSION_TURNS,
            session_owners=SESSION_OWNERS,
            state_manager=SESSION_STATE_MANAGER,
            limit=limit,
        )


def _test_sessions_root() -> Path:
    return TEST_SESSION_CONTROL_SERVICE.test_sessions_root(RUNTIME_DIR)


def _generated_test_session_definitions_dir() -> Path:
    return TEST_SESSION_CONTROL_SERVICE.generated_test_session_definitions_dir(RUNTIME_DIR)


def _test_session_definitions_dir() -> Path:
    return TEST_SESSION_CONTROL_SERVICE.test_session_definitions_dir(BASE_DIR)


def _all_test_session_definition_roots() -> list[tuple[Path, str]]:
    return TEST_SESSION_CONTROL_SERVICE.all_test_session_definition_roots(base_dir=BASE_DIR, runtime_dir=RUNTIME_DIR)


def _available_test_session_definitions(limit: int = 80) -> List[dict]:
    return TEST_SESSION_CONTROL_SERVICE.available_test_session_definitions(
        _all_test_session_definition_roots(),
        limit=limit,
    )


def _resolve_test_session_definition(session_name: str) -> Path | None:
    return TEST_SESSION_CONTROL_SERVICE.resolve_test_session_definition(
        session_name,
        _available_test_session_definitions(500),
    )


def _subconscious_runs_root() -> Path:
    return RUNTIME_DIR / "subconscious_runs"


def _operator_macros_path() -> Path:
    return OPERATOR_CONTROL_SERVICE.operator_macros_path(BASE_DIR)


def _load_operator_macros(limit: int = 24) -> list[dict]:
    return OPERATOR_CONTROL_SERVICE.load_operator_macros(_operator_macros_path(), limit=limit)


def _resolve_operator_macro(macro_id: str) -> dict | None:
    return OPERATOR_CONTROL_SERVICE.resolve_operator_macro(macro_id, _load_operator_macros(200))


def _load_backend_commands(limit: int = 40) -> list[dict]:
    return OPERATOR_CONTROL_SERVICE.load_backend_commands(
        OPERATOR_CONTROL_SERVICE.backend_command_deck_path(BASE_DIR),
        limit=limit,
    )


def _resolve_backend_command(command_id: str) -> dict | None:
    return OPERATOR_CONTROL_SERVICE.resolve_backend_command(command_id, _load_backend_commands(200))


def _parse_backend_dynamic_args(raw: Any) -> list[str]:
    return OPERATOR_CONTROL_SERVICE.parse_backend_dynamic_args(raw)


def _run_backend_command(command_id: str, payload: dict) -> tuple[bool, str, dict]:
    return OPERATOR_CONTROL_SERVICE.run_backend_command(
        command_id,
        payload,
        commands=_load_backend_commands(80),
        python_bin=VENV_PY if VENV_PY.exists() else Path(os.sys.executable),
        base_dir=BASE_DIR,
        subprocess_run=subprocess.run,
    )


def _backend_command_list_action(payload: dict) -> tuple[bool, str, dict, str]:
    return OPERATOR_CONTROL_SERVICE.backend_command_list_action(load_backend_commands_fn=_load_backend_commands)


def _backend_command_run_action(payload: dict) -> tuple[bool, str, dict, str]:
    return OPERATOR_CONTROL_SERVICE.backend_command_run_action(
        payload,
        load_backend_commands_fn=_load_backend_commands,
        run_backend_command_fn=_run_backend_command,
    )


def _render_operator_macro_prompt(macro: Mapping[str, Any], values: Mapping[str, Any] | None = None, note: str = "") -> tuple[bool, str, dict[str, str]]:
    return OPERATOR_CONTROL_SERVICE.render_operator_macro_prompt(macro, values, note)


def _operator_prompt_action(payload: dict) -> tuple[bool, str, dict, str, dict]:
    return OPERATOR_CONTROL_SERVICE.operator_prompt_action_from_runtime(payload, runtime_scope=globals())


def _operator_outbox_respond_action(payload: dict) -> tuple[bool, str, dict, str]:
    result = OPERATOR_OUTBOX_SERVICE.respond_to_notice(
        OPERATOR_OUTBOX_FILE,
        event_id=str(payload.get("event_id") or payload.get("id") or "").strip(),
        message=str(payload.get("message") or payload.get("response") or "").strip(),
        responder=str(payload.get("responder") or payload.get("user_id") or "operator").strip(),
        resolution=str(payload.get("resolution") or "evidence_only").strip(),
        response_payload=payload,
        work_tree_module=work_tree,
    )
    ok = bool(result.get("ok", False))
    msg = "operator_outbox_response_ok" if ok else str(result.get("reason") or "operator_outbox_response_failed")
    detail = f"{msg}:{str(payload.get('event_id') or payload.get('id') or '').strip()}"
    return ok, msg, result, detail


def _operator_outbox_status_action(payload: dict) -> tuple[bool, str, dict, str]:
    event_id = str(payload.get("event_id") or payload.get("id") or "").strip()
    status = str(payload.get("status") or "").strip()
    result = OPERATOR_OUTBOX_SERVICE.set_notice_status(
        OPERATOR_OUTBOX_FILE,
        event_id=event_id,
        status=status,
        note=str(payload.get("note") or "").strip(),
    )
    ok = bool(result.get("ok", False))
    msg = "operator_outbox_status_ok" if ok else str(result.get("reason") or "operator_outbox_status_failed")
    detail = f"{msg}:{event_id}:{status}"
    return ok, msg, result, detail


def _latest_subconscious_report() -> dict:
    return SUBCONSCIOUS_CONTROL_SERVICE.latest_report(_subconscious_runs_root())


def _subconscious_status_summary() -> dict:
    return SUBCONSCIOUS_CONTROL_SERVICE.status_summary(
        _latest_subconscious_report(),
        _available_test_session_definitions(500),
        _subconscious_runs_root() / "latest.json",
    )


def _subconscious_live_summary(limit: int = 6) -> dict:
    return SUBCONSCIOUS_CONTROL_SERVICE.live_summary(
        limit=limit,
        pressure_config=SUBCONSCIOUS_SERVICE.pressure_config(),
        session_turns_items=list(SESSION_TURNS.items()),
        session_owner_lookup=SESSION_OWNERS,
        session_state_peek_fn=SESSION_STATE_MANAGER.peek,
        get_snapshot_fn=SUBCONSCIOUS_SERVICE.get_snapshot,
    )




def _report_status_label(diff_count: int, flagged_probe_count: int) -> str:
    return TEST_SESSION_CONTROL_SERVICE.report_status_label(diff_count, flagged_probe_count)


def _test_session_report_summaries(limit: int = 24) -> List[dict]:
    return TEST_SESSION_CONTROL_SERVICE.test_session_report_summaries(_test_sessions_root(), limit=limit)


def _run_test_session_definition(session_file: str) -> tuple[bool, str, dict]:
    return TEST_SESSION_CONTROL_SERVICE.run_test_session_definition(
        session_file,
        runner_path=TEST_SESSION_RUNNER_PY,
        venv_python=VENV_PY,
        base_dir=BASE_DIR,
        resolve_definition_fn=_resolve_test_session_definition,
        available_definitions_fn=_available_test_session_definitions,
        report_summaries_fn=_test_session_report_summaries,
        subprocess_run=subprocess.run,
    )


def _test_session_run_action(payload: dict) -> tuple[bool, str, dict, str]:
    return TEST_SESSION_CONTROL_SERVICE.test_session_run_action(
        payload,
        run_test_session_definition_fn=_run_test_session_definition,
    )


def _real_world_task_create_action(payload: dict) -> tuple[bool, str, dict, str]:
    return TEST_SESSION_CONTROL_SERVICE.real_world_task_create_action(
        payload,
        runtime_dir=RUNTIME_DIR,
        available_definitions_fn=_available_test_session_definitions,
    )


def _delete_session(session_id: str) -> tuple[bool, str]:
    ok, message = SESSION_ADMIN_SERVICE.delete_session_from_runtime(
        session_id,
        runtime_scope=globals(),
        core_module=nova_core,
    )
    if ok:
        continuity_store = getattr(LEAH_FRONTDOOR_SERVICE, "_continuity_store", None)
        clear_fn = getattr(continuity_store, "clear", None)
        if callable(clear_fn):
            try:
                clear_fn(session_id)
            except Exception:
                pass
        try:
            LEAH_FRONTDOOR_SERVICE._session_context.pop(str(session_id or "").strip(), None)
        except Exception:
            pass
    return ok, message


def _parse_request_path(raw_path: str) -> tuple[str, dict]:
    parsed = urlparse(raw_path or "/")
    return parsed.path or "/", parse_qs(parsed.query or "", keep_blank_values=True)


def _request_control_key(handler: BaseHTTPRequestHandler, qs: dict) -> str:
    h = (handler.headers.get("X-Nova-Control-Key") or "").strip()
    if h:
        return h
    return str((qs.get("key") or [""])[0]).strip()


def _is_local_client(handler: BaseHTTPRequestHandler) -> bool:
    ip = (handler.client_address[0] or "").strip().lower()
    return ip in {"127.0.0.1", "::1", "localhost"}


def _normalize_user_id(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "", raw)
    return cleaned[:64]


def _request_user_id(handler: BaseHTTPRequestHandler, qs: dict, payload: dict | None = None) -> str:
    header_uid = _normalize_user_id(handler.headers.get("X-Nova-User-Id") or "")
    qs_uid = _normalize_user_id(str((qs.get("user_id") or [""])[0]))
    body_uid = ""
    if isinstance(payload, dict):
        body_uid = _normalize_user_id(str(payload.get("user_id") or ""))
    return body_uid or qs_uid or header_uid


def _assert_session_owner(session_id: str, user_id: str, *, allow_bind: bool = True) -> tuple[bool, str]:
    with _SESSION_LOCK:
        return http_session_store.assert_session_owner(
            session_id,
            user_id,
            session_owners=SESSION_OWNERS,
            normalize_user_id=_normalize_user_id,
            persist_callback=_persist_sessions,
            allow_bind=allow_bind,
        )


def _dev_mode_enabled() -> bool:
    raw = str(os.environ.get("NOVA_DEV_MODE") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _chat_users_path() -> Path:
    return CHAT_IDENTITY_SERVICE.chat_users_path(RUNTIME_DIR)


def _chat_auth_source() -> str:
    return CHAT_IDENTITY_SERVICE.chat_auth_source(chat_users_path=_chat_users_path(), environ=os.environ)


def _hash_chat_password(password: str, *, iterations: int = CHAT_PASSWORD_HASH_ITERATIONS) -> dict:
    return CHAT_IDENTITY_SERVICE.hash_chat_password(password, iterations=iterations)


def _save_managed_chat_users(users: dict) -> None:
    CHAT_IDENTITY_SERVICE.save_managed_chat_users(
        users,
        normalize_user_id_fn=_normalize_user_id,
        chat_users_path=_chat_users_path(),
        iterations=CHAT_PASSWORD_HASH_ITERATIONS,
    )


def _chat_users() -> dict:
    return CHAT_IDENTITY_SERVICE.chat_users(
        chat_users_path=_chat_users_path(),
        normalize_user_id_fn=_normalize_user_id,
        environ=os.environ,
    )


def _chat_password_matches(expected, pwd: str) -> bool:
    return CHAT_IDENTITY_SERVICE.chat_password_matches(expected, pwd, iterations_default=CHAT_PASSWORD_HASH_ITERATIONS)


def _record_http_response(code: int) -> None:
    global _HTTP_REQUESTS_TOTAL, _HTTP_ERRORS_TOTAL
    with _METRICS_LOCK:
        _HTTP_REQUESTS_TOTAL += 1
        if int(code) >= 400:
            _HTTP_ERRORS_TOTAL += 1


def _parse_cookie_map(handler: BaseHTTPRequestHandler) -> dict:
    raw = (handler.headers.get("Cookie") or "").strip()
    out = {}
    if not raw:
        return out
    for part in raw.split(";"):
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        out[key.strip()] = value.strip()
    return out


def _control_auth(handler: BaseHTTPRequestHandler, qs: dict) -> tuple[bool, str]:
    return CONTROL_AUTH_SERVICE.control_api_auth(
        handler,
        qs,
        control_login_auth_fn=_control_login_auth,
        is_local_client_fn=_is_local_client,
        request_control_key_fn=_request_control_key,
    )


def _chat_auth_payload() -> dict:
    return SESSION_ADMIN_SERVICE.chat_auth_payload(
        chat_users_fn=_chat_users,
        chat_auth_source_fn=_chat_auth_source,
        chat_users_path_fn=_chat_users_path,
    )


def _chat_user_upsert(username: str, password: str) -> tuple[bool, str]:
    return SESSION_ADMIN_SERVICE.chat_user_upsert(
        username,
        password,
        normalize_user_id_fn=_normalize_user_id,
        chat_users_fn=_chat_users,
        save_managed_chat_users_fn=_save_managed_chat_users,
    )


def _chat_user_delete(username: str) -> tuple[bool, str]:
    return SESSION_ADMIN_SERVICE.chat_user_delete(
        username,
        normalize_user_id_fn=_normalize_user_id,
        chat_users_fn=_chat_users,
        save_managed_chat_users_fn=_save_managed_chat_users,
    )


def _session_delete_action(payload: dict) -> tuple[bool, str, dict, str]:
    return SESSION_ADMIN_SERVICE.session_delete_action(
        payload,
        delete_session_fn=_delete_session,
        session_summaries_fn=_session_summaries,
    )


def _chat_user_list_action(payload: dict) -> tuple[bool, str, dict, str]:
    return SESSION_ADMIN_SERVICE.chat_user_list_action(chat_auth_payload_fn=_chat_auth_payload)


def _chat_user_upsert_action(payload: dict) -> tuple[bool, str, dict, str]:
    return SESSION_ADMIN_SERVICE.chat_user_upsert_action(
        payload,
        chat_user_upsert_fn=_chat_user_upsert,
        chat_auth_payload_fn=_chat_auth_payload,
    )


def _chat_user_delete_action(payload: dict) -> tuple[bool, str, dict, str]:
    return SESSION_ADMIN_SERVICE.chat_user_delete_action(
        payload,
        chat_user_delete_fn=_chat_user_delete,
        chat_auth_payload_fn=_chat_auth_payload,
    )


def _chat_login_enabled() -> bool:
    return CHAT_IDENTITY_SERVICE.chat_login_enabled(chat_users_fn=_chat_users)


def _prune_chat_sessions() -> None:
    CHAT_IDENTITY_SERVICE.prune_chat_sessions(chat_sessions=CHAT_SESSIONS, now_fn=time.time)


def _new_chat_session(user_id: str) -> str:
    return CHAT_IDENTITY_SERVICE.new_chat_session(
        user_id,
        chat_sessions=CHAT_SESSIONS,
        normalize_user_id_fn=_normalize_user_id,
        ttl_seconds=CHAT_SESSION_TTL_SECONDS,
        token_hex_fn=secrets.token_hex,
        now_fn=time.time,
    )


def _clear_chat_session(handler: BaseHTTPRequestHandler) -> None:
    CHAT_IDENTITY_SERVICE.clear_chat_session(
        handler,
        chat_sessions=CHAT_SESSIONS,
        parse_cookie_map_fn=_parse_cookie_map,
    )


def _chat_login_auth(handler: BaseHTTPRequestHandler) -> tuple[bool, str]:
    return CHAT_IDENTITY_SERVICE.chat_login_auth(
        handler,
        chat_login_enabled_fn=_chat_login_enabled,
        prune_chat_sessions_fn=_prune_chat_sessions,
        parse_cookie_map_fn=_parse_cookie_map,
        chat_sessions=CHAT_SESSIONS,
        now_fn=time.time,
    )


def _chat_login_action(payload: dict) -> tuple[int, dict, dict]:
    return CHAT_IDENTITY_SERVICE.chat_login_action(
        payload,
        chat_login_enabled_fn=_chat_login_enabled,
        chat_users_fn=_chat_users,
        normalize_user_id_fn=_normalize_user_id,
        chat_password_matches_fn=_chat_password_matches,
        new_chat_session_fn=_new_chat_session,
    )


def _chat_logout_action(handler: BaseHTTPRequestHandler) -> tuple[int, dict, dict]:
    return CHAT_IDENTITY_SERVICE.chat_logout_action(
        handler,
        clear_chat_session_fn=_clear_chat_session,
    )


def _patch_preview_list_action(payload: dict) -> tuple[bool, str, dict, str]:
    return PATCH_CONTROL_SERVICE.patch_preview_list_action(
        patch_status_payload_fn=nova_core.patch_status_payload,
        preview_summaries_fn=nova_core.patch_preview_summaries,
        patch_action_readiness_payload_fn=_patch_action_readiness_payload,
    )


def _pulse_status_action(payload: dict) -> tuple[bool, str, dict, str]:
    return PATCH_CONTROL_SERVICE.pulse_status_action(
        build_pulse_payload_fn=nova_core.build_pulse_payload,
        render_nova_pulse_fn=nova_core.render_nova_pulse,
        update_now_pending_payload_fn=nova_core.update_now_pending_payload,
    )


def _patch_queue_run_next_action(payload: dict) -> tuple[bool, str, dict, str]:
    try:
        import json as _json
        import time as _time
        trigger = dict(payload or {})
        trigger["_requested_at"] = _time.time()
        PATCH_QUEUE_RUN_TRIGGER_FILE.parent.mkdir(parents=True, exist_ok=True)
        PATCH_QUEUE_RUN_TRIGGER_FILE.write_text(_json.dumps(trigger), encoding="utf-8")
        msg = "patch_queue_run_next_triggered"
        return True, msg, {"triggered": True}, msg
    except Exception as exc:
        msg = f"patch_queue_run_next_trigger_failed:{exc}"
        return False, msg, {}, msg


def _active_work_tree_run_next_action(payload: dict) -> tuple[bool, str, dict, str]:
    """Operator control Run Next Step.

    Control clicks are explicit operator intent: always operator_override so mission
    quiet/green hold does not silently no-op the button. Prefer immediate execute;
    fall back to maintenance trigger file if sync path fails.
    """
    try:
        import json as _json
        import time as _time

        trigger = dict(payload or {})
        if not str(trigger.get("target_branch_id") or "").strip():
            branch_id = str(trigger.get("branch_id") or "").strip()
            if branch_id:
                trigger["target_branch_id"] = branch_id
        if not str(trigger.get("target_task_id") or "").strip():
            task_id = str(trigger.get("task_id") or "").strip()
            if task_id:
                trigger["target_task_id"] = task_id
        # Explicit control-surface click is operator authority.
        trigger["operator_override"] = True
        trigger["_requested_at"] = _time.time()
        trigger.setdefault("max_steps", 1)
        trigger.setdefault("max_trees", 1)

        target_branch_id = str(trigger.get("target_branch_id") or "").strip()
        target_task_id = str(trigger.get("target_task_id") or "").strip()
        target_tree_id = str(trigger.get("target_tree_id") or "").strip()
        target_tool = str(trigger.get("recommended_tool") or trigger.get("target_tool") or "").strip()

        # Immediate path so the button advances work without waiting for the
        # next maintenance cycle (and without mission hold swallowing the click).
        try:
            import autonomy_maintenance as am

            state = am._load_state()
            cycle_kwargs = {
                "max_steps": 1,
                "max_trees": 1,
            }
            if target_branch_id:
                cycle_kwargs["target_branch_id"] = target_branch_id
            if target_task_id:
                cycle_kwargs["target_task_id"] = target_task_id
            if target_tree_id:
                cycle_kwargs["target_tree_id"] = target_tree_id
            if target_tool:
                cycle_kwargs["target_tool"] = target_tool
            cycle = am._run_active_work_tree_cycle(state, **cycle_kwargs)
            am._save_state(state)
            status = str((cycle or {}).get("status") or "unknown").strip() or "unknown"
            executed = int((cycle or {}).get("executed_count") or 0)
            msg = f"active_work_tree_run_next_{status}"
            if executed <= 0:
                reason = str((cycle or {}).get("last_action") or (cycle or {}).get("reason") or status)
                msg = f"{msg}:executed=0:{reason}"
            return True, msg, {
                "triggered": False,
                "executed_now": True,
                "executed_count": executed,
                "cycle": cycle if isinstance(cycle, dict) else {},
                "operator_override": True,
            }, msg
        except Exception as sync_exc:
            # Fall back to async trigger for the maintenance worker.
            WORK_TREE_RUN_TRIGGER_FILE.parent.mkdir(parents=True, exist_ok=True)
            WORK_TREE_RUN_TRIGGER_FILE.write_text(_json.dumps(trigger), encoding="utf-8")
            msg = "active_work_tree_run_next_triggered"
            return True, msg, {
                "triggered": True,
                "executed_now": False,
                "operator_override": True,
                "sync_error": str(sync_exc)[:240],
            }, msg
    except Exception as exc:
        msg = f"active_work_tree_run_next_trigger_failed:{exc}"
        return False, msg, {}, msg


def _codegen_run_action(payload: dict) -> tuple[bool, str, dict, str]:
    msg = "codegen_run_requires_autonomy_maintenance_scope"
    return False, msg, {}, msg


def _leah_build_run_next_action(payload: dict) -> tuple[bool, str, dict, str]:
    """Advance the Leah build pipeline one step for the next promoted capability.

    Gate conditions:
    - layers.leah.mode must be "active"
    - layers.leah.promoted_capabilities must be non-empty
    - The next capability in LEAH_BUILD_SEQUENCE that is both a gap and promoted
      must exist and not already be registered complete.

    On success writes a trigger artifact to runtime/leah_build/ and returns the
    cap name and spec so the operator (or codegen pipeline) can proceed.
    """
    try:
        from services.layer_maturity_policy import (
            normalize_layer_policy,
            next_leah_capability_in_sequence,
            LEAH_BUILD_SEQUENCE,
        )

        # Load live policy
        policy_path = BASE_DIR / "policy.json"
        try:
            policy = json.loads(policy_path.read_text(encoding="utf-8"))
        except Exception:
            policy = {}

        layers = normalize_layer_policy(policy)
        leah_layer = layers.get("leah", {})
        mode = leah_layer.get("mode", "observe")
        promoted = leah_layer.get("promoted_capabilities", [])

        if mode != "active":
            msg = "leah_build_run_next_requires_active_mode"
            return False, msg, {"mode": mode, "promoted": promoted}, msg

        if not promoted:
            msg = "leah_build_run_next_no_promoted_capabilities"
            return False, msg, {"mode": mode, "promoted": promoted}, msg

        # Treat all four sequence caps as gaps unless explicitly registered complete.
        # registered_capabilities comes from runtime evidence, not just code existing.
        gaps = list(LEAH_BUILD_SEQUENCE)

        # Pull any already-registered completions from capabilities module if available.
        registered: set[str] = set()
        try:
            reg_map = capabilities_mod.get_registered_capabilities() if hasattr(capabilities_mod, "get_registered_capabilities") else {}
            if isinstance(reg_map, dict):
                registered = {str(k).strip().lower() for k in reg_map if str(k).strip().lower().startswith("leah_")}
        except Exception:
            pass

        next_cap = next_leah_capability_in_sequence(
            gaps,
            promoted_capabilities=promoted,
            registered_capabilities=registered,
        )

        if not next_cap:
            msg = "leah_build_run_next_sequence_complete"
            return True, msg, {
                "mode": mode,
                "promoted": promoted,
                "registered": sorted(registered),
                "next_cap": None,
                "status": "all_promoted_caps_registered_complete",
            }, msg

        # Build the codegen spec for this capability
        spec = {
            "name": next_cap,
            "purpose": (
                f"Implement and validate {next_cap} for Leah on this Nova instance. "
                "Follow acceptance tests in docs/LEAH_INSTANCE_PROFILE.md."
            ),
            "files": [
                {
                    "path": f"services/{next_cap}.py",
                    "kind": "module",
                    "intent": f"Service implementation for capability: {next_cap}",
                },
                {
                    "path": f"tests/test_{next_cap}_acceptance.py",
                    "kind": "test",
                    "intent": f"Acceptance tests for {next_cap} per instance profile",
                },
            ],
        }

        # Write trigger artifact for pick-up by the codegen pipeline
        trigger_dir = Path(RUNTIME_DIR) / "leah_build"
        trigger_dir.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y%m%d_%H%M%S")
        trigger_path = trigger_dir / f"build_next_{next_cap}_{ts}.json"
        trigger_path.write_text(
            json.dumps({
                "schema": "nova.leah_build.trigger.v1",
                "capability": next_cap,
                "spec": spec,
                "triggered_at": ts,
                "promoted_capabilities": promoted,
                "instance_profile": "docs/LEAH_INSTANCE_PROFILE.md",
                "status": "pending_codegen",
            }, indent=2),
            encoding="utf-8",
        )

        msg = f"leah_build_run_next_triggered:{next_cap}"
        return True, msg, {
            "next_cap": next_cap,
            "spec": spec,
            "trigger_file": str(trigger_path),
            "promoted": promoted,
            "registered": sorted(registered),
            "status": "pending_codegen",
        }, msg

    except Exception as exc:
        msg = f"leah_build_run_next_failed:{exc}"
        return False, msg, {}, msg


# ---------------------------------------------------------------------------
# Temporal calendar event management actions
# ---------------------------------------------------------------------------

def _temporal_events_list_action(payload: dict) -> tuple[bool, str, dict, str]:
    """GET-style action: return all calendar events with enrichment data."""
    try:
        events = read_calendar_events(TEMPORAL_CALENDAR_FILE)
        return True, "ok", {"events": events, "count": len(events)}, "ok"
    except Exception as exc:
        msg = f"temporal_events_list_failed:{exc}"
        return False, msg, {}, msg


def _temporal_event_save_action(payload: dict) -> tuple[bool, str, dict, str]:
    """Create or update a single calendar event (upsert by UID)."""
    try:
        event = dict(payload.get("event") or payload or {})
        if not event.get("title"):
            return False, "temporal_event_missing_title", {}, "temporal_event_missing_title"
        uid = write_calendar_event(TEMPORAL_CALENDAR_FILE, event)
        return True, "ok", {"uid": uid, "saved": True}, "ok"
    except Exception as exc:
        msg = f"temporal_event_save_failed:{exc}"
        return False, msg, {}, msg


def _temporal_event_delete_action(payload: dict) -> tuple[bool, str, dict, str]:
    """Delete a calendar event by UID."""
    try:
        uid = str(payload.get("uid") or "").strip()
        if not uid:
            return False, "temporal_event_delete_missing_uid", {}, "temporal_event_delete_missing_uid"
        removed = delete_calendar_event(TEMPORAL_CALENDAR_FILE, uid)
        return True, "ok", {"uid": uid, "removed": removed}, "ok"
    except Exception as exc:
        msg = f"temporal_event_delete_failed:{exc}"
        return False, msg, {}, msg


def _update_now_dry_run_action(payload: dict) -> tuple[bool, str, dict, str]:
    return PATCH_CONTROL_SERVICE.update_now_dry_run_action(
        tool_update_now_fn=nova_core.tool_update_now,
        update_now_pending_payload_fn=nova_core.update_now_pending_payload,
        patch_status_payload_fn=nova_core.patch_status_payload,
    )


def _update_now_confirm_action(payload: dict) -> tuple[bool, str, dict, str]:
    return PATCH_CONTROL_SERVICE.update_now_confirm_action(
        payload,
        tool_update_now_confirm_fn=nova_core.tool_update_now_confirm,
        update_now_pending_payload_fn=nova_core.update_now_pending_payload,
        patch_status_payload_fn=nova_core.patch_status_payload,
    )


def _update_now_cancel_action(payload: dict) -> tuple[bool, str, dict, str]:
    return PATCH_CONTROL_SERVICE.update_now_cancel_action(
        tool_update_now_cancel_fn=nova_core.tool_update_now_cancel,
        update_now_pending_payload_fn=nova_core.update_now_pending_payload,
    )


def _refresh_status_action(payload: dict) -> tuple[bool, str, dict, str]:
    return CONTROL_ACTIONS_SERVICE.refresh_status_action(control_status_payload_fn=_control_status_payload)


def _device_location_update_action(payload: dict) -> tuple[bool, str, dict, str]:
    return CONTROL_ACTIONS_SERVICE.device_location_update_action(
        payload,
        set_runtime_device_location_fn=nova_core.set_runtime_device_location,
        invalidate_control_status_cache_fn=_invalidate_control_status_cache,
    )


def _device_location_clear_action(payload: dict) -> tuple[bool, str, dict, str]:
    return CONTROL_ACTIONS_SERVICE.device_location_clear_action(
        clear_runtime_device_location_fn=nova_core.clear_runtime_device_location,
        invalidate_control_status_cache_fn=_invalidate_control_status_cache,
    )


def _self_check_action(payload: dict) -> tuple[bool, str, dict, str]:
    return CONTROL_ACTIONS_SERVICE.self_check_action(control_self_check_payload_fn=_control_self_check_payload)


def _tail_log_action(payload: dict) -> tuple[bool, str, dict]:
    return _control_telemetry_service().tail_log_action(
        payload,
        log_dir=LOG_DIR,
        tail_file_fn=_tail_file,
        record_control_action_event_fn=_record_control_action_event,
    )


def _metrics_action(payload: dict) -> tuple[bool, str, dict]:
    return _control_telemetry_service().metrics_action(
        payload,
        metrics_payload_fn=_metrics_payload,
        record_control_action_event_fn=_record_control_action_event,
    )


def _export_ledger_summary_action(payload: dict) -> tuple[bool, str, dict]:
    return _control_telemetry_service().export_ledger_summary_action(
        payload,
        export_dir=EXPORT_DIR,
        action_ledger_summary_fn=_action_ledger_summary,
        record_control_action_event_fn=_record_control_action_event,
        strftime_fn=time.strftime,
    )


def _export_diagnostics_bundle_action(payload: dict) -> tuple[bool, str, dict]:
    return _control_telemetry_service().export_diagnostics_bundle_action_from_runtime(
        payload,
        runtime_scope=globals(),
        core_module=nova_core,
    )


def _control_login_enabled() -> bool:
    return CONTROL_AUTH_SERVICE.control_login_enabled(environ=os.environ)


def _prune_control_sessions() -> None:
    CONTROL_AUTH_SERVICE.prune_control_sessions(control_sessions=CONTROL_SESSIONS, now_fn=time.time)


def _control_login_auth(handler: BaseHTTPRequestHandler) -> tuple[bool, str]:
    return CONTROL_AUTH_SERVICE.control_login_auth(
        handler,
        control_login_enabled_fn=_control_login_enabled,
        prune_control_sessions_fn=_prune_control_sessions,
        parse_cookie_map_fn=_parse_cookie_map,
        control_sessions=CONTROL_SESSIONS,
        now_fn=time.time,
    )


def _control_page_gate(handler: BaseHTTPRequestHandler) -> tuple[bool, str]:
    return CONTROL_AUTH_SERVICE.control_page_gate(
        handler,
        dev_mode_enabled_fn=_dev_mode_enabled,
        control_login_auth_fn=_control_login_auth,
        is_local_client_fn=_is_local_client,
        environ=os.environ,
    )


def _new_control_session() -> str:
    return CONTROL_AUTH_SERVICE.new_control_session(
        control_sessions=CONTROL_SESSIONS,
        ttl_seconds=CONTROL_SESSION_TTL_SECONDS,
        token_hex_fn=secrets.token_hex,
        now_fn=time.time,
    )


def _clear_control_session(handler: BaseHTTPRequestHandler) -> None:
    CONTROL_AUTH_SERVICE.clear_control_session(
        handler,
        control_sessions=CONTROL_SESSIONS,
        parse_cookie_map_fn=_parse_cookie_map,
    )


def _control_login_action(payload: dict) -> tuple[int, dict, dict]:
    return CONTROL_AUTH_SERVICE.control_login_action(
        payload,
        control_login_enabled_fn=_control_login_enabled,
        new_control_session_fn=_new_control_session,
        environ=os.environ,
        compare_digest_fn=secrets.compare_digest,
    )


def _control_logout_action(handler: BaseHTTPRequestHandler) -> tuple[int, dict, dict]:
    return CONTROL_AUTH_SERVICE.control_logout_action(
        handler,
        clear_control_session_fn=_clear_control_session,
    )


def _guard_status_payload(include_fallback_scan: bool = True) -> dict:
    return RUNTIME_STATUS_SERVICE.guard_status_payload_from_runtime(
        globals(),
        include_fallback_scan=include_fallback_scan,
    )


def _start_guard() -> tuple[bool, str]:
    return RUNTIME_CONTROL_SERVICE.start_guard(
        venv_python=VENV_PY,
        guard_py=GUARD_PY,
        runtime_dir=RUNTIME_DIR,
        base_dir=BASE_DIR,
        guard_status_fn=_guard_status_payload,
        restart_intent_path=RESTART_INTENT_PATH,
        restart_provenance_service=RUNTIME_RESTART_PROVENANCE_SERVICE,
        subprocess_module=subprocess,
        os_name=os.name,
    )


def _core_status_payload() -> dict:
    return RUNTIME_STATUS_SERVICE.core_status_payload(
        runtime_dir=RUNTIME_DIR,
        core_py=CORE_PY,
        pid_exists_fn=psutil.pid_exists,
        heartbeat_age_seconds_fn=_heartbeat_age_seconds,
        logical_service_processes_fn=_logical_service_processes,
        prune_orphaned_core_artifacts_fn=_prune_orphaned_core_artifacts,
        select_logical_process_fn=_select_logical_process,
    )


def _http_status_payload() -> dict:
    return RUNTIME_STATUS_SERVICE.http_status_payload(getpid_fn=os.getpid, process_fn=psutil.Process)


def _runtime_summary_payload(guard: dict | None = None, core: dict | None = None, webui: dict | None = None) -> dict:
    return RUNTIME_STATUS_SERVICE.runtime_summary_payload(
        guard or _guard_status_payload(),
        core or _core_status_payload(),
        webui or _http_status_payload(),
    )


def _start_nova_core() -> tuple[bool, str]:
    return RUNTIME_CONTROL_SERVICE.start_nova_core(
        core_py=CORE_PY,
        core_status_fn=_core_status_payload,
        start_guard_fn=_start_guard,
    )


def _stop_guard() -> tuple[bool, str]:
    return RUNTIME_CONTROL_SERVICE.stop_guard(
        venv_python=VENV_PY,
        stop_guard_py=STOP_GUARD_PY,
        base_dir=BASE_DIR,
        subprocess_run=subprocess.run,
    )


def _detached_creation_flags() -> int:
    return RUNTIME_CONTROL_SERVICE.detached_creation_flags(os_name=os.name, subprocess_module=subprocess)


def _schedule_detached_start(
    command: list[str],
    *,
    delay_seconds: float = 1.5,
    cwd: Path | None = None,
    remove_before_start: list[Path] | None = None,
) -> tuple[bool, str]:
    return RUNTIME_CONTROL_SERVICE.schedule_detached_start(
        command,
        venv_python=VENV_PY,
        base_dir=BASE_DIR,
        delay_seconds=delay_seconds,
        cwd=cwd,
        remove_before_start=remove_before_start,
        subprocess_module=subprocess,
        os_name=os.name,
    )


def _core_identity_from_runtime() -> tuple[int | None, float | None]:
    return RUNTIME_CONTROL_SERVICE.core_identity_from_runtime(
        runtime_dir=RUNTIME_DIR,
        runtime_processes_module=runtime_processes,
    )


def _stop_core_owned_process() -> tuple[bool, str]:
    return RUNTIME_CONTROL_SERVICE.stop_core_owned_process(
        runtime_dir=RUNTIME_DIR,
        core_py=CORE_PY,
        runtime_processes_module=runtime_processes,
        psutil_module=psutil,
    )


def _restart_guard() -> tuple[bool, str]:
    return RUNTIME_CONTROL_SERVICE.restart_guard(
        venv_python=VENV_PY,
        guard_py=GUARD_PY,
        base_dir=BASE_DIR,
        guard_status_fn=_guard_status_payload,
        core_status_fn=_core_status_payload,
        stop_guard_fn=_stop_guard,
        schedule_detached_start_fn=_schedule_detached_start,
        start_guard_fn=_start_guard,
        restart_intent_path=RESTART_INTENT_PATH,
        restart_provenance_service=RUNTIME_RESTART_PROVENANCE_SERVICE,
    )


def _restart_core() -> tuple[bool, str]:
    return RUNTIME_CONTROL_SERVICE.restart_core(
        guard_status_fn=_guard_status_payload,
        stop_core_owned_process_fn=_stop_core_owned_process,
        start_guard_fn=_start_guard,
        restart_intent_path=RESTART_INTENT_PATH,
        restart_provenance_service=RUNTIME_RESTART_PROVENANCE_SERVICE,
    )


def _shutdown_http_server_later(delay_seconds: float = 0.25) -> tuple[bool, str]:
    return RUNTIME_CONTROL_SERVICE.shutdown_http_server_later(
        _HTTP_SERVER,
        delay_seconds,
        threading_module=threading,
        time_module=time,
    )


def _restart_webui() -> tuple[bool, str]:
    return RUNTIME_CONTROL_SERVICE.restart_webui(
        venv_python=VENV_PY,
        http_py=HTTP_PY,
        bind_host=_HTTP_BIND_HOST,
        bind_port=_HTTP_BIND_PORT,
        base_dir=BASE_DIR,
        schedule_detached_start_fn=_schedule_detached_start,
        shutdown_http_server_later_fn=_shutdown_http_server_later,
    )


def _start_autonomy_maintenance_worker() -> tuple[bool, str]:
    return RUNTIME_CONTROL_SERVICE.start_autonomy_maintenance_worker(
        venv_python=VENV_PY,
        maintenance_py=AUTONOMY_MAINTENANCE_PY,
        state_path=AUTONOMY_MAINTENANCE_STATE_PATH,
        base_dir=BASE_DIR,
        interval_sec=300,
        runtime_processes_module=runtime_processes,
        subprocess_module=subprocess,
        os_name=os.name,
    )


def _stop_autonomy_maintenance_worker() -> tuple[bool, str]:
    return RUNTIME_CONTROL_SERVICE.stop_autonomy_maintenance_worker(
        state_path=AUTONOMY_MAINTENANCE_STATE_PATH,
        maintenance_py=AUTONOMY_MAINTENANCE_PY,
        runtime_processes_module=runtime_processes,
        psutil_module=psutil,
    )


def _runtime_artifact_show_action(payload: dict) -> tuple[bool, str, dict, str]:
    return RUNTIME_CONTROL_SERVICE.runtime_artifact_show_action(
        payload,
        runtime_artifact_detail_payload_fn=_runtime_artifact_detail_payload,
    )


def _guard_control_action(payload: dict) -> tuple[bool, str, dict, str]:
    return RUNTIME_CONTROL_SERVICE.guard_control_action_from_runtime(payload, runtime_scope=globals())


def _core_runtime_action(payload: dict) -> tuple[bool, str, dict, str]:
    return RUNTIME_CONTROL_SERVICE.core_runtime_action_from_runtime(payload, runtime_scope=globals())


def _autonomy_runtime_action(payload: dict) -> tuple[bool, str, dict, str]:
    return RUNTIME_CONTROL_SERVICE.autonomy_runtime_action_from_runtime(payload, runtime_scope=globals())


def _action_readiness_payload(guard: dict, core: dict, webui: dict) -> dict:
    return RUNTIME_STATUS_SERVICE.action_readiness_payload(guard, core, webui)


def _append_metrics_snapshot(status_payload: dict) -> None:
    _control_telemetry_service().append_metrics_snapshot(
        status_payload,
        metrics_lock=_METRICS_LOCK,
        http_requests_total=_HTTP_REQUESTS_TOTAL,
        http_errors_total=_HTTP_ERRORS_TOTAL,
        metrics_series=_METRICS_SERIES,
        metrics_max_points=_METRICS_MAX_POINTS,
        now_fn=time.time,
    )


def _metrics_payload() -> dict:
    return _control_telemetry_service().metrics_payload(
        metrics_lock=_METRICS_LOCK,
        http_requests_total=_HTTP_REQUESTS_TOTAL,
        http_errors_total=_HTTP_ERRORS_TOTAL,
        metrics_series=_METRICS_SERIES,
    )


def _tail_file(path: Path, max_lines: int = 120) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
        lines = text.splitlines()
        return "\n".join(lines[-max_lines:])
    except Exception as e:
        return f"Unable to read {path.name}: {e}"


def _release_ledger_entries(limit: int = 20) -> list[dict]:
    return RELEASE_STATUS_SERVICE.ledger_entries(RELEASE_LEDGER_PATH, limit)


def _release_entry_matches_build(entry: dict, build_entry: dict) -> bool:
    return RELEASE_STATUS_SERVICE.entry_matches_build(entry, build_entry)


def _release_status_payload(limit: int = 8) -> dict:
    source_root = BASE_DIR
    try:
        Path(RELEASE_LEDGER_PATH).resolve().relative_to(RELEASE_PACKAGES_DIR.resolve())
    except Exception:
        source_root = None
    return RELEASE_STATUS_SERVICE.status_payload(RELEASE_LEDGER_PATH, limit, source_root=source_root, artifact_kind="package-zip")


def _installer_status_payload(limit: int = 8) -> dict:
    return RELEASE_STATUS_SERVICE.status_payload(
        RELEASE_LEDGER_PATH,
        limit,
        source_root=None,
        artifact_kind="windows-installer",
    )


def _coerce_epoch_seconds(value) -> int | None:
    return RUNTIME_TIMELINE_SERVICE.coerce_epoch_seconds(value)


def _runtime_event(action: str, ts_value, source: str, service: str, level: str, title: str, detail: str) -> dict | None:
    return RUNTIME_TIMELINE_SERVICE.runtime_event(action, ts_value, source, service, level, title, detail)


def _runtime_timeline_action_title(action: str) -> str:
    return RUNTIME_TIMELINE_SERVICE.action_title(action)


def _runtime_timeline_action_service(action: str) -> str:
    return RUNTIME_TIMELINE_SERVICE.action_service(action)


def _runtime_timeline_from_control_audit(limit: int) -> list[dict]:
    return RUNTIME_TIMELINE_SERVICE.from_control_audit(CONTROL_AUDIT_LOG, limit)


def _parse_guard_log_line(line: str) -> dict | None:
    return RUNTIME_TIMELINE_SERVICE.parse_guard_log_line(line, time_module=time)


def _runtime_timeline_from_guard_log(limit: int) -> list[dict]:
    return RUNTIME_TIMELINE_SERVICE.from_guard_log(
        GUARD_LOG_PATH,
        limit,
        safe_tail_lines_fn=_safe_tail_lines,
        time_module=time,
    )


def _runtime_timeline_from_boot_history(limit: int) -> list[dict]:
    return RUNTIME_TIMELINE_SERVICE.from_boot_history(GUARD_BOOT_HISTORY_PATH, limit)


def _runtime_timeline_payload(limit: int = 24) -> dict:
    return RUNTIME_TIMELINE_SERVICE.payload(
        limit=limit,
        control_audit_log=CONTROL_AUDIT_LOG,
        guard_log_path=GUARD_LOG_PATH,
        boot_history_path=GUARD_BOOT_HISTORY_PATH,
        safe_tail_lines_fn=_safe_tail_lines,
        time_module=time,
    )


def _file_age_seconds(path: Path) -> int | None:
    try:
        if not path.exists():
            return None
        return max(0, int(time.time() - path.stat().st_mtime))
    except Exception:
        return None


def _safe_json_file(path: Path):
    try:
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8") or "null")
    except Exception:
        return None


def _artifact_status(name: str, path: Path) -> str:
    return RUNTIME_ARTIFACTS_SERVICE.artifact_status(name, path, file_age_seconds_fn=_file_age_seconds)


def _artifact_summary(name: str, path: Path) -> tuple[str, str]:
    return RUNTIME_ARTIFACTS_SERVICE.artifact_summary(
        name,
        path,
        safe_json_file_fn=_safe_json_file,
        tail_file_fn=_tail_file,
        safe_tail_lines_fn=_safe_tail_lines,
        file_age_seconds_fn=_file_age_seconds,
        json_module=json,
    )


def _runtime_artifact_definitions() -> list[tuple[str, Path, str]]:
    return RUNTIME_ARTIFACTS_SERVICE.artifact_definitions(
        runtime_dir=RUNTIME_DIR,
        guard_boot_history_path=GUARD_BOOT_HISTORY_PATH,
        control_audit_log=CONTROL_AUDIT_LOG,
        guard_log_path=GUARD_LOG_PATH,
    )


def _runtime_artifact_service(name: str) -> str:
    return RUNTIME_ARTIFACTS_SERVICE.artifact_service(name)


def _artifact_content(name: str, path: Path, *, max_lines: int = 120, max_chars: int = 12000) -> str:
    return RUNTIME_ARTIFACTS_SERVICE.artifact_content(
        name,
        path,
        max_lines=max_lines,
        max_chars=max_chars,
        safe_tail_lines_fn=_safe_tail_lines,
        tail_file_fn=_tail_file,
        file_age_seconds_fn=_file_age_seconds,
        json_module=json,
    )


def _runtime_artifact_detail_payload(name: str, *, max_lines: int = 120) -> dict:
    return RUNTIME_ARTIFACTS_SERVICE.detail_payload(
        name,
        definitions=_runtime_artifact_definitions(),
        runtime_timeline_payload_fn=_runtime_timeline_payload,
        artifact_summary_fn=_artifact_summary,
        artifact_status_fn=_artifact_status,
        artifact_content_fn=_artifact_content,
        file_age_seconds_fn=_file_age_seconds,
        max_lines=max_lines,
    )


def _runtime_artifacts_payload() -> dict:
    return RUNTIME_ARTIFACTS_SERVICE.payload(
        _runtime_artifact_definitions(),
        artifact_summary_fn=_artifact_summary,
        artifact_status_fn=_artifact_status,
        file_age_seconds_fn=_file_age_seconds,
    )


def _validation_artifact_truth_payload() -> dict:
    return VALIDATION_ARTIFACT_TRUTH_SERVICE.payload(
        runtime_dir=RUNTIME_DIR,
        regression_status_path=RUNTIME_DIR / "regression_status.json",
    )


def _runtime_restart_analytics_payload() -> dict:
    return RUNTIME_ANALYTICS_SERVICE.restart_analytics_payload(
        boot_history_path=GUARD_BOOT_HISTORY_PATH,
        guard_log_path=GUARD_LOG_PATH,
        now=int(time.time()),
    )


def _patch_action_readiness_payload(patch_summary: dict | None = None) -> dict:
    return PATCH_CONTROL_SERVICE.patch_action_readiness_payload(
        patch_summary,
        preview_summaries_fn=nova_core.patch_preview_summaries,
        show_preview_fn=nova_core.show_preview,
        updates_dir=nova_core.UPDATES_DIR,
    )


def _latest_runtime_event_for_service(timeline_payload: dict | None, service: str) -> dict:
    return RUNTIME_STATUS_SERVICE.latest_runtime_event_for_service(timeline_payload, service)


def _failure_reason_for_service(service: str, payload: dict, timeline_payload: dict | None = None) -> dict:
    return RUNTIME_STATUS_SERVICE.failure_reason_for_service(service, payload, timeline_payload)


def _runtime_failure_reasons_payload(guard: dict, core: dict, webui: dict, timeline_payload: dict | None = None) -> dict:
    return RUNTIME_STATUS_SERVICE.runtime_failure_reasons_payload(guard, core, webui, timeline_payload)


def _port_ownership_payload() -> dict:
    return PORT_OWNERSHIP_SERVICE.payload(psutil_module=psutil)


def _heartbeat_age_seconds() -> int | None:
    hb = RUNTIME_DIR / "core.heartbeat"
    if not hb.exists():
        return None
    try:
        return max(0, int(time.time() - hb.stat().st_mtime))
    except Exception:
        return None


def _storage_watch_summary() -> dict:
    now = time.monotonic()
    with _STORAGE_WATCH_CACHE_LOCK:
        cached_at = float(_STORAGE_WATCH_CACHE.get("computed_at") or 0.0)
        cached_payload = _STORAGE_WATCH_CACHE.get("payload")
        if isinstance(cached_payload, dict) and now - cached_at <= STORAGE_WATCH_CACHE_TTL_SECONDS:
            payload = dict(cached_payload)
            payload["snapshot_cached"] = True
            payload["snapshot_age_sec"] = round(max(0.0, now - cached_at), 3)
            return payload

    policy = nova_core.load_policy()
    kidney_config = dict((policy.get("kidney") or {})) if isinstance(policy, dict) else {}
    payload = STORAGE_WATCH_SERVICE.snapshot(
        base_dir=BASE_DIR,
        runtime_dir=RUNTIME_DIR,
        kidney_config=kidney_config,
    )
    payload = dict(payload)
    payload["snapshot_cached"] = False
    payload["snapshot_age_sec"] = 0.0
    with _STORAGE_WATCH_CACHE_LOCK:
        _STORAGE_WATCH_CACHE["computed_at"] = now
        _STORAGE_WATCH_CACHE["payload"] = dict(payload)
    return payload


def _artifact_age_seconds(path: Path) -> int | None:
    if not path.exists():
        return None
    try:
        return max(0, int(time.time() - path.stat().st_mtime))
    except Exception:
        return None


def _remove_runtime_artifact(path: Path) -> None:
    try:
        if path.exists():
            path.unlink()
    except Exception:
        pass


def _prune_orphaned_guard_artifacts(logical_processes: list[dict], pid: int | None, pid_live: bool) -> None:
    RUNTIME_PROCESS_STATE_SERVICE.prune_orphaned_guard_artifacts_from_runtime(
        logical_processes,
        pid,
        pid_live,
        runtime_scope=globals(),
    )


def _prune_orphaned_core_artifacts(
    logical_processes: list[dict],
    pid: int | None,
    pid_live: bool,
    heartbeat_age: int | None,
) -> None:
    RUNTIME_PROCESS_STATE_SERVICE.prune_orphaned_core_artifacts_from_runtime(
        logical_processes,
        pid,
        pid_live,
        heartbeat_age,
        runtime_scope=globals(),
    )


def _matches_script_process(cmdline: list[str], script_path: Path, cwd: str | Path | None = None) -> bool:
    return RUNTIME_PROCESS_STATE_SERVICE.matches_script_process(cmdline, script_path, cwd=cwd)


def _snapshot_script_process(process: psutil.Process, script_path: Path) -> dict | None:
    return RUNTIME_PROCESS_STATE_SERVICE.snapshot_script_process(
        process,
        script_path,
        matches_script_process_fn=_matches_script_process,
    )


def _logical_leaf_processes(matches: list[dict]) -> list[dict]:
    return RUNTIME_PROCESS_STATE_SERVICE.logical_leaf_processes(matches)


def _cached_logical_service_processes(
    script_path: Path,
    *,
    root_pid: int | None = None,
    cache_key: str | None = None,
    max_age_seconds: float = 0.0,
) -> list[dict]:
    return RUNTIME_PROCESS_STATE_SERVICE.cached_logical_service_processes_from_runtime(
        script_path,
        runtime_scope=globals(),
        root_pid=root_pid,
        cache_key=cache_key,
        max_age_seconds=max_age_seconds,
    )


def _logical_service_processes(script_path: Path, root_pid: int | None = None) -> list[dict]:
    return RUNTIME_PROCESS_STATE_SERVICE.logical_service_processes(
        script_path,
        root_pid=root_pid,
        psutil_module=psutil,
        snapshot_script_process_fn=_snapshot_script_process,
        logical_leaf_processes_fn=_logical_leaf_processes,
    )


def _select_logical_process(processes: list[dict], *, pid: int | None = None, create_time: float | None = None) -> dict | None:
    return RUNTIME_PROCESS_STATE_SERVICE.select_logical_process(processes, pid=pid, create_time=create_time)


def _runtime_process_note() -> str:
    return HTTP_CONTROL_SURFACE_SERVICE.runtime_process_note()


def _probe_searxng(endpoint: str, timeout: float = SEARXNG_STATUS_TIMEOUT_SEC) -> tuple[bool, str]:
    probe = nova_core.probe_search_endpoint(
        endpoint,
        timeout=timeout,
        persist_repair=False,
        candidate_limit=SEARXNG_STATUS_CANDIDATE_LIMIT,
    )
    return bool(probe.get("ok")), str(probe.get("note") or "endpoint_unreachable")


def _control_status_payload() -> dict:
    return HTTP_CONTROL_SURFACE_SERVICE.control_status_payload_from_runtime(globals())


def _cached_control_status_payload(max_age_seconds: float = CONTROL_STATUS_CACHE_TTL_SECONDS) -> dict:
    return CONTROL_STATUS_CACHE_SERVICE.cached_payload(
        _CONTROL_STATUS_CACHE,
        lock=_CONTROL_STATUS_CACHE_LOCK,
        max_age_seconds=max_age_seconds,
        monotonic_fn=time.monotonic,
        compute_payload_fn=_control_status_payload,
    )


def _control_status_surfaces_payload() -> dict:
    return HTTP_CONTROL_SURFACE_SERVICE.control_status_surfaces_payload_from_runtime(globals())


def _cached_control_status_surfaces_payload(
    max_age_seconds: float = CONTROL_STATUS_SURFACES_CACHE_TTL_SECONDS,
) -> dict:
    return CONTROL_STATUS_CACHE_SERVICE.cached_payload(
        _CONTROL_STATUS_SURFACES_CACHE,
        lock=_CONTROL_STATUS_SURFACES_CACHE_LOCK,
        max_age_seconds=max_age_seconds,
        monotonic_fn=time.monotonic,
        compute_payload_fn=_control_status_surfaces_payload,
    )


def _generated_work_queue(limit: int = 24) -> dict:
    try:
        payload = service_generated_work_queue_payload(
            int(limit or 24),
            base_dir=BASE_DIR,
            runtime_dir=RUNTIME_DIR,
        )
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _work_trees_payload(limit: int = 32) -> dict:
    return CONTROL_WORK_TREES_SERVICE.payload(
        list_visual_trees_fn=work_tree.list_visual_trees,
        limit=limit,
    )


def _work_tree_pressure_payload() -> dict:
    return CONTROL_WORK_TREES_SERVICE.pressure_payload(work_tree_module=work_tree)


def _operator_outbox_summary(limit: int = 20) -> dict:
    return OPERATOR_OUTBOX_SERVICE.summary(OPERATOR_OUTBOX_FILE, limit=limit)


def _control_policy_payload() -> dict:
    return HTTP_CONTROL_SURFACE_SERVICE.control_policy_payload_from_runtime(globals())


def _control_status_suppliers() -> dict[str, object]:
    return CONTROL_STATUS_SERVICE.runtime_supplier_fns_from_scope(globals())


def _control_action(action: str, payload: dict) -> tuple[bool, str, dict]:
    return HTTP_CONTROL_SURFACE_SERVICE.control_action_from_runtime(action, payload, globals())


def _health_payload() -> dict:
    outbox_summary = OPERATOR_OUTBOX_SERVICE.summary(OPERATOR_OUTBOX_FILE, limit=5)
    return {
        "ok": True,
        "ollama_api_up": bool(nova_core.ollama_api_up()),
        "chat_model": nova_core.chat_model(),
        "memory_enabled": bool(nova_core.mem_enabled()),
        "chat_login_enabled": bool(_chat_login_enabled()),
        "operator_outbox": outbox_summary,
        "operator_outbox_latest_id": str(outbox_summary.get("latest_id") or ""),
        "operator_outbox_latest_open_id": str(outbox_summary.get("latest_open_id") or ""),
    }


def _leah_nova_pulse_payload() -> dict:
    from services.leah_nova_pulse import build_leah_nova_pulse

    return build_leah_nova_pulse(
        ollama_up=bool(nova_core.ollama_api_up()),
        chat_model=str(nova_core.chat_model() or ""),
        memory_enabled=bool(nova_core.mem_enabled()),
        chat_login_enabled=bool(_chat_login_enabled()),
        outbox=OPERATOR_OUTBOX_SERVICE.summary(OPERATOR_OUTBOX_FILE, limit=3),
    )


def _trim_turns(turns: List[Tuple[str, str]]) -> None:
    http_session_store.trim_turns(turns, max_turns=MAX_TURNS)


def _json_response(handler: BaseHTTPRequestHandler, code: int, payload: dict) -> None:
    HTTP_RESPONSE_SERVICE.json_response(
        handler,
        code,
        payload,
        record_http_response_fn=_record_http_response,
    )


def _text_response(handler: BaseHTTPRequestHandler, code: int, text: str) -> None:
    HTTP_RESPONSE_SERVICE.text_response(
        handler,
        code,
        text,
        record_http_response_fn=_record_http_response,
    )


def _file_response(handler: BaseHTTPRequestHandler, code: int, path: Path, content_type: str) -> None:
    HTTP_RESPONSE_SERVICE.file_response(
        handler,
        code,
        path,
        content_type,
        record_http_response_fn=_record_http_response,
    )


def _strip_ui_tip_leak(text: str) -> str:
    t = (text or "").strip()
    if not t:
        return t
    # Remove UI startup hint leakage even when it appears inline with other text.
    t = re.sub(
        r"(?is)\bTip:\s*start server with --host\s+0\.0\.0\.0[^\n]*",
        "",
        t,
    )
    t = re.sub(r"\n{3,}", "\n\n", t).strip()
    return t


def _read_text_safely(path: Path) -> str:
    return nova_core._read_text_safely(path)


def _generate_chat_reply(
    turns: List[Tuple[str, str]],
    text: str,
    ledger_record: dict | None = None,
    pending_action: dict | None = None,
    prefer_web_for_data_queries: bool = False,
    language_mix_spanish_pct: int = 0,
    session=None,
    ensure_active_work_tree_fn=None,
) -> tuple[str, dict]:
    return execute_http_reply_sequence_from_runtime(
        turns=turns,
        text=text,
        ledger_record=ledger_record,
        pending_action=pending_action,
        prefer_web_for_data_queries=prefer_web_for_data_queries,
        language_mix_spanish_pct=language_mix_spanish_pct,
        session=session,
        ensure_reply=nova_core._ensure_reply,
        core=nova_core,
        runtime_scope=globals(),
        ensure_active_work_tree_fn=ensure_active_work_tree_fn,
    )


def process_chat(session_id: str, user_text: str, user_id: str = "") -> str:
    return HTTP_CHAT_RUNTIME_SERVICE.process_chat_from_runtime(
        session_id,
        user_text,
        user_id=user_id,
        core_module=nova_core,
        runtime_scope=globals(),
    )


def resume_last_pending_turn(session_id: str, user_id: str = "") -> dict:
    return http_chat_flow.resume_last_pending_turn_from_runtime(
        session_id,
        user_id,
        runtime_scope=globals(),
    )


class NovaHttpHandler(BaseHTTPRequestHandler):
    server_version = "NovaHTTP/0.1"

    def do_GET(self) -> None:
        HTTP_TRANSPORT_SERVICE.handle_get_request(
            self,
            parse_request_path_fn=_parse_request_path,
            basic_route_request_fn=lambda path, handler: HTTP_GET_ROUTES_SERVICE.handle_basic_route_request_from_runtime(
                path,
                handler=handler,
                runtime_scope=globals(),
            ),
            chat_history_request_fn=lambda handler, qs: HTTP_GET_ROUTES_SERVICE.handle_chat_history_request_from_runtime(
                handler=handler,
                qs=qs,
                runtime_scope=globals(),
            ),
            control_api_request_fn=lambda path, handler, qs: HTTP_GET_ROUTES_SERVICE.handle_control_api_request_from_runtime(
                path,
                handler=handler,
                qs=qs,
                runtime_scope=globals(),
            ),
            json_response_fn=_json_response,
            response_service=HTTP_RESPONSE_SERVICE,
            record_http_response_fn=_record_http_response,
        )

    def do_POST(self) -> None:
        HTTP_TRANSPORT_SERVICE.handle_post_request(
            self,
            parse_request_path_fn=_parse_request_path,
            dispatch_post_request_fn=lambda handler, path, qs: HTTP_POST_DISPATCH_SERVICE.handle_post_request_from_runtime(
                handler=handler,
                path=path,
                qs=qs,
                runtime_scope=globals(),
            ),
            response_service=HTTP_RESPONSE_SERVICE,
            record_http_response_fn=_record_http_response,
        )

    def log_message(self, fmt: str, *args) -> None:
        return



def main() -> None:
    from tools.runtime_singleton import acquire_role_singleton, release_role_singleton

    args = NOVA_HTTP_FRONTDOOR_SERVICE.parse_args()
    role = f"http-{int(args.port)}"
    ok, detail = acquire_role_singleton(role)
    if not ok:
        print(f"Nova HTTP already running on port {args.port} ({detail}). Not starting a second instance.")
        return
    try:
        NOVA_HTTP_FRONTDOOR_SERVICE.serve_from_runtime(
            globals(),
            handler_class=NovaHttpHandler,
            argv=None,
        )
    finally:
        release_role_singleton(role)


if __name__ == "__main__":
    main()
