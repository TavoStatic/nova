"""Regression tests for the 5 seams flagged at robustness ≥ 0.90 by the
subconscious (run 2026-03-24 22:17 UTC-6).

Each class maps to one scenario family + seam.  All tests assert
`test_generic_fallback_does_not_hide_viable_specific_route` — the test name
explicitly requested by the subconscious training-priority output.

They work at two levels:
  1. Probe level  — _probe_turn_routes sees supervisor_viable or fulfillment_viable=True
    2. Routing level — TURN_SUPERVISOR.evaluate_rules / FulfillmentFlowService.should_attempt_fulfillment_flow
     confirms the route is actually taken, not fallen through to fallback.
"""
from __future__ import annotations

import unittest

import nova_core
from conversation_manager import ConversationSession
from subconscious_route_probe import analyze_route_pressure


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _weather_pending() -> dict:
    return {
        "kind": "weather_lookup",
        "status": "awaiting_location",
        "saved_location_available": True,
        "preferred_tool": "weather_current_location",
    }


def _retrieval_state() -> dict:
    return {
        "kind": "retrieval",
        "subject": "web_research",
        "query": "PEIMS attendance",
        "result_count": 2,
        "urls": ["https://tea.texas.gov/a", "https://tea.texas.gov/b"],
    }


def _probe(user_text: str, session: ConversationSession, turns=None, pending_action=None) -> dict:
    return nova_core._probe_turn_routes(
        user_text,
        session,
        list(turns or []),
        pending_action=pending_action,
    )


def _supervisor_claims(user_text: str, session: ConversationSession, turns=None, pending_action=None) -> bool:
    """True when either phase=intent or phase=handle produces a handled route."""
    for phase in ("intent", "handle"):
        r = nova_core.TURN_SUPERVISOR.evaluate_rules(
            user_text,
            manager=session,
            turns=list(turns or []),
            phase=phase,
            entry_point="probe",
        )
        if nova_core._supervisor_result_has_route(r):
            return True
    return False


# ---------------------------------------------------------------------------
# 1. weather-continuation-fallthrough (score 0.97)
# seam: weather_continuation_route_fallthrough
# ---------------------------------------------------------------------------

class TestWeatherContinuationFallthrough(unittest.TestCase):
    """When a weather_lookup pending action is in play, affirmative follow-ups
    ('go ahead', 'yes please use the saved location', 'okay do that') must be
    routed to supervisor_owned — they must NOT fall through to generic fallback."""

    INPUTS = [
        "go ahead",
        "yes please use the saved location",
        "okay do that",
        "yes get the weather for our location",
    ]

    def _session(self) -> ConversationSession:
        s = ConversationSession()
        s.set_pending_action(_weather_pending())
        return s

    def test_generic_fallback_does_not_hide_viable_specific_route(self):
        """Probe must report supervisor_viable=True for all affirmative continuations."""
        for text in self.INPUTS:
            with self.subTest(text=text):
                session = self._session()
                result = _probe(text, session, pending_action=_weather_pending())
                routes = result.get("routes", {})
                supervisor_viable = bool((routes.get("supervisor_owned") or {}).get("viable"))
                self.assertTrue(
                    supervisor_viable,
                    f"Probe hid the supervisor route for '{text}' — "
                    f"comparison_strength={result.get('comparison_strength')}, "
                    f"routes={routes}",
                )

    def test_supervisor_claims_affirmative_weather_continuation(self):
        """Supervisor must directly claim all affirmative weather continuations."""
        for text in self.INPUTS:
            with self.subTest(text=text):
                session = self._session()
                self.assertTrue(
                    _supervisor_claims(text, session, pending_action=_weather_pending()),
                    f"Supervisor did not claim '{text}' with weather pending action",
                )

    def test_fallback_pressure_is_raised_when_route_bypassed(self):
        """analyze_route_pressure must flag fallback_overuse if we pretend fallback was chosen."""
        for text in self.INPUTS[:2]:  # spot check 2 inputs
            with self.subTest(text=text):
                session = self._session()
                probe_result = _probe(text, session, pending_action=_weather_pending())
                record = analyze_route_pressure(probe_result, chosen_route="generic_fallback")
                self.assertIn(
                    "fallback_overuse",
                    record.signals,
                    f"No fallback_overuse signal for '{text}' — subconscious would miss the regression",
                )


