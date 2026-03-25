# Nova Status

Date: 2026-03-25

## Stabilization Checkpoint (March 25, 2026)

This checkpoint is the current canonical baseline after the Phase 1/2 acceleration slice.

Verified now:

- full regression is green on the latest run: `672` tests, `OK`
- representative runtime path smoke remains green:
	- `tests.test_run_test_session`
	- `tests.test_http_identity_chat`
	- `52` tests, `OK`
- maintenance loop is still healthy and applying validated micro-patches
- safety envelope is active in `observe` mode and writing promotion audit rows
- kidney system is active in `observe` mode and reporting cleanup candidates without destructive actions

Current runtime posture:

- keep both `safety_envelope.mode` and `kidney.mode` in `observe` for one more full cycle
- keep feature churn paused during the stabilization window
- continue logging audited results before switching any governance subsystem to `enforce`

New canonical docs for this slice:

- `docs/PHASE2_SAFETY_ENVELOPE.md`
- `docs/KIDNEY_SYSTEM.md`
- `docs/PHASE2_SELF_DIRECTED_IMPROVEMENT.md`
- `docs/PACKAGE_PRODUCT_ROADMAP.md`

Latest local audit artifact:

- `runtime/stability_audit_20260325_1419.md`

## Active Runtime Loop

Nova now has a first active-use loop built from existing subconscious and operator machinery rather than a new architecture layer.

Current loop shape:

- generated subconscious test definitions act as the standing work queue
- latest report summaries act as opportunity detection for open work
- existing priority metadata chooses the next candidate
- the existing session runner executes the selected item
- the control room now reports queue state and can run the next open item directly

This keeps the loop grounded in artifacts Nova already produces:

- subconscious report generation
- generated regression definitions
- priority sorting
- CLI/HTTP parity execution
- operator-visible report summaries

## Product Direction

Nova is becoming the runtime core of NYO System: a supervised local runtime for routing, memory, research, tool execution, operator-console operations, and governed self-change.

The current evaluation is:

- not primarily a chatbot product
- not a bundled domain expert application
- closer to an operator-run execution system with chat, CLI, and admin surfaces on top

The important boundary for this phase is:

- generic public runtime by default
- domain specialization loaded explicitly through packs, policy, tools, or future product layers
- no hidden dependency on bundled vertical-repo knowledge

## Base Package Readiness

Base-package readiness is now tracked explicitly in `docs/BASE_PACKAGE_READINESS.md`.

Current read:

- close to a base runtime package
- moderately close to a base model package
- not yet a clean drop-in distributable package

Main remaining gaps:

- packaging-boundary maintenance and enforcement as the repo evolves
- bootstrap hardening and reduction of workstation-specific assumptions
- cleaner runtime dependency isolation for broad validation
- continued hardening of the consolidated operator handoff story

Current decision:

- dependency-isolation refactor is intentionally deferred until more of Nova's core behavior is finished
- while deferred, avoid expanding direct live-runtime/model coupling beyond the current known hotspots
- treat dependency isolation as a later hardening phase, not current feature work

The packaging boundary now has a canonical matrix in `docs/PACKAGING_MATRIX.md`.

The fresh-machine bootstrap path is now documented in `docs/BOOTSTRAP.md`.

The single operator handoff flow now lives in `docs/HANDOFF.md`.

## Current Verified State (March 23, 2026)

- Focused operator-surface / subconscious / fulfillment validation is green: `c:/Nova/.venv/Scripts/python.exe -m unittest tests.test_subconscious_runner tests.test_http_session_manager tests.test_fit_evaluator tests.test_choice_presenter`
- Latest focused operator-surface result: `60` tests, `OK`

- Full discovered suite is green: `c:/Nova/.venv/Scripts/python.exe -m unittest discover -s tests -p "test_*.py"`
- Latest full-suite result: `585` tests, `OK`
- Latest focused runtime recovery result: `22` tests, `OK`
- Latest focused domain-detachment results:
	- `293` tests, `OK` for `tests.test_http_identity_chat tests.test_nova_http tests.test_core_identity_learning`
	- `21` tests, `OK` for `tests.test_action_planner tests.test_task_engine`
