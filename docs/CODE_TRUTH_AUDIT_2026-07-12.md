# Nova Documentation Code-Truth Audit

Date: 2026-07-12

Commit inspected: `92ca149e452e96dfd0d9224eb2d11a0862c3ccea`

This audit rebuilds documentation scope from source code. It does not use a previous architecture document as the inventory boundary, and it does not claim that a declared surface is correct merely because a test names it.

## Scope

The scan covered:

- every active Python source file outside generated runtime state, tests, agent probes, caches, and archived data lanes
- every Python function, nested function, method, and class in that active source set
- every `services/*.py` and `services/edfi/*.py` module
- `nova.ps1` and the PowerShell release, installer, and OS-capability scripts
- named functions in the control-room and Leah JavaScript
- every `tests/test_*.py` module and every test function
- declared compact regression lanes and source-profile lanes
- the 45 declared wiring surfaces and 45 declared source-root entries
- the guard, core, HTTP, maintenance, Work Tree, Mission, orchestrator, execution gate, outbox, tool, patch, release, data, Ed-Fi, SOCK, Kidney, subconscious, and test paths
- all Markdown documentation under `docs/` plus the root `README.md`

Mechanical inventories are stored in:

- `FUNCTION_INDEX.md`: 281 active Python files, 3,431 functions/methods, 181 classes, plus named JavaScript and PowerShell functions
- `TEST_INDEX.md`: 215 test modules and 2,016 test functions, with declared lane membership
- `SERVICES_INDEX.md`: every current service module and its public API surface

These counts are snapshots of this commit. They are inventory evidence, not health evidence.

## What The Old Documentation Missed

The central documentation was last materially rebuilt between 2026-06-11 and 2026-06-14. The code added or substantially changed Mission, owner verdicts, layer maturity, release runtime truth, Work Tree pressure ownership, operator holds, status hydration, Ed-Fi core, the BISD lane, Leah continuity, code generation, and several runtime-control seams after that baseline.

Concrete drift found:

- `SERVICES_INDEX.md` omitted 41 current top-level service modules.
- `SYSTEM_MAP.md` did not include `nova_mission.py` or `nova_mission_owner_verdicts.py`.
- `SYSTEM_MAP.md` placed the HTTP server inside `nova_core.py`; the actual web runtime is a separate `nova_http.py` process on port 8080.
- `STATUS.md` presented June 14 health and release values as current truth.
- `DATA_PIPELINES.md` said there were no active data lanes; `data_sources/edfi_bisd/` is active and the vendor-neutral Ed-Fi core is wired.
- the Supervisor documentation described populated deterministic rule ownership, while `DEFAULT_SUPERVISOR_RULE_SPECS`, `EXPLICIT_INTENT_OWNERSHIP_RULES`, and `EXPLICIT_HANDLE_OWNERSHIP_RULES` are currently empty.
- SOCK had no dedicated current system document.
- Mission had no dedicated architectural document.
- the test ecosystem had no complete lane and module inventory.
- Kidney documentation did not cover retired generated-definition tracking, export and ledger pressure, snapshot count/size caps, or cleanup snapshot pruning.
- the control-room documentation did not describe split hydration through `/api/control/status/surfaces` and targeted endpoints.

## Current Process Truth

Nova does not run as one process containing every surface.

```text
nova.ps1 / nova.cmd
  |-- nova guard  -> nova_guard.py
  |                   |-- supervises nova_core.py
  |                   `-- launches autonomy_maintenance.py --once on cadence
  |-- nova run    -> nova_core.py directly
  |-- nova webui  -> nova_http.py on port 8080
  `-- tool, test, package, installer, SOCK, and wiring commands
```

`nova_core.py` owns the local interactive core, heartbeat, tool exports, memory adapters, patch compatibility wrappers, and CLI reply path. It does not host the control-room HTTP server.

`nova_http.py` is a separate `ThreadingHTTPServer`. It imports the core as a callable runtime and delegates transport, routes, auth, control actions, status composition, Work Tree views, pipelines, Leah, and chat finalization to services.

`nova_guard.py` owns core process identity, boot observation, heartbeat failure detection, restart resolution, and periodic one-shot maintenance launch.

`autonomy_maintenance.py` can also run as a detached loop worker. The code therefore contains two maintenance-launch arrangements, with cross-process checks intended to prevent simultaneous cycles.

## Current Feedback Loop

The normal maintenance cycle is ordered roughly as follows:

