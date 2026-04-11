from __future__ import annotations

import re
from typing import Callable


def self_correct_reply(
    user_text: str,
    reply: str,
    *,
    is_capability_query_fn: Callable[[str], bool],
    describe_capabilities_fn: Callable[[], str],
) -> tuple[str, bool, str]:
    out = (reply or "").strip()
    if not out:
        return out, False, ""

    if is_capability_query_fn(user_text):
        target = describe_capabilities_fn().strip()
        if target and re.sub(r"\s+", " ", out).lower() != re.sub(r"\s+", " ", target).lower():
            return target, True, "capability_alignment"

    low = out.lower()
    bad_autonomy = [
        "enhance myself on my own",
        "enhance myself autonomously",
        "i can enhance myself",
        "i will enhance myself",
        "self-sustenance",
    ]
    if any(fragment in low for fragment in bad_autonomy):
        corrected = (
            "I cannot self-enhance on my own. I can only improve through your explicit guidance, "
            "validated tool runs, and saved corrections."
        )
        return corrected, True, "autonomy_guard"

    return out, False, ""


def content_tokens(text: str) -> list[str]:
    raw = re.findall(r"[a-z0-9]{3,}", (text or "").lower())
    ignore = {
        "that", "this", "with", "from", "have", "your", "you", "are", "was", "were", "they",
        "them", "then", "than", "what", "when", "where", "which", "would", "could", "should",
        "about", "into", "also", "just", "told", "known", "know", "remember", "recall", "said",
        "made", "make", "gave", "name", "like", "likes", "favorite", "favourite", "colors", "color",
        "developer", "creator", "nova", "gus",
    }
    out: list[str] = []
    for token in raw:
        if token in ignore:
            continue
        if token not in out:
            out.append(token)
    return out


def is_risky_claim_sentence(sentence: str) -> bool:
    low = (sentence or "").strip().lower()
    if not low:
        return False
    if any(low.startswith(prefix) for prefix in [
        "i don't know", "i do not know", "i'm not sure", "i am not sure", "uncertain", "that would be a guess",
    ]):
        return False
    risky_patterns = [
        r"\b(i remember|i recall|we'?ve had|we have had)\b",
        r"\bcreator\b|\bdeveloper\b|\bfull name\b|\bnickname\b",
        r"\bfavorite\b|\bfavourite\b|\bcolors?\b|\bbilingual\b|\blanguages?\b",
        r"\b(?:i am|i'm)\s+in\s+(?:a|the)\s+room\b|\bwith gus\b",
        r"\bsmell\b|\bcoffee\b|\bhear\b|\bsee\b",
        r"\bcurrent physical location\b|\bmy location is\b|\bI am located\b",
        r"\bdownloaded\b|\bsaved\s+to\b|\bcreated\s+(?:file|folder|directory)\b",
    ]
    return any(re.search(pattern, low) for pattern in risky_patterns)


def sentence_supported_by_evidence(
    sentence: str,
    evidence_text: str,
    tool_context: str = "",
    *,
    is_risky_claim_sentence_fn: Callable[[str], bool],
    content_tokens_fn: Callable[[str], list[str]],
) -> bool:
    low = (sentence or "").strip().lower()
    evidence_low = (evidence_text or "").lower()
    tool_low = (tool_context or "").lower()
    if not low:
        return True
    if not is_risky_claim_sentence_fn(sentence):
        quoted_spans = [span.strip().lower() for span in re.findall(r'"([^"]{8,})"', sentence or "") if span.strip()]
        if quoted_spans:
            combined_evidence = (evidence_low + "\n" + tool_low).strip()
            for span in quoted_spans:
                if span not in combined_evidence:
                    return False
        return True

    impossible_claims = [
        r"\b(?:i am|i'm)\s+in\s+(?:a|the)\s+room\b",
        r"\bsmell\b",
        r"\bhear\b",
        r"\bi can see\b",
    ]
    if any(re.search(pattern, low) for pattern in impossible_claims):
        return False

    tool_claims = [r"\bdownloaded\b", r"\bsaved\s+to\b", r"\bcreated\s+(?:file|folder|directory)\b"]
    if any(re.search(pattern, low) for pattern in tool_claims):
        return bool(tool_low)

    tokens = content_tokens_fn(sentence)
    if not tokens:
        return False
    overlap = [token for token in tokens if token in evidence_low]
    if len(overlap) >= min(2, len(tokens)):
        return True
    if any(name in low and name in evidence_low for name in ["gustavo uribe", "brownsville", "english", "spanish", "silver", "blue", "red"]):
        return True
    return False


def apply_claim_gate(
    reply: str,
    evidence_text: str = "",
    tool_context: str = "",
    *,
    sentence_supported_by_evidence_fn: Callable[[str, str, str], bool],
    truthful_limit_reply_fn: Callable[..., str],
) -> tuple[str, bool, str]:
    raw = (reply or "").strip()
    if not raw:
        return raw, False, ""

    parts = [part.strip() for part in re.split(r"(?<=[.!?])\s+", raw) if (part or "").strip()]
    kept: list[str] = []
    blocked = False
    for part in parts:
        if sentence_supported_by_evidence_fn(part, evidence_text, tool_context):
            kept.append(part)
        else:
            blocked = True

    if not blocked:
        return raw, False, ""
    if kept:
        return " ".join(kept).strip(), True, "unsupported_claim_removed"
    return truthful_limit_reply_fn("", include_next_step=False), True, "unsupported_claim_blocked"