- Recent root-cause fixes now locked by regression:
	- bare clarification probes such as `what?` are again classified as clarification turns instead of falling through as `other`
	- heartbeat-only runtime status preserves persisted core identity when the stored pid is dead and an unrelated live `nova_core.py` process exists
	- runtime recovery coverage now explicitly proves heartbeat-only fallback ignores unrelated live core processes
- Public-repo domain posture is now explicit:
	- bundled PEIMS repo knowledge has been detached from shipped runtime behavior
	- local domain grounding now searches only the active knowledge pack instead of arbitrary repo knowledge files
	- PEIMS-style domain help now resolves through sourced web research first, optional active knowledge packs second, and a truthful detached fallback otherwise
- Targeted answer-path closure slice remains green on top of those repairs
- Verified command slices:
	- `c:/Nova/.venv/Scripts/python.exe -m unittest tests.test_core_identity_learning.TestCoreIdentityLearning.test_supervisor_reflective_retry_rule_handles_developer_location tests.test_core_identity_learning.TestCoreIdentityLearning.test_supervisor_profile_certainty_rule_handles_identity_profile_followup tests.test_core_identity_learning.TestCoreIdentityLearning.test_profile_state_followup_handles_are_you_sure_thats_all tests.test_core_identity_learning.TestCoreIdentityLearning.test_cli_open_probe_prompt_records_reply_contract_and_avoids_bypass_warning tests.test_core_identity_learning.TestCoreIdentityLearning.test_handle_supervisor_bypass_raises_in_dev_mode`
	- `c:/Nova/.venv/Scripts/python.exe -m unittest tests.test_http_identity_chat.TestHttpIdentityChat.test_clarification_prompt_does_not_trigger_web_lookup tests.test_http_identity_chat.TestHttpIdentityChat.test_http_writes_action_ledger_record tests.test_http_identity_chat.TestHttpIdentityChat.test_http_reflective_followup_uses_learned_developer_location_relation tests.test_nova_http.TestNovaHttpProfile.test_developer_profile_certainty_challenge_stays_on_profile_thread tests.test_nova_http.TestNovaHttpProfile.test_developer_how_built_has_non_hallucinated_limit`
	- `c:/Nova/.venv/Scripts/python.exe -m unittest tests.test_core_identity_learning.TestCoreIdentityLearning.test_supervisor_location_recall_rule_rejects_clarification_move tests.test_core_identity_learning.TestCoreIdentityLearning.test_supervisor_identity_history_rule_rejects_clarification_move tests.test_core_identity_learning.TestCoreIdentityLearning.test_cli_name_origin_turn_uses_supervisor_contract_without_bypass_warning tests.test_core_identity_learning.TestCoreIdentityLearning.test_cli_identity_history_prompt_uses_supervisor_contract_without_bypass_warning tests.test_core_identity_learning.TestCoreIdentityLearning.test_cli_creator_followup_uses_supervisor_contract_without_bypass_warning tests.test_nova_http.TestNovaHttpProfile.test_http_name_origin_turn_uses_supervisor_contract_without_bypass_warning tests.test_nova_http.TestNovaHttpProfile.test_http_creator_followup_uses_supervisor_contract_without_bypass_warning tests.test_http_identity_chat.TestHttpIdentityChat.test_http_llm_fallback_appends_learning_invitation`
	- `c:/Nova/.venv/Scripts/python.exe -m unittest tests.test_http_identity_chat tests.test_nova_http tests.test_core_identity_learning`
	- `c:/Nova/.venv/Scripts/python.exe -m unittest tests.test_action_planner tests.test_task_engine`
- Broad rerun of the three answer-path suites no longer showed the prior assertion failures, but the run was interrupted later by a live `ollama_chat(...)` dependency during an unrelated test; do not treat that interruption as an answer-path regression
- Supervisor contract: documented in `docs/SUPERVISOR_CONTRACT.md`
- Hard quality bar: documented in `docs/QUALITY_BAR.md`
- Move-first stress harness: `tests/test_move_first_stress_harness.py`
- Architectural seams landed:
	- followup move classification now lives in `followup_move_classifier.py` with direct seam coverage in `tests/test_followup_move_classifier.py`
	- active-task context and binding rules now live in `active_task_constraints.py` with direct seam coverage in `tests/test_active_task_constraints.py`
