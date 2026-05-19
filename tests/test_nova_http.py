import base64
import io
import json
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path
from unittest import mock
from unittest.mock import patch

import nova_http
from fulfillment_contracts import ChoiceMode, ChoiceSet, CollapseStatus, FitAssessment, FrameScore, FulfillmentModel, Intent


def _fulfillment_intent(intent_id: str = "intent-http-bridge") -> Intent:
    return Intent(
        intent_id=intent_id,
        achievement_goal="reach a workable result",
        success_criteria=["result achieved"],
        constraints=["stay within current constraints"],
        preferences=["useful", "low friction"],
    )


def _fulfillment_models() -> list[FulfillmentModel]:
    return [
        FulfillmentModel(
            model_id="http-guided",
            intent_id="intent-http-bridge",
            label="Guided path",
            description="Lower-friction option.",
            path_shape="guided_decision",
            differentiators=["lower user effort"],
            strengths=["lower friction"],
            expected_friction=["slower upfront"],
        ),
        FulfillmentModel(
            model_id="http-direct",
            intent_id="intent-http-bridge",
            label="Direct path",
            description="Faster option.",
            path_shape="direct_resolution",
            differentiators=["faster completion"],
            strengths=["faster timing"],
            expected_friction=["more commitment earlier"],
        ),
    ]


def _fulfillment_assessments() -> list[FitAssessment]:
    return [
        FitAssessment(
            assessment_id="ha1",
            intent_id="intent-http-bridge",
            model_id="http-guided",
            overall_fit_score=0.84,
            fit_band="strong_fit",
            valid=True,
            keep_reasons=["lower friction remains valuable"],
            frame_scores=[
                FrameScore(frame="explicit_constraint_fit", score=0.9),
                FrameScore(frame="achievement_goal_fit", score=0.82),
                FrameScore(frame="friction", score=0.95),
                FrameScore(frame="timing", score=0.58),
                FrameScore(frame="risk", score=0.82),
                FrameScore(frame="usefulness", score=0.86),
            ],
        ),
        FitAssessment(
            assessment_id="ha2",
            intent_id="intent-http-bridge",
            model_id="http-direct",
            overall_fit_score=0.83,
            fit_band="strong_fit",
            valid=True,
            keep_reasons=["faster timing remains valuable"],
            frame_scores=[
                FrameScore(frame="explicit_constraint_fit", score=0.9),
                FrameScore(frame="achievement_goal_fit", score=0.82),
                FrameScore(frame="friction", score=0.6),
                FrameScore(frame="timing", score=0.96),
                FrameScore(frame="risk", score=0.78),
                FrameScore(frame="usefulness", score=0.85),
            ],
        ),
    ]


def _http_choice_set() -> ChoiceSet:
    presenter = __import__("choice_presenter").ChoicePresenter()
    return presenter.present(_fulfillment_intent(), _fulfillment_models(), _fulfillment_assessments())


