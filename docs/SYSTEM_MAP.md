# Nova System Map

Code baseline: `92ca149e452e96dfd0d9224eb2d11a0862c3ccea`

Last verified from code: 2026-07-12

This map describes the system that exists in source. It does not publish a live health verdict. Use runtime artifacts for current process, Work Tree, validation, regression, and release state.

## Reading Order

- `CODE_TRUTH_AUDIT_2026-07-12.md`: scan scope, documentation drift, and known mismatches
- `AUTONOMY_AND_MISSION.md`: maintenance, Mission, orchestrator, execution, and feedback contracts
- `SERVICES_INDEX.md`: every service module and its public surface
- `FUNCTION_INDEX.md`: every active source function, method, and class
- `TEST_ECOSYSTEM.md` and `TEST_INDEX.md`: test lanes and every discovered test

## System Shape

Nova is a local Windows AI runtime with several cooperating front doors and background loops.

```text
Operator / user / scheduler
        |
        +-- nova.cmd -> nova.ps1 command front door
        |      |-- direct core
        |      |-- guard
        |      |-- web UI
        |      |-- tools and tests
        |      `-- package, installer, SOCK, and wiring operations
        |
        +-- nova_http.py :8080
        |      |-- Control Room
        |      |-- Leah
        |      |-- chat and upload APIs
        |      `-- control/status/action APIs
        |
        +-- nova_guard.py
        |      |-- supervises nova_core.py
        |      `-- launches one-shot maintenance cycles
        |
        +-- autonomy_maintenance.py
        |      |-- subconscious
        |      |-- Kidney
        |      |-- queues and Work Tree
        |      |-- Signal Intake
        |      |-- Mission and orchestrator
        |      `-- regression and cycle evidence
        |
        `-- external/local dependencies
               |-- Ollama
               |-- SearXNG and selected web APIs
               |-- Piper and Faster-Whisper
               `-- operator-configured Ed-Fi ODS/API
```

Nova is local-first, not dependency-free. Some capabilities call operator-configured network services.

## Process Topology

### Command Front Door

`nova.cmd` delegates to `nova.ps1`. The PowerShell front door owns environment setup, process launch, runtime status, smoke/test commands, packaging, installer operations, release ledger commands, SOCK, and wiring checks.

Important distinctions:

- `nova run` starts `nova_core.py` directly.
- `nova guard` starts `nova_guard.py`, which supervises core and launches maintenance.
- `nova webui` or `nova webui-start` starts `nova_http.py` separately on port 8080 by default.
- guard/core and web UI are different process identities.

### Guard

`nova_guard.py` owns:

- a single guard lock and PID identity
- core process launch and adoption
- boot state and heartbeat observation
- failure resolution and restart delay
- stop intent handling
- one-shot maintenance launch on cadence
- cross-process detection intended to avoid duplicate maintenance cycles

### Core

`nova_core.py` is the local interactive core. It owns or exposes:

- heartbeat and core identity
- CLI/voice loop integration
- policy and compatibility wrappers
- memory adapters and learned identity context
- tool registry exports and planned-action dispatch
- Ollama health, warming, and chat calls
- patch compatibility functions
- pulse, core health, release, source-root, memory, and subconscious tools

It does not host the operator HTTP server.

### HTTP Runtime

`nova_http.py` uses `ThreadingHTTPServer` and imports core behavior as a callable runtime. The HTTP file retains compatibility wrappers, but delegates major ownership to services.

Pages and static surfaces:

- `/control`
- `/control/login`
- `/leah`
- control and Leah JS/CSS assets

Primary APIs:

- `GET /api/health`
- `GET /api/chat/history`
- `GET /api/control/status`
- `GET /api/control/status/surfaces`
- `GET /api/control/policy`
- `GET /api/control/metrics`
- `GET /api/control/work-trees`
- `GET /api/control/pipelines`
- `GET /api/control/sessions`
- `GET /api/control/test-sessions`
- `POST /api/chat`
- `POST /api/chat/resume`
- `POST /api/chat/login`
- `POST /api/chat/logout`
- `POST /api/chat/upload`
- `POST /api/control/action`
- `POST /api/control/login`
- `POST /api/control/logout`

## Conversation Flow

```text
CLI or HTTP turn
  -> identity and session binding
  -> turn evidence and intent understanding
  -> planner/routing support
  -> fulfillment viability and tool policy
  -> deterministic, tool, research, memory, self-report, or fallback path
  -> reply context and Ollama when needed
  -> reply runtime effects
  -> session update, action ledger, memory learning, and reflection evidence
```

Main owners:

