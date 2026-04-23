# Hygiene Report

## Historical Use

Historical audit snapshot from 2026-04-17.

This file reflects one hygiene audit pass and is not a live cleanup authority.

For current repo-facing truth, use:

1. `docs/REPO_CLEANUP_MATRIX_2026-04-18.md`
2. `This_is_nova`
3. `docs/CURRENT_TRUTH_2026-04-18.md`

The content below is preserved as a historical audit artifact.

Audit mode: observation only. No files were moved, deleted, archived, or repaired during this pass.

## Repo-root density

- Current root inventory:
  - `103` top-level entries
  - `82` top-level files
  - `21` top-level directories
  - `52` top-level Python files
  - `10` top-level Markdown files
  - `6` top-level JSON files
  - `6` top-level text files
- Baseline interpretation: the root remains operationally crowded by entrypoints, reports, runtime helpers, and status artifacts.

## Update and preview pressure

- `updates/previews` currently contains `536` files.
- `updates/` contains `306` `autonomy_micro_patch_*.zip` archives.
- Baseline interpretation: patch-preview and micro-patch history are now a major hygiene pressure surface.

## Runtime test-session pressure

- Current runtime session inventory:
  - `generated_definitions`: `28` files
  - `pending_review`: `26` files
  - `quarantine`: `9` files
  - `promoted`: `21` files
- The broader `runtime/test_sessions/` tree also contains many persisted `cli_vs_http` comparison artifacts.
- Baseline interpretation: generated-session buildup remains real and visible, not just a test assertion artifact.

## Stale and contradictory artifact truth

- HTTP runtime metadata is contradictory:
  - `runtime/http.pid` matches the live listener
  - `runtime/http_runtime.json` still describes an older stopped process
- Runtime freshness is uneven:
  - `runtime/pulse_snapshot.json` is stale from `2026-04-14`
  - several current-status artifact files expected by older assumptions are absent
- A corruption marker is still present at the runtime root:
  - `runtime/work_tree.sqlite3.corrupt_20260415_212517`

## Kidney and maintenance history

- Current dedicated kidney status files were absent in this pass.
- Historical maintenance evidence still exists in `runtime/autonomy_maintenance.guard.log`:
  - prior Kidney enforcement snapshots
  - repeated quarantined-waste deletions
  - earlier maintenance failures such as `ModuleNotFoundError: No module named 'active_task_constraints'`
- Baseline interpretation: hygiene governance has acted historically, but present-day status emission is less coherent than the historical log trail.

## Hygiene conclusion

- Hygiene pressure is concentrated in four places:
  - dense repo root surface area
  - preview and micro-patch accumulation
  - generated session and comparison artifact buildup
  - stale or contradictory runtime metadata that survives beyond the event that created it
- Current hygiene truth is measurable and significant even without executing cleanup.

