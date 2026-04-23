# Nova Memory System Plan

## Purpose

Nova already has several memory mechanisms, but they are not yet governed as one explicit system. This plan defines how Nova should set up, interact with, organize, and use all memory types efficiently.

The goal is simple:
- use the smallest memory lane that can solve the turn
- write only durable signal
- read only the lanes that are relevant to the current task
- keep operator and maintenance memory visible without leaking it into chat replies

## Memory Lanes

### 1. Session Working Memory

Owner surfaces:
- `conversation_manager.py`
- `http_session_store.py`
- HTTP session payloads
- pending-action and continuation state in the supervisor/runtime flow

Purpose:
- hold the live thread state for the current conversation
- track what the user is doing right now
- preserve followups, pending tasks, retrieval/result references, and continuation intent

Should store:
- active subject
- pending tool/result references
- short-lived continuation markers
- unresolved clarification state
- current task bindings

Should not store:
- long-term identity facts
- broad user preferences unless explicitly confirmed
- operator telemetry

Read rule:
- always read this lane first for followups and continuations

Write rule:
- update on every turn when state changes
- expire aggressively when the thread resolves or is abandoned

Efficiency rule:
- followup resolution should prefer session state over re-querying durable memory or re-matching keywords

### 2. Identity Memory

Owner surfaces:
- `services/identity_memory.py`
- identity files under `memory/`
- deterministic identity handlers in the runtime

Purpose:
- store Nova identity and tightly-scoped developer/user identity bindings
- protect identity-only sessions from general memory bleed

Should store:
- assistant name
- developer identity bindings
- tightly controlled user identity anchors when explicitly confirmed

Should not store:
- general chat facts
- inferred personality traits
- broad profile guesses

Read rule:
- deterministic identity paths should consult this lane before generic recall

Write rule:
- allow only approved prefixes and deterministic fact shapes
- reject inferred or freeform identity text

Efficiency rule:
- identity memory must stay small, exact, and deterministic so identity questions never depend on broad semantic retrieval

### 3. Durable User Memory

Owner surfaces:
- `memory.py`
- `services/memory_adapter.py`
- `services/nova_memory_learning.py`
- `nova_memory.sqlite`

Purpose:
- store durable user facts, preferences, and reusable context that helps future turns

Current capabilities:
- semantic embedding recall
- lexical fallback
- explicit `private`, `shared`, and `hybrid` scopes
- duplicate suppression and write filtering

Should store:
- explicit user preferences
- stable facts the user asked Nova to remember
- durable project facts that matter across sessions
- learned facts with clear future value

Should not store:
- questions
- acknowledgements
- UI noise
- assistant-authored text
- one-off ephemeral statements unless promoted deliberately

Read rule:
- query only when the turn references prior facts, preferences, identity-adjacent continuity, or unresolved project context
- do not inject broad recall into every turn

Write rule:
- write only after heuristic or classifier approval
- prefer explicit remember/teach signals and durable declarative statements
- respect scope and active user consistently

Efficiency rule:
- durable recall should be budgeted by intent, score threshold, and context slot count, not dumped into prompts by default

### 4. Knowledge Memory

Owner surfaces:
- `knowledge/`
- allowlisted web/cache flows
- local packs and grounded retrieval helpers

Purpose:
- provide repo-local or operator-loaded knowledge that is not personal memory

Should store:
- domain packs
- curated local documents
- grounded web captures when explicitly retained

Should not store:
- personal identity facts
- transient operator telemetry
- subconscious training noise

Read rule:
- use when the task needs domain grounding rather than personal continuity

Write rule:
- writes should be explicit ingestion or governed capture, not automatic byproducts of ordinary chat

Efficiency rule:
- knowledge retrieval should compete with web/tool routing, not masquerade as personal memory

### 5. Operational Memory

Owner surfaces:
- `runtime/actions/*.json`
- `runtime/memory_events.jsonl`
- control telemetry/status payloads
- release and patch governance ledgers

Purpose:
- preserve runtime truth, observability, and operator-audit history

