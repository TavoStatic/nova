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

    def test_should_warn_supervisor_bypass_is_retired_for_model_owned_chat(self):
        self.assertFalse(
            nova_routing_support.should_warn_supervisor_bypass(
                "anything at all",
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

    def test_should_clarify_unlabeled_numeric_turn_is_retired_for_chat(self):
        self.assertFalse(
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

    def test_llm_classify_routing_intent_returns_none_for_model_none(self):
        called = {"live_gate": 0}

        def _live_gate():
            called["live_gate"] += 1
            return True

        class _Resp:
            def raise_for_status(self):
                pass

            def json(self):
                return {"message": {"content": '{"tool":"none","args":[],"confidence":0.9}'}}

        result = nova_routing_support.llm_classify_routing_intent(
            "Now tell me what would make that storage watch go back into warning.",
            live_ollama_calls_allowed_fn=_live_gate,
            chat_model_fn=lambda: "llama3.2:3b",
            ollama_base="http://127.0.0.1:11434",
            get_saved_location_text_fn=lambda: "Brownsville, Texas",
            requests_post_fn=lambda *args, **kwargs: _Resp(),
        )

        self.assertIsNone(result)
        self.assertEqual(called["live_gate"], 1)

    def test_llm_classify_routing_intent_can_return_explicit_none_payload(self):
        called = {"live_gate": 0}

        def _live_gate():
            called["live_gate"] += 1
            return True

        class _Resp:
            def raise_for_status(self):
                pass

            def json(self):
                return {"message": {"content": '{"tool":"none","args":[],"confidence":0.84,"reason":"conversation"}'}}

        result = nova_routing_support.llm_classify_routing_intent(
            "Now tell me why that answer was confusing.",
            return_none_payload=True,
            live_ollama_calls_allowed_fn=_live_gate,
            chat_model_fn=lambda: "llama3.2:3b",
            ollama_base="http://127.0.0.1:11434",
            get_saved_location_text_fn=lambda: "Brownsville, Texas",
            requests_post_fn=lambda *args, **kwargs: _Resp(),
        )

        self.assertEqual(result.get("tool"), "none")
        self.assertEqual(result.get("args"), [])
        self.assertEqual(called["live_gate"], 1)

    def test_llm_classify_routing_intent_maps_weather_tool_goal(self):
        called = {"live_gate": 0}
        captured = {}

        def _live_gate():
            called["live_gate"] += 1
            return True

        class _Resp:
            def raise_for_status(self):
                pass

            def json(self):
                return {
                    "message": {
                        "content": '{"tool":"weather_current_location","args":[],"confidence":0.88,"reason":"outdoor conditions"}'
                    }
                }

        def _post(_url, json=None, **_kwargs):
            captured["payload"] = json
            return _Resp()

        result = nova_routing_support.llm_classify_routing_intent(
            "should I bring a jacket today?",
            live_ollama_calls_allowed_fn=_live_gate,
            chat_model_fn=lambda: "llama3.2:3b",
            ollama_base="http://127.0.0.1:11434",
            get_saved_location_text_fn=lambda: "Brownsville, Texas",
            requests_post_fn=_post,
        )

        self.assertEqual(result.get("tool"), "weather_current_location")
        self.assertEqual(result.get("args"), [])
        self.assertEqual(called["live_gate"], 1)
        self.assertEqual(captured["payload"]["keep_alive"], "10m")

    def test_llm_classify_routing_intent_maps_live_self_status_goal(self):
        called = {"live_gate": 0}

        def _live_gate():
            called["live_gate"] += 1
            return True

        class _Resp:
            def raise_for_status(self):
                pass

            def json(self):
                return {
                    "message": {
                        "content": '{"tool":"self_status","args":[],"confidence":0.92,"reason":"live operational state"}'
                    }
                }

        result = nova_routing_support.llm_classify_routing_intent(
            "tell me what is happening inside Nova right now",
            live_ollama_calls_allowed_fn=_live_gate,
            chat_model_fn=lambda: "llama3.2:3b",
            ollama_base="http://127.0.0.1:11434",
            get_saved_location_text_fn=lambda: "Brownsville, Texas",
            requests_post_fn=lambda *args, **kwargs: _Resp(),
        )

        self.assertEqual(result.get("tool"), "self_status")
        self.assertEqual(result.get("args"), [])
        self.assertEqual(called["live_gate"], 1)

    def test_coerce_tool_intent_accepts_operational_alias_as_model_output(self):
        result = nova_routing_support._coerce_tool_intent_payload(
            '{"tool":"runtime_status","args":[],"confidence":0.8}',
            user_text="tell me what is happening inside Nova right now",
        )

        self.assertEqual(result.get("tool"), "self_status")
        self.assertEqual(result.get("args"), [])

    def test_coerce_tool_intent_accepts_verified_identity_and_capability_tools(self):
        identity = nova_routing_support._coerce_tool_intent_payload(
            '{"tool":"nova_identity","args":[],"confidence":0.86}',
            user_text="tell me what you can verify about yourself",
        )
        capability = nova_routing_support._coerce_tool_intent_payload(
            '{"tool":"capabilities","args":[],"confidence":0.84}',
            user_text="tell me what you can actually do from your registry",
        )

        self.assertEqual(identity.get("tool"), "runtime_identity")
        self.assertEqual(identity.get("args"), [])
        self.assertEqual(capability.get("tool"), "capability_inventory")
        self.assertEqual(capability.get("args"), [])

    def test_coerce_tool_intent_accepts_operator_help_tool(self):
        result = nova_routing_support._coerce_tool_intent_payload(
            '{"tool":"help_needed","args":[],"confidence":0.86}',
            user_text="neutral user turn",
        )

        self.assertEqual(result.get("tool"), "operator_help")
        self.assertEqual(result.get("args"), [])

    def test_coerce_tool_intent_accepts_work_tree_tool(self):
        result = nova_routing_support._coerce_tool_intent_payload(
            '{"tool":"work_tree_status","args":[],"confidence":0.8}',
            user_text="show me the current work plan state",
        )

        self.assertEqual(result.get("tool"), "work_tree_status")
        self.assertEqual(result.get("args"), [])


if __name__ == "__main__":
    unittest.main()
