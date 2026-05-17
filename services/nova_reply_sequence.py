from __future__ import annotations

import json
import time
from types import SimpleNamespace
from typing import Callable

from services import nova_planner_contract
from services.nova_fallback_flow import finalize_llm_fallback_reply, prepare_fallback_flow
from services.nova_reply_deterministic import (
    _is_queue_pressure_justify_followup,
    _is_queue_pressure_triage_query,
    maybe_handle_deterministic_sequence,
)


def _runtime_fn(runtime_scope: dict[str, object], name: str):
    return runtime_scope[name]


def execute_reply_sequence_from_runtime(
    *,
    turns: list[tuple[str, str]],
    text: str,
    pending_action: dict | None,
    prefer_web_for_data_queries: bool,
    language_mix_spanish_pct: int,
    session,
    trace: Callable[..., None],
    normalize_reply: Callable[[str], str],
    ensure_reply: Callable[[str], str],
    core,
    runtime_scope: dict[str, object],
    pre_planner_branch_group: str = "all",
    post_planner_branch_group: str | None = None,
    planner_before_deterministic_content: bool = False,
    stop_before_llm_fallback: bool = False,
    ensure_active_work_tree_fn: Callable[[str], str] | None = None,
    work_tree_seed_source: str = "",
    work_tree_seed_mode: str = "",
) -> tuple[str, dict]:
    content_enabled = pre_planner_branch_group in {"all", "general"} or post_planner_branch_group in {"all", "general"}
    false_text = lambda _text: False
    empty_reply = lambda *args, **kwargs: ""
    empty_from_turns = lambda _turns, *_args, **_kwargs: ""

    return execute_reply_sequence(
        turns=turns,
        text=text,
        pending_action=pending_action,
        prefer_web_for_data_queries=prefer_web_for_data_queries,
        language_mix_spanish_pct=language_mix_spanish_pct,
        session=session,
        trace=trace,
        normalize_reply=normalize_reply,
        ensure_reply=ensure_reply,
        core=core,
        is_developer_profile_request=_runtime_fn(runtime_scope, "_is_developer_profile_request") if content_enabled else false_text,
        developer_profile_reply=_runtime_fn(runtime_scope, "_developer_profile_reply") if content_enabled else empty_from_turns,
        is_location_request=_runtime_fn(runtime_scope, "_is_location_request") if content_enabled else false_text,
        location_reply=_runtime_fn(runtime_scope, "_location_reply") if content_enabled else empty_reply,
        is_web_preferred_data_query=_runtime_fn(runtime_scope, "nova_query_classifiers").is_web_preferred_data_query,
        is_session_recap_request=_runtime_fn(runtime_scope, "_is_session_recap_request") if content_enabled else false_text,
        session_recap_reply=_runtime_fn(runtime_scope, "_session_recap_reply") if content_enabled else empty_from_turns,
        is_assistant_name_query=_runtime_fn(runtime_scope, "_is_assistant_name_query") if content_enabled else false_text,
        assistant_name_reply=_runtime_fn(runtime_scope, "_assistant_name_reply") if content_enabled else empty_reply,
        is_developer_full_name_query=_runtime_fn(runtime_scope, "_is_developer_full_name_query") if content_enabled else false_text,
        developer_full_name_reply=_runtime_fn(runtime_scope, "_developer_full_name_reply") if content_enabled else empty_reply,
        is_name_origin_question=_runtime_fn(runtime_scope, "_is_name_origin_question") if content_enabled else false_text,
        is_student_data_attendance_rules_query=(
            _runtime_fn(runtime_scope, "nova_query_classifiers").is_student_data_attendance_rules_query
            if content_enabled
            else false_text
        ),
        student_data_attendance_rules_reply=_runtime_fn(runtime_scope, "_peims_attendance_rules_reply") if content_enabled else empty_reply,
        is_conversational_clarification=(
            _runtime_fn(runtime_scope, "nova_query_classifiers").is_conversational_clarification
            if content_enabled
            else false_text
        ),
        clarification_reply=(lambda turns: core._open_probe_reply("what are you talking about ?", turns=turns)[0]) if content_enabled else empty_from_turns,
        is_deep_search_followup_request=_runtime_fn(runtime_scope, "_is_deep_search_followup_request") if content_enabled else false_text,
        infer_research_query_from_turns=_runtime_fn(runtime_scope, "_infer_research_query_from_turns") if content_enabled else empty_from_turns,
        build_grounded_answer=_runtime_fn(runtime_scope, "_build_grounded_answer") if content_enabled else (lambda _query, max_sources=2: ""),
        build_local_topic_digest_answer=_runtime_fn(runtime_scope, "_build_local_topic_digest_answer") if content_enabled else (lambda _query: ""),
        is_groundable_factual_query=lambda _text: False,
        developer_color_reply=_runtime_fn(runtime_scope, "_developer_color_reply") if content_enabled else empty_from_turns,
        developer_bilingual_reply=_runtime_fn(runtime_scope, "_developer_bilingual_reply") if content_enabled else empty_from_turns,
        color_reply=_runtime_fn(runtime_scope, "_color_reply") if content_enabled else empty_from_turns,
        animal_reply=_runtime_fn(runtime_scope, "_animal_reply") if content_enabled else empty_from_turns,
        ensure_active_work_tree_fn=ensure_active_work_tree_fn,
        work_tree_seed_source=work_tree_seed_source,
        work_tree_seed_mode=work_tree_seed_mode,
        pre_planner_branch_group=pre_planner_branch_group,
        post_planner_branch_group=post_planner_branch_group,
        planner_before_deterministic_content=planner_before_deterministic_content,
        stop_before_llm_fallback=stop_before_llm_fallback,
    )


