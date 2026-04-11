import unittest

from services import nova_developer_profile


class TestNovaDeveloperProfile(unittest.TestCase):
    def test_extract_work_role_parts_removes_confirmation_prefix(self):
        parts = nova_developer_profile.extract_work_role_parts(
            "yes you're right nova he is a full stack developer that works as PEIMS Data Specialist",
            strip_confirmation_prefix_fn=nova_developer_profile.strip_confirmation_prefix,
        )

        self.assertIn("full stack developer", parts)
        self.assertIn("PEIMS Data Specialist", parts)

    def test_learn_contextual_developer_facts_stores_colors_and_bilingual(self):
        writes = []
        learned, message = nova_developer_profile.learn_contextual_developer_facts(
            [("user", "What do you know about Gus?")],
            "favorite colors are silver, blue and red and he's bilingual in English and Spanish",
            normalize_turn_text_fn=lambda text: text.lower(),
            recent_turn_mentions_fn=lambda turns, keywords: True,
            mem_enabled_fn=lambda: True,
            mem_add_fn=lambda kind, source, text: writes.append((kind, source, text)),
            extract_color_preferences_from_text_fn=lambda text: ["silver", "blue", "red"],
            extract_work_role_parts_fn=lambda text: [],
            store_developer_role_facts_fn=lambda roles, input_source="typed": (False, ""),
            load_learned_facts_fn=lambda: {},
            save_learned_facts_fn=lambda data: None,
            timestamp_fn=lambda: "2026-04-04 19:00:00",
        )

        self.assertTrue(learned)
        self.assertIn("favorite colors", message.lower())
        self.assertIn("bilingual", message.lower())
        self.assertIn(("identity", "typed", "Gus is bilingual in English and Spanish."), writes)
        self.assertTrue(any(entry[2] == "Gus favorite colors are silver, blue, and red." for entry in writes))


if __name__ == "__main__":
    unittest.main()