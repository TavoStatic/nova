# Self-scan rings — wiring design

Document class: **wiring design / implementation contract**.  
Not session notes. Not current implementation truth until rings are bound to existing scanners.

**Do not put the primary copy in `nova_grok.md`.** That file is archaeology and conversation residue. Nova cannot treat grok notes as a wiring surface. This document is the human + implementer spec for weaving rings into **existing** inventory, signal, and climb paths — no second gap engine.

Related:

- Progress / solution experience (same fractal, work-item scale): progress, trail, executable next step  
- Handoff method: durable code is not “hers” until map + climb + done  
- Later UI: operator plain language (parked; not this doc)

### Backpack adoption (parked one-liner)

**Three rings = backpack adoption protocol. Manifest declares source root + wiring surface + status keys. Nova verifies through rings before treating backpack as hers.**

---

## Core insight

Self-scan at architecture scale **is the progress experience at a larger zoom**:

| Progress (finding) | Self-scan (architecture) |
|--------------------|---------------------------|
| Open finding | Map / contract gap |
| Locate + next tool | Classify / wire / exclude / ask |
| Evidence | Re-scan proves gap gone |
| Hold / thrash | Museum of holds if unclimbable |

**Do not build a second progress system.** Rings **emit or refine work** that the existing work-tree + progress path must climb.

**Do not duplicate scanners.** Rings name **roles** for pieces that largely already exist.

---

## Existing pieces (weave these)

| Piece | Role today | Ring |
|-------|------------|------|
| `services/nova_root_inventory.py` → `build_source_root_inventory_payload` | Unwired roots, unclassified files, missing evidence files | **1** |
| `services/nova_wiring_inventory.py` → `build_wiring_inventory_payload` | Surface-level wiring gaps | **2** |
| `build_root_closure_inventory_payload` | Per-root status/signal/tool/action closure | **2** |
| `build_source_wiring_probe_payload` | Declared paths missing / non-executable | **2** |
| `build_self_repair_closure_inventory_payload` | Self-repair closure gaps | **2** (related) |
| `services/work_tree_signal_ingestion.py` | Turns inventory payloads into work-tree signals / sequences | **1→2 → findings** |
| Control / maintenance status surfaces | Attach inventory to status for signal ingestion | **1–2 input** |
| Work tree next step, tool args, tool_state, progress, trail | Climb integrity for open stems | **3** (target home) |
| Active work candidates / executable / failure-aware | Prefer climbable work; demote failed thrash | **3** (partial today) |

**Not a new product:** no parallel “gap museum,” no LLM free-scan inventing roots, no second inventory DB.

---

## Three rings

Three precise questions. Three deterministic scans. No invention of taxonomy by free roam.

### Ring 1 — Map integrity

**Question:** Does every durable source path have a home (or an explicit exclude)?

**Input:** repo path set + `SOURCE_ROOTS` / coverage rules.  
**Existing scanner:** `build_source_root_inventory_payload`.  
**Output findings (named, concrete):**

- unwired roots  
- missing evidence files for a root  
- unclassified source files (paths listed)

**Does not:** invent new root_ids, redesign surfaces, or judge climbability.

### Ring 2 — Contract integrity

**Question:** For each **declared** surface/root, do signal / tool / action / status / evidence contracts still match reality?

**Input:** `WIRING_SURFACES` + related closure/probe builders + **probe context**.  
**Existing scanners:** wiring inventory, root closure, source wiring probe (and related closure inventories).  
**Output findings:** missing keys, missing paths, declared-but-dead, live-but-undeclared (where measurable).

#### Probe context (required, not optional)

Ring 2 **must know its own probe context** before it speaks:

| Context | Meaning |
|---------|---------|
| `live_status` | Status payload is fresh and intended for closure comparison |
| `offline` / empty status | Do **not** report “all status keys missing” as 46 real architecture failures |
| `partial` | Only evaluate dimensions that are valid without full status |

False alarms erode operator trust. **“46 gaps” with empty status is a probe bug, not a root-cause storm.**

**Does not:** scan the whole repo for new files (that is Ring 1). Does not invent new surfaces.

### Ring 3 — Climb integrity

**Question:** Of the findings we already named, which are actually climbable?

**Input:** **findings queue only** — work-tree open stems / signals produced from Rings 1–2 (and any other governed findings already on the tree).  
**Not input:** full codebase scan.

