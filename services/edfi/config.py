from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from services.nova_runtime_context import BASE_DIR, RUNTIME_DIR

CAPABILITY_SCHEMA = "nova.edfi_capability.v1"
MILESTONE_ID = "NOVA-EDFI-001"

EDFI_RUNTIME_ROOT = RUNTIME_DIR / "edfi"
EDFI_CONNECTIONS_ROOT = EDFI_RUNTIME_ROOT / "connections"
EDFI_PROFILES_ROOT = EDFI_RUNTIME_ROOT / "profiles"
EDFI_AUDIT_LOG = EDFI_RUNTIME_ROOT / "edfi_audit.jsonl"


@dataclass(frozen=True)
class ConnectionConfig:
    connection_id: str
    base_url: str
    client_id: str
    client_secret: str
    token_path: str = "/oauth/token"
    api_root: str = "/data/v3"
    metadata_path: str = "/metadata/resources"
    sample_resource: str = "schools"
    timeout_sec: int = 30
    verify_ssl: bool = True
    ca_bundle_path: str = ""
    token_auth_mode: str = "auto"

    def normalized_base_url(self) -> str:
        return str(self.base_url or "").strip().rstrip("/")

    def token_url(self) -> str:
        return f"{self.normalized_base_url()}{_path(self.token_path)}"

    def metadata_url(self) -> str:
        return f"{self.normalized_base_url()}{_path(self.api_root)}{_path(self.metadata_path)}"

    def sample_resource_url(self) -> str:
        return self.resource_url(self.sample_resource)

    def resource_url(self, resource: str) -> str:
        name = str(resource or "").strip().strip("/")
        return f"{self.normalized_base_url()}{_path(self.api_root)}/{name}"

    def ssl_verify(self) -> bool | str:
        bundle = str(self.ca_bundle_path or "").strip()
        if bundle:
            return bundle
        return bool(self.verify_ssl)

    def to_public_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("client_secret", None)
        return payload


@dataclass
class TokenCacheEntry:
    access_token: str = ""
    token_type: str = "Bearer"
    expires_at: float = 0.0
    scope: str = ""

    def valid(self, *, now: float | None = None) -> bool:
        current = float(now if now is not None else time.time())
        return bool(self.access_token) and current < (self.expires_at - 30)


def _path(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return text if text.startswith("/") else f"/{text}"


def _safe_connection_id(connection_id: str) -> str:
    raw = re.sub(r"[^A-Za-z0-9._-]", "", str(connection_id or "").strip())
    if not raw:
        raise ValueError("connection_id_required")
    return raw[:64]


def connection_dir(connection_id: str) -> Path:
    return EDFI_CONNECTIONS_ROOT / _safe_connection_id(connection_id)


def connection_config_path(connection_id: str) -> Path:
    return connection_dir(connection_id) / "local_config.json"


def profile_path(connection_id: str) -> Path:
    return EDFI_PROFILES_ROOT / f"{_safe_connection_id(connection_id)}.json"


def ensure_runtime_dirs() -> None:
    EDFI_CONNECTIONS_ROOT.mkdir(parents=True, exist_ok=True)
    EDFI_PROFILES_ROOT.mkdir(parents=True, exist_ok=True)
    EDFI_RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)


