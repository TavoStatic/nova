# NYO AI SYSTEMS

Nova is a supervised local AI runtime in late-stage active development.

It is not a finished autonomous system, but it is no longer early-stage. The core systems — CLI, HTTP runtime console, Work Tree, patch and release flows, memory services, tool dispatch, OS capability contracts, operator outbox, autonomy orchestration, and hardware-aware model selection — are implemented, tested, and governed by a passing regression gate. The gaps that remain are specific and known, not scattered across the foundation.

The proof standard has not changed:

- source describes capability
- runtime artifacts show what actually happened
- release gates decide whether a package is promotable
- documentation must not describe a target state as if it is already complete

Project documentation is centralized under [docs/README.md](docs/README.md).

Public branding uses `NYO AI SYSTEMS`.
Internal runtime and module names may still reference `Nova`.

## What Runs Today

Nova currently has:

- CLI and HTTP chat front doors
- operator console and status surfaces
- Work Tree task and branch state with signal ingestion across 30+ wiring surfaces
- runtime health and process telemetry
- memory and identity services
- web, weather, voice, vision, and tool surfaces
- patch preview, approval, apply, and rollback paths
- OS capability registry and script controller for bounded local actions
- operator outbox for durable notices when Nova lacks authority, tools, or information
- release package build, verify, validation, and promotion records
- SOCK — System Optimization and Compatibility Check — hardware-aware model pair selection with VRAM stability enforcement and concurrent warm validation
- autonomy orchestrator with a single clean contract path, full decision surface test coverage, and governed canary execution
- a compact regression gate that covers all of the above and refreshes on every full run

Those systems are meant to work together, and most of them do. Nova surfaces evidence, holds work, runs bounded tools, validates packages, governs its own model selection, and exposes its state. The regression gate is green.

## What Is Still Being Proven

The main unfinished proof areas are:

- end-to-end autonomous self-closure from signal to Work Tree to action to evidence — the machinery exists; sustained runtime demonstration without operator babysitting is what remains
- chat intent quality under ordinary conversation, especially avoiding forced help/task flows
- fresh-machine or VM package validation — same-machine extracted-package validation passes, but independent install on a clean machine has not been run
- autonomous maintenance advancing real non-trivial work — current local model capability limits what the autonomy loop can drive independently

## How To Read This Repo

Read the repo as a governed platform base that is approaching but has not yet reached independent operational capability.

Important current authorities:

- [docs/STATUS.md](docs/STATUS.md): resume point and current source/readiness posture
- `runtime/regression_status.json`: latest full regression evidence
- `runtime/validation/release/latest_release_validation.json`: latest observed release validation
- `runtime/exports/release_packages/release_ledger.jsonl`: package build, verify, and promotion history
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): architecture map
- [docs/SERVICES_INDEX.md](docs/SERVICES_INDEX.md): service ownership map

If this README disagrees with those artifacts, the artifacts win.

## Current Direction

The direction is to close the remaining proof gaps — autonomous closure demonstrated by runtime evidence, fresh-machine validation, and model capability sufficient to drive the autonomy loop on non-trivial work.

The design goal is a local AI runtime that can be watched, steered, corrected, and gradually given more operational responsibility as evidence supports it. The foundation for that is in place. What remains is proving it runs.

## Start Here

- [docs/README.md](docs/README.md)
- [docs/STATUS.md](docs/STATUS.md)
- [docs/OPERATIONS.md](docs/OPERATIONS.md)
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- [docs/SERVICES_INDEX.md](docs/SERVICES_INDEX.md)
- [docs/SUPERVISOR_CONTRACT.md](docs/SUPERVISOR_CONTRACT.md)
- [docs/DOC_OWNERSHIP.md](docs/DOC_OWNERSHIP.md)
- [docs/PATCHING.md](docs/PATCHING.md)
- [docs/PACKAGE_PRODUCT_ROADMAP.md](docs/PACKAGE_PRODUCT_ROADMAP.md)

This root README is the short public entry point. The deeper operational and architectural record lives under [docs/README.md](docs/README.md).
