import unittest
from types import SimpleNamespace

from services.nova_fallback_flow import apply_low_confidence_block
from services.nova_fallback_flow import apply_pending_weather_followup_fallback
from services.nova_fallback_flow import apply_policy_gate_block
from services.nova_fallback_flow import build_fallback_context
from services.nova_fallback_flow import finalize_llm_fallback_reply
from services.nova_fallback_flow import prepare_fallback_flow


class TestNovaFallbackFlow(unittest.TestCase):
    def test_apply_pending_weather_followup_fallback_handles_saved_location_followup(self):
        out = apply_pending_weather_followup_fallback(
            text="yea please do that ..",
            pending_action={"kind": "weather_lookup", "status": "awaiting_location", "saved_location_available": True},
            last_assistant_text="What location should I use?",
            looks_like_affirmative_followup_fn=lambda text: "yea" in text,
            looks_like_shared_location_reference_fn=lambda text: False,
            assistant_offered_weather_lookup_fn=lambda text: False,
            ensure_reply=lambda text: text,
        )
        self.assertTrue(out.get("handled"))
        self.assertEqual(out.get("planner_decision"), "llm_fallback")
        self.assertFalse(out.get("grounded"))
        self.assertTrue(out.get("clear_pending_action"))
        self.assertIn("specific weather source or tool", out.get("reply"))

    def test_build_fallback_context_appends_recent_tool_context_for_prior_reference(self):
        calls = []
        out = build_fallback_context(
            text="what about the first one?",
            turns=[("user", "research peims")],
            recent_tool_context="1) https://example.com/a",
            build_fallback_context_details_fn=lambda text, turns: {
                "context": "BASE",
                "learning_context": "BASE",
                "chat_context": "CHAT",
                "session_fact_sheet": "FACTS",
                "memory_used": True,
                "knowledge_used": False,
                "memory_chars": 4,
                "knowledge_chars": 0,
            },
            uses_prior_reference_fn=lambda text: True,
            action_ledger_add_step=lambda *args, **kwargs: calls.append((args, kwargs)),
        )
        self.assertEqual(out.get("retrieved_context"), "BASE\n\nRECENT TOOL OUTPUT:\n1) https://example.com/a")
        self.assertTrue(any(args[0] == "memory_context" for args, _kwargs in calls))
        self.assertTrue(any(args[0] == "recent_tool_context" for args, _kwargs in calls))

    def test_apply_policy_gate_block_normalizes_reply_and_marks_policy_block(self):
        steps = []
        out = apply_policy_gate_block(
            task=SimpleNamespace(allow_llm=False, message="Blocked by policy."),
            action_ledger_add_step=lambda *args, **kwargs: steps.append((args, kwargs)),
            normalize_reply_fn=lambda reply: f"normalized:{reply}",
        )
        self.assertTrue(out.get("handled"))
        self.assertEqual(out.get("reply"), "normalized:Blocked by policy.")
        self.assertEqual(out.get("planner_decision"), "policy_block")
        self.assertTrue(out.get("grounded"))
        self.assertTrue(any(args[0] == "policy_gate" for args, _kwargs in steps))

    def test_prepare_fallback_flow_returns_policy_block_outcome(self):
        steps = []
        out = prepare_fallback_flow(
            text="I need help deciding.",
            turns=[("user", "I need help deciding.")],
            recent_tool_context="",
            prefer_web_for_data_queries=False,
            analyze_request_fn=lambda text, config=None: SimpleNamespace(allow_llm=False, message="Blocked by policy."),
            normalize_policy_reply_fn=lambda reply: f"normalized:{reply}",
            build_fallback_context_details_fn=lambda text, turns: {"context": "unused"},
            uses_prior_reference_fn=lambda text: False,
            action_ledger_add_step=lambda *args, **kwargs: steps.append((args, kwargs)),
        )
        self.assertTrue(out.get("handled"))
        self.assertEqual((out.get("outcome") or {}).get("reply"), "normalized:Blocked by policy.")
        self.assertTrue(any(args[0] == "policy_gate" for args, _kwargs in steps))

    def test_prepare_fallback_flow_builds_retrieved_context_when_allowed(self):
        steps = []
        out = prepare_fallback_flow(
            text="what about the first one?",
            turns=[("user", "research peims")],
            recent_tool_context="1) https://example.com/a",
            prefer_web_for_data_queries=True,
            analyze_request_fn=lambda text, config=None: SimpleNamespace(allow_llm=True, message=""),
            normalize_policy_reply_fn=lambda reply: reply,
            build_fallback_context_details_fn=lambda text, turns: {
                "context": "BASE",
                "learning_context": "BASE",
                "chat_context": "CHAT",
                "session_fact_sheet": "FACTS",
                "memory_used": True,
                "knowledge_used": False,
                "memory_chars": 4,
                "knowledge_chars": 0,
            },
            uses_prior_reference_fn=lambda text: True,
            action_ledger_add_step=lambda *args, **kwargs: steps.append((args, kwargs)),
        )
        self.assertFalse(out.get("handled"))
        self.assertEqual(out.get("retrieved_context"), "BASE\n\nRECENT TOOL OUTPUT:\n1) https://example.com/a")
        self.assertTrue(any(args[0] == "policy_gate" and args[1] == "allowed" for args, _kwargs in steps))

    def test_apply_low_confidence_block_returns_truthful_limit_reply(self):
        events = []
        steps = []
        out = apply_low_confidence_block(
            text="what is gus doing right now?",
            retrieved_context="",
            recent_tool_context="",
            should_block_low_confidence_fn=lambda text, **kwargs: True,
            behavior_record_event_fn=lambda event: events.append(event),
            truthful_limit_outcome_fn=lambda text: {"reply_contract": "turn.truthful_limit", "reply_text": "I don't know that based on what I can verify."},
            truthful_limit_reply_fn=lambda text: "fallback",
            action_ledger_add_step=lambda *args, **kwargs: steps.append((args, kwargs)),
            ensure_reply=lambda text: text,
        )
        self.assertTrue(out.get("handled"))
        self.assertEqual(out.get("planner_decision"), "blocked_low_confidence")
        self.assertEqual(out.get("reply_contract"), "turn.truthful_limit")
        self.assertEqual(out.get("reply"), "I don't know that based on what I can verify.")
        self.assertIn("low_confidence_block", events)
        self.assertTrue(any(args[0] == "low_confidence_gate" for args, _kwargs in steps))

    def test_finalize_llm_fallback_reply_records_claim_gate_truthful_limit(self):
        events = []
        steps = []
        memories = []
        taught = []
        out = finalize_llm_fallback_reply(
            text="tell me something reflective about ambition",
            raw_user_text="tell me something reflective about ambition",
            input_source="typed",
            retrieved_context="SESSION FACT SHEET",
            recent_tool_context="",
            language_mix_spanish_pct=0,
            active_user="gus",
            ollama_chat_fn=lambda text, retrieved_context="", language_mix_spanish_pct=0: "Unsafe claim.",
            sanitize_llm_reply_fn=lambda reply, tool_context: reply,
            mem_enabled_fn=lambda: True,
            mem_should_store_fn=lambda text: True,
            mem_add_fn=lambda kind, source, text: memories.append((kind, source, text)),
            strip_mem_leak_fn=lambda reply, retrieved_context: reply,
            self_correct_reply_fn=lambda text, reply: (reply, False, ""),
            behavior_record_event_fn=lambda event: events.append(event),
            action_ledger_add_step=lambda *args, **kwargs: steps.append((args, kwargs)),
            teach_store_example_fn=lambda before, after, user=None: taught.append((before, after, user)),
            truthful_limit_outcome_fn=lambda text: {"reply_contract": "turn.truthful_limit", "kind": "cannot_verify"},
            apply_claim_gate_fn=lambda reply, evidence_text="", tool_context="": ("I don't know that based on what I can verify.", True, "unsupported_claim_blocked"),
            is_explicit_request_fn=lambda text: False,
            apply_reply_overrides_fn=lambda text: text,
            ensure_reply_fn=lambda text: text,
        )
        self.assertTrue(out.get("handled"))
        self.assertEqual(out.get("planner_decision"), "llm_fallback")
        self.assertFalse(out.get("grounded"))
        self.assertEqual(out.get("reply_contract"), "turn.truthful_limit")
        self.assertEqual((out.get("reply_outcome") or {}).get("kind"), "cannot_verify")
        self.assertEqual(out.get("reply"), "I don't know that based on what I can verify.")
        self.assertIn("llm_fallback", events)
        self.assertEqual(memories, [("chat_user", "typed", "tell me something reflective about ambition")])
        self.assertFalse(taught)
        self.assertTrue(any(args[0] == "claim_gate" for args, _kwargs in steps))

    def test_finalize_llm_fallback_reply_supports_preprocess_and_post_claim_hooks(self):
        out = finalize_llm_fallback_reply(
            text="tell me something reflective about ambition",
            raw_user_text="tell me something reflective about ambition",
            input_source="typed",
            retrieved_context="SESSION FACT SHEET",
            recent_tool_context="",
            language_mix_spanish_pct=0,
            active_user="gus",
            ollama_chat_fn=lambda text, retrieved_context="", language_mix_spanish_pct=0: "raw reply",
            sanitize_llm_reply_fn=lambda reply, tool_context: reply,
            mem_enabled_fn=lambda: False,
            mem_should_store_fn=lambda text: False,
            mem_add_fn=lambda kind, source, text: None,
            strip_mem_leak_fn=lambda reply, retrieved_context: reply,
            self_correct_reply_fn=lambda text, reply: (reply, False, ""),
            behavior_record_event_fn=lambda event: None,
            action_ledger_add_step=lambda *args, **kwargs: None,
            teach_store_example_fn=lambda before, after, user=None: None,
            truthful_limit_outcome_fn=lambda text: {},
            apply_claim_gate_fn=lambda reply, evidence_text="", tool_context="": (reply, False, ""),
            preprocess_reply_fn=lambda reply: f"pre:{reply}",
            post_claim_reply_transform_fn=lambda reply, reply_contract: f"post:{reply}",
            is_explicit_request_fn=lambda text: True,
            apply_reply_overrides_fn=lambda text: text,
            ensure_reply_fn=lambda text: text,
        )
        self.assertEqual(out.get("reply"), "post:pre:raw reply")


if __name__ == "__main__":
    unittest.main()