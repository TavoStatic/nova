"""
Tests for Codegen Self-Extension Memory Service

Validates:
- Pattern recording and persistence
- Capability-based lookups
- Spec-hash based lookups
- Pattern extraction from generated code
- Memory injection context building
- Service singleton exposure
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch, mock_open

import pytest

from services.codegen_memory_recorder import (
    record_generated_pattern,
    lookup_patterns_by_capability,
    lookup_patterns_by_spec,
    build_memory_injection_context,
    _compute_spec_hash,
    _extract_code_patterns,
    _extract_test_patterns,
    _format_pattern_context,
    CODEGEN_MEMORY_RECORDER_SERVICE,
)


class TestMemoryRecorderBasics:
    """Test basic recording and retrieval functions."""

    def test_compute_spec_hash_deterministic(self):
        """Spec hash should be deterministic for same input."""
        spec = "create a handler for xyz events"
        hash1 = _compute_spec_hash(spec)
        hash2 = _compute_spec_hash(spec)
        assert hash1 == hash2

    def test_compute_spec_hash_different_for_different_inputs(self):
        """Different specs should produce different hashes."""
        spec1 = "create a handler for xyz events"
        spec2 = "create a handler for abc events"
        hash1 = _compute_spec_hash(spec1)
        hash2 = _compute_spec_hash(spec2)
        assert hash1 != hash2

    def test_extract_code_patterns_finds_classes(self):
        """Extract code patterns should identify class definitions."""
        code = """
class EventHandler:
    pass

class DataProcessor:
    pass
"""
        patterns = _extract_code_patterns(code, "python")
        assert any("EventHandler" in p for p in patterns)
        assert any("DataProcessor" in p for p in patterns)

    def test_extract_code_patterns_finds_functions(self):
        """Extract code patterns should identify function definitions."""
        code = """
def process_event(event):
    pass

def validate_input(data):
    pass
"""
        patterns = _extract_code_patterns(code, "python")
        assert "def process_event" in patterns
        assert "def validate_input" in patterns

    def test_extract_code_patterns_finds_exception_handling(self):
        """Extract code patterns should identify exception handling."""
        code = """
try:
    do_something()
except ValueError:
    handle_error()
except KeyError:
    handle_other_error()
"""
        patterns = _extract_code_patterns(code, "python")
        assert "exception_handling" in patterns

    def test_extract_code_patterns_finds_imports(self):
        """Extract code patterns should identify imports."""
        code = """
import json
from pathlib import Path
from typing import List
"""
        patterns = _extract_code_patterns(code, "python")
        assert any("import json" in p for p in patterns)
        assert any("from pathlib" in p for p in patterns)

    def test_extract_code_patterns_deduplicates(self):
        """Extract code patterns should deduplicate repeated patterns."""
        code = """
import json
import json
import json
"""
        patterns = _extract_code_patterns(code, "python")
        import_count = sum(1 for p in patterns if "import json" in p)
        assert import_count == 1

    def test_extract_test_patterns_finds_test_classes(self):
        """Extract test patterns should identify test classes."""
        test_code = """
class TestEventHandler:
    pass

class TestDataValidator:
    pass
"""
        patterns = _extract_test_patterns(test_code, "python")
        assert any("TestEventHandler" in p for p in patterns)
        assert any("TestDataValidator" in p for p in patterns)

    def test_extract_test_patterns_finds_test_methods(self):
        """Extract test patterns should identify test methods."""
        test_code = """
class TestHandler:
    def test_process_valid_input(self):
        pass
    
    def test_reject_invalid_input(self):
        pass
"""
        patterns = _extract_test_patterns(test_code, "python")
        assert "test_process_valid_input" in patterns
        assert "test_reject_invalid_input" in patterns

    def test_extract_test_patterns_finds_assertions(self):
        """Extract test patterns should identify assertion usage."""
        test_code = """
def test_something():
    assert result == expected
    self.assertEqual(a, b)
