from __future__ import annotations

import active_task_constraints as active_tasks
import followup_move_classifier as followup_moves
import re
from typing import Any, Callable, Optional
from services.supervisor_patterns import normalize_text as _normalize_text
from services.supervisor_probes import build_suggestions
from services.supervisor_probes import DEFAULT_SUPERVISOR_PROBES
from services.supervisor_probes import normalize_decision
from services.supervisor_probes import status_line
from services.supervisor_identity_rules import developer_profile_state_rule
from services.supervisor_identity_rules import identity_history_family_rule
from services.supervisor_identity_rules import last_question_recall_rule
from services.supervisor_identity_rules import name_origin_store_rule
from services.supervisor_identity_rules import open_probe_family_rule
from services.supervisor_identity_rules import profile_certainty_rule
from services.supervisor_identity_rules import rules_list_rule
from services.supervisor_identity_rules import session_fact_recall_rule
from services.supervisor_intent_rules import assistant_name_rule
from services.supervisor_intent_rules import capability_query_rule
from services.supervisor_intent_rules import developer_full_name_rule
from services.supervisor_intent_rules import developer_profile_rule
from services.supervisor_intent_rules import name_origin_rule
from services.supervisor_intent_rules import policy_domain_rule
from services.supervisor_intent_rules import self_identity_web_challenge_rule
from services.supervisor_intent_rules import session_summary_rule
from services.supervisor_intent_rules import smalltalk_rule
from services.supervisor_reflective_rules import apply_correction_rule
from services.supervisor_reflective_rules import reflective_retry_rule
from services.supervisor_routing_rules import location_name_rule
from services.supervisor_routing_rules import location_recall_rule
from services.supervisor_routing_rules import location_weather_rule
from services.supervisor_routing_rules import retrieval_followup_rule
from services.supervisor_routing_rules import self_location_rule
from services.supervisor_routing_rules import set_location_rule
from services.supervisor_routing_rules import store_fact_rule
from services.supervisor_routing_rules import weather_lookup_rule
from services.supervisor_routing_rules import web_research_family_rule
from services.supervisor_registry import DEFAULT_SUPERVISOR_RULE_SPECS
_manager_pending_action = active_tasks.manager_pending_action
_manager_retrieval_state = active_tasks.manager_retrieval_state


_uses_prior_reference = followup_moves.uses_prior_reference
_compact_followup_text = followup_moves.compact_followup_text
_looks_like_contextual_continuation = followup_moves.looks_like_contextual_continuation
_looks_like_contextual_followup = followup_moves.looks_like_contextual_followup
_extract_retrieval_result_index = followup_moves.extract_retrieval_result_index
_looks_like_retrieval_followup = followup_moves.looks_like_retrieval_followup
_looks_like_retrieval_continuation = followup_moves.looks_like_retrieval_continuation
_looks_like_shared_location_reference = followup_moves.looks_like_shared_location_reference
_classify_followup_move = followup_moves.classify_followup_move
_looks_like_retrieval_meta_question = followup_moves.looks_like_retrieval_meta_question


def _last_assistant_turn(turns: list[tuple[str, str]]) -> str:
    for role, text in reversed(list(turns or [])):
        if str(role or "").strip().lower() == "assistant":
            return _normalize_text(text)
    return ""


_extract_weather_followup_location_candidate = followup_moves.extract_weather_followup_location_candidate
_looks_like_explicit_location_declaration = followup_moves.looks_like_explicit_location_declaration


_EXPLICIT_INTENT_OWNERSHIP_RULES = frozenset({
    "store_fact",
    "web_research_family",
    "weather_lookup",
    "set_location",
    "capability_query",
    "policy_domain_query",
    "assistant_name",
    "self_identity_web_challenge",
})


_EXPLICIT_HANDLE_OWNERSHIP_RULES = frozenset({
    "reflective_retry",
    "profile_certainty",
    "identity_history_family",
    "open_probe_family",
    "session_fact_recall",
    "self_location",
    "location_recall",
    "retrieval_followup",
    "name_origin_store",
    "apply_correction",
    "rules_list",
    "last_question_recall",
})


