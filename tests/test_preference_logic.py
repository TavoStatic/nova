import unittest

import nova_core


class TestPreferenceLogic(unittest.TestCase):
    def setUp(self):
        self.orig_mem_enabled = nova_core.mem_enabled
        self.orig_mem_recall = nova_core.mem_recall
        self.orig_color_mem = nova_core._extract_color_preferences_from_memory
        self.orig_animal_mem = nova_core._extract_animal_preferences_from_memory

    def tearDown(self):
        nova_core.mem_enabled = self.orig_mem_enabled
        nova_core.mem_recall = self.orig_mem_recall
        nova_core._extract_color_preferences_from_memory = self.orig_color_mem
        nova_core._extract_animal_preferences_from_memory = self.orig_animal_mem

    def test_extract_color_preferences_from_session(self):
        turns = [
            ("user", "hello there"),
            ("user", "I like blue and green a lot."),
            ("assistant", "Noted."),
        ]
        prefs = nova_core._extract_color_preferences(turns)
        self.assertEqual(prefs, ["blue", "green"])

    def test_extract_animal_preferences_from_session_normalizes_plural(self):
        turns = [
            ("user", "I love dog and bird."),
        ]
        prefs = nova_core._extract_animal_preferences(turns)
        self.assertEqual(prefs, ["dogs", "birds"])

    def test_color_lookup_uses_session_first_then_memory_fallback(self):
        fallback_calls = {"n": 0}

        def fake_color_mem():
            fallback_calls["n"] += 1
            return ["red"]

        nova_core._extract_color_preferences_from_memory = fake_color_mem

        # Session has a preference, so fallback must not run.
        turns = [("user", "I prefer blue")]
        prefs = nova_core._extract_color_preferences(turns)
        if not prefs:
            prefs = nova_core._extract_color_preferences_from_memory()

        self.assertEqual(prefs, ["blue"])
        self.assertEqual(fallback_calls["n"], 0)

        # Session lacks a preference, so fallback should run.
        turns = [("user", "hello")]
        prefs = nova_core._extract_color_preferences(turns)
        if not prefs:
            prefs = nova_core._extract_color_preferences_from_memory()

        self.assertEqual(prefs, ["red"])
        self.assertEqual(fallback_calls["n"], 1)

    def test_animal_lookup_uses_session_first_then_memory_fallback(self):
        fallback_calls = {"n": 0}

        def fake_animal_mem():
            fallback_calls["n"] += 1
            return ["cats"]

        nova_core._extract_animal_preferences_from_memory = fake_animal_mem

        turns = [("user", "I like dogs")]
        animals = nova_core._extract_animal_preferences(turns)
        if not animals:
            animals = nova_core._extract_animal_preferences_from_memory()

        self.assertEqual(animals, ["dogs"])
        self.assertEqual(fallback_calls["n"], 0)

        turns = [("user", "good morning")]
        animals = nova_core._extract_animal_preferences(turns)
        if not animals:
            animals = nova_core._extract_animal_preferences_from_memory()

        self.assertEqual(animals, ["cats"])
        self.assertEqual(fallback_calls["n"], 1)

    def test_color_animal_direct_answer_path(self):
        user_text = "What color best matches the animals I like?"
        self.assertTrue(nova_core._is_color_animal_match_question(user_text))

        colors = ["blue", "brown"]
        animals = ["birds"]
        best = nova_core._pick_color_for_animals(colors, animals)

        msg = f"Direct answer: {best} matches best with the animals you like ({', '.join(animals)})."
        if len(colors) > 1:
            msg += f" I considered your options: {', '.join(colors)}."

        self.assertIn("Direct answer:", msg)
        self.assertIn("birds", msg)
        self.assertEqual(best, "blue")

    def test_color_preferences_from_memory_probe(self):
        nova_core.mem_enabled = lambda: True
        nova_core.mem_recall = lambda q: "You said favorite color is yellow and black"
        prefs = nova_core._extract_color_preferences_from_memory()
        self.assertEqual(prefs, ["yellow", "black"])


if __name__ == "__main__":
    unittest.main()
