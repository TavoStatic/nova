import unittest

import planner_decision


class TestPlannerDecisionIntentGate(unittest.TestCase):
    def test_city_name_without_context_asks_for_clarification(self):
        actions = planner_decision.decide_turn("what is the name of the city", config={})

        self.assertEqual(actions[0]["type"], "ask_clarify")
        self.assertIn("Which location", actions[0]["question"])

    def test_city_name_with_location_context_does_not_route_to_wikipedia(self):
        actions = planner_decision.decide_turn(
            "what is the name of the city",
            config={
                "session_turns": [
                    ("assistant", "My current device location is 25.93832,-97.45515. Accuracy about 128m."),
                ]
            },
        )

        self.assertEqual(actions, [])

    def test_research_followup_without_online_intent_does_not_force_web(self):
        actions = planner_decision.decide_turn(
            "find more information",
            config={
                "session_turns": [
                    ("user", "What are the attendance reporting rules for student_data?"),
                    ("assistant", "I can explain what I know from the current context."),
                ]
            },
        )

        self.assertEqual(actions, [])

    def test_research_followup_after_web_offer_can_accept_offer(self):
        actions = planner_decision.decide_turn(
            "yes, find more information",
            config={
                "session_turns": [
                    ("user", "What are the attendance reporting rules for student_data?"),
                    ("assistant", "I can try to find more if you want."),
                ]
            },
        )

        self.assertEqual(actions[0]["type"], "run_tool")
        self.assertEqual(actions[0]["tool"], "web_research")


if __name__ == "__main__":
    unittest.main()
