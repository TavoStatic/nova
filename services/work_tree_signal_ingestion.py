from __future__ import annotations

from datetime import datetime
import hashlib
import json
from typing import Any

import work_tree
from work_tree_contracts import BranchStatus


_VALID_SIGNAL_CLASSES = {
    "runtime_failure",
    "error_spike",
    "dependency_unreachable",
    "code_defect",
    "governance_pressure",
    "maintenance_pressure",
    "operator_requested",
    "regression_failure",
    "subconscious_candidate",
    "release_readiness_gap",
}

_SIGNAL_TO_WORK_CLASS = {
    "runtime_failure": "runtime_failure",
    "error_spike": "runtime_failure",
    "dependency_unreachable": "dependency_unreachable",
    "code_defect": "code_defect",
    "governance_pressure": "governance_pressure",
    "maintenance_pressure": "maintenance_pressure",
    "operator_requested": "operator_requested",
    "regression_failure": "regression_failure",
    "subconscious_candidate": "candidate_review",
    "release_readiness_gap": "release_readiness_gap",
}

_BUCKET_BY_WORK_CLASS = {
    "runtime_failure": "runtime",
    "code_defect": "code_defect",
    "dependency_unreachable": "dependency",
    "governance_pressure": "governance",
    "maintenance_pressure": "maintenance",
    "operator_requested": "operator",
    "regression_failure": "regression",
    "candidate_review": "candidate_review",
    "release_readiness_gap": "release",
}

_DEFAULT_ACTIONABILITY_BY_CLASS = {
    "runtime_failure": "safe_now",
    "code_defect": "safe_now",
    "dependency_unreachable": "dead_end",
    "governance_pressure": "blocked",
    "maintenance_pressure": "safe_now",
    "operator_requested": "safe_now",
    "regression_failure": "safe_now",
    "candidate_review": "safe_now",
    "release_readiness_gap": "blocked",
}

_BRANCH_STATUS_BY_ACTIONABILITY = {
    "safe_now": BranchStatus.READY,
    "blocked": BranchStatus.BLOCKED,
    "dead_end": BranchStatus.STALLED,
}

_RESOLUTION_BY_ACTIONABILITY = {
    "safe_now": "open",
    "blocked": "observing",
    "dead_end": "retired",
}


