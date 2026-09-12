# Nova Living Ledger

_Generated: 2026-09-12 13:52_

Two sources feed this document: **developer sessions** and **Nova's own scan findings**.
Append to `docs/ledger/session_log.jsonl` (developer) or `docs/ledger/nova_findings.jsonl` (Nova),
then re-run `python scripts/generate_nova_ledger.py`.

---

## Session History

Chronological record of every developer session that touched Nova.

### 2026-09-12 — claude-cowork
_Session: push-prep-20260912_

**Modules touched:** `services/gatekeeper.py`, `services/regression_truth_registry.py`, `services/regression_status_projection.py`, `scripts/regression_lane_worker.py`, `autonomy_maintenance.py`

**Changes:**
- Gatekeeper observation layer
- Regression Truth Registry
- status projection
- detached lane worker
- source root inventory alignments
- test profile inventory alignments

**Meta:** 40 tests added

### 2026-09-12 — claude-cowork
_Session: hygiene-and-aliases-20260912_

**Modules touched:** `nova_core.py`, `tools/registry.py`, `services/nova_tool_policy.py`, `tests/test_nova_core_identity_context.py`, `tests/test_tool_registry.py`

**Changes:**
- Fix Spanish ratio estimation mojibake
- add web search/fetch aliases to research handlers and registry
- strip UTF-8 BOM from 28 Python files

**Meta:** 159 tests added

### 2026-09-12 — claude-cowork
_Session: leah-memory-recall-at5-20260912_

**Modules touched:** `services/memory_routing.py`, `tests/test_memory_routing_service.py`, `capabilities_roadmap.json`

**Changes:**
- Fix memory routing purpose inference to match explicit recall cues (what did I tell you
- you said
- we discussed
- last time
- etc.)
- unblocking new-session mem_recall queries for AT-5

**Meta:** 45 tests added

### 2026-09-12 — claude-cowork
_Session: fix-guard-file-leak-20260912_

**Modules touched:** `nova_guard.py`, `tests/test_nova_guard_boot.py`

**Changes:**
- Fix file handle leak in nova_guard._maintenance_tick by wrapping MAINTENANCE_LOG open in context manager

**Meta:** 9 tests added

### 2026-09-12 — claude-cowork
_Session: policy-example-update-20260912_

**Modules touched:** `policy.example.json`

**Changes:**
- Synchronize policy.example.json schema and sections with policy.json

**Meta:** 14 tests added

### 2026-09-12 — claude-cowork
_Session: fix-signal-ingestion-reopen-contract-20260912_

**Modules touched:** `services/work_tree_signal_ingestion.py`, `tests/test_work_tree_signal_ingestion_service.py`

**Changes:**
- Fix root-cause signal ingestion contract defect: prevent ingest_signal from reopening closed branches when the signal sequence has no unfulfilled tasks
- and auto-resolve branches in apply_branch_update when 0 open tasks and no new task stems remain

**Meta:** 144 tests added

### 2026-09-12 — claude-cowork
_Session: fix-signal-reopen-trail-refused-20260912_

**Modules touched:** `services/work_tree_signal_ingestion.py`

**Changes:**
- Fix root-cause signal ingestion contract defect: check trail_world_holds before reopening closed branches
- and treat items with all closed (complete/dropped) tasks as satisfied in _sequence_item_satisfied

**Meta:** 234 tests added

### 2026-09-12 — claude-cowork
_Session: consolidate-type-utils-20260912_

**Modules touched:** `services/type_utils.py`, `services/autonomy_execution_gate.py`, `services/autonomy_orchestrator.py`, `services/autonomy_orchestrator_ledger.py`, `services/decision_proposal_judge.py`, `services/nova_grounded_self_report.py`, `services/nova_mission.py`, `services/nova_mission_owner_verdicts.py`, `services/recurring_finding_lifecycle.py`, `services/regression_evidence.py`, `services/regression_truth_registry.py`, `services/solution_trail.py`, `services/work_tree_operator_hold.py`, `services/work_tree_pressure_snapshot.py`

**Changes:**
- Created services/type_utils.py and consolidated duplicate type-casting helpers (_as_dict
- _as_list
- _as_int
- _as_float
- _as_bool
- _as_bool_or_none
- _text) across 13 service modules

**Meta:** 155 tests added

### 2026-09-12 — claude-cowork
_Session: leah-emotional-state-model-20260912_

**Modules touched:** `services/leah_emotional_state_model.py`, `tests/test_leah_emotional_state_model.py`, `capabilities.json`, `capabilities_roadmap.json`, `services/capability_finish_ownership.py`, `services/regression_lanes.py`

**Changes:**
- Implement leah_emotional_state_model capability: valence/arousal/confidence dimension tracking
- text signal analysis
- primary emotion derivation
- decay dynamics
- prompt posture modulation
- disk persistence
- and CognitiveWorkspace integration

**Meta:** 49 tests added

### 2026-09-12 — claude-cowork
_Session: wire-leah-chat-flow-20260912_

**Modules touched:** `services/nova_http_request_binding.py`, `nova_http.py`, `policy.json`, `policy.example.json`, `services/capability_finish_ownership.py`, `tests/test_nova_http_request_binding.py`

**Changes:**
- Wire leah_voice_persona_engine and leah_emotional_state_model into HTTP /api/chat request binding; promote capabilities in policy.json; update finish ownership

**Meta:** 134 tests added

### 2026-09-09 — opencode

**Modules touched:** `scripts/regression_lane_worker.py`, `tests/test_autonomy_maintenance.py`, `tests/test_regression_lane_worker_integration.py`

**Changes:**
- fix max_lane_seconds default; hermetic autonomy tests; integration tempdir fix

_Note: Regression Truth Registry FULL certification achieved on fingerprint 9230977c17863d2ebc8db072e1c92985103f1d20121f57f10058ded8a1da6e78. Fixed max_lane_seconds() bug (unset env var -> 1s worker timeout). Hermetic 10 _execute_autonomy_recommendation tests via _isolated_work_tree_db(); fixed WinError32 tempdir cleanup in lane_worker_integration (ignore_cleanup_errors). Unit lane PASS 5848s (956 tests), behavior PASS 1953s (144), integration PASS 85s (83). regression_status.json OK/FULL; control surface last_regression_status=OK; regression owner verdict ready blocks_green. truth_ready still False due to pre-existing core_gate_release_drift (layer_maturity)._

### 2026-09-08 — opencode
_Session: regression-truth-registry-slice1-20260908_

**Modules touched:** `services/regression_truth_registry.py`, `tests/test_regression_truth_registry.py`

**Changes:**
- Slice 1 of Regression Truth Registry: pure per-lane truth store (append-only JSONL records)
- fingerprint-only freshness (time is metadata)
- derived certification ladder FULL/PARTIAL/TIMED_OUT/FAILED/NOT_CURRENT with explicit reason
- pending_lanes honoring unit-to-behavior-to-integration eligibility chain
- optional derived truth.json snapshot

**Meta:** 13 tests added

_Note: Test-first per design decided by operator (fingerprint-only freshness; staggered evidence-driven cadence; fast check stays on existing pulse/health; no new lane; no age-based staleness). Pure module, no wiring, no changes to live consumers or regression_status.json. All 13 unit tests green._

### 2026-09-08 — opencode
_Session: regression-truth-registry-slice1-semantic-lock-20260908_

**Modules touched:** `services/regression_truth_registry.py`, `tests/test_regression_truth_registry.py`

**Changes:**
- Applied operator semantic lock to slice 1: FAILED now narrowly means explicit FAILED on the current fingerprint only (TIMED_OUT is an incomplete observation
- never FAILED); certification ladder is FULL/FAILED/PARTIAL/NOT_CURRENT with machine-readable reason codes (e.g. behavior_timed_out_on_current
- integration_not_observed_on_current
- integration_not_current
- unit_failed_on_current); pending_lanes renamed lanes_needing_observation and returns all missing lane observations in preferred order without gating (registry states what is known; scheduler decides what to observe next)

**Meta:** 15 tests added

_Note: Supersedes slice-1 log entry pending_lanes/eligibility-chain wording. Added the two required semantic tests (TIMED_OUT is not FAILED; needs_observation does not become the scheduler) plus six-month-old-record-is-current fingerprint-freshness test. 15 unit tests green; still pure module, no wiring, no live changes._

### 2026-09-08 — opencode
_Session: regression-truth-registry-slice2-20260908_

**Modules touched:** `autonomy_maintenance.py`, `services/regression_truth_registry.py`, `services/regression_status_projection.py`, `tests/test_autonomy_maintenance.py`, `tests/test_regression_truth_registry.py`, `tests/test_regression_status_projection.py`

**Changes:**
- scheduler rewired to per-lane staggered regression runs recorded into regression_truth.jsonl; regression_status.json now written by projection (scheduler:regression_truth_registry); removed whole-file TIMED_OUT path and _write_host_regression_timeout_status; per-day per-lane attempt rail via state regression_lane_attempts; FIRST five pinned scheduler tests rewritten to new contract plus new stagger test

**Meta:** 28 tests added

_Note: slice-2 of regression truth registry. 15 registry + 7 projection + 6 rewritten/new maintenance tests verified green. net-neutral for mission gate and signal intake (regression_outcome_failed treats PARTIAL/NOT_CURRENT as failed). guard-cap: per-lane budget 720s bounded by nova_guard 20min maintenance cap; cold lanes cannot FULL under maintenance -> honest per-lane TIMED_OUT -> PARTIAL. known consumer delta: nova_core pulse regression alert only on startswith(FAIL), PARTIAL no longer alerts; slice-3 decision. run_once smoke test unverified due inherent runtime; regression fully mocked there._

### 2026-09-08 — opencode
_Session: regression-truth-registry-slice3-20260908_

**Modules touched:** `scripts/regression_lane_worker.py`, `autonomy_maintenance.py`, `nova_core.py`, `services/release_validation.py`, `services/regression_evidence.py`, `services/control_status_surfaces.py`, `tests/test_regression_lane_worker.py`, `tests/test_autonomy_maintenance.py`

**Changes:**
- Detached per-lane regression worker making FULL reachable outside guard-capped maintenance; spawn-time attempt rail with pid crash-recovery; pulse alert migrated from startswith(FAIL) to explicit regression truth states; release gate and evidence payload enriched with certification/reason; control status surfaces expose certification/reason

**Meta:** 6 tests added

