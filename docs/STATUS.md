# Nova Status

Date: 2026-06-14

## Current Read

Nova is at full operational health with a clean source tree, zero wiring gaps, and zero source-root classification gaps.
Self-check is 22/22 passing, health score 100, no alerts, work-tree truth clear.

The latest promoted artifact is from 2026-06-13. Source has advanced since that build (three commits on 2026-06-14), so a new package build is the only remaining lifecycle step before the next promotion.

Current evidence:

- current source state: `codex/push-prep` branch; all fixes committed and pushed
- runtime health: self_check 22/22, health score 100, no alerts, work-tree truth clear
- wiring check: `nova wiring-check --offline` → 76 checks, 0 failed
- source-root gap: 0 unclassified source files
- latest full regression evidence lives in `runtime/regression_status.json`
- release build, verify, validation, and promotion evidence live in `runtime/exports/release_packages/release_ledger.jsonl`
- latest observed release validation evidence lives in `runtime/validation/release/latest_release_validation.json`
- release validation treats a missing, stale, or red `runtime/regression_status.json` as a blocking issue

## What Changed Since 2026-06-11

Three targeted commits landed on 2026-06-14:

**`10ad49a`** — Fix work tree stuck tasks: bad find path + classify temporal service files + wire intent understanding
- Fixed bad path in `_root_closure_inventory_signals` task 3
- Registered four temporal service files in root inventory
- Built `services/nova_intent_understanding.py` — multi-level intent classifier
- Wired intent understanding into `execute_reply_sequence` and planner
- Rewired learning loop from `mem_add` to Work Tree signals

**`bb620bf`** — Wire SOCK hardware profile keys into status payload to close wiring gap
- Added `get_sock_status_keys()` TTL-cached accessor in `services/sock_service.py`
- Injected `sock_hardware_profile`, `sock_recommendation`, `sock_policy_diff` into `control_status.py` payload before wiring inventory build
- `hardware_profile` surface now `status_visible: True`; gap_count dropped from 1 to 0

**`123960c`** — Classify intent understanding service in source root inventory
- Fixed source-root classification in `nova_root_inventory.py`
- `nova_intent_understanding.py` no longer unclassified; source-root gap now 0

## Implemented Lanes

The current codebase contains these source-backed lanes:

- Chat intent core: CLI and HTTP chat routing carry turn intent, continuation state, and context before deciding whether a tool or runtime self-report is needed.
- Intent understanding: multi-level intent classifier (`nova_intent_understanding.py`) runs on every turn; low-confidence turns surface Work Tree governance pressure.
- Proof reply shape: grounded self-report replies use live control status and Work Tree evidence, and completed branches no longer leak as current stuck work.
- OS capability chain: registered PowerShell capabilities run through registry contracts, hash verification, argument validation, authority checks, script execution, ledger evidence, and result judgment.
- Operator outbox: Work Tree, autonomy pressure, and OS capability gaps can surface durable operator notices instead of disappearing or waiting for a user chat turn.
- Release validation gate: extracted-package validation now requires fresh full regression truth before the release result can pass.
- Release front-door proof: extracted-package validation exercises `nova run` launch/exit for the base target, and exercises a scripted turn when the runtime/Ollama target is included.
- OS capability evidence visibility: OS capability ledger evidence is surfaced through control status, Work Tree ingestion, root inventory, and wiring closure.
- Temporal feed: operator ICS calendar files are parsed, scored by proximity/confidence/importance, and surfaced as work-tree pressure via the maintenance feed; `nova time` exposes review at the CLI.
- Leah frontend: a separate Leah assistant chat UI is served at `/leah` alongside the operator control room.
- Autonomy orchestrator: `services/autonomy_orchestrator.py` drives work-tree execution cycles and maintenance action selection.
- Regression governance: `services/regression_lanes.py` owns lane membership; `services/regression_profile_inventory.py` detects profile drift, gaps, and unclassified tests.
- Wiring inventory: `services/nova_wiring_inventory.py` performs end-to-end closure analysis and feeds the wiring-check CLI gate and control-room wiring panel.
- SOCK hardware profiling: `services/sock_service.py` scans hardware, recommends models, and diffs against policy; `get_sock_status_keys()` surfaces results in the status payload with TTL caching.

Current source-backed files include:

