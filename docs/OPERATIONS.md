<!--
NOVA_DOC
category: subsystem
authority: active_working
last_session: 2026-08-05
last_agent: claude-cowork
session_state: needs_update
next_step: review operational runbook for accuracy
open: none
-->

# Nova SYSTEMS Operations

## Environment

- Workspace root: `C:\Nova`
- Python environment: `C:\Nova\.venv`
- Main policy file: `C:\Nova\policy.json`
- Runtime state: `C:\Nova\runtime`
- Logs: `C:\Nova\logs`

## Quick Start

Bootstrap the local package environment:

```powershell
C:\Nova\nova.cmd install
```

Install dependencies:

```powershell
C:\Nova\.venv\Scripts\python.exe -m pip install -r C:\Nova\requirements.txt
```

Run preflight:

```powershell
C:\Nova\nova.cmd doctor
```

Run Nova under guard supervision:

```powershell
C:\Nova\nova.cmd guard
```

Run the core directly only when guard supervision and periodic guard-launched maintenance are intentionally not wanted:

```powershell
C:\Nova\nova.cmd run
```

Run the Nova SYSTEMS web UI:

```powershell
C:\Nova\nova.cmd webui --host 127.0.0.1 --port 8080
```

Run a smoke cycle:

```powershell
C:\Nova\nova.cmd smoke-base --fix
C:\Nova\nova.cmd smoke --fix
```

Run the current curated regression loop:

```powershell
C:\Nova\.venv\Scripts\python.exe C:\Nova\scripts\run_regression.py all
```

Run the current release-validation loop after building a candidate:

```powershell
C:\Nova\nova.cmd package-build --label <label>
C:\Nova\nova.cmd package-verify
C:\Nova\nova.cmd package-readiness
C:\Nova\.venv\Scripts\python.exe C:\Nova\scripts\validate_release_package.py
C:\Nova\nova.cmd package-promote --record runtime\exports\release_packages\validation_records\<candidate-validation-record>.md --result pass-with-notes
```

## Typical Startup Sequence

1. `nova.cmd install`
2. `nova.cmd doctor`
3. `nova.cmd guard`
4. `nova.cmd webui-start --host 127.0.0.1 --port 8080`
5. `C:\Nova\.venv\Scripts\python.exe C:\Nova\health.py check`

## Common Commands

```powershell
C:\Nova\nova.cmd help
C:\Nova\nova.cmd install
C:\Nova\nova.cmd doctor --fix
C:\Nova\nova.cmd guard
C:\Nova\nova.cmd run
C:\Nova\nova.cmd webui-start --host 127.0.0.1 --port 8080
C:\Nova\nova.cmd webui-status --port 8080
C:\Nova\nova.cmd webui-stop
C:\Nova\nova.cmd runtime-status
C:\Nova\nova.cmd smoke-base --fix
C:\Nova\nova.cmd smoke --fix
C:\Nova\nova.cmd smoke-runtime
C:\Nova\nova.cmd test
C:\Nova\nova.cmd wiring-check [--offline]
C:\Nova\nova.cmd time                    # temporal review: assess calendar pressure
C:\Nova\nova.cmd package-build --label rc1
C:\Nova\nova.cmd package-verify
C:\Nova\nova.cmd package-readiness
C:\Nova\nova.cmd package-status
C:\Nova\nova.cmd package-ledger --count 5
C:\Nova\nova.cmd package-promote --result pass-with-notes --version <version> --note "..."
C:\Nova\nova.cmd installer-build
C:\Nova\nova.cmd installer-verify
C:\Nova\nova.cmd installer-status
C:\Nova\nova.cmd installer-ledger --count 5
C:\Nova\nova.cmd installer-readiness
C:\Nova\nova.cmd installer-promote --result pass-with-notes --note "..."
C:\Nova\nova.cmd release-clean
C:\Nova\nova.cmd subconscious
C:\Nova\nova.cmd operator
C:\Nova\nova.cmd guard
```

