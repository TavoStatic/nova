import json
import unittest

from services import nova_routing_support


class TestNovaRoutingSupport(unittest.TestCase):
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

    def test_build_routing_decision_records_phases_without_bypass_contract(self):
        decision = nova_routing_support.build_routing_decision(
            "Need weather help",
            entry_point="http",
            intent_result={"matched_rule_name": "weather_intent", "intent": "weather_lookup"},
            handle_result={"matched_rule_name": "weather_handle", "action": "run_tool"},
            final_owner="fallback",
            reply_contract="weather_lookup",
            reply_outcome={"kind": "weather_lookup"},
            turn_acts=["weather"],
            intent_trace_preview_fn=lambda text: text[:12],
            supervisor_phase_record_fn=lambda payload, phase: {"phase": phase, "handled": bool(payload)},
        )

        self.assertEqual(decision["input_preview"], "Need weather")
        self.assertEqual(decision["entry_point"], "http")
        self.assertEqual(decision["intent_phase"], {"phase": "intent", "handled": True})
        self.assertEqual(decision["handle_phase"], {"phase": "handle", "handled": True})
        self.assertEqual(decision["reply_outcome_kind"], "weather_lookup")
        self.assertEqual(decision["turn_acts"], ["weather"])
        self.assertNotIn("allowed_bypass", decision)

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
            "Now tell me why that answer was confusing.",
            live_ollama_calls_allowed_fn=_live_gate,
            chat_model_fn=lambda: "llama3.2:3b",
            ollama_base="http://127.0.0.1:11434",
            get_saved_location_text_fn=lambda: "Brownsville, Texas",
            requests_post_fn=lambda *args, **kwargs: _Resp(),
        )

        self.assertIsNone(result)
        self.assertEqual(called["live_gate"], 1)

    def test_routing_prompt_keeps_tools_bound_to_evidence_gap(self):
        prompt = nova_routing_support.ROUTING_INTENT_PROMPT

        self.assertIn("Do not classify from keywords or surface phrasing", prompt)
        self.assertIn("current turn is the primary evidence for intent", prompt)
        self.assertIn("evidence needed to answer is outside the current conversation/session", prompt)
        self.assertIn("previous assistant reply or its provenance", prompt)
        self.assertIn("evidence_need", prompt)

    def test_llm_classify_routing_intent_can_return_explicit_none_payload(self):
        class _Resp:
            def raise_for_status(self):
                pass

            def json(self):
                return {"message": {"content": '{"tool":"none","args":[],"confidence":0.84,"reason":"conversation"}'}}

        result = nova_routing_support.llm_classify_routing_intent(
            "Now tell me why that answer was confusing.",
            return_none_payload=True,
            live_ollama_calls_allowed_fn=lambda: True,
            chat_model_fn=lambda: "llama3.2:3b",
            ollama_base="http://127.0.0.1:11434",
            get_saved_location_text_fn=lambda: "Brownsville, Texas",
            requests_post_fn=lambda *args, **kwargs: _Resp(),
        )

        self.assertEqual(result.get("tool"), "none")
        self.assertEqual(result.get("args"), [])
        self.assertEqual(result.get("evidence_need"), "conversation")

    def test_none_payload_with_conversation_evidence_normalizes_to_current_conversation(self):
        result = nova_routing_support._coerce_tool_intent_payload(
            '{"answer_target":"external_world","evidence_need":"conversation","tool":null,"args":[],"confidence":0.0}',
            user_text="hi nova",
            return_none_payload=True,
        )

        self.assertEqual(result.get("tool"), "none")
        self.assertEqual(result.get("evidence_need"), "conversation")
        self.assertEqual(result.get("answer_target"), "current_conversation")

    def test_structured_url_routes_to_fetch_when_classifier_omits_tool(self):
        result = nova_routing_support._coerce_tool_intent_payload(
            '{"answer_target":"external_world","evidence_need":"conversation","tool":null,"args":[],"confidence":0.0}',
            user_text="can you access http://127.0.0.1:8080/control",
            return_none_payload=True,
        )

        self.assertEqual(result.get("tool"), "web_fetch")
        self.assertEqual(result.get("args"), ["http://127.0.0.1:8080/control"])
        self.assertEqual(result.get("evidence_need"), "external_source")
        self.assertEqual(result.get("answer_target"), "external_world")

    def test_llm_classify_routing_intent_reads_json_from_prose_envelope(self):
        class _Resp:
            def raise_for_status(self):
                pass

            def json(self):
                return {
                    "message": {
                        "content": (
                            "Here is the classification:\n\n"
                            "```json\n"
                            '{"answer_target":"nova_live_state","evidence_need":"live_self_status","tool":null,'
                            '"args":[],"confidence":0.78,"reason":"current operational state"}'
                            "\n```"
                        )
                    }
                }

        result = nova_routing_support.llm_classify_routing_intent(
            "what is troubling you today?",
            return_none_payload=True,
            live_ollama_calls_allowed_fn=lambda: True,
            chat_model_fn=lambda: "llama3.2:3b",
            ollama_base="http://127.0.0.1:11434",
            get_saved_location_text_fn=lambda: "",
            requests_post_fn=lambda *args, **kwargs: _Resp(),
        )

        self.assertEqual(result.get("tool"), "self_status")
        self.assertEqual(result.get("evidence_need"), "live_self_status")
        self.assertEqual(result.get("answer_target"), "nova_live_state")

    def test_coerce_tool_intent_does_not_turn_prose_into_tool_name(self):
        result = nova_routing_support._coerce_tool_intent_payload(
            "Here is the classification: not valid json",
            user_text="neutral user turn",
            return_none_payload=True,
        )

        self.assertEqual(result.get("tool"), "none")
        self.assertEqual(result.get("reason"), "malformed_intent_payload")

    def test_llm_classify_routing_intent_keeps_current_turn_out_of_recent_turns(self):
        captured = {}

        class _Resp:
            def raise_for_status(self):
                pass

            def json(self):
                return {"message": {"content": '{"tool":"none","args":[],"confidence":0.84,"reason":"conversation"}'}}

        def _post(_url, json=None, timeout=None):
            captured["payload"] = json
            return _Resp()

        nova_routing_support.llm_classify_routing_intent(
            "current turn",
            turns=[("user", "older turn"), ("assistant", "prior answer"), ("user", "current turn")],
            return_none_payload=True,
            live_ollama_calls_allowed_fn=lambda: True,
            chat_model_fn=lambda: "llama3.2:3b",
            ollama_base="http://127.0.0.1:11434",
            get_saved_location_text_fn=lambda: "",
            requests_post_fn=_post,
        )

        user_payload = json.loads(captured["payload"]["messages"][1]["content"])
        self.assertEqual(user_payload["turn"], "current turn")
        self.assertEqual(
            user_payload["recent_turns"],
            [
                {"role": "user", "content": "older turn"},
                {"role": "assistant", "content": "prior answer"},
            ],
        )

    def test_llm_classify_routing_intent_keeps_identity_evidence_need_without_tool(self):
        class _Resp:
            def raise_for_status(self):
                pass

            def json(self):
                return {
                    "message": {
                        "content": '{"answer_target":"nova_self","tool":"none","args":[],"confidence":0.82,"reason":"current-session self understanding","evidence_need":"operational_self"}'
                    }
                }

        result = nova_routing_support.llm_classify_routing_intent(
            "what are you?",
            return_none_payload=True,
            live_ollama_calls_allowed_fn=lambda: True,
            chat_model_fn=lambda: "llama3.2:3b",
            ollama_base="http://127.0.0.1:11434",
            get_saved_location_text_fn=lambda: "",
            requests_post_fn=lambda *args, **kwargs: _Resp(),
        )

        self.assertEqual(result.get("tool"), "none")
        self.assertEqual(result.get("evidence_need"), "operational_self")
        self.assertEqual(result.get("answer_target"), "nova_self")

    def test_llm_classify_routing_intent_promotes_live_status_target_to_tool(self):
        class _Resp:
            def raise_for_status(self):
                pass

            def json(self):
                return {
                    "message": {
                        "content": '{"answer_target":"nova_live_state","tool":"none","args":[],"confidence":0.76,"reason":"current live internal condition","evidence_need":"conversation"}'
                    }
                }

        result = nova_routing_support.llm_classify_routing_intent(
            "what is troubling you today?",
            return_none_payload=True,
            live_ollama_calls_allowed_fn=lambda: True,
            chat_model_fn=lambda: "llama3.2:3b",
            ollama_base="http://127.0.0.1:11434",
            get_saved_location_text_fn=lambda: "",
            requests_post_fn=lambda *args, **kwargs: _Resp(),
        )

        self.assertEqual(result.get("tool"), "self_status")
        self.assertEqual(result.get("evidence_need"), "live_self_status")
        self.assertEqual(result.get("answer_target"), "nova_live_state")

    def test_coerce_tool_intent_downgrades_identity_target_away_from_live_status_tool(self):
        result = nova_routing_support._coerce_tool_intent_payload(
            '{"answer_target":"nova_self","tool":"self_status","args":[],"confidence":0.5,"evidence_need":"live_self_status"}',
            user_text="identity question",
            return_none_payload=True,
        )

        self.assertEqual(result.get("tool"), "none")
        self.assertEqual(result.get("evidence_need"), "operational_self")
        self.assertEqual(result.get("answer_target"), "nova_self")

    def test_llm_classify_routing_intent_maps_weather_tool_goal(self):
        captured = {}

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
            live_ollama_calls_allowed_fn=lambda: True,
            chat_model_fn=lambda: "llama3.2:3b",
            ollama_base="http://127.0.0.1:11434",
            get_saved_location_text_fn=lambda: "Brownsville, Texas",
            requests_post_fn=_post,
        )

        self.assertEqual(result.get("tool"), "weather_current_location")
        self.assertEqual(result.get("args"), [])
        self.assertEqual(captured["payload"]["keep_alive"], "10m")

    def test_llm_classify_routing_intent_maps_live_self_status_goal(self):
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
            live_ollama_calls_allowed_fn=lambda: True,
            chat_model_fn=lambda: "llama3.2:3b",
            ollama_base="http://127.0.0.1:11434",
            get_saved_location_text_fn=lambda: "Brownsville, Texas",
            requests_post_fn=lambda *args, **kwargs: _Resp(),
        )

        self.assertEqual(result.get("tool"), "self_status")
        self.assertEqual(result.get("args"), [])

    def test_llm_classify_routing_intent_prefers_routing_model_when_provided(self):
        captured = {}

        class _Resp:
            def raise_for_status(self):
                pass

            def json(self):
                return {"message": {"content": '{"tool":"none","args":[],"confidence":0.9,"reason":"conversation"}'}}

        def _post(_url, json=None, timeout=None):
            captured["payload"] = json
            return _Resp()

        nova_routing_support.llm_classify_routing_intent(
            "tell me what is happening",
            return_none_payload=True,
            live_ollama_calls_allowed_fn=lambda: True,
            chat_model_fn=lambda: "chat-model",
            routing_model_fn=lambda: "routing-model",
            ollama_base="http://127.0.0.1:11434",
            get_saved_location_text_fn=lambda: "",
            requests_post_fn=_post,
        )

        self.assertEqual((captured.get("payload") or {}).get("model"), "routing-model")

    def test_coerce_tool_intent_rejects_removed_content_tools(self):
        for tool in ("runtime_identity", "capability_inventory", "operator_help", "grounded_self_report"):
            with self.subTest(tool=tool):
                result = nova_routing_support._coerce_tool_intent_payload(
                    f'{{"tool":"{tool}","args":[],"confidence":0.86}}',
                    user_text="neutral user turn",
                    return_none_payload=True,
                )
                self.assertEqual(result.get("tool"), "none")
                self.assertEqual(result.get("reason"), f"unsupported_tool:{tool}")

    def test_coerce_tool_intent_accepts_work_tree_tool(self):
        result = nova_routing_support._coerce_tool_intent_payload(
            '{"tool":"work_tree_status","args":[],"confidence":0.8}',
            user_text="show me the current work plan state",
        )

        self.assertEqual(result.get("tool"), "work_tree_status")
        self.assertEqual(result.get("args"), [])


if __name__ == "__main__":
    unittest.main()
