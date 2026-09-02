<!--
NOVA_DOC
category: architecture
authority: active_authority
last_session: 2026-09-01
last_agent: grok
session_state: current
next_step: none
open: none
-->

# Documentation Ownership

Last verified: 2026-08-16

## Start Here

New agent or returning after a gap? Read in this order:

1. `docs/NOVA_POSTAL.md` — routing table, where everything lives, three-phase protocol
2. `docs/NOVA_LEDGER.md` — living master view, every doc classified by authority

This file tells you who owns what. The ledger tells you what is current.

---

## Authority Classes

### Living Ledger (primary documentation authority)

- `NOVA_LEDGER.md`: rendered master view — generated from both ledger sources. **Read this first.**
- `ledger/session_log.jsonl`: developer session entries — append with `scripts/log_session.py`
- `ledger/nova_findings.jsonl`: Nova's own scan/finding/decision entries — append via `scripts/nova_ledger_ingest.py`
- Regenerate ledger: `python scripts/generate_nova_ledger.py`

### Code Truth (check ledger for drift before relying on these)

- `SYSTEM_MAP.md`: current processes, ownership, APIs, artifacts, and wiring surfaces — anchored to commit 92ca149
- `ARCHITECTURE.md`: design intent and current implementation boundaries
- `SERVICES_INDEX.md`: every service module — regenerate after backpack-host or sanitizer changes (`python scripts/regenerate_services_index.py`)
- `FUNCTION_INDEX.md`: every active source function, method, and class — regenerated 2026-08-05 (561 files, 6577 fns)
- `TEST_INDEX.md`: every discovered test function and lane membership — regenerated 2026-08-05 (245 modules, 2344 fns)

### Live Truth

- `NOVA_LEDGER.md` is the live status view — regenerated after every session and every maintenance cycle
- runtime process, maintenance, Work Tree, outbox, regression, validation, and release artifacts own current state
- `STATUS.md` — superseded by `NOVA_LEDGER.md`; moved to `docs/archive/`

### Dated Audits (historical — not current code truth; moved to `docs/archive/`)

- `CODE_TRUTH_AUDIT_2026-08-04.md`: deep scan August 2026 — archived
- `CODE_TRUTH_AUDIT_2026-07-12.md`: scan baseline July 2026 — archived

### Current Audit Work Map

- `AUDIT_WORK_MAP_2026-08-25.md`: current audit scope and work mapping only; does not declare health or authorize repairs

### Subsystem Truth

- `AUTONOMY_AND_MISSION.md`: Mission, orchestrator, gate, Work Tree, pressure, outbox, and promoted mill skip/remint/stop/pulse (sip-execute not promoted)
- `TEST_ECOSYSTEM.md`: test discovery, lane membership, generated tests, and validation truth
- `KIDNEY_SYSTEM.md`: cleanup and retention
- `SOCK_SYSTEM.md`: hardware/model compatibility and mill capacity lease (standing vs temporary sip)
- `MILL_LANE_MEASURE_2026-09-01.md`: Ollama mill-judgment scores (3.5 vs 2.5); evidence only — does not override live mill
- `DATA_PIPELINES.md`: pipeline framework, data connector core, and domain lanes
- Backpack uninstall contract lives in code: `services/backpack_host/sanitize.py` and `services/backpack_host/install_state.py`. The named decision is `backpack_uninstall_touch_list` in the ledger.
- `SEARCH_PROVIDER_ARCHITECTURE.md`: search providers and research routing
- `PATCHING.md`: patch governance
- `OPERATIONS.md`: commands and operating procedures

### Self-Scan and Decision Systems

- `SELF_SCAN_RINGS_DESIGN.md`: three-ring self-scan design — woven into existing scanners, not a second engine
- `DECISION_PROPOSAL_JUDGE.md`: Decision Judge schemas (DecisionProposal, JudgeReport, DecisionEpisode), disposition rules, provenance
- `SOLUTION_EXPERIENCE_BACKLOG.md`: backlog for solution experience improvements
- `RESEARCH_BRIEF.md`: two-page sponsor brief — preliminary white-box evidence for Work Admission Kernel v1; historical; does not override code/runtime; not a live-autonomy claim

### Nova Coaching

- Coaching session docs moved to `docs/archive/` — historical, do not update.

### Plans And History

Phase, roadmap, promotion-plan, handoff, readiness, and dated audit documents record intent or history. They must be labeled as such and may not override current code or runtime evidence.

Archived (in `docs/archive/` as of 2026-08-05):
- `PHASE2_SAFETY_ENVELOPE.md`, `PHASE_CLOSEOUT_CHECKLIST.md`, `PHASE_COMPLETION_ASSESSMENT.md`
- `CODE_TRUTH_AUDIT_2026-07-12.md`, `CODE_TRUTH_AUDIT_2026-08-04.md`
- `NOVA_COACHING_INCOMPLETE_HANDOFF.md`, `NOVA_COACHING_STUCK_MISSION_HOLD.md`
- `HANDOFF.md` (May 2026 operating handoff), `STATUS.md` (superseded by ledger)

Remaining archive candidates (at root):
- `nova_grok.md`, `NOVA_CODE_SCAN_2026-05-27.md`, `NOVA_HEALTH_REVIEW.md`, `codex_audit.txt`

## Update Rules

- adding or removing a source function requires regenerating `FUNCTION_INDEX.md`
- adding or removing a service requires regenerating `SERVICES_INDEX.md`
- adding or removing tests or lane membership requires regenerating `TEST_INDEX.md` and checking `TEST_ECOSYSTEM.md`
- adding a backpack runtime write path requires declaring it in that backpack's manifest and keeping `services/backpack_host/sanitize.py` able to discover it
- adding a wiring surface or source root requires updating `SYSTEM_MAP.md`
- changing Mission, orchestrator, gate, maintenance order, Work Tree pressure, or outbox semantics requires updating `AUTONOMY_AND_MISSION.md`
- changing process topology or HTTP routes requires updating `SYSTEM_MAP.md` and the root README
- changing data lanes requires updating `DATA_PIPELINES.md`
- a current pass/green/release-ready claim requires fresh artifact identity and timestamp
- every developer session that changes Nova must log an entry in `ledger/session_log.jsonl` and regenerate `NOVA_LEDGER.md`
- every new doc file goes to `docs/` (not root) and gets registered here and in the ledger
- Nova writes findings to `ledger/nova_findings.jsonl` via `nova_ledger_ingest.py` after ring scans and self-reflection cycles
