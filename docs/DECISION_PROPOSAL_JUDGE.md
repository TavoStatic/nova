<!--
NOVA_DOC
category: subsystem
authority: active_working
last_session: 2026-08-05
last_agent: claude-cowork
session_state: current
next_step: calibrate judge — 12-episode bar not yet reached
open: none
-->

# Decision Proposal + Judge (stable contract)

**Status:** implementation contract  
**Scope:** autonomy selected moves (first entrance: `_execute_autonomy_recommendation`)  
**Mode:** observation-first (`observation_only=true` until calibrated)

## One sentence

Actor proposes a move; system contracts define what it is supposed to change; Judge challenges dimension by dimension; tools resolve missing facts; evidence decides whether the world moved; the work item records whether the Judge’s prediction was useful.

## Separation of roles

| Role | Owns | Must not own |
|------|------|----------------|
| Actor / orchestrator | action choice, `actor_reason` | sole author of claim used to judge itself |
| Capability / tool contracts | intended effect, expected evidence shapes | execution policy freezes |
| Pressure record | close condition (when present) | free-text advocacy |
| Judge | scores dimensions, disposition, resolution_action | planning a competing move |
| Arbiter | targeted evidence acquisition for one disputed fact | third full planner |
| Solution trail / episode | prediction vs outcome | blocking execution by default |

## DecisionProposal

```python
DecisionProposal = {
    "pressure_id": str,
    "action_id": str,
    "tool_name": str,
    "arguments": dict,

    "actor_reason": str,  # advocacy only

    "close_condition": str | None,
    "intended_effect": str,
    "expected_evidence": list[str],

    "field_sources": {
        "close_condition": str,       # pressure_record | unknown | none
        "intended_effect": str,       # capability_effect_map | actor_inferred
        "expected_evidence": list[str],  # tool_contract | capability_effect_map | actor_inferred
    },
}
```

### Claim provenance rules

1. **Action** ← Actor / orchestrator  
2. **Close condition** ← pressure record when known; else `None` with source `none`  
3. **Intended effect** ← `capability_effect_map` (tool/action catalog) when present; else **must** tag `actor_inferred` (never silently treat as contract)  
4. **Expected evidence** ← tool contract + close condition schema when present; else tag sources honestly  

`capability_effect_map` today is the in-code catalog in `services/decision_proposal_judge.py` (`_TOOL_CLAIM_CATALOG` / `_ACTION_CLAIM_CATALOG`). Expanding that map is pre-work for full contract coverage; until a tool is catalogued, fields are `actor_inferred` and alignment is weighted more cautiously.

### Actor self-description

Actor free text (`expected_effect`, explain text) is stored only as `actor_reason` / audit note. It is **not** the claim the Judge trusts without a source tag.

## JudgeReport

```python
JudgeReport = {
    "reversibility": {
        "score": float,
        "threshold": float,
        "status": "clear" | "caution" | "fail",
        "reason": str,
    },
    "context_completeness": {
        "score": float,
        "threshold": float,
        "status": "clear" | "caution" | "fail",
        "missing": list[str],
        "reason": str,
    },
    "mission_alignment": {
        "score": float,
        "threshold": float,
        "status": "clear" | "caution" | "fail",
        "reason": str,
    },
    "similar_failed_attempts": int,
    "disposition": str,  # proceed | proceed_annotate | pause_and_surface | abort_and_file
    "controlling_dimension": str,
    "resolution_action": dict | None,
    "annotations": list[str],
    "summary_score": float | None,  # analytics only — never decides execution
    "observation_only": bool,
    "enforce_disposition": bool,
}
```

### Disposition from controlling weakness (not blended average)

```text
mission_alignment status == fail
→ abort_and_file

context_completeness status == fail
→ pause_and_surface (+ resolution_action)

reversibility status == fail or caution
→ annotate, or pause if severity is high / destructive

any status == caution (without fail)
→ proceed_annotate

all clear
→ proceed
```

`summary_score` may exist for dashboards. **It never decides execution.**

### Missing close condition

If `close_condition` is `None` / empty:

- `mission_alignment.status` defaults to **`caution`** (not clear)  
- reason: no close condition to align against  
- This is incomplete scoring context, not full alignment credit  

### Non-proceed must not be a silent hold

Every `pause_and_surface` / `abort_and_file` includes `resolution_action` with:

- what is missing or wrong  
- what to gather / recheck next  
- resume condition  

## DecisionEpisode (durable on work item)

```python
DecisionEpisode = {
    "episode_id": str,
    "ts": str,
    "proposal": DecisionProposal,
    "judge_report": JudgeReport,
    "disposition": str,
    "execution": dict | None,
    "observed_evidence": list[dict],
    "close_condition_before": bool | None,
    "close_condition_after": bool | None,
    "prediction_outcome": {
        "expected_evidence_found": bool | None,
        "predicate_moved": bool | None,
        "judge_was_useful": bool | None,
    },
}
```

Stored on the work item (task meta when `target_step_id` present; else branch `decision_episodes` trail), not only in process logs.

### `judge_was_useful` (automatic)

Computed at observation time when `predicate_moved` is known:

```python
judge_was_useful = (
    (disposition in {"proceed", "proceed_annotate"} and predicate_moved is True)
    or (disposition in {"pause_and_surface", "abort_and_file"} and predicate_moved is False)
)
```

If `predicate_moved` is still unknown, leave `judge_was_useful` as `None` (not false).

This is coarse but computable without human labeling so the feedback loop has data.

## Cycle

```text
Proposal (action + derived claim + field_sources)
  → Judge (dimension statuses + controlling_dimension)
  → unresolved factual dimension?
       → targeted observation (arbiter-as-evidence)
       → Judge refresh
  → disposition
  → Executor (if observation_only or proceed*)
  → re-observe world
  → fill DecisionEpisode.prediction_outcome
```

## Enforcement

Default: `observation_only=true` — Judge never blocks.

Policy flag `decision_judge_enforce=true` may later honor pause/abort **only** when `resolution_action` is present and actionable.

## Implementation map

| Piece | Location |
|-------|----------|
| Catalog + Judge + Episode helpers | `services/decision_proposal_judge.py` |
| Execute entrance (log + stamp) | `autonomy_maintenance._execute_autonomy_recommendation` |
| Tests | `tests/test_decision_proposal_judge.py` |

## Explicit non-goals (v1)

- LLM Judge  
- Permanent third model arbiter  
- Replacing mission hold wholesale  
- Silent confidence blend as execution truth  
- SOCK changes  
