from __future__ import annotations

import argparse
import hashlib
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
import psutil
import requests
import capabilities as capabilities_mod
from conversation_manager import ConversationManager


SESSION_TURNS: Dict[str, List[Tuple[str, str]]] = {}
SESSION_OWNERS: Dict[str, str] = {}
SESSION_STATE_MANAGER = ConversationManager()
MAX_TURNS = 40
BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
CONTROL_TEMPLATE_PATH = TEMPLATES_DIR / "control.html"
CONTROL_CSS_PATH = STATIC_DIR / "control.css"
CONTROL_JS_PATH = STATIC_DIR / "control.js"
SCRIPTS_DIR = BASE_DIR / "scripts"
LOG_DIR = BASE_DIR / "logs"
RUNTIME_DIR = BASE_DIR / "runtime"
SESSION_STORE_PATH = RUNTIME_DIR / "http_chat_sessions.json"
MAX_STORED_SESSIONS = 120
MAX_STORED_TURNS_PER_SESSION = MAX_TURNS * 2
PEIMS_KNOWLEDGE_DIR = BASE_DIR / "knowledge" / "peims"
KNOWLEDGE_DIR = BASE_DIR / "knowledge"
VENV_PY = BASE_DIR / ".venv" / "Scripts" / "python.exe"
GUARD_PY = BASE_DIR / "nova_guard.py"
STOP_GUARD_PY = BASE_DIR / "stop_guard.py"
CORE_PY = BASE_DIR / "nova_core.py"
TEST_SESSION_RUNNER_PY = SCRIPTS_DIR / "run_test_session.py"
EXPORT_DIR = RUNTIME_DIR / "exports"
CONTROL_AUDIT_LOG = RUNTIME_DIR / "control_action_audit.jsonl"
TOOL_EVENTS_LOG = RUNTIME_DIR / "tool_events.jsonl"
MEMORY_EVENTS_LOG = RUNTIME_DIR / "memory_events.jsonl"

CONTROL_SESSIONS: Dict[str, float] = {}
CONTROL_SESSION_TTL_SECONDS = 8 * 60 * 60
CHAT_SESSIONS: Dict[str, tuple[str, float]] = {}
CHAT_SESSION_TTL_SECONDS = 8 * 60 * 60
CHAT_PASSWORD_HASH_ITERATIONS = 120000

_METRICS_LOCK = threading.Lock()
_HTTP_REQUESTS_TOTAL = 0
_HTTP_ERRORS_TOTAL = 0
_METRICS_SERIES: List[dict] = []
_METRICS_MAX_POINTS = 240
_SESSION_LOCK = threading.Lock()


def _record_control_action_event(action: str, result: str, detail: str = "", payload: dict | None = None) -> None:
    entry = {
        "ts": int(time.time()),
        "action": str(action or "").strip(),
        "result": str(result or "").strip(),
        "detail": str(detail or "")[:500],
    }
    if isinstance(payload, dict):
        # Keep a minimal, safe snapshot for smoke telemetry.
        entry["payload_keys"] = sorted([str(k) for k in payload.keys()])[:20]
    try:
        RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        with open(CONTROL_AUDIT_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=True) + "\n")
    except Exception:
        pass


def _safe_tail_lines(path: Path, n: int = 80) -> list[str]:
    text = _tail_file(path, max_lines=max(1, int(n)))
    return text.splitlines() if text else []


def _read_asset_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception as e:
        return f"<!doctype html><html><body><pre>Missing asset: {path.name}: {e}</pre></body></html>"


def _action_ledger_summary(limit: int = 60) -> dict:
    out = {
        "ok": True,
        "count": 0,
        "decision_counts": {},
        "tool_counts": {},
        "grounded_true": 0,
        "grounded_false": 0,
        "route_counts": {},
        "last_record": {},
    }
    try:
        files = sorted(nova_core.ACTION_LEDGER_DIR.glob("*.json"))
        if not files:
            return out
        recent = files[-max(1, int(limit)):]
        out["count"] = len(recent)
        for p in recent:
            try:
                r = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            d = str(r.get("planner_decision") or "unknown").strip() or "unknown"
            t = str(r.get("tool") or "none").strip() or "none"
            route_summary = nova_core.action_ledger_route_summary(r)
            out["decision_counts"][d] = int(out["decision_counts"].get(d, 0)) + 1
            out["tool_counts"][t] = int(out["tool_counts"].get(t, 0)) + 1
            if route_summary:
                out["route_counts"][route_summary] = int(out["route_counts"].get(route_summary, 0)) + 1
            if bool(r.get("grounded")):
                out["grounded_true"] += 1
            else:
                out["grounded_false"] += 1
            out["last_record"] = {
                "intent": r.get("intent"),
                "planner_decision": r.get("planner_decision"),
                "tool": r.get("tool"),
                "grounded": bool(r.get("grounded")),
                "route_summary": route_summary,
                "route_trace": list(r.get("route_trace") or [])[:20] if isinstance(r.get("route_trace"), list) else [],
                "final_answer": str(r.get("final_answer") or "")[:220],
            }
        return out
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _tool_events_summary(limit: int = 80) -> dict:
    out = {
        "ok": True,
        "count": 0,
        "status_counts": {},
        "tool_counts": {},
        "success_count": 0,
        "failure_count": 0,
        "denied_count": 0,
        "avg_latency_ms": 0,
        "avg_latency_ms_by_tool": {},
        "last_error_summary": "",
        "last_event": {},
    }
    try:
        if not TOOL_EVENTS_LOG.exists():
            return out
        lines = TOOL_EVENTS_LOG.read_text(encoding="utf-8", errors="ignore").splitlines()
        recent = lines[-max(1, int(limit)):]
        out["count"] = len(recent)
        latency_total = 0
        latency_count = 0
        latency_by_tool: dict[str, list[int]] = {}
        for line in recent:
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except Exception:
                continue
            status = str(entry.get("status") or "unknown").strip() or "unknown"
            tool = str(entry.get("tool") or "unknown").strip() or "unknown"
            out["status_counts"][status] = int(out["status_counts"].get(status, 0)) + 1
            out["tool_counts"][tool] = int(out["tool_counts"].get(tool, 0)) + 1
            if status == "ok":
                out["success_count"] += 1
            elif status == "error":
                out["failure_count"] += 1
                if not out["last_error_summary"]:
                    out["last_error_summary"] = f"{tool}: {str(entry.get('error') or '')}".strip().strip(": ")
            elif status == "denied":
                out["denied_count"] += 1
                if not out["last_error_summary"]:
                    out["last_error_summary"] = f"{tool}: {str(entry.get('reason') or '')}".strip().strip(": ")
            duration_ms = entry.get("duration_ms")
            if isinstance(duration_ms, (int, float)) and duration_ms >= 0:
                latency_total += int(duration_ms)
                latency_count += 1
                latency_by_tool.setdefault(tool, []).append(int(duration_ms))
            out["last_event"] = {
                "tool": tool,
                "status": status,
                "user": str(entry.get("user") or ""),
                "ts": int(entry.get("ts") or 0),
            }
        out["avg_latency_ms"] = int(round(latency_total / latency_count)) if latency_count else 0
        out["avg_latency_ms_by_tool"] = {
            tool: int(round(sum(values) / len(values)))
            for tool, values in sorted(latency_by_tool.items()) if values
        }
        return out
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _memory_events_summary(limit: int = 80) -> dict:
    out = {
        "ok": True,
        "count": 0,
        "status_counts": {},
        "action_counts": {},
        "write_count": 0,
        "recall_count": 0,
        "audit_count": 0,
        "stats_count": 0,
        "skipped_count": 0,
        "avg_latency_ms": 0,
        "last_error_summary": "",
        "last_event": {},
    }
    try:
        if not MEMORY_EVENTS_LOG.exists():
            return out
        lines = MEMORY_EVENTS_LOG.read_text(encoding="utf-8", errors="ignore").splitlines()
        recent = lines[-max(1, int(limit)):]
        out["count"] = len(recent)
        latency_total = 0
        latency_count = 0
        for line in recent:
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except Exception:
                continue
            status = str(entry.get("status") or "unknown").strip() or "unknown"
            action = str(entry.get("action") or "unknown").strip() or "unknown"
            out["status_counts"][status] = int(out["status_counts"].get(status, 0)) + 1
            out["action_counts"][action] = int(out["action_counts"].get(action, 0)) + 1
            if action == "add" and status == "ok":
                out["write_count"] += 1
            elif action == "recall":
                out["recall_count"] += 1
            elif action == "audit":
                out["audit_count"] += 1
            elif action == "stats":
                out["stats_count"] += 1
            if status == "skipped":
                out["skipped_count"] += 1
            if status == "error" and not out["last_error_summary"]:
                out["last_error_summary"] = f"{action}: {str(entry.get('error') or '')}".strip().strip(": ")
            duration_ms = entry.get("duration_ms")
            if isinstance(duration_ms, (int, float)) and duration_ms >= 0:
                latency_total += int(duration_ms)
                latency_count += 1
            out["last_event"] = {
                "action": action,
                "status": status,
                "user": str(entry.get("user") or ""),
                "ts": int(entry.get("ts") or 0),
            }
        out["avg_latency_ms"] = int(round(latency_total / latency_count)) if latency_count else 0
        return out
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _build_self_check(status: dict, policy: dict, metrics: dict) -> dict:
    checks: list[dict] = []
    alerts: list[str] = []

    def add_check(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": str(detail or "")})

    # Core service checks
    add_check("status_payload", bool(status.get("ok")), "status endpoint payload built")
    add_check("ollama_api", bool(status.get("ollama_api_up")), "ollama api reachability")
    add_check("policy_payload", bool(policy.get("ok")), "policy payload built")
    add_check("metrics_payload", bool(metrics.get("ok")), "metrics payload built")
    add_check("session_manager", True, "session summaries available")
    add_check("guard_status", isinstance(status.get("guard"), dict), "guard payload available")
    add_check("tool_event_summary", bool(status.get("tool_events_ok", True)), "tool event summary available")

    # Capability registry check
    try:
        caps = capabilities_mod.list_capabilities()
        cap_ok = isinstance(caps, dict)
        add_check("capability_registry", cap_ok, f"count={len(caps) if cap_ok else 0}")
    except Exception as e:
        add_check("capability_registry", False, str(e))

    # Threshold alerts
    hb_age = status.get("heartbeat_age_sec")
    if isinstance(hb_age, int):
        hb_ok = hb_age <= 45
        add_check("heartbeat_freshness", hb_ok, f"age={hb_age}s")
        if not hb_ok:
            alerts.append(f"heartbeat_age_high:{hb_age}s")

    web_cfg = policy.get("web") if isinstance(policy.get("web"), dict) else {}
    web_enabled = bool((policy.get("tools_enabled") or {}).get("web")) and bool(web_cfg.get("enabled"))
    allow_domains = list(web_cfg.get("allow_domains") or [])
    domains_ok = (not web_enabled) or bool(allow_domains)
    add_check("allow_domains_present_when_web_enabled", domains_ok, f"web_enabled={web_enabled}; domains={len(allow_domains)}")
    if not domains_ok:
        alerts.append("web_enabled_without_allow_domains")

    # Error spike check from metrics points.
    points = list(metrics.get("points") or [])
    err_spike = False
    err_detail = "insufficient_points"
    if len(points) >= 2:
        p2 = points[-1]
        p1 = points[-2]
        dt = max(1, int(p2.get("ts", 0)) - int(p1.get("ts", 0)))
        dr = max(0, int(p2.get("requests_total", 0)) - int(p1.get("requests_total", 0)))
        de = max(0, int(p2.get("errors_total", 0)) - int(p1.get("errors_total", 0)))
        err_per_min = (de * 60.0) / dt
        req_per_min = (dr * 60.0) / dt
        err_ratio = (de / dr) if dr > 0 else (1.0 if de > 0 else 0.0)
        err_spike = err_per_min > 2.0 and err_ratio > 0.2
        err_detail = f"err/min={err_per_min:.2f}, req/min={req_per_min:.2f}, err_ratio={err_ratio:.2f}"
    add_check("error_rate_spike", not err_spike, err_detail)
    if err_spike:
        alerts.append(f"error_spike:{err_detail}")

    total = len(checks)
    ok_count = sum(1 for c in checks if c.get("ok"))
    ratio = (ok_count / total) if total else 0.0
    score = int(round(ratio * 100))
    return {
        "ok": ok_count == total,
        "checks": checks,
        "alerts": alerts,
        "summary": f"self_check: {ok_count}/{total} checks passed",
        "pass_ratio": ratio,
        "health_score": score,
    }


def _export_capabilities_snapshot() -> tuple[bool, str, dict]:
    try:
        caps = capabilities_mod.list_capabilities()
        if not isinstance(caps, dict):
            caps = {}
        EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        out = EXPORT_DIR / f"capabilities_{stamp}.json"
        out.write_text(json.dumps(caps, ensure_ascii=True, indent=2), encoding="utf-8")
        return True, "capabilities_export_ok", {
            "path": str(out),
            "filename": out.name,
            "capabilities": caps,
            "count": len(caps),
        }
    except Exception as e:
        return False, f"capabilities_export_failed:{e}", {}


def _control_self_check_payload() -> dict:
    return _build_self_check(_control_status_payload(), _control_policy_payload(), _metrics_payload())


def _load_persisted_sessions() -> None:
    try:
        if not SESSION_STORE_PATH.exists():
            return
        data = json.loads(SESSION_STORE_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return
        loaded: Dict[str, List[Tuple[str, str]]] = {}
        for sid, turns in data.items():
            if not isinstance(sid, str):
                continue
            owner = ""
            if isinstance(turns, dict):
                owner = str(turns.get("owner") or "").strip()
                turn_list = turns.get("turns")
            if not isinstance(turn_list, list):
                continue
            cleaned: List[Tuple[str, str]] = []
            for it in turn_list[-MAX_STORED_TURNS_PER_SESSION:]:
                if not isinstance(it, dict):
                    continue
                role = str(it.get("role") or "").strip().lower()
                text = str(it.get("text") or "").strip()
                if role not in {"user", "assistant"} or not text:
                    continue
                cleaned.append((role, text))
            if cleaned:
                loaded[sid] = cleaned
                if owner:
                    SESSION_OWNERS[sid] = owner
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
            payload[sid] = {
                "owner": str(SESSION_OWNERS.get(sid) or ""),
                "turns": safe_turns,
            }

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


def _get_last_session_turn(session_id: str) -> tuple[str, str] | None:
    with _SESSION_LOCK:
        turns = SESSION_TURNS.get(session_id, [])
        if not turns:
            return None
        return turns[-1]


def _session_summaries(limit: int = 60) -> List[dict]:
    with _SESSION_LOCK:
        items = list(SESSION_TURNS.items())[-max(1, int(limit)):]

    out = []
    for sid, turns in reversed(items):
        if not sid:
            continue
        session = SESSION_STATE_MANAGER.peek(sid)
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
                "owner": str(SESSION_OWNERS.get(sid) or ""),
                "turn_count": len(turns),
                "last_user": last_user,
                "last_assistant": last_assistant,
                "state": {
                    "active_subject": session.active_subject() if session is not None else "",
                    "state_kind": session.state_kind() if session is not None else "",
                    "pending_action": dict(session.pending_action) if session is not None and isinstance(session.pending_action, dict) else None,
                    "pending_correction_target": str(session.pending_correction_target or "") if session is not None else "",
                    "continuation_used": bool(session.continuation_used_last_turn) if session is not None else False,
                },
                "reflection": session.reflection_summary() if session is not None else {
                    "active_subject": "",
                    "continuation_used": False,
                    "overrides_active": [],
                },
            }
        )
    return out


def _test_sessions_root() -> Path:
    return RUNTIME_DIR / "test_sessions"


def _test_session_definitions_dir() -> Path:
    return BASE_DIR / "tests" / "sessions"


def _available_test_session_definitions(limit: int = 80) -> List[dict]:
    root = _test_session_definitions_dir()
    if not root.exists():
        return []
    try:
        files = sorted(root.glob("*.json"))[: max(1, int(limit))]
    except Exception:
        return []
    out: list[dict] = []
    for path in files:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            payload = {}
        messages = payload.get("messages") if isinstance(payload, dict) and isinstance(payload.get("messages"), list) else []
        out.append(
            {
                "file": path.name,
                "name": str(payload.get("name") or path.stem) if isinstance(payload, dict) else path.stem,
                "message_count": len(messages),
            }
        )
    return out


def _report_status_label(diff_count: int, flagged_probe_count: int) -> str:
    if diff_count > 0:
        return "drift"
    if flagged_probe_count > 0:
        return "warning"
    return "green"


