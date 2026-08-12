"""Tests for capability gap detection and signal generation."""

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from services.capabilities_gap_detector import (
    CAPABILITY_GAP_DETECTOR_SERVICE,
    detect_capability_gaps,
    enhance_status_with_capability_gaps,
)


class TestCapabilityGapDetector(unittest.TestCase):
    """Test capability gap detection logic."""

    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.base_dir = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def _write_capabilities(self, caps: dict[str, str]):
        """Helper to write capabilities.json."""
        cap_file = self.base_dir / "capabilities.json"
        cap_file.write_text(json.dumps(caps, ensure_ascii=False, indent=2), encoding="utf-8")

    def _write_roadmap(self, roadmap: dict):
        """Helper to write capabilities_roadmap.json."""
        roadmap_file = self.base_dir / "capabilities_roadmap.json"
        roadmap_file.write_text(json.dumps(roadmap, ensure_ascii=False, indent=2), encoding="utf-8")

    def test_detect_no_gaps_when_all_capabilities_registered(self):
        """No gaps when all declared capabilities are registered."""
        self._write_capabilities({
            "codegen_tool": "Can generate code",
            "codegen_patch_bridge": "Can bridge to patch",
            "capability_gap_detection": "Can detect gaps",
        })
        self._write_roadmap({
            "declared_capabilities": {
                "codegen_tool": "Can generate code",
                "codegen_patch_bridge": "Can bridge to patch",
                "capability_gap_detection": "Can detect gaps",
            },
            "gap_detection_config": {"enabled": True},
        })

        gaps, summary = detect_capability_gaps(self.base_dir)
        self.assertEqual(len(gaps), 0)
        self.assertTrue(summary["ok"])
        self.assertEqual(summary["gap_count"], 0)
        self.assertEqual(summary["registered_count"], 3)
        self.assertEqual(summary["declared_count"], 3)

    def test_detect_gaps_when_capabilities_missing(self):
        """Gaps detected when declared capabilities not registered."""
        self._write_capabilities({
            "codegen_tool": "Can generate code",
            "codegen_patch_bridge": "Can bridge to patch",
        })
        self._write_roadmap({
            "declared_capabilities": {
                "codegen_tool": "Can generate code",
                "codegen_patch_bridge": "Can bridge to patch",
                "capability_gap_detection": "Can detect gaps",
                "autonomous_code_generation": "Can auto-generate",
            },
            "gap_detection_config": {"enabled": True},
        })

        gaps, summary = detect_capability_gaps(self.base_dir)
        self.assertEqual(len(gaps), 2)
        self.assertIn("autonomous_code_generation", gaps)
        self.assertIn("capability_gap_detection", gaps)
        self.assertTrue(summary["ok"])
        self.assertEqual(summary["gap_count"], 2)

    def test_detect_gaps_case_insensitive(self):
        """Gap detection is case-insensitive."""
        self._write_capabilities({
            "CodeGen_Tool": "Can generate code",
        })
        self._write_roadmap({
            "declared_capabilities": {
                "codegen_tool": "Can generate code (lowercase)",
                "other_capability": "Other",
            },
            "gap_detection_config": {"enabled": True},
        })

        gaps, summary = detect_capability_gaps(self.base_dir)
        self.assertEqual(len(gaps), 1)
        self.assertIn("other_capability", gaps)

    def test_detect_gaps_returns_empty_without_roadmap(self):
        """Returns empty when roadmap file missing."""
        self._write_capabilities({
            "codegen_tool": "Can generate code",
        })

        gaps, summary = detect_capability_gaps(self.base_dir)
        self.assertEqual(len(gaps), 0)
        self.assertFalse(summary["ok"])
        self.assertEqual(summary["reason"], "roadmap_missing")

    def test_detect_gaps_returns_empty_without_capabilities(self):
        """Returns empty when capabilities file missing (no gap to signal)."""
        self._write_roadmap({
            "declared_capabilities": {
                "codegen_tool": "Can generate code",
            },
            "gap_detection_config": {"enabled": True},
        })

        gaps, summary = detect_capability_gaps(self.base_dir)
        self.assertEqual(len(gaps), 1)
        self.assertEqual(summary["gap_count"], 1)

    def test_enhance_status_with_gaps(self):
        """Status enhancement includes gap information."""
        self._write_capabilities({
            "runtime_core": "Core runtime",
            "codegen_tool": "Codegen",
        })
        self._write_roadmap({
            "declared_capabilities": {
                "runtime_core": "Core runtime",
                "codegen_tool": "Codegen",
                "autonomous_generation": "Auto-gen",
            },
            "gap_detection_config": {"enabled": True},
        })

        status = {"some_field": "value"}
        enhanced = enhance_status_with_capability_gaps(status, self.base_dir)

        self.assertEqual(enhanced["capability_gap_count"], 1)
        self.assertIn("autonomous_generation", enhanced["capability_gaps"])
        self.assertIn("codegen_tool", enhanced["capabilities_registered"])
        self.assertIsNotNone(enhanced["capabilities_roadmap"])
        self.assertIn("capability_gaps_external", enhanced)
        self.assertIn("capability_gaps_nova_code", enhanced)

    def test_enhance_status_preserves_existing_fields(self):
        """Status enhancement preserves original fields."""
        self._write_capabilities({"codegen_tool": "Codegen"})
        self._write_roadmap({
            "declared_capabilities": {"codegen_tool": "Codegen"},
            "gap_detection_config": {"enabled": True},
        })

        status = {
            "existing_field": "existing_value",
            "count": 42,
            "nested": {"key": "value"},
        }
        enhanced = enhance_status_with_capability_gaps(status, self.base_dir)

        self.assertEqual(enhanced["existing_field"], "existing_value")
        self.assertEqual(enhanced["count"], 42)
        self.assertEqual(enhanced["nested"]["key"], "value")