"""
        patterns = _extract_test_patterns(test_code, "python")
        assert "assertions" in patterns

    def test_extract_test_patterns_finds_mocking(self):
        """Extract test patterns should identify mocking."""
        test_code = """
@mock.patch('module.function')
def test_with_mock(self, mock_func):
    mock_func.return_value = 42
"""
        patterns = _extract_test_patterns(test_code, "python")
        assert "mocking" in patterns

    def test_extract_test_patterns_finds_setup_teardown(self):
        """Extract test patterns should identify setUp/tearDown."""
        test_code = """
class TestSuite:
    def setUp(self):
        self.fixture = create_fixture()
    
    def tearDown(self):
        cleanup()
"""
        patterns = _extract_test_patterns(test_code, "python")
        assert "setUp" in patterns
        assert "tearDown" in patterns


class TestMemoryRecording:
    """Test recording and retrieval of patterns."""

    def test_record_pattern_returns_pattern_id(self, tmp_path):
        """Recording a pattern should return a pattern ID."""
        with patch("services.codegen_memory_recorder._get_memory_store_path") as mock_path:
            mock_path.return_value = tmp_path / "patterns.jsonl"
            pattern_id = record_generated_pattern(
                "test_capability",
                "test spec",
                "class Handler: pass",
                "class TestHandler: pass",
            )
            assert pattern_id is not None
            assert len(pattern_id) > 0

    def test_record_pattern_creates_store_file(self, tmp_path):
        """Recording a pattern should create the store file."""
        with patch("services.codegen_memory_recorder._get_memory_store_path") as mock_path:
            mock_path.return_value = tmp_path / "patterns.jsonl"
            record_generated_pattern(
                "test_capability",
                "test spec",
                "class Handler: pass",
                "class TestHandler: pass",
            )
            assert (tmp_path / "patterns.jsonl").exists()

    def test_record_pattern_writes_valid_json(self, tmp_path):
        """Recorded pattern should be valid JSON."""
        with patch("services.codegen_memory_recorder._get_memory_store_path") as mock_path:
            mock_path.return_value = tmp_path / "patterns.jsonl"
            record_generated_pattern(
                "test_capability",
                "test spec",
                "class Handler: pass",
                "class TestHandler: pass",
            )
            with open(tmp_path / "patterns.jsonl") as f:
                line = f.readline()
                record = json.loads(line)
                assert record["capability_name"] == "test_capability"
                assert "id" in record
                assert "timestamp" in record

    def test_record_pattern_includes_patterns(self, tmp_path):
        """Recorded pattern should include extracted code and test patterns."""
        with patch("services.codegen_memory_recorder._get_memory_store_path") as mock_path:
            mock_path.return_value = tmp_path / "patterns.jsonl"
            record_generated_pattern(
                "test_capability",
                "test spec",
                "class Handler: pass",
                "class TestHandler: pass",
            )
            with open(tmp_path / "patterns.jsonl") as f:
                record = json.loads(f.readline())
                assert "code_patterns" in record
                assert "test_patterns" in record
                assert len(record["code_patterns"]) > 0
                assert len(record["test_patterns"]) > 0

    def test_record_pattern_stores_generation_context(self, tmp_path):
        """Recorded pattern should include generation context."""
        with patch("services.codegen_memory_recorder._get_memory_store_path") as mock_path:
            mock_path.return_value = tmp_path / "patterns.jsonl"
            record_generated_pattern(
                "test_capability",
                "test spec",
                "class Handler: pass",
                "class TestHandler: pass",
                tool_version="2.1",
                model_used="custom-model:7b",
            )
            with open(tmp_path / "patterns.jsonl") as f:
                record = json.loads(f.readline())
                assert record["generation_context"]["tool_version"] == "2.1"
                assert record["generation_context"]["model_used"] == "custom-model:7b"


class TestMemoryLookup:
    """Test pattern lookup functions."""

    def test_lookup_by_capability_returns_empty_when_no_store(self):
        """Lookup should return empty list when store doesn't exist."""
        with patch("services.codegen_memory_recorder._get_memory_store_path") as mock_path:
            mock_path.return_value = Path("/nonexistent/path.jsonl")
            patterns = lookup_patterns_by_capability("test_capability")
            assert patterns == []

    def test_lookup_by_capability_finds_matching_patterns(self, tmp_path):
        """Lookup by capability should find recorded patterns."""
        with patch("services.codegen_memory_recorder._get_memory_store_path") as mock_path:
            mock_path.return_value = tmp_path / "patterns.jsonl"
            # Record two patterns
            record_generated_pattern(
                "capability_a",
                "spec a",
                "class A: pass",
                "class TestA: pass",
            )
            record_generated_pattern(
                "capability_b",
                "spec b",
                "class B: pass",
                "class TestB: pass",
            )
            # Lookup should find capability_a
            patterns = lookup_patterns_by_capability("capability_a")
            assert len(patterns) == 1
            assert patterns[0]["capability_name"] == "capability_a"

    def test_lookup_by_capability_case_insensitive(self, tmp_path):
        """Lookup by capability should be case-insensitive."""
        with patch("services.codegen_memory_recorder._get_memory_store_path") as mock_path:
            mock_path.return_value = tmp_path / "patterns.jsonl"
            record_generated_pattern(
                "MyCapability",
                "spec",
                "class X: pass",
                "class TestX: pass",
            )
            patterns = lookup_patterns_by_capability("mycapability")
            assert len(patterns) == 1

    def test_lookup_by_capability_respects_limit(self, tmp_path):
        """Lookup by capability should respect limit parameter."""
        with patch("services.codegen_memory_recorder._get_memory_store_path") as mock_path:
            mock_path.return_value = tmp_path / "patterns.jsonl"
            # Record 3 patterns for same capability
            for i in range(3):
                record_generated_pattern(
                    "test_capability",
                    f"spec {i}",
                    f"class X{i}: pass",
                    f"class TestX{i}: pass",
                )
            patterns = lookup_patterns_by_capability("test_capability", limit=2)
            assert len(patterns) == 2

    def test_lookup_by_capability_returns_newest_first(self, tmp_path):
        """Lookup by capability should return newest patterns first."""
        import time
        with patch("services.codegen_memory_recorder._get_memory_store_path") as mock_path:
            mock_path.return_value = tmp_path / "patterns.jsonl"
            # Record patterns with slight delay to ensure different timestamps
            id1 = record_generated_pattern(
                "test_capability",
                "spec 1",
                "class A: pass",
                "class TestA: pass",
            )
            time.sleep(0.01)  # Small delay to ensure timestamp difference
            id2 = record_generated_pattern(
                "test_capability",
                "spec 2",
                "class B: pass",
                "class TestB: pass",
            )
            patterns = lookup_patterns_by_capability("test_capability")
            assert patterns[0]["id"] == id2  # Newest should be first

    def test_lookup_by_spec_finds_exact_matches(self, tmp_path):
        """Lookup by spec should find exact spec hash matches."""
        with patch("services.codegen_memory_recorder._get_memory_store_path") as mock_path:
            mock_path.return_value = tmp_path / "patterns.jsonl"
            spec = "create an event handler"
            record_generated_pattern(
                "capability",
                spec,
                "class Handler: pass",
                "class TestHandler: pass",
            )
            patterns = lookup_patterns_by_spec(spec)
            assert len(patterns) == 1
            assert patterns[0]["spec_hash"] == _compute_spec_hash(spec)

    def test_lookup_by_spec_with_capability_filter(self, tmp_path):
        """Lookup by spec with capability filter should narrow results."""
        with patch("services.codegen_memory_recorder._get_memory_store_path") as mock_path:
            mock_path.return_value = tmp_path / "patterns.jsonl"
            spec = "shared spec"
            # Record same spec with different capabilities
            record_generated_pattern(
                "capability_a",
                spec,
                "class A: pass",
                "class TestA: pass",
            )
            record_generated_pattern(
                "capability_b",
                spec,
                "class B: pass",
                "class TestB: pass",
            )
            # Lookup with filter should find only capability_a
            patterns = lookup_patterns_by_spec(spec, capability_name="capability_a")
            assert len(patterns) == 1
            assert patterns[0]["capability_name"] == "capability_a"

    def test_lookup_by_spec_returns_empty_when_no_match(self, tmp_path):
        """Lookup by spec should return empty when no match."""
        with patch("services.codegen_memory_recorder._get_memory_store_path") as mock_path:
            mock_path.return_value = tmp_path / "patterns.jsonl"
            patterns = lookup_patterns_by_spec("nonexistent spec")
            assert patterns == []


