import unittest

from services import nova_session_followups


class TestNovaSessionFollowupsService(unittest.TestCase):
    def test_last_question_recall_reply_returns_last_question(self):
        reply, kind = nova_session_followups.last_question_recall_reply(
            "and what about now?",
            turns=[("user", "what is your name?"), ("assistant", "My name is Nova.")],
            extract_last_user_question_fn=lambda turns, current: "what is your name?",
        )
        self.assertEqual(kind, "recall")
        self.assertIn("what is your name?", reply)

    def test_session_fact_recall_reply_returns_value(self):
        reply, kind = nova_session_followups.session_fact_recall_reply(
            {"fact_target": "city", "fact_value": "Brownsville."}
        )
        self.assertEqual(kind, "city")
        self.assertEqual(reply, "Brownsville")

    def test_session_recap_reply_summarizes_recent_user_turns(self):
        reply = nova_session_followups.session_recap_reply(
            [
                ("user", "What is your name?"),
                ("assistant", "My name is Nova."),
                ("user", "Tell me about Gus."),
                ("user", "recap"),
            ],
            "recap",
            is_session_recap_request_fn=lambda text: text.strip().lower() == "recap",
        )
        self.assertIn("Recap of this session so far:", reply)
        self.assertIn("What is your name?", reply)
        self.assertIn("Tell me about Gus.", reply)

    def test_build_session_fact_sheet_collects_identity_location_and_preferences(self):
        reply = nova_session_followups.build_session_fact_sheet(
            [("user", "my favorite color is teal"), ("user", "I like cats")],
            get_learned_fact_fn=lambda key, default="": {
                "assistant_name": "Nova",
                "developer_name": "Gustavo Uribe",
                "developer_nickname": "Gus",
                "developer_location_relation": "same_as_assistant",
            }.get(key, default),
            get_active_user_fn=lambda: "developer",
            get_name_origin_story_fn=lambda: "Named after a bright star.",
            get_saved_location_text_fn=lambda: "Brownsville, Texas",
            extract_color_preferences_fn=lambda _turns: ["teal"],
            extract_developer_color_preferences_fn=lambda _turns: ["blue"],
            extract_developer_color_preferences_from_memory_fn=lambda: [],
            developer_is_bilingual_fn=lambda _turns: True,
            developer_is_bilingual_from_memory_fn=lambda: None,
            extract_animal_preferences_fn=lambda _turns: ["cats"],
        )

        self.assertIn("Assistant name: Nova", reply)
        self.assertIn("Stored runtime location label: Brownsville, Texas", reply)
        self.assertIn("Developer languages: English, Spanish", reply)
        self.assertIn("User-stated animal preferences: cats", reply)
