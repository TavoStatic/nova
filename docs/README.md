<!--
NOVA_DOC
category: architecture
authority: active_authority
last_session: 2026-08-05
last_agent: claude-cowork
session_state: current
next_step: none
open: none
-->

# Nova Documentation

## Start Here

**If you are an agent arriving at this project — read these two files before anything else:**

- [NOVA_POSTAL.md](NOVA_POSTAL.md): the routing table — where to find anything, where to put anything you write, three-phase protocol for arriving / working / leaving
- [NOVA_LEDGER.md](NOVA_LEDGER.md): the living master view — every session that touched Nova, every doc classified by authority, every architectural decision mined from sessions

The ledger tells you what is current and what is stale. The postal office tells you where to go. Do not skip them.

---

## Documentation Authority (in order)

1. **Live runtime** — process state, work tree DB, maintenance logs, guard/core artifacts
2. **Source code** — what the function actually does
3. **Inline docstrings** — what the developer said the function does
4. **NOVA_LEDGER.md + session_log** — what sessions recorded
5. **docs/ authority files** — ARCHITECTURE, SYSTEM_MAP, SERVICES_INDEX (check ledger for drift)
6. **docs/ working files** — plans, roadmaps, coaching
7. **Historical / archive** — phase docs, old scans, founding records

When two sources conflict, the lower-numbered source wins regardless of date.

---

## Current Authority Files

- [SYSTEM_MAP.md](SYSTEM_MAP.md): processes, ownership, APIs, wiring surfaces — anchored to commit 92ca149, check ledger for drift
- [ARCHITECTURE.md](ARCHITECTURE.md): design intent and current implementation boundaries
- [AUTONOMY_AND_MISSION.md](AUTONOMY_AND_MISSION.md): Mission, orchestrator, Work Tree, outbox contracts
- [SERVICES_INDEX.md](SERVICES_INDEX.md): service-module inventory — check ledger for drift
- [FUNCTION_INDEX.md](FUNCTION_INDEX.md): source function/class inventory — check ledger for drift
- [TEST_ECOSYSTEM.md](TEST_ECOSYSTEM.md): test truth model and ownership
- [TEST_INDEX.md](TEST_INDEX.md): test function inventory — check ledger for drift
- [DOC_OWNERSHIP.md](DOC_OWNERSHIP.md): authority classification for all docs

## Current Subsystems

- [KIDNEY_SYSTEM.md](KIDNEY_SYSTEM.md): cleanup, retention, retirement, and storage pressure
- [SOCK_SYSTEM.md](SOCK_SYSTEM.md): hardware/model compatibility and policy recommendations
- [DATA_PIPELINES.md](DATA_PIPELINES.md): pipeline framework, data connector core, and the district lane
- [SEARCH_PROVIDER_ARCHITECTURE.md](SEARCH_PROVIDER_ARCHITECTURE.md): web/research provider roles
- [PATCHING.md](PATCHING.md): patch proposal and apply/rollback governance
- [MEMORY_SYSTEM_PLAN.md](MEMORY_SYSTEM_PLAN.md): memory design and implementation history; verify current behavior against the code indexes
- [NOVA_SERVER_SIDE.md](NOVA_SERVER_SIDE.md): optional server-side/front-door infrastructure

## Operations And Release

- [OPERATIONS.md](OPERATIONS.md)
- [BOOTSTRAP.md](BOOTSTRAP.md)
- [DEPENDENCY_CONTRACT.md](DEPENDENCY_CONTRACT.md)
- [PACKAGING_MATRIX.md](PACKAGING_MATRIX.md)
- [RELEASE_ARTIFACT.md](RELEASE_ARTIFACT.md)
- [FRESH_MACHINE_VALIDATION.md](FRESH_MACHINE_VALIDATION.md)
- [WINDOWS_INSTALLER_PLAN.md](WINDOWS_INSTALLER_PLAN.md)
- [PRIVILEGED_PIPELINE_PROTOCOL.md](PRIVILEGED_PIPELINE_PROTOCOL.md)

## Plans And Historical Records

The following documents are useful planning or historical context, but they are not present-tense code authority:

- `LEAH_INSTANCE_PROMOTION_PLAN.md`
- `PACKAGE_PRODUCT_ROADMAP.md`
- `BASE_PACKAGE_READINESS.md`
- `REAL_WORLD_TASKS.md`
- dated root scans and health reviews

Archived to `docs/archive/` (2026-08-05): `PHASE2_SAFETY_ENVELOPE.md`, `PHASE_CLOSEOUT_CHECKLIST.md`, `PHASE_COMPLETION_ASSESSMENT.md`, `HANDOFF.md`, `STATUS.md`, `CODE_TRUTH_AUDIT_2026-*.md`, coaching session docs.

## Dated Audits and Scan Records

Historical snapshots moved to `docs/archive/` — useful for understanding drift, not for asserting current truth. The ledger (`NOVA_LEDGER.md`) tracks authority classification for all dated files. If a file is not in the ledger, register it before treating it as truth.

---

## Working Rule

When documentation disagrees with code, inspect the code. When code disagrees with live state, inspect the runtime artifact and its freshness. Do not treat a dated audit as current truth. The ledger tells you what is still accurate.
