import unittest
from pathlib import Path

from conversation_manager import ConversationSession
from supervisor import Supervisor


class TestSupervisorOwnershipGate(unittest.TestCase):
    def test_default_supervisor_does_not_register_self_description_content_intents(self):
        rule_names = {str(item.get("name") or "") for item in Supervisor().rules}

        self.assertNotIn("grounded_self_report", rule_names)
        self.assertNotIn("runtime_identity", rule_names)
        self.assertNotIn("capability_inventory", rule_names)
        self.assertNotIn("operator_feedback", rule_names)
        self.assertNotIn("weather_lookup", rule_names)
        self.assertNotIn("web_research_family", rule_names)
        self.assertNotIn("retrieval_followup", rule_names)
        self.assertNotIn("location_weather", rule_names)

    def test_supervisor_does_not_claim_smalltalk_intent(self):
        result = Supervisor().evaluate_rules("how are you doing today ?", phase="intent")

        self.assertFalse(result.get("handled"))
        self.assertNotEqual(result.get("rule_name"), "smalltalk")

    def test_supervisor_does_not_claim_open_ended_name_origin_query(self):
        result = Supervisor().evaluate_rules("why are you called Nova?", phase="intent")

        self.assertFalse(result.get("handled"))
        self.assertNotEqual(result.get("rule_name"), "name_origin")

    def test_supervisor_does_not_claim_open_ended_developer_profile_query(self):
        result = Supervisor().evaluate_rules("who is gus ?", phase="intent")

        self.assertFalse(result.get("handled"))
        self.assertNotEqual(result.get("rule_name"), "developer_profile")

    def test_supervisor_does_not_claim_session_summary_pattern(self):
        result = Supervisor().evaluate_rules("what happened", phase="intent")

        self.assertFalse(result.get("handled"))
        self.assertNotEqual(result.get("rule_name"), "session_summary")

    def test_supervisor_does_not_claim_explicit_weather_current_command(self):
        result = Supervisor().evaluate_rules("weather current location", phase="intent")

        self.assertFalse(result.get("handled"))
        self.assertNotEqual(result.get("rule_name"), "weather_lookup")

    def test_supervisor_does_not_use_saved_location_for_pending_weather_affirmation(self):
        session = ConversationSession()
        session.set_pending_action(
            {
                "kind": "weather_lookup",
                "status": "awaiting_location",
                "saved_location_available": True,
                "preferred_tool": "weather_location",
            }
        )

        result = Supervisor().evaluate_rules("go ahead", manager=session, phase="intent")

        self.assertFalse(result.get("handled"))
        self.assertNotEqual(result.get("rule_name"), "weather_lookup")

    def test_supervisor_does_not_use_saved_location_for_pending_weather_consent_phrase(self):
        session = ConversationSession()
        session.set_pending_action(
            {
                "kind": "weather_lookup",
                "status": "awaiting_location",
                "saved_location_available": True,
                "preferred_tool": "weather_location",
            }
        )

        result = Supervisor().evaluate_rules("yes use the saved location", manager=session, phase="intent")

        self.assertFalse(result.get("handled"))
        self.assertNotEqual(result.get("rule_name"), "weather_lookup")

    def test_supervisor_does_not_claim_retrieval_followup_content(self):
        session = ConversationSession()
        session.set_retrieval_state(
            {
                "kind": "retrieval",
                "subject": "web_research",
                "query": "PEIMS attendance",
                "result_count": 2,
                "urls": ["https://tea.texas.gov/a", "https://tea.texas.gov/b"],
            }
        )

        result = Supervisor().evaluate_rules("tell me about the first one", manager=session, phase="handle")

        self.assertFalse(result.get("handled"))
        self.assertNotEqual(result.get("rule_name"), "retrieval_followup")
        self.assertFalse(any(item.get("rule_name") == "retrieval_followup" for item in result.get("candidates", [])))

    def test_cli_loop_does_not_own_location_trigger_lists(self):
        source = (Path(__file__).resolve().parents[1] / "services" / "nova_cli_loop.py").read_text(encoding="utf-8")

        self.assertNotIn("loc_triggers", source)
        self.assertNotIn("expand_triggers", source)

    def test_followup_dispatch_does_not_own_location_conversation_fallback(self):
        source = (Path(__file__).resolve().parents[1] / "services" / "nova_followup_dispatch.py").read_text(encoding="utf-8")

        self.assertNotIn("handle_location_conversation_turn", source)

    def test_cli_loop_does_not_own_pending_weather_followup_fallback(self):
        source = (Path(__file__).resolve().parents[1] / "services" / "nova_cli_loop.py").read_text(encoding="utf-8")

        self.assertNotIn("apply_pending_weather_followup_fallback", source)

    def test_http_chat_flow_only_imports_active_numeric_turn_outcome(self):
        source = (Path(__file__).resolve().parents[1] / "http_chat_flow.py").read_text(encoding="utf-8")

        self.assertIn("from services.nova_turn_outcomes import apply_numeric_clarify_outcome", source)
        retired_outcomes = [
            "apply_fast_smalltalk",
            "apply_identity_binding_learning",
            "apply_mixed_turn_clarify",
            "apply_supervisor_bypass_safe_fallback",
            "apply_developer_profile_learning",
            "apply_self_profile_learning",
            "apply_location_store_outcome",
            "apply_saved_location_weather_outcome",
            "apply_declarative_store_outcome",
            "apply_developer_guess_outcome",
            "apply_developer_location_outcome",
        ]
        for outcome_name in retired_outcomes:
            self.assertNotIn(f"from services.nova_turn_outcomes import {outcome_name}", source)
            self.assertNotIn(f"def {outcome_name}(", source)

    def test_cli_loop_uses_shared_numeric_clarify_without_mixed_content_owner(self):
        source = (Path(__file__).resolve().parents[1] / "services" / "nova_cli_loop.py").read_text(encoding="utf-8")

        self.assertIn("from services.nova_turn_outcomes import apply_numeric_clarify_outcome", source)
        self.assertNotIn("from services.nova_turn_outcomes import apply_mixed_turn_clarify", source)
        self.assertNotIn("if \"mixed\" in turn_acts", source)
        self.assertNotIn("core._should_clarify_unlabeled_numeric_turn(", source)

    def test_cli_loop_does_not_use_web_override_outcome(self):
        source = (Path(__file__).resolve().parents[1] / "services" / "nova_cli_loop.py").read_text(encoding="utf-8")

        self.assertNotIn("from services.nova_turn_outcomes import apply_web_research_override", source)
        self.assertNotIn("apply_web_research_override(", source)
        self.assertNotIn("core._is_web_research_override_request(", source)

    def test_cli_loop_does_not_apply_supervisor_bypass_reply_outcome(self):
        source = (Path(__file__).resolve().parents[1] / "services" / "nova_cli_loop.py").read_text(encoding="utf-8")

        self.assertNotIn("from services.nova_turn_outcomes import apply_supervisor_bypass_safe_fallback", source)
        self.assertNotIn("apply_supervisor_bypass_safe_fallback(", source)
        self.assertNotIn("safe_reply, safe_kind", source)
        self.assertNotIn("core._open_probe_reply(", source)


if __name__ == "__main__":
    unittest.main()