def execute_http_reply_sequence_from_runtime(
    *,
    turns: list[tuple[str, str]],
    text: str,
    ledger_record: dict | None,
    pending_action: dict | None,
    prefer_web_for_data_queries: bool,
    language_mix_spanish_pct: int,
    session,
    ensure_reply: Callable[[str], str],
    core,
    runtime_scope: dict[str, object],
    pre_planner_branch_group: str = "all",
    post_planner_branch_group: str | None = None,
    ensure_active_work_tree_fn: Callable[[str], str] | None = None,
) -> tuple[str, dict]:
    def _trace(stage: str, outcome: str, detail: str = "", **data) -> None:
        core.action_ledger_add_step(ledger_record, stage, outcome, detail, **data)

    def _normalize_reply(reply_text: str) -> str:
        reply_local = _runtime_fn(runtime_scope, "_strip_ui_tip_leak")(reply_text)
        return ensure_reply(reply_local)

    return execute_reply_sequence_from_runtime(
        turns=turns,
        text=text,
        pending_action=pending_action,
        prefer_web_for_data_queries=prefer_web_for_data_queries,
        language_mix_spanish_pct=language_mix_spanish_pct,
        session=session,
        trace=_trace,
        normalize_reply=_normalize_reply,
        ensure_reply=ensure_reply,
        core=core,
        runtime_scope=runtime_scope,
        ensure_active_work_tree_fn=ensure_active_work_tree_fn,
        work_tree_seed_source="http",
        pre_planner_branch_group=pre_planner_branch_group,
        post_planner_branch_group=post_planner_branch_group,
    )


