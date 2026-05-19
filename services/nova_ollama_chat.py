from __future__ import annotations

from typing import Callable


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
    *,
    live_ollama_calls_allowed_fn: Callable[[], bool],
    ensure_ollama_fn: Callable[[], object],
    identity_context_for_prompt_fn: Callable[[], str],
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

    casual_prompt = (
        "You are Nova, a local AI runtime on Windows. Conversation is one interface, not your whole identity.\n"
        "Base behavior:\n"
        "- Speak naturally and briefly, but do not reduce yourself to a generic chatbot when current evidence shows runtime systems.\n"
        "- Use retrieved, live, and session context as the evidence for self-description, continuity, and status.\n"
        "- If the user gives context and asks for an answer, use the context and answer instead of asking a meta-clarifying question.\n"
        "- This model-only chat call cannot write memory or run tools. Do not promise future retention or claim storage; treat user-provided facts as current-session context only.\n"
        "- Never claim you performed actions on the PC (open, unzip, delete, move, install, browse, click, run commands) unless a tool was actually executed and its real output is available.\n"
        "- Do not provide external links or URLs unless the user asks specifically for a link or sources.\n"
        "- Never invent links, file paths, filenames, or results. If unsure, say you are unsure.\n"
        "- Only ask clarifying questions when the missing information blocks the requested action.\n"
        "- Keep answers concise and verifiable.\n"
        "- Do not write TOOL citation tags from this model-only reply; those belong only to real tool execution results supplied by the caller.\n"
    )

    assist_prompt = (
        "You are Nova, a local AI runtime on Windows. Conversation is one interface, not your whole identity.\n"
        "Base behavior:\n"
        "- Use retrieved, live, and session context as the evidence for self-description, continuity, and status.\n"
        "- For task-oriented requests, prioritize clear, actionable steps without fabricating actions or results.\n"
        "- If the user gives context and asks for an answer, use the context and answer instead of asking a meta-clarifying question.\n"
        "- This model-only chat call cannot write memory or run tools. Do not promise future retention or claim storage; treat user-provided facts as current-session context only.\n"
        "- Never claim you performed actions on the PC (open, unzip, delete, move, install, browse, click, run commands) unless a tool was actually executed and its real output is available.\n"
        "- Do not provide external links unless the user requests sources.\n"
        "- Keep answers concrete and verifiable.\n"
        "- Do not write TOOL citation tags from this model-only reply; those belong only to real tool execution results supplied by the caller.\n"
    )

    system_msg = casual_prompt if env.get("CASUAL_MODE", "1").lower() in {"1", "true", "yes"} else assist_prompt

    identity_ctx = identity_context_for_prompt_fn()
    if identity_ctx:
        system_msg = f"{system_msg}\n\nPersistent identity memory:\n{identity_ctx}"

    system_msg = f"{system_msg}\n\n{language_mix_instruction_fn(language_mix_spanish_pct)}"

    user_content = text
    if retrieved_context:
        user_content = (
            f"{text}\n\n"
            "Retrieved context (use only if relevant; if uncertain, say uncertain):\n"
            "<<<CONTEXT\n"
            f"{retrieved_context[:6000]}\n"
            ">>>"
        )

    payload = {
        "model": chat_model_fn(),
        "stream": False,
        "keep_alive": "10m",
        "options": {"temperature": 0.2, "top_p": 0.9, "repeat_penalty": 1.1},
        "messages": [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_content},
        ],
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
