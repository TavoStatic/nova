# NYO System Operations

## Environment

- Workspace root: `C:\Nova`
- Python environment: `C:\Nova\.venv`
- Main policy file: `C:\Nova\policy.json`
- Runtime state: `C:\Nova\runtime`
- Logs: `C:\Nova\logs`

## Quick Start

Install dependencies:

```powershell
C:\Nova\.venv\Scripts\python.exe -m pip install -r C:\Nova\requirements.txt
```

Run preflight:

```powershell
C:\Nova\nova.cmd doctor
```

Run the Nova runtime core:

```powershell
C:\Nova\nova.cmd run
```

Run the NYO System web UI:

```powershell
C:\Nova\nova.cmd webui --host 127.0.0.1 --port 8080
```

Run a smoke cycle:

```powershell
C:\Nova\nova.cmd smoke --fix
```

## Typical Startup Sequence

1. `nova.cmd doctor`
2. `nova.cmd run`
3. `nova.cmd webui-start --host 127.0.0.1 --port 8080`
4. `C:\Nova\.venv\Scripts\python.exe C:\Nova\health.py check`

## Common Commands

```powershell
C:\Nova\nova.cmd help
C:\Nova\nova.cmd doctor --fix
C:\Nova\nova.cmd test
C:\Nova\nova.cmd webui-start --host 127.0.0.1 --port 8080
C:\Nova\nova.cmd webui-status --port 8080
C:\Nova\nova.cmd webui-stop
```

## Central Backend Command Console

Any new backend operation should be wired through the control console instead of ad hoc manual shell steps.

1. Add a command entry in `C:\Nova\backend_command_deck.json`.
2. Open NYO control (`/control`) and use **Backend Command Console** in the **Tools** tab.
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

1. Verify `GET /api/control/status` still exposes the current truth for sessions, memory, tool activity, action-ledger state, guard/core state, and health score.
2. Verify `POST /api/control/action` still returns the expected payload shape for `refresh_status`, `self_check`, and any policy or runtime action you changed.
3. Verify the operator console still points at the live control endpoints and still exposes the tabs operators use: Overview, Operations, Sessions, and Logs.
4. If you changed session lifecycle behavior, verify session counts, session deletion, and any session-end telemetry still show up in the control surface.
5. If you changed reflection, supervisor, or telemetry behavior, verify the control payload still reflects the new fields or summaries operators need.

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
C:\Nova\.venv\Scripts\python.exe -m unittest discover -s C:\Nova\tests
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
- `run_tools.py`: tool-assisted API chat runner
- `chat_client.py`: CLI chat client for `/api/chat`
- `nova_guard.py`: supervisor/heartbeat management