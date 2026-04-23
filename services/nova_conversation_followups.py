from __future__ import annotations

import difflib
import re
from typing import Callable, Optional
from urllib.parse import urlparse


_TURN_TEXT_TOKEN_FIXES = {
    "yor": "your",
    "hou": "you",
    "locaiton": "location",
    "retreiving": "retrieving",
    "tring": "trying",
    "behing": "behind",
    "teh": "the",
}


_TURN_TEXT_ROUTING_VOCAB = {
    "a", "all", "allowlisted", "am", "and", "answer", "anything", "are", "assistant", "can",
    "chat", "continue", "creator", "current", "data", "developer", "do", "does", "else",
    "fetch", "find", "for", "gather", "grounded", "hello", "help", "hi", "how", "i", "info",
    "information", "is", "it", "kind", "know", "last", "local", "location", "me", "more",
    "name", "next", "not", "nova", "of", "on", "online", "physical", "please", "profile",
    "question", "recap", "remember", "research", "resource", "resources", "result", "results",
    "retrieve", "retrieving", "search", "session", "should", "source", "sources", "sure", "tell",
    "that", "the", "then", "this", "topic", "trying", "tsds", "use", "web", "what", "where",
    "which", "who", "why", "you", "your",
}


def make_conversation_state(kind: str, **data) -> dict:
    state = {"kind": str(kind or "").strip()}
    for key, value in data.items():
        state[str(key)] = value
    return state


def conversation_active_subject(state: Optional[dict]) -> str:
    if not isinstance(state, dict):
        return ""
    kind = str(state.get("kind") or "").strip()
    subject = str(state.get("subject") or "").strip()
    if kind and subject:
        return f"{kind}:{subject}"
    return kind


def normalize_turn_token(token: str) -> str:
    core = str(token or "").strip().lower()
    if not core:
        return core
    if core in _TURN_TEXT_TOKEN_FIXES:
        return _TURN_TEXT_TOKEN_FIXES[core]
    if len(core) < 4 or core in _TURN_TEXT_ROUTING_VOCAB:
        return core
    matches = difflib.get_close_matches(core, sorted(_TURN_TEXT_ROUTING_VOCAB), n=1, cutoff=0.89)
    if matches and abs(len(matches[0]) - len(core)) <= 2:
        return matches[0]
    return core


def normalize_turn_text(text: str) -> str:
    raw = re.sub(r"\s+", " ", (text or "").strip().lower())
    if not raw:
        return ""

    normalized_chunks: list[str] = []
    for chunk in raw.split(" "):
        if not chunk or any(marker in chunk for marker in ("://", "/", "@")):
            normalized_chunks.append(chunk)
            continue
        match = re.match(r"^([^a-z']*)([a-z']+)([^a-z']*)$", chunk)
        if not match:
            normalized_chunks.append(chunk)
            continue
        prefix, core, suffix = match.groups()
        normalized_chunks.append(prefix + normalize_turn_token(core) + suffix)
    return " ".join(normalized_chunks)


def looks_like_contextual_followup(
    text: str,
    *,
    normalize_turn_text_fn: Callable[[str], str],
    uses_prior_reference_fn: Callable[[str], bool],
) -> bool:
    normalized = normalize_turn_text_fn(text).strip(" .,!?")
    if not normalized:
        return False
    if normalized in {
        "what did you find",
        "well what did you find",
        "what else",
        "anything else",
        "go on",
        "continue",
        "ok and then",
        "and then",
        "and",
    }:
        return True
    return len(normalized.split()) <= 4 and uses_prior_reference_fn(normalized)


def looks_like_contextual_continuation(text: str, *, normalize_turn_text_fn: Callable[[str], str]) -> bool:
    normalized = normalize_turn_text_fn(text).strip(" .,!?")
    return normalized in {
        "what did you find",
        "well what did you find",
        "what else",
        "anything else",
        "go on",
        "continue",
        "ok and then",
        "and then",
        "and",
    }


def looks_like_profile_followup(text: str, *, normalize_turn_text_fn: Callable[[str], str]) -> bool:
    normalized = normalize_turn_text_fn(text).strip(" .,!?")
    if not normalized:
        return False
    return normalized in {
        "what else",
        "anything else",
        "what more",
        "anything more",
        "go on",
        "continue",
        "and then",
        "ok and then",
        "tell me more",
    }


