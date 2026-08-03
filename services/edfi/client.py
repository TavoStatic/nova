from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable

import requests

from services.edfi.auth import AuthResult, EdFiAuthService
from services.edfi.config import ConnectionConfig
from services.edfi.errors import classify_http_status, classify_request_exception
from services.edfi.rate_limit_evidence import extract_rate_limit_headers, maybe_record_from_response


@dataclass(frozen=True)
class EdFiResponse:
    ok: bool
    status_code: int = 0
    latency_ms: int = 0
    url: str = ""
    method: str = "GET"
    body: Any = None
    error: str = ""
    error_code: str = ""
    auth: AuthResult | None = None
    # Sanitized rate/limit-related response headers only (never Authorization).
    response_headers: dict[str, str] = field(default_factory=dict)


class EdFiClient:
    """Thin HTTP client for Ed-Fi ODS endpoints."""

    def __init__(
        self,
        config: ConnectionConfig,
        *,
        auth_service: EdFiAuthService | None = None,
        session: requests.Session | None = None,
    ) -> None:
        self.config = config
        self.auth = auth_service or EdFiAuthService(session=session)
        self._session = session or requests.Session()

    def authenticate(self, *, force_refresh: bool = False) -> AuthResult:
        _header, result = self.auth.get_authorization_header(self.config, force_refresh=force_refresh)
        return result

    def request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        retry_auth: bool = True,
    ) -> EdFiResponse:
        started = time.perf_counter()
        auth_header, auth_result = self.auth.get_authorization_header(self.config)
        if not auth_result.ok:
            return EdFiResponse(
                ok=False,
                url=url,
                method=method,
                error=auth_result.error or "authentication_failed",
                error_code=auth_result.error_code or "edfi_auth_failed",
                auth=auth_result,
            )
        headers = {
            "Authorization": auth_header,
            "Accept": "application/json",
        }
        try:
            response = self._session.request(
                method.upper(),
                url,
                params=params,
                json=json_body,
                headers=headers,
                timeout=self.config.timeout_sec,
                verify=self.config.ssl_verify(),
            )
            if retry_auth and response.status_code in {401, 403}:
                auth_header, auth_result = self.auth.get_authorization_header(self.config, force_refresh=True)
                if auth_result.ok:
                    headers["Authorization"] = auth_header
                    response = self._session.request(
                        method.upper(),
                        url,
                        params=params,
                        json=json_body,
                        headers=headers,
                        timeout=self.config.timeout_sec,
                        verify=self.config.ssl_verify(),
                    )
            latency_ms = int((time.perf_counter() - started) * 1000)
            parsed = _parse_json(response)
            status_code = int(response.status_code)
            ok = 200 <= status_code < 300
            error_code = "" if ok else (classify_http_status(status_code) or "edfi_request_failed")
            safe_headers = extract_rate_limit_headers(getattr(response, "headers", None) or {})
            result = EdFiResponse(
                ok=ok,
                status_code=status_code,
                latency_ms=latency_ms,
                url=url,
                method=method.upper(),
                body=parsed,
                error="" if ok else _compact_text(response.text),
                error_code=error_code,
                auth=auth_result,
                response_headers=safe_headers,
            )
            # Passive 429 capture + recovery timing (never floods TEA).
            try:
                maybe_record_from_response(
                    status_code=status_code,
                    method=method.upper(),
                    url=url,
                    error=result.error,
                    error_code=error_code,
                    body=parsed if not ok else None,
                    response_headers=safe_headers,
                    latency_ms=latency_ms,
                    connection_id=str(getattr(self.config, "connection_id", "") or ""),
                    base_url=str(self.config.normalized_base_url() if hasattr(self.config, "normalized_base_url") else ""),
                    source="edfi_client",
                )
            except Exception:
                pass
            return result
        except requests.RequestException as exc:
            latency_ms = int((time.perf_counter() - started) * 1000)
            return EdFiResponse(
                ok=False,
                url=url,
                method=method.upper(),
                latency_ms=latency_ms,
                error=str(exc),
                error_code=classify_request_exception(exc),
                auth=auth_result,
            )

    def get(self, url_or_resource: str, *, params: dict[str, Any] | None = None) -> EdFiResponse:
        url = _resolve_url(self.config, url_or_resource)
        return self.request("GET", url, params=params)

    def test_connection(self) -> EdFiResponse:
        auth_result = self.authenticate()
        if not auth_result.ok:
            return EdFiResponse(
                ok=False,
                url=self.config.token_url(),
                method="POST",
                error=auth_result.error or "authentication_failed",
                error_code=auth_result.error_code or "edfi_auth_failed",
                auth=auth_result,
                latency_ms=auth_result.latency_ms,
                status_code=auth_result.status_code,
            )
        return self.get(self.config.metadata_url())


def _resolve_url(config: ConnectionConfig, url_or_resource: str) -> str:
    text = str(url_or_resource or "").strip()
    if text.startswith("http://") or text.startswith("https://"):
        return text
    return config.resource_url(text)


def _parse_json(response: requests.Response) -> Any:
    if not response.content:
        return None
    try:
        return response.json()
    except Exception:
        return {"raw": _compact_text(response.text, limit=4000)}


def _compact_text(text: str, *, limit: int = 220) -> str:
    return " ".join(str(text or "").split())[:limit]