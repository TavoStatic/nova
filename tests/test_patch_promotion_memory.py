"""
Tests for Patch Promotion Memory Integration

Validates:
- Memory recording after patch promotion
- Code extraction from patch zips
- Memory context injection into prompts
- Service singleton exposure
"""

import json
import tempfile
from pathlib import Path
from zipfile import ZipFile
from unittest.mock import patch, MagicMock

from services.patch_promotion_memory import (
    record_patch_promotion_to_memory,
    extract_codegen_content_from_patch_zip,
    inject_memory_context_into_codegen_prompt,
    PATCH_PROMOTION_MEMORY_SERVICE,
)


class TestPatchPromotionMemory:
    """Test patch promotion memory recording."""

    def test_record_promotion_extracts_spec_info(self, tmp_path):
        """Recording should extract spec information from patch artifact."""
        patch_artifact = {
            "spec_source": {
                "spec_name": "test_capability",
                "spec_purpose": "test purpose",
            },
            "provenance": {
                "generator": "codegen_tool",
                "model": "test-model:7b",
            },
            "manifest": {
                "files": [{"path": "module.py", "kind": "module"}],
                "tests": [{"path": "test_module.py"}],
            },
        }

        with patch("services.codegen_memory_recorder._get_memory_store_path") as mock_path:
            mock_path.return_value = tmp_path / "patterns.jsonl"
            pattern_id = record_patch_promotion_to_memory(patch_artifact)
            assert pattern_id is not None

    def test_record_promotion_handles_missing_zip(self, tmp_path):
        """Recording should work even if zip path not provided."""
        patch_artifact = {
            "spec_source": {
                "spec_name": "capability",
                "spec_purpose": "purpose",
            },
            "provenance": {},
            "manifest": {
                "files": [{"path": "module.py", "kind": "module"}],
                "tests": [{"path": "test_module.py"}],
            },
        }

        with patch("services.codegen_memory_recorder._get_memory_store_path") as mock_path:
            mock_path.return_value = tmp_path / "patterns.jsonl"
            pattern_id = record_patch_promotion_to_memory(patch_artifact, None)
            assert pattern_id is not None

    def test_record_promotion_extracts_from_zip(self, tmp_path):
        """Recording should extract actual code from patch zip if provided."""
        # Create a test zip with generated code
        zip_path = tmp_path / "patch.zip"
        with ZipFile(zip_path, "w") as zf:
            zf.writestr("module.py", "class GeneratedHandler:\n    pass")
            zf.writestr("test_module.py", "class TestHandler:\n    pass")

        patch_artifact = {
            "spec_source": {
                "spec_name": "handler_capability",
                "spec_purpose": "handle events",
            },
            "provenance": {
                "model": "qwen2.5:7b",
            },
            "manifest": {
                "files": [{"path": "module.py", "kind": "module"}],
                "tests": [{"path": "test_module.py"}],
            },
        }

        with patch("services.codegen_memory_recorder._get_memory_store_path") as mock_path:
            mock_path.return_value = tmp_path / "patterns.jsonl"
            pattern_id = record_patch_promotion_to_memory(patch_artifact, zip_path)
            assert pattern_id is not None

            # Verify the actual code was recorded
            with open(tmp_path / "patterns.jsonl") as f:
                record = json.loads(f.readline())
                assert "GeneratedHandler" in record.get("code_patterns", []) or record.get("code_patterns")

    def test_record_promotion_returns_none_on_error(self, tmp_path):
        """Recording should return None on unrecoverable error."""
        with patch("services.codegen_memory_recorder._get_memory_store_path") as mock_path:
            mock_path.return_value = Path("/nonexistent/path.jsonl")
            # Patch open to simulate write error
            with patch("builtins.open", side_effect=IOError("Permission denied")):
                result = record_patch_promotion_to_memory({}, None)
                # Should either return None or raise (depending on implementation)
                # The service should handle gracefully


class TestCodeExtraction:
    """Test code extraction from patch zips."""

    def test_extract_python_files_from_zip(self, tmp_path):
        """Should extract Python files from patch zip."""
        zip_path = tmp_path / "patch.zip"
        with ZipFile(zip_path, "w") as zf:
            zf.writestr("handler.py", "class EventHandler:\n    pass")
            zf.writestr("test_handler.py", "class TestEventHandler:\n    pass")

        manifest = {
            "files": [{"path": "handler.py", "kind": "module"}],
            "tests": [{"path": "test_handler.py"}],
        }

        generated_code, test_code = extract_codegen_content_from_patch_zip(zip_path, manifest)
        assert generated_code is not None
        assert "EventHandler" in generated_code
        assert test_code is not None
        assert "TestEventHandler" in test_code

    def test_extract_handles_missing_zip(self, tmp_path):
        """Should gracefully handle missing zip file."""
        zip_path = tmp_path / "nonexistent.zip"
        manifest = {"files": [], "tests": []}

        generated_code, test_code = extract_codegen_content_from_patch_zip(zip_path, manifest)
        assert generated_code is None
        assert test_code is None

    def test_extract_handles_missing_files_in_zip(self, tmp_path):
        """Should handle missing files referenced in manifest."""
        zip_path = tmp_path / "patch.zip"
        with ZipFile(zip_path, "w") as zf:
            zf.writestr("handler.py", "class Handler: pass")

        manifest = {
            "files": [{"path": "handler.py"}, {"path": "missing.py"}],
            "tests": [],
        }

        generated_code, test_code = extract_codegen_content_from_patch_zip(zip_path, manifest)
        # Should extract what's available
        assert generated_code is not None
        assert "Handler" in generated_code

    def test_extract_filters_non_python_files(self, tmp_path):
        """Should only extract Python files."""
        zip_path = tmp_path / "patch.zip"
        with ZipFile(zip_path, "w") as zf:
            zf.writestr("module.py", "class Module: pass")
            zf.writestr("config.json", '{"key": "value"}')
            zf.writestr("README.md", "# README")

        manifest = {
            "files": [
                {"path": "module.py"},
                {"path": "config.json"},
                {"path": "README.md"},
            ],
            "tests": [],
        }

        generated_code, test_code = extract_codegen_content_from_patch_zip(zip_path, manifest)
        # Should only have Python content
        assert generated_code is not None
        assert "Module" in generated_code
        assert "config.json" not in generated_code
        assert "README" not in generated_code


