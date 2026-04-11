# Nova Package Product Roadmap

Date: 2026-03-25

## Goal
Drive Nova from an actively evolving supervised runtime to a repeatable package product with clear release gates, documented operations, and stable governance defaults.

## Immediate Priorities
1. Protect stability while Phase 2 governance settles.
2. Keep repository documentation synchronized with actual runtime behavior.
3. Reduce packaging ambiguity so a fresh operator can bootstrap and validate the product quickly.

## Release Gate Stack

### Gate 1: Runtime Stability
- Full regression must pass.
- Critical path smoke tests must pass:
  - session replay parity
  - HTTP identity/profile continuity
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
1. Hold `safety_envelope.mode=observe` and `kidney.mode=observe` for one full monitored cycle.
2. If stable, move Kidney to `enforce` first while keeping Safety Envelope in `observe`.
3. Re-audit and then decide on Safety Envelope `enforce` transition.
4. Keep the source-bootstrap zip as the current release artifact and rerun its validation for each candidate.
5. Once governance is stable, run a package-readiness pass and prepare a release candidate checklist.

## Definition of "Close To Package Product"
Nova is considered near package-ready when:
- regression and smoke gates are consistently green
- governance layers are stable and operationally transparent
- packaging boundary is explicit and enforced
- bootstrap + handoff docs are sufficient for a fresh machine/operator
- release notes can be generated from canonical docs without manual archaeology
