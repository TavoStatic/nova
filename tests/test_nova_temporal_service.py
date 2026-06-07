from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from services.nova_calendar_ingestion import normalize_calendar_event, parse_ics_file, parse_ics_text
from services.nova_scheduler import NovaSchedulerService
from services.nova_temporal_service import (
    TemporalEvent,
    TemporalPressure,
    NovaTemporalService,
    build_temporal_pressure,
)


class TestTemporalPressure(unittest.TestCase):
    def test_scores_proximity_and_routes_to_work_tree_for_immediate_deadline(self):
        event = TemporalEvent(
            source="ics",
            title="PEIMS submission",
            start=datetime(2026, 6, 6, 12, 0, tzinfo=timezone.utc),
            confidence="confirmed",
            importance=1.0,
            dependency_risk=1.0,
            stale_evidence=0.8,
            operator_context=0.5,
        )
        pressure = TemporalPressure.from_event(
            event,
            now=datetime(2026, 6, 6, 9, 0, tzinfo=timezone.utc),
        )

        self.assertEqual(pressure.proximity_band, "immediate")
        self.assertEqual(pressure.output_path, "work_tree")
        self.assertEqual(pressure.recommended_action, "surface_to_work_tree")
        self.assertGreaterEqual(pressure.final_score, 75.0)

    def test_background_awareness_stays_silent(self):
        event = TemporalEvent(
            source="ics",
            title="Far future reminder",
            start=datetime(2026, 8, 1, 9, 0, tzinfo=timezone.utc),
        )
        pressure = build_temporal_pressure(event, now=datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc))

        self.assertEqual(pressure.proximity_band, "background awareness")
        self.assertEqual(pressure.output_path, "scheduled_job")
        self.assertLess(pressure.final_score, 45.0)


class TestNovaTemporalService(unittest.TestCase):
    def test_assess_many_groups_results_by_pressure(self):
        service = NovaTemporalService()
        events = [
            TemporalEvent(source="ics", title="Immediate", start=datetime(2026, 6, 2, 9, 0, tzinfo=timezone.utc), importance=1.0),
            TemporalEvent(source="ics", title="Tracked", start=datetime(2026, 6, 20, 9, 0, tzinfo=timezone.utc), importance=0.2),
        ]

        results = service.assess_many(events, now=datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc))

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].output_path, "work_tree")
        self.assertIn(results[1].output_path, {"scheduled_job", "outbox"})

    def test_route_pressure_returns_structured_payload(self):
        service = NovaTemporalService()
        event = TemporalEvent(source="ics", title="PEIMS deadline", start=datetime(2026, 6, 2, 9, 0, tzinfo=timezone.utc), importance=1.0)
        pressure = service.assess(event, now=datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc))

        payload = service.route_pressure(pressure)

        self.assertEqual(payload["kind"], "work_tree")
        self.assertEqual(payload["title"], "PEIMS deadline")
        self.assertIn("pressure", payload)


class TestCalendarIngestion(unittest.TestCase):
    def test_parse_ics_text_extracts_event(self):
        ics_text = """BEGIN:VCALENDAR
BEGIN:VEVENT
UID:deadbeef
SUMMARY:PEIMS deadline
DTSTART;TZID=America/Chicago:20260610T090000
DTEND;TZID=America/Chicago:20260610T100000
STATUS:CONFIRMED
END:VEVENT
END:VCALENDAR
"""

        events = parse_ics_text(ics_text)

        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event.title, "PEIMS deadline")
        self.assertIsNotNone(event.start)
        self.assertEqual(event.timezone, "America/Chicago")
        self.assertEqual(event.confidence, "CONFIRMED")

    def test_parse_ics_file_reads_event(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "calendar.ics"
            path.write_text(
                "BEGIN:VCALENDAR\nBEGIN:VEVENT\nSUMMARY:Review\nDTSTART:20260610T090000Z\nEND:VEVENT\nEND:VCALENDAR\n",
                encoding="utf-8",
            )
            events = parse_ics_file(path)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].title, "Review")

    def test_normalize_calendar_event_accepts_dict(self):
        event = normalize_calendar_event({"summary": "Lunch", "start": "2026-06-10T12:00:00-05:00"})

        self.assertEqual(event.title, "Lunch")
        self.assertEqual(event.source, "ics")


class TestNovaSchedulerService(unittest.TestCase):
    def test_falls_back_when_apscheduler_unavailable(self):
        service = NovaSchedulerService(backend_factory=lambda: None)

        scheduler = service.scheduler()

        self.assertIsNone(scheduler)
        self.assertFalse(service.available)
        self.assertEqual(service.backend_name, "apscheduler-unavailable")

    def test_add_job_raises_without_backend(self):
        service = NovaSchedulerService(backend_factory=lambda: None)

        with self.assertRaises(RuntimeError):
            service.add_job(lambda: None, "date")


if __name__ == "__main__":
    unittest.main()
