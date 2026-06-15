# Nova System Map

**Version:** 2026-06-14 | **Branch:** codex/push-prep | **Health:** 22/22 · Score 100 · Wiring 76/0

This document is the single authoritative reference for every Nova subsystem, process, data store, UI feature, and cross-system interaction. It is intended for operators, developers, and anyone extending or debugging Nova.

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Process Architecture](#2-process-architecture)
3. [Entry Points](#3-entry-points)
4. [Turn Flow — End to End](#4-turn-flow--end-to-end)
5. [Intent Understanding](#5-intent-understanding)
6. [Fulfillment & Routing](#6-fulfillment--routing)
7. [Reply Sequence](#7-reply-sequence)
8. [Memory System](#8-memory-system)
9. [Tool System](#9-tool-system)
10. [Work Tree](#10-work-tree)
11. [Signal Ingestion](#11-signal-ingestion)
12. [Autonomy Orchestrator](#12-autonomy-orchestrator)
13. [Subconscious](#13-subconscious)
14. [Supervisor](#14-supervisor)
15. [OS Capabilities](#15-os-capabilities)
16. [SOCK — Hardware Profiling](#16-sock--hardware-profiling)
17. [Patch System](#17-patch-system)
18. [Regression Governance](#18-regression-governance)
19. [Release Lifecycle](#19-release-lifecycle)
20. [Wiring Inventory](#20-wiring-inventory)
21. [Health & Telemetry](#21-health--telemetry)
22. [Operator Outbox](#22-operator-outbox)
23. [Temporal Feed](#23-temporal-feed)
24. [Voice, STT, and TTS](#24-voice-stt-and-tts)
25. [Vision](#25-vision)
26. [Web Search](#26-web-search)
27. [Data Pipelines](#27-data-pipelines)
28. [Session Management](#28-session-management)
29. [Scheduler & Heartbeat](#29-scheduler--heartbeat)
30. [Knowledge Packs](#30-knowledge-packs)
31. [Control Panel — Full Reference](#31-control-panel--full-reference)
32. [Leah — Full Reference](#32-leah--full-reference)
33. [HTTP API Reference](#33-http-api-reference)
34. [Data Stores](#34-data-stores)
35. [Cross-System Interaction Map](#35-cross-system-interaction-map)
36. [CLI Reference](#36-cli-reference)

---

## 1. System Overview

Nova is a supervised local AI runtime. It runs entirely on a single Windows machine and is designed for personal or small-team use. There is no cloud dependency beyond the Ollama model server running locally.

**Core design principles:**

- Everything is observable. Every action, decision, and state transition writes to a ledger or journal.
- Autonomy is gated. Nova can propose work, but execution requires either operator approval or an explicit policy grant.
- Wiring is verified. Every service surface that exposes a status key is tracked by an inventory check; gaps are detected at build time.
- Fixes go to the root. Nova avoids patching symptoms; signal ingestion routes the root cause to the Work Tree.
- Hardware drives policy. The SOCK subsystem scans the machine and recommends which models to run; policy diffs surface mismatches to the operator.

**Hardware reference (Rogue_One):**

- CPU: AMD Ryzen AI 9 HX 370 w/ Radeon 890M (12 cores, 2 GHz base)
- RAM: 32 GB
- GPU: NVIDIA GeForce RTX 4050 Laptop (6 GB VRAM) — primary inference GPU
- iGPU: AMD Radeon 890M (338 MB) — display/light compute only
- NPU: AMD XDNA 2 (AMD Ryzen AI IPU Device) — detected via PnP; not yet used for inference
- Storage: ~984 GB NVMe, 625 GB used

**Primary models:**

| Role | Model | Notes |
|------|-------|-------|
| Chat + routing | qwen2.5:7b | Served via Ollama |
| Vision | qwen2.5vl:7b | Used by vision tool |
| STT | Whisper medium | CPU or GPU |
| TTS | Piper | Offline neural TTS |

---

## 2. Process Architecture

Nova runs as two cooperating processes managed by a guard/core pattern.

```
nova_guard.py  (nova.cmd "guard" mode)
  └─ spawns and supervises ──► nova_core.py  (the runtime)
                                  ├─ HTTP server (Waitress, port 8090)
                                  ├─ Scheduler loop
                                  ├─ Autonomy maintenance loop
                                  ├─ Heartbeat writer
                                  └─ Subconscious runner
```

**Guard (`nova_guard.py`):** Holds a PID file at `runtime/guard_pid.json` and a lock at `runtime/guard.lock`. Monitors the core process. On unclean exit, guard reads `runtime/restart_intent.json` to determine whether to restart the core or hold. Writes boot history to `runtime/guard_boot_history.json`.

**Core (`nova_core.py`):** The main runtime. Starts Waitress HTTP server, initializes all services, starts the scheduler, and enters the main loop. Writes a heartbeat at `runtime/core.heartbeat` on each cycle. Stores process state at `runtime/core_state.json`.

**Port:** 8090 (default). Port ownership is tracked by `services/port_ownership.py`.

**Stopping:** `nova_stop.py` / `stop_guard.py` writes a stop intent to `runtime/restart_intent.json` and signals the guard. The guard reads the intent and decides whether to restart or cleanly exit.

---

## 3. Entry Points

### 3.1 CLI (`nova.cmd` / `nova.ps1`)

The `nova.cmd` shim delegates to `nova.ps1`, which activates the Python environment and dispatches subcommands:

| Command | Effect |
|---------|--------|
| `nova run` | Start guard + core |
| `nova stop` | Send stop intent to guard |
| `nova restart` | Send restart intent |
| `nova time` | Run the temporal review CLI |
| `nova wiring-check [--offline]` | Run wiring inventory check |
| `nova package-build` | Build release artifact |
| `nova package-verify` | Verify artifact integrity |
| `nova package-validate` | Run validation suite against artifact |
| `nova package-promote` | Promote artifact to release |
| `nova doctor` | Run health diagnostics |
| `nova diag` | Extended diagnostic output |

### 3.2 HTTP Server

Accessible at `http://localhost:8090`. Served by Waitress via `nova_http.py` which wires routes from `nova_http_get_routes.py` and `nova_http_post_routes.py`.

### 3.3 Web UI Entry Points

| Path | Description |
|------|-------------|
| `/` | Redirects to `/control` (authenticated) or `/control/login` |
| `/control` | Operator control panel (password-protected) |
| `/control/login` | Control panel login page |
| `/leah` | Leah chat UI (separate auth) |
| `/leah/login` | Leah login page |

---

## 4. Turn Flow — End to End

A "turn" is one complete request-response cycle initiated from either the Leah chat UI or the CLI.

```
User input (text / voice / upload)
        │
        ▼
[Intent Understanding]          nova_intent_understanding.py
  - classify domain, intent, depth
        │
        ▼
[Planner Contract]              nova_planner_contract.py
  - select route: fulfillment / supervisor / fallback
  - apply policy constraints
        │
        ├─► [Supervisor Check]  supervisor_runtime.py
        │     - owns specific turn types
        │     - returns owned/not-owned signal
        │
        ├─► [Fulfillment Flow]  fulfillment_flow.py
        │     - selects tool(s), calls tool_execution.py
        │     - tools: filesystem, research, system, OS, vision, temporal, patch
        │
        └─► [Fallback Flow]     nova_fallback_flow.py
              - direct Ollama chat when no tool applies
                    │
                    ▼
            [Reply Sequence]    nova_reply_sequence.py
              - builds reply context (nova_reply_context_contract.py)
              - calls Ollama chat (nova_ollama_chat.py)
              - streams or returns response
                    │
                    ▼
            [Turn Finalization] nova_http_turn_finalization.py
              - writes action ledger entry
              - fires memory learning signal
              - fires subconscious probe
              - updates session state
```

**Key files:**

| File | Role |
|------|------|
| `nova_intent_understanding.py` | Multi-level intent classifier |
| `nova_planner_contract.py` | Route selection and policy gating |
| `nova_fulfillment_routing.py` | Dispatches to correct fulfillment handler |
| `fulfillment_flow.py` | Orchestrates tool selection and execution |
| `nova_fallback_flow.py` | Handles unrouted turns via direct LLM |
| `nova_reply_sequence.py` | Assembles and sends reply |
| `nova_http_turn_finalization.py` | Post-turn logging and learning |
| `nova_ollama_chat.py` | Ollama API client |
| `nova_action_ledger.py` | Persistent per-turn action record |

---

## 5. Intent Understanding

**File:** `services/nova_intent_understanding.py`

Nova's intent classifier runs at the start of every turn and classifies the input across three dimensions:

**Domain:** What area of Nova's knowledge does this request touch?
Examples: `memory`, `tools`, `system`, `search`, `conversation`, `temporal`, `vision`, `code`, `policy`.

**Intent:** What action does the user want?
Examples: `query`, `store`, `update`, `delete`, `run`, `analyze`, `summarize`, `configure`, `explain`.

**Depth:** How much work does this request require?
Values: `surface` (quick answer), `moderate` (some reasoning), `deep` (multi-step execution).

The classifier output is passed downstream to the planner contract, where it influences route selection. It is also injected into the reply context so Ollama sees the classified intent when generating a response.

The intent layer is wired into `execute_reply_sequence` via a hook in `nova_runtime_hooks.py` and into the planner via `nova_planner_contract.py`. The status key `intent_understanding_wired` is exposed in the control status payload.

---

## 6. Fulfillment & Routing

**Files:** `nova_fulfillment_routing.py`, `fulfillment_flow.py`, `fulfillment_contracts.py`

Fulfillment is the path taken when a turn has a concrete tool-executable answer. The routing layer selects the most appropriate handler based on intent and domain.

**Routing decision factors:**
- Does the supervisor own this turn? If yes, supervisor handles it.
- Does the intent match a registered tool capability? Route to fulfillment.
- No match: route to fallback (direct LLM chat).

**Fulfillment execution:**
1. Tool is selected from the registry (`tools/registry.py`)
2. Tool is executed via `tool_execution.py` with `tool_execution_contracts.py` validation
3. Tool result is injected into the reply context
4. Reply sequence runs with tool output available

**Tool event summary** is maintained in `runtime/` and exposed in the control status payload as `tool_events_ok`.

**Dynamic replanning (`dynamic_replanner.py`):** If a tool call fails or returns insufficient data, the replanner can invoke a secondary tool or escalate to fallback without failing the turn.

---

## 7. Reply Sequence

**Files:** `nova_reply_sequence.py`, `nova_reply_context_contract.py`, `nova_reply_runtime.py`

The reply sequence assembles the full context package sent to Ollama and handles streaming.

**Context assembly includes:**
- System prompt (from `nova_operational_identity.py` / policy identity)
- Memory context (injected from memory routing)
- Tool result (if fulfillment ran)
- Intent classification
- Session history (rolling window from `conversation_manager.py`)
- Supervisor constraints (if active)
- Safety envelope constraints (`nova_safety_envelope.py`)

**Streaming:** Responses are streamed back to the client via server-sent events (SSE). The HTTP chat runtime (`nova_http_chat_runtime.py`) manages the stream lifecycle.

**Finalization:** After streaming completes, `nova_http_turn_finalization.py` fires:
- Writes to `nova_action_ledger.py` (persistent turn record)
- Emits a `memory_learning` signal to the Work Tree
- Triggers subconscious probe on the completed turn
- Updates session subconscious state

---

## 8. Memory System

Nova's memory is a multi-layer system combining SQLite, disk journals, and an in-memory cache.

### 8.1 Memory Routing (`services/memory_routing.py`)

Routes memory operations to the correct adapter based on scope and type. Scopes include: `conversation`, `identity`, `knowledge`, `episodic`. The active scope can be set by the operator via control action `memory_scope_set`.

### 8.2 Memory Adapter (`services/memory_adapter.py`)

The low-level interface to `nova_memory.sqlite`. Provides read, write, search, and thinning operations. The adapter is wrapped by the routing layer; code above routing never touches the adapter directly.

### 8.3 Memory Health (`services/memory_health.py`)

Periodically checks memory store integrity: row counts, index health, corruption detection. Writes snapshot to `runtime/memory_health_snapshot.json`. Exposed via control status.

### 8.4 Memory Learning (`services/nova_memory_learning.py`)

Triggered after every turn finalization. Evaluates whether the turn produced learnable content (facts, corrections, preferences, episodic markers) and writes new memory records via the adapter. Does not block the turn response; runs as a post-turn hook.

### 8.5 Memory Events (`services/nova_memory_events.py`)

Journal of significant memory operations: stores, deletes, scope changes, corruption events. Appended to `runtime/memory_events.jsonl`. Surfaced in control status for audit.

### 8.6 Identity Bootstrap (`services/memory_identity_bootstrap.py`)

On first boot or identity reset, seeds the memory store with Nova's operational identity: name, role, behavioral commitments, and policy alignment. Governed by `memory_bootstrap_contracts.py` and `memory_bootstrap_judgment.py`. Origin is recorded in `memory_bootstrap_origin.py`.

### 8.7 Memory Thinning (`services/core_thinning.py`)

Background process that prunes low-value or expired memory records to keep the store lean. Thinning is conservative: only removes records below a freshness and relevance threshold.

### 8.8 Identity Memory (`services/identity_memory.py`)

Specialized layer for Nova's persistent self-model: who Nova is, what Nova is committed to, and what Nova has learned about the operator. Survives across sessions and restarts.

### 8.9 Storage (`nova_memory.sqlite`)

SQLite file at the Nova root. Backed by `work_tree.db` for Work Tree state (separate file). Memory DB can fall back to an in-memory database if the file is temporarily unavailable, with disk sync on recovery.

---

## 9. Tool System

Tools are the primary mechanism by which Nova takes concrete action beyond conversation.

### 9.1 Tool Registry (`tools/registry.py`)

Central registry of all available tools. Each tool registers its name, description, parameter schema, and capability tags. The fulfillment router queries the registry to find matching tools for a given intent.

### 9.2 Base Tool (`tools/base_tool.py`)

Abstract base class. All tools implement `run(params)` and expose a `capabilities()` descriptor. Tools validate their own inputs against the `tool_execution_contracts.py` schema before running.

### 9.3 Filesystem Tool (`tools/filesystem_tool.py`)

Read, write, list, and search files within policy-allowed paths. Path access is gated by `policy.json` allow-lists. Writes are journaled. Used for document reading, file organization, and content extraction.

### 9.4 Research Tool (`tools/research_tool.py`)

Orchestrates multi-step web research. Calls the search provider (SearXNG), fetches and parses result pages, synthesizes an answer, and cites sources. Uses `web_research_session.py` for session management. Policy controls which domains are reachable.

### 9.5 System Tool (`tools/system_tool.py`)

Executes system-level queries: process list, memory usage, disk usage, network state, environment variables. Read-only by default. Write-capable operations (e.g., process kill) require explicit policy grant.

### 9.6 OS Capability Tool (`tools/os_capability_tool.py`)

Exposes registered OS capabilities to the fulfillment layer. Capabilities are defined in `tools/os_capabilities/` and registered at startup. Each capability is a named PowerShell or Python script with declared inputs, outputs, and safety level. The tool looks up the requested capability in `os_capability_registry.py` and executes it via `os_script_controller.py`.

### 9.7 Vision Tool (`tools/vision_tool.py`)

Captures a screenshot or accepts an uploaded image and passes it to the vision model (qwen2.5vl:7b via Ollama). Returns a structured description or answers a specific question about the image. Camera capture is handled by `camera.py`.

### 9.8 Temporal Review Tool (`tools/temporal_review_tool.py`)

Reads the temporal feed (calendar events, scheduled items) and surfaces time-sensitive work. Outputs a prioritized list of upcoming obligations with pressure scores. Integrates with the Work Tree to open branches when temporal pressure exceeds threshold. Policy-gated: `temporal_review_enabled` must be true in `policy.json`.

### 9.9 Patch Tool (`tools/patch_tool.py`)

Exposes patch preview, approve, and apply operations to the fulfillment layer. Wraps `services/patch_control.py`. Used when the operator asks Nova to review or apply a pending patch via conversation.

### 9.10 Runtime Processes Tool (`tools/runtime_processes.py`)

Queries the state of Nova's own runtime processes: guard PID, core PID, uptime, restart history. Used for self-diagnostic conversation.

---

## 10. Work Tree

The Work Tree is Nova's persistent task management system. It is the central hub that receives signals from all monitoring subsystems and organizes pending work into an actionable hierarchy.

**Storage:** `work_tree.db` (SQLite) at the Nova root. Schema is migrated automatically on startup.

### 10.1 Data Model

**WorkTree** — a named goal or project. Has a root branch. Statuses: `active`, `complete`, `archived`.

**Branch** — a unit of work within a tree. Branches are hierarchical (parent/child). Key fields:

| Field | Purpose |
|-------|---------|
| `branch_id` | UUID |
| `title` | Human-readable description |
| `bucket` | Category label (e.g., `maintenance`, `signal`, `regression`) |
| `status` | `ready` / `active` / `blocked` / `stalled` / `complete` / `archived` |
| `priority` | Integer 0–100 (higher = more urgent) |
| `score` | Float composite score used for selection |
| `depends_on` | List of branch IDs that must complete first |
| `blocked_by` | List of external blocker IDs |
| `required_tools` | Tools that must be available |
| `allowed_tools` | Tools permitted for this branch |
| `preferred_tool` | Tool to try first |
| `tool_state` | Per-tool status: `ready` / `running` / `failed` / `blocked` |
| `source_type` | What created this branch (e.g., `signal`, `autonomy`, `operator`) |
| `source_key` | The specific signal or action that opened it |
| `source_payload` | Original signal payload for traceability |
| `work_class` | Classification: `investigation`, `fix`, `verification`, `documentation` |
| `actionability` | `immediately_actionable`, `needs_investigation`, `deferred` |
| `resolution_state` | `unresolved`, `in_progress`, `resolved`, `operator_hold` |
| `evidence_count` | Number of signal firings that contributed to this branch |

**Task** — a concrete step within a branch. Statuses: `open`, `active`, `blocked`, `complete`, `dropped`.

### 10.2 Branch Status Transitions

```
READY ──► ACTIVE ──► COMPLETE
  │          │
  │          └──► BLOCKED ──► READY (when blocker clears)
  │
  └──► STALLED (no progress in configured period)
  └──► ARCHIVED (operator or system closes)
```

### 10.3 Tree Selection Logic

When the autonomy orchestrator selects a branch to work, it uses a composite score:

1. Filter to branches with status `READY`
2. Filter to branches whose `depends_on` list has all dependencies complete
3. Filter to branches whose `required_tools` are all available
4. Sort by `score` descending (score incorporates priority, evidence count, age, and pressure)
5. Select the top candidate

### 10.4 Work Tree API (`work_tree.py`)

Key operations:
- `open_branch(tree_id, title, bucket, ...)` — create a new branch
- `close_branch(branch_id)` — mark complete
- `block_branch(branch_id, ...)` — mark blocked
- `advance_task(task_id)` — mark task complete and recalculate branch status
- `get_ready_branches()` — list selectable branches
- `reload_persisted_state()` — reload from SQLite after external change

---

## 11. Signal Ingestion

**File:** `services/work_tree_signal_ingestion.py` (5,679 lines)

Signal ingestion is the monitoring layer that watches Nova's own health, behavior, and environment and translates observed conditions into Work Tree branches.

### 11.1 How It Works

Signal ingestion runs on every autonomy maintenance cycle. It evaluates a set of named signals against the current system state. When a signal fires, it either opens a new branch in the Work Tree or increments the evidence count on an existing branch for the same signal key. When a signal clears, it resolves the corresponding branch.

### 11.2 Signal Categories

**Runtime signals:** guard process dead, core unreachable, heartbeat stale, port conflict, restart loop detected.

**Model signals:** Ollama API down, chat model missing, vision model missing, model performance degraded.

**Memory signals:** memory health failure, memory corruption, identity gap.

**Regression signals:** test profile inventory drift, behavior lane failure, integration lane failure, parity test divergence.

**Patch signals:** patch queue stalled, patch behavioral gate failing, manifest drift.

**Temporal signals:** calendar pressure exceeds threshold, overdue item detected.

**Work Tree signals:** branch stalled beyond threshold, dependency loop detected, operator hold too long.

**Learning signals:** subconscious pressure accumulation, training backlog depth, weak route repeated.

**Hardware signals:** SOCK policy drift (running model mismatches recommended model).

### 11.3 Signal Lifecycle

```
Signal evaluator runs
  ├─► Signal condition TRUE + no existing branch
  │     └─► open_branch() in work_tree.db
  ├─► Signal condition TRUE + existing branch
  │     └─► increment evidence_count
  └─► Signal condition FALSE + existing branch with source_key match
        └─► close_branch() or mark resolved
```

### 11.4 Source Traceability

Every branch opened by signal ingestion records `source_type="signal"`, `source_key=<signal_name>`, and `source_payload=<full signal state dict>`. This makes every open Work Tree branch traceable to the exact condition that created it.

---

## 12. Autonomy Orchestrator

**Files:** `services/autonomy_orchestrator.py`, `services/autonomy_orchestrator_ledger.py`, `services/autonomy_execution_gate.py`, `autonomy_maintenance.py`

The autonomy orchestrator is Nova's decision engine. It runs on a scheduled maintenance cycle and selects the next action to recommend or execute.

### 12.1 Modes

| Mode | Behavior |
|------|---------|
| `advisory` | Recommends actions; does not execute without operator approval |
| `execute` | Executes approved actions autonomously within policy bounds |

Mode is set via control action `memory_scope_set` or the Governance panel. Default: `advisory`.

### 12.2 Decision Types

| Decision | Meaning |
|----------|---------|
| `recommend_action` | An action is proposed for execution |
| `defer_with_reason` | Conditions not right; try again later |
| `block_with_reason` | A hard constraint prevents action |

### 12.3 Cycle Operation

The maintenance cycle runs every 30 seconds (±10% jitter) via `nova_scheduler.py`:

1. Collect evidence: reads full control status payload (guard, runtime, policy, metrics, work tree, queue pressure, temporal feed)
2. Check posture: if system health below `posture_threshold` (default 85), do not act
3. Build candidate actions: enumerate what could be done given current state
4. Score candidates: each candidate is scored against the evidence envelope
5. Select winner: highest score above `recommendation_threshold` (0.55 default)
6. Emit decision: `recommend_action`, `defer_with_reason`, or `block_with_reason`
7. Write ledger: every decision is appended to `runtime/autonomy_orchestrator_ledger.jsonl`
8. Execute (if execute mode): dispatches via `autonomy_execution_gate.py`

### 12.4 Candidate Action Catalog

The orchestrator can propose any action defined in `autonomy_advisory_action_catalog` (from `nova_control_action_dispatcher.py`). The catalog maps action types to their scoring logic, policy requirements, and execution contracts.

**Examples of autonomy-proposable actions:**
- `active_work_tree_run_next` — advance a ready Work Tree branch
- `patch_queue_run_next` — apply next queued patch
- `generated_queue_run_next` — run next generated work item
- `test_session_run` — run a parity test session
- `tail_log` — fetch recent logs for diagnostic review
- `self_check` — run self-check suite

### 12.5 Execution Gate (`autonomy_execution_gate.py`)

Before any autonomy action executes, the gate checks:
- Is the action type in the policy-allowed set?
- Is the runtime healthy enough to execute?
- Is there a conflicting action currently running?
- Does the action require tools that are available?

If any gate condition fails, the action is blocked with a reason and the ledger records the failure.

### 12.6 Ledger (`autonomy_orchestrator_ledger.py`)

Every decision is a JSONL record at `runtime/autonomy_orchestrator_ledger.jsonl` containing: timestamp, decision type, selected action, score breakdown, evidence summary, and the full candidate list with their scores. The control panel's Action Stream and Runtime Timeline panels read from this ledger.

---

## 13. Subconscious

**Files:** `subconscious_runner.py`, `subconscious_live_simulator.py`, `subconscious_route_probe.py`, `subconscious_training_backlog.py`, `subconscious_config.py`, `services/subconscious_runtime.py`, `services/subconscious_review_judgment.py`, `services/subconscious_review_authority.py`, `services/subconscious_work_tree_triage.py`, `services/subconscious_reporting.py`, `services/subconscious_control.py`

Nova's subconscious is a background behavioral self-review process. It does not own turns, does not route decisions, and does not override any runtime component. Its only authority is observation, pressure accumulation, and advisory output.

### 13.1 Charter

The subconscious operates under a strict charter defined in `subconscious_config.py`:

**Mission mode:** `observational_shaping` — observe seam behavior, detect repeated weakness, raise advisory pressure, generate diagnostic and training outputs.

**Forbidden actions:** own turns, route turns, force behavior, override supervisor, override fulfillment, create controller logic, turn diagnostics into commands.

### 13.2 Live Simulator (`subconscious_live_simulator.py`)

After every turn finalization, the live simulator replays the completed turn against a set of behavioral scenarios. It evaluates whether the chosen route (supervisor-owned / fulfillment / fallback) was optimal given the input.

**Pressure signals that can fire:**
- `supervisor_overreach` — supervisor owned a turn where fulfillment looked viable
- `fulfillment_missed` — fulfillment route was skipped when it should have applied
- `fallback_overuse` — direct LLM fallback used repeatedly for answerable requests
- `route_unclear` — router could not clearly decide between two routes
- `route_conflict` — two routes both claimed the turn
- `route_fit_weak` — chosen route matched but with low confidence

### 13.3 Crack Accumulation

Weak pressure signals (`route_unclear`, `route_fit_weak`) accumulate in a rolling window of 12 records. When a weak signal repeats at or above its threshold (default: 2–3 times), the subconscious escalates it to the Work Tree via triage.

### 13.4 Training Backlog (`subconscious_training_backlog.py`)

Strong signals (immediate priority: `supervisor_overreach`, `fulfillment_missed`, `fallback_overuse`, `route_conflict`) immediately generate a training backlog entry. Each entry includes:
- Title and suggested test name
- Rationale
- Example turn that triggered the signal
- Suggested fix direction

The backlog is surfaced in the control panel's Subconscious Watch tab and in exports.

### 13.5 Work Tree Triage (`subconscious_work_tree_triage.py`)

Translates accumulated subconscious pressure into Work Tree branches. Opens a branch in the `subconscious` bucket with `work_class="investigation"` and links the source payload. If a branch for the same signal already exists, adds evidence.

### 13.6 Route Probe (`subconscious_route_probe.py`)

Standalone probe that tests known routes against a set of fixed inputs and records pass/fail. Used by the live simulator to calibrate its expectations. Results are stored in session state via `ConfiguredSubconsciousService`.

### 13.7 Session State Integration

Subconscious state is stored per-session in `services/session_state.py` as a `SubconsciousState` object. Contains: recent pressure records (rolling window), crack counts per signal type, last probe result, chosen route history. This state drives the pressure display in the control panel's Subconscious Watch tab.

---

## 14. Supervisor

**Files:** `supervisor.py`, `services/supervisor_authority.py`, `services/supervisor_patterns.py`, `services/supervisor_probes.py`, `services/supervisor_registry.py`, `services/supervisor_runtime.py`

The supervisor owns specific categories of turns. When the supervisor owns a turn, it bypasses fulfillment and handles the response directly.

### 14.1 Authority (`supervisor_authority.py`)

Defines which turn types the supervisor has authority over. Authority is declared as a set of pattern matchers, not a simple keyword list. Authority declarations are versioned and auditable.

### 14.2 Patterns (`supervisor_patterns.py`)

Compiled pattern library used to match incoming turns. Patterns cover: identity questions, capability questions, safety boundary tests, policy queries, system state questions, and meta-questions about Nova itself.

### 14.3 Probes (`supervisor_probes.py`)

Standalone probes that test whether the supervisor is correctly identifying its own turns. Used by the subconscious live simulator to detect `supervisor_overreach` — the supervisor claiming turns it should not own.

### 14.4 Registry (`supervisor_registry.py`)

Central registry of all supervisor patterns and their metadata. Each entry records: pattern name, match criteria, expected route classification, and the authority level required to execute.

### 14.5 Runtime (`supervisor_runtime.py`)

Evaluates the current turn against the registry and returns: `owned=True/False`, `match_pattern`, `authority_level`. If owned, returns the supervisor's composed response directly without calling Ollama.

---

## 15. OS Capabilities

**Files:** `services/os_capability_registry.py`, `services/os_script_controller.py`, `services/os_capability_operator_outbox.py`, `tools/os_capabilities/`, `capabilities.py`, `capabilities.json`

OS capabilities are named, policy-gated operations that Nova can perform on the Windows host.

### 15.1 Capability Registry (`os_capability_registry.py`)

Loads capability definitions from `capabilities.json` (generated from `capabilities.py`). Each capability has:
- `name` — unique identifier
- `description` — human-readable
- `script` — path to PowerShell or Python script in `tools/os_capabilities/`
- `inputs` — declared parameter schema
- `outputs` — declared output schema
- `safety_level` — `read_only`, `read_write`, `destructive`
- `policy_key` — policy.json key that must be true to allow execution

### 15.2 Script Controller (`os_script_controller.py`)

Executes capability scripts in a controlled subprocess. Captures stdout/stderr, enforces timeout, and returns structured output. Failures are journaled to the capability ledger.

### 15.3 Operator Outbox Bridge (`os_capability_operator_outbox.py`)

When a capability execution produces an operator-relevant event (warning, failure, result requiring human review), it creates an outbox notice via `services/operator_outbox.py`.

### 15.4 Capability Ledger

OS capability events are journaled to `runtime/os_capability_ledger.jsonl` (if configured). Each record: capability name, inputs, result, duration, safety level, policy key, outcome.

---

## 16. SOCK — Hardware Profiling

**File:** `services/sock_service.py`

SOCK (System Optimization and Compatibility Check) scans the local hardware and produces a model recommendation with a policy diff.

### 16.1 Hardware Scan (`scan_hardware()`)

Runs PowerShell queries via `subprocess` to enumerate:
- CPU: name, core count, max clock
- GPU: nvidia-smi first (returns RTX 4050 6 GB directly); falls back to CIM WMI
- RAM: total physical GB
- Disk: available GB on system drive
- NPU: PnP device enumeration for "IPU" entries (AMD XDNA 2 detected as "AMD Ryzen AI IPU Device")

Returns a `HardwareProfile` dataclass.

### 16.2 Model Recommendation (`recommend_models()`)

Takes `HardwareProfile`, applies VRAM-aware tier selection:
- ≥12 GB VRAM: large models (70B class)
- ≥6 GB VRAM: medium models (7–13B class) — Rogue_One tier
- ≥4 GB VRAM: small models (3–7B class)
- CPU-only: tiny models (1–3B class)

Selects a joint `(chat_model, vision_model)` pair where both models fit in VRAM simultaneously. Returns a `ModelRecommendation` dataclass.

### 16.3 Policy Diff (`build_diff()`)

Compares `ModelRecommendation` against the active `policy.json` model settings. Returns a `PolicyDiff` dataclass listing any mismatches between recommended and configured models.

### 16.4 TTL-Cached Accessor (`get_sock_status_keys()`)

Added to `sock_service.py` as a thread-safe, TTL-cached (300 second) accessor. Returns a dict with three keys:
- `sock_hardware_profile` — full `HardwareProfile` as dict
- `sock_recommendation` — full `ModelRecommendation` as dict
- `sock_policy_diff` — full `PolicyDiff` as dict

These keys are injected into the control status payload by `control_status.py` before the wiring inventory check runs. This closes the wiring gap that was the last open surface gap.

### 16.5 Control Status Integration

`control_status.py` calls `get_sock_status_keys()` in a try/except block. On success, the three SOCK keys are present in the payload. On failure (e.g., PowerShell unavailable), empty dicts are substituted so the payload structure is always consistent.

---

## 17. Patch System

**Files:** `services/patch_control.py`, `services/nova_patching.py`, `tools/patch_tool.py`, `services/patch_control.py`

The patch system manages code and configuration updates to Nova itself.

### 17.1 Patch Flow

```
Patch source (operator, autonomy, or external)
  │
  ▼
patch_preview_list    — list queued patches with summary
patch_preview_show    — inspect full diff of a specific patch
patch_preview_approve — mark patch approved for application
patch_preview_reject  — discard patch
patch_preview_apply   — apply approved patch to live files
```

### 17.2 Safety Gates

Before any patch applies:
- `patch_strict_manifest` — patch must declare all files it touches
- `patch_behavioral_gate` — behavioral tests must be available
- `patch_behavioral_tests_available` — test suite must be runnable

All three gates are checked in the self-check suite and must be green before `patch_preview_apply` is permitted.

### 17.3 Patch Queue

The autonomy orchestrator can propose `patch_queue_run_next` to apply the next queued and approved patch. This is blocked if any safety gate is failing.

### 17.4 Update Flow

`update_now_dry_run` / `update_now_confirm` / `update_now_cancel` — operator-initiated full update cycle distinct from the patch queue. Dry run shows what would change; confirm applies it; cancel aborts.

---

## 18. Regression Governance

**Files:** `services/regression_lanes.py`, `services/regression_profile_inventory.py`, `services/behavior_metrics.py`, `run_regression.py`

Nova's regression system tracks behavioral correctness across three test lanes.

### 18.1 Lanes

| Lane | Purpose |
|------|---------|
| `unit` | Fast, isolated unit tests; no external dependencies |
| `behavior` | Integration-style tests that exercise real routing, memory, and tools |
| `integration` | End-to-end tests that require the HTTP server to be running |

### 18.2 Regression Profile Inventory (`regression_profile_inventory.py`)

Maintains a registry of known test profiles (test class + method + expected behavior). On each run, compares actual results against the profile. Drift (a test that previously passed now fails, or vice versa) is a signal that fires in signal ingestion and opens a Work Tree branch.

The `test_profile_inventory_clear` self-check ensures no unresolved drift is present.

### 18.3 Behavior Metrics (`behavior_metrics.py`)

Tracks per-turn behavioral metrics: route classification accuracy, tool selection accuracy, fallback rate, supervisor ownership rate. Metrics are persisted to `runtime/behavior_metrics.json` and surfaced in the control panel's Parity Runs and Per-Turn Drift panels.

### 18.4 Parity Test Runs

Operator can trigger a full parity run via `test_session_run` control action or from the Parity Runs panel. Results are compared against the profile inventory. Findings are displayed in the Parity Findings panel.

---

## 19. Release Lifecycle

**Files:** `services/release_status.py`, `services/release_validation.py`, `services/release_validation_contracts.py`, `services/release_promotion_judgment.py`, `services/release_clean.py`, `services/validation_artifact_truth.py`, `services/installer_validation.py`, `installer/`

Nova's release system packages the codebase into a versioned artifact and validates it before promotion.

### 19.1 Lifecycle Stages

```
nova package-build    — snapshot current source into a versioned artifact
nova package-verify   — check artifact integrity (checksums, manifest)
nova package-validate — run full validation suite against the artifact
nova package-promote  — mark artifact as the active release
```

### 19.2 Release Artifact (`services/runtime_artifacts.py`)

Each build produces a release artifact stored in `runtime/exports/`. The artifact includes: source snapshot, package manifest (`package_manifest.json`), validation report, and promotion status.

### 19.3 Validation (`release_validation.py`)

Validation runs the test suite, checks wiring inventory (`nova wiring-check`), verifies manifest completeness, and evaluates the `source_root` gap. All checks must pass for `validation_artifact_truth_clear` to be true.

### 19.4 Promotion Judgment (`release_promotion_judgment.py`)

Before promotion, the judgment layer evaluates:
- All validation checks green
- No open Work Tree branches blocking release
- No `source-changed-after-build` lifecycle flag
- Wiring check: 0 failures

### 19.5 Lifecycle Flag: `source-changed-after-build`

If any source file changes after the most recent build, the release is flagged as `source-changed-after-build`. This is a lifecycle warning, not a blocker. It is cleared by running `nova package-build` again.

### 19.6 Installer (`installer/`)

Contains the installer package for deploying Nova to a new machine. `installer_validation.py` verifies installer integrity during the validation stage.

---

## 20. Wiring Inventory

**Files:** `services/nova_wiring_inventory.py`, `services/nova_root_inventory.py`, `services/nova_inventory_labels.py`, `services/end_to_end_wiring.py`

The wiring inventory is a compile-time and runtime closure check that verifies every declared service surface is reachable through the status payload.

### 20.1 How It Works

Each service that has an observable surface (something that should appear in `/api/control/status`) declares its surface in `nova_wiring_inventory.py`. The inventory check (`build_wiring_inventory_payload(payload)`) receives the assembled status payload and verifies that every declared key is present.

### 20.2 Surface Declaration

A surface is a named grouping of status keys. Example: the `hardware_profile` surface declares keys `sock_hardware_profile`, `sock_recommendation`, `sock_policy_diff`. If any of those keys are missing from the payload, the surface reports a gap.

### 20.3 Gap Detection

`gap_count` = number of surfaces with one or more missing keys. Current state: **0 gaps** (76 checks, 0 failures).

### 20.4 Source Root Inventory (`nova_root_inventory.py`)

Separate but related: tracks which Python source files are classified (categorized by their role). An unclassified file is a `source_root` gap. Current state: **0 gaps** — all service files including `nova_intent_understanding.py` and `sock_service.py` are classified.

### 20.5 CLI Check

`nova wiring-check [--offline]` runs the full check without starting the HTTP server. `--offline` skips any checks that require a live Ollama connection.

---

## 21. Health & Telemetry

**Files:** `services/control_telemetry.py`, `services/control_status.py`, `services/control_status_cache.py`, `health.py`

### 21.1 Control Status (`control_status.py`)

Assembles the master status payload that all health checks, the wiring inventory, and the control panel consume. The payload is built by aggregating output from every active subsystem. Key sections:

| Section | Content |
|---------|---------|
| `guard` | Guard process state, PID, uptime |
| `core` | Core process state, heartbeat age |
| `ollama_api_up` | Ollama reachability |
| `ollama_model_available` | Chat model loaded |
| `ollama_chat_ready` | Full chat path validated |
| `vision_runtime_ok` | Vision model available |
| `work_tree_*` | Branch counts by status |
| `patch_status_*` | Patch queue state |
| `tool_events_ok` | Tool event journal health |
| `sock_hardware_profile` | Full hardware scan result |
| `sock_recommendation` | Model recommendation |
| `sock_policy_diff` | Policy vs. recommendation diff |
| `wiring_inventory` | Gap count, per-surface status |

### 21.2 Self-Check Suite (22 Checks)

The self-check suite (`build_self_check` in `control_telemetry.py`) evaluates 22 named checks and produces a health score (0–100). Current score: **100** (22/22 passing).

| Check | What it verifies |
|-------|-----------------|
| `status_payload` | Status endpoint payload builds without error |
| `ollama_api` | Ollama API is reachable |
| `ollama_chat_model` | Configured chat model is loaded |
| `ollama_chat_ready` | Full chat path is validated |
| `vision_runtime` | Vision model dependency is satisfied |
| `policy_payload` | Policy endpoint returns valid payload |
| `metrics_payload` | Metrics endpoint returns valid payload |
| `session_manager` | Session summaries are available |
| `guard_status` | Guard payload is present in status |
| `tool_event_summary` | Tool event journal is healthy |
| `patch_status_summary` | Patch governance summary is present |
| `capability_registry` | OS capability registry loaded with entries |
| `heartbeat_freshness` | Core heartbeat file is recent (< threshold seconds) |
| `allow_domains_present_when_web_enabled` | Web mode has at least one allow domain configured |
| `patch_strict_manifest` | Patch manifest strictness gate is on when patch enabled |
| `patch_behavioral_gate` | Behavioral test gate is on when patch enabled |
| `patch_behavioral_tests_available` | Tests are runnable when behavioral gate is on |
| `validation_artifact_truth_clear` | No unresolved validation artifact issues |
| `test_profile_inventory_clear` | No unresolved test profile drift |
| `work_tree_unresolved_truth_clear` | No blocked/observing/latent work tree truth branches |
| `error_rate_spike` | Error rate has not spiked in recent metrics window |
| *(one dynamic check)* | Context-dependent check added per policy state |

Health score = (passing checks / total checks) × 100. Alerts are appended for any failing check.

### 21.3 Status Cache (`control_status_cache.py`)

The full status payload is cached with a short TTL to prevent redundant computation on rapid sequential requests to `/api/control/status`. Cache is invalidated on any control action that changes state.

### 21.4 Telemetry (`control_telemetry.py`)

Beyond health checks, the telemetry layer computes:
- Request rate and error rate (from `runtime_analytics.py`)
- Error spike detection (> 2 errors/min and > 20% error ratio)
- Behavior metric trend (from `behavior_metrics.py`)
- Restart analytics (from `runtime_analytics.py`)

All telemetry is surfaced via `/api/control/metrics`.

---

## 22. Operator Outbox

**Files:** `services/operator_outbox.py`, `services/os_capability_operator_outbox.py`

The operator outbox is a notification queue for items that require human attention.

### 22.1 Notice Types

| Source | Example Notice |
|--------|---------------|
| Work Tree | Branch stalled; operator hold required |
| OS Capability | Capability execution failed with destructive safety level |
| Autonomy | Proposed action blocked by policy; manual override needed |
| Signal Ingestion | High-priority signal fired; operator review recommended |
| Regression | Parity run found new failure not in profile |

### 22.2 Notice Lifecycle

```
Notice created (open)
  ├─► Operator reviews in Operator Outbox panel
  ├─► operator_outbox_respond — operator provides a response
  ├─► operator_outbox_seen — operator marks as seen (no response needed)
  └─► Auto-resolved when source condition clears
```

### 22.3 Storage

Outbox notices are appended to `runtime/operator_outbox.jsonl`. The panel polls `/api/control/status` which includes outbox summary fields.

---

## 23. Temporal Feed

**Files:** `services/nova_calendar_ingestion.py`, tools/temporal_review_tool.py, `services/nova_location_weather.py`

The temporal feed gives Nova awareness of scheduled obligations and time pressure.

### 23.1 Calendar Ingestion (`nova_calendar_ingestion.py`)

Reads ICS calendar files from configured paths. Parses events, filters to a rolling time window (configurable; default: 7 days ahead), and scores each event by proximity and declared priority.

### 23.2 Temporal Service

Maintains a list of upcoming events with pressure scores. Scores increase as event start time approaches. Events crossing the configured pressure threshold trigger a signal in signal ingestion, which opens a Work Tree branch.

### 23.3 Work Tree Integration

A `temporal_pressure` branch is opened when any event's pressure score exceeds `temporal_pressure_threshold` in `policy.json`. The branch title includes the event name and time. The branch closes when the event has passed.

### 23.4 CLI (`nova time`)

`nova time` runs the temporal review CLI: reads the calendar feed, displays upcoming events with scores, and prints any current pressure branches.

### 23.5 Location & Weather (`nova_location_weather.py`)

Optional: reads device location from `runtime/device_location.json` (set via `device_location_update` control action) and can fetch weather context for location-aware responses. Used in the reply context when location is available.

---

## 24. Voice, STT, and TTS

**Files:** `voice.py`, `services/voice_interaction.py`, `tts_piper.py`, `tts_say.py`, `tts_say.ps1`, `piper/`

### 24.1 STT — Whisper

Speech-to-text uses Whisper medium. Mic input is captured via `voice.py`. Whisper transcription runs locally (CPU or GPU). The transcribed text is fed into the normal turn flow.

### 24.2 TTS — Piper

Text-to-speech uses Piper, an offline neural TTS engine. The Piper binary and voice models are in the `piper/` directory. `tts_piper.py` wraps the binary with the selected voice model. `tts_say.py` / `tts_say.ps1` are fallback TTS paths using Windows SAPI.

### 24.3 Voice Interaction Service (`voice_interaction.py`)

Manages the voice session lifecycle: mic open → STT → turn → reply → TTS. Voice mode is toggled by the operator in both the control panel (Runtime Control) and the Leah UI (voice toggle button).

---

## 25. Vision

**Files:** `tools/vision_tool.py`, `camera.py`, `look.py`, `look_crop.py`

### 25.1 Vision Tool

Accepts an image (from camera capture or upload) and queries the vision model (qwen2.5vl:7b via Ollama). Can answer specific questions about the image or produce a general description. Returns structured output injected into the reply context.

### 25.2 Camera (`camera.py`)

Captures a still frame from the default capture device. `look.py` is a standalone CLI for camera capture. `look_crop.py` crops a region of the captured frame before passing to the vision model.

### 25.3 Vision Runtime Check

`vision_runtime_ok` in the status payload reflects whether the vision model is loaded in Ollama. The `vision_runtime` self-check verifies this. Vision-dependent turns fail gracefully with a human-readable message if the model is not available.

---

## 26. Web Search

**Files:** `services/nova_web_tools.py`, `services/nova_web_contracts.py`, `services/web_research_session.py`, `services/nova_http_policy_search.py`

### 26.1 Search Provider

Nova uses SearXNG as its local privacy-preserving search engine. The search provider is configured in `policy.json` under `search_provider`. Multiple providers and endpoints can be configured.

### 26.2 Policy Controls

Web search is gated by:
- `web_enabled` in `policy.json`
- `allow_domains` — list of allowed fetch domains
- `search_provider` — configured provider

Control actions for search: `search_provider` (set provider), `search_provider_toggle` (enable/disable), `search_endpoint_set`, `search_provider_priority_set`, `search_endpoint_probe`.

### 26.3 Research Session (`web_research_session.py`)

Multi-step research: run query → get results → fetch top pages → extract relevant content → synthesize answer with citations. The session object tracks fetched URLs, content snippets, and synthesis state across multiple LLM calls.

---

## 27. Data Pipelines

**Files:** `services/control_pipelines.py`, `services/data_pipeline_registry.py`, `services/pipeline_privileged_bridge.py`, `services/nova_pipeline_tools.py`, `services/nova_http_pipeline_control.py`, `pipelines/`

Pipelines are structured multi-step data workflows defined in the `pipelines/` directory.

### 27.1 Registry (`data_pipeline_registry.py`)

Maintains the list of defined pipelines. Each pipeline has: ID, name, description, steps, status (active/paused/archived), populations, and schema.

### 27.2 Privileged Bridge (`pipeline_privileged_bridge.py`)

Some pipeline steps require elevated access to internal Nova state (e.g., querying work_tree.db directly). The privileged bridge provides a controlled interface for this. Audit trail is written for all privileged operations.

### 27.3 Control Actions

| Action | Effect |
|--------|--------|
| `pipeline_create` | Create a new pipeline definition |
| `pipeline_start` | Start a paused pipeline |
| `pipeline_pause` | Pause a running pipeline |
| `pipeline_update` | Update pipeline definition |
| `pipeline_note_append` | Add a note to a pipeline's log |
| `pipeline_population_upsert` | Add or update a population (data source) |
| `pipeline_archive` | Archive a pipeline |

### 27.4 Data Lanes

The pipeline panel in the control panel displays: active data lanes, lane settings, seeded schemas and populations, population definitions, and scoped intake configuration.

---

## 28. Session Management

**Files:** `services/session_admin.py`, `services/session_state.py`, `http_session_store.py`, `services/chat_identity.py`, `services/control_auth.py`, `services/control_login_frontdoor.py`, `services/leah_frontdoor.py`

### 28.1 HTTP Session Store

Sessions are stored in `runtime/http_chat_sessions.json`. Each session tracks: user identity, message history, subconscious state, session start time, and last activity.

### 28.2 Session State (`session_state.py`)

Per-session state includes: subconscious snapshot (crack counts, recent pressure, probe history), current memory scope, active tool context, and session identity.

### 28.3 Auth (`control_auth.py`)

The control panel requires a password set in `policy.json`. Auth state is tracked per browser session via a secure cookie. The login frontdoor (`control_login_frontdoor.py`) handles login/logout flows.

### 28.4 Leah Auth (`leah_frontdoor.py`)

Leah has its own separate auth path. Users are managed via the Chat Access panel (control actions `chat_user_list`, `chat_user_upsert`, `chat_user_delete`).

### 28.5 Session Admin (`session_admin.py`)

Operator can delete sessions via the `session_delete` control action. Session list is visible in the Live Sessions panel. Test sessions (used for parity runs) are managed separately via `test_session_control.py`.

---

## 29. Scheduler & Heartbeat

**Files:** `services/nova_scheduler.py`, `services/runtime_heartbeat.py`, `services/schedule_registry.py`

### 29.1 Scheduler (`nova_scheduler.py`)

Runs inside the core process. Manages a set of recurring tasks at defined intervals:
- Autonomy maintenance cycle: every 30 seconds (±jitter)
- Heartbeat write: every 5 seconds
- Memory health snapshot: every 5 minutes
- Signal ingestion pass: every autonomy maintenance cycle
- Subconscious pressure evaluation: every turn + periodic background pass

### 29.2 Heartbeat (`runtime_heartbeat.py`)

Writes a timestamp to `runtime/core.heartbeat` every 5 seconds. The guard reads this file to detect a stalled core. The `heartbeat_freshness` self-check verifies the heartbeat is recent.

### 29.3 Schedule Registry (`schedule_registry.py`)

Operator-visible registry of all scheduled tasks. The Scheduled Tree panel in the control panel shows all active scheduled tasks, their last run time, next run time, and status.

---

## 30. Knowledge Packs

**Files:** `services/nova_knowledge_packs.py`, `knowledge/`

Knowledge packs are curated document sets that Nova can reference during conversations. Packs are stored in the `knowledge/` directory as structured JSON or Markdown.

### 30.1 Pack Registration

Each pack is registered with a name, description, and domain tags. The memory routing layer can inject relevant pack content into the reply context when the intent domain matches.

### 30.2 Import Tools

`tools/import_dashboard_reports.py` and `tools/import_eschoolplus_data_dictionary.py` are specialized importers for education-domain data sources. These import structured data from external systems into Nova's knowledge base.

---

## 31. Control Panel — Full Reference

**Entry:** `/control` (requires password auth)
**File:** `templates/control.html`, `static/control.js`

The control panel is Nova's operator interface. It provides full visibility into every Nova subsystem and exposes all control actions.

### 31.1 Sidebar (Left Column)

The sidebar contains three always-visible status sections:

**Core Pulse**
A real-time summary of Nova's health. Shows: health score (0–100), guard status (running/stopped), core status (running/stopped), Ollama API status, chat model status, heartbeat age, and active alert count. Color-coded: green (all clear), yellow (warnings), red (critical).

**Route Trace**
Shows the last completed turn's routing decision: which route was selected (supervisor / fulfillment / fallback), which tool was used (if fulfillment), intent classification result, and the subconscious's assessment of the route quality.

**Ops Snapshot**
A one-glance operational status: Work Tree branch counts (ready/active/blocked/stalled), autonomy mode (advisory/execute), last autonomy decision, and open operator outbox notices.

### 31.2 Telemetry Panel

Four sub-tabs displaying system telemetry:

**Telemetry Live (graph)**
Real-time chart of request rate and error rate over a rolling time window. Plots data points from the metrics endpoint. Shows request/min and error/min as line graphs.

**Signal Snapshot**
Current state of all signal ingestion signals: which signals are active, which are cleared, evidence counts for each active signal, and the Work Tree branches each active signal has opened.

**Pressure Matrix**
Heatmap/table of subconscious pressure by signal type and session. Rows are signal types; columns are recent time windows. Intensity shows accumulated pressure. Helps identify which behavioral patterns are recurring.

**Restart Analytics**
History of Nova process restarts: timestamp, source (guard restart, operator restart, crash recovery), restart intent reason, and time to recover. Chart shows restart frequency over time.

### 31.3 Center Tabs

The main content area has nine tabs:

**System Matrix**
Full status payload displayed as a structured tree. Every key in `/api/control/status` is visible here: guard fields, core fields, Ollama fields, Work Tree counts, SOCK hardware profile, model recommendation, policy diff, wiring inventory, self-check results. This is the raw truth view.

**Subconscious Watch**
Three sub-sections:

- *Live Advisory Pressure:* Current subconscious pressure state. Shows: active pressure signals, crack counts per signal, recent pressure record window (last 12), and whether any signal has crossed the triage threshold.

- *Top Priorities:* Training backlog entries ordered by priority. Each entry shows: signal type, suggested test name, rationale, and the triggering turn. Operator can mark entries as addressed.

- *Standing Work Queue:* Subconscious-originated Work Tree branches that are open. Shows branch title, source signal, evidence count, and current status.

**Patch Readiness**
Current state of the patch system: patch queue depth, approved patches waiting application, pending review patches, safety gate status (manifest, behavioral, tests), and last applied patch. Buttons for patch actions (preview, approve, reject, apply) appear inline.

**Action Stream**
Live feed of autonomy orchestrator decisions. Each entry: timestamp, decision type, selected action (if recommend), score, deferral/block reason (if deferred/blocked), and the top 3 candidate actions considered. Newest entries at top.

**Runtime Timeline**
Chronological view of all significant Nova events: process starts/stops, restart events, autonomy decisions, patch applications, control actions dispatched, Work Tree branch open/close events. Scrollable history. Filters by event type.

**Failure Reasons**
Aggregated failure analysis: groups failures by type and root cause. Shows count, first seen, last seen, and which subsystem originated the failure. Useful for spotting recurring issues.

**Runtime Artifacts**
List of all build artifacts in `runtime/exports/`. For each: version, build timestamp, validation status, promotion status, wiring check result, and manifest integrity. Operator can trigger `runtime_artifact_show` to inspect a specific artifact.

**Release Governance**
Current release lifecycle state: active artifact version, stage (built/verified/validated/promoted), `source-changed-after-build` flag, wiring check pass/fail, open blockers. Buttons for `update_now_dry_run`, `update_now_confirm`, `update_now_cancel`.

**Artifact Drill-Down**
Deep inspection of a selected release artifact: full validation report, per-check results, manifest listing, wiring inventory report, self-check snapshot at build time.

### 31.4 Operations Layer

Three tabs controlling runtime behavior:

**Guard Control**
Guard process management: start, stop, restart guard. Shows guard PID, uptime, lock file status, boot history. `update_now_dry_run` / `update_now_confirm` buttons.

**Raw Runtime Fields**
Raw key-value display of all runtime fields from `core_state.json` and `guard_pid.json`. Unfiltered, unformatted — for deep debugging.

**Core Recovery**
Manual recovery actions: trigger core restart, clear stuck locks, reset heartbeat, force state reload. Each action requires explicit confirm click.

**Web UI Recovery**
Browser-side recovery: reload status, clear cached state, reset panel positions, force full refresh. Does not touch the Nova process.

**Action Readiness**
Shows which control actions are currently available and which are blocked by policy, gate failures, or runtime state. Grouped by category.

**Policy Controls**
Edit `policy.json` fields directly from the UI:
- Toggle web mode on/off
- Set allow domains for web search
- `policy_allow` / `policy_remove` for capability grants
- Memory scope selector (`memory_scope_set`)
- Search provider configuration

**Memory Governance**
Memory system controls: view current memory scope, view memory health snapshot, trigger thinning, view memory event log, reset identity (requires confirm).

**Search Provider**
Configure and test search providers: set provider URL, toggle provider on/off, set priority among multiple providers, probe endpoint connectivity (`search_endpoint_probe`).

**Chat Access**
Manage Leah users: `chat_user_list` shows all registered users, `chat_user_upsert` adds or updates a user (name, credentials), `chat_user_delete` removes a user.

**Operator Command Deck**
Direct command execution: `operator_prompt` sends a raw prompt to Nova's LLM pipeline, bypassing normal turn routing. For testing and debugging. Output appears in the Operator Reply section.

**Operator Reply**
Display area for `operator_prompt` responses and `backend_command_run` output.

**Operator Outbox**
List of all open outbox notices requiring operator attention. Each notice: source, type, message, timestamp. Actions: `operator_outbox_respond` (reply to notice), `operator_outbox_seen` (acknowledge without response).

**Operator Actions**
Quick-access buttons for common autonomy actions: `active_work_tree_run_next` (advance next Work Tree branch), `patch_queue_run_next` (apply next patch), `generated_queue_run_next` (run next generated item), `generated_queue_investigate` (inspect next item without running).

**Backend Command Console**
Execute registered backend commands: `backend_command_list` shows available commands, `backend_command_run` executes a selected command with parameters. Commands are registered in `backend_command_deck.json`.

### 31.5 Sessions Layer

Three tabs for session management:

**Live Sessions**
Table of all active HTTP sessions: user, session ID, start time, last activity, message count, subconscious state summary. Operator can delete any session (`session_delete`).

**Live Probe Findings**
Per-session subconscious probe results. Shows the most recent probe result for each active session: route chosen, probe verdict, pressure signals fired.

**Parity Test Runs**
Trigger and view parity test runs (`test_session_run`). Shows: last run timestamp, pass/fail count, drift count vs. profile, and which tests changed.

**Per-Turn Drift**
Behavioral metric history: per-turn route classification, tool selection, fallback rate. Chart showing how route accuracy trends over time.

**Parity Findings**
Detail view of parity test failures: which test, what changed, expected vs. actual behavior, and whether the profile has been updated.

**Real-World Task Library**
Library of registered real-world tasks used for integration testing. `real_world_task_create` adds a new task to the library with expected behavior.

**Create Real-World Task**
Form for creating a new real-world task: name, input, expected route, expected tool, expected output pattern.

**Scheduled Tree**
View of the Work Tree structure: trees and their branches in a visual hierarchy. Branch status color-coded. Shows priority, score, evidence count, and source type for each branch.

**Branch Inspector**
Deep inspection of a selected Work Tree branch: full branch data, task list with status, source payload, resolution history, tool state.

### 31.6 Pipeline Layer

**Data Lanes**
Active pipeline lanes and their status: running, paused, error, or idle.

**Lane Settings**
Per-lane configuration: schedule, input population, output target, privilege level.

**Seeded Schema and Populations**
View of all seeded schemas and their populations (data source definitions).

**Population Definition**
Inspect or edit a specific population: query, filters, refresh schedule, last loaded count.

**Scoped Intake**
Configure which data sources are available for intake within a given scope.

### 31.7 Logs Layer

**Policy Snapshot**
Current state of `policy.json` rendered as a readable tree. Shows all policy keys, their values, and which keys differ from defaults. Read-only in this view; edits go through Policy Controls.

**Action Output**
Log of the last N control actions dispatched: action type, payload, result (ok/fail), message, timestamp. Useful for auditing what the operator or autonomy has done recently. Also surfaced via `control_action_audit.jsonl`.

### 31.8 Health Layer

**Health Summary**
The 22 self-checks displayed as a checklist: check name, pass/fail indicator, detail string. Overall health score prominently displayed. Active alerts listed below. Color-coded by severity.

**Runtime Summary**
Narrative summary of Nova's current runtime state: uptime, model status, memory health, Work Tree depth, regression state. Generated by `nova_grounded_self_report.py`. Readable paragraph format, not raw JSON.

**Raw Runtime Fields** *(also here)*
Same raw field view as in the Operations layer — replicated for convenience.

**Supervisor Snapshot**
Current supervisor state: authority mode, active patterns matched in recent turns, override rate, and any patterns that fired `supervisor_overreach` in the subconscious.

### 31.9 Inspector Panel

A right-side collapsible inspector with four sub-tabs:

**Planner Decision**
The full planner contract result for the most recent turn: route selected, confidence, policy constraints applied, intent classification, and candidate routes considered with their scores.

**Ledger**
The action ledger entry for the most recent turn: turn ID, timestamp, route, tool, result summary, learning events fired, latency.

**Supervisor**
Supervisor evaluation for the most recent turn: did supervisor own it, which pattern matched, authority level, response source (supervisor vs. Ollama).

**Session State**
Full session state for the current operator browser session: subconscious state object, memory scope, message count, last probe result.

### 31.10 All Control Actions

Complete list of actions dispatched via `POST /api/control/action`:

| Action | Panel | Description |
|--------|-------|-------------|
| `refresh_status` | Any | Force status cache invalidation and reload |
| `device_location_update` | Policy | Set operator device location |
| `device_location_clear` | Policy | Clear device location |
| `patch_preview_list` | Patch Readiness | List queued patches |
| `patch_preview_show` | Patch Readiness | Show full diff of a patch |
| `patch_preview_approve` | Patch Readiness | Approve a patch for application |
| `patch_preview_reject` | Patch Readiness | Reject and discard a patch |
| `patch_preview_apply` | Patch Readiness | Apply approved patch |
| `pulse_status` | Core Pulse | Get pulse summary |
| `update_now_dry_run` | Release Governance | Preview full update |
| `update_now_confirm` | Release Governance | Execute full update |
| `update_now_cancel` | Release Governance | Cancel pending update |
| `runtime_artifact_show` | Runtime Artifacts | Inspect a specific artifact |
| `test_session_run` | Parity Runs | Run a parity test session |
| `generated_pack_run` | Operator Actions | Run a generated work pack |
| `generated_queue_run_next` | Operator Actions | Run next generated queue item |
| `generated_queue_investigate` | Operator Actions | Inspect next generated item |
| `patch_queue_run_next` | Operator Actions | Apply next queued patch |
| `active_work_tree_run_next` | Operator Actions | Advance next Work Tree branch |
| `real_world_task_create` | Task Library | Create a real-world task |
| `backend_command_list` | Backend Console | List available backend commands |
| `backend_command_run` | Backend Console | Execute a backend command |
| `operator_prompt` | Operator Deck | Send raw prompt to LLM pipeline |
| `operator_outbox_respond` | Operator Outbox | Respond to an outbox notice |
| `operator_outbox_seen` | Operator Outbox | Acknowledge an outbox notice |
| `session_delete` | Live Sessions | Delete an HTTP session |
| `policy_allow` | Policy Controls | Grant a capability in policy |
| `policy_remove` | Policy Controls | Revoke a capability from policy |
| `web_mode` | Policy Controls | Toggle web search on/off |
| `memory_scope_set` | Memory Governance | Set active memory scope |
| `search_provider` | Search Provider | Set search provider |
| `search_provider_toggle` | Search Provider | Enable/disable search provider |
| `search_endpoint_set` | Search Provider | Set provider endpoint URL |
| `search_provider_priority_set` | Search Provider | Set provider priority |
| `search_endpoint_probe` | Search Provider | Test endpoint connectivity |
| `chat_user_list` | Chat Access | List Leah users |
| `chat_user_upsert` | Chat Access | Add or update a Leah user |
| `chat_user_delete` | Chat Access | Delete a Leah user |
| `pipeline_note_append` | Pipelines | Append a note to a pipeline |
| `pipeline_create` | Pipelines | Create a new pipeline |
| `pipeline_start` | Pipelines | Start a pipeline |
| `pipeline_pause` | Pipelines | Pause a pipeline |
| `pipeline_update` | Pipelines | Update pipeline definition |
| `pipeline_population_upsert` | Pipelines | Add/update a population |
| `pipeline_archive` | Pipelines | Archive a pipeline |
| `inspect` | Inspector | Deep-inspect a specific item |
| `policy_audit` | Logs | Run a policy audit |
| `tail_log` | Logs | Fetch recent log lines |
| `metrics` | Telemetry | Get current metrics snapshot |
| `self_check` | Health | Run self-check suite |
| `export_capabilities` | Health | Export capability registry |
| `export_ledger_summary` | Health | Export action ledger summary |
| `export_diagnostics_bundle` | Health | Export full diagnostics bundle |

---

## 32. Leah — Full Reference

**Entry:** `/leah` (requires user auth)
**Files:** `templates/leah.html`, `static/leah.js`, `services/leah_frontdoor.py`, `services/nova_http_chat_runtime.py`

Leah is Nova's conversational interface. It is designed for ongoing personal interaction, in contrast to the control panel which is an operator/diagnostic interface.

### 32.1 Layout

Leah's UI is a single-page chat interface with three zones:
- **Left column:** Presence bar, voice/mode controls, session management, activity feed
- **Center:** Chat history and message input
- **Right (when open):** Session detail, context panel

### 32.2 Mood System

Leah has a configurable mood that changes the visual theme and influences response tone.

| Mood | Color Theme | Behavioral Influence |
|------|-------------|---------------------|
| `calm` | Soft blue/gray | Slower, more reflective responses |
| `focus` | Deep blue | Task-oriented, minimal decoration |
| `warm` | Amber/orange | Friendly, conversational tone |
| `alert` | Red/orange | Urgent, concise |
| `creative` | Purple/violet | More exploratory, open-ended |

Mood is set by the user via the mood selector. The selected mood is sent with each chat request and injected into the reply context so Ollama can calibrate tone.

### 32.3 Voice Toggle

A voice toggle button enables/disables voice output (TTS). When on, Nova's text responses are spoken via Piper TTS. The TTS path is `tts_piper.py`. Voice state persists within the session.

### 32.4 Mic Button

A microphone button activates Whisper STT. Holding the button records; releasing sends the audio to Whisper, which transcribes it and submits the text as a chat message. The mic state indicator shows: idle, listening, transcribing.

### 32.5 Listen Mode

A persistent listen mode (distinct from mic button hold) keeps the microphone open and submits on detected silence. Used for hands-free conversation. Toggle from the voice controls area.

### 32.6 Camera

A camera button captures a still frame from the device camera. The captured frame is displayed as a preview in the chat input area. On send, the frame is attached to the message and processed by the vision tool (qwen2.5vl:7b). Camera state: idle, previewing, uploading.

**Camera modes:**
- `live` — shows live camera feed in the input area
- `capture` — takes a still and holds it for review before sending

### 32.7 File Upload

File upload button allows attaching documents to a message. Uploaded files are sent to `POST /api/chat/upload`. Nova processes the file content through the filesystem tool and includes it in the reply context. Supported types include text documents, PDFs, and images.

### 32.8 Session Management

Leah maintains per-user sessions. Session controls:
- **Session label:** Displays current session name (editable). Used to identify the conversation topic.
- **New session:** Start a fresh conversation (preserves memory but clears context window).
- **Load history:** Fetch and display earlier messages from the current session via `GET /api/chat/history`.
- **Resume:** `GET /api/chat/resume` — restores the in-progress session after page reload.

### 32.9 Presence Bar

The presence bar is the left column status display. Shows:

**Voice chip:** Active when voice output is on. Displays current TTS voice name.

**Memory chip:** Active when Nova has relevant memory context loaded for the session. Clicking shows a summary of what memory is active.

**Activity feed:** A log of recent Nova background activity visible to the user: tool executions, memory stores, subconscious advisory triggers. Items auto-expire after a configurable time.

### 32.10 Pulse Field

A subtle animated element that reflects Nova's current processing state:
- Idle: slow pulse
- Processing: faster pulse
- Voice output active: synchronized to speech rhythm
- Error state: irregular pulse

### 32.11 Chat API

**GET `/api/chat/history`:** Returns message history for the current session. Paginated. Each message: role (user/assistant), content, timestamp, tool used (if any), route taken.

**POST `/api/chat` (via chat runtime):** Sends a user message. Body: `{ message, mood, session_id, voice_enabled }`. Response: server-sent event stream of the reply.

**GET `/api/chat/resume`:** Returns current session state and in-progress turn (if any). Used on page load to restore UI state.

**POST `/api/chat/upload`:** Uploads a file. Returns a file reference ID that is included in the next chat message.

### 32.12 Status Indicators

In the Leah header:
- **Nova status dot:** Green (healthy), yellow (degraded), red (critical). Reflects the health score.
- **Model indicator:** Shows the active chat model name.
- **Memory scope indicator:** Shows the current memory scope (conversation/identity/knowledge).

---

## 33. HTTP API Reference

**Base URL:** `http://localhost:8090`

### GET Routes

| Path | Auth | Description |
|------|------|-------------|
| `/` | None | Redirect to `/control` or `/control/login` |
| `/control` | Control password | Operator control panel HTML |
| `/control/login` | None | Control panel login page |
| `/leah` | User auth | Leah chat UI HTML |
| `/leah/login` | None | Leah login page |
| `/api/health` | None | Health check — returns `{"ok": true}` |
| `/api/chat/history` | User auth | Chat message history |
| `/api/chat/resume` | User auth | Resume current session |
| `/api/control/status` | Control | Full status payload (all subsystems) |
| `/api/control/policy` | Control | Current policy.json contents |
| `/api/control/metrics` | Control | Current metrics snapshot |
| `/api/control/work-trees` | Control | Work Tree branch list |
| `/api/control/pipelines` | Control | Pipeline registry |
| `/api/control/sessions` | Control | Active HTTP session list |
| `/api/control/test-sessions` | Control | Test session definitions |

### POST Routes

| Path | Auth | Description |
|------|------|-------------|
| `/api/control/login` | None | Control panel auth |
| `/api/control/logout` | Control | Control panel logout |
| `/api/chat/login` | None | Leah user auth |
| `/api/chat/logout` | User auth | Leah logout |
| `/api/chat/upload` | User auth | File upload for chat |
| `/api/control/action` | Control | Dispatch a control action (all actions above) |

### Control Action Dispatch Format

```json
POST /api/control/action
{
  "action": "<action_type>",
  "payload": { ... }
}
```

Response:
```json
{
  "ok": true | false,
  "message": "...",
  "extra": { ... }
}
```

---

## 34. Data Stores

| File | Format | Content |
|------|--------|---------|
| `work_tree.db` | SQLite | Work Tree: trees, branches, tasks |
| `nova_memory.sqlite` | SQLite | Memory records (all scopes) |
| `runtime/ops_journal.jsonl` | JSONL | Operational event journal |
| `runtime/autonomy_orchestrator_ledger.jsonl` | JSONL | Every autonomy decision |
| `runtime/memory_events.jsonl` | JSONL | Memory store/delete/corruption events |
| `runtime/operator_outbox.jsonl` | JSONL | Operator outbox notices |
| `runtime/control_action_audit.jsonl` | JSONL | All dispatched control actions |
| `runtime/autonomy_maintenance_state.json` | JSON | Maintenance cycle state |
| `runtime/core_state.json` | JSON | Core process state |
| `runtime/guard_pid.json` | JSON | Guard PID and state |
| `runtime/guard_boot_history.json` | JSON | Guard restart history |
| `runtime/memory_health_snapshot.json` | JSON | Last memory health check |
| `runtime/behavior_metrics.json` | JSON | Accumulated behavior metrics |
| `runtime/http_chat_sessions.json` | JSON | Active Leah sessions |
| `runtime/device_location.json` | JSON | Device location (operator-set) |
| `runtime/core.heartbeat` | Text | Timestamp of last core heartbeat |
| `runtime/exports/` | Directory | Release artifacts |
| `runtime/validation/` | Directory | Validation run outputs |
| `runtime/actions/` | Directory | Per-action output files |
| `policy.json` | JSON | Active policy configuration |
| `package_manifest.json` | JSON | Release artifact manifest |
| `backend_command_deck.json` | JSON | Registered backend commands |
| `operator_macros.json` | JSON | Saved operator macros |
| `capabilities.json` | JSON | OS capability definitions |
| `logs/` | Directory | Rotating log files |

---

## 35. Cross-System Interaction Map

This section describes the key integration seams: which subsystem calls which, and what data flows between them.

### Turn Lifecycle

```
Leah / CLI
  → nova_http_chat_runtime / nova_cli_loop
    → nova_intent_understanding (classify)
      → nova_planner_contract (select route)
        → supervisor_runtime (own/not-own)
        → fulfillment_flow (tool execution)
          → tool_registry (select tool)
          → tool_execution (run + validate)
            → filesystem_tool / research_tool / vision_tool / etc.
        → nova_fallback_flow (direct LLM)
      → nova_reply_sequence (build context + call Ollama)
        → memory_routing (inject memory)
        → nova_ollama_chat (stream response)
      → nova_http_turn_finalization
        → nova_action_ledger (write record)
        → nova_memory_learning (learn from turn)
        → subconscious_live_simulator (evaluate route)
          → subconscious_work_tree_triage (open branch if pressure)
        → session_state (update subconscious snapshot)
```

### Autonomy Maintenance Cycle

```
nova_scheduler (30s)
  → autonomy_maintenance
    → control_status (full payload assembly)
      → sock_service.get_sock_status_keys (hardware/sock payload)
      → nova_wiring_inventory (gap check)
    → work_tree_signal_ingestion (evaluate all signals)
      → work_tree (open/close/update branches)
    → autonomy_orchestrator.evaluate_next_action (decide)
      → autonomy_execution_gate (gate check)
        → nova_control_action_dispatcher (execute if approved)
    → autonomy_orchestrator_ledger (write decision)
    → subconscious_reporting (emit advisory pressure)
    → operator_outbox (create notices if needed)
```

### SOCK Integration

```
control_status.py
  → sock_service.get_sock_status_keys() [TTL 300s]
    → scan_hardware() [PowerShell]
    → recommend_models() [VRAM tier logic]
    → build_diff() [policy.json comparison]
  → inject sock_hardware_profile, sock_recommendation, sock_policy_diff into payload
  → nova_wiring_inventory (hardware_profile surface — all 3 keys present → gap_count=0)
```

### Signal → Work Tree → Autonomy

```
Signal (e.g., regression drift detected)
  → work_tree_signal_ingestion
    → work_tree.open_branch(source_key="regression_drift", ...)
      → work_tree.db (persisted)
  → autonomy_orchestrator.evaluate_next_action
    → finds READY branch in work_tree
    → scores it above threshold
    → decision: recommend_action("active_work_tree_run_next")
  → autonomy_execution_gate (checks policy)
    → nova_control_action_dispatcher.dispatch("active_work_tree_run_next")
      → work_tree.advance_task(task_id)
```

### Subconscious → Work Tree

```
Turn finalized
  → subconscious_live_simulator (evaluate route quality)
    → pressure signal: e.g., "fallback_overuse"
    → crack_accumulation (rolling window +=1)
    → if count >= threshold:
        → subconscious_work_tree_triage
          → work_tree.open_branch(bucket="subconscious", source_key="fallback_overuse")
    → subconscious_training_backlog (emit backlog entry)
  → session_state.update_subconscious_state()
```

### Health Check Flow

```
GET /api/control/status
  → control_status.py (assemble payload)
    → all subsystem status getters
  → control_telemetry.build_self_check(status, policy, metrics)
    → 22 named checks → health_score
  → return full payload including self_check, health_score, wiring_inventory
```

---

## 36. CLI Reference

All commands run via `nova.cmd` (or `python nova.ps1` on Windows).

| Command | Description |
|---------|-------------|
| `nova run` | Start Nova (guard + core) |
| `nova stop` | Stop Nova gracefully |
| `nova restart` | Restart the core process |
| `nova time` | Run temporal review; show upcoming scheduled items |
| `nova wiring-check` | Run wiring inventory check (requires live server) |
| `nova wiring-check --offline` | Run wiring check without Ollama |
| `nova package-build` | Build release artifact from current source |
| `nova package-verify` | Verify artifact integrity (checksums, manifest) |
| `nova package-validate` | Run full validation suite against artifact |
| `nova package-promote` | Promote artifact to active release |
| `nova doctor` | Run health check suite; print results |
| `nova diag` | Full diagnostic output (all subsystem state) |
| `python health.py check` | Minimal health check (heartbeat, Ollama, GPU, mic, camera) |
| `python health.py diag` | Extended diagnostics |
| `python health.py repair` | Attempt auto-repair of detected issues |
| `python run_regression.py` | Run full regression suite (all lanes) |
| `python smoke_test.py` | Quick smoke test of core HTTP endpoints |
| `python diag_ollama_check.py` | Check Ollama model availability |

---

*Document generated 2026-06-14 from live codebase inspection on branch `codex/push-prep`.*
*Hardware: Rogue_One — AMD Ryzen AI 9 HX 370, 32 GB RAM, RTX 4050 Laptop 6 GB, AMD XDNA 2 NPU.*
