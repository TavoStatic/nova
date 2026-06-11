# NYO AI SYSTEMS

Nova is a supervised local AI runtime platform.

It is past foundation stage and currently in late-stage proving: core systems are implemented and operating, and remaining gaps are now concentrated in autonomous closure quality and independent packaging proof.

Public branding uses `NYO AI SYSTEMS`. Internal runtime and module names may still reference `Nova`.

## What Nova Is

Nova is designed as a governed local runtime with:

- a single decision spine for routing and execution selection
- CLI and HTTP front doors (`run.py`, `nova_http.py`)
- operator control room (`/control`) and Leah assistant surface (`/leah`)
- Work Tree pressure and branch state as the core work model
- bounded tool execution and OS capability contracts
- runtime evidence, release validation, and promotion ledgers

It is not a "black box chatbot". The intent is operator-visible, evidence-backed behavior with explicit governance boundaries.

## What Nova Can Do Today

Implemented and active capabilities include:

- chat runtime: CLI and web chat front doors
- control surfaces: runtime health, sessions, policies, work trees, pipelines, test sessions
- maintenance orchestration: guard, autonomy orchestrator, work-tree signal ingestion
- temporal pressure feed: ICS ingestion, scoring, surfaced pressure, `nova time` review
- tools and capabilities: registered tools, bounded PowerShell capability registry, evidence ledgers
- memory and identity: scoped memory, memory health, identity bootstrap and learning surfaces
- patch governance: preview, approve, apply, rollback, and patch readiness tracking
- release lifecycle: package build, verify, validate, readiness, promote; installer lifecycle equivalents
- regression governance: lane registration (unit/behavior/integration), profile drift/gap detection

## Current Stage

Current posture is late-stage proving with strong operational health.

As of the latest status record:

- self-check: 22/22 passing
- health score: 100
- temporal feed: active
- release artifact validation: passing in current lane

Remaining proof work is specific, not foundational:

- sustained autonomous self-closure from signal to action to evidence without operator babysitting
- independent fresh-machine/VM validation of package install and operation
- continued intent quality under ordinary conversation
- non-trivial autonomous maintenance throughput under local model constraints

## How To Trust Claims In This Repo

Use this truth hierarchy:

1. runtime artifacts and ledgers
2. release/readiness gates
3. source code
4. docs summaries

Authoritative runtime records:

- [docs/STATUS.md](docs/STATUS.md)
- `runtime/regression_status.json`
- `runtime/validation/release/latest_release_validation.json`
- `runtime/exports/release_packages/release_ledger.jsonl`

If README text conflicts with those artifacts, artifacts win.

## Quick Start

From repo root:

```powershell
.\nova.cmd install
.\nova.cmd doctor
.\nova.cmd run
.\nova.cmd webui-start --host 127.0.0.1 --port 8080
```

Then open:

- Operator control room: `http://127.0.0.1:8080/control`
- Leah assistant: `http://127.0.0.1:8080/leah`

## Read Next

- [docs/README.md](docs/README.md)
- [docs/STATUS.md](docs/STATUS.md)
- [docs/OPERATIONS.md](docs/OPERATIONS.md)
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- [docs/SERVICES_INDEX.md](docs/SERVICES_INDEX.md)
- [docs/SUPERVISOR_CONTRACT.md](docs/SUPERVISOR_CONTRACT.md)
- [docs/DOC_OWNERSHIP.md](docs/DOC_OWNERSHIP.md)
- [docs/PATCHING.md](docs/PATCHING.md)

This root README is the high-level entry point. The detailed operating record lives under [docs/README.md](docs/README.md).
