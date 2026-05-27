# NYO AI SYSTEMS

Nova is not a finished autonomous system.

It is an actively evolving supervised local AI runtime. The repository contains a CLI, HTTP runtime console, control surfaces, Work Tree, patch and release flows, memory services, tool dispatch, OS capability contracts, operator outbox, runtime telemetry, and maintenance loops. Those pieces are real, but they are not all closed end to end yet.

The current proof standard is simple:

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
- Work Tree task and branch state
- runtime health and process telemetry
- memory and identity services
- web, weather, voice, vision, and tool surfaces
- patch preview, approval, apply, and rollback paths
- OS capability registry and script controller for bounded local actions
- operator outbox for durable notices when Nova lacks authority, tools, or information
- release package build, verify, validation, and promotion records

Those systems are meant to work together, but the current repo should still be treated as a supervised runtime under active development. Nova can surface evidence, hold work, run bounded tools, validate packages, and expose its state. It should not be described as independently self-completing until the runtime evidence proves that.

## What Is Still Being Proven

The main unfinished proof areas are:

- chat intent quality under ordinary conversation, especially avoiding forced help/task flows
- end-to-end self-closure from signal to Work Tree to tool/action to evidence to judgment
- autonomous maintenance that advances real work instead of only repeating validation loops
- fresh-machine or VM package validation
- interactive `nova run` validation against release artifacts
- production packaging decisions for large local assets and optional runtime dependencies

## How To Read This Repo

Read the repo as a platform base, not a polished assistant product.

Important current authorities:

- [docs/STATUS.md](docs/STATUS.md): resume point and current source/readiness posture
- `runtime/regression_status.json`: latest full regression evidence
- `runtime/validation/release/latest_release_validation.json`: latest observed release validation
- `runtime/exports/release_packages/release_ledger.jsonl`: package build, verify, and promotion history
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): architecture map
- [docs/SERVICES_INDEX.md](docs/SERVICES_INDEX.md): service ownership map

If this README disagrees with those artifacts, the artifacts win.

## Current Direction

The direction is to make Nova more capable of maintaining continuity, surfacing its own blockers, requesting missing capability or operator input, and carrying work through evidence-backed loops.

That is a direction, not a claim of completion.

The design goal is a local AI runtime that can be watched, steered, corrected, and gradually given more operational responsibility as evidence supports it. Until then, Nova remains a supervised system with explicit gates, ledgers, and operator-visible state.

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