# ---------------------------------------------------------------------------
# 2. memory-capture-fallthrough (score 0.97)
# seam: memory_capture_route_fallthrough
# ---------------------------------------------------------------------------

class TestMemoryCaptureFallthrough(unittest.TestCase):
    """'remember this X' and 'Remember this: X' are explicit store-fact/set-location
    commands.  The supervisor must claim them — not fall through to generic chat."""

    FACT_INPUTS = [
        "Remember this: my favorite color is teal. Don't forget.",
        "remember this I prefer concise summaries with the key facts first",
        "remember this my integration marker is memory-route-alpha",
    ]

    LOCATION_INPUTS = [
        "remember this Brownsville is my location",
    ]

    def test_generic_fallback_does_not_hide_viable_specific_route_for_facts(self):
        for text in self.FACT_INPUTS:
            with self.subTest(text=text):
                session = ConversationSession()
                result = _probe(text, session)
                routes = result.get("routes", {})
                supervisor_viable = bool((routes.get("supervisor_owned") or {}).get("viable"))
                self.assertTrue(
                    supervisor_viable,
                    f"Probe hid the supervisor route for fact input '{text}'",
                )

    def test_generic_fallback_does_not_hide_viable_specific_route_for_location(self):
        for text in self.LOCATION_INPUTS:
            with self.subTest(text=text):
                session = ConversationSession()
                result = _probe(text, session)
                routes = result.get("routes", {})
                supervisor_viable = bool((routes.get("supervisor_owned") or {}).get("viable"))
                self.assertTrue(
                    supervisor_viable,
                    f"Probe hid the supervisor route for location input '{text}'",
                )

    def test_supervisor_claims_remember_this_turns(self):
        for text in self.FACT_INPUTS + self.LOCATION_INPUTS:
            with self.subTest(text=text):
                session = ConversationSession()
                self.assertTrue(
                    _supervisor_claims(text, session),
                    f"Supervisor did not claim memory capture turn '{text}'",
                )

    def test_fallback_pressure_raised_when_route_bypassed(self):
        for text in self.FACT_INPUTS[:1]:
            session = ConversationSession()
            probe_result = _probe(text, session)
            record = analyze_route_pressure(probe_result, chosen_route="generic_fallback")
            self.assertIn("fallback_overuse", record.signals)


# ---------------------------------------------------------------------------
# 3. retrieval-followup-fallthrough (score 0.97)
# seam: retrieval_followup_route_fallthrough
# ---------------------------------------------------------------------------

class TestRetrievalFollowupFallthrough(unittest.TestCase):
    """After a web_research retrieval with active state, follow-up turns
    ('tell me about the first one', 'what did you find', 'web continue')
    must be routed to supervisor_owned via the retrieval_followup rule."""

    INPUTS = [
        "tell me about the first one",
        "what did you find",
        "web continue",
    ]

    def _session(self) -> ConversationSession:
        s = ConversationSession()
        s.set_retrieval_state(_retrieval_state())
        return s

    def test_generic_fallback_does_not_hide_viable_specific_route(self):
        for text in self.INPUTS:
            with self.subTest(text=text):
                session = self._session()
                result = _probe(text, session)
                routes = result.get("routes", {})
                supervisor_viable = bool((routes.get("supervisor_owned") or {}).get("viable"))
                self.assertTrue(
                    supervisor_viable,
                    f"Probe hid supervisor route for retrieval follow-up '{text}'",
                )

    def test_supervisor_claims_retrieval_followup_turns(self):
        for text in self.INPUTS:
            with self.subTest(text=text):
                session = self._session()
                # "web continue" is a command word routed via the planner, not a
                # supervisor rule.  Accept either path claiming supervisor_viable.
                claimed_by_supervisor = _supervisor_claims(text, session)
                if not claimed_by_supervisor:
                    result = _probe(text, session)
                    routes = result.get("routes", {})
                    supervisor_viable = bool((routes.get("supervisor_owned") or {}).get("viable"))
                    self.assertTrue(
                        supervisor_viable,
                        f"Neither supervisor nor probe claimed retrieval follow-up '{text}'",
                    )

    def test_fallback_pressure_raised_when_route_bypassed(self):
        for text in self.INPUTS[:1]:
            session = self._session()
            probe_result = _probe(text, session)
            record = analyze_route_pressure(probe_result, chosen_route="generic_fallback")
            self.assertIn("fallback_overuse", record.signals)


