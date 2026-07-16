"""Tests for codegen to patch artifact bridge conversion."""

import json
import unittest
from unittest.mock import patch

from services.codegen_patch_bridge import (
    CODEGEN_PATCH_BRIDGE_SERVICE,
    bridge_codegen_to_patch,
    format_bridge_summary,
    validate_codegen_preview,
)


class TestCodegenPatchBridgeValidation(unittest.TestCase):
    """Test preview payload validation."""

    def test_validate_valid_preview(self):
        """Valid preview passes validation."""
        payload = {
            "schema": "nova.codegen.preview.v1",
            "status": "preview",
            "preview_only": True,
            "apply_allowed": False,
            "spec": {
                "name": "test_spec",
                "purpose": "Test purpose",
                "file_count": 1,
            },
            "artifacts": [
                {
                    "path": "services/test.py",
                    "kind": "service",
                    "intent": "Test service",
                    "content": "# test content",
                }
            ],
            "provenance": {
                "generator": "codegen_tool",
                "model": "qwen2.5:7b",
                "prompt_hash": "abc123",
            },
        }

        ok, reason, parsed = validate_codegen_preview(payload)
        self.assertTrue(ok)
        self.assertEqual(reason, "")
        self.assertEqual(parsed["spec"]["name"], "test_spec")

    def test_validate_rejects_invalid_schema(self):
        """Invalid schema is rejected."""
        payload = {
            "schema": "unknown.schema.v1",
            "status": "preview",
            "preview_only": True,
            "apply_allowed": False,
        }
        ok, reason, _ = validate_codegen_preview(payload)
        self.assertFalse(ok)
        self.assertEqual(reason, "unknown_schema")

    def test_validate_rejects_non_preview(self):
        """Non-preview payloads are rejected."""
        payload = {
            "schema": "nova.codegen.preview.v1",
            "status": "complete",
            "preview_only": False,
            "apply_allowed": True,
        }
        ok, reason, _ = validate_codegen_preview(payload)
        self.assertFalse(ok)
        self.assertIn(reason, ["invalid_status", "not_preview_only", "apply_already_allowed"])

    def test_validate_rejects_missing_spec(self):
        """Missing spec is rejected."""
        payload = {
            "schema": "nova.codegen.preview.v1",
            "status": "preview",
            "preview_only": True,
            "apply_allowed": False,
        }
        ok, reason, _ = validate_codegen_preview(payload)
        self.assertFalse(ok)
        self.assertEqual(reason, "spec_missing")

    def test_validate_rejects_placeholder_artifacts(self):
        payload = {
            "schema": "nova.codegen.preview.v1",
            "status": "preview",
            "preview_only": True,
            "apply_allowed": False,
            "spec": {"name": "stub", "purpose": "stub", "file_count": 1},
            "artifacts": [
                {
                    "path": "services/stub.py",
                    "kind": "module",
                    "intent": "stub",
                    "content": (
                        '"""Preview-only artifact. Route through patch governance before apply."""\n'
                        "def build_preview() -> dict[str, str]:\n"
                        "    return {}\n"
                    ),
                }
            ],
            "provenance": {"generator": "codegen_tool"},
        }
        ok, reason, _ = validate_codegen_preview(payload)
        self.assertFalse(ok)
        self.assertEqual(reason, "artifact_0_placeholder")

    def test_validate_rejects_artifact_count_mismatch(self):
        """Artifact count must match spec count."""
        payload = {
            "schema": "nova.codegen.preview.v1",
            "status": "preview",
            "preview_only": True,
            "apply_allowed": False,
            "spec": {
                "name": "test",
                "purpose": "test",
                "file_count": 2,
            },
            "artifacts": [
                {"path": "one.py", "content": "# one"}
            ],
            "provenance": {"generator": "codegen_tool"},
        }
        ok, reason, _ = validate_codegen_preview(payload)
        self.assertFalse(ok)
        self.assertEqual(reason, "artifacts_mismatch")


