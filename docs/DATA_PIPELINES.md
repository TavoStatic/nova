# Data Pipelines

Last verified: 2026-05-06

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

## SIS Test Pipeline

The first scaffold lives at [data_sources/sis_test](../data_sources/sis_test).

It is intentionally:

- read-only
- district-network scoped
- config-driven
- query-preview first

The scaffold is ready for:

- `status`
- `schema_probe`
- `safe_query`
- `student_lookup`
- `campus_enrollment_summary`
- `program_membership_lookup`
- `schema_inventory`

The SIS test pipeline also carries lane-specific grounding files:

- [data_sources/sis_test/field_dictionary.json](../data_sources/sis_test/field_dictionary.json)
- [data_sources/sis_test/source_notes.md](../data_sources/sis_test/source_notes.md)
- [data_sources/sis_test/population_definitions.json](../data_sources/sis_test/population_definitions.json)
- [data_sources/sis_test/vendor_dictionary_index.json](../data_sources/sis_test/vendor_dictionary_index.json)
- [data_sources/sis_test/predefined_reports_index.json](../data_sources/sis_test/predefined_reports_index.json)

It supports:

- truthful connectivity/auth readiness checks
- governed dry-run previews
- live read-only execution for allowlisted query templates once local config, driver, and credentials are valid
- schema inventory discovery for table/column grounding
- a temporary 20-row hard cap on governed queries while the data shape is being verified

The first live lane is intentionally small and grounded to the table usage already present in the local UniServer dashboard references.

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

The SIS lane remains read-only and query-template governed.

- Live execution is allowed only for allowlisted operations in `pipeline.json`.
- `safe_query` routes through the connector and query guard.
- `schema_inventory` supports structured schema discovery without hand-maintained table guesses.
- Default row limiting stays in force while operators verify that a request is pulling the intended data shape.
