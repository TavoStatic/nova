import unittest
from unittest import mock

from services.memory_production import (
    apply_user_memory_learning,
    build_memory_read_plan,
    build_memory_recall_plan,
    extract_color_preferences_from_text,
    parse_correction,
)


class TestMemoryProduction(unittest.TestCase):
    def test_parse_correction_detects_prefix_and_pending_state(self):
        handled, parsed = parse_correction("no, my name is Gus")
        self.assertTrue(handled)
        self.assertEqual(parsed, "my name is Gus")

        handled_no, parsed_no = parse_correction("no Gustavo built you")
        self.assertTrue(handled_no)
        self.assertEqual(parsed_no, "Gustavo built you")

        handled_pending, parsed_pending = parse_correction(
            "use Gustavo instead",
            pending_correction_target="developer_name",
        )
        self.assertTrue(handled_pending)
        self.assertEqual(parsed_pending, "use Gustavo instead")

    def test_parse_correction_ignores_ordinary_negations(self):
        for text in (
            "not sure what you mean",
            "no idea what happened",
            "no worries about that",
            "not yet",
            "not yet ready",
            "not quite ready",
        ):
            handled, parsed = parse_correction(text)
            self.assertFalse(handled, msg=text)
            self.assertEqual(parsed, "", msg=text)

    def test_apply_user_memory_learning_does_not_handle_ordinary_negations(self):
        stored: list[dict] = []

        for text in ("not yet", "not sure what you mean", "no idea"):
            outcome = apply_user_memory_learning(
                text,
                mem_enabled_fn=lambda: True,
                mem_add_fn=lambda *_args, **_kwargs: None,
                mem_remember_fact_fn=lambda _fact: "",
                load_learned_facts_fn=lambda: {},
                save_learned_facts_fn=lambda _data: None,
                get_learned_fact_fn=lambda _key, default="": default,
                set_active_user_fn=lambda _name: None,
                get_active_user_fn=lambda: "gus",
                load_identity_profile_fn=lambda: {},
                save_identity_profile_fn=lambda _data: None,
                store_correction_record_fn=lambda *args, **kwargs: stored.append(kwargs),
            )
            self.assertFalse(outcome.get("handled"), msg=text)
            self.assertEqual(outcome.get("action"), "", msg=text)
        self.assertEqual(stored, [])

    def test_extract_color_preferences_from_text(self):
        colors = extract_color_preferences_from_text("blue, green and red")
        self.assertEqual(colors, ["blue", "green", "red"])

    def test_build_memory_recall_plan_delegates_to_router(self):
        with mock.patch(
            "services.memory_production.MEMORY_ROUTING_SERVICE.plan_durable_recall",
            return_value=object(),
        ) as plan_mock:
            plan = build_memory_recall_plan(
                "what is my favorite color",
                purpose="user_preferences",
                conversation_state={"kind": "retrieval"},
            )

        self.assertIs(plan, plan_mock.return_value)
        plan_mock.assert_called_once_with(
            "what is my favorite color",
            purpose="user_preferences",
            conversation_state={"kind": "retrieval"},
            pending_action=None,
        )

    def test_build_memory_read_plan_uses_recent_learning_purpose(self):
        with mock.patch(
            "services.memory_production.MEMORY_ROUTING_SERVICE.plan_durable_recall",
            return_value=object(),
        ) as plan_mock:
            build_memory_read_plan("what have you learned from me")

        plan_mock.assert_called_once_with(
            "what have you learned from me",
            purpose="recent_learning_summary",
            conversation_state=None,
            pending_action=None,
        )

    def test_apply_user_memory_learning_remember_fact_short_circuits(self):
        outcome = apply_user_memory_learning(
            "remember: sky blue is calming",
            mem_enabled_fn=lambda: True,
            mem_add_fn=lambda *_args, **_kwargs: None,
            mem_remember_fact_fn=lambda fact: f"Pinned memory saved: {fact}",
            load_learned_facts_fn=lambda: {},
            save_learned_facts_fn=lambda _data: None,
            get_learned_fact_fn=lambda _key, default="": default,
            set_active_user_fn=lambda _name: None,
            get_active_user_fn=lambda: "gus",
            load_identity_profile_fn=lambda: {},
            save_identity_profile_fn=lambda _data: None,
            store_correction_record_fn=lambda *_args, **_kwargs: None,
        )

        self.assertTrue(outcome.get("handled"))
        self.assertEqual(outcome.get("action"), "remember_fact")
        self.assertIn("sky blue is calming", str(outcome.get("early_reply") or ""))

    def test_apply_user_memory_learning_stores_supervisor_correction(self):
        stored: list[dict] = []

        def _store(correction_text, **kwargs):
            stored.append({"correction_text": correction_text, **kwargs})

        outcome = apply_user_memory_learning(
            "no, Gustavo built you",
            input_source="typed",
            last_assistant="You were made by someone else.",
            mem_enabled_fn=lambda: True,
            mem_add_fn=lambda *_args, **_kwargs: None,
            mem_remember_fact_fn=lambda _fact: "",
            load_learned_facts_fn=lambda: {},
            save_learned_facts_fn=lambda _data: None,
            get_learned_fact_fn=lambda _key, default="": default,
            set_active_user_fn=lambda _name: None,
            get_active_user_fn=lambda: "gus",
            load_identity_profile_fn=lambda: {},
            save_identity_profile_fn=lambda _data: None,
            store_correction_record_fn=_store,
        )

        self.assertTrue(outcome.get("handled"))
        self.assertEqual(outcome.get("action"), "supervisor_correction")
        self.assertEqual(outcome.get("early_reply"), "")
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0]["parsed_correction"], "Gustavo built you")


if __name__ == "__main__":
    unittest.main()