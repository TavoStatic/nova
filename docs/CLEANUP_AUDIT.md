# Nova Cleanup Audit

Date: 2026-03-15

## Confirmed Documentation Sprawl

The project had multiple root-level documents covering overlapping topics:

- `README.md`
- `README.txt`
- `README_NOVA_STRUCTURE.md`
- `README_PATCH.txt`
- `README_SEARXNG_SETUP.md`
- `PROJECT_STATUS.md`
- `BASELINE_20260314.md`

These are now being treated as compatibility entry points, while `docs/` is the canonical location.

## Cleanup Candidates

These items were identified for review before deletion rather than removed blindly:

- `memory 2.docx`: likely stray manual artifact
- `nova_bundle.zip`: likely generated bundle artifact
- `updates/previews/preview_*.txt`: generated preview history that may be prunable
- `nova-mirror.git` and `nova-mirror-backup.git`: local mirrors/backups; keep only if still part of the workflow
- `.git-backup`: confirm whether it is still needed

## Recommended Next Cleanup Pass

1. Confirm whether local mirror repositories are still intentionally used.
2. Remove obsolete generated preview files older than the current working set.
3. Decide whether `memory 2.docx` and `nova_bundle.zip` are still required.
4. Keep root docs as thin pointers only; update new content in `docs/`.

## Completed First Pass

Completed on 2026-03-15:

- removed `memory 2.docx`
- removed `nova_bundle.zip`
- pruned preview reports older than the current day from `updates/previews`

Completed on 2026-03-15 after verification:

- confirmed the working repo is the source of truth and was ahead of the local backup copies
- refreshed `nova-mirror-backup.git` to the current local refs with `git push --mirror`
- removed redundant local repo copies: `.git-backup` and `nova-mirror.git`
- kept `nova-mirror-backup.git` as the single local bare mirror
- ignored local repo backup directories in `.gitignore` so they do not pollute normal status output