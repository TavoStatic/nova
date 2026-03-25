# Phase 2 Safety Envelope

## Purpose
Prevent live-chat ingestion from creating overfit, unstable, or low-value training definitions.

Generated session definitions are evaluated before they are allowed to influence future automated patch packaging. The envelope keeps Phase 1 velocity while adding promotion, review, and quarantine rails for Phase 2.

## Contract
Every live-chat-derived or subconscious-generated definition is evaluated against five gates:

1. Replay stability
- Measured by replaying the definition through `scripts/run_test_session.py`.
- Must produce CLI/HTTP parity, zero diffs, and zero flagged probes.
- In enforce mode this is required.

2. Novelty
- Measured as `1 - max cosine similarity` against the promoted session pool.
- Threshold: `novelty >= 0.35`.

3. Diversity
- Measured with a composite entropy score across inferred intent labels, message shapes, and command-density bins.
- Threshold: `diversity >= 2.8`.

4. Overfit guard
- If the candidate family exists in the latest subconscious report, its `fallback_overuse` robustness must be `<= auto_demote_threshold`.
- If the family is new or not yet measurable, the definition is routed to human review.

5. Human veto window
- The first `human_veto_first_n` promoted definitions of a new family require manual review.
- These are copied to `runtime/test_sessions/pending_review` in enforce mode.

## Modes
- `observe`: evaluate and audit only. Existing generated definitions continue to flow into maintenance packaging.
- `enforce`: only definitions with a latest `promoted` audit decision are included in maintenance micro-patches.

## Destinations
- Generated source: `runtime/test_sessions/generated_definitions`
- Promoted pool: `tests/sessions`
- Pending review: `runtime/test_sessions/pending_review`
- Quarantine: `runtime/test_sessions/quarantine`
- Audit log: `runtime/test_sessions/promotion_audit.jsonl`

## Rollout
1. Start in `observe` mode.
2. Review audit output for several cycles.
3. Flip to `enforce` once replay stability and audit decisions match operator expectations.

## Current Implementation
- `nova_safety_envelope.py` evaluates, audits, promotes, or quarantines candidates.
- `subconscious_runner.py` evaluates newly generated definitions after each unattended run.
- `autonomy_maintenance.py` filters patch packaging through the latest promotion decisions when the envelope is in enforce mode.
