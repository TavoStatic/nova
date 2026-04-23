import unittest

from services import nova_profile_followups


class TestNovaProfileFollowups(unittest.TestCase):
    def test_developer_color_reply_uses_memory_prefix(self):
        reply = nova_profile_followups.developer_color_reply(
            [],
            extract_developer_color_preferences_fn=lambda turns: [],
            extract_developer_color_preferences_from_memory_fn=lambda: ["silver", "blue"],
            prefix_from_earlier_memory_fn=lambda text: f"From earlier memory: {text}",
        )

        self.assertTrue(reply.startswith("From earlier memory:"))
        self.assertIn("silver", reply.lower())

    def test_developer_bilingual_reply_prefers_session_fact(self):
        reply = nova_profile_followups.developer_bilingual_reply(
            [],
            developer_is_bilingual_fn=lambda turns: True,
            developer_is_bilingual_from_memory_fn=lambda: None,
            prefix_from_earlier_memory_fn=lambda text: f"From earlier memory: {text}",
        )

        self.assertEqual(reply, "Yes. From what you've told me, Gus is bilingual in English and Spanish.")

    def test_color_reply_reports_multiple_preferences(self):
        reply = nova_profile_followups.color_reply(
            [],
            extract_color_preferences_fn=lambda turns: ["teal", "blue"],
            extract_color_preferences_from_memory_fn=lambda: [],
            prefix_from_earlier_memory_fn=lambda text: f"From earlier memory: {text}",
        )

        self.assertIn("teal", reply.lower())
        self.assertIn("blue", reply.lower())

    def test_animal_reply_handles_missing_facts(self):
        reply = nova_profile_followups.animal_reply(
            [],
            extract_animal_preferences_fn=lambda turns: [],
            extract_animal_preferences_from_memory_fn=lambda: [],
            prefix_from_earlier_memory_fn=lambda text: f"From earlier memory: {text}",
        )

        self.assertIn("haven't told me animal preferences", reply.lower())

    def test_color_animal_match_reply_reports_best_match(self):
        reply = nova_profile_followups.color_animal_match_reply(
            [],
            extract_color_preferences_fn=lambda turns: ["blue", "brown"],
            extract_color_preferences_from_memory_fn=lambda: [],
            extract_animal_preferences_fn=lambda turns: ["dogs"],
            extract_animal_preferences_from_memory_fn=lambda: [],
            pick_color_for_animals_fn=lambda colors, animals: "brown",
        )

        low = reply.lower()
        self.assertIn("brown matches best", low)
        self.assertIn("dogs", low)
        self.assertIn("blue, brown", low)

    def test_color_animal_match_reply_handles_missing_colors(self):
        reply = nova_profile_followups.color_animal_match_reply(
            [],
            extract_color_preferences_fn=lambda turns: [],
            extract_color_preferences_from_memory_fn=lambda: [],
            extract_animal_preferences_fn=lambda turns: ["dogs"],
            extract_animal_preferences_from_memory_fn=lambda: [],
            pick_color_for_animals_fn=lambda colors, animals: "",
        )

        self.assertIn("don't have your color preferences", reply.lower())

    def test_developer_profile_reply_combines_memory_backed_facts(self):
        reply = nova_profile_followups.developer_profile_reply(
            [],
            "what else do you know about your developer?",
            get_learned_fact_fn=lambda key, default="": {
                "developer_name": "Gustavo Uribe",
                "developer_nickname": "Gus",
            }.get(key, default),
            extract_developer_roles_from_memory_fn=lambda: ["full stack developer", "student_data Data Specialist"],
            extract_developer_color_preferences_fn=lambda turns: [],
            extract_developer_color_preferences_from_memory_fn=lambda: ["silver", "blue"],
            developer_is_bilingual_fn=lambda turns: None,
            developer_is_bilingual_from_memory_fn=lambda: True,
            prefix_from_earlier_memory_fn=lambda text: text,
            format_fact_series_fn=lambda values: ", ".join(values[:-1]) + f", and {values[-1]}" if len(values) > 2 else " and ".join(values),
        )

        low = reply.lower()
        self.assertIn("gustavo uribe", low)
        self.assertIn("student_data data specialist", low)
        self.assertIn("silver", low)
        self.assertIn("english and spanish", low)

    def test_identity_profile_followup_reply_uses_self_memory_facts(self):
        reply = nova_profile_followups.identity_profile_followup_reply(
            "self",
            [],
            get_active_user_fn=lambda: "Ana",
            get_learned_fact_fn=lambda key, default="": default,
            speaker_matches_developer_fn=lambda: False,
            extract_developer_roles_from_memory_fn=lambda: [],
            extract_developer_color_preferences_fn=lambda turns: [],
            extract_developer_color_preferences_from_memory_fn=lambda: [],
            developer_is_bilingual_fn=lambda turns: None,
            developer_is_bilingual_from_memory_fn=lambda: None,
            get_name_origin_story_fn=lambda: "",
            extract_color_preferences_fn=lambda turns: [],
            extract_color_preferences_from_memory_fn=lambda: ["green"],
            extract_animal_preferences_fn=lambda turns: [],
            extract_animal_preferences_from_memory_fn=lambda: ["dogs"],
            format_fact_series_fn=lambda values: ", ".join(values[:-1]) + f", and {values[-1]}" if len(values) > 2 else " and ".join(values),
        )

        low = reply.lower()
        self.assertIn("ana", low)
        self.assertIn("green", low)
        self.assertIn("dogs", low)

    def test_identity_name_followup_reply_uses_verified_developer_identity(self):
        reply = nova_profile_followups.identity_name_followup_reply(
            "self",
            get_active_user_fn=lambda: "Gustavo Uribe",
            get_learned_fact_fn=lambda key, default="": {
                "assistant_name": "Nova",
                "developer_name": "Gustavo Uribe",
                "developer_nickname": "Gus",
            }.get(key, default),
            get_name_origin_story_fn=lambda: "Nova was given its name by Gus.",
            speaker_matches_developer_fn=lambda: True,
        )

        low = reply.lower()
        self.assertIn("your verified full name is gustavo uribe", low)
        self.assertIn("you also go by gus", low)
        self.assertIn("you gave me the name nova", low)

    def test_developer_location_turn_returns_reply_and_profile_state(self):
        reply, next_state = nova_profile_followups.developer_location_turn(
            "where is gus",
            state=None,
            turns=[],
            is_developer_location_request_fn=lambda text, state=None, turns=None: True,
            infer_profile_conversation_state_fn=lambda text: None,
            make_conversation_state_fn=lambda kind, **data: {"kind": kind, **data},
            developer_location_reply_fn=lambda: "Based on the verified relation you gave me, Gus's location is Brownsville.",
        )

        self.assertIn("gus's location is brownsville", reply.lower())
        self.assertEqual(next_state, {"kind": "identity_profile", "subject": "developer"})

    def test_infer_profile_conversation_state_prefers_rule_state_update(self):
        state = nova_profile_followups.infer_profile_conversation_state(
            "whatever",
            normalize_turn_text_fn=lambda text: text.lower().strip(),
            evaluate_rule_state_fn=lambda text: {"state_update": {"kind": "custom", "subject": "developer"}},
            speaker_matches_developer_fn=lambda: False,
            is_developer_color_lookup_request_fn=lambda text: False,
            is_developer_bilingual_request_fn=lambda text: False,
            is_color_lookup_request_fn=lambda text: False,
            make_conversation_state_fn=lambda kind, **data: {"kind": kind, **data},
        )

        self.assertEqual(state, {"kind": "custom", "subject": "developer"})

    def test_infer_profile_conversation_state_sets_developer_identity_when_confirmed(self):
        state = nova_profile_followups.infer_profile_conversation_state(
            "what do you know about me",
            normalize_turn_text_fn=lambda text: text.lower().strip(),
            evaluate_rule_state_fn=lambda text: {},
            speaker_matches_developer_fn=lambda: True,
            is_developer_color_lookup_request_fn=lambda text: False,
            is_developer_bilingual_request_fn=lambda text: False,
            is_color_lookup_request_fn=lambda text: False,
            make_conversation_state_fn=lambda kind, **data: {"kind": kind, **data},
        )

        self.assertEqual(state, {"kind": "developer_identity", "subject": "developer"})


if __name__ == "__main__":
    unittest.main()

