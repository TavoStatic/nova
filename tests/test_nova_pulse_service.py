from __future__ import annotations

import json
import shutil
import unittest
import uuid
from pathlib import Path

from services.nova_pulse import _count_definition_files, build_pulse_payload, render_nova_pulse, write_pulse_snapshot


def _workspace_dir() -> Path:
    root = Path(r"C:\Nova") / f"codex_pulse_test_{uuid.uuid4().hex}"
    root.mkdir(parents=True, exist_ok=True)
    return root


def test_build_pulse_payload_and_render_roundtrip() -> None:
    root = _workspace_dir()
    try:
        generated = root / "generated"
        promoted = root / "promoted"
        pending = root / "pending"
        quarantine = root / "quarantine"
        for folder in (generated, promoted, pending, quarantine):
            folder.mkdir(parents=True, exist_ok=True)
        (generated / "g1.json").write_text("{}", encoding="utf-8")
        (promoted / "p1.json").write_text("{}", encoding="utf-8")
        (pending / "w1.json").write_text("{}", encoding="utf-8")
        (quarantine / "q1.json").write_text("{}", encoding="utf-8")

        promotion_audit_log = root / "promotion_audit.jsonl"
        promotion_audit_log.write_text(
            json.dumps({"file": "foo.json", "status": "promoted", "ts": "2026-04-20 10:00:00"}) + "\n",
            encoding="utf-8",
        )
        behavior_metrics_file = root / "behavior.json"
        behavior_metrics_file.write_text(
            json.dumps({"routing_stable": True, "tool_route": 3, "llm_fallback": 1, "last_reflection_at": "recent"}),
            encoding="utf-8",
        )
        autonomy_file = root / "autonomy.json"
        autonomy_file.write_text(
            json.dumps(
                {
                    "last_fallback_overuse_score": 0.97,
                    "last_regression_status": "ok",
                    "last_generated_queue_run": {
                        "status": "actionable",
                        "latest_report_status": "green",
                    },
                }
            ),
            encoding="utf-8",
        )
        pulse_snapshot_file = root / "pulse_snapshot.json"
        patch_log = root / "patch.log"
        patch_log.write_text(
            "2026-04-20 09:00:00 | APPLY patch_a.zip\n"
            "2026-04-20 09:01:00 | APPLY_OK patch_a.zip\n",
            encoding="utf-8",
        )

        def load_json_file(path: Path, default):
            if not path.exists():
                return default
            data = json.loads(path.read_text(encoding="utf-8") or "null")
            return default if data is None else data

        payload = build_pulse_payload(
            promotion_audit_log=promotion_audit_log,
            generated_definitions_dir=generated,
            promoted_definitions_dir=promoted,
            pending_review_dir=pending,
            quarantine_dir=quarantine,
            behavior_metrics_file=behavior_metrics_file,
            autonomy_maintenance_file=autonomy_file,
            pulse_snapshot_file=pulse_snapshot_file,
            patch_log=patch_log,
            load_json_file_fn=load_json_file,
            patch_status_payload_fn=lambda: {
                "current_revision": 7,
                "previews_approved_eligible": 1,
                "ready_for_validated_apply": True,
                "last_patch_log_line": "tail",
            },
            read_patch_log_tail_line_fn=lambda: "tail",
            ollama_api_up_fn=lambda: True,
            mem_stats_payload_fn=lambda emit_event=False: {"ok": True, "total": 12},
            kidney_summary_fn=lambda: {"mode": "dry_run", "candidate_count": 2, "archive_count": 1, "delete_count": 0},
            safety_policy_fn=lambda: {"enabled": True, "mode": "guarded"},
            latest_approved_update_zip_fn=lambda patch: root / "approved.zip",
        )

        assert payload["promoted_total"] == 1
        assert payload["generated_total"] == 1
        assert payload["patch_revision"] == 7
        assert payload["last_regression_stale"] is False
        assert payload["last_generated_queue_report_status"] == "green"
        assert payload["fallback_pressure_active"] is False
        assert payload["raw_fallback_overuse_score"] == 0.97
        assert payload["active_fallback_overuse_score"] == 0.0
        assert payload["last_fallback_overuse_score"] == 0.0
        assert payload["autonomy_level"] == "operational"

        rendered = render_nova_pulse(payload)
        assert "Nova Pulse" in rendered
        assert "patch revision: 7" in rendered
        assert "active fallback pressure score: 0.00" in rendered
        assert "fallback robustness history: 0.97 (not active; queue report is green)" in rendered
        assert "Type \"update now\"" in rendered
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_write_pulse_snapshot_writes_expected_fields() -> None:
    root = _workspace_dir()
    try:
        snapshot_file = root / "runtime" / "pulse_snapshot.json"
        write_pulse_snapshot(
            {
                "generated_at": "2026-04-20 12:00:00",
                "promoted_total": 5,
                "patch_revision": 9,
                "llm_fallback_count": 2,
                "tool_route_count": 4,
            },
            pulse_snapshot_file=snapshot_file,
        )
        saved = json.loads(snapshot_file.read_text(encoding="utf-8"))
        assert saved["promoted_total"] == 5
        assert saved["patch_revision"] == 9
        assert saved["tool_route_count"] == 4
    finally:
        shutil.rmtree(root, ignore_errors=True)


