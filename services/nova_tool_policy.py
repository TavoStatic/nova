from __future__ import annotations

import hashlib
import mimetypes
import time
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlparse

import requests


def research_handlers(
    *,
    tool_web_fetch_fn: Callable[..., object],
    tool_web_search_fn: Callable[..., object],
    tool_web_research_fn: Callable[..., object],
    tool_web_gather_fn: Callable[..., object],
    tool_wikipedia_lookup_fn: Callable[..., object],
    tool_stackexchange_search_fn: Callable[..., object],
) -> dict[str, object]:
    return {
        "web_fetch": tool_web_fetch_fn,
        "web_search": tool_web_search_fn,
        "web_research": tool_web_research_fn,
        "web_gather": tool_web_gather_fn,
        "wikipedia_lookup": tool_wikipedia_lookup_fn,
        "stackexchange_search": tool_stackexchange_search_fn,
    }


def execute_research_action(
    action: str,
    value: str,
    *,
    execute_registered_tool_fn: Callable[..., str],
    research_handlers_fn: Callable[[], dict[str, object]],
) -> str:
    return execute_registered_tool_fn(
        "research",
        {"action": str(action or "").strip(), "value": str(value or "").strip()},
        extra={"research_handlers": research_handlers_fn()},
    )


def patch_handlers(
    *,
    patch_preview_fn: Callable[..., object],
    list_previews_fn: Callable[[], object],
    show_preview_fn: Callable[..., object],
    approve_preview_fn: Callable[..., object],
    reject_preview_fn: Callable[..., object],
    patch_apply_fn: Callable[..., object],
    patch_rollback_fn: Callable[..., object],
) -> dict[str, object]:
    return {
        "preview": patch_preview_fn,
        "list_previews": lambda _value="": list_previews_fn(),
        "show": show_preview_fn,
        "approve": approve_preview_fn,
        "reject": reject_preview_fn,
        "apply": patch_apply_fn,
        "rollback": lambda _value="": patch_rollback_fn(_value or None),
    }


def execute_patch_action(
    action: str,
    value: str = "",
    *,
    force: bool = False,
    is_admin: bool = True,
    execute_registered_tool_fn: Callable[..., str],
    patch_handlers_fn: Callable[[], dict[str, object]],
) -> str:
    return execute_registered_tool_fn(
        "patch",
        {"action": str(action or "").strip(), "value": str(value or "").strip(), "force": bool(force)},
        is_admin=is_admin,
        extra={"patch_handlers": patch_handlers_fn()},
    )


def web_allowlist_message(context: str = "", *, policy_web_fn: Callable[[], dict]) -> str:
    cfg = policy_web_fn()
    allow_domains = cfg.get("allow_domains") or []
    if not allow_domains:
        return "I attempted to access the web, but web access is restricted by policy and no allowlisted domains are configured."

    lines = [f"I attempted to access the web{(' for ' + context) if context else ''}, but my web tool only allows specific sources:"]
    for domain in allow_domains:
        lines.append(f"- {domain}")

    preferred = None
    for candidate in ("api.weather.gov", "noaa.gov", "weather.gov"):
        for domain in allow_domains:
            if candidate in domain:
                preferred = candidate
                break
        if preferred:
            break

    if preferred:
        lines.append(f"If you'd like, I can try again using {preferred}.")
    else:
        lines.append("If you'd like, tell me which of the allowlisted domains to try, or provide an allowed URL to fetch.")
    lines.append("To add a new allowed domain, use: policy allow <domain>")
    return "\n".join(lines)


def web_fetch(
    url: str,
    save_dir: Path,
    *,
    web_enabled_fn: Callable[[], bool],
    policy_web_fn: Callable[[], dict],
    host_allowed_fn: Callable[[str, list[str]], bool],
) -> dict:
    if not web_enabled_fn():
        return {"ok": False, "error": "Web tool disabled by policy."}

    cfg = policy_web_fn()
    allow_domains = cfg.get("allow_domains") or []
    max_bytes = int(cfg.get("max_bytes") or 20_000_000)

    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https"):
        return {"ok": False, "error": "Only http/https URLs are allowed."}
    host = parsed.hostname or ""
    if not host_allowed_fn(host, allow_domains):
        return {"ok": False, "error": f"Domain not allowed: {host}"}

    save_dir.mkdir(parents=True, exist_ok=True)

    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    ts = time.strftime("%Y%m%d_%H%M%S")
    base = f"{ts}_{host}_{digest}"

    try:
        response = requests.get(url, stream=True, timeout=60, headers={"User-Agent": "Nova/1.0"})
    except requests.exceptions.RequestException as e:
        return {"ok": False, "error": f"Request failed: {e}"}

    try:
        response.raise_for_status()
        ctype = (response.headers.get("Content-Type") or "").split(";")[0].strip().lower()

        if ctype == "application/pdf":
            ext = ".pdf"
        elif ctype in ("text/html", "application/xhtml+xml"):
            ext = ".html"
        elif ctype.startswith("text/"):
            ext = ".txt"
        else:
            ext = mimetypes.guess_extension(ctype) or ".bin"

        out_path = save_dir / (base + ext)
        total = 0
        with open(out_path, "wb") as handle:
            for chunk in response.iter_content(chunk_size=65536):
                if not chunk:
                    continue
                total += len(chunk)
                if total > max_bytes:
                    out_path.unlink(missing_ok=True)
                    return {"ok": False, "error": f"File too large (>{max_bytes} bytes)."}
                handle.write(chunk)

        return {"ok": True, "url": url, "path": str(out_path), "content_type": ctype, "bytes": total}
    except requests.exceptions.RequestException as e:
        return {"ok": False, "error": f"HTTP error: {e}"}
    except Exception as e:
        return {"ok": False, "error": f"Unexpected error: {e}"}
    finally:
        try:
            response.close()
        except Exception:
            pass