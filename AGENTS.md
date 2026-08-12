<!--
NOVA_DOC
category: architecture
authority: active_authority
last_session: 2026-08-05
last_agent: claude-cowork
session_state: current
next_step: none
open: none
-->

# How to work on Nova (agent rules)

Operator-enforced. Read this before scanning, diagnosing, or changing Nova.

**Documentation system: read `docs/NOVA_POSTAL.md` before touching any doc.**
It tells you where to find anything and where to put anything you write.

Docs under `docs/`, `nova_grok.md`, status writeups, and old audits **lag**. They are not authority when they conflict with code or live runtime.

---

## The non-negotiables

### 1. Scan code first
- **Code and live runtime are truth.**
- Documentation is all over the place and has not kept up — especially recent days.
- Do not invent architecture, open-work lists, or “what Nova is” from docs alone.
- Prefer: source, tests, work-tree DB, maintenance logs, guard/core process truth.

### 2. Root only — finish unfinished work end to end
- Fix **roots**, not thrash, not band-aids labeled “root.”
- Honest fix = **finish what is still open**, end to end — not polish a ceremony around incomplete work.
- Do not gate an unfinished product into **ready-to-ship** / release self-rebuild thrash.
- Shipment packaging is **not** the job while major open work remains incomplete.

### 3. Full analysis needs the conveyor running
- Without **guard**, cycles and solution push do not run.
- Do not diagnose “stuck solutions” or deep live behavior while supervision is down without saying the analysis is incomplete.
- Check guard / maintenance cycle clock before treating live state as the full picture.

### 4. Do not confuse loud surfaces with the real job
- Release thrash, mission hold, generated queue, green gates — can be real, but they are not “finish Nova.”
- Do not spend the session “fixing shipment” when the product is still unfinished.
- Do not rewrite/repackage for ship as a substitute for completing open work.

### 5. Say less process theater
- Do not perform long “I will not do X” speeches while still doing X.
- Do not list don’ts instead of finishing work.
- When the operator names a rule, **keep it** — re-asking or re-inventing it is failure.

---

## Do

- Open the **code** (and runtime evidence) first.
- Name unfinished areas as **incomplete end-to-end work**, not as ship blockers only.
- Prefer small closed bricks with proof over mega-missions.
- Use existing inventory/wiring/work-tree rails when climbing governed findings — do not invent a second gap product from vibes.
- When stuck: dig → root → finish; verify with evidence.

## Don’t

- Don’t lead with docs, design notes, or stale STATUS as the map.
- Don’t free-scan invent taxonomy and call it a Nova scan without reading code.
- Don’t “quick win” gates, thrash rails, or release ladder while open product work is unfinished.
- Don’t treat Generated Queue / release rebuild loops as proof the product is done.
- Don’t ignore guard-down when analyzing push/cycle failure.
- Don’t SOCK (operator-owned) without explicit permission.
- Don’t commit unless the operator asked.

---

## Scan order (when asked to scan)

1. **Code** (and live runtime if the question is live).
2. Only then docs — as secondary, often stale, never primary truth.
3. Report unfinished work and incomplete end-to-end paths from what code/runtime actually show.

---

## Related (secondary; not above this file)

- `docs/NOVA_COACHING_INCOMPLETE_HANDOFF.md` — tracks, rings, no invent
- `docs/STATUS.md` — explicitly: history docs do not override code/runtime
- `docs/SELF_SCAN_RINGS_DESIGN.md` — weave existing scanners; no second engine

If this file conflicts with a stale doc: **this file + code win.**

---

## Agent identity and ledger naming

Each agent that works on Nova has a canonical `last_agent` value for NOVA_DOC headers and ledger entries:

| Agent | `last_agent` value | Role |
|---|---|---|
| Claude Cowork | `claude-cowork` | Primary session agent — doc, code, wiring |
| Codex | `codex` | Coding and refactor sessions via OpenAI Codex CLI |
| Grok | `grok` | Architecture and design sessions (see `nova_grok.md`) |
| Nova itself | `nova` | Ring scan findings, autonomy maintenance entries |
| Developer (human) | `developer` | Manual edits, direct commits |

**Codex-specific rules:**
- Use `last_agent: codex` in any NOVA_DOC header you update
- Use `--tool codex` in `log_session.py` entries
- Codex sessions follow the same three-phase protocol as all agents: read AGENTS.md → NOVA_LEDGER.md → NOVA_POSTAL.md before starting; log session on close
- Codex must not register new SOURCE_ROOTs without a corresponding evidence file; scan `services/nova_root_inventory.py` for the current list before adding wiring
- Codex's code-generation sessions are subject to the same "root only" rule — do not generate scaffolding that bypasses existing governance rails (supervisor, work tree, mission)

---

## Documentation ledger rule

Every developer session that changes Nova must close with an entry in `docs/ledger/session_log.jsonl`.

```bash
python scripts/log_session.py \
  --tool claude-cowork \
  --session-id "short_id" \
  --modules "file1.py,file2.py" \
  --changes "What changed,What was added" \
  --tests 0 \
  --docs-added "docs/NEW.md" \
  --notes "Optional note"
```

Every new doc goes to `docs/` (not root) and gets registered in `docs/DOC_OWNERSHIP.md`.
The living ledger is at `docs/NOVA_LEDGER.md` — regenerate with `python scripts/generate_nova_ledger.py`.
