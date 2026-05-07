from pathlib import Path
import subprocess
import unittest

from services.nova_self_status import build_repo_change_snapshot, build_self_status_payload, read_recent_ops_events, render_self_status


def test_self_status_reports_hurt_failure_and_update_signals(tmp_path: Path) -> None:
    payload = build_self_status_payload(
        pulse_payload={
            "ollama_up": False,
            "memory_ok": True,
            "routing_stable": True,
            "last_fallback_overuse_score": 0.2,
            "last_regression_status": "FAILED: test_runtime",
            "approved_eligible_previews": 1,
            "ready_for_validated_apply": True,
            "update_zip_path": "C:/Nova/updates/demo.zip",
            "patch_activity": {"rollback_count": 1, "behavior_fail_count": 0},
        },
        recent_ops_events=[],
    )

    assert payload["level"] == "failed"
    titles = [event["title"] for event in payload["events"]]
    assert "Model runtime is offline" in titles
    assert "Patch rollback pressure is present" in titles
    assert "Validated update is waiting" in titles

    rendered = render_self_status(payload)
    assert "Nova Self Status" in rendered
    assert "Level: failed" in rendered
    assert "update now" in rendered


def test_self_status_reads_ops_journal_and_classifies_update_activity(tmp_path: Path) -> None:
    journal = tmp_path / "ops_journal.jsonl"
    journal.write_text(
        '{"category":"patch","action":"preview","result":"ok","detail":"preview ready"}\n'
        '{"category":"runtime","action":"health_check","result":"error","detail":"heartbeat stale"}\n',
        encoding="utf-8",
    )

    events = read_recent_ops_events(journal)
    payload = build_self_status_payload(
        pulse_payload={
            "ollama_up": True,
            "memory_ok": True,
            "routing_stable": True,
            "last_fallback_overuse_score": 0.1,
            "last_regression_status": "ok",
            "patch_activity": {},
        },
        recent_ops_events=events,
    )

    assert payload["level"] == "failed"
    rendered = render_self_status(payload)
    assert "heartbeat stale" in rendered
    assert "patch preview moved through ok" in rendered


def test_self_status_is_steady_without_signals() -> None:
    payload = build_self_status_payload(
        pulse_payload={
            "ollama_up": True,
            "memory_ok": True,
            "routing_stable": True,
            "last_fallback_overuse_score": 0.1,
            "last_regression_status": "ok",
            "patch_activity": {},
        },
        recent_ops_events=[],
    )

    assert payload["level"] == "steady"
    assert payload["events"] == []
    assert "No current hurt" in render_self_status(payload)


def test_self_status_ignores_stale_regression_failure() -> None:
    payload = build_self_status_payload(
        pulse_payload={
            "ollama_up": True,
            "memory_ok": True,
            "routing_stable": True,
            "last_fallback_overuse_score": 0.1,
            "last_regression_status": "FAILED",
            "last_regression_stale": True,
            "patch_activity": {},
        },
        recent_ops_events=[],
    )

    assert payload["level"] == "steady"
    assert "Latest regression is not green" not in render_self_status(payload)


def test_self_status_keeps_green_fallback_history_out_of_active_status() -> None:
    payload = build_self_status_payload(
        pulse_payload={
            "ollama_up": True,
            "memory_ok": True,
            "routing_stable": True,
            "last_fallback_overuse_score": 0.0,
            "active_fallback_overuse_score": 0.0,
            "raw_fallback_overuse_score": 0.97,
            "fallback_pressure_active": False,
            "last_generated_queue_report_status": "green",
            "last_regression_status": "ok",
            "patch_activity": {},
        },
        recent_ops_events=[],
    )

    assert payload["level"] == "steady"
    rendered = render_self_status(payload)
    assert "Fallback training pressure is being worked" not in rendered
    assert "Level: hurting" not in rendered


class TestNovaSelfStatusService(unittest.TestCase):
    def test_self_status_reports_memory_health_watch(self) -> None:
        payload = build_self_status_payload(
            pulse_payload={
                "ollama_up": True,
                "memory_ok": False,
                "memory_health": {
                    "ok": False,
                    "status": "watch",
                    "issues": [
                        {
                            "code": "learned_facts_orphan_tmp",
                            "detail": "learned_facts has a valid tmp file but no final JSON file.",
                        }
                    ],
                },
                "routing_stable": True,
                "last_fallback_overuse_score": 0.1,
                "last_regression_status": "ok",
                "patch_activity": {},
            },
            recent_ops_events=[],
        )

        self.assertEqual(payload["level"], "hurting")
        rendered = render_self_status(payload)
        self.assertIn("Memory health needs attention", rendered)
        self.assertIn("learned_facts_orphan_tmp", rendered)

    def test_self_status_reports_local_code_change_with_validation(self) -> None:
        payload = build_self_status_payload(
            pulse_payload={
                "ollama_up": True,
                "memory_ok": True,
                "routing_stable": True,
                "last_fallback_overuse_score": 0.1,
                "last_regression_status": "OK",
                "patch_activity": {},
            },
            recent_ops_events=[],
            repo_change_snapshot={
                "ok": True,
                "status": "dirty",
                "changed_count": 1,
                "insertions": 0,
                "deletions": 2,
                "files": [{"path": "nova_core.py", "status": "M", "insertions": 0, "deletions": 2}],
            },
        )

        self.assertEqual(payload["level"], "updating")
        rendered = render_self_status(payload)
        self.assertIn("Local code changed since last accepted state", rendered)
        self.assertIn("nova_core.py", rendered)
        self.assertIn("latest regression is OK", rendered)

    def test_repo_change_snapshot_parses_git_status_and_numstat(self) -> None:
        def fake_run(cmd, **_kwargs):
            if cmd[1:] == ["status", "--short"]:
                return subprocess.CompletedProcess(cmd, 0, stdout=" M nova_core.py\n?? scratch.txt\n", stderr="")
            if cmd[1:] == ["diff", "--numstat", "HEAD", "--"]:
                return subprocess.CompletedProcess(cmd, 0, stdout="3\t2\tnova_core.py\n", stderr="")
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="unexpected")

        snapshot = build_repo_change_snapshot(Path("C:/Nova"), subprocess_run=fake_run)

        self.assertTrue(snapshot.get("ok"))
        self.assertEqual(snapshot.get("status"), "dirty")
        self.assertEqual(snapshot.get("changed_count"), 2)
        self.assertEqual(snapshot.get("insertions"), 3)
        self.assertEqual(snapshot.get("deletions"), 2)
        self.assertEqual([item.get("path") for item in snapshot.get("files")], ["nova_core.py", "scratch.txt"])
