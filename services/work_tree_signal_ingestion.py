from __future__ import annotations

from datetime import datetime
import hashlib
import json
from typing import Any

import work_tree
from services.evidence_validity import evidence_result_valid
from services.nova_temporal_service import build_temporal_pressure
from services.nova_wiring_inventory import build_root_closure_inventory_payload
from services.nova_wiring_inventory import build_self_repair_closure_inventory_payload
from services.nova_wiring_inventory import build_wiring_inventory_payload
from services.nova_wiring_inventory import WIRING_SURFACES
from work_tree_contracts import BranchStatus


_VALID_SIGNAL_CLASSES = {
    "runtime_failure",
    "error_spike",
    "dependency_unreachable",
    "code_defect",
    "governance_pressure",
    "maintenance_pressure",
    "temporal_pressure",
    "operator_requested",
    "regression_failure",
    "subconscious_candidate",
    "release_readiness_gap",
    "declared_capability_absent",
}

_SIGNAL_TO_WORK_CLASS = {
    "runtime_failure": "runtime_failure",
    "error_spike": "runtime_failure",
    "dependency_unreachable": "dependency_unreachable",
    "code_defect": "code_defect",
    "governance_pressure": "governance_pressure",
    "maintenance_pressure": "maintenance_pressure",
    "temporal_pressure": "temporal_pressure",
    "operator_requested": "operator_requested",
    "regression_failure": "regression_failure",
    "subconscious_candidate": "candidate_review",
    "release_readiness_gap": "release_readiness_gap",
    "declared_capability_absent": "capability_gap",
}

MEMORY_BOOTSTRAP_PULSE_TASK_TITLE = "Pulse current memory bootstrap evidence without writing memory files"
MEMORY_IDENTITY_BOOTSTRAP_TASK_TITLE = "Apply operator-confirmed memory identity bootstrap"
MEMORY_BOOTSTRAP_ORIGIN_CONTRACT_REQUIRED = "memory_bootstrap_origin_contract_required"
VOICE_RUNTIME_READ_TASK_TITLE = "Read voice runtime dependency loader and entrypoint wiring"
AUTONOMY_MAINTENANCE_LOG_TASK_TITLE = "Read runtime/autonomy_maintenance.log around the latest maintenance error"
TOOL_EVENTS_READ_TASK_TITLE = "Read runtime/tool_events.jsonl recent tool execution events"
OS_CAPABILITY_LEDGER_READ_TASK_TITLE = "Read runtime/os_capability_ledger.jsonl recent OS capability evidence"
SOURCE_ROOT_JUDGMENT_TASK_TITLE = "Synthesize source-root judgment from collected evidence"
SOURCE_ROOT_JUDGMENT_TOOL = "source_root_judgment"

_SOURCE_ROOT_SIGNAL_SOURCES = frozenset(
    source
    for surface in WIRING_SURFACES
    for source in surface.signal_sources
)
_SPECIALIZED_SEQUENCE_TOOLS = frozenset(
    {
        "memory_bootstrap_judgment",
        "memory_identity_bootstrap",
        "release_promotion_judgment",
        "release_validation_run",
        "release_record_validation_outcome",
        "release_rebuild_verify",
        "installer_validation_run",
        "subconscious_review_judgment",
        SOURCE_ROOT_JUDGMENT_TOOL,
    }
)

_BUCKET_BY_WORK_CLASS = {
    "runtime_failure": "runtime",
    "code_defect": "code_defect",
    "dependency_unreachable": "dependency",
    "governance_pressure": "governance",
    "maintenance_pressure": "maintenance",
    "temporal_pressure": "temporal",
    "operator_requested": "operator",
    "regression_failure": "regression",
    "candidate_review": "candidate_review",
    "release_readiness_gap": "release",
    "capability_gap": "capability",
}

_DEFAULT_ACTIONABILITY_BY_CLASS = {
    "runtime_failure": "safe_now",
    "code_defect": "safe_now",
    "dependency_unreachable": "dead_end",
    "governance_pressure": "blocked",
    "maintenance_pressure": "safe_now",
    "temporal_pressure": "safe_now",
    "operator_requested": "safe_now",
    "regression_failure": "safe_now",
    "candidate_review": "safe_now",
    "release_readiness_gap": "blocked",
    "capability_gap": "safe_now",
}

_BRANCH_STATUS_BY_ACTIONABILITY = {
    "safe_now": BranchStatus.READY,
    "blocked": BranchStatus.BLOCKED,
    "dead_end": BranchStatus.STALLED,
}

_RESOLUTION_BY_ACTIONABILITY = {
    "safe_now": "open",
    "blocked": "observing",
    "dead_end": "retired",
}


def _strip_inactive_resolution_notes(notes: str) -> str:
    """Remove stale closure lines when a signal becomes active again."""
    lines = [
        line
        for line in str(notes or "").splitlines()
        if not line.strip().startswith(("Resolution:", "Observation:", "Retired:"))
    ]
    return "\n".join(line for line in lines if line.strip()).strip()


def _same_artifact_path(left: Any, right: Any) -> bool:
    lhs = str(left or "").strip().replace("\\", "/").rstrip("/").lower()
    rhs = str(right or "").strip().replace("\\", "/").rstrip("/").lower()
    return bool(lhs and rhs and lhs == rhs)


def _port_ownership_for(status_payload: dict[str, Any], port: int) -> dict[str, Any]:
    port_ownership = status_payload.get("port_ownership") if isinstance(status_payload.get("port_ownership"), dict) else {}
    ports = port_ownership.get("ports") if isinstance(port_ownership.get("ports"), dict) else {}
    row = ports.get(str(int(port))) or ports.get(int(port))
    return dict(row) if isinstance(row, dict) else {}


def _model_runtime_model(status_payload: dict[str, Any], ollama_health: dict[str, Any]) -> str:
    return str(
        status_payload.get("ollama_configured_model")
        or ollama_health.get("chat_model")
        or status_payload.get("chat_model")
        or ""
    ).strip()


def _model_runtime_verify_request(
    status_payload: dict[str, Any],
    ollama_health: dict[str, Any],
    *,
    probe_chat: bool,
) -> str:
    base_url = str(
        status_payload.get("ollama_base_url")
        or status_payload.get("ollama_api_endpoint")
        or ollama_health.get("base_url")
        or "http://127.0.0.1:11434"
    ).strip()
    args: dict[str, Any] = {
        "base_url": base_url or "http://127.0.0.1:11434",
        "probe_chat": bool(probe_chat),
    }
    model = _model_runtime_model(status_payload, ollama_health)
    if model:
        args["model"] = model
    return json.dumps({"capability": "verify_ollama_model", "args": args}, sort_keys=True)


def _model_runtime_port_request() -> str:
    return json.dumps({"capability": "inspect_ports", "args": {"ports": [11434]}}, sort_keys=True)


def _model_runtime_task_sequence(
    status_payload: dict[str, Any],
    ollama_health: dict[str, Any],
    *,
    probe_chat: bool,
    inspect_port_first: bool = False,
    include_action_ledger: bool = False,
) -> list[dict[str, Any]]:
    sequence: list[dict[str, Any]] = []
    if inspect_port_first:
        sequence.append({
            "title": "Inspect model runtime port ownership through registered OS capability",
            "allowed_tools": ["os_capability"],
            "preferred_tool": "os_capability",
            "tool_args": [_model_runtime_port_request()],
        })
    sequence.append({
        "title": "Verify Ollama model runtime contract through registered OS capability",
        "allowed_tools": ["os_capability"],
        "preferred_tool": "os_capability",
        "tool_args": [_model_runtime_verify_request(status_payload, ollama_health, probe_chat=probe_chat)],
    })
    if include_action_ledger:
        sequence.append({
            "title": "Read runtime/action_ledger.jsonl around the last LLM failure",
            "allowed_tools": ["read"],
            "preferred_tool": "read",
            "tool_args": ["runtime/action_ledger.jsonl"],
        })
    sequence.extend([
        {
            "title": "Read model runtime health source",
            "allowed_tools": ["read"],
            "preferred_tool": "read",
            "tool_args": ["services/ollama_health.py"],
        },
        {
            "title": "Read model runtime port ownership source",
            "allowed_tools": ["read"],
            "preferred_tool": "read",
            "tool_args": ["services/port_ownership.py"],
        },
    ])
    return sequence


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _memory_health_signal_from_status(status_payload: dict[str, Any]) -> dict[str, Any] | None:
    memory_health = status_payload.get("memory_health") if isinstance(status_payload.get("memory_health"), dict) else {}
    memory_status = str(status_payload.get("memory_health_status") or memory_health.get("status") or "").strip().lower()
    issue_count = int(status_payload.get("memory_health_issue_count", memory_health.get("issue_count", 0)) or 0)
    issues = status_payload.get("memory_health_issues") if isinstance(status_payload.get("memory_health_issues"), list) else memory_health.get("issues")
    issue_rows = [dict(item) for item in list(issues or []) if isinstance(item, dict)]
    bootstrap = memory_health.get("bootstrap") if isinstance(memory_health.get("bootstrap"), dict) else {}
    bootstrap_origin = memory_health.get("bootstrap_origin") if isinstance(memory_health.get("bootstrap_origin"), dict) else {}
    bootstrap_missing = [
        str(item or "").strip()
        for item in list(bootstrap.get("missing") or [])
        if str(item or "").strip()
    ]
    origin_status = str(bootstrap_origin.get("status") or bootstrap.get("origin_status") or "").strip().lower()
    origin_ready = origin_status == "ready" and bool(bootstrap_origin.get("may_seed_identity_facts", False))
    active = bool(
        memory_status
        and memory_status not in {"ok", "unknown"}
        or issue_count > 0
        or bootstrap_missing
    )
    if not active:
        return None

    issue_codes = [
        str(item.get("code") or "").strip()
        for item in issue_rows
        if str(item.get("code") or "").strip()
    ]
    if bootstrap_missing and "memory_bootstrap_incomplete" not in issue_codes:
        issue_codes.append("memory_bootstrap_incomplete")
    error_symbol = "memory_health_failure" if memory_status == "failure" else "memory_health_watch"
    if bootstrap_missing:
        error_symbol = "memory_bootstrap_incomplete"
    blocked_task = "Await operator-confirmed memory bootstrap origin contract before writing identity facts"
    blocked_reason = MEMORY_BOOTSTRAP_ORIGIN_CONTRACT_REQUIRED
    if origin_status == "pending_operator_confirmation":
        blocked_task = "Await operator confirmation of memory bootstrap origin before writing identity facts"
        blocked_reason = "memory_bootstrap_origin_confirmation_pending"
    if origin_ready and bootstrap_missing:
        blocked_task = ""
        blocked_reason = ""

    allowed_tools = ["pulse", "read", "find", "memory_bootstrap_judgment"]
    preferred_tool = "pulse"
    next_task = MEMORY_BOOTSTRAP_PULSE_TASK_TITLE
    task_sequence = [
        {
            "title": MEMORY_BOOTSTRAP_PULSE_TASK_TITLE,
            "allowed_tools": ["pulse"],
            "preferred_tool": "pulse",
        },
        {
            "title": "Find memory_health_payload identity learned_facts bootstrap persistence path",
            "allowed_tools": ["find"],
            "preferred_tool": "find",
        },
        {
            "title": "Find append_memory_event memory_events logging path",
            "allowed_tools": ["find"],
            "preferred_tool": "find",
        },
        {
            "title": "Read memory/bootstrap_origin.json bootstrap origin contract",
            "allowed_tools": ["read"],
            "preferred_tool": "read",
        },
        {
            "title": "Synthesize memory bootstrap judgment from collected evidence",
            "allowed_tools": ["memory_bootstrap_judgment"],
            "preferred_tool": "memory_bootstrap_judgment",
        },
    ]
    if origin_ready and bootstrap_missing:
        allowed_tools = ["memory_identity_bootstrap", "pulse", "read"]
        preferred_tool = "memory_identity_bootstrap"
        next_task = MEMORY_IDENTITY_BOOTSTRAP_TASK_TITLE
        task_sequence = [
            {
                "title": MEMORY_IDENTITY_BOOTSTRAP_TASK_TITLE,
                "allowed_tools": ["memory_identity_bootstrap"],
                "preferred_tool": "memory_identity_bootstrap",
            },
            {
                "title": "Pulse memory health after identity bootstrap",
                "allowed_tools": ["pulse"],
                "preferred_tool": "pulse",
            },
        ]
    return {
        "source": "memory_identity",
        "signal_class": "governance_pressure",
        "title": "Investigate memory persistence bootstrap gap",
        "fingerprint": {
            "class": "governance_pressure",
            "surface": "memory_identity",
            "error": error_symbol,
            "symbol": "identity_memory",
        },
        "payload": {
            "memory_enabled": bool(status_payload.get("memory_enabled", bootstrap.get("memory_enabled", False))),
            "memory_health_status": memory_status or "unknown",
            "memory_health_issue_count": issue_count,
            "memory_health_issue_codes": issue_codes[:8],
            "memory_health_issues": issue_rows[:6],
            "memory_bootstrap": dict(bootstrap),
            "memory_bootstrap_origin": dict(bootstrap_origin),
            "memory_db_total": int(status_payload.get("memory_db_total", 0) or 0),
            "memory_events_log_status": str(status_payload.get("memory_events_log_status") or "").strip(),
            "rationale": "Memory health is not ready while persistence files or event evidence are missing.",
        },
        "severity": "high" if memory_status == "failure" else "medium",
        "actionability": "safe_now",
        "allowed_tools": allowed_tools,
        "preferred_tool": preferred_tool,
        "next_task": next_task,
        "blocked_task": blocked_task,
        "blocked_reason": blocked_reason,
        "task_sequence": task_sequence,
    }


def _control_status_dependency_signals(status_payload: dict[str, Any]) -> list[dict[str, Any]]:
    signals: list[dict[str, Any]] = []
    provider = str(status_payload.get("search_provider") or "").strip().lower()
    searx_ok = status_payload.get("searxng_ok")
    if provider == "searxng" and searx_ok is False:
        signals.append({
            "source": "web_search",
            "signal_class": "dependency_unreachable",
            "title": "SearXNG search dependency unreachable",
            "fingerprint": {
                "class": "dependency_unreachable",
                "surface": "web_search",
                "error": "dependency_unreachable",
                "symbol": "searxng",
            },
            "payload": {
                "search_provider": provider,
                "search_api_endpoint": str(status_payload.get("search_api_endpoint") or ""),
                "searxng_note": str(status_payload.get("searxng_note") or ""),
            },
            "severity": "medium",
            "actionability": "safe_now",
            "allowed_tools": ["web_search", "system_check", "read", "find"],
            "preferred_tool": "web_search",
            "next_task": "Probe configured web search route through web_search tool",
            "task_sequence": [
                {
                    "title": "Probe configured web search route through web_search tool",
                    "allowed_tools": ["web_search"],
                    "preferred_tool": "web_search",
                    "tool_args": ["nova runtime search dependency probe"],
                },
                {
                    "title": "Read web search provider implementation",
                    "allowed_tools": ["read"],
                    "preferred_tool": "read",
                    "tool_args": ["services/nova_web_tools.py"],
                },
                {
                    "title": "Read web search policy control surface",
                    "allowed_tools": ["read"],
                    "preferred_tool": "read",
                    "tool_args": ["services/policy_manager.py"],
                },
            ],
        })
    return signals


def _model_runtime_dependency_signals(status_payload: dict[str, Any]) -> list[dict[str, Any]]:
    signals: list[dict[str, Any]] = []
    ollama_health = status_payload.get("ollama_health") if isinstance(status_payload.get("ollama_health"), dict) else {}
    ollama_port_ownership = _port_ownership_for(status_payload, 11434)
    ollama_tags_ok = bool(status_payload.get("ollama_tags_ok", ollama_health.get("tags_ok", True)))
    ollama_chat_route_ok = bool(status_payload.get("ollama_chat_route_ok", ollama_health.get("chat_route_ok", True)))
    ollama_model_available = bool(status_payload.get("ollama_model_available", ollama_health.get("model_available", True)))
    ollama_server_ok = bool(status_payload.get("ollama_server_ok", status_payload.get("ollama_api_up", ollama_health.get("server_ok", True))))
    ollama_version = str(status_payload.get("ollama_version") or ollama_health.get("version") or "").strip()
    ollama_version_ok = bool(status_payload.get("ollama_version_ok", ollama_health.get("version_ok", False)))
    ollama_api_contract_status = str(status_payload.get("ollama_api_contract_status") or ollama_health.get("api_contract_status") or "").strip()
    if "ollama_server_ok" not in status_payload and "server_ok" not in ollama_health and ollama_tags_ok and ollama_chat_route_ok:
        ollama_server_ok = True
    ollama_chat_ready = bool(status_payload.get("ollama_chat_ready", ollama_health.get("ok", ollama_server_ok)))
    if not ollama_server_ok or not ollama_tags_ok or not ollama_chat_route_ok or not ollama_model_available or not ollama_chat_ready:
        if ollama_tags_ok and ollama_chat_route_ok and not ollama_model_available:
            error_symbol = "ollama_chat_model_missing"
            title = "Ollama configured chat model is not installed"
        elif ollama_tags_ok and ollama_chat_route_ok and not ollama_chat_ready:
            error_symbol = "ollama_chat_contract_unready"
            title = "Ollama chat contract is not ready"
        elif ollama_tags_ok and not ollama_chat_route_ok:
            error_symbol = "ollama_chat_route_unreachable"
            title = "Ollama chat API/version contract unavailable while tags endpoint responds"
        elif not ollama_tags_ok:
            error_symbol = "ollama_tags_unreachable"
            title = "Ollama tags endpoint unavailable"
        else:
            error_symbol = "ollama_api_unhealthy"
            title = "Ollama API health contract failed"
        signals.append({
            "source": "model_runtime",
            "signal_class": "dependency_unreachable",
            "title": title,
            "fingerprint": {
                "class": "dependency_unreachable",
                "surface": "model_runtime",
                "error": error_symbol,
                "symbol": "ollama",
            },
            "payload": {
                "ollama_health": dict(ollama_health),
                "ollama_api_up": ollama_server_ok,
                "ollama_server_ok": ollama_server_ok,
                "ollama_chat_ready": ollama_chat_ready,
                "ollama_tags_ok": ollama_tags_ok,
                "ollama_chat_route_ok": ollama_chat_route_ok,
                "ollama_model_available": ollama_model_available,
                "ollama_configured_model": str(status_payload.get("ollama_configured_model") or ollama_health.get("chat_model") or status_payload.get("chat_model") or ""),
                "ollama_model_status": str(status_payload.get("ollama_model_status") or ollama_health.get("model_status") or ""),
                "ollama_available_models": list(status_payload.get("ollama_available_models") or ollama_health.get("available_models") or []),
                "ollama_version": ollama_version,
                "ollama_version_ok": ollama_version_ok,
                "ollama_api_contract_status": ollama_api_contract_status,
                "ollama_health_status": str(status_payload.get("ollama_health_status") or ollama_health.get("status") or ""),
                "ollama_health_info": str(status_payload.get("ollama_health_info") or ollama_health.get("info") or ""),
                "ollama_port_ownership": ollama_port_ownership,
            },
            "severity": "high",
            "actionability": "safe_now",
            "allowed_tools": ["os_capability", "system_check", "read", "find"],
            "preferred_tool": "os_capability",
            "next_task": "Verify Ollama model runtime contract through registered OS capability",
            "task_sequence": _model_runtime_task_sequence(status_payload, ollama_health, probe_chat=True),
        })
    final_answer = str(status_payload.get("last_action_final_answer") or "").strip()
    route_summary = str(status_payload.get("last_route_summary") or "").strip()
    final_answer_low = final_answer.lower()
    if (
        final_answer
        and status_payload.get("action_ledger_ok") is not False
        and "llm_call:started" in route_summary
        and (
            "llm service unavailable" in final_answer_low
            or "ollama chat model missing" in final_answer_low
            or "ollama chat failed" in final_answer_low
            or "ollama chat api unavailable" in final_answer_low
        )
        and ollama_server_ok
        and ollama_tags_ok
        and ollama_chat_route_ok
        and ollama_model_available
    ):
        signals.append({
            "source": "model_runtime",
            "signal_class": "dependency_unreachable",
            "title": "Last LLM reply failed despite healthy Ollama probes",
            "fingerprint": {
                "class": "dependency_unreachable",
                "surface": "action_ledger",
                "error": "llm_reply_failed_after_healthy_probe",
                "symbol": "ollama",
            },
            "payload": {
                "last_action_final_answer": final_answer[:220],
                "last_route_summary": route_summary,
                "last_planner_decision": str(status_payload.get("last_planner_decision") or ""),
                "ollama_health": dict(ollama_health),
                "rationale": "The last reply recorded an LLM failure even though control status probes report the Ollama route and configured model as available.",
            },
            "severity": "high",
            "actionability": "safe_now",
            "allowed_tools": ["os_capability", "read", "find", "system_check"],
            "preferred_tool": "os_capability",
            "next_task": "Verify Ollama model runtime contract through registered OS capability",
            "task_sequence": _model_runtime_task_sequence(
                status_payload,
                ollama_health,
                probe_chat=True,
                include_action_ledger=True,
            ),
        })
    if bool(ollama_port_ownership.get("listening")) and ollama_port_ownership.get("expected_owner_present") is False:
        signals.append({
            "source": "model_runtime",
            "signal_class": "dependency_unreachable",
            "title": "Ollama port is owned by an unexpected process",
            "fingerprint": {
                "class": "dependency_unreachable",
                "surface": "model_runtime",
                "error": "ollama_port_owner_mismatch",
                "symbol": "ollama",
            },
            "payload": {
                "ollama_port_ownership": ollama_port_ownership,
                "rationale": "Port 11434 is listening, but listener ownership does not match the expected Ollama process identity.",
            },
            "severity": "high",
            "actionability": "safe_now",
            "allowed_tools": ["os_capability", "system_check", "read", "find"],
            "preferred_tool": "os_capability",
            "next_task": "Inspect model runtime port ownership through registered OS capability",
            "task_sequence": _model_runtime_task_sequence(
                status_payload,
                ollama_health,
                probe_chat=False,
                inspect_port_first=True,
            ),
        })
    return signals


def _voice_status_signal_from_status(status_payload: dict[str, Any]) -> dict[str, Any] | None:
    voice_status = status_payload.get("voice_status") if isinstance(status_payload.get("voice_status"), dict) else {}
    status_text = str(status_payload.get("voice_runtime_status") or voice_status.get("status") or "").strip().lower()
    requested = bool(status_payload.get("voice_runtime_requested", voice_status.get("requested", voice_status.get("voice_ready", False))))
    ok = bool(status_payload.get("voice_runtime_ok", voice_status.get("ok", False)))
    if not requested or status_text in {"", "not_initialized"}:
        return None
    if ok and status_text in {"ok", "ready", "loaded"}:
        return None

    import_error = str(status_payload.get("voice_import_error") or voice_status.get("import_error") or "").strip()
    sounddevice_loaded = bool(
        status_payload.get(
            "voice_sounddevice_loaded",
            voice_status.get("sounddevice_loaded", voice_status.get("sounddevice_available", False)),
        )
    )
    wav_loaded = bool(status_payload.get("voice_wav_loaded", voice_status.get("wav_loaded", voice_status.get("wav_available", False))))
    whisper_loaded = bool(
        status_payload.get("voice_whisper_loaded", voice_status.get("whisper_loaded", voice_status.get("whisper_available", False)))
    )

    return {
        "source": "voice",
        "signal_class": "dependency_unreachable",
        "title": "Voice runtime dependency unavailable after voice was requested",
        "fingerprint": {
            "class": "dependency_unreachable",
            "surface": "voice",
            "error": "voice_runtime_unavailable",
            "symbol": "voice_runtime",
        },
        "payload": {
            "voice_status": dict(voice_status),
            "voice_runtime_status": status_text,
            "voice_runtime_requested": requested,
            "voice_runtime_ok": ok,
            "voice_import_error": import_error,
            "voice_sounddevice_loaded": sounddevice_loaded,
            "voice_wav_loaded": wav_loaded,
            "voice_whisper_loaded": whisper_loaded,
            "rationale": "Voice entrypoints requested runtime dependencies, but the dependency loader reported voice disabled or incomplete.",
        },
        "severity": "medium",
        "actionability": "safe_now",
        "allowed_tools": ["read", "find", "system_check"],
        "preferred_tool": "read",
        "next_task": VOICE_RUNTIME_READ_TASK_TITLE,
        "task_sequence": [
            {
                "title": VOICE_RUNTIME_READ_TASK_TITLE,
                "allowed_tools": ["read"],
                "preferred_tool": "read",
                "tool_args": ["services/nova_voice_runtime.py"],
            },
            {
                "title": "Find voice runtime usage across Nova entrypoints",
                "allowed_tools": ["find"],
                "preferred_tool": "find",
                "tool_args": ["record_seconds|transcribe|_ensure_voice_deps", "nova_core.py services tests"],
            },
        ],
    }


def _vision_status_signal_from_status(status_payload: dict[str, Any]) -> dict[str, Any] | None:
    vision_status = status_payload.get("vision_status") if isinstance(status_payload.get("vision_status"), dict) else {}
    status_text = str(status_payload.get("vision_runtime_status") or vision_status.get("status") or "").strip().lower()
    requested = bool(status_payload.get("vision_runtime_requested", vision_status.get("requested", False)))
    ok = bool(status_payload.get("vision_runtime_ok", vision_status.get("ok", False)))
    if not requested or status_text in {"", "not_requested"}:
        return None
    if ok and status_text in {"ok", "ready", "loaded"}:
        return None

    missing_modules = [
        str(item or "").strip()
        for item in list(status_payload.get("vision_missing_modules") or vision_status.get("missing_modules") or [])
        if str(item or "").strip()
    ]
    return {
        "source": "vision",
        "signal_class": "dependency_unreachable",
        "title": "Vision runtime dependency unavailable while vision tools are enabled",
        "fingerprint": {
            "class": "dependency_unreachable",
            "surface": "vision",
            "error": "vision_runtime_unavailable",
            "symbol": "vision_runtime",
        },
        "payload": {
            "vision_status": dict(vision_status),
            "vision_runtime_status": status_text,
            "vision_runtime_requested": requested,
            "vision_runtime_ok": ok,
            "vision_missing_modules": missing_modules,
            "vision_screen_requested": bool(status_payload.get("vision_screen_requested", vision_status.get("screen_requested", False))),
            "vision_camera_requested": bool(status_payload.get("vision_camera_requested", vision_status.get("camera_requested", False))),
            "vision_model": str(status_payload.get("vision_model") or vision_status.get("vision_model") or ""),
            "vision_model_available": bool(status_payload.get("vision_model_available", vision_status.get("vision_model_available", True))),
            "rationale": "Screen or camera tools are enabled by policy, but the vision runtime dependency payload reports the stack is incomplete.",
        },
        "severity": "high",
        "actionability": "safe_now",
        "allowed_tools": ["read", "find", "system_check"],
        "preferred_tool": "read",
        "next_task": "Read vision tool dependency wiring and install manifest",
        "task_sequence": [
            {
                "title": "Read vision runtime dependency wiring",
                "allowed_tools": ["read"],
                "preferred_tool": "read",
                "tool_args": ["tools/vision_tool.py"],
            },
            {
                "title": "Read screen and camera helper imports",
                "allowed_tools": ["read"],
                "preferred_tool": "read",
                "tool_args": ["look_crop.py"],
            },
            {
                "title": "Read install requirements for vision dependencies",
                "allowed_tools": ["read"],
                "preferred_tool": "read",
                "tool_args": ["requirements.txt"],
            },
        ],
    }


def _component_running(component: Any) -> bool | None:
    if not isinstance(component, dict):
        return None
    if "running" in component:
        return bool(component.get("running"))
    if "ok" in component:
        return bool(component.get("ok"))
    status = str(component.get("status") or component.get("state") or "").strip().lower()
    if status in {"running", "ok", "healthy", "up", "online"}:
        return True
    if status in {"stopped", "failed", "down", "offline", "missing"}:
        return False
    return None