class WorkTreeSignalIngestionService:
    """Normalize runtime/control pressure into governed Work Tree branches only."""

    SIGNAL_TREE_KIND = "signal_ingestion"
    SIGNAL_TREE_SOURCE = "runtime_signals"
    SIGNAL_TREE_TITLE = "Signal Intake: Runtime Governance"

    def ingest_signal(self, signal: dict[str, Any]) -> dict[str, Any]:
        normalized = self._normalize_signal(signal)
        signal_class = str(normalized.get("signal_class") or "").strip().lower()
        if signal_class not in _VALID_SIGNAL_CLASSES:
            return {
                "action": "ignored",
                "tree_id": "",
                "branch_id": "",
                "reason": f"unsupported_signal_class:{signal_class or 'missing'}",
            }

        source_key = str(normalized.get("source_key") or "").strip()
        title = str(normalized.get("title") or "").strip()
        if not source_key or not title:
            return {
                "action": "ignored",
                "tree_id": "",
                "branch_id": "",
                "reason": "missing_title_or_fingerprint",
            }

        work_class = str(normalized.get("work_class") or "").strip().lower()
        actionability = str(normalized.get("actionability") or "").strip().lower()
        if not work_class or not actionability:
            return {
                "action": "ignored",
                "tree_id": "",
                "branch_id": "",
                "reason": "missing_work_mapping",
            }

        tree = self._ensure_signal_tree()
        root_branch = work_tree.get_branch(tree.root_branch_id)
        if root_branch is None:
            return {
                "action": "ignored",
                "tree_id": tree.tree_id,
                "branch_id": "",
                "reason": "root_branch_missing",
            }

        open_branch = self._find_branch_by_source_key(tree.tree_id, source_key, open_only=True)
        if open_branch is not None:
            self._apply_branch_update(open_branch, normalized, reopen=False)
            return {
                "action": "updated",
                "tree_id": tree.tree_id,
                "branch_id": open_branch.branch_id,
                "reason": "existing_open_branch",
            }

        closed_branch = self._find_branch_by_source_key(tree.tree_id, source_key, open_only=False)
        if closed_branch is not None:
            self._apply_branch_update(closed_branch, normalized, reopen=True)
            return {
                "action": "reopened",
                "tree_id": tree.tree_id,
                "branch_id": closed_branch.branch_id,
                "reason": "reopened_resolved_branch",
            }

        if not self._deserves_persisted_work(normalized):
            return {
                "action": "ignored",
                "tree_id": tree.tree_id,
                "branch_id": "",
                "reason": "non_actionable_transient",
            }

        branch = work_tree.add_branch_to_tree(
            tree.tree_id,
            title,
            _bucket_for_work_class(work_class),
            root_branch.branch_id,
        )
        self._apply_branch_update(branch, normalized, reopen=False, first_seen=True)

        next_task = str(normalized.get("next_task") or "").strip()
        if next_task and actionability != "dead_end":
            work_tree.add_task_to_branch(branch.branch_id, next_task)
            work_tree.assign_branch_tool_from_text(branch.branch_id, next_task)

        return {
            "action": "created",
            "tree_id": tree.tree_id,
            "branch_id": branch.branch_id,
            "reason": "new_signal_branch",
        }

    def ingest_status_snapshot(self, status_payload: dict[str, Any]) -> list[dict[str, Any]]:
        signals: list[dict[str, Any]] = []
        alerts = [str(item or "").strip() for item in list(status_payload.get("alerts") or []) if str(item or "").strip()]
        for alert in alerts:
            low = alert.lower()
            if "error_spike" in low:
                signals.append({
                    "source": "control_status",
                    "signal_class": "error_spike",
                    "title": "Investigate control/status error spike",
                    "fingerprint": {
                        "class": "runtime_failure",
                        "surface": "control_status",
                        "error": "error_spike",
                        "symbol": "control_status",
                    },
                    "payload": {"alert": alert},
                    "severity": "high",
                    "actionability": "safe_now",
                    "next_task": "Inspect control status logs and isolate failing endpoint path",
                })
            if "ollama_api" in low:
                signals.append({
                    "source": "control_status",
                    "signal_class": "dependency_unreachable",
                    "title": "Ollama API unreachable",
                    "fingerprint": {
                        "class": "dependency_unreachable",
                        "surface": "control_status",
                        "error": "dependency_unreachable",
                        "symbol": "ollama_api",
                    },
                    "payload": {"alert": alert},
                    "severity": "medium",
                    "actionability": "dead_end",
                    "next_task": "Observe dependency reachability and recheck when runtime path is blocked",
                })

        pass_ratio = float(status_payload.get("self_check_pass_ratio") or 0.0)
        if pass_ratio < 1.0:
            signals.append({
                "source": "self_check",
                "signal_class": "governance_pressure",
                "title": "Resolve self-check failures in control status",
                "fingerprint": {
                    "class": "governance_pressure",
                    "surface": "self_check",
                    "error": "self_check_failures",
                    "symbol": "control_status",
                },
                "payload": {
                    "pass_ratio": pass_ratio,
                    "alerts": alerts,
                },
                "severity": "high" if pass_ratio < 0.95 else "medium",
                "actionability": "blocked",
                "next_task": "Confirm failing self-check probes and route each probe to root-cause branch",
            })

        maintenance = status_payload.get("autonomy_maintenance") if isinstance(status_payload.get("autonomy_maintenance"), dict) else {}
        last_regression = str(maintenance.get("last_regression_status") or "").strip()
        last_regression_stale = bool(maintenance.get("last_regression_stale", False))
        if last_regression and "pass" not in last_regression.lower() and last_regression.lower() != "ok" and not last_regression_stale:
            signals.append({
                "source": "regression",
                "signal_class": "regression_failure",
                "title": "Resolve regression/test failures from maintenance cycle",
                "fingerprint": {
                    "class": "regression_failure",
                    "surface": "maintenance_cycle",
                    "error": "regression_failure",
                    "symbol": last_regression,
                },
                "payload": {
                    "last_regression_status": last_regression,
                },
                "severity": "high",
                "actionability": "safe_now",
                "next_task": "Run focused failing regression lane and isolate blocking failures",
            })

        results: list[dict[str, Any]] = []
        for signal in signals:
            results.append(self.ingest_signal(signal))
        return results

    def _ensure_signal_tree(self):
        for tree in work_tree.list_trees():
            meta = dict(getattr(tree, "meta", {}) or {})
            if str(meta.get("kind") or "").strip().lower() == self.SIGNAL_TREE_KIND:
                return tree
        return work_tree.initialize_tree(
            self.SIGNAL_TREE_TITLE,
            meta={
                "kind": self.SIGNAL_TREE_KIND,
                "source": self.SIGNAL_TREE_SOURCE,
                "signal_ingestion": True,
            },
        )

    def _find_branch_by_source_key(self, tree_id: str, source_key: str, *, open_only: bool) -> Any | None:
        for branch in work_tree.list_tree_branches(tree_id):
            if str(getattr(branch, "source_key", "") or "").strip() != source_key:
                continue
            resolution = str(getattr(branch, "resolution_state", "") or "").strip().lower()
            if open_only and resolution in {"resolved", "retired"}:
                continue
            return branch
        return None

    def _deserves_persisted_work(self, normalized: dict[str, Any]) -> bool:
        actionability = str(normalized.get("actionability") or "").strip().lower()
        severity = str(normalized.get("severity") or "").strip().lower()
        if actionability == "dead_end" and severity in {"", "info", "low"}:
            return False
        return True

    def _apply_branch_update(
        self,
        branch,
        normalized: dict[str, Any],
        *,
        reopen: bool,
        first_seen: bool = False,
    ) -> None:
        now = datetime.now()
        actionability = str(normalized.get("actionability") or "safe_now").strip().lower()
        work_class = str(normalized.get("work_class") or "").strip().lower()
        severity = str(normalized.get("severity") or "medium").strip().lower()

        branch.title = str(normalized.get("title") or branch.title)
        branch.bucket = _bucket_for_work_class(work_class)
        branch.source_type = str(normalized.get("source") or "") or None
        branch.source_key = str(normalized.get("source_key") or "") or None
        branch.source_payload = dict(normalized.get("payload") or {})
        branch.work_class = work_class
        branch.actionability = actionability
        branch.resolution_state = _RESOLUTION_BY_ACTIONABILITY.get(actionability, "open")
        branch.last_seen_at = now

        score = _score_for_signal(severity, actionability)
        branch.priority = int(max(branch.priority, score)) if not first_seen else int(score)

        if first_seen:
            branch.evidence_count = 1
        else:
            branch.evidence_count = int(branch.evidence_count or 0) + 1

        branch.status = _BRANCH_STATUS_BY_ACTIONABILITY.get(actionability, BranchStatus.READY)
        if reopen:
            branch.resolution_state = "open"
            if branch.status == BranchStatus.COMPLETE:
                branch.status = BranchStatus.READY

        summary = _branch_why_summary(normalized)
        existing_notes = str(branch.notes or "").strip()
        if summary and summary not in existing_notes:
            branch.notes = f"{existing_notes}\n{summary}".strip() if existing_notes else summary

        work_tree.touch_branch(branch.branch_id)

        next_task = str(normalized.get("next_task") or "").strip()
        if next_task and actionability != "dead_end":
            open_tasks = [
                task
                for task in work_tree.list_branch_tasks(branch.branch_id)
                if str(getattr(task.status, "value", task.status) or "").strip().lower() not in {"complete", "dropped"}
            ]
            if not open_tasks:
                work_tree.add_task_to_branch(branch.branch_id, next_task)
            work_tree.assign_branch_tool_from_text(branch.branch_id, next_task)

    def _normalize_signal(self, signal: dict[str, Any]) -> dict[str, Any]:
        source = str(signal.get("source") or "").strip().lower() or "control_status"
        incoming_class = str(signal.get("signal_class") or "").strip().lower()
        work_class = _SIGNAL_TO_WORK_CLASS.get(incoming_class, "")

        payload = signal.get("payload") if isinstance(signal.get("payload"), dict) else {}
        severity = str(signal.get("severity") or "medium").strip().lower()
        if severity not in {"critical", "high", "medium", "low", "info"}:
            severity = "medium"

        actionability = str(signal.get("actionability") or "").strip().lower()
        if actionability not in {"safe_now", "blocked", "dead_end"}:
            actionability = _DEFAULT_ACTIONABILITY_BY_CLASS.get(work_class, "safe_now")

        source_key = str(signal.get("source_key") or "").strip()
        if not source_key:
            source_key = _signal_fingerprint_key(
                signal_class=incoming_class,
                source=source,
                title=str(signal.get("title") or "").strip(),
                fingerprint=signal.get("fingerprint"),
                payload=payload,
            )

        return {
            "source": source,
            "signal_class": incoming_class,
            "work_class": work_class,
            "title": str(signal.get("title") or "").strip(),
            "source_key": source_key,
            "payload": dict(payload),
            "severity": severity,
            "actionability": actionability,
            "next_task": str(signal.get("next_task") or "").strip(),
        }


