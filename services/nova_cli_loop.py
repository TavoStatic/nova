from __future__ import annotations

import json
import re
import sys
from typing import Optional

from services import nova_planner_contract
from services.nova_cli_delivery import apply_cli_handled_outcome
from services.nova_cli_delivery import apply_cli_outcome_to_ledger
from services.nova_cli_delivery import emit_cli_reply_outcome
from services.nova_fallback_flow import apply_low_confidence_block
from services.nova_fallback_flow import apply_pending_weather_followup_fallback
from services.nova_fallback_flow import prepare_fallback_flow
from services.nova_fallback_flow import finalize_llm_fallback_reply
from services.nova_turn_outcomes import apply_declarative_store_outcome
from services.nova_turn_outcomes import apply_developer_guess_outcome
from services.nova_turn_outcomes import apply_developer_location_outcome
from services.nova_turn_outcomes import apply_developer_profile_learning
from services.nova_turn_outcomes import apply_fast_smalltalk
from services.nova_turn_outcomes import apply_identity_binding_learning
from services.nova_turn_outcomes import apply_location_conversation_outcome
from services.nova_turn_outcomes import apply_location_store_outcome
from services.nova_turn_outcomes import apply_saved_location_weather_outcome
from services.nova_turn_outcomes import apply_self_profile_learning
from services.nova_reply_sequence import execute_reply_sequence
from services.nova_reply_runtime import apply_reply_runtime_effects
from services.nova_session_state import apply_reply_session_updates


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
    print("Commands: screen | camera <prompt> | web <url> | web search <query> | web research <query> | web gather <url> | weather <location-or-lat,lon> | check weather <location> | weather current location | location coords <lat,lon> | domains | policy allow <domain> | chat context | queue status | ls [folder] | read <file> | find <kw> [folder] | health | capabilities | inspect", flush=True)
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

    def _trace(stage: str, outcome: str, detail: str = "", **data) -> None:
        if not pending_action_ledger:
            return
        core.action_ledger_add_step(pending_action_ledger.get("record"), stage, outcome, detail, **data)

    def _apply_sequence_result(final: str, meta: dict) -> None:
        nonlocal recent_tool_context, recent_web_urls, conversation_state
        planner_decision = str(meta.get("planner_decision") or "deterministic")
        tool = str(meta.get("tool") or "")
        tool_args = meta.get("tool_args") if isinstance(meta.get("tool_args"), dict) else {}
        tool_result = str(meta.get("tool_result") or "")
        grounded = meta.get("grounded") if isinstance(meta.get("grounded"), bool) else None
        reply_contract = str(meta.get("reply_contract") or "")
        reply_outcome = meta.get("reply_outcome") if isinstance(meta.get("reply_outcome"), dict) else {}
        route_evidence = meta.get("route_evidence") if isinstance(meta.get("route_evidence"), dict) else {}

        if pending_action_ledger is not None:
            pending_action_ledger["planner_decision"] = planner_decision
            pending_action_ledger["tool"] = tool
            pending_action_ledger["tool_args"] = tool_args
            pending_action_ledger["tool_result"] = tool_result
            pending_action_ledger["grounded"] = grounded
            pending_action_ledger["reply_contract"] = reply_contract
            pending_action_ledger["reply_outcome"] = dict(reply_outcome)
            if route_evidence:
                pending_action_ledger["route_evidence"] = dict(route_evidence)
                pending_action_ledger["routing_decision"] = nova_planner_contract.merge_route_evidence(
                    pending_action_ledger.get("routing_decision") if isinstance(pending_action_ledger.get("routing_decision"), dict) else {},
                    {"route_evidence": route_evidence},
                )

        pending_next = meta.get("pending_action")
        if isinstance(pending_next, dict) and pending_next:
            _set_pending_action(pending_next)
        elif planner_decision == "run_tool" and tool in {"weather_current_location", "weather_location"}:
            _set_pending_action(None)

        runtime_effects = apply_reply_runtime_effects(
            planner_decision=planner_decision,
            tool=tool,
            tool_result=tool_result,
            behavior_record_event_fn=core.behavior_record_event,
            extract_urls_fn=core._extract_urls,
            detect_identity_conflict_fn=core.detect_identity_conflict,
        )
        if runtime_effects.get("identity_conflict"):
            _trace("identity_conflict", "detected")

        apply_reply_session_updates(
            session_state,
            meta={
                "planner_decision": planner_decision,
                "tool": tool,
                "tool_args": tool_args,
                "tool_result": tool_result,
                "pending_action": session_state.pending_action,
            },
            routed_text=routed_user_text,
            turns=session_turns,
            fallback_state=conversation_state,
            infer_post_reply_conversation_state=core._infer_post_reply_conversation_state,
        )
        pending_action = session_state.pending_action
        conversation_state = session_state.conversation_state
        _sync_pending_conversation_tracking()

        if runtime_effects.get("context_updated"):
            recent_tool_context = str(runtime_effects.get("recent_tool_context") or "")
            recent_web_urls = list(runtime_effects.get("recent_web_urls") or [])

        emit_cli_reply_outcome(
            reply_text=final,
            planner_decision=planner_decision,
            session_turns=session_turns,
            print_fn=print,
            speak_chunked_fn=lambda reply: core.speak_chunked(tts, reply),
            say_done_fn=tts.say,
        )

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
        if not core._supervisor_result_has_route(intent_rule):
            llm_intent = core._llm_classify_routing_intent(routed_user_text, turns=session_turns)
            if isinstance(llm_intent, dict) and core._supervisor_result_has_route(llm_intent):
                intent_rule = llm_intent
                _trace("llm_routing", "matched", intent=str(intent_rule.get("intent") or ""))
        if not core._supervisor_result_has_route(intent_rule) and core._should_clarify_unlabeled_numeric_turn(
            routed_user_text,
            pending_action=pending_action,
            current_state=conversation_state,
        ):
            final = core._ensure_reply(core._unlabeled_numeric_turn_reply(routed_user_text))
            _set_conversation_state(core._make_conversation_state("numeric_reference_clarify", value=str(routed_user_text or "").strip()))
            _sync_pending_conversation_tracking()
            if pending_action_ledger is not None:
                pending_action_ledger["planner_decision"] = "ask_clarify"
                pending_action_ledger["grounded"] = False
            _trace("numeric_clarify", "blocked")
            print(f"Nova: {final}\n", flush=True)
            session_turns.append(("assistant", final))
            core.speak_chunked(tts, final)
            continue
        if "mixed" in turn_acts:
            final = core._ensure_reply(core._mixed_info_request_clarify_reply(routed_user_text))
            if pending_action_ledger is not None:
                pending_action_ledger["planner_decision"] = "ask_clarify"
                pending_action_ledger["grounded"] = False
                pending_action_ledger["reply_contract"] = "turn.clarify_mixed_intent"
                pending_action_ledger["reply_outcome"] = {
                    "intent": "clarify_mixed_turn",
                    "kind": "mixed_info_request",
                    "reply_contract": "turn.clarify_mixed_intent",
                }
            _trace("mixed_turn_clarify", "blocked")
            print(f"Nova: {final}\n", flush=True)
            session_turns.append(("assistant", final))
            core.speak_chunked(tts, final)
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
        if handled_intent:
            weather_mode = str(intent_rule.get("weather_mode") or "").strip().lower()
            intent_name = str(intent_rule.get("intent") or "").strip().lower()
            core._emit_supervisor_intent_trace(intent_rule, user_text=routed_user_text)
            final = core._ensure_reply(intent_msg)
            if isinstance(intent_effects, dict) and "pending_action" in intent_effects:
                _set_pending_action(intent_effects.get("pending_action"))
            if isinstance(intent_effects, dict):
                pending_action_ledger["reply_contract"] = str(intent_effects.get("reply_contract") or "")
                pending_action_ledger["reply_outcome"] = dict(intent_effects.get("reply_outcome") or {}) if isinstance(intent_effects.get("reply_outcome"), dict) else {}
            if pending_action_ledger is not None and intent_name == "web_research_family":
                reply_outcome = pending_action_ledger.get("reply_outcome") if isinstance(pending_action_ledger.get("reply_outcome"), dict) else {}
                tool_name = str((reply_outcome or {}).get("tool_name") or intent_rule.get("tool_name") or "web_research").strip().lower() or "web_research"
                query = str((reply_outcome or {}).get("query") or intent_rule.get("query") or routed_user_text).strip()
                pending_action_ledger["planner_decision"] = "run_tool"
                pending_action_ledger["tool"] = tool_name
                pending_action_ledger["tool_args"] = {"args": [query]} if query else {"args": []}
                pending_action_ledger["tool_result"] = str(final or "")
                pending_action_ledger["grounded"] = bool(str(final or "").strip())
                _trace("action_planner", "run_tool", tool=tool_name)
                _trace("tool_execution", "ok", tool=tool_name, grounded=bool(str(final or "").strip()))
            elif pending_action_ledger is not None and intent_name == "weather_lookup" and weather_mode in {"current_location", "explicit_location"}:
                tool_name = "weather_current_location" if weather_mode == "current_location" else "weather_location"
                pending_action_ledger["planner_decision"] = "run_tool"
                pending_action_ledger["tool"] = tool_name
                if tool_name == "weather_location":
                    pending_action_ledger["tool_args"] = {"args": [str(intent_rule.get("location_value") or "").strip()]}
                pending_action_ledger["tool_result"] = str(final or "")
                pending_action_ledger["grounded"] = bool(str(final or "").strip())
                _trace("action_planner", "run_tool", tool=tool_name)
                _trace("tool_execution", "ok", tool=tool_name, grounded=bool(str(final or "").strip()))
            elif pending_action_ledger is not None and intent_name == "weather_lookup" and weather_mode == "clarify":
                pending_action_ledger["planner_decision"] = "ask_clarify"
                pending_action_ledger["grounded"] = False
                _trace("action_planner", "ask_clarify")
                _trace("pending_action", "awaiting_location", tool="weather")
            if isinstance(intent_state, dict):
                _set_conversation_state(intent_state)
                _sync_pending_conversation_tracking()
            _trace(
                "supervisor_intent",
                "handled",
                str(intent_rule.get("intent") or "intent"),
                rule=str(intent_rule.get("rule_name") or ""),
            )
            print(f"Nova: {final}\n", flush=True)
            session_turns.append(("assistant", final))
            core.speak_chunked(tts, final)
            continue
        warn_supervisor_bypass = not core._supervisor_result_has_route(intent_rule) and core._should_warn_supervisor_bypass(routed_user_text)

        try:
            if core._is_web_research_override_request(routed_user_text):
                _set_prefer_web_for_data_queries(True)
                _trace("session_override", "enabled", "prefer_web_for_data_queries")
                if pending_action_ledger is not None:
                    pending_action_ledger["planner_decision"] = "deterministic"
                    pending_action_ledger["grounded"] = True
                final = core._ensure_reply("Understood. I'll prefer web research for broad data queries in this session.")
                print(f"Nova: {final}\n", flush=True)
                session_turns.append(("assistant", final))
                core.speak_chunked(tts, final)
                continue
        except Exception:
            pass

        try:
            identity_learned, identity_msg = core._learn_self_identity_binding(user_text)
            identity_binding_outcome = apply_identity_binding_learning(
                identity_learned=identity_learned,
                identity_msg=identity_msg,
                ledger={},
                action_ledger_add_step=lambda _ledger, stage, outcome, detail="", **data: _trace(stage, outcome, detail, **data),
                ensure_reply=core._ensure_reply,
            )
            if identity_binding_outcome.get("handled"):
                apply_cli_handled_outcome(
                    pending_action_ledger=pending_action_ledger,
                    outcome=identity_binding_outcome,
                    default_planner_decision="deterministic",
                    session_turns=session_turns,
                    print_fn=print,
                    speak_chunked_fn=lambda reply: core.speak_chunked(tts, reply),
                    say_done_fn=tts.say,
                    coerce_grounded=True,
                )
                continue
        except Exception:
            pass

        try:
            teach_text = core.extract_name_origin_teach_text(user_text)
            if teach_text:
                _trace("name_origin", "stored", "captured deterministic name-origin teaching content")
                msg = core.remember_name_origin(teach_text)
                final = core._ensure_reply(msg)
                print(f"Nova: {final}\n", flush=True)
                session_turns.append(("assistant", final))
                core.speak_chunked(tts, final)
                continue
        except Exception:
            pass

        try:
            learned_profile, learned_profile_msg = core._learn_contextual_developer_facts(session_turns, user_text, input_source=input_source)
            developer_profile_outcome = apply_developer_profile_learning(
                learned_profile=learned_profile,
                learned_profile_msg=learned_profile_msg,
                text=user_text,
                session=session_state,
                ledger={},
                infer_profile_conversation_state=core._infer_profile_conversation_state,
                make_conversation_state=core._make_conversation_state,
                action_ledger_add_step=lambda _ledger, stage, outcome, detail="", **data: _trace(stage, outcome, detail, **data),
                ensure_reply=core._ensure_reply,
            )
            if developer_profile_outcome.get("handled"):
                _set_conversation_state(session_state.conversation_state)
                _sync_pending_conversation_tracking()
                apply_cli_handled_outcome(
                    pending_action_ledger=pending_action_ledger,
                    outcome=developer_profile_outcome,
                    default_planner_decision="deterministic",
                    session_turns=session_turns,
                    print_fn=print,
                    speak_chunked_fn=lambda reply: core.speak_chunked(tts, reply),
                    say_done_fn=tts.say,
                    coerce_grounded=True,
                )
                continue
        except Exception:
            pass

        try:
            learned_self, learned_self_msg = core._learn_contextual_self_facts(user_text, input_source=input_source)
            self_profile_outcome = apply_self_profile_learning(
                learned_self=learned_self,
                learned_self_msg=learned_self_msg,
                ledger={},
                action_ledger_add_step=lambda _ledger, stage, outcome, detail="", **data: _trace(stage, outcome, detail, **data),
                ensure_reply=core._ensure_reply,
            )
            if self_profile_outcome.get("handled"):
                apply_cli_handled_outcome(
                    pending_action_ledger=pending_action_ledger,
                    outcome=self_profile_outcome,
                    default_planner_decision="deterministic",
                    session_turns=session_turns,
                    print_fn=print,
                    speak_chunked_fn=lambda reply: core.speak_chunked(tts, reply),
                    say_done_fn=tts.say,
                    coerce_grounded=True,
                )
                continue
        except Exception:
            pass

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
            allowed_actions={"name_origin_store", "self_location", "location_recall", "location_name", "weather_current_location", "apply_correction", "retrieval_followup", "identity_history_family", "open_probe_family", "session_fact_recall", "last_question_recall", "rules_list", "developer_identity_followup", "identity_profile_followup", "developer_location"},
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
            try:
                final = core._apply_reply_overrides(rule_msg)
            except Exception:
                final = rule_msg
            final = core._ensure_reply(final)
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

        fulfillment_result = core._fulfillment_flow_service().maybe_run_fulfillment_flow(
            routed_user_text,
            session_state,
            session_turns,
            pending_action=pending_action,
        )
        if isinstance(fulfillment_result, dict):
            final = core._ensure_reply(str(fulfillment_result.get("reply") or ""))
            if final:
                if pending_action_ledger is not None:
                    pending_action_ledger["planner_decision"] = str(fulfillment_result.get("planner_decision") or "fulfillment")
                    pending_action_ledger["grounded"] = bool(fulfillment_result.get("grounded", True))
                _trace(
                    "fulfillment_flow",
                    "handled",
                    str(fulfillment_result.get("planner_decision") or "fulfillment"),
                )
                print(f"Nova: {final}\n", flush=True)
                session_turns.append(("assistant", final))
                core.speak_chunked(tts, final)
                continue

        try:
            handled_followup, followup_msg, next_state = core._consume_conversation_followup(
                conversation_state,
                routed_user_text,
                input_source=input_source,
                turns=session_turns,
            )
            if handled_followup:
                _trace("conversation_followup", "used", active_subject=core._conversation_active_subject(conversation_state))
                _set_conversation_state(next_state)
                session_state.mark_continuation_used()
                if pending_action_ledger is not None:
                    pending_action_ledger["planner_decision"] = "conversation_followup"
                    pending_action_ledger["grounded"] = True
                    pending_action_ledger["continuation_used"] = True
                _sync_pending_conversation_tracking()
                final = core._ensure_reply(followup_msg)
                runtime_effects = apply_reply_runtime_effects(
                    planner_decision="conversation_followup",
                    tool="",
                    tool_result="",
                    final_reply=final,
                    active_state=conversation_state,
                    behavior_record_event_fn=core.behavior_record_event,
                    extract_urls_fn=core._extract_urls,
                )
                if runtime_effects.get("context_updated"):
                    recent_tool_context = str(runtime_effects.get("recent_tool_context") or "")
                    recent_web_urls = list(runtime_effects.get("recent_web_urls") or [])
                print(f"Nova: {final}\n", flush=True)
                session_turns.append(("assistant", final))
                core.speak_chunked(tts, final)
                continue
            _set_conversation_state(next_state)
            _sync_pending_conversation_tracking()
        except Exception:
            pass

        try:
            msg = core._quick_smalltalk_reply(routed_user_text, active_user=core.get_active_user() or "")
            smalltalk_outcome = apply_fast_smalltalk(
                quick_reply=(core._apply_reply_overrides(msg) if msg else ""),
                ledger={},
                action_ledger_add_step=lambda _ledger, stage, outcome, detail="", **data: _trace(stage, outcome, detail, **data),
            )
            if smalltalk_outcome.get("handled"):
                apply_cli_handled_outcome(
                    pending_action_ledger=pending_action_ledger,
                    outcome=smalltalk_outcome,
                    default_planner_decision="deterministic",
                    session_turns=session_turns,
                    print_fn=print,
                    speak_chunked_fn=lambda reply: core.speak_chunked(tts, reply),
                    say_done_fn=tts.say,
                    coerce_grounded=True,
                )
                continue
        except Exception:
            pass

        try:
            low_q = (routed_user_text or "").strip().lower()
            if low_q.startswith("what else do you remember") or low_q.startswith("what do you remember") or "what else do you remember" in low_q:
                stats = core.mem_stats()
                brief = "I remember a few things about our conversations and some saved facts."
                if stats and "No memory" not in stats:
                    brief += " " + (stats.splitlines()[0] if stats else "")
                brief += " You can ask me to audit specific items, e.g. 'mem audit location'."
                final = core._ensure_reply(brief)
                session_turns.append(("assistant", final))
                print(f"Nova: {final}\n", flush=True)
                core.speak_chunked(tts, final)
                continue
        except Exception:
            pass

        try:
            status_msg = core._retrieval_status_reply(routed_user_text)
            if status_msg:
                _set_conversation_state(core._make_conversation_state("awaiting_retrieval_target"))
                _sync_pending_conversation_tracking()
                final = core._ensure_reply(status_msg)
                session_turns.append(("assistant", final))
                print(f"Nova: {final}\n", flush=True)
                core.speak_chunked(tts, final)
                continue
        except Exception:
            pass

        try:
            m = re.match(r"^remember\s+(.+)$", (routed_user_text or "").strip(), flags=re.I)
            if m:
                subj = m.group(1).strip().strip('.!?,')
                if subj:
                    q = f"What would you like me to remember about {subj}?"
                    final = core._ensure_reply(q)
                    session_turns.append(("assistant", final))
                    print(f"Nova: {final}\n", flush=True)
                    core.speak_chunked(tts, final)
                    continue
        except Exception:
            pass

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

        try:
            low_q = (routed_user_text or "").strip().lower()

            handled_location, msg, next_location_state, _location_intent = core._handle_location_conversation_turn(
                conversation_state,
                routed_user_text,
                turns=session_turns,
            )
            if handled_location:
                try:
                    final = core._apply_reply_overrides(msg)
                except Exception:
                    final = msg
                final = core._ensure_reply(final)
                if isinstance(next_location_state, dict):
                    _set_conversation_state(next_location_state)
                    _sync_pending_conversation_tracking()
                print(f"Nova: {final}\n", flush=True)
                session_turns.append(("assistant", final))
                core.speak_chunked(tts, final)
                continue

            expand_triggers = ["what else", "other information", "anything else", "more about", "what other", "anything more"]
            if "location" in low_q and any(t in low_q for t in expand_triggers):
                try:
                    audit_out = core.mem_audit("location")
                    j = json.loads(audit_out) if audit_out else {}
                    results = j.get("results") if isinstance(j, dict) else []
                    previews = []
                    seen = set()
                    for r in results:
                        p = (r.get("preview") or "").strip()
                        n = re.sub(r"\W+", " ", p.lower()).strip()
                        if not p or n in seen:
                            continue
                        seen.add(n)
                        previews.append(p)

                    if not previews:
                        msg = "I don't have a stored location yet. You can tell me: 'My location is ...'"
                    elif len(previews) == 1:
                        msg = f"I only have one stored location fact right now: {core._normalize_location_preview(previews[0])}"
                    else:
                        summary = "; ".join(core._normalize_location_preview(p) for p in previews[:3])
                        msg = f"I have multiple stored location facts: {summary}"
                except Exception:
                    msg = "I don't have a stored location yet. You can tell me: 'My location is ...'"

                try:
                    final = core._apply_reply_overrides(msg)
                except Exception:
                    final = msg
                final = core._ensure_reply(final)
                _set_conversation_state(core._make_conversation_state("location_recall"))
                _sync_pending_conversation_tracking()
                print(f"Nova: {final}\n", flush=True)
                session_turns.append(("assistant", final))
                core.speak_chunked(tts, final)
                continue

            loc_triggers = [
                "what is your location",
                "where are you located",
                "where are you",
                "what is your location nova",
            ]
            if any(low_q.startswith(t) for t in loc_triggers):
                try:
                    preview = core.get_saved_location_text()
                    if preview:
                        msg = f"My location is {preview}."
                    else:
                        msg = "I don't have a stored location yet. You can tell me: 'My location is ...'"
                except Exception:
                    msg = "I don't have a stored location yet. You can tell me: 'My location is ...'"

                try:
                    final = core._apply_reply_overrides(msg)
                except Exception:
                    final = msg
                final = core._ensure_reply(final)
                print(f"Nova: {final}\n", flush=True)
                session_turns.append(("assistant", final))
                core.speak_chunked(tts, final)
                continue
        except Exception:
            pass

        try:
            developer_guess, next_state = core._developer_work_guess_turn(routed_user_text)
            if developer_guess:
                final = core._ensure_reply(developer_guess)
                _set_conversation_state(next_state)
                _sync_pending_conversation_tracking()
                print(f"Nova: {final}\n", flush=True)
                session_turns.append(("assistant", final))
                core.speak_chunked(tts, final)
                continue
        except Exception:
            pass

        try:
            developer_location_reply, next_state = core._developer_location_turn(
                routed_user_text,
                state=conversation_state,
                turns=session_turns,
            )
            developer_location_outcome = apply_developer_location_outcome(
                reply_text=developer_location_reply,
                next_state=next_state,
                session=session_state,
                ledger={},
                action_ledger_add_step=lambda _ledger, stage, outcome, detail="", **data: _trace(stage, outcome, detail, **data),
            )
            if developer_location_outcome.get("handled"):
                _set_conversation_state(session_state.conversation_state)
                _sync_pending_conversation_tracking()
                apply_cli_handled_outcome(
                    pending_action_ledger=pending_action_ledger,
                    outcome=developer_location_outcome,
                    default_planner_decision="deterministic",
                    session_turns=session_turns,
                    print_fn=print,
                    speak_chunked_fn=lambda reply: core.speak_chunked(tts, reply),
                    say_done_fn=tts.say,
                    coerce_grounded=True,
                )
                continue
        except Exception:
            pass

        try:
            location_ack = core._store_location_fact_reply(
                user_text,
                input_source=input_source,
                pending_action=pending_action,
            )
            location_store_outcome = apply_location_store_outcome(
                location_ack=location_ack,
                conversation_state=conversation_state,
                session=session_state,
                ledger={},
                make_conversation_state=core._make_conversation_state,
                action_ledger_add_step=lambda _ledger, stage, outcome, detail="", **data: _trace(stage, outcome, detail, **data),
            )
            if location_store_outcome.get("handled"):
                _set_conversation_state(session_state.conversation_state)
                _sync_pending_conversation_tracking()
                apply_cli_handled_outcome(
                    pending_action_ledger=pending_action_ledger,
                    outcome=location_store_outcome,
                    default_planner_decision="deterministic",
                    session_turns=session_turns,
                    print_fn=print,
                    speak_chunked_fn=lambda reply: core.speak_chunked(tts, reply),
                    say_done_fn=tts.say,
                    coerce_grounded=True,
                )
                continue
        except Exception:
            pass

        try:
            saved_location_weather_outcome = apply_saved_location_weather_outcome(
                conversation_state=conversation_state,
                routed_text=routed_user_text,
                weather_for_saved_location=core._weather_for_saved_location,
                is_saved_location_weather_query=core._is_saved_location_weather_query,
                session=session_state,
                ledger={},
                make_conversation_state=core._make_conversation_state,
                action_ledger_add_step=lambda _ledger, stage, outcome, detail="", **data: _trace(stage, outcome, detail, **data),
                ensure_reply=core._ensure_reply,
            )
            if saved_location_weather_outcome.get("handled"):
                _set_conversation_state(session_state.conversation_state)
                _sync_pending_conversation_tracking()
                apply_cli_handled_outcome(
                    pending_action_ledger=pending_action_ledger,
                    outcome=saved_location_weather_outcome,
                    default_planner_decision="deterministic",
                    session_turns=session_turns,
                    print_fn=print,
                    speak_chunked_fn=lambda reply: core.speak_chunked(tts, reply),
                    say_done_fn=tts.say,
                    coerce_grounded=True,
                )
                continue
        except Exception:
            pass

        try:
            declarative_outcome = core._store_declarative_fact_outcome(user_text, input_source=input_source)
            declarative_store_outcome = apply_declarative_store_outcome(
                declarative_outcome=declarative_outcome,
                ledger={},
                action_ledger_add_step=lambda _ledger, stage, outcome, detail="", **data: _trace(stage, outcome, detail, **data),
                render_reply=core.render_reply,
            )
            if declarative_store_outcome.get("handled"):
                apply_cli_handled_outcome(
                    pending_action_ledger=pending_action_ledger,
                    outcome=declarative_store_outcome,
                    default_planner_decision="deterministic",
                    session_turns=session_turns,
                    print_fn=print,
                    speak_chunked_fn=lambda reply: core.speak_chunked(tts, reply),
                    say_done_fn=tts.say,
                    update_reply_fields=True,
                    coerce_grounded=True,
                )
                continue
        except Exception:
            pass

        if warn_supervisor_bypass:
            safe_reply, safe_kind = core._open_probe_reply(routed_user_text, turns=session_turns)
            safe_outcome = {
                "intent": "open_probe_family",
                "kind": safe_kind,
                "reply_contract": f"open_probe.{safe_kind}",
                "reply_text": safe_reply,
                "state_delta": {},
            }
            if pending_action_ledger is not None:
                pending_action_ledger["planner_decision"] = "deterministic"
                pending_action_ledger["grounded"] = False
                pending_action_ledger["reply_contract"] = str(safe_outcome.get("reply_contract") or "")
                pending_action_ledger["reply_outcome"] = dict(safe_outcome)
                routing_decision = pending_action_ledger.get("routing_decision")
                if isinstance(routing_decision, dict):
                    routing_decision["final_owner"] = "supervisor_handle"
            _trace("open_probe", "matched", safe_kind)
            final = core._ensure_reply(safe_reply)
            print(f"Nova: {final}\n", flush=True)
            session_turns.append(("assistant", final))
            core.speak_chunked(tts, final)
            continue

        def _normalize_sequence_reply(reply: str) -> str:
            try:
                return core._ensure_reply(core._apply_reply_overrides(reply))
            except Exception:
                return core._ensure_reply(reply)

        def _developer_color_sequence_reply(turns: list[tuple[str, str]]) -> str:
            prefs = core._extract_developer_color_preferences(turns) or core._extract_developer_color_preferences_from_memory()
            if not prefs:
                return "I don't have Gus's color preferences yet."
            if len(prefs) == 1:
                return f"From what you've told me, Gus likes {prefs[0]}."
            return "From what you've told me, Gus likes these colors: " + ", ".join(prefs[:-1]) + f", and {prefs[-1]}."

        def _developer_bilingual_sequence_reply(turns: list[tuple[str, str]]) -> str:
            known = core._developer_is_bilingual(turns)
            if known is None:
                known = core._developer_is_bilingual_from_memory()
            if known is True:
                return "Yes. From what you've told me, Gus is bilingual in English and Spanish."
            if known is False:
                return "From what I have, Gus is not bilingual."
            return "I don't have confirmed language details for Gus yet."

        def _color_sequence_reply(turns: list[tuple[str, str]]) -> str:
            prefs = core._extract_color_preferences(turns) or core._extract_color_preferences_from_memory()
            if not prefs:
                return "You haven't told me a color preference in this current chat yet."
            if len(prefs) == 1:
                return f"You told me you like the color {prefs[0]}."
            return "You told me you like these colors: " + ", ".join(prefs[:-1]) + f", and {prefs[-1]}."

        def _animal_sequence_reply(turns: list[tuple[str, str]]) -> str:
            animals = core._extract_animal_preferences(turns) or core._extract_animal_preferences_from_memory()
            if not animals:
                return "You haven't told me animal preferences yet in this chat, and I can't find them in saved memory."
            if len(animals) == 1:
                return f"You told me you like {animals[0]}."
            return "You told me you like: " + ", ".join(animals[:-1]) + f", and {animals[-1]}."

        sequence_reply, sequence_meta = execute_reply_sequence(
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
            is_developer_profile_request=core._is_developer_profile_request,
            developer_profile_reply=core._developer_profile_reply,
            is_location_request=core._is_location_request,
            location_reply=core._location_reply,
            is_web_preferred_data_query=core._is_web_preferred_data_query,
            is_session_recap_request=core._is_session_recap_request,
            session_recap_reply=core._session_recap_reply,
            is_assistant_name_query=core._is_assistant_name_query,
            assistant_name_reply=core._assistant_name_reply,
            is_developer_full_name_query=core._is_developer_full_name_query,
            developer_full_name_reply=core._developer_full_name_reply,
            is_name_origin_question=core._is_name_origin_question,
            is_peims_attendance_rules_query=getattr(core, "_is_peims_attendance_rules_query", lambda _text: False),
            peims_attendance_rules_reply=getattr(core, "_peims_attendance_rules_reply", lambda: ""),
            is_conversational_clarification=getattr(core, "_is_conversational_clarification", lambda _text: False),
            clarification_reply=getattr(core, "_clarification_reply", lambda _turns: "Can you clarify?"),
            is_deep_search_followup_request=core._is_deep_search_followup_request,
            infer_research_query_from_turns=core._infer_research_query_from_turns,
            build_grounded_answer=lambda query, max_sources=2: core._build_grounded_answer(query, max_sources=max_sources),
            build_local_topic_digest_answer=core._build_local_topic_digest_answer,
            is_groundable_factual_query=getattr(core, "_is_groundable_factual_query", lambda _text: False),
            developer_color_reply=_developer_color_sequence_reply,
            developer_bilingual_reply=_developer_bilingual_sequence_reply,
            color_reply=_color_sequence_reply,
            animal_reply=_animal_sequence_reply,
            stop_before_llm_fallback=True,
        )
        if str((sequence_meta or {}).get("planner_decision") or "") not in {"", "unhandled"}:
            _apply_sequence_result(sequence_reply, sequence_meta)
            continue

        if core._is_color_animal_match_question(routed_user_text):
            colors = core._extract_color_preferences(session_turns)
            if not colors:
                colors = core._extract_color_preferences_from_memory()
            animals = core._extract_animal_preferences(session_turns)
            if not animals:
                animals = core._extract_animal_preferences_from_memory()

            if not colors:
                msg = "I can't pick a best color yet because I don't have your color preferences."
            elif not animals:
                msg = "I can't pick a best color for animals yet because I don't have your animal preferences."
            else:
                best = core._pick_color_for_animals(colors, animals)
                msg = f"Direct answer: {best} matches best with the animals you like ({', '.join(animals)})."
                if len(colors) > 1:
                    msg += f" I considered your options: {', '.join(colors)}."

            print(f"Nova: {msg}\n", flush=True)
            session_turns.append(("assistant", msg))
            core.speak_chunked(tts, msg)
            continue

        last_assistant_text = core._last_assistant_turn_text(session_turns[:-1])
        weather_followup_fallback = apply_pending_weather_followup_fallback(
            text=routed_user_text,
            pending_action=pending_action,
            last_assistant_text=last_assistant_text,
            looks_like_affirmative_followup_fn=core._looks_like_affirmative_followup,
            looks_like_shared_location_reference_fn=core._looks_like_shared_location_reference,
            assistant_offered_weather_lookup_fn=core._assistant_offered_weather_lookup,
            ensure_reply=core._ensure_reply,
        )
        if weather_followup_fallback.get("handled"):
            apply_cli_handled_outcome(
                pending_action_ledger=pending_action_ledger,
                outcome=weather_followup_fallback,
                default_planner_decision="llm_fallback",
                session_turns=session_turns,
                print_fn=print,
                speak_chunked_fn=lambda reply: core.speak_chunked(tts, reply),
                say_done_fn=tts.say,
                coerce_grounded=True,
                clear_pending_action_fn=lambda: _set_pending_action(None),
                sync_pending_conversation_tracking_fn=_sync_pending_conversation_tracking,
            )
            continue

        fallback_entry = prepare_fallback_flow(
            text=routed_user_text,
            turns=session_turns,
            recent_tool_context=recent_tool_context,
            prefer_web_for_data_queries=prefer_web_for_data_queries,
            analyze_request_fn=core.analyze_request,
            normalize_policy_reply_fn=lambda reply: core._apply_reply_overrides(reply),
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

        low_confidence_outcome = apply_low_confidence_block(
            text=routed_user_text,
            retrieved_context=retrieved_context,
            recent_tool_context=recent_tool_context,
            should_block_low_confidence_fn=core.should_block_low_confidence,
            behavior_record_event_fn=core.behavior_record_event,
            truthful_limit_outcome_fn=core._truthful_limit_outcome,
            truthful_limit_reply_fn=core._truthful_limit_reply,
            action_ledger_add_step=lambda stage, outcome, detail="", **data: _trace(stage, outcome, detail, **data),
            ensure_reply=core._ensure_reply,
        )
        if low_confidence_outcome.get("handled"):
            apply_cli_handled_outcome(
                pending_action_ledger=pending_action_ledger,
                outcome=low_confidence_outcome,
                default_planner_decision="blocked_low_confidence",
                session_turns=session_turns,
                print_fn=print,
                speak_chunked_fn=lambda reply: core.speak_chunked(tts, reply),
                say_done_fn=tts.say,
                update_reply_fields=True,
                coerce_grounded=True,
            )
            continue

        llm_fallback_outcome = finalize_llm_fallback_reply(
            text=routed_user_text,
            raw_user_text=user_text,
            input_source=input_source,
            retrieved_context=retrieved_context,
            recent_tool_context=recent_tool_context,
            language_mix_spanish_pct=language_mix_spanish_pct,
            active_user=core.get_active_user() or "",
            ollama_chat_fn=core.ollama_chat,
            sanitize_llm_reply_fn=lambda reply, tool_context: core.sanitize_llm_reply(reply, tool_context=tool_context),
            mem_enabled_fn=core.mem_enabled,
            mem_should_store_fn=core.mem_should_store,
            mem_add_fn=core.mem_add,
            strip_mem_leak_fn=core._strip_mem_leak,
            self_correct_reply_fn=core._self_correct_reply,
            behavior_record_event_fn=core.behavior_record_event,
            action_ledger_add_step=lambda stage, outcome, detail="", **data: _trace(stage, outcome, detail, **data),
            teach_store_example_fn=core._teach_store_example,
            truthful_limit_outcome_fn=core._truthful_limit_outcome,
            apply_claim_gate_fn=lambda reply, evidence_text="", tool_context="": core._apply_claim_gate(reply, evidence_text=evidence_text, tool_context=tool_context),
            is_explicit_request_fn=core._is_explicit_request,
            apply_reply_overrides_fn=core._apply_reply_overrides,
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