def _control_status_runtime_signals(status_payload: dict[str, Any]) -> list[dict[str, Any]]:
    signals: list[dict[str, Any]] = []
    guard = status_payload.get("guard") if isinstance(status_payload.get("guard"), dict) else {}
    core = status_payload.get("core") if isinstance(status_payload.get("core"), dict) else {}
    webui = status_payload.get("webui") if isinstance(status_payload.get("webui"), dict) else {}
    heartbeat_age = int(status_payload.get("core_heartbeat_age_sec", status_payload.get("heartbeat_age_sec", 0)) or 0)

    checks = (
        ("guard", guard, "Guard process is not running", "Inspect guard status and runtime timeline"),
        ("core", core, "Core process is not running", "Inspect core status and heartbeat source"),
        ("webui", webui, "HTTP UI process is not running", "Inspect HTTP UI status and restart path"),
    )
    for symbol, component, title, task in checks:
        running = _component_running(component)
        if running is not False:
            continue
        signals.append({
            "source": "runtime_core",
            "signal_class": "runtime_failure",
            "title": title,
            "fingerprint": {
                "class": "runtime_failure",
                "surface": "runtime_core",
                "error": "process_not_running",
                "symbol": symbol,
            },
            "payload": {"component": symbol, "status": dict(component)},
            "severity": "high",
            "actionability": "safe_now",
            "allowed_tools": ["pulse", "read", "find", "system_check"],
            "preferred_tool": "pulse",
            "next_task": task,
        })

    if heartbeat_age > 30:
        signals.append({
            "source": "runtime_core",
            "signal_class": "runtime_failure",
            "title": "Core heartbeat is stale in control status",
            "fingerprint": {
                "class": "runtime_failure",
                "surface": "runtime_core",
                "error": "heartbeat_stale",
                "symbol": "core_heartbeat",
            },
            "payload": {"heartbeat_age_sec": heartbeat_age},
            "severity": "high",
            "actionability": "safe_now",
            "allowed_tools": ["pulse", "read", "find", "system_check"],
            "preferred_tool": "pulse",
            "next_task": "Pulse runtime heartbeat evidence and inspect stale heartbeat source",
        })
    return signals


def _control_status_maintenance_signals(status_payload: dict[str, Any]) -> list[dict[str, Any]]:
    if status_payload.get("maintenance_scheduler_active") is not False:
        return []
    return [{
        "source": "scheduler_registry",
        "signal_class": "maintenance_pressure",
        "title": "Maintenance scheduler is inactive",
        "fingerprint": {
            "class": "maintenance_pressure",
            "surface": "scheduler_registry",
            "error": "maintenance_scheduler_inactive",
            "symbol": "autonomy_maintenance",
        },
        "payload": {
            "maintenance_scheduler_mode": str(status_payload.get("maintenance_scheduler_mode") or ""),
            "maintenance_scheduler_status": str(status_payload.get("maintenance_scheduler_status") or ""),
        },
        "severity": "high",
        "actionability": "safe_now",
        "allowed_tools": ["queue_status", "pulse", "read", "find", "system_check"],
        "preferred_tool": "queue_status",
        "next_task": "Check maintenance scheduler queue and runtime worker state",
        "task_sequence": [
            {
                "title": "Check maintenance scheduler queue and runtime worker state",
                "allowed_tools": ["queue_status"],
                "preferred_tool": "queue_status",
            },
            {
                "title": "Read maintenance schedule registry",
                "allowed_tools": ["read"],
                "preferred_tool": "read",
                "tool_args": ["services/schedule_registry.py"],
            },
            {
                "title": "Read autonomy maintenance worker loop",
                "allowed_tools": ["read"],
                "preferred_tool": "read",
                "tool_args": ["autonomy_maintenance.py"],
            },
        ],
    }]


def _autonomy_maintenance_error_signal_from_status(status_payload: dict[str, Any]) -> dict[str, Any] | None:
    maintenance = status_payload.get("autonomy_maintenance") if isinstance(status_payload.get("autonomy_maintenance"), dict) else {}
    runtime_worker = maintenance.get("runtime_worker") if isinstance(maintenance.get("runtime_worker"), dict) else {}
    last_error = str(maintenance.get("last_error") or "").strip()
    last_error_stale = bool(maintenance.get("last_error_stale", False))
    worker_status = str(status_payload.get("runtime_worker_status") or runtime_worker.get("last_cycle_status") or "").strip().lower()
    worker_stale_identity = bool(status_payload.get("runtime_worker_stale_identity", runtime_worker.get("stale_identity", False)))

    if last_error and not last_error_stale:
        error_symbol = "maintenance_last_error"
        title = "Autonomy maintenance reports a current error"
        severity = "high"
        rationale = "Maintenance state carries a non-stale last_error, so the scheduler needs root-cause evidence before it can be treated as healthy."
    elif worker_stale_identity:
        error_symbol = "maintenance_worker_stale_identity"
        title = "Autonomy maintenance worker identity is stale"
        severity = "high"
        rationale = "Runtime worker identity no longer matches the expected maintenance process."
    elif worker_status in {"failed", "error", "crashed"}:
        error_symbol = "maintenance_worker_cycle_failed"
        title = "Autonomy maintenance worker cycle failed"
        severity = "high"
        rationale = "Runtime worker cycle status reports failure."
    else:
        return None

    return {
        "source": "autonomy_maintenance",
        "signal_class": "maintenance_pressure",
        "title": title,
        "fingerprint": {
            "class": "maintenance_pressure",
            "surface": "autonomy_maintenance",
            "error": error_symbol,
            "symbol": "maintenance_state",
        },
        "payload": {
            "last_error": last_error,
            "last_error_stale": last_error_stale,
            "runtime_worker": dict(runtime_worker),
            "runtime_worker_status": worker_status,
            "runtime_worker_stale_identity": worker_stale_identity,
            "last_generated_at": str(maintenance.get("last_generated_at") or ""),
            "rationale": rationale,
        },
        "severity": severity,
        "actionability": "safe_now",
        "allowed_tools": ["read", "find", "pulse", "system_check"],
        "preferred_tool": "read",
        "next_task": AUTONOMY_MAINTENANCE_LOG_TASK_TITLE,
        "task_sequence": [
            {
                "title": AUTONOMY_MAINTENANCE_LOG_TASK_TITLE,
                "allowed_tools": ["read"],
                "preferred_tool": "read",
                "tool_args": ["runtime/autonomy_maintenance.log"],
            },
            {
                "title": "Read runtime/autonomy_maintenance_state.json current maintenance state",
                "allowed_tools": ["read"],
                "preferred_tool": "read",
                "tool_args": ["runtime/autonomy_maintenance_state.json"],
            },
        ],
    }


def _runtime_failure_reason_signals_from_status(status_payload: dict[str, Any]) -> list[dict[str, Any]]:
    failures = status_payload.get("runtime_failures") if isinstance(status_payload.get("runtime_failures"), dict) else {}
    signals: list[dict[str, Any]] = []
    for service, row in sorted(failures.items()):
        if not isinstance(row, dict):
            continue
        level = str(row.get("level") or "").strip().lower()
        status = str(row.get("status") or "").strip().lower()
        if level in {"", "good", "ok", "info"} and status in {"", "running", "ok", "healthy"}:
            continue
        if level in {"", "good", "ok", "info"}:
            continue
        service_name = str(service or row.get("service") or "runtime").strip().lower()
        label = str(row.get("label") or service_name).strip() or service_name
        signals.append({
            "source": "runtime_control",
            "signal_class": "runtime_failure",
            "title": f"{label} runtime failure reason is active",
            "fingerprint": {
                "class": "runtime_failure",
                "surface": "runtime_control",
                "error": "runtime_failure_reason",
                "symbol": service_name,
            },
            "payload": {
                "service": service_name,
                "failure": dict(row),
                "rationale": "Runtime failure-reason telemetry reports a non-good level for this service.",
            },
            "severity": "high" if level in {"danger", "critical", "failed", "error"} else "medium",
            "actionability": "safe_now",
            "allowed_tools": ["pulse", "read", "find", "system_check"],
            "preferred_tool": "pulse",
            "next_task": "Pulse runtime failure reason and read the matching runtime artifact",
        })
    return signals


def _runtime_restart_signal_from_status(status_payload: dict[str, Any]) -> dict[str, Any] | None:
    analytics = status_payload.get("runtime_restart_analytics") if isinstance(status_payload.get("runtime_restart_analytics"), dict) else {}
    if not analytics:
        return None
    flap_level = str(analytics.get("flap_level") or "").strip().lower()
    consecutive_failures = int(analytics.get("consecutive_failures", 0) or 0)
    recent_15m = int(analytics.get("recent_restart_count_15m", 0) or 0)
    pressure_15m = int(analytics.get("pressure_restart_count_15m", 0) or 0)
    pressure_1h = int(analytics.get("pressure_restart_count_1h", 0) or 0)
    failure_count = int(analytics.get("failure_count", 0) or 0)
    has_pressure_judgment = "restart_pressure_active" in analytics or "pressure_restart_count_15m" in analytics
    if has_pressure_judgment:
        active = bool(
            bool(analytics.get("restart_pressure_active", False))
            or consecutive_failures > 0
            or pressure_15m >= 3
            or pressure_1h >= 3
        )
    else:
        active = bool(
            flap_level in {"warn", "warning", "danger", "critical", "failed", "error"}
            or consecutive_failures > 0
            or recent_15m >= 3
        )
    if not active:
        return None

    return {
        "source": "runtime_control",
        "signal_class": "runtime_failure",
        "title": "Runtime restart pressure is elevated",
        "fingerprint": {
            "class": "runtime_failure",
            "surface": "runtime_control",
            "error": "restart_pressure",
            "symbol": "guard_boot_history",
        },
        "payload": {
            "runtime_restart_analytics": dict(analytics),
            "failure_count": failure_count,
            "consecutive_failures": consecutive_failures,
            "recent_restart_count_15m": recent_15m,
            "pressure_restart_count_15m": pressure_15m,
            "pressure_restart_count_1h": pressure_1h,
            "rationale": "Guard boot history shows failure-driven restart pressure or supervised recovery churn.",
        },
        "severity": "high" if flap_level in {"danger", "critical", "failed", "error"} else "medium",
        "actionability": "safe_now",
        "allowed_tools": ["read", "find", "pulse", "system_check"],
        "preferred_tool": "read",
        "next_task": "Read guard boot history and guard log around recent restart pressure",
        "task_sequence": [
            {
                "title": "Read runtime/guard_boot_history.json restart history",
                "allowed_tools": ["read"],
                "preferred_tool": "read",
                "tool_args": ["runtime/guard_boot_history.json"],
            },
            {
                "title": "Read logs/guard.log recent restart lines",
                "allowed_tools": ["read"],
                "preferred_tool": "read",
                "tool_args": ["logs/guard.log"],
            },
        ],
    }


def _runtime_restart_provenance_signal_from_status(status_payload: dict[str, Any]) -> dict[str, Any] | None:
    analytics = status_payload.get("runtime_restart_analytics") if isinstance(status_payload.get("runtime_restart_analytics"), dict) else {}
    if not analytics:
        return None
    provenance_status = str(analytics.get("restart_provenance_status") or "").strip().lower()
    gap_count = int(analytics.get("restart_origin_gap_count_1h", 0) or 0)
    active_gap_count = int(analytics.get("restart_origin_active_gap_count_1h", gap_count) or 0)
    if provenance_status not in {"incomplete", "gap", "missing"} and active_gap_count <= 0:
        return None

    return {
        "source": "runtime_control",
        "signal_class": "governance_pressure",
        "title": "Runtime restart provenance is incomplete",
        "fingerprint": {
            "class": "governance_pressure",
            "surface": "runtime_control",
            "error": "restart_provenance_gap",
            "symbol": "guard_boot_history",
        },
        "payload": {
            "runtime_restart_analytics": dict(analytics),
            "restart_origin_gap_count_1h": gap_count,
            "restart_origin_active_gap_count_1h": active_gap_count,
            "rationale": "Guard boot history has recent starts without a recorded operator/supervisor origin.",
        },
        "severity": "medium",
        "actionability": "safe_now",
        "allowed_tools": ["read", "find", "pulse", "system_check"],
        "preferred_tool": "read",
        "next_task": "Read guard boot history and guard log to attribute restart origin",
        "task_sequence": [
            {
                "title": "Read runtime/guard_boot_history.json restart provenance",
                "allowed_tools": ["read"],
                "preferred_tool": "read",
                "tool_args": ["runtime/guard_boot_history.json"],
            },
            {
                "title": "Read logs/guard.log around unattributed starts",
                "allowed_tools": ["read"],
                "preferred_tool": "read",
                "tool_args": ["logs/guard.log"],
            },
        ],
    }


def _storage_watch_signal_from_status(status_payload: dict[str, Any]) -> dict[str, Any] | None:
    status = str(status_payload.get("storage_watch_status") or "").strip().lower()
    if not status or status in {"ok", "clear", "normal", "idle"}:
        return None
    return {
        "source": "storage_release_pressure",
        "signal_class": "maintenance_pressure",
        "title": "Runtime storage watch reports pressure",
        "fingerprint": {
            "class": "maintenance_pressure",
            "surface": "storage_release_pressure",
            "error": "storage_watch_pressure",
            "symbol": status,
        },
        "payload": {
            "storage_watch_status": status,
            "storage_watch_note": str(status_payload.get("storage_watch_note") or ""),
            "storage_watch_total_bytes": int(status_payload.get("storage_watch_total_bytes", 0) or 0),
            "storage_watch_watched_total_bytes": int(status_payload.get("storage_watch_watched_total_bytes", 0) or 0),
            "runtime_storage_total_bytes": int(status_payload.get("runtime_storage_total_bytes", 0) or 0),
            "runtime_storage_file_count": int(status_payload.get("runtime_storage_file_count", 0) or 0),
            "patch_snapshot_count": int(status_payload.get("patch_snapshot_count", 0) or 0),
            "kidney_snapshot_count": int(status_payload.get("kidney_snapshot_count", 0) or 0),
            "release_validation_extract_count": int(status_payload.get("release_validation_extract_count", 0) or 0),
            "release_validation_extract_bytes": int(status_payload.get("release_validation_extract_bytes", 0) or 0),
            "release_stage_count": int(status_payload.get("release_stage_count", 0) or 0),
            "release_stage_bytes": int(status_payload.get("release_stage_bytes", 0) or 0),
            "release_zip_count": int(status_payload.get("release_zip_count", 0) or 0),
            "release_zip_bytes": int(status_payload.get("release_zip_bytes", 0) or 0),
            "rationale": "Storage watch is not ok; snapshot, release-stage, validation-extract, or archive growth may be affecting runtime maintenance.",
        },
        "severity": "high" if status in {"failed", "error", "danger"} else "medium",
        "actionability": "safe_now",
        "allowed_tools": ["read", "find", "system_check"],
        "preferred_tool": "system_check",
        "next_task": "Inspect storage watch snapshot and runtime archive growth",
    }


def _temporal_pressure_signal_from_status(status_payload: dict[str, Any]) -> dict[str, Any] | None:
    raw = status_payload.get("temporal_pressure")
    if raw is None:
        raw = status_payload.get("temporal_event") or status_payload.get("temporal_events")

    candidates: list[dict[str, Any]] = []
    if isinstance(raw, list):
        candidates = [dict(item) for item in raw if isinstance(item, dict)]
    elif isinstance(raw, dict):
        nested = raw.get("items") if isinstance(raw.get("items"), list) else None
        if nested:
            candidates = [dict(item) for item in nested if isinstance(item, dict)]
        else:
            candidates = [dict(raw)]
    if not candidates:
        return None

    strongest: dict[str, Any] | None = None
    strongest_score = float("-inf")
    for candidate in candidates:
        event_input = candidate.get("event") if isinstance(candidate.get("event"), dict) else candidate
        pressure_source = event_input if isinstance(event_input, dict) else candidate
        pressure = build_temporal_pressure(pressure_source).to_dict()
        score = float(pressure.get("final_score") or 0.0)
        if score > strongest_score:
            strongest = {"input": candidate, "pressure": pressure}
            strongest_score = score

    if strongest is None:
        return None

    pressure = dict(strongest["pressure"])
    event = pressure.get("event") if isinstance(pressure.get("event"), dict) else {}
    title = str(event.get("title") or strongest["input"].get("title") or "Temporal pressure review").strip()
    score = float(pressure.get("final_score") or 0.0)
    output_path = str(pressure.get("output_path") or "").strip()
    severity = "high" if score >= 75.0 or output_path == "work_tree" else "medium" if score >= 45.0 else "low"
    actionability = "safe_now" if score >= 45.0 else "dead_end"
    start_text = str(event.get("start") or strongest["input"].get("start") or strongest["input"].get("due_at") or "").strip()
    metadata = event.get("metadata") if isinstance(event.get("metadata"), dict) else {}
    uid_text = str(metadata.get("uid") or strongest["input"].get("uid") or "").strip()
    source = str(strongest["input"].get("source") or event.get("source") or "temporal").strip() or "temporal"
    symbol = f"{title}:{start_text or output_path or 'temporal'}"
    if uid_text:
        symbol = f"{symbol}:{uid_text}"
    return {
        "source": source,
        "signal_class": "temporal_pressure",
        "title": title,
        "fingerprint": {
            "class": "temporal_pressure",
            "surface": source,
            "error": "temporal_pressure",
            "symbol": symbol,
        },
        "payload": pressure,
        "severity": severity,
        "actionability": actionability,
        "allowed_tools": ["temporal_review", "read", "find", "queue_status"],
        "preferred_tool": "temporal_review",
        "next_task": f"Review temporal pressure for {title}",
        "task_sequence": [
            {
                "title": f"Review temporal pressure for {title}",
                "allowed_tools": ["temporal_review"],
                "preferred_tool": "temporal_review",
                "tool_args": [json.dumps({"payload": pressure}, ensure_ascii=True)],
            },
            {
                "title": "Read temporal scoring service and calendar ingestion",
                "allowed_tools": ["read"],
                "preferred_tool": "read",
                "tool_args": ["services/nova_temporal_service.py"],
            },
        ],
    }


def _patch_pipeline_signal_from_status(status_payload: dict[str, Any]) -> dict[str, Any] | None:
    patch_enabled = bool(status_payload.get("patch_enabled", False))
    patch_status_ok = bool(status_payload.get("patch_status_ok", True))
    strict_manifest = bool(status_payload.get("patch_strict_manifest", True))
    behavioral_check = bool(status_payload.get("patch_behavioral_check", True))
    tests_available = bool(status_payload.get("patch_tests_available", True))
    pipeline_ready = bool(status_payload.get("patch_pipeline_ready", True))
    cleanup_status = str(status_payload.get("patch_cleanup_status") or "").strip().lower()
    reasons: list[str] = []
    if not patch_status_ok:
        reasons.append("patch_status_not_ok")
    if patch_enabled and not strict_manifest:
        reasons.append("patch_strict_manifest_disabled")
    if patch_enabled and not behavioral_check:
        reasons.append("patch_behavioral_check_disabled")
    if patch_enabled and behavioral_check and not tests_available:
        reasons.append("patch_tests_missing")
    if patch_enabled and not pipeline_ready:
        reasons.append("patch_pipeline_not_ready")
    if cleanup_status and cleanup_status not in {"ok", "idle", "clear"}:
        reasons.append(f"patch_cleanup_{cleanup_status}")
    if not reasons:
        return None

    return {
        "source": "patch_pipeline",
        "signal_class": "governance_pressure",
        "title": "Patch pipeline governance is not ready",
        "fingerprint": {
            "class": "governance_pressure",
            "surface": "patch_pipeline",
            "error": "patch_pipeline_not_ready",
            "symbol": reasons[0],
        },
        "payload": {
            "reasons": reasons,
            "patch_enabled": patch_enabled,
            "patch_status_ok": patch_status_ok,
            "patch_strict_manifest": strict_manifest,
            "patch_behavioral_check": behavioral_check,
            "patch_tests_available": tests_available,
            "patch_pipeline_ready": pipeline_ready,
            "patch_cleanup_status": cleanup_status,
            "patch_previews_total": int(status_payload.get("patch_previews_total", 0) or 0),
            "patch_review_previews_total": int(status_payload.get("patch_review_previews_total", 0) or 0),
            "rationale": "Patch governance is one of Nova's self-change safety surfaces and must be routed before patch execution can be trusted.",
        },
        "severity": "high",
        "actionability": "safe_now",
        "allowed_tools": ["read", "find", "queue_status", "system_check"],
        "preferred_tool": "queue_status",
        "next_task": "Inspect patch pipeline readiness and cleanup state",
    }


def _data_pipeline_signal_from_status(status_payload: dict[str, Any]) -> dict[str, Any] | None:
    if not _has_data_pipeline_surface(status_payload):
        return None
    data_pipelines = status_payload.get("data_pipelines") if isinstance(status_payload.get("data_pipelines"), dict) else {}
    registry_ok = bool(status_payload.get("data_pipeline_registry_ok", data_pipelines.get("ok", True)))
    registry_error = str(status_payload.get("data_pipeline_registry_error") or data_pipelines.get("error") or "").strip()
    pipeline_rows = [
        dict(item)
        for item in list(data_pipelines.get("pipelines") or [])
        if isinstance(item, dict)
    ]
    blocked_rows: list[dict[str, Any]] = []
    for item in pipeline_rows:
        lane_state = item.get("lane_state") if isinstance(item.get("lane_state"), dict) else {}
        if lane_state and not bool(lane_state.get("enabled", True)):
            blocked_rows.append({
                "pipeline_id": str(item.get("pipeline_id") or "").strip(),
                "reason": "lane_paused",
                "lane_state": dict(lane_state),
            })
            continue
        status_text = str(item.get("status") or item.get("state") or "").strip().lower()
        if status_text in {"failed", "error", "blocked"}:
            blocked_rows.append({
                "pipeline_id": str(item.get("pipeline_id") or "").strip(),
                "reason": f"status_{status_text}",
                "summary": dict(item),
            })
    if registry_ok and not blocked_rows:
        return None

    if not registry_ok:
        error_symbol = "data_pipeline_registry_unreadable"
        title = "Data pipeline registry is not readable"
        severity = "high"
    else:
        error_symbol = "data_pipeline_lane_blocked"
        title = "Data pipeline lane is blocked or paused"
        severity = "medium"
    return {
        "source": "data_pipelines",
        "signal_class": "governance_pressure",
        "title": title,
        "fingerprint": {
            "class": "governance_pressure",
            "surface": "data_pipelines",
            "error": error_symbol,
            "symbol": str(blocked_rows[0].get("pipeline_id") if blocked_rows else "registry") or "registry",
        },
        "payload": {
            "data_pipeline_registry_ok": registry_ok,
            "data_pipeline_registry_error": registry_error,
            "data_pipeline_count": int(status_payload.get("data_pipeline_count", len(pipeline_rows)) or 0),
            "data_pipeline_ids": list(status_payload.get("data_pipeline_ids") or []),
            "blocked_pipelines": blocked_rows[:8],
            "rationale": "Data lanes are part of Nova's external-data nervous system and need Work Tree visibility before lane failures are chased individually.",
        },
        "severity": severity,
        "actionability": "safe_now",
        "allowed_tools": ["pipeline", "read", "find", "system_check"],
        "preferred_tool": "pipeline",
        "next_task": "Inspect data pipeline registry and lane status through the pipeline tool",
        "task_sequence": [
            {
                "title": "List registered data pipelines",
                "allowed_tools": ["pipeline"],
                "preferred_tool": "pipeline",
                "tool_args": ["pipeline list"],
            },
            {
                "title": "Read pipeline registry and data source manifests",
                "allowed_tools": ["find"],
                "preferred_tool": "find",
                "tool_args": ["pipeline.json", "data_sources"],
            },
        ],
    }


_BAD_STATUS_WORDS = {
    "blocked",
    "degraded",
    "denied",
    "error",
    "failed",
    "failure",
    "invalid",
    "missing",
    "stale",
    "timeout",
    "unavailable",
    "unhandled",
    "unreadable",
}

_CLEAR_STATUS_WORDS = {
    "",
    "clear",
    "complete",
    "healthy",
    "idle",
    "none",
    "ok",
    "ready",
    "resolved",
    "running",
    "stable",
    "success",
    "valid",
}


def _status_word(value: Any) -> str:
    return str(value or "").strip().lower()


def _status_is_bad(value: Any) -> bool:
    text = _status_word(value)
    return bool(text and text not in _CLEAR_STATUS_WORDS and text in _BAD_STATUS_WORDS)


def _route_trace_issue_steps(trace: Any, *, stage_terms: set[str] | None = None) -> list[dict[str, Any]]:
    if not isinstance(trace, list):
        return []
    terms = {
        str(item or "").strip().lower()
        for item in set(stage_terms or set())
        if str(item or "").strip()
    }
    issues: list[dict[str, Any]] = []
    for raw in trace:
        if not isinstance(raw, dict):
            continue
        stage = _status_word(raw.get("stage"))
        if terms and not any(term in stage for term in terms):
            continue
        outcome = _status_word(raw.get("outcome") or raw.get("status") or raw.get("result"))
        ok_value = raw.get("ok")
        has_error_field = bool(str(raw.get("rule_error") or raw.get("error") or "").strip())
        if ok_value is not False and not has_error_field and not _status_is_bad(outcome):
            continue
        issues.append({
            "stage": stage or "unknown",
            "outcome": outcome or ("error" if has_error_field else "not_ok"),
            "detail": str(raw.get("detail") or raw.get("rule_error") or raw.get("error") or "")[:220],
        })
    return issues[:8]


def _read_source_task(title: str, path: str) -> dict[str, Any]:
    return {
        "title": title,
        "allowed_tools": ["read"],
        "preferred_tool": "read",
        "tool_args": [path],
    }


def _find_source_task(title: str, pattern: str, scope: str = "services tests") -> dict[str, Any]:
    return {
        "title": title,
        "allowed_tools": ["find"],
        "preferred_tool": "find",
        "tool_args": [pattern, scope],
    }


def _task_tools(item: dict[str, Any]) -> set[str]:
    tools = {
        str(tool or "").strip()
        for tool in list(item.get("allowed_tools") or [])
        if str(tool or "").strip()
    }
    preferred = str(item.get("preferred_tool") or "").strip()
    if preferred:
        tools.add(preferred)
    return tools


def _source_root_judgment_task() -> dict[str, Any]:
    return {
        "title": SOURCE_ROOT_JUDGMENT_TASK_TITLE,
        "allowed_tools": [SOURCE_ROOT_JUDGMENT_TOOL],
        "preferred_tool": SOURCE_ROOT_JUDGMENT_TOOL,
    }


def _append_source_root_judgment_task(source: str, signal: dict[str, Any]) -> dict[str, Any]:
    root_id = str(source or "").strip()
    if root_id not in _SOURCE_ROOT_SIGNAL_SOURCES:
        return signal
    next_task = str(signal.get("next_task") or "").strip()
    task_sequence = [
        dict(item)
        for item in list(signal.get("task_sequence") or [])
        if isinstance(item, dict) and str(item.get("title") or "").strip()
    ]
    preferred_tool = str(signal.get("preferred_tool") or "").strip()
    allowed_tools = [
        str(tool or "").strip()
        for tool in list(signal.get("allowed_tools") or [])
        if str(tool or "").strip()
    ]
    sequence_tools = set().union(*(_task_tools(item) for item in task_sequence)) if task_sequence else set()
    if sequence_tools & _SPECIALIZED_SEQUENCE_TOOLS or preferred_tool in _SPECIALIZED_SEQUENCE_TOOLS:
        signal["task_sequence"] = task_sequence
        return signal
    if not task_sequence and next_task and not allowed_tools and not preferred_tool:
        return signal
    if not task_sequence and next_task:
        task_sequence.append({
            "title": next_task,
            "allowed_tools": allowed_tools,
            "preferred_tool": preferred_tool,
        })
    if not task_sequence:
        return signal
    task_sequence.append(_source_root_judgment_task())
    signal["task_sequence"] = task_sequence
    return signal


