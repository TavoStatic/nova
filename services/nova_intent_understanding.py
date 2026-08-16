"""
nova_intent_understanding.py

Multi-level intent classification for NOVA.
"""

from __future__ import annotations

import json
import re
from typing import Any, Callable, Optional


SHARING = "sharing"
REQUESTING = "requesting"
COMMANDING = "commanding"
CASUAL = "casual"
RESPONDING = "responding"

_VALID_LEVELS = {SHARING, REQUESTING, COMMANDING, CASUAL, RESPONDING}

ACCEPT = "accept_and_engage"
CONFIRM = "confirm_with_data"
CORRECT = "correct_with_data"
ENRICH = "enrich_with_data"
FULFILL = "fulfill"
CLARIFY = "clarify"

_VALID_STRATEGIES = {ACCEPT, CONFIRM, CORRECT, ENRICH, FULFILL, CLARIFY}

WEATHER = "weather"
LOCATION = "location"
SYSTEM = "system"
GENERAL = "general"

_VALID_DOMAINS = {WEATHER, LOCATION, SYSTEM, GENERAL}

_INTENT_PROMPT = (
    "Classify the intent level of the user's current turn.\n"
    "Analyze the full semantic meaning -- not keywords or surface phrasing.\n"
    "\n"
    "Intent levels:\n"
    "- sharing: user is stating, asserting, or providing information\n"
    "- requesting: user is asking a question or requesting information\n"
    "- commanding: user wants an action performed\n"
    "- casual: conversational remark with no specific information need\n"
    "- responding: user is answering a question the assistant just asked\n"
    "\n"
    "Domains:\n"
    "- weather: outdoor conditions, temperature, rain, wind, forecast,\n"
    "  clothing for outdoors, whether to bring an umbrella or jacket\n"
    "- location: physical place, coordinates, where something or someone is\n"
    "- system: live operational condition, pending work, health checks,\n"
    "  capabilities. Not mood, feelings, greetings, or how the conversation feels.\n"
    "- general: anything else, including presence and how Nova is doing as a person\n"
    "\n"
    "If level is 'sharing', extract the specific claim the user is making.\n"
    "If the turn is too vague or ambiguous to classify confidently,\n"
    "set confidence below 0.5.\n"
    "\n"
    "Return JSON only -- no explanation, no markdown:\n"
    '{"level":"<level>","domain":"<domain>","confidence":<0.0-1.0>,'
    '"subject":"<brief subject>","user_claim":"<claim or null>"}\n'
)


def classify_turn_intent(
    text,
    turns,
    *,
    live_ollama_calls_allowed_fn,
    chat_model_fn,
    ollama_base,
    requests_post_fn=None,
):
    user_text = str(text or "").strip()
    if not user_text:
        return _default_intent()

    try:
        if not live_ollama_calls_allowed_fn():
            return _default_intent()
    except Exception:
        return _default_intent()

    recent = []
    for role, content in (turns or [])[-6:]:
        r = str(role or "").strip().lower()
        if r in {"user", "assistant"}:
            recent.append({"role": r, "content": str(content or "").strip()[:500]})

    payload = {
        "model": chat_model_fn(),
        "stream": False,
        "keep_alive": "10m",
        "options": {"temperature": 0.0, "top_p": 0.8},
        "messages": [
            {"role": "system", "content": _INTENT_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    {"turn": user_text, "recent_turns": recent},
                    ensure_ascii=True,
                ),
            },
        ],
    }

    import requests as _requests
    post = requests_post_fn if callable(requests_post_fn) else _requests.post
    try:
        response = post(
            str(ollama_base or "").rstrip("/") + "/api/chat",
            json=payload,
            timeout=3.0,
        )
        response.raise_for_status()
        raw = str(response.json().get("message", {}).get("content") or "").strip()
        return _parse_intent(raw) or _default_intent()
    except Exception:
        return _default_intent()


def select_response_strategy(
    intent,
    *,
    tool_data_available=False,
    data_confirms_claim=None,
):
    level = str(intent.get("level") or CASUAL).strip()
    domain = str(intent.get("domain") or GENERAL).strip()
    confidence = float(intent.get("confidence") or 0.0)

    if confidence < 0.4:
        return {
            "strategy": CLARIFY,
            "use_tool": False,
            "rationale": "low confidence ({:.2f}) on intent classification".format(confidence),
        }

    if level in {REQUESTING, COMMANDING}:
        return {
            "strategy": FULFILL,
            "use_tool": True,
            "rationale": "{} intent in {} domain".format(level, domain),
        }

    if level == RESPONDING:
        return {
            "strategy": FULFILL,
            "use_tool": True,
            "rationale": "user is responding to NOVA's question",
        }

    if level == SHARING and domain in {WEATHER, LOCATION}:
        if not tool_data_available:
            return {
                "strategy": ACCEPT,
                "use_tool": False,
                "rationale": "user sharing {} info, NOVA has no data to verify".format(domain),
            }
        if data_confirms_claim is True:
            return {
                "strategy": CONFIRM,
                "use_tool": True,
                "rationale": "user sharing {} info, data confirms their claim".format(domain),
            }
        if data_confirms_claim is False:
            return {
                "strategy": CORRECT,
                "use_tool": True,
                "rationale": "user sharing {} info, data contradicts their claim".format(domain),
            }
        return {
            "strategy": ENRICH,
            "use_tool": True,
            "rationale": "user sharing {} info, adding relevant data".format(domain),
        }

    return {
        "strategy": ACCEPT,
        "use_tool": False,
        "rationale": "{} intent, conversational response appropriate".format(level),
    }