- `services/nova_intent_understanding.py`
- `services/nova_turn_intent_trace.py`
- `services/nova_planner_contract.py`
- `services/nova_routing_support.py`
- `services/nova_route_probing.py`
- `services/nova_fulfillment_routing.py`
- `services/fulfillment_flow.py`
- `services/nova_reply_sequence.py`
- `services/nova_reply_runtime.py`
- `services/nova_http_turn_finalization.py`
- `services/nova_action_ledger.py`

The Supervisor seam exists, but the current default rule list and explicit ownership sets are empty. Present-tense documentation must not claim populated Supervisor ownership.

## Maintenance And Autonomy Flow

`autonomy_maintenance.py` is the cycle coordinator. It runs subconscious generation, Kidney, queue synchronization, temporal feed, Signal Intake, Mission, orchestrator evaluation/execution, Work Tree lanes, tree archival, regression refresh, and final Mission refresh.

The central flow is:

```text
owner evidence
  -> local/control status
  -> Signal Intake
  -> Work Tree
  -> pressure snapshot
  -> Mission input
  -> Mission verdict
  -> orchestrator action
  -> execution gate
  -> action dispatcher
  -> tool or Work Tree execution
  -> evidence
  -> final Signal Intake and Mission refresh
```

Current policy retains legacy maintenance execution and does not grant sole execution ownership to the orchestrator.

## Mission

Mission composes operations and truth evidence into a cycle verdict. It publishes `status`, `action`, `green_cycle`, `truth_ready`, owner verdicts, owner blockers, and green blockers.

Current truth owners include validation, regression, release, generated queue, layer maturity, and explicit owner verdicts such as core thinning.

Mission also currently applies hold policy, active-work tool exceptions, generated-queue hold exceptions, and ambient-ingestion suppression. See `AUTONOMY_AND_MISSION.md` for the exact current boundary and known risks.

## Work Tree

`work_tree.py` owns SQLite-backed trees, branches, tasks, tool declarations, dependencies, evidence, visual snapshots, and autonomous step execution.

`services/work_tree_signal_ingestion.py` converts runtime surfaces into branches and reconciles them. `services/work_tree_pressure_snapshot.py` composes shared pressure counts. `services/work_tree_operator_hold.py` classifies operator-held branches.

Task states, branch states, resolution states, evidence validity, and operator holds are separate concepts. A branch may remain observable without being autonomously executable.

## Operator Control And Outbox

The control-action dispatcher exposes operator, policy, runtime, queue, test, patch, pipeline, session, search, Mission, and autonomy actions through one HTTP action endpoint.

`services/operator_outbox.py` stores durable notices in `runtime/operator_outbox.jsonl`. Raw open count and operator-actionable count are separate fields. Signal Intake uses the actionable count when present.

The current broad exclusion of `autonomy_maintenance` notices from actionability is a known truth risk documented in the code-truth audit.

## Status And Control Hydration

The control UI does not require one full payload for every view.

- `/api/control/status/surfaces` is the thin status spine.
- `/api/control/status` contains heavier detail.
- Work Trees, pipelines, sessions, tests, policy, and metrics have targeted endpoints.
- `static/control.js` decides which views hydrate full status and targeted payloads.

Mission brief fields belong on the status spine. Heavy visual and diagnostic sections can load separately.

## Memory And Identity

Nova has multiple memory lanes:

- persisted conversation/session state
- identity profile and learned facts
- SQLite semantic/lexical memory
- operational memory and action ledgers
- generated-code memory
- subconscious and maintenance evidence

Policy controls memory enablement, scope, retention kinds, blocked kinds, source exclusions, and recall thresholds. Identity bootstrap and origin confirmation are governed Work Tree flows.

## Tools And OS Capabilities

The direct tool registry contains filesystem, codegen, patch, vision, research, system, OS capability, temporal review, and Ed-Fi explore tools.

Core exports additional named actions over those tools and services. Work Tree execution checks tree, branch, task, and tool declarations before dispatch.

OS capabilities add a second contract:

```text
capability registry
  -> version/hash/arguments/authority
  -> execution-time validation
  -> PowerShell script
  -> ledger/evidence
  -> result judgment or operator notice
```

## SOCK, Kidney, And Subconscious

### SOCK

SOCK profiles hardware and Ollama inventory, recommends model assignments, compares them with policy, optionally applies policy, and validates concurrent warming. See `SOCK_SYSTEM.md`.

### Kidney

Kidney scans generated definitions, review/quarantine files, patch previews, snapshots, exports, ledgers, and temporary artifacts. In enforce mode it snapshots cleanup intent and applies archive/delete actions subject to protection patterns and retention caps.

