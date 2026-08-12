from services.nova_grounded_self_report import GROUNDED_SELF_REPORT_SERVICE


def _status_payload() -> dict:
    return {
        "health_score": 95,
        "alerts": ["error_spike:err/min=40.00, req/min=50.00, err_ratio=0.80"],
        "work_tree_truth_status": "blocked_observing",
        "work_tree_open_task_count": 1,
        "ollama_chat_ready": True,
        "memory_health_status": "ok",
        "release_status": {
            "release_readiness": "needs-promotion",
            "latest_source_status": "current",
            "latest_artifact_stale": False,
            "latest_validation_record_complete": False,
            "latest_validation_record_missing_fields": ["result", "machine or vm name"],
            "latest_artifact": "nova-platform-rc-2026.05.14.1-work-tree-rebuild.zip",
        },
    }


def _work_tree_payload() -> dict:
    return {
        "trees": [
            {
                "nodes": [
                    {
                        "title": "Release package verification",
                        "resolution_state": "observing",
                        "open_task_count": 1,
                        "current_task": {
                            "title": "Complete release validation outcome before marking package ready"
                        },
                    }
                ]
            }
        ]
    }


def test_service_no_longer_classifies_user_phrases() -> None:
    assert not hasattr(GROUNDED_SELF_REPORT_SERVICE, "classify_query")


def test_health_reply_uses_live_score_alerts_and_work_tree_truth() -> None:
    payload = GROUNDED_SELF_REPORT_SERVICE.build_payload(_status_payload(), _work_tree_payload())
    reply = GROUNDED_SELF_REPORT_SERVICE.render("health", payload)

    assert "95/100" in reply
    assert "blocked_observing" in reply
    assert "error_spike" in reply
    assert "Release package is verified but validation outcome is incomplete" in reply
    assert "Source: live control status and Work Tree." in reply


def test_trouble_reply_names_current_open_branch_and_task() -> None:
    payload = GROUNDED_SELF_REPORT_SERVICE.build_payload(_status_payload(), _work_tree_payload())
    reply = GROUNDED_SELF_REPORT_SERVICE.render("trouble", payload)

    assert "Today I am mainly stuck on" in reply
    assert "Release package verification" in reply
    assert "Complete release validation outcome" in reply
    assert "Release readiness: needs-promotion." in reply


def test_release_status_normalizes_latest_readiness_shape() -> None:
    payload = GROUNDED_SELF_REPORT_SERVICE.build_payload(
        {
            "health_score": 100,
            "work_tree_truth_status": "open",
            "work_tree_open_task_count": 1,
            "release_status": {
                "latest_readiness_state": "source-changed-after-build",
                "latest_source_status": "changed-after-build",
                "latest_artifact_stale": True,
                "latest_artifact_name": "nova-platform-rc-demo.zip",
            },
        },
        {},
    )

    assert payload["release"]["readiness"] == "source-changed-after-build"
    assert payload["release"]["latest_source_status"] == "changed-after-build"
    assert payload["release"]["artifact"] == "nova-platform-rc-demo.zip"
    assert "Release package is stale behind live source" in GROUNDED_SELF_REPORT_SERVICE.render("internals", payload)


def test_operator_attention_payload_names_live_help_request() -> None:
    payload = GROUNDED_SELF_REPORT_SERVICE.build_payload(_status_payload(), _work_tree_payload())
    attention = GROUNDED_SELF_REPORT_SERVICE.build_operator_attention(payload)

    assert attention["active"] is True
    assert attention["level"] == "work_tree_attention"
    assert "I need help with:" in attention["message"]
    assert "validation outcome is incomplete" in attention["message"]
    assert attention["source"] == "live_control_status_and_work_tree"


def test_operator_attention_does_not_label_open_work_as_operator_hold() -> None:
    status = _status_payload()
    status["work_tree_truth_status"] = "open"
    payload = GROUNDED_SELF_REPORT_SERVICE.build_payload(status, _work_tree_payload())
    attention = GROUNDED_SELF_REPORT_SERVICE.build_operator_attention(payload)

    assert attention["active"] is True
    assert attention["level"] == "work_tree_attention"


