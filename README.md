# NYO AI SYSTEMS

Nova is no longer best understood as a chatbot project.

It is becoming a supervised local AI runtime: a system that can route, inspect, remember, govern change, expose its own state, and carry maintenance pressure instead of waiting for an operator to do everything by hand.

That matters because most AI projects stop at response generation. Nova keeps moving after the reply. It can open work, track it, review it, repair drift, govern patches, surface its own internals, and keep the operator in the loop while still building toward real autonomy.

Project documentation is centralized under [docs/README.md](docs/README.md).

Public branding uses `NYO AI SYSTEMS`.
Internal runtime and module names may still reference `Nova`.

## Why This Repo Is Different

This repository is not centered on a single UI and it is not built around one narrow assistant persona.

At its core is Nova: a runtime that behaves more like an operator-facing AI system than a simple prompt-response wrapper. The browser control room is one window into that runtime. The CLI is another. The maintenance loop, patch system, Work Tree, supervisor flow, and runtime telemetry are all part of the same organism.

Nova is being shaped to do more than answer.
It is being shaped to:

- route requests through a supervisor-owned decision spine
- expose operator control through CLI flows, HTTP control surfaces, and runtime status views
- maintain scoped memory, structured telemetry, and inspectable runtime artifacts
- run operator-approved tools and web-backed research workflows
- generate, review, and apply change proposals under governed patch flow
- carry scheduled maintenance and self-repair loops instead of relying on ad hoc manual cleanup

## What Nova Has Become

Nova is now the runtime core inside NYO AI SYSTEMS.

That runtime already includes:

- supervised runtime ownership and recovery behavior
- Work Tree orchestration for governed branch and task execution
- patch preview, approval, apply, and rollback workflows
- subconscious session generation and training backlog paths
- a Safety Envelope for promotion and review governance
- a Kidney System for cleanup, retention, and artifact hygiene
- operator-observable control surfaces that expose live system state instead of hiding it

This is not “one assistant with some tools.”
It is a growing local AI operations system with an inspectable control plane.

## Why It’s Interesting

Nova sits in a strange and more ambitious space:

- not a pure research prototype
- not a polished consumer assistant
- not just an automation script pile

It is an attempt to build an AI runtime that can be watched, steered, corrected, and gradually trusted with more of its own upkeep.

If that works, the result is not just a better chat loop.
The result is a system that can participate in its own operation.

## Current Shape

Today, the repository should be read as:

- a runtime core
- a control and inspection surface
- a governed patch and maintenance system
- a growing body of service-owned behavior instead of one monolithic shell
- a platform base that can support external packs, policies, tools, and product layers

Domain-specific behavior should live in explicit packs, policies, tools, or higher-level product layers, not as hidden assumptions buried inside the base runtime.

## Start Here

- [docs/README.md](docs/README.md)
- [docs/OPERATIONS.md](docs/OPERATIONS.md)
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- [docs/SERVICES_INDEX.md](docs/SERVICES_INDEX.md)
- [docs/SUPERVISOR_CONTRACT.md](docs/SUPERVISOR_CONTRACT.md)
- [docs/STATUS.md](docs/STATUS.md)
- [docs/DOC_OWNERSHIP.md](docs/DOC_OWNERSHIP.md)
- [docs/PATCHING.md](docs/PATCHING.md)
- [docs/PACKAGE_PRODUCT_ROADMAP.md](docs/PACKAGE_PRODUCT_ROADMAP.md)

This root README is the short public entry point.
The deeper operational and architectural record lives under [docs/README.md](docs/README.md).