class TestCapabilityGapService(unittest.TestCase):
    """Test the capability gap detector service singleton."""

    def test_service_exposes_all_methods(self):
        """Service singleton exposes public methods."""
        self.assertTrue(hasattr(CAPABILITY_GAP_DETECTOR_SERVICE, "detect_capability_gaps"))
        self.assertTrue(hasattr(CAPABILITY_GAP_DETECTOR_SERVICE, "enhance_status_with_capability_gaps"))
        self.assertTrue(hasattr(CAPABILITY_GAP_DETECTOR_SERVICE, "load_capabilities_json"))
        self.assertTrue(hasattr(CAPABILITY_GAP_DETECTOR_SERVICE, "load_capabilities_roadmap"))
        self.assertTrue(callable(CAPABILITY_GAP_DETECTOR_SERVICE.detect_capability_gaps))
        self.assertTrue(callable(CAPABILITY_GAP_DETECTOR_SERVICE.enhance_status_with_capability_gaps))


class TestCapabilityGapSignalIntegration(unittest.TestCase):
    """Test capability gap signal in work tree signal ingestion."""

    def test_signal_class_is_valid(self):
        """declared_capability_absent is in valid signal classes."""
        from services.work_tree_signal_ingestion import _VALID_SIGNAL_CLASSES
        self.assertIn("declared_capability_absent", _VALID_SIGNAL_CLASSES)

    def test_signal_class_maps_to_work_class(self):
        """Signal class maps to capability_gap work class."""
        from services.work_tree_signal_ingestion import _SIGNAL_TO_WORK_CLASS
        self.assertEqual(_SIGNAL_TO_WORK_CLASS["declared_capability_absent"], "capability_gap")

    def test_capability_gap_in_bucket_mappings(self):
        """capability_gap is in bucket and actionability mappings."""
        from services.work_tree_signal_ingestion import (
            _BUCKET_BY_WORK_CLASS,
            _DEFAULT_ACTIONABILITY_BY_CLASS,
        )
        self.assertEqual(_BUCKET_BY_WORK_CLASS["capability_gap"], "capability")
        self.assertEqual(_DEFAULT_ACTIONABILITY_BY_CLASS["capability_gap"], "safe_now")


