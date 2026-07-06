#!/usr/bin/env python3
"""Demonstrate the Ed-Fi Core governed lifecycle from cold start to domain readiness.

Run:
  python scripts/demo_edfi_core_lifecycle.py
  python scripts/demo_edfi_core_lifecycle.py --pause 45   # ~10-minute presenter pace

The demo uses an isolated runtime directory and saved-profile evidence only.
No live Ed-Fi API calls, no Work Tree branch mutation outside the real ingestion
service, and no control-panel UI.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent


def _bootstrap_child_process(argv: list[str]) -> int:
    demo_runtime = Path(tempfile.mkdtemp(prefix="nova_edfi_demo_"))
    env = os.environ.copy()
    env["NOVA_RUNTIME_DIR"] = str(demo_runtime)
    env["NOVA_EDFI_DEMO_ACTIVE"] = "1"
    try:
        completed = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), *argv],
            env=env,
            cwd=str(ROOT),
            check=False,
        )
        return int(completed.returncode or 0)
    finally:
        shutil.rmtree(demo_runtime, ignore_errors=True)


def _ensure_import_path() -> None:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))


def _healthy_profile_payload(*, discovered_at: int) -> dict[str, Any]:
    from services.edfi.config import CAPABILITY_SCHEMA
    from services.edfi.profile_evidence import EXPECTED_BISD_RESOURCE_COUNT

    return {
        "schema": CAPABILITY_SCHEMA,
        "milestone": "NOVA-EDFI-001",
        "connection_id": "district-main",
        "base_url": "https://odsprod.tea.texas.gov/odsedfiapi2026",
        "health": "ok",
        "discovered_at": discovered_at,
        "auth": {"ok": True, "type": "oauth2_client_credentials"},
        "discovery": {
            "ok": True,
            "resource_count": EXPECTED_BISD_RESOURCE_COUNT,
            "resources": ["ed-fi/schools", "ed-fi/students", "ed-fi/studentSchoolAssociations"],
            "namespaces": ["ed-fi", "TX"],
        },
    }


def _status_payload_from_evidence(evidence: dict[str, Any]) -> dict[str, Any]:
    profile = dict(evidence or {})
    return {
        "edfi_capability_profile": profile,
        "edfi_capability_profile_ok": bool(profile.get("ok")),
        "edfi_capability_profile_status": str(profile.get("status") or ""),
        "edfi_capability_profile_present": bool(profile.get("present")),
        "edfi_capability_profile_connection_id": str(profile.get("connection_id") or ""),
        "edfi_capability_profile_resource_count": int(profile.get("resource_count") or 0),
        "edfi_capability_profile_discovered_at": int(profile.get("discovered_at") or 0),
        "edfi_capability_profile_auth_ok": bool(profile.get("auth_ok")),
        "edfi_capability_profile_issue_count": int(profile.get("issue_count") or 0),
        "edfi_capability_profile_path": str(
            profile.get("profile_evidence_path") or profile.get("profile_path") or ""
        ),
    }


class _Scene:
    def __init__(self, *, pause_sec: float, emit_json: bool) -> None:
        self.pause_sec = max(0.0, float(pause_sec or 0.0))
        self.emit_json = emit_json
        self.step = 0
        self.timeline: list[dict[str, Any]] = []

    def beat(self, title: str, detail: str, payload: dict[str, Any] | None = None) -> None:
        self.step += 1
        entry = {
            "step": self.step,
            "title": title,
            "detail": detail,
            "payload": dict(payload or {}),
        }
        self.timeline.append(entry)
        if self.emit_json:
            print(json.dumps(entry, ensure_ascii=True))
            return
        print()
        print(f"Step {self.step}: {title}")
        print(f"  {detail}")
        for key, value in sorted((payload or {}).items()):
            print(f"  - {key}: {value}")
        if self.pause_sec:
            time.sleep(self.pause_sec)

    def finish(self, *, ok: bool) -> None:
        if self.emit_json:
            print(json.dumps({"ok": ok, "timeline": self.timeline}, ensure_ascii=True, indent=2))
            return
        print()
        print("Ed-Fi Core lifecycle demonstration complete.")
        print(f"Result: {'operational' if ok else 'blocked'}")


def _write_connection_config(runtime_root: Path, *, lea_id: str) -> None:
    connections = runtime_root / "edfi" / "connections" / "district-main"
    connections.mkdir(parents=True, exist_ok=True)
    (connections / "local_config.json").write_text(
        json.dumps(
            {
                "connection_id": "district-main",
                "base_url": "https://odsprod.tea.texas.gov/odsedfiapi2026",
                "client_id": "demo-client-id",
                "client_secret": "demo-client-secret",
                "district_lea_id": lea_id,
            },
            ensure_ascii=True,
            indent=2,
        ),
        encoding="utf-8",
    )


def _write_profile(runtime_root: Path, profile: dict[str, Any]) -> Path:
    profiles = runtime_root / "edfi" / "profiles"
    profiles.mkdir(parents=True, exist_ok=True)
    path = profiles / "district-main.json"
    path.write_text(json.dumps(profile, ensure_ascii=True, indent=2), encoding="utf-8")
    return path


def _signal_branches() -> list[Any]:
    import work_tree

    trees = [
        tree
        for tree in work_tree.list_trees()
        if str((tree.meta or {}).get("kind") or "") == "signal_ingestion"
    ]
    if not trees:
        return []
    tree = trees[0]
    return [
        branch
        for branch in work_tree.list_tree_branches(tree.tree_id)
        if branch.tree_id == tree.tree_id and branch.branch_id != tree.root_branch_id
    ]


def demo_domain_consumer_proceeds(connection_id: str = "district-main") -> dict[str, Any]:
    """Example future PEIMS/TSDS gate: consume district facts only after Core is ready."""
    from services.edfi.core_readiness import read_edfi_core_readiness
    from services.edfi.profile_evidence import get_district_layer_facts

    readiness = read_edfi_core_readiness(connection_id)
    facts = get_district_layer_facts(connection_id)
    if not readiness.get("ready"):
        return {
            "proceed": False,
            "module": "peims-stub",
            "reason": "edfi_core_not_ready",
            "blocking_issues": list(readiness.get("blocking_issues") or []),
        }
    if not str(facts.get("lea_id") or "").strip():
        return {
            "proceed": False,
            "module": "peims-stub",
            "reason": "district_lea_id_missing",
        }
    return {
        "proceed": True,
        "module": "peims-stub",
        "connection_id": facts.get("connection_id"),
        "lea_id": facts.get("lea_id"),
        "resource_count": facts.get("resource_count"),
        "profile_path": facts.get("profile_path"),
        "sync_status_present": bool(facts.get("sync_status")),
        "next_action": "load-domain-collections-from-edfi-core",
    }


def run_demo(*, pause_sec: float = 0.0, emit_json: bool = False) -> int:
    import work_tree
    from services.edfi.core_readiness import read_edfi_core_readiness
    from services.edfi.profile_evidence import (
        EXPECTED_BISD_LEA_ID,
        build_capability_profile_evidence,
        get_district_layer_facts,
    )
    from services.nova_runtime_context import RUNTIME_DIR
    from services.work_tree_signal_ingestion import (
        EDFI_CAPABILITY_PROFILE_READ_TASK_TITLE,
        WorkTreeSignalIngestionService,
    )

    scene = _Scene(pause_sec=pause_sec, emit_json=emit_json)
    runtime_root = Path(RUNTIME_DIR)
    discovered_at = int(time.time())
    service = WorkTreeSignalIngestionService()

    work_tree._clear_in_memory()
    with mock.patch.object(work_tree, "_persist_tree_state", return_value=None):
        _write_connection_config(runtime_root, lea_id=EXPECTED_BISD_LEA_ID)

        scene.beat(
            "Nova boots on an isolated runtime",
            "Cold start uses a fresh runtime root with connection config but no saved profile yet.",
            {
                "runtime_root": str(runtime_root),
                "connection_id": "district-main",
                "profile_present": False,
            },
        )

        readiness_boot = read_edfi_core_readiness("district-main")
        scene.beat(
            "Ed-Fi Core readiness is blocked",
            "Nova can already explain why district ingress is not operational.",
            {
                "ready": readiness_boot.get("ready"),
                "profile_ok": readiness_boot.get("profile_ok"),
                "blocking_issues": "; ".join(readiness_boot.get("blocking_issues") or []) or "none",
                "next_recommended_slice": readiness_boot.get("next_recommended_slice"),
            },
        )
        if readiness_boot.get("ready"):
            scene.finish(ok=False)
            return 1

        missing_evidence = build_capability_profile_evidence("district-main")
        missing_status = _status_payload_from_evidence(missing_evidence)
        scene.beat(
            "Nova discovers a missing Ed-Fi capability profile",
            "Status evidence is built from the saved-profile contract only; no live ODS probe.",
            {
                "profile_status": missing_evidence.get("status"),
                "profile_ok": missing_evidence.get("ok"),
                "issue": (missing_evidence.get("issues") or [{}])[0].get("code"),
            },
        )

        created = service.ingest_status_snapshot(missing_status)
        branches = _signal_branches()
        branch = branches[0] if branches else None
        scene.beat(
            "Work Tree opens a governed branch",
            "Signal ingestion turns the profile gap into a governance-pressure branch with a read-evidence task.",
            {
                "ingest_actions": ", ".join(str(item.get("action") or "") for item in created) or "none",
                "branch_source": str(getattr(branch, "source_type", "") or ""),
                "branch_status": str(getattr(branch, "status", "") or ""),
                "first_task": (
                    work_tree.list_branch_tasks(branch.branch_id)[0].title
                    if branch is not None and work_tree.list_branch_tasks(branch.branch_id)
                    else ""
                ),
            },
        )
        if branch is None:
            scene.finish(ok=False)
            return 1

        scene.beat(
            "Governed repair writes a healthy saved profile",
            "In production this is scripts/run_edfi_profile.py against the district ODS; the demo writes the saved profile artifact.",
            {
                "repair_action": "save_capability_profile",
                "profile_path": "runtime/edfi/profiles/district-main.json",
            },
        )
        profile = _healthy_profile_payload(discovered_at=discovered_at)
        _write_profile(runtime_root, profile)

        read_task = next(
            (
                task
                for task in work_tree.list_branch_tasks(branch.branch_id)
                if task.title == EDFI_CAPABILITY_PROFILE_READ_TASK_TITLE
            ),
            None,
        )
        if read_task is None:
            scene.finish(ok=False)
            return 1
        work_tree.record_task_evidence(
            branch_id=branch.branch_id,
            task_id=read_task.task_id,
            tool_name="read",
            tool_args=["runtime/edfi/profiles/district-main.json"],
            result=json.dumps(profile),
        )
        work_tree.mark_task_complete(read_task.task_id)
        scene.beat(
            "Evidence is gathered and verified",
            "The branch holds until a verified read of the saved profile JSON is recorded in Work Tree evidence.",
            {
                "task": read_task.title,
                "tool": "read",
                "evidence_path": "runtime/edfi/profiles/district-main.json",
                "resource_count": profile["discovery"]["resource_count"],
            },
        )

        healthy_evidence = build_capability_profile_evidence("district-main")
        healthy_status = _status_payload_from_evidence(healthy_evidence)
        resolved = service.sync_status_snapshot(healthy_status)
        branch = work_tree.get_branch(branch.branch_id)
        scene.beat(
            "Profile becomes healthy and the branch resolves",
            "Once saved profile evidence is healthy and verified, signal ingestion resolves the governance branch.",
            {
                "profile_ok": healthy_evidence.get("ok"),
                "sync_actions": ", ".join(str(item.get("action") or "") for item in resolved) or "none",
                "branch_status": str(branch.status),
                "resolution_state": str(branch.resolution_state or ""),
            },
        )
        if branch.status != work_tree.BranchStatus.COMPLETE:
            scene.finish(ok=False)
            return 1

        readiness_final = read_edfi_core_readiness("district-main")
        facts = get_district_layer_facts("district-main")
        scene.beat(
            "Ed-Fi Core readiness updates to operational",
            "The readiness contract summarizes the full arc without adding new behavior.",
            {
                "ready": readiness_final.get("ready"),
                "inventory_declared": readiness_final.get("inventory_declared"),
                "evidence_loop_ready": readiness_final.get("evidence_loop_ready"),
                "district_facts_ok": readiness_final.get("district_facts_ok"),
                "sync_status_present": readiness_final.get("sync_status_present"),
                "lea_id": facts.get("lea_id"),
            },
        )
        if not readiness_final.get("ready"):
            scene.finish(ok=False)
            return 1

        domain = demo_domain_consumer_proceeds("district-main")
        scene.beat(
            "A future domain module consumes district facts",
            "PEIMS/TSDS modules above services/edfi/ should gate on readiness, then read get_district_layer_facts().",
            domain,
        )
        if not domain.get("proceed"):
            scene.finish(ok=False)
            return 1

    scene.finish(ok=True)
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Demonstrate the Ed-Fi Core governed lifecycle from cold start to domain readiness.",
    )
    parser.add_argument(
        "--pause",
        type=float,
        default=0.0,
        help="Seconds to pause between narrator beats (use ~45 for a 10-minute presentation).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON beats instead of presenter text.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if str(os.environ.get("NOVA_EDFI_DEMO_ACTIVE") or "") != "1":
        return _bootstrap_child_process(list(argv or sys.argv[1:]))
    _ensure_import_path()
    return run_demo(pause_sec=float(args.pause or 0.0), emit_json=bool(args.json))


if __name__ == "__main__":
    raise SystemExit(main())