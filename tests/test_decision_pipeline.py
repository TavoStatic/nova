import unittest

from services.decision_pipeline import StageRegistry
from services.decision_pipeline import run_registered_stages


class TestDecisionPipeline(unittest.TestCase):
    def test_registry_runs_in_priority_order_and_marks_skipped_stages(self):
        execution_order = []
        registry = StageRegistry()

        def first_stage(_context):
            execution_order.append("first")
            return {"handled": False, "result": "pass"}

        def second_stage(_context):
            execution_order.append("second")
            return {
                "handled": True,
                "reply": "done",
                "meta": {"planner_decision": "deterministic"},
                "result": "handled",
                "detail": "won",
                "data": {"tool": "sample_tool", "grounded": True},
            }

        def third_stage(_context):
            execution_order.append("third")
            return {"handled": True, "reply": "should not run", "meta": {}}

        registry.register("third_stage", priority=30, handler=third_stage)
        registry.register("first_stage", priority=10, handler=first_stage)
        registry.register("second_stage", priority=20, handler=second_stage)

        outcome = run_registered_stages(registry)

        self.assertEqual(execution_order, ["first", "second"])
        self.assertEqual(outcome.get("reply"), "done")
        self.assertEqual(outcome.get("decision_stage"), "second_stage")
        trace = outcome.get("decision_trace") or []
        self.assertEqual([entry.get("stage") for entry in trace], ["first_stage", "second_stage", "third_stage"])
        self.assertEqual(trace[0].get("result"), "pass")
        self.assertEqual(trace[1].get("result"), "handled")
        self.assertEqual(trace[1].get("detail"), "won")
        self.assertEqual((trace[1].get("data") or {}).get("tool"), "sample_tool")
        self.assertEqual(trace[2].get("result"), "skipped")
        self.assertEqual((trace[2].get("data") or {}).get("handled_by"), "second_stage")


if __name__ == "__main__":
    unittest.main()