## Bootstrap Notes

`nova install` is the canonical bootstrap entrypoint for the current source package.

It will:

1. create `.venv` if needed
2. upgrade `pip`
3. install `requirements.txt`
4. run `doctor.py --fix`

It does not install optional external services such as Ollama or SearXNG.

`nova smoke-base --fix` is the package-level smoke gate that does not require Ollama.

`nova smoke --fix` remains the model-backed runtime smoke gate.

## Control And Leah Surfaces

Once the web UI is running:

- Operator control room: `http://127.0.0.1:8080/control`
- Leah assistant frontend: `http://127.0.0.1:8080/leah`

Key API routes:

| Route | Method | Purpose |
| --- | --- | --- |
| `/api/control/status` | GET | Full live status payload |
| `/api/control/status/surfaces` | GET | Thin status spine used for frequent refresh and Mission/operator summaries |
| `/api/control/policy` | GET | Current policy payload |
| `/api/control/metrics` | GET | Metrics payload |
| `/api/control/work-trees` | GET | Work-tree state |
| `/api/control/pipelines` | GET | Pipeline registry, lane status, and selected pipeline detail |
| `/api/control/sessions` | GET | Session list |
| `/api/control/test-sessions` | GET | Test session list |
| `/api/control/action` | POST | Control actions (self_check, webui_restart, etc.) |
| `/api/health` | GET | Basic health probe |

## Temporal Review

Nova includes a temporal pressure feed that scores operator calendar (ICS) events and surfaces them as work-tree pressure.

Review temporal pressure from the CLI:

```powershell
C:\Nova\nova.cmd time
```

Calendar files live under `runtime/temporal/`. Add or update ICS files there to feed events into the maintenance cycle. The temporal feed runs on a configurable cadence (default 15 minutes) and is reflected in `GET /api/control/status` as `temporal_enabled`, `temporal_feed_status`, `temporal_feed_surfaced_count`, and `temporal_pressure`.

Any new backend operation should be wired through the control console instead of ad hoc manual shell steps.

1. Add a command entry in `C:\Nova\backend_command_deck.json`.
2. Open Nova control (`/control`) and use **Backend Command Console** in the **Tools** tab.
3. Run the command through `backend_command_run` so execution is captured in `runtime/control_action_audit.jsonl`.

Deck command kinds:

- `python_script`: runs `python <workspace-relative-script>`
- `python_module`: runs `python -m <module>`

This keeps backend execution centralized, auditable, and available to operators without code changes to UI routes.

## Health and Diagnostics

```powershell
C:\Nova\.venv\Scripts\python.exe C:\Nova\health.py check
C:\Nova\.venv\Scripts\python.exe C:\Nova\health.py diag
C:\Nova\.venv\Scripts\python.exe C:\Nova\health.py repair
```

## Operator Console Parity Checklist

When Nova core behavior changes, treat the operator console in `nova_http.py` as part of the same release surface.

Run this checklist after changes to routing, session state, policy, telemetry, reflection, or runtime health:

1. Verify `GET /api/control/status/surfaces` carries the thin status contract and `GET /api/control/status` carries the heavier sections without changing owner truth.
2. Verify `POST /api/control/action` still returns the expected payload shape for `refresh_status`, `self_check`, and any policy or runtime action you changed.
3. Verify the operator console still points at the live control endpoints and still exposes the tabs operators use: Overview, Operations, Sessions, and Logs.
4. If you changed session lifecycle behavior, verify session counts, session deletion, and any session-end telemetry still show up in the control surface.
5. If you changed reflection, supervisor, or telemetry behavior, verify the control payload still reflects the new fields or summaries operators need.

Control-status cache behavior:

