# Live Behavior Report

## Historical Use

Historical audit snapshot from 2026-04-17.

This report reflects one live-probe pass and is not the current behavioral authority by itself.

For current repo-facing truth, use:

1. `This_is_nova`
2. `docs/CURRENT_TRUTH_2026-04-18.md`
3. current code wiring and fresh runtime verification

The content below is preserved as an audit artifact.

Audit mode: live probes only. No code changes were made during this pass.

## Probe matrix

1. Public HTTP health probe
2. Public HTTP chat probe for explicit web research
3. Typed CLI probe through `nova_core.py` for explicit web research
4. Typed CLI probe through `nova_core.py` for open-ended fallback
5. Operator-control work-tree prompt probe
6. Plain HTTP chat work-tree create/inspect/continue probe
7. Public Work Tree listing probe

## Healthy live behavior

- HTTP health:
  - `GET /api/health` returned a healthy response with Ollama up, memory enabled, and chat login disabled.
- Public HTTP chat research path:
  - `POST /api/chat` with `research PEIMS online` returned `ok=true` and grounded TEA results plus continuation guidance.
- Typed CLI research path:
  - `nova_core.py` accepted typed input `web research PEIMS attendance reporting rules`.
  - It produced the same family of grounded TEA results and continuation guidance seen on the HTTP path.
- Typed CLI fallback path:
  - Prompt: `tell me something surprising about me`
  - Result: cautious non-fabricating reply.
  - Baseline interpretation: fallback stayed conservative rather than inventing user facts.

## Broken live behavior

- Operator control path did not honor a work-tree creation request.
  - Prompt: `start a work tree for inspect runtime queue pressure`
  - Reply: `I'll create a new workspace for analyzing runtime queue pressure. git add .`
  - Baseline interpretation: this is a route/ownership drift, not a successful work-tree action.
- Plain HTTP chat work-tree session also drifted.
  - `start a work tree for inspect runtime queue pressure` -> `Got it. I'll create a work tree for inspecting runtime queue pressure. git add .`
  - `show active work tree` -> `git status`
  - `continue work on runtime queue pressure` -> `Noted.`
- Tree inventory remained at `22` before and after these probes.
  - Baseline interpretation: the natural-language work-tree prompts did not create or advance a real live work tree during this audit.

## HTTP and CLI parity baseline

- Shared success case:
  - explicit research routing is healthy in both public HTTP chat and the typed CLI path.
- Shared safety case:
  - open-ended fallback remains cautious.
- Broken parity case:
  - work-tree language on operator/chat surfaces does not currently match the backend work-tree capability advertised elsewhere in the repo.

## Execution truth conclusion

- Nova is still adaptive and grounded on explicit research turns.
- The sharpest live behavioral regression in this audit is the work-tree ownership path at the user-facing prompt surface, not HTTP transport, not CLI research, and not fallback safety.