class TestMemoryInjection:
    """Test prompt injection context building."""

    def test_build_injection_context_exact_spec_match(self, tmp_path):
        """Injection context should prefer exact spec matches."""
        with patch("services.codegen_memory_recorder._get_memory_store_path") as mock_path:
            mock_path.return_value = tmp_path / "patterns.jsonl"
            spec = "exact spec"
            record_generated_pattern(
                "capability",
                spec,
                "class Handler: pass",
                "class TestHandler: pass",
            )
            context = build_memory_injection_context("capability", spec)
            assert "Exact Spec Match" in context or "exact_spec_match" in context
            assert "Prior" in context

    def test_build_injection_context_capability_fallback(self, tmp_path):
        """Injection context should fall back to capability lookup."""
        with patch("services.codegen_memory_recorder._get_memory_store_path") as mock_path:
            mock_path.return_value = tmp_path / "patterns.jsonl"
            record_generated_pattern(
                "capability",
                "old spec",
                "class Handler: pass",
                "class TestHandler: pass",
            )
            context = build_memory_injection_context("capability", "new spec")
            assert "prior_capability_pattern" in context or "Prior" in context

    def test_build_injection_context_empty_when_no_patterns(self):
        """Injection context should be empty when no patterns found."""
        with patch("services.codegen_memory_recorder._get_memory_store_path") as mock_path:
            mock_path.return_value = Path("/nonexistent/path.jsonl")
            context = build_memory_injection_context("capability", "spec")
            assert context == ""

    def test_format_pattern_context_includes_capability_name(self, tmp_path):
        """Formatted context should include capability name."""
        with patch("services.codegen_memory_recorder._get_memory_store_path") as mock_path:
            mock_path.return_value = tmp_path / "patterns.jsonl"
            record_generated_pattern(
                "my_capability",
                "spec",
                "class X: pass",
                "class TestX: pass",
            )
            context = build_memory_injection_context("my_capability", "spec")
            assert "my_capability" in context

    def test_format_pattern_context_includes_code_patterns(self, tmp_path):
        """Formatted context should include code patterns."""
        with patch("services.codegen_memory_recorder._get_memory_store_path") as mock_path:
            mock_path.return_value = tmp_path / "patterns.jsonl"
            record_generated_pattern(
                "capability",
                "spec",
                "class EventHandler:\n    def process(self): pass",
                "class TestEventHandler: pass",
            )
            context = build_memory_injection_context("capability", "spec")
            assert "Code Patterns" in context
            assert "def process" in context or "EventHandler" in context

    def test_format_pattern_context_includes_test_patterns(self, tmp_path):
        """Formatted context should include test patterns."""
        with patch("services.codegen_memory_recorder._get_memory_store_path") as mock_path:
            mock_path.return_value = tmp_path / "patterns.jsonl"
            record_generated_pattern(
                "capability",
                "spec",
                "class Handler: pass",
                "class TestHandler:\n    def test_process(self): pass",
            )
            context = build_memory_injection_context("capability", "spec")
            assert "Test Patterns" in context