Should store:
- route decisions
- memory operation events
- control actions
- release/patch outcomes
- runtime health summaries

Should not store:
- prompt context for normal chat replies unless a deterministic operator view explicitly asks for it

Read rule:
- use for control room, debugging, audits, and self-observation

Write rule:
- append structured events, not narrative blobs

Efficiency rule:
- operational memory must stay inspectable and queryable, but it should never become a silent source of conversational context bleed

### 6. Maintenance And Training Memory

Owner surfaces:
- `runtime/subconscious_runs/`
- generated test-session definitions
- `runtime/autonomy_maintenance_state.json`
- kidney/autonomy artifacts

Purpose:
- remember where the system is drifting, what families are failing, and what cleanup or training pressure exists

Should store:
- generated scenario families
- subconscious robustness reports
- maintenance pressure summaries
- cleanup/archive decisions

Should not store:
- direct user-facing conversational context
- generic facts that belong in durable memory

Read rule:
- used by autonomy, steward scoring, queue triage, and operator review

Write rule:
- generated by maintenance systems and explicit operator actions only

Efficiency rule:
- this lane should influence governance and follow-up work, not silently bias end-user replies

## Read Order

Nova should prefer this read order:

1. Session working memory
2. Deterministic identity memory when the turn is identity-bound
3. Durable user memory when the turn references prior user/project context
4. Knowledge memory when the turn needs domain grounding
5. Operational memory only for operator/debugging paths
6. Maintenance memory only for steward, autonomy, queue, and review paths

If a higher lane answers the need, Nova should not open lower lanes.

## Write Order

Nova should prefer this write order:

1. Update session state immediately when the turn changes the active thread
2. Write identity memory only through deterministic approved shapes
3. Write durable memory only after a keep/promote decision
4. Write operational events for every important memory action
5. Write maintenance artifacts only from governed maintenance flows

## Required Runtime Behavior

## Implementation Checkpoint

Implemented now:
- durable recall is routed through a shared memory-routing service instead of opening directly from shell code
- durable recall now records lane, purpose, and skip reason in memory events
- generic fallback-context building now passes conversation state and pending action into the recall router
- control-room memory telemetry now shows lane counts, recall purposes, skip reasons, and the last memory event metadata

Not done yet:
- all profile/developer helper families are not fully migrated to a single shared memory-read contract outside the remaining compatibility wrappers
- the control room does not yet show per-lane hit rate and read-to-reply impact as first-class metrics
- session working memory still needs a more explicit operator-visible summary so it is easier to see when session state correctly outranks durable recall

### Memory should be intent-gated

Nova should not inject durable memory into all prompts. Retrieval should happen for turns such as:
- prior-reference questions
- profile/preference continuity
- explicit remember/recall requests
- active project continuation

### Every memory read should declare why it happened

The runtime should be able to answer:
- which lane was read
- why that lane was opened
- how many results were used
- whether the read changed the reply

### Every memory write should declare why it was kept

The runtime should log a keep reason such as:
- identity-approved
- explicit remember
- durable fact
- project continuity
- policy include

and a skip reason such as:
- question
- ack
- ui_noise
- duplicate
- low_signal
- missing_user

## Near-Term Implementation Steps

1. Add one shared memory-routing service that decides which lane(s) may be read for a turn before fallback or tool routing opens them ad hoc.
2. Add a write-intent classifier that distinguishes identity, durable user fact, operational event, and maintenance artifact instead of relying mainly on text-shape heuristics.
3. Add per-lane budgets so durable recall cannot exceed a fixed context quota and session state always outranks semantic recall.
4. Add compaction and expiry rules for session and maintenance memory so old pressure does not look like fresh truth.
5. Extend control-room telemetry so operators can see memory reads/writes by lane, hit rate, skip reason, and scope.

## Straight Rule

Nova should treat memory as a layered system, not one bucket. Session state should solve followups, identity memory should solve identity, durable memory should solve continuity, knowledge should solve grounding, operational memory should solve observability, and maintenance memory should solve system self-governance.
