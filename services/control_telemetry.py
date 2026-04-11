from __future__ import annotations

import json
from pathlib import Path
import time
from typing import Any, Callable


class ControlTelemetryService:
    """Build control-room telemetry summaries outside the HTTP transport layer."""

    def __init__(self, *, list_capabilities_fn: Callable[[], dict]) -> None:
        self._list_capabilities = list_capabilities_fn

    def action_ledger_summary(
        self,
        action_ledger_dir: Path,
        route_summary_fn: Callable[[dict], str],
        limit: int = 60,
    ) -> dict:
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
            files = sorted(Path(action_ledger_dir).glob("*.json"))
            if not files:
                return out
            recent = files[-max(1, int(limit)):]
            out["count"] = len(recent)
            for path in recent:
                try:
                    record = json.loads(path.read_text(encoding="utf-8"))
                except Exception:
                    continue
                decision = str(record.get("planner_decision") or "unknown").strip() or "unknown"
                tool = str(record.get("tool") or "none").strip() or "none"
                route_summary = str(route_summary_fn(record) or "").strip()
                out["decision_counts"][decision] = int(out["decision_counts"].get(decision, 0)) + 1
                out["tool_counts"][tool] = int(out["tool_counts"].get(tool, 0)) + 1
                if route_summary:
                    out["route_counts"][route_summary] = int(out["route_counts"].get(route_summary, 0)) + 1
                if bool(record.get("grounded")):
                    out["grounded_true"] += 1
                else:
                    out["grounded_false"] += 1
                out["last_record"] = {
                    "intent": record.get("intent"),
                    "planner_decision": record.get("planner_decision"),
                    "tool": record.get("tool"),
                    "grounded": bool(record.get("grounded")),
                    "route_summary": route_summary,
                    "route_trace": list(record.get("route_trace") or [])[:20] if isinstance(record.get("route_trace"), list) else [],
                    "final_answer": str(record.get("final_answer") or "")[:220],
                }
            return out
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def tool_events_summary(self, events_log: Path, limit: int = 80) -> dict:
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
            if not Path(events_log).exists():
                return out
            lines = Path(events_log).read_text(encoding="utf-8", errors="ignore").splitlines()
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
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def memory_events_summary(self, events_log: Path, limit: int = 80) -> dict:
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
            if not Path(events_log).exists():
                return out
            lines = Path(events_log).read_text(encoding="utf-8", errors="ignore").splitlines()
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
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    @staticmethod
    def record_control_action_event(
        runtime_dir: Path,
        control_audit_log: Path,
        action: str,
        result: str,
        detail: str = "",
        payload: dict | None = None,
    ) -> None:
        entry = {
            "ts": int(time.time()),
            "action": str(action or "").strip(),
            "result": str(result or "").strip(),
            "detail": str(detail or "")[:500],
        }
        if isinstance(payload, dict):
            entry["payload_keys"] = sorted([str(key) for key in payload.keys()])[:20]
            safe_fields: dict[str, str] = {}
            for key in ("session_id", "source", "macro", "operator_mode"):
                value = str(payload.get(key) or "").strip()
                if value:
                    safe_fields[key] = value[:120]
            if safe_fields:
                entry["safe_fields"] = safe_fields
        try:
            runtime_dir.mkdir(parents=True, exist_ok=True)
            with open(control_audit_log, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, ensure_ascii=True) + "\n")
        except Exception:
            pass

    @staticmethod
    def safe_tail_lines(path: Path, *, tail_file_fn, n: int = 80) -> list[str]:
        text = tail_file_fn(path, max_lines=max(1, int(n)))
        return text.splitlines() if text else []

    def export_capabilities_snapshot(self, export_dir: Path, *, strftime_fn=time.strftime) -> tuple[bool, str, dict]:
        try:
            caps = self._list_capabilities()
            if not isinstance(caps, dict):
                caps = {}
            export_dir.mkdir(parents=True, exist_ok=True)
            stamp = strftime_fn("%Y%m%d_%H%M%S")
            out = export_dir / f"capabilities_{stamp}.json"
            out.write_text(json.dumps(caps, ensure_ascii=True, indent=2), encoding="utf-8")
            return True, "capabilities_export_ok", {
                "path": str(out),
                "filename": out.name,
                "capabilities": caps,
                "count": len(caps),
            }
        except Exception as exc:
            return False, f"capabilities_export_failed:{exc}", {}

    @staticmethod
    def append_metrics_snapshot(
        status_payload: dict,
        *,
        metrics_lock,
        http_requests_total: int,
        http_errors_total: int,
        metrics_series: list[dict],
        metrics_max_points: int,
        now_fn=time.time,
    ) -> None:
        with metrics_lock:
            point = {
                "ts": int(now_fn()),
                "heartbeat_age_sec": status_payload.get("heartbeat_age_sec"),
                "requests_total": http_requests_total,
                "errors_total": http_errors_total,
                "ollama_api_up": bool(status_payload.get("ollama_api_up")),
                "searxng_ok": status_payload.get("searxng_ok"),
            }
            metrics_series.append(point)
            if len(metrics_series) > metrics_max_points:
                del metrics_series[: len(metrics_series) - metrics_max_points]

    @staticmethod
    def metrics_payload(*, metrics_lock, http_requests_total: int, http_errors_total: int, metrics_series: list[dict]) -> dict:
        with metrics_lock:
            return {
                "ok": True,
                "requests_total": http_requests_total,
                "errors_total": http_errors_total,
                "points": list(metrics_series),
            }

    @staticmethod
    def tail_log_action(payload: dict, *, log_dir: Path, tail_file_fn, record_control_action_event_fn) -> tuple[bool, str, dict]:
        action = "tail_log"
        name = str(payload.get("name") or "").strip().lower()
        allowed = {
            "nova_http.out.log": log_dir / "nova_http.out.log",
            "nova_http.err.log": log_dir / "nova_http.err.log",
            "guard.log": log_dir / "guard.log",
        }
        if name not in allowed:
            record_control_action_event_fn(action, "fail", "invalid_log_name", payload)
            return False, "invalid_log_name", {}
        out = {"name": name, "text": tail_file_fn(allowed[name])}
        record_control_action_event_fn(action, "ok", f"tail_log_ok:{name}", payload)
        return True, "tail_log_ok", out

    @staticmethod
    def metrics_action(payload: dict, *, metrics_payload_fn, record_control_action_event_fn) -> tuple[bool, str, dict]:
        data = metrics_payload_fn()
        record_control_action_event_fn("metrics", "ok", "metrics_ok", payload)
        return True, "metrics_ok", data

    @staticmethod
    def export_ledger_summary_action(
        payload: dict,
        *,
        export_dir: Path,
        action_ledger_summary_fn,
        record_control_action_event_fn,
        strftime_fn=time.strftime,
    ) -> tuple[bool, str, dict]:
        action = "export_ledger_summary"
        try:
            summary = action_ledger_summary_fn(limit=int(payload.get("limit") or 60))
            export_dir.mkdir(parents=True, exist_ok=True)
            stamp = strftime_fn("%Y%m%d_%H%M%S")
            out = export_dir / f"action_ledger_summary_{stamp}.json"
            out.write_text(json.dumps(summary, ensure_ascii=True, indent=2), encoding="utf-8")
            msg = "action_ledger_export_ok"
            extra = {"path": str(out), "filename": out.name, "summary": summary}
            record_control_action_event_fn(action, "ok", msg, payload)
            return True, msg, extra
        except Exception as exc:
            record_control_action_event_fn(action, "fail", str(exc), payload)
            return False, f"action_ledger_export_failed:{exc}", {}

    def export_diagnostics_bundle_action(
        self,
        payload: dict,
        *,
        runtime_dir: Path,
        log_dir: Path,
        control_status_payload_fn,
        control_policy_payload_fn,
        metrics_payload_fn,
        build_self_check_fn,
        behavior_get_metrics_fn,
        action_ledger_summary_fn,
        tool_events_summary_fn,
        safe_tail_lines_fn,
        record_control_action_event_fn,
        now_fn=time.time,
    ) -> tuple[bool, str, dict]:
        action = "export_diagnostics_bundle"
        try:
            status = control_status_payload_fn()
            policy = control_policy_payload_fn()
            metrics = metrics_payload_fn()
            self_check = build_self_check_fn(status, policy, metrics)
            bundle: dict[str, Any] = {
                "ts": int(now_fn()),
                "status": status,
                "policy": policy,
                "metrics": metrics,
                "self_check": self_check,
                "capabilities": self._list_capabilities(),
                "behavior_metrics": behavior_get_metrics_fn(),
                "action_ledger_summary": action_ledger_summary_fn(80),
                "tool_event_summary": tool_events_summary_fn(120),
                "logs": {
                    "nova_http_out": safe_tail_lines_fn(log_dir / "nova_http.out.log", 120),
                    "nova_http_err": safe_tail_lines_fn(log_dir / "nova_http.err.log", 120),
                },
            }
            runtime_dir.mkdir(parents=True, exist_ok=True)
            out = runtime_dir / f"diagnostics_bundle_{int(now_fn())}.json"
            out.write_text(json.dumps(bundle, ensure_ascii=True, indent=2), encoding="utf-8")
            msg = f"diagnostics_bundle_exported:{out.name}"
            record_control_action_event_fn(action, "ok", msg, payload)
            return True, msg, {"path": str(out), "filename": out.name}
        except Exception as exc:
            record_control_action_event_fn(action, "fail", str(exc), payload)
            return False, f"diagnostics_bundle_export_failed:{exc}", {}

    def build_self_check(self, status: dict, policy: dict, metrics: dict) -> dict:
        checks: list[dict] = []
        alerts: list[str] = []

        def add_check(name: str, ok: bool, detail: str = "") -> None:
            checks.append({"name": name, "ok": bool(ok), "detail": str(detail or "")})

        add_check("status_payload", bool(status.get("ok")), "status endpoint payload built")
        add_check("ollama_api", bool(status.get("ollama_api_up")), "ollama api reachability")
        add_check("policy_payload", bool(policy.get("ok")), "policy payload built")
        add_check("metrics_payload", bool(metrics.get("ok")), "metrics payload built")
        add_check("session_manager", True, "session summaries available")
        add_check("guard_status", isinstance(status.get("guard"), dict), "guard payload available")
        add_check("tool_event_summary", bool(status.get("tool_events_ok", True)), "tool event summary available")
        add_check("patch_status_summary", bool(status.get("patch_status_ok", True)), "patch governance summary available")

        try:
            caps = self._list_capabilities()
            cap_ok = isinstance(caps, dict)
            add_check("capability_registry", cap_ok, f"count={len(caps) if cap_ok else 0}")
        except Exception as exc:
            add_check("capability_registry", False, str(exc))

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

        patch_enabled = bool(status.get("patch_enabled", False))
        patch_strict = bool(status.get("patch_strict_manifest", False))
        patch_behavioral = bool(status.get("patch_behavioral_check", False))
        patch_tests_available = bool(status.get("patch_tests_available", False))
        add_check("patch_strict_manifest", (not patch_enabled) or patch_strict, f"enabled={patch_enabled}")
        if patch_enabled and not patch_strict:
            alerts.append("patch_strict_manifest_disabled")
        add_check("patch_behavioral_gate", (not patch_enabled) or patch_behavioral, f"enabled={patch_enabled}; tests_available={patch_tests_available}")
        if patch_enabled and not patch_behavioral:
            alerts.append("patch_behavioral_check_disabled")
        add_check("patch_behavioral_tests_available", (not patch_enabled) or (not patch_behavioral) or patch_tests_available, f"tests_available={patch_tests_available}")
        if patch_enabled and patch_behavioral and not patch_tests_available:
            alerts.append("patch_tests_missing")

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
        ok_count = sum(1 for item in checks if item.get("ok"))
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