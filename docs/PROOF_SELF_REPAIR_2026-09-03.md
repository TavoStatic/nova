<!--
NOVA_DOC
category: evidence
authority: live_runtime_proof
last_session: 2026-09-03
last_agent: claude-cowork
session_state: current
next_step: none
open: none
-->

# Live Self-Repair Proof — Identity Bootstrap, 2026-09-03

Controlled fault-injection experiment on the live runtime. Operator-authorized.
Every claim below is backed by an artifact in the auahority mill
(`runtime/_internal/work_tree.db`), the maintenance log, or a baseline snapshot
taken before injection. No human input between injection and closure.

## Claim proven

Nova detected the loss of her own identity file, planned the correct repair,
executed it, recorded evidence, and closed the finding only after the runtime
confirmed the repair — autonomously, in twenty minutes.

## Timeline (local runtime clock, 2026-09-03)

| Time | Event | Artifact |
|---|---|---|
| 15:29 | Baseline pinned: work_tree.db, outbox, spine window, identity.json copied | experiment snapshots |
| 15:29:26 | **Fault injected**: `memory/identity.json` removed. Origin contract and learned_facts untouched | file absent |
| 15:33:07 | **Detection**: branch `branch_852bbc1f` "Investigate memory persistence bootstrap gap" minted; ingestion signal count 11 → 13 | work_tree_branches row; log 15:33:32 `results=13` |
| 15:33 | **Plan**: single stem "Apply operator-confirmed memory identity bootstrap", `allowed_tools: [memory_identity_bootstrap]` | task_617f376e |
| 15:47:01 | **Repair**: `apply_identity_bootstrap` executed; `identity.json` rebuilt from origin contract | file `applied_at: 2026-09-03 15:47:01` |
| 15:47:11 | **Evidence**: `evidence_2ee639ca98`, tool `memory_identity_bootstrap`, "status: applied, reason: operator_confirmed_identity_bootstrap_applied" | work_tree_evidence row |
| 15:49:04 | **Satisfaction**: `recurring_finding_satisfaction_status: satisfied`, key `governance_pressure:memory_identity:memory_bootstrap_incomplete:identity_memory` | branch payload lifecycle |
| 15:49:08 | **Signal extinguished**: ingestion `resolved=2` | maintenance log |
| 15:49:04 | **Branch closed**: status `complete`, resolution `resolved` | work_tree_branches row |
| 15:51:27 | Signal count back to pre-fault baseline (11) | maintenance log |

## Verification of the repair

Rebuilt file compared to the pre-fault original: all identity fields identical
(`assistant_name: Nova`, `developer: Gustavo Uribe / Gus`, schema, origin
authority). Only difference: `bootstrap.applied_at` — original
`2026-05-13 21:31:13`, rebuilt `2026-09-03 15:47:01`. She wrote the same truth
with a new timestamp, sourced from the operator-confirmed origin contract
(`memory/bootstrap_origin.json`, status ready, all three slots confirmed).

## Why the close is honest

The branch did not close on tool success. The repair ran at 15:47; the close
came at 15:49 only after the next ingestion pass observed the identity file
present, dropped the finding from the active set, and the recurring-finding
lifecycle marked satisfaction. Closure was governed by the observed state of
the world, not by the tool's claim of success.

## Chain of mechanism (each link previously verified by code read)

1. `nova_core.memory_health_payload` (L1517) → missing `IDENTITY_FILE` puts
   `"identity"` in `bootstrap.missing` (services/memory_health.py L368–372)
2. `_memory_health_signal_from_status`
   (services/work_tree_signal_ingestion.py L279–392): `origin_ready and
   bootstrap_missing` → direct-repair branch, preferred tool
   `memory_identity_bootstrap` (L363–378)
3. Mill dispatch (work_tree.py L2540) →
   `apply_identity_bootstrap` (services/memory_identity_bootstrap.py L64+),
   gated on origin contract `may_seed_identity_facts` (derived at
   services/memory_bootstrap_origin.py L186–193)
4. Recurring-finding lifecycle satisfaction + signal resolution closed the
   branch (services/recurring_finding_lifecycle.py)

## Scope — what this does and does not prove

Proves: autonomous detect → plan → repair → evidence → world-confirmed close,
live, within Nova's existing promoted toolset.
Does not prove: novel-code self-repair (codegen remains in observe mode), or
behavior on faults outside her sensed surfaces.

## Experiment conduct

Fault chosen from a verified code-path map before injection; baseline snapshots
taken; single file moved; zero interaction during the run; rollback copy held
throughout and never needed.
