<!--
NOVA_DOC
category: subsystem
authority: active_working
last_session: 2026-09-01
last_agent: grok
session_state: current
next_step: none
open: mill sip-execute not live-promoted
-->

# Nova Autonomy And Mission

Last verified from code: 2026-09-01 (skip/remint/stop/pulse live-promoted; mill sip-execute not promoted; rest of this file still lags)

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
- mill judgment class + pressure are derived, not a fifth stored status; the mill does not name an LLM
- SOCK may lease a temporary mill model from that signal; standing `chat_model()` stays the policy string
- a cycle `ok` with mill `executed=0` is not proof the finding moved
- mill skip of `orchestrator_owns_execution` is a loop event; three trailing mill skips run mill once
- a spine `loop` / `pulse` / `SELF_PREDICTION_MISS` report that leaves the next cycle identical is representation, not control
- paid trail (controlling `redundant` / `refused`) holds the world; ingest must keep `attempt_judgments`

## Mill capacity handoff

Pickup and execute steps carry `mill_judgment_signal` from `services/solution_trail.py` (`mill_judgment_signal`). Mill-adjacent LLM invokes go through `services.sock_service.run_with_mill_capacity`. Kernel tool execute (`source_root_judgment`, `read`, …) is not an LLM sip — leasing 9B around those tools is caffeine with no thinking.

Evidence for which model wins which mill class: `docs/MILL_LANE_MEASURE_2026-09-01.md`. SOCK contract: `docs/SOCK_SYSTEM.md`.

## Mill skip / remint / stop / pulse (promoted 2026-09-01)

Live-validated on `codex/push-prep` commit `23fa484`. Promote **only** this control. Do not promote mill sip-execute.

- Three trailing mill `invoke` skips on `active_work_tree_cycle` (`orchestrator_owns_execution`) run mill once (`mill_skip_stop_run`).
- Mill-ok clears the trailing force. The next cycle does not remint mill; pulse may return.
- Paid trail (`trail_world_holds`) blocks compact-lane remint. Ingest keeps `attempt_judgments`.
- Spine may still report `REPEATED_UNCHANGED_PATH` after mill-ok. Control uses trailing mill observations, not that report.

Live trail 2026-09-01: skip, skip, skip → `22:14:01` mill `idle` / `mill_skip_stop_run` → `22:18:53` mill `skipped` and orchestrator `pulse_status`. Compact-lane `branch_d1817af9` stayed `ATTEMPTED` (`task_53c41ded`); OPEN `[]`.

Overnight 2026-09-01 (~7h) before this control: 74 cycles `ok`, mill execute 0, spine on **pulse_status**. That trail is historical.

Sip-execute of standing 4B / sip 9B when `source_root_judgment` is reached is **wired, not live-promoted**. This cycle did not reach that tool because the paid trail left no OPEN judgment stem.

## Known Current Violations Or Risks

- failed Work Tree tool executions can be marked complete by maintenance after failure evidence is recorded
- broad outbox source filtering can hide actionable autonomy failures
- target resolution is bounded by candidate enumeration
- Mission still contains execution exceptions and ambient-ingestion suppression, so it is more than a thin verdict sentence
- mixed legacy/orchestrator execution creates two paths that must remain behaviorally aligned
- mill sip-execute on `source_root_judgment` is wired (standing 4B / sip 9B) and not live-promoted

These statements are code-truth findings. They are not resolved by this document.
