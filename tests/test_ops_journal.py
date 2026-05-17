import os
import json
import shutil
import unittest
import uuid
from pathlib import Path
from unittest import mock

from services.ops_journal import append_ops_event


WORK_TMP_ROOT = Path(os.environ.get("NOVA_VALIDATION_RUNTIME_DIR") or Path(__file__).resolve().parents[1] / "runtime" / "validation") / "pytest_temp"


def _workspace_case_dir(prefix: str) -> Path:
    WORK_TMP_ROOT.mkdir(parents=True, exist_ok=True)
    path = WORK_TMP_ROOT / f"{prefix}_{uuid.uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    return path


class TestOpsJournal(unittest.TestCase):
    def test_append_ops_event_writes_jsonl_entry(self):
        case_dir = _workspace_case_dir("ops_journal")
        try:
            root = case_dir
            append_ops_event(
                root,
                category="control_action",
                action="refresh_status",
                result="ok",
                detail="status_refreshed",
                payload={"session_id": "abc", "count": 2},
            )

            journal = root / "ops_journal.jsonl"
            self.assertTrue(journal.exists())
            lines = journal.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 1)
            entry = json.loads(lines[0])
            self.assertEqual(entry.get("category"), "control_action")
            self.assertEqual(entry.get("action"), "refresh_status")
            self.assertEqual(entry.get("result"), "ok")
            self.assertEqual((entry.get("payload") or {}).get("session_id"), "abc")

            self.assertFalse((root / "This_is_nova").exists())
        finally:
            shutil.rmtree(case_dir, ignore_errors=True)

    def test_append_ops_event_preserves_live_root_this_is_nova_content(self):
        case_dir = _workspace_case_dir("ops_journal")
        try:
            root = case_dir / "workspace"
            runtime_dir = root / "runtime"
            runtime_dir.mkdir(parents=True, exist_ok=True)
            existing = root / "This_is_nova"
            existing.write_text("Nova summary\n", encoding="utf-8")

            with mock.patch("services.ops_journal.BASE_DIR", root), \
                 mock.patch("services.ops_journal.RUNTIME_DIR", runtime_dir), \
                 mock.patch("services.ops_journal.runtime_scope_name", return_value="live"):
                append_ops_event(
                    runtime_dir,
                    category="runtime",
                    action="tick",
                    result="ok",
                    detail="heartbeat",
                )

            text = existing.read_text(encoding="utf-8")
            self.assertTrue(text.startswith("Nova summary"))
            self.assertIn("ACTIVITY LOG", text)
            self.assertIn("heartbeat", text)
        finally:
            shutil.rmtree(case_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
