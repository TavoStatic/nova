from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from services.nova_action_ledger_helpers import action_ledger_route_summary


_ERROR_PREFIX = "(error:"
_LLM_UNAVAILABLE_MARKERS = (
    "llm service unavailable",
    "ollama chat model missing",
    "ollama chat api unavailable",
    "ollama chat failed",
    "ollama chat route unavailable",
)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _parse_timestamp(value: Any) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d_%H-%M-%S"):
        candidate = text[:19]
        try:
            return datetime.strptime(candidate, fmt).timestamp()
        except ValueError:
            continue
    return None


def _artifact_timestamp(path: Path, record: dict[str, Any]) -> float:
    ts = _parse_timestamp(record.get("ts"))
    if ts is not None:
        return ts
    ts = _parse_timestamp(path.name)
    if ts is not None:
        return ts
    try:
        return float(path.stat().st_mtime)
    except OSError:
        return 0.0


def _compact_route_summary(record: dict[str, Any]) -> str:
    route_summary = str(record.get("route_summary") or "").strip()
    if route_summary:
        return route_summary[:600]
    return action_ledger_route_summary(record)[:600]


def _failure_kind(record: dict[str, Any]) -> str:
    final_answer = str(record.get("final_answer") or "").strip()
    route_summary = _compact_route_summary(record)
    final_low = final_answer.lower()
    route_low = route_summary.lower()
    if not final_low:
        return ""
    if any(marker in final_low for marker in _LLM_UNAVAILABLE_MARKERS):
        return "llm_service_unavailable"
    if final_low.startswith(_ERROR_PREFIX):
        if "llm_call:started" in route_low or str(record.get("planner_decision") or "").strip() == "llm_fallback":
            return "llm_service_unavailable"
        return "final_answer_error"
    return ""


def _compact_failure(path: Path, record: dict[str, Any], failure_kind: str, observed_at_epoch: float) -> dict[str, Any]:
    route_summary = _compact_route_summary(record)
    final_answer = str(record.get("final_answer") or "").strip()
    user_input = str(record.get("user_input") or "").strip()
    return {
        "path": str(path),
        "file": path.name,
        "ts": str(record.get("ts") or ""),
        "observed_at_epoch": observed_at_epoch,
        "session_id": str(record.get("session_id") or ""),
        "user_input": user_input[:220],
        "planner_decision": str(record.get("planner_decision") or ""),
        "route_summary": route_summary,
        "final_answer": final_answer[:260],
        "failure_kind": failure_kind,
        "provider_used": str(record.get("provider_used") or ""),
        "provider_candidate_count": len(record.get("provider_candidates") or [])
        if isinstance(record.get("provider_candidates"), list)
        else 0,
    }


