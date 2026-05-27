from __future__ import annotations

from typing import Callable


COMMON_BEHAVIOR_LINES = (
    "- Read the user's actual goal from the whole turn and recent conversation before answering.",
    "- Answer the final user message. Recent context is transcript evidence, not a draft reply to reuse.",
    "- Do not repeat or paraphrase a previous assistant reply as the answer to a new turn unless the user asks for that exact prior reply.",
    "- If the user challenges or evaluates a prior reply, use transcript evidence and say only what is supported; do not invent motives or hidden causes.",
    "- When the current turn asks about an earlier reply, compare against the transcript and name the observable mismatch or missing evidence instead of resetting the conversation.",
    "- Treat any turn intent/evidence packet as internal context only; it is not a user request, a route command, or proof by itself.",
    "- Use retrieved, live, and session context as the evidence for self-description, continuity, and status.",
    "- When confirmed internal evidence is available for a claim about Nova, do not replace it with model priors.",
    "- When the user's goal is to understand Nova itself, synthesize confirmed identity and operational evidence before generic assistant priors.",
    "- Do not answer from a surfaced status or tool context unless that evidence serves the user's actual goal.",
    "- Do not expose internal context labels, packet field names, or raw evidence packets in the reply; use them only to judge what claims are supported.",
    "- If the user gives context and asks for an answer, use the context and answer instead of asking a meta-clarifying question.",
    "- This model-only chat call itself cannot write memory or run tools. That limit belongs to this fallback call, not to Nova's whole runtime.",
    "- Do not say Nova lacks registered tools or operational systems when tool or operational evidence says otherwise. Do not promise future retention or claim storage; treat user-provided facts as current-session context only.",
    "- Never claim you performed actions on the PC (open, unzip, delete, move, install, browse, click, run commands) unless a tool was actually executed and its real output is available.",
)

CONVERSATION_TURN_BEHAVIOR_LINES = (
    "- Use the current exchange as the active surface.",
    "- Use available session evidence when it belongs to the current exchange.",
    "- Reply with one brief statement.",
)

CASUAL_ONLY_BEHAVIOR_LINES = (
    "- Speak naturally and briefly while grounding self-claims in current evidence.",
    "- Do not provide external links or URLs unless the user asks specifically for a link or sources.",
    "- Never invent links, file paths, filenames, or results. If unsure, say you are unsure.",
    "- Only ask clarifying questions when the missing information blocks the requested action.",
    "- Keep answers concise and verifiable.",
)

ASSIST_ONLY_BEHAVIOR_LINES = (
    "- For task-oriented requests, prioritize clear, actionable steps without fabricating actions or results.",
    "- Do not provide external links unless the user requests sources.",
    "- Keep answers concrete and verifiable.",
)

FINAL_BEHAVIOR_LINES = (
    "- Do not write TOOL citation tags from this model-only reply; those belong only to real tool execution results supplied by the caller.",
)


def _system_prompt(*, casual: bool, reply_form: str = "") -> str:
    lines = ["You are Nova.", "Base behavior:"]
    if str(reply_form or "").strip() == "conversation_turn":
        lines.extend(CONVERSATION_TURN_BEHAVIOR_LINES)
        lines.extend(FINAL_BEHAVIOR_LINES)
        return "\n".join(lines) + "\n"
    if casual:
        lines.extend(CASUAL_ONLY_BEHAVIOR_LINES[:1])
    lines.extend(COMMON_BEHAVIOR_LINES)
    if casual:
        lines.extend(CASUAL_ONLY_BEHAVIOR_LINES[1:])
    else:
        lines.extend(ASSIST_ONLY_BEHAVIOR_LINES)
    lines.extend(FINAL_BEHAVIOR_LINES)
    return "\n".join(lines) + "\n"


def _response_status(exc: Exception) -> int:
    response = getattr(exc, "response", None)
    try:
        return int(getattr(response, "status_code", 0) or 0)
    except (TypeError, ValueError):
        return 0


def _response_text(exc: Exception) -> str:
    response = getattr(exc, "response", None)
    text = str(getattr(response, "text", "") or "")
    if text:
        return text
    try:
        payload = response.json()
    except Exception:
        payload = None
    return str(payload or exc)


def _model_missing_error(exc: Exception, model: str) -> bool:
    text = _response_text(exc).lower()
    return _response_status(exc) == 404 and "model" in text and "not found" in text and str(model or "").lower() in text


def _chat_failure_reply(exc: Exception, model: str) -> str:
    if _model_missing_error(exc, model):
        return f"(error: Ollama chat model missing: {model})"
    status = _response_status(exc)
    if status == 404:
        return "(error: Ollama chat API unavailable: /api/chat returned 404)"
    if status:
        return f"(error: Ollama chat failed: HTTP {status})"
    detail = str(exc or "").strip()
    if detail:
        return f"(error: Ollama chat failed: {detail[:180]})"
    return "(error: Ollama chat failed)"


def ollama_chat(
    text: str,
    retrieved_context: str = "",
    language_mix_spanish_pct: int = 0,
    reply_form: str = "",
    *,
    live_ollama_calls_allowed_fn: Callable[[], bool],
    ensure_ollama_fn: Callable[[], object],
    language_mix_instruction_fn: Callable[[int], str],
    chat_model_fn: Callable[[], str],
    requests_post_fn: Callable[..., object],
    ollama_base: str,
    ollama_req_timeout: float,
    warn_fn: Callable[[str], None],
    kill_ollama_fn: Callable[[], object],
    start_ollama_serve_detached_fn: Callable[[], object],
    sleep_fn: Callable[[float], None],
    env: dict[str, str],
) -> str:
    if not live_ollama_calls_allowed_fn():
        return "(error: LLM service unavailable)"
    del ensure_ollama_fn, kill_ollama_fn, start_ollama_serve_detached_fn, sleep_fn

    reply_form = str(reply_form or "").strip()
    system_msg = _system_prompt(casual=env.get("CASUAL_MODE", "1").lower() in {"1", "true", "yes"}, reply_form=reply_form)

    system_msg = f"{system_msg}\n\n{language_mix_instruction_fn(language_mix_spanish_pct)}"

    messages = [{"role": "system", "content": system_msg}]
    if retrieved_context:
        messages.append(
            {
                "role": "system",
                "content": (
                    "Retrieved context/evidence available to Nova. This is not the user's current message. "
                    "Use it when it is relevant to the user's goal; if uncertain, say uncertain. "
                    "Historical assistant turns inside this context are transcript evidence, not answer drafts. "
                    "Fallback-call limits are not evidence that Nova lacks runtime tools or operational systems.\n"
                    "<<<CONTEXT\n"
                    f"{retrieved_context[:6000]}\n"
                    ">>>"
                ),
            }
        )
    messages.append({"role": "user", "content": text})

    options = {"temperature": 0.2, "top_p": 0.9, "repeat_penalty": 1.1}
    if reply_form == "conversation_turn":
        options["num_predict"] = 32

    payload = {
        "model": chat_model_fn(),
        "stream": False,
        "keep_alive": "10m",
        "options": options,
        "messages": messages,
    }

    try:
        response = requests_post_fn(f"{ollama_base}/api/chat", json=payload, timeout=ollama_req_timeout)
        response.raise_for_status()
        try:
            return response.json()["message"]["content"].strip()
        except Exception:
            return None
    except Exception as exc:
        model = str(payload.get("model") or "")
        reply = _chat_failure_reply(exc, model)
        warn_fn(reply.strip("()"))
        return reply
