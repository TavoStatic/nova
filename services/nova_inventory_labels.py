from __future__ import annotations

SHARED_INVENTORY_LABELS: dict[str, str] = {
    "runtime_control": "Runtime start/stop/restart control, process identity, timelines, and restart provenance",
    "scheduler_registry": "Maintenance schedule registry and detached worker cycle ownership",
    "model_runtime": "Ollama server, version/API contract, model availability, chat route, and port ownership",
    "frontdoor_cli": "Nova command front door, shell dispatch, and local CLI entrypoints",
    "http_api_control": "HTTP transport, API route dispatch, control room, auth, and action hooks",
    "operator_control": "Operator macros, backend commands, local operator CLI, and control-action dispatcher",
    "session_identity_auth": "Chat users, control sessions, active session state, and auth identity",
    "memory_identity": "Memory health, bootstrap origin, identity persistence, and learned facts",
    "identity_profile_answers": "Identity profile answers, durable identity context, and developer-profile recall purpose",
    "conversation_routing": "Semantic tool routing, route probes, reply sequencing, and continuity",
    "supervisor_fulfillment": "Supervisor ownership, fulfillment flow, shared routing rules, and follow-up dispatch",
    "reply_quality_contracts": "Reflection health, reply delivery evidence, and final-turn shaping",
    "web_search": "Web/search provider policy, SearXNG, provider telemetry, and research tools",
    "retrieval_knowledge": "Local knowledge packs and retrieved context",
    "weather_location": "Weather, device location, and saved location tools",
    "work_tree": "Work Tree truth, active branches, evidence, and autonomous step execution",
    "tool_registry_policy": "Tool registry, direct tool catalog, tool policy, console, and planned action dispatch",
    "action_ledger": "Action ledger readback, route summaries, and final answer evidence",
    "installer_packaging": "Windows installer build, verification, ledger, and readiness flow",
    "tts_audio_output": "TTS output, Piper bridge, model assets, and spoken response delivery",
    "http_continuity": "HTTP conversation state, grounded self-report continuity, and active Work Tree identity",
    "diagnostics_hygiene": "Doctor, health checks, diagnostics, smoke checks, and repo hygiene",
    "safety_envelope": "Phase 2 safety envelope, review authority, generated-session quarantine, and promotion gates",
    "metrics_ops_journal": "Behavior metrics, ops journal, metrics snapshots, and operator-visible telemetry",
    "core_steward_reflection": "Core steward posture, core health brief, thinning, and reflective health pressure",
}


def shared_inventory_label(surface_id: str) -> str:
    return SHARED_INVENTORY_LABELS[surface_id]