class TestServiceSingleton:
    """Test service singleton exposure."""

    def test_service_singleton_exposes_record_pattern(self, tmp_path):
        """Service singleton should expose record_pattern method."""
        with patch("services.codegen_memory_recorder._get_memory_store_path") as mock_path:
            mock_path.return_value = tmp_path / "patterns.jsonl"
            pattern_id = CODEGEN_MEMORY_RECORDER_SERVICE.record_pattern(
                "capability",
                "spec",
                "class X: pass",
                "class TestX: pass",
            )
            assert pattern_id is not None

    def test_service_singleton_exposes_lookup_by_capability(self, tmp_path):
        """Service singleton should expose lookup_by_capability method."""
        with patch("services.codegen_memory_recorder._get_memory_store_path") as mock_path:
            mock_path.return_value = tmp_path / "patterns.jsonl"
            CODEGEN_MEMORY_RECORDER_SERVICE.record_pattern(
                "capability",
                "spec",
                "class X: pass",
                "class TestX: pass",
            )
            patterns = CODEGEN_MEMORY_RECORDER_SERVICE.lookup_by_capability("capability")
            assert len(patterns) == 1

    def test_service_singleton_exposes_lookup_by_spec(self, tmp_path):
        """Service singleton should expose lookup_by_spec method."""
        with patch("services.codegen_memory_recorder._get_memory_store_path") as mock_path:
            mock_path.return_value = tmp_path / "patterns.jsonl"
            spec = "test spec"
            CODEGEN_MEMORY_RECORDER_SERVICE.record_pattern(
                "capability",
                spec,
                "class X: pass",
                "class TestX: pass",
            )
            patterns = CODEGEN_MEMORY_RECORDER_SERVICE.lookup_by_spec(spec)
            assert len(patterns) == 1

    def test_service_singleton_exposes_memory_injection_context(self, tmp_path):
        """Service singleton should expose get_memory_injection_context method."""
        with patch("services.codegen_memory_recorder._get_memory_store_path") as mock_path:
            mock_path.return_value = tmp_path / "patterns.jsonl"
            spec = "test spec"
            CODEGEN_MEMORY_RECORDER_SERVICE.record_pattern(
                "capability",
                spec,
                "class X: pass",
                "class TestX: pass",
            )
            context = CODEGEN_MEMORY_RECORDER_SERVICE.get_memory_injection_context(
                "capability", spec
            )
            assert len(context) > 0