def _signal_fingerprint_key(*, signal_class: str, source: str, title: str, fingerprint: Any, payload: dict[str, Any]) -> str:
    if isinstance(fingerprint, str) and fingerprint.strip():
        return fingerprint.strip()

    if isinstance(fingerprint, dict):
        ordered = {str(key): fingerprint[key] for key in sorted(fingerprint.keys(), key=lambda item: str(item))}
        values = [str(ordered.get(key) or "").strip() for key in ("class", "surface", "error", "symbol")]
        if any(values):
            return ":".join([
                str(signal_class or ordered.get("class") or "unknown").strip(),
                str(ordered.get("surface") or source or "unknown").strip(),
                str(ordered.get("error") or "").strip() or "signal",
                str(ordered.get("symbol") or "").strip() or "none",
            ])
        body = json.dumps(ordered, sort_keys=True, ensure_ascii=True)
        return f"{signal_class}:{source}:{hashlib.sha1(body.encode('utf-8')).hexdigest()[:16]}"

    fallback = {
        "signal_class": signal_class,
        "source": source,
        "title": title,
        "payload": payload,
    }
    body = json.dumps(fallback, sort_keys=True, ensure_ascii=True)
    return f"{signal_class}:{source}:{hashlib.sha1(body.encode('utf-8')).hexdigest()[:16]}"


