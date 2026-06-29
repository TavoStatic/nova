import unittest

from services.nova_http_frontdoor import NOVA_HTTP_FRONTDOOR_SERVICE
from services.nova_http_get_routes import HTTP_GET_ROUTES_SERVICE


class TestNovaHttpGetRoutesService(unittest.TestCase):
    def test_handle_basic_route_request_returns_health_payload(self):
        result = HTTP_GET_ROUTES_SERVICE.handle_basic_route_request(
            "/api/health",
            handler=object(),
            control_login_enabled_fn=lambda: True,
            control_page_gate_fn=lambda _handler: (True, ""),
            ollama_api_up_fn=lambda: True,
            chat_model_fn=lambda: "phi",
            memory_enabled_fn=lambda: True,
            chat_login_enabled_fn=lambda: False,
            index_html="index",
            control_login_html="login",
            control_html="control",
            control_css_path="control.css",
            control_js_path="control.js",
        )

        self.assertEqual(
            result,
            {"kind": "json", "code": 200, "body": {"ok": True, "ollama_api_up": True, "chat_model": "phi", "memory_enabled": True, "chat_login_enabled": False}},
        )

    def test_handle_basic_route_request_returns_file_route(self):
        result = HTTP_GET_ROUTES_SERVICE.handle_basic_route_request(
            "/static/control.css",
            handler=object(),
            control_login_enabled_fn=lambda: True,
            control_page_gate_fn=lambda _handler: (True, ""),
            ollama_api_up_fn=lambda: True,
            chat_model_fn=lambda: "phi",
            memory_enabled_fn=lambda: True,
            chat_login_enabled_fn=lambda: False,
            index_html="index",
            control_login_html="login",
            control_html="control",
            control_css_path="control.css",
            control_js_path="control.js",
        )

        self.assertEqual(result, {"kind": "file", "code": 200, "path": "control.css", "content_type": "text/css; charset=utf-8"})

    def test_handle_basic_route_request_enforces_control_login_gate(self):
        result = HTTP_GET_ROUTES_SERVICE.handle_basic_route_request(
            "/control/login",
            handler=object(),
            control_login_enabled_fn=lambda: False,
            control_page_gate_fn=lambda _handler: (True, ""),
            ollama_api_up_fn=lambda: True,
            chat_model_fn=lambda: "phi",
            memory_enabled_fn=lambda: True,
            chat_login_enabled_fn=lambda: False,
            index_html="index",
            control_login_html="login",
            control_html="control",
            control_css_path="control.css",
            control_js_path="control.js",
        )

        self.assertEqual(result, {"kind": "json", "code": 404, "body": {"ok": False, "error": "control_login_disabled"}})

    def test_handle_chat_history_request_shapes_turns(self):
        code, payload = HTTP_GET_ROUTES_SERVICE.handle_chat_history_request(
            "/api/chat/history",
            handler=object(),
            qs={"session_id": ["s1"]},
            chat_login_auth_fn=lambda _handler: (True, "runner"),
            normalize_user_id_fn=lambda user_id: str(user_id or "").strip().lower(),
            request_user_id_fn=lambda _handler, _qs: "runner",
            assert_session_owner_fn=lambda session_id, user_id, allow_bind: (session_id == "s1" and user_id == "runner" and not allow_bind, "denied"),
            get_session_turns_fn=lambda _session_id: [("user", "hello"), ("assistant", "hi")],
            max_stored_turns_per_session=10,
        )

        self.assertEqual(code, 200)
        self.assertEqual(payload["session_id"], "s1")
        self.assertEqual(payload["turns"][0]["role"], "user")
        self.assertEqual(payload["turns"][1]["text"], "hi")

    def test_handle_chat_history_request_ignores_other_paths(self):
        result = HTTP_GET_ROUTES_SERVICE.handle_chat_history_request(
            "/api/control/work-trees",
            handler=object(),
            qs={},
            chat_login_auth_fn=lambda _handler: (True, "runner"),
            normalize_user_id_fn=lambda user_id: str(user_id or "").strip().lower(),
            request_user_id_fn=lambda _handler, _qs: "runner",
            assert_session_owner_fn=lambda _session_id, _user_id, allow_bind: (not allow_bind, "denied"),
            get_session_turns_fn=lambda _session_id: [],
            max_stored_turns_per_session=10,
        )

        self.assertIsNone(result)

    def test_handle_control_api_request_requires_auth(self):
        result = HTTP_GET_ROUTES_SERVICE.handle_control_api_request(
            "/api/control/status",
            qs={},
            control_auth_fn=lambda _qs: (False, "denied"),
            cached_control_status_payload_fn=lambda: {"ok": True},
            control_policy_payload_fn=lambda: {"ok": True},
            metrics_payload_fn=lambda: {"ok": True},
            work_trees_payload_fn=lambda: {"ok": True, "trees": []},
            session_summaries_fn=lambda _limit: [],
            test_session_report_summaries_fn=lambda _limit: [],
            available_test_session_definitions_fn=lambda _limit: [],
        )

        self.assertEqual(result, (403, {"ok": False, "error": "denied"}))

    def test_handle_basic_route_request_from_runtime_resolves_scope(self):
        result = HTTP_GET_ROUTES_SERVICE.handle_basic_route_request_from_runtime(
            "/api/health",
            handler=object(),
            runtime_scope={
                "NOVA_HTTP_FRONTDOOR_SERVICE": NOVA_HTTP_FRONTDOOR_SERVICE,
                "_render_runtime_console_html": lambda: "index",
                "_render_leah_html": lambda: "leah",
                "CONTROL_CSS_PATH": "control.css",
                "CONTROL_JS_PATH": "control.js",
                "LEAH_CSS_PATH": "leah.css",
                "LEAH_JS_PATH": "leah.js",
                "LEAH_FX_JS_PATH": "leah_fx.js",
                "_control_login_enabled": lambda: True,
                "_control_page_gate": lambda _handler: (True, ""),
                "_render_control_login_html": lambda: "login",
                "_render_control_html": lambda: "control",
                "_health_payload": lambda: {"ok": True, "source": "runtime"},
            },
        )

        self.assertEqual(result, {"kind": "json", "code": 200, "body": {"ok": True, "source": "runtime"}})

    def test_handle_control_status_surfaces_request_returns_slim_payload(self):
        surfaces_payload = {
            "ok": True,
            "status_kind": "signal_ingestion_surfaces",
            "operator_outbox_open_count": 0,
            "root_closure_inventory": {"ok": True, "gap_count": 0},
        }

        result = HTTP_GET_ROUTES_SERVICE.handle_control_api_request(
            "/api/control/status/surfaces",
            qs={},
            control_auth_fn=lambda _qs: (True, ""),
            cached_control_status_payload_fn=lambda: {"ok": True, "huge": "full"},
            cached_control_status_surfaces_payload_fn=lambda: surfaces_payload,
            control_policy_payload_fn=lambda: {"ok": True},
            metrics_payload_fn=lambda: {"ok": True},
            work_trees_payload_fn=lambda: {"ok": True, "trees": []},
            session_summaries_fn=lambda _limit: [],
            test_session_report_summaries_fn=lambda _limit: [],
            available_test_session_definitions_fn=lambda _limit: [],
        )

        self.assertEqual(result, (200, surfaces_payload))

    def test_handle_control_status_request_preserves_richer_maintenance_truth(self):
        status_payload = {
            "ok": True,
            "generated_queue_status": "clear",
            "work_tree_status": "ok",
            "autonomy_maintenance": {
                "last_error": "",
                "last_error_stale": False,
                "last_generated_queue_run": {
                    "status": "clear",
                    "queue_open_count": 0,
                    "queue_actionable_count": 0,
                },
                "last_work_tree_cycle": {
                    "status": "ok",
                    "executed_count": 7,
                    "tree_count": 2,
                },
                "last_kidney_status": {
                    "mode": "enforce",
                    "candidate_count": 32,
                },
            },
        }

        result = HTTP_GET_ROUTES_SERVICE.handle_control_api_request(
            "/api/control/status",
            qs={},
            control_auth_fn=lambda _qs: (True, ""),
            cached_control_status_payload_fn=lambda: status_payload,
            control_policy_payload_fn=lambda: {"ok": True},
            metrics_payload_fn=lambda: {"ok": True},
            work_trees_payload_fn=lambda: {"ok": True, "trees": []},
            session_summaries_fn=lambda _limit: [],
            test_session_report_summaries_fn=lambda _limit: [],
            available_test_session_definitions_fn=lambda _limit: [],
        )

        self.assertEqual(result, (200, status_payload))

    def test_handle_control_work_trees_request_shapes_payload(self):
        result = HTTP_GET_ROUTES_SERVICE.handle_control_api_request(
            "/api/control/work-trees",
            qs={},
            control_auth_fn=lambda _qs: (True, ""),
            cached_control_status_payload_fn=lambda: {"ok": True},
            control_policy_payload_fn=lambda: {"ok": True},
            metrics_payload_fn=lambda: {"ok": True},
            work_trees_payload_fn=lambda: {
                "ok": True,
                "counts": {"total": 1, "active": 1},
                "trees": [
                    {
                        "tree_id": "tree_123",
                        "title": "Queue repair",
                        "active_branch_id": "branch_1",
                        "active_branch_title": "Inspect route drift",
                        "next_step": {
                            "action": "execute",
                            "recommended_tool": "find",
                        },
                        "nodes": [
                            {
                                "id": "branch_1",
                                "notes": "Review focus: patch-routing review",
                                "current_task": {
                                    "title": "Inspect route drift",
                                    "status": "open",
                                },
                            }
                        ],
                    }
                ],
            },
            session_summaries_fn=lambda _limit: [],
            test_session_report_summaries_fn=lambda _limit: [],
            available_test_session_definitions_fn=lambda _limit: [],
        )

        self.assertEqual(
            result,
            (
                200,
                {
                    "ok": True,
                    "counts": {"total": 1, "active": 1},
                    "trees": [
                        {
                            "tree_id": "tree_123",
                            "title": "Queue repair",
                            "active_branch_id": "branch_1",
                            "active_branch_title": "Inspect route drift",
                            "next_step": {
                                "action": "execute",
                                "recommended_tool": "find",
                            },
                            "nodes": [
                                {
                                    "id": "branch_1",
                                    "notes": "Review focus: patch-routing review",
                                    "current_task": {
                                        "title": "Inspect route drift",
                                        "status": "open",
                                    },
                                }
                            ],
                        }
                    ],
                },
            ),
        )

    def test_handle_control_work_trees_request_preserves_failure_payload(self):
        failure_payload = {
            "ok": False,
            "error": "db_unavailable",
            "trees": [],
        }

        result = HTTP_GET_ROUTES_SERVICE.handle_control_api_request(
            "/api/control/work-trees",
            qs={},
            control_auth_fn=lambda _qs: (True, ""),
            cached_control_status_payload_fn=lambda: {"ok": True},
            control_policy_payload_fn=lambda: {"ok": True},
            metrics_payload_fn=lambda: {"ok": True},
            work_trees_payload_fn=lambda: failure_payload,
            session_summaries_fn=lambda _limit: [],
            test_session_report_summaries_fn=lambda _limit: [],
            available_test_session_definitions_fn=lambda _limit: [],
        )

        self.assertEqual(result, (200, failure_payload))

    def test_handle_control_pipelines_from_runtime_uses_pipeline_control_service(self):
        class _PipelineControl:
            @staticmethod
            def payload_from_runtime(runtime_scope, *, selected_pipeline_id=""):
                return {
                    "ok": True,
                    "source": runtime_scope["SOURCE"],
                    "selected_pipeline_id": selected_pipeline_id,
                }

        result = HTTP_GET_ROUTES_SERVICE.handle_control_api_request_from_runtime(
            "/api/control/pipelines",
            handler=object(),
            qs={"pipeline_id": ["sis_test"]},
            runtime_scope={
                "SOURCE": "runtime-pipeline-service",
                "HTTP_PIPELINE_CONTROL_SERVICE": _PipelineControl(),
                "_control_auth": lambda _handler, _qs: (True, ""),
                "_cached_control_status_payload": lambda: {"ok": True},
                "_control_policy_payload": lambda: {"ok": True},
                "_metrics_payload": lambda: {"ok": True},
                "_work_trees_payload": lambda: {"ok": True, "trees": []},
                "_session_summaries": lambda _limit: [],
                "_test_session_report_summaries": lambda _limit: [],
                "_available_test_session_definitions": lambda _limit: [],
            },
        )

        self.assertEqual(
            result,
            (
                200,
                {
                    "ok": True,
                    "source": "runtime-pipeline-service",
                    "selected_pipeline_id": "sis_test",
                },
            ),
        )

    def test_handle_control_test_sessions_request_shapes_payload(self):
        result = HTTP_GET_ROUTES_SERVICE.handle_control_api_request(
            "/api/control/test-sessions",
            qs={},
            control_auth_fn=lambda _qs: (True, ""),
            cached_control_status_payload_fn=lambda: {"ok": True},
            control_policy_payload_fn=lambda: {"ok": True},
            metrics_payload_fn=lambda: {"ok": True},
            work_trees_payload_fn=lambda: {"ok": True, "trees": []},
            session_summaries_fn=lambda _limit: [],
            test_session_report_summaries_fn=lambda _limit: [{"file": "report.json"}],
            available_test_session_definitions_fn=lambda _limit: [{"file": "definition.json"}],
        )

        self.assertEqual(
            result,
            (200, {"ok": True, "reports": [{"file": "report.json"}], "definitions": [{"file": "definition.json"}]}),
        )
