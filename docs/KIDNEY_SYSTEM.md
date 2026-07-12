# Kidney System

Last verified from code: 2026-07-12

Kidney owns cleanup and retention. It does not decide whether Nova is healthy, whether a failed task is complete, or whether a release is valid.

Current policy mode: `enforce`.

## Inputs

Kidney reads:

- generated session definitions and their metadata
- pending-review and quarantine artifacts
- promotion audit history
- patch previews and snapshots
- Kidney cleanup snapshots
- temporary and test-session artifacts
- runtime exports
- ledger sizes
- protected path patterns
- retired generated-definition index
- policy age, count, size, novelty, and protection limits

## Candidate Classes

- old or low-novelty generated definitions
- expired quarantine or pending-review material
- stale/ineligible patch previews
- stale or excess snapshots
- old temporary/test artifacts
- export retention pressure
- oversized ledgers

Each candidate carries a category, action, reason, path, and supporting metadata.

## Modes

- `observe`: scan and report candidates
- `enforce`: snapshot the cleanup set, then archive/delete according to policy

## Safety And Retention

- protected patterns are excluded
- cleanup intent is snapshotted before enforcement unless policy and candidate shape allow skipping it
- cleanup snapshots are capped by age, count, and total bytes
- generated definitions retired by Kidney are recorded with fingerprints and metadata
- patch snapshots and Kidney snapshots have separate roots
- status is written to `runtime/kidney/status.json`
- maintenance logs Kidney output with a `[KIDNEY]` prefix

## Paths

- `runtime/kidney/status.json`
- `runtime/kidney/archive/`
- `runtime/kidney/snapshots/`
- `runtime/kidney/protect_patterns.json`
- `runtime/kidney/retired_generated_definitions.json`
- patch preview and snapshot roots under the active runtime/update scope

## Commands

- `kidney status`
- `kidney now`
- `kidney dry-run`
- `kidney protect <pattern>`

## Feedback Loop

Maintenance runs Kidney before pre-execution Signal Intake and orchestrator evaluation. Kidney summary fields can contribute storage/release pressure and generated-definition truth, but Mission should receive those facts through their owning evidence paths rather than rebuilding cleanup logic.
