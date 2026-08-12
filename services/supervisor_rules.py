"""
supervisor_rules.py
--------------------
Default Supervisor rule implementations.

NOVA_DOC:
  category: subsystem
  authority: active_authority
  last_session: 2026-08-05
  last_agent: claude-cowork
  session_state: current
  next_step: none
  open: none

Rules are registered in supervisor_registry.py and loaded by supervisor.py.

Rule signature:
    rule(user_text: str, low: str, manager: Any, turn: int,
         *, turns: list, phase: str, entry_point: str) -> dict

Result keys:
    handled       bool   — True if this rule claims the turn
    action        str    — deterministic action key (e.g. "identity_answer")
    intent        str    — classified user move (e.g. "correction")
    ownership     str    — "explicit" to stop rule evaluation here
    rewrite_text  str    — optional text rewrite (rare)
    state_update  dict   — optional session state mutation

Rules that set `handled=True` + `ownership="explicit"` are exclusively owned.
Rules that set `intent` but NOT `action`/`handled` are informational observers.

See docs/SUPERVISOR_CONTRACT.md for the constitution this implements.

NOVA_DOC:
  category: subsystem
  authority: active_authority
  last_session: 2026-08-05
  last_agent: claude-cowork
  session_state: current
  next_step: add rule_coverage_safe_fallback once clarification contract is exercised
  open: none
"""
from __future__ import annotations

import re
from typing import Any


# ── Move classification tokens ───────────────────────────────────────────────

_CORRECTION_TOKENS = (
    "no, ", "no that", "not right", "that's wrong", "thats wrong",
    "you are wrong", "you're wrong", "incorrect", "you misunderstood",
    "i meant ", "i mean ", "i was saying", "actually ", "to clarify",
    "let me rephrase", "that is not what", "not what i",
)

_REDIRECT_TOKENS = (
    "never mind", "nevermind", "forget that", "let's change",
    "switch to ", "different topic", "new question", "new topic",
    "i have a different", "actually i want", "actually let's",
    "start over", "start fresh", "reset", "change subject",
)

_META_REPAIR_TOKENS = (
    "why did you", "why are you", "that was wrong", "you should have",
    "fix your", "repair", "you broke", "what happened to",
    "go back to", "you ignored", "you missed", "you skipped",
    "check your", "review your",
)

_CONFUSION_TOKENS = (
    "what do you mean", "what does that mean", "i don't understand",
    "i do not understand", "confused", "unclear", "what?", "huh?",
    "can you explain", "elaborate", "say that again",
    "rephrase", "i'm lost", "i am lost", "lost me",
)

_STATE_DECLARATION_TOKENS = (
    "my name is", "i am ", "i'm ", "i work at", "i live in",
    "my location is", "my role is", "remember that", "note that",
    "update my", "save that", "store that",
)

_SELECTION_TOKENS = (
    "the first one", "option one", "option 1", "first option",
    "second one", "option two", "option 2", "the second",
    "third one", "option three", "option 3", "the third",
    "the last one", "that one", "this one", "the other one",
    "number one", "number two", "number three",
    "pick ", "choose ", "select ",
)

_CONTINUATION_TOKENS = (
    "and also", "and then", "what else", "tell me more",
    "continue", "go on", "keep going", "more about",
    "what about ", "how about ", "what if ", "and what",
    "as well", "additionally", "furthermore",
)

# Identity and location tokens (subset from supervisor_probes.py, extended)
_IDENTITY_LOCATION_TOKENS = (
    "what is your location",
    "your current location",
    "your current physical location",
    "where are you",
    "where is nova",
    "where is he",
    "where is gus",
    "gus current location",
    "what is nova's location",
    "where do you live",
    "what city are you in",
    "where are you located",
    "what is your address",
    "what is your physical location",
)


# ── Rule 1: intent_move_classify (intent phase, non-owning) ─────────────────

def rule_intent_move_classify(
    user_text: str,
    low: str,
    manager: Any,
    turn: int,
    *,
    turns: list,
    phase: str,
    entry_point: str,
) -> dict:
    """
    Classify the user's move type from the 8 required categories.
    Non-owning: annotates the routing trace without intercepting the turn.

    Contract-required move categories (SUPERVISOR_CONTRACT.md):
        correction, state_declaration, open_question, selection,
        continuation, redirect, meta_repair, confusion
    """
    # Check most specific / highest-stakes categories first
    if any(tok in low for tok in _CORRECTION_TOKENS):
        return {"handled": False, "intent": "correction"}

    if any(tok in low for tok in _REDIRECT_TOKENS):
        return {"handled": False, "intent": "redirect"}

    if any(tok in low for tok in _META_REPAIR_TOKENS):
        return {"handled": False, "intent": "meta_repair"}

    if any(tok in low for tok in _CONFUSION_TOKENS):
        return {"handled": False, "intent": "confusion"}

    if any(tok in low for tok in _STATE_DECLARATION_TOKENS):
        return {"handled": False, "intent": "state_declaration"}

    if any(tok in low for tok in _SELECTION_TOKENS):
        return {"handled": False, "intent": "selection"}

    if any(tok in low for tok in _CONTINUATION_TOKENS):
        return {"handled": False, "intent": "continuation"}

    # Default: open question
    if "?" in user_text or len(low.split()) > 3:
        return {"handled": False, "intent": "open_question"}

    return {"handled": False, "intent": ""}


