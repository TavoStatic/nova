import tempfile
import unittest
from hashlib import sha1
from pathlib import Path
from unittest import mock

import nova_core
import nova_http
from scripts.run_test_session import compare_sessions
from scripts.run_test_session import _isolated_runner_state
from scripts.run_test_session import load_session
from scripts.run_test_session import run_cli_session
from scripts.run_test_session import run_http_session


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

    def test_generated_canary_has_no_cli_http_drift(self):
        session_meta = load_session(
            r"c:\Nova\runtime\test_sessions\generated_definitions\subconscious_fulfillment-fallthrough-family_clarified-second-turn.json"
        )

        orig_mem_recall = nova_core.mem_recall
        orig_kb_search = nova_core.kb_search
        orig_ollama_chat = nova_core.ollama_chat
        orig_sanitize_llm_reply = nova_core.sanitize_llm_reply

        try:
            nova_core.mem_recall = lambda _query: f"- memory-user:{nova_core._memory_runtime_user() or 'none'}"
            nova_core.kb_search = lambda _query: ""
            nova_core.sanitize_llm_reply = lambda text, tool_context="": text

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
            nova_core.sanitize_llm_reply = orig_sanitize_llm_reply

        self.assertTrue(comparison.get("turn_count_match"))
        self.assertEqual(comparison.get("diffs"), [])