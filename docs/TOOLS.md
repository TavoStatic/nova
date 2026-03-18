# Nova Tools

## Tool Contract

Nova now has a first-pass tool scaffold under `tools/`:

- `tools/base_tool.py`: shared `NovaTool`, `ToolContext`, and `ToolInvocationError`
- `tools/registry.py`: manifest-backed registry and structured tool-event logging
- `TOOL_MANIFEST.json`: declarative inventory of registered tools and actions
- `runtime/tool_events.jsonl`: append-only execution telemetry for command-center and audit use

The active rule is: new tools should register through the shared contract instead of adding more ad hoc `if command == ...` branches.

Core execution now follows that rule for local filesystem, vision, and health-style operator actions as well. Those paths are mediated in `nova_core.py` through the shared registry/context layer instead of open-coded direct subprocess and file handling.

Per-tool metadata is now explicit at both the class and manifest level:

- safe vs unsafe
- local vs networked
- read-only vs mutating
- user-scope vs system-scope
- admin-required vs normal operator access

The patch tool is now the canonical example of a mutating, admin-gated, system-scope tool.

## Current Registered Tools

- `filesystem`: `ls`, `read`, `find`
- `patch`: `preview`, `list_previews`, `show`, `approve`, `reject`, `apply`, `rollback`
- `vision`: `screen`, `camera`
- `research`: `web_fetch`, `web_search`, `web_research`, `web_gather`
- `system`: `health_check`, `doctor`, `diag`

## Current Documented Capabilities

Core capability inventory today still includes:

- web access
- file read
- file search
- vision
- speech-to-text
- text-to-speech
- HTTP chat and control-room administration
- managed chat users and memory-scope administration
- weather, research, and session-aware deterministic command flows

## Operational Tooling Already Present in the Repo

- browser chat UI and control room via `nova_http.py`
- file helpers in `agent.py`
- web research and gather flows in `nova_core.py`
- voice/tool orchestration and registry dispatch in `run_tools.py`
- health, doctor, smoke, and regression flows in launcher scripts

## Operator Entry Points

- `python run_tools.py --list-tools`
- `python run_tools.py --tool filesystem --args-json "{""action"": ""ls""}"`
- `nova tools`

## Observability

- tool execution events append to `runtime/tool_events.jsonl`
- the control-room status payload exposes recent tool-event counts and the last observed tool invocation
- diagnostics bundle export now includes a summarized tool-event section
- status now includes success, failure, and denied counts plus average latency and last-error summary data
- per-turn decision routing now lands in `runtime/actions/*.json` with ordered route traces and a compact route summary

## Patch Governance

Self-patching now has an explicit tool contract rather than remaining a raw special-case path.

- tool name: `patch`
- scope: system
- mutating: true
- admin required: true
- policy surface: `patch.enabled`, `patch.allow_force`, `patch.strict_manifest`

CLI/core patch commands still execute in local operator-admin context, but they now pass through the shared registry and event logging boundary.

## Central Rule

Any new Nova tooling should be documented here and referenced from [TOOLING_ROADMAP.md](TOOLING_ROADMAP.md).