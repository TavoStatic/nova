# Repo Cleanup Matrix

Date: 2026-04-18

## Purpose

This file is a cleanup and alignment aid, not a runtime authority.

It classifies major repo surfaces into four categories:

- `authoritative`: active owner of real system state or behavior
- `derived`: reporting, routing, cache, or aggregation over authoritative owners
- `historical`: preserved context, checkpoint, or baseline material
- `scratch`: one-off helper, probe, or likely cleanup candidate pending confirmation

## Rules

When cleanup work begins, use this order:

1. Preserve `authoritative` files and runtime state.
2. Keep `derived` files aligned to their owners; do not let them compete as truth.
3. Relabel or archive `historical` files so they stop reading like current authority.
4. Review `scratch` files for deletion, relocation, or explicit labeling.

## Matrix

| Path | Category | Why | Cleanup Action |
|---|---|---|---|
| `nova_core.py` | authoritative | Owns core runtime behavior and writes core identity/heartbeat state. The first core alignment pass is now materially established: deterministic identity reply helpers and shell query-classifier helpers delegate to shared service owners, the truth-hierarchy shell routes through `services/nova_truth_hierarchy.py`, the reply-contract layer routes through `services/nova_reply_contracts.py`, the name-origin / identity-history outcome seam routes through `services/nova_identity_history.py`, retrieval followup execution routes through `services/nova_retrieval_followups.py`, session recap / last-question / fact-recall presentation routes through `services/nova_session_followups.py`, the open-fallback / open-probe seam routes through `services/nova_fallback_flow.py`, the developer-profile / profile-followup family routes through `services/nova_profile_followups.py`, the developer-profile support helper family routes through `services/nova_developer_profile.py`, the action-history presenter routes through `services/nova_action_ledger_helpers.py`, the action-ledger lifecycle wrappers route through `services/nova_action_ledger.py`, the reflection-health helper and orchestration family routes through `services/nova_reflection_health.py`, the routing-support decision/bypass/followup helper family routes through `services/nova_routing_support.py`, the conversation-followup helper family routes through `services/nova_conversation_followups.py`, the conversation-followup dispatcher wrapper now routes through `services/nova_followup_dispatch.py`, the identity-preference helper family routes through `services/nova_identity_preferences.py`, the general turn-helper family routes through `services/nova_turn_helpers.py`, the active keyword/tool shortcut seam routes through `services/nova_keyword_tools.py`, the location/weather helper family routes through `services/nova_location_weather.py`, the registered supervisor-rule execution wrapper and the supervisor-intent application block route through `services/nova_supervisor_flow.py`, the broader memory-learning family routes through `services/nova_memory_learning.py` and `services/nova_memory_events.py`, the knowledge-pack search and local topic digest helpers route through `services/nova_knowledge_packs.py`, the search-endpoint probe now routes through `services/nova_search_endpoint.py`, the web-search, web-research, and legacy search-save wrappers now route through `services/nova_web_tools.py`, the pulse/status cluster now routes through `services/nova_pulse.py`, the legacy CLI deterministic turn-outcome cluster routes through `services/nova_turn_outcomes.py` plus `services/nova_cli_delivery.py`, the active CLI loop's sequence reply normalization and sequence-result application block route through `services/nova_cli_sequence.py`, the long deterministic-content block plus fallback-preparation / low-confidence gating and final LLM fallback execution inside `services/nova_reply_sequence.py` route through `services/nova_reply_deterministic.py` and `services/nova_fallback_flow.py`, the planned-tool dispatch wrapper routes through `services/nova_tool_dispatch.py`, the command-handler entrypoint delegates to `services/nova_command_handlers.py`, the CLI loop entrypoint delegates to `services/nova_cli_loop.py`, the patch preview/apply wrappers now route through service-backed preview/apply delegate helpers tied to `services/nova_patching.py`, the `ollama_chat()` shell now routes through `services/nova_ollama_chat.py`, and the `hard_answer()` shell now routes through a thin `truth_hard_answer` delegate helper. The April 20 drift-repair shell reduction brought the saved file from `12,744` lines down to `7,771`, below the `HEAD` baseline of `11,398`, with the legacy seam-lock set now clean. The file is still a gravity well, but the first shell-ownership pass is no longer the main uncertainty. | Keep; shift next work toward broader shell reduction and behavior-level stabilization rather than re-fighting the same ownership seams. |
| `nova_guard.py` | authoritative | Owns supervision, restart behavior, and liveness judgment. | Keep; treat as liveness authority. |
| `nova_http.py` | authoritative | Live transport/control shell still serving real runtime and control paths. The HTTP alignment pass is now much further along: control-status separates source gathering from payload assembly, control-action separates dispatch wiring from the `_control_action()` entrypoint, auth/session access uses explicit control/chat/session-owner context helpers, runtime status/control uses explicit runtime contexts, runtime artifacts/telemetry use explicit metrics/timeline/artifact and runtime-telemetry action contexts, patch/update/control-policy helpers use shared patch/policy contexts, test-session and operator control paths use explicit service-wiring contexts, and summary sources route through a shared summary-source context instead of scattered direct reads. The file remains large, but the remaining risk is now breadth more than invisible wiring drift. | Keep; preserve public contract and use clearer domain seams if more extraction follows. |
| `work_tree.py` | authoritative | Owns Work Tree persistence, schema, branches, tasks, and visual tree data. It now retries transient SQLite write failures, avoids persisting refresh-style reads unnecessarily, reloads persisted state for visual tree rendering, recognizes `test_...` review tasks as `find` work instead of stale fake `read` file paths, and recognizes metadata/symbol-reference inspection as `find` work so stale manual probe branches stop hard-failing and blocking the rest of a live tree. | Keep; treat as Work Tree spine. |
| `autonomy_maintenance.py` | authoritative | Owns maintenance-cycle behavior and persisted maintenance state. It now also translates subconscious `training_priorities` into normalized `subconscious_candidate` Work Tree signals, records the resulting ingestion summary in maintenance state, uses `services/subconscious_work_tree_triage.py` as the owner-aware review gate, uses `services/subconscious_review_authority.py` as the contract consumer before promotion into Work Tree, passes a compact live runtime snapshot into the review context so low-priority subconscious promotions can be deferred under active runtime pressure, can refresh an already staged subconscious branch instead of only skipping it when repeated pressure matches live Work Tree work, and now runs a broader Work Tree autorun lane (`10` execution-budget steps; `web_fetch`, `web_search`, `web_research`, `weather_current_location`, `weather_location`, `location_coords`, `update_now`, `patch_rollback` added) while still keeping `patch_apply` outside the autorun set. The cycle no longer lets non-progress states like `awaiting_operator` or `tool_failed` consume the same execution budget as real completed branch work, and the generated queue path is back to running real generated sessions after the reflection/action-ledger delegate drift in `nova_core.py` was repaired. It now batches generated queue execution up to `3` sessions per cycle and records `attempted_count` / `completed_count`, which has already pushed the live generated queue down into single digits. | Keep; treat as maintenance authority and first subconscious -> Work Tree bridge runner. |
| `http_session_store.py` | authoritative | Owns persisted HTTP session storage format and writes. | Keep; treat as session authority. |
| `memory.py` | authoritative | Owns persistent memory DB access. | Keep; treat as memory authority. |
| `runtime/core_state.json` | authoritative runtime state | Core identity/state artifact used by guard and status services. | Preserve; do not clean or rewrite casually. |
| `runtime/core.heartbeat` | authoritative runtime state | Core heartbeat artifact used for liveness. | Preserve; do not clean or rewrite casually. |
| `runtime/http_chat_sessions.json` | authoritative runtime state | Persisted HTTP session transcript store. | Preserve; treat as production-like state. |
| `runtime/autonomy_maintenance_state.json` | authoritative runtime state | Live maintenance worker and queue-cycle state. | Preserve; do not reset during cleanup. |
| `nova_memory.sqlite` | authoritative runtime state | Persistent memory substrate. | Preserve; do not treat as junk. |
| `services/work_tree_seeding.py` | derived | Seeds and reuses Work Trees on top of `work_tree.py`. | Keep; note tight coupling for future refactor. |
| `services/work_tree_signal_ingestion.py` | derived | Converts runtime/control pressure into Work Tree branches. It now also receives normalized subconscious candidate signals from `autonomy_maintenance.py`, enriches branch evidence with owner/seam/test/rationale summaries, and preserves family-specific review focus emitted by triage in branch notes. | Keep; align to `work_tree.py` as owner and strengthen the triage boundary above it. |
| `services/subconscious_work_tree_triage.py` | derived policy owner | Classifies subconscious priorities into fulfillment/supervisor/route-review lanes, assigns an explicit `review_contract`, builds signal-specific `review_context`, and applies the first review gate before Work Tree promotion. When family/variation metadata is available, the review context can now be sourced from actual subconscious scenarios instead of only generic signal defaults, including matches recovered by `suggested_test_name` as well as by signal. Explicit supervisor-owned fallthrough seams now classify by seam ownership first instead of being flattened into the generic route-comparison lane, triage can now carry a compact maintenance/runtime pressure snapshot alongside the scenario context, and it now emits family-aware next-task / review-focus guidance so future Work Tree branches are more specific than the earlier generic review text. | Keep; use as the current policy owner until fulfillment/supervisor can become the true execution gate. |
| `services/subconscious_review_authority.py` | derived authority layer | Consumes subconscious `review_contract` decisions and returns the promotion verdict before Work Tree ingestion. It now supports a mixed live-organ / route-backed review path for mapped subconscious pressure signals: live fulfillment viability can approve fulfillment-owned review directly, live supervisor-rule evaluation can approve supervisor-owned review directly, live supervisor reflection probes can supply richer red/yellow review signals, and the service falls back to Nova's real route-probe path when the live supervisor organ does not claim the turn. Signal-specific review context can come from actual subconscious family/variation metadata when available, and the service is runtime-aware enough to defer low-priority promotion when maintenance reports active pressure such as failed regression, failed generated queue work, and waiting Work Tree backlog. It is also now backlog-aware enough to suppress low-priority re-promotion when the same subconscious candidate is already staged in Work Tree from a prior maintenance cycle, using real live branch/task detail rather than only the previous maintenance summary. | Keep; expand from mixed live-organ / route-backed review toward fuller fulfillment/supervisor-backed review when that boundary is ready. |
| `kidney.py` | authoritative hygiene engine | Owns runtime hygiene, archival, and pruning policy. It no longer lets dry-run status overwrite the last real enforce snapshot, now retries archive/delete operations on Windows access-denied races, and can mark stale generated definitions as `retired_locked` when the file handle cannot be released. | Keep; use as the hygiene authority and align generated-queue filtering to its retirement truth. |
| `services/test_session_control.py` | derived queue/report owner | Owns generated-queue summaries, definition inventory, and report-driven queue ranking. It now respects kidney retirement records by fingerprint so stale locked generated definitions stop polluting the live queue even if Windows refuses to delete the original file. | Keep; align queue truth to runtime hygiene state. |
| `services/control_status.py` | derived | Wide aggregation payload; reports many authoritative surfaces. The flattening is now split into explicit maintenance/memory/tool/ledger/pulse sections, but it is still a broad mirror layer. | Keep; prevent it from becoming competing truth. |
| `services/runtime_status.py` | derived | Interprets runtime artifacts into status labels. | Keep; align to guard/core contract. |
| `services/runtime_artifacts.py` | derived | Inventories and summarizes runtime files. | Keep; treat as reporting layer only. |
| `services/runtime_analytics.py` | derived | Computes restart analytics from recorded history. | Keep; derived only. |
| `services/control_actions.py` | derived | Small control helpers, no deep ownership. | Keep; low cleanup priority. |
| `services/control_status_cache.py` | derived | Cache wrapper around control status payload. | Keep; low cleanup priority. |
| `services/nova_http_get_routes.py` | derived | GET routing surface only; exposes control APIs. | Keep; transport only. |
| `services/runtime_control.py` | derived | Lifecycle orchestration around guard/core/http flows. | Keep; treat as lifecycle helper, not source of state truth. |
| `services/schedule_registry.py` | derived | Metadata registry for scheduled jobs, not execution authority. | Keep; label mentally as schedule metadata. |
| `services/nova_patching.py` | authoritative service owner | Shared owner for patch governance, preview state, apply engine, and rollback engine; `nova_core.py` now wraps this surface instead of owning duplicate logic. | Keep; treat as the patch engine owner. |
| `services/patch_control.py` | derived control adapter | Control-side patch readiness and preview actions layered on top of `services/nova_patching.py` and runtime wrappers. | Keep; align to service owner, not `nova_core.py` internals. |
| `docs/CURRENT_TRUTH_2026-04-18.md` | historical index | Current repo-facing trust-order index. Useful, but not runtime authority itself. | Keep visible; use as repo truth index. |
| `This_is_nova` | historical recovery surface | Active recovery/history journal with durable project continuity value. | Keep prominent; do not archive casually. |
| `docs/ALIGNMENT_AUDIT_2026-04-18.md` | historical | Alignment audit context for gravity wells and trust order. | Keep; reference during cleanup. |
| `docs/NOVA_HTTP_ALIGNMENT_AUDIT_2026-04-18.md` | historical | Focused HTTP audit context. | Keep; reference during cleanup. |
| `docs/NOVA_CORE_ALIGNMENT_AUDIT_2026-04-18.md` | historical | Focused core audit context. | Keep; reference during cleanup. |
| `docs/STATUS.md` | historical | Explicitly marked as mostly historical checkpoint material. | Keep relabeled as historical. |
| `PROJECT_STATUS.md` | historical | Older project status surface that now competes unless clearly demoted. | Keep relabeled or move deeper into archive later. |
| `docs/archive/audits/2026-04-17/baseline_summary.md` | historical | Baseline artifact, not current authority. | Keep archived. |
| `docs/archive/audits/2026-04-17/runtime_state_report.md` | historical | Audit/report artifact. | Keep archived. |
| `docs/archive/audits/2026-04-17/live_behavior_report.md` | historical | Audit/report artifact. | Keep archived. |
| `docs/archive/audits/2026-04-17/test_baseline_report.md` | historical | Audit/report artifact. | Keep archived. |
| `docs/archive/audits/2026-04-17/work_tree_baseline_report.md` | historical | Audit/report artifact. | Keep archived. |
| `docs/archive/audits/2026-04-17/hygiene_report.md` | historical | Audit/report artifact. | Keep archived. |
| `docs/archive/` | historical | Explicit archive zone. | Keep archived. |
| `tests/legacy/` | historical | Explicitly non-authoritative for current behavior unless cross-checked. | Keep demoted; do not let drive design. |
| `scripts/diagnostics/list_work_tree_tables.py` | scratch utility | One-off DB inspection helper for Work Tree tables. | Keep under diagnostics; not a live owner. |
| `scripts/diagnostics/inspect_core_fail.py` | scratch utility | Local inspection helper around runtime failure artifacts. | Keep under diagnostics; not a live owner. |
| `scripts/repo_hygiene_check.py` | scratch | Hygiene aid, not system authority. | Keep as utility; do not confuse with truth surface. |
| `docs/archive/notes/2026-04-18/README.txt` | historical | Archived bundle note, not current documentation authority. | Keep archived. |
| `docs/archive/notes/2026-04-18/README_PATCH.txt` | historical | Archived patch-note text, not primary patch authority. | Keep archived. |
| `docs/archive/notes/2026-04-18/patch_handle_cmds.txt` | historical | Archived code-note text, not canonical config. | Keep archived. |
| `docs/archive/notes/2026-04-18/PHASE_5_ADAPTIVE_TRACKING_COMPLETE.md` | historical | Archived milestone artifact, not current runtime authority. | Keep archived. |
| `LAST_SESSION.json` | historical recovery helper | Old March handoff helper still referenced by older status surfaces. | Keep for now; relabel mentally as non-canonical. |
| `RESUME_HERE.txt` | historical recovery helper | Old March handoff helper still referenced by older status surfaces. | Keep for now; relabel mentally as non-canonical. |

