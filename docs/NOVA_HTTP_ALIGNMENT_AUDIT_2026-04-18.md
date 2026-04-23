# Nova HTTP Alignment Audit

Date: 2026-04-18

## Scope

This audit covers remaining ownership still authored inline in `nova_http.py` after the recent service extractions already recorded in `This_is_nova`.

## Cross-Checked Summary

`nova_http.py` is no longer the old all-inline shell, but it is still the largest live drift surface in the repo.

The good news:

- GET route ownership is now delegated through `services/nova_http_get_routes.py`.
- major chat-runtime seams already exist and are live: turn entry, post-intent orchestration, reply sequence, and turn finalization.
- much of the control/runtime plane already delegates through dedicated services.

The remaining problem:

- `nova_http.py` still owns too much decision glue, payload assembly, and action dispatch directly.
- when those inline clusters drift, the live runtime diverges even if the service copies on disk look correct.

## What Is Already Thin Enough

These areas look like real wrappers rather than fake extractions:

- runtime-control start/stop/restart helpers calling `services/runtime_control.py`
- runtime timeline wrappers calling `services/runtime_timeline.py`
- runtime artifact wrappers calling `services/runtime_artifacts.py`
- logical process/runtime state wrappers calling `services/runtime_process_state.py`
- GET-side route dispatch in `NovaHttpHandler.do_GET(...)`

These are not the first places to spend the next thinning cycle.

## Remaining Inline Ownership

### 1. `process_chat(...)` is still too large and still owns live coordination logic

Current inline ownership still includes:

- action-ledger lifecycle setup/finalization
- session-state mutation choreography
- supervisor intent and rule bridging
- fulfillment, smalltalk, profile-learning, location-learning, declarative-store, followup, and developer-location application ordering
- post-reply pending-action/state writeback
- local bypass handling and fallback-safe override handling

Why this is still a drift risk:

- the shell is still deciding execution order across many different owners.
- any new “temporary” branch added here can bypass the intended shared seam and become the real runtime contract.

Best next extraction:

- move the remaining post-entry orchestration and session-mutation sequence into a dedicated HTTP orchestration/session-state owner.
- keep `process_chat(...)` focused on request/session binding, injected dependencies, and final emission.

### 2. `_generate_chat_reply(...)` still owns too much pre-LLM and grounded decision flow

Current inline ownership still includes:

- deterministic truth and hard-answer fallback layering
- planner action handling
- command/keyword/tool execution branching
- session-level web-preference override handling
- direct deterministic reply ladder for session recap, assistant name, developer identity, name origin, PEIMS attendance, developer profile, clarification, location, deep-search followup, grounded factual lookup, color/animal/profile replies
- low-confidence gating, fallback context shaping, and claim-gate adjustment before/after LLM fallback

Why this is still a drift risk:

- this function is still partly a reply engine rather than just a caller of one.
- deterministic owners can still reappear here even though `services/nova_reply_sequence.py` and related seams already exist.

Best next extraction:

- collapse the remaining deterministic/grounded/fallback ordering into one shared reply-runtime contract.
- keep `_generate_chat_reply(...)` only as a thin HTTP adapter or remove it entirely in favor of the shared owner.

### 3. `_control_action(...)` is still a giant live dispatch ladder

Current inline ownership still includes:

- large action-to-handler mapping for patch, pulse, update-now, runtime artifacts, runtime control, test sessions, queue investigation, backend commands, operator prompt, policy mutations, search-provider control, chat-user admin, inspect/policy audit/export actions
- per-action audit-event emission embedded in the ladder

Why this is still a drift risk:

- the control plane is service-shaped, but the live registry is still largely assembled inline here.
- adding or restoring one action locally can fork the operator surface from its intended shared dispatcher.

Best next extraction:

- move the action registry and uniform audit wrapping into a dedicated control-action dispatcher service.
- keep `nova_http.py` responsible only for request parsing, auth, and response emission.

### 4. `_control_status_payload(...)` is still a large integration assembler

Current inline ownership still includes:

- policy/provider inspection
- searx probing
- runtime status aggregation
- subconscious/generated queue/operator macro/backend command gathering
- memory/tool/ledger summaries
- patch/readiness/pulse/update-now/runtime-failure payload stitching
- metrics append and self-check projection

Why this is still a drift risk:

- the control plane already has real services, but this payload is still assembled as one large shell-side composition block.
- a restored field or new status source can quietly land here instead of in the control-status owner.

Best next extraction:

- move top-level payload composition into a single control-status assembler service.
- keep shell code responsible only for invoking the assembler and caching its result.

### 5. `_runtime_restart_analytics_payload(...)` is still standalone analytics logic in the shell

Current inline ownership still includes:

- boot-history parsing
- stability/flap calculations
- recent-window counts and summaries

Why this is still a drift risk:

- the runtime status plane already exists as a service surface, but restart analytics remains shell-authored.

Best next extraction:

- move restart-flap analysis into `services/runtime_status.py` or a dedicated runtime analytics owner.

### 6. `do_POST(...)` is still more transport-local than `do_GET(...)`

Cross-checked state:

- GET now delegates through a shared route service.
- POST still visibly owns path allowlisting, body parsing, and branch routing at the shell boundary.

Why this matters:

- GET/POST asymmetry is a classic place for transport drift.
- if POST remains more inline than GET, operator/control/chat changes can regress in only one direction.

Best next extraction:

- finish the POST-side route/dispatch symmetry through the existing POST services.

## Priority Order Inside `nova_http.py`

1. `_generate_chat_reply(...)`
2. `process_chat(...)`
3. `_control_action(...)`
4. `_control_status_payload(...)`
5. `do_POST(...)`
6. `_runtime_restart_analytics_payload(...)`

## Keep / Realign / Leave Alone

Keep:

- `nova_http.py` as the HTTP transport and control shell
- active session binding, auth, request parsing, response emission, and final cache invalidation

Realign:

- reply ordering
- post-entry orchestration
- control-action registry dispatch
- control-status aggregation
- restart analytics
- POST route symmetry

Leave alone for now:

- GET route delegation
- runtime artifact wrappers
- process-state wrappers
- timeline wrappers

## Working Rule

If a new HTTP behavior needs to be added, first decide whether it belongs to:

- transport/session binding,
- shared reply/routing ownership,
- control-status assembly,
- or control-action dispatch.

If it belongs to any of the last three, it should not be authored directly in `nova_http.py`.