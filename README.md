# NYO AI SYSTEMS

**Nova** is a local AI runtime that keeps working after the conversation ends.

It runs on your Windows machine, uses your local Ollama models, and operates a continuous maintenance loop — reading signals from its own runtime, deciding what to work on next, and executing that work autonomously every 5 minutes.

> Public branding: **NYO AI SYSTEMS** · Internal runtime name: `Nova`

---

## What It Actually Does

Nova runs a cycle every 5 minutes. Each cycle:

1. Reads signals from the runtime — errors, health checks, calendar deadlines, regression results
2. Scores them by pressure and converts them into branches in the task tracker
3. The orchestrator decides which branch to advance and with what tool
4. The result is recorded as evidence and the next cycle picks up from there

This is not triggered by a user message. It runs whether or not anyone is talking to it.

---

## What's Inside

**The process keeper** (`nova_guard.py`) — starts the runtime, restarts it when it crashes with exponential backoff, and triggers the maintenance cycle every 5 minutes. Only one instance runs at a time, enforced by a lock file.

**The task tracker** (Work Tree) — a SQLite database that holds the open problems Nova is working through. Each problem is a branch with individual tool-call steps. Branches have statuses: ready, blocked, stalled, done. The orchestrator advances them one step at a time.

**The decision engine** (Autonomy Orchestrator) — scores each work category by pressure and picks the next action. Categories include: generated work queue, patch queue, active task branches, regression review, and subconscious review. It respects confidence thresholds and policy allow-lists before acting.

**The storage keeper** (Kidney) — scans for stale files on every maintenance cycle: old patch previews, outdated snapshots, bloated temp directories, low-quality generated test files. Archives or deletes them based on age, size, and quality scores.

**Calendar awareness** (Temporal) — reads `.ics` calendar files every 15 minutes, scores upcoming events by deadline pressure, and routes anything above the pressure threshold into the task tracker as a branch to work through.

**The background simulator** (Subconscious) — runs unattended to generate test scenarios, simulate them, and produce candidates for review and promotion into the live system.

**The notice board** (Operator Outbox) — where Nova writes things it wants the operator to know about without waiting for a chat turn. Notices have statuses: new, seen, answered, resolved, dismissed.

**The operator control room** (`/control`) — a web dashboard showing live runtime state: health, task branches, patch queue, calendar events, outbox notices, pipelines, sessions, and logs. Direct state, not summaries.

**Memory** — a SQLite store with embeddings from `nomic-embed-text`. Retrieves context using cosine similarity. Scope system: shared, private, and hybrid. Audio transcriptions are excluded from memory by default.

**The patch system** — stages candidate patches as previews, snapshots the current state before applying, runs a behavioral check after apply, and rolls back if the check fails.

---

## What It Runs On

- **OS**: Windows (required — the guard, TTS, and process management are Windows-native)
- **AI backend**: [Ollama](https://ollama.com) running locally at `127.0.0.1:11434`
- **Chat / routing model**: `qwen2.5:7b`
- **Vision model**: `qwen2.5vl:7b`
- **Memory embedding**: `nomic-embed-text`
- **Speech to text**: Faster-Whisper (`medium`, CPU, int8)
- **Text to speech**: Piper TTS (`en_US-lessac-medium`)
- **Web search**: SearXNG (self-hosted at `127.0.0.1:8081`)

---

## How to Trust What You Read Here

Runtime artifacts are the ground truth. If this README conflicts with what the runtime shows, the runtime is right.

| Artifact | What it tells you |
|---|---|
| `runtime/autonomy_maintenance.log` | What every maintenance cycle did |
| `runtime/core_health_brief.json` | Current health score |
| `runtime/operator_outbox.jsonl` | Open notices waiting for operator response |
| `runtime/_internal/work_tree.db` | Active task branches and their status |
| `runtime/tool_events.jsonl` | Every tool call, its result, and whether it was allowed |

---

## Quick Start

```powershell
.\nova.cmd install
.\nova.cmd doctor
.\nova.cmd run
.\nova.cmd webui-start --host 127.0.0.1 --port 8080
```

Open:
- **Operator control room** → `http://127.0.0.1:8080/control`
- **Leah** → `http://127.0.0.1:8080/leah`

---

## Go Deeper

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- [docs/OPERATIONS.md](docs/OPERATIONS.md)
- [docs/SERVICES_INDEX.md](docs/SERVICES_INDEX.md)
- [docs/PATCHING.md](docs/PATCHING.md)
- [docs/STATUS.md](docs/STATUS.md)
