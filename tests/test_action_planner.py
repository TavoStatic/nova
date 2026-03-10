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

    def test_web_gather_intent(self):
        text = "please gather and summarize https://tea.texas.gov/reports"
        actions = decide_actions(text)
        self.assertEqual(actions[0]["type"], "run_tool")
        self.assertEqual(actions[0]["tool"], "web_gather")

    def test_web_research_intent(self):
        text = "get me all the information you can about peims"
        actions = decide_actions(text)
        self.assertEqual(actions[0]["type"], "run_tool")
        self.assertEqual(actions[0]["tool"], "web_research")


if __name__ == "__main__":
    unittest.main()
