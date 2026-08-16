from __future__ import annotations

import time
from typing import Callable

from services import nova_planner_contract
from services.nova_fallback_flow import finalize_llm_fallback_reply, prepare_fallback_flow
from services.nova_intent_understanding import ACCEPT, self_status_belongs_to_turn
from services.memory_production import MEMORY_LEARNING_SHORT_CIRCUIT_ACTIONS
from services.nova_turn_contract import bind_turn_request, maybe_run_attachment_vision_turn


def _runtime_fn(runtime_scope: dict[str, object], name: str):
    return runtime_scope[name]


def execute_reply_sequence_from_runtime(
    *,
    turns: list[tuple[str, str]],
    text: str,
    pending_action: dict | None,
    turn_acts: list[str] | None = None,
    prefer_web_for_data_queries: bool,
    language_mix_spanish_pct: int,
    session,
    trace: Callable[..., None],
    normalize_reply: Callable[[str], str],
    ensure_reply: Callable[[str], str],
    core,
    runtime_scope: dict[str, object],
    stop_before_llm_fallback: bool = False,
    ensure_active_work_tree_fn: Callable[[str], str] | None = None,
    work_tree_seed_source: str = "",
    work_tree_seed_mode: str = "",
    input_source: str = "typed",
    channel: str = "http",
    attachments: list[dict] | None = None,
) -> tuple[str, dict]:
    del runtime_scope

    from services.nova_turn_contract import bind_turn_request, execute_conversation_turn

    turn = bind_turn_request(
        text=text,
        channel=channel,
        input_source=input_source,
        attachments=list(attachments or []),
        work_tree_seed_source=work_tree_seed_source,
    )
    return execute_conversation_turn(
        execute_reply_sequence_fn=execute_reply_sequence,
        turn=turn,
        turns=turns,
        pending_action=pending_action,
        turn_acts=turn_acts,
        prefer_web_for_data_queries=prefer_web_for_data_queries,
        language_mix_spanish_pct=language_mix_spanish_pct,
        session=session,
        trace=trace,
        normalize_reply=normalize_reply,
        ensure_reply=ensure_reply,
        core=core,
        ensure_active_work_tree_fn=ensure_active_work_tree_fn,
        work_tree_seed_source=work_tree_seed_source,
        work_tree_seed_mode=work_tree_seed_mode,
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
    ensure_active_work_tree_fn: Callable[[str], str] | None = None,
    input_source: str = "http",
    channel: str = "http",
    attachments: list[dict] | None = None,
) -> tuple[str, dict]:
    def _trace(stage: str, outcome: str, detail: str = "", **data) -> None:
        core.action_ledger_add_step(ledger_record, stage, outcome, detail, **data)

    def _normalize_reply(reply_text: str) -> str:
        reply_local = _runtime_fn(runtime_scope, "_strip_ui_tip_leak")(reply_text)
        return ensure_reply(reply_local)

    turn_acts = None
    if isinstance(ledger_record, dict) and isinstance(ledger_record.get("turn_acts"), list):
        turn_acts = [str(item).strip() for item in ledger_record.get("turn_acts") if str(item).strip()]

    return execute_reply_sequence_from_runtime(
        turns=turns,
        text=text,
        pending_action=pending_action,
        turn_acts=turn_acts,
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
        input_source=input_source,
        channel=channel,
        attachments=attachments,
    )


