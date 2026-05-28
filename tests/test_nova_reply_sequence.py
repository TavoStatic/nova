import unittest
from types import SimpleNamespace
from unittest import mock

from services.nova_reply_sequence import (
    execute_http_reply_sequence_from_runtime,
    execute_reply_sequence,
    execute_reply_sequence_from_runtime,
)


def _core(**overrides):
    base = {
        "_llm_classify_routing_intent": lambda _text, **_kwargs: {"tool": "none", "args": [], "confidence": 0.9},
        "build_fallback_context_details": lambda _text, _turns, **_kwargs: {},
        "ollama_chat": lambda _text, retrieved_context="", language_mix_spanish_pct=0: "model reply",
        "execute_planned_action": lambda _tool, _args: "",
        "_web_allowlist_message": lambda resource: f"No access to {resource}",
        "behavior_set_flag": lambda *args, **kwargs: None,
        "action_ledger_add_step": lambda *args, **kwargs: None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


class TestNovaReplySequence(unittest.TestCase):
    def _call(self, text, **overrides):
        options = {
            "turns": [("user", "hello")],
            "text": text,
            "pending_action": None,
            "turn_acts": [],
            "prefer_web_for_data_queries": False,
            "language_mix_spanish_pct": 0,
            "session": None,
            "trace": lambda *args, **kwargs: None,
            "normalize_reply": lambda reply: reply,
            "ensure_reply": lambda reply: reply,
            "core": _core(),
        }
        options.update(overrides)
        return execute_reply_sequence(**options)

    def test_execute_reply_sequence_from_runtime_delegates_to_current_sequence_shape(self):
        runtime_scope = {"deleted_phrase_callbacks": object()}

        with mock.patch(
            "services.nova_reply_sequence.execute_reply_sequence",
            return_value=("ok", {"planner_decision": "llm_fallback"}),
        ) as execute_mock:
            reply, meta = execute_reply_sequence_from_runtime(
                turns=[],
                text="hello",
                pending_action=None,
                turn_acts=["chat"],
                prefer_web_for_data_queries=False,
                language_mix_spanish_pct=0,
                session=None,
                trace=lambda *args, **kwargs: None,
                normalize_reply=lambda reply: reply,
                ensure_reply=lambda reply: reply,
                core=_core(),
                runtime_scope=runtime_scope,
                stop_before_llm_fallback=True,
                work_tree_seed_source="http",
            )

        self.assertEqual(reply, "ok")
        self.assertEqual(meta.get("planner_decision"), "llm_fallback")
        self.assertEqual(execute_mock.call_args.kwargs.get("turn_acts"), ["chat"])
        self.assertTrue(execute_mock.call_args.kwargs.get("stop_before_llm_fallback"))
        self.assertEqual(execute_mock.call_args.kwargs.get("work_tree_seed_source"), "http")
        self.assertNotIn("is_developer_profile_request", execute_mock.call_args.kwargs)

    def test_execute_http_reply_sequence_from_runtime_builds_http_normalizer(self):
        runtime_scope = {"_strip_ui_tip_leak": lambda text: text.replace(" UI-TIP", "")}

        with mock.patch(
            "services.nova_reply_sequence.execute_reply_sequence_from_runtime",
            return_value=("ok", {"planner_decision": "llm_fallback"}),
        ) as execute_mock:
            reply, meta = execute_http_reply_sequence_from_runtime(
                turns=[],
                text="hello",
                ledger_record={"turn_acts": ["tool_probe"]},
                pending_action=None,
                prefer_web_for_data_queries=False,
                language_mix_spanish_pct=0,
                session=None,
                ensure_reply=lambda reply: f"ENSURE:{reply}",
                core=_core(),
                runtime_scope=runtime_scope,
            )

        self.assertEqual(reply, "ok")
        self.assertEqual(meta.get("planner_decision"), "llm_fallback")
        normalize_reply = execute_mock.call_args.kwargs.get("normalize_reply")
        self.assertEqual(normalize_reply("draft UI-TIP"), "ENSURE:draft")
        self.assertEqual(execute_mock.call_args.kwargs.get("turn_acts"), ["tool_probe"])

    def test_semantic_tool_result_returns_route_evidence_and_execution_profile(self):
        core = _core(
            _llm_classify_routing_intent=lambda _text, **_kwargs: {
                "tool": "web_fetch",
                "args": ["http://127.0.0.1:8080/control"],
                "confidence": 0.93,
                "reason": "inspect requested URL",
            },
            execute_planned_action=lambda tool, args: "FETCHED_CONTROL" if tool == "web_fetch" else "",
        )

        reply, meta = self._call("can you access http://127.0.0.1:8080/control", core=core)

        self.assertEqual(reply, "FETCHED_CONTROL")
        self.assertEqual(meta.get("planner_decision"), "run_tool")
        self.assertEqual(meta.get("tool"), "web_fetch")
        self.assertEqual((meta.get("route_evidence") or {}).get("planner_tool"), "web_fetch")
        self.assertIn("execution_profile", meta.get("reply_outcome") or {})

    def test_structured_tool_selection_executes_even_when_confidence_metadata_is_empty(self):
        core = _core(
            _llm_classify_routing_intent=lambda _text, **_kwargs: {
                "tool": "web_fetch",
                "args": ["http://127.0.0.1:8080/control"],
                "confidence": 0.0,
                "reason": "",
            },
            execute_planned_action=lambda tool, args: "FETCHED_CONTROL" if tool == "web_fetch" else "",
            ollama_chat=lambda *_args, **_kwargs: "MODEL_SHOULD_NOT_RUN",
        )

        reply, meta = self._call("can you access http://127.0.0.1:8080/control", core=core)

        self.assertEqual(reply, "FETCHED_CONTROL")
        self.assertEqual(meta.get("planner_decision"), "run_tool")
        self.assertEqual(meta.get("tool"), "web_fetch")
        self.assertTrue(meta.get("grounded"))

    def test_no_confidence_status_route_falls_back_to_conversation(self):
        core = _core(
            _llm_classify_routing_intent=lambda _text, **_kwargs: {
                "tool": "self_status",
                "args": [],
                "confidence": 0.0,
                "reason": "",
            },
            execute_planned_action=lambda tool, args: "LIVE_STATUS" if tool == "self_status" else "",
            ollama_chat=lambda *_args, **_kwargs: "MODEL_REPLY",
        )

        reply, meta = self._call("what is your current status?", core=core)

        self.assertIn("MODEL_REPLY", reply)
        self.assertEqual(meta.get("planner_decision"), "llm_fallback")
        self.assertEqual(meta.get("tool"), "")
        self.assertNotEqual((meta.get("reply_outcome") or {}).get("reply_contract"), "self_status.current")

    def test_weak_status_route_does_not_feed_stale_tool_evidence_to_conversation(self):
        captured = {}

        def _chat(_text, retrieved_context="", language_mix_spanish_pct=0, reply_form=""):
            captured["context"] = retrieved_context
            captured["reply_form"] = reply_form
            return "I missed the conversation intent there."

        core = _core(
            _llm_classify_routing_intent=lambda _text, **_kwargs: {
                "tool": "self_status",
                "args": [],
                "confidence": 0.0,
                "reason": "",
                "answer_target": "current_conversation",
                "evidence_need": "conversation",
            },
            build_fallback_context_details=lambda text, turns, **_kwargs: {
                "chat_context": "Assistant returned a tool result.",
                "state_context": "ACTIVE SESSION STATE: last_tool_evidence / self_status\nLast tool evidence:\nPrevious Nova Self Status",
            },
            execute_planned_action=lambda tool, args: "LIVE_STATUS" if tool == "self_status" else "",
            ollama_chat=_chat,
        )

        reply, meta = self._call("are you feeling better?", core=core)

        self.assertEqual(reply, "I missed the conversation intent there.")
        self.assertEqual(meta.get("planner_decision"), "llm_fallback")
        self.assertEqual(meta.get("tool"), "")
        self.assertEqual(captured.get("reply_form"), "conversation_turn")
        self.assertNotIn("Previous Nova Self Status", captured.get("context"))

    def test_status_followup_does_not_reuse_prior_self_status_without_current_live_intent(self):
        captured = {}
        executed = []

        def _intent(text, **_kwargs):
            if text == "are you feeling better?":
                return {
                    "tool": "self_status",
                    "args": [],
                    "confidence": 0.92,
                    "reason": "live state evidence",
                    "answer_target": "nova_live_state",
                    "evidence_need": "live_self_status",
                }
            return {
                "tool": "self_status",
                "args": [],
                "confidence": 0.0,
                "reason": "conversation follow-up",
                "answer_target": "current_conversation",
                "evidence_need": "conversation",
            }

        def _execute(tool, args):
            executed.append((tool, list(args or [])))
            return "Previous Nova Self Status"

        def _chat(text, retrieved_context="", language_mix_spanish_pct=0, reply_form=""):
            captured[text] = retrieved_context
            return "conversation reply"

        core = _core(
            _llm_classify_routing_intent=_intent,
            execute_planned_action=_execute,
            build_fallback_context_details=lambda text, turns, **_kwargs: {
                "chat_context": "Recent conversation only.",
                "state_context": (
                    "ACTIVE SESSION STATE: last_tool_evidence / self_status\n"
                    "Prior tool evidence: context only\n"
                    "Previous Nova Self Status"
                ),
            },
            ollama_chat=_chat,
        )

        _first_reply, first_meta = self._call(
            "are you feeling better?",
            core=core,
            stop_before_llm_fallback=True,
        )

        self.assertEqual(first_meta.get("tool"), "self_status")
        self.assertEqual(first_meta.get("tool_result"), "Previous Nova Self Status")
        self.assertEqual(executed, [("self_status", [])])

        session = SimpleNamespace(
            conversation_state={
                "kind": "last_tool_evidence",
                "tool": "self_status",
                "tool_result": "Previous Nova Self Status",
            }
        )

        second_reply, second_meta = self._call("what is done?", core=core, session=session)

        self.assertEqual(second_reply, "conversation reply")
        self.assertEqual(second_meta.get("planner_decision"), "llm_fallback")
        self.assertEqual(second_meta.get("tool"), "")
        self.assertEqual(executed, [("self_status", [])])
        self.assertNotIn("Previous Nova Self Status", captured.get("what is done?", ""))
        self.assertNotIn("SESSION EVIDENCE", captured.get("what is done?", ""))

    def test_live_status_tool_evidence_is_synthesized_by_fallback(self):
        captured = {}

        def _chat(_text, retrieved_context="", language_mix_spanish_pct=0):
            captured["context"] = retrieved_context
            return "You can help by reviewing the current blocker."

        core = _core(
            _llm_classify_routing_intent=lambda _text, **_kwargs: {
                "tool": "self_status",
                "args": [],
                "confidence": 0.92,
                "reason": "live state evidence",
                "answer_target": "nova_live_state",
                "evidence_need": "live_self_status",
            },
            execute_planned_action=lambda tool, args: "LIVE_STATUS" if tool == "self_status" else "",
            ollama_chat=_chat,
        )

        reply, meta = self._call("how can I help you get better?", core=core)

        self.assertEqual(reply, "You can help by reviewing the current blocker.")
        self.assertEqual(meta.get("planner_decision"), "llm_fallback")
        self.assertEqual(meta.get("tool"), "self_status")
        self.assertEqual(meta.get("tool_result"), "LIVE_STATUS")
        self.assertTrue(meta.get("grounded"))
        self.assertIn("LIVE_STATUS", captured.get("context"))
        self.assertEqual(((meta.get("reply_outcome") or {}).get("deferred_tool") or {}).get("tool"), "self_status")

    def test_stop_before_fallback_carries_deferred_status_evidence(self):
        core = _core(
            _llm_classify_routing_intent=lambda _text, **_kwargs: {
                "tool": "self_status",
                "args": [],
                "confidence": 0.92,
                "reason": "live state evidence",
                "answer_target": "nova_live_state",
                "evidence_need": "live_self_status",
            },
            execute_planned_action=lambda tool, args: "LIVE_STATUS" if tool == "self_status" else "",
            ollama_chat=lambda *_args, **_kwargs: "MODEL_SHOULD_NOT_RUN",
        )

        reply, meta = self._call("what is troubling you today?", core=core, stop_before_llm_fallback=True)

        self.assertEqual(reply, "")
        self.assertEqual(meta.get("planner_decision"), "unhandled")
        self.assertEqual(meta.get("tool"), "self_status")
        self.assertEqual(meta.get("tool_result"), "LIVE_STATUS")
        self.assertEqual((meta.get("semantic_tool_observation") or {}).get("status"), "tool_result_available")

    def test_semantic_none_flows_to_model_fallback_without_content_hooks(self):
        core = _core(
            _llm_classify_routing_intent=lambda _text, **_kwargs: {
                "tool": "none",
                "args": [],
                "confidence": 0.91,
                "reason": "conversation",
            },
            build_fallback_context_details=lambda text, turns, **_kwargs: {"context": "CURRENT CHAT CONTEXT"},
            ollama_chat=lambda text, retrieved_context="", language_mix_spanish_pct=0: f"MODEL:{text}|{retrieved_context}",
        )

        reply, meta = self._call("hi nova", core=core)

        self.assertIn("MODEL:hi nova|", reply)
        self.assertIn("NOVA INTERNAL EVIDENCE SUMMARY", reply)
        self.assertNotIn("available_evidence", reply)
        self.assertIn("CURRENT CHAT CONTEXT", reply)
        self.assertEqual(meta.get("planner_decision"), "llm_fallback")
        self.assertEqual(meta.get("tool"), "")
        self.assertEqual(
            ((meta.get("reply_outcome") or {}).get("intent_evidence_packet") or {}).get("trace_authority"),
            "hypothesis_only",
        )

    def test_semantic_self_evidence_need_returns_evidence_bound_reply_before_model(self):
        core = _core(
            _llm_classify_routing_intent=lambda _text, **_kwargs: {
                "tool": "none",
                "args": [],
                "confidence": 0.9,
                "reason": "self evidence",
                "evidence_need": "operational_self",
                "answer_target": "nova_self",
            },
            build_fallback_context_details=lambda text, turns, **_kwargs: {
                "context": "",
                "learning_context": (
                    "Identity fact: assistant_name=Nova\n"
                    "Identity fact: developer_name=Gustavo Uribe\n"
                    "Identity fact: developer_nickname=Gus\n"
                    "Operational Nova self evidence:\n"
                    "Registered internal surfaces observed from the capability registry:\n"
                    "- runtime_core: Nova runs as a local runtime\n"
                    "- work_tree: Nova can organize internal work\n"
                ),
                "identity_used": True,
                "identity_chars": 90,
                "operational_identity_used": True,
                "operational_identity_chars": 120,
            },
            ollama_chat=lambda *_args, **_kwargs: "MODEL_SHOULD_NOT_RUN",
        )

        reply, meta = self._call("what are you?", core=core)

        self.assertIn("I am Nova", reply)
        self.assertIn("Gustavo Uribe", reply)
        self.assertNotIn("MODEL_SHOULD_NOT_RUN", reply)
        self.assertEqual(meta.get("planner_decision"), "evidence_bound_reply")
        self.assertTrue(meta.get("grounded"))

    def test_stop_before_llm_fallback_returns_unhandled_after_semantic_none(self):
        reply, meta = self._call(
            "open ended",
            core=_core(),
            stop_before_llm_fallback=True,
        )

        self.assertEqual(reply, "")
        self.assertEqual(meta.get("planner_decision"), "unhandled")
        self.assertEqual((meta.get("semantic_tool_observation") or {}).get("status"), "none")

    def test_planner_timing_is_included_in_execution_profile(self):
        planner_meta = {
            "planner_decision": "run_tool",
            "tool": "web_research",
            "tool_args": {"args": ["student_data"]},
            "tool_result": "Grounded result",
            "grounded": True,
            "timing": {"planner_time": 1200, "tool_selection_time": 300, "tool_time": 900},
        }
        perf_values = iter([0, 0, 0.1, 1.2])

        with mock.patch(
            "services.nova_reply_sequence.nova_planner_contract.maybe_handle_planner_sequence",
            return_value=("Grounded result", planner_meta),
        ), mock.patch("services.nova_reply_sequence.time.perf_counter", side_effect=lambda: next(perf_values)):
            reply, meta = self._call("research student_data")

        self.assertEqual(reply, "Grounded result")
        profile = (meta.get("reply_outcome") or {}).get("execution_profile") or {}
        self.assertEqual(profile.get("planner_time"), 1200)
        self.assertEqual(profile.get("tool_selection_time"), 300)
        self.assertEqual(profile.get("tool_time"), 900)
        self.assertEqual(profile.get("llm_time"), 0)

    def test_llm_fallback_records_execution_profile_and_slow_llm_trace(self):
        trace_calls = []
        perf_values = iter([0, 0, 0, 0, 25, 25, 27, 27])

        with mock.patch(
            "services.nova_reply_sequence.nova_planner_contract.maybe_handle_planner_sequence",
            return_value=None,
        ), mock.patch(
            "services.nova_reply_sequence.time.perf_counter",
            side_effect=lambda: next(perf_values),
        ):
            reply, meta = self._call(
                "tell me something open ended",
                core=_core(ollama_chat=lambda _text, retrieved_context="", language_mix_spanish_pct=0: "slow reply"),
                trace=lambda *args, **kwargs: trace_calls.append((args, kwargs)),
            )

        self.assertEqual(reply, "slow reply")
        profile = (meta.get("reply_outcome") or {}).get("execution_profile") or {}
        self.assertEqual(profile.get("llm_time"), 25000)
        self.assertEqual(profile.get("post_time"), 2000)
        self.assertEqual(profile.get("total_time"), 27000)
        self.assertTrue(any(args[:3] == ("llm_call", "slow", "llm_call_slow") for args, _kwargs in trace_calls))


if __name__ == "__main__":
    unittest.main()
