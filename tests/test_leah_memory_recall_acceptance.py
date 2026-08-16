"""Acceptance tests for leah_memory_recall.

Covers:
- _query_warrants_recall() gate logic
- recall_for_turn() with enabled/disabled memory
- recall_from_recent_turns() scanning
- inject_into_message() formatting
- capability_registration()
- AT-5: recall failure never breaks a chat turn (graceful degradation)
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock


class TestQueryWarrantsRecall(unittest.TestCase):
    """_query_warrants_recall() gate logic."""

    def _recall(self, text: str) -> bool:
        from services.leah_memory_recall import _query_warrants_recall
        return _query_warrants_recall(text)

    def test_blank_does_not_warrant(self):
        self.assertFalse(self._recall(""))

    def test_short_query_does_not_warrant(self):
        self.assertFalse(self._recall("hi"))

    def test_status_cue_blocked(self):
        self.assertFalse(self._recall("what is the sync status"))

    def test_pipeline_cue_blocked(self):
        self.assertFalse(self._recall("is the pipeline healthy today"))

    def test_health_cue_blocked(self):
        self.assertFalse(self._recall("Nova health check"))

    def test_recall_cue_triggers(self):
        self.assertTrue(self._recall("what did we discuss last week about the schedule"))

    def test_remember_cue_triggers(self):
        self.assertTrue(self._recall("do you remember the sync window we set"))

    def test_earlier_cue_triggers(self):
        self.assertTrue(self._recall("you mentioned this earlier, what was it?"))

    def test_learned_from_me_triggers(self):
        self.assertTrue(self._recall("what have you learned from me about this project"))

    def test_pure_status_not_triggered_by_length(self):
        self.assertFalse(self._recall("sync status check for the pipeline queue this morning"))


class TestLeahMemoryRecallServiceDisabled(unittest.TestCase):
    """Service returns empty when memory is disabled or not wired."""

    def _make_service(self, enabled=False):
        from services.leah_memory_recall import LeahMemoryRecallService
        return LeahMemoryRecallService(
            mem_recall_fn=None if not enabled else MagicMock(return_value="remembered"),
            mem_enabled_fn=lambda: enabled,
        )

    def test_no_recall_when_disabled(self):
        svc = self._make_service(enabled=False)
        result = svc.recall_for_turn("what did we discuss earlier?")
        self.assertEqual(result, "")

    def test_no_recall_when_no_mem_fn(self):
        from services.leah_memory_recall import LeahMemoryRecallService
        svc = LeahMemoryRecallService(mem_recall_fn=None, mem_enabled_fn=lambda: True)
        result = svc.recall_for_turn("what did we discuss earlier?")
        self.assertEqual(result, "")

    def test_no_recall_when_enabled_fn_missing(self):
        from services.leah_memory_recall import LeahMemoryRecallService
        svc = LeahMemoryRecallService(
            mem_recall_fn=MagicMock(return_value="remembered"),
            mem_enabled_fn=None,
        )
        result = svc.recall_for_turn("what did we discuss earlier?")
        self.assertEqual(result, "")


class TestLeahMemoryRecallServiceEnabled(unittest.TestCase):
    """Service returns recall when enabled and query warrants it."""

    def _make_service(self, recall_return="recalled context"):
        from services.leah_memory_recall import LeahMemoryRecallService
        mem_fn = MagicMock(return_value=recall_return)
        svc = LeahMemoryRecallService(
            mem_recall_fn=mem_fn,
            mem_enabled_fn=lambda: True,
        )
        return svc, mem_fn

    def test_recall_fires_on_cue(self):
        svc, mem_fn = self._make_service()
        result = svc.recall_for_turn("what did we discuss last session?")
        self.assertEqual(result, "recalled context")
        mem_fn.assert_called_once()

    def test_no_recall_for_status_query(self):
        svc, mem_fn = self._make_service()
        result = svc.recall_for_turn("what is the sync status")
        self.assertEqual(result, "")
        mem_fn.assert_not_called()

    def test_mem_fn_exception_returns_empty(self):
        from services.leah_memory_recall import LeahMemoryRecallService
        svc = LeahMemoryRecallService(
            mem_recall_fn=MagicMock(side_effect=RuntimeError("mem broke")),
            mem_enabled_fn=lambda: True,
        )
        result = svc.recall_for_turn("what did we discuss earlier?")
        self.assertEqual(result, "")

    def test_recall_passes_purpose(self):
        svc, mem_fn = self._make_service()
        svc.recall_for_turn("what did we discuss?", purpose="leah_context")
        call_kwargs = mem_fn.call_args[1]
        self.assertEqual(call_kwargs.get("purpose"), "leah_context")


class TestRecallFromRecentTurns(unittest.TestCase):
    """recall_from_recent_turns() scans recent user turns."""

    def _make_service(self, recall_return="prior context"):
        from services.leah_memory_recall import LeahMemoryRecallService
        mem_fn = MagicMock(return_value=recall_return)
        svc = LeahMemoryRecallService(
            mem_recall_fn=mem_fn,
            mem_enabled_fn=lambda: True,
        )
        return svc

    def test_finds_recall_in_recent_user_turn(self):
        svc = self._make_service()
        turns = [
            ("user", "what did we discuss last week about deadlines?"),
            ("assistant", "We discussed setting the deadline for Friday."),
        ]
        result = svc.recall_from_recent_turns(turns)
        self.assertEqual(result, "prior context")

    def test_no_recall_from_assistant_only_turns(self):
        svc = self._make_service()
        turns = [
            ("assistant", "The sync completed successfully."),
        ]
        result = svc.recall_from_recent_turns(turns)
        self.assertEqual(result, "")

    def test_empty_turns_returns_empty(self):
        svc = self._make_service()
        result = svc.recall_from_recent_turns([])
        self.assertEqual(result, "")

    def test_returns_empty_when_disabled(self):
        from services.leah_memory_recall import LeahMemoryRecallService
        svc = LeahMemoryRecallService(
            mem_recall_fn=MagicMock(return_value="x"),
            mem_enabled_fn=lambda: False,
        )
        turns = [("user", "what did we talk about earlier?")]
        result = svc.recall_from_recent_turns(turns)
        self.assertEqual(result, "")


class TestInjectIntoMessage(unittest.TestCase):
    """inject_into_message() formats recall context correctly."""

    def _svc(self):
        from services.leah_memory_recall import LeahMemoryRecallService
        return LeahMemoryRecallService()

    def test_no_inject_when_empty_context(self):
        svc = self._svc()
        result = svc.inject_into_message("what is the status?", "")
        self.assertEqual(result, "what is the status?")

    def test_inject_prepends_block(self):
        svc = self._svc()
        result = svc.inject_into_message("what is the status?", "you set the sync window to 3am")
        self.assertIn("[LEAH memory context]", result)
        self.assertIn("you set the sync window to 3am", result)
        self.assertIn("what is the status?", result)
        # context block must precede original message
        self.assertLess(result.index("[LEAH memory context]"), result.index("what is the status?"))

    def test_original_message_unchanged_when_no_context(self):
        svc = self._svc()
        msg = "show me the pipeline queue"
        self.assertEqual(svc.inject_into_message(msg, None), msg)
        self.assertEqual(svc.inject_into_message(msg, "   "), msg)


class TestAT5RecallFailureDoesNotBreakChat(unittest.TestCase):
    """AT-5: recall_for_turn() exception must never propagate to the caller."""

    def test_exception_in_enabled_fn_returns_empty(self):
        from services.leah_memory_recall import LeahMemoryRecallService
        svc = LeahMemoryRecallService(
            mem_recall_fn=MagicMock(return_value="x"),
            mem_enabled_fn=MagicMock(side_effect=RuntimeError("enabled check exploded")),
        )
        result = svc.recall_for_turn("what did we discuss earlier?")
        self.assertEqual(result, "")

    def test_exception_in_mem_fn_returns_empty(self):
        from services.leah_memory_recall import LeahMemoryRecallService
        svc = LeahMemoryRecallService(
            mem_recall_fn=MagicMock(side_effect=Exception("mem service down")),
            mem_enabled_fn=lambda: True,
        )
        result = svc.recall_for_turn("what did we discuss earlier?")
        self.assertEqual(result, "")


class TestCapabilityRegistration(unittest.TestCase):
    """Capability registration returns correct key."""

    def test_registration_key(self):
        from services.leah_memory_recall import capability_registration
        reg = capability_registration()
        self.assertIn("leah_memory_recall", reg)
        self.assertTrue(reg["leah_memory_recall"])


if __name__ == "__main__":
    unittest.main()