_Note: PARTIAL remains unresolved/not-certified; no readiness changes. 60-test affected-surface run green. Full maintenance module too slow, verify by subset. run_once smoke test unverified (pre-existing slow, mocked)._

### 2026-09-08 — opencode
_Session: regression-truth-registry-e2e-20260908_

**Modules touched:** `scripts/regression_lane_worker.py`, `autonomy_maintenance.py`, `services/regression_lanes.py`, `tests/test_regression_lane_worker_integration.py`, `tests/test_autonomy_maintenance.py`

**Changes:**
- Real end-to-end harness spawning the actual worker and full maintenance spawn chain against a stub lane runner; worker handle tracking + prune to stop detached-Popen GC warnings and give observable worker state; extracted _finalize_regression_branch for run_once outer-cycle stale semantics; NOVA_REGRESSION_RUNNER test seam; unit lane now includes registry/projection/worker/integration/gatekeeper tests; fixed run_once_logs test leaking real detached lane runs under new spawn semantics

**Meta:** 6 tests added

_Note: Proved FULL reachable: full chain (spawn->worker->run->record->republish->consumers) verified on real processes. run_once smoke green 6.4s. Pre-existing lane drift fixed (test_gatekeeper unregistered since 9/7 broke profile-inventory test). Full 100+ module unit lane still to run to completion in production._

### 2026-09-07 — claude-cowork
_Session: gatekeeper-governance-layer_

**Modules touched:** `services/gatekeeper.py`, `services/control_status.py`, `autonomy_maintenance.py`, `tests/test_gatekeeper.py`, `tests/test_autonomy_maintenance.py`

**Changes:**
- Gatekeeper service implemented - validate/append/compact/summarize
- observation_key
- first/last observed_at
- Control-status exposes gatekeeper ledger and gatekeeper_ok
- autonomy_maintenance records regression-gate observations on source-fingerprint change
- Tests - test_gatekeeper.py (4) plus retries-after-fingerprint-change (1)

**Meta:** 5 tests added · docs updated: `docs/SERVICES_INDEX.md`, `docs/FUNCTION_INDEX.md`

_Note: Close-out attests only the Gatekeeper slice verified 2026-09-07. Sessions 2026-09-02 through 2026-09-07 remain unlogged (ledger last logged 2026-09-01 mill-skip-promote). Provenance: Gus = architect/authority, claude-cowork = implementation agent, NOVA = system, evidence = tests plus live runtime (records ledger compacted to 3 rows, same_failed_fingerprint seen_count 21; all-lanes regression run pid 32424 started 22:15:17)._

### 2026-09-07 — codex
_Session: gatekeeper-postal-docs-20260907_

**Modules touched:** `services/gatekeeper.py`, `autonomy_maintenance.py`, `services/control_status.py`, `tests/test_gatekeeper.py`, `docs/DOC_OWNERSHIP.md`, `docs/SYSTEM_MAP.md`

**Changes:**
- Implemented evidence-backed Gatekeeper observation and regression lesson flow
- Documented Gatekeeper ownership and system mapping

**Meta:** 20 tests added · docs added: `none` · docs updated: `docs/DOC_OWNERSHIP.md`, `docs/SYSTEM_MAP.md`

_Note: Gatekeeper is observational only; no policy mutation or automatic retirement. Runtime records compact repeated observations with seen_count and first/last timestamps._

### 2026-09-07 — codex
_Session: ledger-backfill-correction-20260907_

**Modules touched:** `docs/ledger/session_log.jsonl`, `docs/NOVA_LEDGER.md`

**Changes:**
- Backfilled verified runtime-reset
- regression-root
- contract-reconciliation
- and release-validation work preceding Gatekeeper

**Meta:** docs added: `none` · docs updated: `docs/NOVA_LEDGER.md`

_Note: Supersedes the earlier note claiming the 2026-09-02 through 2026-09-07 work remained unlogged. Backfill is consolidated where exact session boundaries were unavailable; no unverified claims were added._

### 2026-09-07 — codex
_Session: gatekeeper-ring1-registration-20260907_

**Modules touched:** `services/nova_root_inventory.py`, `docs/DOC_OWNERSHIP.md`, `docs/SYSTEM_MAP.md`

**Changes:**
- Registered Gatekeeper in autonomy source-root inventory and corrected path classification so Ring 1 map integrity reports zero unclassified source files

**Meta:** 18 tests added · docs added: `none` · docs updated: `none`

_Note: Gatekeeper Ring 1 debt closed: live source inventory ok=true gap_count=0. One unrelated existing wiring test still expects empty status to be non-closed._

### 2026-09-07 — codex
_Session: ring1-phase2-archive-20260907_

**Modules touched:** `docs/PHASE2_SAFETY_ENVELOPE.md`, `docs/archive/PHASE2_SAFETY_ENVELOPE.md`

**Changes:**
- Moved classified historical Phase 2 Safety Envelope document from docs root into docs/archive to clear undeclared current-document drift while preserving the full artifact

**Meta:** 1 tests added · docs added: `none` · docs updated: `none`

_Note: Ring 1 source inventory remains ok=true gap_count=0; Gatekeeper classification remains clean._

### 2026-09-06 — codex
_Session: contract-reconciliation-and-release-20260906_

**Modules touched:** `services/sock_service.py`, `services/regression_lanes.py`, `services/regression_profile_inventory.py`, `services/nova_live_closure.py`, `autonomy_maintenance.py`, `nova_http.py`, `scripts/build_release_package.ps1`, `scripts/verify_release_package.ps1`, `tests/test_sock_service.py`, `tests/test_autonomy_maintenance.py`, `tests/test_autonomy_orchestrator_service.py`, `tests/test_http_session_manager.py`, `tests/test_release_package_scripts.py`, `tests/test_windows_installer_scripts.py`

**Changes:**
- Reconciled stale SOCK and mission contracts
- Removed Ed-Fi core from active regression and closure contracts while preserving backpack surfaces
- Fixed Work Tree attempted-versus-complete expectations and legacy retirement discovery
- Fixed HTTP session continuity deletion
- Fixed release package PowerShell parsing and forbidden-content verification

**Meta:** 124 tests added · docs added: `none` · docs updated: `none`

_Note: Full uncapped regression completed with unit and behavior green; integration was subsequently rerun after package/installer fixes and passed 83 tests. Ed-Fi core remains repository residue for later push cleanup, not an active Nova contract._

### 2026-09-05 — codex
_Session: runtime-reset-and-regression-root-20260905_

**Modules touched:** `work_tree.py`, `autonomy_maintenance.py`, `runtime/_internal/work_tree.db`, `runtime/regression_status.json`

**Changes:**
- Archived and reset runtime state without deleting project code
- Proved full-file SQLite guard read and refresh/preview recomputation costs
- Added header-only database guard and controlled A/B evidence

**Meta:** 70 tests added · docs added: `none` · docs updated: `none`

_Note: Runtime archive preserved before reset. Work Tree tests 70 passed. A/B profiles used the same stopped-service test conditions; no production policy change was made._

### 2026-09-01 — grok
_Session: mill-capacity-lease_

**Modules touched:** `services/sock_service.py`, `services/solution_trail.py`, `work_tree.py`, `services/work_tree_seeding.py`

**Changes:**
- Mill exposes mill_judgment_signal from derived trail kind
- SOCK leases temporary mill capacity without rewriting policy
- 14B has no evidenced class so it is never chosen

**Meta:** 8 tests added

_Note: Standing chat stays qwen2.5:7b. 9B is the evidenced deliberate sip. Paid-trail redundant+inherited stays standing because 9B lost that class._

### 2026-09-01 — grok
_Session: standing-4b-apply_

**Modules touched:** `policy.json`, `services/sock_service.py`

**Changes:**
- Standing chat and routing set to qwen3.5:4b from mill evidence
- Vision stays qwen2.5vl:7b
- 9B remains mill sip

_Note: Operator asked apply. 7B kept pulled as fallback. sock backup restores 7B standing._

### 2026-09-01 — grok
_Session: mill-lane-docs_

**Modules touched:** `docs/SOCK_SYSTEM.md`, `docs/AUTONOMY_AND_MISSION.md`, `docs/MILL_LANE_MEASURE_2026-09-01.md`, `docs/DOC_OWNERSHIP.md`, `docs/NOVA_POSTAL.md`

**Changes:**
- Logged mill lane measure scores
- SOCK mill lease contract
- Overnight mill-skip vs pulse finding

**Meta:** docs added: `docs/MILL_LANE_MEASURE_2026-09-01.md` · docs updated: `docs/SOCK_SYSTEM.md`, `docs/AUTONOMY_AND_MISSION.md`, `docs/DOC_OWNERSHIP.md`, `docs/NOVA_POSTAL.md`

_Note: Evidence for future: generation beat size; 4B standing; 9B sip; 14B no class; overnight combo unused._

### 2026-09-01 — grok
_Session: mill-skip-causal_

**Modules touched:** `autonomy_maintenance.py`, `work_tree.py`, `services/solution_trail.py`, `services/observation_spine.py`, `services/autonomy_orchestrator.py`, `services/work_tree_signal_ingestion.py`

**Changes:**
- Mill skip is a trailing loop event that runs mill then changes the next cycle
- Paid trail and sip skip hold the world and block compact-lane remint
- Ingest keeps attempt_judgments so trail is not wiped
- source_root_judgment sip skip marks ATTEMPTED and does not remint

**Meta:** 4 tests added

_Note: Closure is a changed next cycle in the trail. Model lane closed. No SOCK apply. No commit._

### 2026-09-01 — grok
_Session: mill-skip-promote_

**Modules touched:** `docs/AUTONOMY_AND_MISSION.md`, `docs/SOCK_SYSTEM.md`, `docs/NOVA_POSTAL.md`, `docs/DOC_OWNERSHIP.md`, `docs/NOVA_LEDGER.md`

**Changes:**
- Promote mill skip/remint/stop/pulse as live mill-cycle control
- Leave mill sip-execute unwired-not-claimed
- Record decision mill_skip_remint_stop_pulse_promoted

**Meta:** docs updated: `docs/AUTONOMY_AND_MISSION.md`, `docs/SOCK_SYSTEM.md`, `docs/NOVA_POSTAL.md`, `docs/DOC_OWNERSHIP.md`

_Note: Live trail matched tests for skip/remint/stop/pulse only. No SOCK apply. Sip-execute not promoted._

### 2026-08-31 — grok
_Session: mill-veins-spine_

