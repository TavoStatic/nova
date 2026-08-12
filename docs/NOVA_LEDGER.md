# Nova Living Ledger

_Generated: 2026-08-05 17:27_

Two sources feed this document: **developer sessions** and **Nova's own scan findings**.
Append to `docs/ledger/session_log.jsonl` (developer) or `docs/ledger/nova_findings.jsonl` (Nova),
then re-run `python scripts/generate_nova_ledger.py`.

---

## Session History

Chronological record of every developer session that touched Nova.

### 2026-08-05 — claude-cowork
_Session: fix_entry_points_20260805_

**Modules touched:** `docs/README.md`, `docs/DOC_OWNERSHIP.md`, `docs/NOVA_POSTAL.md`

**Changes:**
- docs/README.md now leads with NOVA_POSTAL and NOVA_LEDGER — retired July audit as primary authority
- DOC_OWNERSHIP.md rewritten — Living Ledger is now primary authority class — dated audits moved to historical section
- NOVA_POSTAL.md complete rewrite — file type as first level of order — three-phase agent protocol (arriving/working/leaving) — product finish map added

**Meta:** docs updated: `docs/README.md`, `docs/DOC_OWNERSHIP.md`, `docs/NOVA_POSTAL.md`

_Note: Phase 1 complete. Fixed the three entry point doors so agents arriving anywhere land in the correct flow. Grok gap findings 1-2-3 addressed._

### 2026-08-05 — claude-cowork
_Session: regenerate_indices_20260805_

**Modules touched:** `docs/SERVICES_INDEX.md`, `docs/SYSTEM_MAP.md`, `scripts/regenerate_services_index.py`

**Changes:**
- SERVICES_INDEX.md regenerated from 191-line manual list to 232 service files — backpack_host
- nova_shell
- decision_proposal_judge
- solution_trail
- self_scan_rings
- nova_setup_wizard all added
- SYSTEM_MAP.md updated — reading order now leads with Ledger and Postal — six missing subsections added: Decision Judge
- Nova Shell
- Backpack Host
- Solution Trail
- Self-Scan Rings
- Setup Wizard — known risks updated
- scripts/regenerate_services_index.py created — auto-generates SERVICES_INDEX from AST scan of services/ directory

**Meta:** docs added: `scripts/regenerate_services_index.py` · docs updated: `docs/SERVICES_INDEX.md`, `docs/SYSTEM_MAP.md`

_Note: Phase 3 complete. All three stale indices updated. Grok gap findings 4-6 addressed. Regenerate SERVICES_INDEX anytime with: python scripts/regenerate_services_index.py_

### 2026-08-05 — claude-cowork
_Session: aug05_hygiene_close_

**Modules touched:** `docs/FUNCTION_INDEX.md`, `docs/TEST_INDEX.md`, `scripts/nova_ledger_ingest.py`, `scripts/generate_nova_ledger.py`, `autonomy_maintenance.py`, `docs/NOVA_LEDGER.md`

**Changes:**
- Regenerated FUNCTION_INDEX (561 files 6577 fns)
- Regenerated TEST_INDEX (245 modules 2344 fns)
- Added emit_drift_alerts_from_ring_result() to nova_ledger_ingest
- Updated generate_nova_ledger to render drift_alert entries in Drift Alerts section
- Wired drift alert emission into autonomy_maintenance cycle
- Emitted 3 current drift alerts (9 unclassified files 9 stale docs 15 probe gaps)

_Note: Closes migration hygiene: FUNCTION_INDEX current, TEST_INDEX current, drift alerts live in ledger. Remaining gaps are tracked (not hidden): 9 source files unclassified, 9 stale NOVA_DOC headers, 15 probe gaps offline-mode. All gaps emit on every maintenance cycle going forward._

### 2026-08-05 — claude-cowork
_Session: aug05_doc_catchup_