class TestCodegenPatchBridgeConversion(unittest.TestCase):
    """Test preview to patch artifact conversion."""

    def setUp(self):
        self.valid_preview = {
            "schema": "nova.codegen.preview.v1",
            "status": "preview",
            "preview_only": True,
            "apply_allowed": False,
            "spec": {
                "name": "leah_v2",
                "purpose": "Add new assistant surface",
                "file_count": 2,
            },
            "artifacts": [
                {
                    "path": "services/leah_v2_service.py",
                    "kind": "service",
                    "intent": "Serve Leah v2",
                    "content": "# Leah service v2\nprint('leah')\n",
                },
                {
                    "path": "templates/leah_v2.html",
                    "kind": "template",
                    "intent": "Render Leah UI",
                    "content": "<html>Leah</html>\n",
                },
            ],
            "provenance": {
                "generator": "codegen_tool",
                "model": "qwen2.5:7b",
                "prompt_hash": "def456",
            },
        }

    def test_bridge_creates_valid_patch_artifact(self):
        """Bridge produces valid patch artifact record."""
        artifact = bridge_codegen_to_patch(self.valid_preview, codegen_id="run-123", operator_id="test-op")

        self.assertEqual(artifact["schema"], "nova.patch.artifact.v1")
        self.assertEqual(artifact["status"], "preview")
        self.assertTrue(artifact["patch_id"].startswith("codegen-leah_v2"))
        self.assertEqual(artifact["file_count"], 2)
        self.assertEqual(artifact["test_count"], 2)
        self.assertTrue(artifact["ready_for_behavioral_gate"])
        self.assertTrue(artifact["ready_for_patch_queue"])

    def test_bridge_generates_test_files(self):
        """Bridge generates behavioral test files."""
        artifact = bridge_codegen_to_patch(self.valid_preview)
        manifest = artifact.get("manifest") or {}
        tests = manifest.get("tests") or []

        self.assertEqual(len(tests), 2)
        for test in tests:
            self.assertTrue(test["path"].startswith("tests/test_"))
            self.assertTrue(test["path"].endswith("_generated.py"))
            self.assertGreater(test["content_length"], 0)
            self.assertTrue(test["content_hash"])

    def test_bridge_preserves_spec_metadata(self):
        """Bridge preserves original spec metadata."""
        artifact = bridge_codegen_to_patch(self.valid_preview)
        spec_source = artifact["spec_source"]

        self.assertEqual(spec_source["type"], "codegen")
        self.assertEqual(spec_source["spec_name"], "leah_v2")
        self.assertEqual(spec_source["spec_purpose"], "Add new assistant surface")
        self.assertEqual(spec_source["spec_file_count"], 2)

    def test_bridge_captures_provenance(self):
        """Bridge captures full provenance chain."""
        artifact = bridge_codegen_to_patch(
            self.valid_preview,
            codegen_id="gen-run-xyz",
            operator_id="alice",
        )
        provenance = artifact["provenance"]

        self.assertEqual(provenance["generator"], "codegen_tool")
        self.assertEqual(provenance["model"], "qwen2.5:7b")
        self.assertEqual(provenance["prompt_hash"], "def456")
        self.assertEqual(provenance["bridge_operator"], "alice")
        self.assertTrue(provenance["bridge_ts"])

    def test_bridge_manifest_includes_governance_gates(self):
        """Bridge manifest includes governance requirements."""
        artifact = bridge_codegen_to_patch(self.valid_preview)
        manifest = artifact["manifest"]
        governance = manifest.get("governance") or {}

        self.assertTrue(governance.get("requires_behavioral_gate"))
        self.assertTrue(governance.get("requires_operator_approval"))
        self.assertTrue(governance.get("preview_only"))
        self.assertFalse(governance.get("apply_allowed"))


class TestCodegenPatchBridgeSummary(unittest.TestCase):
    """Test human-readable summary formatting."""

    def test_format_summary(self):
        """Summary format is clear and complete."""
        preview = {
            "schema": "nova.codegen.preview.v1",
            "status": "preview",
            "preview_only": True,
            "apply_allowed": False,
            "spec": {
                "name": "demo_feature",
                "purpose": "Demo feature implementation",
                "file_count": 3,
            },
            "artifacts": [
                {"path": "a.py", "kind": "module", "content": "# a"},
                {"path": "b.py", "kind": "module", "content": "# b"},
                {"path": "c.py", "kind": "module", "content": "# c"},
            ],
            "provenance": {"generator": "codegen_tool"},
        }

        artifact = bridge_codegen_to_patch(preview)
        summary = format_bridge_summary(preview, artifact)

        self.assertIn("Codegen Bridge Conversion Summary", summary)
        self.assertIn("demo_feature", summary)
        self.assertIn("Files:         3", summary)
        self.assertIn("Generated Tests: 3", summary)
        self.assertIn("behavioral gate validation", summary)

    def test_summary_is_readable(self):
        """Summary output is human-readable."""
        preview = {
            "schema": "nova.codegen.preview.v1",
            "status": "preview",
            "preview_only": True,
            "apply_allowed": False,
            "spec": {
                "name": "feature_x",
                "purpose": "Feature X description",
                "file_count": 1,
            },
            "artifacts": [
                {"path": "services/feature_x.py", "kind": "service", "content": "# Feature X"},
            ],
            "provenance": {"generator": "codegen_tool"},
        }

        artifact = bridge_codegen_to_patch(preview)
        summary = format_bridge_summary(preview, artifact)

        lines = [line for line in summary.split("\n") if line.strip()]
        self.assertGreater(len(lines), 3)
        for line in lines:
            self.assertTrue(any(c.isalnum() or c in " =:-_" for c in line))


class TestCodegenPatchBridgeService(unittest.TestCase):
    """Test the service singleton."""

    def test_service_exposes_all_methods(self):
        """Service singleton exposes public methods."""
        self.assertTrue(hasattr(CODEGEN_PATCH_BRIDGE_SERVICE, "validate_codegen_preview"))
        self.assertTrue(hasattr(CODEGEN_PATCH_BRIDGE_SERVICE, "bridge_codegen_to_patch"))
        self.assertTrue(hasattr(CODEGEN_PATCH_BRIDGE_SERVICE, "format_bridge_summary"))
        self.assertTrue(callable(CODEGEN_PATCH_BRIDGE_SERVICE.validate_codegen_preview))
        self.assertTrue(callable(CODEGEN_PATCH_BRIDGE_SERVICE.bridge_codegen_to_patch))
        self.assertTrue(callable(CODEGEN_PATCH_BRIDGE_SERVICE.format_bridge_summary))


if __name__ == "__main__":
    unittest.main()
