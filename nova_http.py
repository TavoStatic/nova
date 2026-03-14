from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, List, Tuple
from urllib.parse import parse_qs, urlparse

import nova_core
import requests


SESSION_TURNS: Dict[str, List[Tuple[str, str]]] = {}
MAX_TURNS = 40
BASE_DIR = Path(__file__).resolve().parent
LOG_DIR = BASE_DIR / "logs"
RUNTIME_DIR = BASE_DIR / "runtime"
SESSION_STORE_PATH = RUNTIME_DIR / "http_chat_sessions.json"
MAX_STORED_SESSIONS = 120
MAX_STORED_TURNS_PER_SESSION = MAX_TURNS * 2
VENV_PY = BASE_DIR / ".venv" / "Scripts" / "python.exe"
GUARD_PY = BASE_DIR / "nova_guard.py"
STOP_GUARD_PY = BASE_DIR / "stop_guard.py"

CONTROL_SESSIONS: Dict[str, float] = {}
CONTROL_SESSION_TTL_SECONDS = 8 * 60 * 60

_METRICS_LOCK = threading.Lock()
_HTTP_REQUESTS_TOTAL = 0
_HTTP_ERRORS_TOTAL = 0
_METRICS_SERIES: List[dict] = []
_METRICS_MAX_POINTS = 240
_SESSION_LOCK = threading.Lock()


