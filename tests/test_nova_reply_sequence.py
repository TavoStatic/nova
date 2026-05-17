import unittest
from types import SimpleNamespace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from services.nova_reply_sequence import execute_reply_sequence
from services.nova_reply_sequence import execute_http_reply_sequence_from_runtime
from services.nova_reply_sequence import execute_reply_sequence_from_runtime


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
            "is_student_data_attendance_rules_query": lambda _text: False,
            "student_data_attendance_rules_reply": lambda: "attendance reply",
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

    def test_execute_reply_sequence_from_runtime_resolves_http_callback_bundle(self):
        runtime_scope = {
            "_is_developer_profile_request": lambda _text: False,
            "_developer_profile_reply": lambda turns, user_text: "developer profile",
            "_is_location_request": lambda _text: False,
            "_location_reply": lambda: "location reply",
            "_is_session_recap_request": lambda _text: False,
            "_session_recap_reply": lambda turns, user_text: "session recap",
            "_is_assistant_name_query": lambda _text: False,
            "_assistant_name_reply": lambda user_text: "Nova",
            "_is_developer_full_name_query": lambda _text: False,
            "_developer_full_name_reply": lambda: "Gustavo Rivera",
            "_is_name_origin_question": lambda _text: False,
            "_peims_attendance_rules_reply": lambda: "attendance reply",
            "_is_deep_search_followup_request": lambda _text: False,
            "_infer_research_query_from_turns": lambda turns: "",
            "_build_grounded_answer": lambda query, max_sources=2: "",
            "_build_local_topic_digest_answer": lambda query: "",
            "_developer_color_reply": lambda turns: "developer color",
            "_developer_bilingual_reply": lambda turns: "developer bilingual",
            "_color_reply": lambda turns: "color reply",
            "_animal_reply": lambda turns: "animal reply",
            "nova_query_classifiers": SimpleNamespace(
                is_web_preferred_data_query=lambda _text: False,
                is_student_data_attendance_rules_query=lambda _text: False,
                is_conversational_clarification=lambda _text: False,
            ),
        }
        core = SimpleNamespace(_open_probe_reply=lambda prompt, turns=None: ("clarify", "probe"))

        with mock.patch(
            "services.nova_reply_sequence.execute_reply_sequence",
            return_value=("ok", {"planner_decision": "deterministic"}),
        ) as execute_mock:
            reply, meta = execute_reply_sequence_from_runtime(
                turns=[],
                text="hello",
                pending_action=None,
                prefer_web_for_data_queries=False,
                language_mix_spanish_pct=0,
                session=None,
                trace=lambda *args, **kwargs: None,
                normalize_reply=lambda reply: reply,
                ensure_reply=lambda reply: reply,
                core=core,
                runtime_scope=runtime_scope,
                pre_planner_branch_group="operational",
                post_planner_branch_group="general",
            )

        self.assertEqual(reply, "ok")
        self.assertEqual(meta.get("planner_decision"), "deterministic")
        self.assertIs(execute_mock.call_args.kwargs.get("is_developer_profile_request"), runtime_scope["_is_developer_profile_request"])
        self.assertIs(execute_mock.call_args.kwargs.get("developer_profile_reply"), runtime_scope["_developer_profile_reply"])
        self.assertEqual(execute_mock.call_args.kwargs.get("pre_planner_branch_group"), "operational")
        self.assertEqual(execute_mock.call_args.kwargs.get("post_planner_branch_group"), "general")

    def test_execute_http_reply_sequence_from_runtime_builds_http_normalizer(self):
        runtime_scope = {
            "_strip_ui_tip_leak": lambda text: text.replace(" UI-TIP", ""),
            "_is_developer_profile_request": lambda _text: False,
            "_developer_profile_reply": lambda turns, user_text: "developer profile",
            "_is_location_request": lambda _text: False,
            "_location_reply": lambda: "location reply",
            "_is_session_recap_request": lambda _text: False,
            "_session_recap_reply": lambda turns, user_text: "session recap",
            "_is_assistant_name_query": lambda _text: False,
            "_assistant_name_reply": lambda user_text: "Nova",
            "_is_developer_full_name_query": lambda _text: False,
            "_developer_full_name_reply": lambda: "Gustavo Rivera",
            "_is_name_origin_question": lambda _text: False,
            "_peims_attendance_rules_reply": lambda: "attendance reply",
            "_is_deep_search_followup_request": lambda _text: False,
            "_infer_research_query_from_turns": lambda turns: "",
            "_build_grounded_answer": lambda query, max_sources=2: "",
            "_build_local_topic_digest_answer": lambda query: "",
            "_developer_color_reply": lambda turns: "developer color",
            "_developer_bilingual_reply": lambda turns: "developer bilingual",
            "_color_reply": lambda turns: "color reply",
            "_animal_reply": lambda turns: "animal reply",
            "nova_query_classifiers": SimpleNamespace(
                is_web_preferred_data_query=lambda _text: False,
                is_student_data_attendance_rules_query=lambda _text: False,
                is_conversational_clarification=lambda _text: False,
            ),
        }
        events = []
        traces = []
        core = SimpleNamespace(
            action_ledger_add_step=lambda ledger, stage, outcome, detail="", **data: traces.append((stage, outcome, detail)),
            _self_correct_reply=lambda user_text, reply: ("corrected reply", True, "fix"),
            behavior_record_event=lambda name: events.append(name),
            _is_identity_stable_reply=lambda reply: False,
            _apply_reply_overrides=lambda reply: reply + " +override",
            _open_probe_reply=lambda prompt, turns=None: ("clarify", "probe"),
        )

        with mock.patch(
            "services.nova_reply_sequence.execute_reply_sequence_from_runtime",
            return_value=("ok", {"planner_decision": "deterministic"}),
        ) as execute_mock:
            reply, meta = execute_http_reply_sequence_from_runtime(
                turns=[],
                text="hello",
                ledger_record={},
                pending_action=None,
                prefer_web_for_data_queries=False,
                language_mix_spanish_pct=0,
                session=None,
                ensure_reply=lambda reply: f"ENSURE:{reply}",
                core=core,
                runtime_scope=runtime_scope,
                pre_planner_branch_group="operational",
                post_planner_branch_group="general",
            )

        self.assertEqual(reply, "ok")
        self.assertEqual(meta.get("planner_decision"), "deterministic")
        normalize_reply = execute_mock.call_args.kwargs.get("normalize_reply")
        self.assertEqual(normalize_reply("draft UI-TIP"), "ENSURE:draft")
        self.assertEqual(events, [])
        self.assertEqual(traces, [])

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

    def test_post_planner_general_branch_group_handles_session_recap(self):
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

        reply, meta = self._call(
            "give me a recap of this chat",
            core=core,
            is_session_recap_request=lambda _text: True,
            pre_planner_branch_group="operational",
            post_planner_branch_group="general",
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

    def test_student_data_attendance_beats_planner_web_research_route(self):
        core = SimpleNamespace(
            truth_hierarchy_answer=lambda _text: (False, "", "", False),
            hard_answer=lambda _text: None,
            decide_actions=lambda _text, config=None: [{"type": "run_tool", "tool": "web_research", "args": ["student_data attendance rules"]}],
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
            "What are the attendance reporting rules for student_data?",
            core=core,
            is_student_data_attendance_rules_query=lambda _text: True,
            student_data_attendance_rules_reply=lambda: "Attendance data must be reported daily. [source: tea.texas.gov]",
        )

        self.assertIn("Attendance data", reply)
        self.assertEqual(meta.get("planner_decision"), "grounded_lookup")
        self.assertEqual(meta.get("tool"), "student_data_attendance")

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

    def test_queue_pressure_triage_beats_planner_when_planner_runs_early(self):
        with TemporaryDirectory() as td:
            runtime_dir = Path(td)
            (runtime_dir / "autonomy_maintenance_state.json").write_text(
                '{"last_work_tree_cycle": {"status": "idle"}}',
                encoding="utf-8",
            )
            core = SimpleNamespace(
                RUNTIME_DIR=str(runtime_dir),
                truth_hierarchy_answer=lambda _text: (False, "", "", False),
                hard_answer=lambda _text: None,
                decide_actions=lambda _text, config=None: [{"type": "run_tool", "tool": "git_status", "args": []}],
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
                tool_queue_status=lambda: (
                    "Standing work queue:\n"
                    "- open: 3 of 9\n"
                    "- green: 6\n"
                    "- drift: 3\n"
                    "Next item: real_world/stress_queue_pressure_triage.json\n"
                ),
                patch_status_payload=lambda: {
                    "review_previews_pending_distinct": 1,
                    "review_previews_orphaned": 1,
                    "previews_approved_eligible": 0,
                },
            )

            reply, meta = self._call(
                "Inspect the generated queue, patch queue, and work tree pressure. Tell me the single most important next move and why.",
                core=core,
                planner_before_deterministic_content=True,
            )

        self.assertIn("stress_queue_pressure_triage", reply)
        self.assertEqual(meta.get("planner_decision"), "deterministic")
        self.assertEqual(meta.get("tool"), "queue_pressure_triage")

    def test_pre_planner_operational_branch_group_handles_runtime_audit(self):
        core = SimpleNamespace(
            runtime_audit_snapshot=lambda: {
                "source": "control_status_api",
                "control_status_url": "http://127.0.0.1:8080/api/control/status",
                "guard_running": True,
                "guard_status": "running",
                "guard_pid": 1001,
                "core_running": True,
                "core_status": "running",
                "core_pid": 1002,
                "core_heartbeat_age_sec": 0,
                "search_ok": True,
                "search_note": "status=200",
                "search_endpoint": "http://127.0.0.1:8081/search",
                "maintenance_active": True,
                "maintenance_status": "guard_scheduled",
                "maintenance_mode": "guard_tick",
                "queue_status": "clear",
                "queue_open_count": 0,
                "queue_actionable_count": 0,
            },
            truth_hierarchy_answer=lambda _text: (False, "", "", False),
            hard_answer=lambda _text: None,
            decide_actions=lambda _text, config=None: [{"type": "run_tool", "tool": "git_status", "args": []}],
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
            "Inspect the live runtime and tell me whether guard, core, search, and maintenance are healthy. Use only the current live state.",
            core=core,
            pre_planner_branch_group="operational",
            post_planner_branch_group="general",
        )

        self.assertIn("guard is healthy", reply.lower())
        self.assertEqual(meta.get("tool"), "runtime_audit")

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

    def test_planner_before_deterministic_content_does_not_double_invoke_planner(self):
        core = SimpleNamespace(
            truth_hierarchy_answer=lambda _text: (False, "", "", False),
            hard_answer=lambda _text: None,
            analyze_request=lambda _text, config=None: SimpleNamespace(allow_llm=False, message="blocked"),
            build_fallback_context_details=lambda _text, _turns, conversation_state=None, pending_action=None: {},
            should_block_low_confidence=lambda _text, retrieved_context="": False,
            ollama_chat=lambda _text, retrieved_context="", language_mix_spanish_pct=0: "",
            sanitize_llm_reply=lambda reply, _tool: reply,
            _apply_claim_gate=lambda reply, evidence_text="", tool_context="": (reply, False, ""),
            _attach_learning_invitation=lambda reply: reply,
            _truthful_limit_outcome=lambda _text: {},
            _truthful_limit_reply=lambda _text: "",
            _is_developer_color_lookup_request=lambda _text: False,
            _is_developer_bilingual_request=lambda _text: False,
            _is_color_lookup_request=lambda _text: False,
            behavior_set_flag=lambda *args, **kwargs: None,
        )

        with mock.patch(
            "services.nova_reply_sequence.nova_planner_contract.maybe_handle_planner_sequence",
            return_value=None,
        ) as planner_mock:
            reply, meta = self._call(
                "tell me something open ended",
                core=core,
                planner_before_deterministic_content=True,
                stop_before_llm_fallback=True,
            )

        self.assertEqual(reply, "")
        self.assertEqual(meta.get("planner_decision"), "unhandled")
        self.assertEqual(planner_mock.call_count, 1)

    def test_llm_fallback_records_execution_profile_and_slow_llm_trace(self):
        core = SimpleNamespace(
            truth_hierarchy_answer=lambda _text: (False, "", "", False),
            hard_answer=lambda _text: None,
            analyze_request=lambda _text, config=None: SimpleNamespace(allow_llm=True, message=""),
            build_fallback_context_details=lambda _text, _turns, conversation_state=None, pending_action=None: {"context": "ctx"},
            should_block_low_confidence=lambda _text, retrieved_context="": False,
            ollama_chat=lambda _text, retrieved_context="", language_mix_spanish_pct=0: "slow reply",
            sanitize_llm_reply=lambda reply, _tool: reply,
            _apply_claim_gate=lambda reply, evidence_text="", tool_context="": (reply, False, ""),
            _attach_learning_invitation=lambda reply: reply,
            _truthful_limit_outcome=lambda _text: {},
            _truthful_limit_reply=lambda _text: "",
            _is_developer_color_lookup_request=lambda _text: False,
            _is_developer_bilingual_request=lambda _text: False,
            _is_color_lookup_request=lambda _text: False,
            behavior_set_flag=lambda *args, **kwargs: None,
        )
        trace_calls = []
        perf_values = iter([0, 0, 0, 0, 25, 25, 27, 27])

        with mock.patch("services.nova_reply_sequence.nova_planner_contract.maybe_handle_planner_sequence", return_value=None), \
             mock.patch("services.nova_reply_sequence.time.perf_counter", side_effect=lambda: next(perf_values)):
            reply, meta = self._call(
                "tell me something open ended",
                core=core,
                trace=lambda *args, **kwargs: trace_calls.append((args, kwargs)),
            )

        self.assertEqual(reply, "slow reply")
        profile = (meta.get("reply_outcome") or {}).get("execution_profile") or {}
        self.assertEqual(profile.get("planner_time"), 0)
        self.assertEqual(profile.get("llm_time"), 25000)
        self.assertEqual(profile.get("post_time"), 2000)
        self.assertEqual(profile.get("total_time"), 27000)
        self.assertTrue(any(args[:3] == ("llm_call", "slow", "llm_call_slow") for args, _kwargs in trace_calls))

    def test_planner_timing_is_included_in_execution_profile(self):
        planner_meta = {
            "planner_decision": "run_tool",
            "tool": "web_research",
            "tool_args": {"args": ["student_data"]},
            "tool_result": "Grounded result",
            "grounded": True,
            "timing": {"planner_time": 1200, "tool_selection_time": 300, "tool_time": 900},
        }
        perf_values = iter([0, 0, 1.2, 1.2])

        with mock.patch("services.nova_reply_sequence.nova_planner_contract.maybe_handle_planner_sequence", return_value=("Grounded result", planner_meta)), \
             mock.patch("services.nova_reply_sequence.time.perf_counter", side_effect=lambda: next(perf_values)):
            reply, meta = self._call("research student_data")

        self.assertEqual(reply, "Grounded result")
        profile = (meta.get("reply_outcome") or {}).get("execution_profile") or {}
        self.assertEqual(profile.get("planner_time"), 1200)
        self.assertEqual(profile.get("tool_time"), 900)
        self.assertEqual(profile.get("llm_time"), 0)

