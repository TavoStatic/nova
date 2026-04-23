from __future__ import annotations

from typing import Callable, Optional


def execute_retrieval_followup_outcome(
    state: dict,
    text: str,
    *,
    extract_retrieval_result_index_fn: Callable[[str], Optional[int]],
    is_retrieval_meta_question_fn: Callable[[str], bool],
    retrieval_meta_reply_fn: Callable[[dict], str],
    tool_web_gather_fn: Callable[[str], str],
    make_retrieval_conversation_state_fn: Callable[[str, str, str], Optional[dict]],
    looks_like_retrieval_followup_fn: Callable[[str], bool],
    tool_web_research_continue_fn: Callable[[], str],
    web_research_query_fn: Callable[[], str],
    web_research_result_count_fn: Callable[[], int],
    web_research_has_results_fn: Callable[[], bool],
    render_reply_fn: Callable[[Optional[dict]], str],
) -> tuple[str, Optional[dict], dict[str, object]]:
    current_state = state if isinstance(state, dict) else {}
    urls = current_state.get("urls") if isinstance(current_state.get("urls"), list) else []
    query = str(current_state.get("query") or "").strip()
    source = str(current_state.get("subject") or "retrieval").strip().lower()
    result_count = max(0, int(current_state.get("result_count", 0) or 0))
    index = extract_retrieval_result_index_fn(text)

    if is_retrieval_meta_question_fn(text):
        reply_text = retrieval_meta_reply_fn(current_state)
        outcome = {
            "intent": "retrieval_followup",
            "kind": "meta_summary",
            "reply_contract": "retrieval_followup.meta_summary",
            "reply_text": reply_text,
            "query": query,
            "result_count": result_count,
            "selected_index": None,
            "state_delta": current_state,
        }
        return render_reply_fn(outcome), current_state, outcome

    if index is not None and 1 <= index <= len(urls):
        selected_url = str(urls[index - 1])
        result = tool_web_gather_fn(selected_url)
        next_state = make_retrieval_conversation_state_fn("web_gather", selected_url, result) or current_state
        outcome = {
            "intent": "retrieval_followup",
            "kind": "selected_result",
            "reply_contract": "retrieval_followup.selected_result",
            "reply_text": str(result or ""),
            "query": query,
            "result_count": result_count,
            "selected_index": index,
            "selected_url": selected_url,
            "state_delta": next_state,
        }
        return render_reply_fn(outcome), next_state, outcome

    if source == "web_research" and looks_like_retrieval_followup_fn(text):
        result = tool_web_research_continue_fn()
        if result and not result.lower().startswith("no active web research session"):
            continued_query = str(web_research_query_fn() or query).strip()
            next_state = make_retrieval_conversation_state_fn("web_research", continued_query, result) or current_state
            outcome = {
                "intent": "retrieval_followup",
                "kind": "continued_results",
                "reply_contract": "retrieval_followup.continued_results",
                "reply_text": str(result or ""),
                "query": continued_query,
                "result_count": web_research_result_count_fn() if web_research_has_results_fn() else result_count,
                "selected_index": None,
                "state_delta": next_state,
            }
            return render_reply_fn(outcome), next_state, outcome

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
    reply_text = " ".join(parts)
    outcome = {
        "intent": "retrieval_followup",
        "kind": "guidance",
        "reply_contract": "retrieval_followup.guidance",
        "reply_text": reply_text,
        "query": query,
        "result_count": result_count,
        "selected_index": index,
        "state_delta": current_state,
    }
    return render_reply_fn(outcome), current_state, outcome