**Modules touched:** `services/work_tree_signal_ingestion.py`, `services/backpack_host/sanitize.py`, `tests/test_observation_spine.py`

**Changes:**
- Ingest create reopen refuse pulse observation spine
- Sequence mint pulses spine
- Sanitize resolve pulses spine

**Meta:** 3 tests added

_Note: Circulation on existing spine. No new store. Chat untouched._

### 2026-08-30 — grok
_Session: refuse-trail-core_

**Modules touched:** `services/solution_trail.py`, `work_tree.py`, `services/work_tree_signal_ingestion.py`, `autonomy_maintenance.py`, `tests/test_solution_trail.py`

**Changes:**
- Add refused trail judgment written without invoke
- Pickup honors branch-level refuse until retry_when fires
- Ingest teaches unclaimable no-stem branches on the same trail

**Meta:** 41 tests added

_Note: Core claim/instruct/refuse: learning is next selection under the release contract; finding stays open. Not a panel gate._

### 2026-08-30 — grok
_Session: refuse-trail-selection-exam_

**Modules touched:** `services/solution_trail.py`, `work_tree.py`, `autonomy_maintenance.py`, `static/control.js`, `tests/test_solution_trail.py`, `tests/test_autonomy_maintenance.py`

**Changes:**
- Derived branch_memory_kind shared by pickup and visual payload
- Record empty-claim vs inherited-attempt pressure on refuse
- Causal same-world pickup test with retry_when restore
- Leftover no-stem pin refuses without hiding the finding

**Meta:** 4 tests added

_Note: Selection exam not a panel cosmetics pass. Proof is next selection. Findings stay visible._

### 2026-08-29 — grok
_Session: c4-attempted-stem_

**Modules touched:** `work_tree.py`, `services/work_tree_signal_ingestion.py`

**Changes:**
- Execute keeps ATTEMPTED when finding unsatisfied so pickup still has a stem
- Ingest no longer mints meta-continuity cover after real stems already ran

**Meta:** 137 tests added

_Note: C4 only. No timeout change, no test isolation, no zip, no leftover branch close. Pickup treats ATTEMPTED as live after OPEN/ACTIVE._

### 2026-08-29 — github-copilot
_Session: inspect-ai-live-eval-20260829_

**Modules touched:** `tests/inspect_live/nova_live_runtime_eval.py`

**Changes:**
- Added first live Inspect AI integration proof task with adapter smoke phase named capability phase and scorer negative control

**Meta:** 2 tests added

_Note: Inspect logs produced; Phase 2 did not execute os_capability via operator_prompt so this is an integration proof with a surfaced routing/evidence gap, not a passed Nova capability evaluation._

### 2026-08-29 — grok
_Session: work-tree-loop-eval_

**Modules touched:** `tests/inspect_live/nova_work_tree_loop.py`, `tests/test_nova_work_tree_loop_eval.py`

**Changes:**
- Frozen Work Tree mission loop scores seven links from mill execute not chat
- Empty-read cover documented as category error that refuses close but still mis-admits

**Meta:** 3 tests added

_Note: Not live 76a2bb4e. Not panels. Kernel eval only._

### 2026-08-29 — grok
_Session: admission-kernel-whitebox_

**Modules touched:** `research/work_admission/kernel.py`, `research/work_admission/frozen_traces.py`, `research/work_admission/inspect_recorder.py`, `tests/test_work_admission_kernel.py`

**Changes:**
- Pure admission kernel proposal+snapshots+policy to deterministic JSON
- Frozen T0/T1/T2 traces registered before kernel
- Inspect recorder compares JSON only not a Nova gate

**Meta:** 12 tests added

_Note: White-box kernel evaluation, not live Nova proof. No routes, no work_tree.py change, no live 76a2bb4e._

### 2026-08-29 — grok
_Session: admission-v1-protect_

**Modules touched:** `research/work_admission/FREEZE_v1_ADDENDUM.json`, `research/work_admission/FREEZE_v1_unittest.txt`

**Changes:**
- Record v1 winning-path reason-code design question without editing hashed kernel
- Annotated tag work-admission-kernel-v1 on dfa8745
- Clean worktree verified 12 tests OK

**Meta:** 12 tests added

_Note: v1 kernel files untouched. No two-page research brief in repo._

### 2026-08-29 — grok
_Session: research-brief-v1_

**Modules touched:** `docs/RESEARCH_BRIEF.md`, `docs/DOC_OWNERSHIP.md`, `research/work_admission/FREEZE_v1_ADDENDUM.json`, `research/work_admission/FREEZE_v1_unittest.txt`

**Changes:**
- Separate post-freeze documentation commit from kernel v1
- Two-page research brief with safer frozen-cases wording and v1 limitations

**Meta:** docs added: `docs/RESEARCH_BRIEF.md`

_Note: Tag work-admission-kernel-v1 still on dfa8745. Public wording: predefined frozen cases; preregistered internal only._

### 2026-08-27 — grok
_Session: safety-envelope-review-close_

**Modules touched:** `nova_safety_envelope.py`, `services/work_tree_signal_ingestion.py`, `tests/test_safety_envelope.py`, `tests/test_work_tree_signal_ingestion_service.py`

**Changes:**
- Operator-accepted two passing pending reviews
- Failed gates now quarantine inside the human-veto window
- Quarantine-only is no longer open review pressure
- Resolved live safety-envelope branch_e6e96c6c

**Meta:** 4 tests added

_Note: Assisted Nova close of safety-envelope review pressure. pending=0, 2 promoted, 1 quarantined fail remains as settled fail._

### 2026-08-27 — grok
_Session: operator-review-calls_

**Modules touched:** `services/nova_root_inventory.py`, `services/work_tree_signal_ingestion.py`, `runtime/temporal/operator_calendar.ics`, `tests/test_source_root_inventory_service.py`, `tests/test_work_tree_signal_ingestion_service.py`

**Changes:**
- Classified five unclassified source files
- Cancelled past temporal verification calendar event
- Skip cancelled calendar items as work-tree pressure
- Resolved temporal inventory and restart-provenance branches

**Meta:** 2 tests added

_Note: Operator calls only. Left release validation, stale package, regression timeout, and capability gaps open._

### 2026-08-27 — grok
_Session: release-regression-roots_

**Modules touched:** `autonomy_maintenance.py`, `services/nova_wiring_inventory.py`, `runtime/regression_status.json`, `tests/test_autonomy_maintenance.py`

**Changes:**
- Daily regression timeout now writes host regression_status.json
- Dead regression lock is cleared
- Wiring surface points at backpack Ed-Fi files not deleted data_connector

**Meta:** 2 tests added

_Note: Evidence: 12-minute daily all-lanes timeout; Aug 1 OK file left in place; Aug 4 package verify passed but validation failed on stale regression, wiring-check, nova test. Offline wiring-check now OK. Did not rebuild package or rerun full regression._

### 2026-08-26 — codex
_Session: full-audit-20260826_

**Modules touched:** `docs/AUDIT_WORK_MAP_2026-08-25.md`

**Changes:**
- Recorded source inventory
- wiring
- live self-work
- and focused subsystem audit evidence with confirmed failures and unverified timeouts

_Note: No production repair made; audit mapping only_

### 2026-08-23 — grok
_Session: honest-complete-stamp_

**Modules touched:** `work_tree.py`, `tests/test_work_tree.py`

**Changes:**
- Execute tags attempted when the finding is still open
- Complete only when finding satisfied
- resolution already closed
- or scoped stem verified

_Note: False complete was tool-returned. Pickup and open-task count now see attempted stems as still open._

### 2026-08-23 — codex
_Session: scheduled-tree-counts-20260823_

**Modules touched:** `static/control.js`, `services/work_tree_signal_ingestion.py`

**Changes:**
- Clarified Scheduled Tree task-stem versus branch counts
- Advanced sequence past attempted stems without deleting breadcrumbs

**Meta:** 10 tests added

_Note: Preserved attempted task truth; broader legacy execution-contract tests still fail separately._

### 2026-08-23 — codex
_Session: meta-continuity-guard-20260823_

**Modules touched:** `services/work_tree_signal_ingestion.py`, `tests/test_work_tree_signal_ingestion_service.py`

**Changes:**
- Added unresolved-branch continuity task fallback with self-question
- Added regression test for open-branch no-stem continuity

**Meta:** 1 tests added

_Note: Targeted source-root hold test still passes; operator-control closed-notice test fails in this environment with no branch created on first sync._

### 2026-08-23 — codex
_Session: cognitive-events-self-questions-20260823_

**Modules touched:** `services/observation_spine.py`, `tests/test_observation_spine.py`

**Changes:**
- Added evidence-linked cognitive event projection
- Added conservative self-question generation from observed meta findings
- Added focused tests

**Meta:** 17 tests added

_Note: Extended the existing observation spine without introducing hidden-model claims or a parallel planner._

### 2026-08-23 — codex
_Session: grounded-self-model-20260823_

**Modules touched:** `services/observation_spine.py`, `tests/test_observation_spine.py`

**Changes:**
- Added evidence-backed dynamic self-model projection
- Normalized operator payload fields
- Added self-model regression coverage

**Meta:** 31 tests added

_Note: Observation spine now exposes cognitive events, self-questions, and operational self-model from persisted boundary evidence; no hidden-model claims._

### 2026-08-23 — codex
_Session: meta-feedback-selection-20260823_

**Modules touched:** `work_tree.py`, `tests/test_work_tree.py`

**Changes:**
- Exposed observation self-model and self-questions on autonomous decision options
- Added regression coverage for transparent meta feedback

**Meta:** 35 tests added

_Note: Meta context is now available to selection without adding a competing ranking policy; trail eligibility remains authoritative._

### 2026-08-23 — codex
_Session: internal-positions-20260823_

**Modules touched:** `services/observation_spine.py`, `tests/test_observation_spine.py`

**Changes:**
- Added evidence-backed internal positions for competing action offers
- Added tests preserving competing candidate evidence

**Meta:** 32 tests added

_Note: Continued grounded meta architecture; positions remain provisional and trace to observation sequence IDs._

### 2026-08-23 — codex
_Session: internal-position-updates-20260823_

**Modules touched:** `services/observation_spine.py`, `tests/test_observation_spine.py`

**Changes:**
- Added evidence-driven internal position confidence updates
- Preserved supporting and opposing observation references
- Added progression regression coverage

**Meta:** 21 tests added

_Note: Competing positions now strengthen or weaken from later selection and invocation evidence; full spine suite passed on rerun._

