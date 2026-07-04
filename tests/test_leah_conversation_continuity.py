from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from services.leah_conversation_continuity import LeahConversationContinuityStore
from services.leah_frontdoor import LeahFrontdoorService


class _FakeAssetService:
    def read_asset_text(self, _path):
        return "<html></html>"

    def asset_version_token(self, _path):
        return "v1"


class TestLeahConversationContinuity(unittest.TestCase):
    def test_store_persists_and_reloads_session_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "leah_sessions"
            store = LeahConversationContinuityStore(root=root, ttl_seconds=3600)
            store.save(
                "session-1",
                {"stage": "staged", "items": [{"name": "note.txt", "kind": "text"}]},
            )
            loaded = store.load("session-1")
            self.assertIsInstance(loaded, dict)
            self.assertEqual(loaded.get("stage"), "staged")
            self.assertEqual(len(loaded.get("items") or []), 1)

    def test_frontdoor_recovers_context_from_continuity_store(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "leah_sessions"
            store = LeahConversationContinuityStore(root=root, ttl_seconds=3600)
            store.save(
                "abc",
                {"stage": "handoff", "items": [{"name": "scan.png", "kind": "image"}]},
            )
            service = LeahFrontdoorService(
                asset_service=_FakeAssetService(),
                template_path_provider=lambda: Path("template.html"),
                css_path_provider=lambda: Path("leah.css"),
                js_path_provider=lambda: Path("leah.js"),
                upload_root_provider=lambda: Path(tmp) / "uploads",
                continuity_store=store,
            )
            items, stage = service.recent_session_context("abc")
            self.assertEqual(stage, "handoff")
            self.assertEqual(len(items), 1)

    def test_remember_writes_through_to_store(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "leah_sessions"
            store = LeahConversationContinuityStore(root=root, ttl_seconds=3600)
            service = LeahFrontdoorService(
                asset_service=_FakeAssetService(),
                template_path_provider=lambda: Path("template.html"),
                css_path_provider=lambda: Path("leah.css"),
                js_path_provider=lambda: Path("leah.js"),
                upload_root_provider=lambda: Path(tmp) / "uploads",
                continuity_store=store,
            )
            service.remember_session_context(
                "sess-9",
                [{"name": "brief.md", "kind": "text", "text_excerpt": "hello"}],
                stage="staged",
            )
            path = root / "sess-9.json"
            self.assertTrue(path.exists())
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(saved.get("stage"), "staged")


if __name__ == "__main__":
    unittest.main()