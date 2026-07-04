from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable

import requests

from services.edfi.config import ConnectionConfig, TokenCacheEntry
from services.edfi.errors import classify_http_status, classify_request_exception


@dataclass(frozen=True)
class AuthResult:
    ok: bool
    access_token: str = ""
    token_type: str = "Bearer"
    expires_in: int = 0
    scope: str = ""
    latency_ms: int = 0
    status_code: int = 0
    error: str = ""
    error_code: str = ""
    token_endpoint: str = ""


class EdFiAuthService:
    """OAuth2 client-credentials flow for Ed-Fi ODS APIs."""

    def __init__(self, *, session: requests.Session | None = None) -> None:
        self._session = session or requests.Session()
        self._cache: dict[str, TokenCacheEntry] = {}

    def fetch_token(
        self,
        config: ConnectionConfig,
        *,
        now_fn: Callable[[], float] = time.time,
    ) -> AuthResult:
        started = time.perf_counter()
        token_endpoint = config.token_url()
        payload = {
            "grant_type": "client_credentials",
            "client_id": config.client_id,
            "client_secret": config.client_secret,
        }
        try:
            response = self._session.post(
                token_endpoint,
                data=payload,
                timeout=config.timeout_sec,
                headers={"Accept": "application/json"},
                verify=config.ssl_verify(),
            )
            latency_ms = int((time.perf_counter() - started) * 1000)
            status_code = int(response.status_code)
            if status_code >= 400:
                error_code = classify_http_status(status_code) or "edfi_auth_failed"
                return AuthResult(
                    ok=False,
                    latency_ms=latency_ms,
                    status_code=status_code,
                    error=_compact_error(response.text),
                    error_code=error_code,
                    token_endpoint=token_endpoint,
                )
            body = response.json() if response.content else {}
            if not isinstance(body, dict):
                return AuthResult(
                    ok=False,
                    latency_ms=latency_ms,
                    status_code=status_code,
                    error="token_response_not_object",
                    error_code="edfi_token_response_not_object",
                    token_endpoint=token_endpoint,
                )
            access_token = str(body.get("access_token") or "").strip()
            if not access_token:
                return AuthResult(
                    ok=False,
                    latency_ms=latency_ms,
                    status_code=status_code,
                    error="token_missing_access_token",
                    error_code="edfi_token_missing_access_token",
                    token_endpoint=token_endpoint,
                )
            expires_in = int(body.get("expires_in", 3600) or 3600)
            token_type = str(body.get("token_type") or "Bearer").strip() or "Bearer"
            scope = str(body.get("scope") or "").strip()
            self._cache[config.connection_id] = TokenCacheEntry(
                access_token=access_token,
                token_type=token_type,
                expires_at=float(now_fn()) + float(max(60, expires_in)),
                scope=scope,
            )
            return AuthResult(
                ok=True,
                access_token=access_token,
                token_type=token_type,
                expires_in=expires_in,
                scope=scope,
                latency_ms=latency_ms,
                status_code=status_code,
                token_endpoint=token_endpoint,
            )
        except requests.RequestException as exc:
            latency_ms = int((time.perf_counter() - started) * 1000)
            return AuthResult(
                ok=False,
                latency_ms=latency_ms,
                error=str(exc),
                error_code=classify_request_exception(exc),
                token_endpoint=token_endpoint,
            )

    def get_authorization_header(
        self,
        config: ConnectionConfig,
        *,
        force_refresh: bool = False,
        now_fn: Callable[[], float] = time.time,
    ) -> tuple[str, AuthResult]:
        cached = self._cache.get(config.connection_id)
        if not force_refresh and cached is not None:
            if cached.valid(now=now_fn()):
                return f"{cached.token_type} {cached.access_token}", AuthResult(
                    ok=True,
                    access_token=cached.access_token,
                    token_type=cached.token_type,
                    scope=cached.scope,
                )
            self._cache.pop(config.connection_id, None)
        result = self.fetch_token(config, now_fn=now_fn)
        if not result.ok:
            return "", result
        token_type = result.token_type or "Bearer"
        return f"{token_type} {result.access_token}", result


def _compact_error(text: str, *, limit: int = 220) -> str:
    compact = " ".join(str(text or "").split())
    return compact[:limit]