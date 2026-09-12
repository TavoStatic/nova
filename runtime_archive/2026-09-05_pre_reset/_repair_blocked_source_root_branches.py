"""Repair blocked source-root branches with stale failed-evidence holds."""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import work_tree
from services.nova_wiring_inventory import build_root_closure_inventory_payload
from services.source_root_judgment import build_source_root_judgment
from services.work_tree_signal_ingestion import (
    WorkTreeSignalIngestionService,
    _append_source_root_judgment_task,
    _recover_source_root_failed_evidence_hold,
    _root_closure_inventory_signals_from_status,
)


TARGET_BRANCHES = ("branch_c37c40e1", "branch_a00c67c3")


def _fetch_status() -> dict:
    req = urllib.request.Request("http://127.0.0.1:8080/api/control/status")
    with urllib.request.urlopen(req, timeout=60) as response:
        return json.loads(response.read().decode())


def _signal_for_root(status: dict, root_id: str) -> dict | None:
    for signal in _root_closure_inventory_signals_from_status(status):
        payload = signal.get("payload") if isinstance(signal.get("payload"), dict) else {}
        if str(payload.get("root_id") or "").strip() == root_id:
            return _append_source_root_judgment_task(str(signal.get("source") or "root_closure_inventory"), signal)

    inventory = build_root_closure_inventory_payload(status)
    row = next(
        (
            item
            for item in list(inventory.get("roots") or [])
            if isinstance(item, dict) and str(item.get("root_id") or "").strip() == root_id
        ),
        None,
    )
    if row is None:
        return None

    source_files = [str(item or "").strip() for item in list(row.get("source_files") or []) if str(item or "").strip()]
    first_source_file = source_files[0] if source_files else "services/nova_wiring_inventory.py"
    signal = {
        "source": "root_closure_inventory",
        "signal_class": "governance_pressure",
        "title": f"Wire source root end to end: {root_id}",
        "fingerprint": {
            "class": "governance_pressure",
            "surface": "root_closure_inventory",
            "error": "root_closure_gap",
            "symbol": root_id,
        },
        "payload": {
            "root_id": root_id,
            "label": str(row.get("label") or ""),
            "gaps": list(row.get("gaps") or []),
            "missing_source_files": list(row.get("missing_source_files") or []),
            "missing_status_keys": list(row.get("missing_status_keys") or []),
            "missing_signal_sources": list(row.get("missing_signal_sources") or []),
            "missing_planned_tools": list(row.get("missing_planned_tools") or []),
            "missing_advisory_actions": list(row.get("missing_advisory_actions") or []),
            "source_files": source_files,
            "status_keys": list(row.get("status_keys") or []),
            "signal_sources": list(row.get("signal_sources") or []),
            "planned_tools": list(row.get("planned_tools") or []),
            "advisory_actions": list(row.get("advisory_actions") or []),
        },
        "severity": "high",
        "actionability": "safe_now",
        "allowed_tools": ["read", "find", "pulse", "system_check"],
        "preferred_tool": "read",
        "next_task": f"Read source root evidence for {root_id}",
        "task_sequence": [
            {
                "title": f"Read source root evidence for {root_id}",
                "allowed_tools": ["read"],
                "preferred_tool": "read",
                "tool_args": [first_source_file],
            },
            {
                "title": f"Read wiring inventory row for {root_id}",
                "allowed_tools": ["read"],
                "preferred_tool": "read",
                "tool_args": ["services/nova_wiring_inventory.py"],
            },
            {
                "title": f"Find status, signal, tool, and action references for {root_id}",
                "allowed_tools": ["find"],
                "preferred_tool": "find",
                "tool_args": [root_id, "."],
            },
        ],
    }
    return _append_source_root_judgment_task("root_closure_inventory", signal)


def main() -> int:
    work_tree.reload_persisted_state()
    status = _fetch_status()
    service = WorkTreeSignalIngestionService()

    for branch_id in TARGET_BRANCHES:
        branch = work_tree.get_branch(branch_id)
        if branch is None:
            print(f"{branch_id}: missing")
            continue

        payload = dict(getattr(branch, "source_payload", {}) or {})
        root_id = str(payload.get("root_id") or "").strip()
        signal = _signal_for_root(status, root_id)
        if signal is None:
            print(f"{branch_id}: no signal for root {root_id}")
            continue

        normalized = service._normalize_signal(signal)
        recovered = _recover_source_root_failed_evidence_hold(branch, normalized)
        print(f"{branch_id}: recovered={recovered}")

        branch = work_tree.get_branch(branch_id)
        branch_status = getattr(getattr(branch, "status", None), "value", getattr(branch, "status", ""))
        print(f"  branch_status={branch_status}")
        for task in work_tree.list_branch_tasks(branch_id):
            task_status = getattr(getattr(task, "status", None), "value", getattr(task, "status", ""))
            if str(task_status) in {"dropped"}:
                continue
            meta = dict(getattr(task, "meta", {}) or {})
            args = meta.get("tool_args")
            suffix = f" args={args}" if args else ""
            print(f"  task {task.task_id[:12]} {task_status} {task.title}{suffix}")

        judgment = build_source_root_judgment(branch_id)
        print(
            f"  judgment verdict={judgment.get('verdict')} "
            f"failed_count={judgment.get('failed_evidence_count')} "
            f"evidence={len(work_tree.list_branch_evidence(branch_id, limit=80))}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())