import unittest

from services.nova_fallback_flow import build_fallback_context
from services.nova_fallback_flow import finalize_llm_fallback_reply
from services.nova_fallback_flow import prepare_fallback_flow
from services.nova_fallback_flow import _shape_conversation_scoped_reply
from services.nova_self_evidence_reply import turn_asks_nova_self
from services.nova_turn_intent_trace import build_turn_intent_evidence_packet
from services.nova_turn_intent_trace import render_turn_intent_evidence_packet


class TestNovaFallbackFlow(unittest.TestCase):
    def test_build_fallback_context_uses_context_builder_only(self):
        calls = []
        out = build_fallback_context(
            text="what about the first one?",
            turns=[("user", "research student_data")],
            build_fallback_context_details_fn=lambda text, turns: {
                "context": "BASE",
                "learning_context": "BASE",
                "chat_context": "CHAT",
                "session_fact_sheet": "FACTS",
                "memory_used": True,
                "operational_identity_used": True,
                "knowledge_used": False,
                "memory_chars": 4,
                "operational_identity_chars": 20,
                "knowledge_chars": 0,
            },
            action_ledger_add_step=lambda *args, **kwargs: calls.append((args, kwargs)),
        )

        self.assertIn("NOVA INTERNAL EVIDENCE SUMMARY", out.get("retrieved_context"))
        self.assertNotIn("available_evidence", out.get("retrieved_context"))
        self.assertIn("BASE", out.get("retrieved_context"))
        self.assertEqual((out.get("intent_evidence_packet") or {}).get("trace_authority"), "hypothesis_only")
        self.assertTrue(any(args[0] == "memory_context" for args, _kwargs in calls))
        self.assertTrue(any(args[0] == "turn_intent_evidence" for args, _kwargs in calls))
        self.assertFalse(any(args[0] == "recent_tool_context" for args, _kwargs in calls))

    def test_prepare_fallback_flow_builds_retrieved_context_without_policy_gate(self):
        steps = []
        out = prepare_fallback_flow(
            text="tell me why that answer drifted",
            turns=[("user", "tell me why that answer drifted")],
            build_fallback_context_details_fn=lambda text, turns: {
                "context": "CHAT CONTEXT",
                "learning_context": "",
                "chat_context": "CHAT",
                "session_fact_sheet": "",
                "memory_used": False,
                "operational_identity_used": False,
                "knowledge_used": False,
                "memory_chars": 0,
                "operational_identity_chars": 0,
                "knowledge_chars": 0,
            },
            action_ledger_add_step=lambda *args, **kwargs: steps.append((args, kwargs)),
        )

        self.assertFalse(out.get("handled"))
        self.assertIn("NOVA INTERNAL EVIDENCE SUMMARY", out.get("retrieved_context"))
        self.assertNotIn("current_user_turn", out.get("retrieved_context"))
        self.assertIn("CHAT CONTEXT", out.get("retrieved_context"))
        self.assertFalse(any(args[0] == "policy_gate" for args, _kwargs in steps))

    def test_fallback_context_summary_does_not_expose_internal_packet_labels(self):
        out = build_fallback_context(
            text="status check",
            turns=[("user", "status check")],
            build_fallback_context_details_fn=lambda text, turns: {
                "context": "Identity fact: assistant_name=Nova",
                "learning_context": "Identity fact: assistant_name=Nova",
                "chat_context": "",
                "session_fact_sheet": "",
                "identity_used": True,
                "operational_identity_used": True,
                "identity_chars": 30,
                "operational_identity_chars": 45,
            },
            action_ledger_add_step=lambda *args, **kwargs: None,
        )

        retrieved = str(out.get("retrieved_context") or "")
        self.assertIn("NOVA INTERNAL EVIDENCE SUMMARY", retrieved)
        self.assertIn("Confirmed Nova identity evidence is available.", retrieved)
        self.assertIn("Operational Nova self evidence is available.", retrieved)
        self.assertNotIn("confirmed_identity_context", retrieved)
        self.assertNotIn("operational_self_context", retrieved)
        self.assertNotIn("intent_evidence_packet", retrieved)
        self.assertIn("assistant_name=Nova", retrieved)

    def test_finalize_llm_fallback_reply_returns_model_reply_without_content_hooks(self):
        events = []
        memories = []
        out = finalize_llm_fallback_reply(
            text="tell me what you think happened",
            raw_user_text="tell me what you think happened",
            input_source="typed",
            retrieved_context="CURRENT CHAT CONTEXT",
            language_mix_spanish_pct=0,
            ollama_chat_fn=lambda text, retrieved_context="", language_mix_spanish_pct=0: f"model:{text}:{bool(retrieved_context)}",
            mem_enabled_fn=lambda: True,
            mem_should_store_fn=lambda text: True,
            mem_add_fn=lambda kind, source, text: memories.append((kind, source, text)),
            strip_mem_leak_fn=lambda reply, retrieved_context: reply,
            behavior_record_event_fn=lambda event: events.append(event),
            action_ledger_add_step=lambda *args, **kwargs: None,
            ensure_reply_fn=lambda text: text,
            intent_evidence_packet={"trace_authority": "hypothesis_only"},
        )

        self.assertTrue(out.get("handled"))
        self.assertEqual(out.get("planner_decision"), "llm_fallback")
        self.assertEqual(out.get("reply"), "model:tell me what you think happened:True")
        self.assertEqual(out.get("reply_contract"), "")
        self.assertEqual((out.get("reply_outcome") or {}).get("kind"), "llm_fallback")
        self.assertEqual(
            ((out.get("reply_outcome") or {}).get("intent_evidence_packet") or {}).get("trace_authority"),
            "hypothesis_only",
        )
        self.assertEqual(memories, [])
        self.assertEqual(events, ["llm_fallback"])

    def test_finalize_llm_fallback_reply_supports_preprocess_only(self):
        out = finalize_llm_fallback_reply(
            text="say it plainly",
            raw_user_text="say it plainly",
            input_source="typed",
            retrieved_context="",
            language_mix_spanish_pct=0,
            ollama_chat_fn=lambda text, retrieved_context="", language_mix_spanish_pct=0: "raw reply",
            mem_enabled_fn=lambda: False,
            mem_should_store_fn=lambda text: False,
            mem_add_fn=lambda kind, source, text: None,
            strip_mem_leak_fn=lambda reply, retrieved_context: reply,
            behavior_record_event_fn=lambda event: None,
            action_ledger_add_step=lambda *args, **kwargs: None,
            preprocess_reply_fn=lambda reply: f"pre:{reply}",
            ensure_reply_fn=lambda text: text,
        )

        self.assertEqual(out.get("reply"), "pre:raw reply")

    def test_finalize_conversation_scoped_fallback_drops_trailing_question_shape(self):
        packet = build_turn_intent_evidence_packet(
            text="continue the exchange",
            turns=[("user", "continue the exchange")],
            fallback_context={"chat_context": "recent turns"},
            semantic_tool_observation={
                "status": "none",
                "intent": {
                    "tool": "none",
                    "confidence": 0.91,
                    "evidence_need": "conversation",
                    "answer_target": "current_conversation",
                },
            },
        )

        out = finalize_llm_fallback_reply(
            text="continue the exchange",
            raw_user_text="continue the exchange",
            input_source="typed",
            retrieved_context="",
            language_mix_spanish_pct=0,
            ollama_chat_fn=lambda *args, **kwargs: "Direct conversation reply. What should happen next?",
            mem_enabled_fn=lambda: False,
            mem_should_store_fn=lambda text: False,
            mem_add_fn=lambda kind, source, text: None,
            strip_mem_leak_fn=lambda reply, retrieved_context: reply,
            behavior_record_event_fn=lambda event: None,
            action_ledger_add_step=lambda *args, **kwargs: None,
            ensure_reply_fn=lambda text: text,
            intent_evidence_packet=packet,
            fallback_context={},
        )

        self.assertEqual(out.get("planner_decision"), "llm_fallback")
        self.assertEqual(out.get("reply"), "Direct conversation reply.")

    def test_finalize_conversation_scoped_fallback_keeps_direct_paragraph_only(self):
        packet = build_turn_intent_evidence_packet(
            text="continue the exchange",
            turns=[("user", "continue the exchange")],
            fallback_context={"chat_context": "recent turns"},
            semantic_tool_observation={
                "status": "none",
                "intent": {
                    "tool": "none",
                    "confidence": 0.91,
                    "evidence_need": "conversation",
                    "answer_target": "current_conversation",
                },
            },
        )

        out = finalize_llm_fallback_reply(
            text="continue the exchange",
            raw_user_text="continue the exchange",
            input_source="typed",
            retrieved_context="",
            language_mix_spanish_pct=0,
            ollama_chat_fn=lambda *args, **kwargs: "Direct conversation reply.\n\nExtra steering paragraph.",
            mem_enabled_fn=lambda: False,
            mem_should_store_fn=lambda text: False,
            mem_add_fn=lambda kind, source, text: None,
            strip_mem_leak_fn=lambda reply, retrieved_context: reply,
            behavior_record_event_fn=lambda event: None,
            action_ledger_add_step=lambda *args, **kwargs: None,
            ensure_reply_fn=lambda text: text,
            intent_evidence_packet=packet,
            fallback_context={},
        )

        self.assertEqual(out.get("reply"), "Direct conversation reply.")

    def test_finalize_conversation_scoped_fallback_uses_conversation_reply_form_before_generation(self):
        packet = build_turn_intent_evidence_packet(
            text="continue the exchange",
            turns=[("assistant", "prior reply"), ("user", "continue the exchange")],
            fallback_context={
                "context": "RAW OPERATIONAL SELF CONTEXT",
                "chat_context": "CHAT ONLY",
                "operational_identity_used": True,
                "operational_identity_chars": 28,
            },
            semantic_tool_observation={
                "status": "none",
                "intent": {
                    "tool": "none",
                    "confidence": 0.91,
                    "evidence_need": "conversation",
                    "answer_target": "current_conversation",
                },
            },
        )
        captured = {}

        def _chat(text, retrieved_context="", language_mix_spanish_pct=0, reply_form=""):
            captured["text"] = text
            captured["retrieved_context"] = retrieved_context
            captured["reply_form"] = reply_form
            captured["language_mix_spanish_pct"] = language_mix_spanish_pct
            return "Direct conversation reply. Extra explanation follows."

        out = finalize_llm_fallback_reply(
            text="continue the exchange",
            raw_user_text="continue the exchange",
            input_source="typed",
            retrieved_context="NOVA INTERNAL EVIDENCE SUMMARY\nRAW OPERATIONAL SELF CONTEXT",
            language_mix_spanish_pct=7,
            ollama_chat_fn=_chat,
            mem_enabled_fn=lambda: False,
            mem_should_store_fn=lambda text: False,
            mem_add_fn=lambda kind, source, text: None,
            strip_mem_leak_fn=lambda reply, retrieved_context: reply,
            behavior_record_event_fn=lambda event: None,
            action_ledger_add_step=lambda *args, **kwargs: None,
            ensure_reply_fn=lambda text: text,
            intent_evidence_packet=packet,
            fallback_context={
                "context": "RAW OPERATIONAL SELF CONTEXT",
                "chat_context": "CHAT ONLY",
                "operational_identity_used": True,
                "operational_identity_chars": 28,
            },
        )

        self.assertEqual(out.get("reply"), "Direct conversation reply.")
        self.assertEqual(captured.get("reply_form"), "conversation_turn")
        self.assertEqual(captured.get("language_mix_spanish_pct"), 7)
        self.assertIn("reply_form: conversation_turn", captured.get("retrieved_context"))
        self.assertIn("RECENT CHAT CONTEXT:\nCHAT ONLY", captured.get("retrieved_context"))
        self.assertNotIn("RAW OPERATIONAL SELF CONTEXT", captured.get("retrieved_context"))

    def test_finalize_conversation_scoped_fallback_keeps_stale_session_evidence_out(self):
        packet = build_turn_intent_evidence_packet(
            text="what do you mean?",
            turns=[("assistant", "Assistant returned a tool result. The result is available as last tool evidence."), ("user", "what do you mean?")],
            fallback_context={
                "chat_context": "Assistant returned a tool result.",
                "state_context": "ACTIVE SESSION STATE: last_tool_evidence / self_status\nLast tool evidence:\nNova Self Status - stable",
            },
            semantic_tool_observation={
                "status": "none",
                "intent": {
                    "tool": "none",
                    "confidence": 0.0,
                    "evidence_need": "conversation",
                    "answer_target": "current_conversation",
                },
            },
        )
        captured = {}

        def _chat(text, retrieved_context="", language_mix_spanish_pct=0, reply_form=""):
            captured["retrieved_context"] = retrieved_context
            captured["reply_form"] = reply_form
            return "It means the last status said Nova was stable."

        out = finalize_llm_fallback_reply(
            text="what do you mean?",
            raw_user_text="what do you mean?",
            input_source="typed",
            retrieved_context="",
            language_mix_spanish_pct=0,
            ollama_chat_fn=_chat,
            mem_enabled_fn=lambda: False,
            mem_should_store_fn=lambda text: False,
            mem_add_fn=lambda kind, source, text: None,
            strip_mem_leak_fn=lambda reply, retrieved_context: reply,
            behavior_record_event_fn=lambda event: None,
            action_ledger_add_step=lambda *args, **kwargs: None,
            ensure_reply_fn=lambda text: text,
            intent_evidence_packet=packet,
            fallback_context={
                "chat_context": "Assistant returned a tool result.",
                "state_context": "ACTIVE SESSION STATE: last_tool_evidence / self_status\nLast tool evidence:\nNova Self Status - stable",
            },
        )

        self.assertEqual(out.get("reply"), "It means the last status said Nova was stable.")
        self.assertEqual(captured.get("reply_form"), "conversation_turn")
        self.assertNotIn("SESSION EVIDENCE", captured.get("retrieved_context"))
        self.assertNotIn("Nova Self Status - stable", captured.get("retrieved_context"))

    def test_finalize_fallback_uses_existing_tool_evidence_as_context_not_answer(self):
        packet = build_turn_intent_evidence_packet(
            text="what do you mean?",
            turns=[("assistant", "Assistant returned a tool result. The result is available as last tool evidence."), ("user", "what do you mean?")],
            fallback_context={
                "state_context": (
                    "ACTIVE SESSION STATE: last_tool_evidence / self_status\n"
                    "Last tool evidence:\n"
                    "Nova Self Status - 2026-05-20 10:00:00\n"
                    "Level: updating\n"
                    "Summary: Nova is stable and has update activity to review.\n"
                ),
            },
            semantic_tool_observation={
                "status": "tool_evidence_available",
                "intent": {
                    "tool": "none",
                    "confidence": 1.0,
                    "evidence_need": "conversation",
                    "answer_target": "current_conversation",
                },
            },
        )
        calls = []

        out = finalize_llm_fallback_reply(
            text="what do you mean?",
            raw_user_text="what do you mean?",
            input_source="typed",
            retrieved_context="",
            language_mix_spanish_pct=0,
            ollama_chat_fn=lambda *args, **kwargs: calls.append("llm") or "The prior reply repeated status instead of answering.",
            mem_enabled_fn=lambda: False,
            mem_should_store_fn=lambda text: False,
            mem_add_fn=lambda kind, source, text: None,
            strip_mem_leak_fn=lambda reply, retrieved_context: reply,
            behavior_record_event_fn=lambda event: calls.append(event),
            action_ledger_add_step=lambda *args, **kwargs: calls.append(args[0]),
            ensure_reply_fn=lambda text: text,
            intent_evidence_packet=packet,
            fallback_context={
                "state_context": (
                    "ACTIVE SESSION STATE: last_tool_evidence / self_status\n"
                    "Last tool evidence:\n"
                    "Nova Self Status - 2026-05-20 10:00:00\n"
                    "Level: updating\n"
                    "Summary: Nova is stable and has update activity to review.\n"
                ),
            },
        )

        self.assertEqual(out.get("planner_decision"), "llm_fallback")
        self.assertEqual(out.get("reply_contract"), "")
        self.assertEqual(out.get("reply"), "The prior reply repeated status instead of answering.")
        self.assertIn("llm", calls)
        self.assertNotIn("session_evidence", calls)

    def test_finalize_conversation_scoped_fallback_keeps_first_complete_thought(self):
        packet = build_turn_intent_evidence_packet(
            text="continue the exchange",
            turns=[("user", "continue the exchange")],
            fallback_context={"chat_context": "recent turns"},
            semantic_tool_observation={
                "status": "none",
                "intent": {
                    "tool": "none",
                    "confidence": 0.91,
                    "evidence_need": "conversation",
                    "answer_target": "current_conversation",
                },
            },
        )

        out = finalize_llm_fallback_reply(
            text="continue the exchange",
            raw_user_text="continue the exchange",
            input_source="typed",
            retrieved_context="",
            language_mix_spanish_pct=0,
            ollama_chat_fn=lambda *args, **kwargs: "I can stay with this conversation. Extra explanation follows. Another branch follows.",
            mem_enabled_fn=lambda: False,
            mem_should_store_fn=lambda text: False,
            mem_add_fn=lambda kind, source, text: None,
            strip_mem_leak_fn=lambda reply, retrieved_context: reply,
            behavior_record_event_fn=lambda event: None,
            action_ledger_add_step=lambda *args, **kwargs: None,
            ensure_reply_fn=lambda text: text,
            intent_evidence_packet=packet,
            fallback_context={},
        )

        self.assertEqual(out.get("reply"), "I can stay with this conversation.")

    def test_finalize_conversation_scoped_fallback_prefers_statement_over_question_opener(self):
        packet = build_turn_intent_evidence_packet(
            text="continue the exchange",
            turns=[("user", "continue the exchange")],
            fallback_context={"chat_context": "recent turns"},
            semantic_tool_observation={
                "status": "none",
                "intent": {
                    "tool": "none",
                    "confidence": 0.91,
                    "evidence_need": "conversation",
                    "answer_target": "current_conversation",
                },
            },
        )

        out = finalize_llm_fallback_reply(
            text="continue the exchange",
            raw_user_text="continue the exchange",
            input_source="typed",
            retrieved_context="",
            language_mix_spanish_pct=0,
            ollama_chat_fn=lambda *args, **kwargs: "What path now? This can stay simple. Extra explanation follows.",
            mem_enabled_fn=lambda: False,
            mem_should_store_fn=lambda text: False,
            mem_add_fn=lambda kind, source, text: None,
            strip_mem_leak_fn=lambda reply, retrieved_context: reply,
            behavior_record_event_fn=lambda event: None,
            action_ledger_add_step=lambda *args, **kwargs: None,
            ensure_reply_fn=lambda text: text,
            intent_evidence_packet=packet,
            fallback_context={},
        )

        self.assertEqual(out.get("reply"), "This can stay simple.")

    def test_conversation_form_shapes_helpdesk_greeting_to_a_statement(self):
        packet = build_turn_intent_evidence_packet(
            text="hi nova",
            turns=[("user", "hi nova")],
            fallback_context={"chat_context": "recent turns"},
            semantic_tool_observation={
                "status": "none",
                "intent": {
                    "tool": "none",
                    "confidence": 0.91,
                    "evidence_need": "conversation",
                    "answer_target": "current_conversation",
                },
            },
        )
        out = finalize_llm_fallback_reply(
            text="hi nova",
            raw_user_text="hi nova",
            input_source="typed",
            retrieved_context="",
            language_mix_spanish_pct=0,
            ollama_chat_fn=lambda *args, **kwargs: "Hello! How can I assist you today?",
            mem_enabled_fn=lambda: False,
            mem_should_store_fn=lambda text: False,
            mem_add_fn=lambda kind, source, text: None,
            strip_mem_leak_fn=lambda reply, retrieved_context: reply,
            behavior_record_event_fn=lambda event: None,
            action_ledger_add_step=lambda *args, **kwargs: None,
            ensure_reply_fn=lambda text: text,
            intent_evidence_packet=packet,
            fallback_context={},
        )

        self.assertEqual(out.get("reply"), "Hello!")
        self.assertNotIn("assist", str(out.get("reply") or "").lower())

    def test_identity_ask_uses_evidence_when_router_misses_nova_self(self):
        calls = []
        out = finalize_llm_fallback_reply(
            text="who are you?",
            raw_user_text="who are you?",
            input_source="http",
            retrieved_context="",
            language_mix_spanish_pct=0,
            ollama_chat_fn=lambda *args, **kwargs: calls.append("llm") or "I am a chatbot designed to help.",
            mem_enabled_fn=lambda: False,
            mem_should_store_fn=lambda text: False,
            mem_add_fn=lambda kind, source, text: None,
            strip_mem_leak_fn=lambda reply, retrieved_context: reply,
            behavior_record_event_fn=lambda event: None,
            action_ledger_add_step=lambda *args, **kwargs: None,
            ensure_reply_fn=lambda text: text,
            intent_evidence_packet={},
            fallback_context={
                "learning_context": (
                    "Confirmed Nova identity evidence: operator confirmed\n"
                    "Identity fact: assistant_name=Nova\n"
                    "Operational Nova self evidence:\n"
                    "Registered internal surfaces observed from the capability registry:\n"
                    "- runtime_core: Nova runs as a local runtime\n"
                    "- work_tree: Nova can organize internal work\n"
                ),
            },
            leah_fast_chat=True,
        )

        self.assertEqual(out.get("planner_decision"), "evidence_bound_reply")
        self.assertIn("I am Nova", out.get("reply"))
        self.assertIn("local AI runtime", out.get("reply"))
        self.assertNotIn("chatbot", str(out.get("reply") or "").lower())
        self.assertNotIn("llm", calls)

    def test_chatbot_ask_uses_operational_evidence_not_model_prior(self):
        calls = []
        out = finalize_llm_fallback_reply(
            text="are you a chat bot ?",
            raw_user_text="are you a chat bot ?",
            input_source="http",
            retrieved_context="",
            language_mix_spanish_pct=0,
            ollama_chat_fn=lambda *args, **kwargs: calls.append("llm") or "Yes, I'm a chatbot.",
            mem_enabled_fn=lambda: False,
            mem_should_store_fn=lambda text: False,
            mem_add_fn=lambda kind, source, text: None,
            strip_mem_leak_fn=lambda reply, retrieved_context: reply,
            behavior_record_event_fn=lambda event: None,
            action_ledger_add_step=lambda *args, **kwargs: None,
            ensure_reply_fn=lambda text: text,
            intent_evidence_packet={},
            fallback_context={
                "learning_context": (
                    "Identity fact: assistant_name=Nova\n"
                    "Operational Nova self evidence:\n"
                    "Registered internal surfaces observed from the capability registry:\n"
                    "- guard_system: Nova has a guard process\n"
                ),
            },
            leah_fast_chat=True,
        )

        self.assertIn("I am Nova", out.get("reply"))
        self.assertIn("not only a model reply", out.get("reply"))
        self.assertNotIn("Yes, I'm a chatbot", out.get("reply") or "")
        self.assertNotIn("llm", calls)

    def test_finalize_fallback_binds_operational_self_answer_to_evidence_without_llm(self):
        calls = []
        packet = build_turn_intent_evidence_packet(
            text="what are you?",
            turns=[("user", "what are you?")],
            fallback_context={"identity_used": True, "identity_chars": 10, "operational_identity_used": True, "operational_identity_chars": 20},
            semantic_tool_observation={
                "status": "none",
                "intent": {"tool": "none", "confidence": 0.9, "evidence_need": "operational_self", "answer_target": "nova_self"},
            },
        )

        out = finalize_llm_fallback_reply(
            text="what are you?",
            raw_user_text="what are you?",
            input_source="http",
            retrieved_context="",
            language_mix_spanish_pct=0,
            ollama_chat_fn=lambda *args, **kwargs: calls.append("llm") or "MODEL",
            mem_enabled_fn=lambda: False,
            mem_should_store_fn=lambda text: False,
            mem_add_fn=lambda kind, source, text: None,
            strip_mem_leak_fn=lambda reply, retrieved_context: reply,
            behavior_record_event_fn=lambda event: calls.append(event),
            action_ledger_add_step=lambda *args, **kwargs: calls.append(args[0]),
            ensure_reply_fn=lambda text: text,
            intent_evidence_packet=packet,
            fallback_context={
                "learning_context": (
                    "Confirmed Nova identity evidence: Nova identity origin was confirmed by the operator; identity bootstrap status: ready\n"
                    "Identity fact: assistant_name=Nova\n"
                    "Identity fact: developer_name=Gustavo Uribe\n"
                    "Identity fact: developer_nickname=Gus\n"
                    "Operational Nova self evidence:\n"
                    "Registered internal surfaces observed from the capability registry:\n"
                    "- runtime_core: Nova runs as a local runtime\n"
                    "- work_tree: Nova can organize internal work\n"
                    "- autonomy_handling: Nova has autonomy advisory machinery\n"
                ),
            },
        )

        self.assertEqual(out.get("planner_decision"), "evidence_bound_reply")
        self.assertTrue(out.get("grounded"))
        self.assertIn("I am Nova", out.get("reply"))
        self.assertIn("Gustavo Uribe", out.get("reply"))
        self.assertIn("runtime core", out.get("reply"))
        self.assertNotIn("MODEL", out.get("reply"))
        self.assertNotIn("llm", calls)

    def test_finalize_fallback_binds_confirmed_identity_answer_to_evidence_without_llm(self):
        packet = build_turn_intent_evidence_packet(
            text="who made you?",
            turns=[("user", "who made you?")],
            fallback_context={"identity_used": True, "identity_chars": 10},
            semantic_tool_observation={
                "status": "none",
                "intent": {"tool": "none", "confidence": 0.88, "evidence_need": "confirmed_identity", "answer_target": "nova_self"},
            },
        )

        out = finalize_llm_fallback_reply(
            text="who made you?",
            raw_user_text="who made you?",
            input_source="http",
            retrieved_context="",
            language_mix_spanish_pct=0,
            ollama_chat_fn=lambda *args, **kwargs: "MODEL_SHOULD_NOT_RUN",
            mem_enabled_fn=lambda: False,
            mem_should_store_fn=lambda text: False,
            mem_add_fn=lambda kind, source, text: None,
            strip_mem_leak_fn=lambda reply, retrieved_context: reply,
            behavior_record_event_fn=lambda event: None,
            action_ledger_add_step=lambda *args, **kwargs: None,
            ensure_reply_fn=lambda text: text,
            intent_evidence_packet=packet,
            fallback_context={
                "learning_context": (
                    "Confirmed Nova identity evidence: Nova identity origin was confirmed by the operator\n"
                    "Identity fact: assistant_name=Nova\n"
                    "Identity fact: developer_name=Gustavo Uribe\n"
                    "Identity fact: developer_nickname=Gus\n"
                ),
            },
        )

        self.assertEqual(out.get("reply_contract"), "self_evidence.confirmed_identity")
        self.assertIn("developer=Gustavo Uribe (Gus)", out.get("reply"))
        self.assertNotIn("MODEL_SHOULD_NOT_RUN", out.get("reply"))

    def test_finalize_fallback_does_not_upgrade_unclear_self_evidence_need(self):
        packet = build_turn_intent_evidence_packet(
            text="tell me more",
            turns=[("user", "tell me more")],
            fallback_context={"identity_used": True, "identity_chars": 10, "operational_identity_used": True, "operational_identity_chars": 20},
            semantic_tool_observation={
                "status": "none",
                "intent": {"tool": "none", "confidence": 0.9, "evidence_need": "unknown", "answer_target": "nova_self"},
            },
        )

        out = finalize_llm_fallback_reply(
            text="tell me more",
            raw_user_text="tell me more",
            input_source="http",
            retrieved_context="",
            language_mix_spanish_pct=0,
            ollama_chat_fn=lambda *args, **kwargs: "MODEL_REPLY",
            mem_enabled_fn=lambda: False,
            mem_should_store_fn=lambda text: False,
            mem_add_fn=lambda kind, source, text: None,
            strip_mem_leak_fn=lambda reply, retrieved_context: reply,
            behavior_record_event_fn=lambda event: None,
            action_ledger_add_step=lambda *args, **kwargs: None,
            ensure_reply_fn=lambda text: text,
            intent_evidence_packet=packet,
            fallback_context={
                "learning_context": (
                    "Identity fact: assistant_name=Nova\n"
                    "Operational Nova self evidence:\n"
                    "- runtime_core: Nova runs as a local runtime\n"
                ),
            },
        )

        self.assertEqual(out.get("planner_decision"), "llm_fallback")
        self.assertEqual(out.get("reply"), "MODEL_REPLY")

    def test_clear_identity_ask_binds_even_when_router_confidence_is_low(self):
        packet = build_turn_intent_evidence_packet(
            text="what are you?",
            turns=[("user", "what are you?")],
            fallback_context={"identity_used": True, "identity_chars": 10, "operational_identity_used": True, "operational_identity_chars": 20},
            semantic_tool_observation={
                "status": "none",
                "intent": {"tool": "none", "confidence": 0.31, "evidence_need": "operational_self", "answer_target": "nova_self"},
            },
        )

        out = finalize_llm_fallback_reply(
            text="what are you?",
            raw_user_text="what are you?",
            input_source="http",
            retrieved_context="",
            language_mix_spanish_pct=0,
            ollama_chat_fn=lambda *args, **kwargs: "MODEL_REPLY",
            mem_enabled_fn=lambda: False,
            mem_should_store_fn=lambda text: False,
            mem_add_fn=lambda kind, source, text: None,
            strip_mem_leak_fn=lambda reply, retrieved_context: reply,
            behavior_record_event_fn=lambda event: None,
            action_ledger_add_step=lambda *args, **kwargs: None,
            ensure_reply_fn=lambda text: text,
            intent_evidence_packet=packet,
            fallback_context={
                "learning_context": (
                    "Identity fact: assistant_name=Nova\n"
                    "Operational Nova self evidence:\n"
                    "- runtime_core: Nova runs as a local runtime\n"
                ),
            },
        )

        self.assertEqual(out.get("planner_decision"), "evidence_bound_reply")
        self.assertIn("I am Nova", out.get("reply"))
        self.assertNotIn("MODEL_REPLY", out.get("reply") or "")

    def test_finalize_fallback_does_not_bind_low_confidence_unrelated_self_route(self):
        packet = build_turn_intent_evidence_packet(
            text="how is that working?",
            turns=[("user", "how is that working?")],
            fallback_context={"identity_used": True, "identity_chars": 10, "operational_identity_used": True, "operational_identity_chars": 20},
            semantic_tool_observation={
                "status": "none",
                "intent": {"tool": "none", "confidence": 0.31, "evidence_need": "operational_self", "answer_target": "nova_self"},
            },
        )

        out = finalize_llm_fallback_reply(
            text="how is that working?",
            raw_user_text="how is that working?",
            input_source="http",
            retrieved_context="",
            language_mix_spanish_pct=0,
            ollama_chat_fn=lambda *args, **kwargs: "MODEL_REPLY",
            mem_enabled_fn=lambda: False,
            mem_should_store_fn=lambda text: False,
            mem_add_fn=lambda kind, source, text: None,
            strip_mem_leak_fn=lambda reply, retrieved_context: reply,
            behavior_record_event_fn=lambda event: None,
            action_ledger_add_step=lambda *args, **kwargs: None,
            ensure_reply_fn=lambda text: text,
            intent_evidence_packet=packet,
            fallback_context={
                "learning_context": (
                    "Identity fact: assistant_name=Nova\n"
                    "Operational Nova self evidence:\n"
                    "- runtime_core: Nova runs as a local runtime\n"
                ),
            },
        )

        self.assertEqual(out.get("planner_decision"), "llm_fallback")
        self.assertEqual(out.get("reply"), "MODEL_REPLY")

    def test_intent_evidence_packet_keeps_trace_below_authority(self):
        packet = build_turn_intent_evidence_packet(
            text="can you prove what you just said?",
            turns=[
                ("user", "who built this runtime?"),
                ("assistant", "I am not sure from current evidence."),
                ("user", "can you prove what you just said?"),
            ],
            fallback_context={"chat_context": "recent turns"},
            semantic_tool_observation={"status": "none", "intent": {"tool": "none", "confidence": 0.9}},
        )

        self.assertEqual(packet.get("trace_authority"), "hypothesis_only")
        self.assertFalse((packet.get("answer_contract") or {}).get("trace_is_route_authority"))
        self.assertTrue((packet.get("answer_contract") or {}).get("evidence_is_claim_authority"))
        self.assertIn("I am not sure", (packet.get("conversation_frame") or {}).get("previous_assistant_turn"))
        self.assertFalse((packet.get("conversation_frame") or {}).get("last_assistant_repeats_earlier_assistant"))
        self.assertFalse((packet.get("answer_contract") or {}).get("conversation_can_be_complete_without_task"))

    def test_conversation_scoped_intent_marks_conversation_as_complete_without_task(self):
        packet = build_turn_intent_evidence_packet(
            text="continue this exchange",
            turns=[
                ("user", "first turn"),
                ("assistant", "first reply"),
                ("user", "continue this exchange"),
            ],
            fallback_context={"chat_context": "recent turns"},
            semantic_tool_observation={
                "status": "none",
                "intent": {
                    "tool": "none",
                    "confidence": 0.91,
                    "evidence_need": "conversation",
                    "answer_target": "current_conversation",
                },
            },
        )

        rendered = render_turn_intent_evidence_packet(packet)

        self.assertTrue((packet.get("answer_contract") or {}).get("conversation_can_be_complete_without_task"))
        self.assertEqual((packet.get("answer_contract") or {}).get("reply_form"), "conversation_turn")
        self.assertEqual(
            rendered.count("- The current turn is conversation-scoped; do not convert it into a task, help flow, confirmation loop, or closing question."),
            1,
        )
        self.assertIn("without_task", str(packet.get("answer_contract")))

    def test_conversation_scoped_intent_uses_structured_pair_not_numeric_confidence(self):
        packet = build_turn_intent_evidence_packet(
            text="keep this simple",
            turns=[
                ("user", "first turn"),
                ("assistant", "first reply"),
                ("user", "keep this simple"),
            ],
            fallback_context={"chat_context": "recent turns"},
            semantic_tool_observation={
                "status": "none",
                "intent": {
                    "tool": "none",
                    "confidence": 0.0,
                    "evidence_need": "conversation",
                    "answer_target": "current_conversation",
                },
            },
        )

        rendered = render_turn_intent_evidence_packet(packet)

        self.assertTrue((packet.get("answer_contract") or {}).get("conversation_can_be_complete_without_task"))
        self.assertEqual((packet.get("answer_contract") or {}).get("reply_form"), "conversation_turn")
        self.assertIn("conversation-scoped", rendered)

    def test_intent_evidence_render_does_not_replay_prior_assistant_text(self):
        packet = build_turn_intent_evidence_packet(
            text="why did you repeat that?",
            turns=[
                ("user", "how can I help you?"),
                ("assistant", "Prior answer that should not become the next draft."),
                ("user", "why did you repeat that?"),
            ],
            fallback_context={"chat_context": "recent turns"},
            semantic_tool_observation={"status": "none", "intent": {"tool": "none", "confidence": 0.0}},
        )

        rendered = render_turn_intent_evidence_packet(packet)

        self.assertIn("Prior answer that should not become the next draft", (packet.get("conversation_frame") or {}).get("previous_assistant_turn"))
        self.assertFalse((packet.get("conversation_frame") or {}).get("last_assistant_repeats_earlier_assistant"))
        self.assertIn("prior assistant reply is available", rendered)
        self.assertIn("current user turn is the answer target", rendered)
        self.assertNotIn("Prior answer that should not become the next draft", rendered)

    def test_finalize_fallback_does_not_answer_repeat_observation_without_model(self):
        calls = []
        repeated = "Same stale assistant answer."
        packet = build_turn_intent_evidence_packet(
            text="why did you repeat?",
            turns=[
                ("user", "first"),
                ("assistant", repeated),
                ("user", "second"),
                ("assistant", repeated),
                ("user", "why did you repeat?"),
            ],
            fallback_context={"chat_context": "recent turns"},
            semantic_tool_observation={
                "status": "none",
                "intent": {
                    "tool": "none",
                    "confidence": 0.92,
                    "evidence_need": "conversation",
                    "answer_target": "current_conversation",
                },
            },
        )

        out = finalize_llm_fallback_reply(
            text="why did you repeat?",
            raw_user_text="why did you repeat?",
            input_source="typed",
            retrieved_context="",
            language_mix_spanish_pct=0,
            ollama_chat_fn=lambda *args, **kwargs: calls.append("llm") or "I repeated myself there.",
            mem_enabled_fn=lambda: False,
            mem_should_store_fn=lambda text: False,
            mem_add_fn=lambda kind, source, text: None,
            strip_mem_leak_fn=lambda reply, retrieved_context: reply,
            behavior_record_event_fn=lambda event: calls.append(event),
            action_ledger_add_step=lambda *args, **kwargs: calls.append(args[0]),
            ensure_reply_fn=lambda text: text,
            intent_evidence_packet=packet,
            fallback_context={},
        )

        self.assertTrue((packet.get("conversation_frame") or {}).get("last_assistant_repeats_earlier_assistant"))
        self.assertEqual(out.get("planner_decision"), "llm_fallback")
        self.assertEqual(out.get("reply_contract"), "")
        self.assertEqual(out.get("reply"), "I repeated myself there.")
        self.assertIn("llm", calls)


class TestPresenceAndIdentityDetectors(unittest.TestCase):
    def test_identity_ask_is_detected(self):
        self.assertEqual(turn_asks_nova_self("who are you?"), "operational_self")
        self.assertEqual(turn_asks_nova_self("are you a chatbot?"), "operational_self")
        self.assertEqual(turn_asks_nova_self("hi"), "")

    def test_question_only_reply_does_not_keep_the_ticket(self):
        self.assertEqual(_shape_conversation_scoped_reply("What would you like to know or do?"), "")
        self.assertEqual(_shape_conversation_scoped_reply("What topic are you interested in learning about?"), "")


if __name__ == "__main__":
    unittest.main()
