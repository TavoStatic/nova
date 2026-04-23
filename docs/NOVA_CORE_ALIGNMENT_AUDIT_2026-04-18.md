# Nova Core Alignment Audit

Date: 2026-04-18

## Scope

This audit covers remaining ownership still authored inline in `nova_core.py` after the service extractions already documented in `This_is_nova`.

## Cross-Checked Summary

`nova_core.py` has been thinned significantly, but it is still the execution gravity well for the whole runtime.

The good news:

- several previously large seams are already delegated to services.
- tool dispatch, command handling, ollama chat, truth/query support, and parts of followup/profile handling already have real service owners.

The remaining problem:

- `nova_core.py` still directly owns too much deterministic identity/history reply logic, reply-contract/outcome shaping, truthful-limit behavior, and classification glue.

## What Is Already Thin Enough

Cross-checked against the recovery log, these areas should stay put unless a concrete bug appears:

- tool-dispatch and ollama-chat wrappers that already delegate to their service owners
- command-handler delegation
- several supervisor/followup/profile service bridges already made live
- runtime-context path ownership

## Remaining Inline Ownership

### 1. Deterministic identity, creator, and name-origin handling is still heavily shell-authored

Current inline ownership still includes:

- `hard_answer(...)`
- `_is_identity_or_developer_query(...)`
- `_is_assistant_name_query(...)`
- `_is_self_identity_web_challenge(...)`
- `_self_identity_web_challenge_reply(...)`
- `_assistant_name_reply(...)`
- `_is_developer_full_name_query(...)`
- `_developer_full_name_reply(...)`
- creator/profile/name-origin decision branches inside supervisor-intent handling

Why this is still a drift risk:

- identity behavior is split between supervisor rules, truth hierarchy, hard answers, and followup helpers.
- this is exactly the type of logic that drifts when a shell adds one more special case “just to keep behavior working.”

Best next extraction:

- consolidate deterministic identity/history answers into one explicit identity-answer owner and make the shell call it.

### 2. Reply-contract and outcome-shaping logic is still concentrated in the shell

Current inline ownership still includes:

- `REPLY_TEMPLATES`
- `render_reply(...)`
- `_attach_reply_outcome(...)`
- `_classify_set_location_outcome(...)`
- `_classify_correction_outcome(...)`
- `_classify_store_fact_outcome(...)`
- `_classify_weather_lookup_outcome(...)`
- `_execute_weather_lookup_outcome(...)`
- `_classify_name_origin_outcome(...)`
- `_execute_identity_history_outcome(...)`
- `_execute_retrieval_followup_outcome(...)`
- `_classify_web_research_outcome(...)`

Why this is still a drift risk:

- reply contracts are supposed to be a reusable behavior seam, but the classification/rendering table still lives in the main shell.
- that means contract changes can still bypass the service layer and land only in `nova_core.py`.

Best next extraction:

- move reply-contract templates plus outcome classifiers/executors into a dedicated reply-contract/outcome service.

### 3. Truthful-limit and open-fallback behavior is still shell-authored

Current inline ownership still includes:

- `_open_probe_reply(...)`
- `_truthful_limit_reply(...)`
- `_attach_learning_invitation(...)`
- `_truthful_limit_outcome(...)`
- low-confidence and factual-query gating helpers around fallback policy

Why this is still a drift risk:

- fallback behavior is product behavior, not just convenience text.
- if this logic stays inline, HTTP and CLI can still drift by invoking or reshaping it differently.

Best next extraction:

- move truthful-limit and fallback-response shaping into one shared fallback-contract owner.

### 4. Truth hierarchy is still partly a shell implementation rather than only a service call

Current inline ownership still includes:

- `truth_hierarchy_answer(...)`
- action-history, capability, policy, and identity query routing inside the shell

Why this is still a drift risk:

- even with supporting services present, the main truth-order function still lives in `nova_core.py`.
- that keeps ownership-order changes dangerously close to the shell.

Best next extraction:

- finish moving truth-hierarchy routing into a dedicated truth owner and leave only a shell wrapper in `nova_core.py`.

### 5. Query-classification glue is still broad and easy to fork

Current inline ownership still includes:

- `_is_factual_identity_or_policy_query(...)`
- `_is_capability_query(...)`
- `_is_policy_domain_query(...)`
- `_is_action_history_query(...)`
- identity/name-origin/full-name/location/session-recap/deep-search request detection helpers

Why this is still a drift risk:

- these helpers are small, but together they define large parts of turn ownership.
- classification glue spread across the shell invites accidental duplication in CLI and HTTP callers.

Best next extraction:

- consolidate these remaining classifiers into the query/routing support services that already exist.

### 6. Retrieval followup and session recap presentation still live in the shell

Current inline ownership still includes:

- `_session_recap_reply(...)`
- `_last_question_recall_reply(...)`
- `_session_fact_recall_reply(...)`
- retrieval-followup guidance/meta-selection presentation

Why this is still a drift risk:

- these are conversational state behaviors, not core-execution primitives.
- they should live beside the followup/session-state services rather than inside the main shell.

Best next extraction:

- move recap and retrieval-followup presentation into session/followup service owners.

## Priority Order Inside `nova_core.py`

1. deterministic identity/history answer ownership
2. reply-contract and outcome-shaping layer
3. truthful-limit and fallback-response shaping
4. truth-hierarchy implementation
5. classification glue
6. retrieval/session recap presentation helpers

## Keep / Realign / Leave Alone

Keep:

- `nova_core.py` as the execution shell and orchestration center
- policy loading, persistence wiring, action-ledger lifecycle, and top-level execution glue

Realign:

- deterministic identity/profile/history ownership
- reply-contract classification/rendering
- truthful-limit and learning-invitation shaping
- truth-order implementation
- classifier sprawl

Leave alone for now:

- already-extracted wrappers whose service owner is known and live

## Working Rule

If a new deterministic reply family needs to be added, do not add another branch directly to `nova_core.py` unless the shell is only forwarding to the real owner. The shell should orchestrate; it should not silently become the behavior owner again.