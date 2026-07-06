from __future__ import annotations

from typing import Any

import requests


def classify_http_status(status_code: int) -> str:
    code = int(status_code or 0)
    if code == 401:
        return "edfi_auth_unauthorized"
    if code == 403:
        return "edfi_auth_forbidden"
    if code == 404:
        return "edfi_not_found"
    if code == 429:
        return "edfi_rate_limited"
    if code >= 500:
        return "edfi_server_error"
    if code >= 400:
        return "edfi_client_error"
    return ""


def classify_request_exception(exc: BaseException) -> str:
    if isinstance(exc, requests.exceptions.SSLError):
        return "edfi_ssl_error"
    if isinstance(exc, requests.exceptions.ConnectTimeout):
        return "edfi_timeout"
    if isinstance(exc, requests.exceptions.ReadTimeout):
        return "edfi_timeout"
    if isinstance(exc, requests.exceptions.Timeout):
        return "edfi_timeout"
    if isinstance(exc, requests.exceptions.ConnectionError):
        message = str(exc).lower()
        if "name or service not known" in message or "getaddrinfo failed" in message or "nodename" in message:
            return "edfi_dns_failure"
        if "certificate" in message or "ssl" in message:
            return "edfi_ssl_error"
        return "edfi_connection_error"
    if isinstance(exc, requests.exceptions.RequestException):
        return "edfi_transport_error"
    return "edfi_unknown_error"


def issue_from_error(*, severity: str, code: str, detail: str) -> dict[str, str]:
    return {
        "severity": str(severity or "warning")[:24],
        "code": str(code or "edfi_issue")[:80],
        "detail": " ".join(str(detail or "").split())[:260],
    }


def config_validation_issues(errors: list[dict[str, str]]) -> list[dict[str, str]]:
    return [issue_from_error(severity="failure", code=item["code"], detail=item["detail"]) for item in errors]


def empty_health_shell(*, connection_id: str = "", base_url: str = "") -> dict[str, Any]:
    return {
        "ok": False,
        "status": "failure",
        "connection_id": connection_id,
        "base_url": base_url,
        "issues": [],
        "issue_count": 0,
        "latency_ms": {},
        "auth": {"ok": False},
        "discovery": {"ok": False},
    }