### 2026-08-23 — codex
_Session: control-panel-meta-wiring-20260823_

**Modules touched:** `services/control_status.py`, `services/control_status_surfaces.py`, `static/control.js`, `templates/control.html`

**Changes:**
- Preserved rich meta fields through status projection
- Rendered self-questions internal positions and grounded self-model in Meta panel

**Meta:** 33 tests added

_Note: Live panel confirmed old backend process is still serving stale meta payload; restart nova_http is required for browser verification._

### 2026-08-23 — codex
_Session: control-panel-live-verify-20260823_

**Modules touched:** `services/control_status.py`, `services/control_status_surfaces.py`, `static/control.js`, `templates/control.html`, `services/observation_spine.py`

**Changes:**
- Verified restarted control panel exposes meta payload
- Rendered self-model self-questions and internal positions
- Fixed duplicate polling positions in source

**Meta:** 53 tests added

_Note: Live browser confirmed meta finding and new panels; duplicate position view requires one restart after latest deduplication edit._

### 2026-08-22 — grok
_Session: hold-rail-housekeeping-class_

**Modules touched:** `services/nova_mission.py`, `autonomy_maintenance.py`, `tests/test_nova_mission_service.py`

**Changes:**
- Hold rail now distinguishes housekeeping work class from climb findings
- Candidate context carries work_class and source_type so hold does not depend on title keywords

**Meta:** 2 tests added

_Note: The rail was one freeze on all work-tree steps. That blocked vitals to stop expansion._

### 2026-08-22 — grok
_Session: mission-hold-precise-continue_

**Modules touched:** `services/nova_mission.py`, `services/work_tree_signal_ingestion.py`, `tests/test_nova_mission_service.py`, `tests/test_autonomy_orchestrator_service.py`, `tests/test_autonomy_maintenance.py`, `tests/test_work_tree_signal_ingestion_service.py`

**Changes:**
- Mission hold continues existing work-tree cards instead of freezing the lane
- Quiet hold still updates unfinished ambient maps and does not open new fronts
- Generated-queue codegen Leah and unsafe core-thinning stay gated

**Meta:** 1 tests added

_Note: Hold is the expansion verdict, not a freeze of unfinished work. Overlay was hiding maps and caging continue. Operator confirmed the distinction._

### 2026-08-22 — grok
_Session: mission-unfinished-in-equation_

**Modules touched:** `services/nova_mission.py`, `autonomy_maintenance.py`, `tests/test_nova_mission_service.py`, `tests/test_autonomy_orchestrator_service.py`, `tests/test_autonomy_maintenance.py`

**Changes:**
- Reverted the hold execute bypass that let unrelated work-tree steps run
- Unfinished working pending and executable Work Tree counts now enter mission actionable pressure
- Quiet hold still refreshes existing unfinished maps without opening new ambient fronts

**Meta:** 2 tests added

_Note: Safe overlay was stopping evolution. Mission verdict now names unfinished continue as pressure so investigate is the gate. Hold still cages expansion actions. Live pipeline-on-release-drift was the proof the bypass was wrong._

### 2026-08-22 — grok
_Session: step3-reexamine-open-resolution_

**Modules touched:** `work_tree.py`, `tests/test_work_tree.py`, `tests/authoritative/test_work_tree_behavior.py`

**Changes:**
- Branches with finished stems stay unfinished when resolution is not resolved or retired
- A re-examine task is added as the honest failure report

**Meta:** 2 tests added

_Note: Step 3 only. Empty roots with no finished work still complete. Did not run Step 4 hold-rail suite or Step 5 live cycle._

### 2026-08-22 — grok
_Session: task-attempted-not-complete_

**Modules touched:** `work_tree.py`, `work_tree_contracts.py`, `tests/test_work_tree.py`

**Changes:**
- Tool execution no longer marks a task complete unless branch resolution is resolved or retired
- Attempted tasks keep the tool result on the task so re-examine is not working from a success lie

**Meta:** 1 tests added

_Note: Did not run Step 4. Empty roots with no finished work still complete the old way._

### 2026-08-22 — grok
_Session: attempted-stays-the-work_

**Modules touched:** `work_tree.py`, `tests/test_work_tree.py`

**Changes:**
- Attempted is no longer a closed stem
- Re-examine is not minted while the miss is still the current work

_Note: False state was treating attempted like complete so a new success task could run._

### 2026-08-22 — grok
_Session: follow-solution-trail-after-miss_

**Modules touched:** `work_tree.py`, `services/solution_trail.py`, `services/work_tree_signal_ingestion.py`, `tests/test_work_tree.py`, `tests/authoritative/test_work_tree_behavior.py`

**Changes:**
- After execute with open resolution
- follow solution_trail next marker on the same branch
- Stopped minting re-examine tasks
- Attempted stays history and is not a closed stem

_Note: One wire. No fake task. Trail journal is the next move._

### 2026-08-22 — grok
_Session: phase1-observation-spine_

**Modules touched:** `services/observation_spine.py`, `services/solution_trail.py`, `services/autonomy_execution_gate.py`, `services/nova_mission.py`, `services/autonomy_orchestrator.py`, `work_tree.py`, `tests/test_observation_spine.py`

**Changes:**
- Phase 1 observation spine on existing gates
- Repeated unchanged path makes trail ineligible
- Pickup honors trail without a second store

**Meta:** 6 tests added

_Note: Bounded observer over real boundaries. Control effect lands on solution trail. Not Mirror._

### 2026-08-22 — grok
_Session: pickup-gap-unknown-branch_

**Modules touched:** `work_tree.py`, `autonomy_maintenance.py`, `tests/test_observation_spine.py`, `tests/test_autonomy_maintenance.py`

**Changes:**
- Preview next_step matches pickup options
- Target decider no longer invents a branch pickup cannot admit
- Leftover minted re-examine dropped so it cannot stay the mill stem

**Meta:** 3 tests added

_Note: Followed unknown_branch forever loop. Visual advertised a trail-suppressed mill. Pickup refused it. Decider returned the dead pin._

### 2026-08-22 — grok
_Session: pickup-is-executability_

**Modules touched:** `autonomy_maintenance.py`, `tests/test_autonomy_maintenance.py`

**Changes:**
- Planner executable bit is live pickup membership
- After thinning sync a pin not in pickup yields to live options

**Meta:** 1 tests added

_Note: Deeper than preview/decider: orchestrator was selecting from tool-safe+not-failed while pickup used list_autonomous_options._

### 2026-08-22 — grok
_Session: finding-outlives-order_

**Modules touched:** `services/core_thinning.py`, `tests/test_core_thinning_service.py`

**Changes:**
- Retire thinning findings when the scan no longer reports their order
- Ghost stems drop with the finding

**Meta:** 1 tests added

_Note: Root: feed dropped the work order and left the finding alive. Pickup, pins, re-examine, and unknown_branch were downstream of that._

### 2026-08-21 — grok
_Session: leftover-cleanup-paused-workers_

**Modules touched:** `services/pipeline_worker_supervision.py`, `services/data_pipeline_registry.py`, `autonomy_maintenance.py`, `services/backpack_host/sanitize.py`

**Changes:**
- Paused and leftover pipeline workers are stopped instead of respawned
- Uninstall stops workers before deleting their runtime dir
- Cleared live edfi_bisd workers, reports residue, and 1.4GB release extracts

**Meta:** 4 tests added

_Note: Storage watch danger was leftover validation extracts. Lane pause is now worker-lifecycle truth. Did not touch Leah, HTTP extract, or release rebuild._

### 2026-08-21 — grok
_Session: kidney-owns-storage-watch-extracts_

**Modules touched:** `kidney.py`, `policy.json`, `services/storage_watch.py`, `tests/test_kidney.py`

**Changes:**
- Kidney ages and size-caps release validation extracts and stage trees
- Storage watch extract byte totals restored so danger is real
- Release zips and ledger stay identity not bloat

**Meta:** 5 tests added

_Note: Housework on existing kidney rail. Did not touch Leah or HTTP extract. Live proof: kidney deleted _kidney_proof extract._

### 2026-08-21 — grok
_Session: kidney-runs-and-backpack-residue_

**Modules touched:** `kidney.py`, `policy.json`, `services/backpack_host/sanitize.py`, `autonomy_maintenance.py`, `tests/test_kidney.py`, `tests/test_autonomy_maintenance.py`, `tests/test_backpack_sanitize.py`

**Changes:**
- Kidney ages and count-caps subconscious run dirs and recovery quarantine
- Maintenance sanitizes uninstalled backpack residue each cycle
- Residue scan defaults to backpack package paths so reports views is visible

**Meta:** 6 tests added

_Note: Live: sanitizer removed runtime/edfi and views. Kidney deleted 400 oldest subconscious runs plus May decontam. latest.json kept. Remaining runs feed the next cycles._

### 2026-08-21 — grok
_Session: storage-watch-tree-close_

**Modules touched:** `autonomy_maintenance.py`, `tests/test_work_tree_signal_ingestion_service.py`, `tests/test_autonomy_maintenance.py`

**Changes:**
- Signal ingest now stamps live storage_watch fields before sync so an ok snapshot can resolve the branch
- HTTP surfaces omit those keys so the 0 percent storage-watch task never got resolve
- Ran system_check on the live tree then resolved the branch

**Meta:** 2 tests added

_Note: Operator correction: disk ok is not tree close. Live: task_565aad01 complete with system_check evidence_e5c9e1872a; branch_6d18cdb7 complete resolved._

### 2026-08-21 — grok
_Session: hold-allow-system-check-housekeeping_

**Modules touched:** `services/nova_mission.py`, `services/tool_identity.py`, `tests/test_nova_mission_service.py`

**Changes:**
- Mission hold no longer deadlocks storage-watch system_check
- Housekeeping tools are allowed through release-drift hold only on storage/archive context
- Random system_check on other trees stays held

**Meta:** 1 tests added

_Note: Second root of the 0 percent card: hold_allow_active_work_tools omitted system_check while ingest was blind. Do not leave Nova work at the human substitute._

### 2026-08-21 — grok
_Session: run-next-step-noop-pin_

**Modules touched:** `autonomy_maintenance.py`, `static/control.js`, `tests/test_autonomy_maintenance.py`

**Changes:**
- Run Next Step no longer drops a selected branch when inspector preferred_tool disagrees with expected_tool
- Cycle reloads work-tree from sqlite before execute so HTTP and maintenance share one truth
- UI treats executed=0 as an error instead of Step finished