def _result_is_explicitly_owned(rule_name: str, result: dict[str, Any], *, phase: str) -> bool:
    if not bool(result.get("handled")):
        return False
    if bool(result.get("required_safety_intercept")) or bool(result.get("required_policy_intercept")):
        return True
    if str(result.get("ownership") or "").strip().lower() == "explicit":
        return True

    normalized_rule_name = str(rule_name or "").strip()
    normalized_phase = str(phase or "handle").strip().lower()
    if normalized_phase == "intent":
        return normalized_rule_name in _EXPLICIT_INTENT_OWNERSHIP_RULES
    if normalized_phase == "handle":
        return normalized_rule_name in _EXPLICIT_HANDLE_OWNERSHIP_RULES
    return False


class Supervisor:
    def __init__(self) -> None:
        self.probes: dict[str, Callable[[dict], tuple[str, str]]] = dict(DEFAULT_SUPERVISOR_PROBES)
        self.rules: list[dict[str, Any]] = []
        for spec in DEFAULT_SUPERVISOR_RULE_SPECS:
            self.register_rule(
                str(spec.get("name") or ""),
                self._rule_handlers()[str(spec.get("name") or "")],
                priority=int(spec.get("priority", 100)),
                phases=tuple(spec.get("phases") or ("handle",)),
            )
        self.reset()

    @staticmethod
    def _rule_handlers() -> dict[str, Callable[..., dict[str, Any]]]:
        return {
            "reflective_retry": reflective_retry_rule,
            "profile_certainty": profile_certainty_rule,
            "identity_history_family": identity_history_family_rule,
            "open_probe_family": open_probe_family_rule,
            "session_fact_recall": session_fact_recall_rule,
            "developer_profile_state": developer_profile_state_rule,
            "last_question_recall": last_question_recall_rule,
            "self_location": self_location_rule,
            "rules_list": rules_list_rule,
            "location_recall": location_recall_rule,
            "location_name": location_name_rule,
            "location_weather": location_weather_rule,
            "retrieval_followup": retrieval_followup_rule,
            "name_origin_store": name_origin_store_rule,
            "apply_correction": apply_correction_rule,
            "smalltalk": smalltalk_rule,
            "store_fact": store_fact_rule,
            "web_research_family": web_research_family_rule,
            "weather_lookup": weather_lookup_rule,
            "set_location": set_location_rule,
            "capability_query": capability_query_rule,
            "policy_domain_query": policy_domain_rule,
            "assistant_name": assistant_name_rule,
            "self_identity_web_challenge": self_identity_web_challenge_rule,
            "name_origin": name_origin_rule,
            "developer_full_name": developer_full_name_rule,
            "developer_profile": developer_profile_rule,
            "session_summary": session_summary_rule,
        }

    def register_rule(
        self,
        name: str,
        rule: Callable[..., dict[str, Any]],
        *,
        priority: int = 100,
        phases: tuple[str, ...] = ("handle",),
    ) -> None:
        self.rules = [item for item in self.rules if str(item.get("name") or "") != str(name or "")]
        self.rules.append({
            "name": str(name or "").strip(),
            "rule": rule,
            "priority": int(priority),
            "phases": tuple(str(phase or "handle").strip().lower() for phase in phases if str(phase or "").strip()),
        })
        self.rules.sort(key=lambda item: (int(item.get("priority", 100)), str(item.get("name") or "")))

    def evaluate_rules(
        self,
        user_text: str,
        *,
        manager: Any = None,
        turns: Optional[list[tuple[str, str]]] = None,
        phase: str = "handle",
        entry_point: str = "",
    ) -> dict[str, Any]:
        normalized_user_text = str(user_text or "")
        normalized_manager = {} if manager is None else manager
        normalized_turns = list(turns or [])
        normalized_phase = str(phase or "handle").strip().lower() or "handle"
        normalized_entry_point = str(entry_point or "").strip().lower()
        low = _normalize_text(normalized_user_text)
        turn = len(normalized_turns)
        candidates: list[dict[str, Any]] = []
        for item in self.rules:
            phases = tuple(item.get("phases") or ())
            if normalized_phase not in phases:
                continue
            rule_name = str(item.get("name") or "")
            try:
                result = item["rule"](
                    normalized_user_text,
                    low,
                    normalized_manager,
                    turn,
                    turns=list(normalized_turns),
                    phase=normalized_phase,
                    entry_point=normalized_entry_point,
                )
            except Exception as exc:
                result = {"handled": False, "rule_error": str(exc)}
            if not isinstance(result, dict):
                continue
            explicitly_owned = _result_is_explicitly_owned(rule_name, result, phase=normalized_phase)
            candidate = {
                "rule_name": rule_name,
                "priority": int(item.get("priority", 100)),
                "handled": bool(result.get("handled")) and explicitly_owned,
            }
            action = str(result.get("action") or "").strip()
            if action:
                candidate["action"] = action
            intent = str(result.get("intent") or "").strip()
            if intent:
                candidate["intent"] = intent
            if bool(result.get("handled")) and not explicitly_owned:
                candidate["ownership_declined"] = True
            if str(result.get("rewrite_text") or "").strip():
                candidate["rewrite"] = True
            if isinstance(result.get("state_update"), dict):
                candidate["state_update"] = True
            rule_error = str(result.get("rule_error") or "").strip()
            if rule_error:
                candidate["rule_error"] = rule_error[:160]
            candidates.append(candidate)
            if (
                explicitly_owned
                or str(result.get("rewrite_text") or "").strip()
                or isinstance(result.get("state_update"), dict)
            ):
                payload = dict(result)
                payload["phase"] = normalized_phase
                payload["candidates"] = list(candidates)
                if str(payload.get("rule_name") or "").strip():
                    payload["matched_rule_name"] = str(payload.get("rule_name") or "").strip()
                payload["rule_name"] = rule_name
                payload["priority"] = int(item.get("priority", 100))
                if not explicitly_owned:
                    payload["handled"] = False
                return payload
        return {"handled": False, "phase": normalized_phase, "candidates": candidates}

    def reset(self) -> None:
        self.last_decision: dict[str, dict] = {}
        self.last_decision_by_session: dict[str, dict] = {}
        self.override_state_by_session: dict[str, dict[str, tuple[str, ...]]] = {}

    def process_turn(
        self,
        *,
        entry_point: str,
        session_id: str,
        session_summary: Optional[dict],
        current_decision: Optional[dict],
        recent_records: Optional[list[dict]] = None,
        recent_reflections: Optional[list[dict]] = None,
    ) -> dict:
        summary = dict(session_summary or {})
        decision = normalize_decision(
            entry_point,
            session_id,
            summary,
            current_decision or {},
            normalize_text_fn=_normalize_text,
        )
        context = {
            "entry_point": decision["entry_point"],
            "session_id": decision["session_id"],
            "session_summary": summary,
            "decision": decision,
            "recent_records": list(recent_records or []),
            "recent_reflections": list(recent_reflections or []),
            "previous_input_decision": self.last_decision.get(decision["parity_key"]),
            "previous_session_decision": self.last_decision_by_session.get(decision["session_id"]),
            "other_entry_overrides": dict(self.override_state_by_session.get(decision["session_id"], {})),
        }
        findings: list[dict] = []
        for name, probe in self.probes.items():
            try:
                status, message = probe(context)
            except Exception as exc:
                status, message = "yellow", f"Probe error: {exc}"
            clean_status = str(status or "green").strip().lower()
            if clean_status == "green":
                continue
            findings.append({
                "name": name,
                "status": clean_status,
                "message": str(message or "").strip(),
            })

        suggestions = build_suggestions(context, findings)

        self._remember(decision)
        issue_count = len(findings)
        summary_text = "All green" if issue_count == 0 else f"{issue_count} issue{'s' if issue_count != 1 else ''} detected"
        return {
            "entry_point": decision["entry_point"],
            "session_id": decision["session_id"],
            "probe_summary": summary_text,
            "reply_contract": str(decision.get("reply_contract") or ""),
            "reply_outcome_kind": str(decision.get("reply_outcome_kind") or ""),
            "turn_acts": list(decision.get("turn_acts") or []),
            "probe_results": [status_line(item["name"], item["status"], item["message"]) for item in findings],
            "probe_findings": findings,
            "probe_status_counts": {
                "green": max(0, len(self.probes) - issue_count),
                "yellow": sum(1 for item in findings if item["status"] == "yellow"),
                "red": sum(1 for item in findings if item["status"] == "red"),
            },
            "suggestions": suggestions,
            "headline": f"Probe summary: {summary_text}",
        }

    def _remember(self, decision: dict) -> None:
        parity_key = str(decision.get("parity_key") or "")
        if parity_key:
            self.last_decision[parity_key] = dict(decision)
        session_id = str(decision.get("session_id") or "default")
        self.last_decision_by_session[session_id] = dict(decision)
        entry_point = str(decision.get("entry_point") or "unknown")
        self.override_state_by_session.setdefault(session_id, {})[entry_point] = tuple(decision.get("overrides_active") or [])
