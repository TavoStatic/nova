<!--
NOVA_DOC
category: audit
authority: active_working
last_session: 2026-08-25
last_agent: codex
session_state: current
next_step: execute evidence passes by track
open: audit mapping only; no repairs authorized by this document
-->

# Nova Audit Work Map

Date: 2026-08-25
Scope: map the condition of Nova before repair work. This document does not declare health, does not merge findings, and does not authorize changes.

## Audit rule

Every area is checked independently across:

`exists -> runs -> reports -> observes -> decides -> selects -> invokes -> gates -> records evidence -> verifies outcome -> closes work -> appears in control`

A missing observation is recorded as unknown, not as healthy or failed.

## Live baseline already observed

| Area | Evidence | Current state |
|---|---|---|
| Control overview | Live `/control` page | Health overview showed `0/100`, `0% pass`; route and health feeds were pending on refresh. |
| Health detail | Live Health view | Health score and pass ratio showed `n/a`; memory showed `ok`; storage watch showed `unknown`; alerts showed clear. |
| Runtime | Live Runtime Summary | Guard and Core showed running; Web UI showed running but host and port were `n/a`. |
| Supervisor | Live Supervisor Snapshot | Feed remained pending. |
| Scheduled Tree | Live Scheduled Tree view | Tree map, counts, selection, and branch inspector remained pending/awaiting. |
| Meta | Live Meta view | Current finding was `COMPETING_INTERPRETATIONS`; two options were 50/50; select existed; invoke and gate were `none`. |
| Mission | Live Mission Brief | Truth gate displayed `regression_failed` and `core_gate_release_drift`; layer maturity displayed blocked. |
| Data lanes | Live Data Lanes view | Pipeline registry and pipeline signal were pending. |
| Backpacks | Live Backpacks view | Backpack registry and signal were pending. |
| Sessions | Live Sessions view | Overview showed 82 live sessions; session focus and probe trace remained pending. |
| Policy | Live Policy Snapshot | Policy payload displayed; chat auth disabled; memory enabled; Ollama model configured. |

These observations are point-in-time UI evidence. They do not prove the underlying owner state where the surface is pending.

## Work tracks

Each track must produce its own evidence record, owner, gap list, and verification requirement.

