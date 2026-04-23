# Baseline Summary

## Historical Use

Historical audit snapshot from 2026-04-17.

This file captures one audit pass and is not the current canonical baseline.

For current repo-facing truth, use:

1. `This_is_nova`
2. `docs/CURRENT_TRUTH_2026-04-18.md`
3. `docs/ALIGNMENT_AUDIT_2026-04-18.md`

The content below is preserved as a historical audit snapshot.

Read-only baseline audit complete. No fixes were made during the scan.

## What is stable right now?

- Public HTTP health is live and healthy.
- Public HTTP chat still handles explicit grounded research correctly.
- The typed CLI path through `nova_core.py` still handles explicit grounded research correctly.
- Typed CLI fallback remains conservative on open-ended personal prompts.
- `tests/authoritative` is green.
- `tests/runtime` is green against the live HTTP service.
- Work Tree backend persistence and listing are live.

## What has regressed?

- The repo's default regression entrypoint is currently broken.
	- `scripts/run_regression.py` cannot import its named `tests.*` targets and fails all three lanes before it provides trustworthy product signal.
- Work-tree prompt ownership is drifting on user-facing surfaces.
	- operator and plain chat prompts that should create, inspect, or continue work trees are misrouting into generic command-like replies such as `git add .`, `git status`, and `Noted.`
- Runtime metadata consistency has regressed.
	- `runtime/http_runtime.json` does not match the live HTTP process recorded in `runtime/http.pid`.

## What is incomplete but not clearly regressed?

- The control/status surface is reachable, but many summary fields are currently thin or `null` rather than fully populated.
- The autonomy-maintenance ledger is present, but it reads more like prior-cycle evidence than a clean live-health summary.
- Work Tree backend state exists, but many active and blocked branches remain unturned over.

## What old tests are lying?

- Legacy tier is not a current product baseline. Its skips are intentional and should not be treated as regressions.
- Older baseline totals from the default regression lane are not trustworthy until the lane runner itself is repaired.
- Earlier stale audit claims that `tests/runtime` merely skipped and that `/api/chat` was returning `403` are no longer true in the current environment.

## What becomes the new baseline?

- Product-truth baseline:
	- `tests/authoritative`
	- `tests/runtime`
	- live `/api/health`
	- live `/api/chat` explicit research probe
	- typed CLI explicit research probe
	- typed CLI open-ended fallback probe
	- backend Work Tree listing and DB-state inspection
- Execution-truth baseline:
	- treat `scripts/run_regression.py` as currently broken until repaired
	- do not treat its current failures as clean product-regression counts

## Top 5 next needs for Nova

1. Repair `scripts/run_regression.py` so the default unit, behavior, and integration lanes can produce real signal again.
2. Restore correct work-tree routing and ownership on operator and plain chat prompt surfaces.
3. Reconcile live runtime metadata emission so `http_runtime.json`, pid files, and control/status agree.
4. Make current autonomy-maintenance and Kidney state visible through coherent live status artifacts instead of mostly historical logs.
5. Reduce hygiene buildup in `updates/previews`, micro-patch archives, and `runtime/test_sessions` so operator truth surfaces stop competing with stale inventory.

## Baseline conclusion

Nova is not collapsed. The live HTTP and CLI research paths are healthy, and the forward-looking test tiers are green. The main current faults are execution-governance faults around the default regression runner, prompt-surface routing faults around Work Tree, and stale runtime metadata that no longer matches the live process state.

