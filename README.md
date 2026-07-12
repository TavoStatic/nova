# NYO AI SYSTEMS

Nova is a local-first Windows AI runtime with interactive chat, governed tools, durable memory, Work Tree task state, background maintenance, autonomous action selection, operator control surfaces, and inspectable evidence.

Public brand: **NYO AI SYSTEMS**. Internal runtime name: `Nova`.

## What Runs

Nova is not one process:

- `nova_core.py`: direct local core, CLI/voice runtime, heartbeat, memory/tool compatibility surface
- `nova_guard.py`: core supervision, heartbeat failure handling, restart lifecycle, maintenance launch
- `nova_http.py`: separate Control Room and Leah HTTP runtime on port 8080 by default
- `autonomy_maintenance.py`: subconscious, Kidney, queue, Work Tree, Mission, orchestrator, regression, and cycle evidence

The main command front door is `nova.cmd` -> `nova.ps1`.

## Feedback Loop

On a normal maintenance cycle Nova:

1. gathers owner evidence from runtime, queues, tests, release state, temporal inputs, and reflection layers
2. converts actionable pressure into Work Tree branches and tasks
3. composes a Mission verdict from operations and owner truth
4. asks the orchestrator for the next bounded action
5. applies the execution gate and tool/Work Tree contracts
6. records evidence and refreshes Signal Intake and Mission

Mission is a cycle verdict layer inside this loop. Work Tree owns task truth; validation, regression, release, data, and runtime services own their evidence.

## Major Systems

- conversation intent, planner, fulfillment, reply, and action ledger
- Work Tree and Signal Intake
- Mission, autonomy orchestrator, and execution gate
- memory, identity bootstrap, retention, and learning
- direct tools and contract-governed OS capabilities
- subconscious simulation and generated test sessions
- Kidney cleanup and retention
- SOCK hardware/model compatibility
- patch previews, codegen bridge, rollback, and release governance
- control-room status hydration and operator outbox
- data-pipeline framework, vendor-neutral Ed-Fi core, and BISD lane
- voice, TTS, vision, web research, weather/location, and temporal feed
- compact regression, source-profile inventory, generated tests, and validation truth

## Start

```powershell
.\nova.cmd install
.\nova.cmd doctor
.\nova.cmd guard
.\nova.cmd webui-start --host 127.0.0.1 --port 8080
```

Direct core without guard supervision:

```powershell
.\nova.cmd run
```

Open:

- Control Room: `http://127.0.0.1:8080/control`
- Leah: `http://127.0.0.1:8080/leah`

## Trust Order

Use runtime owners for live truth:

- `runtime/autonomy_maintenance_state.json`
- `runtime/autonomy_maintenance.log`
- `runtime/_internal/work_tree.db`
- `runtime/autonomy_orchestrator_ledger.jsonl`
- `runtime/operator_outbox.jsonl`
- `runtime/tool_events.jsonl`
- `runtime/regression_status.json`
- `runtime/validation/release/latest_release_validation.json`
- `runtime/exports/release_packages/release_ledger.jsonl`

Documentation explains ownership and contracts. It does not override newer runtime evidence.

## Documentation

- [Code-truth audit](docs/CODE_TRUTH_AUDIT_2026-07-12.md)
- [System map](docs/SYSTEM_MAP.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Autonomy and Mission](docs/AUTONOMY_AND_MISSION.md)
- [Services index](docs/SERVICES_INDEX.md)
- [Function index](docs/FUNCTION_INDEX.md)
- [Test ecosystem](docs/TEST_ECOSYSTEM.md)
- [Operations](docs/OPERATIONS.md)