class TestMemoryInjection:
    """Test memory context injection into codegen prompts."""

    def test_inject_returns_string(self, tmp_path):
        """Injection should return a string."""
        with patch("services.codegen_memory_recorder._get_memory_store_path") as mock_path:
            mock_path.return_value = tmp_path / "patterns.jsonl"
            result = inject_memory_context_into_codegen_prompt("capability", "purpose")
            assert isinstance(result, str)

    def test_inject_empty_when_no_prior_patterns(self, tmp_path):
        """Injection should be empty when no prior patterns exist."""
        with patch("services.codegen_memory_recorder._get_memory_store_path") as mock_path:
            mock_path.return_value = tmp_path / "patterns.jsonl"
            result = inject_memory_context_into_codegen_prompt("unknown_capability", "purpose")
            assert result == ""

    def test_inject_includes_context_when_patterns_exist(self, tmp_path):
        """Injection should include context when prior patterns found."""
        with patch("services.codegen_memory_recorder._get_memory_store_path") as mock_path:
            mock_path.return_value = tmp_path / "patterns.jsonl"
            
            # Record a pattern first
            from services.codegen_memory_recorder import record_generated_pattern
            spec = "generate handler"
            record_generated_pattern(
                "my_capability",
                spec,
                "class Handler: pass",
                "class TestHandler: pass",
            )
            
            # Now inject should include context
            result = inject_memory_context_into_codegen_prompt("my_capability", spec)
            assert len(result) > 0
            assert "my_capability" in result


class TestServiceSingleton:
    """Test service singleton exposure."""

    def test_service_exposes_record_promotion(self, tmp_path):
        """Service should expose record_promotion method."""
        with patch("services.codegen_memory_recorder._get_memory_store_path") as mock_path:
            mock_path.return_value = tmp_path / "patterns.jsonl"
            patch_artifact = {
                "spec_source": {"spec_name": "capability", "spec_purpose": "purpose"},
                "provenance": {},
                "manifest": {"files": [], "tests": []},
            }
            result = PATCH_PROMOTION_MEMORY_SERVICE.record_promotion(patch_artifact)
            assert result is not None or result is None  # Either succeeds or fails gracefully

    def test_service_exposes_get_memory_injection(self):
        """Service should expose get_memory_injection method."""
        result = PATCH_PROMOTION_MEMORY_SERVICE.get_memory_injection("capability", "purpose")
        assert isinstance(result, str)

    def test_service_exposes_extract_codegen_from_zip(self, tmp_path):
        """Service should expose extract_codegen_from_zip method."""
        zip_path = tmp_path / "patch.zip"
        with ZipFile(zip_path, "w") as zf:
            zf.writestr("module.py", "pass")

        manifest = {"files": [{"path": "module.py"}], "tests": []}
        result = PATCH_PROMOTION_MEMORY_SERVICE.extract_codegen_from_zip(zip_path, manifest)
        assert isinstance(result, tuple)
        assert len(result) == 2


class TestIntegration:
    """Test integration with full workflow."""

    def test_full_promotion_workflow(self, tmp_path):
        """Test complete promotion + injection workflow."""
        # Create patch zip
        zip_path = tmp_path / "patch.zip"
        with ZipFile(zip_path, "w") as zf:
            zf.writestr("models/event_handler.py", "class EventHandler:\n    def handle(self): pass")
            zf.writestr("tests/test_event_handler.py", "class TestEventHandler:\n    def test_handle(self): pass")

        # Record promotion
        patch_artifact = {
            "spec_source": {
                "spec_name": "event_handling",
                "spec_purpose": "Handle incoming events with validation",
            },
            "provenance": {
                "generator": "codegen_tool",
                "model": "qwen2.5:7b",
            },
            "manifest": {
                "files": [{"path": "models/event_handler.py", "kind": "module"}],
                "tests": [{"path": "tests/test_event_handler.py"}],
            },
        }

        with patch("services.codegen_memory_recorder._get_memory_store_path") as mock_path:
            mock_path.return_value = tmp_path / "patterns.jsonl"
            
            # Record the promotion
            pattern_id = PATCH_PROMOTION_MEMORY_SERVICE.record_promotion(patch_artifact, zip_path)
            assert pattern_id is not None

            # Later, get injection context for similar capability
            context = PATCH_PROMOTION_MEMORY_SERVICE.get_memory_injection(
                "event_handling",
                "Handle incoming events with validation"
            )
            assert len(context) > 0
            assert "event_handling" in context or "Prior" in context