def self_status_belongs_to_turn(intent, strategy=None) -> bool:
    """Operator self_status is for live work/health asks, not presence."""
    payload = intent if isinstance(intent, dict) else {}
    plan = strategy if isinstance(strategy, dict) else {}
    level = str(payload.get("level") or "").strip()
    domain = str(payload.get("domain") or "").strip()
    if not level and not domain:
        return True
    if plan and not bool(plan.get("use_tool")):
        return False
    if level == CASUAL:
        return False
    return level in {REQUESTING, COMMANDING} and domain == SYSTEM


def record_intent_outcome(
    text,
    intent,
    strategy,
    *,
    outcome="completed",
    mem_add_fn=None,
    ingest_signal_fn=None,
):
    domain = str(intent.get("domain") or "").strip()
    level = str(intent.get("level") or "").strip()
    strat = str(strategy.get("strategy") or "").strip()
    subject = str(intent.get("subject") or "").strip()

    if not domain or not level or not strat:
        return

    user_text = str(text or "").strip()[:200]
    if not user_text:
        return

    if _is_gap_outcome(strat, outcome):
        if callable(ingest_signal_fn):
            try:
                ingest_signal_fn(
                    _build_intent_gap_signal(domain, level, strat, outcome, user_text)
                )
            except Exception:
                pass
        return

    if callable(mem_add_fn):
        entry = (
            "[intent_pattern] "
            "domain={} level={} strategy={} outcome={}".format(domain, level, strat, outcome)
            + (" subject={}".format(subject) if subject else "")
            + ': "{}"'.format(user_text)
        )
        try:
            mem_add_fn(entry)
        except Exception:
            pass


def _is_gap_outcome(strategy, outcome):
    if strategy == CLARIFY:
        return True
    gap_keywords = {"clarify", "gap", "failed", "unclear"}
    return any(kw in str(outcome or "").lower() for kw in gap_keywords)


def _build_intent_gap_signal(domain, level, strat, outcome, user_text):
    return {
        "source": "intent_understanding",
        "signal_class": "governance_pressure",
        "title": "Intent understanding gap: '{}' domain needs clearer classification".format(domain),
        "fingerprint": {
            "class": "governance_pressure",
            "surface": "intent_understanding",
            "error": "intent_gap",
            "symbol": "{}_{}".format(domain, level),
        },
        "payload": {
            "domain": domain,
            "level": level,
            "strategy": strat,
            "outcome": outcome,
            "sample_text": user_text[:120],
            "rationale": (
                "NOVA could not classify user intent with sufficient confidence. "
                "Repeated clarification pressure in this domain signals a gap "
                "in the intent prompt or confidence thresholds."
            ),
        },
        "severity": "low",
        "actionability": "safe_now",
        "allowed_tools": ["read", "pulse"],
        "preferred_tool": "read",
        "next_task": (
            "Review intent classification accuracy for '{}' domain. "
            "Check _INTENT_PROMPT coverage and confidence thresholds in "
            "services/nova_intent_understanding.py.".format(domain)
        ),
    }


def _default_intent():
    return {
        "level": CASUAL,
        "domain": GENERAL,
        "confidence": 0.0,
        "subject": "",
        "user_claim": None,
    }


def _parse_intent(raw):
    text = str(raw or "").strip()
    if not text:
        return None

    parsed = None
    try:
        parsed = json.loads(text)
    except Exception:
        match = re.search(r"\{[^{}]+\}", text)
        if match:
            try:
                parsed = json.loads(match.group(0))
            except Exception:
                pass

    if not isinstance(parsed, dict):
        return None

    level = str(parsed.get("level") or "").strip().lower()
    if level not in _VALID_LEVELS:
        level = CASUAL

    domain = str(parsed.get("domain") or "").strip().lower()
    if domain not in _VALID_DOMAINS:
        domain = GENERAL

    try:
        confidence = max(0.0, min(1.0, float(parsed.get("confidence") or 0.0)))
    except (TypeError, ValueError):
        confidence = 0.0

    claim_raw = parsed.get("user_claim")
    user_claim = (
        str(claim_raw).strip()[:400]
        if claim_raw and str(claim_raw).strip()
        else None
    )

    return {
        "level": level,
        "domain": domain,
        "confidence": confidence,
        "subject": str(parsed.get("subject") or "").strip()[:200],
        "user_claim": user_claim,
    }