def is_retrieval_meta_question(text: str, *, normalize_turn_text_fn: Callable[[str], str]) -> bool:
    normalized = normalize_turn_text_fn(text)
    if not normalized:
        return False
    return any(phrase in normalized for phrase in (
        "what type of resources",
        "what resources are you trying to fetch",
        "what kind of resources",
        "what sources are you trying to fetch",
        "what are you trying to fetch",
    ))


def retrieval_meta_reply(state: dict) -> str:
    query = str(state.get("query") or "").strip()
    urls = state.get("urls") if isinstance(state.get("urls"), list) else []
    hosts: list[str] = []
    for url in urls:
        host = (urlparse(str(url)).hostname or "").strip().lower()
        if host and host not in hosts:
            hosts.append(host)
    parts = ["I was trying to fetch allowlisted web sources related to your last question"]
    if query:
        parts[0] += f" about '{query}'"
    parts[0] += "."
    if hosts:
        if len(hosts) == 1:
            parts.append(f"Right now the active source host is {hosts[0]}.")
        else:
            parts.append("Right now the active source hosts are " + ", ".join(hosts[:-1]) + f", and {hosts[-1]}.")
    else:
        parts.append("I was looking for grounded web sources rather than local knowledge files.")
    parts.append("If you want, I can gather one of the listed sources or answer the original question directly from the current chat context.")
    return " ".join(parts)


def non_retrieval_resource_meta_reply() -> str:
    return (
        "I'm not trying to fetch web resources for this question right now. "
        "I should stay with the current chat and the verified facts I already have unless you explicitly ask me to do web research."
    )


def extract_retrieval_result_index(text: str, *, normalize_turn_text_fn: Callable[[str], str]) -> Optional[int]:
    normalized = normalize_turn_text_fn(text)
    if not normalized:
        return None

    match = re.search(r"\b(?:result|source|link|item)\s*(\d{1,2})\b", normalized)
    if match:
        try:
            return max(1, int(match.group(1)))
        except Exception:
            return None

    ordinal_map = {
        "first": 1,
        "second": 2,
        "third": 3,
        "fourth": 4,
        "fifth": 5,
    }
    for word, index in ordinal_map.items():
        if re.search(rf"\b{word}\b", normalized):
            return index
    return None


def looks_like_retrieval_followup(
    text: str,
    *,
    normalize_turn_text_fn: Callable[[str], str],
    extract_retrieval_result_index_fn: Callable[[str], Optional[int]],
) -> bool:
    normalized = normalize_turn_text_fn(text).strip(" .,!?")
    if not normalized:
        return False
    if extract_retrieval_result_index_fn(normalized) is not None:
        return True
    triggers = {
        "what else",
        "anything else",
        "go on",
        "continue",
        "tell me more",
        "more results",
        "another result",
        "another source",
        "next",
        "next result",
        "next source",
        "more sources",
        "and then",
    }
    if normalized in triggers:
        return True
    return any(token in normalized for token in ("more result", "another source", "another result", "next source", "next result"))


def is_retrieval_tool(tool_name: str) -> bool:
    return str(tool_name or "").strip().lower() in {
        "web_search",
        "web_research",
        "web_gather",
        "web_fetch",
        "search",
        "wikipedia_lookup",
        "stackexchange_search",
    }


