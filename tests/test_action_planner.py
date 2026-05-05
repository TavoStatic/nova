import unittest
from action_planner import ActionPlanner, decide_actions


class TestActionPlanner(unittest.TestCase):
    def test_web_url_plans_web_fetch(self):
        text = "please fetch https://example.com/index.html for me"
        actions = decide_actions(text)
        self.assertTrue(len(actions) >= 1)
        a = actions[0]
        self.assertEqual(a.get("type"), "run_tool")
        self.assertEqual(a.get("tool"), "web_fetch")
        self.assertTrue(a.get("args") and a.get("args")[0].startswith("https://"))

    def test_scan_request_returns_clarify(self):
        text = "scan my machine for open ports"
        actions = decide_actions(text)
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["type"], "ask_clarify")

    def test_patch_apply_detection(self):
        text = "please patch apply updates.zip"
        actions = decide_actions(text)
        self.assertEqual(actions[0]["type"], "run_tool")
        self.assertIn(actions[0]["tool"], ("patch_apply",))

    def test_web_search_intent(self):
        text = "web search peims attendance rules"
        actions = decide_actions(text)
        self.assertEqual(actions[0]["type"], "run_tool")
        self.assertEqual(actions[0]["tool"], "web_search")

    def test_bare_search_prefix_is_not_a_web_trigger(self):
        actions = decide_actions("search peims attendance rules")
        self.assertEqual(actions, [])

    def test_find_more_information_is_not_local_find_trigger(self):
        actions = decide_actions("find more information")
        self.assertEqual(actions, [])

    def test_ambiguous_web_prefix_is_not_a_keyword_route(self):
        actions = decide_actions("web peims attendance rules")
        self.assertEqual(actions, [])

    def test_web_gather_intent(self):
        text = "please gather and summarize https://tea.texas.gov/reports"
        actions = decide_actions(text)
        self.assertEqual(actions[0]["type"], "run_tool")
        self.assertEqual(actions[0]["tool"], "web_gather")

    def test_web_research_intent(self):
        text = "web research peims attendance rules"
        actions = decide_actions(text)
        self.assertEqual(actions[0]["type"], "run_tool")
        self.assertEqual(actions[0]["tool"], "web_research")

    def test_all_information_request_does_not_force_web_research(self):
        actions = decide_actions("get me all the information you can about peims")
        self.assertEqual(actions, [])

    def test_bare_research_request_does_not_force_web_research(self):
        actions = decide_actions("do research on peims attendance")
        self.assertEqual(actions, [])

    def test_deep_research_request_without_web_does_not_force_web_research(self):
        actions = decide_actions("do a deep research pass on peims attendance")
        self.assertEqual(actions, [])

    def test_wikipedia_command_routes_to_provider(self):
        actions = decide_actions("wikipedia Ada Lovelace")
        self.assertEqual(actions[0]["type"], "run_tool")
        self.assertEqual(actions[0]["tool"], "wikipedia_lookup")

    def test_factual_prompt_prefers_wikipedia_provider(self):
        actions = decide_actions("who is Ada Lovelace?")
        self.assertEqual(actions[0]["type"], "run_tool")
        self.assertEqual(actions[0]["tool"], "wikipedia_lookup")

    def test_ambiguous_reference_prompt_does_not_route_to_wikipedia(self):
        actions = decide_actions("what is the name of the city")
        self.assertEqual(actions[0]["type"], "ask_clarify")
        self.assertIn("Which location", actions[0]["question"])

    def test_generic_explain_prompt_stays_off_wikipedia_provider(self):
        actions = decide_actions("Explain photosynthesis briefly.")
        self.assertFalse(actions and actions[0].get("tool") == "wikipedia_lookup")

    def test_repo_prompt_prefers_general_web_research(self):
        actions = decide_actions("find a GitHub repo for FastAPI OAuth examples")
        self.assertEqual(actions[0]["type"], "run_tool")
        self.assertEqual(actions[0]["tool"], "web_research")

    def test_stackexchange_command_routes_to_provider(self):
        actions = decide_actions("stackexchange fastapi oauth invalid_grant")
        self.assertEqual(actions[0]["type"], "run_tool")
        self.assertEqual(actions[0]["tool"], "stackexchange_search")

    def test_use_your_location_clarifies_without_task_context(self):
        actions = decide_actions("use your location")
        self.assertEqual(actions[0]["type"], "ask_clarify")
        self.assertIn("use my location", actions[0]["question"])


if __name__ == "__main__":
    unittest.main()