def _load_regression_status(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    payload = _safe_read_json(Path(path))
    return payload if isinstance(payload, dict) else {}


class ValidationArtifactTruthService:
    """Compare validation action artifacts with the regression status Nova publishes."""

    def payload(
        self,
        *,
        runtime_dir: Path,
        regression_status_path: Path | None = None,
        limit: int = 400,
        window_before_regression_sec: int = 1800,
        window_after_regression_sec: int = 300,
        window_start_epoch: float | None = None,
        window_end_epoch: float | None = None,
        regression_status_label: str | None = None,
        regression_returncode: int | None = None,
        regression_generated_at: str | None = None,
    ) -> dict[str, Any]:
        runtime_path = Path(runtime_dir)
        action_dir = runtime_path / "validation" / "actions"
        regression_payload = _load_regression_status(regression_status_path)
        regression_generated_label = str(regression_generated_at or regression_payload.get("generated_at") or "")
        regression_at_epoch = _parse_timestamp(regression_generated_label)
        regression_label = str(
            regression_status_label if regression_status_label is not None else regression_payload.get("status") or ""
        ).strip()
        regression_code = _safe_int(
            regression_returncode if regression_returncode is not None else regression_payload.get("returncode"),
            0,
        )
        regression_green = bool(
            regression_label
            and (regression_label.lower() == "ok" or "pass" in regression_label.lower())
            and regression_code == 0
        )

        if not action_dir.exists():
            return {
                "ok": False,
                "status": "validation_actions_missing",
                "truth_state": "unknown",
                "missing_artifact": True,
                "action_dir": str(action_dir),
                "action_count": 0,
                "inspected_count": 0,
                "failure_count": 0,
                "llm_unavailable_count": 0,
                "current_window_action_count": 0,
                "current_window_failure_count": 0,
                "current_window_llm_unavailable_count": 0,
                "hidden_by_green_regression": False,
                "latest_regression_status": regression_label,
                "latest_regression_at": regression_generated_label,
                "latest_failure": {},
                "failures": [],
                "rationale": "Validation action artifact directory is absent, so validation action truth cannot be proven.",
            }

        try:
            files = sorted(action_dir.glob("*.json"), key=lambda item: item.name, reverse=True)
        except OSError as exc:
            return {
                "ok": False,
                "status": "validation_actions_unreadable",
                "action_dir": str(action_dir),
                "action_count": 0,
                "inspected_count": 0,
                "failure_count": 0,
                "llm_unavailable_count": 0,
                "current_window_action_count": 0,
                "current_window_failure_count": 0,
                "current_window_llm_unavailable_count": 0,
                "hidden_by_green_regression": False,
                "latest_regression_status": regression_label,
                "latest_regression_at": regression_generated_label,
                "latest_failure": {},
                "failures": [],
                "error": str(exc),
                "rationale": "Validation action artifact directory could not be read.",
            }

        inspected = files[: max(1, int(limit))]
        rows: list[dict[str, Any]] = []
        failures: list[dict[str, Any]] = []
        for path in inspected:
            record = _safe_read_json(path)
            if not isinstance(record, dict):
                continue
            observed_at_epoch = _artifact_timestamp(path, record)
            failure_kind = _failure_kind(record)
            row = {
                "path": str(path),
                "file": path.name,
                "observed_at_epoch": observed_at_epoch,
                "failure_kind": failure_kind,
            }
            rows.append(row)
            if failure_kind:
                failures.append(_compact_failure(path, record, failure_kind, observed_at_epoch))

        if window_start_epoch is not None or window_end_epoch is not None:
            start_epoch = float(window_start_epoch) if window_start_epoch is not None else 0.0
            end_epoch = float(window_end_epoch) if window_end_epoch is not None else time.time()
            current_rows = [
                row
                for row in rows
                if start_epoch <= float(row.get("observed_at_epoch") or 0.0) <= end_epoch
            ]
            current_failures = [
                row
                for row in failures
                if start_epoch <= float(row.get("observed_at_epoch") or 0.0) <= end_epoch
            ]
            window = {
                "start_epoch": start_epoch,
                "end_epoch": end_epoch,
                "basis": "explicit_window",
            }
        elif regression_at_epoch is not None:
            start_epoch = regression_at_epoch - max(0, int(window_before_regression_sec))
            end_epoch = regression_at_epoch + max(0, int(window_after_regression_sec))
            current_rows = [
                row
                for row in rows
                if start_epoch <= float(row.get("observed_at_epoch") or 0.0) <= end_epoch
            ]
            current_failures = [
                row
                for row in failures
                if start_epoch <= float(row.get("observed_at_epoch") or 0.0) <= end_epoch
            ]
            window = {
                "start_epoch": start_epoch,
                "end_epoch": end_epoch,
                "basis": "latest_regression_generated_at",
            }
        else:
            current_rows = rows
            current_failures = failures
            window = {
                "start_epoch": None,
                "end_epoch": None,
                "basis": "all_inspected_actions",
            }

        current_llm_failures = [
            row
            for row in current_failures
            if str(row.get("failure_kind") or "") == "llm_service_unavailable"
        ]
        hidden_by_green = bool(regression_green and current_failures)
        ok = not current_failures
        if ok:
            status = "ok"
        elif hidden_by_green and current_llm_failures:
            status = "llm_unavailable_in_green_regression"
        elif hidden_by_green:
            status = "validation_failure_in_green_regression"
        elif current_llm_failures:
            status = "llm_unavailable_in_validation"
        else:
            status = "validation_artifact_failure"

        latest_failure = current_failures[0] if current_failures else {}
        latest_historical_failure = failures[0] if failures else {}
        return {
            "ok": ok,
            "status": status,
            "action_dir": str(action_dir),
            "action_count": len(files),
            "inspected_count": len(inspected),
            "inspection_truncated": len(files) > len(inspected),
            "failure_count": len(failures),
            "llm_unavailable_count": sum(1 for row in failures if row.get("failure_kind") == "llm_service_unavailable"),
            "current_window": window,
            "current_window_action_count": len(current_rows),
            "current_window_failure_count": len(current_failures),
            "current_window_llm_unavailable_count": len(current_llm_failures),
            "hidden_by_green_regression": hidden_by_green,
            "latest_regression_status": regression_label,
            "latest_regression_at": regression_generated_label,
            "latest_regression_returncode": regression_code,
            "latest_failure": latest_failure,
            "latest_historical_failure": latest_historical_failure,
            "failures": current_failures[:8],
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "rationale": (
                "Validation runtime action artifacts are regression evidence; a green regression status is not clear "
                "when action records in the regression window finalized with runtime errors."
            ),
        }


VALIDATION_ARTIFACT_TRUTH_SERVICE = ValidationArtifactTruthService()