def retrieval_query_from_text(
    tool_name: str,
    text: str,
    *,
    web_research_query_fn: Callable[[], str],
) -> str:
    raw = str(text or "").strip()
    low = raw.lower()
    tool = str(tool_name or "").strip().lower()

    if tool == "web_research":
        if low in {"web continue", "continue web", "continue web research"}:
            return web_research_query_fn()
        if low.startswith("web research "):
            return raw.split(maxsplit=2)[2].strip() if len(raw.split(maxsplit=2)) >= 3 else ""
    if tool == "web_search":
        if low.startswith("web search "):
            return raw.split(maxsplit=2)[2].strip() if len(raw.split(maxsplit=2)) >= 3 else ""
        if low.startswith("findweb ") or low.startswith("search "):
            return raw.split(maxsplit=1)[1].strip() if len(raw.split(maxsplit=1)) >= 2 else ""
    if tool == "web_gather":
        if low.startswith("web gather "):
            return raw.split(maxsplit=2)[2].strip() if len(raw.split(maxsplit=2)) >= 3 else ""
    if tool == "web_fetch":
        if low.startswith("web "):
            return raw.split(maxsplit=1)[1].strip() if len(raw.split(maxsplit=1)) >= 2 else ""
    if tool == "wikipedia_lookup":
        if low.startswith("wikipedia "):
            return raw.split(maxsplit=1)[1].strip() if len(raw.split(maxsplit=1)) >= 2 else ""
        if low.startswith("wiki "):
            return raw.split(maxsplit=1)[1].strip() if len(raw.split(maxsplit=1)) >= 2 else ""
    if tool == "stackexchange_search":
        if low.startswith("stackexchange "):
            return raw[len("stackexchange "):].strip()
        if low.startswith("stack overflow "):
            return raw[len("stack overflow "):].strip()
    return raw


def provider_name_from_tool(tool_name: str) -> str:
    mapping = {
        "wikipedia_lookup": "wikipedia",
        "stackexchange_search": "stackexchange",
        "web_research": "general_web",
        "web_search": "general_web",
        "web_fetch": "general_web",
        "web_gather": "general_web",
    }
    return str(mapping.get(str(tool_name or "").strip().lower(), "")).strip()


def make_retrieval_conversation_state(
    tool_name: str,
    query: str,
    tool_output: str,
    *,
    extract_urls_fn: Callable[[str], list[str]],
    make_conversation_state_fn: Callable[..., dict],
    web_research_has_results_fn: Callable[[], bool],
    web_research_result_count_fn: Callable[[], int],
    web_research_query_fn: Callable[[], str],
) -> Optional[dict]:
    if not is_retrieval_tool(tool_name):
        return None

    output = str(tool_output or "")
    if not output.strip():
        return None

    urls = extract_urls_fn(output)[:8]
    result_count = len(urls)
    normalized_tool = str(tool_name or "").strip().lower()
    effective_query = str(query or "").strip()

    if normalized_tool == "web_research":
        if web_research_has_results_fn():
            result_count = web_research_result_count_fn()
        if not effective_query:
            effective_query = web_research_query_fn()

    if not urls and normalized_tool not in {"web_research", "web_gather", "web_fetch"}:
        return None

    state = make_conversation_state_fn(
        "retrieval",
        subject=normalized_tool or "retrieval",
        query=effective_query,
        result_count=max(result_count, 0),
        urls=urls,
    )
    if urls:
        state["top_url"] = urls[0]
    return state


def make_queue_status_conversation_state(
    tool_output: str,
    *,
    load_generated_queue_payload_fn: Callable[[int], dict],
    make_conversation_state_fn: Callable[..., dict],
) -> Optional[dict]:
    if not str(tool_output or "").strip():
        return None

    queue = load_generated_queue_payload_fn(12)
    if not queue:
        return None

    next_item = queue.get("next_item") if isinstance(queue.get("next_item"), dict) else {}
    highest = next_item.get("highest_priority") if isinstance(next_item.get("highest_priority"), dict) else {}
    return make_conversation_state_fn(
        "queue_status",
        subject="generated_work_queue",
        count=int(queue.get("count", 0) or 0),
        open_count=int(queue.get("open_count", 0) or 0),
        green_count=int(queue.get("green_count", 0) or 0),
        drift_count=int(queue.get("drift_count", 0) or 0),
        warning_count=int(queue.get("warning_count", 0) or 0),
        never_run_count=int(queue.get("never_run_count", 0) or 0),
        next_item=dict(next_item),
        next_file=str(next_item.get("file") or "").strip(),
        next_family=str(next_item.get("family_id") or "").strip(),
        next_status=str(next_item.get("latest_status") or "").strip(),
        next_reason=str(next_item.get("opportunity_reason") or "").strip(),
        next_report_path=str(next_item.get("latest_report_path") or "").strip(),
        next_signal=str(highest.get("signal") or "").strip(),
        next_urgency=str(highest.get("urgency") or "").strip(),
        next_seam=str(highest.get("seam") or "").strip(),
    )


