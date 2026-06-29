from __future__ import annotations

from typing import Any

from services.release_runtime_truth import release_drift_suppresses_closure_signals

LEAH_BUILD_SEQUENCE = (
    "leah_conversation_continuity",
    "leah_memory_recall",
    "leah_voice_persona_engine",
    "leah_emotional_state_model",
)

CORE_GATE_ROOT_IDS = (
    "model_runtime",
    "conversation_routing",
    "frontdoor_cli",
    "operator_control",
    "http_api_control",
)

LEAH_PREREQUISITE_ROOTS: dict[str, tuple[str, ...]] = {
    "leah_conversation_continuity": ("http_continuity", "session_identity_auth"),
    "leah_memory_recall": ("identity_profile_answers", "memory_identity"),
    "leah_voice_persona_engine": ("voice", "tts_audio_output"),
    "leah_emotional_state_model": ("leah_conversation_continuity", "leah_memory_recall", "leah_voice_persona_engine"),
}

DEFAULT_LAYER_POLICY = {
    "leah": {
        "mode": "observe",
        "promoted_capabilities": [],
    },
    "codegen": {
        "mode": "observe",
        "promoted_capabilities": [],
    },
}


def _clean_mode(value: Any) -> str:
    mode = str(value or "observe").strip().lower()
    return mode if mode in {"observe", "active"} else "observe"