**Modules touched:** `docs/SERVICES_INDEX.md`, `docs/DOC_OWNERSHIP.md`, `docs/README.md`, `docs/NOVA_POSTAL.md`, `services/nova_shell_control_bridge.py`, `services/supervisor_rules.py`, `scripts/nova_ledger_ingest.py`, `scripts/generate_nova_ledger.py`, `scripts/regenerate_function_index.py`, `docs/archive/*`

**Changes:**
- Added nova_shell_control_bridge and supervisor_rules to SERVICES_INDEX
- Embedded NOVA_DOC headers in 5 files missing them
- Archived 9 historical docs (STATUS HANDOFF CODE_TRUTH_AUDITs phase docs coaching docs)
- Updated DOC_OWNERSHIP README NOVA_POSTAL to remove stale archive references
- NOVA_DOC coverage now 35 declared 0 undeclared 0 stale

_Note: Documentation fully caught up with recent build work. Zero stale/undeclared docs. Remaining gaps are tracked in drift alerts: 10 unclassified source files (pre-existing structural debt in scripts/)._

### 2026-08-04 — claude-cowork
_Session: sock_improvements_and_judge_

**Modules touched:** `services/sock_service.py`, `services/ollama_health.py`, `static/control.js`, `tests/test_decision_proposal_judge.py`, `docs/DECISION_PROPOSAL_JUDGE.md`

**Changes:**
- SOCK: ROCm/HIP detection via rocm-smi (AMD dedicated VRAM, no shared RAM contamination)
- SOCK: NPU wiring — npu_inference field + _npu_inference() function
- SOCK: Live VRAM estimates from Ollama /api/show with per-model cache
- SOCK: Cache invalidation hook — invalidate_sock_cache() + notify_ollama_model_change()
- ollama_health.py: _notify_sock_if_changed() wired to detect inventory changes
- control.js: HARDWARE/SOCK section added to System Matrix (GPU, CPU, NPU, chat model, routing model, policy sync)
- Decision Judge: DecisionProposal + JudgeReport + DecisionEpisode schemas designed and built
- Judge: controlling_dimension drives disposition (no blended confidence)
- Judge: field_sources provenance — Actor cannot self-score intended_effect
- Judge: judge_was_useful computed automatically from prediction vs outcome
- Judge: wired to _execute_autonomy_recommendation in observe-only mode (decision_judge_enforce: false by default)
- Judge: calibration bar set — 12 episodes before signals, 30 before enforce conversation

**Meta:** 11 tests added · docs added: `DECISION_PROPOSAL_JUDGE.md`

_Note: SOCK hardware section live in control panel. Judge accumulating episodes in parallel with normal execution._

### 2026-08-04 — claude-cowork
_Session: doc_ledger_and_postal_office_20260804_

**Modules touched:** `static/control.js`, `services/sock_service.py`, `services/ollama_health.py`, `docs/NOVA_POSTAL.md`, `docs/ledger/`

**Changes:**
- HARDWARE/SOCK section in System Matrix
- Living ledger with two write paths
- Postal office routing table
- Full code truth audit
- Decision WHY mining started

**Meta:** docs added: `docs/NOVA_POSTAL.md`, `docs/NOVA_LEDGER.md`, `docs/CODE_TRUTH_AUDIT_2026-08-04.md`

_Note: Session cut short — WHY mining from nova_grok.md and session transcripts pending_

### 2026-08-04 — claude-cowork
_Session: arch_decisions_mining_20260804_

**Modules touched:** `scripts/nova_ledger_ingest.py`, `scripts/generate_nova_ledger.py`, `docs/ledger/nova_findings.jsonl`, `docs/NOVA_LEDGER.md`

**Changes:**
- Added decision entry_type to nova_ledger_ingest.py VALID_ENTRY_TYPES
- Added Architectural Decisions section to generate_nova_ledger.py with named headers rationale and affects
- Mined 12 WHY decisions from nova_grok.md June 2026 Grok session (all 44 turns)
- Ingested decisions into nova_findings.jsonl
- Regenerated NOVA_LEDGER.md with decisions as named sections