def _load_persisted_sessions() -> None:
    try:
        if not SESSION_STORE_PATH.exists():
            return
        data = json.loads(SESSION_STORE_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return
        loaded: Dict[str, List[Tuple[str, str]]] = {}
        for sid, turns in data.items():
            if not isinstance(sid, str) or not isinstance(turns, list):
                continue
            cleaned: List[Tuple[str, str]] = []
            for it in turns[-MAX_STORED_TURNS_PER_SESSION:]:
                if not isinstance(it, dict):
                    continue
                role = str(it.get("role") or "").strip().lower()
                text = str(it.get("text") or "").strip()
                if role not in {"user", "assistant"} or not text:
                    continue
                cleaned.append((role, text))
            if cleaned:
                loaded[sid] = cleaned
        SESSION_TURNS.clear()
        SESSION_TURNS.update(loaded)
    except Exception:
        pass


def _persist_sessions() -> None:
    try:
        RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        items = list(SESSION_TURNS.items())
        if len(items) > MAX_STORED_SESSIONS:
            items = items[-MAX_STORED_SESSIONS:]

        payload = {}
        for sid, turns in items:
            safe_turns = []
            for role, text in turns[-MAX_STORED_TURNS_PER_SESSION:]:
                safe_turns.append({"role": role, "text": text})
            payload[sid] = safe_turns

        tmp = SESSION_STORE_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")
        tmp.replace(SESSION_STORE_PATH)
    except Exception:
        pass


def _append_session_turn(session_id: str, role: str, text: str) -> List[Tuple[str, str]]:
    with _SESSION_LOCK:
        turns = SESSION_TURNS.setdefault(session_id, [])
        turns.append((role, text))
        _trim_turns(turns)
        _persist_sessions()
        return turns


def _get_session_turns(session_id: str) -> List[Tuple[str, str]]:
    with _SESSION_LOCK:
        return list(SESSION_TURNS.get(session_id, []))


def _session_summaries(limit: int = 60) -> List[dict]:
    with _SESSION_LOCK:
        items = list(SESSION_TURNS.items())[-max(1, int(limit)):]

    out = []
    for sid, turns in reversed(items):
        if not sid:
            continue
        last_user = ""
        last_assistant = ""
        for role, text in reversed(turns):
            if not last_user and role == "user":
                last_user = (text or "").strip()[:180]
            if not last_assistant and role == "assistant":
                last_assistant = (text or "").strip()[:180]
            if last_user and last_assistant:
                break
        out.append(
            {
                "session_id": sid,
                "turn_count": len(turns),
                "last_user": last_user,
                "last_assistant": last_assistant,
            }
        )
    return out


def _delete_session(session_id: str) -> tuple[bool, str]:
    sid = (session_id or "").strip()
    if not sid:
        return False, "session_id_required"
    with _SESSION_LOCK:
        existed = sid in SESSION_TURNS
        SESSION_TURNS.pop(sid, None)
        _persist_sessions()
    return True, "session_deleted" if existed else "session_not_found"


def _parse_request_path(raw_path: str) -> tuple[str, dict]:
    parsed = urlparse(raw_path or "/")
    return parsed.path or "/", parse_qs(parsed.query or "", keep_blank_values=True)


def _request_control_key(handler: BaseHTTPRequestHandler, qs: dict) -> str:
    h = (handler.headers.get("X-Nova-Control-Key") or "").strip()
    if h:
        return h
    return str((qs.get("key") or [""])[0]).strip()


def _is_local_client(handler: BaseHTTPRequestHandler) -> bool:
    ip = (handler.client_address[0] or "").strip().lower()
    return ip in {"127.0.0.1", "::1", "localhost"}


def _control_auth(handler: BaseHTTPRequestHandler, qs: dict) -> tuple[bool, str]:
    ok_login, why_login = _control_login_auth(handler)
    if not ok_login:
        return False, why_login

    expected = (os.environ.get("NOVA_CONTROL_TOKEN") or "").strip()
    if expected:
        got = _request_control_key(handler, qs)
        if got and secrets.compare_digest(got, expected):
            return True, ""
        return False, "control_auth_failed"

    if _is_local_client(handler):
        return True, ""
    return False, "control_local_only_set_NOVA_CONTROL_TOKEN"


def _record_http_response(code: int) -> None:
    global _HTTP_REQUESTS_TOTAL, _HTTP_ERRORS_TOTAL
    with _METRICS_LOCK:
        _HTTP_REQUESTS_TOTAL += 1
        if int(code) >= 400:
            _HTTP_ERRORS_TOTAL += 1


def _parse_cookie_map(handler: BaseHTTPRequestHandler) -> dict:
    raw = (handler.headers.get("Cookie") or "").strip()
    out = {}
    if not raw:
        return out
    parts = raw.split(";")
    for p in parts:
        if "=" not in p:
            continue
        k, v = p.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def _control_login_enabled() -> bool:
    u = (os.environ.get("NOVA_CONTROL_USER") or "").strip()
    p = (os.environ.get("NOVA_CONTROL_PASS") or "").strip()
    return bool(u and p)


def _prune_control_sessions() -> None:
    now = time.time()
    stale = [k for k, exp in CONTROL_SESSIONS.items() if exp <= now]
    for k in stale:
        CONTROL_SESSIONS.pop(k, None)


def _control_login_auth(handler: BaseHTTPRequestHandler) -> tuple[bool, str]:
    if not _control_login_enabled():
        return True, ""

    _prune_control_sessions()
    cookies = _parse_cookie_map(handler)
    sid = (cookies.get("nova_control_session") or "").strip()
    if sid and CONTROL_SESSIONS.get(sid, 0) > time.time():
        return True, ""
    return False, "control_login_required"


def _control_page_gate(handler: BaseHTTPRequestHandler) -> tuple[bool, str]:
    ok_login, reason_login = _control_login_auth(handler)
    if not ok_login:
        return False, reason_login

    expected = (os.environ.get("NOVA_CONTROL_TOKEN") or "").strip()
    if expected:
        return True, ""
    if _is_local_client(handler):
        return True, ""
    return False, "control_local_only_set_NOVA_CONTROL_TOKEN"


def _new_control_session() -> str:
    sid = secrets.token_hex(24)
    CONTROL_SESSIONS[sid] = time.time() + CONTROL_SESSION_TTL_SECONDS
    return sid


def _clear_control_session(handler: BaseHTTPRequestHandler) -> None:
    sid = (_parse_cookie_map(handler).get("nova_control_session") or "").strip()
    if sid:
        CONTROL_SESSIONS.pop(sid, None)


def _guard_status_payload() -> dict:
    pid_file = RUNTIME_DIR / "guard_pid.json"
    lock_file = RUNTIME_DIR / "guard.lock"
    stop_file = RUNTIME_DIR / "guard.stop"
    running = False
    pid = None
    if pid_file.exists():
        try:
            data = json.loads(pid_file.read_text(encoding="utf-8"))
            pid = int(data.get("pid", 0) or 0)
            if pid > 0:
                try:
                    os.kill(pid, 0)
                    running = True
                except Exception:
                    running = False
        except Exception:
            pass
    return {
        "running": running,
        "pid": pid,
        "lock_exists": lock_file.exists(),
        "stop_flag": stop_file.exists(),
    }


def _start_guard() -> tuple[bool, str]:
    if not VENV_PY.exists():
        return False, f"venv_python_missing:{VENV_PY}"
    if not GUARD_PY.exists():
        return False, f"guard_script_missing:{GUARD_PY}"
    gs = _guard_status_payload()
    if gs.get("running"):
        return True, "guard_already_running"

    try:
        flags = 0
        if os.name == "nt":
            flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
        subprocess.Popen(
            [str(VENV_PY), str(GUARD_PY)],
            cwd=str(BASE_DIR),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=flags,
        )
        return True, "guard_start_requested"
    except Exception as e:
        return False, f"guard_start_failed:{e}"


def _stop_guard() -> tuple[bool, str]:
    if not VENV_PY.exists() or not STOP_GUARD_PY.exists():
        return False, "stop_guard_script_missing"
    try:
        p = subprocess.run(
            [str(VENV_PY), str(STOP_GUARD_PY)],
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            timeout=25,
        )
        out = (p.stdout or "").strip()
        err = (p.stderr or "").strip()
        if p.returncode == 0:
            return True, out or "guard_stop_requested"
        msg = out or err or f"exit:{p.returncode}"
        return False, f"guard_stop_failed:{msg}"
    except Exception as e:
        return False, f"guard_stop_failed:{e}"


def _append_metrics_snapshot(status_payload: dict) -> None:
    with _METRICS_LOCK:
        point = {
            "ts": int(time.time()),
            "heartbeat_age_sec": status_payload.get("heartbeat_age_sec"),
            "requests_total": _HTTP_REQUESTS_TOTAL,
            "errors_total": _HTTP_ERRORS_TOTAL,
            "ollama_api_up": bool(status_payload.get("ollama_api_up")),
            "searxng_ok": status_payload.get("searxng_ok"),
        }
        _METRICS_SERIES.append(point)
        if len(_METRICS_SERIES) > _METRICS_MAX_POINTS:
            del _METRICS_SERIES[: len(_METRICS_SERIES) - _METRICS_MAX_POINTS]


def _metrics_payload() -> dict:
    with _METRICS_LOCK:
        return {
            "ok": True,
            "requests_total": _HTTP_REQUESTS_TOTAL,
            "errors_total": _HTTP_ERRORS_TOTAL,
            "points": list(_METRICS_SERIES),
        }


def _tail_file(path: Path, max_lines: int = 120) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
        lines = text.splitlines()
        return "\n".join(lines[-max_lines:])
    except Exception as e:
        return f"Unable to read {path.name}: {e}"


def _heartbeat_age_seconds() -> int | None:
    hb = RUNTIME_DIR / "core.heartbeat"
    if not hb.exists():
        return None
    try:
        return max(0, int(time.time() - hb.stat().st_mtime))
    except Exception:
        return None


def _probe_searxng(endpoint: str, timeout: float = 2.5) -> tuple[bool, str]:
    try:
        r = requests.get(
            endpoint,
            params={"q": "health", "format": "json"},
            headers={"User-Agent": "Nova/1.0", "Accept": "application/json"},
            timeout=timeout,
        )
        return r.status_code == 200, f"status={r.status_code}"
    except Exception as e:
        return False, f"error:{e}"


def _control_status_payload() -> dict:
    p = nova_core.load_policy()
    web_cfg = p.get("web") or {}
    provider = str(web_cfg.get("search_provider") or "html").strip().lower()
    endpoint = str(web_cfg.get("search_api_endpoint") or "").strip()

    searx_ok = None
    searx_note = "n/a"
    if provider == "searxng" and endpoint:
        searx_ok, searx_note = _probe_searxng(endpoint)

    payload = {
        "ok": True,
        "server_time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "ollama_api_up": bool(nova_core.ollama_api_up()),
        "chat_model": nova_core.chat_model(),
        "memory_enabled": bool(nova_core.mem_enabled()),
        "web_enabled": bool((p.get("tools_enabled") or {}).get("web")) and bool(web_cfg.get("enabled")),
        "search_provider": provider,
        "search_api_endpoint": endpoint,
        "allow_domains_count": len(web_cfg.get("allow_domains") or []),
        "heartbeat_age_sec": _heartbeat_age_seconds(),
        "active_http_sessions": len(SESSION_TURNS),
        "searxng_ok": searx_ok,
        "searxng_note": searx_note,
        "guard": _guard_status_payload(),
    }
    with _METRICS_LOCK:
        payload["requests_total"] = _HTTP_REQUESTS_TOTAL
        payload["errors_total"] = _HTTP_ERRORS_TOTAL
    _append_metrics_snapshot(payload)
    return payload


def _control_policy_payload() -> dict:
    p = nova_core.load_policy()
    return {
        "ok": True,
        "tools_enabled": p.get("tools_enabled") or {},
        "models": p.get("models") or {},
        "memory": p.get("memory") or {},
        "web": p.get("web") or {},
    }


def _control_action(action: str, payload: dict) -> tuple[bool, str, dict]:
    act = (action or "").strip().lower()
    if not act:
        return False, "action_required", {}

    if act == "refresh_status":
        return True, "status_refreshed", _control_status_payload()

    if act == "guard_status":
        return True, "guard_status_ok", {"guard": _guard_status_payload()}

    if act == "guard_start":
        ok, msg = _start_guard()
        return ok, msg, {"guard": _guard_status_payload()}

    if act == "guard_stop":
        ok, msg = _stop_guard()
        return ok, msg, {"guard": _guard_status_payload()}

    if act == "policy_allow":
        domain = str(payload.get("domain") or "").strip()
        return True, nova_core.policy_allow_domain(domain), {}

    if act == "policy_remove":
        domain = str(payload.get("domain") or "").strip()
        return True, nova_core.policy_remove_domain(domain), {}

    if act == "web_mode":
        mode = str(payload.get("mode") or "").strip()
        return True, nova_core.set_web_mode(mode), {}

    if act == "inspect":
        try:
            data = nova_core.inspect_environment()
            return True, "inspect_ok", {"report": nova_core.format_report(data)}
        except Exception as e:
            return False, f"inspect_failed:{e}", {}

    if act == "policy_audit":
        try:
            return True, "policy_audit_ok", {"text": nova_core.policy_audit(30)}
        except Exception as e:
            return False, f"policy_audit_failed:{e}", {}

    if act == "tail_log":
        name = str(payload.get("name") or "").strip().lower()
        allowed = {
            "nova_http.out.log": LOG_DIR / "nova_http.out.log",
            "nova_http.err.log": LOG_DIR / "nova_http.err.log",
            "guard.log": LOG_DIR / "guard.log",
        }
        if name not in allowed:
            return False, "invalid_log_name", {}
        return True, "tail_log_ok", {"name": name, "text": _tail_file(allowed[name])}

    if act == "metrics":
        return True, "metrics_ok", _metrics_payload()

    if act == "session_delete":
        ok, msg = _delete_session(str(payload.get("session_id") or ""))
        return ok, msg, {"sessions": _session_summaries(80)}

    return False, "unknown_action", {}


def _trim_turns(turns: List[Tuple[str, str]]) -> None:
    if len(turns) > MAX_TURNS * 2:
        del turns[: len(turns) - (MAX_TURNS * 2)]


def _json_response(handler: BaseHTTPRequestHandler, code: int, payload: dict) -> None:
    body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(body)
    _record_http_response(code)


def _fast_smalltalk_reply(user_text: str) -> str | None:
    t = (user_text or "").strip().lower()
    if not t:
        return "Okay."

    if re.match(r"^(hi|hello|hey)([\s!,\.]|$)", t):
        return "Hi there!"

    if "how are you" in t:
        return "I'm doing well."

    if "thank you" in t or t in {"thanks", "thx"}:
        return "You're welcome."

    if any(p in t for p in ["who is your developer", "who's your developer"]):
        return "My developer is Gustavo (Gus). He created me."

    return None


def _diagnostic_reply(known: str, missing: str, need: str) -> str:
    return f"I know: {known} I do not yet know: {missing} To answer better, I need: {need}"


def _text_response(handler: BaseHTTPRequestHandler, code: int, text: str) -> None:
    body = text.encode("utf-8")
    handler.send_response(code)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(body)
    _record_http_response(code)


def _developer_color_reply(turns: List[Tuple[str, str]]) -> str:
    prefs = nova_core._extract_developer_color_preferences(turns)
    if not prefs:
        prefs = nova_core._extract_developer_color_preferences_from_memory()
    if not prefs:
        return "I don't have Gus's color preferences yet."
    if len(prefs) == 1:
        return f"From what you've told me, Gus likes {prefs[0]}."
    return "From what you've told me, Gus likes these colors: " + ", ".join(prefs[:-1]) + f", and {prefs[-1]}."


def _developer_bilingual_reply(turns: List[Tuple[str, str]]) -> str:
    known = nova_core._developer_is_bilingual(turns)
    if known is None:
        known = nova_core._developer_is_bilingual_from_memory()
    if known is True:
        return "Yes. From what you've told me, Gus is bilingual in English and Spanish."
    if known is False:
        return "From what I have, Gus is not bilingual."
    return "I don't have confirmed language details for Gus yet."


def _is_developer_profile_request(user_text: str) -> bool:
    t = (user_text or "").lower()
    has_subject = any(k in t for k in ["developer", "gus", "gustavo"])

    # Pronoun follow-ups that are almost always about previously established developer context.
    pronoun_cues = [
        "how did he develop you", "how did he developed you", "how did he build you",
        "how was he able to develop you", "what else does he",
    ]
    if any(c in t for c in pronoun_cues):
        return True

    if not has_subject:
        return False
    cues = [
        "who is", "who's", "what do you know", "what else", "tell me about",
        "about your developer", "about gus", "about gustavo", "how did", "created you",
        "developed you", "built you",
    ]
    return any(c in t for c in cues)


def _developer_profile_reply(turns: List[Tuple[str, str]], user_text: str) -> str:
    low = (user_text or "").lower()

    base_fact = "My developer is Gustavo (Gus)."
    created_fact = "He created me."

    if "how did" in low or "developed you" in low or "built you" in low:
        return (
            f"{base_fact} {created_fact} "
            "I do not have detailed build-history notes in memory yet."
        )

    facts: List[str] = [base_fact, created_fact]
    has_extra = False

    bilingual = nova_core._developer_is_bilingual(turns)
    if bilingual is None:
        bilingual = nova_core._developer_is_bilingual_from_memory()
    if bilingual is True:
        facts.append("He is bilingual in English and Spanish.")
        has_extra = True

    colors = nova_core._extract_developer_color_preferences(turns)
    if not colors:
        colors = nova_core._extract_developer_color_preferences_from_memory()
    if colors:
        if len(colors) == 1:
            facts.append(f"His known favorite color is {colors[0]}.")
        else:
            facts.append(
                "Known favorite colors: " + ", ".join(colors[:-1]) + f", and {colors[-1]}."
            )
        has_extra = True

    # Memory expansion can be relatively slow; only use it for explicit "what else/what do you know" asks.
    if any(k in low for k in ["what else", "what do you know", "tell me about", "about gus", "about your developer"]):
        mem = nova_core.mem_recall("gustavo gus developer profile facts created me")
        extra = []
        for ln in (mem or "").splitlines():
            s = (ln or "").strip().lstrip("-").strip()
            if not s:
                continue
            low_s = s.lower()
            if not any(a in low_s for a in ["gus", "gustavo", "developer"]):
                continue
            if any(s.rstrip(".") == f.rstrip(".") for f in facts):
                continue
            extra.append(s.rstrip(".") + ".")
            if len(extra) >= 2:
                break
        if extra:
            has_extra = True
            facts.extend(extra)

    if "who is" in low or "who's" in low:
        return f"{base_fact} {created_fact}"

    if any(k in low for k in ["what else", "what do you know", "tell me about", "about gus", "about your developer"]) and not has_extra:
        return _diagnostic_reply(
            "Gus is my developer and he created me.",
            "richer confirmed profile details about him.",
            "you to add specific facts, for example: 'Gus favorite colors are ...' or 'Gus is bilingual in ...'.",
        )

    return " ".join(facts)


def _is_location_request(user_text: str) -> bool:
    t = (user_text or "").lower().strip()
    triggers = [
        "where is nova", "where are you", "your location", "what is your location",
        "where are you located", "where is nova located",
    ]
    return any(x in t for x in triggers)


def _location_reply() -> str:
    try:
        audit_out = nova_core.mem_audit("location")
        j = json.loads(audit_out) if audit_out else {}
        results = j.get("results") if isinstance(j, dict) else []
        if results:
            top = results[0]
            preview = nova_core._normalize_location_preview((top.get("preview") or "").strip())
            if preview:
                return f"I know: I run locally and I have a stored location fact: {preview}."
    except Exception:
        pass

    return _diagnostic_reply(
        "I run locally on this machine.",
        "a confirmed physical location for this running host.",
        "a direct fact such as 'My location is <city/state/country>' or permission to query system/network location tools.",
    )


def _color_reply(turns: List[Tuple[str, str]]) -> str:
    prefs = nova_core._extract_color_preferences(turns)
    if not prefs:
        prefs = nova_core._extract_color_preferences_from_memory()
    if not prefs:
        return "You haven't told me a color preference in this current chat yet."
    if len(prefs) == 1:
        return f"You told me you like the color {prefs[0]}."
    return "You told me you like these colors: " + ", ".join(prefs[:-1]) + f", and {prefs[-1]}."


def _animal_reply(turns: List[Tuple[str, str]]) -> str:
    animals = nova_core._extract_animal_preferences(turns)
    if not animals:
        animals = nova_core._extract_animal_preferences_from_memory()
    if not animals:
        return "You haven't told me animal preferences yet in this chat, and I can't find them in saved memory."
    if len(animals) == 1:
        return f"You told me you like {animals[0]}."
    return "You told me you like: " + ", ".join(animals[:-1]) + f", and {animals[-1]}."


def _extract_last_user_question(turns: List[Tuple[str, str]], current_text: str) -> str:
    target = (current_text or "").strip().lower()
    users = [t for r, t in turns if r == "user" and (t or "").strip()]
    if not users:
        return ""
    # users[-1] is the current message (already appended). Return the previous one.
    if len(users) >= 2:
        return users[-2].strip()
    return ""


def _is_name_origin_question(text: str) -> bool:
    low = (text or "").strip().lower()
    cues = [
        "where your name comes from",
        "where does your name come from",
        "story behind your name",
        "why are you called nova",
        "do you know where your name comes from",
        "what does your name mean",
    ]
    return any(c in low for c in cues)


def _maybe_store_name_origin(text: str) -> tuple[bool, str]:
    raw = (text or "").strip()
    low = raw.lower()
    trigger = (
        "remember this nova" in low
        or "story behind your name" in low
        or low.startswith("remember this")
    )
    if not trigger:
        return False, ""
    stored = nova_core.remember_name_origin(raw)
    return True, stored


def _rules_reply() -> str:
    return (
        "Yes. I follow strict operating rules: I do not fabricate tool actions or files, "
        "I stay within enabled policy/tool limits, and I should say uncertain when I cannot verify something."
    )


def process_chat(session_id: str, user_text: str) -> str:
    text = nova_core._strip_invocation_prefix((user_text or "").strip())
    if not text:
        return "Okay."

    quick = _fast_smalltalk_reply(text)
    if quick:
        return quick

    turns = _append_session_turn(session_id, "user", text)

    stored, store_reply = _maybe_store_name_origin(text)
    if stored:
        reply = nova_core._ensure_reply(store_reply)
        _append_session_turn(session_id, "assistant", reply)
        return reply

    if nova_core._is_declarative_info(text) and nova_core.mem_should_store(text):
        nova_core.mem_add("fact", "typed", text)

    low = text.lower()
    if "what was my last question" in low or "what was my previous question" in low:
        last_q = _extract_last_user_question(turns, text)
        if last_q:
            reply = f"Your last question before this one was: {last_q}"
        else:
            reply = "I don't have an earlier question in this active chat session."
    elif "do you remember our last chat session" in low or "remember our last chat" in low:
        reply = "I remember parts of prior chats only if they were saved to memory; I remember this live session context directly."
    elif "do you have any rules" in low or "what rules do you follow" in low:
        reply = _rules_reply()
    elif _is_name_origin_question(text):
        story = nova_core.get_name_origin_story().strip()
        if story:
            reply = f"Yes. {story}"
        else:
            reply = "I do not have a saved name-origin story yet. You can tell me with: remember this Nova ..."
    elif _is_developer_profile_request(text):
        reply = _developer_profile_reply(turns, text)
    elif _is_location_request(text):
        reply = _location_reply()
    elif nova_core._is_developer_color_lookup_request(text):
        reply = _developer_color_reply(turns)
    elif nova_core._is_developer_bilingual_request(text):
        reply = _developer_bilingual_reply(turns)
    elif nova_core._is_color_lookup_request(text):
        reply = _color_reply(turns)
    elif "what animals do i like" in low or "which animals do i like" in low:
        reply = _animal_reply(turns)
    else:
        retrieved = ""
        # Avoid context bleed: only pull broad memory context when the user
        # explicitly references prior info or asks profile/recall style questions.
        if nova_core._uses_prior_reference(text) or any(k in low for k in ["remember", "profile", "who am i", "what do you know", "name"]):
            retrieved = nova_core.build_learning_context(text)
            chat_ctx = nova_core._render_chat_context(turns)
            if chat_ctx:
                retrieved = (retrieved + "\n\nCURRENT CHAT CONTEXT:\n" + chat_ctx).strip()[:6000]
        reply = nova_core.ollama_chat(text, retrieved_context=retrieved)
        reply = nova_core.sanitize_llm_reply(reply, "")

    reply = nova_core._apply_reply_overrides(reply)
    reply = nova_core._ensure_reply(reply)

    _append_session_turn(session_id, "assistant", reply)
    return reply


class NovaHttpHandler(BaseHTTPRequestHandler):
    server_version = "NovaHTTP/0.1"

    def do_GET(self) -> None:
        path, qs = _parse_request_path(self.path)

        if path == "/":
            _text_response(self, 200, INDEX_HTML)
            return

        if path == "/control/login":
            if not _control_login_enabled():
                _json_response(self, 404, {"ok": False, "error": "control_login_disabled"})
                return
            ok_page, reason_page = _control_page_gate(self)
            if not ok_page and reason_page != "control_login_required":
                _json_response(self, 403, {"ok": False, "error": reason_page})
                return
            _text_response(self, 200, CONTROL_LOGIN_HTML)
            return

        if path == "/control":
            ok_page, reason_page = _control_page_gate(self)
            if not ok_page:
                if reason_page == "control_login_required":
                    _text_response(self, 200, CONTROL_LOGIN_HTML)
                else:
                    _json_response(self, 403, {"ok": False, "error": reason_page})
                return
            _text_response(self, 200, CONTROL_HTML)
            return

        if path == "/api/health":
            payload = {
                "ok": True,
                "ollama_api_up": bool(nova_core.ollama_api_up()),
                "chat_model": nova_core.chat_model(),
                "memory_enabled": bool(nova_core.mem_enabled()),
            }
            _json_response(self, 200, payload)
            return

        if path == "/api/chat/history":
            sid = str((qs.get("session_id") or [""])[0]).strip()
            if not sid:
                _json_response(self, 400, {"ok": False, "error": "session_id_required"})
                return
            turns = _get_session_turns(sid)
            _json_response(
                self,
                200,
                {
                    "ok": True,
                    "session_id": sid,
                    "turns": [{"role": r, "text": t} for r, t in turns[-MAX_STORED_TURNS_PER_SESSION:]],
                },
            )
            return

        if path == "/api/control/status":
            ok, reason = _control_auth(self, qs)
            if not ok:
                _json_response(self, 403, {"ok": False, "error": reason})
                return
            _json_response(self, 200, _control_status_payload())
            return

        if path == "/api/control/policy":
            ok, reason = _control_auth(self, qs)
            if not ok:
                _json_response(self, 403, {"ok": False, "error": reason})
                return
            _json_response(self, 200, _control_policy_payload())
            return

        if path == "/api/control/metrics":
            ok, reason = _control_auth(self, qs)
            if not ok:
                _json_response(self, 403, {"ok": False, "error": reason})
                return
            _json_response(self, 200, _metrics_payload())
            return

        if path == "/api/control/sessions":
            ok, reason = _control_auth(self, qs)
            if not ok:
                _json_response(self, 403, {"ok": False, "error": reason})
                return
            _json_response(self, 200, {"ok": True, "sessions": _session_summaries(80)})
            return

        _json_response(self, 404, {"ok": False, "error": "not_found"})

    def do_POST(self) -> None:
        path, qs = _parse_request_path(self.path)

        if path not in {"/api/chat", "/api/control/action", "/api/control/login", "/api/control/logout"}:
            _json_response(self, 404, {"ok": False, "error": "not_found"})
            return

        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length) if length > 0 else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            _json_response(self, 400, {"ok": False, "error": "invalid_json"})
            return

        if path == "/api/control/login":
            if not _control_login_enabled():
                _json_response(self, 400, {"ok": False, "error": "control_login_disabled"})
                return
            user_expected = (os.environ.get("NOVA_CONTROL_USER") or "").strip()
            pass_expected = (os.environ.get("NOVA_CONTROL_PASS") or "").strip()
            user = str(payload.get("username") or "").strip()
            pwd = str(payload.get("password") or "").strip()
            if user and pwd and secrets.compare_digest(user, user_expected) and secrets.compare_digest(pwd, pass_expected):
                sid = _new_control_session()
                body = json.dumps({"ok": True, "message": "login_ok"}, ensure_ascii=True).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("Set-Cookie", f"nova_control_session={sid}; Path=/; HttpOnly; SameSite=Strict")
                self.end_headers()
                self.wfile.write(body)
                _record_http_response(200)
                return
            _json_response(self, 403, {"ok": False, "error": "invalid_credentials"})
            return

        if path == "/api/control/logout":
            _clear_control_session(self)
            body = json.dumps({"ok": True, "message": "logout_ok"}, ensure_ascii=True).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Set-Cookie", "nova_control_session=; Path=/; Max-Age=0; HttpOnly; SameSite=Strict")
            self.end_headers()
            self.wfile.write(body)
            _record_http_response(200)
            return

        if path == "/api/control/action":
            ok, reason = _control_auth(self, qs)
            if not ok:
                _json_response(self, 403, {"ok": False, "error": reason})
                return

            success, msg, extra = _control_action(str(payload.get("action") or ""), payload)
            code = 200 if success else 400
            body = {"ok": bool(success), "message": msg}
            if extra:
                body.update(extra)
            _json_response(self, code, body)
            return

        message = str(payload.get("message") or "").strip()
        session_id = str(payload.get("session_id") or "").strip()
        if not session_id:
            session_id = secrets.token_hex(8)

        if not message:
            _json_response(self, 400, {"ok": False, "error": "message_required", "session_id": session_id})
            return

        try:
            reply = process_chat(session_id, message)
            _json_response(self, 200, {"ok": True, "session_id": session_id, "reply": reply})
        except Exception as e:
            _json_response(self, 500, {"ok": False, "session_id": session_id, "error": f"chat_failed: {e}"})

    def log_message(self, fmt: str, *args) -> None:
        return


