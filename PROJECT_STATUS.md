# Nova Project Status (Handoff)
Date: 2026-03-08

## Current Stage
Functional prototype with strong runtime hardening and improving memory/research quality.

## What Is Done
- Runtime reliability
  - Consolidated and stabilized `health.py` modes (`check`, `diag`, `repair`).
  - Added `doctor.py` preflight validator and launcher integration.
  - Added lightweight auto-fix (`doctor --fix`) for missing local essentials.
  - Added one-command smoke flow (`nova smoke --fix`) in `nova.ps1`.

- Launch/ops
  - Updated `nova.cmd` to bypass PowerShell signing restrictions process-locally and forward args to `nova.ps1`.
  - Verified launcher flows: `doctor`, `smoke`, `run`, `guard` with preflight checks.

- Self-patch safety
  - Added patch manifest/revision guard in `nova_core.py`:
    - forward-only revision checks
    - base revision compatibility checks
    - strict manifest mode via policy
  - Added clearer patch rejection diagnostics and persisted revision tracking.

- Memory + retrieval
  - Enabled retrieval context injection into LLM prompts (knowledge + memory).
  - Added memory write filtering (`store_min_chars`, low-value skip).
  - Added `memory.py stats` and in-chat `mem stats`.
  - Added `memory.py audit` and in-chat `mem audit <query>` for relevance diagnostics.
  - Added lexical fallback in memory recall (guarded to reduce junk).

- Web capability
  - Added `web search <query>` (allowlisted search).
  - Added `web gather <url>` (fetch + cleaned snippet).
  - Added `web research <query>` (allowlisted traversal + ranking).
  - Added `web gather <index>` behavior from most recent research/search results.

- Hallucination/citation safety
  - Reduced false positives in citation requirement checks.
  - Prevented fabricated `[TOOL:...]` citations unless grounded in real tool output context.

- Session awareness and preferences
  - Added current-session context window injection (non-persistent) for follow-up awareness.
  - Added deterministic color preference recall in-session + memory fallback after restart.
  - Added deterministic animal preference recall and concise color-animal match responder.

- Tests/validation
  - Existing focused suites passing repeatedly:
    - `tests/test_action_planner.py`
    - `tests/test_health.py`
    - `tests/test_patch_guard.py`

## Known Limitations / Still Needs Work
- Web research depth quality
  - On some domains (e.g., dynamic/nav-heavy sites), `web research` may still return shallow/homepage-heavy results.
  - Needs stronger source discovery (sitemap recursion robustness + domain-specific crawling heuristics).

- Memory precision
  - Good progress, but still needs quality tuning for “vital fact” recall vs noise in broader conversations.
  - Could add explicit pinning/promoting of critical facts and confidence scoring in reply selection.

- Preference extraction coverage
  - Color/animal handling improved, but currently deterministic for those categories only.
  - General preference extraction framework is still ad-hoc.

- Test coverage gaps
  - New deterministic preference branches and web traversal paths need dedicated unit tests.

## Recommended Next TODOs (Priority Order)
1. Add tests for deterministic preference logic
   - Color/animal extraction
   - Session-first then memory-fallback behavior
   - Color-animal direct-answer path

2. Improve `web research` source discovery
   - Better sitemap-index recursion and filtering
   - Optionally add domain crawl budgets and URL pattern boosts (`peims`, `attendance`, `tsds`, etc.)

3. Add explicit memory pinning command
   - Example: `remember: <fact>`
   - Store as high-priority `kind=fact` and bias recall toward pinned facts.

4. Add `chat context` operator command
   - Print current in-session context window for debugging.

5. Add compact regression command
   - Single command to run focused checks before release.

## Quick Resume Commands
- Start Nova: `nova.cmd run`
- Preflight: `nova.cmd doctor`
- Smoke cycle: `nova.cmd smoke --fix`
- Focused tests:
  - `C:/Nova/.venv/Scripts/python.exe -m unittest -q tests/test_action_planner.py tests/test_health.py tests/test_patch_guard.py`

## Notes for Next Session
- If behavior looks stale, ensure you’re running the latest `nova_core.py` from `C:\Nova` and restart Nova.
- For memory persistence checks across restarts, keep `policy.json -> memory.enabled` set to `true`.

## Tracking Protocol (Do Every Session)
1. Update `LAST_SESSION.json` with:
  - `last_completed` (what was finished)
  - `next_priority` (what to do next)
2. Update this file (`PROJECT_STATUS.md`) only when priorities or stage change.
3. Keep `RESUME_HERE.txt` pointing to both files.

Current canonical resume order:
1. `C:\Nova\RESUME_HERE.txt`
2. `C:\Nova\LAST_SESSION.json`
3. `C:\Nova\PROJECT_STATUS.md`