class TestCapabilityGapSignalGeneration(unittest.TestCase):
    """Test capability gap signal generation from status payload."""

    def test_signal_generated_when_gaps_present(self):
        """Signal is generated when capability gaps are detected."""
        from services.layer_maturity_policy import enrich_status_with_layer_maturity
        from services.work_tree_signal_ingestion import _capability_gap_signal_from_status

        status = enrich_status_with_layer_maturity(
            {
                "capability_gap_count": 2,
                "capability_gaps": ["autonomous_code_generation", "type_checking"],
                "root_closure_inventory": {
                    "roots": [
                        {"root_id": root_id, "ok": True}
                        for root_id in (
                            "model_runtime",
                            "conversation_routing",
                            "frontdoor_cli",
                            "operator_control",
                            "http_api_control",
                        )
                    ]
                },
            },
            policy={
                "layers": {
                    "codegen": {
                        "mode": "active",
                        "promoted_capabilities": ["autonomous_code_generation", "type_checking"],
                    },
                    "leah": {"mode": "observe", "promoted_capabilities": []},
                }
            },
        )

        signal = _capability_gap_signal_from_status(status)
        self.assertIsNotNone(signal)
        self.assertEqual(signal["signal_class"], "declared_capability_absent")
        self.assertEqual(signal["severity"], "medium")
        self.assertIn("autonomous_code_generation", signal["payload"]["gaps"])
        self.assertEqual(signal["payload"]["execution_group"], "generated_code")

    def test_signal_not_generated_when_no_gaps(self):
        """Signal is not generated when no capability gaps."""
        from services.work_tree_signal_ingestion import _capability_gap_signal_from_status

        status = {
            "capability_gap_count": 0,
            "capability_gaps": [],
        }

        signal = _capability_gap_signal_from_status(status)
        self.assertIsNone(signal)

    def test_signal_not_generated_without_capability_surface(self):
        """Signal is not generated without capability manifest surface."""
        from services.work_tree_signal_ingestion import _capability_gap_signal_from_status

        status = {
            "other_field": "value",
        }

        signal = _capability_gap_signal_from_status(status)
        self.assertIsNone(signal)

    def test_signal_title_reflects_gap_count(self):
        """Signal title reflects number of gaps."""
        from services.layer_maturity_policy import enrich_status_with_layer_maturity
        from services.work_tree_signal_ingestion import _capability_gap_signal_from_status

        status = enrich_status_with_layer_maturity(
            {
                "capability_gap_count": 3,
                "capability_gaps": [
                    "type_checking",
                    "documentation_generation",
                    "configuration_management",
                ],
                "root_closure_inventory": {
                    "roots": [
                        {"root_id": root_id, "ok": True}
                        for root_id in (
                            "model_runtime",
                            "conversation_routing",
                            "frontdoor_cli",
                            "operator_control",
                            "http_api_control",
                        )
                    ]
                },
            },
            policy={
                "layers": {
                    "codegen": {
                        "mode": "active",
                        "promoted_capabilities": [
                            "type_checking",
                            "documentation_generation",
                            "configuration_management",
                        ],
                    },
                    "leah": {"mode": "observe", "promoted_capabilities": []},
                }
            },
        )

        signal = _capability_gap_signal_from_status(status)
        self.assertIsNotNone(signal)
        self.assertIn("3 capabilities", signal["title"])

    def test_signal_task_sequence_includes_roadmap_review(self):
        """Signal task sequence includes roadmap review."""
        from services.layer_maturity_policy import enrich_status_with_layer_maturity
        from services.work_tree_signal_ingestion import _capability_gap_signal_from_status

        status = enrich_status_with_layer_maturity(
            {
                "capability_gap_count": 1,
                "capability_gaps": ["type_checking"],
                "root_closure_inventory": {
                    "roots": [
                        {"root_id": root_id, "ok": True}
                        for root_id in (
                            "model_runtime",
                            "conversation_routing",
                            "frontdoor_cli",
                            "operator_control",
                            "http_api_control",
                        )
                    ]
                },
            },
            policy={
                "layers": {
                    "codegen": {
                        "mode": "active",
                        "promoted_capabilities": ["type_checking"],
                    },
                    "leah": {"mode": "observe", "promoted_capabilities": []},
                }
            },
        )

        signal = _capability_gap_signal_from_status(status)
        self.assertIsNotNone(signal)
        task_sequence = signal.get("task_sequence") or []
        task_titles = [t.get("title") or "" for t in task_sequence]

        self.assertTrue(any("roadmap" in title.lower() for title in task_titles))
        self.assertTrue(any("gap" in title.lower() or "codegen" in title.lower() for title in task_titles))

    def test_leah_gap_uses_leah_build_execution_group(self):
        """Leah-prefixed gaps should route into the Leah build lane."""
        from services.layer_maturity_policy import enrich_status_with_layer_maturity
        from services.work_tree_signal_ingestion import _capability_gap_signal_from_status

        status = enrich_status_with_layer_maturity(
            {
                "capability_gap_count": 2,
                "capability_gaps": ["leah_voice_persona_engine", "leah_memory_recall", "leah_conversation_continuity"],
                "root_closure_inventory": {
                    "roots": [
                        {"root_id": root_id, "ok": True}
                        for root_id in (
                            "model_runtime",
                            "conversation_routing",
                            "frontdoor_cli",
                            "operator_control",
                            "http_api_control",
                            "http_continuity",
                            "session_identity_auth",
                        )
                    ]
                },
            },
            policy={
                "layers": {
                    "leah": {
                        "mode": "active",
                        "promoted_capabilities": ["leah_conversation_continuity"],
                    },
                    "codegen": {"mode": "observe", "promoted_capabilities": []},
                }
            },
        )

        signal = _capability_gap_signal_from_status(status)
        self.assertIsNotNone(signal)
        self.assertTrue(signal["title"].startswith("Leah capability gap"))
        self.assertEqual(signal["payload"]["execution_group"], "leah_build")
        self.assertEqual(signal["payload"]["leah_gap_count"], 1)
        self.assertEqual(signal["payload"]["primary_capability"], "leah_conversation_continuity")


if __name__ == "__main__":
    unittest.main()