def test_ready_with_notes_release_is_status_not_stuck_point() -> None:
    payload = GROUNDED_SELF_REPORT_SERVICE.build_payload(
        {
            "health_score": 100,
            "work_tree_truth_status": "clear",
            "work_tree_open_task_count": 0,
            "release_status": {
                "latest_readiness_state": "ready-with-notes",
                "latest_source_status": "current",
                "latest_artifact_stale": False,
                "latest_ready_to_ship": True,
            },
        },
        {"trees": []},
    )
    attention = GROUNDED_SELF_REPORT_SERVICE.build_operator_attention(payload)
    reply = GROUNDED_SELF_REPORT_SERVICE.render("trouble", payload)

    assert attention["active"] is False
    assert "I do not see an active stuck point" in reply
    assert "Release readiness: ready-with-notes." in reply


def test_completed_branch_with_stale_current_task_is_not_current_work() -> None:
    payload = GROUNDED_SELF_REPORT_SERVICE.build_payload(
        {
            "health_score": 100,
            "work_tree_truth_status": "clear",
            "work_tree_open_task_count": 0,
            "release_status": {
                "latest_readiness_state": "ready-with-notes",
                "latest_source_status": "current",
                "latest_artifact_stale": False,
            },
        },
        {
            "trees": [
                {
                    "nodes": [
                        {
                            "title": "Runtime restart provenance is incomplete",
                            "status": "complete",
                            "resolution_state": "open",
                            "open_task_count": 0,
                            "current_task": {"title": "Read completed evidence"},
                        }
                    ]
                }
            ]
        },
    )
    reply = GROUNDED_SELF_REPORT_SERVICE.render("trouble", payload)

    assert payload["work_item"] == {}
    assert "Runtime restart provenance is incomplete" not in reply
    assert "I do not see an active stuck point" in reply


def test_live_cleared_runtime_branch_does_not_drive_attention() -> None:
    payload = GROUNDED_SELF_REPORT_SERVICE.build_payload(
        {
            "health_score": 100,
            "work_tree_truth_status": "open",
            "work_tree_open_task_count": 2,
            "guard": {"running": True, "status": "running"},
            "runtime_failures": {
                "guard": {"level": "good", "status": "running"},
            },
            "release_status": {
                "latest_readiness_state": "source-changed-after-build",
                "latest_source_status": "changed-after-build",
                "latest_artifact_stale": True,
            },
        },
        {
            "trees": [
                {
                    "nodes": [
                        {
                            "title": "Guard process is not running",
                            "status": "ready",
                            "source_key": "runtime_failure:runtime_core:process_not_running:guard",
                            "tasks_open": 1,
                            "current_task": {"title": "Inspect guard status"},
                        },
                        {
                            "title": "Release package is stale behind live source",
                            "status": "ready",
                            "source_key": "release_readiness_gap:release:release_source_changed_after_build:demo.zip",
                            "tasks_open": 1,
                            "current_task": {"title": "Read release ledger for current package"},
                        },
                    ]
                }
            ]
        },
    )
    attention = GROUNDED_SELF_REPORT_SERVICE.build_operator_attention(payload)

    assert payload["work_tree_open_task_count"] == 1
    assert payload["work_item"]["title"] == "Release package is stale behind live source"
    assert "Guard process is not running" not in attention["message"]
    assert "Release package is stale behind live source" in attention["message"]


def test_only_live_cleared_runtime_branch_leaves_attention_clear() -> None:
    payload = GROUNDED_SELF_REPORT_SERVICE.build_payload(
        {
            "health_score": 100,
            "work_tree_truth_status": "open",
            "work_tree_open_task_count": 1,
            "guard": {"running": True, "status": "running"},
        },
        {
            "trees": [
                {
                    "nodes": [
                        {
                            "title": "Guard process is not running",
                            "status": "ready",
                            "source_key": "runtime_failure:runtime_core:process_not_running:guard",
                            "tasks_open": 1,
                            "current_task": {"title": "Inspect guard status"},
                        }
                    ]
                }
            ]
        },
    )
    attention = GROUNDED_SELF_REPORT_SERVICE.build_operator_attention(payload)

    assert payload["work_tree_truth_status"] == "clear"
    assert payload["work_tree_open_task_count"] == 0
    assert attention["active"] is False