**Meta:** 1 tests added

_Note: Operator clicked Run Next Step many times with no movement. Click path could return ok with executed=0._

### 2026-08-16 — grok
_Session: http-thinning-hold-root_

**Modules touched:** `services/core_thinning.py`, `services/recurring_finding_lifecycle.py`, `services/work_tree_signal_ingestion.py`, `services/operator_outbox.py`, `work_tree.py`

**Changes:**
- HTTP thinning identity is kind|file|theme so closed mapping is not recreated on cluster/line drift
- Unimplemented extract and operator do-not-retry close the extract stage instead of reopening into outbox
- Outbox resolve stamps extract closure and clears the wait-for-operator hold when no actionable notices remain
- Ingest verifies claimed open notice ids against the live outbox so a stale snapshot cannot recreate the hold

**Meta:** 6 tests added

_Note: Root of the thinning/outbox loop: finding identity drifted by cluster index and line counts; extract completion was treated as retryable; operator hold survived a resolved notice because ingest trusted a stale open-count snapshot._

### 2026-08-16 — grok
_Session: extract-outbox-republish-root_

**Modules touched:** `services/operator_outbox.py`, `services/core_thinning.py`

**Changes:**
- Do not republish a tool-failure notice the operator already resolved
- Stale a later duplicate of that same dedupe
- Skip unimplemented HTTP extract failures as operator-judgment pressure
- Feeder closes open extract stages as not-implemented and clears the failed tool state

**Meta:** 4 tests added

_Note: Live loop after the first fix: extract stayed open with core_thinning=failed, so every cycle republished tool_failure_judgment and recreated the wait hold. Applied feed+reconcile+hold resolve on the live tree; intake reads are now the open work._

### 2026-08-16 — grok
_Session: edfi-uninstall-residue_

**Modules touched:** `services/backpack_host/install_state.py`, `services/control_backpacks.py`, `services/edfi/profile_evidence.py`, `services/edfi/core_readiness.py`, `services/backpack_host/capability_surface.py`, `services/backpack_host/registry.py`, `services/work_tree_signal_ingestion.py`

**Changes:**
- Uninstalled Ed-Fi is a valid quiet state
- not a missing-profile defect
- Fusion/core/pipeline registry no longer treat package files as an installed backpack
- Work-tree Ed-Fi and pipeline-registry branches resolve without requiring a read of a deleted profile

**Meta:** 4 tests added

_Note: Residue after backpack uninstall: status still defaulted district-main, fusion scored missing settings as unhealthy, and profile close required read evidence of the deleted file._

### 2026-08-16 — grok
_Session: backpack-uninstall-sanitize_

**Modules touched:** `services/backpack_host/sanitize.py`, `services/control_backpacks.py`, `services/edfi/warehouse_sync.py`

**Changes:**
- Uninstall now sanitizes a declared touch-point list
- not just runtime/edfi
- Fusion cache and pipeline workers are removed with the backpack
- Scheduled warehouse sync stays quiet when the backpack is not installed

**Meta:** 3 tests added

_Note: Operator called the real gap: diagnosis chased the open tasks instead of asking what still believed the backpack was installed. Sanitizer is the install-contract root._

### 2026-08-16 — grok
_Session: any-backpack-uninstall-sanitize_

**Modules touched:** `services/backpack_host/sanitize.py`, `services/control_backpacks.py`, `services/backpack_host/query.py`

**Changes:**
- Uninstall sanitizer now discovers runtime paths from any backpack.json and settings defaults
- Reports uninstall clears runtime/views which is outside runtime/reports
- Residue scan reports leftovers Nova has not declared yet
- Queries refuse uninstalled backpacks instead of treating missing enabled.json as on

**Meta:** 5 tests added

_Note: Ed-Fi-only overlay is no longer the sanitizer. Any backpack gets runtime dir, pipeline workers, manifest paths, matching work-tree branches, and a leftover scan._

### 2026-08-16 — grok
_Session: ledger-decision-dedupe_

**Modules touched:** `scripts/generate_nova_ledger.py`, `services/nova_wiring_inventory.py`, `services/nova_root_inventory.py`, `docs/DOC_OWNERSHIP.md`, `docs/SERVICES_INDEX.md`

**Changes:**
- Elevated backpack_uninstall_touch_list to a named architectural decision
- Ledger scan findings now keep the latest line per finding identity
- Wired backpack_host and classified the leftover source files
- Regenerated SERVICES_INDEX and refreshed DOC_OWNERSHIP

**Meta:** 3 tests added · docs updated: `docs/DOC_OWNERSHIP.md`, `docs/SERVICES_INDEX.md`

_Note: Operator: decision belongs with root_cause_first_principle; scan findings were reprinting every cycle._

### 2026-08-16 — grok
_Session: winerror87-pid-probe_

**Modules touched:** `services/pipeline_worker_supervision.py`, `tests/test_autonomy_maintenance.py`, `tests/test_pipeline_worker_supervision.py`

**Changes:**
- Confirmed regression lock uses psutil.pid_exists
- Replaced the remaining os.kill(pid
- 0) probe in pipeline worker supervision
- Added tests that WinError 87 cannot come back through those paths

**Meta:** 2 tests added

_Note: Overnight cycle exit 1 was POSIX signal-0 on Windows. Named lock helper was already fixed; the same probe was still live on pipeline worker leases._

### 2026-08-15 — grok
_Session: leah-pause_

**Modules touched:** `tests/test_leah_memory_recall_at5.py`, `capabilities_roadmap.json`, `docs/LEAH_INSTANCE_PROFILE.md`

**Changes:**
- Rewrote AT-5 as honest write-path vs inject-if-hit tests
- Recorded operator pause on Leah build

**Meta:** 11 tests added · docs updated: `docs/LEAH_INSTANCE_PROFILE.md`, `capabilities_roadmap.json`

_Note: Operator paused Leah 2026-08-15. Continuity stays promoted. Memory recall not promoted. AT-5 still open on mem_recall surfacing a pinned fact. Do not start voice or emotion._

### 2026-08-05 — claude-cowork
_Session: fix_entry_points_20260805_

**Modules touched:** `docs/README.md`, `docs/DOC_OWNERSHIP.md`, `docs/NOVA_POSTAL.md`

**Changes:**
- docs/README.md now leads with NOVA_POSTAL and NOVA_LEDGER — retired July audit as primary authority
- DOC_OWNERSHIP.md rewritten — Living Ledger is now primary authority class — dated audits moved to historical section
- NOVA_POSTAL.md complete rewrite — file type as first level of order — three-phase agent protocol (arriving/working/leaving) — product finish map added

**Meta:** docs updated: `docs/README.md`, `docs/DOC_OWNERSHIP.md`, `docs/NOVA_POSTAL.md`

_Note: Phase 1 complete. Fixed the three entry point doors so agents arriving anywhere land in the correct flow. Grok gap findings 1-2-3 addressed._

### 2026-08-05 — claude-cowork
_Session: regenerate_indices_20260805_

**Modules touched:** `docs/SERVICES_INDEX.md`, `docs/SYSTEM_MAP.md`, `scripts/regenerate_services_index.py`

**Changes:**
- SERVICES_INDEX.md regenerated from 191-line manual list to 232 service files — backpack_host
- nova_shell
- decision_proposal_judge
- solution_trail
- self_scan_rings
- nova_setup_wizard all added
- SYSTEM_MAP.md updated — reading order now leads with Ledger and Postal — six missing subsections added: Decision Judge
- Nova Shell
- Backpack Host
- Solution Trail
- Self-Scan Rings
- Setup Wizard — known risks updated
- scripts/regenerate_services_index.py created — auto-generates SERVICES_INDEX from AST scan of services/ directory

**Meta:** docs added: `scripts/regenerate_services_index.py` · docs updated: `docs/SERVICES_INDEX.md`, `docs/SYSTEM_MAP.md`

_Note: Phase 3 complete. All three stale indices updated. Grok gap findings 4-6 addressed. Regenerate SERVICES_INDEX anytime with: python scripts/regenerate_services_index.py_

### 2026-08-05 — claude-cowork
_Session: aug05_hygiene_close_

**Modules touched:** `docs/FUNCTION_INDEX.md`, `docs/TEST_INDEX.md`, `scripts/nova_ledger_ingest.py`, `scripts/generate_nova_ledger.py`, `autonomy_maintenance.py`, `docs/NOVA_LEDGER.md`

**Changes:**
- Regenerated FUNCTION_INDEX (561 files 6577 fns)
- Regenerated TEST_INDEX (245 modules 2344 fns)
- Added emit_drift_alerts_from_ring_result() to nova_ledger_ingest
- Updated generate_nova_ledger to render drift_alert entries in Drift Alerts section
- Wired drift alert emission into autonomy_maintenance cycle
- Emitted 3 current drift alerts (9 unclassified files 9 stale docs 15 probe gaps)

_Note: Closes migration hygiene: FUNCTION_INDEX current, TEST_INDEX current, drift alerts live in ledger. Remaining gaps are tracked (not hidden): 9 source files unclassified, 9 stale NOVA_DOC headers, 15 probe gaps offline-mode. All gaps emit on every maintenance cycle going forward._

### 2026-08-05 — claude-cowork
_Session: aug05_doc_catchup_

**Modules touched:** `docs/SERVICES_INDEX.md`, `docs/DOC_OWNERSHIP.md`, `docs/README.md`, `docs/NOVA_POSTAL.md`, `services/nova_shell_control_bridge.py`, `services/supervisor_rules.py`, `scripts/nova_ledger_ingest.py`, `scripts/generate_nova_ledger.py`, `scripts/regenerate_function_index.py`, `docs/archive/*`

**Changes:**
- Added nova_shell_control_bridge and supervisor_rules to SERVICES_INDEX
- Embedded NOVA_DOC headers in 5 files missing them
- Archived 9 historical docs (STATUS HANDOFF CODE_TRUTH_AUDITs phase docs coaching docs)
- Updated DOC_OWNERSHIP README NOVA_POSTAL to remove stale archive references
- NOVA_DOC coverage now 35 declared 0 undeclared 0 stale

_Note: Documentation fully caught up with recent build work. Zero stale/undeclared docs. Remaining gaps are tracked in drift alerts: 10 unclassified source files (pre-existing structural debt in scripts/)._

### 2026-08-04 — claude-cowork
_Session: sock_improvements_and_judge_

