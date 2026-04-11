from __future__ import annotations

import re
from typing import Callable, Optional


_SYNTHETIC_ACTIVE_USERS = {"runner", "local-user", "localuser", "unknown", "local"}


def _display_active_user(active_user: Optional[str], *, default_local_user_id_fn: Callable[[], str]) -> str:
    who = (active_user or "").strip()
    if not who:
        return ""
    if who.lower() in _SYNTHETIC_ACTIVE_USERS:
        return ""
    if who.lower() == default_local_user_id_fn().lower():
        return ""
    return who


def is_session_recap_request(text: str) -> bool:
    low = (text or "").strip().lower()
    cues = [
        "recap",
        "what were we talking about",
        "what we just talked about",
        "previous chat lines",
        "entire chat session",
        "go back to our previous chat",
        "follow the chat",
    ]
    return any(cue in low for cue in cues)


def session_recap_reply(turns: list[tuple[str, str]], current_text: str, *, is_session_recap_request_fn: Callable[[str], bool]) -> str:
    current_low = (current_text or "").strip().lower()
    topics: list[str] = []

    for role, text in turns:
        if role != "user":
            continue
        clean = re.sub(r"\s+", " ", (text or "").strip())
        if not clean:
            continue
        low = clean.lower()
        if low == current_low:
            continue
        if is_session_recap_request_fn(clean):
            continue
        if len(clean) > 180:
            clean = clean[:177] + "..."
        topics.append(clean)

    if not topics:
        return "I do not have enough prior user turns in this session to recap yet."

    lines = ["Recap of this session so far:"]
    for index, topic in enumerate(topics[-6:], start=1):
        lines.append(f"{index}. {topic}")
    return "\n".join(lines)


def is_deep_search_followup_request(text: str) -> bool:
    low = (text or "").strip().lower()
    if not low:
        return False
    cues = (
        "deep search",
        "dig up",
        "search deeper",
        "search more online",
        "look online for more",
    )
    return any(cue in low for cue in cues)


def infer_research_query_from_turns(
    turns: list[tuple[str, str]],
    *,
    is_deep_search_followup_request_fn: Callable[[str], bool],
    is_session_recap_request_fn: Callable[[str], bool],
) -> str:
    for role, text in reversed(turns):
        if role != "user":
            continue
        low = (text or "").strip().lower()
        if not low:
            continue
        if is_deep_search_followup_request_fn(low) or is_session_recap_request_fn(low):
            continue
        if "peims" in low and "attendance" in low:
            return "PEIMS attendance reporting rules Texas TEA ADA excused unexcused absences"
        return text
    return ""


def build_greeting_reply(
    user_text: str,
    *,
    active_user: Optional[str] = None,
    default_local_user_id_fn: Callable[[], str],
) -> Optional[str]:
    text = (user_text or "").strip().lower()
    match = re.compile(r"^(hi|hello|hey|good morning|good afternoon|good evening)([\s!,\.]|$)").match(text)
    if not match:
        return None

    rest = text[match.end():].strip()
    rest = re.sub(r"^nova\b[\s,:\-]*", "", rest, flags=re.I).strip()
    request_markers = [
        "can you", "could you", "would you", "please", "give me", "check", "show", "tell me",
        "weather", "web", "search", "find", "read", "list", "inspect", "health", "help",
    ]
    if rest and any(marker in rest for marker in request_markers):
        return None

    who = _display_active_user(active_user, default_local_user_id_fn=default_local_user_id_fn)
    has_how_are_you = bool(re.search(r"\bhow\s+are\s+you\b", text))
    if has_how_are_you:
        return f"Hey {who}. I'm doing good today. What's going on?" if who else "Hey. I'm doing good today. What's going on?"

    word = match.group(1)
    if word in {"hi", "hello"}:
        return f"Hi {who}." if who else "Hello."
    if word == "hey":
        return f"Hey {who}. What do you need?" if who else "Hey, what do you need?"
    return f"{word.capitalize()}, {who}." if who else f"{word.capitalize()}."


