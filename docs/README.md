# NYO System Documentation

This directory is the canonical documentation hub for NYO System.

## Platform Direction

Nova is becoming the runtime core of NYO System: an inspectable, operator-run local runtime with deterministic routing, scoped memory, tool execution, web research, operator-console operations, and governed patch flow.

It should be evaluated less like a chatbot and more like a supervised execution system with several interfaces.

It is not moving toward a single hard-coded vertical product. The public repo should stay generic by default, while domain-specific behavior is added explicitly through policy, tools, packs, or higher-level product layers.

Start here:

- [HANDOFF.md](HANDOFF.md): single operator flow for install, bootstrap, run, verify, inspect, patch, and rollback
- [BOOTSTRAP.md](BOOTSTRAP.md): fresh-machine bootstrap path for the current base package
- [OPERATIONS.md](OPERATIONS.md): how to run, test, and operate NYO System
- [ARCHITECTURE.md](ARCHITECTURE.md): component map and request flow
- [SUPERVISOR_CONTRACT.md](SUPERVISOR_CONTRACT.md): deterministic behavior ownership contract
- [QUALITY_BAR.md](QUALITY_BAR.md): hard acceptance bar for cleanup, routing, refactors, and patch work
- [STATUS.md](STATUS.md): current project state and resume guidance
- [BASE_PACKAGE_READINESS.md](BASE_PACKAGE_READINESS.md): package-candidate checklist and current readiness score
- [PACKAGING_MATRIX.md](PACKAGING_MATRIX.md): canonical shipped-vs-local boundary for the base package
- [PATCHING.md](PATCHING.md): patch safety, teach proposals, and review flow
- [SELF_FIX_READINESS.md](SELF_FIX_READINESS.md): bounded self-fix readiness checklist and current gate status
- [SEARXNG_SETUP.md](SEARXNG_SETUP.md): self-hosted search provider setup
- [CLEANUP_AUDIT.md](CLEANUP_AUDIT.md): cleanup findings and recommended next removals
- [TOOLS.md](TOOLS.md): current documented tool surface
- [TOOLING_ROADMAP.md](TOOLING_ROADMAP.md): planned tooling expansion

Root-level legacy docs are retained as compatibility pointers, but new updates should go here.