1. Ensure the operator web UI is reachable.
2. Consume explicit Work Tree or patch-queue trigger files, if present.
3. Run the subconscious pack and read its latest report.
4. Re-evaluate pending generated review work.
5. Run Kidney cleanup according to policy.
6. Clean and synchronize patch queue state.
7. Synchronize core-thinning work.
8. Run the legacy patch Work Tree lane when policy allows it.
9. Synchronize generated queue work.
10. Ingest temporal events.
11. Perform a pre-execution Signal Intake sync.
12. Compose Mission and run the Autonomy Orchestrator advisory/execution path.
13. Run generated and active Work Tree lanes according to execution ownership and Mission hold behavior.
14. Archive or retire eligible Work Trees.
15. Run or refresh regression evidence.
16. Perform a post-execution Signal Intake sync.
17. Refresh Mission from the final cycle evidence and persist state.

This ordering matters. A field from the final Mission snapshot must not be assumed to have governed an action that used an earlier snapshot.

## Mission's Actual Place

Mission is currently both a verdict composer and a policy participant.

It composes:

- operations readiness from core posture, runtime readiness, alerts, Work Tree pressure, and fresh-gap pressure
- truth readiness from validation, regression, release truth, generated queue evidence, layer maturity, and explicit owner verdicts
- `status`, `action`, `green_cycle`, `truth_ready`, owner verdicts, owner blockers, and green blockers

It also owns or applies:

- hold block and allow action lists
- the `core_thinning` tool exception during release drift
- generated-queue validation exceptions during hold
- ambient governance-ingestion suppression during hold

That second set is important code truth. It means Mission is not yet only a passive sentence over owner evidence.

## Work Tree And Signal Truth

Work Tree is a SQLite-backed state machine with trees, branches, tasks, tool declarations, dependencies, evidence records, and autonomous step execution. Signal Intake converts runtime surfaces into branches and reconciles them as sources appear or clear.

The current pressure owner is `services/work_tree_pressure_snapshot.py`. Operator-hold classification is owned by `services/work_tree_operator_hold.py`. Consumers still need to be checked for independent pressure logic or fallback interpretations.

Signal Intake is not a small adapter. At this commit it is the largest active source module and owns a broad set of source-specific signal builders, task sequences, source-root judgment flow, branch reconciliation, and ambient suppression behavior.

## Tool And Action Truth

The direct tool registry contains nine tool objects:

- filesystem
- code generation
- patch
- vision
- research
- system
- OS capability
- temporal review
- Ed-Fi explore

Core exports and Work Tree execution expose additional action names over those objects and over service functions, including read/find/list, health, queue, pipeline, weather, patch preview, release judgment, memory bootstrap, subconscious judgment, source-root judgment, and core thinning.

The control-action dispatcher currently handles more than 50 operator and autonomy actions. Only ten are in the autonomy advisory catalog. Documentation must keep those two inventories distinct.

## Testing Truth

The test tree contains more tests than the compact regression runner executes.

- compact unit lane: 81 declared entries
- compact behavior lane: 8 declared entries
- compact integration lane: 8 declared entries
- source-profile map: 20 lane keys total
- full discovered test modules: 215
- discovered test functions: 2,016

The regression profile inventory is therefore part of test truth. A passing compact command is not equivalent to every discovered test being classified or executed.

No tests were run as part of this documentation-only audit. Existing past pass counts are historical evidence only.

## Inventory Defects Found During The Documentation Scan

The scan found code facts that documentation must not hide:

1. `SOURCE_ROOTS` declares 45 entries but only 43 unique root IDs. `edfi_core` and `data_lane_edfi_bisd` are each declared twice.
2. The active-work target path carries `target_tree_id` through orchestrator, execution gate, and maintenance, but resolves it from a bounded active-candidate list. A valid target outside that window can become `stale_execution_contract`.
3. Operator actionability currently excludes every open event whose source is `autonomy_maintenance`, including genuine failed execution notices.
4. Work Tree records invalid tool results as `tool_failed`, restores the task to open, and records failure evidence. Maintenance later marks those failed tasks complete and reports the cycle as `attempted`.
5. The default Supervisor registry and explicit ownership sets are empty. The seam exists, but populated default ownership does not.
6. Policy currently has `orchestrator_owns_execution=false` and `legacy_maintenance_execution_enabled=true`; documentation must not describe orchestrator-only execution as the current mode.

These are documentation findings, not fixes. They remain code work until investigated and corrected at their owners.

## Documentation Authority After This Audit

Use this order for code understanding:

1. `CODE_TRUTH_AUDIT_2026-07-12.md`
2. `SYSTEM_MAP.md`
3. `AUTONOMY_AND_MISSION.md`
4. `SERVICES_INDEX.md`
5. `FUNCTION_INDEX.md`
6. `TEST_ECOSYSTEM.md` and `TEST_INDEX.md`
7. subsystem documents such as `DATA_PIPELINES.md`, `KIDNEY_SYSTEM.md`, and `SOCK_SYSTEM.md`

Use runtime artifacts for live state. Do not use a Markdown status sentence to override current runtime evidence.