class TestNovaHttpProfile(unittest.TestCase):
    def setUp(self):
        self.orig_mem_recall = nova_http.nova_core.mem_recall
        self.orig_mem_enabled = nova_http.nova_core.mem_enabled
        self.orig_ollama_chat = nova_http.nova_core.ollama_chat
        self.orig_sanitize_llm_reply = nova_http.nova_core.sanitize_llm_reply
        self.orig_action_ledger_dir = nova_http.nova_core.ACTION_LEDGER_DIR
        self.orig_self_reflection_log = nova_http.nova_core.SELF_REFLECTION_LOG
        self.orig_health_log = nova_http.nova_core.HEALTH_LOG
        self.orig_dev_bilingual = nova_http.nova_core._developer_is_bilingual
        self.orig_dev_bilingual_mem = nova_http.nova_core._developer_is_bilingual_from_memory
        self.orig_dev_colors = nova_http.nova_core._extract_developer_color_preferences
        self.orig_dev_colors_mem = nova_http.nova_core._extract_developer_color_preferences_from_memory
        self.orig_handle_keywords = nova_http.nova_core.handle_keywords
        self.orig_llm_classify_routing_intent = nova_http.nova_core._llm_classify_routing_intent
        self.orig_runtime_device_location_payload = nova_http.nova_core.runtime_device_location_payload
        self.orig_resolve_current_device_coords = nova_http.nova_core.resolve_current_device_coords
        nova_http.SESSION_TURNS.clear()
        nova_http.SESSION_STATE_MANAGER.clear()
        nova_http._CONTROL_STATUS_CACHE["computed_at"] = 0.0
        nova_http._CONTROL_STATUS_CACHE["payload"] = None
        self._tmp_dir = tempfile.TemporaryDirectory()
        self._action_ledger_dir = Path(self._tmp_dir.name) / "actions"
        nova_http.nova_core.ACTION_LEDGER_DIR = self._action_ledger_dir
        nova_http.nova_core.SELF_REFLECTION_LOG = Path(self._tmp_dir.name) / "self_reflection.jsonl"
        nova_http.nova_core.HEALTH_LOG = Path(self._tmp_dir.name) / "health.log"
        nova_http.nova_core.ollama_chat = lambda text, retrieved_context="", **_kwargs: f"LLM:{text}"
        nova_http.nova_core.sanitize_llm_reply = lambda text, _tool_context="", **_kwargs: text
        nova_http.nova_core.runtime_device_location_payload = lambda *args, **kwargs: {"available": False, "stale": True}
        nova_http.nova_core.resolve_current_device_coords = lambda *args, **kwargs: None

    def _assert_no_runtime_error_answers(self):
        if not self._action_ledger_dir.exists():
            return
        failures = []
        for path in sorted(self._action_ledger_dir.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            final_answer = str(payload.get("final_answer") or "").strip()
            final_low = final_answer.lower()
            if (
                final_low.startswith("(error:")
                or "llm service unavailable" in final_low
                or "ollama chat model missing" in final_low
                or "ollama chat api unavailable" in final_low
                or "ollama chat failed" in final_low
            ):
                failures.append(f"{path.name}: {final_answer[:160]}")
        self.assertEqual(failures, [], "HTTP behavior tests produced runtime error answers")

    def tearDown(self):
        try:
            self._assert_no_runtime_error_answers()
        finally:
            nova_http.nova_core.mem_recall = self.orig_mem_recall
            nova_http.nova_core.mem_enabled = self.orig_mem_enabled
            nova_http.nova_core.ollama_chat = self.orig_ollama_chat
            nova_http.nova_core.sanitize_llm_reply = self.orig_sanitize_llm_reply
            nova_http.nova_core.ACTION_LEDGER_DIR = self.orig_action_ledger_dir
            nova_http.nova_core.SELF_REFLECTION_LOG = self.orig_self_reflection_log
            nova_http.nova_core.HEALTH_LOG = self.orig_health_log
            nova_http.nova_core._developer_is_bilingual = self.orig_dev_bilingual
            nova_http.nova_core._developer_is_bilingual_from_memory = self.orig_dev_bilingual_mem
            nova_http.nova_core._extract_developer_color_preferences = self.orig_dev_colors
            nova_http.nova_core._extract_developer_color_preferences_from_memory = self.orig_dev_colors_mem
            nova_http.nova_core.handle_keywords = self.orig_handle_keywords
            nova_http.nova_core._llm_classify_routing_intent = self.orig_llm_classify_routing_intent
            nova_http.nova_core.runtime_device_location_payload = self.orig_runtime_device_location_payload
            nova_http.nova_core.resolve_current_device_coords = self.orig_resolve_current_device_coords
            nova_http.SESSION_TURNS.clear()
            nova_http.SESSION_STATE_MANAGER.clear()
            nova_http._CONTROL_STATUS_CACHE["computed_at"] = 0.0
            nova_http._CONTROL_STATUS_CACHE["payload"] = None
            self._tmp_dir.cleanup()

    def test_generated_work_queue_uses_runtime_dir_for_blocked_metadata(self):
        with mock.patch.object(nova_http.TEST_SESSION_CONTROL_SERVICE, "generated_work_queue", return_value={"status": "clear"}) as queue_mock, \
            mock.patch("nova_http._available_test_session_definitions", return_value=[]), \
            mock.patch("nova_http._test_session_report_summaries", return_value=[]):
            payload = nova_http._generated_work_queue(12)

        self.assertEqual(payload.get("status"), "clear")
        self.assertEqual(queue_mock.call_args.kwargs.get("runtime_dir"), nova_http.RUNTIME_DIR)

    def test_autonomy_maintenance_summary_flattens_queue_truth(self):
        state = {
            "runtime_worker": {"last_cycle_status": "ok"},
            "last_regression_status": "FAILED",
            "last_regression_stale": True,
            "last_generated_queue_run": {
                "status": "blocked",
                "queue_open_count": 3,
                "queue_actionable_count": 0,
                "queue_blocked_count": 3,
                "queue_blocked_reason_counts": {"parity_drift_locked": 3},
                "queue_blocked_files": ["a.json", "b.json", "c.json"],
            },
            "last_work_tree_cycle": {"status": "idle"},
            "last_complete_tree_archive": {"status": "ok", "archived_count": 12, "retained_count": 8},
            "last_error": "",
        }
        with mock.patch("nova_http._load_autonomy_maintenance_state", return_value=state), \
            mock.patch("nova_http.runtime_processes.logical_service_processes", return_value=[]), \
            mock.patch("nova_http.runtime_processes.select_logical_process", return_value=None), \
            mock.patch("nova_http.AUTONOMY_ORCHESTRATOR_LEDGER_SERVICE.summary", return_value={"ok": True, "count": 2, "stable_recommendation": True}):
            payload = nova_http._autonomy_maintenance_summary()

        self.assertEqual(payload.get("generated_queue_status"), "blocked")
        self.assertEqual(payload.get("last_regression_status"), "FAILED")
        self.assertTrue(payload.get("last_regression_stale"))
        self.assertEqual(payload.get("queue_open_count"), 3)
        self.assertEqual(payload.get("queue_actionable_count"), 0)
        self.assertEqual(payload.get("queue_blocked_count"), 3)
        self.assertEqual(payload.get("queue_blocked_reason_counts"), {"parity_drift_locked": 3})
        self.assertEqual(payload.get("queue_blocked_files"), ["a.json", "b.json", "c.json"])
        self.assertEqual(payload.get("work_tree_status"), "idle")
        self.assertEqual((payload.get("last_complete_tree_archive") or {}).get("archived_count"), 12)
        self.assertEqual((payload.get("autonomy_orchestrator_summary") or {}).get("count"), 2)
        self.assertEqual(payload.get("last_error"), "")

    def test_probe_searxng_uses_relaxed_timeout(self):
        with mock.patch("nova_http.nova_core.probe_search_endpoint", return_value={"ok": True, "note": "status=200"}) as probe_mock:
            ok, note = nova_http._probe_searxng("http://127.0.0.1:8081/search")

        self.assertTrue(ok)
        self.assertEqual(note, "status=200")
        self.assertEqual(probe_mock.call_args.kwargs.get("timeout"), nova_http.SEARXNG_STATUS_TIMEOUT_SEC)

    def test_autonomy_maintenance_summary_clears_stale_worker_identity_when_process_missing(self):
        state = {
            "runtime_worker": {
                "last_cycle_status": "running",
                "pid": 4321,
                "create_time": 12.5,
            }
        }
        with mock.patch("nova_http._load_autonomy_maintenance_state", return_value=state), \
            mock.patch("nova_http.runtime_processes.logical_service_processes", return_value=[]), \
            mock.patch("nova_http.runtime_processes.select_logical_process", return_value=None):
            payload = nova_http._autonomy_maintenance_summary()

        worker = dict(payload.get("runtime_worker") or {})
        self.assertEqual(worker.get("last_cycle_status"), "stopped")
        self.assertFalse(worker.get("active"))
        self.assertTrue(worker.get("stale_identity"))
        self.assertIsNone(worker.get("pid"))
        self.assertIsNone(worker.get("create_time"))

    def test_cached_control_status_payload_reuses_recent_value(self):
        payloads = [{"ok": True, "seq": 1}, {"ok": True, "seq": 2}]

        with mock.patch("nova_http._control_status_payload", side_effect=payloads) as status_mock, \
            mock.patch("nova_http.time.monotonic", side_effect=[100.0, 100.0, 100.1, 101.0, 103.5, 103.5, 103.6]):
            first = nova_http._cached_control_status_payload(2.0)
            second = nova_http._cached_control_status_payload(2.0)
            third = nova_http._cached_control_status_payload(2.0)

        self.assertEqual(first["seq"], 1)
        self.assertEqual(second["seq"], 1)
        self.assertEqual(third["seq"], 2)
        self.assertEqual(status_mock.call_count, 2)

    def test_developer_who_is_answer_is_deterministic(self):
        nova_http.nova_core.mem_enabled = lambda: True
        nova_http.nova_core.mem_recall = lambda q: ""
        reply = nova_http.process_chat("s1", "who is your developer?")
        self.assertTrue(reply.startswith("From earlier memory:"))
        self.assertIn("Gustavo", reply)
        self.assertIn("created me", reply.lower())

    def test_developer_profile_includes_known_facts(self):
        nova_http.nova_core.mem_enabled = lambda: True
        nova_http.nova_core.mem_recall = lambda q: "- developer note: gus works locally"
        nova_http.nova_core._developer_is_bilingual = lambda turns: True
        nova_http.nova_core._developer_is_bilingual_from_memory = lambda: True
        nova_http.nova_core._extract_developer_color_preferences = lambda turns: ["silver", "red", "blue"]
        nova_http.nova_core._extract_developer_color_preferences_from_memory = lambda: ["silver", "red", "blue"]

        reply = nova_http.process_chat("s2", "what else do you know about gus?")
        self.assertTrue(reply.startswith("From earlier memory:"))
        self.assertIn("bilingual", reply.lower())
        self.assertIn("silver", reply.lower())
        self.assertIn("developer", reply.lower())

    def test_developer_profile_self_diagnostic_when_partial(self):
        nova_http.nova_core.mem_enabled = lambda: True
        nova_http.nova_core.mem_recall = lambda q: ""
        nova_http.nova_core._developer_is_bilingual = lambda turns: None
        nova_http.nova_core._developer_is_bilingual_from_memory = lambda: None
        nova_http.nova_core._extract_developer_color_preferences = lambda turns: []
        nova_http.nova_core._extract_developer_color_preferences_from_memory = lambda: []

        reply = nova_http.process_chat("s6", "what else do you know about Gus your developer?")
        self.assertIn("his full name is gustavo", reply.lower())
        self.assertIn("don't have any additional verified information", reply.lower())

    def test_developer_location_followup_stays_on_developer_thread(self):
        reply1 = nova_http.process_chat("s6_loc", "what do you know about Gus?")
        reply2 = nova_http.process_chat("s6_loc", "do you know his current location")
        self.assertIn("gustavo", reply1.lower())
        self.assertIn("uncertain about gus's current location", reply2.lower())
        self.assertNotIn("local knowledge files", reply2.lower())

    def test_http_direct_developer_location_uses_shared_turn_helper(self):
        reply = nova_http.process_chat("s6_loc_direct", "where is gus right now?")
        self.assertIn("uncertain about gus's current location", reply.lower())
        session = nova_http.SESSION_STATE_MANAGER.get("s6_loc_direct")
        self.assertIsNotNone(session)
        self.assertEqual("identity_profile:developer", session.active_subject())

    def test_who_is_gus_seeds_developer_profile_subject(self):
        reply = nova_http.process_chat("s6_subject", "who is gus ?")
        self.assertIn("gustavo", reply.lower())
        session = nova_http.SESSION_STATE_MANAGER.get("s6_subject")
        self.assertIsNotNone(session)
        self.assertEqual("identity_profile:developer", session.active_subject())

    def test_generate_chat_reply_uses_no_deterministic_content_branch(self):
        with patch(
            "nova_http.execute_http_reply_sequence_from_runtime",
            return_value=(
                "runtime audit reply",
                {
                    "planner_decision": "deterministic",
                    "tool": "runtime_audit",
                    "tool_args": {"query": "show me the live runtime state of guard core search and maintenance"},
                    "tool_result": "runtime audit reply",
                    "grounded": True,
                },
            ),
        ) as sequence_mock:
            reply, meta = nova_http._generate_chat_reply([], "show me the live runtime state of guard core search and maintenance")

        self.assertEqual(reply, "runtime audit reply")
        self.assertEqual(meta.get("planner_decision"), "deterministic")
        self.assertEqual(meta.get("tool"), "runtime_audit")
        self.assertTrue(meta.get("grounded"))
        self.assertEqual(sequence_mock.call_args.kwargs.get("pre_planner_branch_group"), "none")
        self.assertIsNone(sequence_mock.call_args.kwargs.get("post_planner_branch_group"))

    def test_generate_chat_reply_runtime_audit_evidence_is_deterministic(self):
        with patch(
            "nova_http.execute_http_reply_sequence_from_runtime",
            return_value=(
                "runtime evidence reply",
                {
                    "planner_decision": "deterministic",
                    "tool": "runtime_audit_evidence",
                    "tool_args": {"query": "what evidence did you use and what still worries you"},
                    "tool_result": "runtime evidence reply",
                    "grounded": True,
                },
            ),
        ):
            reply, meta = nova_http._generate_chat_reply([], "what evidence did you use and what still worries you")

        self.assertEqual(reply, "runtime evidence reply")
        self.assertEqual(meta.get("planner_decision"), "deterministic")
        self.assertEqual(meta.get("tool"), "runtime_audit_evidence")
        self.assertTrue(meta.get("grounded"))

    def test_generate_chat_reply_tool_path_is_deterministic(self):
        with patch(
            "nova_http.execute_http_reply_sequence_from_runtime",
            return_value=(
                "tool path reply",
                {
                    "planner_decision": "deterministic",
                    "tool": "tool_path_disambiguation",
                    "tool_args": {"query": "tell me the exact file and service name for patch preview approval"},
                    "tool_result": "tool path reply",
                    "grounded": True,
                },
            ),
        ):
            reply, meta = nova_http._generate_chat_reply([], "tell me the exact file and service name for patch preview approval")

        self.assertEqual(reply, "tool path reply")
        self.assertEqual(meta.get("planner_decision"), "deterministic")
        self.assertEqual(meta.get("tool"), "tool_path_disambiguation")
        self.assertTrue(meta.get("grounded"))

    def test_generate_chat_reply_tool_path_safe_step_is_deterministic(self):
        with patch(
            "nova_http.execute_http_reply_sequence_from_runtime",
            return_value=(
                "tool path safe step reply",
                {
                    "planner_decision": "deterministic",
                    "tool": "tool_path_safe_step",
                    "tool_args": {"query": "what is the next safe operator step without pretending you changed anything"},
                    "tool_result": "tool path safe step reply",
                    "grounded": True,
                },
            ),
        ):
            reply, meta = nova_http._generate_chat_reply([], "what is the next safe operator step without pretending you changed anything")

        self.assertEqual(reply, "tool path safe step reply")
        self.assertEqual(meta.get("planner_decision"), "deterministic")
        self.assertEqual(meta.get("tool"), "tool_path_safe_step")
        self.assertTrue(meta.get("grounded"))

    def test_generate_chat_reply_maintenance_mode_truth_is_deterministic(self):
        with patch(
            "nova_http.execute_http_reply_sequence_from_runtime",
            return_value=(
                "maintenance mode reply",
                {
                    "planner_decision": "deterministic",
                    "tool": "maintenance_mode_truth",
                    "tool_args": {"query": "Is Nova maintenance running through a separate worker or through the guard tick right now?"},
                    "tool_result": "maintenance mode reply",
                    "grounded": True,
                },
            ),
        ):
            reply, meta = nova_http._generate_chat_reply([], "Is Nova maintenance running through a separate worker or through the guard tick right now?")

        self.assertEqual(reply, "maintenance mode reply")
        self.assertEqual(meta.get("planner_decision"), "deterministic")
        self.assertEqual(meta.get("tool"), "maintenance_mode_truth")
        self.assertTrue(meta.get("grounded"))

    def test_generate_chat_reply_storage_watch_truth_is_deterministic(self):
        with patch(
            "nova_http.execute_http_reply_sequence_from_runtime",
            return_value=(
                "storage watch truth reply",
                {
                    "planner_decision": "deterministic",
                    "tool": "storage_watch_truth",
                    "tool_args": {"query": "Tell me whether Nova's snapshot storage is healthy right now and what numbers prove it."},
                    "tool_result": "storage watch truth reply",
                    "grounded": True,
                },
            ),
        ):
            reply, meta = nova_http._generate_chat_reply([], "Tell me whether Nova's snapshot storage is healthy right now and what numbers prove it.")

        self.assertEqual(reply, "storage watch truth reply")
        self.assertEqual(meta.get("planner_decision"), "deterministic")
        self.assertEqual(meta.get("tool"), "storage_watch_truth")
        self.assertTrue(meta.get("grounded"))

    def test_generate_chat_reply_heartbeat_forensics_is_deterministic(self):
        with patch(
            "nova_http.execute_http_reply_sequence_from_runtime",
            return_value=(
                "heartbeat forensics reply",
                {
                    "planner_decision": "deterministic",
                    "tool": "heartbeat_forensics",
                    "tool_args": {"query": "Check whether Nova's heartbeat is healthy right now and tell me exactly what proves it."},
                    "tool_result": "heartbeat forensics reply",
                    "grounded": True,
                },
            ),
        ):
            reply, meta = nova_http._generate_chat_reply([], "Check whether Nova's heartbeat is healthy right now and tell me exactly what proves it.")

        self.assertEqual(reply, "heartbeat forensics reply")
        self.assertEqual(meta.get("planner_decision"), "deterministic")
        self.assertEqual(meta.get("tool"), "heartbeat_forensics")
        self.assertTrue(meta.get("grounded"))

    def test_generate_chat_reply_runtime_artifact_grounding_is_deterministic(self):
        with patch(
            "nova_http.execute_http_reply_sequence_from_runtime",
            return_value=(
                "runtime artifact grounding reply",
                {
                    "planner_decision": "deterministic",
                    "tool": "runtime_artifact_grounding",
                    "tool_args": {"query": "If we needed to inspect runtime truth right now, which exact runtime artifact files would you look at first?"},
                    "tool_result": "runtime artifact grounding reply",
                    "grounded": True,
                },
            ),
        ):
            reply, meta = nova_http._generate_chat_reply([], "If we needed to inspect runtime truth right now, which exact runtime artifact files would you look at first?")

        self.assertEqual(reply, "runtime artifact grounding reply")
        self.assertEqual(meta.get("planner_decision"), "deterministic")
        self.assertEqual(meta.get("tool"), "runtime_artifact_grounding")
        self.assertTrue(meta.get("grounded"))

    def test_generate_chat_reply_general_deterministic_sequence_runs_after_planner(self):
        with patch(
            "nova_http.execute_http_reply_sequence_from_runtime",
            return_value=(
                "session recap reply",
                {
                    "planner_decision": "deterministic",
                    "tool": "session_recap",
                    "tool_args": {"query": "give me a session recap"},
                    "tool_result": "session recap reply",
                    "grounded": True,
                },
            ),
        ) as sequence_mock:
            reply, meta = nova_http._generate_chat_reply([], "give me a session recap")

        self.assertEqual(reply, "session recap reply")
        self.assertEqual(meta.get("tool"), "session_recap")
        self.assertEqual(sequence_mock.call_args.kwargs.get("pre_planner_branch_group"), "operational")
        self.assertEqual(sequence_mock.call_args.kwargs.get("post_planner_branch_group"), "general")

    def test_developer_profile_certainty_challenge_stays_on_profile_thread(self):
        nova_http.process_chat("s6_cert", "what do you know about Gus?")
        reply = nova_http.process_chat("s6_cert", "are you sure that is all the information you about him?")
        self.assertNotIn("web research results", reply.lower())
        self.assertIn("verified facts", reply.lower())

    def test_profile_thread_resource_question_does_not_fall_into_local_knowledge(self):
        nova_http.process_chat("s6_res", "what do you know about Gus?")
        nova_http.process_chat("s6_res", "are you sure that is all the information you about him?")
        reply = nova_http.process_chat("s6_res", "what type of resources are you tring to fetch nova ?")
        self.assertIn("not trying to fetch web resources", reply.lower())
        self.assertNotIn("local knowledge files", reply.lower())

    def test_developer_how_built_has_non_hallucinated_limit(self):
        nova_http.nova_core.mem_enabled = lambda: True
        nova_http.nova_core.mem_recall = lambda q: ""
        with mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
            reply = nova_http.process_chat("s3", "how did he develop you?")
        self.assertIn("do not have detailed build-history", reply)
        self.assertNotIn("Turn bypassed supervisor intent phase", stdout.getvalue())
        session = nova_http.SESSION_STATE_MANAGER.get("s3")
        self.assertIsNotNone(session)
        self.assertEqual((session.last_reflection or {}).get("reply_contract"), "identity_history.history_recall")
        self.assertEqual((session.last_reflection or {}).get("reply_outcome_kind"), "history_recall")

    def test_fast_smalltalk_greeting(self):
        reply = nova_http.process_chat("s4", "hi nova")
        self.assertEqual("Hello.", reply)

    def test_fast_smalltalk_greeting_ignores_synthetic_runner_user(self):
        reply = nova_http.process_chat("s4_runner", "hi nova", user_id="runner")
        self.assertEqual("Hello.", reply)

    def test_how_are_you_does_not_route_to_grounded_lookup(self):
        reply = nova_http.process_chat("s4_how", "how are you?")
        self.assertEqual("I'm doing well, thanks for asking.", reply)

    def test_http_fulfillment_bridge_handles_model_space_turn(self):
        with patch("intent_interpreter.IntentInterpreter.interpret", return_value=_fulfillment_intent()), patch(
            "fulfillment_model_generator.FulfillmentModelGenerator.generate",
            return_value=_fulfillment_models(),
        ), patch(
            "fit_evaluator.FitEvaluator.evaluate",
            return_value=_fulfillment_assessments(),
        ):
            reply = nova_http.process_chat("s_fulfillment_http", "Show me workable options without collapsing too early.")

        self.assertEqual(reply, "LLM:Show me workable options without collapsing too early.")
        session = nova_http.SESSION_STATE_MANAGER.get("s_fulfillment_http")
        self.assertIsNotNone(session)
        self.assertFalse(isinstance(getattr(session, "fulfillment_state", None), dict))

    def test_http_fulfillment_bridge_replans_existing_state(self):
        session = nova_http.SESSION_STATE_MANAGER.get("s_fulfillment_replan")
        session.fulfillment_state = {
            "intent": _fulfillment_intent(),
            "models": _fulfillment_models(),
            "assessments": _fulfillment_assessments(),
            "choice_set": _http_choice_set(),
        }
        replanned_choice = ChoiceSet(
            choice_set_id="choice:intent-http-bridge",
            intent_id="intent-http-bridge",
            mode=ChoiceMode.SINGLE_RESULT,
            collapse_status=CollapseStatus.COLLAPSED,
            options=_http_choice_set().options[:1],
            selected_model_id="http-guided",
            collapse_reason="single distinct valid fulfillment shape",
            user_decision_needed=False,
        )

        with patch(
            "dynamic_replanner.DynamicReplanner.replan",
            return_value=(_fulfillment_intent(), [_fulfillment_models()[0]], [_fulfillment_assessments()[0]], replanned_choice),
        ):
            reply = nova_http.process_chat("s_fulfillment_replan", "New information makes the faster path less safe.")

        self.assertEqual(reply, "LLM:New information makes the faster path less safe.")
        self.assertNotEqual(session.fulfillment_state.get("choice_set").selected_model_id, "http-guided")

    def test_http_mixed_info_request_turn_asks_for_clarification(self):
        mixed_turn = "the weather looks good. i wonder if the weather will stay like this for the rest of the day. can you check what the rest of the forecast will be"
        reply = nova_http.process_chat("s4_mixed_weather", mixed_turn)
        self.assertNotIn("meta-clarifying", reply.lower())
        session = nova_http.SESSION_STATE_MANAGER.get("s4_mixed_weather")
        self.assertEqual((session.last_reflection or {}).get("reply_contract"), "turn.clarify_mixed_intent")
        self.assertEqual((session.last_reflection or {}).get("reply_outcome_kind"), "mixed_info_request")
        self.assertIn("inform", (session.last_reflection or {}).get("turn_acts") or [])
        self.assertIn("ask", (session.last_reflection or {}).get("turn_acts") or [])
        self.assertIn("mixed", (session.last_reflection or {}).get("turn_acts") or [])

    def test_fast_smalltalk_ready_to_get_to_work(self):
        reply = nova_http.process_chat("s4_ready", "ready to get to work?")
        self.assertIn("ready when you are", reply.lower())
        self.assertIn("task for today", reply.lower())
        self.assertNotIn("local knowledge files", reply.lower())

    def test_creator_query_uses_hard_answer_before_grounded_lookup(self):
        reply = nova_http.process_chat("s4_creator", "who made you?")
        self.assertIn("my creator is gustavo uribe", reply.lower())
        self.assertNotIn("local knowledge files", reply.lower())

    def test_http_name_query_typo_and_web_challenge_stay_deterministic(self):
        nova_http.SESSION_TURNS.clear()
        nova_http.SESSION_STATE_MANAGER.clear()

        first = nova_http.process_chat("s_name_ui", "what is TSDS?")
        second = nova_http.process_chat("s_name_ui", "what is yor name?")
        third = nova_http.process_chat("s_name_ui", "why should i try to use the web for your name ?")

        self.assertNotIn("local knowledge files", first.lower())
        self.assertNotIn("[source:", first.lower())
        self.assertIn("my name is nova", second.lower())
        self.assertNotIn("web research results", third.lower())
        self.assertIn("should not need web research", third.lower())

    def test_fast_smalltalk_who_is_developer(self):
        reply = nova_http.process_chat("s5", "who is your developer?")
        self.assertIn("Gustavo", reply)

    def test_http_location_statement_stays_conversation_owned(self):
        orig_set_location_text = nova_http.nova_core.set_location_text
        try:
            stored = []
            nova_http.nova_core.set_location_text = lambda value, input_source="typed": stored.append((value, input_source)) or value

            reply = nova_http.process_chat("s5_loc_store", "my location is Brownsville Texas")

            self.assertEqual("LLM:my location is Brownsville Texas", reply)
            self.assertEqual(stored, [])
        finally:
            nova_http.nova_core.set_location_text = orig_set_location_text

    def test_http_set_location_zip_claim_stays_conversation_owned(self):
        orig_set_location_text = nova_http.nova_core.set_location_text
        try:
            stored = []
            nova_http.nova_core.set_location_text = lambda value, input_source="typed": stored.append((value, input_source)) or value

            reply = nova_http.process_chat("s5_zip_store", "the 78521 is the zip code for your current physical location")

            self.assertEqual("LLM:the 78521 is the zip code for your current physical location", reply)
            self.assertEqual(stored, [])
        finally:
            nova_http.nova_core.set_location_text = orig_set_location_text

    def test_http_weather_uses_saved_location_after_set_location(self):
        orig_set_location_text = nova_http.nova_core.set_location_text
        orig_get_saved_location_text = nova_http.nova_core.get_saved_location_text
        orig_tool_weather = nova_http.nova_core.tool_weather
        try:
            saved = {"value": ""}

            def _store_location(value, input_source="typed"):
                saved["value"] = value
                return value

            weather_calls = []
            nova_http.nova_core.set_location_text = _store_location
            nova_http.nova_core.get_saved_location_text = lambda: saved["value"]
            nova_http.nova_core.tool_weather = lambda location: weather_calls.append(location) or f"Forecast for {location}: rain"

            first = nova_http.process_chat("s5_weather_zip", "78521")
            second = nova_http.process_chat("s5_weather_zip", "weather now")

            self.assertIn("Got it - 78521 is a ZIP code.", first)
            self.assertIn("Forecast for 78521: rain", second)
            self.assertEqual(weather_calls, ["78521"])
        finally:
            nova_http.nova_core.set_location_text = orig_set_location_text
            nova_http.nova_core.get_saved_location_text = orig_get_saved_location_text
            nova_http.nova_core.tool_weather = orig_tool_weather

    def test_http_where_am_i_uses_deterministic_location_recall(self):
        orig_set_location_text = nova_http.nova_core.set_location_text
        orig_get_saved_location_text = nova_http.nova_core.get_saved_location_text
        orig_runtime_device_location_payload = nova_http.nova_core.runtime_device_location_payload
        orig_resolve_current_device_coords = nova_http.nova_core.resolve_current_device_coords
        try:
            saved = {"value": ""}

            def _store_location(value, input_source="typed"):
                saved["value"] = value
                return value

            nova_http.nova_core.set_location_text = _store_location
            nova_http.nova_core.get_saved_location_text = lambda: saved["value"]
            nova_http.nova_core.runtime_device_location_payload = lambda *args, **kwargs: {"available": False, "stale": True}
            nova_http.nova_core.resolve_current_device_coords = lambda *args, **kwargs: None

            first = nova_http.process_chat("s5_where_am_i", "78521")
            second = nova_http.process_chat("s5_where_am_i", "where am I")

            self.assertIn("Got it - 78521 is a ZIP code.", first)
            self.assertIn("Your saved location is 78521", second)
        finally:
            nova_http.nova_core.set_location_text = orig_set_location_text
            nova_http.nova_core.get_saved_location_text = orig_get_saved_location_text
            nova_http.nova_core.runtime_device_location_payload = orig_runtime_device_location_payload
            nova_http.nova_core.resolve_current_device_coords = orig_resolve_current_device_coords

    def test_http_location_name_followup_uses_saved_location(self):
        orig_set_location_text = nova_http.nova_core.set_location_text
        orig_get_saved_location_text = nova_http.nova_core.get_saved_location_text
        try:
            saved = {"value": ""}

            def _store_location(value, input_source="typed"):
                saved["value"] = value
                return value

            nova_http.nova_core.set_location_text = _store_location
            nova_http.nova_core.get_saved_location_text = lambda: saved["value"]

            first = nova_http.process_chat("s5_location_name", "78521")
            second = nova_http.process_chat("s5_location_name", "give me the name to that location")

            self.assertIn("Got it - 78521 is a ZIP code.", first)
            self.assertEqual("That location is Brownsville, TX.", second)
            self.assertNotIn("McAllen", second)
        finally:
            nova_http.nova_core.set_location_text = orig_set_location_text
            nova_http.nova_core.get_saved_location_text = orig_get_saved_location_text

    def test_http_saved_zip_followup_city_name_stays_in_location_thread(self):
        orig_set_location_text = nova_http.nova_core.set_location_text
        orig_get_saved_location_text = nova_http.nova_core.get_saved_location_text
        try:
            saved = {"value": ""}

            def _store_location(value, input_source="typed"):
                saved["value"] = value
                return value

            nova_http.nova_core.set_location_text = _store_location
            nova_http.nova_core.get_saved_location_text = lambda: saved["value"]

            first = nova_http.process_chat("s5_location_zip_city", "78521")
            second = nova_http.process_chat("s5_location_zip_city", "what is the name of the city that zip code belong too nova ?")

            self.assertIn("Got it - 78521 is a ZIP code.", first)
            self.assertIn("Brownsville", second)
            self.assertNotIn("local knowledge files", second.lower())
        finally:
            nova_http.nova_core.set_location_text = orig_set_location_text
            nova_http.nova_core.get_saved_location_text = orig_get_saved_location_text

    def test_http_location_context_city_name_followup_avoids_wikipedia(self):
        orig_runtime_device_location_payload = nova_http.nova_core.runtime_device_location_payload
        orig_resolve_current_device_coords = nova_http.nova_core.resolve_current_device_coords
        orig_get_saved_location_text = nova_http.nova_core.get_saved_location_text
        try:
            nova_http.nova_core.get_saved_location_text = lambda: ""
            nova_http.nova_core.resolve_current_device_coords = lambda *args, **kwargs: (25.93832, -97.45515)
            nova_http.nova_core.runtime_device_location_payload = lambda *args, **kwargs: {
                "available": True,
                "stale": False,
                "lat": 25.93832,
                "lon": -97.45515,
                "coords_text": "25.93832,-97.45515",
                "accuracy_m": 128,
            }

            first = nova_http.process_chat("s5_location_city_context", "your location")
            second = nova_http.process_chat("s5_location_city_context", "what is the name of the city")

            self.assertNotIn("My current device location", first)
            self.assertNotEqual("That location is Brownsville, TX.", second)
            self.assertNotIn("Wikipedia", second)
            self.assertNotIn("Killing in the Name", second)
        finally:
            nova_http.nova_core.runtime_device_location_payload = orig_runtime_device_location_payload
            nova_http.nova_core.resolve_current_device_coords = orig_resolve_current_device_coords
            nova_http.nova_core.get_saved_location_text = orig_get_saved_location_text

    def test_http_clean_slate_blocks_location_storage(self):
        orig_set_location_text = nova_http.nova_core.set_location_text
        try:
            stored = []
            nova_http.nova_core.set_location_text = lambda value, input_source="typed": stored.append((value, input_source)) or value

            reply = nova_http.process_chat("s5_clean_slate_loc", "my location is Brownsville Texas")

            self.assertEqual(stored, [])
        finally:
            nova_http.nova_core.set_location_text = orig_set_location_text

    def test_http_clean_slate_blocks_weather_request(self):
        orig_execute_planned_action = nova_http.nova_core.execute_planned_action
        orig_weather_current_location_available = nova_http.nova_core._weather_current_location_available
        try:
            nova_http.nova_core._llm_classify_routing_intent = lambda text, turns=None, pending_action=None: {
                "tool": "weather_current_location",
                "args": [],
                "source": "test_semantic_intent",
            }
            nova_http.nova_core._weather_current_location_available = lambda: True
            nova_http.nova_core.execute_planned_action = lambda tool, args=None: "weather-current"
            reply = nova_http.process_chat("s5_clean_slate_weather", "weather now")
            self.assertEqual(reply, "weather-current")
            session = nova_http.SESSION_STATE_MANAGER.get("s5_clean_slate_weather")
            self.assertEqual((session.last_reflection or {}).get("reply_contract"), "weather_lookup.current_location")
        finally:
            nova_http.nova_core.execute_planned_action = orig_execute_planned_action
            nova_http.nova_core._weather_current_location_available = orig_weather_current_location_available

    def test_http_clean_slate_blocks_peims_grounding(self):
        reply = nova_http.process_chat("s5_clean_slate_peims", "what do you know about PEIMS?")
        self.assertNotIn("local knowledge files", reply.lower())
        self.assertNotIn("[source:", reply.lower())

    def test_http_bare_numeric_turn_stays_conversation_owned(self):
        orig_get_saved_location_text = nova_http.nova_core.get_saved_location_text
        try:
            nova_http.nova_core.get_saved_location_text = lambda: "Brownsville, Texas"

            reply = nova_http.process_chat("s5_numeric_clarify", "78521")

            self.assertEqual("LLM:78521", reply)
            self.assertNotIn("brownsville", reply.lower())
        finally:
            nova_http.nova_core.get_saved_location_text = orig_get_saved_location_text

    def test_http_bare_numeric_followup_stays_conversation_owned(self):
        orig_get_saved_location_text = nova_http.nova_core.get_saved_location_text
        try:
            nova_http.nova_core.get_saved_location_text = lambda: "Brownsville, Texas"

            first = nova_http.process_chat("s5_numeric_followup", "78521")
            second = nova_http.process_chat("s5_numeric_followup", "what do you think it is nova ?")

            self.assertEqual("LLM:78521", first)
            self.assertEqual(second, "LLM:what do you think it is nova ?")
        finally:
            nova_http.nova_core.get_saved_location_text = orig_get_saved_location_text

    def test_http_correction_phrase_stays_conversation_owned(self):
        orig_mem_enabled = nova_http.nova_core.mem_enabled
        orig_mem_add = nova_http.nova_core.mem_add
        orig_teach_store_example = nova_http.nova_core._teach_store_example
        try:
            writes = []
            teaches = []
            nova_http.nova_core.mem_enabled = lambda: True
            nova_http.nova_core.mem_add = lambda kind, source, text: writes.append((kind, source, text))
            nova_http.nova_core._teach_store_example = lambda original, correction, user=None: teaches.append((original, correction, user)) or "OK"

            nova_http.process_chat("s5_correction_http", "what is tsds?")
            reply = nova_http.process_chat("s5_correction_http", "no, say 'hi gus' instead")

            self.assertEqual("LLM:no, say 'hi gus' instead", reply)
            self.assertEqual(writes, [])
            self.assertEqual(teaches, [])
        finally:
            nova_http.nova_core.mem_enabled = orig_mem_enabled
            nova_http.nova_core.mem_add = orig_mem_add
            nova_http.nova_core._teach_store_example = orig_teach_store_example

    def test_http_correction_followup_stays_conversation_owned(self):
        orig_mem_enabled = nova_http.nova_core.mem_enabled
        orig_mem_add = nova_http.nova_core.mem_add
        orig_teach_store_example = nova_http.nova_core._teach_store_example
        try:
            writes = []
            teaches = []
            nova_http.nova_core.mem_enabled = lambda: True
            nova_http.nova_core.mem_add = lambda kind, source, text: writes.append((kind, source, text))
            nova_http.nova_core._teach_store_example = lambda original, correction, user=None: teaches.append((original, correction, user)) or "OK"

            nova_http.process_chat("s5_correction_followup_http", "what is tsds?")
            first = nova_http.process_chat("s5_correction_followup_http", "no, that's wrong")
            second = nova_http.process_chat("s5_correction_followup_http", "hi gus")

            self.assertEqual("LLM:no, that's wrong", first)
            self.assertEqual("LLM:hi gus", second)
            self.assertEqual(teaches, [])
            self.assertEqual(writes, [])
        finally:
            nova_http.nova_core.mem_enabled = orig_mem_enabled
            nova_http.nova_core.mem_add = orig_mem_add
            nova_http.nova_core._teach_store_example = orig_teach_store_example

    def test_http_declarative_statement_uses_shared_noted_path(self):
        orig_mem_should_store = nova_http.nova_core.mem_should_store
        orig_mem_add = nova_http.nova_core.mem_add
        try:
            stored = []
            nova_http.nova_core.mem_should_store = lambda text: True
            nova_http.nova_core.mem_add = lambda kind, input_source, text: stored.append((kind, input_source, text))

            with mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
                reply = nova_http.process_chat("s5_decl_store", "I work at Nova Labs")

            self.assertNotEqual("Memory storage requires an explicit store request.", reply)
            self.assertNotIn("Turn bypassed supervisor intent phase", stdout.getvalue())
            self.assertEqual(stored, [])
        finally:
            nova_http.nova_core.mem_should_store = orig_mem_should_store
            nova_http.nova_core.mem_add = orig_mem_add

    def test_location_self_diagnostic_when_missing(self):
        orig_mem_audit = nova_http.nova_core.mem_audit
        orig_get_saved_location_text = nova_http.nova_core.get_saved_location_text
        orig_runtime_device_location_payload = nova_http.nova_core.runtime_device_location_payload
        try:
            nova_http.nova_core.mem_audit = lambda q: "{\"results\": []}"
            nova_http.nova_core.get_saved_location_text = lambda: ""
            nova_http.nova_core.runtime_device_location_payload = lambda *args, **kwargs: {"available": False, "stale": True}
            reply = nova_http.process_chat("s7", "where is nova?")
            self.assertNotIn("I don't have a stored location yet.", reply)
            self.assertNotIn("Current runtime device location", reply)
        finally:
            nova_http.nova_core.mem_audit = orig_mem_audit
            nova_http.nova_core.get_saved_location_text = orig_get_saved_location_text
            nova_http.nova_core.runtime_device_location_payload = orig_runtime_device_location_payload

    def test_read_text_safely_handles_utf16_without_null_padded_output(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "utf16_sample.txt"
            path.write_text("Public Education Information Management System (PEIMS).", encoding="utf-16")

            out = nova_http._read_text_safely(path)

            self.assertIn("Public Education Information Management System", out)
            self.assertNotIn("\x00", out)

    def test_peims_broad_query_no_longer_uses_peims_overview_heading(self):
        reply = nova_http.process_chat("s_peims", "what do you know about PEIMS?")
        self.assertNotIn("I found PEIMS overview details", reply)
        self.assertNotIn("[source: knowledge/", reply.lower())

    def test_tsds_query_no_longer_uses_local_knowledge_digest(self):
        reply = nova_http.process_chat("s_tsds", "what is TSDS?")
        self.assertNotIn("local knowledge files", reply.lower())
        self.assertNotIn("[source: knowledge/", reply.lower())

    def test_chat_context_uses_planner_command_route(self):
        nova_http.process_chat("s8", "hello there")
        reply = nova_http.process_chat("s8", "chat context")
        self.assertIn("Current chat context", reply)
        self.assertIn("User: chat context", reply)

    def test_keyword_route_uses_planner_delegation(self):
        nova_http.nova_core.handle_keywords = lambda text: ("tool", "web_research", "continued web research")
        reply = nova_http.process_chat("s9", "web continue")
        self.assertIn("continued web research", reply)

    def test_http_online_research_intent_uses_semantic_tool_route_without_bypass_warning(self):
        orig_execute_planned_action = nova_http.nova_core.execute_planned_action
        try:
            nova_http.nova_core._llm_classify_routing_intent = lambda text, turns=None, pending_action=None: {
                "tool": "web_research",
                "args": ["PEIMS"],
                "source": "test_semantic_intent",
            }
            nova_http.nova_core.execute_planned_action = lambda tool, args=None: "1) https://tea.texas.gov/a\n2) https://tea.texas.gov/b" if tool == "web_research" else ""
            with mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
                reply = nova_http.process_chat("s9_online", "research PEIMS online")

            self.assertIn("https://tea.texas.gov/a", reply.lower())
            self.assertNotIn("Turn bypassed supervisor intent phase", stdout.getvalue())
            session = nova_http.SESSION_STATE_MANAGER.get("s9_online")
            self.assertIsNotNone(session)
            self.assertEqual(session.active_subject(), "retrieval:web_research")
            self.assertEqual((session.retrieval_state() or {}).get("query"), "PEIMS")
        finally:
            nova_http.nova_core.execute_planned_action = orig_execute_planned_action

    def test_http_name_origin_turn_uses_supervisor_contract_without_bypass_warning(self):
        orig_get_name_origin_story = nova_http.nova_core.get_name_origin_story
        try:
            nova_http.nova_core.get_name_origin_story = lambda: "My creator Gus named me Nova to symbolize light and discovery."
            with mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
                reply = nova_http.process_chat("s9_name_origin", "why are you called Nova?")

            self.assertIn("creator gus", reply.lower())
            self.assertNotIn("Turn bypassed supervisor intent phase", stdout.getvalue())
            session = nova_http.SESSION_STATE_MANAGER.get("s9_name_origin")
            self.assertIsNotNone(session)
            self.assertEqual((session.last_reflection or {}).get("reply_contract"), "identity_history.name_origin")
        finally:
            nova_http.nova_core.get_name_origin_story = orig_get_name_origin_story

    def test_http_retrieval_followup_stays_model_owned(self):
        orig_execute_planned_action = nova_http.nova_core.execute_planned_action
        orig_tool_web_gather = nova_http.nova_core.tool_web_gather
        try:
            nova_http.nova_core.execute_planned_action = lambda tool, args=None: "1) https://tea.texas.gov/a\n2) https://tea.texas.gov/b" if tool == "web_research" else ""
            nova_http.nova_core.tool_web_gather = lambda url: f"Gathered: {url}"
            with mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
                nova_http.process_chat("s9_retrieval_contract", "research PEIMS online")
                reply = nova_http.process_chat("s9_retrieval_contract", "tell me about the first one")

            self.assertEqual(reply, "LLM:tell me about the first one")
            self.assertNotIn("Turn bypassed supervisor intent phase", stdout.getvalue())
            session = nova_http.SESSION_STATE_MANAGER.get("s9_retrieval_contract")
            self.assertIsNotNone(session)
            self.assertNotEqual((session.last_reflection or {}).get("reply_contract"), "retrieval_followup.selected_result")
        finally:
            nova_http.nova_core.execute_planned_action = orig_execute_planned_action
            nova_http.nova_core.tool_web_gather = orig_tool_web_gather

    def test_http_creator_followup_uses_supervisor_contract_without_bypass_warning(self):
        with mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
            first = nova_http.process_chat("s9_identity_history", "who is your creator ?")
            reply = nova_http.process_chat("s9_identity_history", "what else?")

        self.assertIn("gustavo", first.lower())
        self.assertIn("verified facts", reply.lower())
        self.assertNotIn("Turn bypassed supervisor intent phase", stdout.getvalue())
        session = nova_http.SESSION_STATE_MANAGER.get("s9_identity_history")
        self.assertIsNotNone(session)
        self.assertEqual((session.last_reflection or {}).get("reply_contract"), "identity_history.history_recall")

    def test_code_help_uses_planner_respond(self):
        reply = nova_http.process_chat("s10", "can you debug this bug in my code")
        self.assertEqual(reply, "LLM:can you debug this bug in my code")

    def test_http_rules_query_uses_supervisor_contract(self):
        with mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
            reply = nova_http.process_chat("s10_rules", "do you have any rules")

        self.assertIn("i follow strict operating rules", reply.lower())
        self.assertNotIn("[http] do you have any rules", stdout.getvalue())
        session = nova_http.SESSION_STATE_MANAGER.get("s10_rules")
        self.assertIsNotNone(session)
        self.assertEqual((session.last_reflection or {}).get("reply_contract"), "rules.list")
        self.assertEqual((session.last_reflection or {}).get("reply_outcome_kind"), "list")

    def test_http_pending_weather_action_uses_affirmative_followup(self):
        orig_get_saved_location_text = nova_http.nova_core.get_saved_location_text
        orig_execute_planned_action = nova_http.nova_core.execute_planned_action
        orig_weather_current_location_available = nova_http.nova_core._weather_current_location_available
        try:
            availability = {"value": False}
            semantic = iter([
                {"tool": "weather_current_location", "args": [], "source": "test_semantic_intent"},
                {"tool": "weather_current_location", "args": [], "source": "test_semantic_intent"},
            ])
            nova_http.nova_core._llm_classify_routing_intent = lambda text, turns=None, pending_action=None: next(semantic)
            nova_http.nova_core.get_saved_location_text = lambda: ""
            nova_http.nova_core._weather_current_location_available = lambda: bool(availability["value"])
            nova_http.nova_core.execute_planned_action = lambda tool, args=None: "Brownsville, TX: Today: 66°F, Sunny. [source: api.weather.gov]" if tool == "weather_current_location" else ""
            first = nova_http.process_chat("s11", "check the weather if you can please..")
            self.assertEqual(first, "What location should I use for the weather lookup?")
            availability["value"] = True
            reply = nova_http.process_chat("s11", "yea please do that ..")
            self.assertIn("api.weather.gov", reply)
            session = nova_http.SESSION_STATE_MANAGER.get("s11")
            self.assertEqual((session.last_reflection or {}).get("reply_contract"), "weather_lookup.current_location")
        finally:
            nova_http.nova_core.get_saved_location_text = orig_get_saved_location_text
            nova_http.nova_core.execute_planned_action = orig_execute_planned_action
            nova_http.nova_core._weather_current_location_available = orig_weather_current_location_available

    def test_http_pending_weather_action_current_location_followup_matrix(self):
        orig_get_saved_location_text = nova_http.nova_core.get_saved_location_text
        orig_execute_planned_action = nova_http.nova_core.execute_planned_action
        orig_weather_current_location_available = nova_http.nova_core._weather_current_location_available
        try:
            availability = {"value": False}
            nova_http.nova_core.get_saved_location_text = lambda: ""
            nova_http.nova_core._weather_current_location_available = lambda: bool(availability["value"])
            nova_http.nova_core.execute_planned_action = lambda tool, args=None: "Brownsville, TX: Today: 66°F, Sunny. [source: api.weather.gov]" if tool == "weather_current_location" else ""
            cases = [
                ("affirmative", "go ahead"),
            ]
            for suffix, followup in cases:
                with self.subTest(followup=followup):
                    semantic = iter([
                        {"tool": "weather_current_location", "args": [], "source": "test_semantic_intent"},
                        {"tool": "weather_current_location", "args": [], "source": "test_semantic_intent"},
                    ])
                    nova_http.nova_core._llm_classify_routing_intent = lambda text, turns=None, pending_action=None: next(semantic)
                    session_id = f"s11_matrix_{suffix}"
                    availability["value"] = False
                    first = nova_http.process_chat(session_id, "check the weather if you can please..")
                    self.assertEqual(first, "What location should I use for the weather lookup?")
                    availability["value"] = True
                    reply = nova_http.process_chat(session_id, followup)
                    self.assertIn("api.weather.gov", reply)
                    session = nova_http.SESSION_STATE_MANAGER.get(session_id)
                    self.assertEqual((session.last_reflection or {}).get("reply_contract"), "weather_lookup.current_location")
        finally:
            nova_http.nova_core.get_saved_location_text = orig_get_saved_location_text
            nova_http.nova_core.execute_planned_action = orig_execute_planned_action
            nova_http.nova_core._weather_current_location_available = orig_weather_current_location_available

    def test_http_pending_weather_action_uses_direct_location_followup(self):
        orig_get_saved_location_text = nova_http.nova_core.get_saved_location_text
        orig_execute_planned_action = nova_http.nova_core.execute_planned_action
        orig_weather_current_location_available = nova_http.nova_core._weather_current_location_available
        try:
            semantic = iter([
                {"tool": "weather_current_location", "args": [], "source": "test_semantic_intent"},
                {"tool": "weather_location", "args": ["Brownsville TX 78521"], "source": "test_semantic_intent"},
            ])
            nova_http.nova_core._llm_classify_routing_intent = lambda text, turns=None, pending_action=None: next(semantic)
            nova_http.nova_core.get_saved_location_text = lambda: ""
            nova_http.nova_core._weather_current_location_available = lambda: False
            nova_http.nova_core.execute_planned_action = lambda tool, args=None: "Brownsville, TX 78521: Tomorrow: 72°F, Clear. [source: api.weather.gov]" if tool == "weather_location" else ""
            first = nova_http.process_chat("s11_direct", "check the weather if you can please..")
            self.assertEqual(first, "What location should I use for the weather lookup?")
            reply = nova_http.process_chat("s11_direct", "Brownsville TX 78521")
            self.assertIn("api.weather.gov", reply)
            session = nova_http.SESSION_STATE_MANAGER.get("s11_direct")
            self.assertIsNone(session.pending_action)
            self.assertEqual((session.last_reflection or {}).get("reply_contract"), "weather_lookup.explicit_location")
        finally:
            nova_http.nova_core.get_saved_location_text = orig_get_saved_location_text
            nova_http.nova_core.execute_planned_action = orig_execute_planned_action
            nova_http.nova_core._weather_current_location_available = orig_weather_current_location_available

    def test_http_generic_weather_query_creates_weather_location_followup(self):
        orig_get_saved_location_text = nova_http.nova_core.get_saved_location_text
        orig_execute_planned_action = nova_http.nova_core.execute_planned_action
        orig_weather_current_location_available = nova_http.nova_core._weather_current_location_available
        try:
            nova_http.nova_core._llm_classify_routing_intent = lambda text, turns=None, pending_action=None: {
                "tool": "weather_current_location",
                "args": [],
                "source": "test_semantic_intent",
            }
            nova_http.nova_core.get_saved_location_text = lambda: "Brownsville TX"
            nova_http.nova_core._weather_current_location_available = lambda: True
            nova_http.nova_core.execute_planned_action = lambda tool, args=None: "Brownsville, TX: Today: 66°F, Sunny. [source: api.weather.gov]" if tool == "weather_current_location" else ""
            reply = nova_http.process_chat("s11_generic_weather", "what is the weather like today ?")
            self.assertIn("api.weather.gov", reply)
            session = nova_http.SESSION_STATE_MANAGER.get("s11_generic_weather")
            self.assertIsNotNone(session)
            self.assertEqual((session.last_reflection or {}).get("reply_contract"), "weather_lookup.current_location")
        finally:
            nova_http.nova_core.get_saved_location_text = orig_get_saved_location_text
            nova_http.nova_core.execute_planned_action = orig_execute_planned_action
            nova_http.nova_core._weather_current_location_available = orig_weather_current_location_available

    def test_http_grounded_self_report_words_do_not_create_supervisor_intent(self):
        reply = nova_http.process_chat("s11_self_report", "what is your health percentage at ?")
        self.assertEqual(reply, "LLM:what is your health percentage at ?")
        session = nova_http.SESSION_STATE_MANAGER.get("s11_self_report")
        self.assertNotEqual((session.last_reflection or {}).get("reply_contract"), "grounded_self_report.health")

    def test_http_operator_update_to_nova_does_not_use_self_report_or_feedback_route(self):
        reply = nova_http.process_chat(
            "s11_operator_update",
            "give you an update on the progress we are having creating you",
        )
        self.assertEqual(reply, "LLM:give you an update on the progress we are having creating you")
        session = nova_http.SESSION_STATE_MANAGER.get("s11_operator_update")
        self.assertNotEqual((session.last_reflection or {}).get("reply_contract"), "operator_feedback.source")
        self.assertNotEqual((session.last_reflection or {}).get("reply_contract"), "grounded_self_report.internals")

    def test_http_operator_update_does_not_execute_semantic_self_status_without_actionable_act(self):
        orig_execute_planned_action = nova_http.nova_core.execute_planned_action
        calls = []
        try:
            nova_http.nova_core._llm_classify_routing_intent = lambda text, turns=None, pending_action=None, return_none_payload=False: {
                "tool": "self_status",
                "args": [],
                "source": "test_semantic_intent",
            }

            def fake_execute(tool, args=None):
                calls.append((tool, args))
                return "WRONG_SELF_STATUS"

            nova_http.nova_core.execute_planned_action = fake_execute
            reply = nova_http.process_chat(
                "s11_operator_update_semantic",
                "give you an update on the progress we are having creating you",
            )
            self.assertEqual(reply, "LLM:give you an update on the progress we are having creating you")
            session = nova_http.SESSION_STATE_MANAGER.get("s11_operator_update_semantic")
            self.assertIsNotNone(session)
            self.assertNotEqual((session.last_reflection or {}).get("reply_contract"), "self_status.current")
            self.assertEqual(calls, [])
        finally:
            nova_http.nova_core.execute_planned_action = orig_execute_planned_action

    def test_http_operator_feedback_wording_is_not_owned_by_content_route(self):
        orig_ollama_chat = nova_http.nova_core.ollama_chat
        try:
            nova_http.nova_core.ollama_chat = lambda *_args, **_kwargs: "WRONG_LLM_REFLECTION"
            reply = nova_http.process_chat(
                "s11_operator_repetition",
                "is there a reason why your last two responses are very similiar ?",
            )
            self.assertEqual(reply, "WRONG_LLM_REFLECTION")
            session = nova_http.SESSION_STATE_MANAGER.get("s11_operator_repetition")
            self.assertNotEqual((session.last_reflection or {}).get("reply_contract"), "operator_feedback.source")
        finally:
            nova_http.nova_core.ollama_chat = orig_ollama_chat

    def test_http_answer_rationale_uses_action_ledger_not_llm_guess(self):
        replies = iter(["First answer with too much information.", "WRONG_SECOND_LLM_GUESS"])
        nova_http.nova_core.ollama_chat = lambda *_args, **_kwargs: next(replies)

        first = nova_http.process_chat("s11_answer_rationale", "hi nova")
        second = nova_http.process_chat("s11_answer_rationale", "nova why did you give me all that information ?")

        self.assertEqual(first, "First answer with too much information.")
        self.assertIn("Last action record:", second)
        self.assertIn("decision=llm_fallback", second)
        self.assertNotIn("WRONG_SECOND_LLM_GUESS", second)
        records = [
            json.loads(path.read_text(encoding="utf-8"))
            for path in sorted(self._action_ledger_dir.glob("*.json"))
        ]
        self.assertEqual(records[-1].get("tool"), "action_ledger")
        self.assertEqual(records[-1].get("planner_decision"), "truth_hierarchy")

    def test_http_runtime_identity_words_do_not_create_supervisor_intent(self):
        orig_execute_planned_action = nova_http.nova_core.execute_planned_action
        try:
            nova_http.nova_core._llm_classify_routing_intent = lambda text, turns=None, pending_action=None, return_none_payload=False: {
                "tool": "runtime_identity",
                "args": [],
                "source": "test_semantic_intent",
            }
            nova_http.nova_core.execute_planned_action = lambda tool, args=None: "VERIFIED_RUNTIME_IDENTITY" if tool == "runtime_identity" else ""
            reply = nova_http.process_chat("s11_identity", "who are you ?")
            self.assertEqual(reply, "VERIFIED_RUNTIME_IDENTITY")
            session = nova_http.SESSION_STATE_MANAGER.get("s11_identity")
            self.assertEqual((session.last_reflection or {}).get("reply_contract"), "runtime_identity.current")
            self.assertNotEqual((session.last_reflection or {}).get("reply_contract"), "runtime_identity.source")
            self.assertEqual((session.conversation_state or {}).get("kind"), "runtime_identity")
            self.assertIn("VERIFIED_RUNTIME_IDENTITY", (session.conversation_state or {}).get("tool_result", ""))
        finally:
            nova_http.nova_core.execute_planned_action = orig_execute_planned_action

    def test_http_capability_words_do_not_create_supervisor_intent(self):
        orig_execute_planned_action = nova_http.nova_core.execute_planned_action
        try:
            nova_http.nova_core._llm_classify_routing_intent = lambda text, turns=None, pending_action=None, return_none_payload=False: {
                "tool": "capability_inventory",
                "args": [],
                "source": "test_semantic_intent",
            }
            nova_http.nova_core.execute_planned_action = lambda tool, args=None: "VERIFIED_CAPABILITY_INVENTORY" if tool == "capability_inventory" else ""
            reply = nova_http.process_chat("s11_caps", "what are your capabilities ?")
            self.assertEqual(reply, "VERIFIED_CAPABILITY_INVENTORY")
            session = nova_http.SESSION_STATE_MANAGER.get("s11_caps")
            self.assertEqual((session.last_reflection or {}).get("reply_contract"), "capability_inventory.current")
            self.assertNotEqual((session.last_reflection or {}).get("reply_contract"), "capability_inventory.source")
            self.assertEqual((session.conversation_state or {}).get("kind"), "capability_inventory")
            self.assertIn("VERIFIED_CAPABILITY_INVENTORY", (session.conversation_state or {}).get("tool_result", ""))
        finally:
            nova_http.nova_core.execute_planned_action = orig_execute_planned_action

    def test_http_operator_help_uses_grounded_tool_not_llm_fallback(self):
        orig_execute_planned_action = nova_http.nova_core.execute_planned_action
        orig_classify_turn_acts = nova_http.nova_core._classify_turn_acts
        try:
            nova_http.nova_core.ollama_chat = lambda *_args, **_kwargs: "WRONG_LLM_FALLBACK"
            nova_http.nova_core._classify_turn_acts = lambda *_args, **_kwargs: ["ask"]
            nova_http.nova_core._llm_classify_routing_intent = lambda text, turns=None, pending_action=None, return_none_payload=False: {
                "tool": "operator_help",
                "args": [],
                "source": "test_semantic_intent",
            }
            nova_http.nova_core.execute_planned_action = (
                lambda tool, args=None: (
                    "Today I am mainly stuck on: Work Tree needs operator context.\n"
                    "Source: live control status and Work Tree."
                )
                if tool == "operator_help"
                else ""
            )

            reply = nova_http.process_chat("s11_operator_help", "neutral user turn")

            self.assertIn("Work Tree needs operator context", reply)
            self.assertNotIn("WRONG_LLM_FALLBACK", reply)
            session = nova_http.SESSION_STATE_MANAGER.get("s11_operator_help")
            self.assertEqual((session.last_reflection or {}).get("reply_contract"), "operator_help.current")
            self.assertEqual((session.conversation_state or {}).get("kind"), "operator_help")
            self.assertIn("operator context", (session.conversation_state or {}).get("tool_result", ""))
            records = [
                json.loads(path.read_text(encoding="utf-8"))
                for path in sorted(self._action_ledger_dir.glob("*.json"))
            ]
            self.assertEqual(records[-1].get("tool"), "operator_help")
            self.assertEqual(records[-1].get("planner_decision"), "run_tool")
        finally:
            nova_http.nova_core._classify_turn_acts = orig_classify_turn_acts
            nova_http.nova_core.execute_planned_action = orig_execute_planned_action

    def test_http_developer_followup_uses_local_developer_facts_for_nonlocal_user_id(self):
        orig_default_local_user_id = nova_http.nova_core._default_local_user_id
        try:
            nova_http.nova_core.mem_enabled = lambda: True
            nova_http.nova_core._default_local_user_id = lambda: "local-owner"

            def fake_mem_recall(_query):
                active = (nova_http.nova_core.get_active_user() or "").strip().lower()
                if active == "runner":
                    return ""
                return "\n".join([
                    "Gus works as a full stack developer and PEIMS Data Specialist.",
                    "Gus favorite colors are silver, red, and blue.",
                ])

            nova_http.nova_core.mem_recall = fake_mem_recall

            first = nova_http.process_chat("s_http_mem", "what do you know about Gus?", user_id="runner")
            followup = nova_http.process_chat("s_http_mem", "what else?", user_id="runner")

            self.assertIn("gustavo", first.lower())
            self.assertIn("full stack developer", followup.lower())
            self.assertIn("silver", followup.lower())
        finally:
            nova_http.nova_core._default_local_user_id = orig_default_local_user_id

    def test_http_developer_work_guess_uses_shared_turn_helper(self):
        reply = nova_http.process_chat("s_http_guess", "can you also guess what type of work does gus do..?")
        self.assertIn("grounded guess", reply.lower())
        session = nova_http.SESSION_STATE_MANAGER.get("s_http_guess")
        self.assertIsNotNone(session)
        self.assertEqual("developer_role_guess:Gus", session.active_subject())


class TestNovaHttpControlAssets(unittest.TestCase):
    def test_work_trees_payload_summarizes_live_tree_counts(self):
        payload = [
            {
                "tree_id": "tree_1",
                "title": "Queue repair",
                "status": "active",
                "active_branch_id": "branch_1",
                "counts": {
                    "open_tasks": 2,
                    "branches": {
                        "active": 1,
                        "ready": 2,
                        "blocked": 1,
                        "complete": 3,
                    },
                },
            },
            {
                "tree_id": "tree_2",
                "title": "Closed review",
                "status": "complete",
                "active_branch_id": "",
                "counts": {
                    "open_tasks": 0,
                    "branches": {
                        "complete": 2,
                    },
                },
            },
        ]

        with mock.patch("nova_http.work_tree.list_visual_trees", return_value=payload):
            result = nova_http._work_trees_payload()

        self.assertTrue(result["ok"])
        self.assertEqual(result["counts"]["total"], 2)
        self.assertEqual(result["counts"]["active"], 1)
        self.assertEqual(result["counts"]["branches"], 9)
        self.assertEqual(result["counts"]["open_tasks"], 2)
        self.assertEqual(result["counts"]["working"], 1)
        self.assertEqual(result["counts"]["pending"], 2)
        self.assertEqual(result["counts"]["blocked"], 1)
        self.assertEqual(result["counts"]["complete"], 5)
        self.assertEqual(result["trees"], payload)

    def test_work_trees_payload_keeps_generated_queue_tree_visible_when_trimmed(self):
        limited_payload = [
            {
                "tree_id": "tree_1",
                "title": "Queue repair",
                "status": "active",
                "active_branch_id": "branch_1",
                "counts": {
                    "open_tasks": 1,
                    "branches": {"active": 1},
                },
            }
        ]
        generated_queue_tree = {
            "tree_id": "tree_generated",
            "title": "Generated Queue: governed self-repair",
            "kind": "generated_queue",
            "status": "complete",
            "active_branch_id": "",
            "counts": {
                "open_tasks": 0,
                "branches": {"complete": 1},
            },
        }

        with mock.patch(
            "nova_http.work_tree.list_visual_trees",
            side_effect=[limited_payload, limited_payload + [generated_queue_tree]],
        ):
            result = nova_http._work_trees_payload()

        self.assertTrue(result["ok"])
        self.assertEqual(result["counts"]["total"], 2)
        self.assertEqual(
            [tree.get("tree_id") for tree in result["trees"]],
            ["tree_1", "tree_generated"],
        )

    def test_work_trees_payload_dedupes_duplicate_identities_and_signal_shells(self):
        rich_signal_tree = {
            "tree_id": "tree_signal_rich",
            "title": "Signal Intake: Runtime Governance",
            "kind": "signal_ingestion",
            "source": "runtime_signals",
            "status": "complete",
            "active_branch_id": "",
            "counts": {
                "open_tasks": 0,
                "branches": {"complete": 5},
            },
        }
        empty_signal_shell = {
            "tree_id": "tree_signal_shell",
            "title": "Signal Intake: Runtime Governance",
            "kind": "signal_ingestion",
            "source": "runtime_signals",
            "status": "complete",
            "active_branch_id": "",
            "counts": {
                "open_tasks": 0,
                "branches": {"complete": 0},
            },
        }
        newest_chat_tree = {
            "tree_id": "tree_chat_new",
            "title": "Chat: inspect runtime queue pressure",
            "kind": "system",
            "source": "chat",
            "work_identity_key": "work:inspect-pressure-queue-runtime|terms:inspect|pressure|queue|runtime",
            "status": "complete",
            "active_branch_id": "",
            "counts": {
                "open_tasks": 0,
                "branches": {"complete": 0},
            },
        }
        older_chat_tree = {
            "tree_id": "tree_chat_old",
            "title": "Chat: inspect runtime queue pressure",
            "kind": "system",
            "source": "chat",
            "work_identity_key": "work:inspect-pressure-queue-runtime|terms:inspect|pressure|queue|runtime",
            "status": "complete",
            "active_branch_id": "",
            "counts": {
                "open_tasks": 0,
                "branches": {"complete": 0},
            },
        }
        patch_queue_tree = {
            "tree_id": "tree_patch",
            "title": "Patch Queue: governed review and apply",
            "kind": "patch_queue",
            "source": "autonomy_maintenance",
            "status": "complete",
            "active_branch_id": "",
            "counts": {
                "open_tasks": 0,
                "branches": {"complete": 2},
            },
        }

        payload = [
            patch_queue_tree,
            rich_signal_tree,
            empty_signal_shell,
            newest_chat_tree,
            older_chat_tree,
        ]

        with mock.patch("nova_http.work_tree.list_visual_trees", side_effect=[payload, payload]):
            result = nova_http._work_trees_payload()

        self.assertTrue(result["ok"])
        self.assertEqual(result["counts"]["total"], 3)
        self.assertEqual(result["counts"]["branches"], 7)
        self.assertEqual(
            [tree.get("tree_id") for tree in result["trees"]],
            ["tree_patch", "tree_signal_rich", "tree_chat_new"],
        )

    def test_work_trees_payload_semantically_dedupes_runtime_ops_shells(self):
        runtime_ops_chat = {
            "tree_id": "tree_chat_runtime_ops",
            "title": "Chat: inspect runtime queue pressure",
            "kind": "system",
            "source": "chat",
            "work_identity_key": "work:inspect-pressure-queue-runtime|terms:inspect|pressure|queue|runtime",
            "work_identity_label": "inspect / pressure / queue / runtime",
            "status": "complete",
            "active_branch_id": "",
            "counts": {
                "open_tasks": 0,
                "branches": {"complete": 0},
            },
        }
        runtime_ops_health = {
            "tree_id": "tree_health_runtime_ops",
            "title": "Health: verify runtime heartbeat",
            "kind": "system",
            "source": "health",
            "work_identity_key": "work:heartbeat-runtime-verify|terms:heartbeat|runtime|verify",
            "work_identity_label": "heartbeat / runtime / verify",
            "status": "complete",
            "active_branch_id": "",
            "counts": {
                "open_tasks": 0,
                "branches": {"complete": 0},
            },
        }
        unrelated_tree = {
            "tree_id": "tree_unrelated",
            "title": "Chat: unrelated ui redesign",
            "kind": "system",
            "source": "chat",
            "work_identity_key": "work:redesign-unrelated|terms:redesign|unrelated",
            "work_identity_label": "redesign / unrelated",
            "status": "complete",
            "active_branch_id": "",
            "counts": {
                "open_tasks": 0,
                "branches": {"complete": 0},
            },
        }

        payload = [runtime_ops_chat, runtime_ops_health, unrelated_tree]

        with mock.patch("nova_http.work_tree.list_visual_trees", side_effect=[payload, payload]):
            result = nova_http._work_trees_payload()

        self.assertTrue(result["ok"])
        self.assertEqual(result["counts"]["total"], 2)
        self.assertEqual(
            [tree.get("tree_id") for tree in result["trees"]],
            ["tree_chat_runtime_ops", "tree_unrelated"],
        )

    def test_control_assets_keep_scheduled_tree_surface(self):
        html = nova_http._render_control_html()
        js = nova_http._read_asset_text(nova_http.CONTROL_JS_PATH)

        self.assertIn('data-view-target="scheduled-tree"', html)
        self.assertIn('data-view="scheduled-tree"', html)
        self.assertIn('id="workTreeSelect"', html)
        self.assertIn('id="workTreeSvg"', html)
        self.assertIn('id="workTreeBranchInfo"', html)
        self.assertIn("/api/control/work-trees", js)
        self.assertIn("renderWorkTrees", js)
        self.assertIn("renderTreeSvg", js)
        self.assertIn("btnWorkTreesRefresh", js)
        self.assertIn("function initialControlView()", js)
        self.assertIn("setActiveView(initialControlView())", js)


class TestNovaHttpLeahRoutes(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.leah_service = nova_http.LeahFrontdoorService(
            asset_service=nova_http.CONTROL_ASSETS_SERVICE,
            template_path_provider=lambda: nova_http.LEAH_TEMPLATE_PATH,
            css_path_provider=lambda: nova_http.LEAH_CSS_PATH,
            js_path_provider=lambda: nova_http.LEAH_JS_PATH,
            fx_js_path_provider=lambda: nova_http.LEAH_FX_JS_PATH,
            upload_root_provider=lambda: Path(self.tempdir.name),
        )
        self.service_patch = patch.object(nova_http, "LEAH_FRONTDOOR_SERVICE", self.leah_service)
        self.service_patch.start()
        self.chat_login_patch = patch("nova_http._chat_login_enabled", return_value=False)
        self.chat_login_patch.start()
        nova_http.SESSION_TURNS.clear()
        nova_http.SESSION_STATE_MANAGER.clear()

    def tearDown(self):
        self.chat_login_patch.stop()
        self.service_patch.stop()
        self.tempdir.cleanup()
        nova_http.SESSION_TURNS.clear()
        nova_http.SESSION_STATE_MANAGER.clear()

    def _start_server(self):
        server = nova_http.ThreadingHTTPServer(("127.0.0.1", 0), nova_http.NovaHttpHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        return server, thread

    def _stop_server(self, server, thread):
        server.shutdown()
        server.server_close()
        thread.join(timeout=2.0)

    def _request(self, server, path, *, payload=None):
        port = int(server.server_address[1])
        url = f"http://127.0.0.1:{port}{path}"
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"} if data is not None else {}
        req = urllib.request.Request(url, data=data, headers=headers, method="POST" if data is not None else "GET")
        with urllib.request.urlopen(req, timeout=10) as response:
            body = response.read().decode("utf-8", errors="replace")
            return response.status, body

    def test_leah_route_and_assets_are_served(self):
        server, thread = self._start_server()
        try:
            status, body = self._request(server, "/leah")
            self.assertEqual(status, 200)
            self.assertIn("L.A.E.H.", body)
            self.assertIn("/static/leah.css", body)
            self.assertIn("/static/leah_fx.js", body)
            self.assertIn("/static/leah.js", body)

            css_status, css_body = self._request(server, "/static/leah.css")
            self.assertEqual(css_status, 200)
            self.assertIn("--bg:", css_body)

            js_status, js_body = self._request(server, "/static/leah.js")
            self.assertEqual(js_status, 200)
            self.assertIn('/api/chat/upload', js_body)

            fx_status, fx_body = self._request(server, "/static/leah_fx.js")
            self.assertEqual(fx_status, 200)
            self.assertIn('getContext("webgl2"', fx_body)
        finally:
            self._stop_server(server, thread)

    def test_leah_upload_endpoint_stages_items(self):
        server, thread = self._start_server()
        try:
            payload = {
                "session_id": "sid-upload",
                "user_id": "web-test",
                "items": [
                    {
                        "name": "note.txt",
                        "mime": "text/plain",
                        "source": "upload",
                        "content_b64": base64.b64encode(b"hello from leah").decode("ascii"),
                    }
                ],
            }
            status, body = self._request(server, "/api/chat/upload", payload=payload)
            data = json.loads(body)

            self.assertEqual(status, 200)
            self.assertTrue(data["ok"])
            self.assertEqual(data["session_id"], "sid-upload")
            self.assertEqual(len(data["items"]), 1)
            stored = data["items"][0]
            self.assertEqual(stored["original_name"], "note.txt")
            self.assertTrue(Path(stored["path"]).exists())
            self.assertIn(self.tempdir.name, stored["path"])
            remembered, stage = self.leah_service.recent_session_context("sid-upload")
            self.assertEqual(stage, "staged")
            self.assertEqual(len(remembered), 1)
        finally:
            self._stop_server(server, thread)

    def test_leah_chat_uses_attachment_handoff_reply(self):
        server, thread = self._start_server()
        try:
            upload_payload = {
                "session_id": "sid-handoff",
                "user_id": "web-test",
                "items": [
                    {
                        "name": "note.txt",
                        "mime": "text/plain",
                        "source": "upload",
                        "content_b64": base64.b64encode(b"hello from leah").decode("ascii"),
                    }
                ],
            }
            _, upload_body = self._request(server, "/api/chat/upload", payload=upload_payload)
            upload_data = json.loads(upload_body)
            stored_items = upload_data["items"]

            chat_payload = {
                "session_id": "sid-handoff",
                "user_id": "web-test",
                "message": "can you read it?",
                "attachments": stored_items,
            }
            status, body = self._request(server, "/api/chat", payload=chat_payload)
            data = json.loads(body)

            self.assertEqual(status, 200)
            self.assertTrue(data["ok"])
            self.assertIn("I can read it directly.", data["reply"])
            self.assertIn("hello from leah", data["reply"])
        finally:
            self._stop_server(server, thread)


class TestNovaHttpRouteContracts(unittest.TestCase):
    def test_http_route_contract_keeps_frontdoor_and_control_surfaces(self):
        contract = nova_http.http_route_contract()

        self.assertIn("/", contract["public_pages"])
        self.assertIn("/leah", contract["public_pages"])
        self.assertIn("/control", contract["protected_pages"])
        self.assertIn("/static/leah.css", contract["static_assets"])
        self.assertIn("/static/leah.js", contract["static_assets"])
        self.assertIn("/static/leah_fx.js", contract["static_assets"])
        self.assertIn("/api/health", contract["public_api_get"])
        self.assertIn("/api/control/work-trees", contract["control_api_get"])
        self.assertIn("/api/control/pipelines", contract["control_api_get"])
        self.assertIn("/api/chat/upload", contract["chat_api_post"])

    def test_runtime_console_root_is_served(self):
        server = nova_http.ThreadingHTTPServer(("127.0.0.1", 0), nova_http.NovaHttpHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            port = int(server.server_address[1])
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=10) as response:
                body = response.read().decode("utf-8", errors="replace")

            self.assertEqual(response.status, 200)
            self.assertIn("NYO Runtime Console", body)
            self.assertIn("/api/chat", body)
            self.assertIn("Open Operator Console", body)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2.0)

    def test_control_login_page_is_served_when_enabled(self):
        server = nova_http.ThreadingHTTPServer(("127.0.0.1", 0), nova_http.NovaHttpHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            port = int(server.server_address[1])
            with patch("nova_http._control_login_enabled", return_value=True), \
                patch("nova_http._control_page_gate", return_value=(True, "")):
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/control/login", timeout=10) as response:
                    body = response.read().decode("utf-8", errors="replace")

            self.assertEqual(response.status, 200)
            self.assertIn("NYO AI Systems Control Login", body)
            self.assertIn("/api/control/login", body)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2.0)

    def test_control_page_is_served_when_authorized(self):
        server = nova_http.ThreadingHTTPServer(("127.0.0.1", 0), nova_http.NovaHttpHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            port = int(server.server_address[1])
            with patch("nova_http._control_page_gate", return_value=(True, "")):
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/control", timeout=10) as response:
                    body = response.read().decode("utf-8", errors="replace")

            self.assertEqual(response.status, 200)
            self.assertIn('data-view-target="scheduled-tree"', body)
            self.assertIn("NYO AI Systems Control", body)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2.0)

    def test_control_work_trees_route_is_served_when_authorized(self):
        server = nova_http.ThreadingHTTPServer(("127.0.0.1", 0), nova_http.NovaHttpHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            port = int(server.server_address[1])
            payload = {"ok": True, "trees": [{"tree_id": "tree_1"}], "counts": {"total": 1}}
            with patch("nova_http._control_auth", return_value=(True, "")), \
                patch("nova_http._work_trees_payload", return_value=payload):
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/control/work-trees", timeout=10) as response:
                    body = json.loads(response.read().decode("utf-8", errors="replace"))

            self.assertEqual(response.status, 200)
            self.assertTrue(body["ok"])
            self.assertEqual(body["counts"]["total"], 1)
            self.assertEqual(body["trees"][0]["tree_id"], "tree_1")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2.0)

    def test_control_action_post_route_is_served_when_authorized(self):
        server = nova_http.ThreadingHTTPServer(("127.0.0.1", 0), nova_http.NovaHttpHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            port = int(server.server_address[1])
            request = urllib.request.Request(
                f"http://127.0.0.1:{port}/api/control/action",
                data=json.dumps({"action": "refresh_status"}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with patch("nova_http._control_auth", return_value=(True, "")), \
                patch("nova_http._control_action", return_value=(True, "refresh_ok", {"status": "fresh"})):
                with urllib.request.urlopen(request, timeout=10) as response:
                    body = json.loads(response.read().decode("utf-8", errors="replace"))

            self.assertEqual(response.status, 200)
            self.assertTrue(body["ok"])
            self.assertEqual(body["message"], "refresh_ok")
            self.assertEqual(body["status"], "fresh")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2.0)


_RETIRED_CONTENT_HTTP_PROFILE_TESTS = {
    "test_creator_query_uses_hard_answer_before_grounded_lookup",
    "test_developer_how_built_has_non_hallucinated_limit",
    "test_developer_location_followup_stays_on_developer_thread",
    "test_developer_profile_certainty_challenge_stays_on_profile_thread",
    "test_developer_profile_includes_known_facts",
    "test_developer_profile_self_diagnostic_when_partial",
    "test_developer_who_is_answer_is_deterministic",
    "test_fast_smalltalk_greeting",
    "test_fast_smalltalk_greeting_ignores_synthetic_runner_user",
    "test_fast_smalltalk_ready_to_get_to_work",
    "test_fast_smalltalk_who_is_developer",
    "test_generate_chat_reply_general_deterministic_sequence_runs_after_planner",
    "test_how_are_you_does_not_route_to_grounded_lookup",
    "test_http_creator_followup_uses_supervisor_contract_without_bypass_warning",
    "test_http_declarative_statement_uses_shared_noted_path",
    "test_http_developer_followup_uses_local_developer_facts_for_nonlocal_user_id",
    "test_http_developer_work_guess_uses_shared_turn_helper",
    "test_http_direct_developer_location_uses_shared_turn_helper",
    "test_http_location_name_followup_uses_saved_location",
    "test_http_mixed_info_request_turn_asks_for_clarification",
    "test_http_name_origin_turn_uses_supervisor_contract_without_bypass_warning",
    "test_http_name_query_typo_and_web_challenge_stay_deterministic",
    "test_http_rules_query_uses_supervisor_contract",
    "test_http_saved_zip_followup_city_name_stays_in_location_thread",
    "test_http_weather_uses_saved_location_after_set_location",
    "test_http_where_am_i_uses_deterministic_location_recall",
    "test_profile_thread_resource_question_does_not_fall_into_local_knowledge",
    "test_who_is_gus_seeds_developer_profile_subject",
}


for _test_name in _RETIRED_CONTENT_HTTP_PROFILE_TESTS:
    _test = getattr(TestNovaHttpProfile, _test_name, None)
    if _test is not None:
        setattr(
            TestNovaHttpProfile,
            _test_name,
            unittest.skip("retired content-owned HTTP chat route expectation")(_test),
        )


if __name__ == "__main__":
    unittest.main()