**This is the sharpest ring.** Rings 1 and 2 find problems. Ring 3 separates a self-aware system from a **museum of holds**.

Without Ring 3, more self-scan **worsens** the queue: longer holds, catalog re-reads, unresolvable tools.

**Checks (deterministic, on each surfaced finding / next stem):**

- Next tool is in the safe execute set (when autonomy is to run it)  
- Tool args resolvable (no free-text title-as-path)  
- Tool not permanently failed without an alternate stem or trail advance  
- Sequence / trail has a productive next move, or explicit operator hold with a real ask  
- Progress motion not “moving” solely on failure thrash  

**Output:**

- climbable → eligible for active work / progress climb  
- unclimbable → do **not** pin as fake execute; mark blocked/stalled with reason; prefer repair stem (fix args, advance trail, or operator decision pack) over thrash  

**Partial existing weave:** executable candidates, failure-aware decider, unresolvable path args, demote failed tools. Ring 3 is the **named contract** to complete and bind to the findings queue, not a greenfield scanner.

---

## Sequencing

```text
Ring 1 (map)  →  findings A
Ring 2 (contract, with probe context)  →  findings B
Findings queue Q = A ∪ B (and existing open governed work)
Ring 3 (climb)  →  on Q only: climbable vs unclimbable + why
Progress / trail / active work  →  climb the climbable; do not museum the rest
Re-scan Ring 1–2  →  proof of close (or explicit exclude recorded)
```

| Ring | Scope | Must not reach |
|------|--------|----------------|
| 1 | Paths vs map | Live status closure theater |
| 2 | Declared contracts vs reality | Whole-repo invention; offline-as-live |
| 3 | Named findings’ climbability | Repo crawl; new gap types |

Each ring’s input is the previous ring’s output or the findings queue. **No ring reaches past its scope.**

---

## Handoff method (same fractal)

Landing durable code without map + climb + done is incomplete handoff.

| Adoption question | Satisfied by |
|-------------------|--------------|
| Where on the map? | Ring 1 clean (or explicit exclude) |
| Contract declared and live? | Ring 2 clean in live context |
| Can she climb the work? | Ring 3 climbable |
| Done? | Re-scan gap gone + evidence |

Self-scan rings are **how she notices incomplete handoff**. Progress experience is **how she climbs once the finding is named and climbable**.

---

## Implementation stance (do not rush)

1. **Spec first (this doc)** — contract for weave.  
2. **Bind Ring 2 probe context** before trusting gap counts in maintenance/UI.  
3. **Complete Ring 3 on findings queue** using existing executable / trail / progress pieces — no second engine.  
4. **Tighten Ring 1→signal sequences** so next steps are classify / exclude / decision pack, not infinite catalog read.  
5. **Only then** optional deeper probes (e.g. import graph) that still feed Ring 1–2 outputs.

**Runtime weave (landed):**

- `services/self_scan_rings.py` — `run_self_scan_rings`, ring 1–3 runners, `assess_stem_climbability`, `resolve_probe_context`
- `build_wiring_inventory_payload` / `build_root_closure_inventory_payload` — `probe_context` (offline/partial do not score missing status keys)
- Active-work candidates — Ring 3 `climbable` / `climb_reason` on orchestrator branch rows
- Maintenance status refresh — attaches `self_scan_rings` payload after root-closure refresh
- Map coverage — `solution_trail`, `work_tree_task_progress`, `self_scan_rings` under `work_tree`; progress probe scripts under `diagnostics_hygiene`

---

## Explicit non-goals

- LLM invents root taxonomy from a repo walk  
- Second inventory or second progress UI  
- Self-scan that only lengthens holds  
- Claiming full “dark matter” coverage  

---

## Where this lives

| Location | Role |
|----------|------|
| **`docs/SELF_SCAN_RINGS_DESIGN.md` (this file)** | Wiring design / implementation contract |
| `nova_grok.md` | Do **not** use as primary; optional one-line pointer only |
| Code (`nova_root_inventory`, `nova_wiring_inventory`, signal ingestion, work tree, maintenance) | Eventual runtime home of the rings |

Nova treats this as a **wiring spec only when implementers encode the rings into those modules and status/signal paths.** Markdown alone is not a sensor.

---

## One-line contract

> Ring 1 names map gaps; Ring 2 names contract gaps with honest probe context; Ring 3 only asks whether those named findings are climbable — then the existing progress path climbs them, or we stop building a museum of holds.
