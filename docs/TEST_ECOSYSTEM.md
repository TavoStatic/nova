# Nova Test Ecosystem

Last verified from code: 2026-07-12

## Test Truth Has Four Layers

1. Discovered tests: every `tests/test_*.py` module and test function present in the source tree.
2. Compact regression lanes: the unit, behavior, and integration entries executed by the normal compact regression profile.
3. Source-profile lanes: subsystem-specific test membership used to detect source/test drift.
4. Validation artifacts: persisted evidence proving which profile ran, when it ran, and whether hidden or unavailable dependencies affected the result.

A green result at one layer does not automatically prove the other three.

## Current Inventory

- discovered test modules: 215
- discovered test functions: 2,016
- compact unit entries: 81
- compact behavior entries: 8
- compact integration entries: 8
- source-profile lane keys: 20

The complete per-module and per-test inventory is in `TEST_INDEX.md`.

## Owners

| Concern | Owner |
|---|---|
| Lane membership | `services/regression_lanes.py` |
| Regression runner and persisted status | `scripts/run_regression.py` |
| Root compatibility wrapper | `run_regression.py` |
| Profile drift, gaps, and unclassified tests | `services/regression_profile_inventory.py` |
| Session definition execution | `scripts/run_test_session.py` and `services/test_session_control.py` |
| Session definition discovery | `services/test_session_definitions.py` |
| Validation artifact truth | `services/validation_artifact_truth.py` |
| Release validation | `services/release_validation.py` |
| Generated-session governance | `nova_safety_envelope.py` |
| Generated queue snapshot and execution | `services/generated_work_queue_snapshot.py`, `services/nova_http_generated_work.py`, and maintenance |
| Kidney retirement of generated definitions | `kidney.py` |

## Compact Regression

The compact profile contains three lanes:

- unit: broad service and contract checks
- behavior: conversation, HTTP, routing, policy, subconscious fallback, supervisor ownership, and weather behavior
- integration: memory, package scripts, test-session execution, runtime recovery, subconscious runner, and installer scripts

The lists are explicit Python module or test identifiers. Adding a test file does not automatically add it to the compact profile.

## Source Profiles

Source-profile lanes bind subsystem changes to relevant tests. Current profiles cover:

- data pipelines
- HTTP/API/control
- memory/identity
- Ed-Fi core
- BISD Ed-Fi lane
- model runtime
- patch pipeline
- generated code
- release
- reply-quality contracts
- runtime core
- subconscious
- source-root inventory
- test ecosystem
- tool registry/policy
- web search
- Work Tree

The unit, behavior, and integration lanes also appear in the same map.

## Generated Tests

Subconscious simulation can produce generated session definitions. They move through pending review, quarantine, promotion, execution, validation, and Kidney retirement paths. A generated file's existence is not proof it was executed, and execution is not proof it is promoted or release-relevant.

## Runtime Evidence

Important artifacts include:

- `runtime/regression_status.json`
- `runtime/validation/release/latest_release_validation.json`
- `runtime/test_sessions/`
- `runtime/test_sessions/generated_definitions/`
- `runtime/test_sessions/pending_review/`
- `runtime/test_sessions/quarantine/`
- `runtime/subconscious_runs/latest.json`

Read the artifact identity, timestamp, profile, lane results, unavailable dependency counts, and hidden failure counts before using it as truth.

## Documentation Rule

Never write "all tests pass" from a targeted suite. Name the command or profile, the number of tests, the commit, and the artifact timestamp. If a test was not run during the current audit, say so.