- `services/nova_routing_support.py`
- `services/nova_turn_intent_trace.py`
- `services/nova_reply_sequence.py`
- `services/nova_reply_runtime.py`
- `services/nova_reply_context_contract.py`
- `services/nova_fallback_flow.py`
- `services/nova_ollama_chat.py`
- `services/nova_grounded_self_report.py`
- `services/nova_self_evidence_reply.py`
- `services/nova_intent_understanding.py`
- `services/operator_outbox.py`
- `services/os_capability_registry.py`
- `services/os_script_controller.py`
- `services/os_capability_operator_outbox.py`
- `services/release_validation.py`
- `services/control_status.py`
- `services/sock_service.py`
- `services/work_tree_signal_ingestion.py`
- `services/nova_wiring_inventory.py`
- `services/nova_root_inventory.py`
- `services/autonomy_orchestrator.py`
- `services/autonomy_execution_gate.py`
- `services/regression_lanes.py`
- `services/regression_profile_inventory.py`
- `services/validation_artifact_truth.py`
- `services/nova_temporal_service.py`
- `services/nova_calendar_ingestion.py`
- `services/nova_scheduler.py`
- `services/leah_frontdoor.py`
- `services/runtime_control.py`
- `services/runtime_restart_provenance.py`
- `services/port_ownership.py`
- `services/storage_watch.py`
- `tools/os_capabilities/os_capabilities.json`
- `tools/os_capability_tool.py`
- `tools/temporal_review_tool.py`
- `scripts/run_time.py`

## Current Validation

Full regression:

```powershell
.\.venv\Scripts\python.exe scripts\run_regression.py all
```

Latest recorded result should be read from `runtime/regression_status.json`. A valid promotion candidate requires:

- unit lane: `OK`
- behavior lane: `OK`
- integration lane: `OK`
- `runtime/regression_status.json`: `status=OK`
- test profile inventory: no gaps, no drift, no unclassified tests
- validation artifact truth: no hidden LLM-unavailable failure

Expected current regression shape:

- status: `OK`
- lanes: `unit`, `behavior`, `integration`
- test profile inventory: no gaps, no drift, no unclassified tests
- validation artifact truth: `ok`

Release validation:

- package verification must pass for the selected artifact
- release validation must pass or pass-with-notes for the selected artifact
- the validation record must match the selected artifact
- promotion/readiness status must be read from `runtime/exports/release_packages/release_ledger.jsonl`

Expected current release shape:

- readiness: `ready-with-notes` (pending new build after 2026-06-14 source changes)
- validation result: `pass-with-notes`
- promotion recorded in `runtime/exports/release_packages/release_ledger.jsonl`
- source status: `source-changed-after-build` (lifecycle only — next build clears this)
- lifecycle note: latest promoted artifact is from 2026-06-13; source advanced three commits on 2026-06-14

Nonblocking notes from release validation:

- fresh-machine or VM independence is not proven by same-machine extracted-package validation
- model-backed `nova run` conversation proof is required only when the runtime/Ollama target is included

## Current Architecture Posture

Nova is no longer only a chat runtime. It is a local AI runtime with:

- CLI and HTTP chat front doors (`run.py`, `nova_http.py`)
- Leah assistant frontend at `/leah`
- a planner/intent spine with multi-level intent classification
- Work Tree task pressure with autonomous orchestration
- operator-visible status, outbox, and temporal feed surfaces
- OS capability contracts
- SOCK hardware profiling with TTL-cached status payload injection
- release and installer validation evidence
- temporal calendar pressure scoring and maintenance feed
- regression governance with lane membership and profile drift detection
- memory, runtime, web, voice, and control surfaces

The current root rule for chat behavior is:

- understand the user's intent first
- do not route only because a word or phrase appeared
- use tools only when the intent and context require a tool
- answer from live evidence when the user asks about Nova's internal state

## Remaining Production Gaps

Before calling this a full production package, finish or prove:

- rebuild release artifact from 2026-06-14 source and promote
- independent fresh-machine or VM package validation
- model-backed `nova run` scripted-turn validation for an Ollama-included target
- Git LFS installation/configuration for Piper assets on development and release machines
- a production packaging decision for whether Piper remains bundled or moves to a bootstrap-fetch path
- a follow-up assessment of LEAH and the control panel before shifting momentum there

## Git And Asset Notes

The current source tree is clean on `codex/push-prep`. The branch is 3 commits ahead of what the last promoted artifact was built from.

The repo tracks these Piper assets through Git LFS pointers:

- `piper/espeak-ng.dll`
- `piper/models/en_US-lessac-medium.onnx`
- `piper/onnxruntime.dll`
- `piper/onnxruntime_providers_shared.dll`
- `piper/piper.exe`
- `piper/piper_phonemize.dll`

On the current machine, `git lfs` is not installed and local Git LFS filters were configured to pass files through. The working binaries matched the hashes and sizes declared by the LFS pointers, so they were local materialized payloads rather than source changes. They were marked `skip-worktree` locally to keep Git status clean without committing binary payloads.

Proper fix for another machine:

```powershell
git lfs install
git lfs pull
```

## Resume Order

Use this order when resuming:

1. `docs/STATUS.md`
2. `runtime/regression_status.json`
3. `runtime/validation/release/latest_release_validation.json`
4. `runtime/exports/release_packages/release_ledger.jsonl`
5. `docs/BASE_PACKAGE_READINESS.md`
6. `docs/ARCHITECTURE.md`
7. `docs/SERVICES_INDEX.md`

`This_is_nova` remains append-only build history. It is not the current authority for release readiness, policy, runtime state, or test results.
