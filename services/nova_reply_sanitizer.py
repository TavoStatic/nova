from __future__ import annotations

import re
from typing import Callable


def sanitize_llm_reply(
    reply: str,
    tool_context: str = "",
    *,
    weather_unavailable_message_fn: Callable[[], str],
    describe_capabilities_fn: Callable[[], str],
) -> str:
    del describe_capabilities_fn
    rendered = (reply or "").strip()
    lowered = rendered.lower()

    scan_patterns = [
        r"starting nmap",
        r"nmap scan report",
        r"c:\\>nmap",
        r"host is up",
        r"port\s+state\s+service",
        r"i'm running a system scan",
        r"scan report for",
    ]
    for pattern in scan_patterns:
        if re.search(pattern, lowered):
            return (
                "I didn’t run any scans or system commands. I won’t fabricate scan outputs. "
                "If you want a scan, run the tool and paste the real output and I’ll interpret it."
            )

    if re.search(r"\bi\s+(?:fetched|retrieved|got)\s+(?:the\s+)?weather", lowered):
        tool_context_lower = (tool_context or "").lower()
        if "weather for" not in tool_context_lower and "source: wttr.in" not in tool_context_lower:
            return weather_unavailable_message_fn()

    weather_promise_patterns = [
        r"i(?:'| wi)?ll try to find out(?: the weather)?",
        r"let me check(?: the weather)?",
        r"i can try to find out(?: the weather)?",
        r"i(?:'| wi)?ll check(?: the weather)?",
        r"i(?:'| a)m going to check(?: the weather)?",
    ]
    if any(token in lowered for token in ("weather", "rain", "forecast")):
        tool_context_lower = (tool_context or "").lower()
        if "weather for" not in tool_context_lower and "source: wttr.in" not in tool_context_lower:
            for pattern in weather_promise_patterns:
                if re.search(pattern, lowered):
                    return "I haven't actually run the weather tool yet. Tell me what location to use, or ask for our current location if I already have it saved."

    strong_patterns = [
        r"\bsaved\s+to\b",
        r"\bdownloaded\b",
        r"\bpatch\s+appl(?:y|ied)\b",
        r"\bsnapshot(?:_[\w\-]+)?\b",
        r"\b(?:created|wrote)\s+(?:file|folder|directory)\b",
        r"\b(?:/|\\)[\w\-\.\/]+\.[a-z0-9]{1,6}\b",
    ]

    def _needs_citation(text_lower: str) -> bool:
        return any(re.search(pattern, text_lower) for pattern in strong_patterns)

    if _needs_citation(lowered):
        if "[tool:" not in lowered and "[tool:" not in rendered.lower():
            return (
                "I can’t claim tool outputs unless I include an explicit TOOL citation. "
                "Please run the tool and paste its output or enable tool access; I won't fabricate results."
            )

    cited = re.findall(r"\[TOOL:([a-zA-Z0-9_\-]+)\]", rendered)
    if cited:
        tool_context_lower = (tool_context or "").lower()
        bad_found = False
        for name in cited:
            token = f"[tool:{name.lower()}]"
            if token not in tool_context_lower:
                bad_found = True
        if bad_found:
            cleaned = re.sub(r"\[TOOL:[^\]]+\]", "", rendered).strip()
            cleaned = re.sub(r"\s+", " ", cleaned).strip()
            if cleaned:
                return cleaned
            return (
                "I can’t claim tool outputs unless they come from a real tool run in this chat. "
                "I won’t fabricate TOOL citations."
            )

    offer_patterns = [
        r"how can i (help|assist)",
        r"would you like me to",
        r"do you want me to",
        r"\bi can (help|assist)\b",
        r"i(?:'| i)?ll start (?:research|researching)",
        r"i will start (?:research|researching)",
        r"i(?:'| i)?ll research",
        r"i will research",
        r"\bretriev(?:ing|e)?\b",
    ]

    def _sentence_filter(text: str) -> str:
        parts = re.split(r"(?<=[.!?])\s+", text)
        out = []
        for sentence in parts:
            low_sentence = sentence.lower()
            skip = False
            for pattern in offer_patterns:
                if re.search(pattern, low_sentence):
                    if not (tool_context or ""):
                        skip = True
                        break
            if not skip:
                out.append(sentence)
        return " ".join(out).strip()

    research_patterns = [
        r"i\s*(?:'| i)?ll (?:research|look into|investigate|start researching|go research)",
        r"i will (?:research|look into|investigate|start researching|go research)",
        r"i(?:'| i)?m going to (?:research|look into|investigate)",
    ]

    def _remove_research_promises(text: str) -> str:
        parts = re.split(r"(?<=[.!?])\s+", text)
        out = []
        for sentence in parts:
            low_sentence = sentence.lower()
            skip = False
            for pattern in research_patterns:
                if re.search(pattern, low_sentence):
                    if not (tool_context or ""):
                        skip = True
                        break
            if not skip:
                out.append(sentence)
        return " ".join(out).strip()

    filtered = _sentence_filter(rendered)
    filtered = _remove_research_promises(filtered)

    if re.search(r"https?://", filtered) and not (tool_context or ""):
        filtered = re.sub(r"https?://\S+", "[link removed]", filtered)

    filtered = filtered.strip()
    if not filtered:
        return "Okay."

    return filtered