def _frontdoor_cli_signal_from_status(status_payload: dict[str, Any]) -> dict[str, Any] | None:
    if not _has_frontdoor_cli_surface(status_payload):
        return None
    commands = status_payload.get("backend_commands")
    invalid_commands = "backend_commands" in status_payload and not isinstance(commands, list)
    command_count = _as_int(status_payload.get("backend_command_count"), 0)
    status_text = _status_word(status_payload.get("frontdoor_cli_status"))
    if not invalid_commands and command_count >= 0 and not _status_is_bad(status_text):
        return None
    return {
        "source": "frontdoor_cli",
        "signal_class": "maintenance_pressure",
        "title": "Frontdoor CLI command surface is not readable",
        "fingerprint": {
            "class": "maintenance_pressure",
            "surface": "frontdoor_cli",
            "error": "frontdoor_cli_unreadable",
            "symbol": "backend_commands",
        },
        "payload": {
            "backend_command_count": command_count,
            "frontdoor_cli_status": status_text,
            "backend_commands_type": type(commands).__name__,
            "rationale": "The local command front door has status evidence, but the command surface is malformed or not readable.",
        },
        "severity": "medium",
        "actionability": "safe_now",
        "allowed_tools": ["read", "find", "system_check"],
        "preferred_tool": "read",
        "next_task": "Read frontdoor CLI entrypoints and backend command loading path",
        "task_sequence": [
            _read_source_task("Read Nova PowerShell frontdoor", "nova.ps1"),
            _read_source_task("Read typed CLI entrypoint", "agent.py"),
            _read_source_task("Read run.py dispatch entrypoint", "run.py"),
        ],
    }


def _operator_control_signal_from_status(status_payload: dict[str, Any]) -> dict[str, Any] | None:
    if not _has_operator_control_surface(status_payload):
        return None
    outbox = status_payload.get("operator_outbox") if isinstance(status_payload.get("operator_outbox"), dict) else {}
    open_count = _as_int(status_payload.get("operator_outbox_open_count", outbox.get("open_count", 0)), 0)
    outbox_ok = bool(outbox.get("ok", True))
    if outbox_ok and open_count <= 0:
        return None
    error_symbol = "operator_outbox_open" if open_count > 0 else "operator_outbox_unreadable"
    has_open_work = open_count > 0
    return {
        "source": "operator_control",
        "signal_class": "operator_requested" if has_open_work else "maintenance_pressure",
        "title": "Operator outbox has open operator-control work",
        "fingerprint": {
            "class": "operator_requested" if has_open_work else "maintenance_pressure",
            "surface": "operator_control",
            "error": error_symbol,
            "symbol": "operator_outbox",
        },
        "payload": {
            "operator_outbox_open_count": open_count,
            "operator_outbox_latest_open_id": str(status_payload.get("operator_outbox_latest_open_id") or ""),
            "operator_outbox_status_counts": dict(status_payload.get("operator_outbox_status_counts") or {}),
            "operator_outbox": dict(outbox),
            "rationale": "Operator-control pressure is visible and should stay attached to the Work Tree instead of sitting only in the outbox.",
        },
        "severity": "high" if has_open_work else "medium",
        "actionability": "blocked" if has_open_work else "safe_now",
        "allowed_tools": [] if has_open_work else ["read", "find", "pulse"],
        "preferred_tool": "" if has_open_work else "read",
        "next_task": "" if has_open_work else "Read operator outbox and control-action dispatcher evidence",
        "task_sequence": [] if has_open_work else [
            _read_source_task("Read operator outbox service", "services/operator_outbox.py"),
            _read_source_task("Read control-action dispatcher", "services/nova_control_action_dispatcher.py"),
        ],
        "blocked_task": "Wait for operator response or authority assignment on the open outbox item" if has_open_work else "",
        "blocked_reason": "operator_response_required" if has_open_work else "",
    }


def _policy_gates_signal_from_status(status_payload: dict[str, Any]) -> dict[str, Any] | None:
    if not _has_policy_gates_surface(status_payload):
        return None
    reasons: list[str] = []
    if bool(status_payload.get("web_enabled", False)) and _as_int(status_payload.get("allow_domains_count"), 0) <= 0:
        reasons.append("web_enabled_without_allow_domains")
    if bool(status_payload.get("patch_enabled", False)) and not bool(status_payload.get("patch_strict_manifest", True)):
        reasons.append("patch_strict_manifest_disabled")
    if bool(status_payload.get("patch_enabled", False)) and not bool(status_payload.get("patch_behavioral_check", True)):
        reasons.append("patch_behavioral_check_disabled")
    if (
        bool(status_payload.get("patch_enabled", False))
        and bool(status_payload.get("patch_behavioral_check", True))
        and not bool(status_payload.get("patch_tests_available", True))
    ):
        reasons.append("patch_behavioral_tests_missing")
    if not reasons:
        return None
    return {
        "source": "policy_gates",
        "signal_class": "governance_pressure",
        "title": "Policy gates report an action or observation blocker",
        "fingerprint": {
            "class": "governance_pressure",
            "surface": "policy_gates",
            "error": "policy_gate_blocker",
            "symbol": reasons[0],
        },
        "payload": {
            "reasons": reasons,
            "web_enabled": bool(status_payload.get("web_enabled", False)),
            "allow_domains_count": _as_int(status_payload.get("allow_domains_count"), 0),
            "memory_enabled": bool(status_payload.get("memory_enabled", False)),
            "patch_enabled": bool(status_payload.get("patch_enabled", False)),
            "patch_strict_manifest": bool(status_payload.get("patch_strict_manifest", False)),
            "patch_behavioral_check": bool(status_payload.get("patch_behavioral_check", False)),
            "patch_tests_available": bool(status_payload.get("patch_tests_available", False)),
            "rationale": "Policy state is internally visible and currently blocks a declared capability or observation surface.",
        },
        "severity": "high",
        "actionability": "safe_now",
        "allowed_tools": ["read", "find", "system_check"],
        "preferred_tool": "read",
        "next_task": "Read policy gate configuration and control policy surface",
        "task_sequence": [
            _read_source_task("Read policy configuration", "policy.json"),
            _read_source_task("Read policy manager", "services/policy_manager.py"),
            _read_source_task("Read policy control surface", "services/policy_control.py"),
        ],
    }


def _session_identity_auth_signal_from_status(status_payload: dict[str, Any]) -> dict[str, Any] | None:
    if not _has_session_identity_auth_surface(status_payload):
        return None
    login_enabled = bool(status_payload.get("chat_login_enabled", False))
    users_count = _as_int(status_payload.get("chat_users_count"), 0)
    auth_source = _status_word(status_payload.get("chat_auth_source"))
    reasons: list[str] = []
    if login_enabled and users_count <= 0:
        reasons.append("chat_login_enabled_without_users")
    if login_enabled and auth_source in {"", "missing", "unknown", "none"}:
        reasons.append("chat_auth_source_missing")
    if not reasons:
        return None
    return {
        "source": "session_identity_auth",
        "signal_class": "governance_pressure",
        "title": "Session identity/auth surface is not ready",
        "fingerprint": {
            "class": "governance_pressure",
            "surface": "session_identity_auth",
            "error": "session_identity_auth_gap",
            "symbol": reasons[0],
        },
        "payload": {
            "reasons": reasons,
            "chat_login_enabled": login_enabled,
            "chat_users_count": users_count,
            "chat_auth_source": auth_source,
            "rationale": "Chat identity/auth status is visible, but enabled login lacks the user or auth-source evidence needed for accountable sessions.",
        },
        "severity": "high",
        "actionability": "safe_now",
        "allowed_tools": ["read", "find", "pulse"],
        "preferred_tool": "read",
        "next_task": "Read chat identity and session admin surfaces",
        "task_sequence": [
            _read_source_task("Read chat identity service", "services/chat_identity.py"),
            _read_source_task("Read session admin service", "services/session_admin.py"),
            _read_source_task("Read HTTP session store", "http_session_store.py"),
        ],
    }


def _identity_profile_answers_signal_from_status(status_payload: dict[str, Any]) -> dict[str, Any] | None:
    if not _has_identity_profile_answers_surface(status_payload):
        return None
    memory_health = status_payload.get("memory_health") if isinstance(status_payload.get("memory_health"), dict) else {}
    learned_facts = memory_health.get("learned_facts") if isinstance(memory_health.get("learned_facts"), dict) else {}
    identity = memory_health.get("identity") if isinstance(memory_health.get("identity"), dict) else {}
    memory_enabled = bool(status_payload.get("memory_enabled", memory_health.get("memory_enabled", False)))
    profile_status = _status_word(status_payload.get("identity_profile_status") or status_payload.get("profile_answer_status"))
    has_identity_evidence = isinstance(memory_health.get("identity"), dict)
    has_learned_facts_evidence = isinstance(memory_health.get("learned_facts"), dict)
    missing_profile_parts: list[str] = []
    if memory_enabled and has_identity_evidence and not bool(identity.get("exists", False)):
        missing_profile_parts.append("identity_profile_missing")
    if memory_enabled and has_learned_facts_evidence and not bool(learned_facts.get("exists", False)):
        missing_profile_parts.append("learned_facts_missing")
    if _status_is_bad(profile_status):
        missing_profile_parts.append(profile_status)
    if not missing_profile_parts:
        return None
    return {
        "source": "identity_profile_answers",
        "signal_class": "governance_pressure",
        "title": "Identity profile answer evidence is missing",
        "fingerprint": {
            "class": "governance_pressure",
            "surface": "identity_profile_answers",
            "error": "identity_profile_answer_gap",
            "symbol": missing_profile_parts[0],
        },
        "payload": {
            "missing_profile_parts": missing_profile_parts,
            "memory_enabled": memory_enabled,
            "identity_profile_status": profile_status,
            "memory_health_status": str(status_payload.get("memory_health_status") or memory_health.get("status") or ""),
            "identity": dict(identity),
            "learned_facts": dict(learned_facts),
            "rationale": "Nova can only answer durable identity/profile questions honestly when the identity and learned-facts evidence body exists.",
        },
        "severity": "high",
        "actionability": "safe_now",
        "allowed_tools": ["memory_bootstrap_judgment", "read", "find"],
        "preferred_tool": "memory_bootstrap_judgment",
        "next_task": "Synthesize identity profile answer judgment from memory evidence",
        "task_sequence": [
            _read_source_task("Read memory routing purpose controls", "services/memory_routing.py"),
            _read_source_task("Read memory identity bootstrap service", "services/memory_identity_bootstrap.py"),
            {
                "title": "Synthesize identity profile answer judgment from memory evidence",
                "allowed_tools": ["memory_bootstrap_judgment"],
                "preferred_tool": "memory_bootstrap_judgment",
            },
        ],
    }


def _conversation_routing_signal_from_status(status_payload: dict[str, Any]) -> dict[str, Any] | None:
    if not _has_conversation_routing_surface(status_payload):
        return None
    route_trace = status_payload.get("last_route_trace")
    issue_steps = _route_trace_issue_steps(route_trace, stage_terms={"intent", "planner", "route", "router", "action_planner"})
    planner_decision = str(status_payload.get("last_planner_decision") or "").strip()
    action_ledger_total = _as_int(status_payload.get("action_ledger_total"), 0)
    route_summary = str(status_payload.get("last_route_summary") or "").strip()
    missing_decision = action_ledger_total > 0 and not planner_decision
    missing_route = action_ledger_total > 0 and not route_summary
    if not issue_steps and not missing_decision and not missing_route:
        return None
    symbol = "route_trace_issue"
    if missing_decision:
        symbol = "planner_decision_missing"
    elif missing_route:
        symbol = "route_summary_missing"
    return {
        "source": "conversation_routing",
        "signal_class": "governance_pressure",
        "title": "Conversation routing evidence is incomplete or not clean",
        "fingerprint": {
            "class": "governance_pressure",
            "surface": "conversation_routing",
            "error": "conversation_routing_evidence_gap",
            "symbol": symbol,
        },
        "payload": {
            "planner_decision": planner_decision,
            "last_intent": str(status_payload.get("last_intent") or ""),
            "last_route_summary": route_summary,
            "issue_steps": issue_steps,
            "missing_planner_decision": missing_decision,
            "missing_route_summary": missing_route,
            "rationale": "The last action ledger record has routing evidence, but the routing trace is incomplete or contains a structural failure state.",
        },
        "severity": "high" if missing_decision or missing_route else "medium",
        "actionability": "safe_now",
        "allowed_tools": ["read", "find", "pulse"],
        "preferred_tool": "read",
        "next_task": "Read routing support and planner contract for the current route gap",
        "task_sequence": [
            _read_source_task("Read semantic routing support", "services/nova_routing_support.py"),
            _read_source_task("Read planner contract", "services/nova_planner_contract.py"),
            _find_source_task("Find current route trace writer and ledger finalizer", "route_trace|planner_decision|finalize", "services nova_core.py nova_http.py"),
        ],
    }


def _supervisor_fulfillment_signal_from_status(status_payload: dict[str, Any]) -> dict[str, Any] | None:
    if not _has_supervisor_fulfillment_surface(status_payload):
        return None
    issue_steps = _route_trace_issue_steps(
        status_payload.get("last_route_trace"),
        stage_terms={"supervisor", "fulfillment"},
    )
    planner_decision = str(status_payload.get("last_planner_decision") or "").strip().lower()
    grounded = bool(status_payload.get("last_route_grounded", True))
    active_ungrounded = planner_decision.startswith("fulfillment") and not grounded
    if not issue_steps and not active_ungrounded:
        return None
    return {
        "source": "supervisor_fulfillment",
        "signal_class": "governance_pressure",
        "title": "Supervisor/fulfillment handoff is not clean",
        "fingerprint": {
            "class": "governance_pressure",
            "surface": "supervisor_fulfillment",
            "error": "supervisor_fulfillment_route_gap",
            "symbol": "fulfillment_route",
        },
        "payload": {
            "last_planner_decision": planner_decision,
            "last_route_grounded": grounded,
            "issue_steps": issue_steps,
            "rationale": "Supervisor or fulfillment stages are visible in the route trace and report a structural handoff failure.",
        },
        "severity": "medium",
        "actionability": "safe_now",
        "allowed_tools": ["read", "find", "pulse"],
        "preferred_tool": "read",
        "next_task": "Read supervisor and fulfillment handoff code",
        "task_sequence": [
            _read_source_task("Read supervisor registry", "services/supervisor_registry.py"),
            _read_source_task("Read fulfillment flow", "services/fulfillment_flow.py"),
            _read_source_task("Read fulfillment routing bridge", "services/nova_fulfillment_routing.py"),
        ],
    }


def _reply_quality_contracts_signal_from_status(status_payload: dict[str, Any]) -> dict[str, Any] | None:
    if not _has_reply_quality_contracts_surface(status_payload):
        return None
    trace = status_payload.get("last_route_trace")
    issue_steps = _route_trace_issue_steps(trace, stage_terms={"reply", "finalize", "delivery"})
    has_finalize = any(isinstance(item, dict) and _status_word(item.get("stage")) == "finalize" for item in list(trace or []))
    final_answer_present = bool(str(status_payload.get("last_action_final_answer") or "").strip())
    if not issue_steps and (not has_finalize or final_answer_present):
        return None
    symbol = "final_answer_missing" if has_finalize and not final_answer_present else "reply_trace_issue"
    return {
        "source": "reply_quality_contracts",
        "signal_class": "governance_pressure",
        "title": "Reply quality contract evidence is incomplete",
        "fingerprint": {
            "class": "governance_pressure",
            "surface": "reply_quality_contracts",
            "error": "reply_quality_contract_gap",
            "symbol": symbol,
        },
        "payload": {
            "has_finalize_step": has_finalize,
            "final_answer_present": final_answer_present,
            "last_route_grounded": bool(status_payload.get("last_route_grounded", False)),
            "issue_steps": issue_steps,
            "rationale": "The final reply delivery path should leave structural evidence of a final answer and clean finalization.",
        },
        "severity": "medium",
        "actionability": "safe_now",
        "allowed_tools": ["read", "find", "pulse"],
        "preferred_tool": "read",
        "next_task": "Read reply runtime and finalization contract",
        "task_sequence": [
            _read_source_task("Read reply runtime effects", "services/nova_reply_runtime.py"),
            _read_source_task("Read HTTP turn finalization", "services/nova_http_turn_finalization.py"),
            _find_source_task("Find reply contract and final answer writers", "reply_contract|final_answer|reply_outcome", "services nova_core.py nova_http.py"),
        ],
    }


def _retrieval_knowledge_signal_from_status(status_payload: dict[str, Any]) -> dict[str, Any] | None:
    if not _has_retrieval_knowledge_surface(status_payload):
        return None
    retrieval_status = _status_word(status_payload.get("retrieval_knowledge_status") or status_payload.get("knowledge_pack_status"))
    knowledge_used = status_payload.get("knowledge_used")
    knowledge_chars = _as_int(status_payload.get("knowledge_chars"), 0)
    explicit_bad_status = _status_is_bad(retrieval_status)
    empty_used_context = knowledge_used is True and knowledge_chars <= 0
    if not explicit_bad_status and not empty_used_context:
        return None
    return {
        "source": "retrieval_knowledge",
        "signal_class": "maintenance_pressure",
        "title": "Retrieval/knowledge evidence is not usable",
        "fingerprint": {
            "class": "maintenance_pressure",
            "surface": "retrieval_knowledge",
            "error": "retrieval_knowledge_gap",
            "symbol": retrieval_status or "knowledge_context",
        },
        "payload": {
            "retrieval_knowledge_status": retrieval_status,
            "knowledge_used": bool(knowledge_used),
            "knowledge_chars": knowledge_chars,
            "knowledge_active_pack": str(status_payload.get("knowledge_active_pack") or ""),
            "rationale": "Local retrieval reported use or status evidence, but the retrieved context payload is empty or structurally unhealthy.",
        },
        "severity": "medium",
        "actionability": "safe_now",
        "allowed_tools": ["read", "find", "web_search"],
        "preferred_tool": "read",
        "next_task": "Read local knowledge pack retrieval implementation",
        "task_sequence": [
            _read_source_task("Read knowledge pack retrieval service", "services/nova_knowledge_packs.py"),
            _find_source_task("Find knowledge context writers", "knowledge_used|knowledge_chars|kb_search", "services nova_core.py tests"),
        ],
    }


def _weather_location_signal_from_status(status_payload: dict[str, Any]) -> dict[str, Any] | None:
    if not _has_weather_location_surface(status_payload):
        return None
    weather_source = str(status_payload.get("weather_source_host") or "").strip()
    web_enabled = bool(status_payload.get("web_enabled", False))
    issue_steps = _route_trace_issue_steps(status_payload.get("last_route_trace"), stage_terms={"weather", "location"})
    action_tool = str(status_payload.get("last_action_tool") or "").strip()
    weather_tool_selected = action_tool in {"weather_current_location", "weather_location", "location_coords"}
    source_missing = weather_tool_selected and web_enabled and not weather_source and "weather_source_host" in status_payload
    if not issue_steps and not source_missing:
        return None
    return {
        "source": "weather_location",
        "signal_class": "dependency_unreachable",
        "title": "Weather/location route lacks usable source evidence",
        "fingerprint": {
            "class": "dependency_unreachable",
            "surface": "weather_location",
            "error": "weather_location_source_gap",
            "symbol": action_tool or "weather_location",
        },
        "payload": {
            "last_action_tool": action_tool,
            "weather_source_host": weather_source,
            "web_enabled": web_enabled,
            "live_tracking": dict(status_payload.get("live_tracking") or {}) if isinstance(status_payload.get("live_tracking"), dict) else {},
            "issue_steps": issue_steps,
            "rationale": "Weather/location tooling was selected or reported route issues without a usable weather/location evidence source.",
        },
        "severity": "medium",
        "actionability": "safe_now",
        "allowed_tools": ["weather_current_location", "weather_location", "location_coords", "read", "find"],
        "preferred_tool": "weather_current_location" if action_tool != "location_coords" else "location_coords",
        "next_task": "Probe weather/location route using the registered weather tool",
        "task_sequence": [
            {
                "title": "Probe current weather/location route through registered tool",
                "allowed_tools": ["weather_current_location"],
                "preferred_tool": "weather_current_location",
            },
            _read_source_task("Read weather/location implementation", "services/nova_location_weather.py"),
        ],
    }


def _installer_packaging_signal_from_status(status_payload: dict[str, Any]) -> dict[str, Any] | None:
    if not _has_installer_packaging_surface(status_payload):
        return None
    installer_release = status_payload.get("installer_release_status") if isinstance(status_payload.get("installer_release_status"), dict) else {}
    installer_status = _status_word(
        status_payload.get("installer_status")
        or status_payload.get("installer_packaging_status")
        or installer_release.get("latest_readiness_state")
    )
    release = status_payload.get("release_status") if isinstance(status_payload.get("release_status"), dict) else {}
    readiness = _status_word(release.get("latest_readiness_state"))
    release_ready = bool(release.get("latest_ready_to_ship", False))
    installer_ready = bool(installer_release.get("latest_ready_to_ship", False))
    release_artifact_path = str(release.get("latest_artifact_path") or "").strip()
    installer_source_package_path = str(installer_release.get("latest_source_package_artifact_path") or "").strip()
    installer_matches_current_release = bool(
        installer_ready
        and release_ready
        and _same_artifact_path(installer_source_package_path, release_artifact_path)
    )
    installer_provenance_gap = bool(release_ready and installer_ready and not installer_matches_current_release)
    if installer_ready and installer_status in {"ready", "ready-with-notes"} and not installer_provenance_gap:
        return None
    stale_after_release = release_ready and (
        installer_provenance_gap
        or installer_status in {"", "missing", "stale", "unverified", "no-builds", "needs-verification", "needs-promotion"}
    )
    if not _status_is_bad(installer_status) and not stale_after_release:
        return None
    return {
        "source": "installer_packaging",
        "signal_class": "release_readiness_gap",
        "title": "Installer package readiness is not verified against release truth",
        "fingerprint": {
            "class": "release_readiness_gap",
            "surface": "installer_packaging",
            "error": "installer_packaging_gap",
            "symbol": str(release.get("latest_artifact_name") or "") or installer_status or readiness or "installer",
        },
        "payload": {
            "installer_status": installer_status,
            "installer_release_status": dict(installer_release),
            "release_readiness_state": readiness,
            "release_ready_to_ship": release_ready,
            "latest_artifact_name": str(release.get("latest_artifact_name") or ""),
            "latest_artifact_path": release_artifact_path,
            "installer_source_package_artifact_path": installer_source_package_path,
            "installer_matches_current_release": installer_matches_current_release,
            "rationale": "Installer packaging is a release root; when release truth is ready, installer verification must have matching evidence before packaging is considered closed.",
        },
        "severity": "medium",
        "actionability": "safe_now",
        "allowed_tools": ["read", "find", "system_check", "installer_validation_run", SOURCE_ROOT_JUDGMENT_TOOL],
        "preferred_tool": "installer_validation_run",
        "next_task": "Run installer validation from current release package",
        "task_sequence": [
            _read_source_task("Read Windows installer build script", "scripts/build_windows_installer.ps1"),
            _read_source_task("Read Windows installer verification script", "scripts/verify_windows_installer.ps1"),
            _read_source_task("Read installer plan", "docs/WINDOWS_INSTALLER_PLAN.md"),
            {
                "title": "Run installer validation from current release package",
                "allowed_tools": ["installer_validation_run"],
                "preferred_tool": "installer_validation_run",
            },
            _source_root_judgment_task(),
        ],
    }


def _tts_audio_output_signal_from_status(status_payload: dict[str, Any]) -> dict[str, Any] | None:
    if not _has_tts_audio_output_surface(status_payload):
        return None
    tts_status = _status_word(status_payload.get("tts_status") or status_payload.get("tts_audio_status"))
    voice_status = status_payload.get("voice_status") if isinstance(status_payload.get("voice_status"), dict) else {}
    voice_requested = bool(status_payload.get("voice_runtime_requested", voice_status.get("requested", False)))
    voice_ok = bool(status_payload.get("voice_runtime_ok", voice_status.get("ok", not voice_requested)))
    tts_issue = _status_is_bad(tts_status) or (voice_requested and voice_ok and tts_status in {"missing", "unavailable", "failed", "error"})
    if not tts_issue:
        return None
    return {
        "source": "tts_audio_output",
        "signal_class": "dependency_unreachable",
        "title": "TTS audio output surface is unavailable",
        "fingerprint": {
            "class": "dependency_unreachable",
            "surface": "tts_audio_output",
            "error": "tts_audio_unavailable",
            "symbol": tts_status or "tts_runtime",
        },
        "payload": {
            "tts_status": tts_status,
            "voice_runtime_requested": voice_requested,
            "voice_runtime_ok": voice_ok,
            "voice_status": dict(voice_status),
            "rationale": "Spoken output is a separate delivery root and needs its own TTS evidence when voice delivery is requested.",
        },
        "severity": "medium",
        "actionability": "safe_now",
        "allowed_tools": ["read", "find", "system_check"],
        "preferred_tool": "read",
        "next_task": "Read TTS output bridge and Piper fallback",
        "task_sequence": [
            _read_source_task("Read TTS process wrapper", "tts_say.py"),
            _read_source_task("Read Piper TTS bridge", "tts_piper.py"),
            _read_source_task("Read TTS PowerShell bridge", "tts_say.ps1"),
        ],
    }


def _safety_envelope_signal_from_status(status_payload: dict[str, Any]) -> dict[str, Any] | None:
    if not _has_safety_envelope_surface(status_payload):
        return None
    pulse = status_payload.get("pulse") if isinstance(status_payload.get("pulse"), dict) else {}
    safety_enabled = bool(status_payload.get("safety_enabled", pulse.get("safety_enabled", True)))
    safety_mode = _status_word(status_payload.get("safety_mode") or pulse.get("safety_mode"))
    pending_review = _as_int(status_payload.get("pending_review_total", pulse.get("pending_review_total", 0)), 0)
    quarantine = _as_int(status_payload.get("quarantine_total", pulse.get("quarantine_total", 0)), 0)
    status_bad = _status_is_bad(status_payload.get("safety_envelope_status"))
    review_pressure = safety_enabled and (pending_review > 0 or quarantine > 0) and safety_mode not in {"off", "disabled"}
    if not status_bad and not review_pressure:
        return None
    return {
        "source": "safety_envelope",
        "signal_class": "governance_pressure",
        "title": "Safety envelope has pending review or quarantine pressure",
        "fingerprint": {
            "class": "governance_pressure",
            "surface": "safety_envelope",
            "error": "safety_envelope_review_pressure",
            "symbol": "pending_review" if pending_review > 0 else ("quarantine" if quarantine > 0 else safety_mode or "safety_envelope"),
        },
        "payload": {
            "safety_enabled": safety_enabled,
            "safety_mode": safety_mode,
            "pending_review_total": pending_review,
            "quarantine_total": quarantine,
            "generated_total": _as_int(status_payload.get("generated_total", pulse.get("generated_total", 0)), 0),
            "promoted_total": _as_int(status_payload.get("promoted_total", pulse.get("promoted_total", 0)), 0),
            "rationale": "Generated-session promotion safety has pending or quarantined evidence that needs review before learning pressure is treated as settled.",
        },
        "severity": "medium",
        "actionability": "safe_now",
        "allowed_tools": ["phase2_audit", "read", "find"],
        "preferred_tool": "phase2_audit",
        "next_task": "Run safety-envelope audit and read promotion evidence",
        "task_sequence": [
            {
                "title": "Run safety-envelope audit",
                "allowed_tools": ["phase2_audit"],
                "preferred_tool": "phase2_audit",
            },
            _read_source_task("Read safety envelope implementation", "nova_safety_envelope.py"),
        ],
    }


