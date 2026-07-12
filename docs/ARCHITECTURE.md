# Nova Architecture

Last verified from code: 2026-07-12

For the exhaustive process and subsystem map, read `SYSTEM_MAP.md`. For every source function and service, read `FUNCTION_INDEX.md` and `SERVICES_INDEX.md`.

## Architectural Intent

Nova is a local AI runtime organized around evidence-bearing feedback loops:

- understand intent before choosing a route
- keep execution distributed across specialized owners
- keep mutation governed and reversible
- make pressure, evidence, decisions, and outcomes inspectable
- let runtime owners publish truth and let composition layers repeat it
- route unresolved work into Work Tree instead of laundering it into health
- keep core and HTTP as adapters and coordinators, not permanent homes for every new layer

This section states intent. The current implementation still contains heavy files and mixed ownership described below.

## Current Boundaries

### Front Doors

- `nova.cmd` and `nova.ps1`: command and lifecycle front door
- `nova_core.py`: direct local core/voice/CLI runtime
- `nova_http.py`: separate HTTP/control/Leah runtime on port 8080
- `nova_guard.py`: core process supervisor and one-shot maintenance launcher
- `autonomy_maintenance.py`: feedback-cycle coordinator and optional detached loop worker

These are separate process and ownership boundaries. Core does not contain the HTTP server.

### Conversation Spine

The conversation path uses intent evidence, planner contracts, route probing, fulfillment viability, tool policy, reply context, and finalization services.

The target shape is one decision spine with distributed execution. The current Supervisor seam has no populated default rule specs or explicit ownership sets, so the active routing spine is primarily planner/service driven.

### Feedback Spine

Runtime owners publish evidence. Signal Intake converts actionable pressure into Work Tree. Work Tree owns durable task/evidence state. Mission composes the cycle verdict. The orchestrator selects an action. The execution gate checks policy. The dispatcher and Work Tree execute bounded actions.

Mission is currently more than a passive verdict because it also applies hold contracts and narrow execution exceptions. See `AUTONOMY_AND_MISSION.md`.

### Status Spine

Status is composed from owner services and projected through two HTTP boundaries:

- thin surfaces: `/api/control/status/surfaces`
- full status: `/api/control/status`

Targeted endpoints hydrate Work Trees, pipelines, sessions, tests, policy, and metrics. The control panel is a consumer of those surfaces, not the owner of their truth.

### Tool Spine

Tools have registry metadata, policy checks, execution events, and bounded context. OS capabilities add hash, version, argument, authority, and evidence contracts. Work Tree adds tree/branch/task tool declarations before autonomous execution.

### Mutation Spine

Mutation paths are split by owner:

- patch previews and apply/rollback
- generated code and patch bridge
- policy mutation
- memory writes and retention
- data-lane control
- release and installer build/promotion

Passing one mutation gate does not imply release readiness.

## Major Ownership Domains

| Domain | Primary owners |
|---|---|
| Runtime lifecycle | guard, runtime control/process state/heartbeat/restart provenance |
| HTTP and control | HTTP route/transport services, control status/actions/auth/assets |
| Conversation | intent, planner, routing, fulfillment, reply, finalization, action ledger |
| Memory and identity | memory adapter/routing/learning/health/bootstrap/retention |
| Tools | direct registry, tool execution, tool policy, OS capability registry/controller |
| Work and autonomy | Work Tree, Signal Intake, pressure snapshot, Mission, orchestrator, gate |
| Reflection and maintenance | subconscious, Kidney, core steward, core health, core thinning |
| Change governance | safety envelope, patch, codegen, layer maturity, release, installer |
| Data | pipeline framework, privileged protocol, Ed-Fi core, BISD lane |
| Validation | regression lanes, profile inventory, test sessions, validation artifact truth |
| Host adaptation | SOCK, Ollama health, port ownership, voice, vision, TTS |

## Core And HTTP Thinning

`nova_core.py` and `nova_http.py` retain compatibility wrappers because tests and front doors patch them directly. New layers should still place ownership in services and leave wrappers thin.

Core thinning is represented as an owner service and a Work Tree feed. Its current analysis targets both core and HTTP. Mission receives the owner verdict; it should not recreate the size analysis.

Thinning is not task deletion. A safe extraction must preserve:

- public wrapper names used by tests and callers
- runtime dependency injection
- action and evidence semantics
- status keys and wiring inventory
- failure behavior
- source-root classification

## Ingesting New Layers

A new layer is complete only when its ownership path is explicit:

1. owner module and contract
2. policy and runtime configuration
3. status/evidence output
4. Signal Intake behavior, if it creates pressure
5. Work Tree tools/tasks, if Nova can act on it
6. orchestrator and execution policy, if autonomous action is allowed
7. operator/control surface
8. test-profile ownership
9. source-root and wiring inventory
10. documentation ownership

Do not add a second truth calculator merely to make a new layer visible.

## Current Heavy Hitters

At this code baseline:

- `services/work_tree_signal_ingestion.py`: 6,929 lines
- `autonomy_maintenance.py`: 6,250 lines
- `nova_core.py`: 3,798 lines
- `work_tree.py`: 2,643 lines
- `nova_http.py`: 1,878 lines
- `services/control_status.py`: 1,601 lines
- `services/nova_patching.py`: 1,582 lines
- `services/autonomy_orchestrator.py`: 1,550 lines
- `services/operator_outbox.py`: 1,382 lines
- `services/nova_wiring_inventory.py`: 1,239 lines

Line count is pressure evidence, not proof that extraction is safe or necessary. Function ownership and call contracts decide the work.

## Truth Boundaries

- process truth belongs to runtime process owners
- task truth belongs to Work Tree
- tool outcome truth belongs to execution/evidence owners
- regression truth belongs to the regression artifact and profile inventory
- release truth belongs to build identity, validation, and release ledger owners
- data truth belongs to pipeline and Ed-Fi owners
- Mission composes; it does not replace those owners
- the control UI renders; it does not define those owners

## Current Gaps That Architecture Documentation Must Carry

- mixed legacy and orchestrator execution
- Mission-owned execution exceptions and ambient suppression
- broad outbox source suppression
- failed tool tasks completed by maintenance
- bounded active-work target discovery
- empty Supervisor default ownership
- duplicate Ed-Fi source-root IDs

These are not design goals. They are current implementation facts requiring owner-level investigation.
