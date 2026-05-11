from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from services.test_session_control import TEST_SESSION_CONTROL_SERVICE


DEFAULT_CONTRACT_REVALIDATE_HOURS = 24.0


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


class TestingEcologyService:
    """Build a lifecycle report for Nova's generated/saved test ecology."""

    @staticmethod
    def _path_mtime_ts(path_text: str) -> float:
        path = Path(str(path_text or ""))
        try:
            if not path.exists():
                return 0.0
            return float(path.stat().st_mtime)
        except Exception:
            return 0.0

    @staticmethod
    def _evidence_age_hours(report: dict, *, now_ts: float) -> float | None:
        report_path = str((report or {}).get("report_path") or "").strip()
        mtime = TestingEcologyService._path_mtime_ts(report_path)
        if mtime <= 0.0:
            return None
        return max(0.0, (now_ts - mtime) / 3600.0)

    @staticmethod
    def _priority_owner(priority: dict) -> str:
        seam = str(priority.get("seam") or priority.get("target_seam") or "").strip().lower()
        signal = str(priority.get("signal") or "").strip().lower()
        if "fulfillment" in seam or signal == "fulfillment_missed":
            return "fulfillment"
        if "route" in seam or signal in {"route_conflict", "route_unclear", "route_fit_weak"}:
            return "route_comparison"
        if seam or signal:
            return "supervisor"
        return "unknown"

    @staticmethod
    def _priority_sort_key(definition_file: str, priority: dict) -> tuple[int, float, int, str]:
        try:
            return TEST_SESSION_CONTROL_SERVICE.generated_definition_priority_tuple(
                {"training_priorities": [priority], "file": definition_file}
            )
        except Exception:
            urgency_rank = {"high": 0, "medium": 1, "low": 2, "deferred": 3}.get(
                str(priority.get("urgency") or "").strip().lower(),
                4,
            )
            return (urgency_rank, -_safe_float(priority.get("robustness", priority.get("robustness_score")), 0.0), -1, definition_file)

    @staticmethod
    def _definition_priority_summary(definition: dict) -> dict:
        definition_file = str((definition or {}).get("file") or "")
        priorities = [
            dict(item)
            for item in list((definition or {}).get("training_priorities") or [])
            if isinstance(item, dict)
        ]
        if not priorities:
            return {
                "priority_count": 0,
                "top_signal": "",
                "top_seam": "",
                "top_urgency": "",
                "top_robustness": 0.0,
                "owner_hint": "unknown",
            }
        ordered = sorted(
            priorities,
            key=lambda priority: TestingEcologyService._priority_sort_key(definition_file, priority),
        )
        top = dict(ordered[0])
        return {
            "priority_count": len(priorities),
            "top_signal": str(top.get("signal") or "").strip(),
            "top_seam": str(top.get("seam") or top.get("target_seam") or "").strip(),
            "top_urgency": str(top.get("urgency") or "").strip(),
            "top_robustness": _safe_float(top.get("robustness", top.get("robustness_score")), 0.0),
            "owner_hint": TestingEcologyService._priority_owner(top),
        }

    @staticmethod
    def _latest_audit_by_file(runtime_dir: Path | None) -> dict[str, dict]:
        if runtime_dir is None:
            return {}
        return TEST_SESSION_CONTROL_SERVICE._latest_audit_by_file(Path(runtime_dir))

    @staticmethod
    def _is_template_definition(file_name: str) -> bool:
        return Path(str(file_name or "").replace("\\", "/")).name.upper().startswith("TEMPLATE_")

    @staticmethod
    def _ecology_lifecycle(
        lifecycle: dict,
        *,
        file_name: str,
        origin: str,
        latest_status: str,
        has_training_priorities: bool,
    ) -> dict:
        if TestingEcologyService._is_template_definition(file_name):
            return {
                "lifecycle_state": "template",
                "ecology_role": "template",
                "growth_action": "keep_as_definition_template",
                "growth_ready": False,
                "lifecycle_reason": "template definitions are scaffolding, not runtime growth pressure",
            }
        if origin != "generated" and latest_status == "never_run" and not has_training_priorities:
            return {
                "lifecycle_state": "saved_reference",
                "ecology_role": "reference",
                "growth_action": "available_for_manual_run",
                "growth_ready": False,
                "lifecycle_reason": "saved reference sessions without training priorities do not create growth pressure by themselves",
            }
        return dict(lifecycle or {})

    def build_report(
        self,
        definitions: list[dict],
        reports: list[dict],
        *,
        runtime_dir: Path | None = None,
        now_ts: float | None = None,
        contract_revalidate_hours: float = DEFAULT_CONTRACT_REVALIDATE_HOURS,
        limit: int = 200,
    ) -> dict:
        current_ts = float(now_ts if now_ts is not None else time.time())
        definition_rows = [dict(item) for item in list(definitions or []) if isinstance(item, dict)]
        report_by_file = TEST_SESSION_CONTROL_SERVICE.latest_generated_report_by_file(
            reports,
            max(200, len(definition_rows) * 2),
        )
        audit_by_file = self._latest_audit_by_file(runtime_dir)
        items: list[dict] = []
        lifecycle_counts: dict[str, int] = {}
        role_counts: dict[str, int] = {}
        owner_counts: dict[str, int] = {}
        origin_counts: dict[str, int] = {}
        status_counts: dict[str, int] = {}
        mutation_due_count = 0
        stale_evidence_count = 0
        growth_pressure_count = 0

        for definition in definition_rows:
            file_name = str(definition.get("file") or "").strip()
            if not file_name:
                continue
            origin = str(definition.get("origin") or "unknown").strip() or "unknown"
            latest_report = dict(report_by_file.get(file_name) or {})
            latest_status = str(latest_report.get("status") or "never_run").strip().lower() or "never_run"
            fingerprint = str(definition.get("fingerprint") or "")
            audit_row = dict(audit_by_file.get(file_name) or {})
            audit_fingerprint = str(audit_row.get("fingerprint") or "")
            already_reviewed_current = bool(fingerprint and audit_fingerprint and fingerprint == audit_fingerprint)
            priority_summary = self._definition_priority_summary(definition)
            lifecycle = TEST_SESSION_CONTROL_SERVICE.generated_definition_lifecycle(
                latest_status=latest_status,
                already_reviewed_current=already_reviewed_current,
                has_training_priorities=bool(priority_summary.get("priority_count")),
            )
            lifecycle = self._ecology_lifecycle(
                lifecycle,
                file_name=file_name,
                origin=origin,
                latest_status=latest_status,
                has_training_priorities=bool(priority_summary.get("priority_count")),
            )
            evidence_age_hours = self._evidence_age_hours(latest_report, now_ts=current_ts)
            evidence_stale = bool(
                evidence_age_hours is not None
                and evidence_age_hours >= max(0.0, float(contract_revalidate_hours or 0.0))
            )
            mutation_due = bool(
                lifecycle.get("lifecycle_state") == "stable_contract"
                and evidence_stale
            )
            if mutation_due:
                mutation_due_count += 1
            if evidence_stale:
                stale_evidence_count += 1
            growth_ready = bool(lifecycle.get("growth_ready"))
            if growth_ready or mutation_due:
                growth_pressure_count += 1
            lifecycle_state = str(lifecycle.get("lifecycle_state") or "unknown")
            ecology_role = str(lifecycle.get("ecology_role") or "unknown")
            owner_hint = str(priority_summary.get("owner_hint") or "unknown")
            lifecycle_counts[lifecycle_state] = int(lifecycle_counts.get(lifecycle_state, 0) or 0) + 1
            role_counts[ecology_role] = int(role_counts.get(ecology_role, 0) or 0) + 1
            owner_counts[owner_hint] = int(owner_counts.get(owner_hint, 0) or 0) + 1
            origin_counts[origin] = int(origin_counts.get(origin, 0) or 0) + 1
            status_counts[latest_status] = int(status_counts.get(latest_status, 0) or 0) + 1
            item = {
                "file": file_name,
                "name": str(definition.get("name") or file_name),
                "origin": origin,
                "source": str(definition.get("source") or ""),
                "category": str(definition.get("category") or ""),
                "family_id": str(definition.get("family_id") or ""),
                "variation_id": str(definition.get("variation_id") or ""),
                "latest_status": latest_status,
                "latest_run_id": str(latest_report.get("run_id") or ""),
                "latest_report_path": str(latest_report.get("report_path") or ""),
                "evidence_age_hours": round(evidence_age_hours, 4) if evidence_age_hours is not None else None,
                "evidence_stale": evidence_stale,
                "lifecycle_state": lifecycle_state,
                "ecology_role": ecology_role,
                "growth_ready": growth_ready,
                "mutation_due": mutation_due,
                "growth_action": "mutate_or_revalidate_contract" if mutation_due else str(lifecycle.get("growth_action") or ""),
                "lifecycle_reason": str(lifecycle.get("lifecycle_reason") or ""),
                "reviewed_current_fingerprint": already_reviewed_current,
                **priority_summary,
            }
            items.append(item)

        items.sort(
            key=lambda item: (
                0 if bool(item.get("growth_ready")) or bool(item.get("mutation_due")) else 1,
                TEST_SESSION_CONTROL_SERVICE.generated_work_queue_status_rank(str(item.get("latest_status") or "never_run")),
                0 if bool(item.get("mutation_due")) else 1,
                -_safe_float(item.get("top_robustness"), 0.0),
                str(item.get("file") or ""),
            )
        )
        next_growth_item = next(
            (dict(item) for item in items if bool(item.get("growth_ready")) or bool(item.get("mutation_due"))),
            {},
        )
        if mutation_due_count > 0:
            ecology_status = "mutation_due"
        elif growth_pressure_count > 0:
            ecology_status = "growth_ready"
        elif int(role_counts.get("contract", 0) or 0) > 0:
            ecology_status = "stable_watch"
        elif int(role_counts.get("historical", 0) or 0) > 0:
            ecology_status = "historical_watch"
        elif not items:
            ecology_status = "empty"
        else:
            ecology_status = "needs_observation"
        return {
            "ok": True,
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(current_ts)),
            "ecology_status": ecology_status,
            "count": len(items),
            "growth_pressure_count": growth_pressure_count,
            "mutation_due_count": mutation_due_count,
            "stale_evidence_count": stale_evidence_count,
            "lifecycle_counts": lifecycle_counts,
            "ecology_role_counts": role_counts,
            "owner_counts": owner_counts,
            "origin_counts": origin_counts,
            "status_counts": status_counts,
            "contract_revalidate_hours": float(contract_revalidate_hours),
            "next_growth_item": next_growth_item,
            "items": items[: max(1, _safe_int(limit, 200))],
        }


TESTING_ECOLOGY_SERVICE = TestingEcologyService()
