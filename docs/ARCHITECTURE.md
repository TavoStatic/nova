# Nova Architecture

## Main Components

- `nova_core.py`
  - policy loading and mutation
  - deterministic command and truth-hierarchy handling
  - in-process memory service wrappers over `memory.py`
  - structured memory-event logging for writes, recalls, audits, skips, and stats
  - per-turn action ledger with ordered route traces for decision-path observability
  - tool orchestration and teach/patch logic

- `nova_http.py`
  - browser chat UI and control room
  - persistent HTTP sessions and owner binding
  - optional control login and optional chat login
  - admin actions for guard, policy, memory scope, and managed chat users

- `memory.py`
  - SQLite-backed storage in `nova_memory.sqlite`
  - semantic recall with lexical fallback
  - explicit `private`, `shared`, and `hybrid` scope support
  - direct callable service layer used by `nova_core.py` and CLI entrypoints

- `nova_guard.py`
  - process supervision
  - heartbeat and runtime state tracking

- `run_tools.py` and `chat_client.py`
  - client-side access to `/api/chat`
  - identity propagation
  - optional login when chat auth is enabled

- `tools/`
  - shared tool contract via `NovaTool` and `ToolContext`
  - registry-backed dispatch from `run_tools.py`
  - manifest and structured tool-event logging

## Current Identity and Privacy Model

- HTTP chat sessions are persisted and bound to a session owner.
- Active users in `nova_core.py` are thread-local rather than global.
- Memory reads and writes respect policy-driven scope behavior.
- The browser and CLI both send stable `user_id` values.
- Chat login may be backed by:
  - managed local file: `runtime/chat_users.json`
  - env JSON fallback: `NOVA_CHAT_USERS_JSON`
  - single env pair fallback: `NOVA_CHAT_USER` and `NOVA_CHAT_PASS`

## Control Room

The control room now exposes:

- runtime health and telemetry
- session manager
- guard control
- domain and web mode policy changes
- memory scope administration
- memory totals in live status telemetry
- managed chat-user administration
- diagnostics export and log tail actions

## Important Runtime Paths

- `runtime/http_chat_sessions.json`: persisted HTTP chat sessions
- `runtime/chat_users.json`: managed chat-user store
- `runtime/control_action_audit.jsonl`: control room audit events
- `runtime/policy_changes.jsonl`: policy mutations
- `runtime/tool_events.jsonl`: structured tool execution events
- `runtime/memory_events.jsonl`: structured memory operation events
- `runtime/actions/*.json`: per-turn action ledger records including route trace and final planner decision
- `runtime/exports`: exported diagnostics and snapshots

## Request Flow Diagram

```text
User Input
  ↓
HTTP UI / CLI / Tool Runner
  ↓
nova_http.py / chat_client.py / run_tools.py
  ↓
nova_core.py
  ↓
policy + deterministic routing
  ↓
memory lookup
  ↓
tool invocation (optional)
  ↓
response assembly
  ↓
UI / CLI output
```

## Architectural Shape

Nova is currently closer to a consolidating `B` shape than a fully layered `A` shape.

- `nova_core.py` is the de facto center of gravity and is absorbing more of the policy, memory, deterministic routing, and tool orchestration logic.
- `nova_http.py`, `chat_client.py`, and `run_tools.py` still interact with multiple cross-cutting concerns rather than through a strict interface boundary.
- The project is entering the architecture consolidation phase, but it is not yet a clean interface-to-core-to-tools stack.

The likely next turning point is to formalize clearer boundaries around:

- interface adapters
- core orchestration
- tool execution contracts
- memory and persistence services

The first concrete step in that direction is now present: the tool boundary has a shared base contract, a registry, and manifest-backed inventory instead of only open-coded dispatch.

That boundary is now also used by `nova_core.py` for local filesystem, vision, health-style operator actions, and patch-governed mutation flows, which moves Nova one step closer to a true interface-to-core-to-tools shape rather than parallel execution paths.

Patch execution is still separately governed, but it is no longer outside the tool system. It now has an explicit contract, admin gate, and policy surface while remaining intentionally stricter than ordinary operator tools.

## Decision Spine

The current architectural direction should be understood as a single decision spine, not a single monolithic processor.

The rule is:

- one routing authority owns turn classification and dispatch decisions
- execution remains distributed across specialized paths
- tools are capabilities selected by the decision spine, not automatic keyword triggers

That means Nova should prefer this shape:

1. turn interpreter
2. task dispatcher
3. specialized execution path
4. response synthesis

In practical terms, the decision spine should answer only a few questions:

- what kind of turn is this
- is a direct answer possible
- is clarification required
- should this dispatch to a tool path, research path, memory path, or heavier workflow

It should not become the heavy processor for every task. Large retrieval, multi-step workflows, document processing, research expansion, and tool execution should remain outside the routing core once the lane has been chosen.

The design sentence for this phase is:

Nova should have a single decision spine for understanding and dispatch, but execution should remain distributed across specialized paths so orchestration stays coherent without becoming a performance bottleneck.

That shape now has an explicit planner boundary:

- turn understanding lives in `planner_decision.py`
- route classification lives in `planner_decision.py`
- execution choice is mapped back into planner actions before `nova_core.py` and `nova_http.py` dispatch to specialized handlers
- `action_planner.py` is now a thin adapter over that decision module rather than the primary home for mixed string heuristics

## Current Refactor Risk

Nova no longer has the earlier CLI-only split-brain condition where planner routing and direct command/keyword routing both acted as independent authorities.

The current shape is now:

- one planner-owned routing spine in CLI and HTTP
- legacy command and keyword handlers retained as execution targets
- action-ledger traces proving planner ownership of delegated command and keyword routes

The next cleanup priority is therefore not basic route ownership. It is keeping the decision module coherent as coverage grows so:

- one layer owns classification
- one layer owns dispatch choice
- execution helpers remain specialized and reusable
- planner heuristics do not collapse back into one large mixed file

## Request Flow Summary

1. Client submits to `/api/chat`.
2. `nova_http.py` resolves chat auth and request identity.
3. Session ownership is enforced for persisted sessions.
4. Deterministic paths run first.
5. Memory/context is added when appropriate.
6. LLM fallback is used only when deterministic paths do not answer.
7. The final route is written to the action ledger so operators can inspect why that path was chosen.