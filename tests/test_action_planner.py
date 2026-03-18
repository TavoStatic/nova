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

    def test_explicit_online_research_intent_prefers_web_research(self):
        text = "research PEIMS online"
        actions = decide_actions(text)
        self.assertEqual(actions[0]["type"], "run_tool")
        self.assertEqual(actions[0]["tool"], "web_research")

    def test_session_web_override_routes_data_query_to_web_research(self):
        text = "give me anything about PEIMS"
        actions = decide_actions(text, config={"prefer_web_for_data_queries": True})
        self.assertEqual(actions[0]["type"], "run_tool")
        self.assertEqual(actions[0]["tool"], "web_research")

    def test_accepting_find_more_offer_routes_to_web_research(self):
        turns = [
            ("user", "what do you know about PEIMS?"),
            ("assistant", "PEIMS is the Public Education Information Management System. I can try to find more if you'd like."),
        ]
        actions = decide_actions("sure try to find more information if you can", config={"session_turns": turns})
        self.assertEqual(actions[0]["type"], "run_tool")
        self.assertEqual(actions[0]["tool"], "web_research")
        self.assertEqual(actions[0]["args"], ["what do you know about PEIMS?"])

    def test_generic_find_more_followup_reuses_prior_non_identity_topic(self):
        turns = [
            ("user", "what do you know about PEIMS?"),
            ("assistant", "PEIMS is the Public Education Information Management System."),
        ]
        actions = decide_actions("sure try to find more information if you can", config={"session_turns": turns})
        self.assertEqual(actions[0]["type"], "run_tool")
        self.assertEqual(actions[0]["tool"], "web_research")
        self.assertEqual(actions[0]["args"], ["what do you know about PEIMS?"])

    def test_screen_intent(self):
        actions = decide_actions("look at my screen")
        self.assertEqual(actions[0]["type"], "run_tool")
        self.assertEqual(actions[0]["tool"], "screen")

    def test_weather_current_location_intent(self):
        actions = decide_actions("can you give me the current weather in your location?")
        self.assertEqual(actions[0]["type"], "run_tool")
        self.assertEqual(actions[0]["tool"], "weather_current_location")

    def test_generic_weather_asks_for_location(self):
        actions = decide_actions("what is the weather")
        self.assertEqual(actions[0]["type"], "ask_clarify")
        self.assertIn("location", actions[0]["question"].lower())

    def test_code_help_returns_respond(self):
        actions = decide_actions("can you debug this bug in my code")
        self.assertEqual(actions[0]["type"], "respond")
        self.assertIn("file path", actions[0]["note"].lower())

    def test_chat_context_routes_command_handler(self):
        actions = decide_actions("chat context")
        self.assertEqual(actions[0]["type"], "route_command")

    def test_web_continue_routes_keyword_handler(self):
        actions = decide_actions("web continue")
        self.assertEqual(actions[0]["type"], "route_keyword")


if __name__ == "__main__":
    unittest.main()