def make_tool_conversation_state(
    tool_name: str,
    query: str,
    tool_output: str,
    *,
    make_retrieval_conversation_state_fn: Callable[[str, str, str], Optional[dict]],
    make_queue_status_conversation_state_fn: Callable[[str], Optional[dict]],
) -> Optional[dict]:
    next_state = make_retrieval_conversation_state_fn(tool_name, query, tool_output)
    if next_state is not None:
        return next_state
    if str(tool_name or "").strip().lower() == "queue_status":
        return make_queue_status_conversation_state_fn(tool_output)
    return None


def infer_post_reply_conversation_state(
    routed_text: str,
    *,
    planner_decision: str,
    tool: str = "",
    tool_args: Optional[dict] = None,
    tool_result: str = "",
    turns: Optional[list[tuple[str, str]]] = None,
    fallback_state: Optional[dict] = None,
    make_tool_conversation_state_fn: Callable[[str, str, str], Optional[dict]],
    infer_profile_conversation_state_fn: Callable[[str], Optional[dict]],
    is_location_recall_query_fn: Callable[[str], bool],
    looks_like_location_recall_followup_fn: Callable[[list[tuple[str, str]], str], bool],
    make_conversation_state_fn: Callable[..., dict],
) -> Optional[dict]:
    next_state = None
    if planner_decision == "run_tool":
        args_dict = tool_args if isinstance(tool_args, dict) else {}
        action_args = args_dict.get("args") if isinstance(args_dict.get("args"), list) else []
        action_query = str(action_args[0] if action_args else routed_text)
        next_state = make_tool_conversation_state_fn(tool, action_query, tool_result)
    if next_state is None:
        inferred_profile_state = infer_profile_conversation_state_fn(routed_text)
        if inferred_profile_state is not None:
            next_state = inferred_profile_state
        elif is_location_recall_query_fn(routed_text) or looks_like_location_recall_followup_fn(turns or [], routed_text):
            next_state = make_conversation_state_fn("location_recall")
    return next_state if isinstance(next_state, dict) else (fallback_state if isinstance(fallback_state, dict) else None)


def retrieval_followup_reply(
    state: dict,
    text: str,
    *,
    extract_retrieval_result_index_fn: Callable[[str], Optional[int]],
    make_retrieval_conversation_state_fn: Callable[[str, str, str], Optional[dict]],
    looks_like_retrieval_followup_fn: Callable[[str], bool],
    tool_web_gather_fn: Callable[[str], str],
    tool_web_research_continue_fn: Callable[[], str],
    web_research_query_fn: Callable[[], str],
) -> tuple[str, Optional[dict]]:
    urls = state.get("urls") if isinstance(state.get("urls"), list) else []
    query = str(state.get("query") or "").strip()
    source = str(state.get("subject") or "retrieval").strip().lower()
    result_count = max(0, int(state.get("result_count", 0) or 0))
    index = extract_retrieval_result_index_fn(text)

    if index is not None and 1 <= index <= len(urls):
        result = tool_web_gather_fn(str(urls[index - 1]))
        return result, (make_retrieval_conversation_state_fn("web_gather", str(urls[index - 1]), result) or state)

    if source == "web_research" and looks_like_retrieval_followup_fn(text):
        result = tool_web_research_continue_fn()
        if result and not result.lower().startswith("no active web research session"):
            return result, (make_retrieval_conversation_state_fn("web_research", web_research_query_fn(), result) or state)

    parts = []
    if query:
        parts.append(f"Continuing from your last retrieval for '{query}'.")
    else:
        parts.append("Continuing from your last retrieval thread.")
    if result_count > 0:
        parts.append(f"I have {result_count} source(s) in the current retrieval context.")
    if urls:
        parts.append("You can ask me about the first result, the second source, or tell me to gather one directly.")
    else:
        parts.append("If you want, I can run a more specific search or gather a particular source.")
    return " ".join(parts), state


def is_queue_status_reason_followup(text: str, *, normalize_turn_text_fn: Callable[[str], str]) -> bool:
    normalized = normalize_turn_text_fn(text).strip(" .,!?")
    if not normalized:
        return False
    return any(
        phrase in normalized
        for phrase in (
            "why is that the next item in the queue",
            "why is that next in the queue",
            "why is that next",
            "why is that the next item",
            "why is that next item",
            "why that item",
            "why this item",
        )
    )