- Enforcement: supervisor-bypass warnings now carry categorized allowlist metadata, dev mode raises on unallowlisted bypasses via `NOVA_DEV_MODE=1`, each turn records a structured `routing_decision`, and the closed answer-path slice now prefers supervisor-owned reply contracts over generic open fallback
- Migrated families on the outcome + reply-contract layer:
	- `set_location`
	- `apply_correction`
	- `store_fact`
	- `weather_lookup` clarify + execution paths
	- `web_research_family` for explicit online/search and deep-search prompts
	- `name_origin` identity/history followups for saved-story recall
	- `retrieval_followup` for result selection, continued-results followups, and retrieval meta replies
- Parity: CLI and HTTP are aligned on the migrated paths and both persist `reply_contract` / `reply_outcome`
- Health tooling: `scripts/health_check.py` provides a one-command suite baseline check

## Current Architecture

Nova now has:

- one planner-owned routing spine for command/tool selection
- a documented supervisor contract for deterministic ownership
- shared core execution for supervisor-selected actions
- a reply contract / outcome layer for key deterministic acknowledgment families
- ledger and reflection tracking for reply contracts on migrated paths

## Recently Completed

- migrated `set_location` to semantic outcome + renderer + ledger/reflection contracts
- migrated `apply_correction` to semantic outcome + renderer + ledger/reflection contracts
- migrated `store_fact` to semantic outcome + renderer + ledger/reflection contracts
- migrated the full `weather_lookup` family, including execution acknowledgments, to the shared contract layer
- repaired the research handler shim so deep-search and recap flows no longer fail building the research tool handler map
- migrated the `name_origin` identity/history recall family into supervisor-owned deterministic replies
- migrated `retrieval_followup` into supervisor-owned continuation handling with reply contracts for result selection, continued-results followups, and retrieval meta replies
- added per-turn `routing_decision` metadata plus categorized allowlist-backed bypass enforcement for remaining fallback families
- migrated the `identity_history_family` followup slice so creator-thread `what else?` and explicit build-history prompts are now supervisor-owned handle paths with reply contracts
- migrated the `open_probe_family` slice so clarification prompts and safe open-ended probes now resolve through supervisor-owned handle execution with reply contracts
- migrated `last_question_recall` so `what was my last question?` now resolves through supervisor-owned handle execution with reply contracts
- migrated `rules_list` so `do you have any rules` now resolves through supervisor-owned handle execution with reply contracts
- reduced false supervisor-bypass warning noise by delaying bypass warnings until after deterministic handle/followup/store paths have had a chance to claim the turn
- closed the open answer-path cleanup slice so reflective retry, profile certainty, identity history, and open-probe families are explicitly supervisor-owned handle paths
- removed the broad implicit blessing for generic open fallback candidates; unmatched open turns now count as real bypasses unless they are explicitly categorized
- forced CLI and HTTP unmatched open turns through the existing `open_probe.safe_fallback` contract instead of continuing into generic planner / LLM fallback
- tightened weak clarifier handling so bare `what?` is no longer over-owned as an open-probe clarification
- kept CLI and HTTP aligned on migrated deterministic behavior
- added an initial move-first stress harness covering bare values, corrections, declarations, selections, continuations, meta/challenge turns, active-task ambiguity, retrieval followups, weather followups, and conversational non-tool statements
- extracted the first architectural seam by moving followup move classification and its supporting heuristics into `followup_move_classifier.py`, while keeping supervisor-compatible entry points stable
- added a direct seam test pack in `tests/test_followup_move_classifier.py` so classifier behavior stays locked independently of supervisor rule wiring
- extracted the next architectural seam by moving active-task context resolution and pending-thread bindings into `active_task_constraints.py`, while keeping supervisor rule entry points stable
- added a direct seam test pack in `tests/test_active_task_constraints.py` so active-task bindings stay locked independently of supervisor rule ordering
- kept sqlite cleanup stable and avoided reintroducing the prior connection leak / resource-warning path
- fixed teach-proposal manifests so generated proposal zips carry forward `patch_revision` metadata and preview as eligible patches
- hardened live patch apply with a behavioral validation gate plus rollback on behavioral regression
- exposed patch-readiness telemetry in the control room so operators can see revision, preview queue state, and validated-apply readiness
- detached bundled PEIMS knowledge from the public repo runtime
- removed direct runtime fallbacks that read `knowledge/peims/` content from shipped code paths
- constrained repo-local topic grounding to the active knowledge pack so domain content is operator-supplied rather than silently bundled
- updated HTTP and core identity tests to lock the new detached-domain contract
- deleted tracked `knowledge/peims/*.txt` content from the repo working set and ignored future local PEIMS drops via `.gitignore`
- turned subconscious hourly findings into generated review-first test-session definitions and surfaced the latest subconscious summary in the operator console
- improved fulfillment evaluation and choice presentation with weighted fit scoring, stronger option ordering, and concise plurality reasons
- added an operator command deck inside the control console so Nova can be driven from the operator surface without switching to the chat page
- added one-click generated-pack execution for subconscious-generated regression sessions from the operator console
- added a priority-targeted generated-pack mode so the operator can run the highest-value subconscious regressions first
- surfaced generated-session priority rationale directly in the operator dropdown so ranking choices are visible before execution
- added browser mic and speech-output controls to the operator command deck for hands-free operator prompting
- added a shared saved operator-macro catalog used by the control deck and the local `nova operator` CLI mode
- added an operator-session filter in the Sessions view so operator-driven threads can be isolated from ordinary chat traffic
- tagged operator timeline events by source and mode so manual, CLI, and macro-driven prompts are distinguishable in runtime history
- added placeholder-aware operator macros with backend rendering so the control deck and CLI share the same parameterized prompt path
- added a standing generated-session work queue derived from subconscious-generated definitions plus latest report status
- added control-room queue reporting and a one-click `Run Next Queue Item` action that selects the highest-priority non-green generated session and executes it through the existing runner
- added a one-click `Investigate Next Queue Item` action that turns the next open generated-session drift into an operator-session prompt through the existing macro/session flow
- updated `Run Next Queue Item` so the control room auto-selects the newest parity report after execution
- tightened generated-session parity reporting so route-summary drift now counts as a real CLI/HTTP drift signal instead of being silently ignored
- pinned `subconscious_fulfillment-fallthrough-family_clarified-second-turn.json` as a deterministic CLI/HTTP parity regression target
- burned down the full repeated-weak-pressure family by moving vague weak-pressure prompts and soft check-ins onto shared deterministic smalltalk/open-probe paths and aligning the CLI/HTTP route trace
- added a narrow `queue_status` capability so Nova can inspect the standing generated work queue from chat and report the next open regression item through the normal tool/ledger path
- fixed the root follow-up seam for planner-owned direct tools by projecting tool results into shared conversation state, so queue-status replies now support deterministic follow-up reasoning instead of falling through to raw LLM chat

