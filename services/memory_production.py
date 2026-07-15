from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Optional

from services.memory_routing import MEMORY_ROUTING_SERVICE
from services.nova_memory_learning import (
    extract_name_origin_teach_text,
    learn_contextual_self_facts,
    learn_from_user_correction,
    learn_self_identity_binding,
    remember_name_origin,
)


_CORRECTION_PREFIXES = (
    "no, ",
    "actually ",
    "that's wrong",
    "that is wrong",
    "correction:",
    "i meant ",
)

_NO_CORRECTION_RE = re.compile(
    r"^no\s+(?!(?:idea|ide|sure|problem|way|need|longer|more|less|thanks|thank you|worries)\b)",
    re.IGNORECASE,
)

_NOT_CORRECTION_RE = re.compile(
    r"^not\s+(?:correct|right|true|accurate|what you said|quite)\b",
    re.IGNORECASE,
)

_NEGATION_ONLY_RE = re.compile(
    r"^not\s+(?:sure|really|yet|anymore|always|often|exactly|quite|even|if|when|that|this)\b",
    re.IGNORECASE,
)

# Only these memory-learning actions may bypass the normal reply planner.
MEMORY_LEARNING_SHORT_CIRCUIT_ACTIONS = frozenset({
    "remember_fact",
    "identity_binding",
    "user_correction_facts",
    "contextual_self_facts",
    "name_origin",
})


def build_memory_recall_plan(
    query: str,
    *,
    purpose: str = "general",
    conversation_state: Optional[dict] = None,
    pending_action: Optional[dict] = None,
):
    return MEMORY_ROUTING_SERVICE.plan_durable_recall(
        query,
        purpose=purpose,
        conversation_state=conversation_state,
        pending_action=pending_action,
    )


def build_memory_read_plan(
    query: str,
    *,
    purpose: str = "recent_learning_summary",
    conversation_state: Optional[dict] = None,
    pending_action: Optional[dict] = None,
):
    return MEMORY_ROUTING_SERVICE.plan_durable_recall(
        query,
        purpose=purpose,
        conversation_state=conversation_state,
        pending_action=pending_action,
    )


def parse_correction(
    text: str,
    *,
    pending_correction_target: str = "",
    conversation_state: Optional[dict] = None,
) -> tuple[bool, str]:
    raw = str(text or "").strip()
    if not raw:
        return False, ""

    state_kind = ""
    if isinstance(conversation_state, dict):
        state_kind = str(conversation_state.get("kind") or "").strip().lower()
    pending_target = str(pending_correction_target or "").strip()
    if state_kind == "correction_pending" or pending_target:
        return True, raw

    low = raw.lower()
    for prefix in _CORRECTION_PREFIXES:
        if low.startswith(prefix):
            parsed = raw[len(prefix) :].strip()
            return True, parsed or raw

    if _NEGATION_ONLY_RE.match(low):
        return False, ""

    if _NOT_CORRECTION_RE.match(low):
        parsed = _NOT_CORRECTION_RE.sub("", raw, count=1).strip(" ,:-")
        return True, parsed or raw

    no_match = _NO_CORRECTION_RE.match(low)
    if no_match:
        parsed = raw[no_match.end() :].strip()
        return True, parsed or raw

    return False, ""


def extract_color_preferences_from_text(text: str) -> list[str]:
    raw = str(text or "").strip()
    if not raw:
        return []
    parts = re.split(r"\s*,\s*|\s+and\s+", raw, flags=re.I)
    colors: list[str] = []
    seen: set[str] = set()
    for part in parts:
        color = re.sub(r"[^a-zA-Z\- ]+", "", part).strip().lower()
        if not color or color in seen:
            continue
        seen.add(color)
        colors.append(color)
    return colors


@dataclass(frozen=True)
class MemoryLearningOutcome:
    handled: bool
    early_reply: str
    action: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "handled": bool(self.handled),
            "early_reply": str(self.early_reply or ""),
            "action": str(self.action or ""),
        }


