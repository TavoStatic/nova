from __future__ import annotations

import time
from typing import Callable


def maybe_handle_deterministic_sequence(
    *,
    text: str,
    turns: list[tuple[str, str]],
    low: str,
    trace: Callable[..., None],
    normalize_reply: Callable[[str], str],
    is_session_recap_request: Callable[[str], bool],
    session_recap_reply: Callable[[list[tuple[str, str]], str], str],
    is_assistant_name_query: Callable[[str], bool],
    assistant_name_reply: Callable[[str], str],
    is_developer_full_name_query: Callable[[str], bool],
    developer_full_name_reply: Callable[[], str],
    is_name_origin_question: Callable[[str], bool],
    is_student_data_attendance_rules_query: Callable[[str], bool],
    student_data_attendance_rules_reply: Callable[[], str],
    is_developer_profile_request: Callable[[str], bool],
    developer_profile_reply: Callable[[list[tuple[str, str]], str], str],
    is_conversational_clarification: Callable[[str], bool],
    clarification_reply: Callable[[list[tuple[str, str]]], str],
    is_location_request: Callable[[str], bool],
    location_reply: Callable[[], str],
    is_deep_search_followup_request: Callable[[str], bool],
    infer_research_query_from_turns: Callable[[list[tuple[str, str]]], str],
    build_grounded_answer: Callable[[str], str],
    build_local_topic_digest_answer: Callable[[str], str],
    is_groundable_factual_query: Callable[[str], bool],
    developer_color_reply: Callable[[list[tuple[str, str]]], str],
    developer_bilingual_reply: Callable[[list[tuple[str, str]]], str],
    color_reply: Callable[[list[tuple[str, str]]], str],
    animal_reply: Callable[[list[tuple[str, str]]], str],
    core,
) -> tuple[str, dict, str, int] | None:
    if is_session_recap_request(text):
        trace("deterministic_reply", "matched", detail="session_recap")
        reply = session_recap_reply(turns, text)
        return normalize_reply(reply), {
            "planner_decision": "deterministic",
            "tool": "session_recap",
            "tool_args": {"query": text},
            "tool_result": reply,
            "grounded": True,
        }, "timed", 0
    if is_assistant_name_query(text):
        trace("deterministic_reply", "matched", detail="assistant_name")
        reply = assistant_name_reply(text)
        return normalize_reply(reply), {
            "planner_decision": "deterministic",
            "tool": "assistant_name",
            "tool_args": {"query": text},
            "tool_result": reply,
            "grounded": True,
        }, "timed", 0
    if is_developer_full_name_query(text):
        trace("deterministic_reply", "matched", detail="developer_full_name")
        reply = developer_full_name_reply()
        return normalize_reply(reply), {
            "planner_decision": "deterministic",
            "tool": "developer_identity",
            "tool_args": {"query": text},
            "tool_result": reply,
            "grounded": True,
        }, "timed", 0
    if "do you remember our last chat session" in low or "remember our last chat" in low:
        trace("deterministic_reply", "matched", detail="memory_policy_explanation")
        reply = "I remember parts of prior chats only if they were saved to memory; I remember this live session context directly."
        return normalize_reply(reply), {
            "planner_decision": "deterministic",
            "tool": "memory_policy",
            "tool_args": {"query": text},
            "tool_result": reply,
            "grounded": True,
        }, "timed", 0
    if is_name_origin_question(text):
        trace("deterministic_reply", "matched", detail="name_origin_query")
        story = core.get_name_origin_story().strip()
        if story:
            reply = f"Yes. {story}"
        else:
            reply = "I do not have a saved name-origin story yet. You can tell me with: remember this Nova ..."
        return normalize_reply(reply), {
            "planner_decision": "deterministic",
            "tool": "name_origin",
            "tool_args": {"query": text},
            "tool_result": reply,
            "grounded": bool(story),
        }, "timed", 0
    if is_student_data_attendance_rules_query(text):
        trace("grounded_lookup", "matched", tool="student_data_attendance")
        reply = student_data_attendance_rules_reply()
        return normalize_reply(reply), {
            "planner_decision": "grounded_lookup",
            "tool": "student_data_attendance",
            "tool_args": {"query": text},
            "tool_result": reply,
            "grounded": "[source:" in reply.lower(),
        }, "timed", 0
    if is_developer_profile_request(text):
        trace("deterministic_reply", "matched", detail="developer_profile")
        reply = developer_profile_reply(turns, text)
        return normalize_reply(reply), {
            "planner_decision": "deterministic",
            "tool": "developer_profile",
            "tool_args": {"query": text},
            "tool_result": reply,
            "grounded": True,
        }, "logged", 0
    if is_conversational_clarification(text):
        trace("deterministic_reply", "matched", detail="clarification_reply")
        reply = clarification_reply(turns)
        return normalize_reply(reply), {
            "planner_decision": "deterministic",
            "tool": "clarification_reply",
            "tool_args": {"query": text},
            "tool_result": reply,
            "grounded": True,
        }, "logged", 0
    if is_location_request(text):
        trace("deterministic_reply", "matched", detail="location_reply")
        reply = location_reply()
        return normalize_reply(reply), {
            "planner_decision": "deterministic",
            "tool": "location",
            "tool_args": {"query": text},
            "tool_result": reply,
            "grounded": True,
        }, "logged", 0
    if is_deep_search_followup_request(text):
        inferred = infer_research_query_from_turns(turns)
        query = inferred or text
        tool_started = time.perf_counter()
        grounded = build_grounded_answer(query, max_sources=2)
        tool_time_ms = int((time.perf_counter() - tool_started) * 1000)
        trace("timing", "completed", "tool_response", duration_ms=tool_time_ms, tool="web_research")
        trace("timing", "completed", "web_search", duration_ms=tool_time_ms, tool="web_research")
        if grounded:
            trace("grounded_lookup", "matched", tool="web_research")
            reply = grounded
            return normalize_reply(reply), {
                "planner_decision": "grounded_lookup",
                "tool": "web_research",
                "tool_args": {"query": query},
                "tool_result": reply,
                "grounded": True,
            }, "timed", tool_time_ms
        local_started = time.perf_counter()
        local_grounded = build_local_topic_digest_answer(query)
        tool_time_ms += int((time.perf_counter() - local_started) * 1000)
        trace("timing", "completed", "tool_response", duration_ms=tool_time_ms, tool="local_knowledge")
        if local_grounded:
            trace("grounded_lookup", "matched", tool="local_knowledge")
            reply = local_grounded
            return normalize_reply(reply), {
                "planner_decision": "grounded_lookup",
                "tool": "local_knowledge",
                "tool_args": {"query": query},
                "tool_result": reply,
                "grounded": True,
            }, "timed", tool_time_ms
        trace("grounded_lookup", "missed", tool="web_research")
        reply = "I could not find additional grounded sources right now. Please try: web research <topic>"
        return normalize_reply(reply), {
            "planner_decision": "grounded_lookup",
            "tool": "web_research",
            "tool_args": {"query": query},
            "tool_result": reply,
            "grounded": False,
        }, "timed", tool_time_ms
    if is_groundable_factual_query(text):
        tool_started = time.perf_counter()
        grounded = build_grounded_answer(text, max_sources=2)
        tool_time_ms = int((time.perf_counter() - tool_started) * 1000)
        trace("timing", "completed", "tool_response", duration_ms=tool_time_ms, tool="web_research")
        trace("timing", "completed", "web_search", duration_ms=tool_time_ms, tool="web_research")
        if grounded:
            trace("grounded_lookup", "matched", tool="web_research")
            reply = grounded
            return normalize_reply(reply), {
                "planner_decision": "grounded_lookup",
                "tool": "web_research",
                "tool_args": {"query": text},
                "tool_result": reply,
                "grounded": True,
            }, "logged", tool_time_ms
        local_started = time.perf_counter()
        local_grounded = build_local_topic_digest_answer(text)
        tool_time_ms += int((time.perf_counter() - local_started) * 1000)
        trace("timing", "completed", "tool_response", duration_ms=tool_time_ms, tool="local_knowledge")
        if local_grounded:
            trace("grounded_lookup", "matched", tool="local_knowledge")
            reply = local_grounded
            return normalize_reply(reply), {
                "planner_decision": "grounded_lookup",
                "tool": "local_knowledge",
                "tool_args": {"query": text},
                "tool_result": reply,
                "grounded": True,
            }, "logged", tool_time_ms
        trace("grounded_lookup", "missed", tool="web_research")
        reply = "I couldn't find grounded sources for that yet. Please try: web research <your question>"
        return normalize_reply(reply), {
            "planner_decision": "grounded_lookup",
            "tool": "web_research",
            "tool_args": {"query": text},
            "tool_result": reply,
            "grounded": False,
        }, "timed", tool_time_ms
    if core._is_developer_color_lookup_request(text):
        trace("deterministic_reply", "matched", detail="developer_color_reply")
        reply = developer_color_reply(turns)
        return normalize_reply(reply), {
            "planner_decision": "deterministic",
            "tool": "developer_color_reply",
            "tool_args": {"query": text},
            "tool_result": reply,
            "grounded": True,
        }, "logged", 0
    if core._is_developer_bilingual_request(text):
        trace("deterministic_reply", "matched", detail="developer_bilingual_reply")
        reply = developer_bilingual_reply(turns)
        return normalize_reply(reply), {
            "planner_decision": "deterministic",
            "tool": "developer_bilingual_reply",
            "tool_args": {"query": text},
            "tool_result": reply,
            "grounded": True,
        }, "logged", 0
    if core._is_color_lookup_request(text):
        trace("deterministic_reply", "matched", detail="color_reply")
        reply = color_reply(turns)
        return normalize_reply(reply), {
            "planner_decision": "deterministic",
            "tool": "color_reply",
            "tool_args": {"query": text},
            "tool_result": reply,
            "grounded": True,
        }, "logged", 0
    if "what animals do i like" in low or "which animals do i like" in low:
        trace("deterministic_reply", "matched", detail="animal_reply")
        reply = animal_reply(turns)
        return normalize_reply(reply), {
            "planner_decision": "deterministic",
            "tool": "animal_reply",
            "tool_args": {"query": text},
            "tool_result": reply,
            "grounded": True,
        }, "logged", 0
    return None
