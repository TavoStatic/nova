from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable

import requests

from services.edfi.auth import AuthResult, EdFiAuthService
from services.edfi.config import ConnectionConfig


@dataclass(frozen=True)
class EdFiResponse:
    ok: bool
    status_code: int = 0
    latency_ms: int = 0
    url: str = ""
    method: str = "GET"
    body: Any = None
    error: str = ""
    auth: AuthResult | None = None


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
                    )
            latency_ms = int((time.perf_counter() - started) * 1000)
            parsed = _parse_json(response)
            ok = 200 <= int(response.status_code) < 300
            return EdFiResponse(
                ok=ok,
                status_code=int(response.status_code),
                latency_ms=latency_ms,
                url=url,
                method=method.upper(),
                body=parsed,
                error="" if ok else _compact_text(response.text),
                auth=auth_result,
            )
        except requests.RequestException as exc:
            latency_ms = int((time.perf_counter() - started) * 1000)
            return EdFiResponse(
                ok=False,
                url=url,
                method=method.upper(),
                latency_ms=latency_ms,
                error=str(exc),
                auth=auth_result,
            )

    def get(self, url: str, *, params: dict[str, Any] | None = None) -> EdFiResponse:
        return self.request("GET", url, params=params)

    def test_connection(self) -> EdFiResponse:
        auth_result = self.authenticate()
        if not auth_result.ok:
            return EdFiResponse(
                ok=False,
                url=self.config.token_url(),
                method="POST",
                error=auth_result.error or "authentication_failed",
                auth=auth_result,
                latency_ms=auth_result.latency_ms,
                status_code=auth_result.status_code,
            )
        return self.get(self.config.metadata_url())


def _parse_json(response: requests.Response) -> Any:
    if not response.content:
        return None
    try:
        return response.json()
    except Exception:
        return {"raw": _compact_text(response.text, limit=4000)}


def _compact_text(text: str, *, limit: int = 220) -> str:
    return " ".join(str(text or "").split())[:limit]