def _normalize_capability_names(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in values:
        name = str(item or "").strip().lower()
        if not name or name in seen:
            continue
        seen.add(name)
        out.append(name)
    return out


def normalize_layer_policy(policy: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    raw = dict(policy or {})
    layers = raw.get("layers") if isinstance(raw.get("layers"), dict) else {}
    normalized: dict[str, dict[str, Any]] = {}
    for layer_name, defaults in DEFAULT_LAYER_POLICY.items():
        layer_cfg = layers.get(layer_name) if isinstance(layers.get(layer_name), dict) else {}
        normalized[layer_name] = {
            "mode": _clean_mode(layer_cfg.get("mode", defaults.get("mode"))),
            "promoted_capabilities": _normalize_capability_names(
                layer_cfg.get("promoted_capabilities", defaults.get("promoted_capabilities"))
            ),
        }
    return normalized


def layer_for_capability(capability_name: str) -> str:
    clean = str(capability_name or "").strip().lower()
    return "leah" if clean.startswith("leah_") else "codegen"


def _root_closure_by_id(status_payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    inventory = status_payload.get("root_closure_inventory")
    if not isinstance(inventory, dict):
        return {}
    rows = [
        dict(item)
        for item in list(inventory.get("roots") or [])
        if isinstance(item, dict)
    ]
    return {
        str(row.get("root_id") or "").strip(): row
        for row in rows
        if str(row.get("root_id") or "").strip()
    }


def evaluate_core_gate(status_payload: dict[str, Any]) -> dict[str, Any]:
    release_status = (
        status_payload.get("release_status")
        if isinstance(status_payload.get("release_status"), dict)
        else {}
    )
    release_truth = (
        status_payload.get("release_runtime_truth")
        if isinstance(status_payload.get("release_runtime_truth"), dict)
        else {}
    )
    drift_blocked = bool(
        release_truth.get("suppress_closure_inventory_signals")
        or release_drift_suppresses_closure_signals(release_status, runtime_truth=release_truth)
    )
    by_id = _root_closure_by_id(status_payload)
    missing_roots = [
        root_id
        for root_id in CORE_GATE_ROOT_IDS
        if not bool((by_id.get(root_id) or {}).get("ok", False))
    ]
    passed = not drift_blocked and not missing_roots
    return {
        "ok": passed,
        "drift_blocked": drift_blocked,
        "missing_roots": missing_roots,
        "required_roots": list(CORE_GATE_ROOT_IDS),
    }


def _leah_prerequisite_roots_ok(capability_name: str, status_payload: dict[str, Any]) -> tuple[bool, list[str]]:
    clean = str(capability_name or "").strip().lower()
    required = list(LEAH_PREREQUISITE_ROOTS.get(clean, ()))
    if not required:
        return True, []
    by_id = _root_closure_by_id(status_payload)
    missing: list[str] = []
    for root_id in required:
        if root_id.startswith("leah_"):
            continue
        if not bool((by_id.get(root_id) or {}).get("ok", False)):
            missing.append(root_id)
    return not missing, missing


def next_leah_capability_in_sequence(
    gaps: list[str],
    *,
    promoted_capabilities: list[str] | None = None,
    registered_capabilities: set[str] | None = None,
) -> str | None:
    gap_set = {str(item or "").strip().lower() for item in gaps if str(item or "").strip()}
    promoted = {
        str(item or "").strip().lower()
        for item in list(promoted_capabilities or [])
        if str(item or "").strip()
    }
    registered = {
        str(item or "").strip().lower()
        for item in set(registered_capabilities or set())
        if str(item or "").strip()
    }
    for capability in LEAH_BUILD_SEQUENCE:
        if capability not in gap_set:
            continue
        if promoted and capability not in promoted:
            continue
        if capability in registered:
            continue
        return capability
    return None


def capability_action_block_reason(
    capability_name: str,
    *,
    policy: dict[str, Any] | None,
    status_payload: dict[str, Any] | None = None,
) -> str:
    clean = str(capability_name or "").strip().lower()
    if not clean:
        return "capability_missing"
    layers = normalize_layer_policy(policy)
    layer_name = layer_for_capability(clean)
    layer_cfg = layers.get(layer_name, {})
    mode = _clean_mode(layer_cfg.get("mode"))
    if mode == "observe":
        return f"{layer_name}_observe_mode"
    promoted = set(_normalize_capability_names(layer_cfg.get("promoted_capabilities")))
    if not promoted or clean not in promoted:
        return "capability_not_promoted"
    status = dict(status_payload or {})
    core_gate = evaluate_core_gate(status)
    if not core_gate.get("ok"):
        if core_gate.get("drift_blocked"):
            return "core_gate_release_drift"
        return "core_gate_roots_blocked"
    if clean.startswith("leah_"):
        registered = status.get("capabilities_registered")
        registered_names = (
            {str(name or "").strip().lower() for name in registered.keys()}
            if isinstance(registered, dict)
            else set()
        )
        gaps = [
            str(item or "").strip().lower()
            for item in list(status.get("capability_gaps") or [])
            if str(item or "").strip()
        ]
        next_cap = next_leah_capability_in_sequence(
            gaps,
            promoted_capabilities=list(promoted),
            registered_capabilities=registered_names,
        )
        if next_cap != clean:
            return "leah_sequence_order"
        prereq_ok, _missing = _leah_prerequisite_roots_ok(clean, status)
        if not prereq_ok:
            return "leah_prerequisite_roots_blocked"
    return ""


def capability_action_allowed(
    capability_name: str,
    *,
    policy: dict[str, Any] | None,
    status_payload: dict[str, Any] | None = None,
) -> bool:
    return not capability_action_block_reason(
        capability_name,
        policy=policy,
        status_payload=status_payload,
    )


def filter_actionable_capability_gaps(
    gaps: list[str],
    *,
    policy: dict[str, Any] | None,
    status_payload: dict[str, Any] | None = None,
) -> list[str]:
    status = dict(status_payload or {})
    status["capability_gaps"] = list(gaps)
    actionable: list[str] = []
    for gap in list(gaps or []):
        if capability_action_allowed(gap, policy=policy, status_payload=status):
            actionable.append(gap)
    return actionable


def build_layer_maturity_summary(
    status_payload: dict[str, Any],
    *,
    policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = dict(status_payload or {})
    layers = normalize_layer_policy(policy)
    gaps = [
        str(item or "").strip().lower()
        for item in list(payload.get("capability_gaps") or [])
        if str(item or "").strip()
    ]
    actionable_gaps = filter_actionable_capability_gaps(
        gaps,
        policy=policy,
        status_payload=payload,
    )
    observed_gaps = [gap for gap in gaps if gap not in set(actionable_gaps)]
    leah_gaps = [gap for gap in gaps if gap.startswith("leah_")]
    core_gate = evaluate_core_gate(payload)
    next_leah = next_leah_capability_in_sequence(
        gaps,
        promoted_capabilities=layers.get("leah", {}).get("promoted_capabilities"),
        registered_capabilities=(
            {str(name or "").strip().lower() for name in (payload.get("capabilities_registered") or {}).keys()}
            if isinstance(payload.get("capabilities_registered"), dict)
            else set()
        ),
    )
    suppress_signals = not actionable_gaps
    return {
        "ok": True,
        "layers": layers,
        "leah_build_sequence": list(LEAH_BUILD_SEQUENCE),
        "core_gate": core_gate,
        "next_leah_capability": next_leah or "",
        "observed_gap_count": len(observed_gaps),
        "actionable_gap_count": len(actionable_gaps),
        "observed_gaps": observed_gaps[:12],
        "actionable_gaps": actionable_gaps[:12],
        "leah_gap_count": len(leah_gaps),
        "suppress_capability_gap_signals": suppress_signals,
        "codegen_observe_mode": _clean_mode(layers.get("codegen", {}).get("mode")) == "observe",
        "leah_observe_mode": _clean_mode(layers.get("leah", {}).get("mode")) == "observe",
    }


def enrich_status_with_layer_maturity(
    status_payload: dict[str, Any],
    *,
    policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = dict(status_payload or {})
    maturity = build_layer_maturity_summary(result, policy=policy)
    result["layer_maturity"] = maturity
    result["capability_gaps_observed"] = list(maturity.get("observed_gaps") or [])
    result["capability_gaps_actionable"] = list(maturity.get("actionable_gaps") or [])
    result["capability_gap_actionable_count"] = int(maturity.get("actionable_gap_count", 0) or 0)
    result["capability_gap_observed_count"] = int(maturity.get("observed_gap_count", 0) or 0)
    result["suppress_capability_gap_signals"] = bool(maturity.get("suppress_capability_gap_signals"))
    result["next_leah_capability"] = str(maturity.get("next_leah_capability") or "")
    return result


def capability_gap_signal_suppressed(status_payload: dict[str, Any]) -> bool:
    payload = dict(status_payload or {})
    if "suppress_capability_gap_signals" in payload:
        return bool(payload.get("suppress_capability_gap_signals"))
    maturity = payload.get("layer_maturity")
    if isinstance(maturity, dict):
        return bool(maturity.get("suppress_capability_gap_signals"))
    return True


def orchestrator_codegen_action_allowed(
    action_type: str,
    *,
    policy: dict[str, Any] | None,
    status_payload: dict[str, Any] | None = None,
    capability_name: str = "",
) -> bool:
    clean_action = str(action_type or "").strip().lower()
    if clean_action not in {"codegen_run", "leah_build_run_next"}:
        return True
    clean_capability = str(capability_name or "").strip().lower()
    if not clean_capability:
        layers = normalize_layer_policy(policy)
        if clean_action == "leah_build_run_next":
            return _clean_mode(layers.get("leah", {}).get("mode")) == "active" and bool(
                layers.get("leah", {}).get("promoted_capabilities")
            )
        return _clean_mode(layers.get("codegen", {}).get("mode")) == "active" and bool(
            layers.get("codegen", {}).get("promoted_capabilities")
        )
    return capability_action_allowed(
        clean_capability,
        policy=policy,
        status_payload=status_payload,
    )


class LayerMaturityPolicyService:
    @staticmethod
    def normalize_layer_policy(policy: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
        return normalize_layer_policy(policy)

    @staticmethod
    def build_summary(status_payload: dict[str, Any], *, policy: dict[str, Any] | None = None) -> dict[str, Any]:
        return build_layer_maturity_summary(status_payload, policy=policy)

    @staticmethod
    def enrich_status(status_payload: dict[str, Any], *, policy: dict[str, Any] | None = None) -> dict[str, Any]:
        return enrich_status_with_layer_maturity(status_payload, policy=policy)


LAYER_MATURITY_POLICY_SERVICE = LayerMaturityPolicyService()