**Modules touched:** `services/sock_service.py`, `services/ollama_health.py`, `static/control.js`, `tests/test_decision_proposal_judge.py`, `docs/DECISION_PROPOSAL_JUDGE.md`

**Changes:**
- SOCK: ROCm/HIP detection via rocm-smi (AMD dedicated VRAM, no shared RAM contamination)
- SOCK: NPU wiring — npu_inference field + _npu_inference() function
- SOCK: Live VRAM estimates from Ollama /api/show with per-model cache
- SOCK: Cache invalidation hook — invalidate_sock_cache() + notify_ollama_model_change()
- ollama_health.py: _notify_sock_if_changed() wired to detect inventory changes
- control.js: HARDWARE/SOCK section added to System Matrix (GPU, CPU, NPU, chat model, routing model, policy sync)
- Decision Judge: DecisionProposal + JudgeReport + DecisionEpisode schemas designed and built
- Judge: controlling_dimension drives disposition (no blended confidence)
- Judge: field_sources provenance — Actor cannot self-score intended_effect
- Judge: judge_was_useful computed automatically from prediction vs outcome
- Judge: wired to _execute_autonomy_recommendation in observe-only mode (decision_judge_enforce: false by default)
- Judge: calibration bar set — 12 episodes before signals, 30 before enforce conversation

**Meta:** 11 tests added · docs added: `DECISION_PROPOSAL_JUDGE.md`

_Note: SOCK hardware section live in control panel. Judge accumulating episodes in parallel with normal execution._

### 2026-08-04 — claude-cowork
_Session: doc_ledger_and_postal_office_20260804_

**Modules touched:** `static/control.js`, `services/sock_service.py`, `services/ollama_health.py`, `docs/NOVA_POSTAL.md`, `docs/ledger/`

**Changes:**
- HARDWARE/SOCK section in System Matrix
- Living ledger with two write paths
- Postal office routing table
- Full code truth audit
- Decision WHY mining started

**Meta:** docs added: `docs/NOVA_POSTAL.md`, `docs/NOVA_LEDGER.md`, `docs/CODE_TRUTH_AUDIT_2026-08-04.md`

_Note: Session cut short — WHY mining from nova_grok.md and session transcripts pending_

### 2026-08-04 — claude-cowork
_Session: arch_decisions_mining_20260804_

**Modules touched:** `scripts/nova_ledger_ingest.py`, `scripts/generate_nova_ledger.py`, `docs/ledger/nova_findings.jsonl`, `docs/NOVA_LEDGER.md`

**Changes:**
- Added decision entry_type to nova_ledger_ingest.py VALID_ENTRY_TYPES
- Added Architectural Decisions section to generate_nova_ledger.py with named headers rationale and affects
- Mined 12 WHY decisions from nova_grok.md June 2026 Grok session (all 44 turns)
- Ingested decisions into nova_findings.jsonl
- Regenerated NOVA_LEDGER.md with decisions as named sections

_Note: Task 34 complete. Decisions cover: services_import_boundary, three_runtime_architecture, evidence_validity_json_aware, maintenance_local_enrichment, hardware_constraint_core_solid, leah_observe_mode, subconscious_no_routing, control_status_read_only, nova_grok_file_origin, commit_is_deployment, root_cause_first_principle, operator_outbox_durable_lane_

### 2026-08-03 — claude-cowork
_Session: edfi_backpack_and_nova_shell_

**Modules touched:** `backpacks/edfi/`, `services/backpack_host/`, `nova_shell/`, `tools/`

**Changes:**
- Ed-Fi backpack structure built
- Backpack Host — discovery, install, grant enforcement, lifecycle
- Nova Shell security scaffolding, identity, store, roles, auth, admin
- Custom roles CRUD added
- Ed-Fi code scan completed

_Note: Tasks 13-25 completed_

### 2026-08-02 — claude-cowork
_Session: self_scan_rings_and_coaching_

**Modules touched:** `services/nova_root_inventory.py`, `services/nova_wiring_inventory.py`, `docs/`

**Changes:**
- Three-ring self-scan design woven into Nova
- SELF_SCAN_RINGS_DESIGN.md written
- SOLUTION_EXPERIENCE_BACKLOG.md written
- NOVA_COACHING_INCOMPLETE_HANDOFF.md written
- NOVA_COACHING_STUCK_MISSION_HOLD.md written

**Meta:** docs added: `SELF_SCAN_RINGS_DESIGN.md`, `SOLUTION_EXPERIENCE_BACKLOG.md`, `NOVA_COACHING_INCOMPLETE_HANDOFF.md`, `NOVA_COACHING_STUCK_MISSION_HOLD.md`

_Note: Rings 1-2 confirmed real code. Ring 3 on findings queue only._

### 2026-08-01 — claude-cowork
_Session: control_panel_wiring_

**Modules touched:** `nova_http.py`, `static/control.js`, `static/control.html`, `nova_calendar_ingestion.py`, `work_tree_signal_ingestion.py`

**Changes:**
- Calendar RRULE recurrence + sidecar enrichment
- Per-event signals in work_tree_signal_ingestion
- Temporal event HTTP endpoints
- Control panel temporal event controls
- Branch Inspector fix
- Missing control panel buttons restored

_Note: Tasks 1-8 completed_

### 2026-07-12 — claude-cowork
_Session: code_truth_audit_20260712_

**Modules touched:** `all`

**Changes:**
- Full code truth audit. Drift findings documented. Doc ownership structure established.

**Meta:** docs added: `CODE_TRUTH_AUDIT_2026-07-12.md`, `SYSTEM_MAP.md`, `ARCHITECTURE.md`, `SERVICES_INDEX.md`, `FUNCTION_INDEX.md`, `TEST_INDEX.md`, `TEST_ECOSYSTEM.md`, `AUTONOMY_AND_MISSION.md`, `DATA_PIPELINES.md`, `OPERATIONS.md`, `HANDOFF.md`, `SUPERVISOR_CONTRACT.md`, `KIDNEY_SYSTEM.md`, `SOCK_SYSTEM.md`, `MEMORY_SYSTEM_PLAN.md`, `LEAH_INSTANCE_PROMOTION_PLAN.md`, `PACKAGE_PRODUCT_ROADMAP.md`, `PACKAGING_MATRIX.md`, `PATCHING.md`, `PHASE2_SAFETY_ENVELOPE.md`, `PHASE_CLOSEOUT_CHECKLIST.md`, `PHASE_COMPLETION_ASSESSMENT.md`, `WINDOWS_INSTALLER_PLAN.md`, `BASE_PACKAGE_READINESS.md`, `DOC_OWNERSHIP.md`, `STATUS.md`, `NOVA_HEALTH_REVIEW.md` · docs updated: `README.md`

_Note: Anchor commit: 92ca149e452e96dfd0d9224eb2d11a0862c3ccea_

### 2026-06-27 — cursor-grok
_Session: nova_grok_session_

**Modules touched:** `nova_core.py`, `nova_guard.py`, `nova_http.py`, `work_tree.py`

**Changes:**
- ~9h session. Runtime governance, work tree, guard stability. See nova_grok.md turns 1-44.

**Meta:** docs added: `nova_grok.md`, `nova_grok.jsonl`

_Note: Full machine record in nova_grok.jsonl (~6.3MB, 1494 events)_

### 2026-05-27 — claude-cowork
_Session: NOVA_CODE_SCAN_2026-05-27_

**Modules touched:** `all`

**Changes:**
- Full code scan — 281 Python source files, 3431 functions, 181 classes indexed

**Meta:** docs added: `NOVA_CODE_SCAN_2026-05-27.md`

_Note: Baseline scan. Superseded by CODE_TRUTH_AUDIT_2026-07-12.md_

---

## Documentation Registry

Every known doc file classified by authority and last verification date.

### ✅ Active Authority

| File | Last Verified | Verified By | Notes |
|------|--------------|-------------|-------|
| `AGENTS.md` | 2026-08-04 | developer | Operator-enforced agent rules. Root level — must stay at root. |
| `README.md` | 2026-08-03 | developer | Project README. Root level — must stay at root. |
| `docs/ARCHITECTURE.md` | 2026-07-12 | developer | Design intent and current implementation boundaries. Anchored to commit 92ca149. |
| `docs/AUTONOMY_AND_MISSION.md` | 2026-07-12 | developer | Maintenance, Mission, orchestrator, execution, and feedback contracts. |
| `docs/BOOTSTRAP.md` | 2026-05-20 | developer | Bootstrap procedure. |
| `docs/DATA_PIPELINES.md` | 2026-07-12 | developer | Data pipeline architecture. |
| `docs/DECISION_PROPOSAL_JUDGE.md` | 2026-08-04 | developer | Decision Judge architecture — DecisionProposal, JudgeReport, DecisionEpisode schemas. Current. |
| `docs/DEPENDENCY_CONTRACT.md` | 2026-05-20 | developer | Dependency contract. |
| `docs/DOC_OWNERSHIP.md` | 2026-07-12 | developer | Authority structure for all docs. Needs update — new docs since July 12 not registered. |
| `docs/DOC_OWNERSHIP.md` | 2026-08-16 | grok | Updated 2026-08-16: backpack uninstall contract and sanitizer registered. Ledger is authority for the named decision backpack_uninstall_touch_list. |
| `docs/FRESH_MACHINE_VALIDATION.md` | 2026-05-20 | developer | Fresh machine validation protocol. |
| `docs/KIDNEY_SYSTEM.md` | 2026-07-12 | developer | Kidney thinning and memory hygiene system. |
| `docs/NOVA_COACHING_INCOMPLETE_HANDOFF.md` | 2026-08-02 | developer | Nova coaching doc — incomplete handoff behavior. Verified against character test. |
| `docs/NOVA_COACHING_STUCK_MISSION_HOLD.md` | 2026-08-02 | developer | Nova coaching doc — stuck mission hold behavior. |
| `docs/NOVA_POSTAL.md` | — | nova | The postal office — routing table for all Nova documentation. Read before any doc work. |
| `docs/OPERATIONS.md` | 2026-07-12 | developer | Operational procedures. |
| `docs/PACKAGING_MATRIX.md` | 2026-05-18 | developer | Packaging matrix. Verify against current release artifacts. |
| `docs/PATCHING.md` | 2026-07-12 | developer | Patching protocol. |
| `docs/PRIVILEGED_PIPELINE_PROTOCOL.md` | 2026-05-18 | developer | Privileged pipeline protocol. |
| `docs/RC_VALIDATION_TEMPLATE.md` | 2026-05-18 | developer | RC validation template. |
| `docs/RELEASE_ARTIFACT.md` | 2026-06-14 | developer | Release artifact specification. |
| `docs/SEARCH_PROVIDER_ARCHITECTURE.md` | 2026-06-11 | developer | Search provider (SearXNG) architecture. |
| `docs/SELF_SCAN_RINGS_DESIGN.md` | 2026-08-02 | developer | Three-ring self-scan design. Rings 1-2 confirmed real code. Ring 3 on findings queue only. |
| `docs/SERVICES_INDEX.md` | 2026-07-12 | developer | Every service module and its public surface. Drift possible — sock_service, ollama_health, backpack_host changed 2026-08-04. |
| `docs/SUPERVISOR_CONTRACT.md` | 2026-07-12 | developer | Supervisor behavioral contract. |
| `docs/SYSTEM_MAP.md` | 2026-07-12 | developer | Current processes, ownership, APIs, artifacts, wiring surfaces. Anchored to commit 92ca149. |
| `docs/TEST_ECOSYSTEM.md` | 2026-07-12 | developer | Test lanes and strategy. |

