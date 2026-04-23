import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from services.test_session_control import TEST_SESSION_CONTROL_SERVICE


class TestTestSessionControlService(unittest.TestCase):
    def test_saved_session_library_excludes_subconscious_generated_artifacts(self):
        saved_root = Path(__file__).resolve().parents[1] / "tests" / "sessions"
        misplaced = []

        for path in saved_root.rglob("*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if str(payload.get("source") or "").strip() == "subconscious_generated":
                misplaced.append(path.relative_to(saved_root).as_posix())

        self.assertEqual(misplaced, [])

    def test_definition_root_helpers_build_saved_and_generated_paths(self):
        roots = TEST_SESSION_CONTROL_SERVICE.all_test_session_definition_roots(
            base_dir=Path("c:/Nova"),
            runtime_dir=Path("c:/Nova/runtime"),
        )

        self.assertEqual(
            roots,
            [
                (Path("c:/Nova/tests/sessions"), "saved"),
                (Path("c:/Nova/runtime/test_sessions/generated_definitions"), "generated"),
            ],
        )

    def test_generated_queue_operator_note_delegates_to_helper(self):
        note = TEST_SESSION_CONTROL_SERVICE.generated_queue_operator_note(
            {
                "file": "high_drift.json",
                "latest_status": "drift",
                "highest_priority": {"signal": "route_fit_weak", "urgency": "high"},
            }
        )

        self.assertIn("high_drift.json", note)
        self.assertIn("route_fit_weak", note)

    def test_generated_queue_investigate_action_passes_payload_fields(self):
        captured = {}

        ok, msg, extra, detail = TEST_SESSION_CONTROL_SERVICE.generated_queue_investigate_action(
            {"file": "high_drift.json", "session_id": "operator-generated-queue", "user_id": "operator"},
            investigate_generated_work_queue_item_fn=lambda session_file, session_id="", user_id="": captured.update({
                "session_file": session_file,
                "session_id": session_id,
                "user_id": user_id,
            }) or (True, "generated_work_queue_investigation_started", {"selected": {"file": session_file}}),
        )

        self.assertTrue(ok)
        self.assertEqual(msg, "generated_work_queue_investigation_started")
        self.assertEqual(detail, msg)
        self.assertEqual(captured, {"session_file": "high_drift.json", "session_id": "operator-generated-queue", "user_id": "operator"})
        self.assertEqual((extra.get("selected") or {}).get("file"), "high_drift.json")

    def test_investigate_generated_work_queue_item_assembles_operator_dependencies(self):
        queue_payload = {
            "count": 1,
            "open_count": 1,
            "next_item": {
                "file": "high_drift.json",
                "latest_status": "drift",
                "open": True,
                "highest_priority": {"signal": "route_fit_weak", "urgency": "high"},
                "latest_comparison": {"diffs": [{"turn": 1, "issues": {"assistant": {}}}]},
            },
            "items": [],
        }
        summary = {"session_id": "operator-generated-queue", "owner": "operator", "turn_count": 2}
        macro = {"macro_id": "subconscious-review", "prompt": "Review the latest subconscious run and recommend what to run next."}
        captured = {}

        ok, msg, extra = TEST_SESSION_CONTROL_SERVICE.investigate_generated_work_queue_item(
            generated_work_queue_fn=lambda limit=24: queue_payload,
            resolve_operator_macro_fn=lambda macro_id: macro,
            render_operator_macro_prompt_fn=lambda macro_payload, values, note="": (
                True,
                f"Macro:{macro_payload.get('macro_id')}\n{note}",
                {"note": note},
            ),
            normalize_user_id_fn=lambda value: value,
            assert_session_owner_fn=lambda sid, uid: (True, "owner_bound"),
            process_chat_fn=lambda sid, text, user_id="": captured.update({"sid": sid, "text": text, "user_id": user_id}) or "Investigated queue item.",
            session_summaries_fn=lambda limit=20: [summary],
        )

        self.assertTrue(ok)
        self.assertEqual(msg, "generated_work_queue_investigation_started")
        self.assertEqual((extra.get("selected") or {}).get("file"), "high_drift.json")
        self.assertEqual((extra.get("macro") or {}).get("macro_id"), "subconscious-review")
        self.assertEqual(captured.get("sid"), "operator-generated-queue")
        self.assertIn("high_drift.json", captured.get("text", ""))
        self.assertIn("route_fit_weak", captured.get("text", ""))

    def test_available_test_session_definitions_merges_saved_and_generated(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            saved_dir = base / "tests" / "sessions"
            generated_dir = base / "runtime" / "test_sessions" / "generated_definitions"
            saved_dir.mkdir(parents=True, exist_ok=True)
            generated_dir.mkdir(parents=True, exist_ok=True)
            (saved_dir / "saved.json").write_text(json.dumps({"name": "Saved", "messages": ["one"]}, ensure_ascii=True), encoding="utf-8")
            (generated_dir / "generated.json").write_text(json.dumps({"name": "Generated", "messages": ["one", "two"]}, ensure_ascii=True), encoding="utf-8")
            (generated_dir / "latest_manifest.json").write_text(json.dumps({"definition_count": 1}, ensure_ascii=True), encoding="utf-8")

            payload = TEST_SESSION_CONTROL_SERVICE.available_test_session_definitions(
                [(saved_dir, "saved"), (generated_dir, "generated")],
                limit=10,
            )

        self.assertEqual(len(payload), 2)
        self.assertEqual({item.get("file"): item.get("origin") for item in payload}, {"saved.json": "saved", "generated.json": "generated"})

    def test_available_test_session_definitions_reads_nested_real_world_tasks(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            saved_dir = base / "tests" / "sessions"
            nested_dir = saved_dir / "real_world"
            nested_dir.mkdir(parents=True, exist_ok=True)
            (nested_dir / "release_check.json").write_text(
                json.dumps(
                    {
                        "name": "Release check",
                        "task_id": "release_check",
                        "source": "real_world",
                        "category": "release",
                        "objective": "Assess ship readiness.",
                        "messages": ["Assess ship readiness."],
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )

            payload = TEST_SESSION_CONTROL_SERVICE.available_test_session_definitions(
                [(saved_dir, "saved")],
                limit=10,
            )

        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0].get("file"), "real_world/release_check.json")
        self.assertEqual(payload[0].get("source"), "real_world")
        self.assertEqual(payload[0].get("category"), "release")
        self.assertEqual(payload[0].get("task_id"), "release_check")

    def test_create_real_world_task_definition_writes_generated_task_file(self):
        with tempfile.TemporaryDirectory() as td:
            runtime_dir = Path(td) / "runtime"
            ok, msg, extra = TEST_SESSION_CONTROL_SERVICE.create_real_world_task_definition(
                {
                    "name": "Operator Handoff Audit",
                    "category": "handoff",
                    "objective": "Audit the package handoff path.",
                    "prompt": "Pretend I am a new operator and audit the handoff path.",
                    "followup": "What is the first fix?",
                    "notes": "Seeded from control center.",
                },
                runtime_dir=runtime_dir,
                available_definitions_fn=lambda limit: TEST_SESSION_CONTROL_SERVICE.available_test_session_definitions(
                    [(runtime_dir / "test_sessions" / "generated_definitions", "generated")],
                    limit=limit,
                ),
            )

            task_path = runtime_dir / "test_sessions" / "generated_definitions" / "real_world" / "operator_handoff_audit.json"
            task_payload = json.loads(task_path.read_text(encoding="utf-8"))

        self.assertTrue(ok)
        self.assertEqual(msg, "real_world_task_created:real_world/operator_handoff_audit.json")
        self.assertEqual(task_payload.get("source"), "real_world")
        self.assertEqual(task_payload.get("category"), "handoff")
        self.assertEqual(
            task_payload.get("messages"),
            [
                "Pretend I am a new operator and audit the handoff path.",
                "What is the first fix?",
            ],
        )
        self.assertEqual((extra.get("task") or {}).get("file"), "real_world/operator_handoff_audit.json")

    def test_test_session_report_summaries_surface_status_and_artifacts(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "test_sessions"
            run_dir = root / "demo_run"
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "result.json").write_text(
                json.dumps(
                    {
                        "session": {"name": "Demo", "path": "C:/Nova/tests/sessions/demo.json", "messages": ["a", "b"]},
                        "comparison": {
                            "turn_count_match": True,
                            "cli_turns": 2,
                            "http_turns": 2,
                            "diffs": [],
                            "cli_flagged_probes": [{"turn": 1}],
                            "http_flagged_probes": [],
                        },
                        "cli": {"artifacts": {"mode_dir": "cli_dir"}},
                        "http": {"artifacts": {"mode_dir": "http_dir"}},
                        "generated_at": "2026-03-31 12:00:00",
                    },
                    ensure_ascii=True,
                    indent=2,
                ),
                encoding="utf-8",
            )

            payload = TEST_SESSION_CONTROL_SERVICE.test_session_report_summaries(root, limit=10)

        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0].get("status"), "warning")
        self.assertEqual((payload[0].get("comparison") or {}).get("flagged_probe_count"), 1)
        self.assertEqual(((payload[0].get("artifacts") or {}).get("cli_mode_dir")), "cli_dir")

    def test_generated_work_queue_prefers_open_priority_items(self):
        definitions = [
            {"file": "low_green.json", "name": "Low green", "origin": "generated", "training_priorities": [{"urgency": "low", "robustness": 0.2}], "fingerprint": "low"},
            {"file": "high_drift.json", "name": "High drift", "origin": "generated", "training_priorities": [{"urgency": "high", "robustness": 0.9}], "fingerprint": "high"},
            {"file": "medium_new.json", "name": "Medium new", "origin": "generated", "training_priorities": [{"urgency": "medium", "robustness": 0.7}], "fingerprint": "medium"},
        ]
        reports = [
            {"run_id": "high_drift_1", "session_path": "c:/Nova/runtime/test_sessions/generated_definitions/high_drift.json", "status": "drift", "comparison": {"diff_count": 1}, "report_path": "c:/Nova/runtime/test_sessions/high_drift/result.json"},
            {"run_id": "low_green_1", "session_path": "c:/Nova/runtime/test_sessions/generated_definitions/low_green.json", "status": "green", "comparison": {"diff_count": 0}, "report_path": "c:/Nova/runtime/test_sessions/low_green/result.json"},
        ]

        queue = TEST_SESSION_CONTROL_SERVICE.generated_work_queue(definitions, reports, limit=10)

        self.assertEqual(queue.get("open_count"), 2)
        self.assertEqual((queue.get("next_item") or {}).get("file"), "high_drift.json")
        self.assertEqual([item.get("file") for item in (queue.get("items") or [])][:3], ["high_drift.json", "medium_new.json", "low_green.json"])

    def test_generated_work_queue_skips_action_on_current_drift_when_already_reviewed(self):
        definitions = [
            {"file": "high_drift.json", "name": "High drift", "origin": "generated", "training_priorities": [{"urgency": "high", "robustness": 0.9}], "fingerprint": "same"},
            {"file": "medium_new.json", "name": "Medium new", "origin": "generated", "training_priorities": [{"urgency": "medium", "robustness": 0.7}], "fingerprint": "new"},
        ]
        reports = [
            {"run_id": "high_drift_1", "session_path": "c:/Nova/runtime/test_sessions/generated_definitions/high_drift.json", "status": "drift", "comparison": {"diff_count": 1}, "report_path": "c:/Nova/runtime/test_sessions/high_drift/result.json"},
        ]

        with tempfile.TemporaryDirectory() as td:
            runtime_dir = Path(td) / "runtime"
            audit_path = runtime_dir / "test_sessions" / "promotion_audit.jsonl"
            audit_path.parent.mkdir(parents=True, exist_ok=True)
            audit_path.write_text(json.dumps({"file": "high_drift.json", "fingerprint": "same"}) + "\n", encoding="utf-8")

            queue = TEST_SESSION_CONTROL_SERVICE.generated_work_queue(definitions, reports, limit=10, runtime_dir=runtime_dir)

        self.assertEqual(queue.get("open_count"), 2)
        self.assertEqual(queue.get("actionable_count"), 1)
        self.assertEqual((queue.get("next_item") or {}).get("file"), "medium_new.json")

    def test_run_next_generated_work_queue_item_returns_blocked_when_open_items_are_not_actionable(self):
        ok, msg, extra = TEST_SESSION_CONTROL_SERVICE.run_next_generated_work_queue_item(
            generated_work_queue_fn=lambda limit: {"next_item": {}, "items": [{"file": "high_drift.json", "open": True}], "open_count": 1},
            run_test_session_definition_fn=lambda session_file: (True, "ok", {}),
        )

        self.assertTrue(ok)
        self.assertEqual(msg, "generated_work_queue_blocked")
        self.assertEqual(extra.get("selected"), {})

    def test_resolve_test_session_definition_accepts_absolute_or_catalog_lookup(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            session_path = root / "demo.json"
            session_path.write_text(json.dumps({"messages": ["hello"]}, ensure_ascii=True), encoding="utf-8")

            absolute = TEST_SESSION_CONTROL_SERVICE.resolve_test_session_definition(str(session_path), [])
            catalog = TEST_SESSION_CONTROL_SERVICE.resolve_test_session_definition("demo.json", [{"file": "demo.json", "path": str(session_path)}])

        self.assertEqual(absolute, session_path)
        self.assertEqual(catalog, session_path)

    def test_run_test_session_definition_executes_runner_and_returns_reports(self):
        import sys
        completed = SimpleNamespace(returncode=0, stdout="Saved full report", stderr="")
        _py = Path(sys.executable)  # guaranteed to exist on any platform

        ok, msg, extra = TEST_SESSION_CONTROL_SERVICE.run_test_session_definition(
            "demo.json",
            runner_path=_py,
            venv_python=_py,
            base_dir=_py.parent,
            resolve_definition_fn=lambda name: _py,
            available_definitions_fn=lambda limit: [{"file": "demo.json"}],
            report_summaries_fn=lambda limit: [{"run_id": "demo_run", "status": "green"}],
            subprocess_run=lambda *args, **kwargs: completed,
        )

        self.assertTrue(ok)
        self.assertEqual(msg, "test_session_run_completed:demo.json")
        self.assertEqual((extra.get("latest_report") or {}).get("run_id"), "demo_run")
        self.assertEqual((extra.get("definitions") or [])[0].get("file"), "demo.json")

    def test_run_generated_test_session_pack_priority_orders_highest_first(self):
        definitions = [
            {"file": "low.json", "name": "Low", "origin": "generated", "training_priorities": [{"urgency": "low", "robustness": 0.4}]},
            {"file": "high.json", "name": "High", "origin": "generated", "training_priorities": [{"urgency": "high", "robustness": 0.9}]},
            {"file": "saved.json", "name": "Saved", "origin": "saved", "training_priorities": []},
        ]
        executed: list[str] = []

        ok, msg, extra = TEST_SESSION_CONTROL_SERVICE.run_generated_test_session_pack(
            2,
            mode="priority",
            available_definitions_fn=lambda limit: definitions,
            run_test_session_definition_fn=lambda session_file: executed.append(session_file) or (True, f"ok:{session_file}", {"latest_report": {"run_id": session_file}}),
            report_summaries_fn=lambda limit: [{"run_id": "latest", "status": "green"}],
            generated_work_queue_fn=lambda limit: {"count": 1, "items": []},
        )

        self.assertTrue(ok)
        self.assertEqual(msg, "generated_test_sessions_run_priority_completed:2")
        self.assertEqual(executed, ["high.json", "low.json"])
        self.assertEqual((extra.get("latest_report") or {}).get("run_id"), "latest")

    def test_run_next_generated_work_queue_item_returns_clear_when_empty(self):
        ok, msg, extra = TEST_SESSION_CONTROL_SERVICE.run_next_generated_work_queue_item(
            generated_work_queue_fn=lambda limit: {"next_item": {}, "items": []},
            run_test_session_definition_fn=lambda session_file: (True, "ok", {}),
        )

        self.assertTrue(ok)
        self.assertEqual(msg, "generated_work_queue_clear")
        self.assertEqual(extra.get("selected"), {})

    def test_generated_pack_run_action_uses_payload_limit_and_mode(self):
        captured = {}

        ok, msg, extra, detail = TEST_SESSION_CONTROL_SERVICE.generated_pack_run_action(
            {"limit": 3, "mode": "priority"},
            run_generated_test_session_pack_fn=lambda limit=0, mode="recent": captured.update({"limit": limit, "mode": mode}) or (True, "generated_test_sessions_run_priority_completed:3", {"count": 3, "mode": mode}),
        )

        self.assertTrue(ok)
        self.assertEqual(msg, "generated_test_sessions_run_priority_completed:3")
        self.assertEqual(detail, msg)
        self.assertEqual(captured, {"limit": 3, "mode": "priority"})
        self.assertEqual(extra.get("count"), 3)



if __name__ == "__main__":
    unittest.main()