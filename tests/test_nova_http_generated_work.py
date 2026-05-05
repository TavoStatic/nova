import unittest

from services.nova_http_generated_work import HTTP_GENERATED_WORK_SERVICE
from services.test_session_control import TEST_SESSION_CONTROL_SERVICE


class TestNovaHttpGeneratedWorkService(unittest.TestCase):
    def test_generated_pack_action_hook_binds_runtime_functions(self):
        definitions = [
            {"file": "low.json", "name": "Low", "origin": "generated", "training_priorities": [{"urgency": "low", "robustness": 0.2}]},
            {"file": "high.json", "name": "High", "origin": "generated", "training_priorities": [{"urgency": "high", "robustness": 0.9}]},
        ]
        reports = [{"run_id": "latest", "status": "green"}]
        executed = []
        scope = {
            "TEST_SESSION_CONTROL_SERVICE": TEST_SESSION_CONTROL_SERVICE,
            "_available_test_session_definitions": lambda _limit: definitions,
            "_run_test_session_definition": lambda session_file: executed.append(session_file) or (True, f"ok:{session_file}", {"latest_report": {"run_id": session_file}}),
            "_test_session_report_summaries": lambda _limit: reports,
            "_generated_work_queue": lambda _limit: {"items": [], "next_item": {}},
        }

        ok, msg, extra, detail = HTTP_GENERATED_WORK_SERVICE.action_hooks_from_runtime(scope)["generated_pack_run_action_fn"](
            {"limit": 1, "mode": "priority"}
        )

        self.assertTrue(ok)
        self.assertEqual(msg, "generated_test_sessions_run_priority_completed:1")
        self.assertEqual(detail, msg)
        self.assertEqual(executed, ["high.json"])
        self.assertEqual((extra.get("latest_report") or {}).get("run_id"), "latest")

    def test_generated_queue_run_next_hook_uses_runtime_queue_and_runner(self):
        queues = [
            {"open_count": 1, "next_item": {"file": "demo.json"}, "items": [{"file": "demo.json", "open": True}]},
            {"open_count": 0, "next_item": {}, "items": []},
        ]
        scope = {
            "TEST_SESSION_CONTROL_SERVICE": TEST_SESSION_CONTROL_SERVICE,
            "_generated_work_queue": lambda _limit: queues.pop(0),
            "_run_test_session_definition": lambda session_file: (True, f"ok:{session_file}", {"latest_report": {"run_id": session_file}}),
        }

        ok, msg, extra, detail = HTTP_GENERATED_WORK_SERVICE.action_hooks_from_runtime(scope)["generated_queue_run_next_action_fn"]({})

        self.assertTrue(ok)
        self.assertEqual(msg, "generated_work_queue_next_ok:demo.json")
        self.assertEqual(detail, msg)
        self.assertEqual((extra.get("selected") or {}).get("file"), "demo.json")
        self.assertEqual((extra.get("work_queue") or {}).get("open_count"), 0)

    def test_generated_queue_investigate_hook_binds_operator_dependencies(self):
        captured = {}
        queue = {
            "next_item": {"file": "demo.json", "latest_status": "drift", "open": True},
            "items": [],
        }
        scope = {
            "TEST_SESSION_CONTROL_SERVICE": TEST_SESSION_CONTROL_SERVICE,
            "_generated_work_queue": lambda _limit: queue,
            "_resolve_operator_macro": lambda _macro_id: {"macro_id": "subconscious-review", "prompt": "Review."},
            "_render_operator_macro_prompt": lambda macro, values, note="": (True, note or str(values), {}),
            "_normalize_user_id": lambda value: str(value or "").strip().lower(),
            "_assert_session_owner": lambda sid, uid, allow_bind=False: captured.update({"sid": sid, "uid": uid, "allow_bind": allow_bind}) or (True, "owner_bound"),
            "process_chat": lambda session_id, message, user_id="": captured.update({"session_id": session_id, "message": message, "user_id": user_id}) or "Investigated.",
            "_session_summaries": lambda _limit: [],
        }

        ok, msg, extra, detail = HTTP_GENERATED_WORK_SERVICE.action_hooks_from_runtime(scope)["generated_queue_investigate_action_fn"]({})

        self.assertTrue(ok)
        self.assertEqual(msg, "generated_work_queue_investigation_started")
        self.assertEqual(detail, msg)
        self.assertTrue(captured["allow_bind"])
        self.assertEqual(captured["session_id"], "operator-generated-queue")
        self.assertIn("demo.json", captured["message"])
        self.assertEqual(extra.get("reply"), "Investigated.")


if __name__ == "__main__":
    unittest.main()
