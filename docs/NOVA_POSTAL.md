<!--
NOVA_DOC
category: architecture
authority: active_authority
last_session: 2026-08-05
last_agent: claude-cowork
session_state: current
next_step: none
open: none
-->

# Nova Postal Office

**Read this before touching any file in this project.**
This is the routing system for everything written about Nova — by developers, by agents, by Nova herself.

---

## Three-Phase Agent Protocol

### Phase 1 — Arriving

You just opened this project. Do this before scanning, diagnosing, or changing anything:

1. Read `AGENTS.md` (root) — non-negotiables and working rules
2. Read `docs/NOVA_LEDGER.md` — what is current, what is stale, what sessions have run
3. Read `docs/NOVA_POSTAL.md` (this file) — where everything lives, where to put what you write
4. Check the ledger's **Drift Alerts** section — know which indices lag before you rely on them

Do not start scanning or writing until you have done these four things.

### Phase 2 — Working

Use the routing tables below to find what you need and put things where they belong.

Rule: **if it already exists, update it — do not create a parallel version.**
Rule: **files stay where they live — give them order, do not move them.**
Rule: **if you can't find it, check the ledger before creating anything new.**

### Phase 3 — Leaving

Before closing the session:

1. Log the session:
   ```bash
   python scripts/log_session.py \
     --tool <tool-name> \
     --session-id "<short-id>" \
     --modules "<file1.py,file2.py>" \
     --changes "<what changed>" \
     --tests <count> \
     --docs-added "<docs/NEW.md>" \
     --notes "<optional note>"
   ```
2. Regenerate the ledger: `python scripts/generate_nova_ledger.py`
3. If you found a file with no clear home, register it: `python scripts/nova_ledger_ingest.py --entry-type doc_classification ...`
4. Leave the project in a state the next agent can pick up without asking you anything

---

## Routing Tables by File Type

### `.md` files — Markdown documents

| What you need | Where it lives |
|---|---|
| Where everything is and what's current | `docs/NOVA_LEDGER.md` — always start here |
| Agent rules and non-negotiables | `AGENTS.md` (root) |
| This routing document | `docs/NOVA_POSTAL.md` (here) |
| What authority each doc has | `docs/DOC_OWNERSHIP.md` |
| How Nova is designed | `docs/ARCHITECTURE.md` |
| Process topology, APIs, wiring surfaces | `docs/SYSTEM_MAP.md` |
| What each service module does | `docs/SERVICES_INDEX.md` |
| What each function does | `docs/FUNCTION_INDEX.md` (check ledger — may be stale) |
| Autonomy, mission, Work Tree contracts | `docs/AUTONOMY_AND_MISSION.md` |
| Test lanes and test inventory | `docs/TEST_ECOSYSTEM.md` → `docs/TEST_INDEX.md` |
| Data pipeline architecture | `docs/DATA_PIPELINES.md` |
| Operational procedures | `docs/OPERATIONS.md` |
| Nova's behavioral contracts | `docs/NOVA_COACHING_*.md` |
| Decision Judge design | `docs/DECISION_PROPOSAL_JUDGE.md` |
| Self-scan rings design | `docs/SELF_SCAN_RINGS_DESIGN.md` |
| SOCK hardware system | `docs/SOCK_SYSTEM.md` |
| Hardware optimizer decisions | `docs/NOVA_LEDGER.md` → Architectural Decisions |

**Where to write new `.md` files:**
- All new markdown docs go to `docs/` — not root
- Register every new file in `docs/DOC_OWNERSHIP.md` and the ledger
- Do not create a new doc if an existing one covers the topic — update it instead

---

### `.py` files — Python source and scripts

| What you need | Where it lives |
|---|---|
| Service modules (runtime, services) | `services/` |
| Entry point processes | `nova_core.py`, `nova_guard.py`, `nova_http.py`, `autonomy_maintenance.py` (root) |
| Developer CLI tools | `scripts/` |
| Test files | `tests/` |
| OS capability scripts (PowerShell wrappers) | `tools/os_capabilities/` |
| Codegen tools | `tools/codegen_tool.py` |

**Where to write new `.py` files:**
- New service logic → `services/`
- New developer tools → `scripts/`
- New tests → `tests/`
- New OS capability scripts → `tools/os_capabilities/`
- After adding a service: update `docs/SERVICES_INDEX.md` and `docs/SYSTEM_MAP.md`
- After adding functions: regenerate `docs/FUNCTION_INDEX.md`

---

### `.jsonl` files — Append-only ledger streams