| # | Source root / area | Owner evidence to inspect | Audit question |
|---:|---|---|---|
| 1 | `runtime_core` | guard, core, HTTP, runtime status | Are process identity, heartbeat, boot, and failure state truthful? |
| 2 | `runtime_control` | runtime control/process/restart services | Do control actions target the intended live process and report outcomes? |
| 3 | `scheduler_registry` | schedule registry, guard cadence, temporal services | Is scheduled work actually registered, due, launched, and accounted for? |
| 4 | `autonomy_maintenance` | maintenance state, cycle coordinator, maintenance log | Does a complete cycle run, or only selected portions? |
| 5 | `autonomy_orchestrator` | Mission, orchestrator, execution gate, autonomy ledger | Does a recommendation reach execution and outcome recording? |
| 6 | `model_runtime` | Ollama health, model calls, port ownership | Is the configured model reachable and usable for the required routes? |
| 7 | `frontdoor_cli` | `nova.cmd`, `nova.ps1`, CLI runners | Do supported entry points select the same runtime and contracts? |
| 8 | `http_api_control` | HTTP routes, transport, auth, control services | Does every control endpoint return the owner payload without loss? |
| 9 | `operator_control` | dispatcher, operator outbox, operator CLI | Are operator actions durable, authorized, and reflected in state? |
| 10 | `policy_gates` | policy files, policy manager/control | Which actions are enabled, blocked, or observe-only, and is that visible? |
| 11 | `session_identity_auth` | chat identity, sessions, Nova Shell, control auth | Are identity, ownership, login, tokens, and session boundaries working? |
| 12 | `memory_identity` | memory DB, health, bootstrap, retention | Are memory writes, reads, identity, and hygiene current and attributable? |
| 13 | `identity_profile_answers` | memory routing and profile services | Are identity/profile answers stored, recalled, and corrected correctly? |
| 14 | `conversation_routing` | intent, planner, route probing, reply sequence | Does a turn get one explainable route and complete finalization? |
| 15 | `supervisor_fulfillment` | supervisor rules, fulfillment flow/routing | Are ownership rules populated and are viable fulfillment paths reached? |
| 16 | `reply_quality_contracts` | reply runtime, reflection, fallback contracts | Are replies grounded, complete, and free of unsupported claims? |
| 17 | `web_search` | search provider, research sessions, HTTP search | Are provider selection, network scope, results, and failures recorded? |
| 18 | `retrieval_knowledge` | knowledge packs and retrieval | Are local sources found, ranked, cited internally, and followed up? |
| 19 | `weather_location` | location resolution and weather tools | Are location consent, fallback, tool use, and result provenance correct? |
| 20 | `work_tree` | SQLite tree/branch/task/evidence APIs | Do task states, branch resolution, selection, execution, and closure agree? |
| 21 | `tool_registry_policy` | registry, tool policy, OS capability controller | Are tools registered, permitted, argument-safe, and executable? |
| 22 | `tool_evidence` | execution service and validity checks | Does every invocation produce valid evidence or an honest failure? |
| 23 | `action_ledger` | action ledger and helpers | Does the ledger record select, invoke, gate, result, and final route? |
| 24 | `generated_queue` | generated definitions and test-session control | Are generated items distinct, governed, executable, and retired correctly? |
| 25 | `subconscious` | runner, simulator, reporting, triage, review judgment | Does observation produce bounded pressure without taking ownership of routing? |
| 26 | `patch_pipeline` | preview, apply, rollback, update-now | Are mutations previewed, authorized, tested, reversible, and recorded? |
| 27 | `codegen_pipeline` | codegen, bridge, promotion memory, gap detector | Are capability gaps real, governed, and separated from generated repair claims? |
| 28 | `release` | release status, validation, promotion, release-clean | Does artifact identity match validated source and release state? |
| 29 | `installer_packaging` | installer build/verify/promotion | Does the installer preserve the validated runtime and provenance? |
| 30 | `data_pipelines` | registry, schema probes, workers, privileged protocol | Are lanes registered, scoped, supervised, and able to prove query results? |
| 31 | `backpack_host` | discovery, install, grants, sanitize, reports | Are optional capabilities isolated, enabled correctly, and cleaned up? |
| 32 | `voice` | voice runtime, interaction, entry point | Are dependencies, recording, transcription, and failure states honest? |
| 33 | `tts_audio_output` | Piper/TTS scripts and model assets | Does audio output work with declared assets and report failures? |
| 34 | `vision` | screen/camera tools and vision runtime | Are capture permissions, tool results, and model interpretation bounded? |
| 35 | `http_continuity` | conversation manager and HTTP chat runtime | Do HTTP sessions preserve context, ownership, and resume behavior? |
| 36 | `test_ecosystem` | regression lanes, test sessions, validation artifacts | Is current validation fresh, complete, and not hidden by a green summary? |
| 37 | `diagnostics_hygiene` | doctor, health, diagnostics, hygiene checks | Do diagnostics measure current state and expose rather than mask failure? |
| 38 | `safety_envelope` | safety envelope and review authority | Are unsafe, unauthorized, and under-evidenced actions blocked? |
| 39 | `storage_release_pressure` | storage watch, artifacts, Kidney | Are cleanup, retention, archive, and storage pressure correct and reversible? |
| 40 | `metrics_ops_journal` | metrics, ops journal, telemetry | Are request, error, action, and timing metrics live and coherent? |
| 41 | `core_steward_reflection` | core steward, health brief, thinning | Does self-reflection produce owner work without claiming completion? |
| 42 | `source_root_inventory` | root inventory, wiring, end-to-end checks | Does every declared root have real status, signal, action, evidence, and closure paths? |
| 43 | `hardware_profile` | SOCK hardware/model profile | Does hardware evidence match model policy and actual runtime constraints? |
| 44 | `temporal_calendar` | calendar ingestion and temporal controls | Are temporal events parsed, scoped, scheduled, and acted on correctly? |

