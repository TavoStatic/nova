# Work Tree Baseline Report

## Historical Use

Historical audit snapshot from 2026-04-17.

This report reflects one Work Tree audit pass and is not the current Work Tree authority.

For current repo-facing truth, use:

1. `work_tree.py`
2. `This_is_nova`
3. `docs/CURRENT_TRUTH_2026-04-18.md`

The content below is preserved as a historical audit artifact.

Audit mode: mixed live inspection. Listing and database truth were observed directly; code was not changed.

## Backend truth

- Public listing endpoint `GET /api/control/work-trees` is live.
- Snapshot from this audit:
  - `count=22`
  - sampled tree: `Chat: patch rollback`
  - sampled dependency edges were present in the payload.

## Database truth

- Live database path: `runtime/_internal/work_tree.db`
- Current persisted status counts:
  - trees: `14 active`, `8 complete`
  - branches: `22 ready`, `7 blocked`, `35 complete`
  - tasks: `29 open`, `9 complete`

## Identity and duplication truth

- No duplicate persisted `work_identity_key` rows were found in the top duplicate scan.
- Duplication pressure still exists at the title and lifecycle level:
  - repeated near-identical active trees such as `Http: create a work tree for quarterly report planning`
  - repeated near-identical dependency trees such as `Http: create a work tree with dependencies and show me the active work tree`
- Baseline interpretation: current duplication is more about repeated tree creation and low turnover than about identity-key collision.

## Blocked and incomplete judgment truth

- There are `7` blocked branches in the live DB.
- Sample blocked chains show normal dependency encoding but weak turnover:
  - `Step 2: apply patch rollback` blocked on `Step 1: identify patch to roll back`
  - work-tree status/reporting branches blocked behind earlier inspection branches
- There are also ready branches with open work but no governed tool assignment.
  - The top scan found multiple `ready` branches with `open_stem_count > 0` and empty `preferred_tool` / `allowed_tools`.
  - These clustered under `Signal Intake: Runtime Governance` and related remediation titles.
- Baseline interpretation: the backend can persist blocked dependency structure, but some active branches are still under-specified at the tool-governance layer.

## Surface parity truth

- Backend/listing layer: live and populated.
- Natural-language chat/operator layer: currently drifting.
  - work-tree prompts did not return snapshot-style replies or next-step guidance
  - live tree count did not move during the work-tree prompt probes

## Work Tree conclusion

- Work Tree is not dead.
- The backend persistence layer is real and retains dependency structure.
- The main current regression is at the prompt-routing and lifecycle-turnover layer:
  - too many active trees remain open
  - blocked and under-governed branches remain in place
  - user-facing work-tree prompts are not reliably reaching the backend behavior the stored data implies exists.

