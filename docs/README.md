# NYO AI SYSTEMS Documentation

This directory is the public documentation hub for NYO AI SYSTEMS.

Nova should be read here as a supervised local AI runtime with an operator control plane, governed tool use, patch flow, inspectable state, and self-repair loops. The public repo stays generic on purpose. Domain packs, local operator notes, and dated internal audit trails do not define the platform.

## Start Here

- [ARCHITECTURE.md](ARCHITECTURE.md): runtime shape, component map, and request flow
- [SERVICES_INDEX.md](SERVICES_INDEX.md): services-by-domain map for the extracted service layer
- [OPERATIONS.md](OPERATIONS.md): how to run, test, and operate the system
- [SUPERVISOR_CONTRACT.md](SUPERVISOR_CONTRACT.md): deterministic ownership and routing contract
- [PATCHING.md](PATCHING.md): governed change proposal, review, apply, and rollback flow
- [STATUS.md](STATUS.md): current project posture and resume guidance
- [DOC_OWNERSHIP.md](DOC_OWNERSHIP.md): where each kind of documentation update belongs
- [SEARCH_PROVIDER_ARCHITECTURE.md](SEARCH_PROVIDER_ARCHITECTURE.md): search/research routing and provider roles

## Build And Package

- [BOOTSTRAP.md](BOOTSTRAP.md): fresh-machine bootstrap path
- [DEPENDENCY_CONTRACT.md](DEPENDENCY_CONTRACT.md): required vs optional runtime dependencies
- [PACKAGING_MATRIX.md](PACKAGING_MATRIX.md): shipped-vs-local boundary for the base package
- [RELEASE_ARTIFACT.md](RELEASE_ARTIFACT.md): release artifact format and build flow
- [WINDOWS_INSTALLER_PLAN.md](WINDOWS_INSTALLER_PLAN.md): installer direction for Windows packaging
- [PACKAGE_PRODUCT_ROADMAP.md](PACKAGE_PRODUCT_ROADMAP.md): path from runtime to package product
- [DATA_PIPELINES.md](DATA_PIPELINES.md): governed data-lane structure and SIS test lane posture

## Governance And Runtime Health

- [PHASE2_SAFETY_ENVELOPE.md](PHASE2_SAFETY_ENVELOPE.md): promotion and review governance
- [KIDNEY_SYSTEM.md](KIDNEY_SYSTEM.md): cleanup, retention, and runtime hygiene
- [REAL_WORLD_TASKS.md](REAL_WORLD_TASKS.md): realistic operator-grade validation tasks

Internal notes, local packs, and historical audit artifacts are intentionally kept out of this public docs index so the repo reads like a platform, not an internal handoff bundle.
