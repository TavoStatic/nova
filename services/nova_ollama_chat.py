from __future__ import annotations

from typing import Callable


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

    try:
        ensure_ollama_fn()
    except Exception:
        pass

    casual_prompt = (
        "You are Nova, a friendly conversational assistant running locally on Windows.\n"
        "Tone and behavior rules:\n"
        "- Speak naturally and briefly like a person in the room; prefer short acknowledgements for casual statements.\n"
        "- Do NOT repeatedly offer assistance or suggest actions unless the user explicitly asks for help. Avoid endings like 'Would you like me to...' in casual chat.\n"
        "- Avoid formal task-oriented phrasing for ordinary conversation; use gentle acknowledgements (e.g., 'Got it.', 'She sounds tired.', 'Nice.').\n"
        "- Never claim you performed actions on the PC (open, unzip, delete, move, install, browse, click, run commands) unless a tool was actually executed and its real output is available.\n"
        "- Do NOT provide external links or URLs unless the user asks specifically for a link or sources. If asked for a source, provide one and include a TOOL citation only when the output is grounded.\n"
        "- Never invent links, file paths, filenames, or results. If unsure, say you are unsure.\n"
        "- Only ask clarifying questions sparingly and only when necessary to complete a requested task; do not ask follow-ups for simple observational statements.\n"
        "- Keep answers concise and verifiable.\n"
        "- IMPORTANT: If you reference results produced by tools (files saved, snapshots, patches, downloads, paths, etc.), include an exact citation line in this format: '[TOOL:<tool_name>] <short description or path>'.\n"
        "  Example citations:\n"
        "    [TOOL:web_fetch] runtime/web/20260101_example.html\n"
        "    [TOOL:patch_apply] Patch applied: 3 files\n"
        "- Do NOT fabricate any such citation — if you do not have a real tool output, say you don't have the output and provide the command the user should run to get it.\n"
    )

    assist_prompt = (
        "You are Nova, a helpful assistant running locally on Windows.\n"
        "Tone and behavior rules:\n"
        "- Be helpful and offer assistance when helpful, but avoid fabricating actions or results.\n"
        "- If the user is vague and a follow-up is needed to complete a requested task, ask one concise clarifying question.\n"
        "- For task-oriented requests, prioritize clear, actionable steps.\n"
        "- Never claim you performed actions on the PC (open, unzip, delete, move, install, browse, click, run commands) unless a tool was actually executed and its real output is available.\n"
        "- Do NOT provide external links unless the user requests sources; when providing tool outputs include TOOL citations.\n"
        "- Keep answers concrete and verifiable.\n"
        "- IMPORTANT: If you reference results produced by tools (files saved, snapshots, patches, downloads, paths, etc.), include an exact citation line in this format: '[TOOL:<tool_name>] <short description or path>'.\n"
        "  Example citations:\n"
        "    [TOOL:web_fetch] runtime/web/20260101_example.html\n"
        "    [TOOL:patch_apply] Patch applied: 3 files\n"
        "- Do NOT fabricate any such citation — if you do not have a real tool output, say you don't have the output and provide the command the user should run to get it.\n"
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
    except Exception:
        warn_fn("Ollama chat failed; attempting one restart and retry.")
        try:
            kill_ollama_fn()
            sleep_fn(1.2)
            start_ollama_serve_detached_fn()
            sleep_fn(1.2)
            response = requests_post_fn(f"{ollama_base}/api/chat", json=payload, timeout=ollama_req_timeout)
            response.raise_for_status()
            try:
                return response.json()["message"]["content"].strip()
            except Exception:
                return None
        except Exception as exc:
            warn_fn(f"Ollama chat final attempt failed: {exc}")
            return "(error: LLM service unavailable)"