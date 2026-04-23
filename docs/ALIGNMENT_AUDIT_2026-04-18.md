# Nova Alignment Audit

Date: 2026-04-18

## Purpose

This document is a repo-alignment map, not a feature plan. Its job is to separate active authority from stale or historical surfaces so Nova can be brought forward evenly without letting old content steer the runtime backward.

## Trust Order

When sources disagree, use this order:

1. Live runtime behavior and current shell delegation.
2. `This_is_nova` recovery checkpoints.
3. Current checked-in service wiring and active tests.
4. Current operator/control assets.
5. Root/docs status reports.
6. Repo memory notes.
7. Archived docs, generated artifacts, and legacy exact-behavior tests.

## Cross-Checked Current Truth

- `nova_http.py` is still the largest integration gravity well and the highest-risk drift surface.
- `nova_core.py` remains the other major gravity well for truth, identity, fallback assembly, and tool execution.
- The control/runtime plane is relatively healthy and already strongly service-shaped; it is not the first place to spend the next extraction cycle unless a specific drift is observed.
- The Work Tree / Scheduled Tree path is a real product surface and must be preserved, not downgraded to optional or legacy behavior.
- Drift has repeatedly come from service files existing on disk while the live shell still owned or reassembled behavior inline.
- Some repo-facing summaries are stale enough to mislead alignment work. In particular, older baseline/status notes can conflict with newer recovery checkpoints.

## Keep / Realign / Archive Map

### Keep as Active Authority

- `nova_http.py`
  - Keep as the HTTP transport and control shell.
  - Realign by reducing it to request/session orchestration plus delegation.
- `nova_core.py`
  - Keep as the main execution shell.
  - Realign by removing residual truth/identity/fallback ownership that still belongs in services.
- `supervisor.py` and supervisor services
  - Keep as deterministic ownership authority.
- `services/`
  - Keep as the primary home for extracted ownership, control, and runtime contracts.
- `templates/control.html`, `static/control.js`, `static/control.css`
  - Keep as the live operator/control UI.
- `work_tree.py` and work-tree service adapters
  - Keep as Nova's structured execution backbone.
- `nova_guard.py` and runtime status/control services
  - Keep as process truth and supervision authority.
- `tests/authoritative` and active `tests/test_*.py`
  - Keep as current regression truth, with behavior-first assertions where wording is not the contract.
- `scripts/run_regression.py`
  - Keep as the canonical lane runner; it is a live product surface, not historical debris.

### Keep but Treat as Drift Hotspots

- `nova_http.py`
  - Highest-priority realignment target.
  - Any inline deterministic routing, GET/POST routing, session mutation, or reply ordering left here can fork the live runtime.
- `nova_core.py`
  - High-priority realignment target.
  - Any residual deterministic identity/truth block or fallback context assembly left inline can reintroduce split ownership.
- `routing/heuristics.py`
  - Small file with outsized behavior risk; keep under tight ownership review.
- `tests/test_nova_http.py`, `tests/test_http_session_manager.py`, `tests/test_nova_http_transport.py`
  - Keep as shell/parity seam truth for the HTTP surface.

### Keep as Historical Reference Only

- `docs/archive/`
  - Historical reference, not live product truth.
- `tests/legacy/`
  - Opt-in historical behavior archive, not default runtime authority.
- root audit/status artifacts such as `baseline_summary.md`, `runtime_state_report.md`, `live_behavior_report.md`, `work_tree_baseline_report.md`, `test_baseline_report.md`, `hygiene_report.md`
  - Useful snapshots, but not canonical current truth once newer recovery checkpoints supersede them.
- older root README/status notes that predate the latest recovery checkpoints
  - Keep for context, but do not let them override current wiring.

### Keep as Generated Runtime Artifacts, Not Source Truth

- `runtime/`
  - Generated state and telemetry; operationally important, but not source-of-truth architecture.
- `runtime/test_sessions/`
  - Generated/saved session outputs must not compete with curated saved-session surfaces.
- `runtime/exports/`
  - Release/export outputs are downstream artifacts, not architectural authority.
- `runtime/work_tree.sqlite3.corrupt_*`
  - Forensic artifact, not active state.

## Main Gaps To Close

1. Shell ownership is still not thin enough.
   - `nova_http.py` still carries too much integration behavior.
   - `nova_core.py` still carries too much reply/truth/fallback behavior.

2. Repo truth surfaces are not consolidated.
   - `This_is_nova` contains newer architectural truth than several root/docs status files.
   - Alignment work can regress if older summaries are treated as canonical.

3. Generated and historical artifacts still compete with live surfaces.
   - runtime outputs, generated sessions, and archive docs can pollute operator understanding if they are read as current state.

4. Progress has not been made evenly across all visible layers.
   - a service may be current while the shell, assets, tests, or docs that present it are still behind.

## Root Alignment Program

### Phase 1: Declare Current Authority

- Treat `This_is_nova` plus live shell delegation as the recovery authority when status docs disagree.
- Mark root baseline/status reports as snapshot artifacts unless refreshed.
- Keep `docs/archive/` and `tests/legacy/` explicitly non-authoritative.

### Phase 2: Finish Shell Thinning at the Real Gravity Wells

- Continue reducing `nova_http.py` to transport/session/control plumbing.
- Continue reducing `nova_core.py` to execution, persistence, and orchestration plumbing.
- Move remaining routing, identity, truth, and fallback ownership into shared services only once.

### Phase 3: Consolidate Repo Truth Surfaces

- Refresh or replace stale top-level status/baseline docs so they no longer contradict current recovery checkpoints.
- Establish one current architecture/status pair and treat the rest as dated snapshots.

### Phase 4: Separate Live Assets from Generated Debris

- Keep generated runtime/test-session/export outputs visible but explicitly downstream.
- Prevent generated artifacts from being mistaken for curated saved definitions or live state of record.

### Phase 5: Audit By Layer, Not By Accident

- Transport/session entry
- deterministic ownership
- planner/heuristics
- core execution/fallback
- control/runtime plane
- supervision
- maintenance/evolution

Each layer should answer three questions:

- What is the single active owner?
- What shells still duplicate it?
- What docs/tests/assets still describe an older shape?

## Immediate Next Alignment Slice

1. Audit remaining inline ownership in `nova_http.py` against the service seams already called out in `This_is_nova`.
2. Audit remaining inline ownership in `nova_core.py` for deterministic identity/truth and fallback context assembly.
3. Refresh stale repo-facing status artifacts so they stop contradicting the recovery log.
4. Classify generated runtime/test-session artifacts versus curated saved assets so operator truth stays clean.

## Working Rule

Do not remove or downgrade a surface just because it looks duplicated. First decide whether it is:

- the active owner,
- a thin shell over the active owner,
- a historical snapshot,
- or generated output.

Alignment should retire stale ownership, not erase needed product surfaces.