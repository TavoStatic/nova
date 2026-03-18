import json
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import nova_core
import nova_http


class TestCoreMemoryService(unittest.TestCase):
    def setUp(self):
        self.orig_memory_mod = nova_core.memory_mod
        self.orig_active_user = nova_core.get_active_user()
        self.orig_memory_events_log = nova_core.MEMORY_EVENTS_LOG
        self.temp_dir = tempfile.TemporaryDirectory()
        nova_core.MEMORY_EVENTS_LOG = Path(self.temp_dir.name) / "memory_events.jsonl"

    def tearDown(self):
        nova_core.memory_mod = self.orig_memory_mod
        nova_core.set_active_user(self.orig_active_user)
        nova_core.MEMORY_EVENTS_LOG = self.orig_memory_events_log
        self.temp_dir.cleanup()

    def test_mem_recall_uses_in_process_memory_module(self):
        fake_module = types.SimpleNamespace(
            recall=lambda query, top_k, min_score, exclude_sources, user, scope: [
                (0.91, 1, "fact", "typed", user or "", "integration memory alpha bravo")
            ]
        )
        nova_core.memory_mod = fake_module
        nova_core.set_active_user("tester")

        with patch("nova_core.mem_enabled", return_value=True), \
             patch("nova_core.mem_scope", return_value="private"), \
             patch("nova_core.mem_context_top_k", return_value=3), \
             patch("nova_core.mem_min_score", return_value=0.25), \
             patch("nova_core.mem_exclude_sources", return_value=[]), \
             patch("nova_core.subprocess.run", side_effect=AssertionError("subprocess should not be used")):
            out = nova_core.mem_recall("integration memory alpha")

        self.assertIn("integration memory alpha bravo", out)
        entries = [json.loads(line) for line in nova_core.MEMORY_EVENTS_LOG.read_text(encoding="utf-8").splitlines() if line.strip()]
        self.assertEqual(entries[-1]["action"], "recall")
        self.assertEqual(entries[-1]["status"], "ok")
        self.assertEqual(entries[-1]["backend"], "in_process")
        self.assertEqual(entries[-1]["result_count"], 1)

    def test_mem_add_uses_in_process_duplicate_check_and_add(self):
        calls = []

        def fake_recall_explain(query, top_k, min_score, user, scope):
            return {"results": []}

        def fake_add_memory(kind, source, text, user, scope):
            calls.append((kind, source, text, user, scope))

        fake_module = types.SimpleNamespace(
            recall_explain=fake_recall_explain,
            add_memory=fake_add_memory,
        )
        nova_core.memory_mod = fake_module
        nova_core.set_active_user("tester")

        with patch("nova_core.mem_enabled", return_value=True), \
             patch("nova_core.mem_scope", return_value="private"), \
             patch("nova_core.mem_min_score", return_value=0.25), \
             patch("nova_core.subprocess.run", side_effect=AssertionError("subprocess should not be used")):
            nova_core.mem_add("fact", "typed", "remember this durable integration fact alpha bravo")

        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], "fact")
        self.assertEqual(calls[0][3], "tester")
        self.assertEqual(calls[0][4], "private")
        entries = [json.loads(line) for line in nova_core.MEMORY_EVENTS_LOG.read_text(encoding="utf-8").splitlines() if line.strip()]
        self.assertEqual(entries[-1]["action"], "add")
        self.assertEqual(entries[-1]["status"], "ok")
        self.assertEqual(entries[-1]["backend"], "in_process")

    def test_mem_add_duplicate_skip_is_logged(self):
        fake_module = types.SimpleNamespace(
            recall_explain=lambda query, top_k, min_score, user, scope: {
                "results": [{"score": 0.93, "preview": query}]
            },
            add_memory=lambda kind, source, text, user, scope: self.fail("duplicate memory should not be added"),
        )
        nova_core.memory_mod = fake_module
        nova_core.set_active_user("tester")

        with patch("nova_core.mem_enabled", return_value=True), \
             patch("nova_core.mem_scope", return_value="private"), \
             patch("nova_core.mem_min_score", return_value=0.25):
            nova_core.mem_add("fact", "typed", "remember this durable duplicate integration fact alpha bravo")

        entries = [json.loads(line) for line in nova_core.MEMORY_EVENTS_LOG.read_text(encoding="utf-8").splitlines() if line.strip()]
        self.assertEqual(entries[-1]["action"], "add")
        self.assertEqual(entries[-1]["status"], "skipped")
        self.assertEqual(entries[-1]["reason"], "duplicate")

    def test_mem_audit_and_stats_payload_use_in_process_memory_module(self):
        fake_module = types.SimpleNamespace(
            recall_explain=lambda query, top_k, min_score, exclude_sources, user, scope: {
                "query": query,
                "scope": scope,
                "results": [{"score": 0.9, "preview": "memory audit hit"}],
            },
            stats=lambda scope, user: {
                "total": 3,
                "scope": scope,
                "by_kind": {"fact": 3},
                "by_source": {"typed": 3},
                "by_user": {user or "shared": 3},
                "oldest_ts": 1,
                "newest_ts": 2,
            },
        )
        nova_core.memory_mod = fake_module
        nova_core.set_active_user("tester")

        with patch("nova_core.mem_enabled", return_value=True), \
             patch("nova_core.mem_scope", return_value="private"), \
             patch("nova_core.mem_context_top_k", return_value=3), \
             patch("nova_core.mem_min_score", return_value=0.25), \
             patch("nova_core.mem_exclude_sources", return_value=[]), \
             patch("nova_core.subprocess.run", side_effect=AssertionError("subprocess should not be used")):
            audit_out = nova_core.mem_audit("memory audit")
            stats_payload = nova_core.mem_stats_payload()
            stats_text = nova_core.mem_stats()

        audit_json = json.loads(audit_out)
        stats_json = json.loads(stats_text)
        self.assertEqual(audit_json["results"][0]["preview"], "memory audit hit")
        self.assertTrue(stats_payload["ok"])
        self.assertEqual(stats_payload["total"], 3)
        self.assertEqual(stats_json["total"], 3)
        entries = [json.loads(line) for line in nova_core.MEMORY_EVENTS_LOG.read_text(encoding="utf-8").splitlines() if line.strip()]
        self.assertEqual(entries[-3]["action"], "audit")
        self.assertEqual(entries[-2]["action"], "stats")
        self.assertEqual(entries[-1]["action"], "stats")

    def test_memory_event_summary_reports_recent_activity(self):
        fake_module = types.SimpleNamespace(
            recall=lambda query, top_k, min_score, exclude_sources, user, scope: [
                (0.91, 1, "fact", "typed", user or "", "integration memory alpha bravo")
            ],
            recall_explain=lambda query, top_k, min_score, user, scope: {
                "results": [{"score": 0.93, "preview": query}]
            },
        )
        nova_core.memory_mod = fake_module
        nova_core.set_active_user("tester")

        with patch("nova_core.mem_enabled", return_value=True), \
             patch("nova_core.mem_scope", return_value="private"), \
             patch("nova_core.mem_context_top_k", return_value=3), \
             patch("nova_core.mem_min_score", return_value=0.25), \
             patch("nova_core.mem_exclude_sources", return_value=[]):
            nova_core.mem_recall("integration memory alpha")
            nova_core.mem_add("fact", "typed", "remember this durable duplicate integration fact alpha bravo")

        with patch("nova_http.MEMORY_EVENTS_LOG", nova_core.MEMORY_EVENTS_LOG):
            summary = nova_http._memory_events_summary(20)

        self.assertTrue(summary["ok"])
        self.assertEqual(summary["count"], 2)
        self.assertEqual(summary["recall_count"], 1)
        self.assertEqual(summary["skipped_count"], 1)
        self.assertEqual(summary["last_event"]["action"], "add")
        self.assertEqual(summary["last_event"]["status"], "skipped")


if __name__ == "__main__":
    unittest.main()
