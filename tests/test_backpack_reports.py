from __future__ import annotations

import unittest
from unittest import mock

from services.backpack_host.reports import (
    list_report_intents,
    resolve_report_intent,
    run_backpack_report,
)


class TestBackpackReports(unittest.TestCase):
    def test_list_intents_includes_schools(self) -> None:
        intents = {i["intent"] for i in list_report_intents("edfi")}
        self.assertIn("schools", intents)
        self.assertIn("health", intents)

    def test_resolve_aliases(self) -> None:
        meta = resolve_report_intent("show schools", backpack_id="edfi")
        self.assertIsNotNone(meta)
        self.assertEqual(meta["operation"], "list_schools")
        self.assertEqual(meta["intent"], "schools")

    def test_run_schools_report_uses_host(self) -> None:
        fake = {
            "ok": True,
            "summary": "2 school(s): Alpha, Beta.",
            "report_intent": "schools_directory",
            "columns": ["school_id", "school_name", "lea_id"],
            "rows": [
                {"school_id": "1", "school_name": "Alpha", "lea_id": "031901"},
                {"school_id": "2", "school_name": "Beta", "lea_id": "031901"},
            ],
            "row_count": 2,
            "connection_id": "district-main",
            "district_lea_id": "31901",
            "governed_route": "backpack_host",
        }
        with mock.patch(
            "services.backpack_host.query.run_backpack_query",
            return_value=fake,
        ) as q, mock.patch(
            "services.edfi.extract_store.save_extract",
            return_value=__import__("pathlib").Path("runtime/edfi/extracts/edfi/default_conn/031901/schools.json"),
        ) as save:
            report = run_backpack_report(
                "schools",
                role="standard_user",
                limit=10,
                prefer_local=False,
                force_refresh=True,
                use_cache=False,
            )
        q.assert_called_once()
        self.assertEqual(q.call_args.args[0], "edfi")
        self.assertEqual(q.call_args.args[1], "list_schools")
        self.assertTrue(report["ok"])
        self.assertEqual(report["intent"], "schools")
        self.assertEqual(report["row_count"], 2)
        self.assertIn("Alpha", report["summary"])
        self.assertEqual(report["rows"][0]["school_name"], "Alpha")
        self.assertTrue(report.get("extract_saved"))
        save.assert_called_once()

    def test_unknown_intent(self) -> None:
        report = run_backpack_report("payroll")
        self.assertFalse(report["ok"])
        self.assertIn("unknown_report_intent", report["error"])

    def test_health_report_uses_local_profile_without_query(self) -> None:
        fake_profile = {
            "ok": True,
            "connection_id": "district-main",
            "district_lea_id": "031901",
            "health": "ok",
            "resource_count": 10,
            "auth_ok": True,
        }
        with mock.patch(
            "services.edfi.inventory.profile_summary",
            return_value=fake_profile,
        ), mock.patch(
            "services.backpack_host.query.run_backpack_query",
        ) as q:
            report = run_backpack_report("health", force_refresh=False, prefer_local=True)
        q.assert_not_called()
        self.assertTrue(report["ok"])
        self.assertFalse(report.get("live_pull"))
        self.assertIn("local profile", report["summary"].lower())

    def test_rate_limit_is_friendly(self) -> None:
        from services.backpack_host import reports as reports_mod

        reports_mod.clear_report_cache()
        reports_mod._RATE_LIMIT_COOLDOWN_UNTIL = 0.0
        fake = {
            "ok": False,
            "error": '{ "operation" : "ratelimited" }',
            "error_code": "edfi_rate_limited",
            "rate_limited": True,
        }
        with mock.patch(
            "services.backpack_host.query.run_backpack_query",
            return_value=fake,
        ):
            report = run_backpack_report("schools", retry_on_rate_limit=False, use_cache=False)
        self.assertFalse(report["ok"])
        self.assertTrue(report.get("rate_limited"))
        self.assertIn("rate limit", report["error"].lower())
        reports_mod._RATE_LIMIT_COOLDOWN_UNTIL = 0.0


if __name__ == "__main__":
    unittest.main()