INDEX_HTML = """<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Nova LAN Interface</title>
  <style>
    :root {
      --bg: #f7f4ec;
      --panel: #fffdf8;
      --ink: #1f1d19;
      --muted: #70695f;
      --accent: #0d6b5f;
      --accent-2: #d9972d;
      --line: #e4dbc8;
    }
    body { margin: 0; font-family: "Segoe UI", Tahoma, sans-serif; color: var(--ink); background: radial-gradient(circle at top left, #fff8e7, var(--bg)); }
    .wrap { max-width: 900px; margin: 24px auto; padding: 0 16px; }
    .card { background: var(--panel); border: 1px solid var(--line); border-radius: 14px; box-shadow: 0 8px 30px rgba(0,0,0,0.06); overflow: hidden; }
    .head { padding: 14px 16px; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--line); }
    .title { font-weight: 700; letter-spacing: 0.02em; }
    .status { font-size: 12px; color: var(--muted); }
    #chat { height: 58vh; overflow: auto; padding: 14px; display: grid; gap: 10px; }
    .msg { padding: 10px 12px; border-radius: 10px; max-width: 85%; white-space: pre-wrap; line-height: 1.35; }
    .u { margin-left: auto; background: #d7efe9; border: 1px solid #a9d9ce; }
    .a { margin-right: auto; background: #fff4db; border: 1px solid #f0d59f; }
    form { display: grid; grid-template-columns: 1fr auto; gap: 10px; padding: 12px; border-top: 1px solid var(--line); }
    input { font-size: 15px; padding: 10px 12px; border-radius: 9px; border: 1px solid #cabfae; outline: none; }
    button { background: linear-gradient(135deg, var(--accent), #0f8f7d); color: #fff; border: 0; border-radius: 9px; padding: 10px 14px; cursor: pointer; font-weight: 600; }
    .hint { padding: 0 14px 14px; color: var(--muted); font-size: 12px; }
  </style>
</head>
<body>
  <div class=\"wrap\">
    <div class=\"card\">
      <div class=\"head\">
        <div class=\"title\">Nova Network Interface</div>
        <div id=\"status\" class=\"status\">Checking health...</div>
      </div>
      <div id=\"chat\"></div>
      <form id=\"f\">
        <input id=\"m\" placeholder=\"Type a message for Nova...\" autocomplete=\"off\" />
        <button type=\"submit\">Send</button>
      </form>
            <div class=\"hint\">Tip: start server with <code>--host 0.0.0.0</code> to test from another device on your LAN. <a href=\"/control\">Open Control Room</a>.</div>
    </div>
  </div>
<script>
  const chat = document.getElementById('chat');
  const form = document.getElementById('f');
  const input = document.getElementById('m');
  const statusEl = document.getElementById('status');
    const qs = new URLSearchParams(window.location.search || '');
    const sidParam = (qs.get('sid') || '').trim();
    let sessionId = sidParam || localStorage.getItem('nova_session_id') || '';
    if (sidParam) {
        localStorage.setItem('nova_session_id', sessionId);
    }
    let historyLoaded = false;

  function add(kind, text) {
    const d = document.createElement('div');
    d.className = 'msg ' + kind;
    d.textContent = text;
    chat.appendChild(d);
    chat.scrollTop = chat.scrollHeight;
  }

    async function loadHistory() {
        if (!sessionId) return;
        try {
            const r = await fetch('/api/chat/history?session_id=' + encodeURIComponent(sessionId));
            const j = await r.json();
            if (!r.ok || !j.ok || !Array.isArray(j.turns)) return;
            if (j.turns.length === 0) return;

            j.turns.forEach(t => {
                if (!t || !t.role || !t.text) return;
                add(t.role === 'user' ? 'u' : 'a', String(t.text));
            });
            historyLoaded = true;
        } catch (_) {
            // Keep startup resilient; chat can still operate without history.
        }
    }

  async function health() {
    try {
      const r = await fetch('/api/health');
      const j = await r.json();
      statusEl.textContent = j.ollama_api_up ? `Healthy | model: ${j.chat_model}` : 'Ollama unavailable';
    } catch (_) {
      statusEl.textContent = 'Health check failed';
    }
  }

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const message = input.value.trim();
    if (!message) return;
    input.value = '';
    add('u', message);
    try {
      const r = await fetch('/api/chat', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({message, session_id: sessionId})
      });
      const j = await r.json();
      if (j.session_id) {
        sessionId = j.session_id;
        localStorage.setItem('nova_session_id', sessionId);
      }
      add('a', j.reply || (j.error ? `Error: ${j.error}` : 'No reply'));
    } catch (err) {
      add('a', 'Network error: ' + err.message);
    }
  });

    (async () => {
        await loadHistory();
        if (!historyLoaded) {
            add('a', 'Nova LAN interface ready. Ask me anything.');
        }
        health();
    })();
</script>
</body>
</html>
"""


