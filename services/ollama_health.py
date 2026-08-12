from __future__ import annotations

from typing import Callable, Any

# Module-level cache of the last seen Ollama model list.
# Used to detect inventory changes and notify SOCK for cache invalidation.
_last_seen_models: frozenset[str] = frozenset()


def _notify_sock_if_changed(current_models: list[str]) -> None:
    """Invalidate SOCK cache when Ollama's model inventory changes."""
    global _last_seen_models
    current = frozenset(current_models)
    if current == _last_seen_models:
        return
    added = current - _last_seen_models
    removed = _last_seen_models - current
    _last_seen_models = current
    try:
        from services.sock_service import notify_ollama_model_change
        if added:
            for model in added:
                notify_ollama_model_change("pulled", model)
        if removed:
            for model in removed:
                notify_ollama_model_change("deleted", model)
    except Exception:
        pass  # SOCK notification is best-effort — never block health checks


def _status_code(response: Any) -> int:
    try:
        return int(getattr(response, "status_code", 0) or 0)
    except (TypeError, ValueError):
        return 0


def _json_payload(response: Any) -> dict[str, Any]:
    try:
        payload = response.json()
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _available_models(tags_payload: dict[str, Any]) -> list[str]:
    models = []
    for row in list(tags_payload.get("models") or []):
        if not isinstance(row, dict):
            continue
        for key in ("name", "model"):
            value = str(row.get(key) or "").strip()
            if value and value not in models:
                models.append(value)
    return models


def _version_from_payload(version_payload: dict[str, Any]) -> str:
    return str(version_payload.get("version") or "").strip()


def build_ollama_health_payload(
    *,
    requests_get_fn: Callable[..., Any],
    requests_post_fn: Callable[..., Any],
    ollama_base: str,
    chat_model: str = "",
    timeout: float = 2.0,
    live_calls_allowed: bool = True,
) -> dict[str, object]:
    base = str(ollama_base or "").rstrip("/")
    configured_chat_model = str(chat_model or "").strip()
    if not live_calls_allowed:
        return {
            "ok": False,
            "server_ok": False,
            "status": "blocked_by_test_guard",
            "info": "blocked_by_test_guard",
            "tags_ok": False,
            "tags_status": 0,
            "chat_route_ok": False,
            "chat_route_status": 0,
            "chat_model": configured_chat_model,
            "version_ok": False,
            "version_status": 0,
            "version": "",
            "version_error": "",
            "api_contract_status": "blocked_by_test_guard",
            "model_available": False,
            "model_status": "not_checked",
            "available_models": [],
        }

    version_ok = False
    version_status = 0
    version_error = ""
    version_payload: dict[str, Any] = {}
    try:
        version_response = requests_get_fn(f"{base}/api/version", timeout=timeout)
        version_status = _status_code(version_response)
        version_ok = version_status == 200
        if version_ok:
            version_payload = _json_payload(version_response)
    except Exception as exc:
        version_error = str(exc)
    version = _version_from_payload(version_payload)

    tags_ok = False
    tags_status = 0
    tags_error = ""
    tags_payload: dict[str, Any] = {}
    try:
        tags_response = requests_get_fn(f"{base}/api/tags", timeout=timeout)
        tags_status = _status_code(tags_response)
        tags_ok = tags_status == 200
        if tags_ok:
            tags_payload = _json_payload(tags_response)
    except Exception as exc:
        tags_error = str(exc)
    available_models = _available_models(tags_payload)
    if tags_ok:
        _notify_sock_if_changed(available_models)
    model_available = bool(
        not configured_chat_model
        or (tags_ok and configured_chat_model in available_models)
    )
    if not configured_chat_model:
        model_status = "not_configured"
    elif not tags_ok:
        model_status = "not_checked"
    elif model_available:
        model_status = "available"
    else:
        model_status = "missing"

    chat_route_ok = False
    chat_route_status = 0
    chat_route_error = ""
    try:
        chat_response = requests_post_fn(f"{base}/api/chat", json={}, timeout=timeout)
        chat_route_status = _status_code(chat_response)
        chat_route_ok = 200 <= chat_route_status < 500 and chat_route_status != 404
    except Exception as exc:
        chat_route_error = str(exc)

    server_ok = bool(tags_ok and chat_route_ok)
    if tags_ok and chat_route_ok:
        api_contract_status = "chat_api_ready"
    elif tags_ok and not chat_route_ok:
        api_contract_status = "chat_api_missing_or_incompatible"
    elif not tags_ok:
        api_contract_status = "tags_unreachable"
    else:
        api_contract_status = "unknown"

    if server_ok and model_available:
        status = "ok"
    elif not tags_ok:
        status = "tags_unreachable"
    elif not chat_route_ok:
        status = "chat_route_unreachable"
    elif not model_available:
        status = "chat_model_missing"
    else:
        status = "unknown"

    info_parts = [
        f"version={version or version_status}" if not version_error else f"version_error={version_error}",
        f"tags={tags_status}" if not tags_error else f"tags_error={tags_error}",
        f"chat_route={chat_route_status}" if not chat_route_error else f"chat_route_error={chat_route_error}",
    ]
    if configured_chat_model:
        info_parts.append(f"chat_model={configured_chat_model}")
        info_parts.append(f"model_status={model_status}")
    return {
        "ok": bool(server_ok and model_available),
        "server_ok": server_ok,
        "status": status,
        "info": ";".join(info_parts),
        "tags_ok": bool(tags_ok),
        "tags_status": tags_status,
        "tags_error": tags_error,
        "chat_route_ok": bool(chat_route_ok),
        "chat_route_status": chat_route_status,
        "chat_route_error": chat_route_error,
        "version_ok": bool(version_ok),
        "version_status": version_status,
        "version": version,
        "version_error": version_error,
        "api_contract_status": api_contract_status,
        "chat_model": configured_chat_model,
        "model_available": bool(model_available),
        "model_status": model_status,
        "available_models": available_models,
    }
