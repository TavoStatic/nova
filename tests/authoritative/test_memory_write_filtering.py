"""
Authoritative behavior tests — memory write filtering.

Tests that MemoryAdapterService.memory_should_keep_text correctly
filters input before anything reaches the memory store.
Does NOT inspect source code or depend on internal call patterns.
"""
from __future__ import annotations

import unittest

from services.memory_adapter import MemoryAdapterService


def _service(policy_overrides: dict | None = None) -> MemoryAdapterService:
    base = {"store_min_chars": 12, "enabled": True, "scope": "private"}
    if policy_overrides:
        base.update(policy_overrides)
    return MemoryAdapterService(
        policy_memory_getter=lambda: base,
        active_user_getter=lambda: "testuser",
    )


class TestMemoryWriteFiltering(unittest.TestCase):

    # --- Too short ---

    def test_text_below_min_chars_is_rejected(self):
        svc = _service({"store_min_chars": 20})
        keep, reason = svc.memory_should_keep_text("hi")
        self.assertFalse(keep)
        self.assertEqual(reason, "too_short")

    def test_text_with_durable_fact_marker_is_accepted(self):
        # Text containing a durable fact marker is kept regardless of word count
        svc = _service({"store_min_chars": 5})
        keep, reason = svc.memory_should_keep_text("my name is Alex")
        self.assertTrue(keep)
        self.assertEqual(reason, "durable_fact")

    def test_empty_text_is_rejected(self):
        svc = _service()
        keep, reason = svc.memory_should_keep_text("")
        self.assertFalse(keep)
        self.assertEqual(reason, "empty")

    # --- Questions ---

    def test_question_ending_with_mark_is_rejected(self):
        svc = _service({"store_min_chars": 2})
        keep, reason = svc.memory_should_keep_text("what is the weather?")
        self.assertFalse(keep)
        self.assertEqual(reason, "question")

    def test_question_starting_with_what_is_rejected(self):
        svc = _service({"store_min_chars": 2})
        keep, reason = svc.memory_should_keep_text("what time is it now")
        self.assertFalse(keep)
        self.assertEqual(reason, "question")

    def test_long_statement_eight_words_is_accepted(self):
        # 8+ word statements are kept as long_statement regardless of question word
        svc = _service({"store_min_chars": 2})
        keep, reason = svc.memory_should_keep_text("we went to the park several times last summer")
        self.assertTrue(keep)
        self.assertEqual(reason, "long_statement")

    # --- Ack/low-value ---

    def test_ack_ok_is_rejected(self):
        svc = _service({"store_min_chars": 1})
        keep, reason = svc.memory_should_keep_text("ok")
        self.assertFalse(keep)
        self.assertEqual(reason, "ack")

    def test_ack_thanks_is_rejected(self):
        svc = _service({"store_min_chars": 1})
        keep, reason = svc.memory_should_keep_text("thanks")
        self.assertFalse(keep)
        self.assertEqual(reason, "ack")

    # --- UI noise ---

    def test_ui_noise_nova_prefix_is_rejected(self):
        svc = _service({"store_min_chars": 2})
        keep, reason = svc.memory_should_keep_text("nova: checking the weather")
        self.assertFalse(keep)
        self.assertEqual(reason, "ui_noise")

    def test_ui_noise_assistant_prefix_is_rejected(self):
        svc = _service({"store_min_chars": 2})
        keep, reason = svc.memory_should_keep_text("assistant: here you go")
        self.assertFalse(keep)
        self.assertEqual(reason, "ui_noise")

    # --- Policy include patterns override ---

    def test_include_pattern_keeps_otherwise_low_signal_text(self):
        # Include patterns activate after the length/question/ack/noise checks.
        # Use text that passes the min_chars check but would otherwise be "low_signal".
        svc = _service({"store_include_patterns": ["bookmark this"], "store_min_chars": 5})
        keep, reason = svc.memory_should_keep_text("please bookmark this note")
        self.assertTrue(keep)
        self.assertEqual(reason, "policy_include")

    # --- Exclude patterns ---

    def test_exclude_pattern_rejects_matching_text(self):
        svc = _service({"store_exclude_patterns": [r"debug\s+trace"], "store_min_chars": 2})
        keep, reason = svc.memory_should_keep_text("debug trace output here")
        self.assertFalse(keep)
        self.assertEqual(reason, "policy_exclude")

    # --- store_min_chars from policy ---

    def test_default_min_chars_is_12(self):
        svc = _service({})
        self.assertEqual(svc.mem_store_min_chars(), 12)

    def test_min_chars_respects_policy(self):
        svc = _service({"store_min_chars": 30})
        self.assertEqual(svc.mem_store_min_chars(), 30)


if __name__ == "__main__":
    unittest.main()
