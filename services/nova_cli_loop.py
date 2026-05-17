from __future__ import annotations

import re
import sys
from types import SimpleNamespace
from typing import Optional

from services import nova_planner_contract
from services.nova_cli_delivery import apply_cli_handled_outcome
from services.nova_cli_delivery import apply_cli_outcome_to_ledger
from services.nova_cli_delivery import emit_cli_reply_outcome
from services.nova_cli_sequence import execute_cli_sequence as service_execute_cli_sequence
from services.nova_cli_sequence import apply_sequence_result as service_apply_sequence_result
from services.nova_cli_sequence import normalize_sequence_reply as service_normalize_sequence_reply
from services.nova_fallback_flow import prepare_fallback_flow
from services.nova_fallback_flow import finalize_llm_fallback_reply
from services.nova_supervisor_flow import apply_cli_supervisor_intent
from services.nova_turn_outcomes import apply_numeric_clarify_outcome
from services.nova_reply_sequence import execute_reply_sequence
from services.nova_reply_runtime import apply_reply_runtime_effects
from services.nova_session_state import apply_reply_session_updates
from services.work_tree_seeding import WORK_TREE_SEEDING_SERVICE
from services.work_tree_decision_adapter import WORK_TREE_DECISION_ADAPTER


def run_loop(tts, *, core: object) -> None:
    whisper = None
    voice_interactive = bool(getattr(sys.stdin, "isatty", lambda: False)())

    def _ensure_whisper_loaded() -> bool:
        nonlocal whisper
        if whisper is not None:
            return True
        if not voice_interactive:
            return False
        if not core._ensure_voice_deps() or core.WhisperModel is None:
            return False
        print("Nova Core: loading Whisper (CPU mode)...", flush=True)
        whisper = core.WhisperModel(core.whisper_size(), device="cpu", compute_type="int8")
        return whisper is not None

    print("\nNova Core is ready.", flush=True)
    print("Commands: screen | camera <prompt> | web <url> | web search <query> | web research <query> | web gather <url> | weather in <location-or-lat,lon> | check weather for <location> | weather current location | location coords <lat,lon> | domains | policy allow <domain> | chat context | queue status | ls [folder] | read <file> | find <kw> [folder] | health | capabilities | inspect", flush=True)
    print("Press ENTER for voice. Or type a message/command and press ENTER. Type 'q' to quit.\n", flush=True)

    recent_tool_context = ""
    recent_web_urls: list[str] = []
    session_turns: list[tuple[str, str]] = []
    session_state = core.ConversationSession()
    pending_action_ledger: Optional[dict] = None
    pending_action: Optional[dict] = session_state.pending_action
    conversation_state: Optional[dict] = session_state.conversation_state
    prefer_web_for_data_queries = session_state.prefer_web_for_data_queries
    language_mix_spanish_pct = int(session_state.language_mix_spanish_pct or 0)

    def _set_pending_action(value: Optional[dict]) -> None:
        nonlocal pending_action
        pending_action = value if isinstance(value, dict) else None
        session_state.set_pending_action(pending_action)

    def _set_conversation_state(value: Optional[dict]) -> None:
        nonlocal conversation_state
        conversation_state = value if isinstance(value, dict) else None
        session_state.set_conversation_state(conversation_state)

    def _set_prefer_web_for_data_queries(value: bool) -> None:
        nonlocal prefer_web_for_data_queries
        prefer_web_for_data_queries = bool(value)
        session_state.set_prefer_web_for_data_queries(prefer_web_for_data_queries)

    def _set_language_mix_spanish_pct(value: int) -> None:
        nonlocal language_mix_spanish_pct
        language_mix_spanish_pct = core._clamp_language_mix(value)
        session_state.set_language_mix_spanish_pct(language_mix_spanish_pct)

    def _sync_pending_conversation_tracking() -> None:
        if not pending_action_ledger:
            return
        subject = session_state.active_subject()
        pending_action_ledger["active_subject"] = subject
        record = pending_action_ledger.get("record")
        if isinstance(record, dict):
            record["active_subject"] = subject
            record["continuation_used"] = bool(pending_action_ledger.get("continuation_used", False))

    def _ensure_active_work_tree(seed_text: str) -> str:
        existing = str(getattr(session_state, "active_work_tree_id", "") or "").strip()
        existing_identity = str(getattr(session_state, "active_work_identity", "") or "").strip()
        try:
            import work_tree
            if existing and work_tree.get_tree(existing) is not None:
                return existing
            resolution = WORK_TREE_SEEDING_SERVICE.resolve_seeded_tree(
                work_tree_module=work_tree,
                title_seed=str(seed_text or "").strip(),
                source="cli",
                user_id="",
                nova_core_module=core,
                active_tree_id=existing,
                active_work_identity=existing_identity,
            )
        except Exception:
            return ""
        tree_id = str((resolution or {}).get("tree_id") or "").strip()
        work_identity_key = str((resolution or {}).get("work_identity_key") or "").strip()
        continuity = str((resolution or {}).get("continuity") or "").strip()
        branch_decision = str((resolution or {}).get("branch_decision") or "").strip()
        decision_type = str((resolution or {}).get("decision_type") or "").strip()
        branch_id = str((resolution or {}).get("branch_id") or "").strip()
        
        if work_identity_key and (decision_type or continuity):
            if hasattr(session_state, "record_decision"):
                try:
                    session_state.record_decision(
                        decision_type=(decision_type or continuity),
                        work_identity_key=work_identity_key,
                        branch_id=branch_id,
                    )
                except Exception:
                    pass

            bias = WORK_TREE_DECISION_ADAPTER.get_bias_for_identity(
                work_identity_key=work_identity_key
            )
            if bias and hasattr(session_state, "set_decision_adapter_bias"):
                try:
                    session_state.set_decision_adapter_bias(bias)
                except Exception:
                    pass
        
        if hasattr(session_state, "set_active_work_tree_id"):
            try:
                session_state.set_active_work_tree_id(tree_id)
            except Exception:
                pass
        if hasattr(session_state, "set_active_work_identity"):
            try:
                session_state.set_active_work_identity(work_identity_key)
            except Exception:
                pass
        if hasattr(session_state, "set_last_work_continuity"):
            try:
                session_state.set_last_work_continuity(continuity)
            except Exception:
                pass
        # Phase 4: Track branching decisions
        if hasattr(session_state, "set_last_branch_decision"):
            try:
                session_state.set_last_branch_decision(branch_decision or continuity)
            except Exception:
                pass
        return str(tree_id or "").strip()

    def _trace(stage: str, outcome: str, detail: str = "", **data) -> None:
        if not pending_action_ledger:
            return
        core.action_ledger_add_step(pending_action_ledger.get("record"), stage, outcome, detail, **data)

    def _apply_sequence_result(final: str, meta: dict) -> None:
        nonlocal recent_tool_context, recent_web_urls, conversation_state, pending_action
        outcome = service_apply_sequence_result(
            final=final,
            meta=meta,
            pending_action_ledger=pending_action_ledger,
            merge_route_evidence_fn=nova_planner_contract.merge_route_evidence,
            set_pending_action_fn=_set_pending_action,
            session_state=session_state,
            routed_text=routed_user_text,
            turns=session_turns,
            fallback_state=conversation_state,
            infer_post_reply_conversation_state_fn=core._infer_post_reply_conversation_state,
            apply_reply_runtime_effects_fn=apply_reply_runtime_effects,
            apply_reply_session_updates_fn=apply_reply_session_updates,
            sync_pending_conversation_tracking_fn=_sync_pending_conversation_tracking,
            trace_fn=_trace,
            emit_cli_reply_outcome_fn=lambda **kwargs: emit_cli_reply_outcome(
                print_fn=print,
                speak_chunked_fn=lambda reply: core.speak_chunked(tts, reply),
                say_done_fn=tts.say,
                **kwargs,
            ),
            behavior_record_event_fn=core.behavior_record_event,
            extract_urls_fn=core._extract_urls,
            detect_identity_conflict_fn=core.detect_identity_conflict,
            recent_tool_context=recent_tool_context,
            recent_web_urls=recent_web_urls,
        )
        recent_tool_context = str(outcome.get("recent_tool_context") or "")
        recent_web_urls = list(outcome.get("recent_web_urls") or [])
        conversation_state = outcome.get("conversation_state") if isinstance(outcome.get("conversation_state"), dict) else session_state.conversation_state
        pending_action = outcome.get("pending_action") if isinstance(outcome.get("pending_action"), dict) else session_state.pending_action

    def _flush_pending_action_ledger() -> None:
        nonlocal pending_action_ledger
        if not pending_action_ledger:
            return
        try:
            start_idx = int(pending_action_ledger.get("start_idx", len(session_turns)))
        except Exception:
            start_idx = len(session_turns)

        final_answer = ""
        for role, txt in session_turns[start_idx:]:
            if role == "assistant":
                final_answer = txt

        if not final_answer:
            final_answer = str(pending_action_ledger.get("tool_result") or "")

        merged_routing_decision = nova_planner_contract.merge_route_evidence(
            pending_action_ledger.get("routing_decision") if isinstance(pending_action_ledger.get("routing_decision"), dict) else {},
            pending_action_ledger,
        ) or {}

        core.finalize_action_ledger_record(
            pending_action_ledger.get("record") or {},
            final_answer=final_answer,
            planner_decision=str(pending_action_ledger.get("planner_decision") or "deterministic"),
            tool=str(pending_action_ledger.get("tool") or ""),
            tool_args=pending_action_ledger.get("tool_args") if isinstance(pending_action_ledger.get("tool_args"), dict) else {},
            tool_result=str(pending_action_ledger.get("tool_result") or ""),
            grounded=pending_action_ledger.get("grounded") if isinstance(pending_action_ledger.get("grounded"), bool) else None,
            intent=str(pending_action_ledger.get("intent") or ""),
            active_subject=str(pending_action_ledger.get("active_subject") or ""),
            continuation_used=bool(pending_action_ledger.get("continuation_used", False)),
            reply_contract=str(pending_action_ledger.get("reply_contract") or ""),
            reply_outcome=pending_action_ledger.get("reply_outcome") if isinstance(pending_action_ledger.get("reply_outcome"), dict) else {},
            routing_decision=merged_routing_decision,
            reflection_payload=core.build_turn_reflection(
                session_state,
                entry_point="cli",
                session_id="cli",
                current_decision={
                    "user_input": str((pending_action_ledger.get("record") or {}).get("user_input") or ""),
                    "planner_decision": str(pending_action_ledger.get("planner_decision") or "deterministic"),
                    "tool": str(pending_action_ledger.get("tool") or ""),
                    "tool_result": str(pending_action_ledger.get("tool_result") or ""),
                    "final_answer": final_answer,
                    "reply_contract": str(pending_action_ledger.get("reply_contract") or ""),
                    "reply_outcome": pending_action_ledger.get("reply_outcome") if isinstance(pending_action_ledger.get("reply_outcome"), dict) else {},
                    "turn_acts": list(pending_action_ledger.get("turn_acts") or []),
                    "grounded": pending_action_ledger.get("grounded") if isinstance(pending_action_ledger.get("grounded"), bool) else None,
                    "active_subject": str(pending_action_ledger.get("active_subject") or session_state.active_subject() or ""),
                    "continuation_used": bool(pending_action_ledger.get("continuation_used", False)),
                    "pending_action": session_state.pending_action,
                    "routing_decision": core._finalize_routing_decision(
                        merged_routing_decision,
                        planner_decision=str(pending_action_ledger.get("planner_decision") or "deterministic"),
                        reply_contract=str(pending_action_ledger.get("reply_contract") or ""),
                        reply_outcome=pending_action_ledger.get("reply_outcome") if isinstance(pending_action_ledger.get("reply_outcome"), dict) else {},
                        turn_acts=list(pending_action_ledger.get("turn_acts") or []),
                    ),
                    "route_summary": core.action_ledger_route_summary((pending_action_ledger.get("record") or {}).get("route_trace")),
                },
            ),
        )
        pending_action_ledger = None

    while True:
        _flush_pending_action_ledger()
        session_state.reset_turn_flags()
        raw = input("> ").strip()
        input_source = "typed"

        if raw.lower() == "q":
            break

        if raw:
            user_text = raw
            m_idx = re.match(r"^\s*web\s+gather\s+(\d+)\s*$", user_text, flags=re.I)
            if m_idx and recent_web_urls:
                idx = int(m_idx.group(1))
                if 1 <= idx <= len(recent_web_urls):
                    user_text = f"web gather {recent_web_urls[idx - 1]}"
            user_text = core._strip_invocation_prefix(user_text)
            print(f"You (typed): {user_text}", flush=True)
        else:
            input_source = "voice"
            if not _ensure_whisper_loaded():
                core.warn(f"Voice mode disabled; typed chat still works. (Reason: {core.VOICE_IMPORT_ERR})")
                print("Nova: voice is disabled on this machine right now. Type your message instead.\n", flush=True)
                continue
            audio = core.record_seconds(core.RECORD_SECONDS)
            print("Nova: transcribing...", flush=True)
            user_text = core.transcribe(whisper, audio)
            if not user_text:
                print("Nova: (heard nothing)\n", flush=True)
                continue
            user_text = core._strip_invocation_prefix(user_text)
            print(f"You: {user_text}", flush=True)

        session_turns.append(("user", user_text))
        pending_action_ledger = {
            "record": core.start_action_ledger_record(
                user_text,
                channel="cli",
                session_id=core.get_active_user() or "",
                input_source=input_source,
                active_subject=session_state.active_subject(),
            ),
            "start_idx": len(session_turns),
            "intent": core._infer_turn_intent(user_text),
            "planner_decision": "deterministic",
            "tool": "",
            "tool_args": {},
            "tool_result": "",
            "grounded": None,
            "active_subject": session_state.active_subject(),
            "continuation_used": False,
        }

        routed_user_text = user_text
        turn_direction = {
            "primary": "general_chat",
            "effective_query": user_text,
            "analysis_reason": "",
            "turn_acts": [],
            "identity_focused": False,
            "bypass_pattern_routes": False,
        }
        try:
            turn_direction = core._determine_turn_direction(
                session_turns,
                user_text,
                active_subject=session_state.active_subject(),
                pending_action=pending_action,
            )
            routed_user_text = str(turn_direction.get("effective_query") or user_text)
            _set_language_mix_spanish_pct(core._auto_adjust_language_mix(language_mix_spanish_pct, routed_user_text))
            turn_acts = [str(item).strip() for item in list(turn_direction.get("turn_acts") or []) if str(item).strip()]
            if pending_action_ledger is not None:
                pending_action_ledger["turn_acts"] = turn_acts
                record = pending_action_ledger.get("record")
                if isinstance(record, dict):
                    record["turn_acts"] = list(turn_acts)
            _trace(
                "direction_analysis",
                str(turn_direction.get("primary") or "general_chat"),
                str(turn_direction.get("analysis_reason") or "")[:120],
                effective_query=routed_user_text[:180],
                turn_acts=",".join(turn_acts),
                identity_focused=bool(turn_direction.get("identity_focused")),
                bypass_pattern_routes=bool(turn_direction.get("bypass_pattern_routes")),
            )
        except Exception:
            routed_user_text = user_text
            turn_acts = []

        intent_rule = core.TURN_SUPERVISOR.evaluate_rules(
            routed_user_text,
            manager=session_state,
            turns=session_turns,
            phase="intent",
            entry_point="cli",
        )
        if not core._supervisor_result_has_route(intent_rule):
            runtime_intent = core._runtime_set_location_intent(routed_user_text, pending_action=pending_action)
            if isinstance(runtime_intent, dict):
                intent_rule = runtime_intent
        numeric_clarify_outcome = apply_numeric_clarify_outcome(
            has_intent_route=core._supervisor_result_has_route(intent_rule),
            routed_text=routed_user_text,
            pending_action=pending_action,
            current_state=conversation_state,
            session=session_state,
            ledger=pending_action_ledger.get("record") if isinstance(pending_action_ledger, dict) else {},
            should_clarify_unlabeled_numeric_turn=core._should_clarify_unlabeled_numeric_turn,
            unlabeled_numeric_turn_reply=core._unlabeled_numeric_turn_reply,
            make_conversation_state=core._make_conversation_state,
            action_ledger_add_step=lambda _ledger, stage, outcome, detail="", **data: _trace(stage, outcome, detail, **data),
        )
        if numeric_clarify_outcome.get("handled"):
            _set_conversation_state(session_state.conversation_state)
            _sync_pending_conversation_tracking()
            apply_cli_handled_outcome(
                pending_action_ledger=pending_action_ledger,
                outcome=numeric_clarify_outcome,
                default_planner_decision="ask_clarify",
                session_turns=session_turns,
                print_fn=print,
                speak_chunked_fn=lambda reply: core.speak_chunked(tts, reply),
                say_done_fn=lambda _msg: None,
                coerce_grounded=True,
            )
            continue
        handled_intent, intent_msg, intent_state, intent_effects = core._handle_supervisor_intent(
            intent_rule,
            routed_user_text,
            turns=session_turns,
            input_source=input_source,
            entry_point="cli",
        )
        if pending_action_ledger is not None:
            pending_action_ledger["routing_decision"] = core._build_routing_decision(
                routed_user_text,
                entry_point="cli",
                intent_result=intent_rule,
                handle_result=None,
                reply_contract=str(intent_effects.get("reply_contract") or "") if isinstance(intent_effects, dict) else "",
                reply_outcome=dict(intent_effects.get("reply_outcome") or {}) if isinstance(intent_effects, dict) and isinstance(intent_effects.get("reply_outcome"), dict) else {},
                turn_acts=turn_acts,
            )
        handled_cli_intent, final = apply_cli_supervisor_intent(
            intent_rule=intent_rule,
            routed_user_text=routed_user_text,
            handled_intent=handled_intent,
            intent_msg=intent_msg,
            intent_state=intent_state,
            intent_effects=intent_effects,
            pending_action_ledger=pending_action_ledger,
            ensure_reply_fn=core._ensure_reply,
            emit_supervisor_intent_trace_fn=core._emit_supervisor_intent_trace,
            set_pending_action_fn=_set_pending_action,
            set_conversation_state_fn=_set_conversation_state,
            sync_pending_conversation_tracking_fn=_sync_pending_conversation_tracking,
            trace_fn=_trace,
        )
        if handled_cli_intent:
            print(f"Nova: {final}\n", flush=True)
            session_turns.append(("assistant", final))
            core.speak_chunked(tts, final)
            continue
        general_rule = core.TURN_SUPERVISOR.evaluate_rules(
            user_text,
            manager=session_state,
            turns=session_turns,
            phase="handle",
            entry_point="cli",
        )
        handled_rule, rule_msg, rule_state = core._execute_registered_supervisor_rule(
            general_rule,
            user_text,
            conversation_state,
            turns=session_turns,
            input_source=input_source,
            allowed_actions=set(),
        )
        if pending_action_ledger is not None:
            pending_action_ledger["routing_decision"] = core._build_routing_decision(
                routed_user_text,
                entry_point="cli",
                intent_result=intent_rule,
                handle_result=general_rule,
                reply_contract=str(general_rule.get("reply_contract") or "") if isinstance(general_rule, dict) else "",
                reply_outcome=dict(general_rule.get("reply_outcome") or {}) if isinstance(general_rule, dict) and isinstance(general_rule.get("reply_outcome"), dict) else {},
                turn_acts=turn_acts,
            )
        if handled_rule:
            final = core._ensure_reply(rule_msg)
            if pending_action_ledger is not None:
                pending_action_ledger["reply_contract"] = str(general_rule.get("reply_contract") or "")
                pending_action_ledger["reply_outcome"] = dict(general_rule.get("reply_outcome") or {}) if isinstance(general_rule.get("reply_outcome"), dict) else {}
            _set_conversation_state(rule_state)
            if bool(general_rule.get("continuation")):
                session_state.mark_continuation_used()
                if pending_action_ledger is not None:
                    pending_action_ledger["continuation_used"] = True
            _trace(
                str(general_rule.get("ledger_stage") or "registered_rule"),
                "matched",
                str(general_rule.get("rule_name") or "registered_rule"),
                rule=str(general_rule.get("rule_name") or ""),
            )
            core.SUBCONSCIOUS_SERVICE.update_state(
                session_state,
                core._probe_turn_routes(
                    routed_user_text,
                    session_state,
                    session_turns,
                    pending_action=pending_action,
                ),
                chosen_route="supervisor_owned",
            )
            _sync_pending_conversation_tracking()
            print(f"Nova: {final}\n", flush=True)
            session_turns.append(("assistant", final))
            core.speak_chunked(tts, final)
            continue

        try:
            id_m = None
            if id_m:
                name = id_m.group(1).strip().strip(".!,")
                if name:
                    core.mem_add("profile", input_source, f"name: {name}")
                    core.set_active_user(name)
                    ack = f"Nice to meet you, {name}. I'll remember that and use that identity for this session."
                    print(f"Nova: {ack}\n", flush=True)
                    session_turns.append(("assistant", ack))
                    core.speak_chunked(tts, ack)
                    continue
        except Exception:
            pass

        def _normalize_sequence_reply(reply: str) -> str:
            return service_normalize_sequence_reply(
                reply,
                ensure_reply_fn=core._ensure_reply,
                apply_reply_overrides_fn=lambda value: value,
            )

        sequence_reply, sequence_meta = service_execute_cli_sequence(
            execute_reply_sequence_fn=execute_reply_sequence,
            turns=session_turns,
            text=routed_user_text,
            pending_action=pending_action,
            prefer_web_for_data_queries=prefer_web_for_data_queries,
            language_mix_spanish_pct=language_mix_spanish_pct,
            session=session_state,
            trace=_trace,
            normalize_reply=_normalize_sequence_reply,
            ensure_reply=core._ensure_reply,
            core=core,
            is_developer_profile_request=lambda _text: False,
            developer_profile_reply=lambda _turns, _text: "",
            is_location_request=lambda _text: False,
            location_reply=lambda: "",
            is_web_preferred_data_query=getattr(core, "_is_web_preferred_data_query", lambda _text: False),
            is_session_recap_request=lambda _text: False,
            session_recap_reply=lambda _turns, _text: "",
            is_assistant_name_query=lambda _text: False,
            assistant_name_reply=lambda _text: "",
            is_developer_full_name_query=lambda _text: False,
            developer_full_name_reply=lambda: "",
            is_name_origin_question=lambda _text: False,
            is_student_data_attendance_rules_query=lambda _text: False,
            student_data_attendance_rules_reply=lambda: "",
            is_conversational_clarification=lambda _text: False,
            clarification_reply=lambda _turns: "",
            is_deep_search_followup_request=lambda _text: False,
            infer_research_query_from_turns=lambda _turns: "",
            build_grounded_answer=lambda _query, max_sources=2: "",
            build_local_topic_digest_answer=lambda _query: "",
            is_groundable_factual_query=lambda _text: False,
            developer_color_reply=lambda _turns: "",
            developer_bilingual_reply=lambda _turns: "",
            color_reply=lambda _turns: "",
            animal_reply=lambda _turns: "",
            ensure_active_work_tree_fn=_ensure_active_work_tree,
            work_tree_seed_source="cli",
            work_tree_seed_mode="",
        )
        if str((sequence_meta or {}).get("planner_decision") or "") not in {"", "unhandled"}:
            _apply_sequence_result(sequence_reply, sequence_meta)
            continue

        fallback_entry = prepare_fallback_flow(
            text=routed_user_text,
            turns=session_turns,
            recent_tool_context=recent_tool_context,
            prefer_web_for_data_queries=prefer_web_for_data_queries,
            analyze_request_fn=lambda *_args, **_kwargs: SimpleNamespace(allow_llm=True, message=""),
            normalize_policy_reply_fn=lambda reply: reply,
            build_fallback_context_details_fn=core.build_fallback_context_details,
            uses_prior_reference_fn=core._uses_prior_reference,
            action_ledger_add_step=lambda stage, outcome, detail="", **data: _trace(stage, outcome, detail, **data),
        )
        if fallback_entry.get("handled"):
            policy_block_outcome = fallback_entry.get("outcome") if isinstance(fallback_entry.get("outcome"), dict) else {}
            apply_cli_handled_outcome(
                pending_action_ledger=pending_action_ledger,
                outcome=policy_block_outcome,
                default_planner_decision="policy_block",
                session_turns=session_turns,
                print_fn=print,
                speak_chunked_fn=lambda reply: core.speak_chunked(tts, reply),
                say_done_fn=tts.say,
                coerce_grounded=True,
            )
            continue
        retrieved_context = str(fallback_entry.get("retrieved_context") or "")

        llm_fallback_outcome = finalize_llm_fallback_reply(
            text=routed_user_text,
            raw_user_text=user_text,
            input_source=input_source,
            retrieved_context=retrieved_context,
            recent_tool_context=recent_tool_context,
            language_mix_spanish_pct=language_mix_spanish_pct,
            active_user=core.get_active_user() or "",
            ollama_chat_fn=core.ollama_chat,
            sanitize_llm_reply_fn=lambda reply, _tool_context: str(reply or "").strip(),
            mem_enabled_fn=lambda: False,
            mem_should_store_fn=lambda _text: False,
            mem_add_fn=lambda *_args, **_kwargs: None,
            strip_mem_leak_fn=lambda reply, _retrieved_context: reply,
            self_correct_reply_fn=lambda _text, reply: (reply, False, ""),
            behavior_record_event_fn=core.behavior_record_event,
            action_ledger_add_step=lambda stage, outcome, detail="", **data: _trace(stage, outcome, detail, **data),
            teach_store_example_fn=core._teach_store_example,
            truthful_limit_outcome_fn=core._truthful_limit_outcome,
            apply_claim_gate_fn=lambda reply, evidence_text="", tool_context="": (reply, False, ""),
            is_explicit_request_fn=lambda _text: True,
            apply_reply_overrides_fn=lambda reply: reply,
            ensure_reply_fn=core._ensure_reply,
        )
        apply_cli_outcome_to_ledger(
            pending_action_ledger=pending_action_ledger,
            outcome=llm_fallback_outcome,
            default_planner_decision="llm_fallback",
            update_reply_fields=True,
        )
        final = str(llm_fallback_outcome.get("reply") or "")
        emit_cli_reply_outcome(
            reply_text=final,
            planner_decision=str(llm_fallback_outcome.get("planner_decision") or "llm_fallback"),
            session_turns=session_turns,
            print_fn=print,
            speak_chunked_fn=lambda reply: core.speak_chunked(tts, reply),
            say_done_fn=tts.say,
        )

    _flush_pending_action_ledger()

