<!--
NOVA_DOC
category: plan
authority: stale_snapshot
last_session: 2026-08-05
last_agent: claude-cowork
session_state: needs_update
next_step: verify promotion plan against current codegen/observe mode
open: none
-->

# Leah Instance Promotion Plan

Document class: promotion plan. Current policy keeps Leah in `observe` mode with no promoted capabilities.

## 1) Vision: Per-instance Leah

Leah should not be a generic feature pack. Each Nova instance should construct its own Leah from observed operator use, runtime pressure, and validated capability promotion.

Design principle:
- Promote only what the instance proves it needs.
- Build one capability at a time.
- Keep governance signals quieter after each step, not louder.

## 2) Current State (Post Phases 1-5 + Phase A)

As of 2026-06-29 (live verification):
- Core gate is passing in live control status:
  - layer_maturity.core_gate.ok = true
  - layer_maturity.core_gate.drift_blocked = false
  - layer_maturity.core_gate.missing_roots = []
- Required roots report ok in root closure inventory:
  - model_runtime
  - conversation_routing
  - frontdoor_cli
  - operator_control
  - http_api_control
- Leah capability gaps still present:
  - leah_conversation_continuity
  - leah_memory_recall
  - leah_voice_persona_engine
  - leah_emotional_state_model
- Gap policy remains protective:
  - capabilities_roadmap.gap_detection_config.observe_until_core_gate_passes = true

Implication:
- Foundation is now stable enough to begin deliberate Leah promotion.
- Leah is not self-building yet; capability gaps remain unpromoted.

## 3) Gate Criteria

### Global gate (must stay green)

Before and during Leah promotion:
- layer_maturity.core_gate.ok == true
- layer_maturity.core_gate.drift_blocked == false
- layer_maturity.core_gate.missing_roots is empty
- release_status.runtime_drift_expected == false for promotion/release checkpoints
- no growth in blocked governance branches after a promotion

### Per-capability gate

Use LEAH_BUILD_SEQUENCE and prerequisites from services/layer_maturity_policy.py.

Build order:
1. leah_conversation_continuity
2. leah_memory_recall
3. leah_voice_persona_engine
4. leah_emotional_state_model

Minimum per-step prerequisites:
- Capability is selected as next_leah_capability in status.
- Declared prerequisite capabilities/roots evaluate healthy.
- Actionable gap list includes only the active promoted target (narrow scope).

## 4) Promotion Playbook (Observe -> Active)

### Phase B: Instance Leah profile

Goal: encode how this instance should use Leah before codegen activation.

Inputs:
- operator usage patterns
- continuity pain points (session identity, carry-over failure)
- voice/persona expectations for this deployment
- memory retention and recall tolerance

Deliverable:
- a short instance profile document with ordered priority and acceptance tests.

### Phase C: First promotion (leah_conversation_continuity)

Policy actions:
- promote only leah_conversation_continuity
- keep other Leah capabilities unpromoted
- keep codegen scoped to the promoted capability only

Execution path:
- capability gap signal -> one leah_build/codegen branch
- preview -> patch queue -> reviewed apply
- no broad capability batching in a single cycle

Success criteria:
- continuity holds across turns and sessions in real usage
- no new persistent blocked branches tied to this promotion
- capability gap count for promoted target goes to closed/resolved state

### Phase D: Controlled codegen builder mode

Rules:
- codegen remains observe for non-promoted capability gaps
- active generation only for promoted capability
- patch bridge path required for all generated changes:
  - preview
  - patch queue review
  - explicit apply

Safety:
- no auto-apply for Leah capability work until confidence window is met
- generated tests required for every promoted capability increment

### Phase E: Promotion ladder

For each remaining capability in sequence:
1. Promote single capability in policy
2. Generate narrow work-tree branch
3. Validate (tests + control status + operator review)
4. Observe in production window
5. Proceed only if signal noise does not regress

## 5) Rollback Plan

Rollback triggers:
- core gate flips false
- drift_blocked returns true
- blocked branch count rises and persists after promotion
- operator outbox accumulates unresolved Leah-related failure notices

Rollback actions:
1. Revert capability to observe-only state in policy
2. Pause Leah codegen execution group activity
3. Keep generated artifacts in preview/review only
4. Re-run core gate and root closure checks
5. Resume at previous stable capability

## 6) PR-sized Work Items (Dependency Order)

P0 (baseline lock):
- Capture a canonical pre-promotion snapshot of:
  - core gate
  - root closure inventory required roots
  - capability gaps and next_leah_capability

P1 (Phase B profile):
- Add a concise instance profile doc for Leah priorities and acceptance checks.

P2 (single-capability policy promotion):
- Promote leah_conversation_continuity only.
- Ensure maturity filters keep scope narrow.

P3 (execution + validation):
- Execute one governed branch for promoted capability.
- Require tests and patch queue review.
- Verify no persistent blocked-branch regression.

P4 (observe window + decision):
- Run defined observation window.
- If stable, approve next sequence item.
- If unstable, rollback and record root cause.

## 7) Definition of Done for "First Leah Build Started"

This milestone is complete when:
- core gate remains green throughout promotion window
- leah_conversation_continuity is promoted and validated
- capability gap signal for that capability is no longer unresolved
- no new long-lived blocked governance branches are introduced
- next_leah_capability advances according to sequence
