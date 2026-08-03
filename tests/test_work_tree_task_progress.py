from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from services.tool_identity import (
    EVIDENCE_QUALITY,
    OBSERVED_TOOLS,
    RELEASE_PROMOTION_JUDGMENT,
    RELEASE_REBUILD_VERIFY,
    SOURCE_ROOT_JUDGMENT,
    STRUCTURED_JUDGMENT_TOOLS,
    TOOL_ALIASES,
    VERIFIED_TOOLS,
    all_quality_tool_names,
    canonicalize_tool_name,
    collect_marker_tool_names,
    evidence_quality,
    is_verified_tool,
)
from services.work_tree_task_progress import (
    get_ladder,
    learn_families_from_history,
    learn_tool_patterns_from_history,
    list_seeded_families,
    load_learned_ladders,
    measure_task_progress,
    save_learned_ladders,
    SolutionLadder,
    SolutionMarker,
    _SEEDED,
)


class ToolIdentityTests(unittest.TestCase):
    def test_evidence_quality_maps_verified_and_observed(self):
        self.assertEqual(evidence_quality(RELEASE_REBUILD_VERIFY), "verified")
        self.assertEqual(evidence_quality("read"), "observed")
        self.assertEqual(VERIFIED_TOOLS, frozenset(
            n for n, t in EVIDENCE_QUALITY.items() if t == "verified"
        ))
        self.assertEqual(OBSERVED_TOOLS, frozenset(
            n for n, t in EVIDENCE_QUALITY.items() if t == "observed"
        ))

    def test_structured_judgment_tools_are_verified_and_used_by_evidence_validity(self):
        """Gap 2: judgment detection must not maintain a parallel name set."""
        import inspect

        from services import evidence_validity

        self.assertIn(RELEASE_PROMOTION_JUDGMENT, STRUCTURED_JUDGMENT_TOOLS)
        self.assertIn(SOURCE_ROOT_JUDGMENT, STRUCTURED_JUDGMENT_TOOLS)
        for name in STRUCTURED_JUDGMENT_TOOLS:
            self.assertEqual(evidence_quality(name), "verified", name)
        # evidence_validity must use tool_identity.STRUCTURED_JUDGMENT_TOOLS (no local set).
        src = inspect.getsource(evidence_validity)
        self.assertIn("STRUCTURED_JUDGMENT_TOOLS", src)
        self.assertNotIn("_JUDGMENT_TOOLS = {", src)
        # Structured judgment with schema+verdict is valid evidence.
        invalid, reason = evidence_validity.invalid_tool_result(
            RELEASE_PROMOTION_JUDGMENT,
            {"ok": True, "schema": "nova.release.judgment.v1", "verdict": "promote"},
        )
        self.assertFalse(invalid, reason)

    def test_dispatch_and_wiring_use_tool_identity_for_release_tools(self):
        """Gap 3: high-traffic surfaces alias to tool_identity constants."""
        from services.nova_tool_dispatch import _PLANNED_TOOL_ALIASES
        from services.nova_wiring_inventory import WIRING_SURFACES
        from services.tool_identity import RELEASE_REBUILD_VERIFY, RELEASE_VALIDATION_RUN

        self.assertEqual(_PLANNED_TOOL_ALIASES["tool_release_rebuild_verify"], RELEASE_REBUILD_VERIFY)
        self.assertEqual(_PLANNED_TOOL_ALIASES["tool_release_validation_run"], RELEASE_VALIDATION_RUN)
        release_surface = next(s for s in WIRING_SURFACES if s.surface_id == "release")
        self.assertIn(RELEASE_REBUILD_VERIFY, release_surface.planned_tools)
        self.assertIn(RELEASE_VALIDATION_RUN, release_surface.planned_tools)

    def test_quality_tool_names_are_known_to_work_tree(self):
        """Membership check lives in tests only — never fail Nova at import."""
        import work_tree

        known = set(work_tree._KNOWN_TOOL_NAMES)
        quality_names = all_quality_tool_names()
        unknown = sorted(quality_names - known)
        self.assertEqual(
            unknown,
            [],
            f"tool_identity names not in work_tree._KNOWN_TOOL_NAMES: {unknown}",
        )

    def test_seeded_ladder_tools_draw_from_tool_identity(self):
        seeded_tools = set()
        for ladder in _SEEDED.values():
            seeded_tools |= collect_marker_tool_names(ladder.markers)
        quality = all_quality_tool_names()
        unknown = sorted(seeded_tools - quality)
        self.assertEqual(
            unknown,
            [],
            f"seeded marker tools missing from EVIDENCE_QUALITY: {unknown}",
        )

    def test_alias_rewrites_historical_evidence_tool_names(self):
        # Simulate a rename: old evidence string still measures as verified.
        with mock.patch.dict(TOOL_ALIASES, {"legacy_rebuild_tool": RELEASE_REBUILD_VERIFY}, clear=False):
            self.assertEqual(
                canonicalize_tool_name("legacy_rebuild_tool"),
                RELEASE_REBUILD_VERIFY,
            )
            self.assertTrue(is_verified_tool("legacy_rebuild_tool"))
            payload = measure_task_progress(
                task_title="Rebuild package",
                task_status="open",
                work_class="release_readiness_gap",
                source_type="release",
                branch_title="Release package is stale behind live source",
                evidence=[
                    {
                        "tool_name": "read",
                        "result_text": "ledger package seed",
                        "created_at": "2026-07-31T12:00:00",
                    },
                    {
                        "tool_name": "read",
                        "result_text": "source drift stale",
                        "created_at": "2026-07-31T12:01:00",
                    },
                    {
                        "tool_name": "legacy_rebuild_tool",
                        "result_text": "ok",
                        "created_at": "2026-07-31T12:02:00",
                    },
                ],
                learned={},
            )
        rebuilt = next(m for m in payload["markers"] if m["id"] == "package_rebuilt")
        self.assertTrue(rebuilt.get("counts"))
        self.assertEqual(rebuilt.get("quality"), "verified")