_Note: Task 34 complete. Decisions cover: services_import_boundary, three_runtime_architecture, evidence_validity_json_aware, maintenance_local_enrichment, hardware_constraint_core_solid, leah_observe_mode, subconscious_no_routing, control_status_read_only, nova_grok_file_origin, commit_is_deployment, root_cause_first_principle, operator_outbox_durable_lane_

### 2026-08-03 — claude-cowork
_Session: edfi_backpack_and_nova_shell_

**Modules touched:** `backpacks/edfi/`, `services/backpack_host/`, `nova_shell/`, `tools/`

**Changes:**
- data connector backpack structure built
- Backpack Host — discovery, install, grant enforcement, lifecycle
- Nova Shell security scaffolding, identity, store, roles, auth, admin
- Custom roles CRUD added
- data connector code scan completed

_Note: Tasks 13-25 completed_

### 2026-08-02 — claude-cowork
_Session: self_scan_rings_and_coaching_

**Modules touched:** `services/nova_root_inventory.py`, `services/nova_wiring_inventory.py`, `docs/`

**Changes:**
- Three-ring self-scan design woven into Nova
- SELF_SCAN_RINGS_DESIGN.md written
- SOLUTION_EXPERIENCE_BACKLOG.md written
- NOVA_COACHING_INCOMPLETE_HANDOFF.md written
- NOVA_COACHING_STUCK_MISSION_HOLD.md written

**Meta:** docs added: `SELF_SCAN_RINGS_DESIGN.md`, `SOLUTION_EXPERIENCE_BACKLOG.md`, `NOVA_COACHING_INCOMPLETE_HANDOFF.md`, `NOVA_COACHING_STUCK_MISSION_HOLD.md`

_Note: Rings 1-2 confirmed real code. Ring 3 on findings queue only._

### 2026-08-01 — claude-cowork
_Session: control_panel_wiring_

**Modules touched:** `nova_http.py`, `static/control.js`, `static/control.html`, `nova_calendar_ingestion.py`, `work_tree_signal_ingestion.py`

**Changes:**
- Calendar RRULE recurrence + sidecar enrichment
- Per-event signals in work_tree_signal_ingestion
- Temporal event HTTP endpoints
- Control panel temporal event controls
- Branch Inspector fix
- Missing control panel buttons restored

_Note: Tasks 1-8 completed_

### 2026-07-12 — claude-cowork
_Session: code_truth_audit_20260712_

**Modules touched:** `all`

**Changes:**
- Full code truth audit. Drift findings documented. Doc ownership structure established.

**Meta:** docs added: `CODE_TRUTH_AUDIT_2026-07-12.md`, `SYSTEM_MAP.md`, `ARCHITECTURE.md`, `SERVICES_INDEX.md`, `FUNCTION_INDEX.md`, `TEST_INDEX.md`, `TEST_ECOSYSTEM.md`, `AUTONOMY_AND_MISSION.md`, `DATA_PIPELINES.md`, `OPERATIONS.md`, `HANDOFF.md`, `SUPERVISOR_CONTRACT.md`, `KIDNEY_SYSTEM.md`, `SOCK_SYSTEM.md`, `MEMORY_SYSTEM_PLAN.md`, `LEAH_INSTANCE_PROMOTION_PLAN.md`, `PACKAGE_PRODUCT_ROADMAP.md`, `PACKAGING_MATRIX.md`, `PATCHING.md`, `PHASE2_SAFETY_ENVELOPE.md`, `PHASE_CLOSEOUT_CHECKLIST.md`, `PHASE_COMPLETION_ASSESSMENT.md`, `WINDOWS_INSTALLER_PLAN.md`, `BASE_PACKAGE_READINESS.md`, `DOC_OWNERSHIP.md`, `STATUS.md`, `NOVA_HEALTH_REVIEW.md` · docs updated: `README.md`

_Note: Anchor commit: 92ca149e452e96dfd0d9224eb2d11a0862c3ccea_