CONTROL_LOGIN_HTML = """<!doctype html>
<html lang=\"en\">
<head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <title>Nova Control Login</title>
    <style>
        :root { --ink:#1f1d19; --bg:#f3efe6; --panel:#fffdf8; --line:#d9ceba; --accent:#0f7a5c; --danger:#a82720; }
        body {
            margin: 0;
            min-height: 100vh;
            display: grid;
            place-items: center;
            font-family: "Space Grotesk", "Segoe UI", sans-serif;
            color: var(--ink);
            background: radial-gradient(1000px 400px at 10% -20%, #d9ead7, transparent 60%), linear-gradient(160deg, #edf4ec, var(--bg));
        }
        .card {
            width: min(480px, 92vw);
            border: 1px solid var(--line);
            border-radius: 14px;
            background: var(--panel);
            box-shadow: 0 14px 30px rgba(0,0,0,0.08);
            padding: 16px;
        }
        h1 { margin: 0 0 8px; font-size: 20px; }
        p { margin: 0 0 12px; color: #5f5a52; }
        label { display: block; margin: 8px 0 4px; font-size: 13px; color: #5f5a52; }
        input {
            width: 100%;
            padding: 9px 10px;
            border-radius: 9px;
            border: 1px solid #bfb5a8;
            font-size: 14px;
            box-sizing: border-box;
        }
        button {
            margin-top: 12px;
            width: 100%;
            border: 0;
            border-radius: 10px;
            padding: 10px;
            color: #fff;
            cursor: pointer;
            font-weight: 700;
            background: linear-gradient(135deg, var(--accent), #0a986f);
        }
        .err { color: var(--danger); font-size: 13px; min-height: 18px; margin-top: 10px; }
    </style>
</head>
<body>
    <div class=\"card\">
        <h1>Nova Control Room Login</h1>
        <p>Sign in to access administrative controls.</p>
        <form id=\"f\">
            <label for=\"u\">Username</label>
            <input id=\"u\" autocomplete=\"username\" />
            <label for=\"p\">Password</label>
            <input id=\"p\" type=\"password\" autocomplete=\"current-password\" />
            <button type=\"submit\">Sign In</button>
            <div class=\"err\" id=\"err\"></div>
        </form>
    </div>
    <script>
        const f = document.getElementById('f');
        const err = document.getElementById('err');
        f.addEventListener('submit', async (e) => {
            e.preventDefault();
            err.textContent = '';
            try {
                const r = await fetch('/api/control/login', {
                    method: 'POST',
                    headers: {'Content-Type':'application/json'},
                    body: JSON.stringify({
                        username: document.getElementById('u').value.trim(),
                        password: document.getElementById('p').value
                    })
                });
                const j = await r.json();
                if (!r.ok || !j.ok) throw new Error(j.error || 'login_failed');
                window.location.href = '/control';
            } catch (e) {
                err.textContent = 'Login failed: ' + e.message;
            }
        });
    </script>
</body>
</html>
"""


