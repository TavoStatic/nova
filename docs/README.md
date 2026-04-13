# NYO AI SYSTEMS Documentation

This directory is the canonical documentation hub for NYO AI SYSTEMS.

## Platform Direction

Nova is becoming the runtime core of NYO AI SYSTEMS: an inspectable, operator-run local runtime with deterministic routing, scoped memory, tool execution, web research, operator-console operations, and governed patch flow.

It should be evaluated less like a chatbot and more like a supervised execution system with several interfaces.

It is not moving toward a single hard-coded vertical product. The public repo should stay generic by default, while domain-specific behavior is added explicitly through policy, tools, packs, or higher-level product layers.

Start here:

- [HANDOFF.md](HANDOFF.md): single operator flow for install, bootstrap, run, verify, inspect, patch, and rollback
- [BOOTSTRAP.md](BOOTSTRAP.md): fresh-machine bootstrap path for the current base package
- [OPERATIONS.md](OPERATIONS.md): how to run, test, and operate NYO AI SYSTEMS
- [ARCHITECTURE.md](ARCHITECTURE.md): component map and request flow
- [SEARCH_PROVIDER_ARCHITECTURE.md](SEARCH_PROVIDER_ARCHITECTURE.md): target provider stack, routing roles, fallback policy, and command-center governance for web, knowledge, and code search
- [SUPERVISOR_CONTRACT.md](SUPERVISOR_CONTRACT.md): deterministic behavior ownership contract
- [STATUS.md](STATUS.md): current project state and resume guidance
- [PHASE_COMPLETION_ASSESSMENT.md](PHASE_COMPLETION_ASSESSMENT.md): step-back assessment of what is done, what is blocking completion, and what should be deferred
- [PHASE_CLOSEOUT_CHECKLIST.md](PHASE_CLOSEOUT_CHECKLIST.md): master top-level checklist for deciding whether the current phase is actually complete
- [BASE_PACKAGE_READINESS.md](BASE_PACKAGE_READINESS.md): package-candidate checklist and current readiness score
- [PACKAGING_MATRIX.md](PACKAGING_MATRIX.md): canonical shipped-vs-local boundary for the base package
- [DEPENDENCY_CONTRACT.md](DEPENDENCY_CONTRACT.md): required vs optional runtime dependencies and command-level expectations
- [FRESH_MACHINE_VALIDATION.md](FRESH_MACHINE_VALIDATION.md): release-candidate checklist for validating a built artifact on a clean machine
- [REAL_WORLD_TASKS.md](REAL_WORLD_TASKS.md): how to define and run realistic operator-grade task sessions instead of only seam regressions
- [RELEASE_ARTIFACT.md](RELEASE_ARTIFACT.md): canonical base-package artifact format and build flow
- [WINDOWS_INSTALLER_PLAN.md](WINDOWS_INSTALLER_PLAN.md): concrete plan for a Windows executable installer layered on top of the current package flow
- `nova installer-build`: build the Windows installer executable from a verified package zip when Inno Setup is available
- [RC_VALIDATION_TEMPLATE.md](RC_VALIDATION_TEMPLATE.md): result template for recording release-candidate validation runs
- release ledger: `runtime/exports/release_packages/release_ledger.jsonl`
- validation record seeds: `runtime/exports/release_packages/validation_records/`
- [PATCHING.md](PATCHING.md): patch safety, teach proposals, and review flow
- [PACKAGE_PRODUCT_ROADMAP.md](PACKAGE_PRODUCT_ROADMAP.md): release-gate roadmap from runtime to package product
- [PHASE2_SAFETY_ENVELOPE.md](PHASE2_SAFETY_ENVELOPE.md): Phase 2 promotion and review governance
- [KIDNEY_SYSTEM.md](KIDNEY_SYSTEM.md): cleanup and retention governance

Root-level legacy docs are retained as compatibility pointers, but new updates should go here.