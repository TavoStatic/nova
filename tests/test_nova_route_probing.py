import unittest

from services.nova_route_probing import build_probe_turn_routes
from services.nova_route_probing import evaluate_deterministic_route_viability


class TestNovaRouteProbing(unittest.TestCase):
    def test_deterministic_route_viability_prefers_supervisor_owned_result(self):
        def evaluate_rules(user_text, **kwargs):
            phase = kwargs.get("phase")
            if phase == "intent":
                return {"handled": True, "rule_name": "weather_lookup", "intent": "weather_lookup"}
            return {"handled": False}

        result = evaluate_deterministic_route_viability(
            "weather in brownsville",
            object(),
            [],
            evaluate_rules_fn=evaluate_rules,
            supervisor_result_has_route_fn=lambda payload: bool(payload and payload.get("handled")),
            planner_decide_turn_fn=None,
        )

        self.assertTrue(result.get("viable"))
        self.assertEqual(result.get("owner_kind"), "supervisor")
        self.assertEqual((result.get("owned_result") or {}).get("rule_name"), "weather_lookup")

    def test_build_probe_turn_routes_marks_weak_when_multiple_routes_viable(self):
        result = build_probe_turn_routes(
            "show me workable options",
            {"viable": True, "fit_notes": ["explicit supervisor rule"]},
            {"viable": True, "fit_notes": ["fulfillment comparison may help"]},
        )

        self.assertEqual(result.get("comparison_strength"), "weak")
        self.assertTrue(((result.get("routes") or {}).get("generic_fallback") or {}).get("viable"))


if __name__ == "__main__":
    unittest.main()