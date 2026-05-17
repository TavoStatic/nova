from __future__ import annotations

import os
import shutil
import unittest
import uuid
from pathlib import Path

from services.runtime_restart_provenance import RuntimeRestartProvenanceService


WORK_TMP_ROOT = Path(os.environ.get("NOVA_VALIDATION_RUNTIME_DIR") or Path(__file__).resolve().parents[1] / "runtime" / "validation") / "pytest_temp"


def _workspace_case_dir(prefix: str) -> Path:
    WORK_TMP_ROOT.mkdir(parents=True, exist_ok=True)
    path = WORK_TMP_ROOT / f"{prefix}_{uuid.uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    return path


class TestRuntimeRestartProvenanceService(unittest.TestCase):
    def setUp(self) -> None:
        self.svc = RuntimeRestartProvenanceService()
        self.case_dir = _workspace_case_dir("runtime_restart_provenance")

    def tearDown(self) -> None:
        shutil.rmtree(self.case_dir, ignore_errors=True)

    def test_write_and_consume_pending_intent(self) -> None:
        path = self.case_dir / "restart_intent.json"

        written = self.svc.write_pending_intent(
            path,
            source="runtime_control",
            action="guard_restart",
            reason="operator_requested_guard_restart",
            now=100.0,
        )
        consumed = self.svc.consume_pending_intent(path, now=103.0)

        self.assertTrue(written.get("ok"))
        self.assertEqual(consumed.get("action"), "guard_restart")
        self.assertEqual(consumed.get("source"), "runtime_control")
        self.assertEqual(consumed.get("age_sec"), 3.0)
        self.assertFalse(path.exists())

    def test_replace_false_preserves_existing_active_intent(self) -> None:
        path = self.case_dir / "restart_intent.json"

        first = self.svc.write_pending_intent(
            path,
            source="runtime_control",
            action="guard_restart",
            reason="operator_requested_guard_restart",
            now=100.0,
        )
        second = self.svc.write_pending_intent(
            path,
            source="stop_guard_script",
            action="guard_stop",
            reason="operator_requested_guard_stop",
            replace=False,
            now=101.0,
        )

        self.assertEqual(second.get("intent_id"), first.get("intent_id"))
        self.assertTrue(second.get("preserved"))
        self.assertEqual(self.svc.read_pending_intent(path, now=102.0).get("action"), "guard_restart")


if __name__ == "__main__":
    unittest.main()
