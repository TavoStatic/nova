import unittest

from planner_decision import classify_route
from planner_decision import classify_route_with_context
from planner_decision import decide_turn
from routing import RouteDecision
from routing import TurnUnderstanding


class TestActionPlanner(unittest.TestCase):
    def test_static_planner_no_longer_routes_from_surface_text(self):
        for text in (
            "web search state reporting attendance rules",
            "weather in Brownsville TX",
            "wikipedia Ada Lovelace",
            "please patch apply updates.zip",
        ):
            with self.subTest(text=text):
                self.assertEqual(decide_turn(text), [])

    def test_classify_route_returns_no_static_route(self):
        route = classify_route(TurnUnderstanding(
            raw_text="web search state reporting attendance rules",
            text="web search state reporting attendance rules",
            low="web search state reporting attendance rules",
        ))

        self.assertIsInstance(route, RouteDecision)
        self.assertEqual(route.kind, "none")

    def test_classify_route_with_context_ignores_legacy_context_parser(self):
        route = classify_route_with_context(
            TurnUnderstanding(
                raw_text="weather in Brownsville TX",
                text="weather in Brownsville TX",
                low="weather in brownsville tx",
            ),
            config={"pending_action": {"kind": "weather_lookup"}},
        )

        self.assertEqual(route.kind, "none")


if __name__ == "__main__":
    unittest.main()
