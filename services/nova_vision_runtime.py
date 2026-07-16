from __future__ import annotations

import json
import importlib.util
from pathlib import Path
from typing import Any


DEFAULT_VISION_MODEL = "qwen2.5vl:7b"

_MODULE_IMPORTS = {
    "requests": "requests",
    "pillow": "PIL",
    "mss": "mss",
    "opencv": "cv2",
}


def _module_available(import_name: str) -> bool:
    try:
        return importlib.util.find_spec(import_name) is not None
    except Exception:
        return False


def _available_models(ollama_health: dict[str, Any]) -> list[str]:
    models = []
    for item in list(ollama_health.get("available_models") or []):
        value = str(item or "").strip()
        if value and value not in models:
            models.append(value)
    return models


def vision_model_from_policy(policy: dict[str, Any] | None = None) -> str:
    payload = policy if isinstance(policy, dict) else {}
    models = payload.get("models") if isinstance(payload.get("models"), dict) else {}
    return str(models.get("vision") or DEFAULT_VISION_MODEL).strip() or DEFAULT_VISION_MODEL


def vision_model_from_policy_file(base_dir: str | Path | None = None) -> str:
    root = Path(base_dir).resolve() if base_dir is not None else Path(__file__).resolve().parent.parent
    policy_path = root / "policy.json"
    try:
        payload = json.loads(policy_path.read_text(encoding="utf-8"))
    except Exception:
        return DEFAULT_VISION_MODEL
    return vision_model_from_policy(payload if isinstance(payload, dict) else {})


def describe_image_file(
    path: str | Path,
    prompt: str = "",
    *,
    policy: dict[str, Any] | None = None,
    ollama_url: str = "http://localhost:11434/api/chat",
    timeout_seconds: int = 1800,
) -> str:
    import base64

    import requests

    image_path = Path(path)
    if not image_path.exists() or not image_path.is_file():
        raise FileNotFoundError(f"image not found: {image_path}")

    prompt_text = str(prompt or "Describe what you see in this image.").strip() or "Describe what you see in this image."
    model = vision_model_from_policy(policy)
    payload = {
        "model": model,
        "stream": False,
        "messages": [
            {
                "role": "user",
                "content": prompt_text,
                "images": [base64.b64encode(image_path.read_bytes()).decode("utf-8")],
            }
        ],
    }
    response = requests.post(ollama_url, json=payload, timeout=timeout_seconds)
    response.raise_for_status()
    data = response.json()
    message = data.get("message") if isinstance(data.get("message"), dict) else {}
    return str(message.get("content") or "").strip()


def vision_status_payload(
    *,
    policy: dict[str, Any] | None = None,
    ollama_health: dict[str, Any] | None = None,
) -> dict[str, Any]:
    policy_payload = policy if isinstance(policy, dict) else {}
    tools = policy_payload.get("tools_enabled") if isinstance(policy_payload.get("tools_enabled"), dict) else {}
    models = policy_payload.get("models") if isinstance(policy_payload.get("models"), dict) else {}
    screen_requested = bool(tools.get("screen", False))
    camera_requested = bool(tools.get("camera", False))
    requested = bool(screen_requested or camera_requested)
    vision_model = vision_model_from_policy(policy_payload)

    module_status = {
        key: _module_available(import_name)
        for key, import_name in _MODULE_IMPORTS.items()
    }
    missing: list[str] = []
    if screen_requested:
        for key in ("requests", "pillow", "mss"):
            if not module_status.get(key) and key not in missing:
                missing.append(key)
    if camera_requested:
        for key in ("requests", "pillow", "opencv"):
            if not module_status.get(key) and key not in missing:
                missing.append(key)

    health = ollama_health if isinstance(ollama_health, dict) else {}
    available_models = _available_models(health)
    model_available = bool(not vision_model or not available_models or vision_model in available_models)
    server_ok = bool(health.get("server_ok", health.get("ok", True)))

    if not requested:
        status = "not_requested"
        note = "Vision tools are not enabled by policy."
    elif missing:
        status = "missing_python_dependency"
        note = "Missing Python modules: " + ", ".join(missing)
    elif not server_ok:
        status = "ollama_unavailable"
        note = "Ollama is not reachable for vision analysis."
    elif not model_available:
        status = "vision_model_missing"
        note = f"Vision model is not installed: {vision_model}"
    else:
        status = "ok"
        note = "Vision runtime dependencies are available."

    return {
        "ok": bool(status in {"not_requested", "ok"}),
        "status": status,
        "requested": requested,
        "screen_requested": screen_requested,
        "camera_requested": camera_requested,
        "missing_modules": missing,
        "modules": module_status,
        "vision_model": vision_model,
        "vision_model_available": model_available,
        "available_models": available_models,
        "ollama_server_ok": server_ok,
        "note": note,
    }
