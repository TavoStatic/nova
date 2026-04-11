from __future__ import annotations

from typing import Callable
from urllib.parse import urlparse


def normalize_search_endpoint(endpoint: str) -> str:
    raw = str(endpoint or "").strip()
    if not raw:
        return "http://127.0.0.1:8080/search"
    if "://" not in raw:
        raw = "http://" + raw
    parsed = urlparse(raw)
    scheme = str(parsed.scheme or "http").strip().lower() or "http"
    host = str(parsed.hostname or "").strip()
    if not host:
        return raw
    port = f":{parsed.port}" if parsed.port else ""
    path = str(parsed.path or "/search").strip() or "/search"
    return f"{scheme}://{host}{port}{path}"


def search_endpoint_candidates(endpoint: str) -> list[str]:
    configured = normalize_search_endpoint(endpoint)
    candidates: list[str] = []

    def _append(value: str) -> None:
        normalized = normalize_search_endpoint(value)
        if normalized and normalized not in candidates:
            candidates.append(normalized)

    _append(configured)
    parsed = urlparse(configured)
    host = str(parsed.hostname or "").strip().lower()
    if host not in {"127.0.0.1", "localhost"}:
        return candidates

    scheme = str(parsed.scheme or "http").strip().lower() or "http"
    path = str(parsed.path or "/search").strip() or "/search"
    current_port = int(parsed.port or (443 if scheme == "https" else 80))
    ports: list[int] = []
    for port in (current_port, 8080, 8081):
        if port not in ports:
            ports.append(port)
    hosts: list[str] = [host]
    for local_host in ("127.0.0.1", "localhost"):
        if local_host not in hosts:
            hosts.append(local_host)
    for local_host in hosts:
        for port in ports:
            _append(f"{scheme}://{local_host}:{port}{path}")
    return candidates


def is_local_search_endpoint(endpoint: str) -> bool:
    parsed = urlparse(normalize_search_endpoint(endpoint))
    return str(parsed.hostname or "").strip().lower() in {"127.0.0.1", "localhost"}


def probe_search_endpoint(
    endpoint: str = "",
    *,
    timeout: float = 2.5,
    persist_repair: bool = False,
    get_search_endpoint_fn: Callable[[], str],
    auto_repair_search_endpoint_fn: Callable[[str], str],
    requests_get_fn: Callable[..., object],
) -> dict:
    configured = normalize_search_endpoint(endpoint or get_search_endpoint_fn())
    candidates = search_endpoint_candidates(configured)
    last_note = "endpoint_unreachable"
    candidate_errors: list[dict[str, str]] = []
    for candidate in candidates:
        try:
            response = requests_get_fn(
                candidate,
                params={"q": "health", "format": "json"},
                headers={"User-Agent": "Nova/1.0", "Accept": "application/json"},
                timeout=timeout,
            )
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError("non_json_response")
            note = f"status={response.status_code}"
            repair_message = ""
            repaired = False
            if candidate != configured:
                note += f" auto-detected={candidate}"
                if persist_repair and is_local_search_endpoint(configured) and is_local_search_endpoint(candidate):
                    repair_message = auto_repair_search_endpoint_fn(candidate)
                    repaired = bool(repair_message)
                    if repaired:
                        note += " auto-repaired"
            return {
                "ok": True,
                "endpoint": configured,
                "resolved_endpoint": candidate,
                "note": note,
                "auto_detected": candidate != configured,
                "repaired": repaired,
                "repair_message": repair_message,
                "candidate_errors": candidate_errors,
                "checked_endpoints": candidates,
                "message": f"SearXNG probe passed for {candidate} ({note}).",
            }
        except Exception as exc:
            last_note = f"error:{exc}"
            candidate_errors.append({"endpoint": candidate, "note": last_note})

    configured_error = next((item for item in candidate_errors if str(item.get("endpoint") or "") == configured), None)
    checked_summary = "; ".join(
        f"{str(item.get('endpoint') or '')} => {str(item.get('note') or '')}"
        for item in candidate_errors
    )
    note = str((configured_error or {}).get("note") or last_note)
    if checked_summary:
        note = f"configured_failed={note}; checked={checked_summary}"
    return {
        "ok": False,
        "endpoint": configured,
        "resolved_endpoint": "",
        "note": note,
        "auto_detected": False,
        "candidate_errors": candidate_errors,
        "checked_endpoints": candidates,
        "message": f"SearXNG probe failed for {configured} ({note}).",
    }