def _metrics_ops_journal_signal_from_status(status_payload: dict[str, Any]) -> dict[str, Any] | None:
    if not _has_metrics_ops_journal_surface(status_payload):
        return None
    requests_total = _as_int(status_payload.get("requests_total"), 0)
    errors_total = _as_int(status_payload.get("errors_total"), 0)
    journal_status = _status_word(status_payload.get("ops_journal_status") or status_payload.get("metrics_ops_journal_status"))
    impossible_counts = errors_total > requests_total and requests_total >= 0
    if not impossible_counts and not _status_is_bad(journal_status):
        return None
    return {
        "source": "metrics_ops_journal",
        "signal_class": "maintenance_pressure",
        "title": "Metrics/ops journal telemetry is inconsistent",
        "fingerprint": {
            "class": "maintenance_pressure",
            "surface": "metrics_ops_journal",
            "error": "metrics_ops_journal_gap",
            "symbol": "error_count_gt_request_count" if impossible_counts else journal_status or "ops_journal",
        },
        "payload": {
            "requests_total": requests_total,
            "errors_total": errors_total,
            "tool_events_total": _as_int(status_payload.get("tool_events_total"), 0),
            "ops_journal_status": journal_status,
            "rationale": "Operator-visible telemetry must remain numerically coherent and journal evidence must be readable.",
        },
        "severity": "medium",
        "actionability": "safe_now",
        "allowed_tools": ["read", "find", "pulse"],
        "preferred_tool": "read",
        "next_task": "Read behavior metrics and ops journal telemetry writers",
        "task_sequence": [
            _read_source_task("Read behavior metrics store", "services/behavior_metrics.py"),
            _read_source_task("Read ops journal writer", "services/ops_journal.py"),
            _read_source_task("Read control telemetry summaries", "services/control_telemetry.py"),
        ],
    }


def _core_steward_reflection_signal_from_status(status_payload: dict[str, Any]) -> dict[str, Any] | None:
    if not _has_core_steward_reflection_surface(status_payload):
        return None
    health_score = _as_int(status_payload.get("health_score"), 100)
    pulse = status_payload.get("pulse") if isinstance(status_payload.get("pulse"), dict) else {}
    pulse_missing = "pulse" in status_payload and not pulse
    core_steward_status = _status_word(status_payload.get("core_steward_status") or status_payload.get("core_health_brief_status"))
    fallback_pressure = float(pulse.get("active_fallback_overuse_score", 0.0) or 0.0) if pulse else 0.0
    if health_score >= 90 and not pulse_missing and not _status_is_bad(core_steward_status) and fallback_pressure < 0.75:
        return None
    return {
        "source": "core_steward_reflection",
        "signal_class": "governance_pressure",
        "title": "Core steward reflection reports repair or watch pressure",
        "fingerprint": {
            "class": "governance_pressure",
            "surface": "core_steward_reflection",
            "error": "core_steward_reflection_pressure",
            "symbol": core_steward_status or ("pulse_missing" if pulse_missing else "health_score"),
        },
        "payload": {
            "health_score": health_score,
            "pulse_missing": pulse_missing,
            "core_steward_status": core_steward_status,
            "active_fallback_overuse_score": fallback_pressure,
            "pulse_summary": dict(status_payload.get("pulse_summary") or {}) if isinstance(status_payload.get("pulse_summary"), dict) else {},
            "rationale": "Core steward reflection is the root that turns health and pulse evidence into repair/watch pressure.",
        },
        "severity": "high" if health_score < 75 else "medium",
        "actionability": "safe_now",
        "allowed_tools": ["core_health", "core_thinning", "pulse", "read", "find"],
        "preferred_tool": "core_health",
        "next_task": "Build core health brief from steward and pulse evidence",
        "task_sequence": [
            {
                "title": "Build core health brief from steward and pulse evidence",
                "allowed_tools": ["core_health"],
                "preferred_tool": "core_health",
            },
            _read_source_task("Read core steward service", "services/core_steward.py"),
            _read_source_task("Read core health brief service", "services/core_health_brief.py"),
        ],
    }


def _wiring_inventory_signal_from_status(status_payload: dict[str, Any]) -> dict[str, Any] | None:
    inventory = (
        status_payload.get("wiring_inventory")
        if isinstance(status_payload.get("wiring_inventory"), dict)
        else build_wiring_inventory_payload(status_payload)
    )
    gap_count = int(inventory.get("gap_count", 0) or 0)
    if gap_count <= 0:
        return None
    missing_status = list(inventory.get("missing_status_surfaces") or [])
    missing_signals = list(inventory.get("missing_signal_surfaces") or [])
    missing_tools = list(inventory.get("missing_tool_surfaces") or [])
    missing_actions = list(inventory.get("missing_action_surfaces") or [])
    first_gap = (
        (missing_status + missing_signals + missing_tools + missing_actions)
        or ["wiring_inventory"]
    )[0]
    return {
        "source": "work_tree",
        "signal_class": "governance_pressure",
        "title": "Subsystem wiring inventory has uncovered coverage gaps",
        "fingerprint": {
            "class": "governance_pressure",
            "surface": "work_tree",
            "error": "wiring_inventory_gap",
            "symbol": first_gap,
        },
        "payload": {
            "wiring_inventory": dict(inventory),
            "gap_count": gap_count,
            "missing_status_surfaces": missing_status,
            "missing_signal_surfaces": missing_signals,
            "missing_tool_surfaces": missing_tools,
            "missing_action_surfaces": missing_actions,
            "rationale": "Nova should wire every subsystem into status, Signal Intake, executable tools, and advisory action vocabulary before individual failures are interpreted.",
        },
        "severity": "high",
        "actionability": "safe_now",
        "allowed_tools": ["read", "find", "pulse", "system_check"],
        "preferred_tool": "read",
        "next_task": "Read central wiring inventory and Signal Intake coverage map",
        "task_sequence": [
            {
                "title": "Read central subsystem wiring inventory",
                "allowed_tools": ["read"],
                "preferred_tool": "read",
                "tool_args": ["services/nova_wiring_inventory.py"],
            },
            {
                "title": "Read Signal Intake source ingestion coverage",
                "allowed_tools": ["read"],
                "preferred_tool": "read",
                "tool_args": ["services/work_tree_signal_ingestion.py"],
            },
            {
                "title": "Find planned tool catalog and advisory action catalog",
                "allowed_tools": ["find"],
                "preferred_tool": "find",
                "tool_args": ["_PLANNED_TOOL_NAMES|AUTONOMY_ADVISORY_ACTION_CATALOG|_DEFAULT_TREE_ALLOWED_TOOLS", "."],
            },
        ],
    }


def _source_root_inventory_signal_from_status(status_payload: dict[str, Any]) -> dict[str, Any] | None:
    inventory = status_payload.get("source_root_inventory") if isinstance(status_payload.get("source_root_inventory"), dict) else {}
    if not inventory:
        return None
    gap_count = int(status_payload.get("source_root_inventory_gap_count", inventory.get("gap_count", 0)) or 0)
    if gap_count <= 0 and bool(status_payload.get("source_root_inventory_ok", inventory.get("ok", True))):
        return None
    unwired_roots = [
        str(item or "").strip()
        for item in list(status_payload.get("source_root_inventory_unwired_roots", inventory.get("unwired_roots", [])) or [])
        if str(item or "").strip()
    ]
    missing_evidence_roots = [
        str(item or "").strip()
        for item in list(
            status_payload.get(
                "source_root_inventory_missing_evidence_roots",
                inventory.get("missing_evidence_roots", []),
            )
            or []
        )
        if str(item or "").strip()
    ]
    unclassified_source_files = [
        str(item or "").strip()
        for item in list(inventory.get("unclassified_source_files") or [])
        if str(item or "").strip()
    ]
    first_gap = (unwired_roots + missing_evidence_roots + unclassified_source_files or ["source_root_inventory"])[0]
    return {
        "source": "source_root_inventory",
        "signal_class": "governance_pressure",
        "title": "Source root inventory has uncovered unwired roots or files",
        "fingerprint": {
            "class": "governance_pressure",
            "surface": "source_root_inventory",
            "error": "source_root_inventory_gap",
            "symbol": first_gap,
        },
        "payload": {
            "source_root_inventory": dict(inventory),
            "gap_count": gap_count,
            "unwired_roots": unwired_roots,
            "missing_evidence_roots": missing_evidence_roots,
            "unclassified_source_file_count": int(inventory.get("unclassified_source_file_count", len(unclassified_source_files)) or 0),
            "unclassified_source_files": unclassified_source_files[:24],
            "rationale": "Nova discovered source roots or code files that are not represented as first-class wiring surfaces.",
        },
        "severity": "high",
        "actionability": "safe_now",
        "allowed_tools": ["read", "find", "pulse", "system_check"],
        "preferred_tool": "read",
        "next_task": "Read source root inventory and compare every discovered root to wiring surfaces",
        "task_sequence": [
            {
                "title": "Read source root inventory catalog",
                "allowed_tools": ["read"],
                "preferred_tool": "read",
                "tool_args": ["services/nova_root_inventory.py"],
            },
            {
                "title": "Read central subsystem wiring inventory",
                "allowed_tools": ["read"],
                "preferred_tool": "read",
                "tool_args": ["services/nova_wiring_inventory.py"],
            },
            {
                "title": "Find missing source root wiring references",
                "allowed_tools": ["find"],
                "preferred_tool": "find",
                "tool_args": [first_gap, "."],
            },
        ],
    }


def _source_wiring_probe_signal_from_status(status_payload: dict[str, Any]) -> dict[str, Any] | None:
    probe = status_payload.get("source_wiring_probe") if isinstance(status_payload.get("source_wiring_probe"), dict) else {}
    gap_count = int(status_payload.get("source_wiring_probe_gap_count", probe.get("gap_count", 0)) or 0)
    if gap_count <= 0 and bool(status_payload.get("source_wiring_probe_ok", probe.get("ok", True))):
        return None

    gap_fields = (
        "missing_signal_sources",
        "missing_planned_tools",
        "missing_advisory_actions",
        "planned_tools_without_execution",
        "advisory_actions_without_execution",
        "missing_required_evidence_paths",
        "missing_required_judgment_paths",
        "missing_required_closure_paths",
        "missing_required_operator_outbox_paths",
        "missing_required_owned_root_routes",
    )
    gaps_by_field: dict[str, list[str]] = {}
    ordered_gaps: list[str] = []
    for field in gap_fields:
        values = [
            str(item or "").strip()
            for item in list(status_payload.get(f"source_wiring_probe_{field}", probe.get(field, [])) or [])
            if str(item or "").strip()
        ]
        gaps_by_field[field] = values
        ordered_gaps.extend(f"{field}:{value}" for value in values)
    first_gap = ordered_gaps[0] if ordered_gaps else "source_wiring_probe"

    return {
        "source": "source_wiring_probe",
        "signal_class": "governance_pressure",
        "title": "Source wiring probe found missing source-derived paths",
        "fingerprint": {
            "class": "governance_pressure",
            "surface": "source_wiring_probe",
            "error": "source_wiring_probe_gap",
            "symbol": first_gap,
        },
        "payload": {
            "source_wiring_probe": dict(probe),
            "gap_count": gap_count,
            **gaps_by_field,
            "rationale": (
                "The source-derived wiring probe must verify signal sources, planned tools, execution paths, "
                "evidence, judgment, closure, and operator outbox paths before root closure can be trusted."
            ),
        },
        "severity": "high",
        "actionability": "safe_now",
        "allowed_tools": ["read", "find", "pulse", "system_check"],
        "preferred_tool": "read",
        "next_task": "Read source wiring probe and verify the missing source-derived path",
        "task_sequence": [
            {
                "title": "Read central source wiring probe",
                "allowed_tools": ["read"],
                "preferred_tool": "read",
                "tool_args": ["services/nova_wiring_inventory.py"],
            },
            {
                "title": "Read Signal Intake source path detection",
                "allowed_tools": ["read"],
                "preferred_tool": "read",
                "tool_args": ["services/work_tree_signal_ingestion.py"],
            },
            {
                "title": "Find missing source-derived wiring path",
                "allowed_tools": ["find"],
                "preferred_tool": "find",
                "tool_args": [first_gap, "."],
            },
        ],
    }


def _root_closure_inventory_signals_from_status(status_payload: dict[str, Any]) -> list[dict[str, Any]]:
    inventory = (
        status_payload.get("root_closure_inventory")
        if isinstance(status_payload.get("root_closure_inventory"), dict)
        else build_root_closure_inventory_payload(status_payload)
    )
    if int(inventory.get("gap_count", 0) or 0) <= 0:
        return []

    signals: list[dict[str, Any]] = []
    for row in list(inventory.get("roots") or []):
        if not isinstance(row, dict) or bool(row.get("ok", False)):
            continue
        root_id = str(row.get("root_id") or "").strip()
        if not root_id:
            continue
        gaps = [str(item or "").strip() for item in list(row.get("gaps") or []) if str(item or "").strip()]
        source_files = [str(item or "").strip() for item in list(row.get("source_files") or []) if str(item or "").strip()]
        first_source_file = source_files[0] if source_files else "services/nova_root_inventory.py"
        missing_status = [
            str(item or "").strip()
            for item in list(row.get("missing_status_keys") or [])
            if str(item or "").strip()
        ]
        missing_signals = [
            str(item or "").strip()
            for item in list(row.get("missing_signal_sources") or [])
            if str(item or "").strip()
        ]
        missing_tools = [
            str(item or "").strip()
            for item in list(row.get("missing_planned_tools") or [])
            if str(item or "").strip()
        ]
        missing_actions = [
            str(item or "").strip()
            for item in list(row.get("missing_advisory_actions") or [])
            if str(item or "").strip()
        ]
        signals.append(
            {
                "source": "root_closure_inventory",
                "signal_class": "governance_pressure",
                "title": f"Wire source root end to end: {root_id}",
                "fingerprint": {
                    "class": "governance_pressure",
                    "surface": "root_closure_inventory",
                    "error": "root_closure_gap",
                    "symbol": root_id,
                },
                "payload": {
                    "root_id": root_id,
                    "label": str(row.get("label") or ""),
                    "gaps": gaps,
                    "missing_source_files": list(row.get("missing_source_files") or []),
                    "missing_status_keys": missing_status,
                    "missing_signal_sources": missing_signals,
                    "missing_planned_tools": missing_tools,
                    "missing_advisory_actions": missing_actions,
                    "source_files": source_files,
                    "status_keys": list(row.get("status_keys") or []),
                    "signal_sources": list(row.get("signal_sources") or []),
                    "planned_tools": list(row.get("planned_tools") or []),
                    "advisory_actions": list(row.get("advisory_actions") or []),
                    "rationale": "A declared Nova source root is present in code but its full status, signal, tool, and action wiring is not complete.",
                },
                "severity": "high",
                "actionability": "safe_now",
                "allowed_tools": ["read", "find", "pulse", "system_check"],
                "preferred_tool": "read",
                "next_task": f"Read source root evidence for {root_id}",
                "task_sequence": [
                    {
                        "title": f"Read source root evidence for {root_id}",
                        "allowed_tools": ["read"],
                        "preferred_tool": "read",
                        "tool_args": [first_source_file],
                    },
                    {
                        "title": f"Read wiring inventory row for {root_id}",
                        "allowed_tools": ["read"],
                        "preferred_tool": "read",
                        "tool_args": ["services/nova_wiring_inventory.py"],
                    },
                    {
                        "title": f"Find status, signal, tool, and action references for {root_id}",
                        "allowed_tools": ["find"],
                        "preferred_tool": "find",
                        "tool_args": [root_id, "."],
                    },
                ],
            }
        )
    return signals


def _self_repair_closure_inventory_signals_from_status(status_payload: dict[str, Any]) -> list[dict[str, Any]]:
    inventory = (
        status_payload.get("self_repair_closure_inventory")
        if isinstance(status_payload.get("self_repair_closure_inventory"), dict)
        else build_self_repair_closure_inventory_payload(status_payload)
    )
    if int(inventory.get("gap_count", 0) or 0) <= 0:
        return []

    signals: list[dict[str, Any]] = []
    for row in list(inventory.get("roots") or []):
        if not isinstance(row, dict) or bool(row.get("ok", False)):
            continue
        root_id = str(row.get("root_id") or "").strip()
        if not root_id:
            continue
        gaps = [str(item or "").strip() for item in list(row.get("gaps") or []) if str(item or "").strip()]
        source_files = [str(item or "").strip() for item in list(row.get("source_files") or []) if str(item or "").strip()]
        first_source_file = source_files[0] if source_files else "services/nova_wiring_inventory.py"
        closure_depth = str(row.get("closure_depth") or "").strip()
        signals.append(
            {
                "source": "self_repair_closure_inventory",
                "signal_class": "governance_pressure",
                "title": f"Complete self-repair closure for source root: {root_id}",
                "fingerprint": {
                    "class": "governance_pressure",
                    "surface": "self_repair_closure_inventory",
                    "error": "self_repair_closure_gap",
                    "symbol": root_id,
                },
                "payload": {
                    "root_id": root_id,
                    "label": str(row.get("label") or ""),
                    "closure_depth": closure_depth,
                    "gaps": gaps,
                    "source_files": source_files,
                    "missing_execution_path": "missing_execution_path" in gaps,
                    "missing_evidence_paths": list(row.get("missing_evidence_paths") or []),
                    "missing_judgment_paths": list(row.get("missing_judgment_paths") or []),
                    "missing_closure_paths": list(row.get("missing_closure_paths") or []),
                    "missing_operator_outbox_paths": list(row.get("missing_operator_outbox_paths") or []),
                    "missing_owned_root_routes": list(row.get("missing_owned_root_routes") or []),
                    "owned_root_routes": list(row.get("owned_root_routes") or []),
                    "executable_planned_tools": list(row.get("executable_planned_tools") or []),
                    "executable_advisory_actions": list(row.get("executable_advisory_actions") or []),
                    "proof_scope": str(inventory.get("proof_scope") or "source_contract"),
                    "rationale": (
                        "A Nova source root is not counted as source-contract ready until code shows the full chain: "
                        "signal, Work Tree action, execution, evidence, judgment, closure, and operator outbox fallback."
                    ),
                },
                "severity": "high",
                "actionability": "safe_now",
                "allowed_tools": ["read", "find", "pulse", "system_check"],
                "preferred_tool": "read",
                "next_task": f"Read self-repair closure evidence for {root_id}",
                "task_sequence": [
                    {
                        "title": f"Read source root evidence for {root_id}",
                        "allowed_tools": ["read"],
                        "preferred_tool": "read",
                        "tool_args": [first_source_file],
                    },
                    {
                        "title": f"Read self-repair closure inventory for {root_id}",
                        "allowed_tools": ["read"],
                        "preferred_tool": "read",
                        "tool_args": ["services/nova_wiring_inventory.py"],
                    },
                    {
                        "title": f"Find execution, evidence, judgment, and closure references for {root_id}",
                        "allowed_tools": ["find"],
                        "preferred_tool": "find",
                        "tool_args": [root_id, "."],
                    },
                ],
            }
        )
    return signals


def _autonomy_orchestrator_signal_from_status(status_payload: dict[str, Any]) -> dict[str, Any] | None:
    rejection_reasons = [
        str(item or "").strip()
        for item in list(status_payload.get("autonomy_orchestrator_rejection_reasons") or [])
        if str(item or "").strip()
    ]
    ledger_status = str(status_payload.get("autonomy_orchestrator_ledger_status") or "").strip()
    reason = str(status_payload.get("autonomy_orchestrator_reason") or "").strip()
    stale = bool(status_payload.get("autonomy_orchestrator_recommendation_stale", False))
    stale_reasons = [
        str(item or "").strip()
        for item in list(status_payload.get("autonomy_orchestrator_stale_reasons") or [])
        if str(item or "").strip()
    ]
    summary = status_payload.get("autonomy_orchestrator_summary") if isinstance(status_payload.get("autonomy_orchestrator_summary"), dict) else {}
    reason_counts = dict(summary.get("rejection_reason_counts") or {}) if isinstance(summary.get("rejection_reason_counts"), dict) else {}

    if "orchestrator_cycle_failed" in rejection_reasons or ledger_status.startswith("record_failed"):
        error_symbol = "orchestrator_cycle_failed"
        title = "Autonomy orchestrator cycle failed"
        severity = "high"
    elif "operator_ack_required" in rejection_reasons:
        error_symbol = "operator_ack_required"
        title = "Autonomy orchestrator is blocked on operator acknowledgement policy"
        severity = "medium"
    elif stale and stale_reasons:
        error_symbol = "stale_recommendation"
        title = "Autonomy orchestrator recommendation is stale"
        severity = "medium"
    else:
        return None

    return {
        "source": "autonomy_orchestrator",
        "signal_class": "governance_pressure",
        "title": title,
        "fingerprint": {
            "class": "governance_pressure",
            "surface": "autonomy_orchestrator",
            "error": error_symbol,
            "symbol": str(status_payload.get("autonomy_orchestrator_action_type") or "autonomy_orchestrator"),
        },
        "payload": {
            "decision": str(status_payload.get("autonomy_orchestrator_decision") or ""),
            "decision_type": str(status_payload.get("autonomy_orchestrator_decision_type") or ""),
            "action_type": str(status_payload.get("autonomy_orchestrator_action_type") or ""),
            "reason": reason,
            "rejection_reasons": rejection_reasons,
            "ledger_status": ledger_status,
            "recommendation_stale": stale,
            "stale_reasons": stale_reasons,
            "rejection_reason_counts": reason_counts,
            "rationale": "The orchestrator is the action-selection nerve; repeated or current decision blockage needs explicit Work Tree evidence.",
        },
        "severity": severity,
        "actionability": "safe_now",
        "allowed_tools": ["read", "find", "pulse"],
        "preferred_tool": "read",
        "next_task": "Read autonomy orchestrator ledger and policy snapshot for the blocked decision",
        "task_sequence": [
            {
                "title": "Read runtime/autonomy_orchestrator_ledger.jsonl recent decision rows",
                "allowed_tools": ["read"],
                "preferred_tool": "read",
                "tool_args": ["runtime/autonomy_orchestrator_ledger.jsonl"],
            },
            {
                "title": "Read policy.json autonomy execution policy",
                "allowed_tools": ["read"],
                "preferred_tool": "read",
                "tool_args": ["policy.json"],
            },
        ],
    }


def _subconscious_status_signal_from_status(status_payload: dict[str, Any]) -> dict[str, Any] | None:
    if "subconscious_ok" not in status_payload and "subconscious_summary" not in status_payload:
        return None
    summary = status_payload.get("subconscious_summary") if isinstance(status_payload.get("subconscious_summary"), dict) else {}
    ok = bool(status_payload.get("subconscious_ok", summary.get("ok", True)))
    if ok:
        return None
    latest_report_path = str(status_payload.get("subconscious_latest_report_path") or summary.get("latest_report_path") or "").strip()
    return {
        "source": "subconscious",
        "signal_class": "maintenance_pressure",
        "title": "Subconscious status report is unavailable",
        "fingerprint": {
            "class": "maintenance_pressure",
            "surface": "subconscious",
            "error": "subconscious_status_unavailable",
            "symbol": "latest_report",
        },
        "payload": {
            "subconscious_ok": ok,
            "subconscious_generated_at": str(status_payload.get("subconscious_generated_at") or summary.get("generated_at") or ""),
            "subconscious_latest_report_path": latest_report_path,
            "subconscious_family_count": int(status_payload.get("subconscious_family_count", summary.get("family_count", 0)) or 0),
            "subconscious_training_priority_count": int(
                status_payload.get("subconscious_training_priority_count", summary.get("training_priority_count", 0)) or 0
            ),
            "subconscious_live_summary": (
                dict(status_payload.get("subconscious_live_summary") or {})
                if isinstance(status_payload.get("subconscious_live_summary"), dict)
                else {}
            ),
            "rationale": "The subconscious/latest report surface is missing or unreadable, so generated learning pressure cannot be trusted.",
        },
        "severity": "high",
        "actionability": "safe_now",
        "allowed_tools": ["read", "find", "pulse"],
        "preferred_tool": "read",
        "next_task": "Read subconscious latest report and maintenance log before trusting learning pressure",
        "task_sequence": [
            {
                "title": "Read subconscious latest report before trusting learning pressure",
                "allowed_tools": ["read"],
                "preferred_tool": "read",
                "tool_args": [latest_report_path or "runtime/subconscious_runs/latest.json"],
            },
            {
                "title": "Read runtime/autonomy_maintenance.log for subconscious pack errors",
                "allowed_tools": ["read"],
                "preferred_tool": "read",
                "tool_args": ["runtime/autonomy_maintenance.log"],
            },
        ],
    }


def _action_ledger_signal_from_status(status_payload: dict[str, Any]) -> dict[str, Any] | None:
    if "action_ledger_ok" not in status_payload:
        return None
    if bool(status_payload.get("action_ledger_ok", True)):
        return None
    return {
        "source": "action_ledger",
        "signal_class": "maintenance_pressure",
        "title": "Action ledger summary is unavailable",
        "fingerprint": {
            "class": "maintenance_pressure",
            "surface": "action_ledger",
            "error": "action_ledger_unavailable",
            "symbol": "action_ledger",
        },
        "payload": {
            "action_ledger_ok": bool(status_payload.get("action_ledger_ok", False)),
            "action_ledger_total": int(status_payload.get("action_ledger_total", 0) or 0),
            "last_planner_decision": str(status_payload.get("last_planner_decision") or ""),
            "last_route_summary": str(status_payload.get("last_route_summary") or ""),
            "last_action_final_answer": str(status_payload.get("last_action_final_answer") or "")[:220],
            "rationale": "Action ledger readback is unavailable, so Nova cannot reconstruct what it ate before the last reply.",
        },
        "severity": "high",
        "actionability": "safe_now",
        "allowed_tools": ["read", "find", "pulse"],
        "preferred_tool": "read",
        "next_task": "Read runtime action ledger records and isolate ledger parse failure",
    }


def _os_capability_ledger_signal_from_status(status_payload: dict[str, Any]) -> dict[str, Any] | None:
    if not _has_os_capability_ledger_surface(status_payload):
        return None
    ledger = status_payload.get("os_capability_ledger") if isinstance(status_payload.get("os_capability_ledger"), dict) else {}
    readable_ok = bool(status_payload.get("os_capability_ledger_readable_ok", ledger.get("readable_ok", True)))
    issue_count = _as_int(
        status_payload.get("os_capability_ledger_current_issue_count", ledger.get("current_issue_count", 0)),
        0,
    )
    if readable_ok and issue_count <= 0:
        return None

    last_issue = (
        status_payload.get("last_os_capability_issue")
        if isinstance(status_payload.get("last_os_capability_issue"), dict)
        else ledger.get("last_issue")
    )
    last_issue = dict(last_issue) if isinstance(last_issue, dict) else {}
    capability = str(
        status_payload.get("last_os_capability_issue_name")
        or last_issue.get("capability")
        or status_payload.get("last_os_capability_name")
        or "os_capability"
    ).strip()
    status_text = str(
        status_payload.get("last_os_capability_issue_status")
        or last_issue.get("status")
        or ("unreadable" if not readable_ok else "issue")
    ).strip().lower()
    reason_text = str(
        status_payload.get("last_os_capability_issue_reason")
        or last_issue.get("reason")
        or ("ledger_unreadable" if not readable_ok else "os_capability_issue")
    ).strip().lower()
    current_issue_rows = [
        dict(item)
        for item in list(ledger.get("current_issue_rows") or [])
        if isinstance(item, dict)
    ]
    title = "OS capability ledger has unresolved execution evidence"
    if reason_text == "contract_stale":
        title = "OS capability contract drift is blocking execution"
    elif status_text == "timeout":
        title = "OS capability execution timed out"
    elif status_text == "blocked":
        title = "OS capability request is blocked before execution"
    elif not readable_ok:
        title = "OS capability ledger summary is unavailable"

    return {
        "source": "tool_registry_policy",
        "signal_class": "maintenance_pressure",
        "title": title,
        "fingerprint": {
            "class": "maintenance_pressure",
            "surface": "tool_registry_policy",
            "error": reason_text or status_text or "os_capability_issue",
            "symbol": capability or "os_capability",
        },
        "payload": {
            "os_capability_ledger_ok": bool(status_payload.get("os_capability_ledger_ok", ledger.get("ok", False))),
            "os_capability_ledger_readable_ok": readable_ok,
            "os_capability_ledger_total": _as_int(status_payload.get("os_capability_ledger_total", ledger.get("count", 0)), 0),
            "os_capability_ledger_current_issue_count": issue_count,
            "os_capability_ledger_current_blocked_count": _as_int(
                status_payload.get("os_capability_ledger_current_blocked_count", ledger.get("current_blocked_count", 0)),
                0,
            ),
            "os_capability_ledger_current_failure_count": _as_int(
                status_payload.get("os_capability_ledger_current_failure_count", ledger.get("current_failure_count", 0)),
                0,
            ),
            "os_capability_ledger_current_timeout_count": _as_int(
                status_payload.get("os_capability_ledger_current_timeout_count", ledger.get("current_timeout_count", 0)),
                0,
            ),
            "os_capability_ledger_current_operator_outbox_count": _as_int(
                status_payload.get(
                    "os_capability_ledger_current_operator_outbox_count",
                    ledger.get("current_operator_outbox_count", 0),
                ),
                0,
            ),
            "os_capability_ledger_path": str(status_payload.get("os_capability_ledger_path") or ledger.get("ledger_path") or ""),
            "last_os_capability_issue": last_issue,
            "current_issue_rows": current_issue_rows[:6],
            "rationale": "OS capability execution evidence is unresolved, so Nova cannot claim the capability chain is clean.",
        },
        "severity": "high" if reason_text == "contract_stale" or status_text in {"timeout", "failed", "error"} else "medium",
        "actionability": "safe_now",
        "allowed_tools": ["read", "find", "os_capability"],
        "preferred_tool": "read",
        "next_task": OS_CAPABILITY_LEDGER_READ_TASK_TITLE,
        "task_sequence": [
            {
                "title": OS_CAPABILITY_LEDGER_READ_TASK_TITLE,
                "allowed_tools": ["read"],
                "preferred_tool": "read",
                "tool_args": ["runtime/os_capability_ledger.jsonl"],
            },
            {
                "title": "Read OS capability registry contract for the unresolved capability",
                "allowed_tools": ["read"],
                "preferred_tool": "read",
                "tool_args": ["tools/os_capabilities/os_capabilities.json"],
            },
            {
                "title": "Find OS capability controller and operator-outbox routing",
                "allowed_tools": ["find"],
                "preferred_tool": "find",
                "tool_args": ["os_capability_ledger|contract_stale|operator_outbox", "."],
            },
        ],
    }


