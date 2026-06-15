"""
Codegen Self-Extension Memory Service

Records generated code patterns and specifications for pattern reuse on future codegen requests.
When a codegen patch is promoted to applied, captures:
- Capability name (what was built)
- Spec hash (unique identifier for requirement)
- Generated code patterns (structural patterns used)
- Test coverage patterns (how it was tested)
- Generated timestamp

On next codegen call for same/similar capability, injects prior patterns into prompt context
to enable pattern reuse instead of regenerating from scratch.

Schema (codegen.memory.pattern.v1):
  {
    "id": "uuid",
    "capability_name": "str",
    "spec_hash": "sha256(spec_string)",
    "code_patterns": ["class XyzHandler", "def process_xyz", "exception handling"],
    "test_patterns": ["unittest.TestCase", "setUp/tearDown", "mock integration"],
    "language": "python",
    "timestamp": "ISO8601",
    "generation_context": {
      "tool_version": "str",
      "model_used": "str",
      "prompt_style": "str"
    }
  }
"""

import json
import hashlib
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any


def _get_memory_store_path() -> Path:
    """Get path to codegen memory store file."""
    workspace_root = Path(__file__).parent.parent
    memory_dir = workspace_root / "data_sources"
    memory_dir.mkdir(exist_ok=True)
    return memory_dir / "codegen_patterns.jsonl"


def _compute_spec_hash(spec_string: str) -> str:
    """Compute deterministic SHA256 hash of spec."""
    return hashlib.sha256(spec_string.encode("utf-8")).hexdigest()


def record_generated_pattern(
    capability_name: str,
    spec_string: str,
    generated_code: str,
    test_code: str,
    language: str = "python",
    tool_version: str = "1.0",
    model_used: str = "qwen2.5:7b",
) -> str:
    """
    Record a generated code pattern after successful patch promotion.

    Args:
        capability_name: Name of capability that was built (e.g., "autonomous_code_generation")
        spec_string: Full specification that drove code generation
        generated_code: The generated code artifact
        test_code: The test code generated for coverage
        language: Programming language (default: python)
        tool_version: Version of codegen tool that generated this
        model_used: LLM model that generated the code

    Returns:
        pattern_id: UUID of recorded pattern for tracking

    Raises:
        IOError: If memory store cannot be written
    """
    spec_hash = _compute_spec_hash(spec_string)
    pattern_id = str(uuid.uuid4())

    # Extract code patterns from generated code
    code_patterns = _extract_code_patterns(generated_code, language)

    # Extract test patterns from test code
    test_patterns = _extract_test_patterns(test_code, language)

    # Build pattern record
    pattern_record = {
        "id": pattern_id,
        "capability_name": capability_name,
        "spec_hash": spec_hash,
        "code_patterns": code_patterns,
        "test_patterns": test_patterns,
        "language": language,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "generation_context": {
            "tool_version": tool_version,
            "model_used": model_used,
            "prompt_style": "structured_spec",
        },
    }

    # Append to memory store (JSONL format)
    store_path = _get_memory_store_path()
    try:
        with open(store_path, "a") as f:
            f.write(json.dumps(pattern_record) + "\n")
    except IOError as e:
        raise IOError(f"Failed to write to codegen memory store at {store_path}: {e}")

    return pattern_id


def lookup_patterns_by_capability(
    capability_name: str, limit: int = 5
) -> List[Dict[str, Any]]:
    """
    Look up prior patterns recorded for a given capability.

    Args:
        capability_name: Name of capability to search for
        limit: Maximum number of patterns to return (most recent first)

    Returns:
        List of pattern records (newest first), up to limit items
    """
    store_path = _get_memory_store_path()

    if not store_path.exists():
        return []

    patterns = []
    try:
        with open(store_path, "r") as f:
            for line in f:
                if not line.strip():
                    continue
                record = json.loads(line)
                if record.get("capability_name", "").lower() == capability_name.lower():
                    patterns.append(record)
    except (IOError, json.JSONDecodeError) as e:
        # Log error but don't crash; graceful degradation
        print(f"Warning: Failed to read codegen memory store: {e}")
        return []

    # Sort by timestamp (newest first)
    patterns.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

    return patterns[:limit]


def lookup_patterns_by_spec(
    spec_string: str, capability_name: Optional[str] = None, limit: int = 3
) -> List[Dict[str, Any]]:
    """
    Look up patterns by spec hash (exact match for same requirement).

    Args:
        spec_string: Full specification text to search for
        capability_name: Optional filter to capability (speeds up search)
        limit: Maximum number of patterns to return

    Returns:
        List of pattern records matching spec hash, up to limit items
    """
    spec_hash = _compute_spec_hash(spec_string)
    store_path = _get_memory_store_path()

    if not store_path.exists():
        return []

    patterns = []
    try:
        with open(store_path, "r") as f:
            for line in f:
                if not line.strip():
                    continue
                record = json.loads(line)
                if record.get("spec_hash") == spec_hash:
                    if capability_name is None or record.get("capability_name", "").lower() == capability_name.lower():
                        patterns.append(record)
    except (IOError, json.JSONDecodeError) as e:
        print(f"Warning: Failed to read codegen memory store: {e}")
        return []

    # Sort by timestamp (newest first)
    patterns.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

    return patterns[:limit]