class TestNovaPulseService(unittest.TestCase):
    def test_pulse_counts_nested_generated_definition_files(self) -> None:
        root = _workspace_dir()
        try:
            generated = root / "generated"
            nested = generated / "real_world"
            nested.mkdir(parents=True, exist_ok=True)
            (nested / "stress_location_recall.json").write_text("{}", encoding="utf-8")
            (generated / "latest_manifest.json").write_text("{}", encoding="utf-8")

            self.assertEqual(_count_definition_files(generated), 1)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_live_generated_queue_drift_overrides_stale_maintenance_clear(self) -> None:
        root = _workspace_dir()
        try:
            for folder_name in ("generated", "promoted", "pending", "quarantine"):
                (root / folder_name).mkdir(parents=True, exist_ok=True)
            autonomy_file = root / "autonomy.json"
            autonomy_file.write_text(
                json.dumps(
                    {
                        "last_fallback_overuse_score": 0.97,
                        "last_regression_status": "ok",
                        "last_generated_queue_run": {"status": "clear", "latest_report_status": ""},
                    }
                ),
                encoding="utf-8",
            )
            behavior_file = root / "behavior.json"
            behavior_file.write_text(json.dumps({"routing_stable": True}), encoding="utf-8")
            patch_log = root / "patch.log"
            patch_log.write_text("", encoding="utf-8")

            def load_json_file(path: Path, default):
                return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default

            payload = build_pulse_payload(
                promotion_audit_log=root / "promotion.jsonl",
                generated_definitions_dir=root / "generated",
                promoted_definitions_dir=root / "promoted",
                pending_review_dir=root / "pending",
                quarantine_dir=root / "quarantine",
                behavior_metrics_file=behavior_file,
                autonomy_maintenance_file=autonomy_file,
                pulse_snapshot_file=root / "pulse.json",
                patch_log=patch_log,
                load_json_file_fn=load_json_file,
                patch_status_payload_fn=lambda: {},
                read_patch_log_tail_line_fn=lambda: "",
                ollama_api_up_fn=lambda: True,
                mem_stats_payload_fn=lambda emit_event=False: {"ok": True, "total": 0},
                kidney_summary_fn=lambda: {"mode": "enforce", "candidate_count": 0},
                safety_policy_fn=lambda: {"enabled": True, "mode": "enforce"},
                latest_approved_update_zip_fn=lambda _patch: None,
                generated_work_queue_fn=lambda _limit: {"status": "blocked", "count": 12, "green_count": 10, "drift_count": 2},
            )

            self.assertEqual(payload["last_generated_queue_report_status"], "drift")
            self.assertTrue(payload["fallback_pressure_active"])
            self.assertEqual(payload["active_fallback_overuse_score"], 0.97)
            self.assertEqual(payload["autonomy_level"], "guarded")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_memory_health_watch_marks_pulse_memory_not_ok(self) -> None:
        root = _workspace_dir()
        try:
            for folder_name in ("generated", "promoted", "pending", "quarantine"):
                (root / folder_name).mkdir(parents=True, exist_ok=True)
            behavior_file = root / "behavior.json"
            behavior_file.write_text(json.dumps({"routing_stable": True}), encoding="utf-8")
            autonomy_file = root / "autonomy.json"
            autonomy_file.write_text(json.dumps({"last_regression_status": "ok"}), encoding="utf-8")
            patch_log = root / "patch.log"
            patch_log.write_text("", encoding="utf-8")

            def load_json_file(path: Path, default):
                return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default

            payload = build_pulse_payload(
                promotion_audit_log=root / "promotion.jsonl",
                generated_definitions_dir=root / "generated",
                promoted_definitions_dir=root / "promoted",
                pending_review_dir=root / "pending",
                quarantine_dir=root / "quarantine",
                behavior_metrics_file=behavior_file,
                autonomy_maintenance_file=autonomy_file,
                pulse_snapshot_file=root / "pulse.json",
                patch_log=patch_log,
                load_json_file_fn=load_json_file,
                patch_status_payload_fn=lambda: {},
                read_patch_log_tail_line_fn=lambda: "",
                ollama_api_up_fn=lambda: True,
                mem_stats_payload_fn=lambda emit_event=False: {"ok": True, "total": 12},
                kidney_summary_fn=lambda: {"mode": "enforce", "candidate_count": 0},
                safety_policy_fn=lambda: {"enabled": True, "mode": "enforce"},
                latest_approved_update_zip_fn=lambda _patch: None,
                memory_health_payload_fn=lambda: {
                    "ok": False,
                    "status": "watch",
                    "issue_count": 1,
                    "issues": [{"code": "learned_facts_orphan_tmp", "detail": "valid tmp without final"}],
                    "memory_events_log": {"status": "watch", "byte_count": 128, "invalid_tail_count": 1},
                },
            )

            self.assertFalse(payload["memory_ok"])
            self.assertEqual(payload["memory_health_status"], "watch")
            self.assertEqual(payload["memory_scoped_total"], 12)
            self.assertEqual(payload["memory_db_total"], 12)
            self.assertEqual(payload["memory_events_log_status"], "watch")
            self.assertEqual(payload["memory_events_log_invalid_tail_count"], 1)
            rendered = render_nova_pulse(payload)
            self.assertIn("memory watch", rendered)
            self.assertIn("events=watch", rendered)
            self.assertIn("db_total=12", rendered)
            self.assertIn("learned_facts_orphan_tmp", rendered)
        finally:
            shutil.rmtree(root, ignore_errors=True)