def _test_session_report_summaries(limit: int = 24) -> List[dict]:
    root = _test_sessions_root()
    if not root.exists():
        return []

    try:
        run_dirs = [path for path in root.iterdir() if path.is_dir()]
    except Exception:
        return []

    def _sort_key(path: Path) -> float:
        try:
            return path.stat().st_mtime
        except Exception:
            return 0.0

    out: list[dict] = []
    for run_dir in sorted(run_dirs, key=_sort_key, reverse=True)[: max(1, int(limit))]:
        report_path = run_dir / "result.json"
        if not report_path.exists():
            continue
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(report, dict):
            continue

        session_meta = report.get("session") if isinstance(report.get("session"), dict) else {}
        comparison = report.get("comparison") if isinstance(report.get("comparison"), dict) else {}
        cli = report.get("cli") if isinstance(report.get("cli"), dict) else {}
        http = report.get("http") if isinstance(report.get("http"), dict) else {}

        messages = session_meta.get("messages") if isinstance(session_meta.get("messages"), list) else []
        diffs = comparison.get("diffs") if isinstance(comparison.get("diffs"), list) else []
        cli_flagged = comparison.get("cli_flagged_probes") if isinstance(comparison.get("cli_flagged_probes"), list) else []
        http_flagged = comparison.get("http_flagged_probes") if isinstance(comparison.get("http_flagged_probes"), list) else []
        flagged_probe_count = len(cli_flagged) + len(http_flagged)
        diff_count = len(diffs)

        out.append(
            {
                "run_id": run_dir.name,
                "session_name": str(session_meta.get("name") or run_dir.name),
                "session_path": str(session_meta.get("path") or ""),
                "generated_at": str(report.get("generated_at") or ""),
                "message_count": len(messages),
                "report_path": str(report_path),
                "status": _report_status_label(diff_count, flagged_probe_count),
                "comparison": {
                    "turn_count_match": bool(comparison.get("turn_count_match", False)),
                    "cli_turns": int(comparison.get("cli_turns", 0) or 0),
                    "http_turns": int(comparison.get("http_turns", 0) or 0),
                    "diff_count": diff_count,
                    "diffs": diffs,
                    "cli_flagged_probes": cli_flagged,
                    "http_flagged_probes": http_flagged,
                    "flagged_probe_count": flagged_probe_count,
                },
                "artifacts": {
                    "run_dir": str(run_dir),
                    "cli_mode_dir": str((cli.get("artifacts") or {}).get("mode_dir") or "") if isinstance(cli.get("artifacts"), dict) else "",
                    "http_mode_dir": str((http.get("artifacts") or {}).get("mode_dir") or "") if isinstance(http.get("artifacts"), dict) else "",
                },
            }
        )
    return out


