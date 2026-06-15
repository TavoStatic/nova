"""
Patch Promotion Memory Integration

When a patch created from codegen is successfully applied (promoted),
extracts and records the generated code patterns for future reuse.

Integrates with:
- nova_patching.py (patch_apply function) - calls after successful promotion
- codegen_memory_recorder.py (pattern recording)
- patch_control.py (tool interface)
"""

import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from zipfile import ZipFile

from services.codegen_memory_recorder import CODEGEN_MEMORY_RECORDER_SERVICE


def _extract_code_from_artifact_manifest(manifest: Dict[str, Any]) -> tuple[str, str]:
    """
    Extract generated code and test code from patch manifest.
    
    Returns:
        (generated_code_content, test_code_content)
    """
    generated_code_parts = []
    test_code_parts = []

    # Extract from files section of manifest
    files = manifest.get("files", [])
    for file_info in files:
        path = file_info.get("path", "")
        if path.endswith(".py"):
            # This is metadata, not actual content
            # We'll need the actual zip content
            generated_code_parts.append(f"# {path}\n")

    # Extract from tests section of manifest
    tests = manifest.get("tests", [])
    for test_info in tests:
        path = test_info.get("path", "")
        if path.endswith(".py"):
            test_code_parts.append(f"# {path}\n")

    return "\n".join(generated_code_parts), "\n".join(test_code_parts)


def extract_codegen_content_from_patch_zip(
    patch_zip_path: Path,
    patch_manifest: Dict[str, Any],
) -> tuple[Optional[str], Optional[str]]:
    """
    Extract actual generated code and test code from patch zip.
    
    Args:
        patch_zip_path: Path to the patch zip file
        patch_manifest: The patch manifest (from bridge)
    
    Returns:
        (generated_code_content, test_code_content) or (None, None) if extraction fails
    """
    try:
        generated_code_parts = []
        test_code_parts = []

        if not patch_zip_path.exists():
            return None, None

        with ZipFile(patch_zip_path, "r") as zf:
            files = patch_manifest.get("files", [])
            tests = patch_manifest.get("tests", [])

            # Extract generated code files
            for file_info in files:
                path = file_info.get("path", "")
                if path and path.endswith(".py"):
                    try:
                        content = zf.read(path).decode("utf-8", errors="replace")
                        generated_code_parts.append(content)
                    except (KeyError, UnicodeDecodeError):
                        pass  # File not in zip or unreadable

            # Extract test code files
            for test_info in tests:
                path = test_info.get("path", "")
                if path and path.endswith(".py"):
                    try:
                        content = zf.read(path).decode("utf-8", errors="replace")
                        test_code_parts.append(content)
                    except (KeyError, UnicodeDecodeError):
                        pass  # File not in zip or unreadable

        generated_code = "\n\n".join(generated_code_parts) or None
        test_code = "\n\n".join(test_code_parts) or None

        return generated_code, test_code

    except Exception as e:
        logging.warning(f"Failed to extract codegen content from patch zip {patch_zip_path}: {e}")
        return None, None


def record_patch_promotion_to_memory(
    patch_artifact_record: Dict[str, Any],
    patch_zip_path: Optional[Path] = None,
) -> Optional[str]:
    """
    Record a successfully promoted codegen patch to memory.
    
    Called after a patch from codegen is successfully applied.
    Extracts code patterns and records them for future pattern reuse.
    
    Args:
        patch_artifact_record: The patch artifact record (from bridge)
        patch_zip_path: Optional path to the actual patch zip containing applied files
    
    Returns:
        pattern_id if recorded successfully, None otherwise
    """
    try:
        # Extract spec information
        spec_source = patch_artifact_record.get("spec_source") or {}
        spec_name = str(spec_source.get("spec_name") or "unknown")
        spec_purpose = str(spec_source.get("spec_purpose") or "")

        # Full spec string for hashing
        spec_string = f"{spec_name}\n{spec_purpose}"

        # Get manifest
        manifest = patch_artifact_record.get("manifest") or {}

        # Try to extract actual code from zip if provided
        generated_code = None
        test_code = None

        if patch_zip_path and patch_zip_path.exists():
            generated_code, test_code = extract_codegen_content_from_patch_zip(
                patch_zip_path, manifest
            )

        # Fallback: construct from manifest metadata
        if not generated_code:
            files = manifest.get("files", [])
            generated_code = "\n".join(
                f"# {f.get('path', '')}: {f.get('kind', '')}"
                for f in files
                if f.get("path", "").endswith(".py")
            )
            if not generated_code.strip():
                logging.warning("Could not extract generated code from patch")
                return None

        if not test_code:
            tests = manifest.get("tests", [])
            test_code = "\n".join(
                f"# {t.get('path', '')}"
                for t in tests
                if t.get("path", "").endswith(".py")
            )
            if not test_code.strip():
                logging.warning("Could not extract test code from patch")
                test_code = "# No test code extracted"

        # Extract provenance
        provenance = patch_artifact_record.get("provenance") or {}
        generator = str(provenance.get("generator") or "codegen_tool")
        model = str(provenance.get("model") or "qwen2.5:7b")

        # Record to memory
        pattern_id = CODEGEN_MEMORY_RECORDER_SERVICE.record_pattern(
            capability_name=spec_name,
            spec_string=spec_string,
            generated_code=generated_code,
            test_code=test_code,
            language="python",
            tool_version="1.0",
            model_used=model,
        )

        logging.info(f"Recorded codegen pattern {pattern_id} for capability {spec_name}")
        return pattern_id

    except Exception as e:
        logging.error(f"Failed to record patch promotion to memory: {e}")
        return None


def inject_memory_context_into_codegen_prompt(
    spec_name: str,
    spec_purpose: str,
) -> str:
    """
    Build memory injection context for a codegen prompt.
    
    Called before invoking codegen tool to include prior patterns.
    
    Args:
        spec_name: Name of capability being generated
        spec_purpose: Purpose/description of what to generate
    
    Returns:
        Memory context string to inject into prompt, or empty string if no prior patterns
    """
    spec_string = f"{spec_name}\n{spec_purpose}"
    return CODEGEN_MEMORY_RECORDER_SERVICE.get_memory_injection_context(spec_name, spec_string)


# Service singleton
class PatchPromotionMemoryService:
    """Service interface for patch promotion memory recording."""

    @staticmethod
    def record_promotion(
        patch_artifact_record: Dict[str, Any],
        patch_zip_path: Optional[Path] = None,
    ) -> Optional[str]:
        """Record a successfully promoted patch to memory (see record_patch_promotion_to_memory)."""
        return record_patch_promotion_to_memory(patch_artifact_record, patch_zip_path)

    @staticmethod
    def get_memory_injection(spec_name: str, spec_purpose: str) -> str:
        """Get memory context to inject into codegen prompt (see inject_memory_context_into_codegen_prompt)."""
        return inject_memory_context_into_codegen_prompt(spec_name, spec_purpose)

    @staticmethod
    def extract_codegen_from_zip(patch_zip_path: Path, manifest: Dict[str, Any]) -> tuple[Optional[str], Optional[str]]:
        """Extract codegen content from patch zip (see extract_codegen_content_from_patch_zip)."""
        return extract_codegen_content_from_patch_zip(patch_zip_path, manifest)


PATCH_PROMOTION_MEMORY_SERVICE = PatchPromotionMemoryService()
