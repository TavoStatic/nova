import unittest

from planner_decision import choose_execution, classify_route, decide_turn, understand_turn


class TestPlannerDecision(unittest.TestCase):
    def test_understand_turn_extracts_url_and_context_flags(self):
        turn = understand_turn("can you give me the current weather in your location? see https://example.com")
        self.assertEqual(turn.url, "https://example.com")
        self.assertTrue(turn.mentions_location)
        self.assertTrue(turn.mentions_weather)

    def test_classify_route_marks_legacy_command(self):
        route = classify_route(understand_turn("chat context"))
        self.assertEqual(route.kind, "legacy_command")

    def test_classify_route_marks_legacy_keyword(self):
        route = classify_route(understand_turn("web continue"))
        self.assertEqual(route.kind, "legacy_keyword")

    def test_choose_execution_maps_direct_tool(self):
        route = classify_route(understand_turn("look at my screen"))
        actions = choose_execution(route)
        self.assertEqual(actions[0]["type"], "run_tool")
        self.assertEqual(actions[0]["tool"], "screen")

    def test_decide_turn_maps_code_help_to_respond(self):
        actions = decide_turn("can you debug this bug in my code")
        self.assertEqual(actions[0]["type"], "respond")
        self.assertIn("file path", actions[0]["note"].lower())

    def test_decide_turn_maps_shared_location_weather_followup(self):
        actions = decide_turn("yes get the weather for our location")
        self.assertEqual(actions[0]["type"], "run_tool")
        self.assertEqual(actions[0]["tool"], "weather_current_location")

    def test_decide_turn_bare_weather_clarifies(self):
        actions = decide_turn("weather")
        self.assertEqual(actions[0]["type"], "ask_clarify")
        self.assertIn("what location", actions[0]["question"].lower())

    def test_decide_turn_bare_check_weather_clarifies(self):
        actions = decide_turn("check weather")
        self.assertEqual(actions[0]["type"], "ask_clarify")
        self.assertIn("what location", actions[0]["question"].lower())

    def test_decide_turn_weather_question_clarifies(self):
        actions = decide_turn("notice any changes in the weather ?")
        self.assertEqual(actions[0]["type"], "ask_clarify")
        self.assertIn("what location", actions[0]["question"].lower())

    def test_decide_turn_uses_prior_weather_clarification_context(self):
        actions = decide_turn(
            "our location nova",
            config={"session_turns": [("assistant", "What location should I use for the weather lookup?")]},
        )
        self.assertEqual(actions[0]["type"], "run_tool")
        self.assertEqual(actions[0]["tool"], "weather_current_location")

    def test_decide_turn_uses_pending_weather_action_for_affirmative_followup(self):
        actions = decide_turn(
            "yea please do that ..",
            config={
                "pending_action": {
                    "kind": "weather_lookup",
                    "status": "awaiting_location",
                    "saved_location_available": True,
                    "preferred_tool": "weather_current_location",
                }
            },
        )
        self.assertEqual(actions[0]["type"], "run_tool")
        self.assertEqual(actions[0]["tool"], "weather_current_location")


if __name__ == "__main__":
    unittest.main()