"""Direct probes for audit findings — run: python runtime/validation/probe_audit_gaps.py"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.memory_production import parse_correction
from services.nova_mission import NovaMissionService
from services.nova_cli_sequence import apply_sequence_result
from services.edfi.resources import PageResult, get_district_scoped_page
from services.pipeline_worker_supervision import ensure_pipeline_worker_running, read_worker_heartbeat
import autonomy_maintenance


def _ok(label: str, passed: bool, detail: str = "") -> dict:
    status = "PASS" if passed else "FAIL"
    row = {"check": label, "status": status}
    if detail:
        row["detail"] = detail
    print(f"[{status}] {label}" + (f" — {detail}" if detail else ""))
    return row


def probe_mission_composed_blockers() -> list[dict]:
    mission = {
        "enabled": True,
        "mode": "steady_state_guard",
        "action": "hold",
        "validation_fresh": True,
        "regression_current": True,
        "release_truth_current": True,
        "generated_queue_untested_count": 2,
        "green_blockers": [
            {
                "owner": "regression",
                "code": "regression_failed",
                "remediation": {
                    "action": "run_regression",
                    "tools": ["release_rebuild_verify", "core_thinning"],
                },
            },
            {
                "owner": "generated_queue",
                "code": "generated_queue_untested",
                "remediation": {"action": "generated_queue_run_next"},
            },
            {
                "owner": "layer_maturity",
                "code": "core_gate_release_drift",
                "remediation": {
                    "action": "active_work_tree_run_next",
                    "tools": ["release_rebuild_verify", "core_thinning"],
                },
            },
        ],
        "truth_blockers": [
            "regression_failed",
            "generated_queue_untested",
            "core_gate_release_drift",
        ],
        "core_gate": {"drift_blocked": True, "missing_roots": []},
    }
    rows = []
    rows.append(
        _ok(
            "mission: generated_queue_run_next unblocked",
            not NovaMissionService.hold_blocks_action("generated_queue_run_next", mission_snapshot=mission),
        )
    )
    rows.append(
        _ok(
            "mission: active_work_tree + release_rebuild_verify unblocked",
            not NovaMissionService.hold_blocks_action(
                "active_work_tree_run_next",
                mission_snapshot=mission,
                action_context={"recommended_tool": "release_rebuild_verify"},
            ),
        )
    )
    rows.append(
        _ok(
            "mission: active_work_tree + core_thinning unblocked",
            not NovaMissionService.hold_blocks_action(
                "active_work_tree_run_next",
                mission_snapshot=mission,
                action_context={"recommended_tool": "core_thinning"},
            ),
        )
    )
    # Direct tool/action probes — these were in the original audit wording.
    rows.append(
        _ok(
            "mission: direct release_rebuild_verify still blocked (expected gap if only work-tree path wired)",
            NovaMissionService.hold_blocks_action("release_rebuild_verify", mission_snapshot=mission),
            "hold_blocks_action only special-cases active_work_tree_run_next / generated_queue_run_next",
        )
    )
    return rows


def probe_cli_turn_retention() -> list[dict]:
    shared = [("user", "hello")]

    class _Session:
        pending_action = None
        conversation_state = {}

    apply_sequence_result(
        final="world",
        meta={"planner_decision": "deterministic"},
        pending_action_ledger=None,
        merge_route_evidence_fn=lambda a, b: a or {},
        set_pending_action_fn=lambda _v: None,
        session_state=_Session(),
        apply_reply_runtime_effects_fn=lambda **_k: {"context_updated": False},
        apply_reply_session_updates_fn=lambda *_a, **_k: None,
        sync_pending_conversation_tracking_fn=lambda: None,
        trace_fn=lambda *_a, **_k: None,
        emit_cli_reply_outcome_fn=lambda **kwargs: kwargs["session_turns"].append(
            ("assistant", kwargs["reply_text"])
        ),
        behavior_record_event_fn=lambda *_a, **_k: None,
        extract_urls_fn=lambda _t: [],
        session_turns=shared,
        recent_tool_context="",
        recent_web_urls=[],
    )
    return [_ok("cli: assistant turn retained in shared session_turns", shared == [("user", "hello"), ("assistant", "world")], str(shared))]


def probe_patch_autonomous_approve() -> list[dict]:
    rows = []
    rows.append(
        _ok(
            "patch: patch_preview_approve not in PATCH_QUEUE_EXECUTE_TOOLS",
            "patch_preview_approve" not in autonomy_maintenance.PATCH_QUEUE_EXECUTE_TOOLS,
            str(autonomy_maintenance.PATCH_QUEUE_EXECUTE_TOOLS),
        )
    )
    row = {
        "name": "preview_probe.txt",
        "decision": "pending",
        "status": "eligible",
        "artifact_state": "ok",
        "preview_kind": "autonomy_micro_patch",
        "patch_revision": "4",
        "min_base_revision": "3",
        "_current_revision": 3,
    }
    mode = autonomy_maintenance._patch_queue_row_mode(row)
    rows.append(_ok("patch: pending preview mode is review not approve", mode == "review", f"mode={mode}"))
    return rows


def probe_memory() -> list[dict]:
    handled, parsed = parse_correction("not quite ready")
    return [
        _ok(
            "memory: not quite ready is not a correction",
            not handled and parsed == "",
            f"handled={handled} parsed={parsed!r}",
        )
    ]


def probe_edfi() -> list[dict]:
    rows = []

    class _Client:
        class config:
            connection_id = "probe"

    busy = PageResult(
        ok=True,
        status_code=200,
        count=100,
        items=[{"schoolId": 99999001, "localEducationAgencyReference": {"localEducationAgencyId": 99999}}] * 100,
        latency_ms=1,
    )
    from unittest.mock import patch

    with patch("services.edfi.resources.get_page", return_value=busy):
        result = get_district_scoped_page(
            _Client(),
            "ed-fi/schools",
            district_lea_id=31901,
            limit=5,
            max_scan_records=50,
        )
    rows.append(
        _ok(
            "edfi: scan_cap_hit forces ok=false",
            result.scan_cap_hit and not result.ok,
            f"scan_cap_hit={result.scan_cap_hit} ok={result.ok}",
        )
    )
    return rows


def probe_worker_supervision() -> list[dict]:
    rows = []
    with tempfile.TemporaryDirectory() as td:
        runtime_root = Path(td)
        caller_pid = os.getpid()
        result = ensure_pipeline_worker_running(
            "probe_pipeline_missing_script",
            worker_script=runtime_root / "missing_worker.py",
            venv_python=runtime_root / "missing_python.exe",
            runtime_root=runtime_root,
        )
        hb = read_worker_heartbeat("probe_pipeline_missing_script", runtime_root=runtime_root)
        rows.append(
            _ok(
                "worker: supervisor does not write fake running heartbeat on start",
                not hb.get("present") or hb.get("status") != "running" or hb.get("pid") != caller_pid,
                f"present={hb.get('present')} status={hb.get('status')} pid={hb.get('pid')} caller={caller_pid}",
            )
        )
        rows.append(
            _ok(
                "worker: missing script start is not supervised_ok",
                not bool((result.get("heartbeat") or {}).get("supervised_ok")),
                str(result.get("status")),
            )
        )
    return rows


def main() -> int:
    results = []
    for fn in (
        probe_mission_composed_blockers,
        probe_cli_turn_retention,
        probe_patch_autonomous_approve,
        probe_memory,
        probe_edfi,
        probe_worker_supervision,
    ):
        results.extend(fn())

    fails = [row for row in results if row.get("status") == "FAIL"]
    out_path = ROOT / "runtime" / "validation" / "probe_audit_gaps.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({"results": results, "fail_count": len(fails)}, indent=2), encoding="utf-8")
    print(f"\nWrote {out_path}")
    print(f"Summary: {len(results) - len(fails)} passed, {len(fails)} failed")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())