import tempfile
import unittest
import json
from hashlib import sha1
from pathlib import Path
from unittest import mock

import nova_core
import nova_http
from scripts.run_test_session import compare_sessions
from scripts.run_test_session import _comparison_failed
from scripts.run_test_session import _isolated_runner_state
from scripts.run_test_session import load_session
from scripts.run_test_session import run_cli_session
from scripts.run_test_session import run_http_session
from scripts.run_test_session import run_run_tools_session


class TestRunTestSessionIsolation(unittest.TestCase):
    def test_isolated_runner_state_resets_and_restores_active_user(self):
        original_user = nova_core.get_active_user()
        try:
            nova_core.set_active_user("Gustavo Uribe")
            with tempfile.TemporaryDirectory() as td:
                with _isolated_runner_state(Path(td) / "runner"):
                    self.assertIsNone(nova_core.get_active_user())
            self.assertEqual(nova_core.get_active_user(), "Gustavo Uribe")
        finally:
            nova_core.set_active_user(original_user)

    def test_run_http_session_does_not_override_user_identity(self):
        captured_user_ids: list[str] = []

        def fake_process_chat(session_id: str, user_text: str, user_id: str = "") -> str:
            captured_user_ids.append(user_id)
            return f"reply:{user_text}"

        with tempfile.TemporaryDirectory() as td:
            with mock.patch.object(nova_http, "process_chat", side_effect=fake_process_chat):
                result = run_http_session(["hello", "why"], Path(td) / "http_runner")

        self.assertEqual(captured_user_ids, ["", ""])
        self.assertEqual(len(result.get("turns") or []), 2)

    def test_run_run_tools_session_uses_run_tools_session_id(self):
        captured_session_ids: list[str] = []

        def fake_process_chat(session_id: str, user_text: str, user_id: str = "") -> str:
            captured_session_ids.append(session_id)
            return f"reply:{user_text}"

        with tempfile.TemporaryDirectory() as td:
            with mock.patch.object(nova_http, "process_chat", side_effect=fake_process_chat):
                result = run_run_tools_session(["hello", "why"], Path(td) / "run_tools_runner")

        self.assertEqual(captured_session_ids, ["run-tools", "run-tools"])
        self.assertEqual(result.get("mode"), "run_tools")
        self.assertEqual(len(result.get("turns") or []), 2)

    def test_load_session_reads_compare_modes(self):
        with tempfile.TemporaryDirectory() as td:
            session_path = Path(td) / "run_tools_http.json"
            session_path.write_text(
                json.dumps(
                    {
                        "name": "run-tools-http",
                        "compare_modes": ["run_tools", "http"],
                        "messages": ["hello"],
                    }
                ),
                encoding="utf-8",
            )

            payload = load_session(str(session_path))

        self.assertEqual(payload.get("compare_modes"), ["run_tools", "http"])

    def test_load_session_reads_utf8_sig_json(self):
        with tempfile.TemporaryDirectory() as td:
            session_path = Path(td) / "bom_session.json"
            session_path.write_text(
                json.dumps(
                    {
                        "name": "bom-session",
                        "messages": ["hello"],
                    }
                ),
                encoding="utf-8-sig",
            )

            payload = load_session(str(session_path))

        self.assertEqual(payload.get("name"), "bom-session")
        self.assertEqual(payload.get("messages"), ["hello"])

    def test_generated_canary_has_no_cli_http_drift(self):
        with tempfile.TemporaryDirectory() as td:
            canary_path = Path(td) / "generated_canary.json"
            canary_path.write_text(
                json.dumps(
                    {
                        "name": "generated-canary",
                        "messages": [
                            "check queue status",
                            "and what should we do next",
                        ],
                    }
                ),
                encoding="utf-8",
            )
            session_meta = load_session(str(canary_path))

        orig_mem_recall = nova_core.mem_recall
        orig_kb_search = nova_core.kb_search
        orig_ollama_chat = nova_core.ollama_chat

        try:
            nova_core.mem_recall = lambda _query: f"- memory-user:{nova_core._memory_runtime_user() or 'none'}"
            nova_core.kb_search = lambda _query: ""

            def fake_ollama(_text: str, retrieved_context: str = "", **_kwargs) -> str:
                digest = sha1(retrieved_context.encode("utf-8")).hexdigest()[:12]
                return f"CANARY:{digest}"

            nova_core.ollama_chat = fake_ollama

            with tempfile.TemporaryDirectory() as td:
                base = Path(td)
                cli_result = run_cli_session(session_meta["messages"], base / "cli")
                http_result = run_http_session(session_meta["messages"], base / "http")

            comparison = compare_sessions(cli_result, http_result)
        finally:
            nova_core.mem_recall = orig_mem_recall
            nova_core.kb_search = orig_kb_search
            nova_core.ollama_chat = orig_ollama_chat

        self.assertTrue(comparison.get("turn_count_match"))
        self.assertEqual(comparison.get("diffs"), [])

    def test_generated_canary_has_no_run_tools_http_drift(self):
        with tempfile.TemporaryDirectory() as td:
            canary_path = Path(td) / "generated_canary.json"
            canary_path.write_text(
                json.dumps(
                    {
                        "name": "generated-canary-run-tools",
                        "compare_modes": ["run_tools", "http"],
                        "messages": [
                            "for this session remember the codeword cobalt sparrow",
                            "what codeword did i just give you",
                        ],
                    }
                ),
                encoding="utf-8",
            )
            session_meta = load_session(str(canary_path))

        orig_mem_recall = nova_core.mem_recall
        orig_kb_search = nova_core.kb_search
        orig_ollama_chat = nova_core.ollama_chat

        try:
            nova_core.mem_recall = lambda _query: f"- memory-user:{nova_core._memory_runtime_user() or 'none'}"
            nova_core.kb_search = lambda _query: ""

            def fake_ollama(_text: str, retrieved_context: str = "", **_kwargs) -> str:
                digest = sha1(retrieved_context.encode("utf-8")).hexdigest()[:12]
                return f"CANARY:{digest}"

            nova_core.ollama_chat = fake_ollama

            with tempfile.TemporaryDirectory() as td:
                base = Path(td)
                run_tools_result = run_run_tools_session(session_meta["messages"], base / "run_tools")
                http_result = run_http_session(session_meta["messages"], base / "http")

            comparison = compare_sessions(run_tools_result, http_result)
        finally:
            nova_core.mem_recall = orig_mem_recall
            nova_core.kb_search = orig_kb_search
            nova_core.ollama_chat = orig_ollama_chat

        self.assertEqual(comparison.get("left_mode"), "run_tools")
        self.assertEqual(comparison.get("right_mode"), "http")
        self.assertTrue(comparison.get("turn_count_match"))
        self.assertEqual(comparison.get("diffs"), [])

    def test_compare_sessions_ignores_route_summary_instrumentation_noise(self):
        cli = {
            "turns": [
                {
                    "assistant": "Not a file: C:/Nova/updates.zip",
                    "planner_decision": "run_tool",
                    "route_summary": "input:received -> direction_analysis:general_chat -> action_planner:run_tool -> tool_execution:ok -> finalize:run_tool",
                    "active_subject": "",
                    "continuation_used": False,
                    "probe_summary": "All green",
                    "probe_results": [],
                }
            ]
        }
        http = {
            "turns": [
                {
                    "assistant": "Not a file: C:/Nova/updates.zip",
                    "planner_decision": "run_tool",
                    "route_summary": "input:received -> direction_analysis:general_chat -> truth_hierarchy:not_matched -> hard_answer:not_matched -> llm_call:started -> action_planner:run_tool -> tool_execution:ok -> finalize:run_tool",
                    "active_subject": "",
                    "continuation_used": False,
                    "probe_summary": "All green",
                    "probe_results": [],
                }
            ]
        }

        comparison = compare_sessions(cli, http)

        self.assertEqual(comparison.get("diffs"), [])

    def test_compare_sessions_tolerates_llm_fallback_question_wording(self):
        cli = {
            "turns": [
                {
                    "assistant": "Nice. We were in the middle of a conversation, right?",
                    "planner_decision": "llm_fallback",
                    "route_summary": "input:received -> finalize:llm_fallback",
                    "active_subject": "",
                    "continuation_used": False,
                    "probe_summary": "All green",
                    "probe_results": [],
                }
            ]
        }
        http = {
            "turns": [
                {
                    "assistant": "Nice. We were just chatting about something, right? What's on your mind now?",
                    "planner_decision": "llm_fallback",
                    "route_summary": "input:received -> finalize:llm_fallback",
                    "active_subject": "",
                    "continuation_used": False,
                    "probe_summary": "All green",
                    "probe_results": [],
                }
            ]
        }

        comparison = compare_sessions(cli, http)

        self.assertEqual(comparison.get("diffs"), [])

    def test_compare_sessions_surfaces_runtime_error_answers_even_without_drift(self):
        cli = {
            "mode": "cli",
            "turns": [
                {
                    "assistant": "(error: LLM service unavailable)",
                    "planner_decision": "llm_fallback",
                    "route_summary": "input:received -> llm_call:started -> finalize:llm_fallback",
                    "active_subject": "",
                    "continuation_used": False,
                    "probe_summary": "All green",
                    "probe_results": [],
                }
            ],
        }
        http = {
            "mode": "http",
            "turns": [
                {
                    "assistant": "(error: LLM service unavailable)",
                    "planner_decision": "llm_fallback",
                    "route_summary": "input:received -> llm_call:started -> finalize:llm_fallback",
                    "active_subject": "",
                    "continuation_used": False,
                    "probe_summary": "All green",
                    "probe_results": [],
                }
            ],
        }

        comparison = compare_sessions(cli, http)

        self.assertEqual(comparison.get("diffs"), [])
        self.assertEqual(comparison.get("runtime_failure_count"), 2)
        self.assertEqual((comparison.get("cli_runtime_failures") or [])[0]["failure_kind"], "llm_service_unavailable")
        self.assertEqual((comparison.get("http_runtime_failures") or [])[0]["failure_kind"], "llm_service_unavailable")
        self.assertTrue(_comparison_failed(comparison))

    def test_compare_sessions_surfaces_specific_ollama_chat_errors(self):
        cli = {
            "mode": "cli",
            "turns": [
                {
                    "assistant": "(error: Ollama chat API unavailable: /api/chat returned 404)",
                    "planner_decision": "llm_fallback",
                    "route_summary": "input:received -> llm_call:started -> finalize:llm_fallback",
                    "active_subject": "",
                    "continuation_used": False,
                    "probe_summary": "All green",
                    "probe_results": [],
                }
            ],
        }
        http = {
            "mode": "http",
            "turns": [
                {
                    "assistant": "(error: Ollama chat failed: connection refused)",
                    "planner_decision": "llm_fallback",
                    "route_summary": "input:received -> llm_call:started -> finalize:llm_fallback",
                    "active_subject": "",
                    "continuation_used": False,
                    "probe_summary": "All green",
                    "probe_results": [],
                }
            ],
        }

        comparison = compare_sessions(cli, http)

        self.assertEqual(comparison.get("runtime_failure_count"), 2)
        self.assertEqual((comparison.get("cli_runtime_failures") or [])[0]["failure_kind"], "llm_service_unavailable")
        self.assertEqual((comparison.get("http_runtime_failures") or [])[0]["failure_kind"], "llm_service_unavailable")
        self.assertTrue(_comparison_failed(comparison))

    def test_compare_sessions_tolerates_reported_fact_restatement(self):
        run_tools_result = {
            "mode": "run_tools",
            "turns": [
                {
                    "assistant": "Cobalt sparrow.",
                    "planner_decision": "session_fact_recall",
                    "route_summary": "input:received -> finalize:session_fact_recall",
                    "active_subject": "",
                    "continuation_used": False,
                    "probe_summary": "All green",
                    "probe_results": [],
                }
            ],
        }
        http_result = {
            "mode": "http",
            "turns": [
                {
                    "assistant": 'You asked me to remember the codeword "cobalt sparrow".',
                    "planner_decision": "session_fact_recall",
                    "route_summary": "input:received -> finalize:session_fact_recall",
                    "active_subject": "",
                    "continuation_used": False,
                    "probe_summary": "All green",
                    "probe_results": [],
                }
            ],
        }

        comparison = compare_sessions(run_tools_result, http_result)

        self.assertEqual(comparison.get("diffs"), [])

    def test_compare_sessions_surfaces_generic_mode_labels(self):
        run_tools_result = {
            "mode": "run_tools",
            "turns": [
                {
                    "assistant": "codeword confirmed",
                    "planner_decision": "session_memory",
                    "route_summary": "input:received -> finalize:session_memory",
                    "active_subject": "handoff",
                    "continuation_used": True,
                    "probe_summary": "All green",
                    "probe_results": [],
                }
            ],
        }
        http_result = {
            "mode": "http",
            "turns": [
                {
                    "assistant": "different answer",
                    "planner_decision": "session_memory",
                    "route_summary": "input:received -> finalize:session_memory",
                    "active_subject": "handoff",
                    "continuation_used": True,
                    "probe_summary": "All green",
                    "probe_results": [],
                }
            ],
        }

        comparison = compare_sessions(run_tools_result, http_result)

        self.assertEqual(comparison.get("left_label"), "Run Tools")
        self.assertEqual(comparison.get("right_label"), "HTTP")
        self.assertEqual((comparison.get("diffs") or [])[0]["issues"]["assistant"]["run_tools"], "codeword confirmed")
        self.assertEqual((comparison.get("diffs") or [])[0]["issues"]["assistant"]["http"], "different answer")
