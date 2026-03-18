# Nova Status

Date: 2026-03-16

## Current State

Nova is in a stable state after the recent privacy, admin, tool-contract, memory-boundary, memory-observability, and identity-routing work.

Nova now has one actual routing spine in both CLI and HTTP. Legacy command and keyword handlers remain as execution targets, but no longer act as independent authorities. The planner owns route selection; the old handlers are now subordinate paths.

## Recently Completed

- stabilized HTTP privacy and session ownership enforcement
- added explicit memory scopes: `private`, `shared`, `hybrid`
- added managed local chat-user storage with hashed passwords
- added control-room admin UI for memory scope and chat users
- expanded HTTP/privacy/memory regression coverage
- removed the blocking interactive behavior from automated teach-flow test runs unless explicitly enabled
- fixed deterministic routing regressions for developer and location questions
- restored full automated suite health
- replaced `nova_core.py` memory subprocess hops with in-process calls into `memory.py`
- added control-room memory totals to live status payloads
- added focused regression coverage for the direct memory service path
- added structured memory event logging plus control-room summaries for recent memory writes, recalls, skips, and latency
- confirmed live runtime parity for memory observability with one add, one recall, and one duplicate-skip probe against the control-room summary path
- added per-turn action-ledger route traces plus command-center visibility for the latest routing path summary
- reduced local repo backup sprawl by refreshing one retained bare mirror and removing redundant backup copies
- fixed CLI identity-learning and routing regressions for assistant/developer facts, creator binding, and reflective retry prompts
- softened identity truth-hierarchy misses so remaining identity gaps do not terminate reasoning before fallback
- added a session fact sheet and post-draft claim gate to the CLI LLM fallback path to reduce unsupported factual claims
- restored deterministic creator handling for plain creator queries such as "who is your creator?" and "who made you?"
- added focused identity regressions and verified the live CLI creator path end to end
- removed the duplicate planner execution block from the CLI loop and restored a single planner-owned dispatch path before fallback stages
- mirrored the same planner-owned routing shape into `nova_http.py` so CLI and HTTP no longer diverge on command and keyword ownership
- added ledger-level assertions for CLI and HTTP route ownership so tests now verify `planner_decision` and `route_summary`, not just final replies
- extracted planner turn understanding, route classification, and execution choice into `planner_decision.py`
- reduced `action_planner.py` to a thin adapter over the decision module

## Validation

- full automated test suite passes:

```powershell
C:\Nova\.venv\Scripts\python.exe -m unittest discover -s C:\Nova\tests
```

Latest result:

- `143` tests
- `OK`

Focused identity verification:

- `C:\Nova\.venv\Scripts\python.exe -m unittest tests.test_core_identity_learning`
- `39` tests
- `OK`

Focused routing and HTTP verification:

- `C:\Nova\.venv\Scripts\python.exe -m unittest tests.test_planner_decision tests.test_action_planner tests.test_core_identity_learning tests.test_http_identity_chat tests.test_nova_http`
- `96` tests
- `OK`
- ledger assertions now confirm planner ownership for delegated `route_command`, `route_keyword`, and `respond` paths

## Verification Marker

Last verified test run:

- `2026-03-16`

Test suite:

- `96` focused tests
- `OK`

## Open Work

- decide whether memory should get its own explicit service/observability module beyond the current in-process boundary cleanup
- improve `what do you know about me?` when no active developer identity is bound, so the live reply can surface structured session facts instead of a thin uncertainty fallback
- keep extending planner coverage through `planner_decision.py` instead of reintroducing mixed routing heuristics across multiple files

## Documentation Rule

Project documentation is now centralized under `C:\Nova\docs`.

- update `docs/STATUS.md` for project state changes
- update `docs/TOOLS.md` and `docs/TOOLING_ROADMAP.md` for tool changes
- avoid adding new root-level project docs unless they are thin compatibility pointers

## Resume Guidance

Primary resume order:

1. `C:\Nova\RESUME_HERE.txt`
2. `C:\Nova\LAST_SESSION.json`
3. `C:\Nova\docs\STATUS.md`

Suggested resume prompt:

```text
continue from C:\Nova\docs\STATUS.md
```