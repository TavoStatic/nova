# Test Baseline Report

## Historical Use

Historical audit snapshot from 2026-04-17.

This file reflects one baseline test-classification pass and is not the current canonical regression truth.

For current repo-facing truth, use:

1. `This_is_nova`
2. `docs/CURRENT_TRUTH_2026-04-18.md`
3. current active test lanes and fresh execution results

The content below is preserved as a historical audit artifact.

Audit mode: observation only. Failures were classified, not fixed.

## Tier results

- Authoritative tier:
  - `63 passed, 7 subtests passed in 0.45s`
- Legacy tier:
  - `82 skipped in 0.18s`
- Runtime-live tier:
  - `2 passed in 104.43s`
- Default regression runner lanes:
  - `unit`: failed
  - `behavior`: failed
  - `integration`: failed

## Tier interpretation

- `tests/authoritative` is the cleanest current product-aligned baseline.
- `tests/legacy` remains archaeology only. The skips are intentional and should not be interpreted as current product failure.
- `tests/runtime` is currently meaningful: it did not skip, and it passed against the live HTTP service.

## Default execution truth

- The default regression failure is currently an execution-layer defect in `scripts/run_regression.py`, not a clean set of product assertion failures.
- All three default lanes failed the same way:
  - `ModuleNotFoundError: No module named 'tests'`
- Root cause from direct source inspection:
  - `scripts/run_regression.py` loads named unittest targets like `tests.test_health` through `unittest.loadTestsFromNames(...)`.
  - The runner never inserts the repo root onto `sys.path` before that load.
  - Running the script from the repo root does not fix the problem, so this is a runner defect rather than a shell cwd mistake.

## Historical failure signal

- `runtime/autonomy_maintenance_state.json` records a previous failed regression cycle that included:
  - a `smoke_e2e` contract mismatch around the command shape used to launch `run_regression.py`
  - saved-session contamination findings under `tests/test_test_session_control_service.py`
- These are real historical signals, but they were not revalidated as fresh product failures in this scan because the current default runner fails earlier in its own import path.

## Baseline conclusion

- Current trustworthy green baseline:
  - authoritative tier
  - runtime-live tier
- Current trustworthy non-green baseline:
  - the repo's default regression entrypoint is broken as an execution seam
- Current untrustworthy signals:
  - old default-lane aggregate failure totals from prior audits
  - legacy exact-structure coverage as a product-health indicator

