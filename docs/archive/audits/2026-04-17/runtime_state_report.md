# Runtime State Report

## Historical Use

Historical audit snapshot from 2026-04-17.

This report reflects one runtime-state audit pass and is not the current runtime authority.

For current repo-facing truth, use:

1. `This_is_nova`
2. `docs/CURRENT_TRUTH_2026-04-18.md`
3. active code owners and live runtime behavior

The content below is preserved as an audit artifact.

Audit mode: baseline scan only. No runtime logic, cleanup, or repair work was performed during this pass.

## Runtime truth snapshot

- Live HTTP service truth:
  - `nova_http.py` is running as one Windows parent/child process family, which is the expected launcher pattern on this machine rather than duplicate web runtimes.
  - Public health endpoint `GET /api/health` is live and returned:
    - `ok=true`
    - `ollama_api_up=true`
    - `chat_model=llama3.1:8b`
    - `memory_enabled=true`
    - `chat_login_enabled=false`
- Runtime artifact truth:
  - `runtime/http.pid` is current and points at the live HTTP listener PID `62512`.
  - `runtime/http_runtime.json` is stale and contradictory. It still reports older PID `26180`, `started=false`, and a stopped timestamp even though the HTTP service is live.
- Core and guard artifact truth:
  - `runtime/guard.stop`, `runtime/guard.lock`, `runtime/core_state.json`, `runtime/core.heartbeat`, `runtime/kidney_status.json`, and `runtime/kidney_last_run.json` were absent during this scan.
  - `runtime/pulse_snapshot.json` exists but is stale, with `generated_at` still at `2026-04-14 00:12:43`.

## Execution state artifacts

- `runtime/autonomy_maintenance_state.json` is present and gives stronger execution truth than older reports:
  - `last_regression_status=FAILED`
  - `last_regression_date=2026-04-17`
  - `last_auto_apply=skipped_no_generated_defs`
  - `last_fallback_overuse_score=0.97`
  - generated work queue state is `blocked`
- The same file also shows stale worker timing:
  - `runtime_worker.last_started_at=2026-04-14 13:31:06`
  - `runtime_worker.last_cycle_status=ok`
  - `runtime_worker.cycle_count=206`
- Baseline interpretation: the autonomy-maintenance ledger is alive as a record of prior execution, but it does not prove an actively healthy current maintenance worker.

## Control surface truth

- `GET /api/control/status` is reachable, but the currently exposed top-level fields are thin:
  - `core_running=false`
  - `health_score=100`
  - many previously expected summary fields were `null` in this snapshot rather than fully populated.
- Baseline interpretation: the control/status surface exists, but it is not currently a complete authoritative summary of runtime state.

## Runtime conclusion

- Nova is live at the HTTP transport and model layers.
- The strongest runtime contradiction is metadata drift, not service absence:
  - `http.pid` matches the live web runtime.
  - `http_runtime.json` does not.
- Runtime status is currently split across multiple partial truth sources:
  - live process and health probes
  - stale persisted runtime metadata
  - autonomy-maintenance state from a prior failed regression cycle
  - a control/status payload that is reachable but only partially populated.

