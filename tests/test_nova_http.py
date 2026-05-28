import unittest
from unittest import mock

import nova_http


class TestNovaHttpProfile(unittest.TestCase):
    def setUp(self):
        nova_http.SESSION_TURNS.clear()
        nova_http.SESSION_STATE_MANAGER.clear()

    def test_generate_chat_reply_routes_semantic_web_fetch(self):
        with mock.patch.object(
            nova_http.nova_core,
            "_llm_classify_routing_intent",
            return_value={
                "tool": "web_fetch",
                "args": ["http://127.0.0.1:8080/control"],
                "confidence": 0.93,
                "reason": "inspect requested URL",
            },
        ), mock.patch.object(nova_http.nova_core, "tool_web_fetch", return_value="FETCHED"):
            reply, meta = nova_http._generate_chat_reply(
                [("user", "can you access http://127.0.0.1:8080/control")],
                "can you access http://127.0.0.1:8080/control",
            )

        self.assertEqual(reply, "FETCHED")
        self.assertEqual(meta.get("planner_decision"), "run_tool")
        self.assertEqual(meta.get("tool"), "web_fetch")

    def test_generate_chat_reply_semantic_none_uses_model_fallback(self):
        with mock.patch.object(
            nova_http.nova_core,
            "_llm_classify_routing_intent",
            return_value={"tool": "none", "args": [], "confidence": 0.91, "reason": "conversation"},
        ), mock.patch.object(nova_http.nova_core, "build_fallback_context_details", return_value={}), mock.patch.object(
            nova_http.nova_core,
            "ollama_chat",
            return_value="MODEL_REPLY",
        ):
            reply, meta = nova_http._generate_chat_reply([("user", "hi nova")], "hi nova")

        self.assertEqual(reply, "MODEL_REPLY")
        self.assertEqual(meta.get("planner_decision"), "llm_fallback")
        self.assertEqual(meta.get("tool"), "")

    def test_process_chat_appends_user_and_assistant_turns(self):
        with mock.patch.object(
            nova_http.nova_core,
            "_llm_classify_routing_intent",
            return_value={"tool": "none", "args": [], "confidence": 0.91, "reason": "conversation"},
        ), mock.patch.object(nova_http.nova_core, "build_fallback_context_details", return_value={}), mock.patch.object(
            nova_http.nova_core,
            "ollama_chat",
            return_value="MODEL_REPLY",
        ):
            reply = nova_http.process_chat("session-1", "hi nova")

        self.assertEqual(reply, "MODEL_REPLY")
        self.assertEqual(nova_http.SESSION_TURNS["session-1"], [("user", "hi nova"), ("assistant", "MODEL_REPLY")])

    def test_cached_control_status_payload_reuses_recent_value(self):
        nova_http._CONTROL_STATUS_CACHE.clear()
        calls = []

        with mock.patch.object(
            nova_http,
            "_control_status_payload",
            side_effect=lambda: calls.append("called") or {"health_score": 100},
        ):
            first = nova_http._cached_control_status_payload()
            second = nova_http._cached_control_status_payload()

        self.assertEqual(first, {"health_score": 100})
        self.assertEqual(second, {"health_score": 100})
        self.assertEqual(calls, ["called"])

    def test_probe_searxng_status_path_is_bounded_and_non_mutating(self):
        self.assertGreaterEqual(nova_http.SEARXNG_STATUS_TIMEOUT_SEC, 5.0)
        with mock.patch.object(
            nova_http.nova_core,
            "probe_search_endpoint",
            return_value={"ok": False, "note": "endpoint_unreachable"},
        ) as probe:
            ok, note = nova_http._probe_searxng("http://127.0.0.1:8081/search")

        self.assertFalse(ok)
        self.assertEqual(note, "endpoint_unreachable")
        probe.assert_called_once_with(
            "http://127.0.0.1:8081/search",
            timeout=nova_http.SEARXNG_STATUS_TIMEOUT_SEC,
            persist_repair=False,
            candidate_limit=nova_http.SEARXNG_STATUS_CANDIDATE_LIMIT,
        )

    def test_status_runtime_processes_cache_reuses_recent_scan(self):
        nova_http._PROCESS_SCAN_CACHE.clear()
        calls = []

        with mock.patch.object(
            nova_http.runtime_processes,
            "logical_service_processes",
            side_effect=lambda script: calls.append(str(script)) or [{"pid": 10}],
        ), mock.patch.object(nova_http.time, "monotonic", side_effect=[10.0, 11.0]):
            first = nova_http._status_runtime_processes_module().logical_service_processes(nova_http.AUTONOMY_MAINTENANCE_PY)
            second = nova_http._status_runtime_processes_module().logical_service_processes(nova_http.AUTONOMY_MAINTENANCE_PY)

        self.assertEqual(first, [{"pid": 10}])
        self.assertEqual(second, [{"pid": 10}])
        self.assertEqual(len(calls), 1)

    def test_storage_watch_summary_reuses_recent_snapshot_with_age(self):
        nova_http._STORAGE_WATCH_CACHE.clear()
        calls = []

        with mock.patch.object(nova_http.nova_core, "load_policy", return_value={"kidney": {}}), \
            mock.patch.object(
                nova_http.STORAGE_WATCH_SERVICE,
                "snapshot",
                side_effect=lambda **_kwargs: calls.append("scan") or {"status": "ok", "runtime_total_bytes": 123},
            ), mock.patch.object(nova_http.time, "monotonic", side_effect=[20.0, 24.0]):
            first = nova_http._storage_watch_summary()
            second = nova_http._storage_watch_summary()

        self.assertEqual(len(calls), 1)
        self.assertFalse(first.get("snapshot_cached"))
        self.assertTrue(second.get("snapshot_cached"))
        self.assertEqual(second.get("snapshot_age_sec"), 4.0)


if __name__ == "__main__":
    unittest.main()
