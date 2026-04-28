import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from services.nova_reply_deterministic import maybe_handle_deterministic_sequence


class TestNovaReplyDeterministic(unittest.TestCase):
    def _call(self, text, **overrides):
        options = {
            "text": text,
            "turns": [("user", "hello"), ("assistant", "Hi there")],
            "low": text.lower(),
            "trace": lambda *args, **kwargs: None,
            "normalize_reply": lambda reply: reply,
            "is_session_recap_request": lambda _text: False,
            "session_recap_reply": lambda turns, user_text: "Recap of this session.",
            "is_assistant_name_query": lambda _text: False,
            "assistant_name_reply": lambda user_text: "My name is Nova.",
            "is_developer_full_name_query": lambda _text: False,
            "developer_full_name_reply": lambda: "Gustavo Uribe",
            "is_name_origin_question": lambda _text: False,
            "is_student_data_attendance_rules_query": lambda _text: False,
            "student_data_attendance_rules_reply": lambda: "attendance reply",
            "is_developer_profile_request": lambda _text: False,
            "developer_profile_reply": lambda turns, user_text: "developer profile",
            "is_conversational_clarification": lambda _text: False,
            "clarification_reply": lambda turns: "clarify",
            "is_location_request": lambda _text: False,
            "location_reply": lambda: "location reply",
            "is_deep_search_followup_request": lambda _text: False,
            "infer_research_query_from_turns": lambda turns: "",
            "build_grounded_answer": lambda query, max_sources=2: "",
            "build_local_topic_digest_answer": lambda query: "",
            "is_groundable_factual_query": lambda _text: False,
            "developer_color_reply": lambda turns: "developer color",
            "developer_bilingual_reply": lambda turns: "developer bilingual",
            "color_reply": lambda turns: "color reply",
            "animal_reply": lambda turns: "animal reply",
            "core": SimpleNamespace(
                get_name_origin_story=lambda: "",
                _is_developer_color_lookup_request=lambda _text: False,
                _is_developer_bilingual_request=lambda _text: False,
                _is_color_lookup_request=lambda _text: False,
            ),
            "branch_group": "all",
        }
        options.update(overrides)
        return maybe_handle_deterministic_sequence(**options)

    def test_session_recap_outcome_is_timed(self):
        reply, meta, return_mode, tool_time_ms = self._call(
            "give me a recap",
            is_session_recap_request=lambda _text: True,
        )
        self.assertEqual(reply, "Recap of this session.")
        self.assertEqual(meta.get("tool"), "session_recap")
        self.assertEqual(return_mode, "timed")
        self.assertEqual(tool_time_ms, 0)

    def test_groundable_factual_query_prefers_local_digest_when_web_misses(self):
        reply, meta, return_mode, tool_time_ms = self._call(
            "tell me about a niche topic",
            is_groundable_factual_query=lambda _text: True,
            build_local_topic_digest_answer=lambda query: "Local digest",
        )
        self.assertEqual(reply, "Local digest")
        self.assertEqual(meta.get("tool"), "local_knowledge")
        self.assertEqual(return_mode, "logged")
        self.assertGreaterEqual(tool_time_ms, 0)

    def test_animal_reply_uses_logged_mode(self):
        reply, meta, return_mode, tool_time_ms = self._call("what animals do i like")
        self.assertEqual(reply, "animal reply")
        self.assertEqual(meta.get("tool"), "animal_reply")
        self.assertEqual(return_mode, "logged")
        self.assertEqual(tool_time_ms, 0)

    def test_operational_branch_group_skips_general_reply_family(self):
        outcome = self._call(
            "give me a recap",
            is_session_recap_request=lambda _text: True,
            branch_group="operational",
        )
        self.assertIsNone(outcome)

    def test_general_branch_group_skips_operational_reply_family(self):
        core = SimpleNamespace(
            runtime_audit_snapshot=lambda: {
                "source": "control_status_api",
                "control_status_url": "http://127.0.0.1:8080/api/control/status",
                "guard_running": True,
                "guard_status": "running",
                "guard_pid": 1001,
                "core_running": True,
                "core_status": "running",
                "core_pid": 1002,
                "core_heartbeat_age_sec": 0,
                "search_ok": True,
                "search_note": "status=200",
                "search_endpoint": "http://127.0.0.1:8081/search",
                "maintenance_active": True,
                "maintenance_status": "guard_scheduled",
                "maintenance_mode": "guard_tick",
                "queue_status": "clear",
                "queue_open_count": 0,
                "queue_actionable_count": 0,
            },
            get_name_origin_story=lambda: "",
            _is_developer_color_lookup_request=lambda _text: False,
            _is_developer_bilingual_request=lambda _text: False,
            _is_color_lookup_request=lambda _text: False,
        )

        outcome = self._call(
            "Inspect the live runtime and tell me whether guard, core, search, and maintenance are healthy. Use only the current live state.",
            core=core,
            branch_group="general",
        )
        self.assertIsNone(outcome)

    def test_restart_advice_reply_uses_runtime_snapshot(self):
        with TemporaryDirectory() as td:
            runtime_dir = Path(td)
            (runtime_dir / "guard_pid.json").write_text('{"pid": 111}', encoding="utf-8")
            (runtime_dir / "core_state.json").write_text('{"pid": 222}', encoding="utf-8")
            (runtime_dir / "core.heartbeat").write_text("ok", encoding="utf-8")
            core = SimpleNamespace(
                RUNTIME_DIR=str(runtime_dir),
                psutil=SimpleNamespace(pid_exists=lambda pid: pid in {111, 222}),
                get_name_origin_story=lambda: "",
                _is_developer_color_lookup_request=lambda _text: False,
                _is_developer_bilingual_request=lambda _text: False,
                _is_color_lookup_request=lambda _text: False,
            )

            reply, meta, return_mode, tool_time_ms = self._call(
                "Should I restart core right now? Inspect first and answer as an operator adviser. Do not restart anything.",
                core=core,
            )

        self.assertIn("not right now", reply.lower())
        self.assertEqual(meta.get("tool"), "runtime_restart_advice")
        self.assertEqual(return_mode, "logged")
        self.assertEqual(tool_time_ms, 0)

    def test_restart_condition_followup_is_deterministic(self):
        core = SimpleNamespace(
            RUNTIME_DIR="C:\\Nova\\runtime",
            psutil=SimpleNamespace(pid_exists=lambda _pid: True),
            get_name_origin_story=lambda: "",
            _is_developer_color_lookup_request=lambda _text: False,
            _is_developer_bilingual_request=lambda _text: False,
            _is_color_lookup_request=lambda _text: False,
        )

        reply, meta, return_mode, tool_time_ms = self._call(
            "Now tell me one condition that would make restart the right move.",
            core=core,
        )

        self.assertIn("heartbeat", reply.lower())
        self.assertEqual(meta.get("tool"), "runtime_restart_condition")
        self.assertEqual(return_mode, "logged")
        self.assertEqual(tool_time_ms, 0)

    def test_queue_pressure_triage_uses_generated_queue_lead(self):
        with TemporaryDirectory() as td:
            runtime_dir = Path(td)
            (runtime_dir / "autonomy_maintenance_state.json").write_text(
                '{"last_work_tree_cycle": {"status": "idle"}}',
                encoding="utf-8",
            )
            core = SimpleNamespace(
                RUNTIME_DIR=str(runtime_dir),
                tool_queue_status=lambda: (
                    "Standing work queue:\n"
                    "- open: 3 of 9\n"
                    "- green: 6\n"
                    "- drift: 3\n"
                    "- warning: 0\n"
                    "- never run: 0\n"
                    "Next item: real_world/stress_queue_pressure_triage.json\n"
                    "Status: drift (parity_drift)\n"
                ),
                patch_status_payload=lambda: {
                    "review_previews_pending_distinct": 1,
                    "review_previews_orphaned": 1,
                    "previews_approved_eligible": 0,
                },
                get_name_origin_story=lambda: "",
                _is_developer_color_lookup_request=lambda _text: False,
                _is_developer_bilingual_request=lambda _text: False,
                _is_color_lookup_request=lambda _text: False,
            )

            reply, meta, return_mode, tool_time_ms = self._call(
                "Inspect the generated queue, patch queue, and work tree pressure. Tell me the single most important next move and why.",
                core=core,
            )

        self.assertIn("stress_queue_pressure_triage", reply)
        self.assertIn("generated queue", reply.lower())
        self.assertEqual(meta.get("tool"), "queue_pressure_triage")
        self.assertEqual(return_mode, "logged")
        self.assertEqual(tool_time_ms, 0)

    def test_queue_pressure_justification_is_deterministic(self):
        with TemporaryDirectory() as td:
            runtime_dir = Path(td)
            (runtime_dir / "autonomy_maintenance_state.json").write_text(
                '{"last_work_tree_cycle": {"status": "idle"}}',
                encoding="utf-8",
            )
            core = SimpleNamespace(
                RUNTIME_DIR=str(runtime_dir),
                tool_queue_status=lambda: (
                    "Standing work queue:\n"
                    "- open: 2 of 9\n"
                    "- green: 7\n"
                    "- drift: 2\n"
                    "Next item: real_world/stress_runtime_audit.json\n"
                ),
                patch_status_payload=lambda: {
                    "review_previews_pending_distinct": 1,
                    "review_previews_orphaned": 0,
                    "previews_approved_eligible": 0,
                },
                get_name_origin_story=lambda: "",
                _is_developer_color_lookup_request=lambda _text: False,
                _is_developer_bilingual_request=lambda _text: False,
                _is_color_lookup_request=lambda _text: False,
            )

            reply, meta, return_mode, tool_time_ms = self._call(
                "Now justify that recommendation in one short paragraph without pretending you already took the step.",
                core=core,
            )

        self.assertIn("stress_runtime_audit", reply)
        self.assertEqual(meta.get("tool"), "queue_pressure_justification")
        self.assertEqual(return_mode, "logged")
        self.assertEqual(tool_time_ms, 0)

    def test_runtime_audit_reply_uses_live_snapshot(self):
        core = SimpleNamespace(
            runtime_audit_snapshot=lambda: {
                "source": "control_status_api",
                "control_status_url": "http://127.0.0.1:8080/api/control/status",
                "guard_running": True,
                "guard_status": "running",
                "guard_pid": 1001,
                "core_running": True,
                "core_status": "running",
                "core_pid": 1002,
                "core_heartbeat_age_sec": 0,
                "search_ok": True,
                "search_note": "status=200",
                "search_endpoint": "http://127.0.0.1:8081/search",
                "maintenance_active": True,
                "maintenance_status": "guard_scheduled",
                "maintenance_mode": "guard_tick",
                "queue_status": "actionable",
                "queue_open_count": 2,
                "queue_actionable_count": 2,
            },
            get_name_origin_story=lambda: "",
            _is_developer_color_lookup_request=lambda _text: False,
            _is_developer_bilingual_request=lambda _text: False,
            _is_color_lookup_request=lambda _text: False,
        )

        reply, meta, return_mode, tool_time_ms = self._call(
            "Inspect the live runtime and tell me whether guard, core, search, and maintenance are healthy. Use only the current live state.",
            core=core,
        )

        self.assertIn("guard is healthy", reply.lower())
        self.assertIn("core status is `running`", reply.lower())
        self.assertIn("http://127.0.0.1:8081/search", reply)
        self.assertEqual(meta.get("tool"), "runtime_audit")
        self.assertEqual(return_mode, "logged")
        self.assertEqual(tool_time_ms, 0)

    def test_runtime_audit_evidence_followup_uses_snapshot(self):
        core = SimpleNamespace(
            runtime_audit_snapshot=lambda: {
                "source": "control_status_api",
                "control_status_url": "http://127.0.0.1:8080/api/control/status",
                "guard_running": True,
                "guard_status": "running",
                "guard_pid": 1001,
                "core_running": True,
                "core_status": "running",
                "core_pid": 1002,
                "core_heartbeat_age_sec": 1,
                "search_ok": True,
                "search_note": "status=200",
                "search_endpoint": "http://127.0.0.1:8081/search",
                "maintenance_active": True,
                "maintenance_status": "guard_scheduled",
                "maintenance_mode": "guard_tick",
                "queue_status": "actionable",
                "queue_open_count": 2,
                "queue_actionable_count": 2,
            },
            get_name_origin_story=lambda: "",
            _is_developer_color_lookup_request=lambda _text: False,
            _is_developer_bilingual_request=lambda _text: False,
            _is_color_lookup_request=lambda _text: False,
        )

        reply, meta, return_mode, tool_time_ms = self._call(
            "Now tell me what evidence you used and what still worries you.",
            core=core,
        )

        self.assertIn("/api/control/status", reply)
        self.assertIn("generated repair queue", reply.lower())
        self.assertEqual(meta.get("tool"), "runtime_audit_evidence")
        self.assertEqual(return_mode, "logged")
        self.assertEqual(tool_time_ms, 0)

    def test_tool_path_disambiguation_returns_service_owner(self):
        with TemporaryDirectory() as td:
            base_dir = Path(td)
            services_dir = base_dir / "services"
            services_dir.mkdir(parents=True, exist_ok=True)
            (services_dir / "nova_patching.py").write_text(
                "def approve_preview(path_or_name, *, note=''):\\n    return 'Approved.'\\n",
                encoding="utf-8",
            )
            (base_dir / "nova_core.py").write_text(
                "def tool_patch_preview_approve(preview):\\n    return {'ok': True}\\n",
                encoding="utf-8",
            )
            core = SimpleNamespace(
                BASE_DIR=str(base_dir),
                get_name_origin_story=lambda: "",
                _is_developer_color_lookup_request=lambda _text: False,
                _is_developer_bilingual_request=lambda _text: False,
                _is_color_lookup_request=lambda _text: False,
            )

            reply, meta, return_mode, tool_time_ms = self._call(
                "Find where patch preview approval lives and tell me the exact file or service name.",
                core=core,
            )

        self.assertIn("services", reply.lower())
        self.assertIn("approve_preview", reply)
        self.assertEqual(meta.get("tool"), "tool_path_disambiguation")
        self.assertEqual(return_mode, "logged")
        self.assertEqual(tool_time_ms, 0)

    def test_tool_path_safe_step_followup_is_deterministic(self):
        with TemporaryDirectory() as td:
            base_dir = Path(td)
            services_dir = base_dir / "services"
            services_dir.mkdir(parents=True, exist_ok=True)
            (services_dir / "nova_patching.py").write_text(
                "def approve_preview(path_or_name, *, note=''):\\n    return 'Approved.'\\n",
                encoding="utf-8",
            )
            core = SimpleNamespace(
                BASE_DIR=str(base_dir),
                get_name_origin_story=lambda: "",
                _is_developer_color_lookup_request=lambda _text: False,
                _is_developer_bilingual_request=lambda _text: False,
                _is_color_lookup_request=lambda _text: False,
            )

            reply, meta, return_mode, tool_time_ms = self._call(
                "Now tell me the next safe operator step without pretending you changed anything.",
                core=core,
            )

        self.assertIn("i have not changed anything", reply.lower())
        self.assertIn("updates/previews", reply)
        self.assertEqual(meta.get("tool"), "tool_path_safe_step")
        self.assertEqual(return_mode, "logged")
        self.assertEqual(tool_time_ms, 0)

    def test_maintenance_mode_truth_reply_is_deterministic(self):
        core = SimpleNamespace(
            runtime_audit_snapshot=lambda: {
                "maintenance_active": True,
                "maintenance_mode": "guard_tick",
                "maintenance_status": "guard_scheduled",
            },
            get_name_origin_story=lambda: "",
            _is_developer_color_lookup_request=lambda _text: False,
            _is_developer_bilingual_request=lambda _text: False,
            _is_color_lookup_request=lambda _text: False,
        )
        reply, meta, return_mode, tool_time_ms = self._call(
            "Is Nova maintenance running through a separate worker or through the guard tick right now? Use only the live state.",
            core=core,
        )
        self.assertIn("guard tick", reply.lower())
        self.assertEqual(meta.get("tool"), "maintenance_mode_truth")
        self.assertEqual(return_mode, "logged")
        self.assertEqual(tool_time_ms, 0)

    def test_storage_watch_truth_reply_is_deterministic(self):
        core = SimpleNamespace(
            storage_watch_snapshot=lambda: {
                "status": "warn",
                "note": "25 kidney cleanup snapshots retained",
                "total_bytes": 50 * 1024 * 1024,
                "patch_snapshot_count": 2,
                "kidney_snapshot_count": 25,
                "patch_snapshot_warn_count": 3,
                "kidney_snapshot_warn_count": 24,
                "kidney_snapshot_warn_total_mb": 128,
            },
            get_name_origin_story=lambda: "",
            _is_developer_color_lookup_request=lambda _text: False,
            _is_developer_bilingual_request=lambda _text: False,
            _is_color_lookup_request=lambda _text: False,
        )
        reply, meta, return_mode, tool_time_ms = self._call(
            "Tell me whether Nova's snapshot storage is healthy right now and what numbers prove it.",
            core=core,
        )
        self.assertIn("snapshot storage", reply.lower())
        self.assertIn("25", reply)
        self.assertEqual(meta.get("tool"), "storage_watch_truth")
        self.assertEqual(return_mode, "logged")
        self.assertEqual(tool_time_ms, 0)

    def test_heartbeat_forensics_reply_is_deterministic(self):
        with TemporaryDirectory() as td:
            base_dir = Path(td)
            runtime_dir = base_dir / "runtime"
            runtime_dir.mkdir(parents=True, exist_ok=True)
            (runtime_dir / "core.heartbeat").write_text("ok", encoding="utf-8")
            (runtime_dir / "core_heartbeat_status.json").write_text('{"ok": true}', encoding="utf-8")
            core = SimpleNamespace(
                BASE_DIR=str(base_dir),
                RUNTIME_DIR=str(runtime_dir),
                runtime_audit_snapshot=lambda: {
                    "core_status": "running",
                    "core_heartbeat_age_sec": 0,
                },
                get_name_origin_story=lambda: "",
                _is_developer_color_lookup_request=lambda _text: False,
                _is_developer_bilingual_request=lambda _text: False,
                _is_color_lookup_request=lambda _text: False,
            )
            reply, meta, return_mode, tool_time_ms = self._call(
                "Check whether Nova's heartbeat is healthy right now and tell me exactly what proves it.",
                core=core,
            )

        self.assertIn("heartbeat", reply.lower())
        self.assertIn("core_heartbeat_status.json", reply)
        self.assertIn("core.heartbeat", reply)
        self.assertEqual(meta.get("tool"), "heartbeat_forensics")
        self.assertEqual(return_mode, "logged")
        self.assertEqual(tool_time_ms, 0)

    def test_runtime_artifact_grounding_reply_is_deterministic(self):
        with TemporaryDirectory() as td:
            base_dir = Path(td)
            runtime_dir = base_dir / "runtime"
            runtime_dir.mkdir(parents=True, exist_ok=True)
            (runtime_dir / "autonomy_maintenance_state.json").write_text("{}", encoding="utf-8")
            (runtime_dir / "core_heartbeat_status.json").write_text('{"ok": true}', encoding="utf-8")
            core = SimpleNamespace(
                BASE_DIR=str(base_dir),
                RUNTIME_DIR=str(runtime_dir),
                get_name_origin_story=lambda: "",
                _is_developer_color_lookup_request=lambda _text: False,
                _is_developer_bilingual_request=lambda _text: False,
                _is_color_lookup_request=lambda _text: False,
            )
            reply, meta, return_mode, tool_time_ms = self._call(
                "If we needed to inspect runtime truth right now, which exact runtime artifact files would you look at first?",
                core=core,
            )

        self.assertIn("autonomy_maintenance_state.json", reply)
        self.assertIn("core_heartbeat_status.json", reply)
        self.assertEqual(meta.get("tool"), "runtime_artifact_grounding")
        self.assertEqual(return_mode, "logged")
        self.assertEqual(tool_time_ms, 0)
