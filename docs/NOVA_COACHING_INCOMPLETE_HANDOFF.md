# Nova coaching — incomplete handoff (why you failed, how to work, how to fix)

This is **instruction and direction**, not a finished implementation.  
You climb. The operator observes and corrects the track. No magic. No inventing destinations off the map.

Related:

- Design (where rings go): `docs/SELF_SCAN_RINGS_DESIGN.md`
- What happened in the character test: `runtime/character_test_incomplete_handoff.json`
- Existing scanners (do not replace): `services/nova_root_inventory.py`, `services/nova_wiring_inventory.py`, `services/work_tree_signal_ingestion.py`

---

## Why you failed

You failed because **the track was incomplete**, not because you lack a secret power.

1. **Objective was a slogan, not a climb**  
   “Implement self-scan rings — it is yours” is not a next tool with args. It is a destination with no rails.

2. **Design existed but was not put in your hands**  
   `docs/SELF_SCAN_RINGS_DESIGN.md` was on disk. Your open stems had **no `tool_args`**. Free-text titles are not file paths. `read` with empty/unresolvable args **must fail**.

3. **Handoff rule was broken**  
   Durable work is only yours when map + signal + climb + tools + done are set. You were told “yours” without those. That is operator/track error. You ran what you were given.

4. **Pin + failed tool = thrash**  
   When the same stem is targeted again after `read` is failed and still has no args, you will retry the same fail. That is legs thrash under a pin — not creativity.

5. **You did not invent rings (correct)**  
   You must not invent root taxonomy or a second gap engine from a vague title. Failing closed on bad args is better than false complete.

**One line:** You followed incomplete tracks to a dead end. Fix the tracks; do not wait for a hat.

---

## How to work (standing rules)

1. **No path, no execute** — Path tools (`read`, `ls`, `find`) need real args or explicit resolvable meta. Never treat a sentence as a path.
2. **Use pieces that exist** — Rings are roles over existing inventory/signal/climb code. Do not build a parallel gap product.
3. **Three rings, in order** — Map (Ring 1) → contract with probe context (Ring 2) → climbability of **named findings only** (Ring 3). See design doc.
4. **Ring 2 honesty** — Empty/offline status is not “46 real root gaps.” Know probe context before speaking gap counts.
5. **Ring 3** — After a finding is named, ask: is this climbable? If not, do not pin forever; mark unclimbable / advance / ask operator with a real ask.
6. **Done means proof** — Re-scan or evidence that the gap is gone (or explicit exclude recorded). Not “I read the catalog again.”
7. **Operator owns judgment** — Classify vs exclude for orphan files is ownership. Surface the list; do not invent homes if policy requires a human.

---

## How to fix (directions only — you climb)

Work **small bricks**. One brick closed with evidence before the next.

### Brick A — Understand (do this first)

1. Read this coaching file (why / how to work / how to fix).  
2. Read `docs/SELF_SCAN_RINGS_DESIGN.md` (contract).  
3. Read `runtime/character_test_incomplete_handoff.json` (what the fail looked like).  
4. Read the existing scanners (map what already exists; do not replace them):
   - `services/nova_root_inventory.py`
   - `services/nova_wiring_inventory.py`
   - relevant signal paths in `services/work_tree_signal_ingestion.py` (source_root / wiring / root_closure signals)

### Brick B — First real fix (when you implement, not before A)

**Ring 2 probe context only:** when status is missing/empty/offline, do not emit full “all status keys missing” as architecture failure.  
Touch the existing inventory **apply / payload** path. Add or use a clear probe context. Prove with a test or a before/after payload comparison.

### Brick C — Climb integrity on findings (after B)

On the **findings queue** (not a full repo walk): unresolvable path args, failed tool pins, non-executable next steps → demote / skip / hold with reason. Weave into existing executable / failure-aware / progress paths. No second engine.

### Brick D — Map orphans (ownership)

Unclassified durable files (e.g. `services/solution_trail.py`) → classify under the right root **or** explicit exclude. Probe scripts may be exclude. If unsure, operator decision pack with the path list — not infinite catalog re-read.

### Brick E — Re-scan proof

Run source root inventory / wiring payloads again. Gap gone or exclude recorded. Close the stem with evidence.

---

## What you must not do

- Mega-mission “build all rings” with no args  
- LLM free-scan inventing roots  
- Second progress system or second inventory  
- False complete without re-scan proof  
- Treat operator holds as thrash to power through  

---

## Operator stance (for humans)

Explain why. Point how to work and how to fix. **Do not hand-carry the implementation.** Observe. Correct the track if she leaves it. She runs the rails you set.