### 2026-06-27 — cursor-grok
_Session: nova_grok_session_

**Modules touched:** `nova_core.py`, `nova_guard.py`, `nova_http.py`, `work_tree.py`

**Changes:**
- ~9h session. Runtime governance, work tree, guard stability. See nova_grok.md turns 1-44.

**Meta:** docs added: `nova_grok.md`, `nova_grok.jsonl`

_Note: Full machine record in nova_grok.jsonl (~6.3MB, 1494 events)_

### 2026-05-27 — claude-cowork
_Session: NOVA_CODE_SCAN_2026-05-27_

**Modules touched:** `all`

**Changes:**
- Full code scan — 281 Python source files, 3431 functions, 181 classes indexed

**Meta:** docs added: `NOVA_CODE_SCAN_2026-05-27.md`

_Note: Baseline scan. Superseded by CODE_TRUTH_AUDIT_2026-07-12.md_

---

## Documentation Registry

Every known doc file classified by authority and last verification date.

### ✅ Active Authority

| File | Last Verified | Verified By | Notes |
|------|--------------|-------------|-------|
| `AGENTS.md` | 2026-08-04 | developer | Operator-enforced agent rules. Root level — must stay at root. |
| `README.md` | 2026-08-03 | developer | Project README. Root level — must stay at root. |
| `docs/ARCHITECTURE.md` | 2026-07-12 | developer | Design intent and current implementation boundaries. Anchored to commit 92ca149. |
| `docs/AUTONOMY_AND_MISSION.md` | 2026-07-12 | developer | Maintenance, Mission, orchestrator, execution, and feedback contracts. |
| `docs/BOOTSTRAP.md` | 2026-05-20 | developer | Bootstrap procedure. |
| `docs/DATA_PIPELINES.md` | 2026-07-12 | developer | Data pipeline architecture. |
| `docs/DECISION_PROPOSAL_JUDGE.md` | 2026-08-04 | developer | Decision Judge architecture — DecisionProposal, JudgeReport, DecisionEpisode schemas. Current. |
| `docs/DEPENDENCY_CONTRACT.md` | 2026-05-20 | developer | Dependency contract. |
| `docs/DOC_OWNERSHIP.md` | 2026-07-12 | developer | Authority structure for all docs. Needs update — new docs since July 12 not registered. |
| `docs/FRESH_MACHINE_VALIDATION.md` | 2026-05-20 | developer | Fresh machine validation protocol. |
| `docs/KIDNEY_SYSTEM.md` | 2026-07-12 | developer | Kidney thinning and memory hygiene system. |
| `docs/NOVA_COACHING_INCOMPLETE_HANDOFF.md` | 2026-08-02 | developer | Nova coaching doc — incomplete handoff behavior. Verified against character test. |
| `docs/NOVA_COACHING_STUCK_MISSION_HOLD.md` | 2026-08-02 | developer | Nova coaching doc — stuck mission hold behavior. |
| `docs/NOVA_POSTAL.md` | — | nova | The postal office — routing table for all Nova documentation. Read before any doc work. |
| `docs/OPERATIONS.md` | 2026-07-12 | developer | Operational procedures. |
| `docs/PACKAGING_MATRIX.md` | 2026-05-18 | developer | Packaging matrix. Verify against current release artifacts. |
| `docs/PATCHING.md` | 2026-07-12 | developer | Patching protocol. |
| `docs/PRIVILEGED_PIPELINE_PROTOCOL.md` | 2026-05-18 | developer | Privileged pipeline protocol. |
| `docs/RC_VALIDATION_TEMPLATE.md` | 2026-05-18 | developer | RC validation template. |
| `docs/RELEASE_ARTIFACT.md` | 2026-06-14 | developer | Release artifact specification. |
| `docs/SEARCH_PROVIDER_ARCHITECTURE.md` | 2026-06-11 | developer | Search provider (SearXNG) architecture. |
| `docs/SELF_SCAN_RINGS_DESIGN.md` | 2026-08-02 | developer | Three-ring self-scan design. Rings 1-2 confirmed real code. Ring 3 on findings queue only. |
| `docs/SERVICES_INDEX.md` | 2026-07-12 | developer | Every service module and its public surface. Drift possible — sock_service, ollama_health, backpack_host changed 2026-08-04. |
| `docs/SUPERVISOR_CONTRACT.md` | 2026-07-12 | developer | Supervisor behavioral contract. |
| `docs/SYSTEM_MAP.md` | 2026-07-12 | developer | Current processes, ownership, APIs, artifacts, wiring surfaces. Anchored to commit 92ca149. |
| `docs/TEST_ECOSYSTEM.md` | 2026-07-12 | developer | Test lanes and strategy. |

