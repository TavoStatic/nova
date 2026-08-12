from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.base_tool import ToolContext, ToolInvocationError
from tools.temporal_review_tool import TemporalReviewTool, _load_input_payload, _pressure_from_input


def _ctx(policy: dict | None = None, *, is_admin: bool = False) -> ToolContext:
    return ToolContext(
        user_id="test",
        session_id="s0",
        policy=policy if policy is not None else {"tools_enabled": {"temporal_review": True}},
        is_admin=is_admin,
    )


def _enabled_policy() -> dict:
    return {"tools_enabled": {"temporal_review": True}}


def _disabled_policy() -> dict:
    return {"tools_enabled": {"temporal_review": False}}


class TestCheckPolicy(unittest.TestCase):
    def setUp(self):
        self.tool = TemporalReviewTool()

    def test_policy_enabled_allows(self):
        ok, reason = self.tool.check_policy({}, _ctx(_enabled_policy()))
        self.assertTrue(ok)
        self.assertEqual(reason, "")

    def test_policy_disabled_blocks(self):
        ok, reason = self.tool.check_policy({}, _ctx(_disabled_policy()))
        self.assertFalse(ok)
        self.assertEqual(reason, "temporal_review_tool_disabled")

    def test_policy_key_absent_allows(self):
        # tools_enabled present but no temporal_review key → should allow
        ok, reason = self.tool.check_policy({}, _ctx({"tools_enabled": {}}))
        self.assertTrue(ok)
        self.assertEqual(reason, "")

    def test_policy_tools_enabled_missing_allows(self):
        # no tools_enabled block at all → should allow (fail-open for tool policy)
        ok, reason = self.tool.check_policy({}, _ctx({}))
        self.assertTrue(ok)
        self.assertEqual(reason, "")

    def test_admin_not_required(self):
        # tool has requires_admin=False; non-admin context should pass base check
        ok, reason = self.tool.check_policy({}, _ctx(_enabled_policy(), is_admin=False))
        self.assertTrue(ok)


class TestRunEmptyInput(unittest.TestCase):
    def setUp(self):
        self.tool = TemporalReviewTool()
        self.ctx = _ctx()

    def test_empty_args_returns_no_temporal_input(self):
        result = json.loads(self.tool.run({}, self.ctx))
        self.assertEqual(result["status"], "no_temporal_input")
        self.assertEqual(result["tool"], "temporal_review")

    def test_payload_empty_string_returns_no_temporal_input(self):
        result = json.loads(self.tool.run({"payload": ""}, self.ctx))
        self.assertEqual(result["status"], "no_temporal_input")

    def test_event_none_returns_no_temporal_input(self):
        result = json.loads(self.tool.run({"event": None}, self.ctx))
        self.assertEqual(result["status"], "no_temporal_input")


class TestRunUnknownAction(unittest.TestCase):
    def setUp(self):
        self.tool = TemporalReviewTool()
        self.ctx = _ctx()

    def test_unknown_action_raises(self):
        with self.assertRaises(ToolInvocationError):
            self.tool.run({"action": "explode", "payload": {"title": "x"}}, self.ctx)

    def test_review_action_is_default_and_valid(self):
        result = json.loads(self.tool.run({"payload": {"title": "test event"}}, self.ctx))
        self.assertEqual(result["status"], "ok")

    def test_assess_action_is_valid(self):
        result = json.loads(self.tool.run({"action": "assess", "payload": {"title": "test event"}}, self.ctx))
        self.assertEqual(result["status"], "ok")

    def test_route_action_is_valid(self):
        result = json.loads(self.tool.run({"action": "route", "payload": {"title": "test event"}}, self.ctx))
        self.assertEqual(result["status"], "ok")


