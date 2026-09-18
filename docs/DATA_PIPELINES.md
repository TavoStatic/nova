# Data Pipelines

Nova provides a governed pipeline framework and optional installable backpack lanes.

## Framework

The framework owns discovery, query governance, audit, privileged execution, control actions, and status projection. A lane may provide:

- `pipeline.json`
- schema and operation manifests
- connector behavior
- local configuration
- lane control state

Backpacks add optional capabilities after core installation. The host owns discovery, installation, settings validation, grants, residue cleanup, and governed queries; each backpack owns its connector and declared operations.

## Control Flow

The control panel and CLI use the same service contracts. Queries pass through the pipeline registry and query guard, then execute through the privileged request protocol when the lane requires a worker.

Local settings and runtime evidence remain outside the tracked source tree. A missing optional backpack is a valid install state and must not create a core runtime import dependency.
