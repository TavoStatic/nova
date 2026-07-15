import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from services.codegen_patch_bridge import bridge_codegen_to_patch, validate_codegen_preview
from services.governance_chain import (
    governed_patch_apply,
    release_rebuild_success,
    release_rebuild_tool_payload,
    run_codegen_to_patch_chain,
)


class TestGovernanceChain(unittest.TestCase):
    def test_release_rebuild_success_requires_package_verify(self):
        ok, reason = release_rebuild_success(
            {
                "artifact": r"C:\nova\runtime\exports\release_packages\pkg.zip",
                "steps": [
                    {"name": "repo_hygiene", "returncode": 0},
                    {"name": "smoke_runtime", "returncode": 0},
                    {"name": "package_build", "returncode": 0},
                    {"name": "package_verify", "returncode": 1},
                ],
            }
        )
        self.assertFalse(ok)
        self.assertIn("package_verify", reason)

    def test_release_rebuild_tool_payload_marks_missing_verify_failed(self):
        payload = release_rebuild_tool_payload(
            {
                "artifact": r"C:\nova\runtime\exports\release_packages\pkg.zip",
                "steps": [
                    {"name": "repo_hygiene", "returncode": 0},
                    {"name": "smoke_runtime", "returncode": 0},
                    {"name": "package_build", "returncode": 0},
                ],
            }
        )
        self.assertFalse(payload.get("ok"))
        self.assertIn("package_verify", str(payload.get("failure_reason") or ""))

    def test_governed_patch_apply_requires_approval_before_apply(self):
        preview_out = (
            "Patch Preview\nStatus: eligible\nPreview written: preview_a.txt\n"
        )
        outcome = governed_patch_apply(
            "updates/sample.zip",
            patch_preview_fn=lambda _path, _write_report=False: preview_out,
            preview_approved_fn=lambda _path: False,
            execute_patch_apply_fn=lambda *_args, **_kwargs: "should not run",
        )
        self.assertFalse(outcome.get("ok"))
        self.assertEqual(outcome.get("reason"), "preview_approval_missing")

    def test_governed_patch_apply_uses_non_admin_apply_path(self):
        preview_out = (
            "Patch Preview\nStatus: eligible\nPreview written: preview_a.txt\n"
        )
        captured: dict[str, object] = {}

        def _apply(action, value, **kwargs):
            captured.update({"action": action, "value": value, **kwargs})
            return "Patch applied."

        outcome = governed_patch_apply(
            "updates/sample.zip",
            patch_preview_fn=lambda _path, _write_report=False: preview_out,
            preview_approved_fn=lambda _path: True,
            execute_patch_apply_fn=_apply,
        )
        self.assertTrue(outcome.get("ok"))
        self.assertFalse(bool(captured.get("is_admin")))

    def test_run_codegen_to_patch_chain_materializes_zip(self):
        preview = {
            "schema": "nova.codegen.preview.v1",
            "status": "preview",
            "preview_only": True,
            "apply_allowed": False,
            "spec": {"name": "demo_cap", "purpose": "demo", "file_count": 1},
            "artifacts": [
                {
                    "path": "services/demo_cap.py",
                    "kind": "module",
                    "intent": "demo",
                    "content": (
                        '"""Generated module for demo_cap."""\n\n'
                        "from __future__ import annotations\n\n\n"
                        "class DemoCapService:\n"
                        "    def describe(self) -> dict[str, str]:\n"
                        "        return {'spec': 'demo_cap'}\n"
                    ),
                }
            ],
            "provenance": {"generator": "codegen_tool", "prompt_hash": "abc"},
        }
        ok, reason, parsed = validate_codegen_preview(preview)
        self.assertTrue(ok, reason)

        with tempfile.TemporaryDirectory() as tmp:
            updates = Path(tmp)
            chain = run_codegen_to_patch_chain(
                parsed,
                updates_dir=updates,
                current_revision=3,
                codegen_id="demo-1",
                operator_id="test",
            )
            self.assertTrue(chain.get("ok"))
            zip_path = Path(str(chain.get("zip_path") or ""))
            self.assertTrue(zip_path.exists())
            with zipfile.ZipFile(zip_path, "r") as archive:
                names = archive.namelist()
            self.assertIn("services/demo_cap.py", names)
            self.assertIn("nova_patch.json", names)
            self.assertTrue(any(name.startswith("tests/test_") for name in names))


if __name__ == "__main__":
    unittest.main()