def apply_user_memory_learning(
    text: str,
    *,
    input_source: str = "typed",
    conversation_state: Optional[dict] = None,
    pending_correction_target: str = "",
    last_assistant: str = "",
    mem_enabled_fn: Callable[[], bool],
    mem_add_fn: Callable[[str, str, str], None],
    mem_remember_fact_fn: Callable[[str], str],
    load_learned_facts_fn: Callable[[], dict],
    save_learned_facts_fn: Callable[[dict], None],
    get_learned_fact_fn: Callable[[str, str], str],
    set_active_user_fn: Callable[[str], None],
    get_active_user_fn: Callable[[], Optional[str]],
    load_identity_profile_fn: Callable[[], dict],
    save_identity_profile_fn: Callable[[dict], None],
    store_correction_record_fn: Callable[..., None],
    clear_pending_correction_target_fn: Callable[[], None] | None = None,
) -> dict[str, Any]:
    raw = str(text or "").strip()
    if not raw:
        return MemoryLearningOutcome(False, "", "").as_dict()

    low = raw.lower()
    if low.startswith("remember:") or low.startswith("remember "):
        fact_text = raw.split(":", 1)[1].strip() if ":" in raw else raw[len("remember ") :].strip()
        reply = mem_remember_fact_fn(fact_text)
        return MemoryLearningOutcome(True, reply, "remember_fact").as_dict()

    learned, message = learn_self_identity_binding(
        raw,
        set_active_user_fn=set_active_user_fn,
        get_learned_fact_fn=get_learned_fact_fn,
    )
    if learned and message:
        return MemoryLearningOutcome(True, message, "identity_binding").as_dict()

    learned, message = learn_from_user_correction(
        raw,
        load_learned_facts_fn=load_learned_facts_fn,
        get_learned_fact_fn=get_learned_fact_fn,
        save_learned_facts_fn=save_learned_facts_fn,
        set_active_user_fn=set_active_user_fn,
        mem_enabled_fn=mem_enabled_fn,
        mem_add_fn=mem_add_fn,
    )
    if learned and message:
        return MemoryLearningOutcome(True, message, "user_correction_facts").as_dict()

    learned, message = learn_contextual_self_facts(
        raw,
        input_source=input_source,
        speaker_matches_developer_fn=lambda: _speaker_matches_developer(
            get_active_user_fn=get_active_user_fn,
            get_learned_fact_fn=get_learned_fact_fn,
        ),
        extract_color_preferences_from_text_fn=extract_color_preferences_from_text,
        mem_enabled_fn=mem_enabled_fn,
        mem_add_fn=mem_add_fn,
    )
    if learned and message:
        return MemoryLearningOutcome(True, message, "contextual_self_facts").as_dict()

    origin_story = extract_name_origin_teach_text(raw)
    if origin_story:
        reply = remember_name_origin(
            origin_story,
            load_identity_profile_fn=load_identity_profile_fn,
            save_identity_profile_fn=save_identity_profile_fn,
            mem_enabled_fn=mem_enabled_fn,
            mem_add_fn=mem_add_fn,
        )
        return MemoryLearningOutcome(True, reply, "name_origin").as_dict()

    is_correction, parsed_correction = parse_correction(
        raw,
        pending_correction_target=pending_correction_target,
        conversation_state=conversation_state,
    )
    if is_correction:
        store_correction_record_fn(
            raw,
            input_source=input_source,
            last_assistant=last_assistant,
            parsed_correction=parsed_correction,
        )
        if callable(clear_pending_correction_target_fn):
            clear_pending_correction_target_fn()
        return MemoryLearningOutcome(
            True,
            "",
            "supervisor_correction",
        ).as_dict()

    return MemoryLearningOutcome(False, "", "").as_dict()


def _speaker_matches_developer(
    *,
    get_active_user_fn: Callable[[], Optional[str]],
    get_learned_fact_fn: Callable[[str, str], str],
) -> bool:
    active_user = str(get_active_user_fn() or "").strip().lower()
    if not active_user:
        return False
    developer_name = get_learned_fact_fn("developer_name", "Gustavo Uribe").strip().lower()
    developer_nickname = get_learned_fact_fn("developer_nickname", "Gus").strip().lower()
    developer_first = developer_name.split()[0] if developer_name else ""
    return active_user in {developer_name, developer_nickname, developer_first}