def _http_conversation_signal_from_status(status_payload: dict[str, Any]) -> dict[str, Any] | None:
    if not _has_http_conversation_surface(status_payload):
        return None
    active_sessions = _as_int(status_payload.get("active_http_sessions"), 0)
    if active_sessions >= 0:
        return None
    return {
        "source": "http_continuity",
        "signal_class": "maintenance_pressure",
        "title": "HTTP conversation state is reporting invalid session telemetry",
        "fingerprint": {
            "class": "maintenance_pressure",
            "surface": "http_continuity",
            "error": "invalid_active_session_count",
            "symbol": "active_http_sessions",
        },
        "payload": {
            "active_http_sessions": active_sessions,
            "last_route_summary": str(status_payload.get("last_route_summary") or ""),
            "last_action_final_answer": str(status_payload.get("last_action_final_answer") or "")[:220],
        },
        "severity": "medium",
        "actionability": "safe_now",
        "allowed_tools": ["read", "find", "pulse"],
        "preferred_tool": "read",
        "next_task": "Read HTTP session state and isolate invalid conversation telemetry",
    }


def _validation_artifact_truth_signal_from_status(status_payload: dict[str, Any]) -> dict[str, Any] | None:
    if not _has_validation_artifact_truth_surface(status_payload):
        return None
    truth = status_payload.get("validation_artifact_truth") if isinstance(status_payload.get("validation_artifact_truth"), dict) else {}
    validation_ok = bool(status_payload.get("validation_artifact_truth_ok", truth.get("ok", True)))
    failure_count = _as_int(
        status_payload.get(
            "validation_artifact_failure_count",
            truth.get("current_window_failure_count", truth.get("failure_count", 0)),
        ),
        0,
    )
    if validation_ok and failure_count <= 0:
        return None

    llm_failure_count = _as_int(
        status_payload.get(
            "validation_artifact_llm_unavailable_count",
            truth.get("current_window_llm_unavailable_count", truth.get("llm_unavailable_count", 0)),
        ),
        0,
    )
    hidden_by_green = bool(
        status_payload.get(
            "validation_artifact_hidden_by_green_regression",
            truth.get("hidden_by_green_regression", False),
        )
    )
    status_text = str(status_payload.get("validation_artifact_truth_status") or truth.get("status") or "unknown").strip()
    latest_failure = (
        status_payload.get("validation_artifact_latest_failure")
        if isinstance(status_payload.get("validation_artifact_latest_failure"), dict)
        else truth.get("latest_failure")
    )
    latest_failure = dict(latest_failure) if isinstance(latest_failure, dict) else {}
    latest_failure_path = str(latest_failure.get("path") or "").strip()
    failure_kind = str(latest_failure.get("failure_kind") or "").strip()
    missing_artifact = bool(truth.get("missing_artifact")) or status_text == "validation_actions_missing"
    if missing_artifact:
        error_symbol = "validation_actions_missing"
        title = "Validation action artifact directory is missing"
    elif hidden_by_green and llm_failure_count > 0:
        error_symbol = "llm_unavailable_hidden_by_green_regression"
        title = "Validation artifacts recorded LLM failure under green regression"
    elif llm_failure_count > 0:
        error_symbol = "llm_unavailable_in_validation"
        title = "Validation artifacts recorded LLM failure"
    else:
        error_symbol = status_text or "validation_artifact_failure"
        title = "Validation artifacts disagree with regression status"

    task_sequence: list[dict[str, Any]] = []
    if latest_failure_path:
        task_sequence.append({
            "title": "Read validation action artifact with the failing final answer",
            "allowed_tools": ["read"],
            "preferred_tool": "read",
            "tool_args": [latest_failure_path],
        })
    if missing_artifact:
        task_sequence.extend([
            {
                "title": "Read regression status before trusting green status",
                "allowed_tools": ["read"],
                "preferred_tool": "read",
                "tool_args": ["runtime/regression_status.json"],
            },
            {
                "title": "List validation runtime artifact parent directory",
                "allowed_tools": ["ls"],
                "preferred_tool": "ls",
                "tool_args": ["runtime/validation"],
            },
            {
                "title": "Read validation artifact truth source",
                "allowed_tools": ["read"],
                "preferred_tool": "read",
                "tool_args": ["services/validation_artifact_truth.py"],
            },
        ])
    else:
        task_sequence.extend([
            {
                "title": "Read regression status before trusting green status",
                "allowed_tools": ["read"],
                "preferred_tool": "read",
                "tool_args": ["runtime/regression_status.json"],
            },
            {
                "title": "Read regression runner contract before trusting green status",
                "allowed_tools": ["read"],
                "preferred_tool": "read",
                "tool_args": ["scripts/run_regression.py"],
            },
            {
                "title": "Find matching validation-runtime final-answer errors",
                "allowed_tools": ["find"],
                "preferred_tool": "find",
                "tool_args": ["runtime/validation/actions", "(error:"],
            },
        ])

    return {
        "source": "test_ecosystem",
        "signal_class": "regression_failure",
        "title": title,
        "fingerprint": {
            "class": "regression_failure",
            "surface": "test_ecosystem",
            "error": error_symbol,
            "symbol": failure_kind or "validation_actions",
        },
        "payload": {
            "test_ecosystem_signal": "validation_artifact_truth",
            "status": status_text,
            "failure_count": failure_count,
            "llm_unavailable_count": llm_failure_count,
            "hidden_by_green_regression": hidden_by_green,
            "latest_regression_status": str(truth.get("latest_regression_status") or ""),
            "latest_regression_at": str(truth.get("latest_regression_at") or ""),
            "action_dir": str(truth.get("action_dir") or ""),
            "missing_artifact": missing_artifact,
            "latest_failure": latest_failure,
            "failures": [dict(item) for item in list(truth.get("failures") or []) if isinstance(item, dict)][:6],
            "rationale": (
                "Validation runtime action ledgers are part of regression evidence. Nova must not report "
                "a clean test ecosystem when validation action evidence is missing or contains runtime errors."
            ),
        },
        "severity": "high",
        "actionability": "safe_now",
        "allowed_tools": ["read", "find", "system_check"],
        "preferred_tool": "read",
        "next_task": "Read validation action artifact and regression runner contract before trusting green status",
        "task_sequence": task_sequence,
        "blocked_task": (
            "Wait for validation action evidence to be produced before treating regression truth as proven"
            if missing_artifact
            else "Wait for a new regression run to confirm validation artifact truth is clean"
        ),
        "blocked_reason": (
            "validation_action_evidence_missing"
            if missing_artifact
            else "validation_artifact_failure_requires_new_regression_evidence"
        ),
    }


def _test_profile_inventory_signal_from_status(status_payload: dict[str, Any]) -> dict[str, Any] | None:
    if not _has_test_profile_inventory_surface(status_payload):
        return None
    inventory = status_payload.get("test_profile_inventory") if isinstance(status_payload.get("test_profile_inventory"), dict) else {}
    inventory_ok = bool(status_payload.get("test_profile_inventory_ok", inventory.get("ok", True)))
    gap_count = _as_int(
        status_payload.get("test_profile_profile_gap_count", inventory.get("profile_gap_count", 0)),
        0,
    )
    outside_curated_count = _as_int(
        status_payload.get("test_profile_outside_curated_count", inventory.get("outside_curated_count", 0)),
        0,
    )
    source_observed_count = _as_int(
        status_payload.get(
            "test_profile_source_observed_count",
            inventory.get("source_observed_count", outside_curated_count),
        ),
        outside_curated_count,
    )
    drift_count = _as_int(
        status_payload.get(
            "test_profile_profile_drift_count",
            inventory.get("profile_drift_count", gap_count + source_observed_count),
        ),
        gap_count + source_observed_count,
    )
    attention_count = _as_int(
        status_payload.get(
            "test_profile_profile_attention_count",
            inventory.get("profile_attention_count", drift_count),
        ),
        drift_count,
    )
    if inventory_ok and drift_count <= 0 and gap_count <= 0:
        return None

    inactive_profile_count = _as_int(
        status_payload.get("test_profile_install_profile_inactive_count", inventory.get("install_profile_inactive_count", 0)),
        0,
    )
    optional_inactive_profile_count = _as_int(
        status_payload.get(
            "test_profile_install_profile_optional_inactive_count",
            inventory.get("install_profile_optional_inactive_count", 0),
        ),
        0,
    )
    unclassified_count = _as_int(
        status_payload.get("test_profile_unclassified_count", inventory.get("unclassified_count", 0)),
        0,
    )
    gap_tests = [
        dict(item)
        for item in list(inventory.get("gap_tests") or status_payload.get("test_profile_gap_tests") or [])
        if isinstance(item, dict)
    ]
    drift_tests = [
        dict(item)
        for item in list(
            inventory.get("profile_drift_tests")
            or status_payload.get("test_profile_profile_drift_tests")
            or gap_tests
            or inventory.get("attention_tests")
            or []
        )
        if isinstance(item, dict)
    ]
    first_gap = (gap_tests or drift_tests or [{}])[0]
    first_path = str(first_gap.get("path") or "test_profile_inventory").strip()
    if inactive_profile_count > 0:
        error_symbol = "inactive_install_profile_tests"
        title = "Validation profile still contains tests for inactive install lanes"
    elif unclassified_count > 0:
        error_symbol = "unclassified_tests"
        title = "Validation profile has unclassified tests"
    else:
        error_symbol = "source_observed_tests_outside_validation_profile"
        title = "Validation profile has source-observed tests outside compact lanes"

    task_sequence: list[dict[str, Any]] = [
        {
            "title": "Read regression profile inventory contract",
            "allowed_tools": ["read"],
            "preferred_tool": "read",
            "tool_args": ["services/regression_profile_inventory.py"],
        },
        {
            "title": "Read compact regression lane contract",
            "allowed_tools": ["read"],
            "preferred_tool": "read",
            "tool_args": ["scripts/run_regression.py"],
        },
    ]
    if first_path and first_path != "test_profile_inventory":
        task_sequence.append({
            "title": "Read first validation profile drift test",
            "allowed_tools": ["read"],
            "preferred_tool": "read",
            "tool_args": [first_path],
        })
    if inactive_profile_count > 0:
        task_sequence.append({
            "title": "Find inactive data-lane test expectations",
            "allowed_tools": ["find"],
            "preferred_tool": "find",
            "tool_args": ["sis_test", "tests docs data_sources"],
        })

    return {
        "source": "test_ecosystem",
        "signal_class": "governance_pressure",
        "title": title,
        "fingerprint": {
            "class": "governance_pressure",
            "surface": "test_ecosystem",
            "error": error_symbol,
            "symbol": first_path,
        },
        "payload": {
            "test_ecosystem_signal": "test_profile_inventory",
            "profile_gap_count": gap_count,
            "profile_drift_count": drift_count,
            "profile_attention_count": attention_count,
            "source_observed_count": source_observed_count,
            "outside_curated_count": outside_curated_count,
            "install_profile_inactive_count": inactive_profile_count,
            "install_profile_optional_inactive_count": optional_inactive_profile_count,
            "unclassified_count": unclassified_count,
            "curated_target_count": _as_int(inventory.get("curated_target_count"), 0),
            "curated_test_file_count": _as_int(inventory.get("curated_test_file_count"), 0),
            "root_test_file_count": _as_int(inventory.get("root_test_file_count"), 0),
            "all_test_file_count": _as_int(inventory.get("all_test_file_count"), 0),
            "gap_tests": gap_tests[:12],
            "profile_drift_tests": drift_tests[:12],
            "rationale": (
                "Nova's compact regression result cannot be treated as complete source truth while root tests "
                "still target inactive install lanes, cannot be classified, or live outside any validation lane."
            ),
        },
        "severity": "medium",
        "actionability": "safe_now",
        "allowed_tools": ["read", "find", "queue_status"],
        "preferred_tool": "read",
        "next_task": "Classify validation profile drift before trusting compact regression as full test truth",
        "task_sequence": task_sequence,
        "blocked_task": "Await source-contract judgment for validation profile drift",
        "blocked_reason": "validation_profile_contract_judgment_required",
    }


def _alert_surface(alert: str) -> str:
    text = str(alert or "").strip().lower()
    if ":" in text:
        return text.split(":", 1)[0].strip()
    return text


def _self_check_unowned_alerts(alerts: list[str], routed_signals: list[dict[str, Any]]) -> list[str]:
    surface_aliases = {
        "test_ecosystem": {"test_profile_inventory", "validation_artifact_truth"},
        "work_tree": {"wiring_inventory", "work_tree_unresolved_truth"},
    }
    covered_surfaces = {
        "validation_artifact_truth",
        "test_profile_inventory",
        "work_tree_unresolved_truth",
    }
    covered_alerts: set[str] = set()
    for signal in routed_signals:
        if not isinstance(signal, dict):
            continue
        payload = signal.get("payload") if isinstance(signal.get("payload"), dict) else {}
        exact_alert = str(payload.get("alert") or "").strip()
        if exact_alert:
            covered_alerts.add(exact_alert)

        source = str(signal.get("source") or "").strip().lower()
        if source:
            covered_surfaces.add(source)
            covered_surfaces.update(surface_aliases.get(source, set()))
        fingerprint = signal.get("fingerprint") if isinstance(signal.get("fingerprint"), dict) else {}
        surface = str(fingerprint.get("surface") or "").strip().lower()
        if surface:
            covered_surfaces.add(surface)
            covered_surfaces.update(surface_aliases.get(surface, set()))

    return [
        alert
        for alert in alerts
        if alert not in covered_alerts and _alert_surface(alert) not in covered_surfaces
    ]


def _self_check_signal_from_status(
    status_payload: dict[str, Any],
    routed_signals: list[dict[str, Any]],
) -> dict[str, Any] | None:
    alerts = [str(item or "").strip() for item in list(status_payload.get("alerts") or []) if str(item or "").strip()]
    pass_ratio = float(status_payload.get("self_check_pass_ratio") or 0.0)
    unowned_alerts = _self_check_unowned_alerts(alerts, routed_signals)
    if pass_ratio >= 1.0 or not unowned_alerts:
        return None

    return {
        "source": "diagnostics_hygiene",
        "signal_class": "governance_pressure",
        "title": "Resolve self-check failures in control status",
        "fingerprint": {
            "class": "governance_pressure",
            "surface": "diagnostics_hygiene",
            "error": "self_check_failures",
            "symbol": "control_status",
        },
        "payload": {
            "pass_ratio": pass_ratio,
            "alerts": unowned_alerts,
        },
        "severity": "high" if pass_ratio < 0.95 else "medium",
        "actionability": "blocked",
        "next_task": "Confirm failing self-check probes and route each probe to root-cause branch",
    }


def _self_check_routed_signals_from_status(status_payload: dict[str, Any]) -> list[dict[str, Any]]:
    routed: list[dict[str, Any]] = []
    for signal in (
        _validation_artifact_truth_signal_from_status(status_payload),
        _test_profile_inventory_signal_from_status(status_payload),
    ):
        if signal is not None:
            routed.append(signal)
    return routed


def _has_self_check_surface(status_payload: dict[str, Any]) -> bool:
    return "self_check_pass_ratio" in status_payload or "alerts" in status_payload


def _has_dependency_surface(status_payload: dict[str, Any]) -> bool:
    return any(
        key in status_payload
        for key in (
            "search_provider",
            "searxng_ok",
        )
    )


def _has_model_runtime_surface(status_payload: dict[str, Any]) -> bool:
    return any(
        key in status_payload
        for key in (
            "ollama_api_up",
            "ollama_server_ok",
            "ollama_health",
            "ollama_tags_ok",
            "ollama_chat_route_ok",
            "ollama_model_available",
            "ollama_configured_model",
            "ollama_chat_ready",
            "ollama_version",
            "ollama_api_contract_status",
            "port_ownership",
        )
    )


def _has_runtime_surface(status_payload: dict[str, Any]) -> bool:
    return any(key in status_payload for key in ("guard", "core", "webui", "core_heartbeat_age_sec", "heartbeat_age_sec"))


def _has_maintenance_surface(status_payload: dict[str, Any]) -> bool:
    return "maintenance_scheduler_active" in status_payload


def _has_autonomy_maintenance_error_surface(status_payload: dict[str, Any]) -> bool:
    return "autonomy_maintenance" in status_payload or any(
        key in status_payload
        for key in (
            "runtime_worker_status",
            "runtime_worker_stale_identity",
        )
    )


def _has_runtime_failures_surface(status_payload: dict[str, Any]) -> bool:
    return isinstance(status_payload.get("runtime_failures"), dict) and bool(status_payload.get("runtime_failures"))


def _has_runtime_restart_surface(status_payload: dict[str, Any]) -> bool:
    return isinstance(status_payload.get("runtime_restart_analytics"), dict) and bool(status_payload.get("runtime_restart_analytics"))


def _has_storage_watch_surface(status_payload: dict[str, Any]) -> bool:
    return any(
        key in status_payload
        for key in (
            "storage_watch_status",
            "storage_watch_note",
            "storage_watch_total_bytes",
            "patch_snapshot_count",
            "kidney_snapshot_count",
            "release_validation_extract_bytes",
            "release_stage_bytes",
            "release_zip_bytes",
        )
    )


def _has_patch_pipeline_surface(status_payload: dict[str, Any]) -> bool:
    return any(
        key in status_payload
        for key in (
            "patch_status_ok",
            "patch_enabled",
            "patch_pipeline_ready",
            "patch_cleanup_status",
            "patch_tests_available",
        )
    )


def _has_data_pipeline_surface(status_payload: dict[str, Any]) -> bool:
    return any(
        key in status_payload
        for key in (
            "data_pipelines",
            "data_pipeline_registry_ok",
            "data_pipeline_count",
            "data_pipeline_ids",
        )
    )


def _has_frontdoor_cli_surface(status_payload: dict[str, Any]) -> bool:
    return any(key in status_payload for key in ("backend_commands", "backend_command_count", "frontdoor_cli_status"))


def _has_operator_control_surface(status_payload: dict[str, Any]) -> bool:
    return any(
        key in status_payload
        for key in (
            "operator_outbox",
            "operator_outbox_open_count",
            "operator_outbox_latest_open_id",
            "operator_macros",
            "backend_commands",
        )
    )


def _has_policy_gates_surface(status_payload: dict[str, Any]) -> bool:
    return any(
        key in status_payload
        for key in (
            "web_enabled",
            "allow_domains_count",
            "memory_enabled",
            "patch_enabled",
            "patch_strict_manifest",
            "patch_behavioral_check",
            "patch_tests_available",
            "vision_status",
            "voice_status",
        )
    )


def _has_session_identity_auth_surface(status_payload: dict[str, Any]) -> bool:
    return any(key in status_payload for key in ("chat_login_enabled", "chat_auth_source", "chat_users_count"))


def _has_identity_profile_answers_surface(status_payload: dict[str, Any]) -> bool:
    return any(
        key in status_payload
        for key in (
            "memory_health",
            "memory_health_status",
            "memory_enabled",
            "identity_profile_status",
        )
    )


def _has_conversation_routing_surface(status_payload: dict[str, Any]) -> bool:
    return any(
        key in status_payload
        for key in (
            "last_intent",
            "last_planner_decision",
            "last_route_summary",
            "last_route_trace",
            "action_ledger_total",
        )
    )


def _has_supervisor_fulfillment_surface(status_payload: dict[str, Any]) -> bool:
    return any(
        key in status_payload
        for key in (
            "last_route_trace",
            "last_route_summary",
            "last_planner_decision",
            "supervisor_fulfillment_status",
        )
    )


def _has_reply_quality_contracts_surface(status_payload: dict[str, Any]) -> bool:
    return any(
        key in status_payload
        for key in (
            "last_action_final_answer",
            "last_route_grounded",
            "last_route_trace",
            "reply_quality_status",
        )
    )


def _has_retrieval_knowledge_surface(status_payload: dict[str, Any]) -> bool:
    return any(
        key in status_payload
        for key in (
            "retrieval_knowledge_status",
            "knowledge_pack_status",
            "knowledge_used",
            "knowledge_chars",
            "knowledge_active_pack",
            "last_provider_hit",
        )
    )


def _has_weather_location_surface(status_payload: dict[str, Any]) -> bool:
    return any(
        key in status_payload
        for key in (
            "weather_source_host",
            "last_action_tool",
            "last_route_trace",
            "live_tracking",
            "web_enabled",
        )
    )


def _has_installer_packaging_surface(status_payload: dict[str, Any]) -> bool:
    return any(
        key in status_payload
        for key in (
            "installer_status",
            "installer_packaging_status",
            "release_status",
        )
    )


def _has_tts_audio_output_surface(status_payload: dict[str, Any]) -> bool:
    return any(
        key in status_payload
        for key in (
            "tts_status",
            "tts_audio_status",
            "voice_status",
            "voice_runtime_requested",
        )
    )


def _has_safety_envelope_surface(status_payload: dict[str, Any]) -> bool:
    return any(
        key in status_payload
        for key in (
            "safety_envelope_status",
            "safety_enabled",
            "safety_mode",
            "pending_review_total",
            "quarantine_total",
            "pulse",
        )
    )


def _has_metrics_ops_journal_surface(status_payload: dict[str, Any]) -> bool:
    return any(
        key in status_payload
        for key in (
            "requests_total",
            "errors_total",
            "tool_events_total",
            "ops_journal_status",
            "metrics_ops_journal_status",
        )
    )


def _has_core_steward_reflection_surface(status_payload: dict[str, Any]) -> bool:
    return any(
        key in status_payload
        for key in (
            "pulse",
            "pulse_summary",
            "health_score",
            "core_steward_status",
            "core_health_brief_status",
        )
    )


def _has_wiring_inventory_surface(status_payload: dict[str, Any]) -> bool:
    return any(
        key in status_payload
        for key in (
            "wiring_inventory",
            "wiring_inventory_ok",
            "wiring_inventory_gap_count",
        )
    )


def _has_source_root_inventory_surface(status_payload: dict[str, Any]) -> bool:
    return any(
        key in status_payload
        for key in (
            "source_root_inventory",
            "source_root_inventory_ok",
            "source_root_inventory_gap_count",
            "source_root_inventory_unwired_roots",
            "source_root_inventory_missing_evidence_roots",
        )
    )


def _has_source_wiring_probe_surface(status_payload: dict[str, Any]) -> bool:
    return any(
        key in status_payload
        for key in (
            "source_wiring_probe",
            "source_wiring_probe_ok",
            "source_wiring_probe_gap_count",
        )
    )


def _has_root_closure_inventory_surface(status_payload: dict[str, Any]) -> bool:
    return any(
        key in status_payload
        for key in (
            "root_closure_inventory",
            "root_closure_inventory_ok",
            "root_closure_inventory_gap_count",
            "root_closure_inventory_gap_roots",
        )
    )


def _has_self_repair_closure_inventory_surface(status_payload: dict[str, Any]) -> bool:
    return any(
        key in status_payload
        for key in (
            "self_repair_closure_inventory",
            "self_repair_closure_inventory_ok",
            "self_repair_closure_inventory_gap_count",
            "self_repair_closure_inventory_gap_roots",
        )
    )


def _has_autonomy_orchestrator_surface(status_payload: dict[str, Any]) -> bool:
    return any(
        key in status_payload
        for key in (
            "autonomy_orchestrator_decision",
            "autonomy_orchestrator_rejection_reasons",
            "autonomy_orchestrator_ledger_status",
            "autonomy_orchestrator_summary",
        )
    )


def _has_subconscious_status_surface(status_payload: dict[str, Any]) -> bool:
    return any(
        key in status_payload
        for key in (
            "subconscious_ok",
            "subconscious_summary",
            "subconscious_latest_report_path",
        )
    )


def _has_action_ledger_surface(status_payload: dict[str, Any]) -> bool:
    return any(
        key in status_payload
        for key in (
            "action_ledger_ok",
            "action_ledger_total",
            "last_planner_decision",
            "last_route_summary",
        )
    )


def _has_os_capability_ledger_surface(status_payload: dict[str, Any]) -> bool:
    return any(
        key in status_payload
        for key in (
            "os_capability_ledger",
            "os_capability_ledger_ok",
            "os_capability_ledger_readable_ok",
            "os_capability_ledger_current_issue_count",
            "last_os_capability_issue",
        )
    )


def _has_http_conversation_surface(status_payload: dict[str, Any]) -> bool:
    return any(
        key in status_payload
        for key in (
            "active_http_sessions",
            "last_route_summary",
            "last_action_final_answer",
        )
    )


def _has_validation_artifact_truth_surface(status_payload: dict[str, Any]) -> bool:
    return any(
        key in status_payload
        for key in (
            "validation_artifact_truth",
            "validation_artifact_truth_ok",
            "validation_artifact_truth_status",
            "validation_artifact_failure_count",
            "validation_artifact_latest_failure",
        )
    )


def _has_test_profile_inventory_surface(status_payload: dict[str, Any]) -> bool:
    return any(
        key in status_payload
        for key in (
            "test_profile_inventory",
            "test_profile_inventory_ok",
            "test_profile_profile_gap_count",
            "test_profile_profile_drift_count",
            "test_profile_profile_attention_count",
            "test_profile_outside_curated_count",
            "test_profile_install_profile_inactive_count",
            "test_profile_install_profile_optional_inactive_count",
            "test_profile_unclassified_count",
        )
    )


def _has_regression_surface(status_payload: dict[str, Any]) -> bool:
    maintenance = status_payload.get("autonomy_maintenance") if isinstance(status_payload.get("autonomy_maintenance"), dict) else {}
    return "last_regression_status" in maintenance or "last_regression_stale" in maintenance


def _has_release_surface(status_payload: dict[str, Any]) -> bool:
    release = status_payload.get("release_status") if isinstance(status_payload.get("release_status"), dict) else {}
    return bool(release)


def _has_memory_surface(status_payload: dict[str, Any]) -> bool:
    return any(
        key in status_payload
        for key in (
            "memory_health",
            "memory_health_status",
            "memory_health_issue_count",
            "memory_health_issues",
        )
    )


def _has_generated_queue_surface(status_payload: dict[str, Any]) -> bool:
    generated_queue = (
        status_payload.get("generated_work_queue")
        if isinstance(status_payload.get("generated_work_queue"), dict)
        else {}
    )
    return bool(generated_queue) or any(
        key in status_payload
        for key in (
            "generated_queue_status",
            "queue_open_count",
            "queue_actionable_count",
            "queue_blocked_count",
            "queue_blocked_reason_counts",
            "queue_blocked_files",
        )
    )


