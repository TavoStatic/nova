from __future__ import annotations

from collections import Counter
import re
from typing import Any, Callable, Optional


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def _status_line(name: str, status: str, message: str) -> str:
    label = str(status or "green").upper()
    clean = str(message or "").strip()
    return f"{label}: {name}" if not clean else f"{label}: {name} - {clean}"


def _manager_active_subject(manager: Any) -> str:
    if manager is None:
        return ""
    try:
        active_subject = getattr(manager, "active_subject", None)
        if callable(active_subject):
            return str(active_subject() or "").strip()
    except Exception:
        return ""
    if isinstance(manager, dict):
        kind = str(manager.get("kind") or "").strip()
        subject = str(manager.get("subject") or "").strip()
        if kind and subject:
            return f"{kind}:{subject}"
        return kind
    return ""


def _looks_like_reflective_retry(low: str) -> bool:
    if not low:
        return False
    cues = (
        "if you think for a bit",
        "think for a bit",
        "keep trying",
        "keep thinking",
        "think about it",
        "look at this session",
        "look at this conversation",
        "big clue",
        "almost there",
        "read what you're saying",
        "read what your saying",
        "are you sure because i just gave you",
    )
    return any(cue in low for cue in cues)


def _looks_like_self_location(low: str) -> bool:
    if not low:
        return False
    triggers = (
        "where is nova",
        "where are you",
        "your location",
        "what is your location",
        "what is your current location",
        "what is your current physical location",
        "where are you located",
        "where is nova located",
    )
    return any(trigger in low for trigger in triggers)


def _looks_like_profile_certainty_followup(low: str) -> bool:
    if not low:
        return False
    return any(phrase in low for phrase in (
        "are you sure that is all",
        "is that all the information",
        "is that all you know",
        "are you sure that's all",
        "are you sure that is all the information",
    ))


def _looks_like_developer_profile_query(low: str) -> bool:
    if not low:
        return False
    creator_cues = (
        "who is your developer",
        "who's your developer",
        "who is your creator",
        "who's your creator",
        "who created you",
        "your creator",
        "is gus your creator",
        "so gus is your creator",
        "is gustavo your creator",
        "is he your creator",
        "creator is gus",
        "creator is gustavo",
    )
    if any(cue in low for cue in creator_cues):
        return True
    if not any(token in low for token in ("developer", "gus", "gustavo")):
        return False
    cues = (
        "who is",
        "who's",
        "what do you know",
        "what else",
        "tell me about",
        "about your developer",
        "about gus",
        "about gustavo",
        "how did",
        "created you",
        "developed you",
        "built you",
    )
    return any(cue in low for cue in cues)


def _mentions_location_phrase(low: str) -> bool:
    if not low:
        return False
    return any(token in low for token in (
        "location",
        "locaiton",
        "physical location",
        "physical locaiton",
    ))


def _extract_last_user_question(turns: list[tuple[str, str]], current_text: str) -> str:
    target = _normalize_text(current_text)
    for role, text in reversed(list(turns or [])[:-1]):
        if str(role or "").strip().lower() != "user":
            continue
        candidate = str(text or "").strip()
        if not candidate:
            continue
        normalized = _normalize_text(candidate)
        if normalized == target:
            continue
        if "?" in candidate or normalized.startswith((
            "what ", "who ", "why ", "how ", "when ", "where ", "which ",
            "do ", "does ", "did ", "can ", "could ", "would ", "will ", "are ", "is ",
        )):
            return candidate
    return ""


def reflective_retry_rule(
    user_text: str,
    low: str,
    manager: Any,
    turn: int,
    *,
    turns: Optional[list[tuple[str, str]]] = None,
    phase: str = "handle",
    entry_point: str = "",
) -> dict[str, Any]:
    del turn, entry_point
    if not _looks_like_reflective_retry(low):
        return {"handled": False}

    active_subject = _manager_active_subject(manager)
    if phase == "handle":
        if (
            active_subject in {"identity_profile:developer", "developer_identity:developer"}
            and _mentions_location_phrase(low)
            and any(token in low for token in ("gus", "gustavo", "his", "developer", "creator"))
        ):
            return {
                "handled": True,
                "action": "developer_location",
                "continuation": True,
                "ledger_stage": "developer_location",
                "intent": "developer_location",
                "grounded": True,
            }
        return {"handled": False}

    if _mentions_location_phrase(low) and any(token in low for token in ("gus", "gustavo", "his", "developer", "creator")):
        return {
            "handled": False,
            "rewrite_text": str(user_text or "").strip(),
            "analysis_reason": "reflective_retry_location_hint",
        }

    prior_question = _extract_last_user_question(list(turns or []), user_text)
    if prior_question:
        return {
            "handled": False,
            "rewrite_text": prior_question,
            "analysis_reason": "reflective_retry_prior_question",
        }
    return {"handled": False}


