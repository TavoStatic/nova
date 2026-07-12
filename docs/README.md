# NYO AI SYSTEMS Documentation

This directory separates current code truth, live runtime truth, operating instructions, and historical plans.

## Current Code Authority

- [CODE_TRUTH_AUDIT_2026-07-12.md](CODE_TRUTH_AUDIT_2026-07-12.md): full scan scope, documentation drift, and unresolved code findings
- [SYSTEM_MAP.md](SYSTEM_MAP.md): current processes, feedback loops, ownership, APIs, and wiring surfaces
- [ARCHITECTURE.md](ARCHITECTURE.md): architectural intent, current boundaries, heavy hitters, and layer-ingestion rules
- [AUTONOMY_AND_MISSION.md](AUTONOMY_AND_MISSION.md): Mission, orchestrator, execution, Work Tree, and outbox contracts
- [SERVICES_INDEX.md](SERVICES_INDEX.md): exhaustive current service-module inventory
- [FUNCTION_INDEX.md](FUNCTION_INDEX.md): exhaustive active source function/class inventory
- [TEST_ECOSYSTEM.md](TEST_ECOSYSTEM.md): test truth model and ownership
- [TEST_INDEX.md](TEST_INDEX.md): every discovered test function and declared lane membership
- [STATUS.md](STATUS.md): documentation baseline and where to read live truth

## Current Subsystems

- [KIDNEY_SYSTEM.md](KIDNEY_SYSTEM.md): cleanup, retention, retirement, and storage pressure
- [SOCK_SYSTEM.md](SOCK_SYSTEM.md): hardware/model compatibility and policy recommendations
- [DATA_PIPELINES.md](DATA_PIPELINES.md): pipeline framework, Ed-Fi core, and BISD lane
- [SEARCH_PROVIDER_ARCHITECTURE.md](SEARCH_PROVIDER_ARCHITECTURE.md): web/research provider roles
- [PATCHING.md](PATCHING.md): patch proposal and apply/rollback governance
- [MEMORY_SYSTEM_PLAN.md](MEMORY_SYSTEM_PLAN.md): memory design and implementation history; verify current behavior against the code indexes
- [NOVA_SERVER_SIDE.md](NOVA_SERVER_SIDE.md): optional server-side/front-door infrastructure

## Operations And Release

- [OPERATIONS.md](OPERATIONS.md)
- [BOOTSTRAP.md](BOOTSTRAP.md)
- [DEPENDENCY_CONTRACT.md](DEPENDENCY_CONTRACT.md)
- [PACKAGING_MATRIX.md](PACKAGING_MATRIX.md)
- [RELEASE_ARTIFACT.md](RELEASE_ARTIFACT.md)
- [FRESH_MACHINE_VALIDATION.md](FRESH_MACHINE_VALIDATION.md)
- [WINDOWS_INSTALLER_PLAN.md](WINDOWS_INSTALLER_PLAN.md)
- [PRIVILEGED_PIPELINE_PROTOCOL.md](PRIVILEGED_PIPELINE_PROTOCOL.md)

## Plans And Historical Records

The following documents are useful planning or historical context, but they are not present-tense code authority:

- `LEAH_INSTANCE_PROMOTION_PLAN.md`
- `PACKAGE_PRODUCT_ROADMAP.md`
- `PHASE2_SAFETY_ENVELOPE.md`
- `PHASE_CLOSEOUT_CHECKLIST.md`
- `PHASE_COMPLETION_ASSESSMENT.md`
- `BASE_PACKAGE_READINESS.md`
- `HANDOFF.md`
- `REAL_WORLD_TASKS.md`
- dated root scans and health reviews

## Working Rule

When documentation disagrees with code, inspect the owning code path. When documentation or code disagrees with live state, inspect the current runtime artifact and its freshness. Do not convert an old status sentence into a current health claim.