### 🔵 Active Working

| File | Last Verified | Verified By | Notes |
|------|--------------|-------------|-------|
| `docs/BASE_PACKAGE_READINESS.md` | 2026-07-12 | developer | Base package readiness checklist. |
| `docs/FUNCTION_INDEX.md` | 2026-08-05 | nova | Regenerated 2026-08-05 via inline scan. 561 files, 6577 functions, 527 classes. Excludes .venv, .git, runtime. Shallow scan. |
| `docs/HANDOFF.md` | 2026-07-12 | developer | Handoff protocol between sessions. |
| `docs/LEAH_INSTANCE_PROMOTION_PLAN.md` | 2026-07-12 | developer | Leah promotion plan. Development paused. |
| `docs/MEMORY_SYSTEM_PLAN.md` | 2026-07-12 | developer | Memory system plan. Verify against current memory.py implementation. |
| `docs/NOVA_SERVER_SIDE.md` | 2026-06-26 | developer | Server-side architecture notes. |
| `docs/PACKAGE_PRODUCT_ROADMAP.md` | 2026-07-12 | developer | Product roadmap. |
| `docs/REAL_WORLD_TASKS.md` | 2026-04-28 | developer | Real world task examples. Oldest active doc — verify still relevant. |
| `docs/SOCK_SYSTEM.md` | 2026-08-05 | nova | Updated 2026-08-05. Hardware Detection section added covering ROCm/HIP, NPU, live VRAM, cache invalidation. |
| `docs/SOLUTION_EXPERIENCE_BACKLOG.md` | 2026-08-02 | developer | Backlog for solution experience improvements. Active. |
| `docs/TEST_INDEX.md` | 2026-08-05 | nova | Regenerated 2026-08-05. 245 test modules, 2344 test functions. Up from 215 modules / 2016 fns (July 12 vintage). |
| `docs/WINDOWS_INSTALLER_PLAN.md` | 2026-07-12 | developer | Windows installer plan. |

### ⚠️  Stale Snapshot

| File | Last Verified | Verified By | Notes |
|------|--------------|-------------|-------|
| `docs/FUNCTION_INDEX.md` | 2026-07-12 | developer | 3431 functions indexed 2026-07-12. Significant drift since — Judge, SOCK improvements, backpack host, nova_shell all added. Regeneration needed. |
| `docs/SOCK_SYSTEM.md` | 2026-07-12 | developer | SOCK system doc. Drift — ROCm, NPU, live VRAM, cache invalidation all added 2026-08-04. Needs refresh. |
| `docs/TEST_INDEX.md` | 2026-07-12 | developer | Test function index as of July 12. 11 new tests added 2026-08-04 (Judge). Regeneration needed. |

### 📦 Historical / Archive

