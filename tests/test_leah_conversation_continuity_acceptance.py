"""Acceptance tests for leah_conversation_continuity — Phase C validation.

Covers AT-1 through AT-4 from docs/LEAH_INSTANCE_PROFILE.md.
All four must pass before the capability is considered validated in real usage.
"""

from __future__ import annotations

import json
import time
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


class TestAT1TurnRecoveryAfterReload(unittest.TestCase):
    """AT-1: Turn recovery after reload.

    Simulate: operator sends turns → process memory is cleared (reload)
    → next call to get_session_turns recovers turns from disk.
    """

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.store_root = Path(self.tmpdir.name)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_turns_survive_memory_clear(self):
        from services.leah_conversation_continuity import LeahConversationContinuityStore
        store = LeahConversationContinuityStore(root=self.store_root)
        session = "session_reload_test"

        # Operator sends two turns — record them
        turns = [("user", "what is the sync status?"), ("assistant", "Last sync completed 4 minutes ago.")]
        store.record_turns(session, turns)

        # Simulate reload — new store instance (memory gone, disk remains)
        store2 = LeahConversationContinuityStore(root=self.store_root)
        recovered = store2.load_turns(session)

        self.assertEqual(len(recovered), 2)
        self.assertEqual(recovered[0], ("user", "what is the sync status?"))
        self.assertEqual(recovered[1], ("assistant", "Last sync completed 4 minutes ago."))

    def test_recovered_turns_are_in_order(self):
        from services.leah_conversation_continuity import LeahConversationContinuityStore
        store = LeahConversationContinuityStore(root=self.store_root)
        session = "session_order_test"

        turns = [
            ("user", "first message"),
            ("assistant", "first reply"),
            ("user", "second message"),
            ("assistant", "second reply"),
        ]
        store.record_turns(session, turns)

        store2 = LeahConversationContinuityStore(root=self.store_root)
        recovered = store2.load_turns(session)

        self.assertEqual(len(recovered), 4)
        for i, (role, text) in enumerate(turns):
            self.assertEqual(recovered[i][0], role)
            self.assertEqual(recovered[i][1], text)


class TestAT2AttachmentContextSurvival(unittest.TestCase):
    """AT-2: Attachment context survives navigation within TTL.

    Simulate: operator stages a file → navigates away (new request)
    → returns and asks about the file → context is recovered.
    """

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.store_root = Path(self.tmpdir.name) / "sessions"
        self.upload_root = Path(self.tmpdir.name) / "uploads"

    def tearDown(self):
        self.tmpdir.cleanup()

    def _make_frontdoor(self):
        from services.leah_conversation_continuity import LeahConversationContinuityStore
        from services.leah_frontdoor import LeahFrontdoorService

        store = LeahConversationContinuityStore(root=self.store_root)

        class _FakeAssets:
            def read_asset_text(self, path):
                return ""
            def asset_version_token(self, path):
                return "test"

        return LeahFrontdoorService(
            asset_service=_FakeAssets(),
            template_path_provider=lambda: Path("/nonexistent/leah.html"),
            css_path_provider=lambda: Path("/nonexistent/leah.css"),
            js_path_provider=lambda: Path("/nonexistent/leah.js"),
            upload_root_provider=lambda: self.upload_root,
            continuity_store=store,
        )

    def test_staged_items_recovered_after_navigation(self):
        svc = self._make_frontdoor()
        session = "session_attach_test"
        items = [{"name": "report.pdf", "bytes": 1024, "mime": "application/pdf", "source": "upload", "path": "/tmp/report.pdf"}]

        svc.remember_session_context(session, items, stage="staged")

        # Simulate navigation: new frontdoor instance but same continuity store
        svc2 = self._make_frontdoor()
        recovered_items, stage = svc2.recent_session_context(session)

        self.assertEqual(len(recovered_items), 1)
        self.assertEqual(recovered_items[0]["name"], "report.pdf")
        self.assertEqual(stage, "staged")

    def test_attachment_expired_after_ttl(self):
        from services.leah_conversation_continuity import LeahConversationContinuityStore
        # TTL is clamped to min 60s by the constructor — use a ts older than 60s
        store = LeahConversationContinuityStore(root=self.store_root)
        session = "session_ttl_test"

        payload = {
            "ts": time.time() - 3700,  # over an hour ago → expired (default 30min TTL)
            "stage": "staged",
            "items": [{"name": "old.pdf"}],
        }
        store.save(session, payload)

        # Should return None since attachment expired and no turns to keep
        loaded = store.load(session)
        self.assertIsNone(loaded)


