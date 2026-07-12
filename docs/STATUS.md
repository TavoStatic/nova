# Nova Status

Documentation baseline: 2026-07-12

Code baseline: `92ca149e452e96dfd0d9224eb2d11a0862c3ccea`

## What This Page Can Truthfully Say

The documentation has been rebuilt against the current source tree. It now inventories Mission, autonomy, Work Tree pressure ownership, status hydration, Ed-Fi core and BISD lane, SOCK, Kidney, subconscious, codegen, release truth, and the test ecosystem.

This page does not claim Nova is green, healthy, release-ready, or regression-clean. Those are live or artifact-backed verdicts and must be read from their owners.

## Current Code Shape

- 281 active Python source files in the documentation function inventory
- 3,431 Python functions/methods and 181 classes indexed
- 168 top-level service modules plus the Ed-Fi service subpackage represented in the service index
- 45 unique wiring surfaces
- 45 source-root declarations but 43 unique IDs
- 215 discovered test modules and 2,016 test functions indexed
- Mission and owner-verdict composition enabled in policy
- mixed autonomy execution mode: legacy maintenance execution enabled; orchestrator sole ownership disabled
- Leah and codegen layers in `observe` mode with no promoted capabilities
- active vendor-neutral Ed-Fi core and active BISD data lane

## Live Truth Sources

| Question | Read this owner |
|---|---|
| Are guard/core/web UI running? | runtime process status and identity files |
| What did the last maintenance cycle do? | `runtime/autonomy_maintenance_state.json` and log |
| What is Mission's latest verdict? | `last_nova_mission` in maintenance state |
| What work is open or blocked? | `runtime/_internal/work_tree.db` |
| What did the orchestrator decide? | `runtime/autonomy_orchestrator_ledger.jsonl` |
| What does Nova want the operator to know? | `runtime/operator_outbox.jsonl` |
| Did regression run and pass? | `runtime/regression_status.json` |
| Is validation evidence usable? | validation artifact truth and release validation record |
| Does source match the running/released build? | release runtime truth and release ledger |
| What cleanup occurred? | `runtime/kidney/status.json` |

## Documentation Findings Still Open In Code

- failed Work Tree tool executions may be marked complete by maintenance
- autonomy-maintenance outbox notices are broadly excluded from operator actionability
- active target resolution searches a bounded candidate list
- Mission applies policy exceptions and suppression in addition to verdict composition
- Supervisor default rules and explicit ownership sets are empty
- Ed-Fi source-root IDs are duplicated in the root inventory

These are not documentation defects anymore. They are named code findings.

## Validation Note

No test suite was run during the documentation audit. Historical pass counts remain historical. Before publishing a current validation claim, record the exact command, commit, profile, test count, timestamp, and artifact identity.

## Resume Order

1. `CODE_TRUTH_AUDIT_2026-07-12.md`
2. `SYSTEM_MAP.md`
3. `AUTONOMY_AND_MISSION.md`
4. live maintenance, Work Tree, regression, and release artifacts
5. `SERVICES_INDEX.md` and `FUNCTION_INDEX.md`
6. `TEST_ECOSYSTEM.md` and `TEST_INDEX.md`

`This_is_nova`, phase assessments, dated scans, and roadmap documents are history or planning context. They do not override current code or runtime evidence.
