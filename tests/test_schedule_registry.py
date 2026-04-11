import unittest

from services.schedule_registry import (
    SCHEDULE_REGISTRY,
    SCHEDULED_TASKS,
    MAINTENANCE_CYCLE_INTERVAL_SEC,
    get_schedule_status,
    get_task,
)


class TestScheduleRegistry(unittest.TestCase):
    def test_all_task_names_are_unique(self):
        names = [t.name for t in SCHEDULED_TASKS]
        self.assertEqual(len(names), len(set(names)))

    def test_required_tasks_are_registered(self):
        names = {t.name for t in SCHEDULED_TASKS}
        for expected in (
            "core_heartbeat",
            "guard_poll",
            "maintenance_launcher",
            "subconscious_pack",
            "generated_queue",
            "kidney_cleanup",
            "work_tree_cycle",
            "daily_regression",
        ):
            self.assertIn(expected, names, f"missing task: {expected}")

    def test_work_tree_cycle_is_per_maintenance_cycle(self):
        task = get_task("work_tree_cycle")
        self.assertIsNotNone(task)
        self.assertEqual(task.trigger, "per_maintenance_cycle")
        self.assertEqual(task.interval_sec, MAINTENANCE_CYCLE_INTERVAL_SEC)
        self.assertEqual(task.owner, "autonomy_maintenance.py")
        self.assertEqual(task.state_key, "last_work_tree_cycle")

    def test_get_schedule_status_returns_all_tasks(self):
        rows = get_schedule_status({})
        self.assertEqual(len(rows), len(SCHEDULED_TASKS))
        for row in rows:
            for field in ("name", "label", "owner", "trigger", "interval_sec", "description", "last_run_at", "last_run_status"):
                self.assertIn(field, row, f"missing field '{field}' in task '{row.get('name')}'")

    def test_get_schedule_status_merges_live_state(self):
        state = {
            "last_work_tree_cycle": {"ts": "2026-04-10 09:00:00", "status": "ok"},
            "last_kidney_status": {"ts": "2026-04-10 09:01:00"},
            "last_generated_queue_run": {"ts": "2026-04-10 09:02:00", "status": "clear"},
            "last_regression_date": "2026-04-10",
            "last_regression_status": "OK",
            "runtime_worker": {"last_completed_at": "2026-04-10 09:05:00", "last_cycle_status": "ok"},
        }
        rows = {r["name"]: r for r in get_schedule_status(state)}

        self.assertEqual(rows["work_tree_cycle"]["last_run_at"], "2026-04-10 09:00:00")
        self.assertEqual(rows["work_tree_cycle"]["last_run_status"], "ok")
        self.assertEqual(rows["kidney_cleanup"]["last_run_at"], "2026-04-10 09:01:00")
        self.assertEqual(rows["generated_queue"]["last_run_status"], "clear")
        self.assertEqual(rows["daily_regression"]["last_run_at"], "2026-04-10")
        self.assertEqual(rows["daily_regression"]["last_run_status"], "OK")
        self.assertEqual(rows["maintenance_launcher"]["last_run_at"], "2026-04-10 09:05:00")

    def test_get_schedule_status_tolerates_empty_state(self):
        rows = get_schedule_status(None)
        self.assertEqual(len(rows), len(SCHEDULED_TASKS))
        for row in rows:
            self.assertIn(row["last_run_at"], ("", None, row["last_run_at"]))

    def test_schedule_registry_singleton_exposes_helpers(self):
        self.assertIs(SCHEDULE_REGISTRY.scheduled_tasks, SCHEDULED_TASKS)
        self.assertIsNotNone(SCHEDULE_REGISTRY.get_task("daily_regression"))
        rows = SCHEDULE_REGISTRY.get_schedule_status({})
        self.assertIsInstance(rows, list)


if __name__ == "__main__":
    unittest.main()
