<!--
NOVA_DOC
category: subsystem
authority: active_working
last_session: 2026-08-05
last_agent: claude-cowork
session_state: needs_update
next_step: supervisor rules still empty — Task #43
open: Task 43: populate supervisor rules
-->

# Supervisor Ownership Constitution

Last checked against code: 2026-07-12

This file is the intended enforcement contract for deterministic behavior in Nova.

## Current Implementation Status (2026-08-05)

Four rules are registered. The seam is no longer empty.

| Rule | Phase | Owning | Purpose |
|---|---|---|---|
| `intent_move_classify` | intent | No | Classifies user move from 8 required categories (correction, redirect, meta_repair, confusion, state_declaration, selection, continuation, open_question) |
| `identity_location_guard` | handle | **Yes** | Intercepts identity/location queries before they reach local knowledge retrieval; fires RED on `identity_location_route` probe |
| `ambiguous_clarifier_gate` | handle | No | Detects bare ambiguous tokens ("what?", "ok", single-word clarifiers); annotates candidates for routing trace |
| `safe_fallback_contract` | handle | No | Flags tool-directed and factual-domain queries that should not fall through to generic llm_fallback; surfaces `rule_coverage` probe pressure |

Files:
- `services/supervisor_rules.py`: rule implementations + `DEFAULT_RULE_HANDLERS`
- `services/supervisor_registry.py`: `DEFAULT_SUPERVISOR_RULE_SPECS` (4 entries)
- `supervisor.py`: `_EXPLICIT_HANDLE_OWNERSHIP_RULES = {"identity_location_guard"}`
- `services/supervisor_authority.py`: matching explicit ownership sets

Remaining gaps:
- `safe_fallback_contract` is non-owning — it surfaces pressure but doesn't prevent the fallback. Elevate to owning once a safe fallback contract exists in the fulfillment path.
- `intent_move_classify` annotates candidates but the fulfillment path does not yet read the intent annotation to inform routing decisions.
- No purity regression tests yet for supervisor-owned turns.

The constitution below describes the full target. The rules above are the first implementation step — not the complete picture.

## Constitution

1. Every deterministic behavior MUST start as a supervisor rule in `intent` or `handle` phase.
2. `nova_core.py` MAY NOT own new phrase-to-action mapping outside supervisor.
3. `nova_core.py` MAY ONLY execute actions selected by supervisor.
4. `nova_http.py` MAY NOT own routing or deterministic logic. It MUST mirror core execution of supervisor actions.
5. Bypassing supervisor `intent` or `handle` phase is a bug. In development, any unallowlisted bypass must raise immediately.
6. Every turn should carry a structured `routing_decision` record so supervisor ownership, fallback use, and allowlisted bypasses are inspectable in ledger/reflection artifacts.
7. A small set of explicitly intentional model-owned prompts may remain allowlisted, but they must be categorized clearly so they are not confused with unmigrated deterministic debt.
8. Unmatched open-ended turns in the closed answer-path slice must not continue into generic no-contract fallthrough. They should terminate through the existing safe fallback contract instead.

## Interpretation Precedence

Supervisor intent and handle phases MUST interpret turns in this order:

1. classify the user's move first
2. check active task and pending-slot state second
3. check whether ambiguity remains
4. classify domain/content only after steps 1-3
5. ask a clarifying question if multiple interpretations remain plausible

The required move-first categories are:

- answering an open question
- declaring or updating state
- correcting Nova
- selecting from prior results
- continuing an active thread
- redirecting to a new task
- asking for meta-analysis or repair
- expressing confusion or challenge

Hard rules:

- content shape MUST NOT be the first classifier
- a scalar, short phrase, ordinal, pronoun, or other low-information token is ambiguous by default
- active-task context may constrain interpretation, but it may not blindly swallow explicit declarations, corrections, or meta turns
- if the system cannot defend a single interpretation after move classification and active-task checks, it MUST ask instead of binding the content to a domain

Examples of forbidden first-step classification:

- `78521` -> `zip code`
- `first one` -> `retrieval selection`
- `what else?` -> `continue current thread`

Those may become valid interpretations later, but only after supervisor has determined what the user is trying to do with the content in the current turn.

## Required Change Pattern

Every new deterministic behavior must be expressed as:

1. A new or extended supervisor rule.
2. A shared core executor branch for the supervisor-selected action.
3. Surface wiring that only passes the supervisor result through shared execution.
4. A regression or purity test proving the turn is claimed by supervisor.

For answer-path closure specifically:

1. open-ended fallback should prefer a supervisor-owned safe fallback contract over generic model-owned drift
2. clarification replies should resolve through supervisor-owned contracts when the phrase is a real clarification, but weak bare clarifiers like `what?` must not be over-owned without stronger thread evidence
3. identity-history and profile followups should carry reply contracts in both CLI and HTTP rather than falling through as no-contract chat behavior

## Forbidden Shortcuts

Do not add new phrase detection branches directly in:

- `nova_core.py` main loop
- `nova_http.py` request flow
- CLI or HTTP-only special cases that bypass supervisor selection

If a fix needs a new `if` or `elif` for deterministic routing in those files, stop and add a supervisor rule instead.

The only narrow exception is a shared contract-preserving short-circuit that prevents a known legacy fallback branch from bypassing an already established supervisor contract or safe fallback contract. That exception must reduce drift, not create a new route owner.

## Review Checklist

Before merging deterministic behavior changes, verify:

- supervisor rule exists and is registered
- move-first interpretation precedence is preserved in supervisor intent/handle logic
- core executes a supervisor-selected action
- HTTP mirrors core instead of forking behavior
- purity tests still pass
- route traces or warnings make supervisor ownership visible
- `routing_decision` captures supervisor intent/handle candidates plus any allowlisted bypass category
