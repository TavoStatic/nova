# NYO System Base Package Readiness

Date: 2026-05-18
Last verified: 2026-05-18

## Purpose

This is the canonical checklist for deciding whether NYO System is ready to be treated as a base package candidate.

It is intentionally stricter than "the repo runs on my machine" and narrower than a full product release.

## Current Read

- release-clean candidate `2026.05.18.23` exists and is promoted `ready-with-notes`
- base runtime package validation passed from a same-machine extracted package
- Work Tree is complete with `0` open tasks for the current runtime governance tree
- not yet a final broadly deployable package until independent fresh-machine or VM validation is complete

## Current Gate Status

### Gate 1: Runtime Stability

Status: satisfied for the current candidate, must be re-verified for each release

Required:

- full regression green
- critical smoke path green
- no known blocking regressions in operator-console runtime flows

### Gate 2: Governance Stability

Status: enforced, still must be monitored before final release language

Current posture from `policy.json` and status docs:

- Safety Envelope is in `enforce`
- Kidney is in `enforce`
- packaging should not claim full governance maturity until enforced-mode behavior is monitored and the release posture is re-verified

### Gate 3: Packaging Boundary

Status: mostly satisfied

Required:

- shipped vs generated boundary matches [PACKAGING_MATRIX.md](PACKAGING_MATRIX.md)
- runtime-generated state stays out of base package payload
- operator-provided inputs stay explicit

### Gate 4: Operator Handoff

Status: improved and current for the `.23` release candidate, must be rerun per release candidate

Required:

- bootstrap path documented and executable
- handoff flow documented and current
- operations runbook aligned with actual launcher behavior

## Release-Candidate Checklist

The package is a release candidate only when all items below are true.

### Documentation

- `docs/README.md` only references documents that actually exist
- `docs/STATUS.md` reflects current runtime and package posture
- `docs/BOOTSTRAP.md` matches the real install flow
- `docs/HANDOFF.md` matches the real operator flow
- `docs/OPERATIONS.md` matches the real launcher commands

### Bootstrap

- `nova install` completes on a clean checkout
- `.venv` is created or reused correctly
- requirements install completes without manual archaeology
- `doctor --fix` completes after install
- `nova package-build` produces a reviewable zip artifact without local state folded into the payload

### Runtime Validation

- `nova doctor` passes
- `nova runtime-status` is readable and truthful
- `nova run` launches cleanly
- `nova webui-start --host 127.0.0.1 --port 8080` launches cleanly
- `/control` loads and reflects live control payloads

### Package Boundary

- no machine-local runtime state is being treated as shipped package content
- optional domain packs remain operator-provided inputs
- local previews, logs, and runtime archives remain outside the base package

### Verification

- `nova smoke-base --fix` passes
- `nova smoke --fix` passes when the runtime model backend is part of the target deployment
- `nova test` passes or has explicitly documented exclusions
- package validation has been run on a clean or near-clean environment
- the latest candidate reports `ready` or `ready-with-notes` from `nova package-readiness`

Latest packaging validation on `2026-05-18`:

- release-clean candidate `2026.05.18.23` reports `ready-with-notes`
- artifact: `runtime/exports/release_packages/nyo-system-base-rc-2026.05.18.23-proof-shape-closed-20260518_203219.zip`
- zip verification and extracted-package validation passed
- extracted package bootstrap succeeded from `runtime/validation/release/x-20260518203249-9bec6380/pkg`
- extracted `nova doctor`, `nova runtime-status`, `nova wiring-check --offline`, `nova smoke-base --fix`, and `nova test` passed
- temporary extracted web UI start/stop passed
- release validation result is `pass-with-notes` with no blocking issues

## Main Remaining Gaps

- packaging-boundary maintenance as the repo evolves
- independent fresh-machine or VM execution of the built zip artifact is still outstanding
- interactive `nova run` execution of the current artifact is still outstanding
- Git LFS must be installed/configured on release machines so Piper assets resolve from pointers cleanly
- cleaner runtime dependency isolation for broad validation
- keep regression and release-validation rerun discipline before promoting beyond release-candidate language

## Non-Goals For This Gate

This checklist does not require:

- a frozen executable build
- automatic installation of Ollama or SearXNG
- cross-platform parity
- full product-release packaging polish

Those belong to a later productization stage.