def self_location_rule(
    user_text: str,
    low: str,
    manager: Any,
    turn: int,
    *,
    turns: Optional[list[tuple[str, str]]] = None,
    phase: str = "handle",
    entry_point: str = "",
) -> dict[str, Any]:
    del user_text, manager, turn, turns, entry_point
    if phase != "handle" or not _looks_like_self_location(low):
        return {"handled": False}
    return {
        "handled": True,
        "action": "self_location",
        "next_state": {"kind": "location_recall"},
        "ledger_stage": "self_location",
        "intent": "self_location",
        "grounded": True,
    }


def name_origin_store_rule(
    user_text: str,
    low: str,
    manager: Any,
    turn: int,
    *,
    turns: Optional[list[tuple[str, str]]] = None,
    phase: str = "handle",
    entry_point: str = "",
) -> dict[str, Any]:
    del manager, turn, turns, entry_point
    if phase != "handle":
        return {"handled": False}

    raw = str(user_text or "").strip()
    trigger = (
        "remember this nova" in low
        or "story behind your name" in low
        or "story behing your name" in low
        or "gus gave you your name" in low
        or "gus named you" in low
        or low.startswith("remember this")
    )
    if not trigger:
        return {"handled": False}

    store_text = raw
    if "gus gave you your name" in low and "remember this" not in low:
        store_text = "Gus gave me the name Nova."
    elif "gus named you" in low and "remember this" not in low:
        store_text = raw if len(raw) >= 30 else "Gus named me Nova."

    return {
        "handled": True,
        "action": "name_origin_store",
        "store_text": store_text,
        "ledger_stage": "name_origin",
        "intent": "name_origin_store",
        "grounded": True,
    }


def profile_certainty_rule(
    user_text: str,
    low: str,
    manager: Any,
    turn: int,
    *,
    turns: Optional[list[tuple[str, str]]] = None,
    phase: str = "handle",
    entry_point: str = "",
) -> dict[str, Any]:
    del user_text, turn, turns, entry_point
    if phase != "handle" or not _looks_like_profile_certainty_followup(low):
        return {"handled": False}

    active_subject = _manager_active_subject(manager)
    if active_subject.startswith("developer_identity"):
        return {
            "handled": True,
            "action": "developer_identity_followup",
            "continuation": True,
            "name_focus": False,
            "ledger_stage": "profile_followup",
            "intent": "conversation_followup",
            "grounded": True,
        }
    if active_subject.startswith("identity_profile"):
        subject = active_subject.split(":", 1)[1] if ":" in active_subject else "self"
        return {
            "handled": True,
            "action": "identity_profile_followup",
            "continuation": True,
            "subject": subject or "self",
            "ledger_stage": "profile_followup",
            "intent": "conversation_followup",
            "grounded": True,
        }
    return {"handled": False}


def developer_profile_state_rule(
    user_text: str,
    low: str,
    manager: Any,
    turn: int,
    *,
    turns: Optional[list[tuple[str, str]]] = None,
    phase: str = "handle",
    entry_point: str = "",
) -> dict[str, Any]:
    del user_text, manager, turn, turns, entry_point
    if phase != "state" or not _looks_like_developer_profile_query(low):
        return {"handled": False}
    return {
        "handled": False,
        "state_update": {"kind": "identity_profile", "subject": "developer"},
    }


def apply_correction_rule(
    user_text: str,
    low: str,
    manager: Any,
    turn: int,
    **kwargs,
) -> dict[str, Any]:
    del manager, turn, kwargs
    triggers = [
        "wrong", "no,", "actually", "that's not", "not true", "incorrect",
        "mistake", "you lied", "that's wrong", "no it's not", "correction:",
    ]
    if any(trigger in low for trigger in triggers):
        return {
            "handled": True,
            "intent": "apply_correction",
            "user_correction_text": user_text,
            "confidence": 0.80,
        }
    return {"handled": False}


