from __future__ import annotations

import argparse
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
import capabilities as capabilities_mod
import http_chat_flow
import http_session_store
import work_tree
from conversation_manager import ConversationManager
from services.control_assets import CONTROL_ASSETS_SERVICE
from services.control_actions import CONTROL_ACTIONS_SERVICE
from services.control_auth import CONTROL_AUTH_SERVICE
from services.control_telemetry import ControlTelemetryService
from services.control_status import CONTROL_STATUS_SERVICE
from services.control_status_cache import CONTROL_STATUS_CACHE_SERVICE
from services.chat_identity import CHAT_IDENTITY_SERVICE
from services.nova_http_chat_orchestration import HTTP_CHAT_ORCHESTRATION_SERVICE
from services.nova_http_chat_runtime import HTTP_CHAT_RUNTIME_SERVICE
from services.nova_http_turn_entry import HTTP_TURN_ENTRY_SERVICE
from services.nova_http_turn_finalization import HTTP_TURN_FINALIZATION_SERVICE
from services.operator_control import OPERATOR_CONTROL_SERVICE
from services.patch_control import PATCH_CONTROL_SERVICE
from services.policy_control import POLICY_CONTROL_SERVICE
from services.release_status import RELEASE_STATUS_SERVICE
from services.runtime_artifacts import RUNTIME_ARTIFACTS_SERVICE
from services.runtime_analytics import RUNTIME_ANALYTICS_SERVICE
from services.runtime_control import RUNTIME_CONTROL_SERVICE
from services.runtime_process_state import RUNTIME_PROCESS_STATE_SERVICE
from services.runtime_status import RUNTIME_STATUS_SERVICE
from services.runtime_timeline import RUNTIME_TIMELINE_SERVICE
from services.session_admin import SESSION_ADMIN_SERVICE
from services.schedule_registry import SCHEDULE_REGISTRY
from services.subconscious_control import SUBCONSCIOUS_CONTROL_SERVICE
from services.test_session_control import TEST_SESSION_CONTROL_SERVICE
from services.subconscious_runtime import SUBCONSCIOUS_SERVICE
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
SCRIPTS_DIR = BASE_DIR / "scripts"
LOG_DIR = BASE_DIR / "logs"
RUNTIME_DIR = BASE_DIR / "runtime"
SESSION_STORE_PATH = RUNTIME_DIR / "http_chat_sessions.json"
MAX_STORED_SESSIONS = 120
MAX_STORED_TURNS_PER_SESSION = MAX_TURNS * 2
KNOWLEDGE_DIR = BASE_DIR / "knowledge"


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

CONTROL_SESSIONS: Dict[str, float] = {}
CONTROL_SESSION_TTL_SECONDS = 8 * 60 * 60
CHAT_SESSIONS: Dict[str, tuple[str, float]] = {}
CHAT_SESSION_TTL_SECONDS = 8 * 60 * 60
CHAT_PASSWORD_HASH_ITERATIONS = 120000
PROCESS_SCAN_CACHE_TTL_SECONDS = 5.0
_PROCESS_SCAN_CACHE: Dict[str, tuple[float, list[dict]]] = {}
CONTROL_STATUS_CACHE_TTL_SECONDS = 2.0
_CONTROL_STATUS_CACHE_LOCK = threading.Lock()
_CONTROL_STATUS_CACHE: Dict[str, Any] = {"computed_at": 0.0, "payload": None}
AUTONOMY_MAINTENANCE_STATE_PATH = RUNTIME_DIR / "autonomy_maintenance_state.json"


def _invalidate_control_status_cache() -> None:
    CONTROL_STATUS_CACHE_SERVICE.invalidate(_CONTROL_STATUS_CACHE, lock=_CONTROL_STATUS_CACHE_LOCK)