### 🔵 Active Working

| File | Last Verified | Verified By | Notes |
|------|--------------|-------------|-------|
| `docs/AUTONOMY_AND_MISSION.md` | 2026-09-01 | nova | Mill signal handoff; overnight mill-skip vs spine-on-pulse still open |
| `docs/BASE_PACKAGE_READINESS.md` | 2026-07-12 | developer | Base package readiness checklist. |
| `docs/FUNCTION_INDEX.md` | 2026-08-05 | nova | Regenerated 2026-08-05 via inline scan. 561 files, 6577 functions, 527 classes. Excludes .venv, .git, runtime. Shallow scan. |
| `docs/HANDOFF.md` | 2026-07-12 | developer | Handoff protocol between sessions. |
| `docs/LEAH_INSTANCE_PROMOTION_PLAN.md` | 2026-07-12 | developer | Leah promotion plan. Development paused. |
| `docs/MEMORY_SYSTEM_PLAN.md` | 2026-07-12 | developer | Memory system plan. Verify against current memory.py implementation. |
| `docs/NOVA_SERVER_SIDE.md` | 2026-06-26 | developer | Server-side architecture notes. |
| `docs/PACKAGE_PRODUCT_ROADMAP.md` | 2026-07-12 | developer | Product roadmap. |
| `docs/REAL_WORLD_TASKS.md` | 2026-04-28 | developer | Real world task examples. Oldest active doc — verify still relevant. |
| `docs/SERVICES_INDEX.md` | 2026-08-16 | grok | Regenerated 2026-08-16. Includes backpack_host/sanitize.py and install_state.py. |
| `docs/SOCK_SYSTEM.md` | 2026-08-05 | nova | Updated 2026-08-05. Hardware Detection section added covering ROCm/HIP, NPU, live VRAM, cache invalidation. |
| `docs/SOCK_SYSTEM.md` | 2026-09-01 | nova | Mill capacity lease and this-box standing 4B / sip 9B |
| `docs/SOLUTION_EXPERIENCE_BACKLOG.md` | 2026-08-02 | developer | Backlog for solution experience improvements. Active. |
| `docs/TEST_INDEX.md` | 2026-08-05 | nova | Regenerated 2026-08-05. 245 test modules, 2344 test functions. Up from 215 modules / 2016 fns (July 12 vintage). |
| `docs/WINDOWS_INSTALLER_PLAN.md` | 2026-07-12 | developer | Windows installer plan. |

### ⚠️  Stale Snapshot

| File | Last Verified | Verified By | Notes |
|------|--------------|-------------|-------|
| `docs/FUNCTION_INDEX.md` | 2026-07-12 | developer | 3431 functions indexed 2026-07-12. Significant drift since — Judge, SOCK improvements, backpack host, nova_shell all added. Regeneration needed. |
| `docs/SOCK_SYSTEM.md` | 2026-07-12 | developer | SOCK system doc. Drift — ROCm, NPU, live VRAM, cache invalidation all added 2026-08-04. Needs refresh. |
| `docs/TEST_INDEX.md` | 2026-07-12 | developer | Test function index as of July 12. 11 new tests added 2026-08-04 (Judge). Regeneration needed. |

### 📦 Historical / Archive

| File | Last Verified | Verified By | Notes |
|------|--------------|-------------|-------|
| `NOVA_CODE_SCAN_2026-05-27.md` | 2026-05-27 | developer | Superseded by CODE_TRUTH_AUDIT_2026-07-12.md. Archive candidate — move to docs/archive/. |
| `NOVA_HEALTH_REVIEW.md` | 2026-07-12 | developer | Health review snapshot July 12. Archive candidate — move to docs/archive/. |
| `This_is_nova` | — | nova | Nova's founding action ledger — May 13-16 2026, 821 entries, first chat sessions, first tool calls, first grounded responses. Stays at root. Named with intent. |
| `codex_audit.txt` | 2026-07-12 | developer | Codex audit transcript. Archive candidate — move to docs/archive/. |
| `docs/CODE_TRUTH_AUDIT_2026-07-12.md` | 2026-07-12 | developer | Scan baseline and drift findings as of July 12. Historical record, not current truth. |
| `docs/MILL_LANE_MEASURE_2026-09-01.md` | 2026-09-01 | nova | Ollama mill-judgment scores 2026-09-01; evidence only |
| `docs/PHASE2_SAFETY_ENVELOPE.md` | 2026-07-12 | developer | Phase 2 safety envelope. Phase complete — archive candidate. |
| `docs/PHASE_CLOSEOUT_CHECKLIST.md` | 2026-07-12 | developer | Phase closeout checklist. Phase complete — archive candidate. |
| `docs/PHASE_COMPLETION_ASSESSMENT.md` | 2026-07-12 | developer | Phase completion assessment. Historical — archive candidate. |
| `nova_grok.md` | 2026-06-27 | developer | Grok/Cursor session handoff transcript. Archive candidate — move to docs/archive/. |

---

## Architectural Decisions

WHY decisions mined from sessions, transcripts, and code audits.
These are the reasons behind Nova's structural choices.

### `services_import_boundary` — 2026-06-27
_Modules: services/ (all)_

services/ never imports nova_core. Work tree executes tools via injected callback (execute_planned_action_fn passed by caller). This keeps the graph store independent from the runtime brain.

**Rationale:** Circular imports would make the graph store untestable in isolation and couple the data layer to the runtime brain.

**Affects:** `work_tree.py`, `services/`, `nova_core.py`
**Source:** `nova_grok.md` · Status: active

### `three_runtime_architecture` — 2026-06-27
_Modules: nova_guard.py / nova_core.py / nova_http.py / autonomy_maintenance.py_

Three parallel runtimes: guard spawns and heartbeats core; HTTP serves UI and chat; maintenance is a separate worker triggered by guard every ~300s. Four processes total, each with a distinct role and failure domain.

**Rationale:** Monolithic process would mean a core crash takes down the UI, maintenance, and guard simultaneously. Separate processes allow partial recovery and independent restart.

**Affects:** `nova_guard.py`, `nova_core.py`, `nova_http.py`, `autonomy_maintenance.py`
**Source:** `nova_grok.md` · Status: active

### `evidence_validity_json_aware` — 2026-06-27
_Modules: services/evidence_validity.py / services/source_root_judgment.py / services/work_tree_signal_ingestion.py_

Evidence validity redesigned June 2026. Original _looks_like_failed_evidence() used naive 'ok': false substring matching. This false-positived on source code reads — ollama_health.py contains 'ok': False in Python source. Fix: JSON-aware parsing with length check (<=4000 chars, looks like a tool result, not source). Both call sites (judgment + ingestion) now route through evidence_validity.evidence_result_valid().

**Rationale:** Source code reads legitimately contain 'ok': False as Python syntax. A naive string search cannot distinguish a tool result from a file read. Structured JSON parsing with a length guard solves this without false positives.

**Affects:** `services/evidence_validity.py`, `services/source_root_judgment.py`, `services/work_tree_signal_ingestion.py`
**Source:** `nova_grok.md` · Status: active

### `maintenance_local_enrichment` — 2026-06-27
_Modules: autonomy_maintenance.py_

Maintenance local fallback was missing status surfaces. When HTTP is unavailable, the fallback payload did not populate last_intent, root_closure_inventory, source_root_inventory, and other surfaces that control_status.py builds. Fix: enrichment helpers (_apply_local_model_runtime_status, _apply_local_source_root_status_surfaces, _refresh_root_closure_inventory_surfaces) run after every HTTP merge, filling only missing keys.

**Rationale:** Two code paths (HTTP and fallback) must produce equivalent surfaces for signal ingestion to work correctly. Maintenance enrichment is cheaper and more resilient than requiring HTTP for every cycle.

**Affects:** `autonomy_maintenance.py`, `services/work_tree_signal_ingestion.py`
**Source:** `nova_grok.md` · Status: active

### `hardware_constraint_core_solid` — 2026-06-27
_Modules: all_

As of June 2026, Nova's codebase (~150 services, 320KB status payloads, 300s maintenance cycles) has outgrown available hardware. IA models are fine. Strategic decision: core solid, not expansion. Three-pillar response: (1) Reduce scheduled-tree churn by deduping closure tracks, (2) Make observation cheap via local-first status path targeting <2s local/<5s with HTTP, (3) Shorten release/restart loop to prevent drift. All expansion deferred until 48h core stability.

**Rationale:** Expansion on constrained hardware multiplies governance load. Each new wiring surface and duplicate closure track adds maintenance cost. Core integrity must come before capability addition.

**Affects:** `all`
**Source:** `nova_grok.md` · Status: active

### `leah_observe_mode` — 2026-06-27
_Modules: services/leah_frontdoor.py / capabilities_roadmap.json_

LEAH capabilities (voice persona engine, memory recall, emotional state model, conversation continuity) are gated behind core stability. Policy: Tier B (LEAH) observe-only until Tier A (runtime core) is green for 48h+. Gap signals are logged but no new codegen branches spawned. LEAH shell and frontdoor (/leah) exist and stay — only the four leah_* phase_2 capabilities are held.

**Rationale:** LEAH depends on solid http_continuity, memory_routing, voice root closure. Building capabilities on an unstable core creates compounding failures. Observe mode prevents governance from treating unbuilt persona engine as an active gap requiring codegen on every cycle.

