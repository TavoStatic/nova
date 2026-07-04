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

    def normalized_base_url(self) -> str:
        return str(self.base_url or "").strip().rstrip("/")

    def token_url(self) -> str:
        return f"{self.normalized_base_url()}{_path(self.token_path)}"

    def metadata_url(self) -> str:
        return f"{self.normalized_base_url()}{_path(self.api_root)}{_path(self.metadata_path)}"

    def sample_resource_url(self) -> str:
        resource = str(self.sample_resource or "schools").strip().strip("/")
        return f"{self.normalized_base_url()}{_path(self.api_root)}/{resource}"

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
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def load_connection_config(connection_id: str) -> ConnectionConfig | None:
    data = _load_json_dict(connection_config_path(connection_id))
    if not data:
        return None
    return connection_config_from_dict(data, connection_id=connection_id)


def connection_config_from_dict(data: dict[str, Any], *, connection_id: str = "") -> ConnectionConfig:
    payload = dict(data or {})
    resolved_id = str(connection_id or payload.get("connection_id") or "").strip()
    base_url = str(payload.get("base_url") or "").strip()
    client_id = str(payload.get("client_id") or "").strip()
    client_secret = str(payload.get("client_secret") or "").strip()
    if not resolved_id or not base_url or not client_id or not client_secret:
        raise ValueError("connection_config_incomplete")
    parsed = urlparse(base_url)
    if parsed.scheme not in {"https", "http"} or not parsed.netloc:
        raise ValueError("connection_base_url_invalid")
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