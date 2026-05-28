from __future__ import annotations

import re
import sys
from typing import Optional

from services import nova_planner_contract
from services.nova_cli_delivery import apply_cli_outcome_to_ledger
from services.nova_cli_delivery import emit_cli_reply_outcome
from services.nova_cli_sequence import execute_cli_sequence as service_execute_cli_sequence
from services.nova_cli_sequence import apply_sequence_result as service_apply_sequence_result
from services.nova_cli_sequence import normalize_sequence_reply as service_normalize_sequence_reply
from services.nova_fallback_flow import prepare_fallback_flow
from services.nova_fallback_flow import finalize_llm_fallback_reply
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

    def _build_fallback_context_details(text: str, turns: list[tuple[str, str]]) -> dict:
        build_fn = core.build_fallback_context_details
        try:
            return build_fn(
                text,
                turns,
                conversation_state=conversation_state,
                pending_action=pending_action,
            )
        except TypeError:
            return build_fn(text, turns)

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
            session_turns=session_turns,
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
            "planner_decision": "deterministic",
            "tool": "",
            "tool_args": {},
            "tool_result": "",
            "grounded": None,
            "active_subject": session_state.active_subject(),
            "continuation_used": False,
        }

        routed_user_text = user_text
        turn_acts: list[str] = []

        def _normalize_sequence_reply(reply: str) -> str:
            return service_normalize_sequence_reply(
                reply,
                ensure_reply_fn=core._ensure_reply,
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
            build_fallback_context_details_fn=_build_fallback_context_details,
            action_ledger_add_step=lambda stage, outcome, detail="", **data: _trace(stage, outcome, detail, **data),
            pending_action=pending_action,
            semantic_tool_observation=sequence_meta.get("semantic_tool_observation") if isinstance(sequence_meta, dict) else {},
            planner_decision=str((sequence_meta or {}).get("planner_decision") or ""),
            tool=str((sequence_meta or {}).get("tool") or ""),
            tool_result=str((sequence_meta or {}).get("tool_result") or ""),
        )
        retrieved_context = str(fallback_entry.get("retrieved_context") or "")
        intent_evidence_packet = fallback_entry.get("intent_evidence_packet") if isinstance(fallback_entry.get("intent_evidence_packet"), dict) else {}

        llm_fallback_outcome = finalize_llm_fallback_reply(
            text=routed_user_text,
            raw_user_text=user_text,
            input_source=input_source,
            retrieved_context=retrieved_context,
            language_mix_spanish_pct=language_mix_spanish_pct,
            ollama_chat_fn=core.ollama_chat,
            mem_enabled_fn=lambda: False,
            mem_should_store_fn=lambda _text: False,
            mem_add_fn=lambda *_args, **_kwargs: None,
            strip_mem_leak_fn=lambda reply, _retrieved_context: reply,
            behavior_record_event_fn=core.behavior_record_event,
            action_ledger_add_step=lambda stage, outcome, detail="", **data: _trace(stage, outcome, detail, **data),
            ensure_reply_fn=core._ensure_reply,
            intent_evidence_packet=intent_evidence_packet,
            fallback_context=fallback_entry.get("fallback_context") if isinstance(fallback_entry.get("fallback_context"), dict) else {},
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