class TestErrorHandling:
    """Test error handling and graceful degradation."""

    def test_record_pattern_raises_on_io_error(self):
        """Record should raise IOError when write fails."""
        with patch("services.codegen_memory_recorder._get_memory_store_path") as mock_path:
            mock_path.return_value = Path("/nonexistent/deeply/nested/path/patterns.jsonl")
            # This will fail to write to nonexistent directory
            # We expect an IOError
            # Note: This may not raise if Path doesn't verify parent exists
            # So we use mock to force the error
            with patch("builtins.open", side_effect=IOError("Permission denied")):
                with pytest.raises(IOError):
                    record_generated_pattern(
                        "capability",
                        "spec",
                        "class X: pass",
                        "class TestX: pass",
                    )

    def test_lookup_handles_corrupted_json_gracefully(self, tmp_path):
        """Lookup should gracefully handle corrupted JSON in store."""
        with patch("services.codegen_memory_recorder._get_memory_store_path") as mock_path:
            mock_path.return_value = tmp_path / "patterns.jsonl"
            # Write corrupted JSON
            with open(tmp_path / "patterns.jsonl", "w") as f:
                f.write("{ invalid json }\n")
            # Lookup should return empty list, not crash
            patterns = lookup_patterns_by_capability("capability")
            assert patterns == []

    def test_lookup_handles_missing_fields_gracefully(self, tmp_path):
        """Lookup should handle patterns missing expected fields."""
        with patch("services.codegen_memory_recorder._get_memory_store_path") as mock_path:
            mock_path.return_value = tmp_path / "patterns.jsonl"
            # Write JSON missing fields
            with open(tmp_path / "patterns.jsonl", "w") as f:
                f.write('{"id": "123"}\n')
            # Lookup should return empty list (pattern filtered out), not crash
            patterns = lookup_patterns_by_capability("capability")
            assert patterns == []
