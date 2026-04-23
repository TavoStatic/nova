# NYO System Real-World Tasks

Date: 2026-04-01

## Purpose

This document defines how to evaluate Nova on real-world tasks instead of only seam regressions, synthetic probes, or packaging gates.

The repo already has the machinery to run multi-turn task sessions:

- `scripts/run_test_session.py`
- `tests/sessions/*.json`
- operator sessions through `/control`
- generated work queue and parity reporting

What has been missing is a deliberate task format for realistic operator work.

This document closes that gap.

## What Counts As A Real-World Task

A real-world task is not just a narrow routing probe.

It should require Nova to do one or more of the following:

- understand an operator objective
- keep context across multiple turns
- inspect real repo or runtime state
- choose between multiple viable actions
- explain tradeoffs or risks
- produce an operator-usable outcome

Good examples:

- assess whether the current release candidate is actually shippable
- inspect the next open queue item and propose the shortest blocking fix path
- plan an operator handoff from an extracted package
- investigate a drift or status mismatch and explain what is wrong

Non-examples:

- one-shot keyword probes only meant to test routing ownership
- trivial command aliases
- synthetic prompts with no operator outcome

## Storage Location

Store real-world task definitions under:

- `tests/sessions/real_world/`

These files use the same session runner as the existing test sessions.

That means they can be replayed without inventing a new harness.

## Task File Format

The current runner requires only:

- `name`
- `messages`

But real-world task files should include richer metadata so they are useful as a task library.

Recommended fields:

```json
{
  "name": "short display name",
  "task_id": "stable_task_id",
  "source": "real_world",
  "category": "release|operator|investigation|handoff|research",
  "objective": "what the operator is trying to get done",
  "messages": [
    "first operator prompt",
    "optional follow-up prompt"
  ],
  "success_signals": [
    "what good behavior looks like"
  ],
  "failure_signals": [
    "what bad behavior looks like"
  ],
  "evidence_to_review": [
    "route summary",
    "assistant answer quality",
    "grounding",
    "tool use"
  ],
  "notes": "optional setup or review notes"
}
```

Extra fields are safe because the current runner ignores metadata it does not need.

## How To Run A Real-World Task

From the workspace root:

```powershell
C:\Nova\.venv\Scripts\python.exe C:\Nova\scripts\run_test_session.py real_world\release_candidate_assessment.json
```

Or pass an explicit path:

```powershell
C:\Nova\.venv\Scripts\python.exe C:\Nova\scripts\run_test_session.py C:\Nova\tests\sessions\real_world\operator_handoff_audit.json
```

## Review Standard

When reviewing a real-world task run, do not score only on whether Nova answered something plausible.

Review these dimensions:

1. objective understanding
2. context retention across turns
3. grounding in actual repo/runtime truth
4. route choice quality
5. operator usefulness of the final answer
6. honesty about uncertainty or blockers

## How To Add New Real-World Tasks

1. Start from `tests/sessions/real_world/TEMPLATE_real_world_task.json`.
2. Write the task as an operator objective, not a routing probe.
3. Include at least one success signal and one failure signal.
4. Prefer tasks that expose real coordination problems across routing, memory, operator surfaces, packaging, or runtime truth.
5. Keep the task stable enough to be rerun after refactors.

## Starter Task Set

The repo now includes starter real-world tasks for:

- release candidate assessment
- operator handoff audit
- queue-item investigation planning

These should be treated as the first task library, not the final one.

## Next Maturity Step

Once this library is useful, the next step should be to add a small summary command that:

- lists the real-world tasks
- runs one by name
- records a review note or outcome

That is optional.

The critical step right now is simply to start evaluating Nova against realistic operator work instead of only seam-level regressions.