class TestAT3NoCrossSessionBleed(unittest.TestCase):
    """AT-3: No cross-session bleed.

    Different session IDs must never share turn history.
    """

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.store_root = Path(self.tmpdir.name)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_session_a_turns_not_visible_to_session_b(self):
        from services.leah_conversation_continuity import LeahConversationContinuityStore
        store = LeahConversationContinuityStore(root=self.store_root)

        store.record_turns("session_A", [("user", "only session A should see this")])
        turns_b = store.load_turns("session_B")

        self.assertEqual(turns_b, [])

    def test_separate_session_files_on_disk(self):
        from services.leah_conversation_continuity import LeahConversationContinuityStore
        store = LeahConversationContinuityStore(root=self.store_root)

        store.record_turns("session_X", [("user", "message X")])
        store.record_turns("session_Y", [("user", "message Y")])

        path_x = store.session_path("session_X")
        path_y = store.session_path("session_Y")
        self.assertNotEqual(path_x, path_y)
        self.assertTrue(path_x.exists())
        self.assertTrue(path_y.exists())

        data_x = json.loads(path_x.read_text(encoding="utf-8"))
        data_y = json.loads(path_y.read_text(encoding="utf-8"))
        turns_x = [t["text"] for t in data_x.get("turns", [])]
        turns_y = [t["text"] for t in data_y.get("turns", [])]
        self.assertIn("message X", turns_x)
        self.assertNotIn("message X", turns_y)


class TestAT4ContinuityFailureDoesNotBreakChat(unittest.TestCase):
    """AT-4: Continuity failure must not break the chat turn.

    Missing directory, corrupt file, or any exception must degrade
    gracefully and return [] — never raise to the caller.
    """

    def test_missing_sessions_dir_returns_empty(self):
        from services.leah_conversation_continuity import LeahConversationContinuityStore
        store = LeahConversationContinuityStore(root=Path("/nonexistent/path/that/does/not/exist"))
        result = store.load_turns("any_session")
        self.assertEqual(result, [])

    def test_corrupt_session_file_returns_empty(self):
        import tempfile
        from services.leah_conversation_continuity import LeahConversationContinuityStore
        with tempfile.TemporaryDirectory() as d:
            store = LeahConversationContinuityStore(root=Path(d))
            # Write garbage to the session file
            path = store.session_path("corrupt_session")
            path.write_text("this is not json {{{{", encoding="utf-8")
            result = store.load_turns("corrupt_session")
            self.assertEqual(result, [])

    def test_empty_session_file_returns_empty(self):
        import tempfile
        from services.leah_conversation_continuity import LeahConversationContinuityStore
        with tempfile.TemporaryDirectory() as d:
            store = LeahConversationContinuityStore(root=Path(d))
            path = store.session_path("empty_session")
            path.write_text("", encoding="utf-8")
            result = store.load_turns("empty_session")
            self.assertEqual(result, [])

    def test_save_to_missing_dir_does_not_raise(self):
        from services.leah_conversation_continuity import LeahConversationContinuityStore
        # Root is a file path that can't be a directory — save must silently pass
        with tempfile.NamedTemporaryFile() as f:
            store = LeahConversationContinuityStore(root=Path(f.name) / "impossible_subdir")
            try:
                store.record_turns("x", [("user", "hello")])
            except Exception as exc:
                self.fail(f"record_turns raised an exception: {exc}")


