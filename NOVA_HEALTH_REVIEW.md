# Nova Project — Health Review

Reviewer: second set of eyes
Date: 2026-05-20
Branch reviewed: `codex/push-prep` (HEAD `3500866 Update Nova documentation for current release truth`)

## Summary

The codebase is structurally sound — all 1,857 Python source files compile cleanly, and every unit-lane test module passes when run in isolation. The real risks are not in the code; they are in **a stale documentation/release picture and a release gate that let a package through while the full regression was red.** Nothing here is on fire, but the "release-candidate, ready-with-notes" story in `docs/STATUS.md` no longer matches what the artifacts on disk say.

## Critical findings

### 1. The latest full regression FAILED, but STATUS.md says it passed

`runtime/regression_status.json` (generated 2026-05-20 00:02:17) reports:

- `status: FAILED`, `returncode: 1`, `detail: "unit lane"`

`docs/STATUS.md` (dated 2026-05-18) still claims `regression status: OK` with unit 528 / behavior 561 / integration 84 all green. That snapshot is two days and one failed run stale. Anyone resuming from STATUS.md — which the doc explicitly tells you to read first — gets a false "all green" read.

Note: I re-ran every unit-lane module in a Linux sandbox and each passed individually. So the recorded failure is most likely **timing- or environment-specific** (the autonomy-maintenance tests run real cycles and are sensitive to timing; Ollama availability also varies). It should be reproduced and pinned down rather than assumed flaky.

### 2. A release package was built and "passed validation" after the regression failed

Timeline on 2026-05-20:

- 00:02 — full regression run → FAILED (unit lane)
- 00:11 — package `nyo-system-base-rc-2026.05.20-work-tree-rebuild` built + verified
- 00:25 — release validation ran → `ok: true`, no blocking issues

The release validator runs `nova test` (a ~49s smoke subset), not the full `scripts/run_regression.py all`. So the release validation gate **structurally cannot catch what the full regression caught.** A package can show "ready" while the canonical test suite is red. This is the single most important thing to fix: the release validation profile should either run the full regression or hard-gate on `regression_status.json` being `OK` and fresh.

### 3. Nova's own autonomy already flagged this

`runtime/operator_outbox.jsonl` contains repeated notices titled *"Nova needs a tool assignment: Resolve regression/test failures from maintenance cycle"* (05-19 00:05, 05-19 22:45, 05-20 00:05) and a work-tree item *"Release package is stale behind live source"* (`work_class: release_readiness_gap`, 4 tasks). The system detected both problems; the notices are now marked `stale` / `work_tree_pressure_cleared` without the underlying failures being resolved. Worth checking whether "pressure cleared" is masking unresolved work.

## Documentation / release inconsistencies

The working tree is mid-refactor: **178 uncommitted changes (11 added, 98 modified, 69 deleted; +3,302 / −27,244 lines).** The docs were committed before this refactor and no longer describe the current tree:

- `docs/STATUS.md` lists `routing/context_router.py` and `services/nova_turn_heuristics.py` as source-backed evidence files. **Both are deleted in the working tree** (along with `routing/command_router.py`, `heuristics.py`, `legacy_routes.py`, `turn_parser.py`).
- STATUS.md says promotion judgment is `already_promoted`. The release ledger shows the latest package (`rc-2026.05.20`) has only `build` + `verify` events — **no promotion event.** The last actually-promoted package was `rc-2026.05.19.12`. STATUS.md/HANDOFF.md still reference `2026.05.18.23`, which isn't the current artifact at all.
- Version labels are inconsistent across docs and the ledger (`2026.05.18.23`, `2026.05.19.12`, `2026.05.20`), which makes "which build are we talking about" genuinely ambiguous.

None of this is a code defect — it's a truth-tracking gap. Given STATUS.md is the designated "resume here" doc, it should be regenerated from the live artifacts (`regression_status.json`, the release ledger, the current file tree) rather than hand-maintained, or at minimum refreshed before the next handoff.

## Runtime stability observations

- **Guard restart loop:** `logs/guard.log` shows the core process repeatedly failing to stay up between 05-15 and 05-19 — `heartbeat_stale`, `boot_timeout_no_state`, `pid_missing` — with backoff escalating 2s→4s→8s→16s→30s. The guard recovers each time, but the frequency of unplanned restarts is worth investigating; `guard_boot_history.json` confirms multiple `restart_cause_reason: pid_missing` supervised restarts.
- **HTTP server leaks tracebacks on client disconnect:** `logs/nova_http.err.log` has 3 unhandled `ConnectionAbortedError [WinError 10053]` tracebacks in `services/nova_http_responses.py:27` (`handler.wfile.write(body)`). A client closing the connection mid-response is normal browser behavior; it should be caught and logged quietly, not surfaced as an exception trace.
- **Quality probe:** `runtime/health.log` flagged a YELLOW `thin_answer_frequency` probe once on 05-19 ("thin answers 3x in last 10 turns"). Isolated, but the probe itself suggested "consider hardening rule" — track if it recurs.

## What looks healthy

- All source compiles; no `TODO`/`FIXME`/`XXX`/`HACK` markers in `services/`, `routing/`, `pipelines/`, `tools/`.
- Every unit-lane test module passes in isolation (398+ tests across the modules I ran).
- Package verification is thorough — manifest checks, forbidden-path checks, and forbidden-pattern checks all pass.
- The architecture is well-separated (CLI/HTTP front doors, planner spine, work-tree pressure, OS capability contracts, operator outbox).
- The non-blocking release notes are honest about real gaps (no fresh-machine/VM validation; interactive `nova run` not exercised).

## Recommended next steps, in priority order

1. **Reproduce and fix the 2026-05-20 unit-lane failure**, or confirm it is flaky and stabilize the offending test. Don't ship until `regression_status.json` is `OK` and dated after the fix.
2. **Close the release-gate hole**: make release validation fail if the full regression is not `OK` and recent (e.g. read `regression_status.json` as a hard precondition), so a red suite can never produce a "ready" package.
3. **Regenerate `docs/STATUS.md`** from live artifacts — fix the deleted-file references, the promotion claim, and the version labels. Consider auto-generating it.
4. **Commit or shelve the 178-file refactor.** A working tree this far from HEAD makes every doc and every artifact ambiguous; the docs can't be trusted until the tree and HEAD agree.
5. **Harden the HTTP write path** against `ConnectionAbortedError` in `services/nova_http_responses.py`.
6. **Investigate the guard restart frequency** — the core shouldn't be dropping its heartbeat / pid this often.

## Sources

- `docs/STATUS.md`, `docs/HANDOFF.md`, `docs/BASE_PACKAGE_READINESS.md`
- `runtime/regression_status.json`
- `runtime/validation/release/latest_release_validation.json`
- `runtime/exports/release_packages/release_ledger.jsonl`
- `runtime/operator_outbox.jsonl`, `runtime/guard_boot_history.json`
- `logs/guard.log`, `logs/nova_http.err.log`, `runtime/health.log`
- `git status` / `git diff HEAD --stat` on branch `codex/push-prep`
