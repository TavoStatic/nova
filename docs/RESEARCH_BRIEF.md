<!--
NOVA_DOC
category: research
authority: historical
last_session: 2026-08-29
last_agent: grok
session_state: current
next_step: independent challenge of work-admission kernel v1
open: live mill loop unproven
-->

# Nova research brief

**Audience:** potential academic sponsor.  
**Date:** 2026-08-29.  
**Scope:** two pages. Code and live runtime remain authority over this brief.

This note states a research question, one frozen white-box result, and what that result does **not** prove. It is not a release claim, health score, or live-autonomy demonstration.

---

## Research question

Can a governed autonomous system **admit work** before it enters an executable tree—rejecting cover, duplication, and “no such step”—and later **update that decision from causal evidence** (same proposal family under unchanged vs changed controlling conditions)?

That is stronger than “the agent picked a tool.” It requires: a real unsatisfied target; a step that could change that target; refusal when the step is ceremonial or ungrounded; suppression of the same failed path while facts are stable; reconsideration when an **independent** observation of a **relevant** fingerprint changes; and no closure from tool success alone.

Nova’s mill already executes tools, records evidence, and can refuse to close a finding when satisfaction is missing. The live system still files some non-jobs as `tool_failed` after they have already entered the tree. The missing primitive is **admission**: *this proposed work is not a real step, so it must never become executable.*

---

## Preliminary technical evidence

**Work Admission Kernel v1** is frozen at commit `dfa8745376dc769bc55bcdf8f0c65c13a59db00c` (short `dfa8745`), annotated tag `work-admission-kernel-v1`. Parent: `635e52a`.

It is a deterministic, non-mutating function:

`proposal + read-only snapshots + policy snapshot → decision JSON`

It does not import Work Tree or runtime, does not write files, and does not call an LLM. Caller-supplied tools are treated as proposals. Authority denial does not rewrite whether the underlying work is real.

**Public wording:** evaluated against **12 predefined, frozen cases**. The development record preserves the initial mismatch and a **kernel-only** correction. Internally those cases were treated as preregistered; Git shows traces and the corrected kernel **together** in `dfa8745`, so an outside reviewer can verify they are frozen but **cannot** prove creation order from that commit alone.

Clean-checkout command (CPython 3.13.1, Windows 11 AMD64):

```text
python -m unittest tests.test_work_admission_kernel -v
```

Result on a worktree of `dfa8745`: **12 tests, OK.** Console: `research/work_admission/FREEZE_v1_unittest.txt` (post-freeze documentation commit, not the v1 implementation commit). Hashes and the first-table mismatch are in `research/work_admission/FREEZE_v1.json`.

Behaviors the fixture suite actually showed:

- Cover (empty/non-causal `read`) stays **rejected** (`COVER_OR_GOAL_SUBSTITUTION`), including after unrelated noise and after independent satisfaction.
- Unchanged controlling fingerprint + prior unsatisfied causal attempt → **duplicate**, not new progress.
- Unrelated outbox/token change does **not** reactivate the causal proposal.
- Relevant package/source fingerprint change makes the causal proposal **reconsiderable** (`admitted`).
- Tool-success evidence with unsatisfied validation predicate does **not** yield `TARGET_ALREADY_SATISFIED`.
- Independent `OK` validation evidence yields **rejected** `TARGET_ALREADY_SATISFIED`, including when the fixture tree still lists an open (stale) row.
- Unauthorized proposed tool: `work_decision=admitted`, `authority_decision=tool_denied`.

**Limitation (v1, not changed):** the specification asked for independent dimension evaluation; v1 **emits winning-path `reason_codes` only**. A rejected cover may have current evidence that does not appear in `reason_codes`. Recorded as a design question in `research/work_admission/FREEZE_v1_ADDENDUM.json`. A possible v2 split (`evaluated_facts` / `decision_reason_codes` / `winning_rule`) waits on unseen tests.

---

## What remains unproven

| Claim | Status |
|---|---|
| Live Work Tree admits/rejects before materializing a stem | Unproven |
| Unstructured real mission → correct finding | Unproven |
| Empty-read cover never enters the executable tree | Unproven (live mill still can file `tool_failed`) |
| Black-box / Inspect-as-independent-judge | Unproven |
| Independent reproduction by an outside runner | Unproven |
| Mutation testing of fingerprint/cover/freshness/precedence | Unproven |

v1 is **not** live autonomous convergence. It must not be wired to mill, routes, health, or release.

---

## Independent-evaluation path

Keep v1 immutable. Next work is **outside** those hashed files: unseen cases (wording vs predicate, stale-looking-new evidence, simultaneous relevant/irrelevant change, conflicting observations, disguised cover, satisfied target then new artifact); mutation tests on **copies**; an outside reviewer reproducing `dfa8745` and challenging the contract.

Nova can show a sponsor a **versioned hypothesis**, an **implemented mechanism**, a **reproducible internal result**, a **disclosed mismatch**, and a **clear next evaluation**—not a finished autonomous product.