## Required outputs per track

For each numbered area, record:

- owner modules and runtime process
- data stores and current timestamp
- live probe performed and raw result
- status: working, degraded, broken, incomplete, contradictory, disabled, or unknown
- separate gaps for observe, decide, select, invoke, gate, evidence, closure, and display
- dependencies, without merging unrelated findings
- verification needed before repair can be accepted

## Current planning boundary

No repair work is authorized by this map. The next audit pass fills the 44 rows with evidence. Only after that pass is complete should repair ordering be chosen.

## Audit evidence collected 2026-08-26

These are evidence results, not a health score and not repair priorities.

### Source and wiring

- `42` source roots are declared and discovered.
- `5` source files are unclassified: `check_changes.py`, `run_critical_tests.py`, `services/cognitive_workspace.py`, `services/observation_spine.py`, `status_check.py`.
- Source wiring probe: passed, `gap_count=0`.
- Offline wiring inventory: passed, `47` surfaces, `gap_count=0`.
- End-to-end wiring check: failed, `2` checks failed:
	- source root inventory: the 5 unclassified files above
	- `wiring-source:data_lane_data_connector`: missing `data_sources/data_connector/connector.py` and `data_sources/data_connector/pipeline.json`
- A prior live-context wiring probe using a synthetic incomplete status payload reported status gaps. That result is invalid as a product finding because the probe input was incomplete; it is not counted here.

### Live self-work path

- Guard state: live PID and lock present.
- Maintenance state: current cycle records `status=skipped`, `reason=orchestrator_owns_execution` for the legacy Work Tree cycle.
- Orchestrator ledger: repeated recommendations for `active_work_tree_run_next` on `branch_e6e96c6c`.
- Execution records: recent cycles record `gate_status=allowed`, `result=success`, `executed=1`, and evidence IDs.
- Branch state: `branch_e6e96c6c` remains active with safety pressure `pending_review=2`, `quarantine=1`, `promoted=0`.
- Branch progress: `75%`, `2/3` markers, solution status `open`; the `settled` marker is absent.
- This is not classified as false task completion: step tasks are complete, while branch solution remains open. The unresolved work is the safety review/promote path.

### Focused test results

- HTTP/control surfaces: passed, `38 passed`.
- Memory/routing/planner/fulfillment: passed, `67 passed, 4 subtests passed`.
- Subconscious/decision/safety/layer maturity/validation/regression evidence: passed, `57 passed, 4 subtests passed`.
- Release/patch/Kidney/storage: passed, `88 passed`.
- Work Tree task progress: passed, `24 passed`.
- Solution trail: passed, `11 passed`.
- Work Tree core: failed, `9 failed, 60 passed`. Failures include expected `ATTEMPTED` task state being returned as `COMPLETE`, and an expected `task_close=attempted` field being absent.
- Backpack/data/pipeline/voice/vision/SOCK group: failed, `7 failed, 76 passed, 10 skipped`. Backpack failures include invalid/missing district LEA validation and settings/bootstrap behavior. SOCK failures include model recommendations not matching the tests for 8GB/high-VRAM scenarios.
- Work Tree signal-ingestion test: not completed; exceeded the 100-second test timeout. No pass/fail result is assigned.
- Tool/ledger/control batch: not completed; exceeded the 110-second test timeout. No pass/fail result is assigned.

### Current audit status

The project is not proven solid. Several focused lanes pass, while Work Tree behavior, Backpack/SOCK behavior, source classification, and legacy data-connector evidence are confirmed work areas. Two large test lanes remain unverified because they timed out. No repair has been made from these findings.
