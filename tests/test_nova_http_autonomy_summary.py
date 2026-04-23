from __future__ import annotations

import json
import unittest
import uuid
from pathlib import Path
from unittest import mock

import nova_http


class TestNovaHttpAutonomySummary(unittest.TestCase):
    def test_autonomy_maintenance_summary_preserves_patch_queue_fields(self):
        base_tmp = Path("C:/Nova/runtime/_test_tmp")
        base_tmp.mkdir(parents=True, exist_ok=True)
        state_path = base_tmp / f"autonomy_state_{uuid.uuid4().hex}.json"
        state_path.write_text(
            json.dumps(
                {
                    "runtime_worker": {"last_cycle_status": "ok", "interval_sec": 300},
                    "last_generated_queue_run": {"status": "blocked", "queue_open_count": 3},
                    "last_work_tree_cycle": {"status": "idle", "executed_count": 0, "tree_count": 1},
                    "last_patch_queue_sync": {"status": "ok", "review_previews_total": 17},
                    "last_patch_cleanup": {
                        "status": "ok",
                        "orphan_rejected_count": 238,
                        "superseded_archived_count": 347,
                        "review_total_before": 29,
                        "review_total_after": 17,
                    },
                    "last_kidney_status": {"mode": "enforce", "candidate_count": 19},
                },
                ensure_ascii=True,
            ),
            encoding="utf-8",
        )
        self.addCleanup(lambda: state_path.unlink(missing_ok=True))

        with mock.patch.object(nova_http, "AUTONOMY_MAINTENANCE_STATE_PATH", state_path), \
             mock.patch.object(nova_http.runtime_processes, "logical_service_processes", return_value=[]), \
             mock.patch.object(nova_http.runtime_processes, "select_logical_process", return_value=None):
            payload = nova_http._autonomy_maintenance_summary()

        self.assertEqual((payload.get("last_work_tree_cycle") or {}).get("status"), "idle")
        self.assertEqual((payload.get("last_patch_queue_sync") or {}).get("review_previews_total"), 17)
        self.assertEqual((payload.get("last_patch_cleanup") or {}).get("orphan_rejected_count"), 238)
        self.assertEqual((payload.get("last_patch_cleanup") or {}).get("superseded_archived_count"), 347)
        self.assertEqual((payload.get("last_kidney_status") or {}).get("candidate_count"), 19)


if __name__ == "__main__":
    unittest.main()
