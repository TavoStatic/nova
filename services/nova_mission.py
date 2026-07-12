from __future__ import annotations

import time
from typing import Any

from services.nova_mission_owner_verdicts import build_mission_truth_gate


def _as_dict(value: Any) -> dict:
    return dict(value) if isinstance(value, dict) else {}


def _as_list(value: Any) -> list:
    return list(value) if isinstance(value, list) else []


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _text(value: Any, limit: int = 220) -> str:
    return str(value or "").strip()[:limit]


def _normalize_action_names(values: Any) -> set[str]:
    if not isinstance(values, list):
        return set()
    return {_text(item, 120) for item in values if _text(item, 120)}


class NovaMissionService:
    """Build a compact mission snapshot for each autonomy cycle."""

    DEFAULT_POLICY = {
        "enabled": True,
        "mode": "steady_state_guard",
        "objective": "hold_steady_and_surface_fresh_gaps",
        "release_stale_ready_is_pressure": False,
        "subconscious_triage_is_pressure": False,
        "generated_queue_backlog_is_pressure": False,
        "require_core_gate_for_green": True,
        "ingestion_suppress_ambient_on_hold": True,
        "sustained_watch_cycles": 6,
        "hold_block_actions": [
            "active_work_tree_run_next",
            "generated_queue_run_next",
            "generated_queue_investigate",
            "pulse_status",
            "codegen_run",
            "leah_build_run_next",
        ],
        "hold_allow_actions": [
            "patch_queue_run_next",
            "guard_start",
            "autonomy_maintenance_start",
        ],
        "hold_allow_active_work_tools": [
            "core_thinning",
        ],
    }

    MODE_PROFILES: dict[str, dict[str, Any]] = {
        "steady_state_guard": {
            "objective": "hold_steady_and_surface_fresh_gaps",
            "default_action_on_ready": "hold",
        },
        "observe_only": {
            "objective": "observe_without_autonomous_execution",
            "default_action_on_ready": "hold",
            "generated_queue_backlog_is_pressure": False,
            "subconscious_triage_is_pressure": False,
        },
        "recovery": {
            "objective": "recover_runtime_and_posture_before_expansion",
            "default_action_on_ready": "investigate",
            "generated_queue_backlog_is_pressure": False,
            "subconscious_triage_is_pressure": False,
        },
        "promote_layer": {
            "objective": "promote_one_layer_capability_after_core_gate",
            "default_action_on_ready": "investigate",
            "require_core_gate_for_green": True,
        },
        "operator_focus": {
            "objective": "surface_operator_holds_without_autonomous_noise",
            "default_action_on_ready": "hold",
            "generated_queue_backlog_is_pressure": False,
            "subconscious_triage_is_pressure": False,
        },
    }

    TRUTH_VALIDATION_BLOCKERS = frozenset(
        {
            "validation_truth_missing",
            "regression_stale",
        }
    )
    ACTIVE_WORK_EVIDENCE_BLOCKERS = frozenset(
        {
            "validation_truth_missing",
            "regression_stale",
            "generated_queue_untested",
            "release_truth_stale",
        }
    )
    BASE_EVIDENCE_BLOCKERS = frozenset(
        {
            "validation_truth_missing",
            "regression_stale",
            "release_truth_stale",
        }
    )
    BLOCKER_DEFAULT_OWNERS = {
        "generated_queue_untested": "generated_queue",
        "core_gate_release_drift": "layer_maturity",
    }
    TOOL_HOLD_ALLOWANCE_BLOCKERS = {
        "core_thinning": frozenset({("layer_maturity", "core_gate_release_drift")}),
    }
    GENERATED_QUEUE_REFRESH_ALLOWED_BLOCKERS = frozenset(
        {
            ("generated_queue", "generated_queue_untested"),
            ("layer_maturity", "core_gate_release_drift"),
        }
    )

    @staticmethod
    def _mission_policy(policy_snapshot: dict | None) -> dict:
        policy = _as_dict(policy_snapshot)
        mission = _as_dict(policy.get("mission"))
        merged = dict(NovaMissionService.DEFAULT_POLICY)
        merged.update(mission)
        mode = _text(merged.get("mode"), 80).lower() or "steady_state_guard"
        profile = dict(NovaMissionService.MODE_PROFILES.get(mode, {}))
        for key, value in profile.items():
            if key == "objective" and not _text(mission.get("objective"), 200):
                merged["objective"] = _text(value, 200)
            elif key.startswith("default_"):
                continue
            elif key not in mission:
                merged[key] = value
        return merged

    @classmethod
    def execution_contract(cls, policy_snapshot: dict | None) -> dict[str, Any]:
        policy = cls._mission_policy(policy_snapshot)
        block = _normalize_action_names(policy.get("hold_block_actions")) or _normalize_action_names(
            cls.DEFAULT_POLICY["hold_block_actions"]
        )
        allow = _normalize_action_names(policy.get("hold_allow_actions")) or _normalize_action_names(
            cls.DEFAULT_POLICY["hold_allow_actions"]
        )
        allow_active_tools = _normalize_action_names(policy.get("hold_allow_active_work_tools")) or _normalize_action_names(
            cls.DEFAULT_POLICY["hold_allow_active_work_tools"]
        )
        return {
            "hold_block_actions": sorted(block),
            "hold_allow_actions": sorted(allow),
            "hold_allow_active_work_tools": sorted(allow_active_tools),
        }

    @classmethod
    def _blocker_codes(cls, values: Any) -> set[str]:
        codes: set[str] = set()
        for item in _as_list(values):
            if isinstance(item, dict):
                code = _text(_as_dict(item).get("code"), 120)
            else:
                code = _text(item, 120)
            if code:
                codes.add(code)
        return codes

    @classmethod
    def _blocker_records(cls, values: Any) -> list[dict[str, str]]:
        records: list[dict[str, str]] = []
        for item in _as_list(values):
            if isinstance(item, dict):
                payload = _as_dict(item)
                code = _text(payload.get("code"), 120)
                if not code:
                    continue
                records.append(
                    {
                        "owner": _text(payload.get("owner"), 80),
                        "code": code,
                        "source": _text(payload.get("source"), 160),
                    }
                )
            else:
                code = _text(item, 120)
                if code:
                    records.append({"owner": "", "code": code, "source": ""})
        return records

    @classmethod
    def active_work_evidence_current(cls, mission_snapshot: dict | None) -> bool:
        mission = _as_dict(mission_snapshot)
        if _as_bool(mission.get("truth_ready"), False) or _as_bool(mission.get("green_cycle"), False):
            return True
        if not cls._base_evidence_pillars_current(mission):
            return False
        if _as_int(mission.get("generated_queue_untested_count"), 0) > 0:
            return False

        truth_blockers = cls._blocker_codes(mission.get("truth_blockers"))
        green_blockers = cls._blocker_codes(mission.get("green_blockers"))
        if truth_blockers & cls.ACTIVE_WORK_EVIDENCE_BLOCKERS:
            return False
        if green_blockers & cls.ACTIVE_WORK_EVIDENCE_BLOCKERS:
            return False
        return True

    @classmethod
    def _base_evidence_pillars_current(cls, mission_snapshot: dict | None) -> bool:
        mission = _as_dict(mission_snapshot)
        if not _as_bool(mission.get("validation_fresh"), False):
            return False
        if not _as_bool(mission.get("regression_current"), False):
            return False
        if not _as_bool(mission.get("release_truth_current"), False):
            return False

        truth_blockers = cls._blocker_codes(mission.get("truth_blockers"))
        green_blockers = cls._blocker_codes(mission.get("green_blockers"))
        if truth_blockers & cls.BASE_EVIDENCE_BLOCKERS:
            return False
        if green_blockers & cls.BASE_EVIDENCE_BLOCKERS:
            return False
        return True

    @classmethod
    def _mission_green_blocker_records(cls, mission_snapshot: dict | None) -> list[dict[str, str]]:
        mission = _as_dict(mission_snapshot)
        green_records = cls._blocker_records(mission.get("green_blockers"))
        if green_records:
            return green_records
        return cls._blocker_records(mission.get("truth_blockers"))

    @classmethod
    def _mission_green_blocker_pairs(cls, mission_snapshot: dict | None) -> list[tuple[str, str]]:
        pairs: list[tuple[str, str]] = []
        for blocker in cls._mission_green_blocker_records(mission_snapshot):
            code = _text(blocker.get("code"), 120)
            if not code:
                continue
            owner = _text(blocker.get("owner"), 80) or cls.BLOCKER_DEFAULT_OWNERS.get(code, "")
            pairs.append((owner, code))
        return pairs

    @classmethod
    def _release_drift_is_core_gate_only(cls, mission_snapshot: dict | None) -> bool:
        mission = _as_dict(mission_snapshot)
        core_gate = _as_dict(mission.get("core_gate"))
        if not core_gate:
            return False
        if not _as_bool(core_gate.get("drift_blocked"), False):
            return False
        if _as_list(core_gate.get("missing_roots")):
            return False
        if not _as_bool(mission.get("release_truth_current"), False):
            return False

        release_evidence: dict[str, Any] = {}
        for verdict in _as_list(mission.get("owner_verdicts")):
            payload = _as_dict(verdict)
            if _text(payload.get("owner"), 80) == "release":
                release_evidence = _as_dict(payload.get("evidence"))
                break
        if release_evidence:
            if not _as_bool(release_evidence.get("runtime_drift_tolerated"), False):
                return False
            if not (
                _as_bool(release_evidence.get("runtime_drift_expected"), False)
                or _as_bool(release_evidence.get("latest_source_changed_after_build"), False)
                or _as_bool(release_evidence.get("suppress_closure_inventory_signals"), False)
            ):
                return False
        return True

    @classmethod
    def generated_queue_validation_allowed_during_hold(cls, mission_snapshot: dict | None) -> bool:
        mission = _as_dict(mission_snapshot)
        if not cls._base_evidence_pillars_current(mission):
            return False
        blocker_codes = cls._blocker_codes(mission.get("truth_blockers")) | cls._blocker_codes(
            mission.get("green_blockers")
        )
        generated_queue_truth_missing = bool(
            _as_int(mission.get("generated_queue_untested_count"), 0) > 0
            or "generated_queue_untested" in blocker_codes
        )
        if not generated_queue_truth_missing:
            return False
        blocker_pairs = cls._mission_green_blocker_pairs(mission)
        if not blocker_pairs:
            return True
        for pair in blocker_pairs:
            if pair not in cls.GENERATED_QUEUE_REFRESH_ALLOWED_BLOCKERS:
                return False
            if pair == ("layer_maturity", "core_gate_release_drift") and not cls._release_drift_is_core_gate_only(
                mission
            ):
                return False
        return True

    @classmethod
    def active_work_tool_allowed_during_hold(cls, tool: str, mission_snapshot: dict | None) -> bool:
        clean_tool = _text(tool, 120)
        if not clean_tool:
            return False
        allowed_blockers = cls.TOOL_HOLD_ALLOWANCE_BLOCKERS.get(clean_tool)
        if not allowed_blockers:
            return False
        if not cls.active_work_evidence_current(mission_snapshot):
            return False
        blocker_records = cls._mission_green_blocker_records(mission_snapshot)
        if not blocker_records:
            return True
        for blocker in blocker_records:
            pair = (_text(blocker.get("owner"), 80), _text(blocker.get("code"), 120))
            if pair not in allowed_blockers:
                return False
            if pair == ("layer_maturity", "core_gate_release_drift") and not cls._release_drift_is_core_gate_only(
                mission_snapshot
            ):
                return False
        return True

    @classmethod
    def hold_blocks_legacy_execution(cls, mission_snapshot: dict | None) -> bool:
        mission = _as_dict(mission_snapshot)
        if not _as_bool(mission.get("enabled"), True):
            return False
        mode = _text(mission.get("mode"), 80).lower()
        if mode not in {"steady_state_guard", "observe_only", "operator_focus"}:
            return False
        return _text(mission.get("action"), 40).lower() == "hold"

    @classmethod
    def hold_blocks_action(
        cls,
        action_type: str,
        *,
        mission_snapshot: dict | None,
        policy_snapshot: dict | None = None,
        action_context: dict | None = None,
    ) -> bool:
        action = _text(action_type, 120)
        if not action:
            return False
        contract = cls.execution_contract(policy_snapshot)
        allow = set(contract.get("hold_allow_actions") or [])
        if action in allow:
            return False
        if not cls.hold_blocks_legacy_execution(mission_snapshot):
            return False
        block = set(contract.get("hold_block_actions") or [])
        if action == "active_work_tree_run_next" and action in block:
            context = _as_dict(action_context)
            tool = _text(context.get("recommended_tool") or context.get("tool"), 120)
            allow_tools = set(contract.get("hold_allow_active_work_tools") or [])
            mission = _as_dict(mission_snapshot)
            if tool in allow_tools and cls.active_work_tool_allowed_during_hold(tool, mission):
                return False
        if action == "generated_queue_run_next" and action in block:
            if cls.generated_queue_validation_allowed_during_hold(mission_snapshot):
                return False
        return action in block

    @classmethod
    def ingestion_suppresses_ambient_governance(cls, mission_snapshot: dict | None, policy_snapshot: dict | None = None) -> bool:
        policy = cls._mission_policy(policy_snapshot)
        if not _as_bool(policy.get("ingestion_suppress_ambient_on_hold"), True):
            return False
        mission = _as_dict(mission_snapshot)
        if not cls.hold_blocks_legacy_execution(mission):
            return False
        return _as_int(mission.get("actionable_fresh_gap_signal_count"), 0) <= 0

    @staticmethod
    def _release_stale_ready_count(work_tree_snapshot: dict | None) -> int:
        snapshot = _as_dict(work_tree_snapshot)
        count = 0
        for item in _as_list(snapshot.get("branches")):
            branch = _as_dict(item)
            status = _text(branch.get("status"), 80).lower()
            if status != "ready":
                continue
            title = _text(branch.get("title"), 240).lower()
            task_title = _text(branch.get("task_title"), 240).lower()
            if (
                "release-stale" in title
                or "release stale" in title
                or "validation outcome is missing" in title
                or "release-stale" in task_title
                or "release stale" in task_title
                or "validation outcome is missing" in task_title
            ):
                count += 1
        return count

    @classmethod
    def _evaluate_truth_gate(
        cls,
        *,
        truth_evidence: dict | None,
        queue: dict,
        policy: dict,
    ) -> dict[str, Any]:
        return build_mission_truth_gate(
            truth_evidence=truth_evidence,
            queue=queue,
            policy=policy,
        )

    @classmethod
    def append_history(cls, state: dict | None, mission_snapshot: dict | None, *, limit: int = 48) -> list[dict]:
        if not isinstance(state, dict):
            return []
        current_state = state
        mission = _as_dict(mission_snapshot)
        if not mission:
            return list(current_state.get("nova_mission_history") or [])
        row = {
            "snapshot_ts_utc": _text(mission.get("snapshot_ts_utc"), 80),
            "status": _text(mission.get("status"), 40),
            "action": _text(mission.get("action"), 40),
            "green_cycle": _as_bool(mission.get("green_cycle"), False),
            "truth_ready": _as_bool(mission.get("truth_ready"), False),
            "truth_blockers": list(mission.get("truth_blockers") or []),
            "owner_blockers": list(mission.get("owner_blockers") or []),
            "headline": _text(mission.get("headline"), 220),
        }
        history = [
            dict(item)
            for item in list(current_state.get("nova_mission_history") or [])
            if isinstance(item, dict)
        ]
        if history and history[-1].get("snapshot_ts_utc") == row.get("snapshot_ts_utc"):
            history[-1] = row
        else:
            history.append(row)
        current_state["nova_mission_history"] = history[-max(1, int(limit or 48)) :]
        sustained_threshold = _as_int(mission.get("sustained_watch_cycles"), 6)
        watch_streak = 0
        for item in reversed(history):
            if _text(item.get("status"), 40).lower() == "watch":
                watch_streak += 1
            else:
                break
        current_state["nova_mission_watch_streak"] = watch_streak
        current_state["nova_mission_sustained_watch"] = bool(
            watch_streak >= sustained_threshold and not _as_bool(mission.get("green_cycle"), False)
        )
        return list(current_state["nova_mission_history"])

    def build_snapshot(
        self,
        *,
        work_tree_snapshot: dict | None,
        steward_posture: dict | None,
        queue_pressure: dict | None,
        runtime_guard_status: dict | None,
        triage_hints: dict | None,
        policy_snapshot: dict | None,
        truth_evidence: dict | None = None,
    ) -> dict:
        policy = self._mission_policy(policy_snapshot)
        enabled = _as_bool(policy.get("enabled"), True)
        mode = _text(policy.get("mode"), 80) or "steady_state_guard"
        objective = _text(policy.get("objective"), 200) or "hold_steady_and_surface_fresh_gaps"
        release_stale_ready_is_pressure = _as_bool(policy.get("release_stale_ready_is_pressure"), False)
        subconscious_triage_is_pressure = _as_bool(policy.get("subconscious_triage_is_pressure"), False)
        generated_queue_backlog_is_pressure = _as_bool(policy.get("generated_queue_backlog_is_pressure"), False)

        posture = _as_dict(steward_posture)
        queue = _as_dict(queue_pressure)
        runtime = _as_dict(runtime_guard_status)
        hints = _as_dict(triage_hints)

        posture_band = _text(posture.get("posture_band"), 40).lower()
        queue_band = _text(queue.get("pressure_band"), 40).lower() or "low"
        guard_running = _as_bool(runtime.get("guard_running"), False)
        core_running = _as_bool(runtime.get("core_running"), False)
        webui_running = _as_bool(runtime.get("webui_running"), False)
        runtime_ready = bool(guard_running and core_running and webui_running)

        critical_alerts = _as_int(posture.get("critical_alerts"), 0)
        work_tree = _as_dict(work_tree_snapshot)
        release_stale_ready_count = _as_int(work_tree.get("release_stale_ready_count"), -1)
        if release_stale_ready_count < 0:
            release_stale_ready_count = self._release_stale_ready_count(work_tree_snapshot)
        latent_root_signal_count = _as_int(work_tree.get("latent_root_signal_count"), 0)
        blocked_count = _as_int(work_tree.get("blocked_count"), 0)
        operator_hold_count = _as_int(work_tree.get("operator_hold_count"), 0)
        non_operator_blocked_count = max(0, blocked_count - operator_hold_count)
        triage_approved = _as_int(hints.get("approved_review_count"), 0)
        high_priority = _as_int(queue.get("high_priority_count"), 0)
        generated_actionable = _as_int(queue.get("generated_actionable_count"), high_priority)
        patch_ready = _as_int(queue.get("patch_ready_count"), 0)

        truth_gate = self._evaluate_truth_gate(truth_evidence=truth_evidence, queue=queue, policy=policy)
        truth_ready = _as_bool(truth_gate.get("truth_ready"), False)
        truth_blockers = list(truth_gate.get("truth_blockers") or [])
        owner_verdicts = [
            dict(item)
            for item in list(truth_gate.get("owner_verdicts") or [])
            if isinstance(item, dict)
        ]
        owner_blockers = [
            dict(item)
            for item in list(truth_gate.get("owner_blockers") or [])
            if isinstance(item, dict)
        ]
        green_blockers = [
            dict(item)
            for item in list(truth_gate.get("green_blockers") or [])
            if isinstance(item, dict)
        ]
        core_gate = _as_dict(truth_gate.get("core_gate"))

        ambient_triage_count = 0 if subconscious_triage_is_pressure else max(0, triage_approved)
        ambient_generated_queue_count = 0 if generated_queue_backlog_is_pressure else max(0, generated_actionable)
        ambient_gap_signal_count = ambient_triage_count + ambient_generated_queue_count

        actionable_triage_count = triage_approved if subconscious_triage_is_pressure else 0
        actionable_queue_count = high_priority if generated_queue_backlog_is_pressure else max(0, patch_ready)
        actionable_fresh_gap_signal_count = max(
            0,
            latent_root_signal_count
            + actionable_triage_count
            + actionable_queue_count
            + non_operator_blocked_count,
        )
        if mode == "operator_focus" and operator_hold_count > 0:
            actionable_fresh_gap_signal_count = max(actionable_fresh_gap_signal_count, operator_hold_count)
        fresh_gap_signal_count = actionable_fresh_gap_signal_count

        ops_ready = bool(
            posture_band == "green"
            and runtime_ready
            and critical_alerts == 0
            and actionable_fresh_gap_signal_count == 0
        )
        profile = self.MODE_PROFILES.get(mode, {})
        default_ready_action = _text(profile.get("default_action_on_ready"), 40).lower() or "hold"

        green_cycle = bool(enabled and ops_ready and truth_ready)

        needs_investigation = bool(
            not enabled
            or mode == "recovery"
            or posture_band != "green"
            or not runtime_ready
            or critical_alerts > 0
            or actionable_fresh_gap_signal_count > 0
            or (mode == "promote_layer" and not _as_bool(core_gate.get("ok"), False))
        )

        if needs_investigation:
            action = "investigate"
            status = "watch"
        elif mode in {"steady_state_guard", "observe_only", "operator_focus"}:
            action = "hold"
            if truth_ready:
                status = "quiet_hold" if ambient_gap_signal_count > 0 else "green"
            elif any(code in self.TRUTH_VALIDATION_BLOCKERS for code in truth_blockers):
                status = "validation_required"
            else:
                status = "validation_required"
        else:
            action = default_ready_action if truth_ready else "investigate"
            status = "watch" if action == "investigate" else ("green" if truth_ready else "validation_required")

        if green_cycle:
            status = "quiet_hold" if ambient_gap_signal_count > 0 else "green"
            if ambient_gap_signal_count > 0:
                headline = "steady governance cycle; ambient gap signals remain non-pressure"
            else:
                headline = "steady governance cycle; fresh validation and release truth confirmed"
        elif action == "hold" and status == "validation_required":
            headline = "mission hold: validation or release truth is not current"
            if truth_blockers:
                headline += f" ({', '.join(truth_blockers)})"
        elif action == "hold" and status == "quiet_hold":
            headline = "mission quiet hold: no actionable gaps; ambient signals remain visible"
        elif action == "hold":
            headline = "mission hold: steady-state guard without green health claim"
        else:
            headline = "mission watch: evaluate fresh gap pressure"
        if release_stale_ready_count > 0 and not release_stale_ready_is_pressure:
            headline += "; release-stale ready remains non-pressure"

        contract = self.execution_contract(policy_snapshot)
        return {
            "enabled": enabled,
            "mode": mode,
            "objective": objective,
            "status": status,
            "action": action,
            "green_cycle": green_cycle,
            "headline": headline,
            "truth_ready": truth_ready,
            "truth_blockers": truth_blockers,
            "owner_verdicts": owner_verdicts,
            "owner_blockers": owner_blockers,
            "green_blockers": green_blockers,
            "active_work_evidence_current": self.active_work_evidence_current(
                {
                    "truth_ready": truth_ready,
                    "green_cycle": green_cycle,
                    "validation_fresh": _as_bool(truth_gate.get("validation_fresh"), False),
                    "regression_current": _as_bool(truth_gate.get("regression_current"), False),
                    "release_truth_current": _as_bool(truth_gate.get("release_truth_current"), False),
                    "generated_queue_untested_count": _as_int(
                        truth_gate.get("generated_queue_untested_count"),
                        0,
                    ),
                    "truth_blockers": truth_blockers,
                    "green_blockers": green_blockers,
                }
            ),
            "blocking_owner_count": len(
                {
                    _text(item.get("owner"), 80)
                    for item in green_blockers
                    if _text(item.get("owner"), 80)
                }
            ),
            "validation_fresh": _as_bool(truth_gate.get("validation_fresh"), False),
            "regression_current": _as_bool(truth_gate.get("regression_current"), False),
            "release_truth_current": _as_bool(truth_gate.get("release_truth_current"), False),
            "core_gate_ok": _as_bool(truth_gate.get("core_gate_ok"), False),
            "core_gate": core_gate,
            "core_gate_source": _text(truth_gate.get("core_gate_source"), 160),
            "core_gate_missing_roots": list(core_gate.get("missing_roots") or []),
            "generated_queue_untested_count": _as_int(truth_gate.get("generated_queue_untested_count"), 0),
            "release_stale_ready_is_pressure": release_stale_ready_is_pressure,
            "release_stale_ready_count": release_stale_ready_count,
            "subconscious_triage_is_pressure": subconscious_triage_is_pressure,
            "generated_queue_backlog_is_pressure": generated_queue_backlog_is_pressure,
            "ambient_gap_signal_count": ambient_gap_signal_count,
            "blocked_count": blocked_count,
            "operator_hold_count": operator_hold_count,
            "non_operator_blocked_count": non_operator_blocked_count,
            "actionable_fresh_gap_signal_count": actionable_fresh_gap_signal_count,
            "fresh_gap_signal_count": fresh_gap_signal_count,
            "posture_band": posture_band,
            "queue_pressure_band": queue_band,
            "effective_queue_pressure_band": queue_band,
            "runtime_ready": runtime_ready,
            "ops_ready": ops_ready,
            "ingestion_suppress_ambient_on_hold": _as_bool(policy.get("ingestion_suppress_ambient_on_hold"), True),
            "hold_block_actions": list(contract.get("hold_block_actions") or []),
            "hold_allow_actions": list(contract.get("hold_allow_actions") or []),
            "hold_allow_active_work_tools": list(contract.get("hold_allow_active_work_tools") or []),
            "sustained_watch_cycles": _as_int(policy.get("sustained_watch_cycles"), 6),
            "snapshot_ts_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "source": "services.nova_mission",
            "source_freshness_sec": 0,
        }


NOVA_MISSION_SERVICE = NovaMissionService()
