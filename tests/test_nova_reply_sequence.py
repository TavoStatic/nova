import unittest
from types import SimpleNamespace

from services.nova_reply_sequence import execute_reply_sequence


class TestNovaReplySequence(unittest.TestCase):
    def _call(self, text, **overrides):
        core = SimpleNamespace(
            truth_hierarchy_answer=lambda _text: (False, "", "", False),
            hard_answer=lambda _text: None,
            decide_actions=lambda _text, config=None: [],
            analyze_request=lambda _text, config=None: SimpleNamespace(allow_llm=False, message="blocked"),
            build_fallback_context_details=lambda _text, _turns: {},
            should_block_low_confidence=lambda _text, retrieved_context="": False,
            _truthful_limit_outcome=lambda _text: {},
            _truthful_limit_reply=lambda _text: "",
            ollama_chat=lambda _text, retrieved_context="", language_mix_spanish_pct=0: "",
            sanitize_llm_reply=lambda reply, _tool: reply,
            _apply_claim_gate=lambda reply, evidence_text="", tool_context="": (reply, False, ""),
            _attach_learning_invitation=lambda reply: reply,
            _is_developer_color_lookup_request=lambda _text: False,
            _is_developer_bilingual_request=lambda _text: False,
            _is_color_lookup_request=lambda _text: False,
        )
        options = {
            "turns": [("user", "hello"), ("assistant", "Hi there")],
            "text": text,
            "pending_action": None,
            "prefer_web_for_data_queries": False,
            "language_mix_spanish_pct": 0,
            "session": None,
            "trace": lambda *args, **kwargs: None,
            "normalize_reply": lambda reply: reply,
            "ensure_reply": lambda reply: reply,
            "core": core,
            "is_developer_profile_request": lambda _text: False,
            "developer_profile_reply": lambda turns, user_text: "developer profile",
            "is_location_request": lambda _text: False,
            "location_reply": lambda: "location reply",
            "is_web_preferred_data_query": lambda _text: False,
            "is_session_recap_request": lambda _text: False,
            "session_recap_reply": lambda turns, user_text: "Recap of this session.",
            "is_assistant_name_query": lambda _text: False,
            "assistant_name_reply": lambda user_text: "My name is Nova.",
            "is_developer_full_name_query": lambda _text: False,
            "developer_full_name_reply": lambda: "Gustavo Rivera",
            "is_name_origin_question": lambda _text: False,
            "is_peims_attendance_rules_query": lambda _text: False,
            "peims_attendance_rules_reply": lambda: "attendance reply",
            "is_conversational_clarification": lambda _text: False,
            "clarification_reply": lambda turns: "clarify",
            "is_deep_search_followup_request": lambda _text: False,
            "infer_research_query_from_turns": lambda turns: "",
            "build_grounded_answer": lambda query, max_sources=2: "",
            "build_local_topic_digest_answer": lambda query: "",
            "is_groundable_factual_query": lambda _text: False,
            "developer_color_reply": lambda turns: "developer color",
            "developer_bilingual_reply": lambda turns: "developer bilingual",
            "color_reply": lambda turns: "color reply",
            "animal_reply": lambda turns: "animal reply",
        }
        options.update(overrides)
        return execute_reply_sequence(**options)

    def test_session_recap_beats_planner_run_tool(self):
        core = SimpleNamespace(
            truth_hierarchy_answer=lambda _text: (False, "", "", False),
            hard_answer=lambda _text: None,
            decide_actions=lambda _text, config=None: [{"type": "run_tool", "tool": "queue_status", "args": []}],
            analyze_request=lambda _text, config=None: SimpleNamespace(allow_llm=False, message="blocked"),
            build_fallback_context_details=lambda _text, _turns: {},
            should_block_low_confidence=lambda _text, retrieved_context="": False,
            _truthful_limit_outcome=lambda _text: {},
            _truthful_limit_reply=lambda _text: "",
            ollama_chat=lambda _text, retrieved_context="", language_mix_spanish_pct=0: "",
            sanitize_llm_reply=lambda reply, _tool: reply,
            _apply_claim_gate=lambda reply, evidence_text="", tool_context="": (reply, False, ""),
            _attach_learning_invitation=lambda reply: reply,
            _is_developer_color_lookup_request=lambda _text: False,
            _is_developer_bilingual_request=lambda _text: False,
            _is_color_lookup_request=lambda _text: False,
        )
        reply, meta = self._call(
            "give me a recap of this entire chat session nova",
            core=core,
            is_session_recap_request=lambda _text: True,
        )
        self.assertEqual(reply, "Recap of this session.")
        self.assertEqual(meta.get("planner_decision"), "deterministic")
        self.assertEqual(meta.get("tool"), "session_recap")

    def test_planner_run_tool_still_handles_unmatched_turns(self):
        core = SimpleNamespace(
            truth_hierarchy_answer=lambda _text: (False, "", "", False),
            hard_answer=lambda _text: None,
            decide_actions=lambda _text, config=None: [{"type": "run_tool", "tool": "queue_status", "args": []}],
            execute_planned_action=lambda tool, args: "Standing work queue",
            _web_allowlist_message=lambda subject: f"No access to {subject}",
            handle_commands=lambda text, session_turns=None, session=None: "",
            handle_keywords=lambda text: None,
            tool_web_research=lambda text: "",
            analyze_request=lambda _text, config=None: SimpleNamespace(allow_llm=False, message="blocked"),
            build_fallback_context_details=lambda _text, _turns: {},
            should_block_low_confidence=lambda _text, retrieved_context="": False,
            _truthful_limit_outcome=lambda _text: {},
            _truthful_limit_reply=lambda _text: "",
            ollama_chat=lambda _text, retrieved_context="", language_mix_spanish_pct=0: "",
            sanitize_llm_reply=lambda reply, _tool: reply,
            _apply_claim_gate=lambda reply, evidence_text="", tool_context="": (reply, False, ""),
            _attach_learning_invitation=lambda reply: reply,
            _is_developer_color_lookup_request=lambda _text: False,
            _is_developer_bilingual_request=lambda _text: False,
            _is_color_lookup_request=lambda _text: False,
            make_pending_weather_action=lambda: {},
        )
        reply, meta = self._call("what should you work on next", core=core)
        self.assertEqual(reply, "Standing work queue")
        self.assertEqual(meta.get("planner_decision"), "run_tool")
        self.assertEqual(meta.get("tool"), "queue_status")

    def test_developer_profile_beats_planner_wikipedia_route(self):
        core = SimpleNamespace(
            truth_hierarchy_answer=lambda _text: (False, "", "", False),
            hard_answer=lambda _text: None,
            decide_actions=lambda _text, config=None: [{"type": "run_tool", "tool": "wikipedia_lookup", "args": ["who is gus ?"]}],
            execute_planned_action=lambda tool, args: "Wikipedia summary for Gus" if tool == "wikipedia_lookup" else "",
            _web_allowlist_message=lambda subject: f"No access to {subject}",
            handle_commands=lambda text, session_turns=None, session=None: "",
            handle_keywords=lambda text: None,
            tool_web_research=lambda text: "",
            analyze_request=lambda _text, config=None: SimpleNamespace(allow_llm=False, message="blocked"),
            build_fallback_context_details=lambda _text, _turns: {},
            should_block_low_confidence=lambda _text, retrieved_context="": False,
            _truthful_limit_outcome=lambda _text: {},
            _truthful_limit_reply=lambda _text: "",
            ollama_chat=lambda _text, retrieved_context="", language_mix_spanish_pct=0: "",
            sanitize_llm_reply=lambda reply, _tool: reply,
            _apply_claim_gate=lambda reply, evidence_text="", tool_context="": (reply, False, ""),
            _attach_learning_invitation=lambda reply: reply,
            _is_developer_color_lookup_request=lambda _text: False,
            _is_developer_bilingual_request=lambda _text: False,
            _is_color_lookup_request=lambda _text: False,
            make_pending_weather_action=lambda: {},
        )

        reply, meta = self._call(
            "who is gus ?",
            core=core,
            is_developer_profile_request=lambda _text: True,
            developer_profile_reply=lambda turns, user_text: "My developer is Gustavo Uribe. Gus is his nickname. He created me.",
        )

        self.assertIn("Gustavo", reply)
        self.assertEqual(meta.get("planner_decision"), "deterministic")
        self.assertEqual(meta.get("tool"), "developer_profile")

    def test_peims_attendance_beats_planner_web_research_route(self):
        core = SimpleNamespace(
            truth_hierarchy_answer=lambda _text: (False, "", "", False),
            hard_answer=lambda _text: None,
            decide_actions=lambda _text, config=None: [{"type": "run_tool", "tool": "web_research", "args": ["PEIMS attendance rules"]}],
            execute_planned_action=lambda tool, args: "web research summary" if tool == "web_research" else "",
            _web_allowlist_message=lambda subject: f"No access to {subject}",
            handle_commands=lambda text, session_turns=None, session=None: "",
            handle_keywords=lambda text: None,
            tool_web_research=lambda text: "",
            analyze_request=lambda _text, config=None: SimpleNamespace(allow_llm=False, message="blocked"),
            build_fallback_context_details=lambda _text, _turns: {},
            should_block_low_confidence=lambda _text, retrieved_context="": False,
            _truthful_limit_outcome=lambda _text: {},
            _truthful_limit_reply=lambda _text: "",
            ollama_chat=lambda _text, retrieved_context="", language_mix_spanish_pct=0: "",
            sanitize_llm_reply=lambda reply, _tool: reply,
            _apply_claim_gate=lambda reply, evidence_text="", tool_context="": (reply, False, ""),
            _attach_learning_invitation=lambda reply: reply,
            _is_developer_color_lookup_request=lambda _text: False,
            _is_developer_bilingual_request=lambda _text: False,
            _is_color_lookup_request=lambda _text: False,
            make_pending_weather_action=lambda: {},
        )

        reply, meta = self._call(
            "What are the attendance reporting rules for PEIMS?",
            core=core,
            is_peims_attendance_rules_query=lambda _text: True,
            peims_attendance_rules_reply=lambda: "Attendance data must be reported daily. [source: tea.texas.gov]",
        )

        self.assertIn("Attendance data", reply)
        self.assertEqual(meta.get("planner_decision"), "grounded_lookup")
        self.assertEqual(meta.get("tool"), "peims_attendance")

    def test_location_reply_beats_planner_weather_route(self):
        core = SimpleNamespace(
            truth_hierarchy_answer=lambda _text: (False, "", "", False),
            hard_answer=lambda _text: None,
            decide_actions=lambda _text, config=None: [{"type": "run_tool", "tool": "weather_current_location", "args": []}],
            execute_planned_action=lambda tool, args: "weather reply" if tool == "weather_current_location" else "",
            _web_allowlist_message=lambda subject: f"No access to {subject}",
            handle_commands=lambda text, session_turns=None, session=None: "",
            handle_keywords=lambda text: None,
            tool_web_research=lambda text: "",
            analyze_request=lambda _text, config=None: SimpleNamespace(allow_llm=False, message="blocked"),
            build_fallback_context_details=lambda _text, _turns: {},
            should_block_low_confidence=lambda _text, retrieved_context="": False,
            _truthful_limit_outcome=lambda _text: {},
            _truthful_limit_reply=lambda _text: "",
            ollama_chat=lambda _text, retrieved_context="", language_mix_spanish_pct=0: "",
            sanitize_llm_reply=lambda reply, _tool: reply,
            _apply_claim_gate=lambda reply, evidence_text="", tool_context="": (reply, False, ""),
            _attach_learning_invitation=lambda reply: reply,
            _is_developer_color_lookup_request=lambda _text: False,
            _is_developer_bilingual_request=lambda _text: False,
            _is_color_lookup_request=lambda _text: False,
            make_pending_weather_action=lambda: {},
        )

        reply, meta = self._call(
            "where am i right now?",
            core=core,
            is_location_request=lambda _text: True,
            location_reply=lambda: "You appear to be in Brownsville, Texas.",
        )

        self.assertIn("Brownsville", reply)
        self.assertEqual(meta.get("planner_decision"), "deterministic")
        self.assertEqual(meta.get("tool"), "location")

    def test_assistant_name_beats_planner_wikipedia_route(self):
        core = SimpleNamespace(
            truth_hierarchy_answer=lambda _text: (False, "", "", False),
            hard_answer=lambda _text: None,
            decide_actions=lambda _text, config=None: [{"type": "run_tool", "tool": "wikipedia_lookup", "args": ["Nova"]}],
            execute_planned_action=lambda tool, args: "Wikipedia summary for Nova" if tool == "wikipedia_lookup" else "",
            _web_allowlist_message=lambda subject: f"No access to {subject}",
            handle_commands=lambda text, session_turns=None, session=None: "",
            handle_keywords=lambda text: None,
            tool_web_research=lambda text: "",
            analyze_request=lambda _text, config=None: SimpleNamespace(allow_llm=False, message="blocked"),
            build_fallback_context_details=lambda _text, _turns: {},
            should_block_low_confidence=lambda _text, retrieved_context="": False,
            _truthful_limit_outcome=lambda _text: {},
            _truthful_limit_reply=lambda _text: "",
            ollama_chat=lambda _text, retrieved_context="", language_mix_spanish_pct=0: "",
            sanitize_llm_reply=lambda reply, _tool: reply,
            _apply_claim_gate=lambda reply, evidence_text="", tool_context="": (reply, False, ""),
            _attach_learning_invitation=lambda reply: reply,
            _is_developer_color_lookup_request=lambda _text: False,
            _is_developer_bilingual_request=lambda _text: False,
            _is_color_lookup_request=lambda _text: False,
            make_pending_weather_action=lambda: {},
        )

        reply, meta = self._call(
            "what is your name?",
            core=core,
            is_assistant_name_query=lambda _text: True,
            assistant_name_reply=lambda _text: "My name is Nova.",
        )

        self.assertEqual(reply, "My name is Nova.")
        self.assertEqual(meta.get("planner_decision"), "deterministic")
        self.assertEqual(meta.get("tool"), "assistant_name")

    def test_planner_can_run_before_deterministic_content_when_requested(self):
        core = SimpleNamespace(
            truth_hierarchy_answer=lambda _text: (False, "", "", False),
            hard_answer=lambda _text: None,
            decide_actions=lambda _text, config=None: [{"type": "run_tool", "tool": "wikipedia_lookup", "args": ["Nova"]}],
            execute_planned_action=lambda tool, args: "Wikipedia summary for Nova" if tool == "wikipedia_lookup" else "",
            _web_allowlist_message=lambda subject: f"No access to {subject}",
            handle_commands=lambda text, session_turns=None, session=None: "",
            handle_keywords=lambda text: None,
            tool_web_research=lambda text: "",
            analyze_request=lambda _text, config=None: SimpleNamespace(allow_llm=False, message="blocked"),
            build_fallback_context_details=lambda _text, _turns: {},
            should_block_low_confidence=lambda _text, retrieved_context="": False,
            _truthful_limit_outcome=lambda _text: {},
            _truthful_limit_reply=lambda _text: "",
            ollama_chat=lambda _text, retrieved_context="", language_mix_spanish_pct=0: "",
            sanitize_llm_reply=lambda reply, _tool: reply,
            _apply_claim_gate=lambda reply, evidence_text="", tool_context="": (reply, False, ""),
            _attach_learning_invitation=lambda reply: reply,
            _is_developer_color_lookup_request=lambda _text: False,
            _is_developer_bilingual_request=lambda _text: False,
            _is_color_lookup_request=lambda _text: False,
            make_pending_weather_action=lambda: {},
        )

        reply, meta = self._call(
            "what is your name?",
            core=core,
            is_assistant_name_query=lambda _text: True,
            assistant_name_reply=lambda _text: "My name is Nova.",
            planner_before_deterministic_content=True,
        )

        self.assertEqual(reply, "Wikipedia summary for Nova")
        self.assertEqual(meta.get("planner_decision"), "run_tool")
        self.assertEqual(meta.get("tool"), "wikipedia_lookup")