def execute_reply_sequence(
    *,
    turns: list[tuple[str, str]],
    text: str,
    pending_action: dict | None,
    turn_acts: list[str] | None = None,
    prefer_web_for_data_queries: bool,
    language_mix_spanish_pct: int,
    session,
    trace: Callable[..., None],
    normalize_reply: Callable[[str], str],
    ensure_reply: Callable[[str], str],
    core,
    ensure_active_work_tree_fn: Callable[[str], str] | None = None,
    work_tree_seed_source: str = "",
    work_tree_seed_mode: str = "",
    input_source: str = "typed",
    channel: str = "cli",
    attachments: list[dict] | None = None,
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

    def _break_fallback_loop(reply_text: str, meta: dict) -> tuple[str, dict]:
        normalized_reply = normalize_reply(reply_text)
        return normalized_reply, meta

    def _build_fallback_context_details(user_text: str, session_turns: list[tuple[str, str]]):
        build_fn = core.build_fallback_context_details
        try:
            return build_fn(
                user_text,
                session_turns,
                conversation_state=getattr(session, "conversation_state", None),
                pending_action=pending_action,
                include_state_context=True,
                include_chat_context=True,
            )
        except TypeError:
            return build_fn(user_text, session_turns)

    turn = bind_turn_request(
        text=text,
        channel=channel,
        input_source=input_source,
        attachments=attachments,
        work_tree_seed_source=work_tree_seed_source,
    )
    input_source = turn.input_source
    work_tree_seed_source = turn.work_tree_seed_source

    _apply_learning_fn = getattr(core, "apply_user_memory_learning", None)
    if callable(_apply_learning_fn):
        try:
            learning_outcome = _apply_learning_fn(
                text,
                input_source=input_source,
                session=session,
                turns=turns,
                pending_action=pending_action,
            ) or {}
        except Exception:
            learning_outcome = {}
        if isinstance(learning_outcome, dict) and learning_outcome.get("handled"):
            action = str(learning_outcome.get("action") or "").strip()
            trace("memory_learning", "handled", action or "learning")
            early_reply = str(learning_outcome.get("early_reply") or "").strip()
            if action in MEMORY_LEARNING_SHORT_CIRCUIT_ACTIONS and early_reply:
                return _timed_return(
                    early_reply,
                    {
                        "planner_decision": "memory_learning",
                        "memory_learning_action": action,
                    },
                )

    # --- Intent understanding: classify the turn BEFORE the planner runs ---
    turn_intent: dict = {}
    response_strategy: dict = {}
    _classify_intent_fn = getattr(core, "classify_turn_intent", None)
    _select_strategy_fn = getattr(core, "select_response_strategy", None)
    if callable(_classify_intent_fn):
        try:
            turn_intent = _classify_intent_fn(text, turns) or {}
        except Exception:
            turn_intent = {}
    if callable(_select_strategy_fn) and turn_intent:
        try:
            response_strategy = _select_strategy_fn(turn_intent) or {}
        except Exception:
            response_strategy = {}
    if turn_intent:
        trace(
            "intent_understanding",
            "classified",
            str(turn_intent.get("subject") or ""),
            level=str(turn_intent.get("level") or ""),
            domain=str(turn_intent.get("domain") or ""),
            confidence=float(turn_intent.get("confidence") or 0.0),
            strategy=str(response_strategy.get("strategy") or ""),
        )

    planner_call_started = time.perf_counter()
    semantic_tool_observation: dict[str, object] = {}

    def _observe_semantic_tool(payload: dict) -> None:
        semantic_tool_observation.clear()
        if isinstance(payload, dict):
            semantic_tool_observation.update(payload)

    attachment_vision_outcome = maybe_run_attachment_vision_turn(
        text=text,
        attachments=turn.attachments,
        core=core,
        trace=trace,
        normalize_reply=normalize_reply,
    )
    if attachment_vision_outcome is not None:
        return _timed_return(*_break_fallback_loop(*attachment_vision_outcome))

    planner_outcome = None
    if str(response_strategy.get("strategy") or "") == ACCEPT:
        timing_profile["planner_time"] = 0
        trace("timing", "completed", "planner_call", duration_ms=0)
    else:
        planner_outcome = nova_planner_contract.maybe_handle_planner_sequence(
        text=text,
        turns=turns,
        pending_action=pending_action,
        turn_acts=turn_acts,
        prefer_web_for_data_queries=prefer_web_for_data_queries,
        session=session,
        core=core,
        trace=trace,
        normalize_reply=normalize_reply,
        ensure_active_work_tree_fn=ensure_active_work_tree_fn,
        work_tree_seed_source=work_tree_seed_source,
        work_tree_seed_mode=work_tree_seed_mode,
        semantic_tool_observer_fn=_observe_semantic_tool,
    )
    timing_profile["planner_time"] = int((time.perf_counter() - planner_call_started) * 1000)
    trace("timing", "completed", "planner_call", duration_ms=timing_profile["planner_time"])
    deferred_tool_meta: dict[str, object] = {}
    if planner_outcome is not None:
        planner_reply, planner_meta = planner_outcome
        planner_payload = dict(planner_meta or {})
        if bool(planner_payload.get("defer_to_fallback")):
            deferred_tool_meta = planner_payload
            observed_intent = dict((semantic_tool_observation.get("intent") or {}) if isinstance(semantic_tool_observation.get("intent"), dict) else {})
            if not observed_intent:
                observed_intent = {
                    "tool": str(planner_payload.get("tool") or ""),
                    "args": list((planner_payload.get("tool_args") or {}).get("args") or [])
                    if isinstance(planner_payload.get("tool_args"), dict)
                    else [],
                    "evidence_need": "tool_result",
                    "answer_target": "current_conversation",
                }
            semantic_tool_observation.clear()
            semantic_tool_observation.update(
                {
                    "status": "tool_result_available",
                    "intent": observed_intent,
                    "tool": str(planner_payload.get("tool") or ""),
                    "tool_result_available": True,
                }
            )
            if (
                str(planner_payload.get("tool") or "").strip() == "self_status"
                and not self_status_belongs_to_turn(turn_intent, response_strategy)
            ):
                deferred_tool_meta = {}
                semantic_tool_observation.clear()
                trace("action_planner", "self_status_held_for_conversation")
            else:
                trace(
                    "action_planner",
                    "tool_evidence_for_fallback",
                    tool=str(planner_payload.get("tool") or ""),
                )
        else:
            return _timed_return(*_break_fallback_loop(planner_reply, planner_payload))

    # Attempt fulfillment flow before falling to generic LLM.
    # Only fires when planner found no tool action and no deferred tool result.
    if not deferred_tool_meta:
        fulfillment_fn = getattr(core, "maybe_run_fulfillment_flow", None)
        if callable(fulfillment_fn):
            try:
                fulfillment_result = fulfillment_fn(
                    text,
                    session,
                    list(turns),
                    pending_action=pending_action,
                    semantic_observation=dict(semantic_tool_observation),
                )
            except TypeError:
                fulfillment_result = fulfillment_fn(
                    text,
                    session,
                    list(turns),
                    pending_action=pending_action,
                )
            except Exception:
                fulfillment_result = None
            if isinstance(fulfillment_result, dict) and str(fulfillment_result.get("reply") or "").strip():
                trace("fulfillment", "handled", planner_decision=str(fulfillment_result.get("planner_decision") or "fulfillment"))
                reply, meta = _break_fallback_loop(
                    ensure_reply(str(fulfillment_result.get("reply") or "")),
                    {
                        "planner_decision": str(fulfillment_result.get("planner_decision") or "fulfillment"),
                        "tool": "",
                        "tool_args": {},
                        "tool_result": "",
                        "grounded": bool(fulfillment_result.get("grounded")),
                        "reply_contract": "fulfillment.reply",
                        "reply_outcome": {"kind": str(fulfillment_result.get("planner_decision") or "fulfillment")},
                    },
                )
                return _timed_return(reply, meta)

    if stop_before_llm_fallback:
        meta = {
            "planner_decision": "unhandled",
            "semantic_tool_observation": dict(semantic_tool_observation),
        }
        if deferred_tool_meta:
            meta["tool"] = str(deferred_tool_meta.get("tool") or "")
            meta["tool_args"] = deferred_tool_meta.get("tool_args") if isinstance(deferred_tool_meta.get("tool_args"), dict) else {}
            meta["tool_result"] = str(deferred_tool_meta.get("tool_result") or "")
            meta["grounded"] = deferred_tool_meta.get("grounded") if isinstance(deferred_tool_meta.get("grounded"), bool) else None
            meta["reply_contract"] = str(deferred_tool_meta.get("reply_contract") or "")
            meta["deferred_tool"] = dict(deferred_tool_meta)
        return _timed_return("", meta)

    fallback_entry = prepare_fallback_flow(
        text=text,
        turns=turns,
        build_fallback_context_details_fn=_build_fallback_context_details,
        action_ledger_add_step=lambda stage, outcome, detail="", **data: trace(stage, outcome, detail, **data),
        pending_action=pending_action,
        semantic_tool_observation=semantic_tool_observation,
        planner_decision=str(deferred_tool_meta.get("planner_decision") or "") if deferred_tool_meta else "",
        tool=str(deferred_tool_meta.get("tool") or "") if deferred_tool_meta else "",
        tool_result=str(deferred_tool_meta.get("tool_result") or "") if deferred_tool_meta else "",
        turn_intent=turn_intent,
        response_strategy=response_strategy,
    )

    retrieved = str(fallback_entry.get("retrieved_context") or "")
    intent_evidence_packet = fallback_entry.get("intent_evidence_packet") if isinstance(fallback_entry.get("intent_evidence_packet"), dict) else {}
    trace("llm_fallback", "invoked", retrieved_chars=len(retrieved))
    trace("llm_call", "started")
    llm_fallback_outcome = finalize_llm_fallback_reply(
        text=text,
        raw_user_text=text,
        input_source=str(input_source or "typed"),
        retrieved_context=retrieved,
        language_mix_spanish_pct=int(language_mix_spanish_pct or 0),
        ollama_chat_fn=core.ollama_chat,
        mem_enabled_fn=getattr(core, "mem_enabled", lambda: False),
        mem_should_store_fn=getattr(core, "mem_should_store", lambda _text: False),
        mem_add_fn=getattr(core, "mem_add", lambda *_args, **_kwargs: None),
        strip_mem_leak_fn=lambda reply, _retrieved_context: reply,
        behavior_record_event_fn=getattr(core, "behavior_record_event", lambda *_args, **_kwargs: None),
        action_ledger_add_step=lambda stage, outcome, detail="", **data: trace(stage, outcome, detail, **data),
        ensure_reply_fn=ensure_reply,
        intent_evidence_packet=intent_evidence_packet,
        fallback_context=fallback_entry.get("fallback_context") if isinstance(fallback_entry.get("fallback_context"), dict) else {},
    )
    timing_profile["llm_time"] = int(llm_fallback_outcome.get("llm_time_ms") or 0)
    trace("timing", "completed", "llm_call", duration_ms=timing_profile["llm_time"])
    if timing_profile["llm_time"] > 20000:
        trace("llm_call", "slow", "llm_call_slow", duration_ms=timing_profile["llm_time"])
    reply = str(llm_fallback_outcome.get("reply") or "")
    reply_contract = str(llm_fallback_outcome.get("reply_contract") or "")
    reply_outcome: dict[str, object] = dict(llm_fallback_outcome.get("reply_outcome") or {})
    if deferred_tool_meta:
        reply_outcome["deferred_tool"] = {
            "tool": str(deferred_tool_meta.get("tool") or ""),
            "reply_contract": str(deferred_tool_meta.get("reply_contract") or ""),
            "grounded": bool(deferred_tool_meta.get("grounded")),
        }
    g = llm_fallback_outcome.get("grounded")
    if g is None and deferred_tool_meta:
        g = True
    reply, meta = _break_fallback_loop(reply, {
        "planner_decision": str(llm_fallback_outcome.get("planner_decision") or "llm_fallback"),
        "tool": str(deferred_tool_meta.get("tool") or "") if deferred_tool_meta else "",
        "tool_args": {},
        "tool_result": str(deferred_tool_meta.get("tool_result") or "") if deferred_tool_meta else "",
        "grounded": g,
        "reply_contract": reply_contract,
        "reply_outcome": reply_outcome,
    })
    timing_profile["post_time"] = int(llm_fallback_outcome.get("post_time_ms") or 0)
    trace("timing", "completed", "post_processing", duration_ms=timing_profile["post_time"])
    return _timed_return(reply, meta)
