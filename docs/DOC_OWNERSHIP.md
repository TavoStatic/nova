# Documentation Ownership

Last verified: 2026-07-12

## Authority Classes

### Code Truth

- `CODE_TRUTH_AUDIT_2026-07-12.md`: scan baseline, drift findings, and unresolved code facts
- `SYSTEM_MAP.md`: current processes, ownership, APIs, artifacts, and wiring surfaces
- `ARCHITECTURE.md`: design intent and current implementation boundaries
- `SERVICES_INDEX.md`: every service module
- `FUNCTION_INDEX.md`: every active source function, method, and class
- `TEST_INDEX.md`: every discovered test function and lane membership

### Live Truth

- `STATUS.md` only points to live owners; it must not hard-code a green verdict
- runtime process, maintenance, Work Tree, outbox, regression, validation, and release artifacts own current state

### Subsystem Truth

- `AUTONOMY_AND_MISSION.md`: Mission, orchestrator, gate, Work Tree, pressure, and outbox
- `TEST_ECOSYSTEM.md`: test discovery, lane membership, generated tests, and validation truth
- `KIDNEY_SYSTEM.md`: cleanup and retention
- `SOCK_SYSTEM.md`: hardware/model compatibility
- `DATA_PIPELINES.md`: pipeline framework, Ed-Fi core, and domain lanes
- `SEARCH_PROVIDER_ARCHITECTURE.md`: search providers and research routing
- `PATCHING.md`: patch governance
- `OPERATIONS.md`: commands and operating procedures

### Plans And History

Phase, roadmap, promotion-plan, handoff, readiness, and dated audit documents record intent or history. They must be labeled as such and may not override current code or runtime evidence.

## Update Rules

- adding or removing a source function requires regenerating `FUNCTION_INDEX.md`
- adding or removing a service requires regenerating `SERVICES_INDEX.md`
- adding or removing tests or lane membership requires regenerating `TEST_INDEX.md` and checking `TEST_ECOSYSTEM.md`
- adding a wiring surface or source root requires updating `SYSTEM_MAP.md`
- changing Mission, orchestrator, gate, maintenance order, Work Tree pressure, or outbox semantics requires updating `AUTONOMY_AND_MISSION.md`
- changing process topology or HTTP routes requires updating `SYSTEM_MAP.md` and the root README
- changing data lanes requires updating `DATA_PIPELINES.md`
- a current pass/green/release-ready claim requires fresh artifact identity and timestamp
