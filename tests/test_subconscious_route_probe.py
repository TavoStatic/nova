import unittest

from subconscious_route_probe import analyze_route_pressure


def _probe(
    *,
    user_text: str,
    comparison_strength: str,
    supervisor_viable: bool,
    fulfillment_viable: bool,
    fallback_viable: bool = True,
) -> dict:
    return {
        "user_text": user_text,
        "comparison_strength": comparison_strength,
        "routes": {
            "supervisor_owned": {
                "viable": supervisor_viable,
                "fit_notes": ["explicit supervisor rule"] if supervisor_viable else [],
            },
            "fulfillment_applicable": {
                "viable": fulfillment_viable,
                "fit_notes": ["fulfillment comparison may be useful"] if fulfillment_viable else [],
            },
            "generic_fallback": {
                "viable": fallback_viable,
                "fit_notes": ["generic fallback remains available"],
            },
        },
    }


class TestSubconsciousRouteProbe(unittest.TestCase):
    def test_explicit_supervisor_turn_emits_no_pressure_by_default(self):
        record = analyze_route_pressure(
            _probe(
                user_text="check the weather if you can please..",
                comparison_strength="clear",
                supervisor_viable=True,
                fulfillment_viable=False,
            ),
            chosen_route="supervisor_owned",
        )

        self.assertEqual(record.signals, [])
        self.assertTrue(record.supervisor_viable)
        self.assertFalse(record.fulfillment_viable)

    def test_clear_fulfillment_turn_flags_missed_when_fallback_used(self):
        record = analyze_route_pressure(
            _probe(
                user_text="show me workable options without collapsing too early",
                comparison_strength="clear",
                supervisor_viable=False,
                fulfillment_viable=True,
            ),
            chosen_route="generic_fallback",
        )

        self.assertIn("fulfillment_missed", record.signals)
        self.assertIn("fallback_overuse", record.signals)

    def test_ordinary_fallback_turn_stays_low_pressure(self):
        record = analyze_route_pressure(
            _probe(
                user_text="how are you doing today ?",
                comparison_strength="weak",
                supervisor_viable=False,
                fulfillment_viable=False,
            ),
            chosen_route="generic_fallback",
        )

        self.assertNotIn("fallback_overuse", record.signals)
        self.assertIn("route_unclear", record.signals)
        self.assertIn("route_fit_weak", record.signals)

    def test_weak_comparison_emits_unclear_and_fit_weak(self):
        record = analyze_route_pressure(
            _probe(
                user_text="what now",
                comparison_strength="weak",
                supervisor_viable=False,
                fulfillment_viable=False,
            ),
        )

        self.assertIn("route_unclear", record.signals)
        self.assertIn("route_fit_weak", record.signals)

    def test_route_conflict_case_emits_conflict_and_supervisor_overreach_when_chosen(self):
        record = analyze_route_pressure(
            _probe(
                user_text="compare options and also use the saved route",
                comparison_strength="weak",
                supervisor_viable=True,
                fulfillment_viable=True,
            ),
            chosen_route="supervisor_owned",
        )

        self.assertIn("route_conflict", record.signals)
        self.assertIn("supervisor_overreach", record.signals)
        self.assertIn("route_unclear", record.signals)


if __name__ == "__main__":
    unittest.main()