def _load_json_dict(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("connection_config_json_invalid") from exc
    except Exception as exc:
        raise ValueError("connection_config_read_failed") from exc
    if not isinstance(data, dict):
        raise ValueError("connection_config_json_invalid")
    return data


def validate_connection_payload(data: dict[str, Any], *, connection_id: str = "") -> list[dict[str, str]]:
    payload = dict(data or {})
    errors: list[dict[str, str]] = []
    resolved_id = str(connection_id or payload.get("connection_id") or "").strip()
    if not resolved_id:
        errors.append({"code": "connection_id_required", "detail": "Connection id is required."})
    base_url = str(payload.get("base_url") or "").strip()
    if not base_url:
        errors.append({"code": "connection_base_url_missing", "detail": "Base URL is required."})
    else:
        parsed = urlparse(base_url)
        if parsed.scheme not in {"https", "http"} or not parsed.netloc:
            errors.append({"code": "connection_base_url_invalid", "detail": "Base URL must be a valid http(s) URL."})
    client_id = str(payload.get("client_id") or "").strip()
    if not client_id:
        errors.append({"code": "connection_client_id_missing", "detail": "Client id is required."})
    client_secret = str(payload.get("client_secret") or "").strip()
    if not client_secret:
        errors.append({"code": "connection_client_secret_missing", "detail": "Client secret is required."})
    if "verify_ssl" in payload and not isinstance(payload.get("verify_ssl"), bool):
        errors.append({"code": "connection_ssl_verify_invalid", "detail": "verify_ssl must be true or false."})
    ca_bundle_path = str(payload.get("ca_bundle_path") or "").strip()
    if ca_bundle_path and not Path(ca_bundle_path).is_file():
        errors.append({"code": "connection_ca_bundle_missing", "detail": "CA bundle path does not exist."})
    timeout_raw = payload.get("timeout_sec", 30)
    try:
        timeout_sec = int(timeout_raw)
        if timeout_sec < 5:
            errors.append({"code": "connection_timeout_invalid", "detail": "timeout_sec must be at least 5."})
    except (TypeError, ValueError):
        errors.append({"code": "connection_timeout_invalid", "detail": "timeout_sec must be an integer."})
    return errors


def load_connection_config(connection_id: str) -> ConnectionConfig | None:
    path = connection_config_path(connection_id)
    if not path.exists():
        return None
    data = _load_json_dict(path)
    if not data:
        return None
    return connection_config_from_dict(data, connection_id=connection_id)


def connection_config_from_dict(data: dict[str, Any], *, connection_id: str = "") -> ConnectionConfig:
    errors = validate_connection_payload(data, connection_id=connection_id)
    if errors:
        raise ValueError(errors[0]["code"])
    payload = dict(data or {})
    resolved_id = str(connection_id or payload.get("connection_id") or "").strip()
    base_url = str(payload.get("base_url") or "").strip()
    client_id = str(payload.get("client_id") or "").strip()
    client_secret = str(payload.get("client_secret") or "").strip()
    return ConnectionConfig(
        connection_id=_safe_connection_id(resolved_id),
        base_url=base_url.rstrip("/"),
        client_id=client_id,
        client_secret=client_secret,
        token_path=str(payload.get("token_path") or "/oauth/token"),
        api_root=str(payload.get("api_root") or "/data/v3"),
        metadata_path=str(payload.get("metadata_path") or "/metadata/resources"),
        sample_resource=str(payload.get("sample_resource") or "schools"),
        timeout_sec=max(5, int(payload.get("timeout_sec", 30) or 30)),
        verify_ssl=bool(payload.get("verify_ssl", True)),
        ca_bundle_path=str(payload.get("ca_bundle_path") or "").strip(),
        token_auth_mode=str(payload.get("token_auth_mode") or "auto").strip().lower() or "auto",
    )


def save_connection_config(config: ConnectionConfig) -> Path:
    ensure_runtime_dirs()
    target = connection_config_path(config.connection_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(config)
    target.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
    return target


def save_capability_profile(connection_id: str, profile: dict[str, Any]) -> Path:
    ensure_runtime_dirs()
    target = profile_path(connection_id)
    target.write_text(json.dumps(profile, ensure_ascii=True, indent=2), encoding="utf-8")
    return target


def load_capability_profile(connection_id: str) -> dict[str, Any]:
    return _load_json_dict(profile_path(connection_id))


def runtime_roots() -> dict[str, str]:
    return {
        "base_dir": str(BASE_DIR),
        "runtime_root": str(EDFI_RUNTIME_ROOT),
        "connections_root": str(EDFI_CONNECTIONS_ROOT),
        "profiles_root": str(EDFI_PROFILES_ROOT),
        "audit_log": str(EDFI_AUDIT_LOG),
    }