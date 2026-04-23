import unittest

from services import nova_truth_hierarchy


class TestNovaTruthHierarchy(unittest.TestCase):
    def test_assistant_name_query_tolerates_yor_typo(self):
        self.assertTrue(nova_truth_hierarchy.is_assistant_name_query("what is yor name"))

    def test_developer_full_name_reply_expands_default_name(self):
        reply = nova_truth_hierarchy.developer_full_name_reply(
            get_learned_fact_fn=lambda key, default: {
                "developer_name": "Gustavo",
                "developer_nickname": "Gus",
            }.get(key, default),
        )
        self.assertEqual(reply, "My developer's full name is Gustavo Uribe. Gus is his nickname.")

    def test_action_history_reply_formats_latest_record(self):
        reply = nova_truth_hierarchy.action_history_reply(
            latest_action_ledger_record_fn=lambda: {
                "tool": "web_research",
                "planner_decision": "run_tool",
                "intent": "research",
                "grounded": True,
                "final_answer": "A" * 300,
            },
            action_ledger_route_summary_fn=lambda record: "planner -> tool",
        )
        self.assertIn("intent=research", reply)
        self.assertIn("tool=web_research", reply)
        self.assertIn("route=planner -> tool", reply)
        self.assertIn("...", reply)

    def test_truth_hierarchy_answer_returns_policy_summary(self):
        handled, answer, source, grounded = nova_truth_hierarchy.truth_hierarchy_answer(
            "what domain access do you have?",
            is_action_history_query_fn=lambda text: False,
            action_history_reply_fn=lambda: "",
            is_identity_or_developer_query_fn=lambda text: False,
            hard_answer_fn=lambda text: "",
            get_name_origin_story_fn=lambda: "",
            is_capability_query_fn=lambda text: False,
            describe_capabilities_fn=lambda: "",
            is_policy_domain_query_fn=lambda text: True,
            policy_web_fn=lambda: {"enabled": True, "allow_domains": ["weather.gov", "noaa.gov"]},
        )
        self.assertTrue(handled)
        self.assertEqual(source, "policy_json")
        self.assertTrue(grounded)
        self.assertIn("weather.gov", answer)


if __name__ == "__main__":
    unittest.main()