def _has_voice_surface(status_payload: dict[str, Any]) -> bool:
    voice = status_payload.get("voice_status") if isinstance(status_payload.get("voice_status"), dict) else {}
    return bool(voice) or any(
        key in status_payload
        for key in (
            "voice_runtime_status",
            "voice_runtime_requested",
            "voice_runtime_ok",
            "voice_import_error",
        )
    )


def _has_vision_surface(status_payload: dict[str, Any]) -> bool:
    vision = status_payload.get("vision_status") if isinstance(status_payload.get("vision_status"), dict) else {}
    return bool(vision) or any(
        key in status_payload
        for key in (
            "vision_runtime_status",
            "vision_runtime_requested",
            "vision_runtime_ok",
            "vision_missing_modules",
        )
    )


def _voice_status_reports_clear(status_payload: dict[str, Any]) -> bool:
    if not _has_voice_surface(status_payload):
        return False
    voice = status_payload.get("voice_status") if isinstance(status_payload.get("voice_status"), dict) else {}
    requested = bool(status_payload.get("voice_runtime_requested", voice.get("requested", voice.get("voice_ready", False))))
    status_text = str(status_payload.get("voice_runtime_status") or voice.get("status") or "").strip().lower()
    ok = bool(status_payload.get("voice_runtime_ok", voice.get("ok", False)))
    return bool(requested and ok and status_text in {"ok", "ready", "loaded"})


def _vision_status_reports_clear(status_payload: dict[str, Any]) -> bool:
    if not _has_vision_surface(status_payload):
        return False
    vision = status_payload.get("vision_status") if isinstance(status_payload.get("vision_status"), dict) else {}
    requested = bool(status_payload.get("vision_runtime_requested", vision.get("requested", False)))
    status_text = str(status_payload.get("vision_runtime_status") or vision.get("status") or "").strip().lower()
    ok = bool(status_payload.get("vision_runtime_ok", vision.get("ok", False)))
    return bool(requested and ok and status_text in {"ok", "ready", "loaded"})


def _generated_queue_signal_from_status(status_payload: dict[str, Any]) -> dict[str, Any] | None:
    generated_queue = (
        status_payload.get("generated_work_queue")
        if isinstance(status_payload.get("generated_work_queue"), dict)
        else {}
    )
    queue_status = str(status_payload.get("generated_queue_status") or generated_queue.get("status") or "").strip().lower()
    open_count = int(status_payload.get("queue_open_count", generated_queue.get("open_count", 0)) or 0)
    actionable_count = int(status_payload.get("queue_actionable_count", generated_queue.get("actionable_count", 0)) or 0)
    blocked_count = int(status_payload.get("queue_blocked_count", generated_queue.get("blocked_count", 0)) or 0)
    if open_count > 0 and blocked_count <= 0 and actionable_count <= 0:
        blocked_count = open_count
    reason_counts = (
        status_payload.get("queue_blocked_reason_counts")
        if isinstance(status_payload.get("queue_blocked_reason_counts"), dict)
        else generated_queue.get("blocked_reason_counts")
    )
    blocked_reason_counts = dict(reason_counts or {}) if isinstance(reason_counts, dict) else {}
    files = (
        status_payload.get("queue_blocked_files")
        if isinstance(status_payload.get("queue_blocked_files"), list)
        else generated_queue.get("blocked_files")
    )
    blocked_files = [str(item or "").strip() for item in list(files or []) if str(item or "").strip()]
    active = bool(open_count > 0 and blocked_count > 0 and actionable_count <= 0 and queue_status not in {"", "clear"})
    if not active:
        return None

    top_reason = "blocked"
    if blocked_reason_counts:
        top_reason = sorted(
            ((str(key or "").strip() or "blocked", int(value or 0)) for key, value in blocked_reason_counts.items()),
            key=lambda item: (-item[1], item[0]),
        )[0][0]

    return {
        "source": "generated_queue",
        "signal_class": "maintenance_pressure",
        "title": "Generated Work Queue is blocked with no actionable session",
        "fingerprint": {
            "class": "maintenance_pressure",
            "surface": "generated_queue",
            "error": "generated_queue_blocked",
            "symbol": top_reason,
        },
        "payload": {
            "generated_queue_status": queue_status,
            "queue_open_count": open_count,
            "queue_actionable_count": actionable_count,
            "queue_blocked_count": blocked_count,
            "queue_blocked_reason_counts": blocked_reason_counts,
            "queue_blocked_files": blocked_files[:12],
            "rationale": "Generated sessions are open, but none are currently actionable; Nova needs to inspect why the echo loop is blocked instead of running more sessions.",
        },
        "severity": "medium",
        "actionability": "safe_now",
        "allowed_tools": ["queue_status", "read", "find"],
        "preferred_tool": "queue_status",
        "next_task": "Inspect generated queue blocked reasons without running generated sessions",
    }


def _has_tool_events_surface(status_payload: dict[str, Any]) -> bool:
    return any(
        key in status_payload
        for key in (
            "tool_events_error_count",
            "tool_events_failure_count",
            "last_tool_error_summary",
            "last_tool_error_stale",
            "last_tool_name",
            "last_tool_status",
        )
    )


def _tool_events_signal_from_status(status_payload: dict[str, Any]) -> dict[str, Any] | None:
    error_count = int(status_payload.get("tool_events_error_count", 0) or 0)
    failure_count = int(status_payload.get("tool_events_failure_count", 0) or 0)
    last_error_summary = str(status_payload.get("last_tool_error_summary") or "").strip()
    stale = bool(status_payload.get("last_tool_error_stale", False))
    if not last_error_summary or stale or (error_count <= 0 and failure_count <= 0):
        return None

    tool_name = str(status_payload.get("last_tool_name") or "").strip()
    symbol = tool_name or last_error_summary.split(":", 1)[0].strip() or "tool_execution"
    return {
        "source": "tool_evidence",
        "signal_class": "runtime_failure",
        "title": "Tool execution has a current error event",
        "fingerprint": {
            "class": "runtime_failure",
            "surface": "tool_evidence",
            "error": "tool_execution_error",
            "symbol": symbol,
        },
        "payload": {
            "tool_events_error_count": error_count,
            "tool_events_failure_count": failure_count,
            "last_tool_error_summary": last_error_summary,
            "last_tool_error_ts": int(status_payload.get("last_tool_error_ts", 0) or 0),
            "last_tool_error_age_sec": status_payload.get("last_tool_error_age_sec"),
            "last_tool_name": tool_name,
            "last_tool_status": str(status_payload.get("last_tool_status") or "").strip(),
            "rationale": "Tool telemetry reports an error that has not been superseded by a later successful tool event.",
        },
        "severity": "medium",
        "actionability": "safe_now",
        "allowed_tools": ["read", "find", "queue_status"],
        "preferred_tool": "read",
        "next_task": TOOL_EVENTS_READ_TASK_TITLE,
        "task_sequence": [
            {
                "title": TOOL_EVENTS_READ_TASK_TITLE,
                "allowed_tools": ["read"],
                "preferred_tool": "read",
                "tool_args": ["runtime/tool_events.jsonl"],
            },
        ],
    }


def _release_readiness_signal_from_status(status_payload: dict[str, Any]) -> dict[str, Any] | None:
    release = status_payload.get("release_status") if isinstance(status_payload.get("release_status"), dict) else {}
    if not release:
        return None

    latest_state = str(release.get("latest_state") or "").strip().lower()
    readiness_state = str(release.get("latest_readiness_state") or "").strip().lower()
    ready_to_ship = bool(release.get("latest_ready_to_ship", False))
    artifact_path = str(release.get("latest_artifact_path") or "").strip()
    artifact_name = str(release.get("latest_artifact_name") or "").strip()
    ledger_path = str(release.get("ledger_path") or "").strip()
    validation_seed_path = str(release.get("latest_validation_seed_path") or "").strip()
    release_ok = bool(release.get("ok", True))

    if release_ok and ready_to_ship:
        return None
    if release_ok and latest_state in {"", "no-builds"} and readiness_state in {"", "no-builds"} and not artifact_path:
        return None

    if not release_ok:
        error_symbol = "release_status_unreadable"
        title = "Release status could not read release readiness truth"
        severity = "high"
        actionability = "safe_now"
        next_task = "Read release status and ledger parse failure before changing package state"
    elif readiness_state == "needs-verification":
        error_symbol = "release_needs_verification"
        title = "Release package exists without current verification"
        severity = "medium"
        actionability = "safe_now"
        next_task = "Read release ledger and verify the latest package before promotion judgment"
    elif readiness_state == "needs-promotion":
        error_symbol = "release_validation_outcome_missing"
        title = "Release package is verified but validation outcome is missing"
        severity = "medium"
        actionability = "safe_now"
        next_task = "Run release validation profile before release promotion judgment"
    elif readiness_state == "source-changed-after-build":
        error_symbol = "release_source_changed_after_build"
        title = "Release package is stale behind live source"
        severity = "high"
        actionability = "safe_now"
        next_task = "Read release source freshness and rebuild after current source changes settle"
    elif readiness_state == "blocked":
        error_symbol = "release_validation_blocked"
        title = "Release package has failing validation"
        severity = "high"
        actionability = "safe_now"
        next_task = "Read release validation failure and isolate the package blocker"
    else:
        error_symbol = "release_readiness_not_ready"
        title = "Release readiness is not ready to ship"
        severity = "medium"
        actionability = "blocked" if artifact_path else "safe_now"
        next_task = "Read release readiness state and ledger evidence"

    task_sequence: list[dict[str, Any]] = []
    if ledger_path:
        task_sequence.append({
            "title": "Read release ledger for current package",
            "allowed_tools": ["read"],
            "preferred_tool": "read",
            "tool_args": [ledger_path],
        })
    if validation_seed_path:
        task_sequence.append({
            "title": "Read release validation seed for current package",
            "allowed_tools": ["read"],
            "preferred_tool": "read",
            "tool_args": [validation_seed_path],
        })
    if readiness_state == "needs-promotion":
        if not bool(release.get("latest_validation_record_complete", False)):
            task_sequence.append({
                "title": "Run release validation profile from current artifact",
                "allowed_tools": ["release_validation_run"],
                "preferred_tool": "release_validation_run",
            })
        task_sequence.append({
            "title": "Run release promotion judgment from validation evidence",
            "allowed_tools": ["release_promotion_judgment"],
            "preferred_tool": "release_promotion_judgment",
        })
        task_sequence.append({
            "title": "Record completed validation outcome in release ledger",
            "allowed_tools": ["release_record_validation_outcome"],
            "preferred_tool": "release_record_validation_outcome",
        })
    newest_source_path = str(release.get("latest_source_newest_path") or "").strip()
    if readiness_state == "source-changed-after-build" and newest_source_path:
        task_sequence.append({
            "title": "Read newest changed source file after release build",
            "allowed_tools": ["read"],
            "preferred_tool": "read",
            "tool_args": [newest_source_path],
        })
    if readiness_state == "source-changed-after-build":
        task_sequence.append({
            "title": "Rebuild and verify release package from current source",
            "allowed_tools": ["release_rebuild_verify"],
            "preferred_tool": "release_rebuild_verify",
            "tool_args": ["work-tree-rebuild"],
        })
    blocked_task = ""
    blocked_reason = ""
    if actionability == "blocked":
        blocked_task = (
            "Complete release validation outcome before marking package ready"
            if readiness_state == "needs-promotion"
            else "Hold release readiness until blocking release evidence is resolved"
        )
        blocked_reason = (
            "release_validation_outcome_required"
            if readiness_state == "needs-promotion"
            else "release_readiness_blocked"
        )

    return {
        "source": "release",
        "signal_class": "release_readiness_gap",
        "title": title,
        "fingerprint": {
            "class": "release_readiness_gap",
            "surface": "release",
            "error": error_symbol,
            "symbol": artifact_name or artifact_path or "release_package",
        },
        "payload": {
            "release_status_ok": release_ok,
            "latest_state": latest_state or "unknown",
            "latest_readiness_state": readiness_state or "unknown",
            "latest_ready_to_ship": ready_to_ship,
            "latest_readiness_note": str(release.get("latest_readiness_note") or ""),
            "latest_artifact_path": artifact_path,
            "latest_artifact_name": artifact_name,
            "latest_version": str(release.get("latest_version") or ""),
            "latest_channel": str(release.get("latest_channel") or ""),
            "latest_label": str(release.get("latest_label") or ""),
            "latest_build_recorded_at": str(release.get("latest_build_recorded_at") or ""),
            "latest_verified_at": str(release.get("latest_verified_at") or ""),
            "latest_promoted_at": str(release.get("latest_promoted_at") or ""),
            "latest_validation_result": str(release.get("latest_validation_result") or ""),
            "latest_validation_seed_path": validation_seed_path,
            "latest_validation_record_exists": bool(release.get("latest_validation_record_exists", False)),
            "latest_validation_record_complete": bool(release.get("latest_validation_record_complete", False)),
            "latest_validation_record_result": str(release.get("latest_validation_record_result") or ""),
            "latest_validation_record_missing_fields": list(release.get("latest_validation_record_missing_fields") or []),
            "latest_validation_record_artifact_matches": bool(release.get("latest_validation_record_artifact_matches", False)),
            "latest_validation_record_ollama_expected": str(
                (release.get("latest_validation_record") or {}).get("ollama_expected")
                if isinstance(release.get("latest_validation_record"), dict)
                else ""
            ),
            "latest_artifact_stale": bool(release.get("latest_artifact_stale", False)),
            "latest_source_status": str(release.get("latest_source_status") or ""),
            "latest_source_changed_after_build": bool(release.get("latest_source_changed_after_build", False)),
            "latest_source_changed_after_build_count": int(release.get("latest_source_changed_after_build_count", 0) or 0),
            "latest_source_newest_path": newest_source_path,
            "latest_source_newest_mtime": str(release.get("latest_source_newest_mtime") or ""),
            "latest_source_changed_after_build_sample": list(release.get("latest_source_changed_after_build_sample") or []),
            "ledger_path": ledger_path,
            "rationale": "Release readiness status is present in control status but not ready to ship.",
        },
        "severity": severity,
        "actionability": actionability,
        "allowed_tools": ["read", "find", "system_check", "release_rebuild_verify"]
        if readiness_state == "source-changed-after-build"
        else ["read", "find", "system_check", "release_validation_run", "release_promotion_judgment", "release_record_validation_outcome"],
        "preferred_tool": "release_rebuild_verify"
        if readiness_state == "source-changed-after-build"
        else ("release_validation_run" if readiness_state == "needs-promotion" else "read"),
        "next_task": next_task,
        "task_sequence": task_sequence,
        "blocked_task": blocked_task,
        "blocked_reason": blocked_reason,
    }


def _next_sequence_task(branch_id: str, normalized: dict[str, Any]) -> dict[str, Any]:
    sequence = [
        dict(item)
        for item in list(normalized.get("task_sequence") or [])
        if isinstance(item, dict) and str(item.get("title") or "").strip()
    ]
    if not sequence:
        return {}
    for item in sequence:
        if not _sequence_item_satisfied(branch_id, item):
            return item
    return {}


def _first_sequence_task(normalized: dict[str, Any]) -> dict[str, Any]:
    for item in list(normalized.get("task_sequence") or []):
        if isinstance(item, dict) and str(item.get("title") or "").strip():
            return dict(item)
    return {}


def _sequence_has_tool(normalized: dict[str, Any], tool_name: str) -> bool:
    selected = str(tool_name or "").strip()
    if not selected:
        return False
    return any(
        selected in _task_tools(item)
        for item in list(normalized.get("task_sequence") or [])
        if isinstance(item, dict)
    )


def _branch_has_failed_execution_evidence(branch_id: str) -> bool:
    try:
        evidence_rows = work_tree.list_branch_evidence(branch_id, limit=200)
    except Exception:
        evidence_rows = []
    for row in evidence_rows:
        if not isinstance(row, dict):
            continue
        text = str(row.get("result_text") or "").strip().lower()
        if not text:
            continue
        if (
            text.startswith("[fail]")
            or '"ok": false' in text
            or "'ok': false" in text
            or " tool failed:" in text
            or "tool error:" in text
            or "unknown planned tool" in text
            or "llm service unavailable" in text
            or "ollama chat api unavailable" in text
            or "ollama chat failed" in text
        ):
            return True
    return False


def _branch_has_failed_evidence(branch_id: str) -> bool:
    return _branch_has_failed_execution_evidence(branch_id)


def _branch_has_source_root_failed_judgment(branch_id: str) -> bool:
    try:
        evidence_rows = work_tree.list_branch_evidence(branch_id, limit=200)
    except Exception:
        evidence_rows = []
    for row in evidence_rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("tool_name") or "").strip() != SOURCE_ROOT_JUDGMENT_TOOL:
            continue
        text = str(row.get("result_text") or "").strip().lower()
        if "evidence_failed" in text or "operator_outbox: needed (failed_evidence)" in text:
            return True
    return False


def _source_root_operator_reason_from_judgment_text(text: str) -> str:
    for line in str(text or "").splitlines():
        clean = line.strip()
        prefix = "- operator_outbox: needed ("
        if not clean.startswith(prefix) or not clean.endswith(")"):
            continue
        reason = clean[len(prefix):-1].strip()
        if reason and reason != "failed_evidence":
            return reason
    return ""


def _branch_source_root_operator_reason(branch_id: str) -> str:
    try:
        evidence_rows = work_tree.list_branch_evidence(branch_id, limit=200)
    except Exception:
        evidence_rows = []
    for row in reversed(evidence_rows):
        if not isinstance(row, dict):
            continue
        if str(row.get("tool_name") or "").strip() != SOURCE_ROOT_JUDGMENT_TOOL:
            continue
        reason = _source_root_operator_reason_from_judgment_text(str(row.get("result_text") or ""))
        if reason:
            return reason
    return ""


def _expected_source_root_operator_reason(normalized: dict[str, Any]) -> str:
    source = str(normalized.get("source") or "").strip().lower()
    work_class = str(normalized.get("work_class") or "").strip().lower()
    if source != "runtime_control" or work_class != "governance_pressure":
        return ""
    payload = normalized.get("payload") if isinstance(normalized.get("payload"), dict) else {}
    analytics = payload.get("runtime_restart_analytics") if isinstance(payload.get("runtime_restart_analytics"), dict) else {}
    provenance_status = str(
        analytics.get("restart_provenance_status") or payload.get("restart_provenance_status") or ""
    ).strip().lower()
    active_gap_count = _as_int(
        analytics.get("restart_origin_active_gap_count_1h")
        if "restart_origin_active_gap_count_1h" in analytics
        else payload.get("restart_origin_active_gap_count_1h"),
        0,
    )
    if provenance_status in {"incomplete", "gap", "missing"} or active_gap_count > 0:
        return "restart_provenance_operator_attribution_required"
    return ""


def _source_root_judgment_prerequisites_satisfied(branch_id: str, normalized: dict[str, Any]) -> bool:
    for item in list(normalized.get("task_sequence") or []):
        if not isinstance(item, dict):
            continue
        if SOURCE_ROOT_JUDGMENT_TOOL in _task_tools(item):
            return True
        if not _sequence_item_satisfied(branch_id, item):
            return False
    return False


def _sequence_item_expected_tools(item: dict[str, Any]) -> list[str]:
    allowed = [
        str(tool or "").strip()
        for tool in list(item.get("allowed_tools") or [])
        if str(tool or "").strip()
    ]
    preferred = str(item.get("preferred_tool") or "").strip()
    if preferred and preferred not in allowed:
        allowed.insert(0, preferred)
    return allowed


def _sequence_item_satisfied(branch_id: str, item: dict[str, Any]) -> bool:
    title = str(item.get("title") or "").strip()
    if not title:
        return True
    matching_tasks = [
        task
        for task in work_tree.list_branch_tasks(branch_id)
        if str(getattr(task, "title", "") or "").strip() == title
    ]
    if not matching_tasks:
        return False
    complete_task_ids = {
        str(getattr(task, "task_id", "") or "").strip()
        for task in matching_tasks
        if str(getattr(getattr(task, "status", ""), "value", getattr(task, "status", "")) or "").strip().lower() == "complete"
    }
    if not complete_task_ids:
        return False
    expected_tools = set(_sequence_item_expected_tools(item))
    if not expected_tools:
        return True
    try:
        evidence_rows = work_tree.list_branch_evidence(branch_id, limit=200)
    except Exception:
        evidence_rows = []
    return any(
        str(row.get("task_id") or "").strip() in complete_task_ids
        and str(row.get("tool_name") or "").strip() in expected_tools
        and _sequence_evidence_result_valid(row)
        for row in evidence_rows
        if isinstance(row, dict)
    )


def _sequence_evidence_result_valid(row: dict[str, Any]) -> bool:
    return evidence_result_valid(row)




def _has_capability_manifest_surface(status_payload: dict) -> bool:
    return any(
        key in status_payload
        for key in (
            "capabilities_registered",
            "capabilities_roadmap",
            "capability_gap_count",
            "capability_gaps",
        )
    )


def _capability_gap_signal_from_status(status_payload: dict) -> dict | None:
    """Generate signal when desired capabilities are not yet implemented."""
    if not _has_capability_manifest_surface(status_payload):
        return None

    gap_count = int(status_payload.get("capability_gap_count", 0) or 0)
    gaps = status_payload.get("capability_gaps")
    gap_list = [str(item or "").strip() for item in list(gaps or []) if str(item or "").strip()] if isinstance(gaps, list) else []

    if gap_count <= 0 and not gap_list:
        return None

    leah_gaps = [gap for gap in gap_list if gap.startswith("leah_")]
    execution_group = "leah_build" if leah_gaps else "generated_code"
    primary_capability = gap_list[0] if gap_list else "declared_capability_absent"

    error_symbol = "declared_capability_gap"
    title = f"Declared capability gap: {gap_count} capabilities not yet implemented"
    if gap_count == 1 and gap_list:
        title = f"Declared capability gap: {gap_list[0]}"
    if leah_gaps:
        title = f"Leah capability gap: {gap_count} capabilities not yet implemented"
        if gap_count == 1:
            title = f"Leah capability gap: {gap_list[0]}"

    task_sequence = [
        {
            "title": "Read capabilities roadmap manifest",
            "allowed_tools": ["read"],
            "preferred_tool": "read",
            "tool_args": ["capabilities_roadmap.json"],
        },
        {
            "title": "Read registered capabilities",
            "allowed_tools": ["read"],
            "preferred_tool": "read",
            "tool_args": ["capabilities.json"],
        },
        {
            "title": "Analyze capability gap and propose codegen specification",
            "allowed_tools": ["read", "find", "pulse"],
            "preferred_tool": "pulse",
        },
    ]
    if leah_gaps:
        task_sequence.insert(1, {
            "title": "Read Leah roadmap capabilities before generating Leah work",
            "allowed_tools": ["read"],
            "preferred_tool": "read",
            "tool_args": ["capabilities_roadmap.json"],
        })

    return {
        "source": "codegen_pipeline",
        "signal_class": "declared_capability_absent",
        "title": title,
        "fingerprint": {
            "class": "capability_gap",
            "surface": "codegen_pipeline",
            "error": "capability_absent",
            "symbol": error_symbol,
        },
        "payload": {
            "gap_count": gap_count,
            "gaps": gap_list[:5],
            "primary_capability": primary_capability,
            "execution_group": execution_group,
            "capability_prefixes": sorted({gap.split("_", 1)[0] for gap in gap_list if gap}),
            "leah_gap_count": len(leah_gaps),
        },
        "severity": "medium",
        "actionability": "safe_now",
        "allowed_tools": ["read", "find", "pulse"],
        "preferred_tool": "pulse",
        "next_task": "Review capabilities roadmap and prioritize next codegen work",
        "task_sequence": task_sequence,
    }

