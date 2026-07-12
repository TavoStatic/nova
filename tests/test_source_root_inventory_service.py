from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from services.nova_root_inventory import build_source_root_inventory_payload
from services.nova_root_inventory import source_root_ids


class TestSourceRootInventoryService(unittest.TestCase):
    def test_source_inventory_prunes_ignored_directories_before_classifying_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "services").mkdir()
            (root / "services" / "nova_root_inventory.py").write_text("# inventory\n", encoding="utf-8")
            (root / "nova.cmd").write_text("@echo off\n", encoding="utf-8")
            (root / "NOVA_HEALTH_REVIEW.md").write_text("# Review\n", encoding="utf-8")
            for ignored in (".venv", "runtime", ".pytest_cache", "__pycache__", "logs", "terminals", ".vscode"):
                ignored_dir = root / ignored
                ignored_dir.mkdir()
                (ignored_dir / "test_shadow.py").write_text("def test_shadow(): pass\n", encoding="utf-8")

            payload = build_source_root_inventory_payload(root=root, wiring_surface_ids=source_root_ids())

        self.assertEqual(payload.get("source_file_count"), 3)
        covered = {
            path
            for row in payload.get("roots") or []
            for path in row.get("covered_source_files") or []
        }
        self.assertIn("services/nova_root_inventory.py", covered)
        self.assertIn("nova.cmd", covered)
        self.assertIn("NOVA_HEALTH_REVIEW.md", covered)
        self.assertFalse(any("test_shadow.py" in path for path in covered))
        self.assertFalse(any("test_shadow.py" in path for path in payload.get("unclassified_source_files") or []))

    def test_source_inventory_classifies_server_side_and_session_handoff_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scripts = root / "scripts"
            scripts.mkdir()
            (scripts / "nova_server_side.py").write_text("# server\n", encoding="utf-8")
            (scripts / "reverse_proxy_frontdoor.py").write_text("# proxy\n", encoding="utf-8")
            (root / "NYO-Nova-Autostart.ps1").write_text("# autostart\n", encoding="utf-8")
            updates = root / "updates"
            updates.mkdir()
            (updates / "approvals.jsonl").write_text("{}\n", encoding="utf-8")
            (root / "nova_grok.jsonl").write_text("{}\n", encoding="utf-8")

            payload = build_source_root_inventory_payload(root=root, wiring_surface_ids=source_root_ids())

        self.assertEqual(payload.get("unclassified_source_file_count"), 0)
        self.assertEqual(payload.get("unclassified_source_files"), [])
        covered = {
            path
            for row in payload.get("roots") or []
            for path in row.get("covered_source_files") or []
        }
        self.assertIn("scripts/nova_server_side.py", covered)
        self.assertIn("scripts/reverse_proxy_frontdoor.py", covered)
        self.assertIn("NYO-Nova-Autostart.ps1", covered)
        self.assertIn("updates/approvals.jsonl", covered)
        self.assertIn("nova_grok.jsonl", covered)

    def test_source_inventory_keeps_edfi_core_and_bisd_lane_separate(self) -> None:
        payload = build_source_root_inventory_payload()
        roots = {row["root_id"]: set(row.get("covered_source_files") or []) for row in payload.get("roots") or []}

        core_paths = {path for path in roots.get("edfi_core", set()) if "edfi" in path.lower()}
        lane_paths = {path for path in roots.get("data_lane_edfi_bisd", set()) if "edfi" in path.lower()}

        self.assertTrue(any(path.startswith("services/edfi/") for path in core_paths))
        self.assertIn("tools/edfi_tool.py", core_paths)
        self.assertIn("data_sources/edfi_bisd/connector.py", lane_paths)
        self.assertIn("scripts/run_edfi_profile.py", lane_paths)
        self.assertIn("scripts/run_edfi_explore.py", lane_paths)
        self.assertFalse(any(path.startswith("services/edfi/") for path in lane_paths))
        self.assertFalse(any(path.startswith("data_sources/edfi_bisd/") for path in core_paths))

        unclassified_edfi = [
            path
            for path in payload.get("unclassified_source_files") or []
            if "edfi" in path.lower()
        ]
        self.assertEqual(unclassified_edfi, [])

    def test_source_inventory_ignores_vscode_tasks_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            vscode = root / ".vscode"
            vscode.mkdir()
            (vscode / "tasks.json").write_text("{}", encoding="utf-8")
            (root / "nova.cmd").write_text("@echo off\n", encoding="utf-8")

            payload = build_source_root_inventory_payload(root=root, wiring_surface_ids=source_root_ids())

        self.assertEqual(payload.get("unclassified_source_file_count"), 0)
        self.assertEqual(payload.get("unclassified_source_files"), [])
        self.assertNotIn(".vscode/tasks.json", list(payload.get("unclassified_source_files") or []))


if __name__ == "__main__":
    unittest.main()