def _load_autonomy_maintenance_state() -> dict:
    try:
        payload = json.loads(AUTONOMY_MAINTENANCE_STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        payload = {}
    return payload if isinstance(payload, dict) else {}


def _autonomy_maintenance_summary() -> dict:
    payload = _load_autonomy_maintenance_state()
    runtime_worker = dict(payload.get("runtime_worker") or {}) if isinstance(payload.get("runtime_worker"), dict) else {}
    last_generated_queue_run = dict(payload.get("last_generated_queue_run") or {}) if isinstance(payload.get("last_generated_queue_run"), dict) else {}
    pid = runtime_worker.get("pid")
    create_time = runtime_worker.get("create_time")
    selected = runtime_processes.select_logical_process(
        runtime_processes.logical_service_processes(AUTONOMY_MAINTENANCE_PY),
        pid=int(pid) if isinstance(pid, int) else (int(pid) if isinstance(pid, str) and pid.isdigit() else None),
        create_time=float(create_time) if isinstance(create_time, (int, float)) else None,
    )
    if selected is not None:
        runtime_worker["pid"] = int(selected.get("pid") or runtime_worker.get("pid") or 0)
        runtime_worker["create_time"] = float(selected.get("create_time") or runtime_worker.get("create_time") or 0.0) or runtime_worker.get("create_time")
        runtime_worker["script_path"] = str(runtime_worker.get("script_path") or AUTONOMY_MAINTENANCE_PY)
        if str(runtime_worker.get("last_cycle_status") or "").strip().lower() in {"", "stopped"}:
            runtime_worker["last_cycle_status"] = "running"
    elif str(runtime_worker.get("last_cycle_status") or "").strip().lower() == "running":
        runtime_worker["last_cycle_status"] = "stopped"
    return {
        "ok": bool(payload),
        "last_generated_at": str(payload.get("last_generated_at") or ""),
        "last_regression_status": str(payload.get("last_regression_status") or ""),
        "last_auto_apply": str(payload.get("last_auto_apply") or ""),
        "runtime_worker": runtime_worker,
        "last_generated_queue_run": last_generated_queue_run,
    }

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


def _control_telemetry_service() -> ControlTelemetryService:
    return ControlTelemetryService(list_capabilities_fn=capabilities_mod.list_capabilities)


def _action_ledger_summary(limit: int = 60) -> dict:
    return _control_telemetry_service().action_ledger_summary(
        nova_core.ACTION_LEDGER_DIR,
        nova_core.action_ledger_route_summary,
        limit=limit,
    )


def _provider_telemetry_payload(*, ledger_summary: dict, tool_summary: dict) -> dict:
    active_priority = [str(item or "").strip().lower() for item in list(nova_core.get_search_provider_priority()) if str(item or "").strip()]
    active_provider_set = {item for item in active_priority if item}
    last_record = ledger_summary.get("last_record") if isinstance(ledger_summary.get("last_record"), dict) else {}
    last_tool = str(last_record.get("tool") or "").strip()
    last_provider_used = str(last_record.get("provider_used") or nova_core._provider_name_from_tool(last_tool)).strip().lower()
    if last_provider_used and last_provider_used not in active_provider_set:
        last_provider_used = ""
    last_query = str(((last_record.get("reply_outcome") or {}).get("query") or "")).strip() if isinstance(last_record.get("reply_outcome"), dict) else ""
    hits: dict[str, int] = {}
    for rec in nova_core._recent_action_ledger_records(limit=80):
        if not isinstance(rec, dict):
            continue
        provider = str(rec.get("provider_used") or nova_core._provider_name_from_tool(rec.get("tool") or "")).strip().lower()
        if not provider or provider not in active_provider_set:
            continue
        hits[provider] = int(hits.get(provider, 0) or 0) + 1
    web_cfg = nova_core.policy_web()
    last_provider_family = str(last_record.get("provider_family") or last_provider_used or "").strip().lower()
    if last_provider_family and last_provider_family not in active_provider_set:
        last_provider_family = ""
    candidates = [
        str(item or "").strip().lower()
        for item in list(last_record.get("provider_candidates") or [])
        if str(item or "").strip().lower() in active_provider_set
    ] if isinstance(last_record.get("provider_candidates"), list) else []
    return {
        "priority": active_priority,
        "last_provider_used": last_provider_used,
        "last_provider_family": last_provider_family,
        "last_provider_query": last_query,
        "last_provider_candidates": candidates,
        "hits_last_window": hits,
        "tool_latency_ms_by_tool": dict(tool_summary.get("avg_latency_ms_by_tool") or {}),
        "stackexchange_site": str(web_cfg.get("stackexchange_site") or "stackoverflow").strip() or "stackoverflow",
    }


def _tool_events_summary(limit: int = 80) -> dict:
    return _control_telemetry_service().tool_events_summary(TOOL_EVENTS_LOG, limit=limit)


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


def _append_session_turn(session_id: str, role: str, text: str) -> List[Tuple[str, str]]:
    with _SESSION_LOCK:
        return http_session_store.append_session_turn(
            session_id,
            role,
            text,
            session_turns=SESSION_TURNS,
            max_turns=MAX_TURNS,
            persist_callback=_persist_sessions,
        )


def _get_session_turns(session_id: str) -> List[Tuple[str, str]]:
    with _SESSION_LOCK:
        return http_session_store.get_session_turns(session_id, session_turns=SESSION_TURNS)


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
    return OPERATOR_CONTROL_SERVICE.operator_prompt_action(
        payload,
        resolve_operator_macro_fn=_resolve_operator_macro,
        render_operator_macro_prompt_fn=_render_operator_macro_prompt,
        load_operator_macros_fn=_load_operator_macros,
        normalize_user_id_fn=_normalize_user_id,
        assert_session_owner_fn=_assert_session_owner,
        process_chat_fn=process_chat,
        session_summaries_fn=_session_summaries,
        token_hex_fn=secrets.token_hex,
    )


def _policy_allow_action(payload: dict) -> tuple[bool, str, dict, str]:
    return POLICY_CONTROL_SERVICE.policy_allow_action(
        payload,
        policy_allow_domain_fn=nova_core.policy_allow_domain,
    )


def _policy_remove_action(payload: dict) -> tuple[bool, str, dict, str]:
    return POLICY_CONTROL_SERVICE.policy_remove_action(
        payload,
        policy_remove_domain_fn=nova_core.policy_remove_domain,
    )


def _web_mode_action(payload: dict) -> tuple[bool, str, dict, str]:
    return POLICY_CONTROL_SERVICE.web_mode_action(
        payload,
        set_web_mode_fn=nova_core.set_web_mode,
    )


def _memory_scope_set_action(payload: dict) -> tuple[bool, str, dict, str]:
    return POLICY_CONTROL_SERVICE.memory_scope_set_action(
        payload,
        set_memory_scope_fn=nova_core.set_memory_scope,
        control_policy_payload_fn=_control_policy_payload,
        invalidate_control_status_cache_fn=_invalidate_control_status_cache,
    )


def _search_provider_action(payload: dict) -> tuple[bool, str, dict, str]:
    return POLICY_CONTROL_SERVICE.search_provider_action(
        payload,
        set_search_provider_fn=nova_core.set_search_provider,
        control_policy_payload_fn=_control_policy_payload,
        invalidate_control_status_cache_fn=_invalidate_control_status_cache,
    )


def _search_provider_toggle_action(payload: dict) -> tuple[bool, str, dict, str]:
    return POLICY_CONTROL_SERVICE.search_provider_toggle_action(
        toggle_search_provider_fn=nova_core.toggle_search_provider,
        control_policy_payload_fn=_control_policy_payload,
        invalidate_control_status_cache_fn=_invalidate_control_status_cache,
    )


def _search_endpoint_set_action(payload: dict) -> tuple[bool, str, dict, str]:
    return POLICY_CONTROL_SERVICE.search_endpoint_set_action(
        payload,
        set_search_endpoint_fn=nova_core.set_search_endpoint,
        control_policy_payload_fn=_control_policy_payload,
        invalidate_control_status_cache_fn=_invalidate_control_status_cache,
    )


def _search_provider_priority_set_action(payload: dict) -> tuple[bool, str, dict, str]:
    return POLICY_CONTROL_SERVICE.search_provider_priority_set_action(
        payload,
        set_search_provider_priority_fn=nova_core.set_search_provider_priority,
        control_policy_payload_fn=_control_policy_payload,
        invalidate_control_status_cache_fn=_invalidate_control_status_cache,
    )


def _search_endpoint_probe_action(payload: dict) -> tuple[bool, str, dict, str]:
    def _probe(endpoint: str) -> dict:
        return nova_core.probe_search_endpoint(str(endpoint or nova_core.get_search_endpoint() or "").strip())

    return POLICY_CONTROL_SERVICE.search_endpoint_probe_action(
        payload,
        probe_search_endpoint_fn=_probe,
    )


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


def _generated_definition_priority_tuple(item: dict) -> tuple[int, float, int, str]:
    return TEST_SESSION_CONTROL_SERVICE.generated_definition_priority_tuple(item)


def _generated_work_queue_status_rank(status: str) -> int:
    return TEST_SESSION_CONTROL_SERVICE.generated_work_queue_status_rank(status)


def _latest_generated_report_by_file(limit: int = 200) -> dict[str, dict]:
    return TEST_SESSION_CONTROL_SERVICE.latest_generated_report_by_file(
        _test_session_report_summaries(max(24, int(limit or 200))),
        limit=limit,
    )


def _generated_work_queue(limit: int = 24) -> dict:
    return TEST_SESSION_CONTROL_SERVICE.generated_work_queue(
        _available_test_session_definitions(500),
        _test_session_report_summaries(max(200, len(_available_test_session_definitions(500)) * 2)),
        limit=limit,
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


def _run_generated_test_session_pack(limit: int = 12, *, mode: str = "recent") -> tuple[bool, str, dict]:
    return TEST_SESSION_CONTROL_SERVICE.run_generated_test_session_pack(
        limit,
        mode=mode,
        available_definitions_fn=_available_test_session_definitions,
        run_test_session_definition_fn=_run_test_session_definition,
        report_summaries_fn=_test_session_report_summaries,
        generated_work_queue_fn=_generated_work_queue,
    )


def _run_next_generated_work_queue_item() -> tuple[bool, str, dict]:
    return TEST_SESSION_CONTROL_SERVICE.run_next_generated_work_queue_item(
        generated_work_queue_fn=_generated_work_queue,
        run_test_session_definition_fn=_run_test_session_definition,
    )


def _generated_queue_operator_note(item: Mapping[str, Any]) -> str:
    return TEST_SESSION_CONTROL_SERVICE.generated_queue_operator_note(dict(item) if isinstance(item, Mapping) else {})


def _investigate_generated_work_queue_item(session_file: str = "", *, session_id: str = "", user_id: str = "operator") -> tuple[bool, str, dict]:
    return TEST_SESSION_CONTROL_SERVICE.investigate_generated_work_queue_item(
        session_file=session_file,
        session_id=session_id,
        user_id=user_id,
        generated_work_queue_fn=_generated_work_queue,
        resolve_operator_macro_fn=_resolve_operator_macro,
        render_operator_macro_prompt_fn=_render_operator_macro_prompt,
        normalize_user_id_fn=_normalize_user_id,
        assert_session_owner_fn=lambda sid, uid: _assert_session_owner(sid, uid, allow_bind=True),
        process_chat_fn=process_chat,
        session_summaries_fn=_session_summaries,
    )


def _test_session_run_action(payload: dict) -> tuple[bool, str, dict, str]:
    return TEST_SESSION_CONTROL_SERVICE.test_session_run_action(
        payload,
        run_test_session_definition_fn=_run_test_session_definition,
    )


def _generated_pack_run_action(payload: dict) -> tuple[bool, str, dict, str]:
    return TEST_SESSION_CONTROL_SERVICE.generated_pack_run_action(
        payload,
        run_generated_test_session_pack_fn=_run_generated_test_session_pack,
    )


def _generated_queue_run_next_action(payload: dict) -> tuple[bool, str, dict, str]:
    return TEST_SESSION_CONTROL_SERVICE.generated_queue_run_next_action(
        run_next_generated_work_queue_item_fn=_run_next_generated_work_queue_item,
    )


def _generated_queue_investigate_action(payload: dict) -> tuple[bool, str, dict, str]:
    return TEST_SESSION_CONTROL_SERVICE.generated_queue_investigate_action(
        payload,
        investigate_generated_work_queue_item_fn=_investigate_generated_work_queue_item,
    )


def _real_world_task_create_action(payload: dict) -> tuple[bool, str, dict, str]:
    return TEST_SESSION_CONTROL_SERVICE.real_world_task_create_action(
        payload,
        runtime_dir=RUNTIME_DIR,
        available_definitions_fn=_available_test_session_definitions,
    )


def _delete_session(session_id: str) -> tuple[bool, str]:
    return SESSION_ADMIN_SERVICE.delete_session(
        session_id,
        session_lock=_SESSION_LOCK,
        delete_session_fn=http_session_store.delete_session,
        session_turns=SESSION_TURNS,
        session_owners=SESSION_OWNERS,
        state_manager=SESSION_STATE_MANAGER,
        persist_callback=_persist_sessions,
        on_session_end=lambda sid, session: nova_core.record_health_snapshot(
            session_id=sid,
            reflection=session.last_reflection,
            session_end=True,
        ),
    )


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
    ok_login, why_login = _control_login_auth(handler)
    if not ok_login:
        return False, why_login

    expected = (os.environ.get("NOVA_CONTROL_TOKEN") or "").strip()
    if expected:
        got = _request_control_key(handler, qs)
        if got and secrets.compare_digest(got, expected):
            return True, ""
        return False, "control_auth_failed"

    if _is_local_client(handler):
        return True, ""
    return False, "control_local_only_set_NOVA_CONTROL_TOKEN"


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
    return _control_telemetry_service().export_diagnostics_bundle_action(
        payload,
        runtime_dir=RUNTIME_DIR,
        log_dir=LOG_DIR,
        control_status_payload_fn=_control_status_payload,
        control_policy_payload_fn=_control_policy_payload,
        metrics_payload_fn=_metrics_payload,
        build_self_check_fn=_build_self_check,
        behavior_get_metrics_fn=nova_core.behavior_get_metrics,
        action_ledger_summary_fn=_action_ledger_summary,
        tool_events_summary_fn=_tool_events_summary,
        safe_tail_lines_fn=_safe_tail_lines,
        record_control_action_event_fn=_record_control_action_event,
        now_fn=time.time,
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
    return RUNTIME_STATUS_SERVICE.guard_status_payload(
        runtime_dir=RUNTIME_DIR,
        guard_py=GUARD_PY,
        include_fallback_scan=include_fallback_scan,
        pid_exists_fn=psutil.pid_exists,
        cached_logical_service_processes_fn=_cached_logical_service_processes,
        logical_service_processes_fn=_logical_service_processes,
        prune_orphaned_guard_artifacts_fn=_prune_orphaned_guard_artifacts,
        select_logical_process_fn=_select_logical_process,
        process_scan_cache_ttl_seconds=PROCESS_SCAN_CACHE_TTL_SECONDS,
    )


def _start_guard() -> tuple[bool, str]:
    return RUNTIME_CONTROL_SERVICE.start_guard(
        venv_python=VENV_PY,
        guard_py=GUARD_PY,
        runtime_dir=RUNTIME_DIR,
        base_dir=BASE_DIR,
        guard_status_fn=_guard_status_payload,
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


def _schedule_detached_start(command: list[str], *, delay_seconds: float = 1.5, cwd: Path | None = None) -> tuple[bool, str]:
    return RUNTIME_CONTROL_SERVICE.schedule_detached_start(
        command,
        venv_python=VENV_PY,
        base_dir=BASE_DIR,
        delay_seconds=delay_seconds,
        cwd=cwd,
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
    )


def _restart_core() -> tuple[bool, str]:
    return RUNTIME_CONTROL_SERVICE.restart_core(
        guard_status_fn=_guard_status_payload,
        stop_core_owned_process_fn=_stop_core_owned_process,
        start_guard_fn=_start_guard,
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
    action = str(payload.get("_action") or "").strip().lower()
    if action == "guard_status":
        return RUNTIME_CONTROL_SERVICE.guard_status_action(guard_status_payload_fn=_guard_status_payload)
    if action == "guard_start":
        return RUNTIME_CONTROL_SERVICE.guard_start_action(
            start_guard_fn=_start_guard,
            guard_status_payload_fn=_guard_status_payload,
        )
    if action == "guard_stop":
        return RUNTIME_CONTROL_SERVICE.guard_stop_action(
            stop_guard_fn=_stop_guard,
            guard_status_payload_fn=_guard_status_payload,
        )
    if action == "guard_restart":
        return RUNTIME_CONTROL_SERVICE.guard_restart_action(
            restart_guard_fn=_restart_guard,
            guard_status_payload_fn=_guard_status_payload,
            core_status_payload_fn=_core_status_payload,
        )
    return False, "runtime_action_unknown", {}, "runtime_action_unknown"


def _core_runtime_action(payload: dict) -> tuple[bool, str, dict, str]:
    action = str(payload.get("_action") or "").strip().lower()
    if action == "nova_start":
        return RUNTIME_CONTROL_SERVICE.nova_start_action(
            start_nova_core_fn=_start_nova_core,
            core_status_payload_fn=_core_status_payload,
        )
    if action == "core_stop":
        return RUNTIME_CONTROL_SERVICE.core_stop_action(
            stop_core_owned_process_fn=_stop_core_owned_process,
            guard_status_payload_fn=_guard_status_payload,
            core_status_payload_fn=_core_status_payload,
        )
    if action == "core_restart":
        return RUNTIME_CONTROL_SERVICE.core_restart_action(
            restart_core_fn=_restart_core,
            guard_status_payload_fn=_guard_status_payload,
            core_status_payload_fn=_core_status_payload,
        )
    if action == "webui_restart":
        return RUNTIME_CONTROL_SERVICE.webui_restart_action(
            restart_webui_fn=_restart_webui,
            http_status_payload_fn=_http_status_payload,
        )
    return False, "runtime_action_unknown", {}, "runtime_action_unknown"


def _autonomy_runtime_action(payload: dict) -> tuple[bool, str, dict, str]:
    action = str(payload.get("_action") or "").strip().lower()
    if action == "autonomy_maintenance_start":
        return RUNTIME_CONTROL_SERVICE.autonomy_maintenance_start_action(
            start_autonomy_maintenance_worker_fn=_start_autonomy_maintenance_worker,
            autonomy_maintenance_summary_fn=_autonomy_maintenance_summary,
        )
    if action == "autonomy_maintenance_stop":
        return RUNTIME_CONTROL_SERVICE.autonomy_maintenance_stop_action(
            stop_autonomy_maintenance_worker_fn=_stop_autonomy_maintenance_worker,
            autonomy_maintenance_summary_fn=_autonomy_maintenance_summary,
        )
    return False, "runtime_action_unknown", {}, "runtime_action_unknown"


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
    return RELEASE_STATUS_SERVICE.status_payload(RELEASE_LEDGER_PATH, limit)


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


def _runtime_restart_analytics_payload() -> dict:
    return RUNTIME_ANALYTICS_SERVICE.restart_analytics_payload(
        boot_history_path=GUARD_BOOT_HISTORY_PATH,
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


def _heartbeat_age_seconds() -> int | None:
    hb = RUNTIME_DIR / "core.heartbeat"
    if not hb.exists():
        return None
    try:
        return max(0, int(time.time() - hb.stat().st_mtime))
    except Exception:
        return None


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
    RUNTIME_PROCESS_STATE_SERVICE.prune_orphaned_guard_artifacts(
        logical_processes,
        pid,
        pid_live,
        runtime_dir=RUNTIME_DIR,
        artifact_age_seconds_fn=_artifact_age_seconds,
        remove_runtime_artifact_fn=_remove_runtime_artifact,
    )


def _prune_orphaned_core_artifacts(
    logical_processes: list[dict],
    pid: int | None,
    pid_live: bool,
    heartbeat_age: int | None,
) -> None:
    RUNTIME_PROCESS_STATE_SERVICE.prune_orphaned_core_artifacts(
        logical_processes,
        pid,
        pid_live,
        heartbeat_age,
        runtime_dir=RUNTIME_DIR,
        artifact_age_seconds_fn=_artifact_age_seconds,
        remove_runtime_artifact_fn=_remove_runtime_artifact,
    )


def _matches_script_process(cmdline: list[str], script_path: Path) -> bool:
    return RUNTIME_PROCESS_STATE_SERVICE.matches_script_process(cmdline, script_path)


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
    return RUNTIME_PROCESS_STATE_SERVICE.cached_logical_service_processes(
        script_path,
        root_pid=root_pid,
        cache_key=cache_key,
        max_age_seconds=max_age_seconds,
        process_scan_cache=_PROCESS_SCAN_CACHE,
        monotonic_fn=time.monotonic,
        logical_service_processes_fn=_logical_service_processes,
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
    if os.name == "nt":
        return (
            "Windows note: the operator console reports logical service state. "
            "Launcher and child interpreter pairs can appear as duplicate python processes, "
            "but nova_http reporting collapses them to the leaf service process."
        )
    return "Process counts reflect the active service process state."


def _probe_searxng(endpoint: str, timeout: float = 2.5) -> tuple[bool, str]:
    probe = nova_core.probe_search_endpoint(endpoint, timeout=timeout, persist_repair=True)
    return bool(probe.get("ok")), str(probe.get("note") or "endpoint_unreachable")


def _control_status_payload() -> dict:
    p = nova_core.load_policy()
    web_cfg = p.get("web") or {}
    provider = str(web_cfg.get("search_provider") or "html").strip().lower()
    endpoint = str(web_cfg.get("search_api_endpoint") or "").strip()

    searx_ok = None
    searx_note = "n/a"
    if provider == "searxng":
        if endpoint:
            searx_ok, searx_note = _probe_searxng(endpoint)
        else:
            searx_ok, searx_note = None, "endpoint_missing"

    guard_status = _guard_status_payload()
    core_status = _core_status_payload()
    webui_status = _http_status_payload()
    timeline_payload = _runtime_timeline_payload()
    subconscious_summary = _subconscious_status_summary()
    subconscious_live_summary = _subconscious_live_summary()
    generated_work_queue = _generated_work_queue(24)
    autonomy_maintenance = _autonomy_maintenance_summary()
    operator_macros = _load_operator_macros(24)
    backend_commands = _load_backend_commands(40)
    memory_stats = nova_core.mem_stats_payload(emit_event=False)
    memory_summary = _memory_events_summary(80)
    tool_summary = _tool_events_summary(80)
    ledger_summary = _action_ledger_summary(80)
    patch_summary = nova_core.patch_status_payload()
    pulse_payload = nova_core.build_pulse_payload()
    update_now_pending = nova_core.update_now_pending_payload()
    with _METRICS_LOCK:
        requests_total = _HTTP_REQUESTS_TOTAL
        errors_total = _HTTP_ERRORS_TOTAL

    payload = CONTROL_STATUS_SERVICE.status_payload(
        policy=p,
        provider=provider,
        endpoint=endpoint,
        searx_ok=searx_ok,
        searx_note=searx_note,
        search_provider_priority=list(nova_core.get_search_provider_priority()),
        provider_telemetry=_provider_telemetry_payload(ledger_summary=ledger_summary, tool_summary=tool_summary),
        ollama_api_up=bool(nova_core.ollama_api_up()),
        chat_model=nova_core.chat_model(),
        memory_enabled=bool(nova_core.mem_enabled()),
        subconscious_summary=subconscious_summary,
        subconscious_live_summary=subconscious_live_summary,
        generated_work_queue=generated_work_queue,
        autonomy_maintenance=autonomy_maintenance,
        operator_macros=operator_macros,
        backend_commands=backend_commands,
        memory_scope=str((p.get("memory") or {}).get("scope") or "private"),
        web_enabled=bool((p.get("tools_enabled") or {}).get("web")) and bool(web_cfg.get("enabled")),
        allow_domains_count=len(web_cfg.get("allow_domains") or []),
        process_counting_mode="logical_leaf_processes" if os.name == "nt" else "direct_process_state",
        runtime_process_note=_runtime_process_note(),
        heartbeat_age_sec=_heartbeat_age_seconds(),
        active_http_sessions=len(SESSION_TURNS),
        chat_login_enabled=bool(_chat_login_enabled()),
        chat_auth_source=_chat_auth_source(),
        chat_users_count=len(_chat_users()),
        guard_status=guard_status,
        core_status=core_status,
        webui_status=webui_status,
        runtime_summary=_runtime_summary_payload(guard=guard_status, core=core_status, webui=webui_status),
        timeline_payload=timeline_payload,
        runtime_artifacts=_runtime_artifacts_payload(),
        runtime_restart_analytics=_runtime_restart_analytics_payload(),
        runtime_failures=_runtime_failure_reasons_payload(guard_status, core_status, webui_status, timeline_payload),
        live_tracking=nova_core.runtime_device_location_payload(),
        action_readiness=_action_readiness_payload(guard_status, core_status, webui_status),
        release_status=_release_status_payload(),
        memory_stats=memory_stats,
        memory_summary=memory_summary,
        tool_summary=tool_summary,
        ledger_summary=ledger_summary,
        patch_summary=patch_summary,
        patch_action_readiness=_patch_action_readiness_payload(patch_summary),
        pulse_payload=pulse_payload,
        update_now_pending=update_now_pending,
        requests_total=requests_total,
        errors_total=errors_total,
        schedule_tree=SCHEDULE_REGISTRY.get_schedule_status(autonomy_maintenance),
    )
    _append_metrics_snapshot(payload)
    # Derive health score from strict self-check ratio.
    sc = _build_self_check(payload, _control_policy_payload(), _metrics_payload())
    payload["health_score"] = int(sc.get("health_score", 0))
    payload["self_check_pass_ratio"] = float(sc.get("pass_ratio", 0.0))
    payload["alerts"] = list(sc.get("alerts") or [])
    return payload


def _cached_control_status_payload(max_age_seconds: float = CONTROL_STATUS_CACHE_TTL_SECONDS) -> dict:
    return CONTROL_STATUS_CACHE_SERVICE.cached_payload(
        _CONTROL_STATUS_CACHE,
        lock=_CONTROL_STATUS_CACHE_LOCK,
        max_age_seconds=max_age_seconds,
        monotonic_fn=time.monotonic,
        compute_payload_fn=_control_status_payload,
    )


def _control_policy_payload() -> dict:
    p = nova_core.load_policy()
    return {
        "ok": True,
        "tools_enabled": p.get("tools_enabled") or {},
        "models": p.get("models") or {},
        "memory": p.get("memory") or {},
        "web": p.get("web") or {},
        "chat_auth": _chat_auth_payload(),
    }


def _control_action(action: str, payload: dict) -> tuple[bool, str, dict]:
    act = (action or "").strip().lower()
    if not act:
        return False, "action_required", {}

    def _patch_control_state(*, include_readiness: bool = True) -> dict:
        patch = nova_core.patch_status_payload()
        previews = list(patch.get("previews") or []) if isinstance(patch.get("previews"), list) else []
        if not previews:
            previews = list(nova_core.patch_preview_summaries(40) or [])
        readiness_payload = _patch_action_readiness_payload(patch) if include_readiness else None
        return PATCH_CONTROL_SERVICE.patch_control_state(
            patch,
            previews,
            include_readiness=include_readiness,
            readiness_payload=readiness_payload,
        )

    if act == "refresh_status":
        ok, msg, extra, detail = _refresh_status_action(payload)
        _record_control_action_event(act, "ok" if ok else "fail", detail, payload)
        return ok, msg, extra

    if act == "device_location_update":
        ok, msg, extra, detail = _device_location_update_action(payload)
        _record_control_action_event(act, "ok" if ok else "fail", detail, payload)
        return ok, msg, extra

    if act == "device_location_clear":
        ok, msg, extra, detail = _device_location_clear_action(payload)
        _record_control_action_event(act, "ok" if ok else "fail", detail, payload)
        return ok, msg, extra

    if act == "patch_preview_list":
        ok, msg, extra, detail = _patch_preview_list_action(payload)
        _record_control_action_event(act, "ok" if ok else "fail", detail, payload)
        return ok, msg, extra

    if act == "patch_preview_show":
        ok, msg, extra, detail = PATCH_CONTROL_SERVICE.patch_preview_show(
            payload,
            preview_target_fn=lambda current_payload: PATCH_CONTROL_SERVICE.patch_preview_target(current_payload, nova_core.patch_preview_summaries(40)),
            patch_control_state_fn=_patch_control_state,
            show_preview_fn=nova_core.show_preview,
        )
        _record_control_action_event(act, "ok" if ok else "fail", detail, payload)
        return ok, msg, extra

    if act == "patch_preview_approve":
        ok, msg, extra, detail = PATCH_CONTROL_SERVICE.patch_preview_decision(
            "approve",
            payload,
            preview_target_fn=lambda current_payload: PATCH_CONTROL_SERVICE.patch_preview_target(current_payload, nova_core.patch_preview_summaries(40)),
            patch_control_state_fn=_patch_control_state,
            decision_fn=lambda target, note: nova_core.approve_preview(target, note=note),
        )
        _record_control_action_event(act, "ok" if ok else "fail", detail, payload)
        return ok, msg, extra

    if act == "patch_preview_reject":
        ok, msg, extra, detail = PATCH_CONTROL_SERVICE.patch_preview_decision(
            "reject",
            payload,
            preview_target_fn=lambda current_payload: PATCH_CONTROL_SERVICE.patch_preview_target(current_payload, nova_core.patch_preview_summaries(40)),
            patch_control_state_fn=_patch_control_state,
            decision_fn=lambda target, note: nova_core.reject_preview(target, note=note),
        )
        _record_control_action_event(act, "ok" if ok else "fail", detail, payload)
        return ok, msg, extra

    if act == "patch_preview_apply":
        ok, msg, extra, detail = PATCH_CONTROL_SERVICE.patch_preview_apply(
            payload,
            preview_target_fn=lambda current_payload: PATCH_CONTROL_SERVICE.patch_preview_target(current_payload, nova_core.patch_preview_summaries(40)),
            preview_entry_fn=lambda target: PATCH_CONTROL_SERVICE.patch_preview_entry(target, nova_core.patch_preview_summaries(40)),
            patch_control_state_fn=_patch_control_state,
            show_preview_fn=nova_core.show_preview,
            updates_dir=nova_core.UPDATES_DIR,
            patch_apply_fn=nova_core.patch_apply,
        )
        _record_control_action_event(act, "ok" if ok else "fail", detail, payload)
        return ok, msg, extra

    if act == "pulse_status":
        ok, msg, extra, detail = _pulse_status_action(payload)
        _record_control_action_event(act, "ok" if ok else "fail", detail, payload)
        return ok, msg, extra

    if act == "update_now_dry_run":
        ok, msg, extra, detail = _update_now_dry_run_action(payload)
        _record_control_action_event(act, "ok" if ok else "fail", detail, payload)
        return ok, msg, extra

    if act == "update_now_confirm":
        ok, msg, extra, detail = _update_now_confirm_action(payload)
        _record_control_action_event(act, "ok" if ok else "fail", detail, payload)
        return ok, msg, extra

    if act == "update_now_cancel":
        ok, msg, extra, detail = _update_now_cancel_action(payload)
        _record_control_action_event(act, "ok" if ok else "fail", detail, payload)
        return ok, msg, extra

    if act == "runtime_artifact_show":
        ok, msg, extra, detail = _runtime_artifact_show_action(payload)
        _record_control_action_event(act, "ok" if ok else "fail", detail, payload)
        return ok, msg, extra

    if act in {"guard_status", "guard_start", "guard_stop", "guard_restart"}:
        ok, msg, extra, detail = _guard_control_action({**payload, "_action": act})
        _record_control_action_event(act, "ok" if ok else "fail", detail, payload)
        return ok, msg, extra

    if act in {"nova_start", "core_stop", "core_restart", "webui_restart"}:
        ok, msg, extra, detail = _core_runtime_action({**payload, "_action": act})
        _record_control_action_event(act, "ok" if ok else "fail", detail, payload)
        return ok, msg, extra

    if act in {"autonomy_maintenance_start", "autonomy_maintenance_stop"}:
        ok, msg, extra, detail = _autonomy_runtime_action({**payload, "_action": act})
        if ok:
            _invalidate_control_status_cache()
        _record_control_action_event(act, "ok" if ok else "fail", detail, payload)
        return ok, msg, extra

    if act == "test_session_run":
        ok, msg, extra, detail = _test_session_run_action(payload)
        _record_control_action_event(act, "ok" if ok else "fail", detail, payload)
        return ok, msg, extra

    if act == "generated_pack_run":
        ok, msg, extra, detail = _generated_pack_run_action(payload)
        _record_control_action_event(act, "ok" if ok else "fail", detail, payload)
        return ok, msg, extra

    if act == "generated_queue_run_next":
        ok, msg, extra, detail = _generated_queue_run_next_action(payload)
        _record_control_action_event(act, "ok" if ok else "fail", detail, payload)
        return ok, msg, extra

    if act == "generated_queue_investigate":
        ok, msg, extra, detail = _generated_queue_investigate_action(payload)
        _record_control_action_event(act, "ok" if ok else "fail", detail, payload)
        return ok, msg, extra

    if act == "real_world_task_create":
        ok, msg, extra, detail = _real_world_task_create_action(payload)
        _record_control_action_event(act, "ok" if ok else "fail", detail, payload)
        return ok, msg, extra

    if act == "backend_command_list":
        ok, msg, extra, detail = _backend_command_list_action(payload)
        _record_control_action_event(act, "ok" if ok else "fail", detail, payload)
        return ok, msg, extra

    if act == "backend_command_run":
        ok, msg, extra, detail = _backend_command_run_action(payload)
        _record_control_action_event(act, "ok" if ok else "fail", detail, payload)
        return ok, msg, extra

    if act == "operator_prompt":
        ok, msg, extra, detail, audit_payload = _operator_prompt_action(payload)
        _record_control_action_event(act, "ok" if ok else "fail", detail, audit_payload)
        return ok, msg, extra

    if act == "session_delete":
        ok, msg, extra, detail = _session_delete_action(payload)
        _record_control_action_event(act, "ok" if ok else "fail", detail, payload)
        return ok, msg, extra

    if act == "policy_allow":
        ok, msg, extra, detail = _policy_allow_action(payload)
        _record_control_action_event(act, "ok" if ok else "fail", detail, payload)
        return ok, msg, extra

    if act == "policy_remove":
        ok, msg, extra, detail = _policy_remove_action(payload)
        _record_control_action_event(act, "ok" if ok else "fail", detail, payload)
        return ok, msg, extra

    if act == "web_mode":
        ok, msg, extra, detail = _web_mode_action(payload)
        _record_control_action_event(act, "ok" if ok else "fail", detail, payload)
        return ok, msg, extra

    if act == "memory_scope_set":
        ok, msg, extra, detail = _memory_scope_set_action(payload)
        _record_control_action_event(act, "ok" if ok else "fail", detail, payload)
        return ok, msg, extra

    if act == "search_provider":
        ok, msg, extra, detail = _search_provider_action(payload)
        _record_control_action_event(act, "ok" if ok else "fail", detail, payload)
        return ok, msg, extra

    if act == "search_provider_toggle":
        ok, msg, extra, detail = _search_provider_toggle_action(payload)
        _record_control_action_event(act, "ok" if ok else "fail", detail, payload)
        return ok, msg, extra

    if act == "search_endpoint_set":
        ok, msg, extra, detail = _search_endpoint_set_action(payload)
        _record_control_action_event(act, "ok" if ok else "fail", detail, payload)
        return ok, msg, extra

    if act == "search_provider_priority_set":
        ok, msg, extra, detail = _search_provider_priority_set_action(payload)
        _record_control_action_event(act, "ok" if ok else "fail", detail, payload)
        return ok, msg, extra

    if act == "search_endpoint_probe":
        ok, msg, extra, detail = _search_endpoint_probe_action(payload)
        _record_control_action_event(act, "ok" if ok else "fail", detail, payload)
        return ok, msg, extra

    if act == "chat_user_list":
        ok, msg, extra, detail = _chat_user_list_action(payload)
        _record_control_action_event(act, "ok" if ok else "fail", detail, payload)
        return ok, msg, extra

    if act == "chat_user_upsert":
        ok, msg, extra, detail = _chat_user_upsert_action(payload)
        _record_control_action_event(act, "ok" if ok else "fail", detail, payload)
        return ok, msg, extra

    if act == "chat_user_delete":
        ok, msg, extra, detail = _chat_user_delete_action(payload)
        _record_control_action_event(act, "ok" if ok else "fail", detail, payload)
        return ok, msg, extra

    if act == "inspect":
        try:
            data = nova_core.inspect_environment()
            report = nova_core.format_report(data)
            _record_control_action_event(act, "ok", "inspect_ok", payload)
            return True, "inspect_ok", {"report": report}
        except Exception as e:
            _record_control_action_event(act, "fail", str(e), payload)
            return False, f"inspect_failed:{e}", {}

    if act == "policy_audit":
        try:
            text = nova_core.policy_audit(30)
            _record_control_action_event(act, "ok", "policy_audit_ok", payload)
            return True, "policy_audit_ok", {"text": text}
        except Exception as e:
            _record_control_action_event(act, "fail", str(e), payload)
            return False, f"policy_audit_failed:{e}", {}

    if act == "tail_log":
        return _tail_log_action(payload)

    if act == "metrics":
        return _metrics_action(payload)

    if act == "self_check":
        ok, msg, extra, detail = _self_check_action(payload)
        _record_control_action_event(act, "ok" if ok else "fail", detail, payload)
        return ok, msg, extra

    if act == "export_capabilities":
        ok, msg, extra = _export_capabilities_snapshot()
        _record_control_action_event(act, "ok" if ok else "fail", msg, payload)
        return ok, msg, extra

    if act == "export_ledger_summary":
        return _export_ledger_summary_action(payload)

    if act == "export_diagnostics_bundle":
        return _export_diagnostics_bundle_action(payload)

    _record_control_action_event(act, "fail", "unknown_action", payload)
    return False, "unknown_action", {}


def _trim_turns(turns: List[Tuple[str, str]]) -> None:
    http_session_store.trim_turns(turns, max_turns=MAX_TURNS)


def _json_response(handler: BaseHTTPRequestHandler, code: int, payload: dict) -> None:
    _json_response_with_headers(handler, code, payload)


def _json_response_with_headers(
    handler: BaseHTTPRequestHandler,
    code: int,
    payload: dict,
    headers: dict[str, str] | None = None,
) -> None:
    body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    for key, value in (headers or {}).items():
        handler.send_header(key, value)
    handler.end_headers()
    handler.wfile.write(body)
    _record_http_response(code)


def _fast_smalltalk_reply(user_text: str) -> str | None:
    return nova_core._quick_smalltalk_reply(user_text, active_user=nova_core.get_active_user())


def _diagnostic_reply(known: str, missing: str, need: str) -> str:
    return f"I know: {known} I do not yet know: {missing} To answer better, I need: {need}"


def _text_response(handler: BaseHTTPRequestHandler, code: int, text: str) -> None:
    body = text.encode("utf-8")
    handler.send_response(code)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(body)
    _record_http_response(code)


def _file_response(handler: BaseHTTPRequestHandler, code: int, path: Path, content_type: str) -> None:
    try:
        body = path.read_bytes()
    except Exception as e:
        _json_response(handler, 404, {"ok": False, "error": f"asset_not_found:{path.name}:{e}"})
        return
    handler.send_response(code)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(body)
    _record_http_response(code)


def _developer_color_reply(turns: List[Tuple[str, str]]) -> str:
    prefs = nova_core._extract_developer_color_preferences(turns)
    from_memory = False
    if not prefs:
        prefs = nova_core._extract_developer_color_preferences_from_memory()
        from_memory = bool(prefs)
    if not prefs:
        return "I don't have Gus's color preferences yet."
    if len(prefs) == 1:
        reply = f"From what you've told me, Gus likes {prefs[0]}."
    else:
        reply = "From what you've told me, Gus likes these colors: " + ", ".join(prefs[:-1]) + f", and {prefs[-1]}."
    return nova_core._prefix_from_earlier_memory(reply) if from_memory else reply


def _developer_bilingual_reply(turns: List[Tuple[str, str]]) -> str:
    known = nova_core._developer_is_bilingual(turns)
    from_memory = False
    if known is None:
        known = nova_core._developer_is_bilingual_from_memory()
        from_memory = known is not None
    if known is True:
        reply = "Yes. From what you've told me, Gus is bilingual in English and Spanish."
        return nova_core._prefix_from_earlier_memory(reply) if from_memory else reply
    if known is False:
        reply = "From what I have, Gus is not bilingual."
        return nova_core._prefix_from_earlier_memory(reply) if from_memory else reply
    return "I don't have confirmed language details for Gus yet."


def _is_developer_profile_request(user_text: str) -> bool:
    return nova_core._is_developer_profile_request(user_text)


def _developer_profile_reply(turns: List[Tuple[str, str]], user_text: str) -> str:
    return nova_core._developer_profile_reply(turns, user_text)


def _is_developer_location_request(user_text: str, state: dict | None = None, turns: List[Tuple[str, str]] | None = None) -> bool:
    return nova_core._is_developer_location_request(user_text, state=state, turns=turns)


def _developer_location_reply() -> str:
    return nova_core._developer_location_reply()


def _recent_turn_mentions(turns: List[Tuple[str, str]], keywords: list[str], limit: int = 6) -> bool:
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


def _learn_contextual_developer_facts(turns: List[Tuple[str, str]], text: str) -> tuple[bool, str]:
    return nova_core._learn_contextual_developer_facts(turns, text, input_source="typed")


def _is_location_request(user_text: str) -> bool:
    return nova_core._is_location_request(user_text)


def _location_reply() -> str:
    return nova_core._location_reply()


def _color_reply(turns: List[Tuple[str, str]]) -> str:
    prefs = nova_core._extract_color_preferences(turns)
    from_memory = False
    if not prefs:
        prefs = nova_core._extract_color_preferences_from_memory()
        from_memory = bool(prefs)
    if not prefs:
        return "You haven't told me a color preference in this current chat yet."
    if len(prefs) == 1:
        reply = f"You told me you like the color {prefs[0]}."
    else:
        reply = "You told me you like these colors: " + ", ".join(prefs[:-1]) + f", and {prefs[-1]}."
    return nova_core._prefix_from_earlier_memory(reply) if from_memory else reply


def _animal_reply(turns: List[Tuple[str, str]]) -> str:
    animals = nova_core._extract_animal_preferences(turns)
    from_memory = False
    if not animals:
        animals = nova_core._extract_animal_preferences_from_memory()
        from_memory = bool(animals)
    if not animals:
        return "You haven't told me animal preferences yet in this chat, and I can't find them in saved memory."
    if len(animals) == 1:
        reply = f"You told me you like {animals[0]}."
    else:
        reply = "You told me you like: " + ", ".join(animals[:-1]) + f", and {animals[-1]}."
    return nova_core._prefix_from_earlier_memory(reply) if from_memory else reply


def _extract_last_user_question(turns: List[Tuple[str, str]], current_text: str) -> str:
    return nova_core._extract_last_user_question(turns, current_text)


def _is_name_origin_question(text: str) -> bool:
    return nova_core._is_name_origin_question(text)


def _is_assistant_name_query(text: str) -> bool:
    return nova_core._is_assistant_name_query(text)


def _assistant_name_reply(text: str) -> str:
    return nova_core._assistant_name_reply(text)


def _is_developer_full_name_query(text: str) -> bool:
    return nova_core._is_developer_full_name_query(text)


def _developer_full_name_reply() -> str:
    return nova_core._developer_full_name_reply()


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
    keep, _reason = nova_core._memory_should_keep_text(cleaned)
    return cleaned if keep else ""


def _rules_reply() -> str:
    return nova_core._rules_reply()


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


def _is_session_recap_request(text: str) -> bool:
    return nova_core._is_session_recap_request(text)


def _session_recap_reply(turns: List[Tuple[str, str]], current_text: str) -> str:
    return nova_core._session_recap_reply(turns, current_text)


def _is_deep_search_followup_request(text: str) -> bool:
    del text
    return False


def _infer_research_query_from_turns(turns: List[Tuple[str, str]]) -> str:
    return nova_core._infer_research_query_from_turns(turns)


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


def _extract_key_lines(text: str, max_lines: int = 5) -> List[str]:
    out: List[str] = []
    for raw in (text or "").splitlines():
        s = (raw or "").strip().lstrip("-•").strip()
        if not s:
            continue
        if len(s) < 12:
            continue
        if s.lower().startswith("attendance reporting"):
            continue
        out.append(s.rstrip("."))
        if len(out) >= max_lines:
            break
    return out


def _topic_tokens(text: str) -> List[str]:
    low = (text or "").lower()
    toks = re.findall(r"[a-z0-9]{3,}", low)
    stop = {
        "what", "when", "where", "which", "about", "could", "would", "should",
        "there", "their", "have", "your", "with", "from", "that", "this",
        "please", "tell", "more", "info", "information", "topic",
    }
    out: List[str] = []
    for t in toks:
        if t in stop:
            continue
        if t not in out:
            out.append(t)
    return out[:12]


def _extract_matching_lines(text: str, tokens: List[str], max_lines: int = 3) -> List[str]:
    if not tokens:
        return _extract_key_lines(text, max_lines=max_lines)
    out: List[str] = []
    for raw in (text or "").splitlines():
        s = (raw or "").strip().lstrip("-•").strip()
        if not s or len(s) < 14:
            continue
        low = s.lower()
        score = sum(1 for t in tokens if t in low)
        if score <= 0:
            continue
        out.append(s.rstrip("."))
        if len(out) >= max_lines:
            break
    if out:
        return out
    return _extract_key_lines(text, max_lines=max_lines)


def _build_local_topic_digest_answer(query_text: str, max_files: int = 4, max_points: int = 10) -> str:
    return nova_core._build_local_topic_digest_answer(query_text, max_files=max_files, max_points=max_points)


def _is_peims_attendance_rules_query(text: str) -> bool:
    low = (text or "").strip().lower()
    if not low:
        return False
    return "peims" in low and "attendance" in low and any(token in low for token in ("rule", "rules", "reporting", "report"))


def _is_peims_broad_query(text: str) -> bool:
    del text
    return False


def _is_web_preferred_data_query(text: str) -> bool:
    low = (text or "").strip().lower()
    if not low:
        return False
    data_terms = (
        "peims",
        "tsds",
        "attendance",
        "ada",
        "submission",
        "submissions",
        "student data",
        "records",
        "reporting",
        "data system",
    )
    if not any(term in low for term in data_terms):
        return False
    broad_cues = (
        "anything about",
        "what do you know about",
        "tell me about",
        "explain",
        "overview",
        "summary",
        "information",
        "anything",
    )
    return any(cue in low for cue in broad_cues)


def _extract_urls(text: str) -> List[str]:
    seen = set()
    out = []
    for u in re.findall(r"https?://[^\s<>\]')\"]+", text or ""):
        clean = (u or "").strip().rstrip(".,;:)")
        if clean and clean not in seen:
            seen.add(clean)
            out.append(clean)
    return out


def _host_label(url: str) -> str:
    try:
        return (urlparse(url).hostname or "source").lower()
    except Exception:
        return "source"


def _summary_from_gather_output(raw: str) -> str:
    txt = (raw or "").strip()
    if not txt:
        return ""
    m = re.search(r"(?is)Summary snippet:\s*(.+)$", txt)
    if not m:
        return ""
    s = re.sub(r"\s+", " ", (m.group(1) or "").strip())
    # Keep grounded summary brief and readable.
    return s[:260]


def _is_weak_grounded_snippet(s: str) -> bool:
    low = (s or "").strip().lower()
    if not low:
        return True
    weak_cues = [
        "welcome to texas education agency",
        "skip to main content",
        "mega menu",
        "general information",
        "enable javascript to run this app",
        "you need to enable javascript to run this app",
    ]
    if any(c in low for c in weak_cues):
        return True
    # Avoid using extremely short/unspecific snippets as factual grounding.
    if len(low.split()) < 8:
        return True
    return False


def _is_conversational_clarification(text: str) -> bool:
    low = (text or "").strip().lower()
    if not low:
        return False
    cues = [
        "what are you talking about",
        "what are you talking",
        "are you sure about that information",
        "are you sure about that",
        "why i am not asking you",
        "why am i not asking you",
        "you will not find that information",
        "do you need help",
        "what ?",
        "what?",
    ]
    return any(c in low for c in cues)


def _clarification_reply(turns: List[Tuple[str, str]]) -> str:
    reply, _kind = nova_core._open_probe_reply("what are you talking about ?", turns=turns)
    return reply


def _normalize_bypass_phrase(text: str) -> str:
    normalized = re.sub(r"\s+", " ", str(text or "").strip().lower())
    return normalized.strip(" .,!?:;\t\r\n")


def _prefer_llm_fallback_over_planner(text: str) -> bool:
    normalized = _normalize_bypass_phrase(text)
    return normalized in {
        "explain photosynthesis briefly",
        "please explain photosynthesis briefly",
    }


def _is_groundable_factual_query(text: str) -> bool:
    del text
    return False


def _build_grounded_answer(query_text: str, max_sources: int = 2) -> str:
    research = nova_core.tool_web_research(query_text)
    if not isinstance(research, str) or not research.strip():
        return ""

    urls = _extract_urls(research)
    if not urls:
        return ""

    snippets: List[tuple[str, str]] = []
    for u in urls[: max(1, int(max_sources))]:
        g = nova_core.tool_web_gather(u)
        snip = _summary_from_gather_output(g if isinstance(g, str) else "")
        if snip and not _is_weak_grounded_snippet(snip):
            snippets.append((u, snip))

    # If all gathered snippets are too generic, let caller use deterministic fallback.
    if not snippets:
        return ""

    lines = []
    lines.append("I found sourced information from allowlisted references:")
    for u, snip in snippets:
        lines.append(f"- {snip}")

    cited_hosts = []
    for u in urls[: max(1, int(max_sources))]:
        host = _host_label(u)
        if host not in cited_hosts:
            cited_hosts.append(host)
    for h in cited_hosts:
        lines.append(f"[source: {h}]")

    return "\n".join(lines)


def _peims_attendance_rules_reply() -> str:
    grounded = _build_grounded_answer("PEIMS attendance reporting rules Texas TEA", max_sources=2)
    if grounded:
        return grounded
    local_grounded = _build_local_topic_digest_answer("PEIMS attendance reporting rules")
    if local_grounded:
        return local_grounded
    return nova_core._detached_domain_reply("PEIMS", "web research PEIMS attendance reporting rules")


def _generate_chat_reply(
    turns: List[Tuple[str, str]],
    text: str,
    ledger_record: dict | None = None,
    pending_action: dict | None = None,
    prefer_web_for_data_queries: bool = False,
    language_mix_spanish_pct: int = 0,
    session=None,
) -> tuple[str, dict]:
    def _trace(stage: str, outcome: str, detail: str = "", **data) -> None:
        nova_core.action_ledger_add_step(ledger_record, stage, outcome, detail, **data)

    def _normalize_reply(reply_text: str) -> str:
        reply_local = _strip_ui_tip_leak(reply_text)
        corrected_reply, was_corrected, _reason = nova_core._self_correct_reply(text, reply_local)
        if was_corrected:
            nova_core.behavior_record_event("correction_applied")
            nova_core.behavior_record_event("self_correction_applied")
            _trace("llm_postprocess", "self_corrected")
            reply_local = corrected_reply
        if not nova_core._is_identity_stable_reply(reply_local):
            reply_local = nova_core._apply_reply_overrides(reply_local)
        return nova_core._ensure_reply(reply_local)

    low = text.lower()
    if _is_location_request(text):
        _trace("deterministic_reply", "matched", detail="location_reply")
        reply = _location_reply()
        return _normalize_reply(reply), {
            "planner_decision": "deterministic",
            "tool": "location",
            "tool_args": {"query": text},
            "tool_result": reply,
            "grounded": True,
        }

    force_llm_fallback = _prefer_llm_fallback_over_planner(text)
    if not force_llm_fallback:
        handled_truth, truth_reply, _truth_source, _truth_grounded = nova_core.truth_hierarchy_answer(text)
        if handled_truth:
            _trace("truth_hierarchy", "matched", tool=str(_truth_source or ""), grounded=bool(_truth_grounded))
            reply = truth_reply
            used_hard_answer = False
            # For creator/name profile prompts, prefer deterministic hard answers when available.
            if _is_developer_profile_request(text):
                hard = nova_core.hard_answer(text)
                if hard:
                    reply = hard
                    used_hard_answer = True
                elif reply.lower().startswith("uncertain. no structured identity fact"):
                    reply = _developer_profile_reply(turns, text)
            elif reply.lower().startswith("uncertain. no structured identity fact"):
                if _is_location_request(text):
                    reply = _location_reply()
                else:
                    hard = nova_core.hard_answer(text)
                    if hard:
                        reply = hard
                        used_hard_answer = True
            final_reply = nova_core._ensure_reply(reply) if used_hard_answer else _normalize_reply(reply)
            return final_reply, {
                "planner_decision": "truth_hierarchy",
                "tool": str(_truth_source or ""),
                "tool_args": {"query": text},
                "tool_result": str(reply or ""),
                "grounded": bool(_truth_grounded),
            }
        _trace("truth_hierarchy", "not_matched")

        hard = nova_core.hard_answer(text)
        if hard:
            _trace("hard_answer", "matched", grounded=True)
            reply = nova_core._ensure_reply(hard)
            return reply, {
                "planner_decision": "deterministic",
                "tool": "hard_answer",
                "tool_args": {"query": text},
                "tool_result": reply,
                "grounded": True,
            }
        _trace("hard_answer", "not_matched")

        if _is_developer_profile_request(text):
            actions = []
        else:
            try:
                actions = nova_core.decide_actions(
                    text,
                    config={
                        "session_turns": turns,
                        "pending_action": pending_action or {},
                        "prefer_web_for_data_queries": prefer_web_for_data_queries,
                    },
                )
            except Exception:
                actions = []
    else:
        _trace("llm_fallback_override", "matched", detail="prefer_llm_over_planner")
        actions = []

    if actions:
        act = actions[0]
        atype = act.get("type")
        if atype == "ask_clarify":
            _trace("action_planner", "ask_clarify")
            reply = act.get("question") or act.get("note") or "Can you clarify?"
            return _normalize_reply(reply), {
                "planner_decision": "ask_clarify",
                "tool": "",
                "tool_args": {"query": text},
                "tool_result": str(reply or ""),
                "grounded": False,
                "pending_action": nova_core.make_pending_weather_action() if "weather lookup" in str(reply or "").lower() else {},
            }

        if atype == "respond":
            _trace("action_planner", "respond")
            reply = act.get("note") or act.get("message") or "Tell me a bit more about what you want me to inspect."
            return _normalize_reply(reply), {
                "planner_decision": "respond",
                "tool": "",
                "tool_args": {"query": text},
                "tool_result": str(reply or ""),
                "grounded": False,
            }

        if atype == "route_command":
            _trace("action_planner", "route_command")
            cmd_reply = nova_core.handle_commands(text, session_turns=turns, session=session)
            if cmd_reply:
                tool_name = "weather" if "api.weather.gov" in str(cmd_reply).lower() else ""
                _trace("command", "matched", tool=tool_name)
                return _normalize_reply(cmd_reply), {
                    "planner_decision": "command",
                    "tool": tool_name,
                    "tool_args": {"raw": text},
                    "tool_result": str(cmd_reply or ""),
                    "grounded": bool(tool_name),
                    "pending_action": {},
                }
            _trace("command", "not_matched")

        if atype == "route_keyword":
            _trace("action_planner", "route_keyword")
            kw = nova_core.handle_keywords(text)
            if kw:
                _kind, _tool, out = kw
                _trace("keyword_tool", "matched", tool=str(_tool or ""), grounded=bool(str(out or "").strip()))
                return _normalize_reply(str(out or "")), {
                    "planner_decision": "run_tool",
                    "tool": str(_tool or ""),
                    "tool_args": {"raw": text},
                    "tool_result": str(out or ""),
                    "grounded": bool(str(out or "").strip()),
                    "pending_action": {},
                }
            _trace("keyword_tool", "not_matched")

        if atype == "run_tool":
            tool = str(act.get("tool") or "")
            args = act.get("args") or []
            _trace("action_planner", "run_tool", tool=tool)
            out = nova_core.execute_planned_action(tool, args)
            if out is None or (isinstance(out, str) and not out.strip()):
                _trace("tool_execution", "empty_result", tool=tool)
                reply = nova_core._web_allowlist_message("requested resource") if tool.startswith("web") else f"The {tool} tool did not return a result. No data was available."
                return _normalize_reply(reply), {
                    "planner_decision": "run_tool",
                    "tool": tool,
                    "tool_args": {"args": list(args) if isinstance(args, (list, tuple)) else args},
                    "tool_result": "",
                    "grounded": False,
                    "pending_action": {},
                }
            if isinstance(out, dict) and not out.get("ok", True):
                _trace("tool_execution", "error", tool=tool, error=str(out.get("error") or "unknown error"))
                err = out.get("error", "unknown error")
                if isinstance(err, str) and ("not allowed" in err.lower() or "domain not allowed" in err.lower()):
                    reply = nova_core._web_allowlist_message(args[0] if args else "")
                else:
                    reply = f"Tool {tool} failed: {err}"
                return _normalize_reply(reply), {
                    "planner_decision": "run_tool",
                    "tool": tool,
                    "tool_args": {"args": list(args) if isinstance(args, (list, tuple)) else args},
                    "tool_result": json.dumps(out, ensure_ascii=True),
                    "grounded": False,
                    "pending_action": {},
                }
            if str(tool or "").strip().lower() == "web_research":
                query_text = str(args[0] if isinstance(args, (list, tuple)) and args else text)
                if _is_peims_attendance_rules_query(query_text):
                    reply = _peims_attendance_rules_reply()
                    _trace("grounded_lookup", "matched", tool="web_research")
                    return _normalize_reply(reply), {
                        "planner_decision": "grounded_lookup",
                        "tool": "web_research",
                        "tool_args": {"query": query_text},
                        "tool_result": reply,
                        "grounded": bool("[source:" in str(reply).lower()),
                        "pending_action": {},
                    }
            _trace("tool_execution", "ok", tool=tool, grounded=bool(str(out or "").strip()))
            return _normalize_reply(str(out or "")), {
                "planner_decision": "run_tool",
                "tool": tool,
                "tool_args": {"args": list(args) if isinstance(args, (list, tuple)) else args},
                "tool_result": str(out or ""),
                "grounded": bool(str(out or "").strip()),
                "pending_action": {},
            }

    if prefer_web_for_data_queries and _is_web_preferred_data_query(text):
        _trace("session_override", "matched", detail="prefer_web_for_data_queries", tool="web_research")
        out = nova_core.execute_planned_action("web_research", [text])
        if out is None or (isinstance(out, str) and not out.strip()):
            out = nova_core.tool_web_research(text)
        if isinstance(out, dict) and not out.get("ok", True):
            _trace("tool_execution", "error", tool="web_research", error=str(out.get("error") or "unknown error"))
            err = out.get("error", "unknown error")
            reply = f"Tool web_research failed: {err}"
            return _normalize_reply(reply), {
                "planner_decision": "run_tool",
                "tool": "web_research",
                "tool_args": {"args": [text]},
                "tool_result": json.dumps(out, ensure_ascii=True),
                "grounded": False,
                "pending_action": {},
            }
        if str(out or "").strip():
            if _is_peims_attendance_rules_query(text):
                reply = _peims_attendance_rules_reply()
                _trace("grounded_lookup", "matched", tool="web_research")
                return _normalize_reply(reply), {
                    "planner_decision": "grounded_lookup",
                    "tool": "web_research",
                    "tool_args": {"query": text},
                    "tool_result": reply,
                    "grounded": bool("[source:" in str(reply).lower()),
                    "pending_action": {},
                }
            _trace("tool_execution", "ok", tool="web_research", grounded=True)
            return _normalize_reply(str(out or "")), {
                "planner_decision": "run_tool",
                "tool": "web_research",
                "tool_args": {"args": [text]},
                "tool_result": str(out or ""),
                "grounded": True,
                "pending_action": {},
            }
        _trace("tool_execution", "empty_result", tool="web_research")

    if _is_session_recap_request(text):
        _trace("deterministic_reply", "matched", detail="session_recap")
        reply = _session_recap_reply(turns, text)
        return _normalize_reply(reply), {
            "planner_decision": "deterministic",
            "tool": "session_recap",
            "tool_args": {"query": text},
            "tool_result": reply,
            "grounded": True,
        }
    elif _is_assistant_name_query(text):
        _trace("deterministic_reply", "matched", detail="assistant_name")
        reply = _assistant_name_reply(text)
        return _normalize_reply(reply), {
            "planner_decision": "deterministic",
            "tool": "assistant_name",
            "tool_args": {"query": text},
            "tool_result": reply,
            "grounded": True,
        }
    elif _is_developer_full_name_query(text):
        _trace("deterministic_reply", "matched", detail="developer_full_name")
        reply = _developer_full_name_reply()
        return _normalize_reply(reply), {
            "planner_decision": "deterministic",
            "tool": "developer_identity",
            "tool_args": {"query": text},
            "tool_result": reply,
            "grounded": True,
        }
    elif "do you remember our last chat session" in low or "remember our last chat" in low:
        _trace("deterministic_reply", "matched", detail="memory_policy_explanation")
        reply = "I remember parts of prior chats only if they were saved to memory; I remember this live session context directly."
        return _normalize_reply(reply), {
            "planner_decision": "deterministic",
            "tool": "memory_policy",
            "tool_args": {"query": text},
            "tool_result": reply,
            "grounded": True,
        }
    elif _is_name_origin_question(text):
        _trace("deterministic_reply", "matched", detail="name_origin_query")
        story = nova_core.get_name_origin_story().strip()
        if story:
            reply = f"Yes. {story}"
        else:
            reply = "I do not have a saved name-origin story yet. You can tell me with: remember this Nova ..."
        return _normalize_reply(reply), {
            "planner_decision": "deterministic",
            "tool": "name_origin",
            "tool_args": {"query": text},
            "tool_result": reply,
            "grounded": bool(story),
        }
    elif _is_peims_attendance_rules_query(text):
        _trace("grounded_lookup", "matched", tool="peims_attendance")
        reply = _peims_attendance_rules_reply()
        return _normalize_reply(reply), {
            "planner_decision": "grounded_lookup",
            "tool": "peims_attendance",
            "tool_args": {"query": text},
            "tool_result": reply,
            "grounded": "[source:" in reply.lower(),
        }
    elif _is_developer_profile_request(text):
        _trace("deterministic_reply", "matched", detail="developer_profile")
        reply = _developer_profile_reply(turns, text)
        return _normalize_reply(reply), {
            "planner_decision": "deterministic",
            "tool": "developer_profile",
            "tool_args": {"query": text},
            "tool_result": reply,
            "grounded": True,
        }
    elif _is_conversational_clarification(text):
        _trace("deterministic_reply", "matched", detail="clarification_reply")
        reply = _clarification_reply(turns)
        return _normalize_reply(reply), {
            "planner_decision": "deterministic",
            "tool": "clarification_reply",
            "tool_args": {"query": text},
            "tool_result": reply,
            "grounded": True,
        }
    elif _is_location_request(text):
        _trace("deterministic_reply", "matched", detail="location_reply")
        reply = _location_reply()
        return _normalize_reply(reply), {
            "planner_decision": "deterministic",
            "tool": "location",
            "tool_args": {"query": text},
            "tool_result": reply,
            "grounded": True,
        }
    elif _is_deep_search_followup_request(text):
        inferred = _infer_research_query_from_turns(turns)
        query = inferred or text
        grounded = _build_grounded_answer(query, max_sources=2)
        if grounded:
            _trace("grounded_lookup", "matched", tool="web_research")
            reply = grounded
            return _normalize_reply(reply), {
                "planner_decision": "grounded_lookup",
                "tool": "web_research",
                "tool_args": {"query": query},
                "tool_result": reply,
                "grounded": True,
            }
        else:
            local_grounded = _build_local_topic_digest_answer(query)
            if local_grounded:
                _trace("grounded_lookup", "matched", tool="local_knowledge")
                reply = local_grounded
                return _normalize_reply(reply), {
                    "planner_decision": "grounded_lookup",
                    "tool": "local_knowledge",
                    "tool_args": {"query": query},
                    "tool_result": reply,
                    "grounded": True,
                }
            else:
                _trace("grounded_lookup", "missed", tool="web_research")
                reply = "I could not find additional grounded sources right now. Please try: web research <topic>"
                return _normalize_reply(reply), {
                    "planner_decision": "grounded_lookup",
                    "tool": "web_research",
                    "tool_args": {"query": query},
                    "tool_result": reply,
                    "grounded": False,
                }
    elif _is_groundable_factual_query(text):
        grounded = _build_grounded_answer(text, max_sources=2)
        if grounded:
            _trace("grounded_lookup", "matched", tool="web_research")
            reply = grounded
            return _normalize_reply(reply), {
                "planner_decision": "grounded_lookup",
                "tool": "web_research",
                "tool_args": {"query": text},
                "tool_result": reply,
                "grounded": True,
            }
        else:
            local_grounded = _build_local_topic_digest_answer(text)
            if local_grounded:
                _trace("grounded_lookup", "matched", tool="local_knowledge")
                reply = local_grounded
                return _normalize_reply(reply), {
                    "planner_decision": "grounded_lookup",
                    "tool": "local_knowledge",
                    "tool_args": {"query": text},
                    "tool_result": reply,
                    "grounded": True,
                }
            else:
                _trace("grounded_lookup", "missed", tool="web_research")
                reply = "I couldn't find grounded sources for that yet. Please try: web research <your question>"
                return _normalize_reply(reply), {
                    "planner_decision": "grounded_lookup",
                    "tool": "web_research",
                    "tool_args": {"query": text},
                    "tool_result": reply,
                    "grounded": False,
                }
    elif nova_core._is_developer_color_lookup_request(text):
        _trace("deterministic_reply", "matched", detail="developer_color_reply")
        reply = _developer_color_reply(turns)
        return _normalize_reply(reply), {
            "planner_decision": "deterministic",
            "tool": "developer_color_reply",
            "tool_args": {"query": text},
            "tool_result": reply,
            "grounded": True,
        }
    elif nova_core._is_developer_bilingual_request(text):
        _trace("deterministic_reply", "matched", detail="developer_bilingual_reply")
        reply = _developer_bilingual_reply(turns)
        return _normalize_reply(reply), {
            "planner_decision": "deterministic",
            "tool": "developer_bilingual_reply",
            "tool_args": {"query": text},
            "tool_result": reply,
            "grounded": True,
        }
    elif nova_core._is_color_lookup_request(text):
        _trace("deterministic_reply", "matched", detail="color_reply")
        reply = _color_reply(turns)
        return _normalize_reply(reply), {
            "planner_decision": "deterministic",
            "tool": "color_reply",
            "tool_args": {"query": text},
            "tool_result": reply,
            "grounded": True,
        }
    elif "what animals do i like" in low or "which animals do i like" in low:
        _trace("deterministic_reply", "matched", detail="animal_reply")
        reply = _animal_reply(turns)
        return _normalize_reply(reply), {
            "planner_decision": "deterministic",
            "tool": "animal_reply",
            "tool_args": {"query": text},
            "tool_result": reply,
            "grounded": True,
        }
    else:
        task = nova_core.analyze_request(
            text,
            config={"prefer_web_for_data_queries": prefer_web_for_data_queries},
        )
        if not getattr(task, "allow_llm", False):
            _trace("policy_gate", "blocked", detail=str(getattr(task, "message", "") or "")[:160])
            reply = str(getattr(task, "message", "") or "")
            return _normalize_reply(reply), {
                "planner_decision": "policy_block",
                "tool": "",
                "tool_args": {},
                "tool_result": "",
                "grounded": True,
            }
        _trace("policy_gate", "allowed")

        fallback_context = nova_core.build_fallback_context_details(text, turns)
        retrieved = str(fallback_context.get("context") or "")
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
        if nova_core.should_block_low_confidence(text, retrieved_context=retrieved):
            _trace("low_confidence_gate", "blocked")
            truthful_outcome = nova_core._truthful_limit_outcome(text)
            reply = str(truthful_outcome.get("reply_text") or nova_core._truthful_limit_reply(text))
            return _normalize_reply(reply), {
                "planner_decision": "blocked_low_confidence",
                "tool": "",
                "tool_args": {},
                "tool_result": "",
                "grounded": False,
                "reply_contract": str(truthful_outcome.get("reply_contract") or ""),
                "reply_outcome": dict(truthful_outcome),
            }
        _trace("llm_fallback", "invoked", retrieved_chars=len(retrieved))
        reply = nova_core.ollama_chat(
            text,
            retrieved_context=retrieved,
            language_mix_spanish_pct=int(language_mix_spanish_pct or 0),
        )
        reply = nova_core.sanitize_llm_reply(reply, "")
        reply_contract = ""
        reply_outcome: dict[str, object] = {}
        claim_gated_reply, claim_gate_changed, claim_gate_reason = nova_core._apply_claim_gate(
            reply,
            evidence_text=retrieved,
            tool_context="",
        )
        if claim_gate_changed:
            _trace("claim_gate", "adjusted", claim_gate_reason)
            reply = claim_gated_reply
            if claim_gate_reason == "unsupported_claim_blocked":
                truthful_outcome = nova_core._truthful_limit_outcome(text)
                reply_contract = str(truthful_outcome.get("reply_contract") or "")
                reply_outcome = dict(truthful_outcome)
        if not reply_contract:
            reply = nova_core._attach_learning_invitation(reply)
        return _normalize_reply(reply), {
            "planner_decision": "llm_fallback",
            "tool": "",
            "tool_args": {},
            "tool_result": "",
            "grounded": False if not reply else None,
            "reply_contract": reply_contract,
            "reply_outcome": reply_outcome,
        }


def process_chat(session_id: str, user_text: str, user_id: str = "") -> str:
    previous_user = nova_core.get_active_user()
    nova_core.set_active_user(user_id or previous_user)
    try:
        text = nova_core._strip_invocation_prefix((user_text or "").strip())
        if not text:
            _invalidate_control_status_cache()
            return "Okay."

        session = SESSION_STATE_MANAGER.get(session_id)
        session.reset_turn_flags()
        conversation_state = session.conversation_state

        ledger = nova_core.start_action_ledger_record(
            text,
            channel="http",
            session_id=session_id,
            input_source="typed",
            active_subject=session.active_subject(),
        )
        routing_decision: dict | None = None

        def _finalize_http_reply(
            reply_text: str,
            *,
            planner_decision: str = "deterministic",
            tool: str = "",
            tool_args: dict | None = None,
            tool_result: str = "",
            grounded: bool | None = None,
            intent: str = "",
            reply_contract: str = "",
            reply_outcome: dict | None = None,
        ) -> str:
            reflection_payload = nova_core.build_turn_reflection(
                session,
                entry_point="http",
                session_id=session_id,
                current_decision={
                    "user_input": text,
                    "planner_decision": planner_decision,
                    "tool": tool,
                    "tool_args": tool_args if isinstance(tool_args, dict) else {},
                    "tool_result": tool_result,
                    "final_answer": reply_text,
                    "reply_contract": str(reply_contract or ""),
                    "reply_outcome": reply_outcome if isinstance(reply_outcome, dict) else {},
                    "turn_acts": list(ledger.get("turn_acts") or []),
                    "grounded": grounded,
                    "active_subject": session.active_subject(),
                    "continuation_used": session.continuation_used_last_turn,
                    "pending_action": session.pending_action,
                    "routing_decision": nova_core._finalize_routing_decision(
                        routing_decision if isinstance(routing_decision, dict) else {},
                        planner_decision=planner_decision,
                        reply_contract=str(reply_contract or ""),
                        reply_outcome=reply_outcome if isinstance(reply_outcome, dict) else {},
                        turn_acts=list(ledger.get("turn_acts") or []),
                    ),
                    "route_summary": nova_core.action_ledger_route_summary(ledger),
                    "overrides_active": session.reflection_summary().get("overrides_active", []),
                },
            )
            nova_core.finalize_action_ledger_record(
                ledger,
                final_answer=reply_text,
                planner_decision=planner_decision,
                tool=tool,
                tool_args=tool_args if isinstance(tool_args, dict) else {},
                tool_result=tool_result,
                grounded=grounded,
                intent=intent,
                active_subject=session.active_subject(),
                continuation_used=session.continuation_used_last_turn,
                reply_contract=str(reply_contract or ""),
                reply_outcome=reply_outcome if isinstance(reply_outcome, dict) else {},
                routing_decision=routing_decision if isinstance(routing_decision, dict) else {},
                reflection_payload=reflection_payload,
            )
            return reply_text

        def _finalize_flow_reply(flow_result: dict) -> str:
            reply = str(flow_result.get("reply") or "")
            _append_session_turn(session_id, "assistant", reply)
            return _finalize_http_reply(
                reply,
                planner_decision=str(flow_result.get("planner_decision") or "deterministic"),
                tool=str(flow_result.get("tool") or ""),
                tool_args=flow_result.get("tool_args") if isinstance(flow_result.get("tool_args"), dict) else {},
                tool_result=str(flow_result.get("tool_result") or ""),
                grounded=flow_result.get("grounded") if isinstance(flow_result.get("grounded"), bool) else None,
                intent=str(flow_result.get("intent") or ""),
                reply_contract=str(flow_result.get("reply_contract") or ""),
                reply_outcome=flow_result.get("reply_outcome") if isinstance(flow_result.get("reply_outcome"), dict) else {},
            )

        prepared_turn = http_chat_flow.prepare_chat_turn(
            session_id=session_id,
            text=text,
            session=session,
            ledger=ledger,
            append_session_turn=_append_session_turn,
            determine_turn_direction=nova_core._determine_turn_direction,
            auto_adjust_language_mix=nova_core._auto_adjust_language_mix,
            action_ledger_add_step=nova_core.action_ledger_add_step,
            evaluate_supervisor_rules=lambda routed_text, **kwargs: nova_core.TURN_SUPERVISOR.evaluate_rules(routed_text, **kwargs),
            supervisor_has_route=nova_core._supervisor_result_has_route,
            runtime_set_location_intent=nova_core._runtime_set_location_intent,
            llm_classify_routing_intent=nova_core._llm_classify_routing_intent,
            is_identity_only_session=nova_core._session_identity_only_mode,
            identity_only_block_kind=nova_core._identity_only_block_kind,
        )
        turns = list(prepared_turn.get("turns") or [])
        routed_text = str(prepared_turn.get("routed_text") or text)
        turn_acts = [str(item).strip() for item in list(prepared_turn.get("turn_acts") or []) if str(item).strip()]
        intent_rule = prepared_turn.get("intent_rule") if isinstance(prepared_turn.get("intent_rule"), dict) else {}

        flow_result = http_chat_flow.apply_identity_only_mode_block(
            routed_text=routed_text,
            intent_rule=intent_rule,
            identity_only_block_kind=str(prepared_turn.get("identity_only_block_kind") or ""),
            ledger=ledger,
            build_routing_decision=nova_core._build_routing_decision,
            identity_only_block_reply=nova_core._identity_only_block_reply,
            action_ledger_add_step=nova_core.action_ledger_add_step,
        )
        if flow_result.get("handled"):
            routing_decision = flow_result.get("routing_decision") if isinstance(flow_result.get("routing_decision"), dict) else routing_decision
            return _finalize_flow_reply(flow_result)

        flow_result = http_chat_flow.apply_numeric_clarify_outcome(
            has_intent_route=bool(nova_core._supervisor_result_has_route(intent_rule)),
            routed_text=routed_text,
            pending_action=session.pending_action,
            current_state=conversation_state,
            session=session,
            ledger=ledger,
            should_clarify_unlabeled_numeric_turn=nova_core._should_clarify_unlabeled_numeric_turn,
            unlabeled_numeric_turn_reply=nova_core._unlabeled_numeric_turn_reply,
            make_conversation_state=nova_core._make_conversation_state,
            action_ledger_add_step=nova_core.action_ledger_add_step,
        )
        if flow_result.get("handled"):
            return _finalize_flow_reply(flow_result)

        correction_pending = bool(session.pending_correction_target) or (
            isinstance(conversation_state, dict)
            and str(conversation_state.get("kind") or "") == "correction_pending"
        )
        flow_result = http_chat_flow.apply_mixed_turn_clarify(
            turn_acts=turn_acts,
            correction_pending=correction_pending,
            routed_text=routed_text,
            ledger=ledger,
            mixed_info_request_clarify_reply=nova_core._mixed_info_request_clarify_reply,
            action_ledger_add_step=nova_core.action_ledger_add_step,
        )
        if flow_result.get("handled"):
            return _finalize_flow_reply(flow_result)

        routing_decision = nova_core._build_routing_decision(
            routed_text,
            entry_point="http",
            intent_result=intent_rule,
            handle_result=None,
            turn_acts=turn_acts,
        )
        # DO NOT add new deterministic routing branches in HTTP.
        # Add a supervisor rule plus shared core action execution instead.
        # See docs/SUPERVISOR_CONTRACT.md.
        handled_intent, intent_msg, intent_state, intent_effects = nova_core._handle_supervisor_intent(
            intent_rule,
            routed_text,
            turns=turns,
            input_source="typed",
            entry_point="http",
        )
        if handled_intent:
            flow_result = http_chat_flow.apply_handled_supervisor_intent(
                intent_rule=intent_rule,
                routed_text=routed_text,
                intent_msg=intent_msg,
                intent_state=intent_state,
                intent_effects=intent_effects,
                session=session,
                conversation_state=conversation_state,
                ledger=ledger,
                emit_supervisor_intent_trace=nova_core._emit_supervisor_intent_trace,
                action_ledger_add_step=nova_core.action_ledger_add_step,
                ensure_reply=nova_core._ensure_reply,
            )
            conversation_state = flow_result.get("conversation_state") if isinstance(flow_result.get("conversation_state"), dict) else session.conversation_state
            return _finalize_flow_reply(flow_result)
        warn_supervisor_bypass = not nova_core._supervisor_result_has_route(intent_rule) and nova_core._should_warn_supervisor_bypass(routed_text)

        flow_result = http_chat_flow.apply_web_research_override(
            text=text,
            session=session,
            ledger=ledger,
            is_web_research_override_request=nova_core._is_web_research_override_request,
            action_ledger_add_step=nova_core.action_ledger_add_step,
        )
        if flow_result.get("handled"):
            return _finalize_flow_reply(flow_result)

        try:
            identity_learned, identity_msg = nova_core._learn_self_identity_binding(text)
            flow_result = http_chat_flow.apply_identity_binding_learning(
                identity_learned=identity_learned,
                identity_msg=identity_msg,
                ledger=ledger,
                action_ledger_add_step=nova_core.action_ledger_add_step,
                ensure_reply=nova_core._ensure_reply,
            )
            if flow_result.get("handled"):
                return _finalize_flow_reply(flow_result)
        except Exception:
            pass

        general_rule = nova_core.TURN_SUPERVISOR.evaluate_rules(
            text,
            manager=session,
            turns=turns,
            phase="handle",
            entry_point="http",
        )
        # HTTP mirrors supervisor-selected core behavior and may not fork deterministic logic.
        # See docs/SUPERVISOR_CONTRACT.md.
        handled_rule, rule_reply, rule_state = nova_core._execute_registered_supervisor_rule(
            general_rule,
            text,
            conversation_state,
            turns=turns,
            input_source="typed",
            allowed_actions={"name_origin_store", "self_location", "location_recall", "location_name", "weather_current_location", "apply_correction", "retrieval_followup", "identity_history_family", "open_probe_family", "session_fact_recall", "last_question_recall", "rules_list", "developer_identity_followup", "identity_profile_followup", "developer_location"},
        )
        routing_decision = nova_core._build_routing_decision(
            routed_text,
            entry_point="http",
            intent_result=intent_rule,
            handle_result=general_rule,
            reply_contract=str(general_rule.get("reply_contract") or "") if isinstance(general_rule, dict) else "",
            reply_outcome=general_rule.get("reply_outcome") if isinstance(general_rule.get("reply_outcome"), dict) else {},
        )
        flow_result = http_chat_flow.apply_registered_supervisor_rule(
            handled_rule=handled_rule,
            general_rule=general_rule,
            rule_reply=rule_reply,
            rule_state=rule_state,
            session=session,
            ledger=ledger,
            action_ledger_add_step=nova_core.action_ledger_add_step,
            ensure_reply=nova_core._ensure_reply,
        )
        if flow_result.get("handled"):
            return _finalize_flow_reply(flow_result)

        fulfillment_result = nova_core._fulfillment_flow_service().maybe_run_fulfillment_flow(
            routed_text,
            session,
            turns,
            pending_action=session.pending_action,
        )
        flow_result = http_chat_flow.apply_fulfillment_flow(
            fulfillment_result=fulfillment_result,
            ledger=ledger,
            action_ledger_add_step=nova_core.action_ledger_add_step,
            ensure_reply=nova_core._ensure_reply,
        )
        if flow_result.get("handled"):
            return _finalize_flow_reply(flow_result)

        quick = _fast_smalltalk_reply(text)
        flow_result = http_chat_flow.apply_fast_smalltalk(
            quick_reply=quick,
            ledger=ledger,
            action_ledger_add_step=nova_core.action_ledger_add_step,
        )
        if flow_result.get("handled"):
            return _finalize_flow_reply(flow_result)

        learned_profile, learned_profile_msg = _learn_contextual_developer_facts(turns, text)
        flow_result = http_chat_flow.apply_developer_profile_learning(
            learned_profile=learned_profile,
            learned_profile_msg=learned_profile_msg,
            text=text,
            session=session,
            ledger=ledger,
            infer_profile_conversation_state=nova_core._infer_profile_conversation_state,
            make_conversation_state=nova_core._make_conversation_state,
            action_ledger_add_step=nova_core.action_ledger_add_step,
            ensure_reply=nova_core._ensure_reply,
        )
        if flow_result.get("handled"):
            return _finalize_flow_reply(flow_result)

        try:
            learned_self, learned_self_msg = nova_core._learn_contextual_self_facts(text, input_source="typed")
            flow_result = http_chat_flow.apply_self_profile_learning(
                learned_self=learned_self,
                learned_self_msg=learned_self_msg,
                ledger=ledger,
                action_ledger_add_step=nova_core.action_ledger_add_step,
                ensure_reply=nova_core._ensure_reply,
            )
            if flow_result.get("handled"):
                return _finalize_flow_reply(flow_result)
        except Exception:
            pass

        memory_teach = _extract_memory_teach_text(text)
        if memory_teach and nova_core.mem_enabled():
            pass

        try:
            location_ack = nova_core._store_location_fact_reply(
                text,
                input_source="typed",
                pending_action=session.pending_action,
            )
            flow_result = http_chat_flow.apply_location_store_outcome(
                location_ack=location_ack,
                conversation_state=conversation_state,
                session=session,
                ledger=ledger,
                make_conversation_state=nova_core._make_conversation_state,
                action_ledger_add_step=nova_core.action_ledger_add_step,
            )
            if flow_result.get("handled"):
                conversation_state = flow_result.get("conversation_state") if isinstance(flow_result.get("conversation_state"), dict) else session.conversation_state
                return _finalize_flow_reply(flow_result)
        except Exception:
            pass

        try:
            flow_result = http_chat_flow.apply_saved_location_weather_outcome(
                conversation_state=conversation_state,
                routed_text=routed_text,
                weather_for_saved_location=nova_core._weather_for_saved_location,
                is_saved_location_weather_query=nova_core._is_saved_location_weather_query,
                session=session,
                ledger=ledger,
                make_conversation_state=nova_core._make_conversation_state,
                action_ledger_add_step=nova_core.action_ledger_add_step,
                ensure_reply=nova_core._ensure_reply,
            )
            if flow_result.get("handled"):
                conversation_state = flow_result.get("conversation_state") if isinstance(flow_result.get("conversation_state"), dict) else session.conversation_state
                return _finalize_flow_reply(flow_result)
        except Exception:
            pass

        declarative_outcome = nova_core._store_declarative_fact_outcome(text, input_source="typed")
        flow_result = http_chat_flow.apply_declarative_store_outcome(
            declarative_outcome=declarative_outcome,
            ledger=ledger,
            action_ledger_add_step=nova_core.action_ledger_add_step,
            render_reply=nova_core.render_reply,
        )
        if flow_result.get("handled"):
            return _finalize_flow_reply(flow_result)

        try:
            handled_followup, followup_msg, next_state = nova_core._consume_conversation_followup(
                conversation_state,
                routed_text,
                input_source="typed",
                turns=turns,
            )
            flow_result = http_chat_flow.apply_conversation_followup_outcome(
                handled_followup=handled_followup,
                followup_msg=followup_msg,
                next_state=next_state,
                conversation_state=conversation_state,
                session=session,
                ledger=ledger,
                conversation_active_subject=nova_core._conversation_active_subject,
                action_ledger_add_step=nova_core.action_ledger_add_step,
                ensure_reply=nova_core._ensure_reply,
            )
            if flow_result.get("handled"):
                conversation_state = flow_result.get("conversation_state") if isinstance(flow_result.get("conversation_state"), dict) else session.conversation_state
                return _finalize_flow_reply(flow_result)
            conversation_state = flow_result.get("conversation_state") if isinstance(flow_result.get("conversation_state"), dict) else conversation_state
        except Exception:
            pass

        try:
            developer_guess, next_state = nova_core._developer_work_guess_turn(routed_text)
            flow_result = http_chat_flow.apply_developer_guess_outcome(
                developer_guess=developer_guess,
                next_state=next_state,
                session=session,
                ledger=ledger,
                action_ledger_add_step=nova_core.action_ledger_add_step,
                ensure_reply=nova_core._ensure_reply,
            )
            if flow_result.get("handled"):
                conversation_state = flow_result.get("conversation_state") if isinstance(flow_result.get("conversation_state"), dict) else session.conversation_state
                return _finalize_flow_reply(flow_result)
        except Exception:
            pass

        reply, next_state = nova_core._developer_location_turn(
            routed_text,
            state=conversation_state,
            turns=turns,
        )
        flow_result = http_chat_flow.apply_developer_location_outcome(
            reply_text=reply,
            next_state=next_state,
            session=session,
            ledger=ledger,
            action_ledger_add_step=nova_core.action_ledger_add_step,
        )
        if flow_result.get("handled"):
            conversation_state = flow_result.get("conversation_state") if isinstance(flow_result.get("conversation_state"), dict) else session.conversation_state
            return _finalize_flow_reply(flow_result)

        try:
            handled_location, location_reply, next_location_state, location_intent = nova_core._handle_location_conversation_turn(
                conversation_state,
                routed_text,
                turns=turns,
            )
            flow_result = http_chat_flow.apply_location_conversation_outcome(
                handled_location=handled_location,
                location_reply=location_reply,
                next_location_state=next_location_state,
                location_intent=location_intent,
                conversation_state=conversation_state,
                session=session,
                ensure_reply=nova_core._ensure_reply,
            )
            if flow_result.get("handled"):
                conversation_state = flow_result.get("conversation_state") if isinstance(flow_result.get("conversation_state"), dict) else session.conversation_state
                return _finalize_flow_reply(flow_result)
        except Exception:
            pass

        reply, meta = _generate_chat_reply(
            turns,
            routed_text,
            ledger_record=ledger,
            pending_action=session.pending_action,
            prefer_web_for_data_queries=session.prefer_web_for_data_queries,
            language_mix_spanish_pct=int(session.language_mix_spanish_pct or 0),
            session=session,
        )
        reply_contract = str(meta.get("reply_contract") or "") if isinstance(meta, dict) else ""
        planner_decision = str(meta.get("planner_decision") or "deterministic")
        flow_result = http_chat_flow.apply_supervisor_bypass_safe_fallback(
            warn_supervisor_bypass=warn_supervisor_bypass,
            reply_contract=reply_contract,
            routed_text=routed_text,
            turns=turns,
            routing_decision=routing_decision,
            ledger=ledger,
            open_probe_reply=nova_core._open_probe_reply,
            action_ledger_add_step=nova_core.action_ledger_add_step,
        )
        if flow_result.get("handled"):
            reply = str(flow_result.get("reply") or reply)
            reply_contract = str(flow_result.get("reply_contract") or reply_contract)
            planner_decision = str(flow_result.get("planner_decision") or planner_decision)
            meta = flow_result.get("meta") if isinstance(flow_result.get("meta"), dict) else meta
            routing_decision = flow_result.get("routing_decision") if isinstance(flow_result.get("routing_decision"), dict) else routing_decision
        tool = str(meta.get("tool") or "")
        tool_args = meta.get("tool_args") if isinstance(meta.get("tool_args"), dict) else {}
        tool_result = str(meta.get("tool_result") or "")
        grounded = meta.get("grounded") if isinstance(meta.get("grounded"), bool) else None
        pending_next = meta.get("pending_action")
        session.set_pending_action(pending_next if isinstance(pending_next, dict) and pending_next else None)

        if planner_decision in {"command", "run_tool", "grounded_lookup"}:
            nova_core.behavior_record_event("tool_route")
        elif planner_decision == "llm_fallback":
            nova_core.behavior_record_event("llm_fallback")

        next_state = nova_core._infer_post_reply_conversation_state(
            routed_text,
            planner_decision=planner_decision,
            tool=tool,
            tool_args=tool_args,
            tool_result=tool_result,
            turns=turns,
            fallback_state=conversation_state,
        )
        if isinstance(next_state, dict) and str(next_state.get("kind") or "").strip() == "retrieval":
            session.set_retrieval_state(next_state)
        else:
            session.apply_state_update(next_state)

        _append_session_turn(session_id, "assistant", reply)
        reply_text = _finalize_http_reply(
            reply,
            planner_decision=planner_decision,
            tool=tool,
            tool_args=tool_args,
            tool_result=tool_result,
            grounded=grounded,
            reply_contract=reply_contract,
            reply_outcome=meta.get("reply_outcome") if isinstance(meta, dict) and isinstance(meta.get("reply_outcome"), dict) else {},
        )
        _invalidate_control_status_cache()
        return reply_text
    finally:
        nova_core.set_active_user(previous_user)


def resume_last_pending_turn(session_id: str, user_id: str = "") -> dict:
    return http_chat_flow.resume_last_pending_turn(
        session_id,
        user_id,
        get_active_user=nova_core.get_active_user,
        set_active_user=nova_core.set_active_user,
        get_last_session_turn=_get_last_session_turn,
        get_session_turns=_get_session_turns,
        generate_chat_reply=_generate_chat_reply,
        append_session_turn=_append_session_turn,
        invalidate_control_status_cache=_invalidate_control_status_cache,
    )


def _control_work_trees_payload() -> dict:
    trees: list[dict] = []
    tree_map = getattr(work_tree, "_TREES", {})
    tree_ids = sorted(str(tree_id).strip() for tree_id in tree_map.keys() if str(tree_id).strip()) if isinstance(tree_map, dict) else []
    for tree_id in tree_ids:
        visual = work_tree.get_visual_tree_data(tree_id)
        if not isinstance(visual, dict):
            continue
        nodes_in = visual.get("nodes") if isinstance(visual.get("nodes"), list) else []
        nodes: list[dict] = []
        for node in nodes_in:
            if not isinstance(node, dict):
                continue
            preferred_tool = node.get("preferred_tool")
            normalized_preferred_tool = str(preferred_tool).strip() if preferred_tool is not None and str(preferred_tool).strip() else None
            nodes.append(
                {
                    "id": str(node.get("id") or ""),
                    "title": str(node.get("title") or ""),
                    "status": str(node.get("status") or ""),
                    "parent_id": str(node.get("parent_id")) if node.get("parent_id") is not None else None,
                    "depth": int(node.get("depth") or 0),
                    "tasks_open": int(node.get("tasks_open") or 0),
                    "tasks_total": int(node.get("tasks_total") or 0),
                    "preferred_tool": normalized_preferred_tool,
                    "required_tools": [str(item) for item in list(node.get("required_tools") or []) if str(item).strip()],
                    "allowed_tools": [str(item) for item in list(node.get("allowed_tools") or []) if str(item).strip()],
                    "blocked_by": [str(item) for item in list(node.get("blocked_by") or []) if str(item).strip()],
                    "depends_on": [str(item) for item in list(node.get("depends_on") or []) if str(item).strip()],
                }
            )

        edges_in = visual.get("dependency_edges") if isinstance(visual.get("dependency_edges"), list) else []
        dependency_edges: list[dict] = []
        for edge in edges_in:
            if not isinstance(edge, dict):
                continue
            dependency_edges.append(
                {
                    "from": str(edge.get("from") or ""),
                    "to": str(edge.get("to") or ""),
                }
            )

        trees.append(
            {
                "tree_id": str(visual.get("tree_id") or tree_id),
                "title": str(visual.get("title") or ""),
                "status": str(visual.get("status") or ""),
                "root_branch_id": str(visual.get("root_branch_id") or ""),
                "updated_at": str(visual.get("updated_at") or ""),
                "nodes": nodes,
                "dependency_edges": dependency_edges,
            }
        )
    return {"ok": True, "trees": trees}


class NovaHttpHandler(BaseHTTPRequestHandler):
    server_version = "NovaHTTP/0.1"

    def do_GET(self) -> None:
        path, qs = _parse_request_path(self.path)

        if path == "/":
            _text_response(self, 200, INDEX_HTML)
            return

        if path == "/static/control.css":
            _file_response(self, 200, CONTROL_CSS_PATH, "text/css; charset=utf-8")
            return

        if path == "/static/control.js":
            _file_response(self, 200, CONTROL_JS_PATH, "application/javascript; charset=utf-8")
            return

        if path == "/control/login":
            if not _control_login_enabled():
                _json_response(self, 404, {"ok": False, "error": "control_login_disabled"})
                return
            ok_page, reason_page = _control_page_gate(self)
            if not ok_page and reason_page != "control_login_required":
                _json_response(self, 403, {"ok": False, "error": reason_page})
                return
            _text_response(self, 200, CONTROL_LOGIN_HTML)
            return

        if path == "/control":
            ok_page, reason_page = _control_page_gate(self)
            if not ok_page:
                if reason_page == "control_login_required":
                    _text_response(self, 200, CONTROL_LOGIN_HTML)
                else:
                    _json_response(self, 403, {"ok": False, "error": reason_page})
                return
            _text_response(self, 200, CONTROL_HTML)
            return

        if path == "/api/health":
            payload = {
                "ok": True,
                "ollama_api_up": bool(nova_core.ollama_api_up()),
                "chat_model": nova_core.chat_model(),
                "memory_enabled": bool(nova_core.mem_enabled()),
                "chat_login_enabled": bool(_chat_login_enabled()),
            }
            _json_response(self, 200, payload)
            return

        if path == "/api/chat/history":
            ok_chat, chat_user = _chat_login_auth(self)
            if not ok_chat:
                _json_response(self, 403, {"ok": False, "error": chat_user})
                return
            sid = str((qs.get("session_id") or [""])[0]).strip()
            user_id = _normalize_user_id(chat_user) or _request_user_id(self, qs)
            ok_owner, reason_owner = _assert_session_owner(sid, user_id, allow_bind=False)
            if not ok_owner:
                _json_response(self, 403, {"ok": False, "error": reason_owner, "session_id": sid})
                return
            turns = _get_session_turns(sid)
            _json_response(
                self,
                200,
                {
                    "ok": True,
                    "session_id": sid,
                    "turns": [{"role": r, "text": t} for r, t in turns[-MAX_STORED_TURNS_PER_SESSION:]],
                },
            )
            return

        if path == "/api/control/status":
            ok, reason = _control_auth(self, qs)
            if not ok:
                _json_response(self, 403, {"ok": False, "error": reason})
                return
            _json_response(self, 200, _cached_control_status_payload())
            return

        if path == "/api/control/policy":
            ok, reason = _control_auth(self, qs)
            if not ok:
                _json_response(self, 403, {"ok": False, "error": reason})
                return
            _json_response(self, 200, _control_policy_payload())
            return

        if path == "/api/control/metrics":
            ok, reason = _control_auth(self, qs)
            if not ok:
                _json_response(self, 403, {"ok": False, "error": reason})
                return
            _json_response(self, 200, _metrics_payload())
            return

        if path == "/api/control/sessions":
            ok, reason = _control_auth(self, qs)
            if not ok:
                _json_response(self, 403, {"ok": False, "error": reason})
                return
            _json_response(self, 200, {"ok": True, "sessions": _session_summaries(80)})
            return

        if path == "/api/control/test-sessions":
            ok, reason = _control_auth(self, qs)
            if not ok:
                _json_response(self, 403, {"ok": False, "error": reason})
                return
            _json_response(self, 200, {"ok": True, "reports": _test_session_report_summaries(24), "definitions": _available_test_session_definitions(80)})
            return

        if path == "/api/control/work-trees":
            ok, reason = _control_auth(self, qs)
            if not ok:
                _json_response(self, 403, {"ok": False, "error": reason})
                return
            _json_response(self, 200, _control_work_trees_payload())
            return

        _json_response(self, 404, {"ok": False, "error": "not_found"})

    def do_POST(self) -> None:
        path, qs = _parse_request_path(self.path)

        if path not in {"/api/chat", "/api/chat/resume", "/api/chat/login", "/api/chat/logout", "/api/control/action", "/api/control/login", "/api/control/logout"}:
            _json_response(self, 404, {"ok": False, "error": "not_found"})
            return

        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length) if length > 0 else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            _json_response(self, 400, {"ok": False, "error": "invalid_json"})
            return

        if path == "/api/control/login":
            code, response_payload, response_headers = _control_login_action(payload)
            _json_response_with_headers(self, code, response_payload, response_headers)
            return

        if path == "/api/control/logout":
            code, response_payload, response_headers = _control_logout_action(self)
            _json_response_with_headers(self, code, response_payload, response_headers)
            return

        if path == "/api/chat/login":
            code, response_payload, response_headers = _chat_login_action(payload)
            _json_response_with_headers(self, code, response_payload, response_headers)
            return

        if path == "/api/chat/logout":
            code, response_payload, response_headers = _chat_logout_action(self)
            _json_response_with_headers(self, code, response_payload, response_headers)
            return

        if path == "/api/control/action":
            ok, reason = _control_auth(self, qs)
            if not ok:
                _json_response(self, 403, {"ok": False, "error": reason})
                return

            success, msg, extra = _control_action(str(payload.get("action") or ""), payload)
            code = 200 if success else 400
            body = {"ok": bool(success), "message": msg}
            if extra:
                body.update(extra)
            _json_response(self, code, body)
            return

        if path == "/api/chat/resume":
            ok_chat, chat_user = _chat_login_auth(self)
            if not ok_chat:
                _json_response(self, 403, {"ok": False, "error": chat_user})
                return
            sid = str(payload.get("session_id") or "").strip()
            user_id = _normalize_user_id(chat_user) or _request_user_id(self, qs, payload)
            ok_owner, reason_owner = _assert_session_owner(sid, user_id, allow_bind=False)
            if not ok_owner:
                _json_response(self, 403, {"ok": False, "error": reason_owner, "session_id": sid})
                return
            out = resume_last_pending_turn(sid, user_id=user_id)
            code = 200 if out.get("ok") else 400
            if out.get("ok") and out.get("resumed"):
                _invalidate_control_status_cache()
            _json_response(self, code, out)
            return

        ok_chat, chat_user = _chat_login_auth(self)
        if not ok_chat:
            _json_response(self, 403, {"ok": False, "error": chat_user})
            return

        message = str(payload.get("message") or "").strip()
        session_id = str(payload.get("session_id") or "").strip()
        user_id = _normalize_user_id(chat_user) or _request_user_id(self, qs, payload)
        if not session_id:
            session_id = secrets.token_hex(8)

        if not message:
            _json_response(self, 400, {"ok": False, "error": "message_required", "session_id": session_id})
            return

        ok_owner, reason_owner = _assert_session_owner(session_id, user_id, allow_bind=True)
        if not ok_owner:
            _json_response(self, 403, {"ok": False, "error": reason_owner, "session_id": session_id})
            return

        try:
            reply = process_chat(session_id, message, user_id=user_id)
            _invalidate_control_status_cache()
            _json_response(self, 200, {"ok": True, "session_id": session_id, "reply": reply})
        except Exception as e:
            _json_response(self, 500, {"ok": False, "session_id": session_id, "error": f"chat_failed: {e}"})

    def log_message(self, fmt: str, *args) -> None:
        return


INDEX_HTML = """<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <title>NYO Runtime Console</title>
  <style>
    :root {
      --bg: #f7f4ec;
      --panel: #fffdf8;
      --ink: #1f1d19;
      --muted: #70695f;
      --accent: #0d6b5f;
      --accent-2: #d9972d;
      --line: #e4dbc8;
    }
    body { margin: 0; font-family: "Segoe UI", Tahoma, sans-serif; color: var(--ink); background: radial-gradient(circle at top left, #fff8e7, var(--bg)); }
    .wrap { max-width: 900px; margin: 24px auto; padding: 0 16px; }
    .card { background: var(--panel); border: 1px solid var(--line); border-radius: 14px; box-shadow: 0 8px 30px rgba(0,0,0,0.06); overflow: hidden; }
    .head { padding: 14px 16px; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--line); }
    .title { font-weight: 700; letter-spacing: 0.02em; }
    .status { font-size: 12px; color: var(--muted); }
    .head-right { display: flex; align-items: center; gap: 10px; }
    .btn-mini { padding: 6px 10px; font-size: 12px; }
    .btn-mini.alt { background: linear-gradient(135deg, #846540, #a47d4f); }
    .btn-mini.muted { background: linear-gradient(135deg, #8d8a84, #6d6a65); }
    #chat { height: 58vh; overflow: auto; padding: 14px; display: grid; gap: 10px; }
    .msg { padding: 10px 12px; border-radius: 10px; max-width: 85%; white-space: pre-wrap; line-height: 1.35; }
    .u { margin-left: auto; background: #d7efe9; border: 1px solid #a9d9ce; }
    .a { margin-right: auto; background: #fff4db; border: 1px solid #f0d59f; }
    form { display: grid; grid-template-columns: 1fr auto; gap: 10px; padding: 12px; border-top: 1px solid var(--line); }
    input { font-size: 15px; padding: 10px 12px; border-radius: 9px; border: 1px solid #cabfae; outline: none; }
    button { background: linear-gradient(135deg, var(--accent), #0f8f7d); color: #fff; border: 0; border-radius: 9px; padding: 10px 14px; cursor: pointer; font-weight: 600; }
    .hint { padding: 0 14px 14px; color: var(--muted); font-size: 12px; }
  </style>
</head>
<body>
  <div class=\"wrap\">
    <div class=\"card\">
            <div class=\"head\">
                <div class=\"title\">NYO Runtime Console</div>
                <div class=\"head-right\">
                    <div id=\"status\" class=\"status\">Checking health...</div>
                    <button id="btnToggleAudio" type="button" class="btn-mini alt">Voice Off</button>
                    <button id="btnMic" type="button" class="btn-mini muted">Mic Unavailable</button>
                    <button id=\"btnNewSession\" type=\"button\" class=\"btn-mini\">New Session</button>
                </div>
            </div>
      <div id=\"chat\"></div>
      <form id=\"f\">
        <input id=\"m\" placeholder=\"Enter a request for the NYO runtime...\" autocomplete=\"off\" />
        <button type=\"submit\">Send</button>
      </form>
            <div class=\"hint\">Tip: start server with <code>--host 0.0.0.0</code> to test from another device on your LAN. <a href=\"/control\">Open Operator Console</a>.</div>
    </div>
  </div>
<script>
  const chat = document.getElementById('chat');
  const form = document.getElementById('f');
  const input = document.getElementById('m');
    const statusEl = document.getElementById('status');
        const btnToggleAudio = document.getElementById('btnToggleAudio');
        const btnMic = document.getElementById('btnMic');
    const btnNewSession = document.getElementById('btnNewSession');
    const qs = new URLSearchParams(window.location.search || '');
        const SpeechRecognitionCtor = window.SpeechRecognition || window.webkitSpeechRecognition || null;
    const sidParam = (qs.get('sid') || '').trim();
    const uidParam = (qs.get('uid') || '').trim();
    const makeUserId = () => {
        if (window.crypto && typeof window.crypto.randomUUID === 'function') {
            return 'web-' + window.crypto.randomUUID().replace(/-/g, '').slice(0, 24);
        }
        return 'web-' + Math.random().toString(16).slice(2) + Date.now().toString(16);
    };
    let userId = uidParam || localStorage.getItem('nova_user_id') || makeUserId();
    localStorage.setItem('nova_user_id', userId);
    let chatLoginEnabled = false;
    let sessionId = sidParam || localStorage.getItem('nova_session_id') || '';
    let voiceOutputEnabled = localStorage.getItem('nova_voice_output') === 'on';
    let recognition = null;
    let recognitionActive = false;
    if (sidParam) {
        localStorage.setItem('nova_session_id', sessionId);
    }
        let historyLoaded = false;
        let pendingResumeNeeded = false;

    function syncAudioButton() {
        if (!btnToggleAudio) return;
        btnToggleAudio.textContent = voiceOutputEnabled ? 'Voice On' : 'Voice Off';
        btnToggleAudio.classList.toggle('alt', voiceOutputEnabled);
        btnToggleAudio.classList.toggle('muted', !voiceOutputEnabled);
    }

    function syncMicButton() {
        if (!btnMic) return;
        if (!SpeechRecognitionCtor) {
            btnMic.textContent = 'Mic Unavailable';
            btnMic.disabled = true;
            return;
        }
        btnMic.disabled = false;
        btnMic.textContent = recognitionActive ? 'Listening...' : 'Mic Ready';
        btnMic.classList.toggle('alt', recognitionActive);
        btnMic.classList.toggle('muted', !recognitionActive);
    }

    function speakAssistant(text) {
        if (!voiceOutputEnabled || !window.speechSynthesis) return;
        const spoken = String(text || '').trim();
        if (!spoken) return;
        try {
            window.speechSynthesis.cancel();
            const utterance = new SpeechSynthesisUtterance(spoken);
            utterance.rate = 1.0;
            utterance.pitch = 1.0;
            window.speechSynthesis.speak(utterance);
        } catch (_) {
            // Keep chat usable if browser speech APIs fail.
        }
    }

  function add(kind, text) {
    const d = document.createElement('div');
    d.className = 'msg ' + kind;
    d.textContent = text;
    chat.appendChild(d);
    chat.scrollTop = chat.scrollHeight;
    if (kind === 'a') {
        speakAssistant(text);
    }
  }

    async function sendMessage(message) {
        if (!message) return;
        add('u', message);
        try {
            const r = await chatFetch('/api/chat', {
                method: 'POST',
                headers: {'Content-Type': 'application/json', 'X-Nova-User-Id': userId},
                body: JSON.stringify({message, session_id: sessionId, user_id: userId})
            });
            const j = await r.json();
            if (j.session_id) {
                sessionId = j.session_id;
                localStorage.setItem('nova_session_id', sessionId);
            }
            add('a', j.reply || (j.error ? `Error: ${j.error}` : 'No reply'));
        } catch (err) {
            add('a', 'Network error: ' + err.message);
        }
    }

    function initSpeechRecognition() {
        if (!SpeechRecognitionCtor || recognition) return;
        recognition = new SpeechRecognitionCtor();
        recognition.lang = 'en-US';
        recognition.interimResults = false;
        recognition.maxAlternatives = 1;
        recognition.onstart = () => {
            recognitionActive = true;
            syncMicButton();
        };
        recognition.onend = () => {
            recognitionActive = false;
            syncMicButton();
        };
        recognition.onerror = () => {
            recognitionActive = false;
            syncMicButton();
        };
        recognition.onresult = (event) => {
            const transcript = String(event.results?.[0]?.[0]?.transcript || '').trim();
            if (!transcript) return;
            input.value = transcript;
            if (typeof form.requestSubmit === 'function') {
                form.requestSubmit();
            } else {
                form.dispatchEvent(new Event('submit', {cancelable: true}));
            }
        };
    }

    async function ensureChatLogin(forcePrompt = false) {
        if (!chatLoginEnabled && !forcePrompt) return true;
        let username = (localStorage.getItem('nova_chat_user') || userId || '').trim();
        if (!username || forcePrompt) {
            username = (window.prompt('NYO username', username || userId || '') || '').trim();
        }
        if (!username) return false;
        const password = window.prompt('NYO password', '');
        if (password === null) return false;
        try {
            const r = await fetch('/api/chat/login', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({username, password})
            });
            const j = await r.json();
            if (!r.ok || !j.ok) throw new Error(j.error || 'login_failed');
            userId = String(j.user_id || username).trim() || username;
            localStorage.setItem('nova_chat_user', userId);
            localStorage.setItem('nova_user_id', userId);
            return true;
        } catch (err) {
            add('a', 'Login failed: ' + err.message);
            return false;
        }
    }

    async function chatFetch(url, options = {}) {
        const headers = Object.assign({}, options.headers || {});
        if (userId) headers['X-Nova-User-Id'] = userId;
        let response = await fetch(url, Object.assign({}, options, {headers}));
        if (response.status !== 403) return response;

        let payload = null;
        try {
            payload = await response.clone().json();
        } catch (_) {
            return response;
        }
        if (!payload || payload.error !== 'chat_login_required') return response;

        const ok = await ensureChatLogin(true);
        if (!ok) return response;

        const retryHeaders = Object.assign({}, options.headers || {});
        if (userId) retryHeaders['X-Nova-User-Id'] = userId;
        return fetch(url, Object.assign({}, options, {headers: retryHeaders}));
    }

    async function loadHistory() {
        if (!sessionId) return;
        try {
            const r = await chatFetch('/api/chat/history?session_id=' + encodeURIComponent(sessionId) + '&user_id=' + encodeURIComponent(userId));
            const j = await r.json();
            if (!r.ok || !j.ok || !Array.isArray(j.turns)) return;
            if (j.turns.length === 0) return;

            j.turns.forEach(t => {
                if (!t || !t.role || !t.text) return;
                add(t.role === 'user' ? 'u' : 'a', String(t.text));
            });
                        const last = j.turns[j.turns.length - 1];
                        pendingResumeNeeded = Boolean(last && String(last.role || '').toLowerCase() === 'user');
            historyLoaded = true;
        } catch (_) {
            // Keep startup resilient; chat can still operate without history.
        }
    }

    async function resumePendingTurn() {
        if (!sessionId || !pendingResumeNeeded) return;
        try {
            const r = await chatFetch('/api/chat/resume', {
                method: 'POST',
                headers: {'Content-Type': 'application/json', 'X-Nova-User-Id': userId},
                body: JSON.stringify({session_id: sessionId, user_id: userId})
            });
            const j = await r.json();
            if (r.ok && j.ok && j.resumed && j.reply) {
                add('a', String(j.reply));
            }
        } catch (_) {
            // Keep UI responsive even if resume fails.
        } finally {
            pendingResumeNeeded = false;
        }
    }

  async function health() {
    try {
      const r = await fetch('/api/health');
      const j = await r.json();
            chatLoginEnabled = Boolean(j.chat_login_enabled);
      statusEl.textContent = j.ollama_api_up ? `Healthy | model: ${j.chat_model}` : 'Ollama unavailable';
    } catch (_) {
      statusEl.textContent = 'Health check failed';
    }
  }

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const message = input.value.trim();
    if (!message) return;
    input.value = '';
    await sendMessage(message);
  });

    if (btnToggleAudio) {
        syncAudioButton();
        btnToggleAudio.addEventListener('click', () => {
            voiceOutputEnabled = !voiceOutputEnabled;
            localStorage.setItem('nova_voice_output', voiceOutputEnabled ? 'on' : 'off');
            if (!voiceOutputEnabled && window.speechSynthesis) {
                window.speechSynthesis.cancel();
            }
            syncAudioButton();
            add('a', voiceOutputEnabled ? 'Browser voice output enabled.' : 'Browser voice output disabled.');
        });
    }

    initSpeechRecognition();
    syncMicButton();
    if (btnMic && SpeechRecognitionCtor) {
        btnMic.addEventListener('click', () => {
            if (!recognition) {
                initSpeechRecognition();
            }
            if (!recognition) return;
            if (recognitionActive) {
                recognition.stop();
                return;
            }
            try {
                recognition.start();
            } catch (_) {
                recognitionActive = false;
                syncMicButton();
            }
        });
    }

    if (btnNewSession) {
        btnNewSession.addEventListener('click', () => {
            sessionId = '';
            pendingResumeNeeded = false;
            historyLoaded = false;
            localStorage.removeItem('nova_session_id');
            chat.innerHTML = '';
            add('a', 'Started a new runtime session. Context was reset.');
            input.focus();
        });
    }

    (async () => {
        await loadHistory();
        await resumePendingTurn();
        if (!historyLoaded) {
            add('a', 'NYO runtime console ready. Enter a request when you are ready.');
        }
        health();
    })();
</script>
</body>
</html>
"""


CONTROL_LOGIN_HTML = """<!doctype html>
<html lang=\"en\">
<head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <title>NYO System Control Login</title>
    <link href=\"https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css\" rel=\"stylesheet\" integrity=\"sha384-QWTKZyjpPEjISv5WaRU9OFeRpok6YctnYmDr5pNlyT2bRjXh0JMhjY6hW+ALEwIH\" crossorigin=\"anonymous\">
    <style>
        :root { --ink:#1f1d19; --bg:#f3efe6; --panel:#fffdf8; --line:#d9ceba; --accent:#0f7a5c; --danger:#a82720; }
        body {
            margin: 0;
            min-height: 100vh;
            display: grid;
            place-items: center;
            font-family: "Space Grotesk", "Segoe UI", sans-serif;
            color: var(--ink);
            background: radial-gradient(1000px 400px at 10% -20%, #d9ead7, transparent 60%), linear-gradient(160deg, #edf4ec, var(--bg));
        }
        .login-card {
            width: min(480px, 92vw);
            border: 1px solid var(--line);
            border-radius: 14px;
            background: var(--panel);
            box-shadow: 0 14px 30px rgba(0,0,0,0.08);
        }
        h1 { margin: 0 0 8px; font-size: 20px; }
        p { margin: 0 0 12px; color: #5f5a52; }
        .err { color: var(--danger); font-size: 13px; min-height: 18px; margin-top: 10px; }
        .btn-nova {
            color: #fff;
            font-weight: 700;
            border: 0;
            background: linear-gradient(135deg, var(--accent), #0a986f);
        }
    </style>
</head>
<body>
    <div class=\"login-card p-4\">
        <h1>NYO System Control Login</h1>
        <p>Sign in to access the branded operator console for the NYO runtime.</p>
        <form id=\"f\" class=\"d-grid gap-2\">
            <label for=\"u\" class=\"form-label mb-0\">Username</label>
            <input id=\"u\" class=\"form-control\" autocomplete=\"username\" />
            <label for=\"p\" class=\"form-label mb-0 mt-2\">Password</label>
            <input id=\"p\" class=\"form-control\" type=\"password\" autocomplete=\"current-password\" />
            <button type=\"submit\" class=\"btn btn-nova mt-3\">Sign In</button>
            <div class=\"err\" id=\"err\"></div>
        </form>
    </div>
    <script>
        const f = document.getElementById('f');
        const err = document.getElementById('err');
        f.addEventListener('submit', async (e) => {
            e.preventDefault();
            err.textContent = '';
            try {
                const r = await fetch('/api/control/login', {
                    method: 'POST',
                    headers: {'Content-Type':'application/json'},
                    body: JSON.stringify({
                        username: document.getElementById('u').value.trim(),
                        password: document.getElementById('p').value
                    })
                });
                const j = await r.json();
                if (!r.ok || !j.ok) throw new Error(j.error || 'login_failed');
                window.location.href = '/control';
            } catch (e) {
                err.textContent = 'Login failed: ' + e.message;
            }
        });
    </script>
</body>
</html>
"""


_LEGACY_CONTROL_HTML = """<!doctype html>
<html lang=\"en\">
<head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <title>NYO Operator Console</title>
    <link href=\"https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css\" rel=\"stylesheet\" integrity=\"sha384-QWTKZyjpPEjISv5WaRU9OFeRpok6YctnYmDr5pNlyT2bRjXh0JMhjY6hW+ALEwIH\" crossorigin=\"anonymous\">
    <style>
        :root {
            --bg0: #e8efe8;
            --bg1: #f4efe5;
            --panel: #fffcf4;
            --ink: #1a1e1b;
            --muted: #59615b;
            --accent: #0a7a4a;
            --accent2: #c76c1d;
            --danger: #b3261e;
            --line: #d7d5cb;
            --good: #0b7a5f;
            --warn: #b87515;
        }
        * { box-sizing: border-box; }
        body {
            margin: 0;
            color: var(--ink);
            font-family: "Space Grotesk", "Segoe UI", Tahoma, sans-serif;
            background:
                radial-gradient(900px 400px at 8% -10%, #d8ead8, transparent 60%),
                radial-gradient(1100px 500px at 92% -20%, #ffe7cf, transparent 55%),
                linear-gradient(160deg, var(--bg0), var(--bg1));
            min-height: 100vh;
        }
        .wrap { max-width: 1240px; margin: 0 auto; padding: 20px 14px 30px; }
        .bar {
            display: flex; gap: 10px; align-items: center; justify-content: space-between;
            margin-bottom: 12px;
            background: rgba(255,255,255,0.65);
            border: 1px solid var(--line);
            padding: 10px 12px;
            border-radius: 14px;
            backdrop-filter: blur(6px);
        }
        .tabs-wrap {
            background: rgba(255,255,255,0.58);
            border: 1px solid var(--line);
            border-radius: 12px;
            padding: 8px 10px 0;
            margin-bottom: 12px;
        }
        .nav-tabs .nav-link {
            color: #2d3a33;
            font-weight: 600;
            cursor: pointer;
            pointer-events: auto;
        }
        .nav-tabs .nav-link.active {
            color: #0a7a4a;
            border-color: var(--line) var(--line) #fff;
            background: #fff;
        }
        .health-badge {
            border-radius: 999px;
            padding: 4px 10px;
            font-size: 12px;
            font-weight: 700;
            border: 1px solid var(--line);
            background: #f6f5ef;
            color: #3f3a34;
        }
        .feedback-strip {
            border: 1px solid var(--line);
            border-radius: 10px;
            padding: 8px 10px;
            margin: 0 0 12px;
            font-size: 13px;
            background: rgba(255,255,255,0.75);
        }
        .feedback-strip.good { color: var(--good); }
        .feedback-strip.warn { color: var(--warn); }
        .feedback-strip.danger { color: var(--danger); }
        body.js-ready .pane-hidden { display: none !important; }
        .title { font-weight: 700; letter-spacing: 0.02em; font-size: 18px; }
        .grid {
            display: grid;
            grid-template-columns: 1.2fr 1fr;
            gap: 12px;
        }
        .card {
            border: 1px solid var(--line);
            border-radius: 14px;
            background: var(--panel);
            box-shadow: 0 8px 24px rgba(0,0,0,0.07);
            overflow: hidden;
        }
        .head { display: flex; align-items: center; justify-content: space-between; padding: 10px 12px; border-bottom: 1px solid var(--line); font-weight: 600; }
        .body { padding: 12px; }
        .mono { font-family: "IBM Plex Mono", Consolas, monospace; }
        .kv { display: grid; grid-template-columns: 170px 1fr; gap: 6px 10px; font-size: 14px; }
        .muted { color: var(--muted); }
        .good { color: var(--good); font-weight: 600; }
        .warn { color: var(--warn); font-weight: 600; }
        .danger { color: var(--danger); font-weight: 600; }
        .row { display: flex; gap: 8px; flex-wrap: wrap; }
        .btn-nova { color: #fff; border: 0; font-weight: 600; background: linear-gradient(135deg, var(--accent), #0f9f61); }
        .btn-alt { color: #fff; border: 0; font-weight: 600; background: linear-gradient(135deg, #6f4f3e, #9d6a4f); }
        .btn-warn { color: #fff; border: 0; font-weight: 600; background: linear-gradient(135deg, #9a5316, #cf7e24); }
        .btn-danger-nova { color: #fff; border: 0; font-weight: 600; background: linear-gradient(135deg, #8a1d15, #bf2c1f); }
        button.btn {
            position: relative;
            z-index: 2;
            pointer-events: auto !important;
            cursor: pointer;
        }
        .form-control, .form-select {
            border: 1px solid #bfc4b7;
            background: #fff;
        }
        pre {
            margin: 0;
            white-space: pre-wrap;
            word-break: break-word;
            max-height: 280px;
            overflow: auto;
            font-size: 12.5px;
            border-radius: 10px;
            border: 1px solid var(--line);
            background: #f8f7f1;
            padding: 10px;
        }
                .span2 { grid-column: span 2; }
                canvas {
                    width: 100%;
                    height: 220px;
                    border: 1px solid var(--line);
                    border-radius: 10px;
                    background: linear-gradient(180deg, #f9f8f2, #f1efe7);
                }
        .pulse { animation: pulse 1.2s ease-in-out 1; }
        @keyframes pulse {
            0% { box-shadow: 0 0 0 0 rgba(10,122,74,0.45); }
            100% { box-shadow: 0 0 0 14px rgba(10,122,74,0); }
        }
        @media (max-width: 900px) {
            .grid { grid-template-columns: 1fr; }
            .span2 { grid-column: auto; }
            .kv { grid-template-columns: 1fr; }
        }
    </style>
</head>
<body>
    <div class=\"wrap\">
        <nav class=\"bar navbar\">
            <div class=\"title\">NYO Operator Console</div>
            <div class=\"row\">
                <span id=\"healthBadge\" class=\"health-badge\">Health --</span>
                <a href=\"/\">Runtime Console</a>
                <button id=\"btnRefresh\" class=\"btn btn-sm btn-nova\">Refresh</button>
                <button id=\"btnLogout\" class=\"btn btn-sm btn-danger-nova\">Logout</button>
            </div>
        </nav>

        <div id=\"feedbackBar\" class=\"feedback-strip muted\">Operator console ready.</div>
        <div id=\"runtimeNoteBar\" class=\"feedback-strip muted\">Runtime note not loaded yet.</div>

        <div class=\"tabs-wrap\">
            <ul class=\"nav nav-tabs\" id=\"controlTabs\">
                <li class=\"nav-item\"><button class=\"nav-link active\" data-pane-target=\"overview\" type=\"button\">Overview</button></li>
                <li class=\"nav-item\"><button class=\"nav-link\" data-pane-target=\"ops\" type=\"button\">Operations</button></li>
                <li class=\"nav-item\"><button class=\"nav-link\" data-pane-target=\"sessions\" type=\"button\">Sessions</button></li>
                <li class=\"nav-item\"><button class=\"nav-link\" data-pane-target=\"logs\" type=\"button\">Logs</button></li>
            </ul>
        </div>

        <div class=\"grid\">
            <section class=\"card pane pane-overview\">
                <div class=\"head\">Runtime Health</div>
                <div class=\"body\">
                    <div class="kv" id="statusKv"></div>
                </div>
            </section>

            <section class="card pane pane-sessions pane-hidden">
                <div class="head">Session Manager</div>
                <div class="body">
                    <div class="row" style="margin-bottom:8px;">
                        <select id="sessionSelect" class="form-select"></select>
                    </div>
                    <div class="row" style="margin-bottom:8px;">
                        <button id="btnSessionsRefresh" class="btn btn-sm btn-alt">Refresh Sessions</button>
                        <select id="searchProvider" class="form-select">
                            <option value="html">search provider html</option>
                            <option value="searxng">search provider searxng</option>
                        </select>
                        <button id="btnSearchProvider" class="btn btn-sm btn-nova">Apply Provider</button>
                        <button id="btnSearchToggle" class="btn btn-sm btn-alt">Toggle Provider</button>
                        <button id="btnSessionOpen" class="btn btn-sm btn-nova">Open In Chat</button>
                        <button id="btnSessionCopy" class="btn btn-sm btn-warn">Copy Session ID</button>
                        <button id="btnSessionDelete" class="btn btn-sm btn-danger-nova">Delete Session</button>
                    </div>
                    <pre id="sessionBox" class="mono">No session selected.</pre>
                </div>
            </section>

            <section class=\"card pane pane-overview\">
                <div class=\"head\">Control Access</div>
                <div class=\"body\">
                    <label class=\"muted\" for=\"key\">Control key (optional if local-only mode):</label>
                    <input id=\"key\" class=\"form-control\" type=\"password\" placeholder=\"NOVA_CONTROL_TOKEN\" />
                </div>
            </section>

            <section class=\"card pane pane-ops pane-hidden\">
                <div class=\"head\">Guard Control</div>
                <div class=\"body\">
                    <div class=\"row\" style=\"margin-bottom:8px;\">
                        <button id=\"btnGuardStatus\" class=\"btn btn-sm btn-alt\">Guard Status</button>
                        <button id=\"btnGuardStart\" class=\"btn btn-sm btn-nova\">Start Guard</button>
                        <button id=\"btnGuardStop\" class=\"btn btn-sm btn-danger-nova\">Stop Guard</button>
                    </div>
                    <pre id=\"guardBox\" class=\"mono\">No guard data yet.</pre>
                </div>
            </section>

            <section class=\"card pane pane-ops pane-hidden\">
                <div class=\"head\">Policy Controls</div>
                <div class=\"body\">
                    <div class=\"row\" style=\"margin-bottom:8px;\">
                        <input id=\"domainInput\" class=\"form-control\" placeholder=\"example.com\" />
                        <button id=\"btnAllow\" class=\"btn btn-sm btn-nova\">Allow Domain</button>
                        <button id=\"btnRemove\" class=\"btn btn-sm btn-alt\">Remove Domain</button>
                    </div>
                    <div class=\"row\">
                        <select id=\"webMode\" class=\"form-select\">
                            <option value=\"normal\">web mode normal</option>
                            <option value=\"max\">web mode max</option>
                        </select>
                        <button id=\"btnMode\" class=\"btn btn-sm btn-warn\">Apply Web Mode</button>
                        <button id=\"btnAudit\" class=\"btn btn-sm btn-alt\">Policy Audit</button>
                    </div>
                </div>
            </section>

            <section class=\"card pane pane-ops pane-hidden\">
                <div class=\"head\">Memory Governance</div>
                <div class=\"body\">
                    <div class=\"row\" style=\"margin-bottom:8px;\">
                        <select id=\"memoryScope\" class=\"form-select\">
                            <option value=\"private\">memory scope private</option>
                            <option value=\"hybrid\">memory scope hybrid</option>
                            <option value=\"shared\">memory scope shared</option>
                        </select>
                        <button id=\"btnMemoryScope\" class=\"btn btn-sm btn-nova\">Apply Memory Scope</button>
                    </div>
                    <pre id=\"memoryScopeBox\" class=\"mono\">Memory scope not loaded yet.</pre>
                </div>
            </section>

            <section class=\"card pane pane-ops pane-hidden\">
                <div class=\"head\">Chat Access</div>
                <div class=\"body\">
                    <div class=\"row\" style=\"margin-bottom:8px;\">
                        <select id=\"chatUserSelect\" class=\"form-select\"></select>
                        <input id=\"chatUserName\" class=\"form-control\" placeholder=\"username\" />
                        <input id=\"chatUserPass\" class=\"form-control\" type=\"password\" placeholder=\"new password\" />
                    </div>
                    <div class=\"row\" style=\"margin-bottom:8px;\">
                        <button id=\"btnChatUserUpsert\" class=\"btn btn-sm btn-nova\">Save Chat User</button>
                        <button id=\"btnChatUserDelete\" class=\"btn btn-sm btn-danger-nova\">Delete Chat User</button>
                        <button id=\"btnChatUserRefresh\" class=\"btn btn-sm btn-alt\">Refresh Chat Users</button>
                    </div>
                    <pre id=\"chatAuthBox\" class=\"mono\">Chat access not loaded yet.</pre>
                </div>
            </section>

            <section class=\"card pane pane-ops pane-hidden\">
                <div class=\"head\">Ops Actions</div>
                <div class=\"body\">
                    <div class=\"row\">
                        <button id=\"btnInspect\" class=\"btn btn-sm btn-warn\">Inspect Environment</button>
                        <button id=\"btnNovaStart\" class=\"btn btn-sm btn-nova\">Start Nova Core</button>
                        <button id=\"btnSelfCheck\" class=\"btn btn-sm btn-nova\">Run Self-Check</button>
                        <button id=\"btnExportCaps\" class=\"btn btn-sm btn-alt\">Export Capabilities</button>
                        <button id=\"btnExportLedger\" class=\"btn btn-sm btn-alt\">Export Ledger Summary</button>
                        <button id=\"btnExportBundle\" class=\"btn btn-sm btn-warn\">Export Diagnostics Bundle</button>
                        <button id=\"btnOut\" class=\"btn btn-sm btn-alt\">Tail HTTP OUT</button>
                        <button id=\"btnErr\" class=\"btn btn-sm btn-danger-nova\">Tail HTTP ERR</button>
                    </div>
                </div>
            </section>

            <section class=\"card span2 pane pane-overview\">
                <div class=\"head\">Policy Snapshot</div>
                <div class=\"body\">
                    <pre id=\"policyBox\" class=\"mono\">Loading...</pre>
                </div>
            </section>

            <section class=\"card span2 pane pane-overview\">
                <div class=\"head\">Telemetry</div>
                <div class=\"body\">
                    <canvas id=\"metricsCanvas\" width=\"1100\" height=\"220\"></canvas>
                    <div class=\"muted\" style=\"margin-top:8px;font-size:12px;\">Green: heartbeat age | Blue: requests/min | Red: errors/min</div>
                </div>
            </section>

            <section class=\"card span2 pane pane-logs pane-hidden\">
                <div class=\"head\">Action Output</div>
                <div class=\"body\">
                    <pre id=\"actionBox\" class=\"mono\">No actions yet.</pre>
                </div>
            </section>
        </div>
    </div>

<script>
    document.body.classList.add('js-ready');

    const keyInput = document.getElementById('key');
    const statusKv = document.getElementById('statusKv');
    const healthBadge = document.getElementById('healthBadge');
    const feedbackBar = document.getElementById('feedbackBar');
    const runtimeNoteBar = document.getElementById('runtimeNoteBar');
    const policyBox = document.getElementById('policyBox');
    const actionBox = document.getElementById('actionBox');
    const guardBox = document.getElementById('guardBox');
    const sessionSelect = document.getElementById('sessionSelect');
    const sessionBox = document.getElementById('sessionBox');
    const memoryScopeSelect = document.getElementById('memoryScope');
    const memoryScopeBox = document.getElementById('memoryScopeBox');
    const chatUserSelect = document.getElementById('chatUserSelect');
    const chatUserNameInput = document.getElementById('chatUserName');
    const chatUserPassInput = document.getElementById('chatUserPass');
    const chatAuthBox = document.getElementById('chatAuthBox');
    const metricsCanvas = document.getElementById('metricsCanvas');
    const ctx = metricsCanvas ? metricsCanvas.getContext('2d') : null;
    const tabButtons = Array.from(document.querySelectorAll('[data-pane-target]'));
    const allPanes = Array.from(document.querySelectorAll('.pane'));
    let sessionsCache = [];

    function setActivePane(name) {
        tabButtons.forEach((b) => {
            const on = (b.getAttribute('data-pane-target') || '') === name;
            b.classList.toggle('active', on);
        });
        allPanes.forEach((p) => {
            const show = p.classList.contains('pane-' + name);
            p.classList.toggle('pane-hidden', !show);
        });
    }

    tabButtons.forEach((b) => {
        b.addEventListener('click', () => {
            const target = (b.getAttribute('data-pane-target') || '').trim();
            if (target) setActivePane(target);
        });
    });

    if (keyInput) {
        keyInput.value = localStorage.getItem('nova_control_key') || '';
        keyInput.addEventListener('change', () => {
            localStorage.setItem('nova_control_key', keyInput.value.trim());
        });
    }

    function controlHeaders() {
        const k = keyInput ? keyInput.value.trim() : '';
        const headers = {'Content-Type': 'application/json'};
        if (k) headers['X-Nova-Control-Key'] = k;
        return headers;
    }

    function fmtStatusValue(k, v) {
        if (k === 'ollama_api_up' || k === 'web_enabled' || k === 'memory_enabled' || k === 'searxng_ok' || k === 'chat_login_enabled') {
            if (v === true) return `<span class=\"good\">true</span>`;
            if (v === false) return `<span class=\"danger\">false</span>`;
        }
        if (k === 'patch_enabled' || k === 'patch_strict_manifest' || k === 'patch_allow_force' || k === 'patch_behavioral_check' || k === 'patch_tests_available' || k === 'patch_ready_for_validated_apply') {
            if (v === true) return `<span class=\"good\">true</span>`;
            if (v === false) return `<span class=\"danger\">false</span>`;
        }
        if (k === 'heartbeat_age_sec' && typeof v === 'number') {
            const cls = v <= 15 ? 'good' : (v <= 45 ? 'warn' : 'danger');
            return `<span class=\"${cls}\">${v}s</span>`;
        }
        if (k === 'patch_last_preview_status') {
            const text = String(v || '');
            const cls = text.startsWith('eligible') ? 'good' : (text.startsWith('rejected') ? 'danger' : 'warn');
            return `<span class=\"${cls}\">${text || 'unknown'}</span>`;
        }
        return `<span class=\"mono\">${String(v)}</span>`;
    }

    function renderGovernance(policy, status) {
        const memory = policy && policy.memory && typeof policy.memory === 'object' ? policy.memory : {};
        const chatAuth = policy && policy.chat_auth && typeof policy.chat_auth === 'object' ? policy.chat_auth : {};
        const source = String(chatAuth.source || (status && status.chat_auth_source) || 'disabled');
        const users = Array.isArray(chatAuth.users) ? chatAuth.users : [];
        const count = Number(chatAuth.count || users.length || 0);
        const scope = String(memory.scope || (status && status.memory_scope) || 'private').trim().toLowerCase();

                'tool_events_total', 'tool_events_success_count', 'tool_events_failure_count', 'tool_events_denied_count',
                'tool_events_avg_latency_ms', 'tool_avg_latency_ms_by_tool', 'last_tool_name', 'last_tool_status', 'last_tool_error_summary'
        if (memoryScopeSelect && ['private', 'shared', 'hybrid'].includes(scope)) {
            memoryScopeSelect.value = scope;
        }
        if (memoryScopeBox) {
            memoryScopeBox.textContent = [
                `Current scope: ${scope}`,
                `Memory enabled: ${Boolean(memory.enabled)}`,
                `Mode: ${String(memory.mode || '')}`,
                `Top K: ${String(memory.top_k || '')}`,
            ].join('\\n');
        }

        if (chatUserSelect) {
            const prev = (chatUserSelect.value || '').trim();
            chatUserSelect.innerHTML = '';
            const first = document.createElement('option');
            first.value = '';
            first.textContent = users.length ? '(select chat user)' : '(no chat users)';
            chatUserSelect.appendChild(first);
            users.forEach((user) => {
                const opt = document.createElement('option');
                opt.value = user;
                opt.textContent = user;
                chatUserSelect.appendChild(opt);
            });
            if (prev && users.includes(prev)) {
                chatUserSelect.value = prev;
            }
        }
        if (chatAuthBox) {
            chatAuthBox.textContent = [
                `Login enabled: ${Boolean(chatAuth.enabled)}`,
                `Source: ${source}`,
                `Users: ${count}`,
                `Managed file: ${String(chatAuth.managed_path || '')}`,
                '',
                'Usernames:',
                users.length ? users.join('\\n') : '(none)',
            ].join('\\n');
        }
    }

    function setAction(text) {
        if (!actionBox) return;
        actionBox.textContent = text;
        actionBox.classList.remove('pulse');
        void actionBox.offsetWidth;
        actionBox.classList.add('pulse');
        const first = String(text || '').split('\\n')[0].trim() || 'Action complete.';
        setFeedback(first, /failed|error|denied|forbidden/i.test(first) ? 'danger' : 'good');
    }

    function setFeedback(text, level='muted') {
        if (!feedbackBar) return;
        feedbackBar.classList.remove('muted', 'good', 'warn', 'danger');
        const normalized = ['good', 'warn', 'danger', 'muted'].includes(level) ? level : 'muted';
        feedbackBar.classList.add(normalized);
        feedbackBar.textContent = text;
    }

    function bindClick(id, handler) {
        const el = document.getElementById(id);
        if (!el) {
            console.warn('Control UI missing element:', id);
            setFeedback(`Control UI warning: missing element ${id}`, 'warn');
            return;
        }
        // Force button semantics and bind one click pathway.
        if (el.tagName === 'BUTTON') {
            el.setAttribute('type', 'button');
            el.disabled = false;
        }
        const wrapped = (ev) => {
            try {
                if (ev && typeof ev.preventDefault === 'function') ev.preventDefault();
                setFeedback('Clicked ' + id + ' ...', 'muted');
                return handler(ev);
            } catch (err) {
                setFeedback('Handler error for ' + id + ': ' + (err && err.message ? err.message : String(err)), 'danger');
            }
        };
        el.addEventListener('click', wrapped);
    }

    function setHealthBadge(score, ratio, alerts) {
        const s = Number(score || 0);
        const a = Array.isArray(alerts) ? alerts : [];
        const pct = Math.max(0, Math.min(100, Math.round((Number(ratio || 0)) * 100)));
        let cls = 'warn';
        if (s >= 90 && a.length === 0) cls = 'good';
        else if (s < 70 || a.length > 0) cls = 'danger';
        if (!healthBadge) return;
        healthBadge.classList.remove('good', 'warn', 'danger');
        healthBadge.classList.add(cls);
        healthBadge.textContent = `Health ${s}/100 (${pct}%)`;
        healthBadge.title = a.length ? ('Alerts: ' + a.join('; ')) : 'No active alerts';
    }

    function drawMetrics(points) {
        if (!ctx) return;
        const w = metricsCanvas.width;
        const h = metricsCanvas.height;
        ctx.clearRect(0, 0, w, h);
        ctx.fillStyle = '#f5f3eb';
        ctx.fillRect(0, 0, w, h);

        if (!points || points.length < 2) {
            ctx.fillStyle = '#6a665f';
            ctx.font = '14px Segoe UI';
            ctx.fillText('Telemetry will appear after a few refresh cycles.', 12, 28);
            return;
        }

        const pad = 28;
        const iw = w - pad * 2;
        const ih = h - pad * 2;
        const recent = points.slice(-60);

        const hb = recent.map(p => Number(p.heartbeat_age_sec || 0));
        const reqPerMin = [];
        const errPerMin = [];
        for (let i = 0; i < recent.length; i++) {
            if (i === 0) { reqPerMin.push(0); errPerMin.push(0); continue; }
            const dt = Math.max(1, Number(recent[i].ts || 0) - Number(recent[i - 1].ts || 0));
            const dr = Math.max(0, Number(recent[i].requests_total || 0) - Number(recent[i - 1].requests_total || 0));
            const de = Math.max(0, Number(recent[i].errors_total || 0) - Number(recent[i - 1].errors_total || 0));
            reqPerMin.push((dr * 60) / dt);
            errPerMin.push((de * 60) / dt);
        }

        const ymax = Math.max(5, ...hb, ...reqPerMin, ...errPerMin);
        const x = (i) => pad + (i / (recent.length - 1)) * iw;
        const y = (v) => pad + ih - (Math.max(0, v) / ymax) * ih;

        ctx.strokeStyle = '#d8d5cc';
        ctx.lineWidth = 1;
        for (let i = 0; i <= 4; i++) {
            const gy = pad + (ih / 4) * i;
            ctx.beginPath();
            ctx.moveTo(pad, gy);
            ctx.lineTo(w - pad, gy);
            ctx.stroke();
        }

        function plot(arr, color) {
            ctx.strokeStyle = color;
            ctx.lineWidth = 2;
            ctx.beginPath();
            arr.forEach((v, i) => {
                const px = x(i);
                const py = y(v);
                if (i === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
            });
            ctx.stroke();
        }

        plot(hb, '#0f8f5c');
        plot(reqPerMin, '#2563eb');
        plot(errPerMin, '#c62828');

        ctx.fillStyle = '#46413a';
        ctx.font = '12px IBM Plex Mono, Consolas, monospace';
        ctx.fillText('0', 6, h - pad + 4);
        ctx.fillText(String(Math.round(ymax)), 6, pad + 4);
    }

    async function getJson(url) {
        const r = await fetch(url, {headers: controlHeaders()});
        const j = await r.json();
        if (!r.ok || !j.ok) throw new Error(j.error || j.message || ('HTTP ' + r.status));
        return j;
    }

    async function postAction(action, body={}) {
        const r = await fetch('/api/control/action', {
            method: 'POST',
            headers: controlHeaders(),
            body: JSON.stringify({action, ...body})
        });
        const j = await r.json();
        if (!r.ok || !j.ok) throw new Error(j.error || j.message || ('HTTP ' + r.status));
        return j;
    }

    async function refresh() {
        try {
            const results = await Promise.allSettled([
                getJson('/api/control/status'),
                getJson('/api/control/policy'),
                getJson('/api/control/metrics'),
                getJson('/api/control/sessions')
            ]);

            const status = results[0].status === 'fulfilled' ? results[0].value : null;
            const policy = results[1].status === 'fulfilled' ? results[1].value : null;
            const metrics = results[2].status === 'fulfilled' ? results[2].value : null;
            const sess = results[3].status === 'fulfilled' ? results[3].value : null;

            const failed = results
                .map((r, i) => ({r, i}))
                .filter(x => x.r.status !== 'fulfilled')
                .map(x => ['status', 'policy', 'metrics', 'sessions'][x.i]);

            const keys = [
                'server_time', 'ollama_api_up', 'chat_model', 'memory_enabled', 'memory_scope', 'web_enabled',
                'memory_stats_ok', 'memory_entries_total', 'memory_by_user_count',
                'memory_events_ok', 'memory_events_total', 'memory_write_count', 'memory_recall_count',
                'memory_skipped_count', 'memory_events_avg_latency_ms', 'last_memory_action', 'last_memory_status',
                'chat_login_enabled', 'chat_auth_source', 'chat_users_count',
                'patch_enabled', 'patch_strict_manifest', 'patch_behavioral_check', 'patch_behavioral_check_timeout_sec',
                'patch_tests_available', 'patch_ready_for_validated_apply', 'patch_current_revision',
                'patch_previews_total', 'patch_previews_pending', 'patch_previews_approved', 'patch_previews_rejected',
                'patch_last_preview_name', 'patch_last_preview_status', 'patch_last_preview_decision',
                'search_provider', 'search_api_endpoint', 'allow_domains_count', 'process_counting_mode',
                'heartbeat_age_sec', 'core_running', 'core_pid', 'core_heartbeat_age_sec',
                'active_http_sessions', 'requests_total', 'errors_total', 'searxng_ok', 'searxng_note'
            ];
            if (status) {
                if (statusKv) {
                    statusKv.innerHTML = keys.map(k => `<div class=\"muted\">${k}</div><div>${fmtStatusValue(k, status[k])}</div>`).join('');
                }
                if (runtimeNoteBar) {
                    runtimeNoteBar.textContent = String(status.runtime_process_note || '');
                }
                const providerSelect = document.getElementById('searchProvider');
                if (providerSelect && typeof status.search_provider === 'string') {
                    const sp = status.search_provider.trim().toLowerCase();
                    if (sp === 'html' || sp === 'searxng') {
                        providerSelect.value = sp;
                    }
                }
                setHealthBadge(status.health_score, status.self_check_pass_ratio, status.alerts || []);
                if (guardBox) {
                    guardBox.textContent = JSON.stringify(status.guard || {}, null, 2);
                }
            }
            if (policy) {
                if (policyBox) {
                    policyBox.textContent = JSON.stringify(policy, null, 2);
                }
                renderGovernance(policy, status);
            }
            if (metrics) {
                drawMetrics(metrics.points || []);
            }
            if (sess) {
                sessionsCache = Array.isArray(sess.sessions) ? sess.sessions : [];
                renderSessions();
            }
            if (!status && !policy && !metrics && !sess) {
                throw new Error('All control endpoints failed');
            }

            if (failed.length) {
                setFeedback('Partial refresh (' + failed.join(', ') + ' failed) at ' + new Date().toLocaleTimeString(), 'warn');
            } else {
                setFeedback('Live status refreshed at ' + new Date().toLocaleTimeString(), 'muted');
            }
        } catch (err) {
            setAction('Refresh failed: ' + err.message);
        }
    }

    function renderSessions() {
        const prev = (sessionSelect.value || '').trim();
        if (!sessionSelect || !sessionBox) return;
        sessionSelect.innerHTML = '';
        if (!sessionsCache.length) {
            const o = document.createElement('option');
            o.value = '';
            o.textContent = '(no sessions)';
            sessionSelect.appendChild(o);
            sessionBox.textContent = 'No persisted chat sessions found.';
            return;
        }
        sessionsCache.forEach(s => {
            const o = document.createElement('option');
            o.value = s.session_id;
            o.textContent = `${s.session_id} (${s.turn_count} turns)`;
            sessionSelect.appendChild(o);
        });
        if (prev && sessionsCache.some(s => s.session_id === prev)) {
            sessionSelect.value = prev;
        }
        renderSessionPreview();
    }

    function renderSessionPreview() {
        const sid = (sessionSelect.value || '').trim();
        if (!sessionBox) return;
        const s = sessionsCache.find(x => x.session_id === sid);
        if (!s) {
            sessionBox.textContent = 'No session selected.';
            return;
        }
        const lines = [
            `Session: ${s.session_id}`,
            `Turns: ${s.turn_count}`,
            '',
            'Last user:',
            s.last_user || '(none)',
            '',
            'Last assistant:',
            s.last_assistant || '(none)',
        ];
        sessionBox.textContent = lines.join('\\n');
    }

    bindClick('btnRefresh', refresh);
    if (sessionSelect) {
        sessionSelect.addEventListener('change', renderSessionPreview);
    }

    bindClick('btnLogout', async () => {
        try {
            await fetch('/api/control/logout', {method: 'POST', headers: controlHeaders(), body: '{}'});
            window.location.href = '/control';
        } catch (err) {
            setAction('Logout failed: ' + err.message);
        }
    });

    bindClick('btnSessionsRefresh', async () => {
        try {
            const sess = await getJson('/api/control/sessions');
            sessionsCache = Array.isArray(sess.sessions) ? sess.sessions : [];
            renderSessions();
            setAction('Session list refreshed.');
        } catch (err) {
            setAction('Session refresh failed: ' + err.message);
        }
    });

    bindClick('btnSessionOpen', () => {
        const sid = (sessionSelect.value || '').trim();
        if (!sid) {
            setAction('Select a session first.');
            return;
        }
        window.open('/?sid=' + encodeURIComponent(sid), '_blank');
    });

    bindClick('btnSessionCopy', async () => {
        const sid = (sessionSelect.value || '').trim();
        if (!sid) {
            setAction('Select a session first.');
            return;
        }
        try {
            await navigator.clipboard.writeText(sid);
            setAction('Session ID copied: ' + sid);
        } catch (_) {
            setAction('Unable to copy to clipboard. Session ID: ' + sid);
        }
    });

    bindClick('btnSessionDelete', async () => {
        const sid = (sessionSelect.value || '').trim();
        if (!sid) {
            setAction('Select a session first.');
            return;
        }
        try {
            const j = await postAction('session_delete', {session_id: sid});
            sessionsCache = Array.isArray(j.sessions) ? j.sessions : sessionsCache.filter(x => x.session_id !== sid);
            renderSessions();
            setAction(j.message || 'Session deleted.');
        } catch (err) {
            setAction('Delete session failed: ' + err.message);
        }
    });

    bindClick('btnGuardStatus', async () => {
        try {
            const j = await postAction('guard_status');
            guardBox.textContent = JSON.stringify(j.guard || {}, null, 2);
            setAction(j.message || 'guard_status done');
            await refresh();
        } catch (err) {
            setAction('Guard status failed: ' + err.message);
        }
    });

    bindClick('btnGuardStart', async () => {
        try {
            const j = await postAction('guard_start');
            guardBox.textContent = JSON.stringify(j.guard || {}, null, 2);
            setAction(j.message || 'guard_start done');
            await refresh();
        } catch (err) {
            setAction('Guard start failed: ' + err.message);
        }
    });

    bindClick('btnGuardStop', async () => {
        try {
            const j = await postAction('guard_stop');
            guardBox.textContent = JSON.stringify(j.guard || {}, null, 2);
            setAction(j.message || 'guard_stop done');
            await refresh();
        } catch (err) {
            setAction('Guard stop failed: ' + err.message);
        }
    });

    bindClick('btnAllow', async () => {
        try {
            const domain = (document.getElementById('domainInput').value || '').trim();
            const j = await postAction('policy_allow', {domain});
            setAction(j.message || 'policy_allow done');
            await refresh();
        } catch (err) {
            setAction('Allow failed: ' + err.message);
        }
    });

    bindClick('btnRemove', async () => {
        try {
            const domain = (document.getElementById('domainInput').value || '').trim();
            const j = await postAction('policy_remove', {domain});
            setAction(j.message || 'policy_remove done');
            await refresh();
        } catch (err) {
            setAction('Remove failed: ' + err.message);
        }
    });

    bindClick('btnMode', async () => {
        try {
            const mode = document.getElementById('webMode').value;
            const j = await postAction('web_mode', {mode});
            setAction(j.message || 'web_mode done');
            await refresh();
        } catch (err) {
            setAction('Web mode failed: ' + err.message);
        }
    });

    bindClick('btnMemoryScope', async () => {
        try {
            const scope = memoryScopeSelect ? memoryScopeSelect.value : 'private';
            const j = await postAction('memory_scope_set', {scope});
            setAction(j.message || 'memory_scope_set done');
            await refresh();
        } catch (err) {
            setAction('Memory scope update failed: ' + err.message);
        }
    });

    bindClick('btnSearchProvider', async () => {
        try {
            const provider = document.getElementById('searchProvider').value;
            const j = await postAction('search_provider', {provider});
            setAction(j.message || 'search_provider done');
            await refresh();
        } catch (err) {
            setAction('Search provider apply failed: ' + err.message);
        }
    });

    bindClick('btnSearchToggle', async () => {
        try {
            const j = await postAction('search_provider_toggle');
            setAction(j.message || 'search_provider_toggle done');
            await refresh();
        } catch (err) {
            setAction('Search provider toggle failed: ' + err.message);
        }
    });

    if (chatUserSelect && chatUserNameInput) {
        chatUserSelect.addEventListener('change', () => {
            const user = (chatUserSelect.value || '').trim();
            if (user) chatUserNameInput.value = user;
        });
    }

    bindClick('btnChatUserRefresh', async () => {
        try {
            await refresh();
            setAction('Chat user list refreshed.');
        } catch (err) {
            setAction('Chat user refresh failed: ' + err.message);
        }
    });

    bindClick('btnChatUserUpsert', async () => {
        try {
            const username = chatUserNameInput ? chatUserNameInput.value.trim() : '';
            const password = chatUserPassInput ? chatUserPassInput.value : '';
            const j = await postAction('chat_user_upsert', {username, password});
            if (chatUserPassInput) chatUserPassInput.value = '';
            setAction(j.message || 'chat_user_upsert done');
            await refresh();
        } catch (err) {
            setAction('Chat user save failed: ' + err.message);
        }
    });

    bindClick('btnChatUserDelete', async () => {
        try {
            const username = (chatUserNameInput && chatUserNameInput.value.trim()) || (chatUserSelect && chatUserSelect.value.trim()) || '';
            const j = await postAction('chat_user_delete', {username});
            if (chatUserNameInput) chatUserNameInput.value = '';
            if (chatUserPassInput) chatUserPassInput.value = '';
            setAction(j.message || 'chat_user_delete done');
            await refresh();
        } catch (err) {
            setAction('Chat user delete failed: ' + err.message);
        }
    });

    bindClick('btnAudit', async () => {
        try {
            const j = await postAction('policy_audit');
            setAction(j.text || j.message || 'policy_audit done');
        } catch (err) {
            setAction('Policy audit failed: ' + err.message);
        }
    });

    bindClick('btnInspect', async () => {
        try {
            const j = await postAction('inspect');
            setAction(j.report || j.message || 'inspect done');
        } catch (err) {
            setAction('Inspect failed: ' + err.message);
        }
    });

    bindClick('btnNovaStart', async () => {
        try {
            const j = await postAction('nova_start');
            const core = j.core || {};
            const pid = core.pid ? (' pid=' + core.pid) : '';
            const hb = Number.isFinite(Number(core.heartbeat_age_sec)) ? (' hb_age=' + Number(core.heartbeat_age_sec) + 's') : '';
            setAction((j.message || 'nova_start done') + (core.running ? ' (running)' : ' (starting)') + pid + hb);
            await refresh();
        } catch (err) {
            setAction('Start Nova failed: ' + err.message);
        }
    });

    bindClick('btnSelfCheck', async () => {
        try {
            const r = await fetch('/api/control/action', {
                method: 'POST',
                headers: controlHeaders(),
                body: JSON.stringify({action: 'self_check'})
            });
            const j = await r.json();
            const checks = Array.isArray(j.checks) ? j.checks : [];
            const lines = [j.summary || 'self_check completed'];
            checks.forEach((c) => {
                lines.push(`- ${c.name}: ${c.ok ? 'OK' : 'FAIL'}${c.detail ? ' (' + c.detail + ')' : ''}`);
            });
            if (!r.ok && !checks.length) {
                throw new Error(j.error || j.message || ('HTTP ' + r.status));
            }
            setAction(lines.join('\\n'));
            await refresh();
        } catch (err) {
            setAction('Self-check failed: ' + err.message);
        }
    });

    bindClick('btnExportCaps', async () => {
        try {
            const j = await postAction('export_capabilities');
            const caps = j.capabilities || {};
            const fileName = j.filename || 'capabilities_export.json';
            const blob = new Blob([JSON.stringify(caps, null, 2)], {type: 'application/json'});
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = fileName;
            document.body.appendChild(a);
            a.click();
            a.remove();
            URL.revokeObjectURL(url);
            setAction(`Capabilities exported (${Object.keys(caps).length}) to ${fileName}`);
        } catch (err) {
            setAction('Export capabilities failed: ' + err.message);
        }
    });

    bindClick('btnExportLedger', async () => {
        try {
            const j = await postAction('export_ledger_summary', {limit: 80});
            const summary = j.summary || {};
            const fileName = j.filename || 'action_ledger_summary.json';
            const blob = new Blob([JSON.stringify(summary, null, 2)], {type: 'application/json'});
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = fileName;
            document.body.appendChild(a);
            a.click();
            a.remove();
            URL.revokeObjectURL(url);
            setAction(`Action ledger summary exported to ${fileName}`);
        } catch (err) {
            setAction('Export ledger summary failed: ' + err.message);
        }
    });

    bindClick('btnExportBundle', async () => {
        try {
            const j = await postAction('export_diagnostics_bundle');
            const fileName = j.filename || 'diagnostics_bundle.json';
            const p = (j.path || '').trim();
            setAction(`Diagnostics bundle exported: ${fileName}${p ? ' @ ' + p : ''}`);
        } catch (err) {
            setAction('Export diagnostics bundle failed: ' + err.message);
        }
    });

    bindClick('btnOut', async () => {
        try {
            const j = await postAction('tail_log', {name: 'nova_http.out.log'});
            setAction(j.text || 'No output');
        } catch (err) {
            setAction('Tail OUT failed: ' + err.message);
        }
    });

    bindClick('btnErr', async () => {
        try {
            const j = await postAction('tail_log', {name: 'nova_http.err.log'});
            setAction(j.text || 'No output');
        } catch (err) {
            setAction('Tail ERR failed: ' + err.message);
        }
    });

    window.addEventListener('error', (ev) => {
        const msg = (ev && ev.message) ? ev.message : 'Unknown script error';
        setFeedback('UI script error: ' + msg, 'danger');
    });

    window.addEventListener('unhandledrejection', (ev) => {
        const reason = ev && ev.reason ? String(ev.reason) : 'Unhandled promise rejection';
        setFeedback('UI async error: ' + reason, 'danger');
    });

    document.addEventListener('click', (ev) => {
        const t = ev && ev.target ? ev.target.closest('button, a, [data-pane-target]') : null;
        if (!t) return;
        const id = t.id ? ('#' + t.id) : (t.getAttribute('data-pane-target') ? ('tab:' + t.getAttribute('data-pane-target')) : t.tagName.toLowerCase());
        setFeedback('Click received: ' + id, 'muted');
    }, true);

    setFeedback('Control UI connected. Fetching live status...', 'muted');
    setActivePane('overview');
    refresh();
    setInterval(refresh, 15000);
</script>
</body>
</html>
"""

CONTROL_HTML = _render_control_html()


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Nova LAN HTTP interface")
    ap.add_argument("--host", default="127.0.0.1", help="Bind host (use 0.0.0.0 for LAN)")
    ap.add_argument("--port", type=int, default=8080, help="Bind port")
    return ap.parse_args()


def main() -> None:
    global _HTTP_SERVER, _HTTP_BIND_HOST, _HTTP_BIND_PORT
    args = parse_args()
    _HTTP_BIND_HOST = str(args.host)
    _HTTP_BIND_PORT = int(args.port)
    _load_persisted_sessions()
    try:
        nova_core.ensure_ollama_boot()
    except Exception:
        pass

    srv = ThreadingHTTPServer((args.host, args.port), NovaHttpHandler)
    _HTTP_SERVER = srv
    print(f"Nova HTTP runtime console ready at http://{args.host}:{args.port}", flush=True)
    print(f"Control Room: http://{args.host}:{args.port}/control", flush=True)
    if args.host == "0.0.0.0":
        print("LAN mode enabled. Open from another device via http://<this-pc-ip>:" + str(args.port), flush=True)
    if _dev_mode_enabled():
        print("Control Room auth: DEVELOPMENT MODE enabled (NOVA_DEV_MODE=1, auth checks bypassed).", flush=True)
    elif (os.environ.get("NOVA_CONTROL_TOKEN") or "").strip():
        print("Control Room auth: NOVA_CONTROL_TOKEN is enabled (required for admin API access).", flush=True)
    else:
        print("Control Room auth: local-only mode (set NOVA_CONTROL_TOKEN for LAN-secure access).", flush=True)
    if _control_login_enabled():
        print("Control Room login: enabled (set via NOVA_CONTROL_USER / NOVA_CONTROL_PASS).", flush=True)
    else:
        print("Control Room login: disabled (optional).", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        _HTTP_SERVER = None
        srv.server_close()


if __name__ == "__main__":
    main()