class WorkTreeTaskProgressTests(unittest.TestCase):
    def test_seeded_families_include_release(self):
        families = {row["family_key"] for row in list_seeded_families()}
        self.assertIn("release_readiness_gap|release", families)
        self.assertIn("governance_pressure|root_closure_inventory", families)

    def test_release_task_without_evidence_is_zero_not_started(self):
        payload = measure_task_progress(
            task_id="t1",
            task_title="Read release ledger for current package",
            task_status="open",
            work_class="release_readiness_gap",
            source_type="release",
            branch_title="Release package is stale behind live source",
            evidence=[],
            task_meta={"expected_tool": "read"},
        )
        self.assertEqual(payload["percent"], 0)
        self.assertEqual(payload["motion"], "not_started")
        self.assertTrue(payload["intent"])
        self.assertTrue(payload["solution"])
        self.assertGreaterEqual(payload["markers_total"], 3)
        self.assertEqual(payload["markers_achieved"], 0)
        self.assertEqual(payload["effort_count"], 0)
        self.assertIsNotNone(payload.get("next_marker"))

    def test_release_rebuild_evidence_advances_markers(self):
        from datetime import datetime, timedelta

        now = datetime.now()
        evidence = [
            {
                "evidence_id": "e1",
                "tool_name": "read",
                "tool_args": ["runtime/release"],
                "result_text": "ledger path ok",
                "created_at": (now - timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%S"),
            },
            {
                "evidence_id": "e2",
                "tool_name": "release_rebuild_verify",
                "tool_args": [],
                "result_text": "rebuild ok",
                "created_at": (now - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%S"),
            },
        ]
        payload = measure_task_progress(
            task_title="Rebuild and verify release package from current source",
            task_status="open",
            work_class="release_readiness_gap",
            source_type="release",
            branch_title="Release package is stale behind live source",
            evidence=evidence,
            stall_hours=6.0,
        )
        self.assertGreaterEqual(payload["percent"], 40)
        self.assertLess(payload["percent"], 100)
        self.assertEqual(payload["motion"], "moving")
        self.assertGreaterEqual(payload["markers_achieved"], 1)
        self.assertEqual(payload["effort_count"], 2)

    def test_complete_without_effort_is_not_one_hundred(self):
        """Closed finding with no tools must not invent 100% / full markers."""
        payload = measure_task_progress(
            task_title="anything",
            task_status="complete",
            work_class="release_readiness_gap",
            source_type="release",
            evidence=[],
        )
        self.assertEqual(payload["percent"], 0)
        self.assertEqual(payload["motion"], "done")
        self.assertTrue(payload.get("closed_without_effort"))
        self.assertFalse(any(m.get("achieved") for m in payload["markers"]))

    def test_complete_with_effort_is_one_hundred(self):
        payload = measure_task_progress(
            task_title="Rebuild package",
            task_status="complete",
            work_class="release_readiness_gap",
            source_type="release",
            branch_title="Release package is stale behind live source",
            evidence=[
                {
                    "tool_name": "read",
                    "result_text": "ledger package seed source stale",
                    "created_at": "2026-08-01T12:00:00",
                },
                {
                    "tool_name": "release_rebuild_verify",
                    "result_text": "ok",
                    "created_at": "2026-08-01T12:10:00",
                },
            ],
        )
        self.assertEqual(payload["percent"], 100)
        self.assertEqual(payload["motion"], "done")
        self.assertTrue(all(m["achieved"] for m in payload["markers"]))
        self.assertGreaterEqual(payload["effort_count"], 1)

    def test_stalled_when_evidence_old(self):
        evidence = [
            {
                "tool_name": "read",
                "result_text": "ledger",
                "tool_args": [],
                "created_at": "2020-01-01T00:00:00",
            }
        ]
        payload = measure_task_progress(
            task_title="Read release ledger for current package",
            task_status="open",
            work_class="release_readiness_gap",
            source_type="release",
            branch_title="Release package is stale behind live source",
            evidence=evidence,
            stall_hours=1.0,
        )
        self.assertEqual(payload["motion"], "stalled")
        self.assertGreater(payload["percent"], 0)

    def test_generic_ladder_for_unknown_family(self):
        ladder = get_ladder(work_class="novel_work", source_type="novel_source")
        self.assertIn("novel_work|novel_source", ladder.family_key)
        payload = measure_task_progress(
            task_title="Do novel thing",
            task_status="open",
            work_class="novel_work",
            source_type="novel_source",
            evidence=[{"tool_name": "read", "result_text": "ok", "created_at": "t"}],
        )
        self.assertGreaterEqual(payload["percent"], 30)
        self.assertEqual(payload["motion"], "moving")

    def test_learn_patterns_handles_missing_db(self):
        payload = learn_tool_patterns_from_history(
            work_class="release_readiness_gap",
            source_type="release",
            db_path=Path("runtime/_internal/does_not_exist_work_tree.db"),
        )
        self.assertFalse(payload.get("ok"))

    def test_save_and_load_learned_ladders(self):
        ladder = SolutionLadder(
            family_key="demo|demo",
            intent="Demo intent",
            solution="Demo solution",
            source="learned",
            markers=(
                SolutionMarker("a", "A", 0.5, stage=0, any_evidence=True),
                SolutionMarker("b", "B", 0.5, stage=1, requires_complete=True),
            ),
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ladders.json"
            save_learned_ladders({"demo|demo": ladder}, path=path)
            loaded = load_learned_ladders(path=path)
            self.assertIn("demo|demo", loaded)
            self.assertEqual(loaded["demo|demo"].intent, "Demo intent")
            self.assertEqual(len(loaded["demo|demo"].markers), 2)

    def test_hybrid_merge_prefers_seeded_intent(self):
        learned = {
            "release_readiness_gap|release": SolutionLadder(
                family_key="release_readiness_gap|release",
                intent="WRONG intent from history",
                solution="WRONG solution",
                source="learned",
                markers=(
                    SolutionMarker("via_custom", "Custom", 1.0, stage=0, tools=("custom_tool_xyz",)),
                ),
            )
        }
        ladder = get_ladder(
            work_class="release_readiness_gap",
            source_type="release",
            learned=learned,
        )
        self.assertIn("trustworthy", ladder.intent.lower())
        self.assertEqual(ladder.source, "hybrid")
        tools = {t for m in ladder.markers for t in m.tools}
        self.assertIn("custom_tool_xyz", tools)

    def test_learn_families_from_history_dry(self):
        # Should not crash; may return empty families on tiny DBs
        with mock.patch(
            "services.work_tree_task_progress.work_tree_db_path",
            return_value=Path("runtime/_internal/does_not_exist.db"),
        ):
            result = learn_families_from_history(persist=False)
        self.assertFalse(result.get("ok"))

    def test_rebuild_without_prereqs_does_not_count(self):
        """Honest: rebuild evidence alone cannot count until drift is understood."""
        from datetime import datetime, timedelta

        now = datetime.now()
        evidence = [
            {
                "tool_name": "release_rebuild_verify",
                "result_text": "rebuild ok",
                "created_at": now.strftime("%Y-%m-%dT%H:%M:%S"),
            }
        ]
        payload = measure_task_progress(
            task_title="Rebuild and verify release package from current source",
            task_status="open",
            work_class="release_readiness_gap",
            source_type="release",
            branch_title="Release package rebuild",
            evidence=evidence,
            stall_hours=6.0,
            learned={},  # seeded only
        )
        rebuilt = next(m for m in payload["markers"] if m["id"] == "package_rebuilt")
        self.assertTrue(rebuilt["observed"] or rebuilt["quality"] == "verified")
        self.assertFalse(rebuilt["counts"])
        self.assertFalse(rebuilt["prereqs_met"])
        self.assertEqual(payload["percent"], 0)

    def test_release_full_honest_path(self):
        from datetime import datetime, timedelta

        now = datetime.now()
        ts = lambda m: (now - timedelta(minutes=m)).strftime("%Y-%m-%dT%H:%M:%S")
        evidence = [
            {
                "tool_name": "read",
                "tool_args": ["ledger"],
                "result_text": "package ledger",
                "created_at": ts(40),
            },
            {
                "tool_name": "read",
                "tool_args": ["source"],
                "result_text": "source changed stale drift",
                "created_at": ts(30),
            },
            {
                "tool_name": "release_rebuild_verify",
                "result_text": "rebuild ok",
                "created_at": ts(20),
            },
            {
                "tool_name": "release_record_validation_outcome",
                "result_text": "validation ok",
                "created_at": ts(10),
            },
        ]
        payload = measure_task_progress(
            task_title="Release validation",
            task_status="open",
            work_class="release_readiness_gap",
            source_type="release",
            branch_title="Release package ready path",
            evidence=evidence,
            stall_hours=6.0,
            learned={},
        )
        self.assertGreaterEqual(payload["percent"], 75)
        self.assertLess(payload["percent"], 100)
        self.assertEqual(payload["motion"], "moving")
        rebuilt = next(m for m in payload["markers"] if m["id"] == "package_rebuilt")
        self.assertTrue(rebuilt["counts"])
        self.assertTrue(rebuilt["verified"])
        self.assertEqual(rebuilt["confidence"], 1.0)

    def test_stale_branch_contradicts_validation_without_rebuild_chain(self):
        from datetime import datetime

        now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        payload = measure_task_progress(
            task_title="Record validation",
            task_status="open",
            work_class="release_readiness_gap",
            source_type="release",
            branch_title="Release package is stale behind live source",
            evidence=[
                {
                    "tool_name": "release_record_validation_outcome",
                    "result_text": "ok",
                    "created_at": now,
                }
            ],
            learned={},
            context={"release_stale": True},
        )
        validation = next(m for m in payload["markers"] if m["id"] == "validation_recorded")
        self.assertTrue(validation.get("contradicted") or not validation.get("counts"))

    def test_solution_progress_is_branch_owned_not_stem_owned(self):
        """Root unit: progress lives on the branch/finding across sequence stems."""
        from datetime import datetime

        import work_tree
        from services.work_tree_task_progress import measure_solution_progress

        tree = work_tree.create_tree("Solution progress unit")
        work_tree._TREES[tree.tree_id] = tree
        root = work_tree.create_branch(tree.tree_id, "Root", "work")
        work_tree._BRANCHES[root.branch_id] = root
        tree.root_branch_id = root.branch_id
        branch = work_tree.create_branch(
            tree.tree_id,
            "Release package is stale behind live source",
            "work",
            root.branch_id,
        )
        branch.work_class = "release_readiness_gap"
        branch.source_type = "release"
        work_tree._BRANCHES[branch.branch_id] = branch
        step1 = work_tree.add_task_to_branch(
            branch.branch_id,
            "Read release ledger for current package",
            meta={"expected_tool": "read"},
        )
        now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        work_tree.record_task_evidence(
            branch_id=branch.branch_id,
            task_id=step1.task_id,
            tool_name="read",
            tool_args=["release_ledger.jsonl"],
            result={"text": "ledger package seed artifact"},
        )
        work_tree.mark_task_complete(step1.task_id)
        step2 = work_tree.add_task_to_branch(
            branch.branch_id,
            "Rebuild and verify release package from current source",
            meta={"expected_tool": "release_rebuild_verify"},
        )
        # Intermediate stem complete must not force 100% solution.
        mid = work_tree._branch_progress_payload(branch)
        self.assertIsNotNone(mid)
        self.assertEqual(mid.get("unit"), "solution")
        self.assertLess(int(mid.get("percent") or 0), 100)
        self.assertNotEqual(mid.get("motion"), "done")
        # Same number whether we stamp via task id or branch id.
        via_task = work_tree.stamp_task_progress(step2.task_id, persist=False)
        via_branch = work_tree.stamp_branch_progress(branch.branch_id, persist=False)
        self.assertEqual(via_task.get("percent"), via_branch.get("percent"))
        self.assertEqual(
            (branch.source_payload or {}).get("solution_progress", {}).get("percent"),
            via_branch.get("percent"),
        )
        # Direct solution measure with branch evidence is the contract.
        direct = measure_solution_progress(
            work_class="release_readiness_gap",
            source_type="release",
            branch_title=branch.title,
            current_step_title=step2.title,
            solution_status="open",
            evidence=work_tree.list_branch_evidence(branch.branch_id, limit=20),
            context={"release_stale": True},
        )
        self.assertEqual(direct.get("unit"), "solution")
        self.assertGreaterEqual(int(direct.get("percent") or 0), 0)

    def test_solution_timeline_surfaced_and_work_started(self):
        """Finding carries radar time and work-start time for operators."""
        import work_tree

        tree = work_tree.create_tree("Timeline stamps")
        work_tree._TREES[tree.tree_id] = tree
        root = work_tree.create_branch(tree.tree_id, "Root", "work")
        work_tree._BRANCHES[root.branch_id] = root
        tree.root_branch_id = root.branch_id
        branch = work_tree.create_branch(
            tree.tree_id,
            "Release package is verified but validation outcome is missing",
            "work",
            root.branch_id,
        )
        branch.work_class = "release_readiness_gap"
        branch.source_type = "release"
        work_tree._BRANCHES[branch.branch_id] = branch
        task = work_tree.add_task_to_branch(
            branch.branch_id,
            "Read release ledger for current package",
            meta={"expected_tool": "read"},
        )
        before = work_tree._branch_progress_payload(branch)
        self.assertTrue(str(before.get("surfaced_at") or "").strip())
        self.assertEqual(before.get("work_start_state"), "not_started")
        self.assertFalse(str(before.get("work_started_at") or "").strip())
        self.assertTrue(str(before.get("current_step_opened_at") or "").strip())
        work_tree.record_task_evidence(
            branch_id=branch.branch_id,
            task_id=task.task_id,
            tool_name="read",
            tool_args=["ledger.jsonl"],
            result={"text": "ledger package seed"},
        )
        after = work_tree._branch_progress_payload(branch)
        self.assertEqual(after.get("work_start_state"), "started")
        self.assertTrue(str(after.get("work_started_at") or "").strip())
        self.assertTrue(str((branch.source_payload or {}).get("work_started_at") or "").strip())


if __name__ == "__main__":
    unittest.main()
