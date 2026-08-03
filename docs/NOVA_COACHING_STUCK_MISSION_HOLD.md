# Coaching: why you looked stuck (mission hold vs climbable work)

This is **why + how to work + how to fix** — directions. You climb. Operator observes.

Evidence pack: `agent-tools/_stuck_evidence.py` (run when diagnosing).

---

## Why you looked stuck

You still had **climbable Work Tree tasks** (release ledger read, phase2_audit, release rebuild/validation).  
Autonomy often **did not run them** because mission truth said **hold / validation_required**.

### Evidence (what the stuck was saying)

1. **`last_regression_status=FAILED`** with:
   - empty `failed_tests`
   - empty `failed_lane`
   - tail: `regression already running (pid=…)`
2. That is **lock contention**, not a failed test suite.
3. Mission treated it as **`regression_failed`**, which freezes **validation_required** hold.
4. **Root wire bug (proved):** `_truth_evidence_for_mission` did **not** pass `last_regression_tail` / failed_tests into the truth gate. Without the tail, lock-contention cannot be detected → same FAILED becomes `regression_failed` even when the contention helper would clear it.
5. Proof: truth gate **with** full evidence → `truth_blockers=[]`. Truth gate **without** tail/tests → `truth_blockers` includes `regression_failed`.
6. Meanwhile orchestrator sometimes still recommended `active_work_tree_run_next` — and you **did** execute (e.g. read release ledger). So you are not tool-broken; you were **gated**.

**One line:** Stuck signal = “truth gate blocked the climb (and the gate was blind to lock-contention detail),” not “I can’t read/audit.”

---

## What you cannot fix alone

- **False regression FAILED in maintenance state** caused by concurrent regression lock.  
  You cannot “test your way” out of a lock-contention stamp that freezes mission.  
  Protocol fix belongs in regression/mission truth (operator/implementer). **Done in code:** lock contention is not `regression_failed` / not a mission blocker.

- **core_gate_release_drift** (if still present after refresh) is a separate truth pillar — dig before treating as thrash.

---

## What you can fix (climb)

When mission is not freezing on false regression:

1. Prefer **one release ladder** at a time (rebuild → validation → record outcome) — do not open six parallel “Run release validation” stems as separate thrash.
2. **phase2_audit** and **read** with real `tool_args` are climbable when recommended.
3. Runtime **core/guard not running** stems: use `pulse` / inspect — if core is truly down, surface that; you cannot invent a running core.

---

## How to work when stuck again

1. List open stems: climbable vs operator hold vs truth gate.  
2. If tools/args are fine but cycles show `active_work_tree trees=0` + mission `validation_required` → **read mission truth blockers**, not just the task title.  
3. If blocker is lock-contention regression → not your test failure; wait for truth protocol (now fixed) + next mission refresh.  
4. If blocker is real failed tests → climb remediation tools on the regression signal, or operator runs regression.  
5. If climbable and recommended → run the next tool; do not invent a new system.

---

## Operator stance

- Dig evidence first.  
- If Nova cannot fix the gate → we fix the gate (protocol).  
- If Nova can climb → give directions, let her climb.  
- Do not hand-clear state as the permanent strategy; do not special-case forever without proof.