| File | Last Verified | Verified By | Notes |
|------|--------------|-------------|-------|
| `NOVA_CODE_SCAN_2026-05-27.md` | 2026-05-27 | developer | Superseded by CODE_TRUTH_AUDIT_2026-07-12.md. Archive candidate — move to docs/archive/. |
| `NOVA_HEALTH_REVIEW.md` | 2026-07-12 | developer | Health review snapshot July 12. Archive candidate — move to docs/archive/. |
| `This_is_nova` | — | nova | Nova's founding action ledger — May 13-16 2026, 821 entries, first chat sessions, first tool calls, first grounded responses. Stays at root. Named with intent. |
| `codex_audit.txt` | 2026-07-12 | developer | Codex audit transcript. Archive candidate — move to docs/archive/. |
| `docs/CODE_TRUTH_AUDIT_2026-07-12.md` | 2026-07-12 | developer | Scan baseline and drift findings as of July 12. Historical record, not current truth. |
| `docs/PHASE2_SAFETY_ENVELOPE.md` | 2026-07-12 | developer | Phase 2 safety envelope. Phase complete — archive candidate. |
| `docs/PHASE_CLOSEOUT_CHECKLIST.md` | 2026-07-12 | developer | Phase closeout checklist. Phase complete — archive candidate. |
| `docs/PHASE_COMPLETION_ASSESSMENT.md` | 2026-07-12 | developer | Phase completion assessment. Historical — archive candidate. |
| `nova_grok.md` | 2026-06-27 | developer | Grok/Cursor session handoff transcript. Archive candidate — move to docs/archive/. |

---

## Architectural Decisions

WHY decisions mined from sessions, transcripts, and code audits.
These are the reasons behind Nova's structural choices.

### `services_import_boundary` — 2026-06-27
_Modules: services/ (all)_

services/ never imports nova_core. Work tree executes tools via injected callback (execute_planned_action_fn passed by caller). This keeps the graph store independent from the runtime brain.

**Rationale:** Circular imports would make the graph store untestable in isolation and couple the data layer to the runtime brain.

**Affects:** `work_tree.py`, `services/`, `nova_core.py`
**Source:** `nova_grok.md` · Status: active

### `three_runtime_architecture` — 2026-06-27
_Modules: nova_guard.py / nova_core.py / nova_http.py / autonomy_maintenance.py_

Three parallel runtimes: guard spawns and heartbeats core; HTTP serves UI and chat; maintenance is a separate worker triggered by guard every ~300s. Four processes total, each with a distinct role and failure domain.

**Rationale:** Monolithic process would mean a core crash takes down the UI, maintenance, and guard simultaneously. Separate processes allow partial recovery and independent restart.

**Affects:** `nova_guard.py`, `nova_core.py`, `nova_http.py`, `autonomy_maintenance.py`
**Source:** `nova_grok.md` · Status: active

### `evidence_validity_json_aware` — 2026-06-27
_Modules: services/evidence_validity.py / services/source_root_judgment.py / services/work_tree_signal_ingestion.py_

Evidence validity redesigned June 2026. Original _looks_like_failed_evidence() used naive 'ok': false substring matching. This false-positived on source code reads — ollama_health.py contains 'ok': False in Python source. Fix: JSON-aware parsing with length check (<=4000 chars, looks like a tool result, not source). Both call sites (judgment + ingestion) now route through evidence_validity.evidence_result_valid().

**Rationale:** Source code reads legitimately contain 'ok': False as Python syntax. A naive string search cannot distinguish a tool result from a file read. Structured JSON parsing with a length guard solves this without false positives.

**Affects:** `services/evidence_validity.py`, `services/source_root_judgment.py`, `services/work_tree_signal_ingestion.py`
**Source:** `nova_grok.md` · Status: active

### `maintenance_local_enrichment` — 2026-06-27
_Modules: autonomy_maintenance.py_

Maintenance local fallback was missing status surfaces. When HTTP is unavailable, the fallback payload did not populate last_intent, root_closure_inventory, source_root_inventory, and other surfaces that control_status.py builds. Fix: enrichment helpers (_apply_local_model_runtime_status, _apply_local_source_root_status_surfaces, _refresh_root_closure_inventory_surfaces) run after every HTTP merge, filling only missing keys.

**Rationale:** Two code paths (HTTP and fallback) must produce equivalent surfaces for signal ingestion to work correctly. Maintenance enrichment is cheaper and more resilient than requiring HTTP for every cycle.

