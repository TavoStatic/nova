# Nova Status

Date: 2026-05-18

## Current Read

Nova is in a release-candidate posture for the current base runtime source.

Current evidence:

- latest source commit: `ccc2767 Close Nova intent and release lanes`
- latest package artifact: `runtime/exports/release_packages/nyo-system-base-rc-2026.05.18.23-proof-shape-closed-20260518_203219.zip`
- release validation result: `pass-with-notes`
- blocking release issues: none
- promotion judgment: `ready`, `already_promoted`
- release readiness: `ready-with-notes`
- Work Tree: `Signal Intake: Runtime Governance` is `complete`, with `0` open tasks
- operator help surface reports no active stuck point
- regression status: `OK`
- validation artifact truth: `ok`

This is not final broad production language yet. The package is still waiting on independent fresh-machine or VM validation and the interactive `nova run` front door was not exercised by the noninteractive release validator.

## Closed Lanes

The current code/release evidence closes these four lanes:

- Chat intent core: CLI and HTTP chat routing now carry turn intent, continuation state, and context before deciding whether a tool or runtime self-report is needed.
- Proof reply shape: grounded self-report replies use live control status and Work Tree evidence, and completed branches no longer leak as current stuck work.
- OS capability chain: registered PowerShell capabilities now run through a contract chain of registry, hash verification, argument validation, authority check, script execution, ledger evidence, and result judgment.
- Operator outbox: Work Tree, autonomy pressure, and OS capability gaps can surface durable operator notices instead of disappearing or waiting for a user chat turn.

These lanes are source-backed by:

- `routing/context_router.py`
- `services/nova_turn_heuristics.py`
- `services/nova_planner_contract.py`
- `services/nova_reply_sequence.py`
- `services/nova_grounded_self_report.py`
- `services/operator_outbox.py`
- `services/os_capability_registry.py`
- `services/os_script_controller.py`
- `services/os_capability_operator_outbox.py`
- `tools/os_capabilities/os_capabilities.json`
- `tools/os_capability_tool.py`

## Current Validation

Full regression:

```powershell
.\.venv\Scripts\python.exe scripts\run_regression.py all
```

Result:

- unit lane: `528` tests, `OK`, `1` skipped
- behavior lane: `561` tests, `OK`, `100` skipped
- integration lane: `84` tests, `OK`
- `runtime/regression_status.json`: `status=OK`
- test profile inventory: no gaps, no drift, no unclassified tests
- validation artifact truth: no hidden LLM-unavailable failure

Release validation for `.23`:

- `nova package-verify .`: passed inside extracted package
- `nova install`: passed inside extracted package
- `nova doctor`: passed
- `nova runtime-status`: passed
- `nova wiring-check --offline`: passed, `72` checks, `0` failed
- `nova smoke-base --fix`: passed
- `nova test`: passed
- temporary web UI start/stop validation: passed

Nonblocking notes from release validation:

- fresh-machine or VM independence is not proven by same-machine extracted-package validation
- `nova run` interactive front door was not exercised by the noninteractive validation runner

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
- interactive `nova run` validation against the current artifact
- Git LFS installation/configuration for Piper assets on development and release machines
- a production packaging decision for whether Piper remains bundled or moves to a bootstrap-fetch path
- a follow-up assessment of LEAH and the control panel before shifting momentum there

## Git And Asset Notes

The current source commit intentionally excludes local Piper binary dirt.

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