def execute_reply_sequence(
    *,
    turns: list[tuple[str, str]],
    text: str,
    pending_action: dict | None,
    prefer_web_for_data_queries: bool,
    language_mix_spanish_pct: int,
    session,
    trace: Callable[..., None],
    normalize_reply: Callable[[str], str],
    ensure_reply: Callable[[str], str],
    core,
    is_developer_profile_request: Callable[[str], bool],
    developer_profile_reply: Callable[[list[tuple[str, str]], str], str],
    is_location_request: Callable[[str], bool],
    location_reply: Callable[[], str],
    is_web_preferred_data_query: Callable[[str], bool],
    is_session_recap_request: Callable[[str], bool],
    session_recap_reply: Callable[[list[tuple[str, str]], str], str],
    is_assistant_name_query: Callable[[str], bool],
    assistant_name_reply: Callable[[str], str],
    is_developer_full_name_query: Callable[[str], bool],
    developer_full_name_reply: Callable[[], str],
    is_name_origin_question: Callable[[str], bool],
    is_student_data_attendance_rules_query: Callable[[str], bool],
    student_data_attendance_rules_reply: Callable[[], str],
    is_conversational_clarification: Callable[[str], bool],
    clarification_reply: Callable[[list[tuple[str, str]]], str],
    is_deep_search_followup_request: Callable[[str], bool],
    infer_research_query_from_turns: Callable[[list[tuple[str, str]]], str],
    build_grounded_answer: Callable[[str], str],
    build_local_topic_digest_answer: Callable[[str], str],
    is_groundable_factual_query: Callable[[str], bool],
    developer_color_reply: Callable[[list[tuple[str, str]]], str],
    developer_bilingual_reply: Callable[[list[tuple[str, str]]], str],
    color_reply: Callable[[list[tuple[str, str]]], str],
    animal_reply: Callable[[list[tuple[str, str]]], str],
    ensure_active_work_tree_fn: Callable[[str], str] | None = None,
    work_tree_seed_source: str = "",
    work_tree_seed_mode: str = "",
    pre_planner_branch_group: str = "all",
    post_planner_branch_group: str | None = None,
    planner_before_deterministic_content: bool = False,
    stop_before_llm_fallback: bool = False,
) -> tuple[str, dict]:
    sequence_started = time.perf_counter()
    timing_profile = {
        "planner_time": 0,
        "tool_selection_time": 0,
        "tool_time": 0,
        "llm_time": 0,
        "post_time": 0,
    }
    planner_already_attempted = False

    def _merge_timing(meta: dict | None) -> dict:
        payload = dict(meta or {})
        raw_timing = payload.get("timing") if isinstance(payload.get("timing"), dict) else {}
        timing_profile["planner_time"] = int(raw_timing.get("planner_time") or timing_profile["planner_time"] or 0)
        timing_profile["tool_selection_time"] = int(raw_timing.get("tool_selection_time") or timing_profile["tool_selection_time"] or 0)
        timing_profile["tool_time"] = int(raw_timing.get("tool_time") or timing_profile["tool_time"] or 0)
        return payload

    def _complete_return(reply: str, meta: dict, *, record_high_latency: bool) -> tuple[str, dict]:
        payload = _merge_timing(meta)
        duration_ms = int((time.perf_counter() - sequence_started) * 1000)
        execution_profile = {
            "total_time": duration_ms,
            "planner_time": int(timing_profile["planner_time"] or 0),
            "llm_time": int(timing_profile["llm_time"] or 0),
            "tool_time": int(timing_profile["tool_time"] or 0),
            "post_time": int(timing_profile["post_time"] or 0),
            "tool_selection_time": int(timing_profile["tool_selection_time"] or 0),
        }
        reply_outcome = dict(payload.get("reply_outcome") or {})
        reply_outcome["execution_profile"] = execution_profile
        payload["reply_outcome"] = reply_outcome
        trace("timing", "completed", "execute_reply_sequence", duration_ms=duration_ms)
        trace("timing_breakdown", "completed", "execute_reply_sequence", **execution_profile)
        if record_high_latency and duration_ms > 10000:
            core.behavior_set_flag("high_latency", layer="execute_reply_sequence", duration_ms=duration_ms)
        return reply, payload

    def _timed_return(reply: str, meta: dict) -> tuple[str, dict]:
        return _complete_return(reply, meta, record_high_latency=True)

    def _logged_return(reply: str, meta: dict) -> tuple[str, dict]:
        return _complete_return(reply, meta, record_high_latency=False)

    def _break_fallback_loop(reply_text: str, meta: dict) -> tuple[str, dict]:
        normalized_reply = normalize_reply(reply_text)
        last_reply = str(getattr(session, "last_fallback_reply", "") or "").strip()
        current_reply = str(normalized_reply or "").strip()
        planner_decision = str((meta or {}).get("planner_decision") or "").strip().lower()
        degraded = planner_decision in {"llm_fallback", "fulfillment_choice", "respond", "ask_clarify", "blocked_low_confidence"}
        if degraded and current_reply and current_reply == last_reply:
            core.behavior_set_flag("fallback_loop_detected", detail=planner_decision)
            trace("fallback_loop", "detected", planner_decision)
            loop_reply = normalize_reply("I am hitting the same degraded path twice. Stopping the loop. Please restate the next concrete step.")
            if hasattr(session, "last_fallback_reply"):
                session.last_fallback_reply = loop_reply
            meta = dict(meta or {})
            meta["planner_decision"] = "degraded_fallback_break"
            meta["tool_result"] = str(meta.get("tool_result") or "")
            meta["grounded"] = False
            meta["degraded_failure"] = True
            return loop_reply, meta
        if hasattr(session, "last_fallback_reply"):
            session.last_fallback_reply = current_reply if degraded else ""
        return normalized_reply, meta

    def _build_fallback_context_details(user_text: str, session_turns: list[tuple[str, str]]):
        build_fn = core.build_fallback_context_details
        try:
            return build_fn(
                user_text,
                session_turns,
                conversation_state=getattr(session, "conversation_state", None),
                pending_action=pending_action,
            )
        except TypeError:
            return build_fn(user_text, session_turns)

    low = text.lower()
    allow_general_content = pre_planner_branch_group in {"all", "general"}

    if allow_general_content and is_developer_profile_request(text):
        trace("developer_profile", "matched")
        reply = developer_profile_reply(turns, text)
        return _timed_return(normalize_reply(reply), {
            "planner_decision": "deterministic",
            "tool": "developer_profile",
            "tool_args": {"query": text},
            "tool_result": reply,
            "grounded": True,
        })

    if allow_general_content:
        handled_truth, truth_reply, truth_source, truth_grounded = core.truth_hierarchy_answer(text)
        if handled_truth:
            trace("truth_hierarchy", "matched", tool=str(truth_source or ""), grounded=bool(truth_grounded))
            reply = truth_reply
            used_hard_answer = False
            if is_developer_profile_request(text):
                hard = core.hard_answer(text)
                if hard:
                    reply = hard
                    used_hard_answer = True
                elif reply.lower().startswith("uncertain. no structured identity fact"):
                    reply = developer_profile_reply(turns, text)
            elif reply.lower().startswith("uncertain. no structured identity fact"):
                if is_location_request(text):
                    reply = location_reply()
                else:
                    hard = core.hard_answer(text)
                    if hard:
                        reply = hard
                        used_hard_answer = True
            final_reply = ensure_reply(reply) if used_hard_answer else normalize_reply(reply)
            return _timed_return(final_reply, {
                "planner_decision": "truth_hierarchy",
                "tool": str(truth_source or ""),
                "tool_args": {"query": text},
                "tool_result": str(reply or ""),
                "grounded": bool(truth_grounded),
            })
        trace("truth_hierarchy", "not_matched")
    else:
        trace("truth_hierarchy", "skipped", detail="content_owned_chat_disabled")

    if allow_general_content:
        hard = core.hard_answer(text)
        if hard:
            trace("hard_answer", "matched", grounded=True)
            reply = ensure_reply(hard)
            return _timed_return(reply, {
                "planner_decision": "deterministic",
                "tool": "hard_answer",
                "tool_args": {"query": text},
                "tool_result": reply,
                "grounded": True,
            })
        trace("hard_answer", "not_matched")
    else:
        trace("hard_answer", "skipped", detail="content_owned_chat_disabled")

    force_pre_planner_deterministic = _is_queue_pressure_triage_query(text) or _is_queue_pressure_justify_followup(text)

    if planner_before_deterministic_content and not force_pre_planner_deterministic:
        planner_already_attempted = True
        planner_call_started = time.perf_counter()
        planner_outcome = nova_planner_contract.maybe_handle_planner_sequence(
            text=text,
            turns=turns,
            pending_action=pending_action,
            prefer_web_for_data_queries=prefer_web_for_data_queries,
            session=session,
            core=core,
            trace=trace,
            normalize_reply=normalize_reply,
            is_web_preferred_data_query=is_web_preferred_data_query,
            ensure_active_work_tree_fn=ensure_active_work_tree_fn,
            work_tree_seed_source=work_tree_seed_source,
            work_tree_seed_mode=work_tree_seed_mode,
        )
        timing_profile["planner_time"] = int((time.perf_counter() - planner_call_started) * 1000)
        trace("timing", "completed", "planner_call", duration_ms=timing_profile["planner_time"])
        if planner_outcome is not None:
            return _timed_return(*_break_fallback_loop(planner_outcome[0], planner_outcome[1]))

    deterministic_outcome = maybe_handle_deterministic_sequence(
        text=text,
        turns=turns,
        low=low,
        trace=trace,
        normalize_reply=normalize_reply,
        is_session_recap_request=is_session_recap_request,
        session_recap_reply=session_recap_reply,
        is_assistant_name_query=is_assistant_name_query,
        assistant_name_reply=assistant_name_reply,
        is_developer_full_name_query=is_developer_full_name_query,
        developer_full_name_reply=developer_full_name_reply,
        is_name_origin_question=is_name_origin_question,
        is_student_data_attendance_rules_query=is_student_data_attendance_rules_query,
        student_data_attendance_rules_reply=student_data_attendance_rules_reply,
        is_developer_profile_request=is_developer_profile_request,
        developer_profile_reply=developer_profile_reply,
        is_conversational_clarification=is_conversational_clarification,
        clarification_reply=clarification_reply,
        is_location_request=is_location_request,
        location_reply=location_reply,
        is_deep_search_followup_request=is_deep_search_followup_request,
        infer_research_query_from_turns=infer_research_query_from_turns,
        build_grounded_answer=build_grounded_answer,
        build_local_topic_digest_answer=build_local_topic_digest_answer,
        is_groundable_factual_query=is_groundable_factual_query,
        developer_color_reply=developer_color_reply,
        developer_bilingual_reply=developer_bilingual_reply,
        color_reply=color_reply,
        animal_reply=animal_reply,
        core=core,
        branch_group=pre_planner_branch_group,
    )
    if deterministic_outcome is not None:
        reply, meta, return_mode, tool_time_ms = deterministic_outcome
        timing_profile["tool_time"] = int(tool_time_ms or timing_profile["tool_time"] or 0)
        if return_mode == "logged":
            return _logged_return(reply, meta)
        return _timed_return(reply, meta)

    if not planner_already_attempted:
        planner_call_started = time.perf_counter()
        planner_outcome = nova_planner_contract.maybe_handle_planner_sequence(
            text=text,
            turns=turns,
            pending_action=pending_action,
            prefer_web_for_data_queries=prefer_web_for_data_queries,
            session=session,
            core=core,
            trace=trace,
            normalize_reply=normalize_reply,
            is_web_preferred_data_query=is_web_preferred_data_query,
            ensure_active_work_tree_fn=ensure_active_work_tree_fn,
            work_tree_seed_source=work_tree_seed_source,
            work_tree_seed_mode=work_tree_seed_mode,
        )
        timing_profile["planner_time"] = int((time.perf_counter() - planner_call_started) * 1000)
        trace("timing", "completed", "planner_call", duration_ms=timing_profile["planner_time"])
        if planner_outcome is not None:
            return _timed_return(*_break_fallback_loop(planner_outcome[0], planner_outcome[1]))

    if post_planner_branch_group:
        deterministic_outcome = maybe_handle_deterministic_sequence(
            text=text,
            turns=turns,
            low=low,
            trace=trace,
            normalize_reply=normalize_reply,
            is_session_recap_request=is_session_recap_request,
            session_recap_reply=session_recap_reply,
            is_assistant_name_query=is_assistant_name_query,
            assistant_name_reply=assistant_name_reply,
            is_developer_full_name_query=is_developer_full_name_query,
            developer_full_name_reply=developer_full_name_reply,
            is_name_origin_question=is_name_origin_question,
            is_student_data_attendance_rules_query=is_student_data_attendance_rules_query,
            student_data_attendance_rules_reply=student_data_attendance_rules_reply,
            is_developer_profile_request=is_developer_profile_request,
            developer_profile_reply=developer_profile_reply,
            is_conversational_clarification=is_conversational_clarification,
            clarification_reply=clarification_reply,
            is_location_request=is_location_request,
            location_reply=location_reply,
            is_deep_search_followup_request=is_deep_search_followup_request,
            infer_research_query_from_turns=infer_research_query_from_turns,
            build_grounded_answer=build_grounded_answer,
            build_local_topic_digest_answer=build_local_topic_digest_answer,
            is_groundable_factual_query=is_groundable_factual_query,
            developer_color_reply=developer_color_reply,
            developer_bilingual_reply=developer_bilingual_reply,
            color_reply=color_reply,
            animal_reply=animal_reply,
            core=core,
            branch_group=post_planner_branch_group,
        )
        if deterministic_outcome is not None:
            reply, meta, return_mode, tool_time_ms = deterministic_outcome
            timing_profile["tool_time"] = int(tool_time_ms or timing_profile["tool_time"] or 0)
            if return_mode == "logged":
                return _logged_return(reply, meta)
            return _timed_return(reply, meta)

    if stop_before_llm_fallback:
        return _timed_return("", {"planner_decision": "unhandled"})

    fallback_entry = prepare_fallback_flow(
        text=text,
        turns=turns,
        recent_tool_context="",
        prefer_web_for_data_queries=prefer_web_for_data_queries,
        analyze_request_fn=lambda *_args, **_kwargs: SimpleNamespace(allow_llm=True, message=""),
        normalize_policy_reply_fn=normalize_reply,
        build_fallback_context_details_fn=_build_fallback_context_details,
        uses_prior_reference_fn=lambda _text: False,
        action_ledger_add_step=lambda stage, outcome, detail="", **data: trace(stage, outcome, detail, **data),
    )
    if fallback_entry.get("handled"):
        policy_block_outcome = fallback_entry.get("outcome") if isinstance(fallback_entry.get("outcome"), dict) else {}
        return _timed_return(str(policy_block_outcome.get("reply") or ""), {
            "planner_decision": str(policy_block_outcome.get("planner_decision") or "policy_block"),
            "tool": "",
            "tool_args": {},
            "tool_result": "",
            "grounded": bool(policy_block_outcome.get("grounded")),
        })

    retrieved = str(fallback_entry.get("retrieved_context") or "")
    trace("llm_fallback", "invoked", retrieved_chars=len(retrieved))
    trace("llm_call", "started")
    llm_fallback_outcome = finalize_llm_fallback_reply(
        text=text,
        raw_user_text="",
        input_source="",
        retrieved_context=retrieved,
        recent_tool_context="",
        language_mix_spanish_pct=int(language_mix_spanish_pct or 0),
        active_user="",
        ollama_chat_fn=core.ollama_chat,
        sanitize_llm_reply_fn=lambda reply, _tool_context: str(reply or "").strip(),
        mem_enabled_fn=lambda: False,
        mem_should_store_fn=lambda _text: False,
        mem_add_fn=lambda *_args, **_kwargs: None,
        strip_mem_leak_fn=lambda reply, _retrieved_context: reply,
        self_correct_reply_fn=lambda _text, reply: (reply, False, ""),
        behavior_record_event_fn=lambda *_args, **_kwargs: None,
        action_ledger_add_step=lambda *_args, **_kwargs: None,
        teach_store_example_fn=lambda *_args, **_kwargs: None,
        truthful_limit_outcome_fn=core._truthful_limit_outcome,
        apply_claim_gate_fn=lambda reply, evidence_text="", tool_context="": (reply, False, ""),
        post_claim_reply_transform_fn=lambda reply, reply_contract: reply,
        is_explicit_request_fn=lambda _text: True,
        apply_reply_overrides_fn=lambda reply: reply,
        ensure_reply_fn=lambda reply: reply,
    )
    timing_profile["llm_time"] = int(llm_fallback_outcome.get("llm_time_ms") or 0)
    trace("timing", "completed", "llm_call", duration_ms=timing_profile["llm_time"])
    if timing_profile["llm_time"] > 20000:
        trace("llm_call", "slow", "llm_call_slow", duration_ms=timing_profile["llm_time"])
    reply = str(llm_fallback_outcome.get("reply") or "")
    reply_contract = str(llm_fallback_outcome.get("reply_contract") or "")
    reply_outcome: dict[str, object] = dict(llm_fallback_outcome.get("reply_outcome") or {})
    if reply_contract:
        trace("claim_gate", "adjusted", "unsupported_claim_blocked")
    reply, meta = _break_fallback_loop(reply, {
        "planner_decision": str(llm_fallback_outcome.get("planner_decision") or "llm_fallback"),
        "tool": "",
        "tool_args": {},
        "tool_result": "",
        "grounded": llm_fallback_outcome.get("grounded"),
        "reply_contract": reply_contract,
        "reply_outcome": reply_outcome,
    })
    timing_profile["post_time"] = int(llm_fallback_outcome.get("post_time_ms") or 0)
    trace("timing", "completed", "post_processing", duration_ms=timing_profile["post_time"])
    return _timed_return(reply, meta)