## Validation

Latest focused queue/parity run:

- `c:/Nova/.venv/Scripts/python.exe -m unittest tests.test_run_test_session tests.test_http_identity_chat tests.test_http_session_manager`
- `96` tests, `OK`

Latest focused queue/operator/repeated-weak-pressure rerun:

- `c:/Nova/.venv/Scripts/python.exe -m unittest tests.test_http_session_manager tests.test_run_test_session tests.test_http_identity_chat tests.test_core_identity_learning tests.test_move_first_stress_harness`
- `306` tests, `OK`

Latest queue-capability validation:

- `c:/Nova/.venv/Scripts/python.exe -m unittest tests.test_action_planner tests.test_tool_registry tests.test_http_identity_chat tests.test_core_identity_learning`
- `281` tests, `OK`
- live chat experiment now shows `queue_status` in the capability registry and answers `what should you work on next` via `action_planner:run_tool -> tool_execution:ok`
- follow-up diagnostic now stays on structured queue state: `what should you work on next` -> `why is that the next item in the queue?` now resolves through `conversation_followup:used` with active subject `queue_status:generated_work_queue`

Checkpoint for next chat:

- the `queue_status` root follow-up seam fix is implemented and locked for both CLI and HTTP paths
- deterministic queue follow-ups for `why is that the next item`, `what seam is it failing on`, and `show me the report path` are implemented and validated
- focused lock-in validation passed under a local fake-audio import shim after direct targeted test entry hit import-time `sounddevice` / PortAudio initialization in `nova_core.py`
- current remaining engineering task: harden the import/test path so focused tests can run directly without the shim

