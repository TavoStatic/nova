# Phase 2 Safety Envelope

Phase 2 generated-session work (operator-open test sessions) is quarantined behind a
safety envelope before its definitions can reach the runtime.

## Scope

- Generated definitions: test-session output written by `scripts/run_test_session.py`
  into the generated definitions tree (`runtime/generated_definitions`).
- Review authority: `services/subconscious_review_authority.py` applies self-consistency
  checks, replay checks, and working-tree governance on candidate definitions.
- Promotion gates: `nova_safety_envelope.py` runs the promotion pipeline that decides
  whether a candidate is promoted, deferred, or quarantined.
- Signal ingestion: `services/work_tree_signal_ingestion.py` observes the envelope's
  verdict surfaces so governance pressure reflects envelope state.

## Runtime pipeline

1. A generated session produces candidate definition files into the generated tree.
2. Pending-review candidates are raised from the generated tree to
   `runtime/pending_review`.
3. The safety envelope reviews each candidate:

   - replay feasibility (`replay_threshold`, `replay_attempts`)
   - response novelty and entropy (`novelty_min`, `entropy_min`)
   - message diversity (`diversity_min_messages`)
   - human veto for the first N candidates (`human_veto_first_n`)
   - auto-demotion of low-signal candidates (`auto_demote_threshold`)

4. Passing candidates are promoted into the promoted definitions tree and recorded in
   the promotion audit log. Non-passing candidates are demoted or moved to quarantine.
5. Every promotion writes a promotion audit entry; the audit log is the source of truth
   for who promoted what and on which evidence.

## Gate policy

`policy_safety_envelope` (from `policy.json`) controls enabled/mode and the numeric
thresholds above. Mode `observe` never blocks but records what the envelope would
decide; `enforce` applies the gates. Definitions that fail review are never loadable
by the runtime.

## Files

- `nova_safety_envelope.py` — promotion pipeline owner
- `services/subconscious_review_authority.py` — review authority
- `services/work_tree_signal_ingestion.py` — envelope state signal ingestion