def _bucket_for_work_class(work_class: str) -> str:
    return _BUCKET_BY_WORK_CLASS.get(work_class, "signals")


def _score_for_signal(severity: str, actionability: str) -> int:
    severity_score = {
        "critical": 95,
        "high": 85,
        "medium": 70,
        "low": 55,
        "info": 40,
    }.get(severity, 70)
    actionability_bonus = {
        "safe_now": 5,
        "blocked": -5,
        "dead_end": -20,
    }.get(actionability, 0)
    return max(0, min(100, severity_score + actionability_bonus))


def _branch_why_summary(normalized: dict[str, Any]) -> str:
    payload = normalized.get("payload") if isinstance(normalized.get("payload"), dict) else {}
    signal_class = str(normalized.get("signal_class") or "").strip()
    source = str(normalized.get("source") or "").strip()
    actionability = str(normalized.get("actionability") or "").strip()
    severity = str(normalized.get("severity") or "").strip()
    alert = str(payload.get("alert") or "").strip()
    rationale = str(payload.get("rationale") or "").strip()
    target_seam = str(payload.get("target_seam") or "").strip()
    signal_name = str(payload.get("signal") or "").strip()
    suggested_test_name = str(payload.get("suggested_test_name") or "").strip()
    preferred_owner = str(payload.get("preferred_owner") or "").strip()
    route_hint = str(payload.get("route_hint") or "").strip()
    branch_note = str(payload.get("branch_note") or "").strip()
    parts = [
        f"source={source or 'unknown'}",
        f"signal_class={signal_class or 'unknown'}",
        f"severity={severity or 'unknown'}",
        f"actionability={actionability or 'safe_now'}",
    ]
    if alert:
        parts.append(f"alert={alert}")
    if target_seam:
        parts.append(f"seam={target_seam}")
    if signal_name:
        parts.append(f"signal={signal_name}")
    if suggested_test_name:
        parts.append(f"test={suggested_test_name}")
    if preferred_owner:
        parts.append(f"owner={preferred_owner}")
    if route_hint:
        parts.append(f"route_hint={route_hint}")
    summary = "Signal evidence: " + " | ".join(parts)
    extra_lines = [summary]
    if rationale:
        extra_lines.append(f"Rationale: {rationale}")
    if branch_note:
        extra_lines.append(f"Review focus: {branch_note}")
    return "\n".join(extra_lines)


WORK_TREE_SIGNAL_INGESTION_SERVICE = WorkTreeSignalIngestionService()
