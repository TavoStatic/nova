from __future__ import annotations

import os
from pathlib import Path
import unittest
import uuid

import work_tree
from services.core_health_brief import (
    CORE_HEALTH_WORK_IDENTITY,
    build_core_health_brief,
    feed_core_health_brief_to_work_tree,
)


def _validation_tmp_root() -> Path:
    return Path(os.environ.get("NOVA_VALIDATION_RUNTIME_DIR") or Path(__file__).resolve().parents[1] / "runtime" / "validation") / "_test_tmp"


class TestCoreHealthBriefService(unittest.TestCase):
    def setUp(self) -> None:
        base_tmp = _validation_tmp_root()
        base_tmp.mkdir(parents=True, exist_ok=True)
        self._db_path = base_tmp / f"core_health_brief_{uuid.uuid4().hex}.sqlite3"
        work_tree._set_db_path(self._db_path)

    def tearDown(self) -> None:
        for path in (self._db_path, self._db_path.with_name(f"{self._db_path.name}-journal")):
            try:
                if path.exists():
                    path.unlink()
            except Exception:
                pass

    def test_build_brief_turns_existing_health_signals_into_repair_orders(self):
        brief = build_core_health_brief(
            core_steward={
                "level": "repair",
                "maintenance_queue": [
                    {
                        "priority": "high",
                        "title": "Recover core runtime",
                        "reason": "Heartbeat or core-state health is degraded.",
                        "command": "nova runtime-status",
                    }
                ],
            },
            self_status={
                "level": "hurting",
                "events": [
                    {
                        "severity": "warning",
                        "title": "Fallback pressure is high",
                        "detail": "Fallback overuse score is 0.93.",
                        "source": "pulse",
                        "command": "learning status",
                    }
                ],
            },
            runtime_summary={"core": {"status": "heartbeat_stale"}},
        )

        self.assertEqual(brief.get("level"), "repair")
        orders = list(brief.get("repair_work_orders") or [])
        self.assertGreaterEqual(len(orders), 2)
        titles = {order.get("title") for order in orders}
        self.assertIn("Recover core runtime", titles)
        self.assertIn("Resolve core runtime state", titles)
        advisory_titles = {item.get("title") for item in list(brief.get("advisories") or [])}
        self.assertIn("Fallback pressure is high", advisory_titles)

    def test_training_pressure_without_drift_is_advisory_not_repair(self):
        stale_brief = build_core_health_brief(
            core_steward={
                "level": "repair",
                "maintenance_queue": [
                    {
                        "priority": "high",
                        "title": "Recover core runtime",
                        "reason": "Heartbeat or core-state health is degraded.",
                        "command": "nova runtime-status",
                    }
                ],
            }
        )
        seeded = feed_core_health_brief_to_work_tree(stale_brief, work_tree_module=work_tree)

        brief = build_core_health_brief(
            core_steward={
                "level": "strong",
                "maintenance_queue": [
                    {
                        "priority": "medium",
                        "title": "Review fallback training pressure",
                        "reason": "Fallback training pressure is elevated at 0.97, but the latest queue status is clear.",
                        "command": "pulse",
                    }
                ],
            },
            self_status={
                "level": "hurting",
                "events": [
                    {
                        "severity": "warning",
                        "title": "Fallback pressure is high",
                        "detail": "Fallback overuse score is 0.97.",
                        "source": "pulse",
                        "command": "learning status",
                    }
                ],
            },
        )

        self.assertEqual(brief.get("level"), "steady")
        self.assertEqual(brief.get("repair_order_count"), 0)
        self.assertEqual(brief.get("advisory_count"), 2)

        feed = feed_core_health_brief_to_work_tree(brief, work_tree_module=work_tree)
        self.assertEqual(feed.get("status"), "clear")
        self.assertEqual(feed.get("added_count"), 0)
        self.assertEqual(feed.get("tree_id"), seeded.get("tree_id"))
        self.assertEqual(feed.get("resolved_count"), 1)
        tasks = work_tree.list_tree_tasks(str(seeded.get("tree_id")))
        self.assertEqual([getattr(task.status, "value", task.status) for task in tasks], ["complete"])

    def test_enforced_cleanup_pressure_is_advisory_not_repair(self):
        brief = build_core_health_brief(
            core_steward={
                "level": "strong",
                "maintenance_queue": [
                    {
                        "priority": "medium",
                        "title": "Review cleanup pressure",
                        "reason": "Kidney is actively enforcing cleanup and reported 1 candidate(s) this cycle.",
                        "command": "kidney dry-run",
                    }
                ],
            }
        )

        self.assertEqual(brief.get("level"), "steady")
        self.assertEqual(brief.get("repair_order_count"), 0)
        self.assertEqual(brief.get("advisory_count"), 1)

    def test_feed_brief_creates_deduped_core_health_work_tree(self):
        brief = build_core_health_brief(
            core_steward={
                "level": "repair",
                "maintenance_queue": [
                    {
                        "priority": "high",
                        "title": "Recover core runtime",
                        "reason": "Heartbeat or core-state health is degraded.",
                        "command": "nova runtime-status",
                    }
                ],
            }
        )

        first = feed_core_health_brief_to_work_tree(brief, work_tree_module=work_tree)
        second = feed_core_health_brief_to_work_tree(brief, work_tree_module=work_tree)

        self.assertTrue(first.get("ok"))
        self.assertTrue(first.get("created"))
        self.assertEqual(first.get("added_count"), 1)
        self.assertEqual(second.get("status"), "deduped")
        self.assertEqual(second.get("added_count"), 0)
        self.assertEqual(first.get("tree_id"), second.get("tree_id"))

        tree = work_tree.get_tree(str(first.get("tree_id")))
        self.assertIsNotNone(tree)
        self.assertEqual((tree.meta or {}).get("work_identity_key"), CORE_HEALTH_WORK_IDENTITY)
        self.assertEqual(len(work_tree.list_tree_tasks(tree.tree_id)), 1)


if __name__ == "__main__":
    unittest.main()
