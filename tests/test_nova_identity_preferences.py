import unittest

from services import nova_identity_preferences


class TestNovaIdentityPreferences(unittest.TestCase):
    def test_extract_color_preferences_finds_unique_colors(self):
        colors = nova_identity_preferences.extract_color_preferences(
            [("user", "I like blue and green and blue again")],
            known_colors={"blue", "green", "red"},
        )

        self.assertEqual(colors, ["blue", "green"])

    def test_extract_last_user_question_keeps_identity_lookups(self):
        question = nova_identity_preferences.extract_last_user_question(
            [
                ("user", "what colors do I like"),
                ("assistant", "I need more info."),
                ("user", "keep trying"),
            ],
            "keep trying",
            is_identity_or_developer_query_fn=lambda text: False,
            is_color_lookup_request_fn=lambda text: "colors do i like" in text.lower(),
            is_developer_color_lookup_request_fn=lambda text: False,
            is_developer_bilingual_request_fn=lambda text: False,
        )

        self.assertEqual(question, "what colors do I like")

    def test_pick_color_for_animals_prefers_bird_palette(self):
        best = nova_identity_preferences.pick_color_for_animals(["red", "brown"], ["birds"])
        self.assertEqual(best, "red")


if __name__ == "__main__":
    unittest.main()