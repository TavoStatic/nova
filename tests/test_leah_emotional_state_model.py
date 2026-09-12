"""Unit tests for services.leah_emotional_state_model."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from services.cognitive_workspace import current_workspace
from services.leah_emotional_state_model import (
    CAPABILITY_DESCRIPTION,
    CAPABILITY_NAME,
    EmotionalState,
    LEAH_EMOTIONAL_STATE_MODEL_SERVICE,
    LeahEmotionalStateModelService,
    derive_emotion_instruction,
    derive_primary_emotion,
)


class TestLeahEmotionalStateModel(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.state_path = Path(self.tmp_dir.name) / "leah_emotional_state.json"
        self.service = LeahEmotionalStateModelService(state_path=self.state_path)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_capability_metadata(self):
        self.assertEqual(CAPABILITY_NAME, "leah_emotional_state_model")
        self.assertEqual(
            CAPABILITY_DESCRIPTION,
            "Leah can track a simple emotional state model for replies",
        )

    def test_initial_state(self):
        state = self.service.get_state()
        self.assertEqual(state.valence, 0.0)
        self.assertEqual(state.arousal, 0.3)
        self.assertEqual(state.confidence, 0.8)
        self.assertEqual(state.primary_emotion, "neutral")
        self.assertEqual(state.turn_count, 0)

    def test_analyze_positive_text_signals(self):
        deltas = self.service.analyze_text_signals("Thanks! That is awesome and helpful.")
        self.assertGreater(deltas["valence_delta"], 0.0)
        self.assertGreater(deltas["arousal_delta"], 0.0)

    def test_analyze_negative_text_signals(self):
        deltas = self.service.analyze_text_signals("Error and failure, broken bug and issue.")
        self.assertLess(deltas["valence_delta"], 0.0)
        self.assertGreater(deltas["arousal_delta"], 0.0)

    def test_analyze_curiosity_signals(self):
        deltas = self.service.analyze_text_signals("Why and how does this work? I am curious.")
        self.assertGreater(deltas["arousal_delta"], 0.0)

    def test_analyze_focus_signals(self):
        deltas = self.service.analyze_text_signals("Let's review the code, function, test, and class.")
        self.assertGreater(deltas["confidence_delta"], 0.0)

    def test_update_state_positive(self):
        initial = self.service.get_state()
        updated = self.service.update_state("Thank you so much! Excellent work.")
        self.assertGreater(updated.valence, initial.valence)
        self.assertEqual(updated.turn_count, 1)

    def test_update_state_negative(self):
        initial = self.service.get_state()
        updated = self.service.update_state("Error crash broken failure bug!")
        self.assertLess(updated.valence, initial.valence)
        self.assertEqual(updated.turn_count, 1)

    def test_state_decay_on_neutral_text(self):
        self.service.update_state("Error crash broken failure bug!")
        state1 = self.service.get_state()
        self.assertLess(state1.valence, 0.0)

        # Neutral text triggers decay back toward baseline 0.0
        self.service.update_state("plain text statement")
        state2 = self.service.get_state()
        self.assertGreater(state2.valence, state1.valence)

    def test_derive_primary_emotion(self):
        self.assertEqual(derive_primary_emotion(-0.5, 0.7, 0.5), "empathetic")
        self.assertEqual(derive_primary_emotion(-0.5, 0.3, 0.5), "reassuring")
        self.assertEqual(derive_primary_emotion(0.5, 0.7, 0.5), "encouraging")
        self.assertEqual(derive_primary_emotion(0.5, 0.3, 0.5), "friendly")
        self.assertEqual(derive_primary_emotion(0.0, 0.8, 0.5), "curious")
        self.assertEqual(derive_primary_emotion(0.0, 0.3, 0.9), "focused")
        self.assertEqual(derive_primary_emotion(0.0, 0.3, 0.5), "thoughtful")

    def test_derive_emotion_instruction(self):
        state = EmotionalState(primary_emotion="empathetic")
        instruction = derive_emotion_instruction(state)
        self.assertIn("Empathetic and supportive", instruction)

        state2 = EmotionalState(primary_emotion="encouraging")
        instruction2 = derive_emotion_instruction(state2)
        self.assertIn("Encouraging and positive", instruction2)

    def test_get_instruction_enabled_disabled(self):
        self.service.set_enabled(True)
        self.assertTrue(self.service.is_enabled())
        self.assertIn("Emotional posture:", self.service.get_instruction())

        self.service.set_enabled(False)
        self.assertFalse(self.service.is_enabled())
        self.assertEqual(self.service.get_instruction(), "")

    def test_reset_state(self):
        self.service.update_state("Error broken fail!")
        self.assertNotEqual(self.service.get_state().turn_count, 0)

        reset_state = self.service.reset_state()
        self.assertEqual(reset_state.turn_count, 0)
        self.assertEqual(reset_state.valence, 0.0)

    def test_save_and_load_state(self):
        self.service.update_state("Awesome job!")
        saved = self.service.get_state()

        new_service = LeahEmotionalStateModelService(state_path=self.state_path)
        loaded = new_service.get_state()

        self.assertEqual(loaded.turn_count, saved.turn_count)
        self.assertAlmostEqual(loaded.valence, saved.valence, places=2)

    def test_syncs_with_cognitive_workspace(self):
        self.service.update_state("Great work on the code!")
        ws = current_workspace()
        self.assertIn("valence", ws.emotional_equivalents)
        self.assertIn("arousal", ws.emotional_equivalents)

    def test_global_service_instance_exists(self):
        self.assertIsNotNone(LEAH_EMOTIONAL_STATE_MODEL_SERVICE)
        self.assertTrue(hasattr(LEAH_EMOTIONAL_STATE_MODEL_SERVICE, "update_state"))


if __name__ == "__main__":
    unittest.main()