- Successful policy mutations through `POST /api/control/action` must invalidate the cached `GET /api/control/status` payload before returning so provider priority, endpoint, memory scope, and related governance values are visible on the next refresh.
- Successful `POST /api/chat` and `POST /api/chat/resume` requests must also invalidate the cached control-status payload so provider telemetry and last-hit summaries update immediately after live chat traffic.
- When validating provider routing, read `GET /api/control/status` immediately after both a governance mutation and a chat turn; a stale result after either path is a regression.

Search-provider runtime notes:

- Search-provider priority is now limited to `wikipedia`, `stackexchange`, and `general_web`. Code or repository discovery prompts should fall back to normal web research rather than requiring a separate GitHub-backed provider.
- The SearXNG probe attempts the configured local endpoint first, then falls back across localhost `8080` and `8081` when the configured host is local. If the control surface reports an `8081` failure while policy shows `http://127.0.0.1:8080/search`, that usually means the probe repaired or compared against a previously configured local endpoint rather than a different active policy value.
- For local SearXNG validation, use the `search_endpoint_probe` control action or inspect the `checked_endpoints`, `resolved_endpoint`, and `note` fields in the probe payload before assuming the policy itself is wrong.

Focused operator-console regression:

```powershell
C:\Nova\.venv\Scripts\python.exe -m unittest tests.test_http_session_manager
```

## Memory Operations

```powershell
C:\Nova\.venv\Scripts\python.exe C:\Nova\memory.py stats
C:\Nova\.venv\Scripts\python.exe C:\Nova\memory.py audit --query "student reporting timeline"
```

## Repo Policy

Local-generated state is not source of truth and should stay out of normal Git history.

- local-only: `runtime/`, `logs/`, `memory/`, `knowledge/web/`, `*.sqlite`, `LAST_SESSION.json`, test caches, local archives, and ad hoc run outputs
- source-controlled until packaging changes: shipped Piper/TTS runtime assets under `piper/` and `tts/`

If the repo later gains a documented asset bootstrap or download step, those shipped assets can move into the local-only bucket in a separate policy change.

Piper asset note:

- Piper binaries are tracked through Git LFS pointers.
- Development and release machines should have Git LFS installed before checkout or push work.
- If Git LFS is missing, valid materialized binaries can appear as modified even when their hashes match the pointers.
- Do not commit Piper binary payloads as ordinary Git changes unless the packaging policy intentionally changes.

Expected setup:

```powershell
git lfs install
git lfs pull
```

Current policy supports explicit memory scopes:

- `private`: per-user only
- `shared`: shared memory only
- `hybrid`: shared plus current user memory

Bundled domain-specific knowledge has been reduced. Public repo behavior should assume domain packs are optional operator-provided inputs rather than shipped product content.

## Test Commands

Replay a stored parity session through both CLI and HTTP paths:

```powershell
C:\Nova\.venv\Scripts\python.exe C:\Nova\scripts\run_test_session.py gus_profile_test.json
```

Session definitions live under `tests/sessions/`. Runner outputs are written under `runtime/test_sessions/`.

Run the full automated suite:

```powershell
C:\Nova\.venv\Scripts\python.exe C:\Nova\scripts\run_regression.py all
```

Run the focused HTTP/privacy slice:

```powershell
C:\Nova\.venv\Scripts\python.exe -m unittest \
  tests.test_http_identity_chat \
  tests.test_http_session_manager \
  tests.test_http_resume_pending \
  tests.test_http_chat_persistence \
  tests.test_http_privacy_guards \
  tests.test_memory_scope
```

## Files Worth Knowing

- `nova_core.py`: core orchestration, policy, memory, tools, teach flow
- `nova_http.py`: runtime console, operator console, auth, session APIs
- `memory.py`: SQLite-backed memory storage and recall
- `run.py`: voice chat front door using the shared voice interaction service
- `run_tools.py`: voice/tool runner and registered-tool listing helper
- `nova_guard.py`: supervisor/heartbeat management
- `tools/os_capabilities/os_capabilities.json`: registered OS capability contracts
- `services/operator_outbox.py`: durable Nova-to-operator notice lane
