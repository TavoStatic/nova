# Kidney System

## Purpose
The Kidney is the cleanup partner to the Phase 2 safety envelope.

- Safety envelope controls what can be promoted into future training and patch packaging.
- Kidney controls what should be archived or flushed once it becomes stale, low-value, or clearly disposable.

## Modes
- `observe`: scan and report only.
- `enforce`: snapshot and apply archive/delete actions.

## Commands
- `kidney status`
- `kidney now`
- `kidney dry-run`
- `kidney protect <pattern>`

## Filters
1. Old definitions
- Generated definitions older than `definition_max_age_days` or with novelty below `definition_novelty_min` are marked for archive.

2. Quarantined waste
- Pending-review or quarantine definitions older than `quarantine_max_age_hours`, or carrying excessive fallback pressure, are marked for deletion.

3. Preview junk
- Patch preview reports older than `preview_max_age_days` and no longer marked `eligible` are marked for deletion.

4. Stale snapshots
- Patch snapshots and backup-style runtime state files older than `snapshot_max_age_days` are marked for deletion.

5. Temp bloat
- Old test-session run artifacts, runtime text dumps, and temp probe artifacts older than `temp_max_age_days` are marked for deletion.

## Safety Rails
- Enforce mode creates a pre-flush snapshot under `runtime/kidney/snapshots`.
- Protected patterns are never touched.
- Status is written to `runtime/kidney/status.json`.
- Maintenance logs Kidney activity with a `[KIDNEY]` prefix.