def store_fact_rule(
    user_text: str,
    low: str,
    manager: Any,
    turn: int,
    **kwargs,
) -> dict[str, Any]:
    del manager, turn, kwargs
    triggers = [
        "remember this", "learn this", "note that", "store", "save this",
        "add to memory", "keep in mind", "important:", "fact:",
    ]
    present = [trigger for trigger in triggers if trigger in low]
    if not present:
        return {"handled": False}
    fact_start = min(low.find(trigger) + len(trigger) for trigger in present)
    fact = user_text[fact_start:].strip() if fact_start < len(user_text) else str(user_text or "").strip()
    return {
        "handled": True,
        "intent": "store_fact",
        "fact_text": fact,
        "confidence": 0.90,
    }


def session_summary_rule(
    user_text: str,
    low: str,
    manager: Any,
    turn: int,
    **kwargs,
) -> dict[str, Any]:
    del user_text, manager, turn, kwargs
    triggers = [
        "what happened", "recap", "summarize", "digest", "review chat",
        "what did we talk about", "session summary", "what's going on",
    ]
    if any(trigger in low for trigger in triggers):
        return {
            "handled": True,
            "intent": "session_summary",
            "target": "current_session_only",
            "confidence": 0.95,
        }
    return {"handled": False}


class Supervisor:
    def __init__(self) -> None:
        self.probes: dict[str, Callable[[dict], tuple[str, str]]] = {
            "entrypoint_parity": self.probe_entrypoint_parity,
            "continuation_drop": self.probe_continuation_drop,
            "pending_action_leak": self.probe_pending_action_leak,
            "override_consistency": self.probe_override_consistency,
            "thin_answer_frequency": self.probe_thin_answer_frequency,
            "identity_location_route": self.probe_identity_location_route,
            "rule_coverage": self.probe_rule_coverage,
        }
        self.rules: list[dict[str, Any]] = []
        self.register_rule("reflective_retry", reflective_retry_rule, priority=30, phases=("rewrite", "handle"))
        self.register_rule("profile_certainty", profile_certainty_rule, priority=35, phases=("handle",))
        self.register_rule("developer_profile_state", developer_profile_state_rule, priority=38, phases=("state",))
        self.register_rule("self_location", self_location_rule, priority=40, phases=("handle",))
        self.register_rule("name_origin_store", name_origin_store_rule, priority=50, phases=("handle",))
        self.register_rule("apply_correction", apply_correction_rule, priority=60, phases=("intent",))
        self.register_rule("store_fact", store_fact_rule, priority=65, phases=("intent",))
        self.register_rule("session_summary", session_summary_rule, priority=70, phases=("intent",))
        self.reset()

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
        normalized_phase = str(phase or "handle").strip().lower() or "handle"
        low = _normalize_text(user_text)
        turn = len(list(turns or []))
        for item in self.rules:
            phases = tuple(item.get("phases") or ())
            if normalized_phase not in phases:
                continue
            try:
                result = item["rule"](
                    user_text,
                    low,
                    manager,
                    turn,
                    turns=list(turns or []),
                    phase=normalized_phase,
                    entry_point=str(entry_point or "").strip().lower(),
                )
            except Exception as exc:
                result = {"handled": False, "rule_error": str(exc)}
            if not isinstance(result, dict):
                continue
            if (
                bool(result.get("handled"))
                or str(result.get("rewrite_text") or "").strip()
                or isinstance(result.get("state_update"), dict)
            ):
                payload = dict(result)
                payload["rule_name"] = str(item.get("name") or "")
                payload["priority"] = int(item.get("priority", 100))
                return payload
        return {"handled": False}

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
        decision = self._normalize_decision(entry_point, session_id, summary, current_decision or {})
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

        suggestions = self._build_suggestions(context, findings)

        self._remember(decision)
        issue_count = len(findings)
        summary_text = "All green" if issue_count == 0 else f"{issue_count} issue{'s' if issue_count != 1 else ''} detected"
        return {
            "entry_point": decision["entry_point"],
            "session_id": decision["session_id"],
            "probe_summary": summary_text,
            "probe_results": [_status_line(item["name"], item["status"], item["message"]) for item in findings],
            "probe_findings": findings,
            "probe_status_counts": {
                "green": max(0, len(self.probes) - issue_count),
                "yellow": sum(1 for item in findings if item["status"] == "yellow"),
                "red": sum(1 for item in findings if item["status"] == "red"),
            },
            "suggestions": suggestions,
            "headline": f"Probe summary: {summary_text}",
        }

    def _normalize_decision(self, entry_point: str, session_id: str, session_summary: dict, current_decision: dict) -> dict:
        overrides = current_decision.get("overrides_active")
        if not isinstance(overrides, list):
            overrides = session_summary.get("overrides_active") if isinstance(session_summary.get("overrides_active"), list) else []
        pending_action = current_decision.get("pending_action") if isinstance(current_decision.get("pending_action"), dict) else None
        tool_result = str(current_decision.get("tool_result") or "")
        final_answer = str(current_decision.get("final_answer") or current_decision.get("reply_text") or "")
        user_input = str(current_decision.get("user_input") or "")
        return {
            "entry_point": str(entry_point or "unknown").strip().lower() or "unknown",
            "session_id": str(session_id or "").strip() or "default",
            "user_input": user_input,
            "parity_key": _normalize_text(user_input),
            "active_subject": str(current_decision.get("active_subject") or session_summary.get("active_subject") or "").strip(),
            "continuation_used": bool(current_decision.get("continuation_used", session_summary.get("continuation_used", False))),
            "planner_decision": str(current_decision.get("planner_decision") or "deterministic").strip() or "deterministic",
            "tool": str(current_decision.get("tool") or "").strip(),
            "tool_result": tool_result,
            "final_answer": final_answer,
            "pending_action": pending_action,
            "overrides_active": sorted(str(item).strip() for item in overrides if str(item).strip()),
            "grounded": bool(current_decision.get("grounded")) if isinstance(current_decision.get("grounded"), bool) else bool(tool_result.strip()),
            "route_summary": str(current_decision.get("route_summary") or "").strip(),
        }

    def _remember(self, decision: dict) -> None:
        parity_key = str(decision.get("parity_key") or "")
        if parity_key:
            self.last_decision[parity_key] = dict(decision)
        session_id = str(decision.get("session_id") or "default")
        self.last_decision_by_session[session_id] = dict(decision)
        entry_point = str(decision.get("entry_point") or "unknown")
        self.override_state_by_session.setdefault(session_id, {})[entry_point] = tuple(decision.get("overrides_active") or [])

    def _recent_issue_names(self, recent_reflections: list[dict]) -> list[str]:
        names: list[str] = []
        for reflection in recent_reflections[-5:]:
            findings = reflection.get("probe_findings") if isinstance(reflection, dict) else None
            if isinstance(findings, list):
                for item in findings:
                    if not isinstance(item, dict):
                        continue
                    status = str(item.get("status") or "").strip().lower()
                    if status not in {"yellow", "red"}:
                        continue
                    name = str(item.get("name") or "").strip()
                    if name:
                        names.append(name)
                continue
            for line in list(reflection.get("probe_results") or []):
                text = str(line or "").strip()
                match = re.match(r"^(?:YELLOW|RED):\s+([a-z_]+)", text, flags=re.I)
                if match:
                    names.append(match.group(1))
        return names

    def _build_suggestions(self, context: dict, findings: list[dict]) -> list[str]:
        repeated = Counter(self._recent_issue_names(list(context.get("recent_reflections") or [])))
        for item in findings:
            status = str(item.get("status") or "").strip().lower()
            name = str(item.get("name") or "").strip()
            if status in {"yellow", "red"} and name:
                repeated[name] += 1
        suggestions: list[str] = []
        for issue, count in repeated.items():
            if count < 3:
                continue
            suggestions.append(f"Repeated {issue} ({count}x) - consider hardening rule: {self.suggest_hardening(issue)}")
        return suggestions[:3]

    def suggest_hardening(self, issue: str) -> str:
        name = str(issue or "").strip().lower()
        if name == "pending_action_leak":
            return "auto-clear pending_action after tool success"
        if name == "continuation_drop":
            return "broaden continuation triggers or add a still-on-subject prompt"
        if name == "entrypoint_parity":
            return "compare CLI and HTTP ordering around the last matching input"
        if name == "identity_location_route":
            return "guard identity and location turns from local knowledge retrieval routes"
        if name == "rule_coverage":
            return "add a deterministic handler or tighten fallback gating for factual/tool turns"
        return "review probe details"

    def _looks_like_identity_location_turn(self, current: dict) -> bool:
        low = str(current.get("user_input") or "").strip().lower()
        if not low:
            return False
        return any(token in low for token in (
            "what is your location",
            "your current location",
            "your current physical location",
            "where are you",
            "where is nova",
            "his location",
            "where is he",
            "where is gus",
            "gus current location",
        ))

    def _looks_like_suspicious_fallback(self, current: dict) -> bool:
        low = str(current.get("user_input") or "").strip().lower()
        if not low:
            return False
        suspicious_terms = (
            "weather",
            "peims",
            "tsds",
            "attendance",
            "domain",
            "policy",
            "fetch",
            "search",
            "research",
            "tool",
            "location",
            "who is",
            "what is",
            "where is",
            "current location",
        )
        return any(term in low for term in suspicious_terms)

    def probe_entrypoint_parity(self, context: dict) -> tuple[str, str]:
        current = context.get("decision") or {}
        previous = context.get("previous_input_decision") or {}
        if not previous:
            return "green", ""
        if str(previous.get("entry_point") or "") == str(current.get("entry_point") or ""):
            return "green", ""
        prev_subject = str(previous.get("active_subject") or "")
        current_subject = str(current.get("active_subject") or "")
        if prev_subject != current_subject:
            return "red", f"Drift: {previous.get('entry_point')} -> {prev_subject or 'none'} vs {current.get('entry_point')} -> {current_subject or 'none'}"
        if bool(previous.get("continuation_used", False)) != bool(current.get("continuation_used", False)):
            return "yellow", f"Continuation mismatch on similar input: {previous.get('entry_point')} -> {bool(previous.get('continuation_used', False))} vs {current.get('entry_point')} -> {bool(current.get('continuation_used', False))}"
        return "green", ""

    def probe_continuation_drop(self, context: dict) -> tuple[str, str]:
        current = context.get("decision") or {}
        previous = context.get("previous_session_decision") or {}
        if not previous:
            return "green", ""
        if not bool(previous.get("continuation_used", False)) or bool(current.get("continuation_used", False)):
            return "green", ""
        previous_subject = str(previous.get("active_subject") or "")
        current_subject = str(current.get("active_subject") or "")
        if previous_subject and previous_subject != current_subject:
            return "yellow", f"Previous turn continued on {previous_subject}, current turn dropped to {current_subject or 'none'}"
        return "green", ""

    def probe_pending_action_leak(self, context: dict) -> tuple[str, str]:
        current = context.get("decision") or {}
        pending = current.get("pending_action")
        if not isinstance(pending, dict) or not pending:
            return "green", ""
        planner_decision = str(current.get("planner_decision") or "")
        tool_result = str(current.get("tool_result") or "").strip()
        if planner_decision in {"run_tool", "command"} and (bool(current.get("grounded", False)) or bool(tool_result)):
            return "red", f"Pending action still set after successful {planner_decision}"
        return "green", ""

    def probe_override_consistency(self, context: dict) -> tuple[str, str]:
        current = context.get("decision") or {}
        current_entry = str(current.get("entry_point") or "")
        current_overrides = tuple(current.get("overrides_active") or [])
        other_entries = context.get("other_entry_overrides") or {}
        for other_entry, other_overrides in other_entries.items():
            if str(other_entry or "") == current_entry:
                continue
            if tuple(other_overrides or ()) != current_overrides:
                return "yellow", f"Override mismatch: {other_entry} -> {list(other_overrides or [])} vs {current_entry} -> {list(current_overrides)}"
        return "green", ""

    def probe_thin_answer_frequency(self, context: dict) -> tuple[str, str]:
        recent = context.get("recent_records") or []
        if not isinstance(recent, list):
            return "green", ""
        count = 0
        for record in recent[-10:]:
            if not isinstance(record, dict):
                continue
            low = str(record.get("final_answer") or "").strip().lower()
            if not low:
                continue
            if any(token in low for token in (
                "i don't have",
                "i do not have",
                "uncertain",
                "not sure",
                "don't yet know",
                "do not yet know",
            )):
                count += 1
        if count > 2:
            return "yellow", f"Thin answers appearing {count} times in the last 10 turns"
        return "green", ""

    def probe_identity_location_route(self, context: dict) -> tuple[str, str]:
        current = context.get("decision") or {}
        if not self._looks_like_identity_location_turn(current):
            return "green", ""
        rendered = " ".join(
            str(current.get(field) or "")
            for field in ("final_answer", "tool_result", "route_summary")
        ).lower()
        if "local knowledge files" in rendered or "[source: knowledge/" in rendered:
            return "red", "Location or identity turn routed to local knowledge retrieval"
        return "green", ""

    def probe_rule_coverage(self, context: dict) -> tuple[str, str]:
        current = context.get("decision") or {}
        if str(current.get("planner_decision") or "") == "llm_fallback":
            if self._looks_like_suspicious_fallback(current):
                return "red", "Suspicious fallback on a factual or tool-directed turn"
            return "yellow", "Fallback used on an open-ended turn"
        return "green", ""