def _extract_code_patterns(code: str, language: str) -> List[str]:
    """Extract structural patterns from generated code."""
    patterns = []

    if language == "python":
        lines = code.split("\n")
        for line in lines:
            stripped = line.strip()
            # Capture class definitions
            if stripped.startswith("class "):
                patterns.append(stripped.split("(")[0].replace("class ", ""))
            # Capture function definitions
            elif stripped.startswith("def "):
                func_name = stripped.split("(")[0].replace("def ", "")
                patterns.append(f"def {func_name}")
            # Capture exception handling patterns
            elif stripped.startswith("except "):
                patterns.append("exception_handling")
            # Capture import patterns
            elif stripped.startswith("from ") or stripped.startswith("import "):
                patterns.append(stripped)

    # Deduplicate while preserving order
    seen = set()
    unique_patterns = []
    for p in patterns:
        if p not in seen:
            seen.add(p)
            unique_patterns.append(p)

    return unique_patterns[:20]  # Limit to most important 20


def _extract_test_patterns(test_code: str, language: str) -> List[str]:
    """Extract test structural patterns from test code."""
    patterns = []

    if language == "python":
        lines = test_code.split("\n")
        for line in lines:
            stripped = line.strip()
            # Capture test class definitions
            if stripped.startswith("class Test"):
                patterns.append(stripped.split("(")[0].replace("class ", ""))
            # Capture test methods
            elif stripped.startswith("def test_"):
                test_name = stripped.split("(")[0].replace("def ", "")
                patterns.append(test_name)
            # Capture assertion patterns
            elif "assert" in stripped.lower():
                patterns.append("assertions")
            # Capture mock patterns
            elif "mock" in stripped.lower():
                patterns.append("mocking")
            # Capture setup/teardown
            elif stripped.startswith("def setUp") or stripped.startswith("def tearDown"):
                patterns.append(stripped.split("(")[0].replace("def ", ""))

    # Deduplicate while preserving order
    seen = set()
    unique_patterns = []
    for p in patterns:
        if p not in seen:
            seen.add(p)
            unique_patterns.append(p)

    return unique_patterns[:15]  # Limit to most important 15


def build_memory_injection_context(capability_name: str, spec_string: str) -> str:
    """
    Build context string to inject prior patterns into codegen prompt.

    Args:
        capability_name: Name of capability being generated
        spec_string: Full specification for the generation

    Returns:
        Formatted context string for prompt injection, or empty string if no prior patterns
    """
    # First try exact spec match
    spec_patterns = lookup_patterns_by_spec(spec_string, capability_name)
    if spec_patterns:
        pattern = spec_patterns[0]
        return _format_pattern_context("exact_spec_match", pattern)

    # Fall back to capability lookup
    cap_patterns = lookup_patterns_by_capability(capability_name, limit=2)
    if cap_patterns:
        pattern = cap_patterns[0]
        return _format_pattern_context("prior_capability_pattern", pattern)

    return ""


def _format_pattern_context(match_type: str, pattern: Dict[str, Any]) -> str:
    """Format a pattern record into prompt injection context."""
    context = f"\n## Prior {match_type.replace('_', ' ').title()}\n"
    context += f"Capability: {pattern.get('capability_name', 'unknown')}\n"
    context += f"Language: {pattern.get('language', 'python')}\n"
    context += f"Generated on: {pattern.get('timestamp', 'unknown')}\n"
    context += f"\n### Code Patterns Used:\n"
    for code_pattern in pattern.get("code_patterns", [])[:10]:
        context += f"- {code_pattern}\n"
    context += f"\n### Test Patterns Used:\n"
    for test_pattern in pattern.get("test_patterns", [])[:8]:
        context += f"- {test_pattern}\n"
    context += "\nConsider reusing these patterns if they fit the current requirement.\n"
    return context


# Service singleton
class CodegenMemoryRecorderService:
    """Service interface for codegen memory recording and retrieval."""

    @staticmethod
    def record_pattern(
        capability_name: str,
        spec_string: str,
        generated_code: str,
        test_code: str,
        language: str = "python",
        tool_version: str = "1.0",
        model_used: str = "qwen2.5:7b",
    ) -> str:
        """Record a generated code pattern (see record_generated_pattern)."""
        return record_generated_pattern(
            capability_name,
            spec_string,
            generated_code,
            test_code,
            language,
            tool_version,
            model_used,
        )

    @staticmethod
    def lookup_by_capability(capability_name: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Look up patterns by capability name (see lookup_patterns_by_capability)."""
        return lookup_patterns_by_capability(capability_name, limit)

    @staticmethod
    def lookup_by_spec(
        spec_string: str, capability_name: Optional[str] = None, limit: int = 3
    ) -> List[Dict[str, Any]]:
        """Look up patterns by spec hash (see lookup_patterns_by_spec)."""
        return lookup_patterns_by_spec(spec_string, capability_name, limit)

    @staticmethod
    def get_memory_injection_context(capability_name: str, spec_string: str) -> str:
        """Build prompt injection context (see build_memory_injection_context)."""
        return build_memory_injection_context(capability_name, spec_string)


CODEGEN_MEMORY_RECORDER_SERVICE = CodegenMemoryRecorderService()
