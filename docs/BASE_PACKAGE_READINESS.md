# NYO System Base Package Readiness

Date: 2026-03-30
Last verified: 2026-05-06

## Purpose

This is the canonical checklist for deciding whether NYO System is ready to be treated as a base package candidate.

It is intentionally stricter than "the repo runs on my machine" and narrower than a full product release.

## Current Read

- release-clean candidate exists and is promoted `ready-with-notes`
- base runtime package validation passed from a same-machine short-path extract
- not yet a final broadly deployable package until independent fresh-machine or VM validation is complete

## Current Gate Status

### Gate 1: Runtime Stability

Status: mostly satisfied, must be re-verified at release time

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

Status: improved and near-clean validation completed, must be rerun per release candidate

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

Latest packaging validation on `2026-05-06`:

- release-clean candidate `2026.05.06.2` reports `ready-with-notes`
- zip verification and extracted-package verification passed
- extracted package bootstrap succeeded from short path `C:\N\r62_082924`
- extracted `nova doctor`, `nova runtime-status`, `nova smoke-base --fix`, and `nova test` passed

## Main Remaining Gaps

- packaging-boundary maintenance as the repo evolves
- independent fresh-machine or VM execution of the built zip artifact is still outstanding
- cleaner runtime dependency isolation for broad validation
- keep both compact and full-discovery validation rerun discipline before promoting beyond release-candidate language

## Non-Goals For This Gate

This checklist does not require:

- a frozen executable build
- automatic installation of Ollama or SearXNG
- cross-platform parity
- full product-release packaging polish

Those belong to a later productization stage.
