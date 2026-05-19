# Data Pipelines

Last verified: 2026-05-18

Nova can host multiple governed data pipelines without turning `nova_core.py` into a pile of one-off database logic.

## Shape

```text
C:\Nova\
|-- pipelines\
|   |-- base.py
|   |-- registry.py
|   |-- query_guard.py
|   `-- audit.py
|-- data_sources\
|   `-- <pipeline_id>\
|       |-- pipeline.json
|       |-- schema_manifest.json
|       |-- query_templates.json
|       |-- field_dictionary.json
|       |-- population_definitions.json
|       |-- vendor_dictionary_index.json
|       |-- predefined_reports_index.json
|       |-- connector.py
|       |-- lane_control.json
|       |-- operator_intake.jsonl
|       `-- local_config.example.json
`-- services\
    |-- data_pipeline_registry.py
    |-- control_pipelines.py
    `-- nova_http_pipeline_control.py
```

## What Nova Owns

- pipeline discovery and registration
- governed operation names
- query guard behavior
- audit logging
- schema and template introspection
- control-panel lane management
- scoped operator intake per lane

## What Each Pipeline Owns

- connector/runtime details
- schema grounding
- safe query templates
- local config requirements
- redaction defaults
- population definitions and report notes that belong only to that lane

## Current Lane Inventory

There are no active data lanes in the current source tree.

The previous `data_sources/sis_test` scaffold has been removed from the active package surface and archived under `data_sources/_archived/`. Do not treat SIS test docs or old collection failures as active Nova package truth.

Current source-owned pipeline pieces remain:

- `pipelines/base.py`
- `pipelines/registry.py`
- `pipelines/query_guard.py`
- `pipelines/audit.py`
- `services/data_pipeline_registry.py`
- `services/control_pipelines.py`
- `services/nova_http_pipeline_control.py`

The lane system is still available for future operator-provided pipelines, but active data content must be explicitly created or restored before it is considered part of runtime behavior.

## Data Lane Control

The control panel exposes data lanes as operator-managed runtime extensions.

Current lane controls are backed by `services/control_pipelines.py` and the HTTP action bridge in `services/nova_http_pipeline_control.py`.

Supported management actions:

- create a new lane scaffold under `data_sources/<pipeline_id>`
- pause or start an existing lane with `lane_control.json`
- update lane metadata such as display name and description
- archive a lane directory instead of deleting it in place
- save scoped operator notes to `operator_intake.jsonl`
- save pipeline-specific population definitions to `population_definitions.json`

When a lane is paused, query execution returns a blocked result before connector code runs.

## Query Guard Posture

Future lanes should remain read-only and query-template governed until their connector, credentials, and operator intent are explicit.

- Live execution should be allowed only for allowlisted operations in `pipeline.json`.
- `safe_query` should route through the connector and query guard.
- schema discovery should be structured and recorded instead of guessed from chat text.
- default row limiting should remain in force while operators verify that a request is pulling the intended data shape.