def quick_smalltalk_reply(
    user_text: str,
    *,
    active_user: Optional[str] = None,
    build_greeting_reply_fn: Callable[[str], Optional[str]],
) -> Optional[str]:
    text = (user_text or "").strip().lower()
    if not text:
        return "Okay."

    who = _display_active_user(active_user, default_local_user_id_fn=lambda: "")

    greeting = build_greeting_reply_fn(user_text)
    if greeting:
        return greeting

    normalized = re.sub(r"[^a-z0-9 ]+", " ", text)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    if normalized.startswith("how are you doing") or normalized.startswith("how is your day going") or normalized.startswith("are you doing alright today nova"):
        return f"Hey {who}. I'm doing good today. What's going on?" if who else "Hey. I'm doing good today. What's going on?"
    if "thank you" in text or text in {"thanks", "thx"}:
        return "You're welcome."
    if any(phrase in text for phrase in ["ready to get to work", "ready to work", "ready when you are"]):
        return "Ready when you are. What's the task for today?"
    if any(phrase in text for phrase in ["who is your developer", "who's your developer"]):
        return "My developer is Gustavo (Gus). He created me."
    return None


def is_declarative_info(text: str) -> bool:
    raw = (text or "").strip()
    if not raw:
        return False
    low = raw.lower()
    if "?" in raw:
        return False

    request_markers = [
        "can you", "could you", "would you", "do you", "what ", "how ", "why ", "where ", "when ", "which ",
        "curious", "capable", "abilities", "ability", "know what", "tell me", "give me",
    ]
    if any(marker in low for marker in request_markers):
        return False

    declarative_prefixes = [
        "my name is",
        "i am",
        "i'm",
        "my location is",
        "i live in",
        "i work at",
        "i'm from",
        "i was born",
        "i have",
        "this is",
    ]
    for prefix in declarative_prefixes:
        if low.startswith(prefix) and len(raw.split()) >= 2:
            return True
    return len(raw.split()) <= 6 and any(word in low for word in ["live", "located", "from", "born", "work"])


def is_explicit_request(text: str) -> bool:
    raw = (text or "").strip()
    if not raw:
        return False
    low = raw.lower().strip()
    qwords = ["who", "what", "when", "where", "why", "how", "which"]
    if low.endswith("?"):
        return True
    if any(low.startswith(word + " ") for word in qwords):
        return True
    if any(keyword in low for keyword in ["please", "could you", "can you", "would you", "show me", "find", "search", "do you"]):
        return True
    verbs = ["open", "run", "create", "save", "search", "find", "read", "show", "list", "fetch", "gather"]
    first = low.split()[0]
    return first in verbs


def split_turn_clauses(text: str) -> list[str]:
    raw = str(text or "").strip()
    if not raw:
        return []
    pieces: list[str] = []
    for chunk in re.split(r"[.!?;]+", raw):
        fragment = str(chunk or "").strip(" \t\r\n\"'")
        if not fragment:
            continue
        subparts = re.split(
            r"(?:,\s*|\b(?:and|but)\s+)(?=(?:can|could|would|do|does|did|what|how|why|where|when|which|please|show|tell|give|check|find|search|look|fetch|gather)\b)",
            fragment,
            flags=re.I,
        )
        for subpart in subparts:
            cleaned = str(subpart or "").strip(" \t\r\n\"'")
            if cleaned:
                pieces.append(cleaned)
    return pieces


def is_statement_like_clause(
    text: str,
    *,
    is_explicit_request_fn: Callable[[str], bool],
    is_explicit_command_like_fn: Callable[[str], bool],
    is_declarative_info_fn: Callable[[str], bool],
) -> bool:
    raw = str(text or "").strip()
    if not raw:
        return False
    low = raw.lower()
    if is_explicit_request_fn(raw) or is_explicit_command_like_fn(raw):
        return False
    if is_declarative_info_fn(raw):
        return True
    if low.startswith(("i wonder if", "i'm wondering if", "i am wondering if")):
        return False
    if len(raw.split()) < 3:
        return False
    subject_markers = ("the ", "this ", "that ", "it ", "i ", "we ", "you ", "he ", "she ", "they ")
    verb_markers = (" is ", " are ", " was ", " were ", " looks ", " look ", " seems ", " seem ", " feels ", " feel ", " stays ", " stay ", " remains ", " remain ", " has ", " have ")
    return low.startswith(subject_markers) and any(marker in low for marker in verb_markers)