def queue_status_reason_reply(state: dict) -> str:
    next_file = str(state.get("next_file") or "").strip()
    next_status = str(state.get("next_status") or "unknown").strip() or "unknown"
    next_reason = str(state.get("next_reason") or "unknown").strip() or "unknown"
    next_signal = str(state.get("next_signal") or "").strip()
    next_urgency = str(state.get("next_urgency") or "").strip()
    next_seam = str(state.get("next_seam") or "").strip()
    next_family = str(state.get("next_family") or "").strip()

    if not next_file:
        return "There is no next open queue item right now because the generated work queue is clear."

    parts = [f"{next_file} is next because it is still open with status {next_status} and reason {next_reason}."]
    if next_signal:
        signal_text = f"Its highest-priority signal is {next_signal}"
        if next_urgency:
            signal_text += f" at {next_urgency} urgency"
        if next_seam:
            signal_text += f" on seam {next_seam}"
        parts.append(signal_text + ".")
    if next_family:
        parts.append(f"It currently leads the {next_family} family among open generated queue items.")
    return " ".join(parts)


def is_queue_status_report_followup(text: str, *, normalize_turn_text_fn: Callable[[str], str]) -> bool:
    normalized = normalize_turn_text_fn(text).strip(" .,!?")
    if not normalized:
        return False
    return any(
        phrase in normalized
        for phrase in (
            "show me the report path",
            "what is the report path",
            "where is the report",
            "where is the latest report",
            "show me the latest report",
        )
    )


def queue_status_report_reply(state: dict) -> str:
    next_file = str(state.get("next_file") or "").strip()
    report_path = str(state.get("next_report_path") or "").strip()
    if not report_path:
        if next_file:
            return f"I don't have a saved report path yet for {next_file}."
        return "I don't have a saved report path because there is no current open queue item."
    if next_file:
        return f"The latest report for {next_file} is at {report_path}"
    return f"The latest queue report path is {report_path}"


def is_queue_status_seam_followup(text: str, *, normalize_turn_text_fn: Callable[[str], str]) -> bool:
    normalized = normalize_turn_text_fn(text).strip(" .,!?")
    if not normalized:
        return False
    return any(
        phrase in normalized
        for phrase in (
            "what seam is it failing on",
            "what seam is it on",
            "which seam is failing",
            "what seam",
        )
    )


def queue_status_seam_reply(state: dict) -> str:
    next_file = str(state.get("next_file") or "").strip()
    next_seam = str(state.get("next_seam") or "").strip()
    next_signal = str(state.get("next_signal") or "").strip()
    if not next_seam:
        if next_file:
            return f"I don't have a recorded seam yet for {next_file}."
        return "I don't have a recorded seam because there is no current open queue item."
    if next_signal:
        return f"{next_file or 'That queue item'} is currently failing on seam {next_seam} with signal {next_signal}."
    return f"{next_file or 'That queue item'} is currently failing on seam {next_seam}."


def is_location_recall_state(state: Optional[dict]) -> bool:
    return isinstance(state, dict) and str(state.get("kind") or "") == "location_recall"


def looks_like_location_recall_followup(
    session_turns: list[tuple[str, str]],
    text: str,
    *,
    looks_like_contextual_continuation_fn: Callable[[str], bool],
) -> bool:
    if looks_like_contextual_continuation_fn(text):
        recent = session_turns[-6:] if isinstance(session_turns, list) else []
        for _role, content in reversed(recent):
            low = str(content or "").strip().lower()
            if not low:
                continue
            if low.startswith("your saved location is") or low.startswith("i don't have a stored location yet"):
                return True
    t = re.sub(r"\s+", " ", (text or "").strip().lower())
    t = re.sub(r"\s*\?+$", "", t).strip()
    if t not in {"what did you find", "well what did you find"}:
        return False
    recent = session_turns[-6:] if isinstance(session_turns, list) else []
    for _role, content in reversed(recent):
        low = str(content or "").strip().lower()
        if not low:
            continue
        if "location" in low and any(cue in low for cue in ("recall", "remember", "saved", "stored", "current physical location")):
            return True
        if low.startswith("your saved location is") or low.startswith("i don't have a stored location yet"):
            return True
    return False