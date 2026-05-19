# Documentation Ownership

Last verified: 2026-05-18

Use this page when deciding where a change should be documented.

## Current State

- `STATUS.md`: current project posture, latest validation read, remaining debt, and resume guidance.
- `BASE_PACKAGE_READINESS.md`: release-candidate gates and what must be true before package promotion language is safe.
- `PHASE_CLOSEOUT_CHECKLIST.md`: phase-level closeout checklist and unresolved operator handoff items.
- `HANDOFF.md`: practical install, run, verify, inspect, patch, and stop flow.

## Architecture And Runtime Ownership

- `ARCHITECTURE.md`: system shape, decision spine, routing map, OS capability chain, operator-outbox shape, and major component boundaries.
- `SERVICES_INDEX.md`: services-by-domain map for the extracted service layer.
- `SUPERVISOR_CONTRACT.md`: deterministic ownership, supervisor routing, and no-trigger-word routing principles.
- `SEARCH_PROVIDER_ARCHITECTURE.md`: web/search provider roles and routing expectations.
- `DATA_PIPELINES.md`: governed data-lane structure, operator controls, and SIS test lane posture.

## Packaging And Install

- `BOOTSTRAP.md`: source-bootstrap install path.
- `DEPENDENCY_CONTRACT.md`: required, bundled, optional, and operator-provided dependencies.
- `PACKAGING_MATRIX.md`: shipped-vs-generated package boundary and root artifact policy.
- `RELEASE_ARTIFACT.md`: release package format, build flow, and promotion record.
- `FRESH_MACHINE_VALIDATION.md`: independent clean-machine or VM validation checklist.
- `WINDOWS_INSTALLER_PLAN.md`: Windows installer direction and pending installer validation work.

## Governance And Change

- `PHASE2_SAFETY_ENVELOPE.md`: generated-session promotion and review governance.
- `KIDNEY_SYSTEM.md`: cleanup, retention, and runtime hygiene governance.
- `PATCHING.md`: governed patch proposal, preview, apply, and rollback flow.
- `REAL_WORLD_TASKS.md`: operator-grade validation tasks.

## Historical Context

`C:\Nova\This_is_nova` is append-only build history and a cross-system context guide. Consult it for chronology and project memory, but do not treat it as the current authority over policy, package readiness, runtime truth, or tests.
