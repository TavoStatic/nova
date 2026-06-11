# Documentation Ownership

Last verified: 2026-06-11

Use this page when deciding where a change should be documented.

## Current State

- `STATUS.md`: current project posture, latest validation read, remaining debt, and resume guidance.
- `BASE_PACKAGE_READINESS.md`: release-candidate gates and what must be true before package promotion language is safe.
- `PHASE_CLOSEOUT_CHECKLIST.md`: phase-level closeout checklist and unresolved operator handoff items.
- `HANDOFF.md`: practical install, run, verify, inspect, patch, and stop flow.

## Architecture And Runtime Ownership

- `ARCHITECTURE.md`: system shape, decision spine, routing map, OS capability chain, operator-outbox shape, major component boundaries, Leah frontend, temporal stack, autonomy orchestrator, regression governance, and wiring inventory.
- `SERVICES_INDEX.md`: services-by-domain map for the extracted service layer. **Update this file whenever a new `services/*.py` file is added.**
- `SUPERVISOR_CONTRACT.md`: deterministic ownership, supervisor routing, and no-trigger-word routing principles.
- `SEARCH_PROVIDER_ARCHITECTURE.md`: web/search provider roles and routing expectations. Whoogle and Brave are not active; do not add them as current providers without a code change.
- `DATA_PIPELINES.md`: governed data-lane structure, operator controls, and SIS test lane posture.

## New Surfaces

These surfaces were added after the initial doc pass and require ongoing maintenance:

- **Leah frontend** (`services/leah_frontdoor.py`, `/leah` route, `static/leah.*`): owned by `ARCHITECTURE.md` and `SERVICES_INDEX.md`.
- **Temporal stack** (`services/nova_temporal_service.py`, `services/nova_calendar_ingestion.py`, `services/nova_scheduler.py`, `tools/temporal_review_tool.py`, `scripts/run_time.py`): owned by `ARCHITECTURE.md`, `SERVICES_INDEX.md`, and `OPERATIONS.md`.
- **Autonomy orchestrator** (`services/autonomy_orchestrator.py`, `services/autonomy_execution_gate.py`, `services/autonomy_orchestrator_ledger.py`): owned by `ARCHITECTURE.md` and `SERVICES_INDEX.md`.
- **Regression governance** (`services/regression_lanes.py`, `services/regression_profile_inventory.py`, `services/validation_artifact_truth.py`): owned by `SERVICES_INDEX.md`.
- **Wiring inventory** (`services/nova_wiring_inventory.py`, `services/nova_root_inventory.py`): owned by `ARCHITECTURE.md` and `SERVICES_INDEX.md`.

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