### Subconscious

Subconscious runs scenario families, produces unattended reports and generated session definitions, identifies robust weakness pressure, and feeds review candidates into Signal Intake. Review authority and judgment determine whether pressure becomes repair work, observation, or terminal no-owner-root-repair evidence.

## Patch, Codegen, And Release

Patch governance includes preview creation, manifest checks, approval, snapshot, apply, compile/behavior checks, rollback, cleanup, and update-now state.

Codegen includes capability-gap detection, preview generation, preview validation, patch bridging, code-pattern memory, promotion memory, and Leah build scaffolding. Current layer policy keeps Leah and codegen in observe mode unless explicitly promoted.

Release governance includes package build/verify, validation, runtime build identity, source/build drift, promotion judgment, release-clean, installer build/verify, and ledger/readiness views.

## Test Ecosystem

Nova distinguishes discovered tests, compact lanes, source-profile lanes, generated sessions, and validation artifacts. See `TEST_ECOSYSTEM.md` and `TEST_INDEX.md`.

No static test count or old pass result is live truth.

## Data Pipelines And Ed-Fi

The pipeline framework owns manifests, registry discovery, query guards, audit, privileged protocol/worker, control actions, schema probes, and query execution.

The vendor-neutral Ed-Fi core owns OAuth, client behavior, discovery, resources, paging, district scope, diagnostics, capability profiles, readiness, and change tracking.

The active BISD lane owns district-specific configuration, allowlisted query templates, schema manifest, connector behavior, and lane controls. Domain logic does not belong in the vendor-neutral Ed-Fi core.

## Wiring Surfaces

`services/nova_wiring_inventory.py` declares 45 unique surfaces:

| Domain | Surface IDs |
|---|---|
| Runtime | `runtime_core`, `runtime_control`, `scheduler_registry`, `autonomy_maintenance`, `model_runtime`, `http_api_control`, `http_continuity` |
| Autonomy and work | `autonomy_orchestrator`, `work_tree`, `generated_queue`, `subconscious`, `core_steward_reflection`, `source_root_inventory` |
| Conversation | `conversation_routing`, `supervisor_fulfillment`, `reply_quality_contracts`, `action_ledger`, `session_identity_auth` |
| Tools and policy | `tool_registry_policy`, `tool_evidence`, `policy_gates`, `operator_control`, `safety_envelope` |
| Memory and retrieval | `memory_identity`, `identity_profile_answers`, `web_search`, `retrieval_knowledge`, `weather_location` |
| Mutation and release | `patch_pipeline`, `codegen_pipeline`, `release`, `installer_packaging`, `storage_release_pressure` |
| Data | `data_pipelines`, `edfi_capability_profile`, `edfi_core`, `data_lane_edfi_bisd` |
| Media and host | `voice`, `tts_audio_output`, `vision`, `hardware_profile` |
| Quality and operations | `test_ecosystem`, `diagnostics_hygiene`, `metrics_ops_journal`, `frontdoor_cli` |

The source-root inventory declares 45 rows but only 43 unique IDs because Ed-Fi core and BISD lane are duplicated. That is current code truth, not a documentation count to normalize away.

## Important Runtime Artifacts

- `runtime/core_state.json`
- `runtime/core.heartbeat`
- `runtime/guard_pid.json`
- `runtime/autonomy_maintenance_state.json`
- `runtime/autonomy_maintenance.log`
- `runtime/autonomy_orchestrator_ledger.jsonl`
- `runtime/_internal/work_tree.db`
- `runtime/operator_outbox.jsonl`
- `runtime/tool_events.jsonl`
- `runtime/actions/`
- `runtime/memory_events.jsonl`
- `runtime/os_capability_ledger.jsonl`
- `runtime/subconscious_runs/latest.json`
- `runtime/regression_status.json`
- `runtime/validation/release/latest_release_validation.json`
- `runtime/exports/release_packages/release_ledger.jsonl`
- `runtime/kidney/status.json`

## Current Known Architectural Risks

- `autonomy_maintenance.py`, Signal Intake, core, HTTP, and Work Tree remain heavy files.
- Mission contains policy behavior in addition to verdict composition.
- legacy and orchestrator execution coexist.
- failed Work Tree tools can be marked complete by maintenance.
- actionable outbox classification is too broad by source.
- active-work target resolution is bounded by candidate enumeration.
- Supervisor default ownership is currently empty.
- source-root inventory contains duplicate IDs.

These are part of the map because hiding them would make the documentation less truthful than the code.
