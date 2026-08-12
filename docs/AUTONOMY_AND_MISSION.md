<!--
NOVA_DOC
category: subsystem
authority: active_working
last_session: 2026-08-05
last_agent: claude-cowork
session_state: needs_update
next_step: review mission boundary after orchestrator work
open: none
-->

# Nova Autonomy And Mission

Last verified from code: 2026-07-12

## Purpose

Nova's autonomy is a feedback loop, not a single agent call. Runtime owners publish evidence, Signal Intake turns relevant pressure into Work Tree state, the orchestrator recommends an action, the execution gate checks policy, Work Tree executes bounded steps, and Mission composes the cycle verdict.

Mission belongs inside that loop. It does not own the underlying validation, regression, release, queue, Work Tree, or core-thinning facts.

## Owners

| Concern | Current owner |
|---|---|
| Maintenance cycle and persisted cycle state | `autonomy_maintenance.py` |
| Pressure-to-action selection | `services/autonomy_orchestrator.py` |
| Execution policy checks | `services/autonomy_execution_gate.py` |
| Decision ledger | `services/autonomy_orchestrator_ledger.py` |
| Task/branch/evidence state | `work_tree.py` |
| Runtime signal conversion and reconciliation | `services/work_tree_signal_ingestion.py` |
| Work Tree pressure composition | `services/work_tree_pressure_snapshot.py` |
| Operator-hold classification | `services/work_tree_operator_hold.py` |
| Mission cycle verdict | `services/nova_mission.py` |
| Mission owner-verdict normalization and truth gate | `services/nova_mission_owner_verdicts.py` |
| Layer promotion and core gate | `services/layer_maturity_policy.py` |
| Release/source/build identity | `services/release_runtime_truth.py` |
| Core/http thinning analysis and Work Tree feed | `services/core_thinning.py` |
| Operator notices | `services/operator_outbox.py` |

## Evidence Flow

```text
runtime owners
  -> control/local status surfaces
  -> Signal Intake
  -> Work Tree branches/tasks/evidence
  -> pressure snapshot
  -> Mission input envelope
  -> Mission verdict
  -> Orchestrator recommendation
  -> execution gate
  -> control-action dispatcher
  -> bounded Work Tree/tool execution
  -> evidence and cycle state
  -> second Signal Intake pass
  -> refreshed Mission verdict
```

Mission is composed before orchestrator evaluation and refreshed after the final Signal Intake pass. Consumers must identify which snapshot they read.

## Mission Inputs

Mission currently reads these composed groups:

- policy and Mission mode
- core steward posture and runtime readiness
- Work Tree pressure and active candidates
- generated and patch queue pressure
- alert and fresh-gap counts
- validation artifact truth
- regression status and staleness
- release runtime truth and release status
- layer-maturity core gate
- explicit owner verdicts, including core thinning

An output field should be traceable to one of those inputs in the same cycle. Missing evidence is not equivalent to a negative fact.

## Mission Outputs

The main snapshot publishes:

- `enabled`, `mode`, `objective`
- `status` and `action`
- `green_cycle`, `ops_ready`, and `truth_ready`
- `truth_blockers` for compatibility
- `owner_verdicts`, `owner_blockers`, and `green_blockers`
- validation, regression, release, queue, core-gate, and pressure summaries
- hold block/allow contracts and active-work tool allowance
- source timestamp and freshness

`green_cycle` is the conjunction of operations readiness and truth readiness. A hold is not automatically green.

## Current Mission Modes

- `steady_state_guard`: hold when ready, investigate active operational pressure, and retain truth blockers.
- `observe_only`: observe without autonomous execution.
- `recovery`: investigate repair pressure.
- `operator_focus`: hold for operator-led work.

Current policy uses `steady_state_guard`.

## Hold Contract

Current policy blocks these actions while Mission hold is active:

- active Work Tree execution
- generated queue execution and investigation
- pulse status action
- code generation
- Leah build execution

Current policy allows:

- patch queue execution
- guard start
- autonomy maintenance start

The service default also permits targeted `core_thinning` active work during the specific release-drift blocker and permits generated-queue validation under a narrow blocker set. These are current code behaviors, not properties of truth itself.

## Execution Ownership

Current `policy.json` uses:

- `orchestrator_owns_execution=false`
- `legacy_maintenance_execution_enabled=true`

That means Nova is still in a mixed execution mode. The orchestrator evaluates and can dispatch actions, while maintenance retains legacy lane execution paths. Documentation must not describe the transition target as already complete.

## Active Work Targeting

The intended target contract is:

```text
Work Tree candidate
  -> branch_id + task_id + tree_id + recommended_tool
  -> orchestrator recommended_action
  -> execution gate dispatch_payload
  -> maintenance active-work action
  -> targeted Work Tree cycle
```

The target fields are wired across that chain. The current resolver still obtains candidates through a bounded list before filtering for the target, so target existence and target visibility are not yet identical.

## Operator Outbox

The outbox stores raw open notices and also publishes an `operator_actionable_open_count`. Signal Intake uses the actionable count when available to avoid converting Nova's internal wait into operator-control pressure.

Current code excludes all `autonomy_maintenance` source events from actionability. That suppresses feedback loops, but it also suppresses genuine autonomy failures. The distinction needs to be based on the event contract, not only its source.

## Honesty Invariants

These are the required documentation and implementation invariants:

- evidence absence is not evidence of zero
- a tool failure remains unresolved until an owner or explicit judgment closes it
- a test pass proves only the exercised contract
- Mission repeats owner evidence; it does not replace owner evidence
- hold, blocked, observing, attempted, complete, and green are different states
- pressure visibility must not be converted into truth failure without an owner contract
- pressure suppression must not erase diagnosis
- execution context must identify the same tree, branch, task, and tool at every handoff

## Known Current Violations Or Risks

- failed Work Tree tool executions can be marked complete by maintenance after failure evidence is recorded
- broad outbox source filtering can hide actionable autonomy failures
- target resolution is bounded by candidate enumeration
- Mission still contains execution exceptions and ambient-ingestion suppression, so it is more than a thin verdict sentence
- mixed legacy/orchestrator execution creates two paths that must remain behaviorally aligned

These statements are code-truth findings. They are not resolved by this document.
