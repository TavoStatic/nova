from __future__ import annotations

"""
Passive TEA/Ed-Fi rate-limit evidence capture.

Purpose:
  When a real 429 (or ratelimited body) occurs during normal Nova use, save
  headers/body/timing under runtime/ so we can learn TEA's actual cooldown
  (Retry-After, RateLimit-*, recovery after success) without deliberately
  flooding the API.

Safety:
  Do NOT implement "request until 429" probes against production TEA.
  Aggressive probing can look like abuse, exhaust shared quota, and may
  trigger temporary blocks or security review on the client key / IP.
  Capture evidence from organic failures; measure recovery only when a later
  legitimate request succeeds.
"""

import json
import re
import time
from pathlib import Path
from typing import Any, Mapping

from services.nova_runtime_context import RUNTIME_DIR

EVIDENCE_DIR = RUNTIME_DIR / "edfi" / "rate_limit_evidence"
LATEST_PATH = EVIDENCE_DIR / "latest.json"
EVENTS_PATH = EVIDENCE_DIR / "events.jsonl"

# Headers worth keeping (case-insensitive prefix/name match).
_HEADER_ALLOW = re.compile(
    r"^(retry-after|x-ratelimit|ratelimit|x-rate-limit|x-request-id|"
    r"x-correlation|date|server|cf-ray|x-ms-|www-authenticate|"
    r"x-ed-fi|strict-transport|cache-control)",
    re.I,
)

# In-process: last 429 epoch for recovery measurement on next success.
_LAST_429_EPOCH: float = 0.0
_LAST_429_ID: str = ""


def evidence_dir() -> Path:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    return EVIDENCE_DIR


def extract_rate_limit_headers(headers: Mapping[str, Any] | None) -> dict[str, str]:
    """Keep rate/limit-related response headers; drop Authorization and noise."""
    out: dict[str, str] = {}
    if not headers:
        return out
    for key, value in headers.items():
        name = str(key or "").strip()
        if not name:
            continue
        if name.lower() == "authorization":
            continue
        if _HEADER_ALLOW.match(name) or "rate" in name.lower() or "retry" in name.lower():
            text = " ".join(str(value or "").split())
            if text:
                out[name] = text[:500]
    return out


def parse_retry_after_seconds(headers: Mapping[str, str] | None) -> float | None:
    """Parse Retry-After as seconds (integer delay) or HTTP-date → remaining sec."""
    if not headers:
        return None
    raw = ""
    for key, value in headers.items():
        if str(key).lower() == "retry-after":
            raw = str(value or "").strip()
            break
    if not raw:
        return None
    # Delay-seconds
    if re.fullmatch(r"\d+", raw):
        return float(max(0, int(raw)))
    # HTTP-date
    try:
        from email.utils import parsedate_to_datetime

        when = parsedate_to_datetime(raw)
        if when is not None:
            return float(max(0.0, when.timestamp() - time.time()))
    except Exception:
        pass
    return None


def suggested_cooldown_seconds(
    headers: Mapping[str, str] | None = None,
    *,
    default: float = 60.0,
) -> float:
    """
    Prefer Retry-After / RateLimit-Reset style headers; else default.
    Never returns less than 5s (avoid tight retry loops).
    """
    hdrs = dict(headers or {})
    retry = parse_retry_after_seconds(hdrs)
    if retry is not None and retry > 0:
        return max(5.0, float(retry))

    # RateLimit-Reset: either delta-seconds or unix epoch
    for key, value in hdrs.items():
        kl = str(key).lower()
        if kl in {"ratelimit-reset", "x-ratelimit-reset", "x-rate-limit-reset"}:
            text = str(value or "").strip()
            if re.fullmatch(r"\d+", text):
                n = int(text)
                # Heuristic: large values are unix timestamps
                if n > 1_000_000_000:
                    return max(5.0, float(n) - time.time())
                return max(5.0, float(n))
    return max(5.0, float(default))


def _compact_body(body: Any, *, limit: int = 800) -> Any:
    if body is None:
        return None
    if isinstance(body, (dict, list)):
        try:
            text = json.dumps(body, ensure_ascii=False, default=str)
        except Exception:
            text = str(body)
        if len(text) > limit:
            return {"_truncated": text[:limit]}
        return body
    text = " ".join(str(body).split())
    return text[:limit]