class TestRunSingleEvent(unittest.TestCase):
    def setUp(self):
        self.tool = TemporalReviewTool()
        self.ctx = _ctx()

    def test_event_dict_returns_ok_with_pressure_and_decision(self):
        result = json.loads(self.tool.run(
            {"payload": {"title": "state education data deadline", "importance": 0.9}},
            self.ctx,
        ))
        self.assertEqual(result["status"], "ok")
        self.assertIn("pressure", result)
        self.assertIn("decision", result)

    def test_pressure_has_final_score(self):
        result = json.loads(self.tool.run(
            {"event": {"title": "deadline", "importance": 1.0}},
            self.ctx,
        ))
        self.assertIn("final_score", result["pressure"])
        self.assertIsInstance(result["pressure"]["final_score"], (int, float))

    def test_decision_has_kind(self):
        result = json.loads(self.tool.run(
            {"payload": {"title": "x", "importance": 1.0}},
            self.ctx,
        ))
        self.assertIn("kind", result["decision"])

    def test_context_extra_forwarded(self):
        ctx = ToolContext(
            user_id="gus",
            session_id="s1",
            policy=_enabled_policy(),
            extra={"source": "leah"},
        )
        result = json.loads(self.tool.run(
            {"payload": {"title": "x"}},
            ctx,
        ))
        self.assertEqual(result.get("context", {}).get("source"), "leah")

    def test_json_string_payload_is_parsed(self):
        payload_str = json.dumps({"title": "json string event", "importance": 0.5})
        result = json.loads(self.tool.run({"payload": payload_str}, self.ctx))
        self.assertEqual(result["status"], "ok")


class TestRunBatchInput(unittest.TestCase):
    def setUp(self):
        self.tool = TemporalReviewTool()
        self.ctx = _ctx()

    def test_list_of_two_events_returns_results_array(self):
        payload = [
            {"title": "Event A", "importance": 0.9},
            {"title": "Event B", "importance": 0.2},
        ]
        result = json.loads(self.tool.run({"payload": payload}, self.ctx))
        self.assertEqual(result["status"], "ok")
        self.assertIn("results", result)
        self.assertEqual(len(result["results"]), 2)

    def test_each_batch_result_has_pressure(self):
        payload = [{"title": f"ev{i}"} for i in range(3)]
        result = json.loads(self.tool.run({"payload": payload}, self.ctx))
        for item in result["results"]:
            self.assertIn("pressure", item)

    def test_empty_list_returns_no_temporal_input(self):
        result = json.loads(self.tool.run({"payload": []}, self.ctx))
        self.assertEqual(result["status"], "no_temporal_input")


class TestRunFileInput(unittest.TestCase):
    def setUp(self):
        self.tool = TemporalReviewTool()
        self.ctx = _ctx()

    def test_json_file_path_is_loaded(self):
        payload = {"title": "from file", "importance": 0.7}
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False, encoding="utf-8") as f:
            json.dump(payload, f)
            tmp_path = f.name
        try:
            result = json.loads(self.tool.run({"path": tmp_path}, self.ctx))
            self.assertEqual(result["status"], "ok")
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_ics_file_path_is_loaded(self):
        ics_text = (
            "BEGIN:VCALENDAR\r\n"
            "VERSION:2.0\r\n"
            "BEGIN:VEVENT\r\n"
            "SUMMARY:ICS File Event\r\n"
            "DTSTART:20260615T090000Z\r\n"
            "DTEND:20260615T100000Z\r\n"
            "END:VEVENT\r\n"
            "END:VCALENDAR\r\n"
        )
        with tempfile.NamedTemporaryFile(suffix=".ics", mode="w", delete=False, encoding="utf-8") as f:
            f.write(ics_text)
            tmp_path = f.name
        try:
            result = json.loads(self.tool.run({"path": tmp_path}, self.ctx))
            self.assertEqual(result["status"], "ok")
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_missing_path_raises(self):
        with self.assertRaises(ToolInvocationError):
            self.tool.run({"path": "/no/such/file.json"}, self.ctx)


class TestPolicyDisabledPath(unittest.TestCase):
    """Integration: run() should not be reachable when check_policy blocks."""

    def setUp(self):
        self.tool = TemporalReviewTool()

    def test_disabled_policy_check_policy_returns_false(self):
        ok, reason = self.tool.check_policy({}, _ctx(_disabled_policy()))
        self.assertFalse(ok)
        self.assertEqual(reason, "temporal_review_tool_disabled")

    def test_callers_honour_check_policy_before_run(self):
        # Simulate what nova_core does: gate run() on check_policy result
        ctx = _ctx(_disabled_policy())
        ok, reason = self.tool.check_policy({"payload": {"title": "x"}}, ctx)
        self.assertFalse(ok, "check_policy must block when temporal_review is disabled")
        # run() must never be called; calling it directly still works (tool is stateless)
        # — this test asserts the policy gate result, not that run() crashes


if __name__ == "__main__":
    unittest.main()