class TestAT2PostNavigationStoreRecovery(unittest.TestCase):
    """AT-2 post-navigation path: handle_chat_request injects staged context from store
    when the browser sends no attachments (JS staged list cleared after navigation).

    This is the real-usage failure path confirmed in live testing 2026-08-15:
    upload wrote the file and store, but the next chat turn (after navigation) sent
    no attachments, so compose_chat_message was never called and Nova had no context.

    Fix: elif branch in nova_http_request_binding.handle_chat_request() — when no live
    attachments, call recent_session_context() and compose if store has items.
    """

    def _make_chat_request(self, *, store_items=None, store_stage="staged"):
        """Call handle_chat_request with no live attachments, return the message that
        was passed to process_chat_fn."""
        from services.nova_http_request_binding import NovaHttpRequestBindingService

        captured = {}

        def fake_process_chat(session_id, message, user_id=""):
            captured["message"] = message
            return "ok"

        attachment_svc = MagicMock()
        attachment_svc.recent_session_context.return_value = (
            list(store_items or []),
            store_stage,
        )
        attachment_svc.compose_chat_message.side_effect = lambda msg, items: (
            msg + "\n[LEAH session context]\n" + ", ".join(i.get("name", "") for i in items)
        )

        handler = MagicMock()
        code, body = NovaHttpRequestBindingService.handle_chat_request(
            handler=handler,
            qs={},
            payload={"message": "what about the file I just uploaded?", "session_id": "nav_test"},
            chat_login_auth_fn=lambda h: (True, "operator"),
            normalize_user_id_fn=lambda u: u,
            request_user_id_fn=lambda h, q, p: "operator",
            assert_session_owner_fn=lambda s, u, allow_bind=False: (True, ""),
            process_chat_fn=fake_process_chat,
            invalidate_control_status_cache_fn=lambda: None,
            token_hex_fn=lambda n: "abc123",
            attachment_context_service=attachment_svc,
            append_session_turn_fn=None,
            memory_recall_service=None,
        )
        return code, body, captured, attachment_svc

    def test_no_live_attachments_but_store_has_items_injects_context(self):
        """After navigation: no attachments in payload, but store has staged items.
        Expect compose_chat_message called with recovered items."""
        store_items = [{"name": "warehouse-label.txt", "bytes": 512, "mime": "text/plain"}]
        code, body, captured, svc = self._make_chat_request(store_items=store_items)

        self.assertEqual(code, 200)
        svc.recent_session_context.assert_called_once_with("nav_test")
        svc.compose_chat_message.assert_called_once()
        self.assertIn("warehouse-label.txt", captured.get("message", ""))

    def test_no_live_attachments_empty_store_does_not_inject(self):
        """No attachments, empty store — compose_chat_message must not be called."""
        code, body, captured, svc = self._make_chat_request(store_items=[])

        self.assertEqual(code, 200)
        svc.recent_session_context.assert_called_once_with("nav_test")
        svc.compose_chat_message.assert_not_called()
        self.assertNotIn("[LEAH session context]", captured.get("message", ""))

    def test_store_exception_does_not_break_chat(self):
        """If recent_session_context raises, chat turn must still return 200."""
        from services.nova_http_request_binding import NovaHttpRequestBindingService

        attachment_svc = MagicMock()
        attachment_svc.recent_session_context.side_effect = RuntimeError("store exploded")

        handler = MagicMock()
        code, body, *_ = NovaHttpRequestBindingService.handle_chat_request(
            handler=handler,
            qs={},
            payload={"message": "anything", "session_id": "err_test"},
            chat_login_auth_fn=lambda h: (True, "operator"),
            normalize_user_id_fn=lambda u: u,
            request_user_id_fn=lambda h, q, p: "operator",
            assert_session_owner_fn=lambda s, u, allow_bind=False: (True, ""),
            process_chat_fn=lambda s, m, user_id="": "ok",
            invalidate_control_status_cache_fn=lambda: None,
            token_hex_fn=lambda n: "abc123",
            attachment_context_service=attachment_svc,
            append_session_turn_fn=None,
            memory_recall_service=None,
        )
        self.assertEqual(code, 200)


class TestCapabilityRegistration(unittest.TestCase):
    """Verify the capability registers its name correctly."""

    def test_capability_name_registered(self):
        from services.leah_conversation_continuity import capability_registration
        reg = capability_registration()
        self.assertIn("leah_conversation_continuity", reg)
        self.assertTrue(reg["leah_conversation_continuity"])


if __name__ == "__main__":
    unittest.main()