**Affects:** `autonomy_maintenance.py`, `services/work_tree_signal_ingestion.py`
**Source:** `nova_grok.md` · Status: active

### `hardware_constraint_core_solid` — 2026-06-27
_Modules: all_

As of June 2026, Nova's codebase (~150 services, 320KB status payloads, 300s maintenance cycles) has outgrown available hardware. IA models are fine. Strategic decision: core solid, not expansion. Three-pillar response: (1) Reduce scheduled-tree churn by deduping closure tracks, (2) Make observation cheap via local-first status path targeting <2s local/<5s with HTTP, (3) Shorten release/restart loop to prevent drift. All expansion deferred until 48h core stability.

**Rationale:** Expansion on constrained hardware multiplies governance load. Each new wiring surface and duplicate closure track adds maintenance cost. Core integrity must come before capability addition.

**Affects:** `all`
**Source:** `nova_grok.md` · Status: active

### `leah_observe_mode` — 2026-06-27
_Modules: services/leah_frontdoor.py / capabilities_roadmap.json_

LEAH capabilities (voice persona engine, memory recall, emotional state model, conversation continuity) are gated behind core stability. Policy: Tier B (LEAH) observe-only until Tier A (runtime core) is green for 48h+. Gap signals are logged but no new codegen branches spawned. LEAH shell and frontdoor (/leah) exist and stay — only the four leah_* phase_2 capabilities are held.

**Rationale:** LEAH depends on solid http_continuity, memory_routing, voice root closure. Building capabilities on an unstable core creates compounding failures. Observe mode prevents governance from treating unbuilt persona engine as an active gap requiring codegen on every cycle.

**Affects:** `services/leah_frontdoor.py`, `capabilities_roadmap.json`, `autonomy_maintenance.py`
**Source:** `nova_grok.md` · Status: active

### `subconscious_no_routing` — 2026-06-27
_Modules: services/subconscious_config.py / services/subconscious_live_simulator.py_

Subconscious is deliberately forbidden from routing or controlling execution. subconscious_config.py explicitly lists forbidden_actions: own_turns, route_turns, force_behavior, override_supervisor, override_fulfillment, create_controller_logic, turn_diagnostics_into_commands. It detects pressure signals and emits triage hints to the orchestrator — nothing more.

**Rationale:** If the observer can route, it can route incorrectly based on its own incomplete view. Routing authority belongs to the orchestrator which has the full input envelope. Subconscious provides pressure signals only.

**Affects:** `services/subconscious_config.py`, `services/subconscious_live_simulator.py`, `autonomy_maintenance.py`
**Source:** `nova_grok.md` · Status: active

### `control_status_read_only` — 2026-06-27
_Modules: services/control_status.py_

control_status.py (~1,214 lines) assembles the full runtime snapshot — it only observes. Nothing routes there. The observation feeds signal ingestion which feeds the work tree. Routing and execution happen downstream. Polled at /api/control/status; UI polls it freely.

**Rationale:** Side effects in the observation layer would mean that inspecting the system changes the system. This makes diagnosis unreliable. Observation must be pure.

**Affects:** `services/control_status.py`, `nova_http.py`
**Source:** `nova_grok.md` · Status: active

### `commit_is_deployment` — 2026-06-27
_Modules: all_

Two blast radii for any code change: (1) local disk changes affect the running Nova instance immediately on the next maintenance cycle (~300s), not just on commit; (2) a pushed commit makes changes available to the hourly-sync Nova on its next pull. Rule: no casual commit. Treat local edits as live-runtime changes until validated. Only commit when both instances should absorb the same state.

**Rationale:** A second Nova instance pulls from GitHub hourly. Careless pushes deploy half-finished work to a live instance that will ingest signals, open work-tree branches, and run maintenance against the new code immediately.

**Affects:** `all`
**Source:** `nova_grok.md` · Status: active

### `root_cause_first_principle` — 2026-06-27
_Modules: all_