def _run_test_session_definition(session_file: str) -> tuple[bool, str, dict]:
    session_name = str(session_file or "").strip()
    if not session_name:
        return False, "test_session_file_required", {}
    runner_path = TEST_SESSION_RUNNER_PY
    if not runner_path.exists():
        return False, f"test_session_runner_missing:{runner_path}", {}
    if not VENV_PY.exists():
        return False, f"venv_python_missing:{VENV_PY}", {}

    known = {item.get("file") for item in _available_test_session_definitions(200)}
    if session_name not in known:
        return False, f"test_session_not_found:{session_name}", {"available": _available_test_session_definitions(80)}

    try:
        proc = subprocess.run(
            [str(VENV_PY), str(runner_path), session_name],
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            timeout=180,
        )
    except Exception as e:
        return False, f"test_session_run_failed:{e}", {}

    output = ((proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")).strip()
    reports = _test_session_report_summaries(24)
    latest = reports[0] if reports else {}
    ok = proc.returncode == 0
    message = f"test_session_run_completed:{session_name}" if ok else f"test_session_run_failed:{session_name}:exit:{proc.returncode}"
    return ok, message, {
        "stdout": output,
        "latest_report": latest,
        "reports": reports,
        "definitions": _available_test_session_definitions(80),
    }


def _delete_session(session_id: str) -> tuple[bool, str]:
    sid = (session_id or "").strip()
    if not sid:
        return False, "session_id_required"
    with _SESSION_LOCK:
        existed = sid in SESSION_TURNS
        session = SESSION_STATE_MANAGER.peek(sid)
        if session is not None:
            nova_core.record_health_snapshot(session_id=sid, reflection=session.last_reflection, session_end=True)
        SESSION_TURNS.pop(sid, None)
        SESSION_OWNERS.pop(sid, None)
        SESSION_STATE_MANAGER.drop(sid)
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


def _normalize_user_id(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "", raw)
    return cleaned[:64]


def _request_user_id(handler: BaseHTTPRequestHandler, qs: dict, payload: dict | None = None) -> str:
    header_uid = _normalize_user_id(handler.headers.get("X-Nova-User-Id") or "")
    qs_uid = _normalize_user_id(str((qs.get("user_id") or [""])[0]))
    body_uid = ""
    if isinstance(payload, dict):
        body_uid = _normalize_user_id(str(payload.get("user_id") or ""))
    return body_uid or qs_uid or header_uid


def _assert_session_owner(session_id: str, user_id: str, *, allow_bind: bool = True) -> tuple[bool, str]:
    sid = (session_id or "").strip()
    uid = _normalize_user_id(user_id)
    if not sid:
        return False, "session_id_required"
    if not uid:
        return False, "user_id_required"
    with _SESSION_LOCK:
        owner = _normalize_user_id(SESSION_OWNERS.get(sid) or "")
        if not owner:
            if allow_bind:
                SESSION_OWNERS[sid] = uid
                _persist_sessions()
                return True, "owner_bound"
            return False, "session_owner_missing"
        if owner != uid:
            return False, "session_owner_mismatch"
    return True, "ok"


def _dev_mode_enabled() -> bool:
    raw = str(os.environ.get("NOVA_DEV_MODE") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _chat_users_path() -> Path:
    return RUNTIME_DIR / "chat_users.json"


def _chat_auth_source() -> str:
    if _chat_users_path().exists():
        return "managed_file"
    if str(os.environ.get("NOVA_CHAT_USERS_JSON") or "").strip():
        return "env_json"
    if str(os.environ.get("NOVA_CHAT_USER") or "").strip() and str(os.environ.get("NOVA_CHAT_PASS") or "").strip():
        return "env_pair"
    return "disabled"


def _hash_chat_password(password: str, *, iterations: int = CHAT_PASSWORD_HASH_ITERATIONS) -> dict:
    pwd = str(password or "")
    salt = os.urandom(16).hex()
    digest = hashlib.pbkdf2_hmac("sha256", pwd.encode("utf-8"), bytes.fromhex(salt), max(1, int(iterations))).hex()
    return {"salt": salt, "hash": digest, "iterations": max(1, int(iterations))}


def _save_managed_chat_users(users: dict) -> None:
    payload: dict[str, dict] = {}
    for raw_user, value in dict(users or {}).items():
        user = _normalize_user_id(str(raw_user or ""))
        if not user:
            continue
        if isinstance(value, dict):
            salt_hex = str(value.get("salt") or "").strip().lower()
            hash_hex = str(value.get("hash") or "").strip().lower()
            iterations = int(value.get("iterations") or CHAT_PASSWORD_HASH_ITERATIONS)
            if salt_hex and hash_hex:
                payload[user] = {"salt": salt_hex, "hash": hash_hex, "iterations": max(1, iterations)}
                continue
        payload[user] = _hash_chat_password(str(value or ""))
    _chat_users_path().parent.mkdir(parents=True, exist_ok=True)
    _chat_users_path().write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")


def _chat_users() -> dict:
    managed_path = _chat_users_path()
    if managed_path.exists():
        try:
            data = json.loads(managed_path.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        out: dict = {}
        if isinstance(data, dict):
            for raw_user, value in data.items():
                user = _normalize_user_id(str(raw_user or ""))
                if not user:
                    continue
                out[user] = value
        return out

    env_json = str(os.environ.get("NOVA_CHAT_USERS_JSON") or "").strip()
    if env_json:
        try:
            data = json.loads(env_json)
        except Exception:
            data = {}
        out: dict = {}
        if isinstance(data, dict):
            for raw_user, value in data.items():
                user = _normalize_user_id(str(raw_user or ""))
                if not user:
                    continue
                out[user] = value
        return out

    env_user = _normalize_user_id(str(os.environ.get("NOVA_CHAT_USER") or ""))
    env_pass = str(os.environ.get("NOVA_CHAT_PASS") or "")
    if env_user and env_pass:
        return {env_user: env_pass}
    return {}


def _chat_password_matches(expected, pwd: str) -> bool:
    if isinstance(expected, dict):
        salt_hex = str(expected.get("salt") or "").strip().lower()
        hash_hex = str(expected.get("hash") or "").strip().lower()
        iterations = int(expected.get("iterations") or CHAT_PASSWORD_HASH_ITERATIONS)
        if not salt_hex or not hash_hex:
            return False
        try:
            candidate = hashlib.pbkdf2_hmac("sha256", str(pwd or "").encode("utf-8"), bytes.fromhex(salt_hex), max(1, iterations)).hex()
        except Exception:
            return False
        return secrets.compare_digest(candidate, hash_hex)
    return secrets.compare_digest(str(expected or ""), str(pwd or ""))


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
    for part in raw.split(";"):
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        out[key.strip()] = value.strip()
    return out


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


def _chat_auth_payload() -> dict:
    users = _chat_users()
    return {
        "enabled": bool(users),
        "source": _chat_auth_source(),
        "count": len(users),
        "users": sorted(users.keys()),
        "managed_path": str(_chat_users_path()),
    }


def _chat_user_upsert(username: str, password: str) -> tuple[bool, str]:
    user = _normalize_user_id(username)
    pwd = str(password or "")
    if not user:
        return False, "username_required"
    if not pwd:
        return False, "password_required"
    users = dict(_chat_users())
    users[user] = pwd
    _save_managed_chat_users(users)
    return True, f"chat_user_saved:{user}"


def _chat_user_delete(username: str) -> tuple[bool, str]:
    user = _normalize_user_id(username)
    if not user:
        return False, "username_required"
    users = dict(_chat_users())
    if user not in users:
        return False, "chat_user_not_found"
    users.pop(user, None)
    _save_managed_chat_users(users)
    return True, f"chat_user_deleted:{user}"


def _chat_login_enabled() -> bool:
    return bool(_chat_users())


def _prune_chat_sessions() -> None:
    now = time.time()
    stale = [sid for sid, (_user, exp) in CHAT_SESSIONS.items() if exp <= now]
    for sid in stale:
        CHAT_SESSIONS.pop(sid, None)


def _new_chat_session(user_id: str) -> str:
    sid = secrets.token_hex(24)
    CHAT_SESSIONS[sid] = (_normalize_user_id(user_id), time.time() + CHAT_SESSION_TTL_SECONDS)
    return sid


def _clear_chat_session(handler: BaseHTTPRequestHandler) -> None:
    sid = (_parse_cookie_map(handler).get("nova_chat_session") or "").strip()
    if sid:
        CHAT_SESSIONS.pop(sid, None)


def _chat_login_auth(handler: BaseHTTPRequestHandler) -> tuple[bool, str]:
    if not _chat_login_enabled():
        return True, ""

    _prune_chat_sessions()
    cookies = _parse_cookie_map(handler)
    sid = (cookies.get("nova_chat_session") or "").strip()
    if sid:
        info = CHAT_SESSIONS.get(sid)
        if info and info[1] > time.time():
            return True, str(info[0] or "")
    return False, "chat_login_required"


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
    if _dev_mode_enabled():
        return True, ""

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
                running = bool(psutil.pid_exists(pid))
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
    # A prior stop request leaves guard.stop behind; clear it on explicit start.
    stop_file = RUNTIME_DIR / "guard.stop"
    try:
        if stop_file.exists():
            stop_file.unlink()
    except Exception:
        pass
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


def _core_status_payload() -> dict:
    state_path = RUNTIME_DIR / "core_state.json"
    hb_age = _heartbeat_age_seconds()
    pid = None
    running = False
    create_time = None
    try:
        if state_path.exists():
            st = json.loads(state_path.read_text(encoding="utf-8") or "{}")
            pid_raw = st.get("pid")
            if isinstance(pid_raw, int) and pid_raw > 0:
                pid = pid_raw
            elif isinstance(pid_raw, str) and pid_raw.isdigit():
                pid = int(pid_raw)
            ct_raw = st.get("create_time")
            if isinstance(ct_raw, (int, float)):
                create_time = float(ct_raw)
    except Exception:
        pass

    if isinstance(pid, int) and pid > 0:
        running = bool(psutil.pid_exists(pid))

    if not running and isinstance(hb_age, int) and hb_age <= 5:
        # Fallback signal when state pid is stale but heartbeat is fresh.
        running = True

    return {
        "running": bool(running),
        "pid": pid,
        "create_time": create_time,
        "heartbeat_age_sec": hb_age,
    }


def _start_nova_core() -> tuple[bool, str]:
    if not CORE_PY.exists():
        return False, f"core_script_missing:{CORE_PY}"
    cs = _core_status_payload()
    if cs.get("running"):
        return True, "nova_core_already_running"

    # Start via guard so core restart/heartbeat supervision remains deterministic.
    ok, msg = _start_guard()
    if not ok:
        return False, f"nova_core_start_failed:{msg}"
    if msg in {"guard_start_requested", "guard_already_running"}:
        return True, "nova_core_start_requested_via_guard"
    return True, f"nova_core_start_via_guard:{msg}"


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


def _runtime_process_note() -> str:
    if os.name == "nt":
        return (
            "Windows note: Command Center reports logical service state. "
            "Launcher and child interpreter pairs can appear as duplicate python processes, "
            "but nova_http reporting collapses them to the leaf service process."
        )
    return "Process counts reflect the active service process state."


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
    if provider == "searxng":
        if endpoint:
            searx_ok, searx_note = _probe_searxng(endpoint)
        else:
            searx_ok, searx_note = None, "endpoint_missing"

    payload = {
        "ok": True,
        "server_time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "ollama_api_up": bool(nova_core.ollama_api_up()),
        "chat_model": nova_core.chat_model(),
        "memory_enabled": bool(nova_core.mem_enabled()),
        "memory_scope": str((p.get("memory") or {}).get("scope") or "private"),
        "web_enabled": bool((p.get("tools_enabled") or {}).get("web")) and bool(web_cfg.get("enabled")),
        "search_provider": provider,
        "search_api_endpoint": endpoint,
        "allow_domains_count": len(web_cfg.get("allow_domains") or []),
        "process_counting_mode": "logical_leaf_processes" if os.name == "nt" else "direct_process_state",
        "runtime_process_note": _runtime_process_note(),
        "heartbeat_age_sec": _heartbeat_age_seconds(),
        "active_http_sessions": len(SESSION_TURNS),
        "chat_login_enabled": bool(_chat_login_enabled()),
        "chat_auth_source": _chat_auth_source(),
        "chat_users_count": len(_chat_users()),
        "searxng_ok": searx_ok,
        "searxng_note": searx_note,
        "guard": _guard_status_payload(),
    }
    memory_stats = nova_core.mem_stats_payload(emit_event=False)
    payload["memory_stats_ok"] = bool(memory_stats.get("ok", False))
    payload["memory_entries_total"] = int(memory_stats.get("total", 0) or 0)
    payload["memory_by_user_count"] = len(memory_stats.get("by_user") or {}) if isinstance(memory_stats.get("by_user"), dict) else 0
    memory_summary = _memory_events_summary(80)
    payload["memory_events_ok"] = bool(memory_summary.get("ok", False))
    payload["memory_events_total"] = int(memory_summary.get("count", 0))
    payload["memory_write_count"] = int(memory_summary.get("write_count", 0))
    payload["memory_recall_count"] = int(memory_summary.get("recall_count", 0))
    payload["memory_skipped_count"] = int(memory_summary.get("skipped_count", 0))
    payload["memory_events_avg_latency_ms"] = int(memory_summary.get("avg_latency_ms", 0))
    last_memory = memory_summary.get("last_event") if isinstance(memory_summary.get("last_event"), dict) else {}
    payload["last_memory_action"] = str(last_memory.get("action") or "")
    payload["last_memory_status"] = str(last_memory.get("status") or "")
    tool_summary = _tool_events_summary(80)
    payload["tool_events_ok"] = bool(tool_summary.get("ok", False))
    payload["tool_events_total"] = int(tool_summary.get("count", 0))
    status_counts = tool_summary.get("status_counts") if isinstance(tool_summary.get("status_counts"), dict) else {}
    last_tool = tool_summary.get("last_event") if isinstance(tool_summary.get("last_event"), dict) else {}
    payload["tool_events_ok_count"] = int(status_counts.get("ok", 0))
    payload["tool_events_denied_count"] = int(status_counts.get("denied", 0))
    payload["tool_events_error_count"] = int(status_counts.get("error", 0))
    payload["tool_events_success_count"] = int(tool_summary.get("success_count", 0))
    payload["tool_events_failure_count"] = int(tool_summary.get("failure_count", 0))
    payload["tool_events_avg_latency_ms"] = int(tool_summary.get("avg_latency_ms", 0))
    payload["tool_avg_latency_ms_by_tool"] = tool_summary.get("avg_latency_ms_by_tool") or {}
    payload["last_tool_error_summary"] = str(tool_summary.get("last_error_summary") or "")
    payload["last_tool_name"] = str(last_tool.get("tool") or "")
    payload["last_tool_status"] = str(last_tool.get("status") or "")
    payload["last_tool_user"] = str(last_tool.get("user") or "")
    ledger_summary = _action_ledger_summary(80)
    payload["action_ledger_ok"] = bool(ledger_summary.get("ok", False))
    payload["action_ledger_total"] = int(ledger_summary.get("count", 0) or 0)
    last_record = ledger_summary.get("last_record") if isinstance(ledger_summary.get("last_record"), dict) else {}
    payload["last_intent"] = str(last_record.get("intent") or "")
    payload["last_planner_decision"] = str(last_record.get("planner_decision") or "")
    payload["last_action_tool"] = str(last_record.get("tool") or "")
    payload["last_route_summary"] = str(last_record.get("route_summary") or "")
    payload["last_route_grounded"] = bool(last_record.get("grounded")) if last_record else False
    payload["last_route_trace"] = list(last_record.get("route_trace") or []) if isinstance(last_record.get("route_trace"), list) else []
    payload["last_action_final_answer"] = str(last_record.get("final_answer") or "")
    core = _core_status_payload()
    payload["core"] = core
    payload["core_running"] = bool(core.get("running"))
    payload["core_pid"] = core.get("pid")
    payload["core_heartbeat_age_sec"] = core.get("heartbeat_age_sec")
    with _METRICS_LOCK:
        payload["requests_total"] = _HTTP_REQUESTS_TOTAL
        payload["errors_total"] = _HTTP_ERRORS_TOTAL
    _append_metrics_snapshot(payload)
    # Derive health score from strict self-check ratio.
    sc = _build_self_check(payload, _control_policy_payload(), _metrics_payload())
    payload["health_score"] = int(sc.get("health_score", 0))
    payload["self_check_pass_ratio"] = float(sc.get("pass_ratio", 0.0))
    payload["alerts"] = list(sc.get("alerts") or [])
    return payload


def _control_policy_payload() -> dict:
    p = nova_core.load_policy()
    return {
        "ok": True,
        "tools_enabled": p.get("tools_enabled") or {},
        "models": p.get("models") or {},
        "memory": p.get("memory") or {},
        "web": p.get("web") or {},
        "chat_auth": _chat_auth_payload(),
    }


def _control_action(action: str, payload: dict) -> tuple[bool, str, dict]:
    act = (action or "").strip().lower()
    if not act:
        return False, "action_required", {}

    if act == "refresh_status":
        ok, msg, extra = True, "status_refreshed", _control_status_payload()
        _record_control_action_event(act, "ok", msg, payload)
        return ok, msg, extra

    if act == "guard_status":
        ok, msg, extra = True, "guard_status_ok", {"guard": _guard_status_payload()}
        _record_control_action_event(act, "ok", msg, payload)
        return ok, msg, extra

    if act == "guard_start":
        ok, msg = _start_guard()
        _record_control_action_event(act, "ok" if ok else "fail", msg, payload)
        return ok, msg, {"guard": _guard_status_payload()}

    if act == "guard_stop":
        ok, msg = _stop_guard()
        _record_control_action_event(act, "ok" if ok else "fail", msg, payload)
        return ok, msg, {"guard": _guard_status_payload()}

    if act == "nova_start":
        ok, msg = _start_nova_core()
        _record_control_action_event(act, "ok" if ok else "fail", msg, payload)
        return ok, msg, {"core": _core_status_payload()}

    if act == "test_session_run":
        ok, msg, extra = _run_test_session_definition(str(payload.get("session_file") or ""))
        _record_control_action_event(act, "ok" if ok else "fail", msg, payload)
        return ok, msg, extra

    if act == "session_delete":
        ok, msg = _delete_session(str(payload.get("session_id") or ""))
        _record_control_action_event(act, "ok" if ok else "fail", msg, payload)
        return ok, msg, {"sessions": _session_summaries(80)}

    if act == "policy_allow":
        domain = str(payload.get("domain") or "").strip()
        msg = nova_core.policy_allow_domain(domain)
        _record_control_action_event(act, "ok", msg, payload)
        return True, msg, {}

    if act == "policy_remove":
        domain = str(payload.get("domain") or "").strip()
        msg = nova_core.policy_remove_domain(domain)
        _record_control_action_event(act, "ok", msg, payload)
        return True, msg, {}

    if act == "web_mode":
        mode = str(payload.get("mode") or "").strip()
        msg = nova_core.set_web_mode(mode)
        _record_control_action_event(act, "ok", msg, payload)
        return True, msg, {}

    if act == "memory_scope_set":
        scope = str(payload.get("scope") or "").strip()
        msg = nova_core.set_memory_scope(scope)
        ok = not msg.lower().startswith("usage:")
        _record_control_action_event(act, "ok" if ok else "fail", msg, payload)
        return ok, msg, {"policy": _control_policy_payload()}

    if act == "search_provider":
        provider = str(payload.get("provider") or "").strip()
        msg = nova_core.set_search_provider(provider)
        ok = not msg.lower().startswith("usage:")
        _record_control_action_event(act, "ok" if ok else "fail", msg, payload)
        return ok, msg, {"policy": _control_policy_payload()}

    if act == "search_provider_toggle":
        msg = nova_core.toggle_search_provider()
        _record_control_action_event(act, "ok", msg, payload)
        return True, msg, {"policy": _control_policy_payload()}

    if act == "chat_user_list":
        msg = "chat_user_list_ok"
        _record_control_action_event(act, "ok", msg, payload)
        return True, msg, {"chat_auth": _chat_auth_payload()}

    if act == "chat_user_upsert":
        ok, msg = _chat_user_upsert(str(payload.get("username") or ""), str(payload.get("password") or ""))
        _record_control_action_event(act, "ok" if ok else "fail", msg, payload)
        return ok, msg, {"chat_auth": _chat_auth_payload()}

    if act == "chat_user_delete":
        ok, msg = _chat_user_delete(str(payload.get("username") or ""))
        _record_control_action_event(act, "ok" if ok else "fail", msg, payload)
        return ok, msg, {"chat_auth": _chat_auth_payload()}

    if act == "inspect":
        try:
            data = nova_core.inspect_environment()
            report = nova_core.format_report(data)
            _record_control_action_event(act, "ok", "inspect_ok", payload)
            return True, "inspect_ok", {"report": report}
        except Exception as e:
            _record_control_action_event(act, "fail", str(e), payload)
            return False, f"inspect_failed:{e}", {}

    if act == "policy_audit":
        try:
            text = nova_core.policy_audit(30)
            _record_control_action_event(act, "ok", "policy_audit_ok", payload)
            return True, "policy_audit_ok", {"text": text}
        except Exception as e:
            _record_control_action_event(act, "fail", str(e), payload)
            return False, f"policy_audit_failed:{e}", {}

    if act == "tail_log":
        name = str(payload.get("name") or "").strip().lower()
        allowed = {
            "nova_http.out.log": LOG_DIR / "nova_http.out.log",
            "nova_http.err.log": LOG_DIR / "nova_http.err.log",
            "guard.log": LOG_DIR / "guard.log",
        }
        if name not in allowed:
            _record_control_action_event(act, "fail", "invalid_log_name", payload)
            return False, "invalid_log_name", {}
        out = {"name": name, "text": _tail_file(allowed[name])}
        _record_control_action_event(act, "ok", f"tail_log_ok:{name}", payload)
        return True, "tail_log_ok", out

    if act == "metrics":
        m = _metrics_payload()
        _record_control_action_event(act, "ok", "metrics_ok", payload)
        return True, "metrics_ok", m

    if act == "self_check":
        data = _build_self_check(_control_status_payload(), _control_policy_payload(), _metrics_payload())
        ok = bool(data.get("ok"))
        msg = str(data.get("summary") or "self_check_completed")
        _record_control_action_event(act, "ok" if ok else "fail", msg, payload)
        return ok, msg, data

    if act == "export_capabilities":
        ok, msg, extra = _export_capabilities_snapshot()
        _record_control_action_event(act, "ok" if ok else "fail", msg, payload)
        return ok, msg, extra

    if act == "export_ledger_summary":
        try:
            summary = _action_ledger_summary(limit=int(payload.get("limit") or 60))
            EXPORT_DIR.mkdir(parents=True, exist_ok=True)
            stamp = time.strftime("%Y%m%d_%H%M%S")
            out = EXPORT_DIR / f"action_ledger_summary_{stamp}.json"
            out.write_text(json.dumps(summary, ensure_ascii=True, indent=2), encoding="utf-8")
            msg = "action_ledger_export_ok"
            extra = {"path": str(out), "filename": out.name, "summary": summary}
            _record_control_action_event(act, "ok", msg, payload)
            return True, msg, extra
        except Exception as e:
            _record_control_action_event(act, "fail", str(e), payload)
            return False, f"action_ledger_export_failed:{e}", {}

    if act == "export_diagnostics_bundle":
        try:
            status = _control_status_payload()
            policy = _control_policy_payload()
            metrics = _metrics_payload()
            self_check = _build_self_check(status, policy, metrics)
            bundle = {
                "ts": int(time.time()),
                "status": status,
                "policy": policy,
                "metrics": metrics,
                "self_check": self_check,
                "capabilities": capabilities_mod.list_capabilities(),
                "behavior_metrics": nova_core.behavior_get_metrics(),
                "action_ledger_summary": _action_ledger_summary(80),
                "tool_event_summary": _tool_events_summary(120),
                "logs": {
                    "nova_http_out": _safe_tail_lines(LOG_DIR / "nova_http.out.log", 120),
                    "nova_http_err": _safe_tail_lines(LOG_DIR / "nova_http.err.log", 120),
                },
            }
            out = RUNTIME_DIR / f"diagnostics_bundle_{int(time.time())}.json"
            out.write_text(json.dumps(bundle, ensure_ascii=True, indent=2), encoding="utf-8")
            msg = f"diagnostics_bundle_exported:{out.name}"
            _record_control_action_event(act, "ok", msg, payload)
            return True, msg, {"path": str(out), "filename": out.name}
        except Exception as e:
            _record_control_action_event(act, "fail", str(e), payload)
            return False, f"diagnostics_bundle_export_failed:{e}", {}

    _record_control_action_event(act, "fail", "unknown_action", payload)
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
    return nova_core._quick_smalltalk_reply(user_text, active_user=nova_core.get_active_user())


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


def _file_response(handler: BaseHTTPRequestHandler, code: int, path: Path, content_type: str) -> None:
    try:
        body = path.read_bytes()
    except Exception as e:
        _json_response(handler, 404, {"ok": False, "error": f"asset_not_found:{path.name}:{e}"})
        return
    handler.send_response(code)
    handler.send_header("Content-Type", content_type)
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
    return nova_core._is_developer_profile_request(user_text)


def _developer_profile_reply(turns: List[Tuple[str, str]], user_text: str) -> str:
    return nova_core._developer_profile_reply(turns, user_text)


def _is_developer_location_request(user_text: str, state: dict | None = None, turns: List[Tuple[str, str]] | None = None) -> bool:
    return nova_core._is_developer_location_request(user_text, state=state, turns=turns)


def _developer_location_reply() -> str:
    return nova_core._developer_location_reply()


def _recent_turn_mentions(turns: List[Tuple[str, str]], keywords: list[str], limit: int = 6) -> bool:
    keys = [str(k or "").strip().lower() for k in keywords if str(k or "").strip()]
    if not keys:
        return False
    for role, text in reversed(turns[-max(1, int(limit)):]):
        low = (text or "").strip().lower()
        if not low:
            continue
        if any(k in low for k in keys):
            return True
    return False


def _learn_contextual_developer_facts(turns: List[Tuple[str, str]], text: str) -> tuple[bool, str]:
    return nova_core._learn_contextual_developer_facts(turns, text, input_source="typed")


def _is_location_request(user_text: str) -> bool:
    return nova_core._is_location_request(user_text)


def _location_reply() -> str:
    return nova_core._location_reply()


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
    return nova_core._extract_last_user_question(turns, current_text)


def _is_name_origin_question(text: str) -> bool:
    return nova_core._is_name_origin_question(text)


def _is_assistant_name_query(text: str) -> bool:
    return nova_core._is_assistant_name_query(text)


def _assistant_name_reply(text: str) -> str:
    return nova_core._assistant_name_reply(text)


def _is_developer_full_name_query(text: str) -> bool:
    return nova_core._is_developer_full_name_query(text)


def _developer_full_name_reply() -> str:
    return nova_core._developer_full_name_reply()


def _extract_memory_teach_text(text: str) -> str:
    raw = (text or "").strip()
    if not raw:
        return ""
    low = raw.lower()
    cues = ["remember that", "remember this", "can you remember", "think you can remember"]
    if not any(c in low for c in cues):
        return ""

    cleaned = re.sub(r"(?is)\b(?:can\s+you\s+remember\s+that|think\s+you\s+can\s+remember\s+that|remember\s+that|remember\s+this)\b\s*\??", "", raw).strip(" .,!?")
    if not cleaned:
        return ""
    keep, _reason = nova_core._memory_should_keep_text(cleaned)
    return cleaned if keep else ""


def _rules_reply() -> str:
    return (
        "Yes. I follow strict operating rules: I do not fabricate tool actions or files, "
        "I stay within enabled policy/tool limits, and I should say uncertain when I cannot verify something."
    )


def _strip_ui_tip_leak(text: str) -> str:
    t = (text or "").strip()
    if not t:
        return t
    # Remove UI startup hint leakage even when it appears inline with other text.
    t = re.sub(
        r"(?is)\bTip:\s*start server with --host\s+0\.0\.0\.0[^\n]*",
        "",
        t,
    )
    t = re.sub(r"\n{3,}", "\n\n", t).strip()
    return t


def _is_session_recap_request(text: str) -> bool:
    return nova_core._is_session_recap_request(text)


def _session_recap_reply(turns: List[Tuple[str, str]], current_text: str) -> str:
    return nova_core._session_recap_reply(turns, current_text)


def _is_deep_search_followup_request(text: str) -> bool:
    return nova_core._is_deep_search_followup_request(text)


def _infer_research_query_from_turns(turns: List[Tuple[str, str]]) -> str:
    return nova_core._infer_research_query_from_turns(turns)


def _read_text_safely(path: Path) -> str:
    try:
        raw = path.read_bytes()
    except Exception:
        return ""

    for enc in ("utf-8", "utf-16", "utf-16-le", "utf-16-be"):
        try:
            txt = raw.decode(enc)
            if "\x00" in txt:
                continue
            if txt.strip():
                return txt
        except Exception:
            continue
    return ""


def _extract_key_lines(text: str, max_lines: int = 5) -> List[str]:
    out: List[str] = []
    for raw in (text or "").splitlines():
        s = (raw or "").strip().lstrip("-•").strip()
        if not s:
            continue
        if len(s) < 12:
            continue
        if s.lower().startswith("attendance reporting"):
            continue
        out.append(s.rstrip("."))
        if len(out) >= max_lines:
            break
    return out


def _topic_tokens(text: str) -> List[str]:
    low = (text or "").lower()
    toks = re.findall(r"[a-z0-9]{3,}", low)
    stop = {
        "what", "when", "where", "which", "about", "could", "would", "should",
        "there", "their", "have", "your", "with", "from", "that", "this",
        "please", "tell", "more", "info", "information", "topic",
    }
    out: List[str] = []
    for t in toks:
        if t in stop:
            continue
        if t not in out:
            out.append(t)
    return out[:12]


def _extract_matching_lines(text: str, tokens: List[str], max_lines: int = 3) -> List[str]:
    if not tokens:
        return _extract_key_lines(text, max_lines=max_lines)
    out: List[str] = []
    for raw in (text or "").splitlines():
        s = (raw or "").strip().lstrip("-•").strip()
        if not s or len(s) < 14:
            continue
        low = s.lower()
        score = sum(1 for t in tokens if t in low)
        if score <= 0:
            continue
        out.append(s.rstrip("."))
        if len(out) >= max_lines:
            break
    if out:
        return out
    return _extract_key_lines(text, max_lines=max_lines)


def _build_local_topic_digest_answer(query_text: str, max_files: int = 4, max_points: int = 10) -> str:
    return nova_core._build_local_topic_digest_answer(query_text, max_files=max_files, max_points=max_points)


def _build_local_peims_attendance_answer() -> str:
    files = [
        PEIMS_KNOWLEDGE_DIR / "05_attendance_reporting.txt",
        PEIMS_KNOWLEDGE_DIR / "03_submissions.txt",
        PEIMS_KNOWLEDGE_DIR / "13_reporting_timeline.txt",
        PEIMS_KNOWLEDGE_DIR / "15_terminology.txt",
    ]
    available = [p for p in files if p.exists()]
    if not available:
        return ""

    lines = ["I found additional attendance reporting details in the local PEIMS knowledge files:"]
    facts_added = 0

    backup_lines: List[str] = []

    for p in available:
        key_lines = _extract_key_lines(_read_text_safely(p), max_lines=3)
        for k in key_lines:
            low = k.lower()
            if len(backup_lines) < 4:
                backup_lines.append(k)
            if not any(token in low for token in ["attendance", "ada", "absence", "submission", "report"]):
                continue
            lines.append(f"- {k}.")
            facts_added += 1
            if facts_added >= 4:
                break
        if facts_added >= 4:
            break

    if facts_added == 0:
        for k in backup_lines[:4]:
            lines.append(f"- {k}.")
        facts_added = len(backup_lines[:4])

    if facts_added == 0:
        return ""

    cited = {f"knowledge/peims/{p.name}" for p in available}
    for c in sorted(cited):
        lines.append(f"[source: {c}]")
    return "\n".join(lines)


def _build_local_peims_overview_answer() -> str:
    return nova_core._build_local_peims_overview_answer()


def _is_peims_attendance_rules_query(text: str) -> bool:
    low = (text or "").lower()
    has_peims = "peims" in low
    has_attendance = "attendance" in low
    has_rules = any(k in low for k in ["rules", "requirements", "reporting", "what are", "tea say"])
    return bool(has_peims and has_attendance and has_rules)


def _is_peims_broad_query(text: str) -> bool:
    return nova_core._is_peims_broad_query(text)


def _extract_urls(text: str) -> List[str]:
    seen = set()
    out = []
    for u in re.findall(r"https?://[^\s<>\]')\"]+", text or ""):
        clean = (u or "").strip().rstrip(".,;:)")
        if clean and clean not in seen:
            seen.add(clean)
            out.append(clean)
    return out


def _host_label(url: str) -> str:
    try:
        return (urlparse(url).hostname or "source").lower()
    except Exception:
        return "source"


def _summary_from_gather_output(raw: str) -> str:
    txt = (raw or "").strip()
    if not txt:
        return ""
    m = re.search(r"(?is)Summary snippet:\s*(.+)$", txt)
    if not m:
        return ""
    s = re.sub(r"\s+", " ", (m.group(1) or "").strip())
    # Keep grounded summary brief and readable.
    return s[:260]


def _is_weak_grounded_snippet(s: str) -> bool:
    low = (s or "").strip().lower()
    if not low:
        return True
    weak_cues = [
        "welcome to texas education agency",
        "skip to main content",
        "mega menu",
        "general information",
        "enable javascript to run this app",
        "you need to enable javascript to run this app",
    ]
    if any(c in low for c in weak_cues):
        return True
    # Avoid using extremely short/unspecific snippets as factual grounding.
    if len(low.split()) < 8:
        return True
    return False


def _is_conversational_clarification(text: str) -> bool:
    low = (text or "").strip().lower()
    if not low:
        return False
    cues = [
        "what are you talking about",
        "what are you talking",
        "are you sure about that information",
        "are you sure about that",
        "why i am not asking you",
        "why am i not asking you",
        "you will not find that information",
        "do you need help",
        "what ?",
        "what?",
    ]
    return any(c in low for c in cues)


def _clarification_reply(turns: List[Tuple[str, str]]) -> str:
    last_assistant = ""
    for role, txt in reversed(turns):
        if role == "assistant":
            last_assistant = (txt or "").strip()
            break
    if last_assistant and "allowlisted references" in last_assistant.lower():
        return "You're right. That response drifted into web lookup when you were asking a direct chat question. Ask it again and I'll answer it directly."
    return "You're right. I should stay with the current chat instead of jumping to web lookup for that kind of question."


def _is_groundable_factual_query(text: str) -> bool:
    low = (text or "").strip().lower()
    if not low or len(low) < 8:
        return False
    if not (
        low.startswith(("what", "how", "when", "why", "which", "where", "who"))
        or "tell me about" in low
        or "what do you know about" in low
    ):
        return False
    # Keep identity/smalltalk out of research path.
    if any(x in low for x in ["your name", "who are you", "how are you", "creator", "developer"]):
        return False
    if nova_core._is_capability_query(low):
        return False
    if _is_conversational_clarification(low):
        return False
    return True


def _build_grounded_answer(query_text: str, max_sources: int = 2) -> str:
    research = nova_core.tool_web_research(query_text)
    if not isinstance(research, str) or not research.strip():
        return ""

    urls = _extract_urls(research)
    if not urls:
        return ""

    snippets: List[tuple[str, str]] = []
    for u in urls[: max(1, int(max_sources))]:
        g = nova_core.tool_web_gather(u)
        snip = _summary_from_gather_output(g if isinstance(g, str) else "")
        if snip and not _is_weak_grounded_snippet(snip):
            snippets.append((u, snip))

    # If all gathered snippets are too generic, let caller use deterministic fallback.
    if not snippets:
        return ""

    lines = []
    lines.append("I found sourced information from allowlisted references:")
    for u, snip in snippets:
        lines.append(f"- {snip}")

    cited_hosts = []
    for u in urls[: max(1, int(max_sources))]:
        host = _host_label(u)
        if host not in cited_hosts:
            cited_hosts.append(host)
    for h in cited_hosts:
        lines.append(f"[source: {h}]")

    return "\n".join(lines)


def _peims_attendance_rules_reply() -> str:
    grounded = _build_grounded_answer("PEIMS attendance reporting rules Texas TEA", max_sources=2)
    if grounded:
        return grounded
    local_grounded = _build_local_peims_attendance_answer()
    if local_grounded:
        return local_grounded
    return "I couldn't gather sourced PEIMS attendance rules right now. Please try: web research PEIMS attendance reporting rules"


def _generate_chat_reply(
    turns: List[Tuple[str, str]],
    text: str,
    ledger_record: dict | None = None,
    pending_action: dict | None = None,
    prefer_web_for_data_queries: bool = False,
) -> tuple[str, dict]:
    def _trace(stage: str, outcome: str, detail: str = "", **data) -> None:
        nova_core.action_ledger_add_step(ledger_record, stage, outcome, detail, **data)

    def _normalize_reply(reply_text: str) -> str:
        reply_local = _strip_ui_tip_leak(reply_text)
        corrected_reply, was_corrected, _reason = nova_core._self_correct_reply(text, reply_local)
        if was_corrected:
            nova_core.behavior_record_event("correction_applied")
            nova_core.behavior_record_event("self_correction_applied")
            _trace("llm_postprocess", "self_corrected")
            reply_local = corrected_reply
        if not nova_core._is_identity_stable_reply(reply_local):
            reply_local = nova_core._apply_reply_overrides(reply_local)
        return nova_core._ensure_reply(reply_local)

    low = text.lower()
    handled_truth, truth_reply, _truth_source, _truth_grounded = nova_core.truth_hierarchy_answer(text)
    if handled_truth:
        _trace("truth_hierarchy", "matched", tool=str(_truth_source or ""), grounded=bool(_truth_grounded))
        reply = truth_reply
        # For creator/name profile prompts, prefer deterministic hard answers when available.
        if _is_developer_profile_request(text):
            hard = nova_core.hard_answer(text)
            if hard:
                reply = hard
            elif reply.lower().startswith("uncertain. no structured identity fact"):
                reply = _developer_profile_reply(turns, text)
        elif reply.lower().startswith("uncertain. no structured identity fact"):
            if _is_location_request(text):
                reply = _location_reply()
            else:
                hard = nova_core.hard_answer(text)
                if hard:
                    reply = hard
        return _normalize_reply(reply), {
            "planner_decision": "truth_hierarchy",
            "tool": str(_truth_source or ""),
            "tool_args": {"query": text},
            "tool_result": str(reply or ""),
            "grounded": bool(_truth_grounded),
        }
    _trace("truth_hierarchy", "not_matched")

    hard = nova_core.hard_answer(text)
    if hard:
        _trace("hard_answer", "matched", grounded=True)
        reply = _normalize_reply(hard)
        return reply, {
            "planner_decision": "deterministic",
            "tool": "hard_answer",
            "tool_args": {"query": text},
            "tool_result": reply,
            "grounded": True,
        }
    _trace("hard_answer", "not_matched")

    try:
        actions = nova_core.decide_actions(
            text,
            config={
                "session_turns": turns,
                "pending_action": pending_action or {},
                "prefer_web_for_data_queries": prefer_web_for_data_queries,
            },
        )
    except Exception:
        actions = []

    if actions:
        act = actions[0]
        atype = act.get("type")
        if atype == "ask_clarify":
            _trace("action_planner", "ask_clarify")
            reply = act.get("question") or act.get("note") or "Can you clarify?"
            return _normalize_reply(reply), {
                "planner_decision": "ask_clarify",
                "tool": "",
                "tool_args": {"query": text},
                "tool_result": str(reply or ""),
                "grounded": False,
                "pending_action": nova_core.make_pending_weather_action() if "weather lookup" in str(reply or "").lower() else {},
            }

        if atype == "respond":
            _trace("action_planner", "respond")
            reply = act.get("note") or act.get("message") or "Tell me a bit more about what you want me to inspect."
            return _normalize_reply(reply), {
                "planner_decision": "respond",
                "tool": "",
                "tool_args": {"query": text},
                "tool_result": str(reply or ""),
                "grounded": False,
            }

        if atype == "route_command":
            _trace("action_planner", "route_command")
            cmd_reply = nova_core.handle_commands(text, session_turns=turns)
            if cmd_reply:
                tool_name = "weather" if "api.weather.gov" in str(cmd_reply).lower() else ""
                _trace("command", "matched", tool=tool_name)
                return _normalize_reply(cmd_reply), {
                    "planner_decision": "command",
                    "tool": tool_name,
                    "tool_args": {"raw": text},
                    "tool_result": str(cmd_reply or ""),
                    "grounded": bool(tool_name),
                    "pending_action": {},
                }
            _trace("command", "not_matched")

        if atype == "route_keyword":
            _trace("action_planner", "route_keyword")
            kw = nova_core.handle_keywords(text)
            if kw:
                _kind, _tool, out = kw
                _trace("keyword_tool", "matched", tool=str(_tool or ""), grounded=bool(str(out or "").strip()))
                return _normalize_reply(str(out or "")), {
                    "planner_decision": "run_tool",
                    "tool": str(_tool or ""),
                    "tool_args": {"raw": text},
                    "tool_result": str(out or ""),
                    "grounded": bool(str(out or "").strip()),
                    "pending_action": {},
                }
            _trace("keyword_tool", "not_matched")

        if atype == "run_tool":
            tool = str(act.get("tool") or "")
            args = act.get("args") or []
            _trace("action_planner", "run_tool", tool=tool)
            out = nova_core.execute_planned_action(tool, args)
            if out is None or (isinstance(out, str) and not out.strip()):
                _trace("tool_execution", "empty_result", tool=tool)
                reply = nova_core._web_allowlist_message("requested resource") if tool.startswith("web") else f"The {tool} tool did not return a result. No data was available."
                return _normalize_reply(reply), {
                    "planner_decision": "run_tool",
                    "tool": tool,
                    "tool_args": {"args": list(args) if isinstance(args, (list, tuple)) else args},
                    "tool_result": "",
                    "grounded": False,
                    "pending_action": {},
                }
            if isinstance(out, dict) and not out.get("ok", True):
                _trace("tool_execution", "error", tool=tool, error=str(out.get("error") or "unknown error"))
                err = out.get("error", "unknown error")
                if isinstance(err, str) and ("not allowed" in err.lower() or "domain not allowed" in err.lower()):
                    reply = nova_core._web_allowlist_message(args[0] if args else "")
                else:
                    reply = f"Tool {tool} failed: {err}"
                return _normalize_reply(reply), {
                    "planner_decision": "run_tool",
                    "tool": tool,
                    "tool_args": {"args": list(args) if isinstance(args, (list, tuple)) else args},
                    "tool_result": json.dumps(out, ensure_ascii=True),
                    "grounded": False,
                    "pending_action": {},
                }
            _trace("tool_execution", "ok", tool=tool, grounded=bool(str(out or "").strip()))
            return _normalize_reply(str(out or "")), {
                "planner_decision": "run_tool",
                "tool": tool,
                "tool_args": {"args": list(args) if isinstance(args, (list, tuple)) else args},
                "tool_result": str(out or ""),
                "grounded": bool(str(out or "").strip()),
                "pending_action": {},
            }

    if _is_peims_broad_query(text):
        local_overview = _build_local_peims_overview_answer()
        if local_overview:
            _trace("grounded_lookup", "matched", tool="local_knowledge")
            return _normalize_reply(local_overview), {
                "planner_decision": "grounded_lookup",
                "tool": "local_knowledge",
                "tool_args": {"query": text},
                "tool_result": local_overview,
                "grounded": True,
            }

    if _is_session_recap_request(text):
        _trace("deterministic_reply", "matched", detail="session_recap")
        reply = _session_recap_reply(turns, text)
        return _normalize_reply(reply), {
            "planner_decision": "deterministic",
            "tool": "session_recap",
            "tool_args": {"query": text},
            "tool_result": reply,
            "grounded": True,
        }
    elif _is_assistant_name_query(text):
        _trace("deterministic_reply", "matched", detail="assistant_name")
        reply = _assistant_name_reply(text)
        return _normalize_reply(reply), {
            "planner_decision": "deterministic",
            "tool": "assistant_name",
            "tool_args": {"query": text},
            "tool_result": reply,
            "grounded": True,
        }
    elif "what was my last question" in low or "what was my previous question" in low:
        _trace("deterministic_reply", "matched", detail="last_question")
        last_q = _extract_last_user_question(turns, text)
        if last_q:
            reply = f"Your last question before this one was: {last_q}"
        else:
            reply = "I don't have an earlier question in this active chat session."
        return _normalize_reply(reply), {
            "planner_decision": "deterministic",
            "tool": "session_history",
            "tool_args": {"query": text},
            "tool_result": reply,
            "grounded": True,
        }
    elif _is_developer_full_name_query(text):
        _trace("deterministic_reply", "matched", detail="developer_full_name")
        reply = _developer_full_name_reply()
        return _normalize_reply(reply), {
            "planner_decision": "deterministic",
            "tool": "developer_identity",
            "tool_args": {"query": text},
            "tool_result": reply,
            "grounded": True,
        }
    elif "do you remember our last chat session" in low or "remember our last chat" in low:
        _trace("deterministic_reply", "matched", detail="memory_policy_explanation")
        reply = "I remember parts of prior chats only if they were saved to memory; I remember this live session context directly."
        return _normalize_reply(reply), {
            "planner_decision": "deterministic",
            "tool": "memory_policy",
            "tool_args": {"query": text},
            "tool_result": reply,
            "grounded": True,
        }
    elif "do you have any rules" in low or "what rules do you follow" in low:
        _trace("deterministic_reply", "matched", detail="rules_reply")
        reply = _rules_reply()
        return _normalize_reply(reply), {
            "planner_decision": "deterministic",
            "tool": "rules",
            "tool_args": {"query": text},
            "tool_result": reply,
            "grounded": True,
        }
    elif _is_name_origin_question(text):
        _trace("deterministic_reply", "matched", detail="name_origin_query")
        story = nova_core.get_name_origin_story().strip()
        if story:
            reply = f"Yes. {story}"
        else:
            reply = "I do not have a saved name-origin story yet. You can tell me with: remember this Nova ..."
        return _normalize_reply(reply), {
            "planner_decision": "deterministic",
            "tool": "name_origin",
            "tool_args": {"query": text},
            "tool_result": reply,
            "grounded": bool(story),
        }
    elif _is_peims_attendance_rules_query(text):
        _trace("grounded_lookup", "matched", tool="peims_attendance")
        reply = _peims_attendance_rules_reply()
        return _normalize_reply(reply), {
            "planner_decision": "grounded_lookup",
            "tool": "peims_attendance",
            "tool_args": {"query": text},
            "tool_result": reply,
            "grounded": "[source:" in reply.lower(),
        }
    elif _is_developer_profile_request(text):
        _trace("deterministic_reply", "matched", detail="developer_profile")
        reply = _developer_profile_reply(turns, text)
        return _normalize_reply(reply), {
            "planner_decision": "deterministic",
            "tool": "developer_profile",
            "tool_args": {"query": text},
            "tool_result": reply,
            "grounded": True,
        }
    elif _is_conversational_clarification(text):
        _trace("deterministic_reply", "matched", detail="clarification_reply")
        reply = _clarification_reply(turns)
        return _normalize_reply(reply), {
            "planner_decision": "deterministic",
            "tool": "clarification_reply",
            "tool_args": {"query": text},
            "tool_result": reply,
            "grounded": True,
        }
    elif _is_location_request(text):
        _trace("deterministic_reply", "matched", detail="location_reply")
        reply = _location_reply()
        return _normalize_reply(reply), {
            "planner_decision": "deterministic",
            "tool": "location",
            "tool_args": {"query": text},
            "tool_result": reply,
            "grounded": True,
        }
    elif _is_deep_search_followup_request(text):
        inferred = _infer_research_query_from_turns(turns)
        query = inferred or text
        grounded = _build_grounded_answer(query, max_sources=2)
        if grounded:
            _trace("grounded_lookup", "matched", tool="web_research")
            reply = grounded
            return _normalize_reply(reply), {
                "planner_decision": "grounded_lookup",
                "tool": "web_research",
                "tool_args": {"query": query},
                "tool_result": reply,
                "grounded": True,
            }
        else:
            local_grounded = _build_local_topic_digest_answer(query)
            if local_grounded:
                _trace("grounded_lookup", "matched", tool="local_knowledge")
                reply = local_grounded
                return _normalize_reply(reply), {
                    "planner_decision": "grounded_lookup",
                    "tool": "local_knowledge",
                    "tool_args": {"query": query},
                    "tool_result": reply,
                    "grounded": True,
                }
            else:
                _trace("grounded_lookup", "missed", tool="web_research")
                reply = "I could not find additional grounded sources right now. Please try: web research <topic>"
                return _normalize_reply(reply), {
                    "planner_decision": "grounded_lookup",
                    "tool": "web_research",
                    "tool_args": {"query": query},
                    "tool_result": reply,
                    "grounded": False,
                }
    elif _is_groundable_factual_query(text):
        grounded = _build_grounded_answer(text, max_sources=2)
        if grounded:
            _trace("grounded_lookup", "matched", tool="web_research")
            reply = grounded
            return _normalize_reply(reply), {
                "planner_decision": "grounded_lookup",
                "tool": "web_research",
                "tool_args": {"query": text},
                "tool_result": reply,
                "grounded": True,
            }
        else:
            local_grounded = _build_local_topic_digest_answer(text)
            if local_grounded:
                _trace("grounded_lookup", "matched", tool="local_knowledge")
                reply = local_grounded
                return _normalize_reply(reply), {
                    "planner_decision": "grounded_lookup",
                    "tool": "local_knowledge",
                    "tool_args": {"query": text},
                    "tool_result": reply,
                    "grounded": True,
                }
            else:
                _trace("grounded_lookup", "missed", tool="web_research")
                reply = "I couldn't find grounded sources for that yet. Please try: web research <your question>"
                return _normalize_reply(reply), {
                    "planner_decision": "grounded_lookup",
                    "tool": "web_research",
                    "tool_args": {"query": text},
                    "tool_result": reply,
                    "grounded": False,
                }
    elif nova_core._is_developer_color_lookup_request(text):
        _trace("deterministic_reply", "matched", detail="developer_color_reply")
        reply = _developer_color_reply(turns)
        return _normalize_reply(reply), {
            "planner_decision": "deterministic",
            "tool": "developer_color_reply",
            "tool_args": {"query": text},
            "tool_result": reply,
            "grounded": True,
        }
    elif nova_core._is_developer_bilingual_request(text):
        _trace("deterministic_reply", "matched", detail="developer_bilingual_reply")
        reply = _developer_bilingual_reply(turns)
        return _normalize_reply(reply), {
            "planner_decision": "deterministic",
            "tool": "developer_bilingual_reply",
            "tool_args": {"query": text},
            "tool_result": reply,
            "grounded": True,
        }
    elif nova_core._is_color_lookup_request(text):
        _trace("deterministic_reply", "matched", detail="color_reply")
        reply = _color_reply(turns)
        return _normalize_reply(reply), {
            "planner_decision": "deterministic",
            "tool": "color_reply",
            "tool_args": {"query": text},
            "tool_result": reply,
            "grounded": True,
        }
    elif "what animals do i like" in low or "which animals do i like" in low:
        _trace("deterministic_reply", "matched", detail="animal_reply")
        reply = _animal_reply(turns)
        return _normalize_reply(reply), {
            "planner_decision": "deterministic",
            "tool": "animal_reply",
            "tool_args": {"query": text},
            "tool_result": reply,
            "grounded": True,
        }
    else:
        # Always provide recent session turns so the model can follow thread continuity.
        context_blocks: List[str] = []

        # Match CLI recall behavior: always build learning context for better continuity.
        context_details = nova_core.build_learning_context_details(text)
        mem_ctx = str(context_details.get("context") or "")
        _trace(
            "memory_context",
            "used" if mem_ctx else "empty",
            memory_used=bool(context_details.get("memory_used")),
            knowledge_used=bool(context_details.get("knowledge_used")),
            memory_chars=int(context_details.get("memory_chars") or 0),
            knowledge_chars=int(context_details.get("knowledge_chars") or 0),
        )
        if mem_ctx:
            context_blocks.append(mem_ctx)

        chat_ctx = nova_core._render_chat_context(turns)
        if chat_ctx:
            context_blocks.append("CURRENT CHAT CONTEXT:\n" + chat_ctx)
            _trace("chat_context", "used", chars=len(chat_ctx))

        retrieved = "\n\n".join(context_blocks).strip()[:6000]
        _trace("llm_fallback", "invoked", retrieved_chars=len(retrieved))
        reply = nova_core.ollama_chat(text, retrieved_context=retrieved)
        reply = nova_core.sanitize_llm_reply(reply, "")
        return _normalize_reply(reply), {
            "planner_decision": "llm_fallback",
            "tool": "",
            "tool_args": {},
            "tool_result": "",
            "grounded": False if not reply else None,
        }


def process_chat(session_id: str, user_text: str, user_id: str = "") -> str:
    previous_user = nova_core.get_active_user()
    nova_core.set_active_user(user_id or previous_user)
    try:
        text = nova_core._strip_invocation_prefix((user_text or "").strip())
        if not text:
            return "Okay."

        session = SESSION_STATE_MANAGER.get(session_id)
        session.reset_turn_flags()
        conversation_state = session.conversation_state

        ledger = nova_core.start_action_ledger_record(
            text,
            channel="http",
            session_id=session_id,
            input_source="typed",
            active_subject=session.active_subject(),
        )

        def _finalize_http_reply(
            reply_text: str,
            *,
            planner_decision: str = "deterministic",
            tool: str = "",
            tool_args: dict | None = None,
            tool_result: str = "",
            grounded: bool | None = None,
            intent: str = "",
        ) -> str:
            reflection_payload = nova_core.build_turn_reflection(
                session,
                entry_point="http",
                session_id=session_id,
                current_decision={
                    "user_input": text,
                    "planner_decision": planner_decision,
                    "tool": tool,
                    "tool_args": tool_args if isinstance(tool_args, dict) else {},
                    "tool_result": tool_result,
                    "final_answer": reply_text,
                    "grounded": grounded,
                    "active_subject": session.active_subject(),
                    "continuation_used": session.continuation_used_last_turn,
                    "pending_action": session.pending_action,
                    "route_summary": nova_core.action_ledger_route_summary(ledger),
                    "overrides_active": session.reflection_summary().get("overrides_active", []),
                },
            )
            nova_core.finalize_action_ledger_record(
                ledger,
                final_answer=reply_text,
                planner_decision=planner_decision,
                tool=tool,
                tool_args=tool_args if isinstance(tool_args, dict) else {},
                tool_result=tool_result,
                grounded=grounded,
                intent=intent,
                active_subject=session.active_subject(),
                continuation_used=session.continuation_used_last_turn,
                reflection_payload=reflection_payload,
            )
            return reply_text

        quick = _fast_smalltalk_reply(text)
        if quick:
            nova_core.action_ledger_add_step(ledger, "fast_smalltalk", "matched")
            return _finalize_http_reply(quick, planner_decision="deterministic", grounded=False)

        turns = _append_session_turn(session_id, "user", text)

        # HTTP pending-correction flow mirrors CLI autonomous correction behavior.
        pending = session.pending_correction_target
        if pending:
            corr = nova_core._extract_authoritative_correction_text(text)
            if corr:
                nova_core.action_ledger_add_step(ledger, "correction_capture", "applied")
                corr_store = nova_core._normalize_correction_for_storage(corr)
                nova_core._teach_store_example(pending, corr_store)
                session.clear_pending_correction_target()
                nova_core.behavior_record_event("correction_applied")
                reply = "Understood. I corrected that and will use your version going forward."
                _append_session_turn(session_id, "assistant", reply)
                return _finalize_http_reply(reply, planner_decision="deterministic", grounded=True, intent="correction_apply")

        if nova_core._is_negative_feedback(text):
            last_assistant = ""
            for role, txt in reversed(turns[:-1]):
                if role == "assistant":
                    last_assistant = txt
                    break
            if last_assistant:
                corr = nova_core._extract_authoritative_correction_text(text)
                if corr:
                    nova_core.action_ledger_add_step(ledger, "correction_feedback", "learned")
                    corr_store = nova_core._normalize_correction_for_storage(corr)
                    nova_core._teach_store_example(last_assistant, corr_store)
                    nova_core.behavior_record_event("correction_learned")
                    reply = "You're right. I saved your correction and will use it next time."
                else:
                    session.set_pending_correction_target(last_assistant)
                    nova_core.action_ledger_add_step(ledger, "correction_feedback", "pending")
                    reply = "You're right. Give me the exact corrected answer and I will learn it now."
                _append_session_turn(session_id, "assistant", reply)
                return _finalize_http_reply(reply, planner_decision="deterministic", grounded=True, intent="correction_feedback")

        if nova_core._is_web_research_override_request(text):
            session.set_prefer_web_for_data_queries(True)
            nova_core.action_ledger_add_step(ledger, "routing_override", "enabled")
            reply = "Understood. For this session, I will prefer web research for PEIMS and similar data-domain questions instead of a database route."
            _append_session_turn(session_id, "assistant", reply)
            return _finalize_http_reply(reply, planner_decision="deterministic", grounded=True, intent="routing_override")

        # Learn explicit user corrections as structured facts before routing.
        learned, learned_msg = nova_core.learn_from_user_correction(text)
        if learned:
            nova_core.behavior_record_event("correction_learned")
            nova_core.action_ledger_add_step(ledger, "correction_learning", "stored")
            reply = nova_core._ensure_reply(learned_msg)
            _append_session_turn(session_id, "assistant", reply)
            return _finalize_http_reply(reply, planner_decision="deterministic", grounded=True, intent="correction_learned")

        try:
            identity_learned, identity_msg = nova_core._learn_self_identity_binding(text)
            if identity_learned:
                nova_core.action_ledger_add_step(ledger, "identity_binding", "stored")
                reply = nova_core._ensure_reply(identity_msg)
                _append_session_turn(session_id, "assistant", reply)
                return _finalize_http_reply(reply, planner_decision="deterministic", grounded=True, intent="identity_binding")
        except Exception:
            pass

        general_rule = nova_core.TURN_SUPERVISOR.evaluate_rules(
            text,
            manager=session,
            turns=turns,
            phase="handle",
            entry_point="http",
        )
        handled_rule, rule_reply, rule_state = nova_core._execute_registered_supervisor_rule(
            general_rule,
            text,
            conversation_state,
            turns=turns,
            input_source="typed",
            allowed_actions={"name_origin_store", "self_location"},
        )
        if handled_rule:
            session.apply_state_update(rule_state, fallback_state=conversation_state)
            if bool(general_rule.get("continuation")):
                session.mark_continuation_used()
            nova_core.action_ledger_add_step(
                ledger,
                str(general_rule.get("ledger_stage") or "registered_rule"),
                "matched",
                rule=str(general_rule.get("rule_name") or "registered_rule"),
            )
            reply = nova_core._ensure_reply(rule_reply)
            _append_session_turn(session_id, "assistant", reply)
            return _finalize_http_reply(
                reply,
                planner_decision="deterministic",
                grounded=bool(general_rule.get("grounded", True)),
                intent=str(general_rule.get("intent") or "deterministic"),
            )

        learned_profile, learned_profile_msg = _learn_contextual_developer_facts(turns, text)
        if learned_profile:
            session.apply_state_update(
                nova_core._infer_profile_conversation_state(text)
                or nova_core._make_conversation_state("identity_profile", subject="developer")
            )
            nova_core.action_ledger_add_step(ledger, "developer_profile", "stored")
            reply = nova_core._ensure_reply(learned_profile_msg)
            _append_session_turn(session_id, "assistant", reply)
            return _finalize_http_reply(reply, planner_decision="deterministic", grounded=True, intent="developer_profile_store")

        try:
            learned_self, learned_self_msg = nova_core._learn_contextual_self_facts(text, input_source="typed")
            if learned_self:
                nova_core.action_ledger_add_step(ledger, "self_profile", "stored")
                reply = nova_core._ensure_reply(learned_self_msg)
                _append_session_turn(session_id, "assistant", reply)
                return _finalize_http_reply(reply, planner_decision="deterministic", grounded=True, intent="self_profile_store")
        except Exception:
            pass

        memory_teach = _extract_memory_teach_text(text)
        if memory_teach and nova_core.mem_enabled():
            nova_core.action_ledger_add_step(ledger, "declarative_memory", "stored")
            nova_core.mem_add("fact", "typed", memory_teach)
            reply = "Yes. I stored that for future context."
            _append_session_turn(session_id, "assistant", reply)
            return _finalize_http_reply(reply, planner_decision="deterministic", grounded=True, intent="memory_store")

        try:
            location_ack = nova_core._store_location_fact_reply(
                text,
                input_source="typed",
                pending_action=session.pending_action,
            )
            if location_ack:
                nova_core.action_ledger_add_step(ledger, "location_memory", "stored")
                reply = location_ack
                _append_session_turn(session_id, "assistant", reply)
                return _finalize_http_reply(reply, planner_decision="deterministic", grounded=True, intent="location_store")
        except Exception:
            pass

        declarative_ack = nova_core._store_declarative_fact_reply(text, input_source="typed")
        if declarative_ack:
            nova_core.action_ledger_add_step(ledger, "declarative_memory", "stored")
            reply = declarative_ack
            _append_session_turn(session_id, "assistant", reply)
            return _finalize_http_reply(reply, planner_decision="deterministic", grounded=True, intent="declarative_store")

        routed_text = text
        try:
            turn_direction = nova_core._determine_turn_direction(turns, text)
            routed_text = str(turn_direction.get("effective_query") or text)
            nova_core.action_ledger_add_step(
                ledger,
                "direction_analysis",
                str(turn_direction.get("primary") or "general_chat"),
                str(turn_direction.get("analysis_reason") or "")[:120],
                effective_query=routed_text[:180],
                identity_focused=bool(turn_direction.get("identity_focused")),
                bypass_pattern_routes=bool(turn_direction.get("bypass_pattern_routes")),
            )
        except Exception:
            routed_text = text

        try:
            handled_followup, followup_msg, next_state = nova_core._consume_conversation_followup(
                conversation_state,
                routed_text,
                input_source="typed",
                turns=turns,
            )
            if handled_followup:
                session.mark_continuation_used()
                if isinstance(next_state, dict) and str(next_state.get("kind") or "").strip() == "retrieval":
                    session.set_retrieval_state(next_state)
                else:
                    session.apply_state_update(next_state)
                nova_core.action_ledger_add_step(
                    ledger,
                    "conversation_followup",
                    "used",
                    active_subject=nova_core._conversation_active_subject(conversation_state),
                )
                reply = nova_core._ensure_reply(followup_msg)
                _append_session_turn(session_id, "assistant", reply)
                return _finalize_http_reply(reply, planner_decision="conversation_followup", grounded=True, intent="conversation_followup")
            conversation_state = next_state if isinstance(next_state, dict) else conversation_state
            session.apply_state_update(conversation_state)
        except Exception:
            pass

        try:
            developer_guess, next_state = nova_core._developer_work_guess_turn(routed_text)
            if developer_guess:
                session.apply_state_update(next_state)
                nova_core.action_ledger_add_step(ledger, "developer_role_guess", "matched")
                reply = nova_core._ensure_reply(developer_guess)
                _append_session_turn(session_id, "assistant", reply)
                return _finalize_http_reply(reply, planner_decision="deterministic", grounded=True, intent="developer_role_guess")
        except Exception:
            pass

        reply, next_state = nova_core._developer_location_turn(
            routed_text,
            state=conversation_state,
            turns=turns,
        )
        if reply:
            session.apply_state_update(next_state)
            nova_core.action_ledger_add_step(ledger, "developer_location", "matched")
            _append_session_turn(session_id, "assistant", reply)
            return _finalize_http_reply(reply, planner_decision="deterministic", grounded=True, intent="developer_location")

        reply, meta = _generate_chat_reply(
            turns,
            routed_text,
            ledger_record=ledger,
            pending_action=session.pending_action,
            prefer_web_for_data_queries=session.prefer_web_for_data_queries,
        )
        planner_decision = str(meta.get("planner_decision") or "deterministic")
        tool = str(meta.get("tool") or "")
        tool_args = meta.get("tool_args") if isinstance(meta.get("tool_args"), dict) else {}
        tool_result = str(meta.get("tool_result") or "")
        grounded = meta.get("grounded") if isinstance(meta.get("grounded"), bool) else None
        pending_next = meta.get("pending_action")
        session.set_pending_action(pending_next if isinstance(pending_next, dict) and pending_next else None)

        if planner_decision in {"command", "run_tool", "grounded_lookup"}:
            nova_core.behavior_record_event("tool_route")
        elif planner_decision == "llm_fallback":
            nova_core.behavior_record_event("llm_fallback")

        next_state = nova_core._infer_post_reply_conversation_state(
            routed_text,
            planner_decision=planner_decision,
            tool=tool,
            tool_args=tool_args,
            tool_result=tool_result,
            turns=turns,
            fallback_state=conversation_state,
        )
        if isinstance(next_state, dict) and str(next_state.get("kind") or "").strip() == "retrieval":
            session.set_retrieval_state(next_state)
        else:
            session.apply_state_update(next_state)

        _append_session_turn(session_id, "assistant", reply)
        return _finalize_http_reply(
            reply,
            planner_decision=planner_decision,
            tool=tool,
            tool_args=tool_args,
            tool_result=tool_result,
            grounded=grounded,
        )
    finally:
        nova_core.set_active_user(previous_user)


def resume_last_pending_turn(session_id: str, user_id: str = "") -> dict:
    previous_user = nova_core.get_active_user()
    nova_core.set_active_user(user_id or previous_user)
    try:
        sid = (session_id or "").strip()
        if not sid:
            return {"ok": False, "error": "session_id_required"}

        last = _get_last_session_turn(sid)
        if not last:
            return {"ok": True, "resumed": False, "reason": "no_turns"}

        role, text = last
        if role != "user":
            return {"ok": True, "resumed": False, "reason": "no_pending_user_turn"}

        turns = _get_session_turns(sid)
        reply, _meta = _generate_chat_reply(turns, text)
        _append_session_turn(sid, "assistant", reply)
        return {"ok": True, "resumed": True, "session_id": sid, "reply": reply}
    finally:
        nova_core.set_active_user(previous_user)


class NovaHttpHandler(BaseHTTPRequestHandler):
    server_version = "NovaHTTP/0.1"

    def do_GET(self) -> None:
        path, qs = _parse_request_path(self.path)

        if path == "/":
            _text_response(self, 200, INDEX_HTML)
            return

        if path == "/static/control.css":
            _file_response(self, 200, CONTROL_CSS_PATH, "text/css; charset=utf-8")
            return

        if path == "/static/control.js":
            _file_response(self, 200, CONTROL_JS_PATH, "application/javascript; charset=utf-8")
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
                "chat_login_enabled": bool(_chat_login_enabled()),
            }
            _json_response(self, 200, payload)
            return

        if path == "/api/chat/history":
            ok_chat, chat_user = _chat_login_auth(self)
            if not ok_chat:
                _json_response(self, 403, {"ok": False, "error": chat_user})
                return
            sid = str((qs.get("session_id") or [""])[0]).strip()
            user_id = _normalize_user_id(chat_user) or _request_user_id(self, qs)
            ok_owner, reason_owner = _assert_session_owner(sid, user_id, allow_bind=False)
            if not ok_owner:
                _json_response(self, 403, {"ok": False, "error": reason_owner, "session_id": sid})
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

        if path == "/api/control/test-sessions":
            ok, reason = _control_auth(self, qs)
            if not ok:
                _json_response(self, 403, {"ok": False, "error": reason})
                return
            _json_response(self, 200, {"ok": True, "reports": _test_session_report_summaries(24), "definitions": _available_test_session_definitions(80)})
            return

        _json_response(self, 404, {"ok": False, "error": "not_found"})

    def do_POST(self) -> None:
        path, qs = _parse_request_path(self.path)

        if path not in {"/api/chat", "/api/chat/resume", "/api/chat/login", "/api/chat/logout", "/api/control/action", "/api/control/login", "/api/control/logout"}:
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

        if path == "/api/chat/login":
            if not _chat_login_enabled():
                _json_response(self, 400, {"ok": False, "error": "chat_login_disabled"})
                return
            users = _chat_users()
            username = _normalize_user_id(str(payload.get("username") or ""))
            pwd = str(payload.get("password") or "")
            expected = users.get(username, "")
            if username and expected and _chat_password_matches(expected, pwd):
                sid = _new_chat_session(username)
                body = json.dumps({"ok": True, "message": "login_ok", "user_id": username}, ensure_ascii=True).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("Set-Cookie", f"nova_chat_session={sid}; Path=/; HttpOnly; SameSite=Strict")
                self.end_headers()
                self.wfile.write(body)
                _record_http_response(200)
                return
            _json_response(self, 403, {"ok": False, "error": "invalid_credentials"})
            return

        if path == "/api/chat/logout":
            _clear_chat_session(self)
            body = json.dumps({"ok": True, "message": "logout_ok"}, ensure_ascii=True).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Set-Cookie", "nova_chat_session=; Path=/; Max-Age=0; HttpOnly; SameSite=Strict")
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

        if path == "/api/chat/resume":
            ok_chat, chat_user = _chat_login_auth(self)
            if not ok_chat:
                _json_response(self, 403, {"ok": False, "error": chat_user})
                return
            sid = str(payload.get("session_id") or "").strip()
            user_id = _normalize_user_id(chat_user) or _request_user_id(self, qs, payload)
            ok_owner, reason_owner = _assert_session_owner(sid, user_id, allow_bind=False)
            if not ok_owner:
                _json_response(self, 403, {"ok": False, "error": reason_owner, "session_id": sid})
                return
            out = resume_last_pending_turn(sid, user_id=user_id)
            code = 200 if out.get("ok") else 400
            _json_response(self, code, out)
            return

        ok_chat, chat_user = _chat_login_auth(self)
        if not ok_chat:
            _json_response(self, 403, {"ok": False, "error": chat_user})
            return

        message = str(payload.get("message") or "").strip()
        session_id = str(payload.get("session_id") or "").strip()
        user_id = _normalize_user_id(chat_user) or _request_user_id(self, qs, payload)
        if not session_id:
            session_id = secrets.token_hex(8)

        if not message:
            _json_response(self, 400, {"ok": False, "error": "message_required", "session_id": session_id})
            return

        ok_owner, reason_owner = _assert_session_owner(session_id, user_id, allow_bind=True)
        if not ok_owner:
            _json_response(self, 403, {"ok": False, "error": reason_owner, "session_id": session_id})
            return

        try:
            reply = process_chat(session_id, message, user_id=user_id)
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
    .head-right { display: flex; align-items: center; gap: 10px; }
    .btn-mini { padding: 6px 10px; font-size: 12px; }
    .btn-mini.alt { background: linear-gradient(135deg, #846540, #a47d4f); }
    .btn-mini.muted { background: linear-gradient(135deg, #8d8a84, #6d6a65); }
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
                <div class=\"title\">NYO System Interface</div>
                <div class=\"head-right\">
                    <div id=\"status\" class=\"status\">Checking health...</div>
                    <button id="btnToggleAudio" type="button" class="btn-mini alt">Voice Off</button>
                    <button id="btnMic" type="button" class="btn-mini muted">Mic Unavailable</button>
                    <button id=\"btnNewSession\" type=\"button\" class=\"btn-mini\">New Session</button>
                </div>
            </div>
      <div id=\"chat\"></div>
      <form id=\"f\">
        <input id=\"m\" placeholder=\"Type a message for NYO System...\" autocomplete=\"off\" />
        <button type=\"submit\">Send</button>
      </form>
            <div class=\"hint\">Tip: start server with <code>--host 0.0.0.0</code> to test from another device on your LAN. <a href=\"/control\">Open NYO Control</a>.</div>
    </div>
  </div>
<script>
  const chat = document.getElementById('chat');
  const form = document.getElementById('f');
  const input = document.getElementById('m');
    const statusEl = document.getElementById('status');
        const btnToggleAudio = document.getElementById('btnToggleAudio');
        const btnMic = document.getElementById('btnMic');
    const btnNewSession = document.getElementById('btnNewSession');
    const qs = new URLSearchParams(window.location.search || '');
        const SpeechRecognitionCtor = window.SpeechRecognition || window.webkitSpeechRecognition || null;
    const sidParam = (qs.get('sid') || '').trim();
    const uidParam = (qs.get('uid') || '').trim();
    const makeUserId = () => {
        if (window.crypto && typeof window.crypto.randomUUID === 'function') {
            return 'web-' + window.crypto.randomUUID().replace(/-/g, '').slice(0, 24);
        }
        return 'web-' + Math.random().toString(16).slice(2) + Date.now().toString(16);
    };
    let userId = uidParam || localStorage.getItem('nova_user_id') || makeUserId();
    localStorage.setItem('nova_user_id', userId);
    let chatLoginEnabled = false;
    let sessionId = sidParam || localStorage.getItem('nova_session_id') || '';
    let voiceOutputEnabled = localStorage.getItem('nova_voice_output') === 'on';
    let recognition = null;
    let recognitionActive = false;
    if (sidParam) {
        localStorage.setItem('nova_session_id', sessionId);
    }
        let historyLoaded = false;
        let pendingResumeNeeded = false;

    function syncAudioButton() {
        if (!btnToggleAudio) return;
        btnToggleAudio.textContent = voiceOutputEnabled ? 'Voice On' : 'Voice Off';
        btnToggleAudio.classList.toggle('alt', voiceOutputEnabled);
        btnToggleAudio.classList.toggle('muted', !voiceOutputEnabled);
    }

    function syncMicButton() {
        if (!btnMic) return;
        if (!SpeechRecognitionCtor) {
            btnMic.textContent = 'Mic Unavailable';
            btnMic.disabled = true;
            return;
        }
        btnMic.disabled = false;
        btnMic.textContent = recognitionActive ? 'Listening...' : 'Mic Ready';
        btnMic.classList.toggle('alt', recognitionActive);
        btnMic.classList.toggle('muted', !recognitionActive);
    }

    function speakAssistant(text) {
        if (!voiceOutputEnabled || !window.speechSynthesis) return;
        const spoken = String(text || '').trim();
        if (!spoken) return;
        try {
            window.speechSynthesis.cancel();
            const utterance = new SpeechSynthesisUtterance(spoken);
            utterance.rate = 1.0;
            utterance.pitch = 1.0;
            window.speechSynthesis.speak(utterance);
        } catch (_) {
            // Keep chat usable if browser speech APIs fail.
        }
    }

  function add(kind, text) {
    const d = document.createElement('div');
    d.className = 'msg ' + kind;
    d.textContent = text;
    chat.appendChild(d);
    chat.scrollTop = chat.scrollHeight;
    if (kind === 'a') {
        speakAssistant(text);
    }
  }

    async function sendMessage(message) {
        if (!message) return;
        add('u', message);
        try {
            const r = await chatFetch('/api/chat', {
                method: 'POST',
                headers: {'Content-Type': 'application/json', 'X-Nova-User-Id': userId},
                body: JSON.stringify({message, session_id: sessionId, user_id: userId})
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
    }

    function initSpeechRecognition() {
        if (!SpeechRecognitionCtor || recognition) return;
        recognition = new SpeechRecognitionCtor();
        recognition.lang = 'en-US';
        recognition.interimResults = false;
        recognition.maxAlternatives = 1;
        recognition.onstart = () => {
            recognitionActive = true;
            syncMicButton();
        };
        recognition.onend = () => {
            recognitionActive = false;
            syncMicButton();
        };
        recognition.onerror = () => {
            recognitionActive = false;
            syncMicButton();
        };
        recognition.onresult = (event) => {
            const transcript = String(event.results?.[0]?.[0]?.transcript || '').trim();
            if (!transcript) return;
            input.value = transcript;
            if (typeof form.requestSubmit === 'function') {
                form.requestSubmit();
            } else {
                form.dispatchEvent(new Event('submit', {cancelable: true}));
            }
        };
    }

    async function ensureChatLogin(forcePrompt = false) {
        if (!chatLoginEnabled && !forcePrompt) return true;
        let username = (localStorage.getItem('nova_chat_user') || userId || '').trim();
        if (!username || forcePrompt) {
            username = (window.prompt('NYO username', username || userId || '') || '').trim();
        }
        if (!username) return false;
        const password = window.prompt('NYO password', '');
        if (password === null) return false;
        try {
            const r = await fetch('/api/chat/login', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({username, password})
            });
            const j = await r.json();
            if (!r.ok || !j.ok) throw new Error(j.error || 'login_failed');
            userId = String(j.user_id || username).trim() || username;
            localStorage.setItem('nova_chat_user', userId);
            localStorage.setItem('nova_user_id', userId);
            return true;
        } catch (err) {
            add('a', 'Login failed: ' + err.message);
            return false;
        }
    }

    async function chatFetch(url, options = {}) {
        const headers = Object.assign({}, options.headers || {});
        if (userId) headers['X-Nova-User-Id'] = userId;
        let response = await fetch(url, Object.assign({}, options, {headers}));
        if (response.status !== 403) return response;

        let payload = null;
        try {
            payload = await response.clone().json();
        } catch (_) {
            return response;
        }
        if (!payload || payload.error !== 'chat_login_required') return response;

        const ok = await ensureChatLogin(true);
        if (!ok) return response;

        const retryHeaders = Object.assign({}, options.headers || {});
        if (userId) retryHeaders['X-Nova-User-Id'] = userId;
        return fetch(url, Object.assign({}, options, {headers: retryHeaders}));
    }

    async function loadHistory() {
        if (!sessionId) return;
        try {
            const r = await chatFetch('/api/chat/history?session_id=' + encodeURIComponent(sessionId) + '&user_id=' + encodeURIComponent(userId));
            const j = await r.json();
            if (!r.ok || !j.ok || !Array.isArray(j.turns)) return;
            if (j.turns.length === 0) return;

            j.turns.forEach(t => {
                if (!t || !t.role || !t.text) return;
                add(t.role === 'user' ? 'u' : 'a', String(t.text));
            });
                        const last = j.turns[j.turns.length - 1];
                        pendingResumeNeeded = Boolean(last && String(last.role || '').toLowerCase() === 'user');
            historyLoaded = true;
        } catch (_) {
            // Keep startup resilient; chat can still operate without history.
        }
    }

    async function resumePendingTurn() {
        if (!sessionId || !pendingResumeNeeded) return;
        try {
            const r = await chatFetch('/api/chat/resume', {
                method: 'POST',
                headers: {'Content-Type': 'application/json', 'X-Nova-User-Id': userId},
                body: JSON.stringify({session_id: sessionId, user_id: userId})
            });
            const j = await r.json();
            if (r.ok && j.ok && j.resumed && j.reply) {
                add('a', String(j.reply));
            }
        } catch (_) {
            // Keep UI responsive even if resume fails.
        } finally {
            pendingResumeNeeded = false;
        }
    }

  async function health() {
    try {
      const r = await fetch('/api/health');
      const j = await r.json();
            chatLoginEnabled = Boolean(j.chat_login_enabled);
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
    await sendMessage(message);
  });

    if (btnToggleAudio) {
        syncAudioButton();
        btnToggleAudio.addEventListener('click', () => {
            voiceOutputEnabled = !voiceOutputEnabled;
            localStorage.setItem('nova_voice_output', voiceOutputEnabled ? 'on' : 'off');
            if (!voiceOutputEnabled && window.speechSynthesis) {
                window.speechSynthesis.cancel();
            }
            syncAudioButton();
            add('a', voiceOutputEnabled ? 'Browser voice output enabled.' : 'Browser voice output disabled.');
        });
    }

    initSpeechRecognition();
    syncMicButton();
    if (btnMic && SpeechRecognitionCtor) {
        btnMic.addEventListener('click', () => {
            if (!recognition) {
                initSpeechRecognition();
            }
            if (!recognition) return;
            if (recognitionActive) {
                recognition.stop();
                return;
            }
            try {
                recognition.start();
            } catch (_) {
                recognitionActive = false;
                syncMicButton();
            }
        });
    }

    if (btnNewSession) {
        btnNewSession.addEventListener('click', () => {
            sessionId = '';
            pendingResumeNeeded = false;
            historyLoaded = false;
            localStorage.removeItem('nova_session_id');
            chat.innerHTML = '';
            add('a', 'Started a new chat session. Context was reset.');
            input.focus();
        });
    }

    (async () => {
        await loadHistory();
        await resumePendingTurn();
        if (!historyLoaded) {
            add('a', 'NYO System interface ready. Ask Nova anything.');
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
    <title>NYO System Control Login</title>
    <link href=\"https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css\" rel=\"stylesheet\" integrity=\"sha384-QWTKZyjpPEjISv5WaRU9OFeRpok6YctnYmDr5pNlyT2bRjXh0JMhjY6hW+ALEwIH\" crossorigin=\"anonymous\">
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
        .login-card {
            width: min(480px, 92vw);
            border: 1px solid var(--line);
            border-radius: 14px;
            background: var(--panel);
            box-shadow: 0 14px 30px rgba(0,0,0,0.08);
        }
        h1 { margin: 0 0 8px; font-size: 20px; }
        p { margin: 0 0 12px; color: #5f5a52; }
        .err { color: var(--danger); font-size: 13px; min-height: 18px; margin-top: 10px; }
        .btn-nova {
            color: #fff;
            font-weight: 700;
            border: 0;
            background: linear-gradient(135deg, var(--accent), #0a986f);
        }
    </style>
</head>
<body>
    <div class=\"login-card p-4\">
        <h1>NYO System Control Login</h1>
        <p>Sign in to access the branded operator console for the NYO runtime.</p>
        <form id=\"f\" class=\"d-grid gap-2\">
            <label for=\"u\" class=\"form-label mb-0\">Username</label>
            <input id=\"u\" class=\"form-control\" autocomplete=\"username\" />
            <label for=\"p\" class=\"form-label mb-0 mt-2\">Password</label>
            <input id=\"p\" class=\"form-control\" type=\"password\" autocomplete=\"current-password\" />
            <button type=\"submit\" class=\"btn btn-nova mt-3\">Sign In</button>
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


_LEGACY_CONTROL_HTML = """<!doctype html>
<html lang=\"en\">
<head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <title>Nova Command Center</title>
    <link href=\"https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css\" rel=\"stylesheet\" integrity=\"sha384-QWTKZyjpPEjISv5WaRU9OFeRpok6YctnYmDr5pNlyT2bRjXh0JMhjY6hW+ALEwIH\" crossorigin=\"anonymous\">
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
        .wrap { max-width: 1240px; margin: 0 auto; padding: 20px 14px 30px; }
        .bar {
            display: flex; gap: 10px; align-items: center; justify-content: space-between;
            margin-bottom: 12px;
            background: rgba(255,255,255,0.65);
            border: 1px solid var(--line);
            padding: 10px 12px;
            border-radius: 14px;
            backdrop-filter: blur(6px);
        }
        .tabs-wrap {
            background: rgba(255,255,255,0.58);
            border: 1px solid var(--line);
            border-radius: 12px;
            padding: 8px 10px 0;
            margin-bottom: 12px;
        }
        .nav-tabs .nav-link {
            color: #2d3a33;
            font-weight: 600;
            cursor: pointer;
            pointer-events: auto;
        }
        .nav-tabs .nav-link.active {
            color: #0a7a4a;
            border-color: var(--line) var(--line) #fff;
            background: #fff;
        }
        .health-badge {
            border-radius: 999px;
            padding: 4px 10px;
            font-size: 12px;
            font-weight: 700;
            border: 1px solid var(--line);
            background: #f6f5ef;
            color: #3f3a34;
        }
        .feedback-strip {
            border: 1px solid var(--line);
            border-radius: 10px;
            padding: 8px 10px;
            margin: 0 0 12px;
            font-size: 13px;
            background: rgba(255,255,255,0.75);
        }
        .feedback-strip.good { color: var(--good); }
        .feedback-strip.warn { color: var(--warn); }
        .feedback-strip.danger { color: var(--danger); }
        body.js-ready .pane-hidden { display: none !important; }
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
        .btn-nova { color: #fff; border: 0; font-weight: 600; background: linear-gradient(135deg, var(--accent), #0f9f61); }
        .btn-alt { color: #fff; border: 0; font-weight: 600; background: linear-gradient(135deg, #6f4f3e, #9d6a4f); }
        .btn-warn { color: #fff; border: 0; font-weight: 600; background: linear-gradient(135deg, #9a5316, #cf7e24); }
        .btn-danger-nova { color: #fff; border: 0; font-weight: 600; background: linear-gradient(135deg, #8a1d15, #bf2c1f); }
        button.btn {
            position: relative;
            z-index: 2;
            pointer-events: auto !important;
            cursor: pointer;
        }
        .form-control, .form-select {
            border: 1px solid #bfc4b7;
            background: #fff;
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
        <nav class=\"bar navbar\">
            <div class=\"title\">Nova Command Center</div>
            <div class=\"row\">
                <span id=\"healthBadge\" class=\"health-badge\">Health --</span>
                <a href=\"/\">Chat UI</a>
                <button id=\"btnRefresh\" class=\"btn btn-sm btn-nova\">Refresh</button>
                <button id=\"btnLogout\" class=\"btn btn-sm btn-danger-nova\">Logout</button>
            </div>
        </nav>

        <div id=\"feedbackBar\" class=\"feedback-strip muted\">Control UI ready.</div>
        <div id=\"runtimeNoteBar\" class=\"feedback-strip muted\">Runtime note not loaded yet.</div>

        <div class=\"tabs-wrap\">
            <ul class=\"nav nav-tabs\" id=\"controlTabs\">
                <li class=\"nav-item\"><button class=\"nav-link active\" data-pane-target=\"overview\" type=\"button\">Overview</button></li>
                <li class=\"nav-item\"><button class=\"nav-link\" data-pane-target=\"ops\" type=\"button\">Operations</button></li>
                <li class=\"nav-item\"><button class=\"nav-link\" data-pane-target=\"sessions\" type=\"button\">Sessions</button></li>
                <li class=\"nav-item\"><button class=\"nav-link\" data-pane-target=\"logs\" type=\"button\">Logs</button></li>
            </ul>
        </div>

        <div class=\"grid\">
            <section class=\"card pane pane-overview\">
                <div class=\"head\">Runtime Health</div>
                <div class=\"body\">
                    <div class="kv" id="statusKv"></div>
                </div>
            </section>

            <section class="card pane pane-sessions pane-hidden">
                <div class="head">Session Manager</div>
                <div class="body">
                    <div class="row" style="margin-bottom:8px;">
                        <select id="sessionSelect" class="form-select"></select>
                    </div>
                    <div class="row" style="margin-bottom:8px;">
                        <button id="btnSessionsRefresh" class="btn btn-sm btn-alt">Refresh Sessions</button>
                        <select id="searchProvider" class="form-select">
                            <option value="html">search provider html</option>
                            <option value="searxng">search provider searxng</option>
                        </select>
                        <button id="btnSearchProvider" class="btn btn-sm btn-nova">Apply Provider</button>
                        <button id="btnSearchToggle" class="btn btn-sm btn-alt">Toggle Provider</button>
                        <button id="btnSessionOpen" class="btn btn-sm btn-nova">Open In Chat</button>
                        <button id="btnSessionCopy" class="btn btn-sm btn-warn">Copy Session ID</button>
                        <button id="btnSessionDelete" class="btn btn-sm btn-danger-nova">Delete Session</button>
                    </div>
                    <pre id="sessionBox" class="mono">No session selected.</pre>
                </div>
            </section>

            <section class=\"card pane pane-overview\">
                <div class=\"head\">Control Access</div>
                <div class=\"body\">
                    <label class=\"muted\" for=\"key\">Control key (optional if local-only mode):</label>
                    <input id=\"key\" class=\"form-control\" type=\"password\" placeholder=\"NOVA_CONTROL_TOKEN\" />
                </div>
            </section>

            <section class=\"card pane pane-ops pane-hidden\">
                <div class=\"head\">Guard Control</div>
                <div class=\"body\">
                    <div class=\"row\" style=\"margin-bottom:8px;\">
                        <button id=\"btnGuardStatus\" class=\"btn btn-sm btn-alt\">Guard Status</button>
                        <button id=\"btnGuardStart\" class=\"btn btn-sm btn-nova\">Start Guard</button>
                        <button id=\"btnGuardStop\" class=\"btn btn-sm btn-danger-nova\">Stop Guard</button>
                    </div>
                    <pre id=\"guardBox\" class=\"mono\">No guard data yet.</pre>
                </div>
            </section>

            <section class=\"card pane pane-ops pane-hidden\">
                <div class=\"head\">Policy Controls</div>
                <div class=\"body\">
                    <div class=\"row\" style=\"margin-bottom:8px;\">
                        <input id=\"domainInput\" class=\"form-control\" placeholder=\"example.com\" />
                        <button id=\"btnAllow\" class=\"btn btn-sm btn-nova\">Allow Domain</button>
                        <button id=\"btnRemove\" class=\"btn btn-sm btn-alt\">Remove Domain</button>
                    </div>
                    <div class=\"row\">
                        <select id=\"webMode\" class=\"form-select\">
                            <option value=\"normal\">web mode normal</option>
                            <option value=\"max\">web mode max</option>
                        </select>
                        <button id=\"btnMode\" class=\"btn btn-sm btn-warn\">Apply Web Mode</button>
                        <button id=\"btnAudit\" class=\"btn btn-sm btn-alt\">Policy Audit</button>
                    </div>
                </div>
            </section>

            <section class=\"card pane pane-ops pane-hidden\">
                <div class=\"head\">Memory Governance</div>
                <div class=\"body\">
                    <div class=\"row\" style=\"margin-bottom:8px;\">
                        <select id=\"memoryScope\" class=\"form-select\">
                            <option value=\"private\">memory scope private</option>
                            <option value=\"hybrid\">memory scope hybrid</option>
                            <option value=\"shared\">memory scope shared</option>
                        </select>
                        <button id=\"btnMemoryScope\" class=\"btn btn-sm btn-nova\">Apply Memory Scope</button>
                    </div>
                    <pre id=\"memoryScopeBox\" class=\"mono\">Memory scope not loaded yet.</pre>
                </div>
            </section>

            <section class=\"card pane pane-ops pane-hidden\">
                <div class=\"head\">Chat Access</div>
                <div class=\"body\">
                    <div class=\"row\" style=\"margin-bottom:8px;\">
                        <select id=\"chatUserSelect\" class=\"form-select\"></select>
                        <input id=\"chatUserName\" class=\"form-control\" placeholder=\"username\" />
                        <input id=\"chatUserPass\" class=\"form-control\" type=\"password\" placeholder=\"new password\" />
                    </div>
                    <div class=\"row\" style=\"margin-bottom:8px;\">
                        <button id=\"btnChatUserUpsert\" class=\"btn btn-sm btn-nova\">Save Chat User</button>
                        <button id=\"btnChatUserDelete\" class=\"btn btn-sm btn-danger-nova\">Delete Chat User</button>
                        <button id=\"btnChatUserRefresh\" class=\"btn btn-sm btn-alt\">Refresh Chat Users</button>
                    </div>
                    <pre id=\"chatAuthBox\" class=\"mono\">Chat access not loaded yet.</pre>
                </div>
            </section>

            <section class=\"card pane pane-ops pane-hidden\">
                <div class=\"head\">Ops Actions</div>
                <div class=\"body\">
                    <div class=\"row\">
                        <button id=\"btnInspect\" class=\"btn btn-sm btn-warn\">Inspect Environment</button>
                        <button id=\"btnNovaStart\" class=\"btn btn-sm btn-nova\">Start Nova Core</button>
                        <button id=\"btnSelfCheck\" class=\"btn btn-sm btn-nova\">Run Self-Check</button>
                        <button id=\"btnExportCaps\" class=\"btn btn-sm btn-alt\">Export Capabilities</button>
                        <button id=\"btnExportLedger\" class=\"btn btn-sm btn-alt\">Export Ledger Summary</button>
                        <button id=\"btnExportBundle\" class=\"btn btn-sm btn-warn\">Export Diagnostics Bundle</button>
                        <button id=\"btnOut\" class=\"btn btn-sm btn-alt\">Tail HTTP OUT</button>
                        <button id=\"btnErr\" class=\"btn btn-sm btn-danger-nova\">Tail HTTP ERR</button>
                    </div>
                </div>
            </section>

            <section class=\"card span2 pane pane-overview\">
                <div class=\"head\">Policy Snapshot</div>
                <div class=\"body\">
                    <pre id=\"policyBox\" class=\"mono\">Loading...</pre>
                </div>
            </section>

            <section class=\"card span2 pane pane-overview\">
                <div class=\"head\">Telemetry</div>
                <div class=\"body\">
                    <canvas id=\"metricsCanvas\" width=\"1100\" height=\"220\"></canvas>
                    <div class=\"muted\" style=\"margin-top:8px;font-size:12px;\">Green: heartbeat age | Blue: requests/min | Red: errors/min</div>
                </div>
            </section>

            <section class=\"card span2 pane pane-logs pane-hidden\">
                <div class=\"head\">Action Output</div>
                <div class=\"body\">
                    <pre id=\"actionBox\" class=\"mono\">No actions yet.</pre>
                </div>
            </section>
        </div>
    </div>

<script>
    document.body.classList.add('js-ready');

    const keyInput = document.getElementById('key');
    const statusKv = document.getElementById('statusKv');
    const healthBadge = document.getElementById('healthBadge');
    const feedbackBar = document.getElementById('feedbackBar');
    const runtimeNoteBar = document.getElementById('runtimeNoteBar');
    const policyBox = document.getElementById('policyBox');
    const actionBox = document.getElementById('actionBox');
    const guardBox = document.getElementById('guardBox');
    const sessionSelect = document.getElementById('sessionSelect');
    const sessionBox = document.getElementById('sessionBox');
    const memoryScopeSelect = document.getElementById('memoryScope');
    const memoryScopeBox = document.getElementById('memoryScopeBox');
    const chatUserSelect = document.getElementById('chatUserSelect');
    const chatUserNameInput = document.getElementById('chatUserName');
    const chatUserPassInput = document.getElementById('chatUserPass');
    const chatAuthBox = document.getElementById('chatAuthBox');
    const metricsCanvas = document.getElementById('metricsCanvas');
    const ctx = metricsCanvas ? metricsCanvas.getContext('2d') : null;
    const tabButtons = Array.from(document.querySelectorAll('[data-pane-target]'));
    const allPanes = Array.from(document.querySelectorAll('.pane'));
    let sessionsCache = [];

    function setActivePane(name) {
        tabButtons.forEach((b) => {
            const on = (b.getAttribute('data-pane-target') || '') === name;
            b.classList.toggle('active', on);
        });
        allPanes.forEach((p) => {
            const show = p.classList.contains('pane-' + name);
            p.classList.toggle('pane-hidden', !show);
        });
    }

    tabButtons.forEach((b) => {
        b.addEventListener('click', () => {
            const target = (b.getAttribute('data-pane-target') || '').trim();
            if (target) setActivePane(target);
        });
    });

    if (keyInput) {
        keyInput.value = localStorage.getItem('nova_control_key') || '';
        keyInput.addEventListener('change', () => {
            localStorage.setItem('nova_control_key', keyInput.value.trim());
        });
    }

    function controlHeaders() {
        const k = keyInput ? keyInput.value.trim() : '';
        const headers = {'Content-Type': 'application/json'};
        if (k) headers['X-Nova-Control-Key'] = k;
        return headers;
    }

    function fmtStatusValue(k, v) {
        if (k === 'ollama_api_up' || k === 'web_enabled' || k === 'memory_enabled' || k === 'searxng_ok' || k === 'chat_login_enabled') {
            if (v === true) return `<span class=\"good\">true</span>`;
            if (v === false) return `<span class=\"danger\">false</span>`;
        }
        if (k === 'heartbeat_age_sec' && typeof v === 'number') {
            const cls = v <= 15 ? 'good' : (v <= 45 ? 'warn' : 'danger');
            return `<span class=\"${cls}\">${v}s</span>`;
        }
        return `<span class=\"mono\">${String(v)}</span>`;
    }

    function renderGovernance(policy, status) {
        const memory = policy && policy.memory && typeof policy.memory === 'object' ? policy.memory : {};
        const chatAuth = policy && policy.chat_auth && typeof policy.chat_auth === 'object' ? policy.chat_auth : {};
        const source = String(chatAuth.source || (status && status.chat_auth_source) || 'disabled');
        const users = Array.isArray(chatAuth.users) ? chatAuth.users : [];
        const count = Number(chatAuth.count || users.length || 0);
        const scope = String(memory.scope || (status && status.memory_scope) || 'private').trim().toLowerCase();

                'tool_events_total', 'tool_events_success_count', 'tool_events_failure_count', 'tool_events_denied_count',
                'tool_events_avg_latency_ms', 'tool_avg_latency_ms_by_tool', 'last_tool_name', 'last_tool_status', 'last_tool_error_summary'
        if (memoryScopeSelect && ['private', 'shared', 'hybrid'].includes(scope)) {
            memoryScopeSelect.value = scope;
        }
        if (memoryScopeBox) {
            memoryScopeBox.textContent = [
                `Current scope: ${scope}`,
                `Memory enabled: ${Boolean(memory.enabled)}`,
                `Mode: ${String(memory.mode || '')}`,
                `Top K: ${String(memory.top_k || '')}`,
            ].join('\\n');
        }

        if (chatUserSelect) {
            const prev = (chatUserSelect.value || '').trim();
            chatUserSelect.innerHTML = '';
            const first = document.createElement('option');
            first.value = '';
            first.textContent = users.length ? '(select chat user)' : '(no chat users)';
            chatUserSelect.appendChild(first);
            users.forEach((user) => {
                const opt = document.createElement('option');
                opt.value = user;
                opt.textContent = user;
                chatUserSelect.appendChild(opt);
            });
            if (prev && users.includes(prev)) {
                chatUserSelect.value = prev;
            }
        }
        if (chatAuthBox) {
            chatAuthBox.textContent = [
                `Login enabled: ${Boolean(chatAuth.enabled)}`,
                `Source: ${source}`,
                `Users: ${count}`,
                `Managed file: ${String(chatAuth.managed_path || '')}`,
                '',
                'Usernames:',
                users.length ? users.join('\\n') : '(none)',
            ].join('\\n');
        }
    }

    function setAction(text) {
        if (!actionBox) return;
        actionBox.textContent = text;
        actionBox.classList.remove('pulse');
        void actionBox.offsetWidth;
        actionBox.classList.add('pulse');
        const first = String(text || '').split('\\n')[0].trim() || 'Action complete.';
        setFeedback(first, /failed|error|denied|forbidden/i.test(first) ? 'danger' : 'good');
    }

    function setFeedback(text, level='muted') {
        if (!feedbackBar) return;
        feedbackBar.classList.remove('muted', 'good', 'warn', 'danger');
        const normalized = ['good', 'warn', 'danger', 'muted'].includes(level) ? level : 'muted';
        feedbackBar.classList.add(normalized);
        feedbackBar.textContent = text;
    }

    function bindClick(id, handler) {
        const el = document.getElementById(id);
        if (!el) {
            console.warn('Control UI missing element:', id);
            setFeedback(`Control UI warning: missing element ${id}`, 'warn');
            return;
        }
        // Force button semantics and bind one click pathway.
        if (el.tagName === 'BUTTON') {
            el.setAttribute('type', 'button');
            el.disabled = false;
        }
        const wrapped = (ev) => {
            try {
                if (ev && typeof ev.preventDefault === 'function') ev.preventDefault();
                setFeedback('Clicked ' + id + ' ...', 'muted');
                return handler(ev);
            } catch (err) {
                setFeedback('Handler error for ' + id + ': ' + (err && err.message ? err.message : String(err)), 'danger');
            }
        };
        el.addEventListener('click', wrapped);
    }

    function setHealthBadge(score, ratio, alerts) {
        const s = Number(score || 0);
        const a = Array.isArray(alerts) ? alerts : [];
        const pct = Math.max(0, Math.min(100, Math.round((Number(ratio || 0)) * 100)));
        let cls = 'warn';
        if (s >= 90 && a.length === 0) cls = 'good';
        else if (s < 70 || a.length > 0) cls = 'danger';
        if (!healthBadge) return;
        healthBadge.classList.remove('good', 'warn', 'danger');
        healthBadge.classList.add(cls);
        healthBadge.textContent = `Health ${s}/100 (${pct}%)`;
        healthBadge.title = a.length ? ('Alerts: ' + a.join('; ')) : 'No active alerts';
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
            const results = await Promise.allSettled([
                getJson('/api/control/status'),
                getJson('/api/control/policy'),
                getJson('/api/control/metrics'),
                getJson('/api/control/sessions')
            ]);

            const status = results[0].status === 'fulfilled' ? results[0].value : null;
            const policy = results[1].status === 'fulfilled' ? results[1].value : null;
            const metrics = results[2].status === 'fulfilled' ? results[2].value : null;
            const sess = results[3].status === 'fulfilled' ? results[3].value : null;

            const failed = results
                .map((r, i) => ({r, i}))
                .filter(x => x.r.status !== 'fulfilled')
                .map(x => ['status', 'policy', 'metrics', 'sessions'][x.i]);

            const keys = [
                'server_time', 'ollama_api_up', 'chat_model', 'memory_enabled', 'memory_scope', 'web_enabled',
                'memory_stats_ok', 'memory_entries_total', 'memory_by_user_count',
                'memory_events_ok', 'memory_events_total', 'memory_write_count', 'memory_recall_count',
                'memory_skipped_count', 'memory_events_avg_latency_ms', 'last_memory_action', 'last_memory_status',
                'chat_login_enabled', 'chat_auth_source', 'chat_users_count',
                'search_provider', 'search_api_endpoint', 'allow_domains_count', 'process_counting_mode',
                'heartbeat_age_sec', 'core_running', 'core_pid', 'core_heartbeat_age_sec',
                'active_http_sessions', 'requests_total', 'errors_total', 'searxng_ok', 'searxng_note'
            ];
            if (status) {
                if (statusKv) {
                    statusKv.innerHTML = keys.map(k => `<div class=\"muted\">${k}</div><div>${fmtStatusValue(k, status[k])}</div>`).join('');
                }
                if (runtimeNoteBar) {
                    runtimeNoteBar.textContent = String(status.runtime_process_note || '');
                }
                const providerSelect = document.getElementById('searchProvider');
                if (providerSelect && typeof status.search_provider === 'string') {
                    const sp = status.search_provider.trim().toLowerCase();
                    if (sp === 'html' || sp === 'searxng') {
                        providerSelect.value = sp;
                    }
                }
                setHealthBadge(status.health_score, status.self_check_pass_ratio, status.alerts || []);
                if (guardBox) {
                    guardBox.textContent = JSON.stringify(status.guard || {}, null, 2);
                }
            }
            if (policy) {
                if (policyBox) {
                    policyBox.textContent = JSON.stringify(policy, null, 2);
                }
                renderGovernance(policy, status);
            }
            if (metrics) {
                drawMetrics(metrics.points || []);
            }
            if (sess) {
                sessionsCache = Array.isArray(sess.sessions) ? sess.sessions : [];
                renderSessions();
            }
            if (!status && !policy && !metrics && !sess) {
                throw new Error('All control endpoints failed');
            }

            if (failed.length) {
                setFeedback('Partial refresh (' + failed.join(', ') + ' failed) at ' + new Date().toLocaleTimeString(), 'warn');
            } else {
                setFeedback('Live status refreshed at ' + new Date().toLocaleTimeString(), 'muted');
            }
        } catch (err) {
            setAction('Refresh failed: ' + err.message);
        }
    }

    function renderSessions() {
        const prev = (sessionSelect.value || '').trim();
        if (!sessionSelect || !sessionBox) return;
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
        if (!sessionBox) return;
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
        sessionBox.textContent = lines.join('\\n');
    }

    bindClick('btnRefresh', refresh);
    if (sessionSelect) {
        sessionSelect.addEventListener('change', renderSessionPreview);
    }

    bindClick('btnLogout', async () => {
        try {
            await fetch('/api/control/logout', {method: 'POST', headers: controlHeaders(), body: '{}'});
            window.location.href = '/control';
        } catch (err) {
            setAction('Logout failed: ' + err.message);
        }
    });

    bindClick('btnSessionsRefresh', async () => {
        try {
            const sess = await getJson('/api/control/sessions');
            sessionsCache = Array.isArray(sess.sessions) ? sess.sessions : [];
            renderSessions();
            setAction('Session list refreshed.');
        } catch (err) {
            setAction('Session refresh failed: ' + err.message);
        }
    });

    bindClick('btnSessionOpen', () => {
        const sid = (sessionSelect.value || '').trim();
        if (!sid) {
            setAction('Select a session first.');
            return;
        }
        window.open('/?sid=' + encodeURIComponent(sid), '_blank');
    });

    bindClick('btnSessionCopy', async () => {
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

    bindClick('btnSessionDelete', async () => {
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

    bindClick('btnGuardStatus', async () => {
        try {
            const j = await postAction('guard_status');
            guardBox.textContent = JSON.stringify(j.guard || {}, null, 2);
            setAction(j.message || 'guard_status done');
            await refresh();
        } catch (err) {
            setAction('Guard status failed: ' + err.message);
        }
    });

    bindClick('btnGuardStart', async () => {
        try {
            const j = await postAction('guard_start');
            guardBox.textContent = JSON.stringify(j.guard || {}, null, 2);
            setAction(j.message || 'guard_start done');
            await refresh();
        } catch (err) {
            setAction('Guard start failed: ' + err.message);
        }
    });

    bindClick('btnGuardStop', async () => {
        try {
            const j = await postAction('guard_stop');
            guardBox.textContent = JSON.stringify(j.guard || {}, null, 2);
            setAction(j.message || 'guard_stop done');
            await refresh();
        } catch (err) {
            setAction('Guard stop failed: ' + err.message);
        }
    });

    bindClick('btnAllow', async () => {
        try {
            const domain = (document.getElementById('domainInput').value || '').trim();
            const j = await postAction('policy_allow', {domain});
            setAction(j.message || 'policy_allow done');
            await refresh();
        } catch (err) {
            setAction('Allow failed: ' + err.message);
        }
    });

    bindClick('btnRemove', async () => {
        try {
            const domain = (document.getElementById('domainInput').value || '').trim();
            const j = await postAction('policy_remove', {domain});
            setAction(j.message || 'policy_remove done');
            await refresh();
        } catch (err) {
            setAction('Remove failed: ' + err.message);
        }
    });

    bindClick('btnMode', async () => {
        try {
            const mode = document.getElementById('webMode').value;
            const j = await postAction('web_mode', {mode});
            setAction(j.message || 'web_mode done');
            await refresh();
        } catch (err) {
            setAction('Web mode failed: ' + err.message);
        }
    });

    bindClick('btnMemoryScope', async () => {
        try {
            const scope = memoryScopeSelect ? memoryScopeSelect.value : 'private';
            const j = await postAction('memory_scope_set', {scope});
            setAction(j.message || 'memory_scope_set done');
            await refresh();
        } catch (err) {
            setAction('Memory scope update failed: ' + err.message);
        }
    });

    bindClick('btnSearchProvider', async () => {
        try {
            const provider = document.getElementById('searchProvider').value;
            const j = await postAction('search_provider', {provider});
            setAction(j.message || 'search_provider done');
            await refresh();
        } catch (err) {
            setAction('Search provider apply failed: ' + err.message);
        }
    });

    bindClick('btnSearchToggle', async () => {
        try {
            const j = await postAction('search_provider_toggle');
            setAction(j.message || 'search_provider_toggle done');
            await refresh();
        } catch (err) {
            setAction('Search provider toggle failed: ' + err.message);
        }
    });

    if (chatUserSelect && chatUserNameInput) {
        chatUserSelect.addEventListener('change', () => {
            const user = (chatUserSelect.value || '').trim();
            if (user) chatUserNameInput.value = user;
        });
    }

    bindClick('btnChatUserRefresh', async () => {
        try {
            await refresh();
            setAction('Chat user list refreshed.');
        } catch (err) {
            setAction('Chat user refresh failed: ' + err.message);
        }
    });

    bindClick('btnChatUserUpsert', async () => {
        try {
            const username = chatUserNameInput ? chatUserNameInput.value.trim() : '';
            const password = chatUserPassInput ? chatUserPassInput.value : '';
            const j = await postAction('chat_user_upsert', {username, password});
            if (chatUserPassInput) chatUserPassInput.value = '';
            setAction(j.message || 'chat_user_upsert done');
            await refresh();
        } catch (err) {
            setAction('Chat user save failed: ' + err.message);
        }
    });

    bindClick('btnChatUserDelete', async () => {
        try {
            const username = (chatUserNameInput && chatUserNameInput.value.trim()) || (chatUserSelect && chatUserSelect.value.trim()) || '';
            const j = await postAction('chat_user_delete', {username});
            if (chatUserNameInput) chatUserNameInput.value = '';
            if (chatUserPassInput) chatUserPassInput.value = '';
            setAction(j.message || 'chat_user_delete done');
            await refresh();
        } catch (err) {
            setAction('Chat user delete failed: ' + err.message);
        }
    });

    bindClick('btnAudit', async () => {
        try {
            const j = await postAction('policy_audit');
            setAction(j.text || j.message || 'policy_audit done');
        } catch (err) {
            setAction('Policy audit failed: ' + err.message);
        }
    });

    bindClick('btnInspect', async () => {
        try {
            const j = await postAction('inspect');
            setAction(j.report || j.message || 'inspect done');
        } catch (err) {
            setAction('Inspect failed: ' + err.message);
        }
    });

    bindClick('btnNovaStart', async () => {
        try {
            const j = await postAction('nova_start');
            const core = j.core || {};
            const pid = core.pid ? (' pid=' + core.pid) : '';
            const hb = Number.isFinite(Number(core.heartbeat_age_sec)) ? (' hb_age=' + Number(core.heartbeat_age_sec) + 's') : '';
            setAction((j.message || 'nova_start done') + (core.running ? ' (running)' : ' (starting)') + pid + hb);
            await refresh();
        } catch (err) {
            setAction('Start Nova failed: ' + err.message);
        }
    });

    bindClick('btnSelfCheck', async () => {
        try {
            const r = await fetch('/api/control/action', {
                method: 'POST',
                headers: controlHeaders(),
                body: JSON.stringify({action: 'self_check'})
            });
            const j = await r.json();
            const checks = Array.isArray(j.checks) ? j.checks : [];
            const lines = [j.summary || 'self_check completed'];
            checks.forEach((c) => {
                lines.push(`- ${c.name}: ${c.ok ? 'OK' : 'FAIL'}${c.detail ? ' (' + c.detail + ')' : ''}`);
            });
            if (!r.ok && !checks.length) {
                throw new Error(j.error || j.message || ('HTTP ' + r.status));
            }
            setAction(lines.join('\\n'));
            await refresh();
        } catch (err) {
            setAction('Self-check failed: ' + err.message);
        }
    });

    bindClick('btnExportCaps', async () => {
        try {
            const j = await postAction('export_capabilities');
            const caps = j.capabilities || {};
            const fileName = j.filename || 'capabilities_export.json';
            const blob = new Blob([JSON.stringify(caps, null, 2)], {type: 'application/json'});
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = fileName;
            document.body.appendChild(a);
            a.click();
            a.remove();
            URL.revokeObjectURL(url);
            setAction(`Capabilities exported (${Object.keys(caps).length}) to ${fileName}`);
        } catch (err) {
            setAction('Export capabilities failed: ' + err.message);
        }
    });

    bindClick('btnExportLedger', async () => {
        try {
            const j = await postAction('export_ledger_summary', {limit: 80});
            const summary = j.summary || {};
            const fileName = j.filename || 'action_ledger_summary.json';
            const blob = new Blob([JSON.stringify(summary, null, 2)], {type: 'application/json'});
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = fileName;
            document.body.appendChild(a);
            a.click();
            a.remove();
            URL.revokeObjectURL(url);
            setAction(`Action ledger summary exported to ${fileName}`);
        } catch (err) {
            setAction('Export ledger summary failed: ' + err.message);
        }
    });

    bindClick('btnExportBundle', async () => {
        try {
            const j = await postAction('export_diagnostics_bundle');
            const fileName = j.filename || 'diagnostics_bundle.json';
            const p = (j.path || '').trim();
            setAction(`Diagnostics bundle exported: ${fileName}${p ? ' @ ' + p : ''}`);
        } catch (err) {
            setAction('Export diagnostics bundle failed: ' + err.message);
        }
    });

    bindClick('btnOut', async () => {
        try {
            const j = await postAction('tail_log', {name: 'nova_http.out.log'});
            setAction(j.text || 'No output');
        } catch (err) {
            setAction('Tail OUT failed: ' + err.message);
        }
    });

    bindClick('btnErr', async () => {
        try {
            const j = await postAction('tail_log', {name: 'nova_http.err.log'});
            setAction(j.text || 'No output');
        } catch (err) {
            setAction('Tail ERR failed: ' + err.message);
        }
    });

    window.addEventListener('error', (ev) => {
        const msg = (ev && ev.message) ? ev.message : 'Unknown script error';
        setFeedback('UI script error: ' + msg, 'danger');
    });

    window.addEventListener('unhandledrejection', (ev) => {
        const reason = ev && ev.reason ? String(ev.reason) : 'Unhandled promise rejection';
        setFeedback('UI async error: ' + reason, 'danger');
    });

    document.addEventListener('click', (ev) => {
        const t = ev && ev.target ? ev.target.closest('button, a, [data-pane-target]') : null;
        if (!t) return;
        const id = t.id ? ('#' + t.id) : (t.getAttribute('data-pane-target') ? ('tab:' + t.getAttribute('data-pane-target')) : t.tagName.toLowerCase());
        setFeedback('Click received: ' + id, 'muted');
    }, true);

    setFeedback('Control UI connected. Fetching live status...', 'muted');
    setActivePane('overview');
    refresh();
    setInterval(refresh, 15000);
</script>
</body>
</html>
"""

CONTROL_HTML = _read_asset_text(CONTROL_TEMPLATE_PATH)


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
    if _dev_mode_enabled():
        print("Control Room auth: DEVELOPMENT MODE enabled (NOVA_DEV_MODE=1, auth checks bypassed).", flush=True)
    elif (os.environ.get("NOVA_CONTROL_TOKEN") or "").strip():
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