**Affects:** `services/leah_frontdoor.py`, `capabilities_roadmap.json`, `autonomy_maintenance.py`
**Source:** `nova_grok.md` · Status: active

### `subconscious_no_routing` — 2026-06-27
_Modules: services/subconscious_config.py / services/subconscious_live_simulator.py_

Subconscious is deliberately forbidden from routing or controlling execution. subconscious_config.py explicitly lists forbidden_actions: own_turns, route_turns, force_behavior, override_supervisor, override_fulfillment, create_controller_logic, turn_diagnostics_into_commands. It detects pressure signals and emits triage hints to the orchestrator — nothing more.

**Rationale:** If the observer can route, it can route incorrectly based on its own incomplete view. Routing authority belongs to the orchestrator which has the full input envelope. Subconscious provides pressure signals only.

**Affects:** `services/subconscious_config.py`, `services/subconscious_live_simulator.py`, `autonomy_maintenance.py`
**Source:** `nova_grok.md` · Status: active

### `control_status_read_only` — 2026-06-27
_Modules: services/control_status.py_

control_status.py (~1,214 lines) assembles the full runtime snapshot — it only observes. Nothing routes there. The observation feeds signal ingestion which feeds the work tree. Routing and execution happen downstream. Polled at /api/control/status; UI polls it freely.

**Rationale:** Side effects in the observation layer would mean that inspecting the system changes the system. This makes diagnosis unreliable. Observation must be pure.

**Affects:** `services/control_status.py`, `nova_http.py`
**Source:** `nova_grok.md` · Status: active

### `commit_is_deployment` — 2026-06-27
_Modules: all_

Two blast radii for any code change: (1) local disk changes affect the running Nova instance immediately on the next maintenance cycle (~300s), not just on commit; (2) a pushed commit makes changes available to the hourly-sync Nova on its next pull. Rule: no casual commit. Treat local edits as live-runtime changes until validated. Only commit when both instances should absorb the same state.

**Rationale:** A second Nova instance pulls from GitHub hourly. Careless pushes deploy half-finished work to a live instance that will ingest signals, open work-tree branches, and run maintenance against the new code immediately.

**Affects:** `all`
**Source:** `nova_grok.md` · Status: active

### `root_cause_first_principle` — 2026-06-27
_Modules: all_

Working rule for all Nova development sessions: fix roots only. Before any fix, answer three questions: (1) Why does this problem exist? (2) How did it come to be? (3) What will fixing it affect? Band-aid fixes in one layer move pressure to another, or clear branches while leaving the underlying gap intact so it reopens next cycle.

**Rationale:** Nova's governance loop self-corrects. A band-aid that silences an outbox notice will be reopened by the next maintenance cycle if the underlying wiring is genuinely incomplete. Only root fixes produce durable closure.

**Affects:** `all`
**Source:** `nova_grok.md` · Status: active

### `operator_outbox_durable_lane` — 2026-06-27
_Modules: services/operator_outbox.py_

operator_outbox.py is a durable notice lane, not a conversational router. It records internal runtime pressure as notices (new -> seen -> answered -> resolved/dismissed/stale) so the UI can surface them without waiting for a user chat turn. Sources: autonomy orchestrator blocks, OS capability gaps, work tree operator holds, subconscious triage escalations.

**Rationale:** Chat turns are ephemeral and require a human present. Governance pressure is persistent and must survive session close. A durable notice lane decouples Nova's observations from user availability.

**Affects:** `services/operator_outbox.py`, `nova_http.py`, `static/control.js`
**Source:** `nova_grok.md` · Status: active

### `nova_grok_file_origin` — 2026-06-28
_Modules: nova_grok.md (root)_

nova_grok.md was created at the end of the June 27-28 2026 Grok session (Turn 41-44). Gus asked to save the full chat verbatim. Grok parsed the JSONL session transcript and wrote the full conversation to nova_grok.md. Named with intent — it is a session artifact, not documentation. Stays at root.

**Rationale:** Gus needed session continuity across a close. The file preserves nine hours of architectural discovery that would otherwise be lost on session close.

**Affects:** `nova_grok.md`
**Source:** `nova_grok.md Turn 41-44` · Status: active

### `backpack_uninstall_touch_list` — 2026-08-16
_Modules: services/backpack_host/sanitize.py_

If a backpack can write into a Nova surface, that surface has to be on the uninstall list. Uninstall is not delete runtime/{id}. Discover runtime paths from the backpack manifest and settings defaults, overlay the Nova surfaces the package cannot declare (work-tree sources, fusion cache, maintenance keys), resolve matching work-tree pressure, and report undeclared leftovers instead of pretending the rest of Nova is clean.

**Rationale:** Nova self-corrects. An uninstall that only deletes the backpack folder leaves status, fusion, pipeline workers, warehouse sync, and work-tree signals treating the backpack as a broken install. Those surfaces keep opening the same tasks. The install contract must name every write target or the residue scan must admit the gap.

**Affects:** `services/backpack_host/sanitize.py`, `services/backpack_host/install_state.py`, `services/control_backpacks.py`, `services/edfi/warehouse_sync.py`, `services/work_tree_signal_ingestion.py`
**Source:** `operator session 2026-08-16` · Status: active

### `unnamed` — 2026-09-01
_Modules: sock_service_

Mill does not name a model. SOCK leases temporary capacity from mill_judgment_signal. Standing qwen3.5:4b; sip qwen3.5:9b on refused and redundant+empty_claim; 14B has no mill class. Generation beat size on Nova mill set.


### `mill_skip_remint_stop_pulse_promoted` — 2026-09-01
_Modules: autonomy_maintenance.py / services/observation_spine.py / services/solution_trail.py / services/autonomy_orchestrator.py / services/work_tree_signal_ingestion.py_

Promote skip/remint/stop/pulse mill-cycle control only. Three trailing mill skips run mill once; mill-ok clears the force; pulse may return; paid trail blocks compact-lane remint. Do not promote mill sip-execute of standing 4B / sip 9B on source_root_judgment.

**Rationale:** Live trail on 2026-09-01 matched the test trail for skip, remint, stop, and pulse (commit 23fa484). source_root_judgment was not reached because the paid trail left no OPEN stem, so sip-execute is wired but not live-promoted.

**Affects:** `autonomy_maintenance.py`, `services/observation_spine.py`, `services/solution_trail.py`, `services/autonomy_orchestrator.py`, `services/work_tree_signal_ingestion.py`, `work_tree.py`
**Source:** `docs/AUTONOMY_AND_MISSION.md` · Status: active

---

## Nova Scan Findings

Latest ring and execution findings. Identical cycle reprints are collapsed to one line.

- **2026-09-12** Ring 3 `climb_integrity` — verified: gap_count=0, queue=1 climbable=1 unclimbable=0
- **2026-09-12** Ring 2 `contract_integrity` — drifted: gap_count=61, probe_context=live_status, wiring_gaps=33, closure_gaps=28
- **2026-09-12** Ring 1 `map_integrity` — drifted: gap_count=2, unclassified_files=1, undeclared_docs=1
- **2026-09-12** Ring 1 `map_integrity` — drifted: gap_count=1, undeclared_docs=1
- **2026-09-12** Ring 2 `contract_integrity` — verified: gap_count=0, probe_context=live_status
- **2026-09-09** Ring 1 `map_integrity` — drifted: gap_count=2, unclassified_files=2
- **2026-09-09** Ring 2 `contract_integrity` — drifted: gap_count=1, probe_context=live_status, closure_gaps=1
- **2026-09-08** Ring 1 `map_integrity` — verified: gap_count=0
- **2026-09-01** `autonomy_maintenance` — caution: Overnight 2026-08-31 23:45 to 2026-09-01 06:41: 74 cycles ok, mill executed=0 trees=0, no capacity lease. Spine REPEATED_UNCHANGED_PATH on pulse_status not mill skip.
- **2026-08-22** Ring 2 `contract_integrity` — drifted: gap_count=76, probe_context=live_status, wiring_gaps=40, closure_gaps=35, probe_gaps=1
- **2026-08-22** Ring 2 `contract_integrity` — drifted: gap_count=2, probe_context=live_status, closure_gaps=1, probe_gaps=1
- **2026-08-16** Ring 1 `map_integrity` — verified: gap_count=0, unwired_roots=0, unclassified_files=0
- **2026-08-16** Ring 1 `nova_root_inventory` — verified: 0 source root(s) not wired in nova_root_inventory.py
- **2026-08-16** Ring 1 `nova_root_inventory` — verified: 0 source file(s) have no SOURCE_ROOT classification
- **2026-08-05** Ring 1 `map_integrity` — drifted: gap_count=9, unclassified_files=9, stale_docs=9
- **2026-08-05** Ring 2 `contract_integrity` — drifted: gap_count=15, probe_context=offline, probe_gaps=15

---

## Drift Alerts

### Ring scan gaps (latest per category)

- **2026-08-05** Ring 1 `nova_doc_coverage` — 9 doc(s) have stale NOVA_DOC block (last_session > 30 days)
- **2026-09-12** Ring 1 `nova_root_inventory` — 1 source file(s) have no SOURCE_ROOT classification
- **2026-09-12** Ring 1 `nova_doc_coverage` — 1 doc(s) in docs/ missing NOVA_DOC header block
- **2026-09-12** Ring 2 `ring2_contract_integrity` — 28 closure gap(s): work-tree tracks open but no resolution evidence
- **2026-08-22** Ring 2 `ring2_contract_integrity` — 1 contract probe gap(s) (live_status): services lack HTTP-reachable health probe
- **2026-09-12** Ring 2 `ring2_contract_integrity` — 33 wiring gap(s): service/script registered but not surfaced in status

### Stale authority documents

- `docs/FUNCTION_INDEX.md` — last verified 2026-07-12: 3431 functions indexed 2026-07-12. Significant drift since — Judge, SOCK improvements, backpack host, nova_shell all added. Regeneration needed.
- `docs/SOCK_SYSTEM.md` — last verified 2026-07-12: SOCK system doc. Drift — ROCm, NPU, live VRAM, cache invalidation all added 2026-08-04. Needs refresh.
- `docs/TEST_INDEX.md` — last verified 2026-07-12: Test function index as of July 12. 11 new tests added 2026-08-04 (Judge). Regeneration needed.

---

_End of ledger. Append entries to the source JSONL files and regenerate to update._