def looks_like_correction_turn(
    text: str,
    *,
    is_negative_feedback_fn: Callable[[str], bool],
    parse_correction_fn: Callable[[str], object],
) -> bool:
    raw = str(text or "").strip()
    if not raw:
        return False
    low = raw.lower()
    identity_correction_patterns = (
        r"\byour\s+name\s+is\s+[a-z]",
        r"\b(?:his|the\s+developer(?:'s)?)\s+full\s+name\s+is\s+[a-z]",
        r"\bdeveloper(?:'s)?\s+name\s+is\s+[a-z]",
        r"\bcreator(?:'s)?\s+full\s+name\s+is\s+[a-z]",
    )
    triggers = (
        "wrong",
        "no,",
        "actually",
        "that's not",
        "that is not",
        "not true",
        "incorrect",
        "mistake",
        "you lied",
        "correction:",
        "you gave me garbage",
        "garbage back",
    )
    if is_negative_feedback_fn(raw) or parse_correction_fn(raw):
        return True
    if any(trigger in low for trigger in triggers):
        return True
    return "?" not in raw and any(re.search(pattern, low) for pattern in identity_correction_patterns)


def assistant_offered_weather_lookup(text: str, *, normalize_turn_text_fn: Callable[[str], str]) -> bool:
    normalized = normalize_turn_text_fn(text)
    if not normalized:
        return False
    return any(
        phrase in normalized
        for phrase in (
            "what location should i use for the weather lookup",
            "tell me what location to use",
            "ask for our current location",
            "check the weather for you",
        )
    )


def looks_like_continue_thread_turn(
    text: str,
    *,
    turns: Optional[list[tuple[str, str]]] = None,
    active_subject: str = "",
    pending_action: Optional[dict] = None,
    last_assistant_turn_text_fn: Callable[[Optional[list[tuple[str, str]]]], str],
    looks_like_contextual_followup_fn: Callable[[str], bool],
    extract_retrieval_result_index_fn: Callable[[str], Optional[int]],
    looks_like_affirmative_followup_fn: Callable[[str], bool],
    looks_like_shared_location_reference_fn: Callable[[str], bool],
    assistant_offered_weather_lookup_fn: Callable[[str], bool],
) -> bool:
    raw = str(text or "").strip()
    if not raw:
        return False
    normalized_active_subject = str(active_subject or "").strip()
    pending = pending_action if isinstance(pending_action, dict) else {}
    assistant_turn = last_assistant_turn_text_fn(list(turns or []))
    thread_active = bool(normalized_active_subject or str(pending.get("kind") or "").strip() or assistant_turn)
    if not thread_active:
        return False
    if looks_like_contextual_followup_fn(raw):
        return True
    if extract_retrieval_result_index_fn(raw) is not None:
        return True
    if looks_like_affirmative_followup_fn(raw) or looks_like_shared_location_reference_fn(raw):
        return True
    return bool(assistant_turn) and assistant_offered_weather_lookup_fn(assistant_turn) and looks_like_affirmative_followup_fn(raw)


def classify_turn_acts(
    text: str,
    *,
    turns: Optional[list[tuple[str, str]]] = None,
    active_subject: str = "",
    pending_action: Optional[dict] = None,
    split_turn_clauses_fn: Callable[[str], list[str]],
    is_explicit_command_like_fn: Callable[[str], bool],
    looks_like_correction_turn_fn: Callable[[str], bool],
    is_explicit_request_fn: Callable[[str], bool],
    is_statement_like_clause_fn: Callable[[str], bool],
    looks_like_continue_thread_turn_fn: Callable[..., bool],
) -> list[str]:
    raw = str(text or "").strip()
    if not raw:
        return []
    clauses = split_turn_clauses_fn(raw) or [raw]
    has_command = is_explicit_command_like_fn(raw)
    has_correct = looks_like_correction_turn_fn(raw)
    has_ask = any(is_explicit_request_fn(clause) for clause in clauses)
    has_inform = any(is_statement_like_clause_fn(clause) for clause in clauses)
    has_continue_thread = looks_like_continue_thread_turn_fn(
        raw,
        turns=turns,
        active_subject=active_subject,
        pending_action=pending_action,
    )

    acts: list[str] = []
    if has_correct:
        acts.append("correct")
    if has_command:
        acts.append("command")
    elif has_ask:
        acts.append("ask")
    if has_inform:
        acts.append("inform")
    if has_continue_thread:
        acts.append("continue_thread")
    if has_inform and (has_ask or has_command):
        acts.append("mixed")
    return acts


def looks_like_mixed_info_request_turn(text: str, *, classify_turn_acts_fn: Callable[[str], list[str]]) -> bool:
    return "mixed" in classify_turn_acts_fn(text)


def mixed_info_request_clarify_reply(text: str) -> str:
    del text
    return (
        "I think you're both giving context and asking me to do something. "
        "Do you want me to treat the first part as context and answer the request, "
        "or focus on just one part first?"
    )