Working rule for all Nova development sessions: fix roots only. Before any fix, answer three questions: (1) Why does this problem exist? (2) How did it come to be? (3) What will fixing it affect? Band-aid fixes in one layer move pressure to another, or clear branches while leaving the underlying gap intact so it reopens next cycle.

**Rationale:** Nova's governance loop self-corrects. A band-aid that silences an outbox notice will be reopened by the next maintenance cycle if the underlying wiring is genuinely incomplete. Only root fixes produce durable closure.

**Affects:** `all`
**Source:** `nova_grok.md` · Status: active

### `operator_outbox_durable_lane` — 2026-06-27
_Modules: services/operator_outbox.py_

operator_outbox.py is a durable notice lane, not a conversational router. It records internal runtime pressure as notices (new -> seen -> answered -> resolved/dismissed/stale) so the UI can surface them without waiting for a user chat turn. Sources: autonomy orchestrator blocks, OS capability gaps, work tree operator holds, subconscious triage escalations.

**Rationale:** Chat turns are ephemeral and require a human present. Governance pressure is persistent and must survive session close. A durable notice lane decouples Nova's observations from user availability.

**Affects:** `services/operator_outbox.py`, `nova_http.py`, `static/control.js`
**Source:** `nova_grok.md` · Status: active

### `nova_grok_file_origin` — 2026-06-28
_Modules: nova_grok.md (root)_

nova_grok.md was created at the end of the June 27-28 2026 Grok session (Turn 41-44). Gus asked to save the full chat verbatim. Grok parsed the JSONL session transcript and wrote the full conversation to nova_grok.md. Named with intent — it is a session artifact, not documentation. Stays at root.

**Rationale:** Gus needed session continuity across a close. The file preserves nine hours of architectural discovery that would otherwise be lost on session close.

**Affects:** `nova_grok.md`
**Source:** `nova_grok.md Turn 41-44` · Status: active

---

## Nova Scan Findings

Findings written by Nova's rings, self-reflection, and execution outcomes.

- **2026-08-05** Ring 1 `map_integrity` — drifted: gap_count=9, unclassified_files=9, stale_docs=9
- **2026-08-05** Ring 2 `contract_integrity` — drifted: gap_count=15, probe_context=offline, probe_gaps=15
- **2026-08-05** Ring 3 `climb_integrity` — verified: gap_count=0, queue=0 climbable=0 unclimbable=0
- **2026-08-05** Ring 1 `nova_root_inventory` — drifted: 9 source file(s) have no SOURCE_ROOT classification
- **2026-08-05** Ring 1 `nova_doc_coverage` — drifted: 9 doc(s) have stale NOVA_DOC block (last_session > 30 days)
- **2026-08-05** Ring 2 `ring2_contract_integrity` — drifted: 15 contract probe gap(s) (offline): services lack HTTP-reachable health probe

---

## Drift Alerts

### Ring scan gaps (latest per category)

- **2026-08-05** Ring 1 `nova_doc_coverage` — 9 doc(s) have stale NOVA_DOC block (last_session > 30 days)
- **2026-08-05** Ring 1 `nova_root_inventory` — 9 source file(s) have no SOURCE_ROOT classification
- **2026-08-05** Ring 2 `ring2_contract_integrity` — 15 contract probe gap(s) (offline): services lack HTTP-reachable health probe

### Stale authority documents

- `docs/FUNCTION_INDEX.md` — last verified 2026-07-12: 3431 functions indexed 2026-07-12. Significant drift since — Judge, SOCK improvements, backpack host, nova_shell all added. Regeneration needed.
- `docs/SOCK_SYSTEM.md` — last verified 2026-07-12: SOCK system doc. Drift — ROCm, NPU, live VRAM, cache invalidation all added 2026-08-04. Needs refresh.
- `docs/TEST_INDEX.md` — last verified 2026-07-12: Test function index as of July 12. 11 new tests added 2026-08-04 (Judge). Regeneration needed.

---

_End of ledger. Append entries to the source JSONL files and regenerate to update._
