import unittest

from services import supervisor_runtime
from supervisor import Supervisor


class TestSupervisorRuntime(unittest.TestCase):
    def test_register_rule_replaces_existing_name_and_sorts(self):
        def alpha(*_args, **_kwargs):
            return {"handled": False}

        def beta(*_args, **_kwargs):
            return {"handled": False}

        rules = supervisor_runtime.register_rule([], "beta", beta, priority=20)
        rules = supervisor_runtime.register_rule(rules, "alpha", alpha, priority=10)
        rules = supervisor_runtime.register_rule(rules, "beta", alpha, priority=5)

        self.assertEqual([item["name"] for item in rules], ["beta", "alpha"])
        self.assertIs(rules[0]["rule"], alpha)

    def test_supervisor_does_not_claim_legacy_identity_intent_patterns(self):
        turn_supervisor = Supervisor()

        result = turn_supervisor.evaluate_rules(
            "Tell me about your developer",
            phase="intent",
        )

        self.assertFalse(result.get("handled"))

    def test_result_is_explicitly_owned_respects_phase_gate(self):
        self.assertTrue(
            supervisor_runtime.result_is_explicitly_owned(
                "weather_lookup",
                {"handled": True},
                phase="intent",
            )
        )

    def test_compatibility_wrapper_exposes_shared_intent_rules(self):
        self.assertNotIn("developer_profile", supervisor_runtime.EXPLICIT_INTENT_OWNERSHIP_RULES)
        self.assertNotIn("session_summary", supervisor_runtime.EXPLICIT_INTENT_OWNERSHIP_RULES)
        self.assertFalse(
            supervisor_runtime.result_is_explicitly_owned(
                "smalltalk",
                {"handled": True},
                phase="intent",
            )
        )


if __name__ == "__main__":
    unittest.main()