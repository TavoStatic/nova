<!--
NOVA_DOC
category: standard
authority: active_authority
last_session: 2026-08-05
last_agent: claude-cowork
session_state: current
next_step: embed in remaining docs/ files and key .py entry points
open: none
-->

# NOVA_DOC Header Standard

Every file in this project that carries documentation, design intent, or architectural decisions must declare itself with a NOVA_DOC header. This makes files self-declaring — any agent opening a file immediately knows what it is, how current it is, and where the last session left off.

Ring 1 scans for NOVA_DOC headers as part of map integrity. Files missing headers are reported as `undeclared`.

---

## Format by File Type

### Markdown (`.md`) files

Place the header as the **first block** in the file — before the title:

```
<!--
NOVA_DOC
category: <category>
authority: <authority_class>
last_session: <YYYY-MM-DD>
last_agent: <tool-name>
session_state: <state>
next_step: <one line — what needs to happen to this file>
open: <open items or breadcrumbs, or "none">
-->
```

### Python (`.py`) files — module docstring

Add to the **module-level docstring**, separated from the description by a blank line:

```python
"""
<existing description>

NOVA_DOC:
  category: <category>
  authority: <authority_class>
  last_session: <YYYY-MM-DD>
  last_agent: <tool-name>
  session_state: <state>
  next_step: <one line>
  open: <open items or "none">
"""
```

### No-extension files (e.g. `This_is_nova`)

Add at the top as plain text:

```
NOVA_DOC
category: <category>
authority: <authority_class>
last_session: <YYYY-MM-DD>
last_agent: <tool-name>
session_state: <state>
next_step: <one line>
open: <open items or "none">
```

---

## Field Reference

| Field | Values | Meaning |
|---|---|---|
| `category` | `architecture`, `subsystem`, `coaching`, `plan`, `ledger`, `standard`, `historical`, `service`, `script` | What kind of file this is |
| `authority` | `active_authority`, `active_working`, `stale_snapshot`, `historical` | How much to trust this file — matches DOC_OWNERSHIP classes |
| `last_session` | `YYYY-MM-DD` | Date of last session that touched this file |
| `last_agent` | `claude-cowork`, `grok`, `codex`, `nova`, `developer` | Who last wrote to this file |
| `session_state` | `current`, `needs_update`, `stale` | Whether the file reflects current reality |
| `next_step` | One line | What needs to happen to this file next. `none` if nothing pending. |
| `open` | One line | Open items, breadcrumbs for the next agent. `none` if clean. |

---

## Which Files Get Headers

**Required** (Ring 1 will report missing):
- All files in `docs/` with `.md` extension
- `AGENTS.md` (root)
- `This_is_nova` (root, no-extension)
- `nova_grok.md` (root)

**Encouraged** (not enforced by Ring 1):
- Entry-point `.py` files: `nova_core.py`, `nova_guard.py`, `nova_http.py`, `autonomy_maintenance.py`
- Key service files added or modified in the current session

**Not required:**
- Test files
- Auto-generated files (NOVA_LEDGER.md, runtime artifacts)
- `.jsonl` ledger files

---

## Ring 1 Integration

`services/self_scan_rings.py` → `run_ring1_map_integrity()` includes a `nova_doc_coverage` sub-check:

- Scans all `.md` files in `docs/` plus `AGENTS.md` and `nova_grok.md` at root
- Checks for presence of `NOVA_DOC` block
- Extracts `authority` and `session_state` fields
- Reports: `declared` count, `undeclared` files, `stale` files (`session_state: stale`)
- Results feed `docs/ledger/nova_findings.jsonl` as `entry_type: ring1_scan`

---

## Update Rule

When you modify a file that has a NOVA_DOC header:
1. Update `last_session` to today's date
2. Update `last_agent` to your tool name
3. Update `session_state` if it changed
4. Update `next_step` and `open` to reflect current state
5. Log the session in the ledger

Do not leave a stale header. A stale header is worse than no header — it actively misleads the next agent.
