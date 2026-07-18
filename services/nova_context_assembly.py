from __future__ import annotations

import json
import re
from typing import Any, Callable


def render_chat_context(
    turns: list[tuple[str, str]],
    *,
    max_chars: int = 1800,
    current_text: str = "",
    chat_context_turns: int = 6,
) -> str:
    if not turns:
        return ""
    lines = []
    prior_turns = list(turns)
    current = re.sub(r"\s+", " ", str(current_text or "").strip())
    if prior_turns and prior_turns[-1][0] == "user":
        latest = re.sub(r"\s+", " ", str(prior_turns[-1][1] or "").strip())
        if current and latest == current:
            prior_turns = prior_turns[:-1]
    for role, text in prior_turns[-int(chat_context_turns or 6) :]:
        role_name = "User" if role == "user" else "Assistant"
        t = re.sub(r"\s+", " ", (text or "").strip())
        if not t:
            continue
        lines.append(f"{role_name}: {t[:300]}")
    if not lines:
        return ""
    out = "\n".join(lines)
    return out[:max_chars]


def render_session_state_context(
    *,
    conversation_state: dict | None = None,
    pending_action: dict | None = None,
    max_chars: int = 1600,
) -> str:
    lines: list[str] = []
    state = conversation_state if isinstance(conversation_state, dict) else {}
    pending = pending_action if isinstance(pending_action, dict) else {}
    if state:
        kind = str(state.get("kind") or "").strip()
        subject = str(state.get("subject") or "").strip()
        header = "ACTIVE SESSION STATE"
        if kind:
            header += f": {kind}"
        if subject:
            header += f" / {subject}"
        lines.append(header)
        if str(state.get("tool_result") or "").strip():
            lines.append(
                "Prior tool evidence: context only; not current answer authority unless "
                "current structured intent asks for the same live tool evidence."
            )
            lines.append(str(state.get("tool_result") or "").strip()[:1200])
        else:
            public_state = {
                key: value
                for key, value in state.items()
                if key not in {"tool_result"} and value not in (None, "", [], {})
            }
            if public_state:
                lines.append(json.dumps(public_state, ensure_ascii=True, sort_keys=True)[:900])
    if pending:
        lines.append("PENDING ACTION:")
        lines.append(json.dumps(pending, ensure_ascii=True, sort_keys=True)[:600])
    return "\n".join(line for line in lines if str(line or "").strip())[:max_chars]


def build_learning_context_details(
    query: str,
    *,
    conversation_state: dict | None = None,
    pending_action: dict | None = None,
    identity_context_for_prompt_fn: Callable[..., str],
    operational_identity_context_for_prompt_fn: Callable[..., str],
    load_identity_profile_fn: Callable[[], dict],
    load_learned_facts_fn: Callable[[], dict],
    load_capabilities_fn: Callable[[], dict],
    kb_search_fn: Callable[[str], str],
    memory_recall_plan_fn: Callable[..., Any],
    mem_get_recent_learned_fn: Callable[[], list[str]],
    mem_recall_fn: Callable[..., str],
) -> dict:
    blocks = []
    identity_block = identity_context_for_prompt_fn(
        load_identity_profile_fn=load_identity_profile_fn,
        load_learned_facts_fn=load_learned_facts_fn,
    )
    operational_identity_block = operational_identity_context_for_prompt_fn(
        load_capabilities_fn=load_capabilities_fn,
    )
    kb_block = kb_search_fn(query)
    recall_plan = memory_recall_plan_fn(
        query,
        purpose="general_context",
        conversation_state=conversation_state,
        pending_action=pending_action,
    )
    mem_block = ""
    if bool(getattr(recall_plan, "allow", False)):
        recall_purpose = str(getattr(recall_plan, "purpose", "") or "general").strip() or "general"
        if recall_purpose == "recent_learning_summary":
            recent_items = mem_get_recent_learned_fn()
            if recent_items:
                mem_block = "Recent learning:\n" + "\n".join(f"- {item}" for item in recent_items)
        else:
            mem_block = mem_recall_fn(
                query,
                purpose=recall_purpose,
                conversation_state=conversation_state,
                pending_action=pending_action,
            )

    if identity_block:
        blocks.append(identity_block)

    if operational_identity_block:
        blocks.append(operational_identity_block)

    if kb_block:
        blocks.append(kb_block)

    if mem_block:
        # Keep memory context for the LLM but avoid injecting visible markers into user-facing reply.
        blocks.append(mem_block)

    if not blocks:
        return {
            "context": "",
            "knowledge_used": False,
            "identity_used": False,
            "operational_identity_used": False,
            "memory_used": False,
            "knowledge_chars": 0,
            "identity_chars": 0,
            "operational_identity_chars": 0,
            "memory_chars": 0,
        }

    context = "\n\n".join(blocks)[:4000]
    return {
        "context": context,
        "knowledge_used": bool(kb_block),
        "identity_used": bool(identity_block),
        "operational_identity_used": bool(operational_identity_block),
        "memory_used": bool(mem_block),
        "knowledge_chars": len(kb_block or ""),
        "identity_chars": len(identity_block or ""),
        "operational_identity_chars": len(operational_identity_block or ""),
        "memory_chars": len(mem_block or ""),
    }


def build_fallback_context_details(
    query: str,
    turns: list[tuple[str, str]] | None = None,
    *,
    conversation_state: dict | None = None,
    pending_action: dict | None = None,
    include_state_context: bool = True,
    include_chat_context: bool = True,
    build_learning_context_details_fn: Callable[..., dict],
    chat_context_turns: int = 6,
) -> dict[str, Any]:
    session_turns = turns if isinstance(turns, list) else []
    learning_details = build_learning_context_details_fn(
        query,
        conversation_state=conversation_state,
        pending_action=pending_action,
    )
    learning_context = str(learning_details.get("context") or "")
    chat_context = (
        render_chat_context(
            session_turns,
            current_text=query,
            chat_context_turns=chat_context_turns,
        )
        if bool(include_chat_context)
        else ""
    )
    state_context = (
        render_session_state_context(
            conversation_state=conversation_state,
            pending_action=pending_action,
        )
        if bool(include_state_context)
        else ""
    )

    context_blocks: list[str] = []
    if chat_context:
        context_blocks.append("CURRENT CHAT CONTEXT (transcript evidence; answer the current user turn):\n" + chat_context)
    if state_context:
        context_blocks.append(state_context)
    if learning_context:
        context_blocks.append(learning_context)

    return {
        "context": "\n\n".join(context_blocks).strip()[:6000],
        "learning_context": learning_context,
        "runtime_context": "",
        "state_context": state_context,
        "chat_context": chat_context,
        "session_fact_sheet": "",
        "memory_used": bool(learning_details.get("memory_used")),
        "identity_used": bool(learning_details.get("identity_used")),
        "operational_identity_used": bool(learning_details.get("operational_identity_used")),
        "knowledge_used": bool(learning_details.get("knowledge_used")),
        "memory_chars": int(learning_details.get("memory_chars") or 0),
        "identity_chars": int(learning_details.get("identity_chars") or 0),
        "operational_identity_chars": int(learning_details.get("operational_identity_chars") or 0),
        "knowledge_chars": int(learning_details.get("knowledge_chars") or 0),
    }
