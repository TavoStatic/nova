import unittest

from services.autonomy_execution_gate import AUTONOMY_EXECUTION_GATE_SERVICE
from services.autonomy_orchestrator import SPEC_DECISION_DEFER, SPEC_DECISION_RECOMMEND_ACTION


def _decision(action_type="generated_queue_run_next", *, confidence=0.72, decision_type=SPEC_DECISION_RECOMMEND_ACTION):
    return {
        "cycle_id": "cycle-test",
        "decision_type": decision_type,
        "recommended_action": {
            "action_type": action_type,
            "target_kind": "queue",
            "target_id": "generated_work_queue",
            "reason_code": "queue_pressure_actionable",
            "requires_ack": False,
            "cooldown_sec": 180,
        },
        "confidence": confidence,
        "refusal_reasons": [],
    }


def _policy(**overrides):
    payload = {
        "enabled": True,
        "mode": "canary",
        "execute_enabled": True,
        "execute_allowed_actions": ["generated_queue_run_next"],
        "execute_blocked_actions": [],
        "requires_operator_ack_for": [],
        "execute_min_confidence": 0.55,
    }
    payload.update(overrides)
    return payload


class TestAutonomyExecutionGateService(unittest.TestCase):
    def test_allows_canary_dispatch_for_policy_enabled_recommendation(self):
        result = AUTONOMY_EXECUTION_GATE_SERVICE.evaluate(_decision(), _policy())

        self.assertTrue(result["allow_execute"])
        self.assertEqual(result["status"], "allowed")
        self.assertEqual(result["action_type"], "generated_queue_run_next")
        self.assertEqual(result["dispatch_payload"]["action"], "generated_queue_run_next")

    def test_blocks_when_action_not_execute_allowed(self):
        result = AUTONOMY_EXECUTION_GATE_SERVICE.evaluate(
            _decision("pulse_status"),
            _policy(execute_allowed_actions=["generated_queue_run_next"]),
        )

        self.assertFalse(result["allow_execute"])
        self.assertEqual(result["status"], "blocked")
        self.assertIn("action_not_execute_allowed", result["refusal_reasons"])

    def test_defers_when_decision_is_not_recommend_action(self):
        result = AUTONOMY_EXECUTION_GATE_SERVICE.evaluate(
            _decision(decision_type=SPEC_DECISION_DEFER),
            _policy(),
        )

        self.assertFalse(result["allow_execute"])
        self.assertEqual(result["status"], "deferred")
        self.assertIn("decision_not_recommend_action", result["refusal_reasons"])

    def test_defers_when_cooldown_is_active(self):
        result = AUTONOMY_EXECUTION_GATE_SERVICE.evaluate(
            _decision(),
            _policy(),
            last_execution_context={
                "last_action_type": "generated_queue_run_next",
                "last_target_id": "generated_work_queue",
                "cooldown_active": True,
            },
        )

        self.assertFalse(result["allow_execute"])
        self.assertEqual(result["status"], "deferred")
        self.assertIn("cooldown_active", result["refusal_reasons"])


if __name__ == "__main__":
    unittest.main()
