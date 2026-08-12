<!--
NOVA_DOC
category: subsystem
authority: active_working
last_session: 2026-08-05
last_agent: grok
session_state: current
next_step: none
open: none
-->

# Data Pipelines

Last verified from code: 2026-08-05

Nova has a governed pipeline framework, a vendor-neutral data connector core, the **data connector backpack** (`backpacks/edfi` + `services/backpack_host`), and a legacy the district lane under `data_sources/data_connector`. New operator/tool traffic uses the backpack path.

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

### Vendor-Neutral data connector Core

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

The core does not own Texas, state education data, the district, or district-specific reporting semantics.

### data connector Backpack (preferred path)

`backpacks/edfi/` + `services/backpack_host/` is the installable backpack product:

- `backpack.json`, `operations.json`, `query_templates.json`, `settings_schema.json`, `brief.md`
- pipeline: `backpacks/edfi/pipeline/connector.py`
- tool: `tools/edfi_tool.py` (`edfi_explore`) via backpack host grants
- local warehouse: `services/edfi/warehouse.py` + `warehouse_sync.py` (schools phase 1)
- reports prefer warehouse/extract; live ODS only on explicit refresh
- operations include `view_status`, `view_data`, `run_sync`, **`run_warehouse_sync`** (`warehouse_status` / `warehouse_sync`)
- maintenance may run paced warehouse sync when schedule is due (`last_edfi_warehouse_sync`)

### the district data connector Lane (legacy lane on disk)

`data_sources/data_connector/` remains for migration and lane-style tests. New operator/tool traffic should use the backpack path.

Operator probes:

- `scripts/run_backpack.py` (warehouse sync CLI)
- `scripts/run_edfi_profile.py`
- `scripts/run_edfi_explore.py`
- `scripts/demo_edfi_core_lifecycle.py`

The lane uses data connector core services and keeps district-specific scope and query contracts outside the vendor-neutral core.

### Archived SIS Test Lane

The previous SIS test lane is under `data_sources/_archived/`. It is history, not an active pipeline.

## data connector Tool

`tools/edfi_tool.py` registers `DataConnectorExploreTool`. Core exports the `edfi_explore` action for health, discovery, profile, resource, and query-oriented inspection according to its tool contract.

## Evidence And Readiness

data connector evidence appears through:

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

The source-root inventory declares `edfi_core` twice and `data_lane_data_connector` twice. The wiring inventory has unique surface IDs; the duplication is in source-root declarations and remains code work.