class WorkTreeSignalIngestionService:
    """Normalize runtime/control pressure into governed Work Tree branches only."""

    SIGNAL_TREE_KIND = "signal_ingestion"
    SIGNAL_TREE_SOURCE = "runtime_signals"
    SIGNAL_TREE_TITLE = "Signal Intake: Runtime Governance"

    def ingest_signal(self, signal: dict[str, Any]) -> dict[str, Any]:
        normalized = self._normalize_signal(signal)
        signal_class = str(normalized.get("signal_class") or "").strip().lower()
        if signal_class not in _VALID_SIGNAL_CLASSES:
            return {
                "action": "ignored",
                "tree_id": "",
                "branch_id": "",
                "reason": f"unsupported_signal_class:{signal_class or 'missing'}",
            }

        source_key = str(normalized.get("source_key") or "").strip()
        title = str(normalized.get("title") or "").strip()
        if not source_key or not title:
            return {
                "action": "ignored",
                "tree_id": "",
                "branch_id": "",
                "reason": "missing_title_or_fingerprint",
            }

        work_class = str(normalized.get("work_class") or "").strip().lower()
        actionability = str(normalized.get("actionability") or "").strip().lower()
        if not work_class or not actionability:
            return {
                "action": "ignored",
                "tree_id": "",
                "branch_id": "",
                "reason": "missing_work_mapping",
            }

        tree = self._ensure_signal_tree()
        root_branch = work_tree.get_branch(tree.root_branch_id)
        if root_branch is None:
            return {
                "action": "ignored",
                "tree_id": tree.tree_id,
                "branch_id": "",
                "reason": "root_branch_missing",
            }

        open_branch = self._find_branch_by_source_key(tree.tree_id, source_key, open_only=True)
        if open_branch is not None:
            self._apply_branch_update(open_branch, normalized, reopen=False)
            return {
                "action": "updated",
                "tree_id": tree.tree_id,
                "branch_id": open_branch.branch_id,
                "reason": "existing_open_branch",
            }

        closed_branch = self._find_branch_by_source_key(tree.tree_id, source_key, open_only=False)
        if closed_branch is not None:
            self._apply_branch_update(closed_branch, normalized, reopen=True)
            return {
                "action": "reopened",
                "tree_id": tree.tree_id,
                "branch_id": closed_branch.branch_id,
                "reason": "reopened_resolved_branch",
            }

        if not self._deserves_persisted_work(normalized):
            return {
                "action": "ignored",
                "tree_id": tree.tree_id,
                "branch_id": "",
                "reason": "non_actionable_transient",
            }

        branch = work_tree.add_branch_to_tree(
            tree.tree_id,
            title,
            _bucket_for_work_class(work_class),
            root_branch.branch_id,
        )
        self._apply_branch_update(branch, normalized, reopen=False, first_seen=True)

        return {
            "action": "created",
            "tree_id": tree.tree_id,
            "branch_id": branch.branch_id,
            "reason": "new_signal_branch",
        }

    def ingest_status_snapshot(self, status_payload: dict[str, Any]) -> list[dict[str, Any]]:
        signals: list[dict[str, Any]] = []
        alerts = [str(item or "").strip() for item in list(status_payload.get("alerts") or []) if str(item or "").strip()]
        for alert in alerts:
            low = alert.lower()
            if "error_spike" in low:
                signals.append({
                    "source": "http_api_control",
                    "signal_class": "error_spike",
                    "title": "Investigate control/status error spike",
                    "fingerprint": {
                        "class": "runtime_failure",
                        "surface": "http_api_control",
                        "error": "error_spike",
                        "symbol": "control_status",
                    },
                    "payload": {"alert": alert},
                    "severity": "high",
                    "actionability": "safe_now",
                    "allowed_tools": ["read", "find", "system_check", "pulse"],
                    "preferred_tool": "read",
                    "next_task": "Inspect control status logs and isolate failing endpoint path",
                    "task_sequence": [
                        _read_source_task("Read control status assembly", "services/control_status.py"),
                        _read_source_task("Read HTTP control transport", "nova_http.py"),
                        _read_source_task("Read control telemetry service", "services/control_telemetry.py"),
                        _read_source_task("Read control action audit ledger", "runtime/control_action_audit.jsonl"),
                    ],
                })
            if "ollama_api" in low:
                signals.append({
                    "source": "model_runtime",
                    "signal_class": "dependency_unreachable",
                    "title": "Ollama API unreachable",
                    "fingerprint": {
                        "class": "dependency_unreachable",
                        "surface": "model_runtime",
                        "error": "dependency_unreachable",
                        "symbol": "ollama_api",
                    },
                    "payload": {"alert": alert},
                    "severity": "medium",
                    "actionability": "safe_now",
                    "allowed_tools": ["os_capability", "system_check", "read", "find"],
                    "preferred_tool": "os_capability",
                    "next_task": "Verify Ollama model runtime contract through registered OS capability",
                    "task_sequence": _model_runtime_task_sequence(status_payload, {}, probe_chat=True),
                })

        signals.extend(_control_status_dependency_signals(status_payload))
        signals.extend(_model_runtime_dependency_signals(status_payload))
        voice_signal = _voice_status_signal_from_status(status_payload)
        if voice_signal is not None:
            signals.append(voice_signal)
        vision_signal = _vision_status_signal_from_status(status_payload)
        if vision_signal is not None:
            signals.append(vision_signal)
        signals.extend(_control_status_runtime_signals(status_payload))
        signals.extend(_control_status_maintenance_signals(status_payload))
        maintenance_error_signal = _autonomy_maintenance_error_signal_from_status(status_payload)
        if maintenance_error_signal is not None:
            signals.append(maintenance_error_signal)
        signals.extend(_runtime_failure_reason_signals_from_status(status_payload))
        runtime_restart_signal = _runtime_restart_signal_from_status(status_payload)
        if runtime_restart_signal is not None:
            signals.append(runtime_restart_signal)
        runtime_restart_provenance_signal = _runtime_restart_provenance_signal_from_status(status_payload)
        if runtime_restart_provenance_signal is not None:
            signals.append(runtime_restart_provenance_signal)
        storage_watch_signal = _storage_watch_signal_from_status(status_payload)
        if storage_watch_signal is not None:
            signals.append(storage_watch_signal)
        temporal_pressure_signal = _temporal_pressure_signal_from_status(status_payload)
        if temporal_pressure_signal is not None:
            signals.append(temporal_pressure_signal)
        patch_pipeline_signal = _patch_pipeline_signal_from_status(status_payload)
        if patch_pipeline_signal is not None:
            signals.append(patch_pipeline_signal)
        data_pipeline_signal = _data_pipeline_signal_from_status(status_payload)
        if data_pipeline_signal is not None:
            signals.append(data_pipeline_signal)
        for signal in (
            _frontdoor_cli_signal_from_status(status_payload),
            _operator_control_signal_from_status(status_payload),
            _policy_gates_signal_from_status(status_payload),
            _session_identity_auth_signal_from_status(status_payload),
            _identity_profile_answers_signal_from_status(status_payload),
            _conversation_routing_signal_from_status(status_payload),
            _supervisor_fulfillment_signal_from_status(status_payload),
            _reply_quality_contracts_signal_from_status(status_payload),
            _retrieval_knowledge_signal_from_status(status_payload),
            _weather_location_signal_from_status(status_payload),
            _installer_packaging_signal_from_status(status_payload),
            _tts_audio_output_signal_from_status(status_payload),
            _safety_envelope_signal_from_status(status_payload),
            _metrics_ops_journal_signal_from_status(status_payload),
            _core_steward_reflection_signal_from_status(status_payload),
        ):
            if signal is not None:
                signals.append(signal)
        if _has_wiring_inventory_surface(status_payload):
            wiring_inventory_signal = _wiring_inventory_signal_from_status(status_payload)
            if wiring_inventory_signal is not None:
                signals.append(wiring_inventory_signal)
        source_root_inventory_signal = _source_root_inventory_signal_from_status(status_payload)
        if source_root_inventory_signal is not None:
            signals.append(source_root_inventory_signal)
        source_wiring_probe_signal = _source_wiring_probe_signal_from_status(status_payload)
        if source_wiring_probe_signal is not None:
            signals.append(source_wiring_probe_signal)
        if _has_root_closure_inventory_surface(status_payload):
            signals.extend(_root_closure_inventory_signals_from_status(status_payload))
        if _has_self_repair_closure_inventory_surface(status_payload):
            signals.extend(_self_repair_closure_inventory_signals_from_status(status_payload))
        orchestrator_signal = _autonomy_orchestrator_signal_from_status(status_payload)
        if orchestrator_signal is not None:
            signals.append(orchestrator_signal)
        subconscious_status_signal = _subconscious_status_signal_from_status(status_payload)
        if subconscious_status_signal is not None:
            signals.append(subconscious_status_signal)
        action_ledger_signal = _action_ledger_signal_from_status(status_payload)
        if action_ledger_signal is not None:
            signals.append(action_ledger_signal)
        os_capability_ledger_signal = _os_capability_ledger_signal_from_status(status_payload)
        if os_capability_ledger_signal is not None:
            signals.append(os_capability_ledger_signal)
        http_conversation_signal = _http_conversation_signal_from_status(status_payload)
        if http_conversation_signal is not None:
            signals.append(http_conversation_signal)
        validation_truth_signal = _validation_artifact_truth_signal_from_status(status_payload)
        if validation_truth_signal is not None:
            signals.append(validation_truth_signal)
        test_profile_signal = _test_profile_inventory_signal_from_status(status_payload)
        if test_profile_signal is not None:
            signals.append(test_profile_signal)
        generated_queue_signal = _generated_queue_signal_from_status(status_payload)
        if generated_queue_signal is not None:
            signals.append(generated_queue_signal)
        tool_events_signal = _tool_events_signal_from_status(status_payload)
        if tool_events_signal is not None:
            signals.append(tool_events_signal)
        release_signal = _release_readiness_signal_from_status(status_payload)
        if release_signal is not None:
            signals.append(release_signal)

        capability_gap_signal = _capability_gap_signal_from_status(status_payload)
        if capability_gap_signal is not None:
            signals.append(capability_gap_signal)

        self_check_signal = _self_check_signal_from_status(status_payload, signals)
        if self_check_signal is not None:
            signals.append(self_check_signal)

        maintenance = status_payload.get("autonomy_maintenance") if isinstance(status_payload.get("autonomy_maintenance"), dict) else {}
        last_regression = str(maintenance.get("last_regression_status") or "").strip()
        last_regression_stale = bool(maintenance.get("last_regression_stale", False))
        if last_regression and "pass" not in last_regression.lower() and last_regression.lower() != "ok" and not last_regression_stale:
            signals.append({
                "source": "test_ecosystem",
                "signal_class": "regression_failure",
                "title": "Resolve regression/test failures from maintenance cycle",
                "fingerprint": {
                    "class": "regression_failure",
                    "surface": "test_ecosystem",
                    "error": "regression_failure",
                    "symbol": "daily_regression",
                },
                "payload": {
                    "test_ecosystem_signal": "daily_regression",
                    "last_regression_status": last_regression,
                },
                "severity": "high",
                "actionability": "safe_now",
                "allowed_tools": ["read", "find", "queue_status"],
                "preferred_tool": "read",
                "next_task": "Read regression status and runner evidence before isolating failures",
                "task_sequence": [
                    {
                        "title": "Read regression status from the maintenance cycle",
                        "allowed_tools": ["read"],
                        "preferred_tool": "read",
                        "tool_args": ["runtime/regression_status.json"],
                    },
                    {
                        "title": "Read regression runner contract for the failing lane",
                        "allowed_tools": ["read"],
                        "preferred_tool": "read",
                        "tool_args": ["scripts/run_regression.py"],
                    },
                    {
                        "title": "Find tests related to the failing regression lane",
                        "allowed_tools": ["find"],
                        "preferred_tool": "find",
                        "tool_args": [last_regression, "tests scripts services"],
                    },
                ],
            })

        memory_signal = _memory_health_signal_from_status(status_payload)
        if memory_signal is not None:
            signals.append(memory_signal)

        results: list[dict[str, Any]] = []
        for signal in signals:
            results.append(self.ingest_signal(signal))
        return results

    def sync_status_snapshot(self, status_payload: dict[str, Any]) -> list[dict[str, Any]]:
        results = list(self.ingest_status_snapshot(status_payload))
        alerts = [str(item or "").strip().lower() for item in list(status_payload.get("alerts") or [])]
        if "alerts" in status_payload and not any("error_spike" in alert for alert in alerts):
            results.extend(
                self.resolve_signal_branches(
                    signal_class="runtime_failure",
                    source="http_api_control",
                    reason="HTTP/control status alerts no longer report a control/status error spike.",
                )
            )
        if _has_dependency_surface(status_payload) and not _control_status_dependency_signals(status_payload):
            results.extend(
                self.resolve_signal_branches(
                    signal_class="dependency_unreachable",
                    source="web_search",
                    reason="Web search provider status reports no active search dependency outage.",
                )
            )
        if _has_model_runtime_surface(status_payload) and not _model_runtime_dependency_signals(status_payload):
            results.extend(
                self.resolve_signal_branches(
                    signal_class="dependency_unreachable",
                    source="model_runtime",
                    reason="Model runtime reports Ollama route, model, and listener ownership healthy.",
                )
            )
        if _voice_status_reports_clear(status_payload) and _voice_status_signal_from_status(status_payload) is None:
            results.extend(
                self.resolve_signal_branches(
                    signal_class="dependency_unreachable",
                    source="voice",
                    reason="Voice runtime reports requested dependencies loaded.",
                )
            )
        if _vision_status_reports_clear(status_payload) and _vision_status_signal_from_status(status_payload) is None:
            results.extend(
                self.resolve_signal_branches(
                    signal_class="dependency_unreachable",
                    source="vision",
                    reason="Vision runtime reports requested dependencies loaded.",
                )
            )
        if _has_runtime_surface(status_payload) and not _control_status_runtime_signals(status_payload):
            results.extend(
                self.resolve_signal_branches(
                    signal_class="runtime_failure",
                    source="runtime_core",
                    reason="Runtime core reports guard, core, HTTP UI, and heartbeat healthy.",
                )
            )
        if _has_maintenance_surface(status_payload) and not _control_status_maintenance_signals(status_payload):
            results.extend(
                self.resolve_signal_branches(
                    signal_class="maintenance_pressure",
                    source="scheduler_registry",
                    reason="Scheduler registry reports maintenance scheduler active.",
                )
            )
        if _has_autonomy_maintenance_error_surface(status_payload) and _autonomy_maintenance_error_signal_from_status(status_payload) is None:
            results.extend(
                self.resolve_signal_branches(
                    signal_class="maintenance_pressure",
                    source="autonomy_maintenance",
                    reason="Autonomy maintenance no longer reports a current error or stale worker identity.",
                )
            )
        if _has_runtime_failures_surface(status_payload) and not _runtime_failure_reason_signals_from_status(status_payload):
            results.extend(
                self.resolve_signal_branches(
                    signal_class="runtime_failure",
                    source="runtime_control",
                    reason="Runtime failure-reason telemetry reports all services healthy.",
                )
            )
        if _has_runtime_restart_surface(status_payload) and _runtime_restart_signal_from_status(status_payload) is None:
            results.extend(
                self.resolve_signal_branches(
                    signal_class="runtime_failure",
                    source="runtime_control",
                    reason="Runtime restart analytics no longer reports elevated restart pressure.",
                )
            )
        if _has_runtime_restart_surface(status_payload) and _runtime_restart_provenance_signal_from_status(status_payload) is None:
            results.extend(
                self.resolve_signal_branches(
                    signal_class="governance_pressure",
                    source="runtime_control",
                    reason="Runtime restart analytics now attributes recent restart origins.",
                )
            )
        if _has_storage_watch_surface(status_payload) and _storage_watch_signal_from_status(status_payload) is None:
            results.extend(
                self.resolve_signal_branches(
                    signal_class="maintenance_pressure",
                    source="storage_release_pressure",
                    reason="Storage watch reports normal snapshot and archive pressure.",
                )
            )
        if _has_patch_pipeline_surface(status_payload) and _patch_pipeline_signal_from_status(status_payload) is None:
            results.extend(
                self.resolve_signal_branches(
                    signal_class="governance_pressure",
                    source="patch_pipeline",
                    reason="Patch pipeline governance reports ready status.",
                )
            )
        if _has_data_pipeline_surface(status_payload) and _data_pipeline_signal_from_status(status_payload) is None:
            results.extend(
                self.resolve_signal_branches(
                    signal_class="governance_pressure",
                    source="data_pipelines",
                    reason="Data pipeline registry and active lanes report no current wiring blocker.",
                )
            )
        if _has_frontdoor_cli_surface(status_payload) and _frontdoor_cli_signal_from_status(status_payload) is None:
            results.extend(
                self.resolve_signal_branches(
                    signal_class="maintenance_pressure",
                    source="frontdoor_cli",
                    reason="Frontdoor CLI command surface reports readable command evidence.",
                )
            )
        operator_control_signal = _operator_control_signal_from_status(status_payload) if _has_operator_control_surface(status_payload) else None
        if _has_operator_control_surface(status_payload) and operator_control_signal is None:
            results.extend(
                self.resolve_signal_branches(
                    signal_class="operator_requested",
                    source="operator_control",
                    reason="Operator control outbox no longer has open operator work.",
                )
            )
            results.extend(
                self.resolve_signal_branches(
                    signal_class="maintenance_pressure",
                    source="operator_control",
                    reason="Operator control outbox reports readable state.",
                )
            )
        elif operator_control_signal is not None:
            normalized_operator_signal = self._normalize_signal(dict(operator_control_signal))
            active_key = str(normalized_operator_signal.get("source_key") or "").strip()
            if active_key:
                results.extend(
                    self.resolve_inactive_signal_branches(
                        signal_class=str(operator_control_signal.get("signal_class") or ""),
                        source="operator_control",
                        active_source_keys={active_key},
                        reason="Operator control pressure moved to the canonical operator outbox source key.",
                    )
                )
        if _has_policy_gates_surface(status_payload) and _policy_gates_signal_from_status(status_payload) is None:
            results.extend(
                self.resolve_signal_branches(
                    signal_class="governance_pressure",
                    source="policy_gates",
                    reason="Policy gates report no current action or observation blocker.",
                )
            )
        if _has_session_identity_auth_surface(status_payload) and _session_identity_auth_signal_from_status(status_payload) is None:
            results.extend(
                self.resolve_signal_branches(
                    signal_class="governance_pressure",
                    source="session_identity_auth",
                    reason="Session identity/auth status reports accountable chat identity state.",
                )
            )
        if _has_identity_profile_answers_surface(status_payload) and _identity_profile_answers_signal_from_status(status_payload) is None:
            results.extend(
                self.resolve_signal_branches(
                    signal_class="governance_pressure",
                    source="identity_profile_answers",
                    reason="Identity profile answer evidence reports required memory/profile parts present.",
                )
            )
        if _has_conversation_routing_surface(status_payload) and _conversation_routing_signal_from_status(status_payload) is None:
            results.extend(
                self.resolve_signal_branches(
                    signal_class="governance_pressure",
                    source="conversation_routing",
                    reason="Conversation routing evidence reports a complete planner decision and clean route trace.",
                )
            )
        if _has_supervisor_fulfillment_surface(status_payload) and _supervisor_fulfillment_signal_from_status(status_payload) is None:
            results.extend(
                self.resolve_signal_branches(
                    signal_class="governance_pressure",
                    source="supervisor_fulfillment",
                    reason="Supervisor/fulfillment route trace reports no active handoff gap.",
                )
            )
        if _has_reply_quality_contracts_surface(status_payload) and _reply_quality_contracts_signal_from_status(status_payload) is None:
            results.extend(
                self.resolve_signal_branches(
                    signal_class="governance_pressure",
                    source="reply_quality_contracts",
                    reason="Reply finalization reports a final answer and clean reply trace.",
                )
            )
        if _has_retrieval_knowledge_surface(status_payload) and _retrieval_knowledge_signal_from_status(status_payload) is None:
            results.extend(
                self.resolve_signal_branches(
                    signal_class="maintenance_pressure",
                    source="retrieval_knowledge",
                    reason="Retrieval/knowledge status reports usable context evidence.",
                )
            )
        if _has_weather_location_surface(status_payload) and _weather_location_signal_from_status(status_payload) is None:
            results.extend(
                self.resolve_signal_branches(
                    signal_class="dependency_unreachable",
                    source="weather_location",
                    reason="Weather/location status reports no active source or route gap.",
                )
            )
        if _has_installer_packaging_surface(status_payload) and _installer_packaging_signal_from_status(status_payload) is None:
            results.extend(
                self.resolve_signal_branches(
                    signal_class="release_readiness_gap",
                    source="installer_packaging",
                    reason="Installer packaging status reports no active release packaging gap.",
                )
            )
        if _has_tts_audio_output_surface(status_payload) and _tts_audio_output_signal_from_status(status_payload) is None:
            results.extend(
                self.resolve_signal_branches(
                    signal_class="dependency_unreachable",
                    source="tts_audio_output",
                    reason="TTS audio output status reports no active delivery dependency gap.",
                )
            )
        if _has_safety_envelope_surface(status_payload) and _safety_envelope_signal_from_status(status_payload) is None:
            results.extend(
                self.resolve_signal_branches(
                    signal_class="governance_pressure",
                    source="safety_envelope",
                    reason="Safety envelope reports no pending review or quarantine pressure.",
                )
            )
        if _has_metrics_ops_journal_surface(status_payload) and _metrics_ops_journal_signal_from_status(status_payload) is None:
            results.extend(
                self.resolve_signal_branches(
                    signal_class="maintenance_pressure",
                    source="metrics_ops_journal",
                    reason="Metrics and ops journal telemetry reports coherent readable state.",
                )
            )
        if _has_core_steward_reflection_surface(status_payload) and _core_steward_reflection_signal_from_status(status_payload) is None:
            results.extend(
                self.resolve_signal_branches(
                    signal_class="governance_pressure",
                    source="core_steward_reflection",
                    reason="Core steward reflection reports no current repair or watch pressure.",
                )
            )
        if _has_wiring_inventory_surface(status_payload) and _wiring_inventory_signal_from_status(status_payload) is None:
            results.extend(
                self.resolve_signal_branches(
                    signal_class="governance_pressure",
                    source="work_tree",
                    reason="Subsystem wiring inventory reports full source/status/signal/tool/action coverage.",
                )
            )
        if _has_source_root_inventory_surface(status_payload) and _source_root_inventory_signal_from_status(status_payload) is None:
            results.extend(
                self.resolve_signal_branches(
                    signal_class="governance_pressure",
                    source="source_root_inventory",
                    reason="Source root inventory reports every discovered root has a first-class wiring surface.",
                )
            )
        if _has_source_wiring_probe_surface(status_payload) and _source_wiring_probe_signal_from_status(status_payload) is None:
            results.extend(
                self.resolve_signal_branches(
                    signal_class="governance_pressure",
                    source="source_wiring_probe",
                    reason="Source wiring probe reports all required source-derived paths are present.",
                )
            )
        if _has_root_closure_inventory_surface(status_payload):
            root_closure_signals = _root_closure_inventory_signals_from_status(status_payload)
            if root_closure_signals:
                active_keys = {
                    self.source_key_for_signal(signal)
                    for signal in root_closure_signals
                    if self.source_key_for_signal(signal)
                }
                results.extend(
                    self.resolve_inactive_signal_branches(
                        signal_class="governance_pressure",
                        source="root_closure_inventory",
                        active_source_keys=active_keys,
                        reason="Root closure inventory moved to a newer active source signal.",
                    )
                )
            else:
                results.extend(
                    self.resolve_signal_branches(
                        signal_class="governance_pressure",
                        source="root_closure_inventory",
                        reason="Root closure inventory reports every declared root has status, signal, tool, and action wiring.",
                    )
                )
        if _has_self_repair_closure_inventory_surface(status_payload):
            self_repair_closure_signals = _self_repair_closure_inventory_signals_from_status(status_payload)
            if self_repair_closure_signals:
                active_keys = {
                    self.source_key_for_signal(signal)
                    for signal in self_repair_closure_signals
                    if self.source_key_for_signal(signal)
                }
                results.extend(
                    self.resolve_inactive_signal_branches(
                        signal_class="governance_pressure",
                        source="self_repair_closure_inventory",
                        active_source_keys=active_keys,
                        reason="Self-repair closure inventory moved to a newer active source signal.",
                    )
                )
            else:
                results.extend(
                    self.resolve_signal_branches(
                        signal_class="governance_pressure",
                        source="self_repair_closure_inventory",
                        reason=(
                            "Self-repair closure inventory reports every declared root has signal, action, "
                            "execution, evidence, judgment, closure, and operator outbox wiring."
                        ),
                    )
                )
        if _has_autonomy_orchestrator_surface(status_payload) and _autonomy_orchestrator_signal_from_status(status_payload) is None:
            results.extend(
                self.resolve_signal_branches(
                    signal_class="governance_pressure",
                    source="autonomy_orchestrator",
                    reason="Autonomy orchestrator no longer reports a current cycle failure, stale recommendation, or acknowledgement hold.",
                )
            )
        if _has_subconscious_status_surface(status_payload) and _subconscious_status_signal_from_status(status_payload) is None:
            results.extend(
                self.resolve_signal_branches(
                    signal_class="maintenance_pressure",
                    source="subconscious",
                    reason="Subconscious status reports a readable latest report.",
                )
            )
        if _has_action_ledger_surface(status_payload) and _action_ledger_signal_from_status(status_payload) is None:
            results.extend(
                self.resolve_signal_branches(
                    signal_class="maintenance_pressure",
                    source="action_ledger",
                    reason="Action ledger summary reports readable ledger state.",
                )
            )
        if _has_os_capability_ledger_surface(status_payload) and _os_capability_ledger_signal_from_status(status_payload) is None:
            results.extend(
                self.resolve_signal_branches(
                    signal_class="maintenance_pressure",
                    source="tool_registry_policy",
                    reason="OS capability ledger reports no unresolved capability execution evidence.",
                )
            )
        if _has_http_conversation_surface(status_payload) and _http_conversation_signal_from_status(status_payload) is None:
            results.extend(
                self.resolve_signal_branches(
                    signal_class="maintenance_pressure",
                    source="http_continuity",
                    reason="HTTP conversation status reports valid session telemetry.",
                )
            )
        if _has_validation_artifact_truth_surface(status_payload) and _validation_artifact_truth_signal_from_status(status_payload) is None:
            results.extend(
                self.resolve_signal_branches(
                    signal_class="regression_failure",
                    source="test_ecosystem",
                    payload_match={"test_ecosystem_signal": "validation_artifact_truth"},
                    reason="Validation action artifacts no longer disagree with the latest regression window.",
                )
            )
        if _has_test_profile_inventory_surface(status_payload) and _test_profile_inventory_signal_from_status(status_payload) is None:
            results.extend(
                self.resolve_signal_branches(
                    signal_class="governance_pressure",
                    source="test_ecosystem",
                    payload_match={"test_ecosystem_signal": "test_profile_inventory"},
                    reason="Validation profile inventory no longer reports source/test contract gaps.",
                )
            )
        if (
            _has_self_check_surface(status_payload)
            and _self_check_signal_from_status(status_payload, _self_check_routed_signals_from_status(status_payload)) is None
        ):
            results.extend(
                self.resolve_signal_branches(
                    signal_class="governance_pressure",
                    source="diagnostics_hygiene",
                    reason="Self-check alerts are either clear or owned by first-class signal branches.",
                )
            )
            results.extend(
                self.resolve_signal_branches(
                    signal_class="governance_pressure",
                    source="self_check",
                    reason="Legacy generic self-check branch is owned by a first-class signal branch.",
                )
            )
        if _has_generated_queue_surface(status_payload) and _generated_queue_signal_from_status(status_payload) is None:
            results.extend(
                self.resolve_signal_branches(
                    signal_class="maintenance_pressure",
                    source="generated_queue",
                    reason="Generated Work Queue no longer reports a blocked no-actionable state.",
                )
            )
        if _has_tool_events_surface(status_payload) and _tool_events_signal_from_status(status_payload) is None:
            results.extend(
                self.resolve_signal_branches(
                    signal_class="runtime_failure",
                    source="tool_evidence",
                    reason="Tool telemetry no longer reports a current unsuperseded tool error.",
                )
            )
        temporal_surface_present = any(
            key in status_payload
            for key in ("temporal_enabled", "temporal_pressure", "temporal_event", "temporal_events")
        )
        if temporal_surface_present:
            temporal_signal = _temporal_pressure_signal_from_status(status_payload)
            if temporal_signal is None:
                results.extend(
                    self.resolve_signal_branches(
                        signal_class="temporal_pressure",
                        source="",
                        reason="Temporal feed reports no active surfaced calendar pressure.",
                    )
                )
            else:
                active_key = self.source_key_for_signal(temporal_signal)
                results.extend(
                    self.resolve_inactive_signal_branches(
                        signal_class="temporal_pressure",
                        source="",
                        active_source_keys={active_key} if active_key else set(),
                        reason="Temporal feed moved to a newer active source signal.",
                    )
                )
        maintenance = status_payload.get("autonomy_maintenance") if isinstance(status_payload.get("autonomy_maintenance"), dict) else {}
        last_regression = str(maintenance.get("last_regression_status") or "").strip()
        last_regression_stale = bool(maintenance.get("last_regression_stale", False))
        regression_active = bool(
            last_regression
            and "pass" not in last_regression.lower()
            and last_regression.lower() != "ok"
            and not last_regression_stale
        )
        if _has_regression_surface(status_payload) and not regression_active:
            if last_regression_stale:
                reason = "Regression failure aged stale in maintenance state."
            elif last_regression:
                reason = "Regression failure cleared in maintenance state."
            else:
                reason = "No active regression failure remains in maintenance state."
            results.extend(
                self.resolve_signal_branches(
                    signal_class="regression_failure",
                    source="test_ecosystem",
                    payload_match={"test_ecosystem_signal": "daily_regression"},
                    reason=reason,
                )
            )
        if _has_release_surface(status_payload):
            release_signal = _release_readiness_signal_from_status(status_payload)
            if release_signal is None:
                results.extend(
                    self.resolve_signal_branches(
                        signal_class="release_readiness_gap",
                        source="release",
                        reason="Release status no longer reports an active readiness gap.",
                    )
                )
            else:
                active_key = self.source_key_for_signal(release_signal)
                results.extend(
                    self.resolve_inactive_signal_branches(
                        signal_class="release_readiness_gap",
                        source="release",
                        active_source_keys={active_key} if active_key else set(),
                        reason="Release readiness moved to a newer active source signal.",
                    )
                )
        if _has_memory_surface(status_payload) and _memory_health_signal_from_status(status_payload) is None:
            results.extend(
                self.resolve_signal_branches(
                    signal_class="governance_pressure",
                    source="memory_identity",
                    reason="Memory health no longer reports an active persistence bootstrap gap.",
                )
            )
        return results

    def resolve_signal_branches(
        self,
        *,
        signal_class: str,
        source: str = "",
        reason: str = "",
        payload_match: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        tree = self._find_signal_tree()
        if tree is None:
            return []

        target_work_class = _SIGNAL_TO_WORK_CLASS.get(str(signal_class or "").strip().lower(), "")
        normalized_source = str(source or "").strip().lower()
        expected_payload = {
            str(key): str(value or "").strip()
            for key, value in dict(payload_match or {}).items()
            if str(key or "").strip()
        }
        note = str(reason or "").strip() or "Signal no longer active."
        results: list[dict[str, Any]] = []
        now = datetime.now()

        for branch in work_tree.list_tree_branches(tree.tree_id):
            if branch.branch_id == tree.root_branch_id:
                continue
            if target_work_class and str(getattr(branch, "work_class", "") or "").strip().lower() != target_work_class:
                continue
            if normalized_source and str(getattr(branch, "source_type", "") or "").strip().lower() != normalized_source:
                continue
            if expected_payload:
                branch_payload = dict(getattr(branch, "source_payload", {}) or {})
                if any(str(branch_payload.get(key) or "").strip() != value for key, value in expected_payload.items()):
                    continue
            resolution = str(getattr(branch, "resolution_state", "") or "").strip().lower()
            if resolution in {"resolved", "retired"} and branch.status == BranchStatus.COMPLETE:
                continue
            for task in work_tree.list_branch_tasks(branch.branch_id):
                status = str(getattr(getattr(task, "status", None), "value", getattr(task, "status", "")) or "").strip().lower()
                if status in {"complete", "dropped"}:
                    continue
                work_tree.mark_task_complete(task.task_id)
            branch.status = BranchStatus.COMPLETE
            branch.resolution_state = "resolved"
            branch.priority = 0
            branch.allowed_tools = []
            branch.preferred_tool = None
            branch.last_seen_at = now
            existing_notes = str(branch.notes or "").strip()
            if note and note not in existing_notes:
                branch.notes = f"{existing_notes}\nResolution: {note}".strip() if existing_notes else f"Resolution: {note}"
            work_tree.touch_branch(branch.branch_id)
            results.append(
                {
                    "action": "resolved",
                    "tree_id": tree.tree_id,
                    "branch_id": branch.branch_id,
                    "reason": note,
                }
            )
        return results

    def source_key_for_signal(self, signal: dict[str, Any]) -> str:
        return str(self._normalize_signal(signal).get("source_key") or "").strip()

    def _preserve_inactive_signal_branch(self, *, branch: Any, note: str, now: datetime) -> bool:
        hold_reason = "inactive_signal_requires_fix_evidence"
        hold_title = "Hold latent root-repair signal until fix evidence confirms closure"
        changed = False

        open_tasks = []
        for task in work_tree.list_branch_tasks(branch.branch_id):
            status = str(getattr(getattr(task, "status", None), "value", getattr(task, "status", "")) or "").strip().lower()
            if status in {"complete", "dropped"}:
                continue
            open_tasks.append(task)

        if not open_tasks:
            task = work_tree.add_task_to_branch(
                branch.branch_id,
                hold_title,
                meta={
                    "inactive_signal_observation": True,
                    "blocked_reason": hold_reason,
                    "block_reason": hold_reason,
                    "inactive_signal_reason": note,
                },
            )
            open_tasks.append(task)
            changed = True

        for task in open_tasks:
            status = str(getattr(getattr(task, "status", None), "value", getattr(task, "status", "")) or "").strip().lower()
            meta = dict(getattr(task, "meta", {}) or {})
            if meta.get("inactive_signal_observation") and str(getattr(task, "title", "") or "") != hold_title:
                work_tree.update_blocked_task(task.task_id, title=hold_title, reason=hold_reason)
                changed = True
                continue
            if status != "blocked" or meta.get("blocked_reason") != hold_reason or meta.get("block_reason") != hold_reason:
                work_tree.update_blocked_task(task.task_id, reason=hold_reason)
                changed = True

        if branch.status != BranchStatus.BLOCKED:
            branch.status = BranchStatus.BLOCKED
            changed = True
        if str(getattr(branch, "resolution_state", "") or "").strip().lower() != "observing":
            branch.resolution_state = "observing"
            changed = True
        if int(getattr(branch, "priority", 0) or 0) < 55:
            branch.priority = 55
            changed = True
        if list(getattr(branch, "allowed_tools", []) or []):
            branch.allowed_tools = []
            changed = True
        if getattr(branch, "preferred_tool", None):
            branch.preferred_tool = None
            changed = True

        observation = (
            f"Observation: {note} "
            "Root repair remains open until fix evidence or synthesized judgment confirms closure."
        )
        existing_notes = str(getattr(branch, "notes", "") or "").strip()
        if observation and observation not in existing_notes:
            branch.notes = f"{existing_notes}\n{observation}".strip() if existing_notes else observation
            changed = True

        if changed:
            branch.last_seen_at = now
            work_tree.touch_branch(branch.branch_id)
        return changed

    def resolve_inactive_signal_branches(
        self,
        *,
        signal_class: str,
        source: str,
        active_source_keys: set[str],
        reason: str = "",
        resolution_mode: str = "resolve",
    ) -> list[dict[str, Any]]:
        tree = self._find_signal_tree()
        if tree is None:
            return []

        target_work_class = _SIGNAL_TO_WORK_CLASS.get(str(signal_class or "").strip().lower(), "")
        normalized_source = str(source or "").strip().lower()
        active_keys = {str(item or "").strip() for item in set(active_source_keys or set()) if str(item or "").strip()}
        note = str(reason or "").strip() or "Signal disappeared from the latest active signal set."
        mode = str(resolution_mode or "resolve").strip().lower()
        preserve_as_observation = mode in {"observe", "observing", "preserve", "preserved", "hold"}
        retire_inactive = mode in {"retire", "retired", "retire_inactive", "retired_inactive"}
        results: list[dict[str, Any]] = []
        now = datetime.now()

        for branch in work_tree.list_tree_branches(tree.tree_id):
            if branch.branch_id == tree.root_branch_id:
                continue
            if target_work_class and str(getattr(branch, "work_class", "") or "").strip().lower() != target_work_class:
                continue
            if normalized_source and str(getattr(branch, "source_type", "") or "").strip().lower() != normalized_source:
                continue
            source_key = str(getattr(branch, "source_key", "") or "").strip()
            if source_key in active_keys:
                continue
            resolution = str(getattr(branch, "resolution_state", "") or "").strip().lower()
            if preserve_as_observation:
                if resolution in {"retired", "archived"} or branch.status == BranchStatus.ARCHIVED:
                    continue
                if self._preserve_inactive_signal_branch(branch=branch, note=note, now=now):
                    results.append(
                        {
                            "action": "observing",
                            "tree_id": tree.tree_id,
                            "branch_id": branch.branch_id,
                            "reason": note,
                        }
                    )
                continue
            if resolution in {"resolved", "retired"} and branch.status == BranchStatus.COMPLETE:
                continue
            for task in work_tree.list_branch_tasks(branch.branch_id):
                status = str(getattr(getattr(task, "status", None), "value", getattr(task, "status", "")) or "").strip().lower()
                if status in {"complete", "dropped"}:
                    continue
                work_tree.mark_task_complete(task.task_id)
            branch.status = BranchStatus.COMPLETE
            branch.resolution_state = "retired" if retire_inactive else "resolved"
            branch.priority = 0
            branch.allowed_tools = []
            branch.preferred_tool = None
            branch.last_seen_at = now
            existing_notes = str(branch.notes or "").strip()
            if note and note not in existing_notes:
                prefix = "Retired" if retire_inactive else "Resolution"
                branch.notes = f"{existing_notes}\n{prefix}: {note}".strip() if existing_notes else f"{prefix}: {note}"
            work_tree.touch_branch(branch.branch_id)
            results.append(
                {
                    "action": "retired" if retire_inactive else "resolved",
                    "tree_id": tree.tree_id,
                    "branch_id": branch.branch_id,
                    "reason": note,
                }
            )
        return results

    def _find_signal_tree(self):
        candidates = []
        for tree in work_tree.list_trees():
            meta = dict(getattr(tree, "meta", {}) or {})
            if str(meta.get("kind") or "").strip().lower() == self.SIGNAL_TREE_KIND:
                status = str(getattr(getattr(tree, "status", ""), "value", getattr(tree, "status", "")) or "").strip().lower()
                if status == "archived":
                    continue
                candidates.append(tree)
        candidates.sort(
            key=lambda item: (
                0 if str(getattr(getattr(item, "status", ""), "value", getattr(item, "status", "")) or "").strip().lower() == "active" else 1,
                getattr(item, "created_at", datetime.max),
                str(getattr(item, "tree_id", "")),
            )
        )
        return candidates[0] if candidates else None

    def _ensure_signal_tree(self):
        existing = self._find_signal_tree()
        if existing is not None:
            canonical_id = str(getattr(existing, "tree_id", "") or "")
            for tree in work_tree.list_trees():
                meta = dict(getattr(tree, "meta", {}) or {})
                if str(meta.get("kind") or "").strip().lower() != self.SIGNAL_TREE_KIND:
                    continue
                tree_id = str(getattr(tree, "tree_id", "") or "")
                status = str(getattr(getattr(tree, "status", ""), "value", getattr(tree, "status", "")) or "").strip().lower()
                if not tree_id or tree_id == canonical_id or status == "archived":
                    continue
                work_tree.archive_tree(
                    tree_id,
                    reason=f"Duplicate Signal Intake retired; canonical signal tree is {canonical_id}.",
                )
            meta = dict(getattr(existing, "meta", {}) or {})
            policy = meta.get("execution_policy") if isinstance(meta.get("execution_policy"), dict) else {}
            allowed = [
                str(item or "").strip()
                for item in list(policy.get("allowed_tools") or [])
                if str(item or "").strip()
            ]
            needed_tools = work_tree.default_tree_allowed_tools()
            missing_tools = [tool for tool in needed_tools if tool not in allowed]
            if missing_tools:
                work_tree.set_tree_execution_policy(
                    existing.tree_id,
                    allowed_tools=allowed + missing_tools if allowed else needed_tools,
                    require_explicit_allow=bool(policy.get("require_explicit_allow", True)),
                )
            return existing
        return work_tree.initialize_tree(
            self.SIGNAL_TREE_TITLE,
            meta={
                "kind": self.SIGNAL_TREE_KIND,
                "source": self.SIGNAL_TREE_SOURCE,
                "signal_ingestion": True,
            },
        )

    def _find_branch_by_source_key(self, tree_id: str, source_key: str, *, open_only: bool) -> Any | None:
        for branch in work_tree.list_tree_branches(tree_id):
            if str(getattr(branch, "source_key", "") or "").strip() != source_key:
                continue
            resolution = str(getattr(branch, "resolution_state", "") or "").strip().lower()
            if open_only and resolution in {"resolved", "retired"}:
                continue
            return branch
        return None

    def _deserves_persisted_work(self, normalized: dict[str, Any]) -> bool:
        actionability = str(normalized.get("actionability") or "").strip().lower()
        severity = str(normalized.get("severity") or "").strip().lower()
        if actionability == "dead_end" and severity in {"", "info", "low"}:
            return False
        return True

    def _apply_branch_update(
        self,
        branch,
        normalized: dict[str, Any],
        *,
        reopen: bool,
        first_seen: bool = False,
    ) -> None:
        now = datetime.now()
        actionability = str(normalized.get("actionability") or "safe_now").strip().lower()
        work_class = str(normalized.get("work_class") or "").strip().lower()
        severity = str(normalized.get("severity") or "medium").strip().lower()

        branch.title = str(normalized.get("title") or branch.title)
        branch.bucket = _bucket_for_work_class(work_class)
        branch.source_type = str(normalized.get("source") or "") or None
        branch.source_key = str(normalized.get("source_key") or "") or None
        branch.source_payload = dict(normalized.get("payload") or {})
        branch.work_class = work_class
        branch.actionability = actionability
        branch.resolution_state = _RESOLUTION_BY_ACTIONABILITY.get(actionability, "open")
        branch.last_seen_at = now

        score = _score_for_signal(severity, actionability)
        branch.priority = int(max(branch.priority, score)) if not first_seen else int(score)

        if first_seen:
            branch.evidence_count = 1
        else:
            branch.evidence_count = int(branch.evidence_count or 0) + 1

        branch.status = _BRANCH_STATUS_BY_ACTIONABILITY.get(actionability, BranchStatus.READY)
        if reopen:
            branch.resolution_state = _RESOLUTION_BY_ACTIONABILITY.get(actionability, "open")
            if branch.status == BranchStatus.COMPLETE:
                branch.status = _BRANCH_STATUS_BY_ACTIONABILITY.get(actionability, BranchStatus.READY)

        explicit_tools = [
            str(tool or "").strip()
            for tool in list(normalized.get("allowed_tools") or [])
            if str(tool or "").strip()
        ]
        preferred_tool = str(normalized.get("preferred_tool") or "").strip()
        if explicit_tools:
            work_tree.set_branch_tools(
                branch.branch_id,
                allowed_tools=explicit_tools,
                preferred_tool=preferred_tool if preferred_tool in explicit_tools else explicit_tools[0],
            )
        else:
            work_tree.set_branch_tools(branch.branch_id, allowed_tools=[], preferred_tool="")

        summary = _branch_why_summary(normalized)
        existing_notes = _strip_inactive_resolution_notes(str(branch.notes or "").strip())
        if existing_notes != str(branch.notes or "").strip():
            branch.notes = existing_notes
        if summary and summary not in existing_notes:
            branch.notes = f"{existing_notes}\n{summary}".strip() if existing_notes else summary

        work_tree.touch_branch(branch.branch_id)

        next_task = str(normalized.get("next_task") or "").strip()
        blocked_task = str(normalized.get("blocked_task") or "").strip()
        sequence_configured = bool(list(normalized.get("task_sequence") or []))
        if (next_task or sequence_configured or blocked_task) and actionability != "dead_end":
            task_text = next_task
            task_allowed_tools = list(explicit_tools)
            task_preferred_tool = preferred_tool
            sequence_task = _next_sequence_task(branch.branch_id, normalized)
            if sequence_task:
                task_text = str(sequence_task.get("title") or "").strip()
                task_allowed_tools = [
                    str(tool or "").strip()
                    for tool in list(sequence_task.get("allowed_tools") or [])
                    if str(tool or "").strip()
                ] or task_allowed_tools
                task_preferred_tool = str(sequence_task.get("preferred_tool") or "").strip() or task_preferred_tool
            elif sequence_configured:
                task_text = ""
                task_allowed_tools = []
                task_preferred_tool = ""
            open_tasks = [
                task
                for task in work_tree.list_branch_tasks(branch.branch_id)
                if str(getattr(task.status, "value", task.status) or "").strip().lower() not in {"complete", "dropped"}
            ]
            blocked_open_tasks = bool(open_tasks) and all(
                str(getattr(task.status, "value", task.status) or "").strip().lower() == "blocked"
                for task in open_tasks
            )
            failed_source_root_evidence = (
                sequence_configured
                and _sequence_has_tool(normalized, SOURCE_ROOT_JUDGMENT_TOOL)
                and _branch_has_failed_evidence(branch.branch_id)
            )
            source_root_failed_judged = failed_source_root_evidence and _branch_has_source_root_failed_judgment(branch.branch_id)
            source_root_operator_reason = ""
            if sequence_configured and _sequence_has_tool(normalized, SOURCE_ROOT_JUDGMENT_TOOL):
                source_root_operator_reason = _branch_source_root_operator_reason(branch.branch_id)
            expected_source_root_operator_reason = _expected_source_root_operator_reason(normalized)
            if (
                expected_source_root_operator_reason
                and not source_root_operator_reason
                and _source_root_judgment_prerequisites_satisfied(branch.branch_id, normalized)
                and not any(
                    str(getattr(task, "title", "") or "").strip() == SOURCE_ROOT_JUDGMENT_TASK_TITLE
                    for task in open_tasks
                )
            ):
                for task in open_tasks:
                    work_tree.mark_task_dropped(
                        task.task_id,
                        reason=f"source_root_judgment_stale_for:{expected_source_root_operator_reason}",
                    )
                open_tasks = []
                blocked_open_tasks = False
                sequence_task = _source_root_judgment_task()
                task_text = str(sequence_task.get("title") or "").strip()
                task_allowed_tools = [
                    str(tool or "").strip()
                    for tool in list(sequence_task.get("allowed_tools") or [])
                    if str(tool or "").strip()
                ]
                task_preferred_tool = str(sequence_task.get("preferred_tool") or "").strip()
            if source_root_failed_judged and not blocked_open_tasks:
                for task in open_tasks:
                    work_tree.mark_task_dropped(
                        task.task_id,
                        reason="source_root_failed_evidence_judged",
                    )
                blocked = work_tree.add_task_to_branch(
                    branch.branch_id,
                    "Hold source-root branch for operator/tool failure judgment",
                    meta={"blocked_reason": "source_root_failed_evidence_operator_judgment_required"},
                )
                work_tree.mark_task_blocked(
                    blocked.task_id,
                    "source_root_failed_evidence_operator_judgment_required",
                )
                open_tasks = [blocked]
                blocked_open_tasks = True
                sequence_task = {}
                task_text = ""
                task_allowed_tools = []
                task_preferred_tool = ""
            elif source_root_failed_judged and blocked_open_tasks:
                sequence_task = {}
                task_text = ""
                task_allowed_tools = []
                task_preferred_tool = ""
            elif source_root_operator_reason and not blocked_open_tasks:
                for task in open_tasks:
                    work_tree.mark_task_dropped(
                        task.task_id,
                        reason=f"source_root_operator_judgment:{source_root_operator_reason}",
                    )
                blocked = work_tree.add_task_to_branch(
                    branch.branch_id,
                    "Hold source-root branch for operator judgment",
                    meta={"blocked_reason": source_root_operator_reason},
                )
                work_tree.mark_task_blocked(
                    blocked.task_id,
                    source_root_operator_reason,
                )
                open_tasks = [blocked]
                blocked_open_tasks = True
                sequence_task = {}
                task_text = ""
                task_allowed_tools = []
                task_preferred_tool = ""
            elif source_root_operator_reason and blocked_open_tasks:
                sequence_task = {}
                task_text = ""
                task_allowed_tools = []
                task_preferred_tool = ""
            if failed_source_root_evidence and not any(
                str(getattr(task, "title", "") or "").strip() == SOURCE_ROOT_JUDGMENT_TASK_TITLE
                for task in open_tasks
            ) and not source_root_failed_judged:
                for task in open_tasks:
                    work_tree.mark_task_dropped(
                        task.task_id,
                        reason="failed_evidence_to_source_root_judgment",
                    )
                open_tasks = []
                blocked_open_tasks = False
                sequence_task = _source_root_judgment_task()
                task_text = str(sequence_task.get("title") or "").strip()
                task_allowed_tools = [
                    str(tool or "").strip()
                    for tool in list(sequence_task.get("allowed_tools") or [])
                    if str(tool or "").strip()
                ]
                task_preferred_tool = str(sequence_task.get("preferred_tool") or "").strip()
            judgment_already_complete = _sequence_has_tool(normalized, SOURCE_ROOT_JUDGMENT_TOOL) and _sequence_item_satisfied(
                branch.branch_id, _source_root_judgment_task()
            )
            if (
                not open_tasks
                and sequence_configured
                and not sequence_task
                and str(branch.resolution_state or "").strip().lower() == "open"
                and _sequence_has_tool(normalized, SOURCE_ROOT_JUDGMENT_TOOL)
                and not judgment_already_complete
            ):
                sequence_task = _first_sequence_task(normalized)
                if sequence_task:
                    task_text = str(sequence_task.get("title") or "").strip()
                    task_allowed_tools = [
                        str(tool or "").strip()
                        for tool in list(sequence_task.get("allowed_tools") or [])
                        if str(tool or "").strip()
                    ] or task_allowed_tools
                    task_preferred_tool = str(sequence_task.get("preferred_tool") or "").strip() or task_preferred_tool
            source_name = str(normalized.get("source") or "").strip().lower()
            realign_blocked_sequence = source_name == "subconscious" or (
                source_name == "memory_identity"
                and str((normalized.get("payload") or {}).get("memory_bootstrap_origin", {}).get("status") or "").strip().lower() == "ready"
            )
            if open_tasks and sequence_configured and sequence_task and task_text and (not blocked_open_tasks or realign_blocked_sequence):
                open_title = str(getattr(open_tasks[0], "title", "") or "").strip()
                if open_title != task_text:
                    for task in open_tasks:
                        work_tree.mark_task_dropped(
                            task.task_id,
                            reason=f"sequence_realigned_to:{task_text}",
                        )
                    open_tasks = []
                    blocked_open_tasks = False
            if open_tasks and sequence_configured:
                open_title = str(getattr(open_tasks[0], "title", "") or "").strip()
                for item in list(normalized.get("task_sequence") or []):
                    if not isinstance(item, dict):
                        continue
                    if str(item.get("title") or "").strip() != open_title:
                        continue
                    task_allowed_tools = [
                        str(tool or "").strip()
                        for tool in list(item.get("allowed_tools") or [])
                        if str(tool or "").strip()
                    ]
                    task_preferred_tool = str(item.get("preferred_tool") or "").strip()
                    meta_updates: dict[str, object] = {}
                    if task_preferred_tool:
                        meta_updates["expected_tool"] = task_preferred_tool
                    if task_allowed_tools:
                        meta_updates["allowed_tools"] = list(task_allowed_tools)
                    if isinstance(item.get("tool_args"), list):
                        meta_updates["tool_args"] = [str(arg) for arg in list(item.get("tool_args") or [])]
                    if meta_updates:
                        work_tree.update_task_meta(open_tasks[0].task_id, meta_updates)
                    break
            if not open_tasks and task_text:
                task_meta: dict[str, object] = {}
                if task_preferred_tool:
                    task_meta["expected_tool"] = task_preferred_tool
                if task_allowed_tools:
                    task_meta["allowed_tools"] = list(task_allowed_tools)
                if isinstance(sequence_task.get("tool_args"), list):
                    task_meta["tool_args"] = [str(arg) for arg in list(sequence_task.get("tool_args") or [])]
                work_tree.add_task_to_branch(branch.branch_id, task_text, meta=task_meta)
            elif not open_tasks and blocked_task:
                blocked_reason = str(normalized.get("blocked_reason") or "").strip() or MEMORY_BOOTSTRAP_ORIGIN_CONTRACT_REQUIRED
                task = work_tree.add_task_to_branch(
                    branch.branch_id,
                    blocked_task,
                    meta={"blocked_reason": blocked_reason},
                )
                work_tree.mark_task_blocked(task.task_id, blocked_reason)
                blocked_open_tasks = True
            elif blocked_open_tasks and blocked_task:
                blocked_reason = str(normalized.get("blocked_reason") or "").strip() or MEMORY_BOOTSTRAP_ORIGIN_CONTRACT_REQUIRED
                for task in open_tasks:
                    if str(getattr(task.status, "value", task.status) or "").strip().lower() != "blocked":
                        continue
                    work_tree.update_blocked_task(task.task_id, title=blocked_task, reason=blocked_reason)
            elif blocked_open_tasks and not blocked_task and task_text:
                for task in open_tasks:
                    work_tree.mark_task_dropped(
                        task.task_id,
                        reason=f"blocked_task_released_to:{task_text}",
                    )
                open_tasks = []
                blocked_open_tasks = False
                task_meta: dict[str, object] = {}
                if task_preferred_tool:
                    task_meta["expected_tool"] = task_preferred_tool
                if task_allowed_tools:
                    task_meta["allowed_tools"] = list(task_allowed_tools)
                if isinstance(sequence_task.get("tool_args"), list):
                    task_meta["tool_args"] = [str(arg) for arg in list(sequence_task.get("tool_args") or [])]
                work_tree.add_task_to_branch(branch.branch_id, task_text, meta=task_meta)
            if blocked_open_tasks:
                work_tree.set_branch_tools(branch.branch_id, allowed_tools=[], preferred_tool="")
            elif task_allowed_tools:
                work_tree.set_branch_tools(
                    branch.branch_id,
                    allowed_tools=task_allowed_tools,
                    preferred_tool=task_preferred_tool if task_preferred_tool in task_allowed_tools else task_allowed_tools[0],
                )

    def _normalize_signal(self, signal: dict[str, Any]) -> dict[str, Any]:
        source = str(signal.get("source") or "").strip().lower() or "control_status"
        incoming_class = str(signal.get("signal_class") or "").strip().lower()
        work_class = _SIGNAL_TO_WORK_CLASS.get(incoming_class, "")

        payload = signal.get("payload") if isinstance(signal.get("payload"), dict) else {}
        severity = str(signal.get("severity") or "medium").strip().lower()
        if severity not in {"critical", "high", "medium", "low", "info"}:
            severity = "medium"

        actionability = str(signal.get("actionability") or "").strip().lower()
        if actionability not in {"safe_now", "blocked", "dead_end"}:
            actionability = _DEFAULT_ACTIONABILITY_BY_CLASS.get(work_class, "safe_now")

        source_key = str(signal.get("source_key") or "").strip()
        if not source_key:
            source_key = _signal_fingerprint_key(
                signal_class=incoming_class,
                source=source,
                title=str(signal.get("title") or "").strip(),
                fingerprint=signal.get("fingerprint"),
                payload=payload,
            )

        normalized = {
            "source": source,
            "signal_class": incoming_class,
            "work_class": work_class,
            "title": str(signal.get("title") or "").strip(),
            "source_key": source_key,
            "payload": dict(payload),
            "severity": severity,
            "actionability": actionability,
            "allowed_tools": [
                str(item or "").strip()
                for item in list(signal.get("allowed_tools") or [])
                if str(item or "").strip()
            ],
            "preferred_tool": str(signal.get("preferred_tool") or "").strip(),
            "task_sequence": [
                dict(item)
                for item in list(signal.get("task_sequence") or [])
                if isinstance(item, dict) and str(item.get("title") or "").strip()
            ],
            "next_task": str(signal.get("next_task") or "").strip(),
            "blocked_task": str(signal.get("blocked_task") or "").strip(),
            "blocked_reason": str(signal.get("blocked_reason") or "").strip(),
        }
        return _append_source_root_judgment_task(source, normalized)


def _signal_fingerprint_key(*, signal_class: str, source: str, title: str, fingerprint: Any, payload: dict[str, Any]) -> str:
    if isinstance(fingerprint, str) and fingerprint.strip():
        return fingerprint.strip()

    if isinstance(fingerprint, dict):
        ordered = {str(key): fingerprint[key] for key in sorted(fingerprint.keys(), key=lambda item: str(item))}
        values = [str(ordered.get(key) or "").strip() for key in ("class", "surface", "error", "symbol")]
        if any(values):
            return ":".join([
                str(signal_class or ordered.get("class") or "unknown").strip(),
                str(ordered.get("surface") or source or "unknown").strip(),
                str(ordered.get("error") or "").strip() or "signal",
                str(ordered.get("symbol") or "").strip() or "none",
            ])
        body = json.dumps(ordered, sort_keys=True, ensure_ascii=True)
        return f"{signal_class}:{source}:{hashlib.sha1(body.encode('utf-8')).hexdigest()[:16]}"

    fallback = {
        "signal_class": signal_class,
        "source": source,
        "title": title,
        "payload": payload,
    }
    body = json.dumps(fallback, sort_keys=True, ensure_ascii=True)
    return f"{signal_class}:{source}:{hashlib.sha1(body.encode('utf-8')).hexdigest()[:16]}"


def _bucket_for_work_class(work_class: str) -> str:
    return _BUCKET_BY_WORK_CLASS.get(work_class, "signals")


def _score_for_signal(severity: str, actionability: str) -> int:
    severity_score = {
        "critical": 95,
        "high": 85,
        "medium": 70,
        "low": 55,
        "info": 40,
    }.get(severity, 70)
    actionability_bonus = {
        "safe_now": 5,
        "blocked": -5,
        "dead_end": -20,
    }.get(actionability, 0)
    return max(0, min(100, severity_score + actionability_bonus))


def _branch_why_summary(normalized: dict[str, Any]) -> str:
    payload = normalized.get("payload") if isinstance(normalized.get("payload"), dict) else {}
    signal_class = str(normalized.get("signal_class") or "").strip()
    source = str(normalized.get("source") or "").strip()
    actionability = str(normalized.get("actionability") or "").strip()
    severity = str(normalized.get("severity") or "").strip()
    alert = str(payload.get("alert") or "").strip()
    rationale = str(payload.get("rationale") or "").strip()
    target_seam = str(payload.get("target_seam") or "").strip()
    signal_name = str(payload.get("signal") or "").strip()
    suggested_test_name = str(payload.get("suggested_test_name") or "").strip()
    preferred_owner = str(payload.get("preferred_owner") or "").strip()
    route_hint = str(payload.get("route_hint") or "").strip()
    branch_note = str(payload.get("branch_note") or "").strip()
    parts = [
        f"source={source or 'unknown'}",
        f"signal_class={signal_class or 'unknown'}",
        f"severity={severity or 'unknown'}",
        f"actionability={actionability or 'safe_now'}",
    ]
    if alert:
        parts.append(f"alert={alert}")
    if target_seam:
        parts.append(f"seam={target_seam}")
    if signal_name:
        parts.append(f"signal={signal_name}")
    if suggested_test_name:
        parts.append(f"test={suggested_test_name}")
    if preferred_owner:
        parts.append(f"owner={preferred_owner}")
    if route_hint:
        parts.append(f"route_hint={route_hint}")
    summary = "Signal evidence: " + " | ".join(parts)
    extra_lines = [summary]
  