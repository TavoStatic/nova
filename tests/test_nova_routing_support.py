import unittest

from services import nova_routing_support


class TestNovaRoutingSupport(unittest.TestCase):
    def test_classify_supervisor_bypass_marks_open_fallback_as_not_allowlisted(self):
        result = nova_routing_support.classify_supervisor_bypass(
            "just answer however you want",
            normalize_bypass_phrase_fn=lambda text: text.lower().strip(),
            allowed_supervisor_bypasses=(),
            looks_like_open_fallback_turn_fn=lambda text: True,
        )

        self.assertFalse(result["allowed"])
        self.assertEqual(result["category"], "intentional_fallback.open_fulfillment_or_model")
        self.assertEqual(result["reason"], "open_fallback_candidate")

    def test_should_warn_supervisor_bypass_ignores_weather_shortcuts(self):
        self.assertFalse(
            nova_routing_support.should_warn_supervisor_bypass(
                "weather now",
                looks_like_open_fallback_turn_fn=lambda text: False,
                is_explicit_command_like_fn=lambda text: False,
                is_location_request_fn=lambda text: False,
                normalize_turn_text_fn=lambda text: text.lower().strip(),
                is_student_data_broad_query_fn=lambda text: False,
                is_local_knowledge_topic_query_fn=lambda text: False,
            )
        )

    def test_supervisor_candidate_trace_trims_fields(self):
        trace = nova_routing_support.supervisor_candidate_trace(
            {
                "candidates": [
                    {
                        "rule_name": "route_weather",
                        "priority": 3,
                        "handled": True,
                        "action": "run_tool",
                        "intent": "weather_lookup",
                        "rewrite": True,
                        "state_update": True,
                        "rule_error": "x" * 200,
                    }
                ]
            }
        )

        self.assertEqual(trace[0]["rule_name"], "route_weather")
        self.assertTrue(trace[0]["rewrite"])
        self.assertTrue(trace[0]["state_update"])
        self.assertEqual(len(trace[0]["rule_error"]), 160)

    def test_build_routing_decision_uses_supervisor_phase_records(self):
        decision = nova_routing_support.build_routing_decision(
            "Need weather help",
            entry_point="http",
            intent_result={"matched_rule_name": "weather_intent", "intent": "weather_lookup"},
            handle_result={"matched_rule_name": "weather_handle", "action": "run_tool"},
            final_owner="fallback",
            allowed_bypass=True,
            allowed_bypass_category="intentional_fallback.open_fulfillment_or_model",
            bypass_reason="open_fallback_candidate",
            reply_contract="weather_lookup",
            reply_outcome={"kind": "weather_lookup"},
            turn_acts=["weather", "followup"],
            intent_trace_preview_fn=lambda text: text[:12],
            supervisor_phase_record_fn=lambda payload, phase: {"phase": phase, "handled": bool(payload)},
        )

        self.assertEqual(decision["input_preview"], "Need weather")
        self.assertEqual(decision["entry_point"], "http")
        self.assertEqual(decision["intent_phase"], {"phase": "intent", "handled": True})
        self.assertEqual(decision["handle_phase"], {"phase": "handle", "handled": True})
        self.assertEqual(decision["reply_outcome_kind"], "weather_lookup")
        self.assertEqual(decision["turn_acts"], ["weather", "followup"])

    def test_build_routing_decision_supports_runtime_scope_hook_resolution(self):
        decision = nova_routing_support.build_routing_decision(
            "Need weather help",
            entry_point="http",
            intent_result={"matched_rule_name": "weather_intent"},
            handle_result={"matched_rule_name": "weather_handle"},
            runtime_scope={
                "_intent_trace_preview": lambda text: text[:4],
                "_supervisor_phase_record": lambda payload, phase: {"phase": phase, "handled": bool(payload)},
            },
        )

        self.assertEqual(decision["input_preview"], "Need")
        self.assertEqual(decision["intent_phase"], {"phase": "intent", "handled": True})
        self.assertEqual(decision["handle_phase"], {"phase": "handle", "handled": True})

    def test_should_clarify_unlabeled_numeric_turn_respects_saved_location_state(self):
        self.assertTrue(
            nova_routing_support.should_clarify_unlabeled_numeric_turn(
                "78521",
                pending_action=None,
                current_state=None,
                get_saved_location_text_fn=lambda: "Brownsville, Texas",
            )
        )
        self.assertFalse(
            nova_routing_support.should_clarify_unlabeled_numeric_turn(
                "78521",
                pending_action={"kind": "weather_lookup", "status": "awaiting_location"},
                current_state=None,
                get_saved_location_text_fn=lambda: "Brownsville, Texas",
            )
        )

    def test_llm_classify_routing_intent_skips_deterministic_operator_truth_queries(self):
        called = {"live_gate": 0}

        def _live_gate():
            called["live_gate"] += 1
            return True

        result = nova_routing_support.llm_classify_routing_intent(
            "Now tell me what would make that storage watch go back into warning.",
            live_ollama_calls_allowed_fn=_live_gate,
            chat_model_fn=lambda: (_ for _ in ()).throw(AssertionError("chat model should not be called")),
            ollama_base="http://127.0.0.1:11434",
            get_saved_location_text_fn=lambda: "Brownsville, Texas",
        )

        self.assertIsNone(result)
        self.assertEqual(called["live_gate"], 0)


if __name__ == "__main__":
    unittest.main()