# ── Rule 2: identity_location_guard (handle phase, owning) ──────────────────

def rule_identity_location_guard(
    user_text: str,
    low: str,
    manager: Any,
    turn: int,
    *,
    turns: list,
    phase: str,
    entry_point: str,
) -> dict:
    """
    Intercept identity and location queries before they reach local knowledge retrieval.

    Probe `identity_location_route` fires RED when these turns route to
    `knowledge/` files. This rule claims ownership so routing can dispatch
    to identity_answer instead.

    Owning: handled=True + ownership="explicit" → evaluation stops here.
    """
    if any(tok in low for tok in _IDENTITY_LOCATION_TOKENS):
        return {
            "handled": True,
            "action": "identity_answer",
            "intent": "open_question",
            "ownership": "explicit",
            "rule_name": "identity_location_guard",
        }
    return {"handled": False}


# ── Rule 3: ambiguous_clarifier_gate (handle phase, non-owning observer) ────

_BARE_CLARIFIERS = frozenset({
    "what", "what?", "huh", "huh?", "ok", "okay", "really", "really?",
    "and?", "so?", "yes?", "no?", "sure", "go on", "continue",
})

def rule_ambiguous_clarifier_gate(
    user_text: str,
    low: str,
    manager: Any,
    turn: int,
    *,
    turns: list,
    phase: str,
    entry_point: str,
) -> dict:
    """
    Detect bare ambiguous clarifiers — single tokens or very short phrases that
    could mean anything depending on thread context.

    Non-owning: annotates candidates as "ambiguous_clarifier" so the routing
    trace captures it. Does not intercept; the planner / fulfillment path
    resolves from thread context.

    Contract: "a scalar, short phrase, ordinal, pronoun, or other low-information
    token is ambiguous by default." (SUPERVISOR_CONTRACT.md)
    """
    words = low.split()
    # Bare single-word clarifiers
    if len(words) == 1 and words[0].rstrip("?!.") in _BARE_CLARIFIERS:
        return {"handled": False, "intent": "ambiguous_clarifier"}
    # Very short (≤2 word) phrases with a question mark
    if len(words) <= 2 and "?" in user_text:
        return {"handled": False, "intent": "ambiguous_clarifier"}
    return {"handled": False}


# ── Rule 4: safe_fallback_contract (handle phase, non-owning observer) ───────

_SUSPICIOUS_FALLBACK_TERMS = frozenset({
    "weather", "tsds", "attendance", "domain", "policy",
    "fetch", "search", "research", "location",
})

def rule_safe_fallback_contract(
    user_text: str,
    low: str,
    manager: Any,
    turn: int,
    *,
    turns: list,
    phase: str,
    entry_point: str,
) -> dict:
    """
    Flag turns that are likely tool-directed or factual queries.
    If these end up in generic llm_fallback, probe `rule_coverage` fires RED.

    Non-owning: records a candidate intent for the routing trace.
    The fulfillment route should handle these — if they fall through to
    generic fallback, the probe will fire and surface the gap.

    Future: once a safe_fallback contract exists, elevate this to owning.
    """
    # Explicit tool-directed patterns
    if re.search(r"\b(search|fetch|find|look up|look for|get me|show me)\b", low):
        return {"handled": False, "intent": "tool_directed_query"}

    # Known factual domains that should not fallback
    if any(term in low for term in _SUSPICIOUS_FALLBACK_TERMS):
        return {"handled": False, "intent": "factual_domain_query"}

    return {"handled": False}


# ── Registry of all default rules ───────────────────────────────────────────

DEFAULT_RULE_HANDLERS: dict = {
    "intent_move_classify": rule_intent_move_classify,
    "identity_location_guard": rule_identity_location_guard,
    "ambiguous_clarifier_gate": rule_ambiguous_clarifier_gate,
    "safe_fallback_contract": rule_safe_fallback_contract,
}
