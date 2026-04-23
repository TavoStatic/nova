from __future__ import annotations

import ast
import re
from typing import Callable, Optional


def parse_correction(text: str) -> Optional[str]:
    """Parse a freeform correction and return the corrected reply if found."""
    if not text:
        return None
    candidate = text.strip()
    patterns = [
        r"^(?:no|nah|nope|that's wrong|wrong|not quite|don't)\b.*(?:say|respond|reply|use)\s+[\"'](.+?)[\"'](?:\s*instead)?$",
        r"^(?:say|respond|reply|use)\s+[\"'](.+?)[\"']\s*(?:instead)?$",
        r".*instead[,:\s]+[\"']?(.+?)[\"']?$",
    ]
    for pattern in patterns:
        match = re.match(pattern, candidate, flags=re.I)
        if not match:
            continue
        correction = match.group(1).strip()
        if correction:
            return correction
    return None


def looks_like_correction_cancel(text: str, *, normalize_turn_text: Callable[[str], str]) -> bool:
    normalized = normalize_turn_text(text)
    if not normalized:
        return False
    cues = (
        "dont have to replace",
        "don't have to replace",
        "no need to replace",
        "you dont have to replace",
        "you don't have to replace",
        "i was just small talk",
        "it was just small talk",
        "just small talk",
        "leave it alone",
        "never mind that correction",
        "nevermind that correction",
    )
    return any(cue in normalized for cue in cues)


def looks_like_pending_replacement_text(text: str, *, normalize_turn_text: Callable[[str], str]) -> bool:
    raw = str(text or "").strip()
    if not raw or "?" in raw:
        return False
    if bool(re.fullmatch(r"['\"].+['\"]", raw)):
        return True
    normalized = normalize_turn_text(raw)
    words = [word for word in normalized.split() if word]
    if not words:
        return False
    return len(words) <= 4


def safe_eval_arithmetic_expression(expr: str) -> Optional[float]:
    text = str(expr or "").strip()
    if not text:
        return None
    try:
        node = ast.parse(text, mode="eval")
    except Exception:
        return None

    def _eval(current: ast.AST) -> float:
        if isinstance(current, ast.Expression):
            return _eval(current.body)
        if isinstance(current, ast.Constant) and isinstance(current.value, (int, float)):
            return float(current.value)
        if isinstance(current, ast.UnaryOp) and isinstance(current.op, (ast.UAdd, ast.USub)):
            value = _eval(current.operand)
            return value if isinstance(current.op, ast.UAdd) else -value
        if isinstance(current, ast.BinOp) and isinstance(current.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)):
            left = _eval(current.left)
            right = _eval(current.right)
            if isinstance(current.op, ast.Add):
                return left + right
            if isinstance(current.op, ast.Sub):
                return left - right
            if isinstance(current.op, ast.Mult):
                return left * right
            if right == 0:
                raise ZeroDivisionError()
            return left / right
        raise ValueError("unsupported_expression")

    try:
        return _eval(node)
    except Exception:
        return None


def is_negative_feedback(text: str) -> bool:
    normalized = str(text or "").strip().lower()
    cues = [
        "you are wrong",
        "you're wrong",
        "that is wrong",
        "you gave me garbage",
        "that is garbage",
        "not correct",
        "not right",
        "that is not true",
        "you made that up",
        "what happen",
        "what happened",
    ]
    return any(cue in normalized for cue in cues)


def extract_authoritative_correction_text(text: str) -> Optional[str]:
    candidate = str(text or "").strip()
    if not candidate:
        return None

    correction = parse_correction(candidate)
    if correction:
        return correction

    normalized = candidate.lower()
    if "?" in candidate and len(candidate) < 220:
        return None

    if len(candidate) >= 80:
        cleaned = re.sub(
            r"(?is)^\s*(you're right about something|you are right about something|listen|look)\s*[,:.-]*\s*",
            "",
            candidate,
        ).strip()
        return cleaned or None

    short_decl_patterns = [
        r"^\s*my\s+name\s+is\s+.+",
        r"^\s*your\s+name\s+is\s+.+",
        r"^\s*please\s+use\s+.+",
    ]
    if any(re.match(pattern, normalized) for pattern in short_decl_patterns):
        return candidate

    return None


def normalize_correction_for_storage(correction: str) -> str:
    cleaned = re.sub(r"\s+", " ", (correction or "").strip())
    if not cleaned:
        return cleaned

    matched_name = re.search(r"(?i)\bmy\s+name\s+is\s+[^.?!]+", cleaned)
    if matched_name:
        return matched_name.group(0).strip().rstrip(".?!") + "."

    parts = re.split(r"(?<=[.!?])\s+", cleaned)
    return (parts[0] if parts else cleaned).strip()


def looks_like_correction_turn(text: str) -> bool:
    raw = str(text or "").strip()
    if not raw:
        return False
    normalized = raw.lower()
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
    if is_negative_feedback(raw) or parse_correction(raw):
        return True
    if any(trigger in normalized for trigger in triggers):
        return True
    return "?" not in raw and any(re.search(pattern, normalized) for pattern in identity_correction_patterns)