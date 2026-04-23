# NYO AI SYSTEMS

Project documentation is now centralized under [docs/README.md](docs/README.md).

Public branding uses NYO AI SYSTEMS.
Internal runtime and module names may still reference Nova.

## What Nova Has Become

Nova is now the core runtime inside NYO AI SYSTEMS: a supervised local operations system with deterministic routing, operator control surfaces, patch governance, and self-maintenance loops.

This repository is no longer best understood as a simple chat assistant project. It now centers on a runtime that can:

- route requests through a supervisor-owned decision spine
- expose operator control through CLI flows, HTTP control surfaces, and runtime status views
- maintain scoped memory, structured telemetry, and inspectable runtime artifacts
- run operator-approved tools and web-backed research workflows
- generate, review, and apply change proposals under patch governance
- perform scheduled maintenance and improvement loops instead of relying on ad hoc manual intervention

## Current Shape

The current Nova runtime includes:

- supervised runtime ownership and recovery behavior
- patch preview, approval, apply, and rollback workflows
- subconscious/session generation and training backlog paths
- a Phase 2 Safety Envelope for promotion and review governance
- a Kidney System for cleanup, retention, and artifact hygiene
- package-readiness and productization documentation for moving from project state to releasable system state

The browser control room is one interface into the runtime. It is not the entire product.

Domain-specific behavior should live in external packs, policies, tools, or product layers rather than as hidden assumptions inside the base repository.

## Start Here

- [docs/README.md](docs/README.md)
- [docs/OPERATIONS.md](docs/OPERATIONS.md)
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- [docs/SUPERVISOR_CONTRACT.md](docs/SUPERVISOR_CONTRACT.md)
- [docs/STATUS.md](docs/STATUS.md)
- [docs/PATCHING.md](docs/PATCHING.md)
- [docs/PACKAGE_PRODUCT_ROADMAP.md](docs/PACKAGE_PRODUCT_ROADMAP.md)

This root README is the short public entry point. The detailed operational and architectural record lives under [docs/README.md](docs/README.md).