Latest generated-pack priority sweep after parity hardening:

- `22` generated definitions executed through the existing runner
- fulfillment-fallthrough family is green, including the pinned clarified-second-turn canary
- remaining non-green generated sessions now surface as standing queue work instead of passive backlog only

Latest live queue execution check:

- standing queue selected `subconscious_repeated-weak-pressure-family_ambiguous-clarification.json` as the next open item
- execution completed through the existing session runner and wrote a fresh report artifact
- the item remained open because it still reports CLI/HTTP assistant drift, which is the intended queue behavior

Latest repeated-weak-pressure family rerun after the shared deterministic fix:

- `subconscious_repeated-weak-pressure-family_ambiguous-clarification.json`: green
- `subconscious_repeated-weak-pressure-family_casual-checkin.json`: green
- `subconscious_repeated-weak-pressure-family_plain-followup.json`: green
- `subconscious_repeated-weak-pressure-family_soft-smalltalk-then-ambiguity.json`: green

Latest verified full-suite run:

- date: `2026-03-23`
- tests: `585`
- result: `OK`
- runtime observed: about `127` seconds on the latest full discovery verification pass

Run manually:

```powershell
c:/Nova/.venv/Scripts/python.exe -m unittest discover -s tests -p "test_*.py"
```

Quick health check:

```powershell
c:/Nova/.venv/Scripts/python.exe scripts/health_check.py
```

## Remaining Debt

- `nova_core.py` is still the main structural risk because too many concerns remain centralized there
- broad suite completion still depends on isolating or mocking live `ollama_chat(...)` calls in tests that are not part of the closed answer-path assertion slice
- planner-owned command/tool paths and supervisor-owned deterministic paths are cleaner, but cleanup should continue removing dead or duplicated fallback branches that can no longer win under the contract-first model
- some planner comments, prompts, and regression fixtures may still use PEIMS-shaped example text even though bundled PEIMS product content has been detached

## Current Answer-Path Position

Closed answer-path expectations now are:

- one enforced answer contract for the targeted open/followup slice
- one safe fallback path via `open_probe.safe_fallback` for unmatched open turns
- the same fallback posture in CLI and HTTP for that slice
- clarification and identity-history followups should resolve through supervisor-owned handle rules rather than generic no-contract fallthrough

## Enforcement Target

- Target: keep shrinking uncategorized bypasses and dead legacy fallback branches without reintroducing generic open-fallback drift

## Next Recommended Work

1. prune answer-path branches that are now unreachable or redundant under the contract-first fallback model
2. isolate broad-suite tests from live `ollama_chat(...)` dependencies so answer-path reruns finish deterministically
3. keep shrinking the responsibility footprint of `nova_core.py`
4. use the existing subconscious simulator only as a contract-audit stress lens for the closed answer-path slice, not as a new behavior layer

## Documentation Rule

Project documentation is centralized under `C:\Nova\docs`.

- update `docs/STATUS.md` for project-state changes
- update `docs/TOOLS.md` and `docs/TOOLING_ROADMAP.md` for tool changes
- avoid adding new root-level project docs unless they are thin compatibility pointers

## Resume Guidance

Primary resume order:

1. `C:\Nova\RESUME_HERE.txt`
2. `C:\Nova\LAST_SESSION.json`
3. `C:\Nova\docs\STATUS.md`

Suggested resume prompt:

```text
continue from C:\Nova\docs\STATUS.md
```