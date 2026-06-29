from __future__ import annotations

from typing import Any

from services.control_status_surfaces import release_drift_detected


MODEL_RUNTIME_HTTP_PROBE_KEYS = (
    "ollama_api_up",
    "ollama_health",
    "ollama_version",
    "ollama_api_contract_status",
    "ollama_chat_route_ok",
    "port_ownership",
)


def running_build_identity(release_status: dict[str, Any]) -> str:
    release = dict(release_status or {})
    version = str(release.get("latest_version") or "").strip()
    channel = str(release.get("latest_channel") or "").strip()
    label = str(release.get("latest_label") or "").strip()
    if version:
        parts = [version]
        if channel:
            parts.append(channel)
        if label:
            parts.append(label)
        return ":".join(parts)
    artifact = str(release.get("latest_artifact_name") or release.get("latest_artifact_path") or "").strip()
    return artifact or "unknown"


def enrich_release_status(release_status: dict[str, Any]) -> dict[str, Any]:
    release = dict(release_status or {})
    drift = bool(release.get("latest_source_changed_after_build")) or release_drift_detected(release)
    release["running_build_identity"] = running_build_identity(release)
    release["runtime_drift_expected"] = drift
    release["runtime_drift_tolerated"] = drift
    release["runtime_drift_reason"] = (
        str(release.get("latest_readiness_state") or release.get("latest_source_status") or "").strip()
        if drift
        else ""
    )
    return release


def build_release_runtime_truth_summary(release_status: dict[str, Any]) -> dict[str, Any]:
    release = enrich_release_status(release_status)
    return {
        "running_build_identity": str(release.get("running_build_identity") or ""),
        "runtime_drift_expected": bool(release.get("runtime_drift_expected", False)),
        "runtime_drift_tolerated": bool(release.get("runtime_drift_tolerated", False)),
        "runtime_drift_reason": str(release.get("runtime_drift_reason") or ""),
        "latest_readiness_state": str(release.get("latest_readiness_state") or ""),
        "latest_source_changed_after_build": bool(release.get("latest_source_changed_after_build", False)),
        "latest_source_changed_after_build_count": int(
            release.get("latest_source_changed_after_build_count", 0) or 0
        ),
        "latest_source_newest_path": str(release.get("latest_source_newest_path") or ""),
        "suppress_closure_inventory_signals": release_drift_suppresses_closure_signals(release),
    }


def release_drift_suppresses_closure_signals(
    release_status: dict[str, Any],
    *,
    runtime_truth: dict[str, Any] | None = None,
) -> bool:
    truth = dict(runtime_truth or {})
    if truth.get("suppress_closure_inventory_signals") is True:
        return True
    release = enrich_release_status(release_status) if release_status else {}
    return bool(release.get("runtime_drift_expected"))


def evaluate_http_model_runtime_probe(
    http_payload: dict[str, Any],
    *,
    required_keys: tuple[str, ...] = MODEL_RUNTIME_HTTP_PROBE_KEYS,
) -> dict[str, Any]:
    payload = dict(http_payload or {})
    missing: list[str] = []
    for key in required_keys:
        if key not in payload:
            missing.append(key)
            continue
        value = payload.get(key)
        if value is None:
            missing.append(key)
        elif isinstance(value, str) and not value.strip():
            missing.append(key)
        elif isinstance(value, (dict, list, tuple)) and not value:
            missing.append(key)
    present = [key for key in required_keys if key not in missing]
    return {
        "ok": not missing,
        "required_key_count": len(required_keys),
        "present_key_count": len(present),
        "missing_keys": missing,
        "present_keys": present,
        "source": "http_surfaces",
    }


class ReleaseRuntimeTruthService:
    @staticmethod
    def enrich_release_status(release_status: dict[str, Any]) -> dict[str, Any]:
        return enrich_release_status(release_status)

    @staticmethod
    def build_runtime_truth_summary(release_status: dict[str, Any]) -> dict[str, Any]:
        return build_release_runtime_truth_summary(release_status)

    @staticmethod
    def release_drift_suppresses_closure_signals(
        release_status: dict[str, Any],
        *,
        runtime_truth: dict[str, Any] | None = None,
    ) -> bool:
        return release_drift_suppresses_closure_signals(release_status, runtime_truth=runtime_truth)

    @staticmethod
    def evaluate_http_model_runtime_probe(
        http_payload: dict[str, Any],
        *,
        required_keys: tuple[str, ...] = MODEL_RUNTIME_HTTP_PROBE_KEYS,
    ) -> dict[str, Any]:
        return evaluate_http_model_runtime_probe(http_payload, required_keys=required_keys)


RELEASE_RUNTIME_TRUTH_SERVICE = ReleaseRuntimeTruthService()