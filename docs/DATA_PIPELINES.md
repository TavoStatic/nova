# Data Pipelines

Nova can host multiple governed data pipelines without turning `nova_core.py` into a pile of one-off database logic.

## Shape

```text
C:\Nova\
├─ pipelines\
│  ├─ base.py
│  ├─ registry.py
│  ├─ query_guard.py
│  └─ audit.py
├─ data_sources\
│  └─ <pipeline_id>\
│     ├─ pipeline.json
│     ├─ schema_manifest.json
│     ├─ query_templates.json
│     ├─ connector.py
│     └─ local_config.example.json
└─ services\
   └─ data_pipeline_registry.py
```

## What Nova Owns

- pipeline discovery and registration
- governed operation names
- query guard behavior
- audit logging
- schema and template introspection

## What Each Pipeline Owns

- connector/runtime details
- schema grounding
- safe query templates
- local config requirements
- redaction defaults

## SIS Test Pipeline

The first scaffold lives at [C:\Nova\data_sources\sis_test](C:/Nova/data_sources/sis_test).

It is intentionally:

- read-only
- district-network scoped
- config-driven
- query-preview first

The scaffold is ready for:

- `status`
- `schema_probe`
- `student_lookup`
- `campus_enrollment_summary`
- `program_membership_lookup`

The SIS test pipeline now also carries a local field dictionary and source notes:

- [C:\Nova\data_sources\sis_test\field_dictionary.json](C:/Nova/data_sources/sis_test/field_dictionary.json)
- [C:\Nova\data_sources\sis_test\source_notes.md](C:/Nova/data_sources/sis_test/source_notes.md)

It now supports:

- truthful connectivity/auth readiness checks
- governed dry-run previews
- live read-only execution for the allowlisted query templates once the local config, driver, and credentials are valid

The first live lane is intentionally small and grounded to the table usage already present in the local UniServer dashboard references.
