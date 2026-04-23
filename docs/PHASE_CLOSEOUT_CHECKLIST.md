# NYO System Phase Closeout Checklist

Date: 2026-04-01

## Purpose

This is the master checklist for closing the current NYO System phase.

It is intentionally short.

It does not replace the detailed checklists. It tells the team:

- what must be true before this phase can be called complete
- which detailed document owns each proof step
- what is phase-blocking versus only important

Use this file as the top-level control document.

Use the linked documents as the detailed procedures.

Status legend:

- `[x]` satisfied
- `[-]` partial / in progress
- `[ ]` still open

## Main Objective

Close this phase only when one release candidate is truthful across all four surfaces:

1. workspace root
2. packaged artifact
3. installed copy
4. operator handoff documentation

If those disagree, the phase is not complete.

## Exit Standard

The current phase is complete only when every item below is true.

## A. Workspace Truth

- [x] `nova install` works from the workspace root
- [x] `nova doctor` passes from the workspace root
- [x] `nova runtime-status` is readable and truthful from the workspace root
- [-] `nova run` and `nova webui-start` launch cleanly enough for operator use
- [x] focused or compact regression is green for the current candidate

Current read:

- workspace launcher validation is documented green in `docs/STATUS.md`
- compact regression is documented green
- operator use is credible, but should still be treated as part of final release-candidate rerun discipline

Primary references:

- [OPERATIONS.md](c:/Nova/docs/OPERATIONS.md)
- [BASE_PACKAGE_READINESS.md](c:/Nova/docs/BASE_PACKAGE_READINESS.md)

## B. Package Truth

- [x] `nova package-build` produces the expected artifact without folding in local runtime state
- [x] `nova package-verify` passes for the current package candidate
- [x] `nova package-status` and `nova package-readiness` reflect the real candidate state
- [-] package boundary still matches [PACKAGING_MATRIX.md](c:/Nova/docs/PACKAGING_MATRIX.md)

Current read:

- package build and verification flows are real and working
- package ledger and readiness flows are real and working
- boundary discipline is mostly satisfied, but still treated as an active maintenance concern in `docs/STATUS.md` and `docs/BASE_PACKAGE_READINESS.md`

Primary references:

- [RELEASE_ARTIFACT.md](c:/Nova/docs/RELEASE_ARTIFACT.md)
- [BASE_PACKAGE_READINESS.md](c:/Nova/docs/BASE_PACKAGE_READINESS.md)
- [PACKAGING_MATRIX.md](c:/Nova/docs/PACKAGING_MATRIX.md)

## C. Installed-Copy Truth

- [x] installer or extracted-package validation has been run against an isolated or clean target
- [x] the installed or extracted copy passes `doctor`
- [ ] the installed or extracted copy passes `runtime-status`
- [ ] the installed or extracted copy does not depend on hidden workspace assumptions
- [x] any deviations are written into the release ledger as notes, not carried informally

Current read:

- isolated same-machine installer validation has been run
- guided installed copy created `.venv` and passed `doctor`
- installed-copy `runtime-status` still exposed a real launcher/runtime gap in the packaged `nova.ps1`
- this section is still phase-blocking until installed-copy truth matches workspace truth

Primary references:

- [FRESH_MACHINE_VALIDATION.md](c:/Nova/docs/FRESH_MACHINE_VALIDATION.md)
- [WINDOWS_INSTALLER_PLAN.md](c:/Nova/docs/WINDOWS_INSTALLER_PLAN.md)
- [RELEASE_ARTIFACT.md](c:/Nova/docs/RELEASE_ARTIFACT.md)

## D. Operator Truth

- [-] [HANDOFF.md](c:/Nova/docs/HANDOFF.md) matches the real operator flow
- [-] [OPERATIONS.md](c:/Nova/docs/OPERATIONS.md) matches the real launcher behavior
- [-] `/control` and operator-facing runtime surfaces still reflect live state correctly
- [x] operator-console parity checks have been rerun when control, routing, telemetry, or session behavior changed

Current read:

- operator-console parity coverage exists and recent focused operator-surface tests are documented green
- operator flow docs are credible, but this section should not be marked fully closed until the installed-copy truth gap is gone and the next release-candidate rerun is complete

Primary references:

- [HANDOFF.md](c:/Nova/docs/HANDOFF.md)
- [OPERATIONS.md](c:/Nova/docs/OPERATIONS.md)

## E. Architecture and Boundary Completion

- [ ] the remaining `nova_http.py` duplicate/helper cleanup is finished for this phase
- [-] service-boundary work has removed stale duplicate logic rather than leaving parallel truths in place
- [-] no known phase-blocking disagreement remains between HTTP behavior and core behavior

Current active HTTP-boundary work:

- [-] inspect duplicated HTTP helpers
- [ ] wire `nova_http.py` to modules
- [ ] remove stale duplicate logic
- [ ] rerun focused HTTP tests after cleanup

Current read:

- the architecture docs already record that `nova_http.py` is much narrower than before
- major control-room and deterministic ownership has already moved into services
- the remaining work is now cleanup and truth consolidation, not first-pass extraction
- this section stays open until the active HTTP-boundary items above are complete

Primary references:

- [ARCHITECTURE.md](c:/Nova/docs/ARCHITECTURE.md)
- [PHASE_COMPLETION_ASSESSMENT.md](c:/Nova/docs/PHASE_COMPLETION_ASSESSMENT.md)

## F. Governance Posture

- [x] governance maturity gaps are explicitly recorded rather than assumed away
- [x] readiness and promotion records match the actual validation work performed
- [-] the candidate is recorded as `ready` or `ready-with-notes` for the correct reasons

Current read:

- governance posture is being recorded honestly
- package and installer ledger/promotion flows are real
- final release truth is still partial because installed-copy runtime truth is not fully closed

Primary references:

- [STATUS.md](c:/Nova/docs/STATUS.md)
- [BASE_PACKAGE_READINESS.md](c:/Nova/docs/BASE_PACKAGE_READINESS.md)
- [PHASE_COMPLETION_ASSESSMENT.md](c:/Nova/docs/PHASE_COMPLETION_ASSESSMENT.md)

## Phase-Blocking Items

Treat these as blocking for phase closeout:

- installed-copy failures that do not appear in workspace validation
- incorrect launcher/runtime-status truth in a packaged or installed copy
- stale duplicated logic that leaves HTTP and core behavior disagreeing
- package or installer readiness state that does not match the real validation evidence
- documentation that instructs operators to do something the shipped candidate does not actually support

## Important But Not Blocking By Default

Do not let these automatically hijack the phase unless they break the checklist above:

- deeper architecture purity work outside the known active seams
- broader memory, research, or preference feature expansion
- additional installer polish beyond validation truth
- future autonomy and maintenance enhancements

## Working Rule

When new work appears, classify it immediately:

- blocks this checklist
- important but can wait
- future work

If it does not block this checklist, it should not replace the main objective for this phase.