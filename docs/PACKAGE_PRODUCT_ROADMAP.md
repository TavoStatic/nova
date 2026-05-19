# Nova Package Product Roadmap

Date: 2026-05-18
Last verified: 2026-05-18

## Goal
Drive Nova from an actively evolving supervised runtime to a repeatable package product with clear release gates, documented operations, and stable governance defaults.

## Immediate Priorities
1. Complete independent fresh-machine or VM validation for `2026.05.18.23`.
2. Exercise the interactive `nova run` front door against the current artifact.
3. Keep repository documentation synchronized with actual runtime behavior.
4. Decide whether Piper remains bundled through Git LFS or moves to a bootstrap-fetch path later.

## Release Gate Stack

### Gate 1: Runtime Stability
- Full regression must pass.
- Critical path smoke tests must pass:
  - session replay parity
  - HTTP identity/profile continuity
  - chat intent and grounded proof replies
  - OS capability contract execution and blocked-contract evidence
  - operator-outbox notice/reconciliation path
  - patch governance path
  - maintenance loop execution

### Gate 2: Governance Stability
- Safety envelope active and auditable.
- Kidney active and auditable.
- At least one full maintenance cycle with no regressions and no uncontrolled destructive behavior.

### Gate 3: Packaging Boundary
- Packaging matrix current and accurate.
- Runtime-generated directories excluded from package payload.
- Operator-provided inputs clearly separated from shipped assets.

### Gate 4: Operator Handoff
- Bootstrap flow documented and verified.
- Operations runbook current.
- Product status and roadmap docs reflect current code reality.
- Release artifact is buildable from the canonical launcher flow.

## GitHub Update Protocol (Per Iteration)
1. Update canonical docs after each meaningful architectural slice:
  - `docs/STATUS.md`
  - `docs/PACKAGING_MATRIX.md`
  - `docs/OPERATIONS.md` (when behavior changes)
2. Include runtime verification summary in the PR body:
  - full regression count/result
  - targeted smoke suites and result
  - maintenance/governance notes
3. Keep product-facing docs consistent with shipped behavior, not aspirational behavior.

## Near-Term Plan
1. Keep the source-bootstrap zip as the current release artifact and rerun its validation for each candidate.
2. Use `nova package-readiness` and the release validation record as the release-candidate truth gate.
3. Complete independent fresh-machine or VM validation before final release language.
4. Verify the interactive `nova run` front door for the current artifact.
5. Keep product-facing docs consistent with shipped behavior, not aspirational behavior.

## Definition of "Close To Package Product"
Nova is considered near package-ready when:
- regression and smoke gates are consistently green
- governance layers are stable and operationally transparent
- packaging boundary is explicit and enforced
- bootstrap + handoff docs are sufficient for a fresh machine/operator
- release notes can be generated from canonical docs without manual archaeology
