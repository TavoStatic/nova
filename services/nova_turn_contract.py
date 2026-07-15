from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable

from services.evidence_validity import invalid_tool_result

VALID_CHANNELS = frozenset({"cli", "http", "voice", "control"})
VALID_INPUT_SOURCES = frozenset({"typed", "voice", "http"})

_ATTACHMENT_VISION_CUES = (
    "can you see",
    "look at it",
    "look at this",
    "inspect it",
    "inspect this",
    "review it",
    "review this",
    "what do you see",
    "describe it",
    "describe this",
    "what is in",
    "what's in",
)


@dataclass
class TurnRequest:
    text: str
    channel: str = "http"
    input_source: str = "http"
    session_id: str = ""
    user_id: str = ""
    attachments: list[dict[str, Any]] = field(default_factory=list)
    work_tree_seed_source: str = ""


def normalize_channel(channel: str) -> str:
    clean = str(channel or "").strip().lower()
    return clean if clean in VALID_CHANNELS else "http"


def normalize_input_source(input_source: str, *, channel: str = "") -> str:
    clean = str(input_source or "").strip().lower()
    if clean in VALID_INPUT_SOURCES:
        return clean
    channel_clean = normalize_channel(channel)
    if channel_clean in {"cli", "control"}:
        return "typed"
    if channel_clean == "voice":
        return "voice"
    return "http"


def default_work_tree_seed_source(channel: str) -> str:
    channel_clean = normalize_channel(channel)
    if channel_clean == "cli":
        return "cli"
    return "http"


def bind_turn_request(
    *,
    text: str,
    channel: str = "http",
    input_source: str = "",
    session_id: str = "",
    user_id: str = "",
    attachments: list[dict[str, Any]] | None = None,
    work_tree_seed_source: str = "",
) -> TurnRequest:
    channel_clean = normalize_channel(channel)
    return TurnRequest(
        text=str(text or "").strip(),
        channel=channel_clean,
        input_source=normalize_input_source(input_source, channel=channel_clean),
        session_id=str(session_id or "").strip(),
        user_id=str(user_id or "").strip(),
        attachments=[dict(item) for item in list(attachments or []) if isinstance(item, dict)],
        work_tree_seed_source=str(work_tree_seed_source or "").strip() or default_work_tree_seed_source(channel_clean),
    )


def _normalized_message(text: str) -> str:
    return " ".join(str(text or "").strip().lower().split())


def _attachment_requests_vision(message: str) -> bool:
    normalized = _normalized_message(message)
    if not normalized:
        return True
    return any(cue in normalized for cue in _ATTACHMENT_VISION_CUES)


def _staged_image_from_attachments(attachments: list[dict[str, Any]]) -> dict[str, Any] | None:
    for item in attachments:
        mime = str(item.get("mime") or "").strip().lower()
        source = str(item.get("source") or "").strip().lower()
        path = str(item.get("path") or "").strip()
        if not path:
            continue
        if mime.startswith("image/") or source == "camera":
            return dict(item)
    return None


def _staged_image_from_context_text(text: str) -> str:
    body = str(text or "")
    if "[leah session context]" not in body.lower():
        return ""
    if "image/" not in body.lower() and "camera:" not in body.lower():
        return ""
    match = re.search(r"path=([^\s|]+)", body, flags=re.IGNORECASE)
    return str(match.group(1) or "").strip() if match else ""


def maybe_run_attachment_vision_turn(
    *,
    text: str,
    attachments: list[dict[str, Any]] | None,
    core,
    trace: Callable[..., None],
    normalize_reply: Callable[[str], str],
) -> tuple[str, dict[str, Any]] | None:
    staged = _staged_image_from_attachments(list(attachments or []))
    image_path = str((staged or {}).get("path") or "").strip()
    if not image_path:
        image_path = _staged_image_from_context_text(text)
    if not image_path:
        return None
    if not _attachment_requests_vision(text):
        return None

    prompt = str(text or "").strip() or "Describe what you see in this image."
    trace("attachment_vision", "started", image_path=image_path)
    try:
        execute_fn = getattr(core, "execute_planned_action", None)
        if not callable(execute_fn):
            return None
        out = execute_fn(
            "vision",
            {"action": "describe_file", "path": image_path, "prompt": prompt},
        )
    except Exception as exc:
        trace("attachment_vision", "error", error=str(exc))
        reply = normalize_reply(f"Vision could not analyze the staged image: {exc}")
        return reply, {
            "planner_decision": "run_tool",
            "tool": "vision",
            "tool_args": {"action": "describe_file", "path": image_path, "prompt": prompt},
            "tool_result": str(exc),
            "grounded": False,
            "reply_contract": "attachment_vision.failed",
            "reply_outcome": {"kind": "vision_failed"},
        }

    invalid, reason = invalid_tool_result("vision", out)
    if invalid:
        trace("attachment_vision", "invalid_result", reason=reason)
        reply = normalize_reply(f"Vision could not analyze the staged image: {reason}")
        return reply, {
            "planner_decision": "run_tool",
            "tool": "vision",
            "tool_args": {"action": "describe_file", "path": image_path, "prompt": prompt},
            "tool_result": str(out or reason),
            "grounded": False,
            "reply_contract": "attachment_vision.invalid",
            "reply_outcome": {"kind": "vision_invalid"},
        }

    rendered = normalize_reply(str(out or "").strip())
    trace("attachment_vision", "ok", chars=len(rendered))
    return rendered, {
        "planner_decision": "run_tool",
        "tool": "vision",
        "tool_args": {"action": "describe_file", "path": image_path, "prompt": prompt},
        "tool_result": str(out or ""),
        "grounded": bool(rendered.strip()),
        "reply_contract": "attachment_vision.describe_file",
        "reply_outcome": {"kind": "vision_describe_file"},
    }


def execute_conversation_turn(
    *,
    execute_reply_sequence_fn: Callable[..., tuple[str, dict]],
    turn: TurnRequest,
    **kwargs: Any,
) -> tuple[str, dict]:
    options = dict(kwargs or {})
    options["text"] = turn.text
    options["input_source"] = turn.input_source
    options["work_tree_seed_source"] = turn.work_tree_seed_source or default_work_tree_seed_source(turn.channel)
    options["attachments"] = list(turn.attachments)
    return execute_reply_sequence_fn(**options)