| What you need | Where it lives |
|---|---|
| Developer session log | `docs/ledger/session_log.jsonl` |
| Nova's scan and finding entries | `docs/ledger/nova_findings.jsonl` |
| Autonomy orchestrator decisions | `runtime/autonomy_orchestrator_ledger.jsonl` |
| Action ledger (per turn) | `runtime/action_ledger.jsonl` |
| OS capability ledger | `runtime/os_capability_ledger.jsonl` |

**Where to write:**
- Developer sessions → `docs/ledger/session_log.jsonl` via `scripts/log_session.py`
- Nova findings, decisions, ring scans → `docs/ledger/nova_findings.jsonl` via `scripts/nova_ledger_ingest.py`
- Never edit JSONL files by hand — use the ingest scripts

---

### `.json` files — Configuration and runtime state

| What you need | Where it lives |
|---|---|
| Policy (tools, models, memory, safety) | `policy.json` (root) |
| Declared capabilities and roadmap | `capabilities.json`, `capabilities_roadmap.json` (root) |
| Live runtime state | `runtime/core_state.json`, `runtime/autonomy_maintenance_state.json` |
| Regression status | `runtime/regression_status.json` |
| Wiring inventory | built by `services/nova_wiring_inventory.py` |

**Where to write:**
- Policy changes → `policy.json` via control actions in the dispatcher — not by hand
- Runtime state → written by Nova's processes, not by developers

---

### `.txt` / no-extension files — Session transcripts and founding artifacts

| What you need | Where it lives |
|---|---|
| Nova's founding action ledger (May 2026) | `This_is_nova` (root, no extension) |
| Codex audit transcript | `codex_audit.txt` (root) |

**Rules:**
- Do not move these files — they are where they are by intent
- Do not rename them — named with intent
- Register them in the ledger with `entry_type: doc_classification` and `authority_class: historical`
- `This_is_nova` stays at root permanently — it is the founding record

---

### `.db` files — SQLite databases

| What you need | Where it lives |
|---|---|
| Work Tree (task graph, branch state, evidence) | `runtime/_internal/work_tree.db` |

**Rules:**
- Never edit directly — use `work_tree.py` API
- Read via `work_tree.list_*` functions or the control panel

---

## Order of Authority

When two sources conflict:

```
1. Live runtime (process state, work tree, maintenance logs)
2. Source code (what the function actually does)
3. Inline docstrings (what the developer said the function does)
4. NOVA_LEDGER.md + session_log (what sessions recorded)
5. docs/ authority files (ARCHITECTURE, SYSTEM_MAP, SERVICES_INDEX)
6. docs/ working files (plans, roadmaps, coaching)
7. Historical / archive (phase docs, old scans, founding records)
```

A lower-numbered source always beats a higher-numbered one regardless of date.
A more recent source beats an older one at the same level.

---

## Product Finish Map

Where to look when working on unfinished product layers:

| Layer | Status | Where to start |
|---|---|---|
| **Runtime core** | Active — primary focus | `AGENTS.md`, `SYSTEM_MAP.md`, `AUTONOMY_AND_MISSION.md` |
| **LEAH** | Observe mode — shell exists, 4 capabilities not built | `docs/LEAH_INSTANCE_PROMOTION_PLAN.md`, `capabilities_roadmap.json` phase_2_leah_build |
| **data connector / backpack** | In progress — warehouse path first-class | `docs/DATA_PIPELINES.md`, `backpacks/edfi/`, `services/backpack_host/` |
| **Codegen / Leah Build** | Wired in governance, not yet active | `capabilities_roadmap.json`, `services/codegen_pipeline.py` |
| **Nova Shell** | Wired into HTTP auth via nova_shell_control_bridge.py (2026-08-05) | `nova_shell/`, `services/nova_shell_control_bridge.py` |
| **Decision Judge** | Active, observe mode (enforce off) | `docs/DECISION_PROPOSAL_JUDGE.md`, `services/decision_proposal_judge.py` |

LEAH capabilities build in order: `leah_conversation_continuity` → `leah_memory_recall` → `leah_voice_persona_engine` → `leah_emotional_state_model`. Do not skip ahead.

---

## What Does NOT Go in `docs/`

| Content | Correct location |
|---|---|
| Runtime state (process state, heartbeat, locks) | `runtime/` |
| Log files | `runtime/logs/` |
| Session transcripts and raw exports | root or `runtime/` — register in ledger |
| Test fixtures and test data | `tests/` |
| Scripts and developer tools | `scripts/` |
| Service modules | `services/` |

Documentation describes Nova. Runtime files are Nova running. Do not mix them.

---

## The One Rule

**If you touched it, document it before you close the session.**

No exception for small changes. No exception for "I'll do it next time."
The next agent will read this file and trust the ledger is current.
