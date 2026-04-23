import unittest

from services import supervisor_routing_rules


class TestSupervisorRoutingRules(unittest.TestCase):
    def test_extract_store_fact_payload_accepts_colon_form(self):
        payload = supervisor_routing_rules.extract_store_fact_payload(
            "Remember this: the deployment window is Friday night.",
            "remember this: the deployment window is friday night.",
        )

        self.assertEqual(payload.get("fact_text"), "the deployment window is Friday night")
        self.assertEqual(payload.get("memory_kind"), "user_fact")

    def test_set_location_rule_extracts_zip_payload(self):
        result = supervisor_routing_rules.set_location_rule(
            "My zip is 78504",
            "my zip is 78504",
            None,
            1,
            phase="intent",
        )

        self.assertTrue(result.get("handled"))
        self.assertEqual(result.get("intent"), "set_location")
        self.assertEqual(result.get("location_kind"), "zip")
        self.assertEqual(result.get("location_ack_kind"), "fact_only")

    def test_web_research_family_selects_stackexchange_for_debug_query(self):
        result = supervisor_routing_rules.web_research_family_rule(
            "research fastapi oauth error online",
            "research fastapi oauth error online",
            None,
            1,
            phase="intent",
        )

        self.assertTrue(result.get("handled"))
        self.assertEqual(result.get("tool_name"), "stackexchange_search")


if __name__ == "__main__":
    unittest.main()