CONTROL_HTML = """<!doctype html>
<html lang=\"en\">
<head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <title>Nova Control Room</title>
    <style>
        :root {
            --bg0: #e8efe8;
            --bg1: #f4efe5;
            --panel: #fffcf4;
            --ink: #1a1e1b;
            --muted: #59615b;
            --accent: #0a7a4a;
            --accent2: #c76c1d;
            --danger: #b3261e;
            --line: #d7d5cb;
            --good: #0b7a5f;
            --warn: #b87515;
        }
        * { box-sizing: border-box; }
        body {
            margin: 0;
            color: var(--ink);
            font-family: "Space Grotesk", "Segoe UI", Tahoma, sans-serif;
            background:
                radial-gradient(900px 400px at 8% -10%, #d8ead8, transparent 60%),
                radial-gradient(1100px 500px at 92% -20%, #ffe7cf, transparent 55%),
                linear-gradient(160deg, var(--bg0), var(--bg1));
            min-height: 100vh;
        }
        .wrap { max-width: 1200px; margin: 0 auto; padding: 20px 14px 30px; }
        .bar {
            display: flex; gap: 10px; align-items: center; justify-content: space-between;
            margin-bottom: 12px;
            background: rgba(255,255,255,0.65);
            border: 1px solid var(--line);
            padding: 10px 12px;
            border-radius: 14px;
            backdrop-filter: blur(6px);
        }
        .title { font-weight: 700; letter-spacing: 0.02em; font-size: 18px; }
        .grid {
            display: grid;
            grid-template-columns: 1.2fr 1fr;
            gap: 12px;
        }
        .card {
            border: 1px solid var(--line);
            border-radius: 14px;
            background: var(--panel);
            box-shadow: 0 8px 24px rgba(0,0,0,0.07);
            overflow: hidden;
        }
        .head { display: flex; align-items: center; justify-content: space-between; padding: 10px 12px; border-bottom: 1px solid var(--line); font-weight: 600; }
        .body { padding: 12px; }
        .mono { font-family: "IBM Plex Mono", Consolas, monospace; }
        .kv { display: grid; grid-template-columns: 170px 1fr; gap: 6px 10px; font-size: 14px; }
        .muted { color: var(--muted); }
        .good { color: var(--good); font-weight: 600; }
        .warn { color: var(--warn); font-weight: 600; }
        .danger { color: var(--danger); font-weight: 600; }
        .row { display: flex; gap: 8px; flex-wrap: wrap; }
        button {
            border: 0; border-radius: 10px; padding: 8px 11px; cursor: pointer;
            color: #fff; font-weight: 600;
            background: linear-gradient(135deg, var(--accent), #0f9f61);
        }
        button.alt { background: linear-gradient(135deg, #6f4f3e, #9d6a4f); }
        button.warn { background: linear-gradient(135deg, #9a5316, #cf7e24); }
        button.danger { background: linear-gradient(135deg, #8a1d15, #bf2c1f); }
        input, select {
            width: 100%; border-radius: 9px; border: 1px solid #bfc4b7; padding: 8px 9px;
            font-family: inherit; background: #fff;
        }
        pre {
            margin: 0;
            white-space: pre-wrap;
            word-break: break-word;
            max-height: 280px;
            overflow: auto;
            font-size: 12.5px;
            border-radius: 10px;
            border: 1px solid var(--line);
            background: #f8f7f1;
            padding: 10px;
        }
                .span2 { grid-column: span 2; }
                canvas {
                    width: 100%;
                    height: 220px;
                    border: 1px solid var(--line);
                    border-radius: 10px;
                    background: linear-gradient(180deg, #f9f8f2, #f1efe7);
                }
        .pulse { animation: pulse 1.2s ease-in-out 1; }
        @keyframes pulse {
            0% { box-shadow: 0 0 0 0 rgba(10,122,74,0.45); }
            100% { box-shadow: 0 0 0 14px rgba(10,122,74,0); }
        }
        @media (max-width: 900px) {
            .grid { grid-template-columns: 1fr; }
            .span2 { grid-column: auto; }
            .kv { grid-template-columns: 1fr; }
        }
    </style>
</head>
<body>
    <div class=\"wrap\">
        <div class=\"bar\">
            <div class=\"title\">Nova Control Room</div>
            <div class=\"row\">
                <a href=\"/\">Chat UI</a>
                <button id=\"btnRefresh\">Refresh</button>
                <button id=\"btnLogout\" class=\"danger\">Logout</button>
            </div>
        </div>

        <div class=\"grid\">
            <section class=\"card\">
                <div class=\"head\">Runtime Health</div>
                <div class=\"body\">
                    <div class="kv" id="statusKv"></div>
                </div>
            </section>

            <section class="card">
                <div class="head">Session Manager</div>
                <div class="body">
                    <div class="row" style="margin-bottom:8px;">
                        <select id="sessionSelect"></select>
                    </div>
                    <div class="row" style="margin-bottom:8px;">
                        <button id="btnSessionsRefresh" class="alt">Refresh Sessions</button>
                        <button id="btnSessionOpen">Open In Chat</button>
                        <button id="btnSessionCopy" class="warn">Copy Session ID</button>
                        <button id="btnSessionDelete" class="danger">Delete Session</button>
                    </div>
                    <pre id="sessionBox" class="mono">No session selected.</pre>
                </div>
            </section>

            <section class=\"card\">
                <div class=\"head\">Control Access</div>
                <div class=\"body\">
                    <label class=\"muted\" for=\"key\">Control key (optional if local-only mode):</label>
                    <input id=\"key\" type=\"password\" placeholder=\"NOVA_CONTROL_TOKEN\" />
                </div>
            </section>

            <section class=\"card\">
                <div class=\"head\">Guard Control</div>
                <div class=\"body\">
                    <div class=\"row\" style=\"margin-bottom:8px;\">
                        <button id=\"btnGuardStatus\" class=\"alt\">Guard Status</button>
                        <button id=\"btnGuardStart\">Start Guard</button>
                        <button id=\"btnGuardStop\" class=\"danger\">Stop Guard</button>
                    </div>
                    <pre id=\"guardBox\" class=\"mono\">No guard data yet.</pre>
                </div>
            </section>

            <section class=\"card\">
                <div class=\"head\">Policy Controls</div>
                <div class=\"body\">
                    <div class=\"row\" style=\"margin-bottom:8px;\">
                        <input id=\"domainInput\" placeholder=\"example.com\" />
                        <button id=\"btnAllow\">Allow Domain</button>
                        <button id=\"btnRemove\" class=\"alt\">Remove Domain</button>
                    </div>
                    <div class=\"row\">
                        <select id=\"webMode\">
                            <option value=\"normal\">web mode normal</option>
                            <option value=\"max\">web mode max</option>
                        </select>
                        <button id=\"btnMode\" class=\"warn\">Apply Web Mode</button>
                        <button id=\"btnAudit\" class=\"alt\">Policy Audit</button>
                    </div>
                </div>
            </section>

            <section class=\"card\">
                <div class=\"head\">Ops Actions</div>
                <div class=\"body\">
                    <div class=\"row\">
                        <button id=\"btnInspect\" class=\"warn\">Inspect Environment</button>
                        <button id=\"btnOut\" class=\"alt\">Tail HTTP OUT</button>
                        <button id=\"btnErr\" class=\"danger\">Tail HTTP ERR</button>
                    </div>
                </div>
            </section>

            <section class=\"card span2\">
                <div class=\"head\">Policy Snapshot</div>
                <div class=\"body\">
                    <pre id=\"policyBox\" class=\"mono\">Loading...</pre>
                </div>
            </section>

            <section class=\"card span2\">
                <div class=\"head\">Telemetry</div>
                <div class=\"body\">
                    <canvas id=\"metricsCanvas\" width=\"1100\" height=\"220\"></canvas>
                    <div class=\"muted\" style=\"margin-top:8px;font-size:12px;\">Green: heartbeat age | Blue: requests/min | Red: errors/min</div>
                </div>
            </section>

            <section class=\"card span2\">
                <div class=\"head\">Action Output</div>
                <div class=\"body\">
                    <pre id=\"actionBox\" class=\"mono\">No actions yet.</pre>
                </div>
            </section>
        </div>
    </div>

<script>
    const keyInput = document.getElementById('key');
    const statusKv = document.getElementById('statusKv');
    const policyBox = document.getElementById('policyBox');
    const actionBox = document.getElementById('actionBox');
    const guardBox = document.getElementById('guardBox');
    const sessionSelect = document.getElementById('sessionSelect');
    const sessionBox = document.getElementById('sessionBox');
    const metricsCanvas = document.getElementById('metricsCanvas');
    const ctx = metricsCanvas.getContext('2d');
    let sessionsCache = [];

    keyInput.value = localStorage.getItem('nova_control_key') || '';
    keyInput.addEventListener('change', () => {
        localStorage.setItem('nova_control_key', keyInput.value.trim());
    });

    function controlHeaders() {
        const k = keyInput.value.trim();
        const headers = {'Content-Type': 'application/json'};
        if (k) headers['X-Nova-Control-Key'] = k;
        return headers;
    }

    function fmtStatusValue(k, v) {
        if (k === 'ollama_api_up' || k === 'web_enabled' || k === 'memory_enabled' || k === 'searxng_ok') {
            if (v === true) return `<span class=\"good\">true</span>`;
            if (v === false) return `<span class=\"danger\">false</span>`;
        }
        if (k === 'heartbeat_age_sec' && typeof v === 'number') {
            const cls = v <= 15 ? 'good' : (v <= 45 ? 'warn' : 'danger');
            return `<span class=\"${cls}\">${v}s</span>`;
        }
        return `<span class=\"mono\">${String(v)}</span>`;
    }

    function setAction(text) {
        actionBox.textContent = text;
        actionBox.classList.remove('pulse');
        void actionBox.offsetWidth;
        actionBox.classList.add('pulse');
    }

    function drawMetrics(points) {
        if (!ctx) return;
        const w = metricsCanvas.width;
        const h = metricsCanvas.height;
        ctx.clearRect(0, 0, w, h);
        ctx.fillStyle = '#f5f3eb';
        ctx.fillRect(0, 0, w, h);

        if (!points || points.length < 2) {
            ctx.fillStyle = '#6a665f';
            ctx.font = '14px Segoe UI';
            ctx.fillText('Telemetry will appear after a few refresh cycles.', 12, 28);
            return;
        }

        const pad = 28;
        const iw = w - pad * 2;
        const ih = h - pad * 2;
        const recent = points.slice(-60);

        const hb = recent.map(p => Number(p.heartbeat_age_sec || 0));
        const reqPerMin = [];
        const errPerMin = [];
        for (let i = 0; i < recent.length; i++) {
            if (i === 0) { reqPerMin.push(0); errPerMin.push(0); continue; }
            const dt = Math.max(1, Number(recent[i].ts || 0) - Number(recent[i - 1].ts || 0));
            const dr = Math.max(0, Number(recent[i].requests_total || 0) - Number(recent[i - 1].requests_total || 0));
            const de = Math.max(0, Number(recent[i].errors_total || 0) - Number(recent[i - 1].errors_total || 0));
            reqPerMin.push((dr * 60) / dt);
            errPerMin.push((de * 60) / dt);
        }

        const ymax = Math.max(5, ...hb, ...reqPerMin, ...errPerMin);
        const x = (i) => pad + (i / (recent.length - 1)) * iw;
        const y = (v) => pad + ih - (Math.max(0, v) / ymax) * ih;

        ctx.strokeStyle = '#d8d5cc';
        ctx.lineWidth = 1;
        for (let i = 0; i <= 4; i++) {
            const gy = pad + (ih / 4) * i;
            ctx.beginPath();
            ctx.moveTo(pad, gy);
            ctx.lineTo(w - pad, gy);
            ctx.stroke();
        }

        function plot(arr, color) {
            ctx.strokeStyle = color;
            ctx.lineWidth = 2;
            ctx.beginPath();
            arr.forEach((v, i) => {
                const px = x(i);
                const py = y(v);
                if (i === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
            });
            ctx.stroke();
        }

        plot(hb, '#0f8f5c');
        plot(reqPerMin, '#2563eb');
        plot(errPerMin, '#c62828');

        ctx.fillStyle = '#46413a';
        ctx.font = '12px IBM Plex Mono, Consolas, monospace';
        ctx.fillText('0', 6, h - pad + 4);
        ctx.fillText(String(Math.round(ymax)), 6, pad + 4);
    }

    async function getJson(url) {
        const r = await fetch(url, {headers: controlHeaders()});
        const j = await r.json();
        if (!r.ok || !j.ok) throw new Error(j.error || j.message || ('HTTP ' + r.status));
        return j;
    }

    async function postAction(action, body={}) {
        const r = await fetch('/api/control/action', {
            method: 'POST',
            headers: controlHeaders(),
            body: JSON.stringify({action, ...body})
        });
        const j = await r.json();
        if (!r.ok || !j.ok) throw new Error(j.error || j.message || ('HTTP ' + r.status));
        return j;
    }

    async function refresh() {
        try {
            const [status, policy, metrics, sess] = await Promise.all([
                getJson('/api/control/status'),
                getJson('/api/control/policy'),
                getJson('/api/control/metrics'),
                getJson('/api/control/sessions')
            ]);

            const keys = [
                'server_time', 'ollama_api_up', 'chat_model', 'memory_enabled', 'web_enabled',
                'search_provider', 'search_api_endpoint', 'allow_domains_count',
                'heartbeat_age_sec', 'active_http_sessions', 'requests_total', 'errors_total', 'searxng_ok', 'searxng_note'
            ];
            statusKv.innerHTML = keys.map(k => `<div class=\"muted\">${k}</div><div>${fmtStatusValue(k, status[k])}</div>`).join('');
            policyBox.textContent = JSON.stringify(policy, null, 2);
            drawMetrics(metrics.points || []);
            guardBox.textContent = JSON.stringify(status.guard || {}, null, 2);
            sessionsCache = Array.isArray(sess.sessions) ? sess.sessions : [];
            renderSessions();
        } catch (err) {
            setAction('Refresh failed: ' + err.message);
        }
    }

    function renderSessions() {
        const prev = (sessionSelect.value || '').trim();
        sessionSelect.innerHTML = '';
        if (!sessionsCache.length) {
            const o = document.createElement('option');
            o.value = '';
            o.textContent = '(no sessions)';
            sessionSelect.appendChild(o);
            sessionBox.textContent = 'No persisted chat sessions found.';
            return;
        }
        sessionsCache.forEach(s => {
            const o = document.createElement('option');
            o.value = s.session_id;
            o.textContent = `${s.session_id} (${s.turn_count} turns)`;
            sessionSelect.appendChild(o);
        });
        if (prev && sessionsCache.some(s => s.session_id === prev)) {
            sessionSelect.value = prev;
        }
        renderSessionPreview();
    }

    function renderSessionPreview() {
        const sid = (sessionSelect.value || '').trim();
        const s = sessionsCache.find(x => x.session_id === sid);
        if (!s) {
            sessionBox.textContent = 'No session selected.';
            return;
        }
        const lines = [
            `Session: ${s.session_id}`,
            `Turns: ${s.turn_count}`,
            '',
            'Last user:',
            s.last_user || '(none)',
            '',
            'Last assistant:',
            s.last_assistant || '(none)',
        ];
        sessionBox.textContent = lines.join('\n');
    }

    document.getElementById('btnRefresh').addEventListener('click', refresh);
    sessionSelect.addEventListener('change', renderSessionPreview);

    document.getElementById('btnLogout').addEventListener('click', async () => {
        try {
            await fetch('/api/control/logout', {method: 'POST', headers: controlHeaders(), body: '{}'});
            window.location.href = '/control';
        } catch (err) {
            setAction('Logout failed: ' + err.message);
        }
    });

    document.getElementById('btnSessionsRefresh').addEventListener('click', async () => {
        try {
            const sess = await getJson('/api/control/sessions');
            sessionsCache = Array.isArray(sess.sessions) ? sess.sessions : [];
            renderSessions();
            setAction('Session list refreshed.');
        } catch (err) {
            setAction('Session refresh failed: ' + err.message);
        }
    });

    document.getElementById('btnSessionOpen').addEventListener('click', () => {
        const sid = (sessionSelect.value || '').trim();
        if (!sid) {
            setAction('Select a session first.');
            return;
        }
        window.open('/?sid=' + encodeURIComponent(sid), '_blank');
    });

    document.getElementById('btnSessionCopy').addEventListener('click', async () => {
        const sid = (sessionSelect.value || '').trim();
        if (!sid) {
            setAction('Select a session first.');
            return;
        }
        try {
            await navigator.clipboard.writeText(sid);
            setAction('Session ID copied: ' + sid);
        } catch (_) {
            setAction('Unable to copy to clipboard. Session ID: ' + sid);
        }
    });

    document.getElementById('btnSessionDelete').addEventListener('click', async () => {
        const sid = (sessionSelect.value || '').trim();
        if (!sid) {
            setAction('Select a session first.');
            return;
        }
        try {
            const j = await postAction('session_delete', {session_id: sid});
            sessionsCache = Array.isArray(j.sessions) ? j.sessions : sessionsCache.filter(x => x.session_id !== sid);
            renderSessions();
            setAction(j.message || 'Session deleted.');
        } catch (err) {
            setAction('Delete session failed: ' + err.message);
        }
    });

    document.getElementById('btnGuardStatus').addEventListener('click', async () => {
        try {
            const j = await postAction('guard_status');
            guardBox.textContent = JSON.stringify(j.guard || {}, null, 2);
            setAction(j.message || 'guard_status done');
            await refresh();
        } catch (err) {
            setAction('Guard status failed: ' + err.message);
        }
    });

    document.getElementById('btnGuardStart').addEventListener('click', async () => {
        try {
            const j = await postAction('guard_start');
            guardBox.textContent = JSON.stringify(j.guard || {}, null, 2);
            setAction(j.message || 'guard_start done');
            await refresh();
        } catch (err) {
            setAction('Guard start failed: ' + err.message);
        }
    });

    document.getElementById('btnGuardStop').addEventListener('click', async () => {
        try {
            const j = await postAction('guard_stop');
            guardBox.textContent = JSON.stringify(j.guard || {}, null, 2);
            setAction(j.message || 'guard_stop done');
            await refresh();
        } catch (err) {
            setAction('Guard stop failed: ' + err.message);
        }
    });

    document.getElementById('btnAllow').addEventListener('click', async () => {
        try {
            const domain = (document.getElementById('domainInput').value || '').trim();
            const j = await postAction('policy_allow', {domain});
            setAction(j.message || 'policy_allow done');
            await refresh();
        } catch (err) {
            setAction('Allow failed: ' + err.message);
        }
    });

    document.getElementById('btnRemove').addEventListener('click', async () => {
        try {
            const domain = (document.getElementById('domainInput').value || '').trim();
            const j = await postAction('policy_remove', {domain});
            setAction(j.message || 'policy_remove done');
            await refresh();
        } catch (err) {
            setAction('Remove failed: ' + err.message);
        }
    });

    document.getElementById('btnMode').addEventListener('click', async () => {
        try {
            const mode = document.getElementById('webMode').value;
            const j = await postAction('web_mode', {mode});
            setAction(j.message || 'web_mode done');
            await refresh();
        } catch (err) {
            setAction('Web mode failed: ' + err.message);
        }
    });

    document.getElementById('btnAudit').addEventListener('click', async () => {
        try {
            const j = await postAction('policy_audit');
            setAction(j.text || j.message || 'policy_audit done');
        } catch (err) {
            setAction('Policy audit failed: ' + err.message);
        }
    });

    document.getElementById('btnInspect').addEventListener('click', async () => {
        try {
            const j = await postAction('inspect');
            setAction(j.report || j.message || 'inspect done');
        } catch (err) {
            setAction('Inspect failed: ' + err.message);
        }
    });

    document.getElementById('btnOut').addEventListener('click', async () => {
        try {
            const j = await postAction('tail_log', {name: 'nova_http.out.log'});
            setAction(j.text || 'No output');
        } catch (err) {
            setAction('Tail OUT failed: ' + err.message);
        }
    });

    document.getElementById('btnErr').addEventListener('click', async () => {
        try {
            const j = await postAction('tail_log', {name: 'nova_http.err.log'});
            setAction(j.text || 'No output');
        } catch (err) {
            setAction('Tail ERR failed: ' + err.message);
        }
    });

    refresh();
    setInterval(refresh, 15000);
</script>
</body>
</html>
"""


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Nova LAN HTTP interface")
    ap.add_argument("--host", default="127.0.0.1", help="Bind host (use 0.0.0.0 for LAN)")
    ap.add_argument("--port", type=int, default=8080, help="Bind port")
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    _load_persisted_sessions()
    try:
        nova_core.ensure_ollama_boot()
    except Exception:
        pass

    srv = ThreadingHTTPServer((args.host, args.port), NovaHttpHandler)
    print(f"Nova HTTP interface ready at http://{args.host}:{args.port}", flush=True)
    print(f"Control Room: http://{args.host}:{args.port}/control", flush=True)
    if args.host == "0.0.0.0":
        print("LAN mode enabled. Open from another device via http://<this-pc-ip>:" + str(args.port), flush=True)
    if (os.environ.get("NOVA_CONTROL_TOKEN") or "").strip():
        print("Control Room auth: NOVA_CONTROL_TOKEN is enabled (required for admin API access).", flush=True)
    else:
        print("Control Room auth: local-only mode (set NOVA_CONTROL_TOKEN for LAN-secure access).", flush=True)
    if _control_login_enabled():
        print("Control Room login: enabled (set via NOVA_CONTROL_USER / NOVA_CONTROL_PASS).", flush=True)
    else:
        print("Control Room login: disabled (optional).", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
