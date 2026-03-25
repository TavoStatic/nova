"""Intent interpretation seams for Nova's shared-state architecture.

This module is intentionally light on implementation. It defines the callable
surface for turning raw user input plus shared context into an updated Intent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import re
from typing import Any, Mapping

from fulfillment_contracts import Intent


def _normalized_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip())


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        cleaned = _normalized_text(value).strip(" .,!?:;")
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(cleaned)
    return ordered


def _intent_id(seed_text: str) -> str:
    digest = hashlib.sha1(seed_text.encode("utf-8", errors="ignore")).hexdigest()[:10]
    return f"intent:{digest}"


def _recent_user_turns(shared_context: Mapping[str, Any] | None) -> list[str]:
    if not isinstance(shared_context, Mapping):
        return []
    raw_turns = shared_context.get("recent_turns")
    if not isinstance(raw_turns, list):
        return []
    collected: list[str] = []
    for item in raw_turns:
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            continue
        role = str(item[0] or "").strip().lower()
        text = _normalized_text(str(item[1] or ""))
        if role == "user" and text:
            collected.append(text)
    return collected


def _looks_like_followup_adjustment(text: str) -> bool:
    low = _normalized_text(text).lower()
    if not low:
        return False
    prefixes = (
        "new information",
        "actually",
        "instead",
        "that said",
        "but ",
        "however",
        "certainty matters",
        "speed matters",
        "safety matters",
        "cost matters",
    )
    return low.startswith(prefixes)


def _initial_achievement_goal(raw_input: str, shared_context: Mapping[str, Any] | None) -> str:
    text = _normalized_text(raw_input)
    recent_user_turns = _recent_user_turns(shared_context)
    if _looks_like_followup_adjustment(text):
        for prior_text in reversed(recent_user_turns):
            if prior_text.lower() != text.lower():
                return prior_text
    return text


def _initial_evidence(raw_input: str, shared_context: Mapping[str, Any] | None) -> list[str]:
    text = _normalized_text(raw_input)
    evidence: list[str] = []
    goal_seed = _initial_achievement_goal(text, shared_context)
    if goal_seed:
        evidence.append(goal_seed)
    if text and text.lower() != goal_seed.lower():
        evidence.append(text)
    return _unique(evidence)


def _combined_seed_text(raw_input: str, shared_context: Mapping[str, Any] | None) -> str:
    return " ".join(_initial_evidence(raw_input, shared_context)).strip() or _normalized_text(raw_input)


def _extract_constraints(raw_input: str) -> list[str]:
    raw = _normalized_text(raw_input)
    if not raw:
        return []
    patterns = (
        r"\bwithout\s+([^,.!?;]+)",
        r"\bdo not\s+([^,.!?;]+)",
        r"\bdon't\s+([^,.!?;]+)",
        r"\bmust\s+([^,.!?;]+)",
        r"\bneed to\s+([^,.!?;]+)",
    )
    constraints: list[str] = []
    for pattern in patterns:
        for match in re.finditer(pattern, raw, flags=re.I):
            constraints.append(match.group(0))
    return _unique(constraints)


def _extract_preferences(raw_input: str) -> list[str]:
    low = _normalized_text(raw_input).lower()
    preferences: list[str] = []
    cue_map = {
        "low friction": ("low friction", "simpler path"),
        "simple": ("low friction",),
        "fast": ("timely",),
        "quick": ("timely",),
        "faster": ("timely",),
        "certainty": ("higher certainty",),
        "safe": ("higher certainty",),
        "safer": ("higher certainty",),
        "compare": ("preserve alternatives",),
        "options": ("preserve alternatives",),
        "choice": ("preserve alternatives",),
        "explain": ("explainable path",),
        "show": ("visible tradeoffs",),
        "help": ("workable result",),
    }
    for cue, mapped in cue_map.items():
        if cue in low:
            preferences.extend(mapped)
    if "?" in raw_input:
        preferences.append("keep ambiguity visible until fit improves")
    return _unique(preferences)


def _extract_success_criteria(raw_input: str) -> list[str]:
    low = _normalized_text(raw_input).lower()
    criteria = ["requested result is reachable", "path remains explainable"]
    if any(token in low for token in ("compare", "options", "choice", "different ways")):
        criteria.append("materially different paths remain visible")
    if any(token in low for token in ("fast", "quick", "faster", "timely")):
        criteria.append("time-sensitive path remains visible")
    if any(token in low for token in ("low friction", "simple", "easy", "easier")):
        criteria.append("lower-friction path remains visible")
    return _unique(criteria)


def _extract_unresolved_questions(raw_input: str) -> list[str]:
    low = _normalized_text(raw_input).lower()
    questions: list[str] = []
    if "?" in raw_input or any(token in low for token in ("which", "best", "compare", "options", "choice")):
        questions.append("which fulfillment shape best fits the latest information")
    if any(token in low for token in ("tradeoff", "trade-off", "versus", "vs")):
        questions.append("which tradeoff balance is best under current constraints")
    return _unique(questions)


@dataclass(slots=True)
class IntentInterpreter:
    """Interpret raw input into an updated intent view.

    The interpreter is expected to work against shared living state, not a
    one-way pipeline. Implementations should preserve ambiguity when it affects
    fulfillment shape and avoid content-first branching.
    """

    config: Mapping[str, Any] = field(default_factory=dict)

    def interpret(
        self,
        raw_input: str,
        *,
        current_intent: Intent | None = None,
        shared_context: Mapping[str, Any] | None = None,
    ) -> Intent:
        """Return a revised Intent derived from raw input and current context.

        TODO:
        - Merge new evidence into the active intent without forcing collapse.
        - Preserve unresolved ambiguity when it changes fulfillment fit.
        - Avoid converting topic/content hints into routing decisions.
        """
        text = _normalized_text(raw_input)
        if not text:
            raise ValueError("raw_input must not be empty")

        if current_intent is None:
            achievement_goal = _initial_achievement_goal(text, shared_context)
            seed_text = _combined_seed_text(text, shared_context)
            return Intent(
                intent_id=_intent_id(achievement_goal.lower()),
                achievement_goal=achievement_goal,
                success_criteria=_extract_success_criteria(seed_text),
                constraints=_extract_constraints(seed_text),
                friction_factors=_unique([item for item in _extract_preferences(seed_text) if item in {"low friction", "simpler path", "timely", "higher certainty"}]),
                preferences=_extract_preferences(seed_text),
                unresolved_questions=_extract_unresolved_questions(seed_text),
                ambiguity_notes=_unique([
                    "multiple fulfillment shapes may remain valid"
                    if _extract_unresolved_questions(seed_text) or "?" in seed_text
                    else ""
                ]),
                evidence=_initial_evidence(text, shared_context),
                confidence=0.68 if "?" in text else 0.72,
            )

        return Intent(
            intent_id=current_intent.intent_id,
            achievement_goal=current_intent.achievement_goal,
            success_criteria=_unique(list(current_intent.success_criteria) + _extract_success_criteria(text)),
            constraints=_unique(list(current_intent.constraints) + _extract_constraints(text)),
            friction_factors=_unique(list(current_intent.friction_factors) + [item for item in _extract_preferences(text) if item in {"low friction", "simpler path", "timely", "higher certainty"}]),
            preferences=_unique(list(current_intent.preferences) + _extract_preferences(text)),
            unresolved_questions=_unique(list(current_intent.unresolved_questions) + _extract_unresolved_questions(text)),
            ambiguity_notes=_unique(list(current_intent.ambiguity_notes) + ["multiple fulfillment shapes may remain valid"]),
            evidence=_unique(list(current_intent.evidence) + [text]),
            confidence=max(float(current_intent.confidence or 0.0), 0.72),
        )


def interpret_intent(
    raw_input: str,
    *,
    current_intent: Intent | None = None,
    shared_context: Mapping[str, Any] | None = None,
    config: Mapping[str, Any] | None = None,
) -> Intent:
    """Convenience wrapper for intent interpretation.

    TODO:
    - Keep this wrapper thin so tests can target the class directly.
    - Preserve a stable functional seam for callers that prefer pure-style use.
    """
    interpreter = IntentInterpreter(config=config or {})
    return interpreter.interpret(
        raw_input,
        current_intent=current_intent,
        shared_context=shared_context,
    )
