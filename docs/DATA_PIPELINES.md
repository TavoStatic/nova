# Data Pipelines

Last verified from code: 2026-07-12

Nova has a governed pipeline framework, a vendor-neutral Ed-Fi core, and an active BISD Ed-Fi lane. Domain-specific logic belongs in the lane, not in core or HTTP.

## Framework

```text
pipelines/
  base.py                  manifest and base pipeline contracts
  registry.py              pipeline discovery and loading
  query_guard.py           operation, parameter, and row-limit checks
  audit.py                 pipeline audit records
  privileged_protocol.py   request/claim/response artifact protocol
  privileged_worker.py     trusted worker execution

services/
  data_pipeline_registry.py
  control_pipelines.py
  nova_http_pipeline_control.py
  nova_pipeline_tools.py
  pipeline_privileged_bridge.py
```

The control room can list, inspect, create, start, pause, update, archive, and query lanes through the control-action dispatcher.

## Pipeline Contract

Each lane owns:

- `pipeline.json`
- schema manifest
- allowlisted query templates
- connector behavior
- lane control state
- local configuration contract
- domain-specific population/report definitions when present

The framework owns discovery, query governance, audit, privileged execution, control actions, and status projection.

## Active Inventory

### Vendor-Neutral Ed-Fi Core

`services/edfi/` owns:

- connection configuration and runtime paths
- OAuth token acquisition and cache behavior
- HTTP client and error classification
- metadata discovery and capability profiles
- resource inventory and paging
- district scoping strategies
- diagnostics and readiness
- saved profile evidence
- change-version cursor and incremental change tracking

The core does not own Texas, PEIMS, BISD, or district-specific reporting semantics.

### BISD Ed-Fi Lane

`data_sources/edfi_bisd/` is active. It owns:

- `connector.py`
- `pipeline.json`
- `schema_manifest.json`
- `query_templates.json`
- `lane_control.json`
- local configuration example and local operator configuration

Operator probes:

- `scripts/run_edfi_profile.py`
- `scripts/run_edfi_explore.py`
- `scripts/demo_edfi_core_lifecycle.py`

The lane uses Ed-Fi core services and keeps district-specific scope and query contracts outside the vendor-neutral core.

### Archived SIS Test Lane

The previous SIS test lane is under `data_sources/_archived/`. It is history, not an active pipeline.

## Ed-Fi Tool

`tools/edfi_tool.py` registers `EdFiExploreTool`. Core exports the `edfi_explore` action for health, discovery, profile, resource, and query-oriented inspection according to its tool contract.

## Evidence And Readiness

Ed-Fi evidence appears through:

- saved connection and capability profile artifacts
- core readiness status
- profile evidence service
- pipeline registry/status surfaces
- Work Tree Signal Intake
- wiring and source-root inventory
- source-profile regression lanes

Profile existence, authentication success, resource discovery, district scope, lane readiness, and change-cursor freshness are separate facts.

## Query Safety

- operations must be declared by the lane
- parameters and row limits pass the query guard
- lane pause blocks execution before connector work
- privileged requests use the artifact protocol and trusted worker
- audit records preserve the request and outcome
- district scoping is explicit; it is not inferred from chat text
- vendor API behavior that ignores server-side filters must be represented in the lane/client strategy

## Current Inventory Defect

The source-root inventory declares `edfi_core` twice and `data_lane_edfi_bisd` twice. The wiring inventory has unique surface IDs; the duplication is in source-root declarations and remains code work.