# ---------------------------------------------------------------------------
# 4. patch-routing-fallthrough (score 0.97)
# seam: patch_routing_fallthrough
# ---------------------------------------------------------------------------

class TestPatchRoutingFallthrough(unittest.TestCase):
    """Patch commands ('patch apply X', 'patch preview X', 'patch rollback')
    must be routed deterministically — never to generic fallback."""

    INPUTS = [
        "please patch apply updates.zip",
        "patch preview teach.zip",
        "patch rollback",
    ]

    def test_generic_fallback_does_not_hide_viable_specific_route(self):
        for text in self.INPUTS:
            with self.subTest(text=text):
                session = ConversationSession()
                result = _probe(text, session)
                routes = result.get("routes", {})
                supervisor_viable = bool((routes.get("supervisor_owned") or {}).get("viable"))
                self.assertTrue(
                    supervisor_viable,
                    f"Probe hid deterministic patch route for '{text}'",
                )

    def test_supervisor_or_planner_claims_patch_turns(self):
        for text in self.INPUTS:
            with self.subTest(text=text):
                session = ConversationSession()
                # Either the supervisor claims it, or probe shows supervisor_viable=True
                result = _probe(text, session)
                routes = result.get("routes", {})
                supervisor_viable = bool((routes.get("supervisor_owned") or {}).get("viable"))
                self.assertTrue(
                    supervisor_viable or _supervisor_claims(text, session),
                    f"Neither probe nor supervisor claimed patch turn '{text}'",
                )

    def test_fallback_pressure_raised_when_route_bypassed(self):
        for text in self.INPUTS[:1]:
            session = ConversationSession()
            probe_result = _probe(text, session)
            record = analyze_route_pressure(probe_result, chosen_route="generic_fallback")
            self.assertIn("fallback_overuse", record.signals)


# ---------------------------------------------------------------------------
# 5. fulfillment-fallthrough (score 0.97)
# seam: fulfillment_bridge_entry_fallthrough
# ---------------------------------------------------------------------------

class TestFulfillmentFallthrough(unittest.TestCase):
    """Explicit multi-option / comparison requests must show fulfillment_viable=True
    so they can be served by the fulfillment bridge rather than generic fallback."""

    INPUTS = [
        "Show me workable options without collapsing too early.",
        "Can you compare a few viable ways forward before picking one for me ?",
        "I need options here. Do not collapse to one answer yet.",
    ]

    def test_generic_fallback_does_not_hide_viable_specific_route(self):
        for text in self.INPUTS:
            with self.subTest(text=text):
                session = ConversationSession()
                result = _probe(text, session)
                routes = result.get("routes", {})
                fulfillment_viable = bool((routes.get("fulfillment_applicable") or {}).get("viable"))
                self.assertTrue(
                    fulfillment_viable,
                    f"Probe hid fulfillment route for '{text}' — "
                    f"comparison_strength={result.get('comparison_strength')}, "
                    f"routes={routes}",
                )

    def test_fulfillment_flow_attempted_for_explicit_options_requests(self):
        flow_service = nova_core._fulfillment_flow_service()
        for text in self.INPUTS:
            with self.subTest(text=text):
                session = ConversationSession()
                turns: list = []
                should = flow_service.should_attempt_fulfillment_flow(text, session, turns)
                self.assertTrue(
                    should,
                    f"FulfillmentFlowService.should_attempt_fulfillment_flow returned False for '{text}'",
                )

    def test_fallback_pressure_raised_when_fulfillment_bypassed(self):
        for text in self.INPUTS[:1]:
            session = ConversationSession()
            probe_result = _probe(text, session)
            record = analyze_route_pressure(probe_result, chosen_route="generic_fallback")
            # fulfillment_missed requires comparison_strength=clear; if probe is weak,
            # at minimum fallback_overuse should fire when fulfillment_viable=True
            routes = probe_result.get("routes", {})
            fulfillment_viable = bool((routes.get("fulfillment_applicable") or {}).get("viable"))
            if fulfillment_viable:
                self.assertTrue(
                    "fallback_overuse" in record.signals or "fulfillment_missed" in record.signals,
                    f"No pressure signal for '{text}' despite fulfillment being viable",
                )


if __name__ == "__main__":
    unittest.main()