def record_rate_limit_event(
    *,
    status_code: int = 429,
    method: str = "GET",
    url: str = "",
    error: str = "",
    error_code: str = "",
    body: Any = None,
    response_headers: Mapping[str, str] | None = None,
    latency_ms: int = 0,
    connection_id: str = "",
    base_url: str = "",
    source: str = "edfi_client",
    now_epoch: float | None = None,
) -> dict[str, Any]:
    """
    Persist one rate-limit observation. Safe to call from any request path.
    Never stores credentials or Authorization headers.
    """
    global _LAST_429_EPOCH, _LAST_429_ID

    now = float(now_epoch if now_epoch is not None else time.time())
    headers = extract_rate_limit_headers(response_headers or {})
    cooldown = suggested_cooldown_seconds(headers, default=60.0)
    event_id = f"rl-{int(now)}-{abs(hash((url, status_code, error)) % 10_000):04d}"

    # Redact query secrets if any token-like query params appear (defensive).
    safe_url = _redact_url(url)

    event: dict[str, Any] = {
        "event_id": event_id,
        "kind": "rate_limited",
        "captured_at_epoch": now,
        "captured_at_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
        "status_code": int(status_code or 0),
        "method": str(method or "GET").upper(),
        "url": safe_url,
        "error": " ".join(str(error or "").split())[:400],
        "error_code": str(error_code or "")[:80],
        "body": _compact_body(body),
        "response_headers": headers,
        "latency_ms": int(latency_ms or 0),
        "connection_id": str(connection_id or "")[:80],
        "base_url": _redact_url(base_url),
        "source": str(source or "edfi_client")[:80],
        "suggested_cooldown_sec": cooldown,
        "retry_after_sec": parse_retry_after_seconds(headers),
        "note": (
            "Passive capture from a real TEA/ODS response. "
            "Do not hammer the API to force more samples."
        ),
    }

    evidence_dir()
    LATEST_PATH.write_text(json.dumps(event, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    with EVENTS_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")

    _LAST_429_EPOCH = now
    _LAST_429_ID = event_id
    return event


def record_recovery_if_pending(
    *,
    method: str = "GET",
    url: str = "",
    status_code: int = 200,
    connection_id: str = "",
    now_epoch: float | None = None,
) -> dict[str, Any] | None:
    """
    If we previously saw a 429 in this process, record how long until a success.
    This is the safe way to learn cooldown without a flood probe.
    """
    global _LAST_429_EPOCH, _LAST_429_ID
    if _LAST_429_EPOCH <= 0:
        return None
    now = float(now_epoch if now_epoch is not None else time.time())
    recovered_after = max(0.0, now - _LAST_429_EPOCH)
    event: dict[str, Any] = {
        "event_id": f"rec-{int(now)}",
        "kind": "recovered_after_rate_limit",
        "captured_at_epoch": now,
        "captured_at_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
        "prior_rate_limit_event_id": _LAST_429_ID,
        "recovered_after_sec": round(recovered_after, 2),
        "status_code": int(status_code or 0),
        "method": str(method or "GET").upper(),
        "url": _redact_url(url),
        "connection_id": str(connection_id or "")[:80],
        "note": (
            "A later legitimate request succeeded after a rate-limit. "
            "This elapsed time is observed recovery, not an official TEA SLA."
        ),
    }
    evidence_dir()
    with EVENTS_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
    # Clear so we only measure first success after each 429.
    _LAST_429_EPOCH = 0.0
    _LAST_429_ID = ""
    return event


def load_latest_evidence() -> dict[str, Any] | None:
    if not LATEST_PATH.is_file():
        return None
    try:
        data = json.loads(LATEST_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def load_recent_events(*, limit: int = 20) -> list[dict[str, Any]]:
    if not EVENTS_PATH.is_file():
        return []
    lines = EVENTS_PATH.read_text(encoding="utf-8").splitlines()
    rows: list[dict[str, Any]] = []
    for line in lines[-max(1, int(limit)) :]:
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except Exception:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows


def evidence_summary() -> dict[str, Any]:
    latest = load_latest_evidence()
    events = load_recent_events(limit=50)
    recoveries = [e for e in events if e.get("kind") == "recovered_after_rate_limit"]
    rate_events = [e for e in events if e.get("kind") == "rate_limited"]
    observed = [float(r.get("recovered_after_sec") or 0) for r in recoveries if r.get("recovered_after_sec")]
    return {
        "ok": True,
        "evidence_dir": str(EVIDENCE_DIR),
        "latest": latest,
        "rate_limit_event_count_recent": len(rate_events),
        "recovery_event_count_recent": len(recoveries),
        "observed_recovery_sec": {
            "samples": observed[-10:],
            "min": min(observed) if observed else None,
            "max": max(observed) if observed else None,
            "avg": (sum(observed) / len(observed)) if observed else None,
        },
        "safety": {
            "deliberate_flood_probe": "disabled",
            "guidance": (
                "Do not send requests until you force a 429. "
                "That can look like abuse and may flag or throttle the client key/IP. "
                "Use normal Refresh once; if limited, evidence is captured automatically. "
                "Retry later to record recovery timing."
            ),
        },
    }


def maybe_record_from_response(
    *,
    status_code: int,
    method: str,
    url: str,
    error: str = "",
    error_code: str = "",
    body: Any = None,
    response_headers: Mapping[str, Any] | None = None,
    latency_ms: int = 0,
    connection_id: str = "",
    base_url: str = "",
    source: str = "edfi_client",
) -> dict[str, Any] | None:
    """Record if status is 429 or body/error looks rate-limited."""
    code = int(status_code or 0)
    text = f"{error} {body}".lower()
    limited = code == 429 or "ratelimit" in text.replace(" ", "") or "rate_limit" in text
    if not limited:
        if 200 <= code < 300:
            return record_recovery_if_pending(
                method=method,
                url=url,
                status_code=code,
                connection_id=connection_id,
            )
        return None
    return record_rate_limit_event(
        status_code=code or 429,
        method=method,
        url=url,
        error=error,
        error_code=error_code,
        body=body,
        response_headers=extract_rate_limit_headers(response_headers),
        latency_ms=latency_ms,
        connection_id=connection_id,
        base_url=base_url,
        source=source,
    )


def _redact_url(url: str) -> str:
    text = str(url or "").strip()
    if not text:
        return ""
    # Drop query string secrets if present
    if "?" in text:
        base, _, query = text.partition("?")
        if any(k in query.lower() for k in ("secret", "token", "password", "key=")):
            return base + "?[redacted]"
    return text[:500]
