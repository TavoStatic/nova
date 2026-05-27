# Nova Status

Date: 2026-05-20

## Current Read

Nova is in an active source-refactor posture with a current validated release artifact.
It is not a final production declaration because independent fresh-machine or VM proof remains open.

Current evidence:

- current source state: large uncommitted routing/reply/tooling refactor in the working tree
- latest full regression evidence lives in `runtime/regression_status.json`
- release build, verify, validation, and promotion evidence live in `runtime/exports/release_packages/release_ledger.jsonl`
- latest observed release validation evidence lives in `runtime/validation/release/latest_release_validation.json`
- release validation result for a candidate is not valid unless the full-regression gate passes first
- latest release-clean pass produced a promoted `ready-with-notes` artifact; read the ledger for the exact artifact name
- installed runtime after validation: guard, core, and web UI are running

Release validation now treats a missing, stale, or red `runtime/regression_status.json` as a blocking issue. Use the runtime ledger and validation record for the exact current artifact name instead of treating this document as a release tag.

## Implemented Lanes

The current codebase contains these source-backed lanes:

- Chat intent core: CLI and HTTP chat routing carry turn intent, continuation state, and context before deciding whether a tool or runtime self-report is needed.
- Proof reply shape: grounded self-report replies use live control status and Work Tree evidence, and completed branches no longer leak as current stuck work.
- OS capability chain: registered PowerShell capabilities run through registry contracts, hash verification, argument validation, authority checks, script execution, ledger evidence, and result judgment.
- Operator outbox: Work Tree, autonomy pressure, and OS capability gaps can surface durable operator notices instead of disappearing or waiting for a user chat turn.
- Release validation gate: extracted-package validation now requires fresh full regression truth before the release result can pass.
- Release front-door proof: extracted-package validation exercises `nova run` launch/exit for the base target, and exercises a scripted turn when the runtime/Ollama target is included.
- OS capability evidence visibility: OS capability ledger evidence is surfaced through control status, Work Tree ingestion, root inventory, and wiring closure without treating old stale probes as live pressure.

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
- `services/operator_outbox.py`
- `services/os_capability_registry.py`
- `services/os_script_controller.py`
- `services/os_capability_operator_outbox.py`
- `services/release_validation.py`
- `services/control_status.py`
- `services/work_tree_signal_ingestion.py`
- `services/nova_wiring_inventory.py`
- `services/nova_root_inventory.py`
- `tools/os_capabilities/os_capabilities.json`
- `tools/os_capability_tool.py`

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

- readiness: `ready-with-notes`
- validation result: `pass-with-notes`
- promotion recorded in `runtime/exports/release_packages/release_ledger.jsonl`
- source status: `current`
- source changed after build count: `0`

Nonblocking notes from release validation:

- fresh-machine or VM independence is not proven by same-machine extracted-package validation
- model-backed `nova run` conversation proof is required only when the runtime/Ollama target is included

## Current Architecture Posture

Nova is no longer only a chat runtime. It is a local AI runtime with:

- CLI and HTTP chat front doors
- a planner/intent spine
- Work Tree task pressure
- operator-visible status and outbox surfaces
- OS capability contracts
- release and validation evidence
- memory, runtime, web, voice, and control surfaces

The current root rule for chat behavior is:

- understand the user's intent first
- do not route only because a word or phrase appeared
- use tools only when the intent and context require a tool
- answer from live evidence when the user asks about Nova's internal state

## Remaining Production Gaps

Before calling this a full production package, finish or prove:

- independent fresh-machine or VM package validation
- model-backed `nova run` scripted-turn validation for an Ollama-included target
- Git LFS installation/configuration for Piper assets on development and release machines
- a production packaging decision for whether Piper remains bundled or moves to a bootstrap-fetch path
- a follow-up assessment of LEAH and the control panel before shifting momentum there

## Git And Asset Notes

The current source tree is not clean. Treat this document and `runtime/regression_status.json` as resume truth, not as a release tag.

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