## Highest-Risk Cleanup Areas

These need care because cleanup can accidentally change the live system story:

1. Patch execution still enters through `nova_core.py` runtime wrappers while authority now lives in `services/nova_patching.py`; keep future cleanup aligned to that owner.
2. `services/work_tree_signal_ingestion.py` and the main read-side scans in `services/work_tree_seeding.py` now use public `work_tree.py` helpers; remaining Work Tree drift is narrower and mostly on broader adapter complexity rather than raw private-global reach.
3. `services/control_status.py` is narrower than it was, and the first-pass `nova_http.py` alignment is now complete enough that the remaining HTTP risk is breadth and physical file size more than hidden wiring knots.
4. `nova_core.py` still has major breadth, but the first-pass fallback/open-probe, developer-profile/profile-followup, supervisor-flow, action-ledger/reflection-health, routing-support, memory-learning, knowledge-pack, web-search, search-endpoint, pulse/status, conversation-followup-dispatch, and legacy CLI turn-outcome seams now belong with `services/nova_fallback_flow.py`, `services/nova_profile_followups.py`, `services/nova_supervisor_flow.py`, `services/nova_action_ledger.py`, `services/nova_reflection_health.py`, `services/nova_routing_support.py`, `services/nova_memory_learning.py`, `services/nova_memory_events.py`, `services/nova_knowledge_packs.py`, `services/nova_web_tools.py`, `services/nova_search_endpoint.py`, `services/nova_pulse.py`, `services/nova_followup_dispatch.py`, `services/nova_turn_outcomes.py`, and `services/nova_cli_delivery.py`; remaining core work is broader shell reduction, not these specific ownership splits.
5. Root-level markdown and report artifacts that still look current at a glance.

## Safe Early Cleanup Moves

These should be safe once explicitly approved:

1. Move one-off report artifacts into a dated archive folder.
2. Move scratch helper probes into a `scripts/diagnostics/` area or remove root-level pointers once stable.
3. Keep only one obvious repo-facing truth index at the top of the docs stack.
4. Add explicit historical banners to any remaining root-level status files that still read like current authority.

## Not Safe To Treat As Junk

- `runtime/` as a whole
- `logs/` as a whole
- `updates/` as a whole
- `nova_memory.sqlite`
- Work Tree DB and related runtime state
- persisted HTTP sessions
- maintenance state

These directories contain real operating state mixed with artifacts. Cleanup here must be selective, not broad.
