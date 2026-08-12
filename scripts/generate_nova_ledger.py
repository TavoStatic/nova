"""
generate_nova_ledger.py
-----------------------

NOVA_DOC:
  category: script
  authority: active_authority
  last_session: 2026-08-05
  last_agent: claude-cowork
  session_state: current
  next_step: none
  open: none
Renders docs/NOVA_LEDGER.md from both ledger sources:
  - docs/ledger/session_log.jsonl   (developer sessions)
  - docs/ledger/nova_findings.jsonl (Nova's scan findings)

Run after any session or after Nova writes new findings.
Usage: python scripts/generate_nova_ledger.py
"""
from __future__ import annotations

import json
import os
from collections import defaultdict
from datetime import datetime
from pathlib import Path

NOVA_ROOT = Path(__file__).parent.parent
LEDGER_DIR = NOVA_ROOT / "docs" / "ledger"
SESSION_LOG = LEDGER_DIR / "session_log.jsonl"
NOVA_FINDINGS = LEDGER_DIR / "nova_findings.jsonl"
OUTPUT = NOVA_ROOT / "docs" / "NOVA_LEDGER.md"

AUTHORITY_ORDER = ["active_authority", "active_working", "stale_snapshot", "historical"]
AUTHORITY_LABEL = {
    "active_authority": "✅ Active Authority",
    "active_working": "🔵 Active Working",
    "stale_snapshot": "⚠️  Stale Snapshot",
    "historical": "📦 Historical / Archive",
}


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    entries = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return entries


def _fmt_date(d: str) -> str:
    try:
        return datetime.strptime(d, "%Y-%m-%d").strftime("%Y-%m-%d")
    except Exception:
        return str(d)


def render(sessions: list[dict], findings: list[dict]) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines: list[str] = []

    lines.append("# Nova Living Ledger")
    lines.append("")
    lines.append(f"_Generated: {now}_")
    lines.append("")
    lines.append("Two sources feed this document: **developer sessions** and **Nova's own scan findings**.")
    lines.append("Append to `docs/ledger/session_log.jsonl` (developer) or `docs/ledger/nova_findings.jsonl` (Nova),")
    lines.append("then re-run `python scripts/generate_nova_ledger.py`.")
    lines.append("")

    # ── Session History ────────────────────────────────────────────────────────
    lines.append("---")
    lines.append("")
    lines.append("## Session History")
    lines.append("")
    lines.append("Chronological record of every developer session that touched Nova.")
    lines.append("")

    session_entries = [s for s in sessions if s.get("entry_type") != "doc_classification"]
    session_entries.sort(key=lambda x: x.get("date", ""), reverse=True)

    for s in session_entries:
        date = _fmt_date(s.get("date", "unknown"))
        tool = s.get("tool", "unknown")
        sid = s.get("session_id", "")
        lines.append(f"### {date} — {tool}")
        if sid:
            lines.append(f"_Session: {sid}_")
        lines.append("")

        modules = s.get("modules_touched", [])
        if modules:
            lines.append(f"**Modules touched:** {', '.join(f'`{m}`' for m in modules)}")
            lines.append("")

        changes = s.get("changes", [])
        if changes:
            lines.append("**Changes:**")
            for c in changes:
                lines.append(f"- {c}")
            lines.append("")

        tests = s.get("tests_added", 0)
        docs_added = s.get("docs_added", [])
        docs_updated = s.get("docs_updated", [])
        if tests or docs_added or docs_updated:
            meta = []
            if tests:
                meta.append(f"{tests} tests added")
            if docs_added:
                meta.append(f"docs added: {', '.join(f'`{d}`' for d in docs_added)}")
            if docs_updated:
                meta.append(f"docs updated: {', '.join(f'`{d}`' for d in docs_updated)}")
            lines.append(f"**Meta:** {' · '.join(meta)}")
            lines.append("")

        notes = s.get("notes", "")
        if notes:
            lines.append(f"_Note: {notes}_")
            lines.append("")

    # ── Documentation Registry ─────────────────────────────────────────────────
    lines.append("---")
    lines.append("")
    lines.append("## Documentation Registry")
    lines.append("")
    lines.append("Every known doc file classified by authority and last verification date.")
    lines.append("")

    doc_entries = [f for f in findings if f.get("entry_type") == "doc_classification"]
    by_class: dict[str, list[dict]] = defaultdict(list)
    for d in doc_entries:
        cls = d.get("authority_class", "historical")
        by_class[cls].append(d)

    for cls in AUTHORITY_ORDER:
        docs = sorted(by_class.get(cls, []), key=lambda x: x.get("file", ""))
        if not docs:
            continue
        lines.append(f"### {AUTHORITY_LABEL[cls]}")
        lines.append("")
        lines.append("| File | Last Verified | Verified By | Notes |")
        lines.append("|------|--------------|-------------|-------|")
        for d in docs:
            f = d.get("file", "")
            lv = _fmt_date(d.get("last_verified", "—"))
            vb = d.get("verified_by", "—")
            notes = d.get("notes", "").replace("|", "\\|")
            lines.append(f"| `{f}` | {lv} | {vb} | {notes} |")
        lines.append("")

    # ── Architectural Decisions ────────────────────────────────────────────────
    decision_entries = [
        f for f in findings
        if f.get("entry_type") == "decision"
    ]

    if decision_entries:
        lines.append("---")
        lines.append("")
        lines.append("## Architectural Decisions")
        lines.append("")
        lines.append("WHY decisions mined from sessions, transcripts, and code audits.")
        lines.append("These are the reasons behind Nova's structural choices.")
        lines.append("")

        decision_entries.sort(key=lambda x: x.get("decision_date", x.get("date", "")))
        for d in decision_entries:
            name = d.get("decision_name", "unnamed")
            date = _fmt_date(d.get("decision_date", d.get("date", "")))
            source = d.get("source_doc", "")
            module = d.get("module", "")
            detail = d.get("detail", "")
            rationale = d.get("rationale", "")
            affects = d.get("affects", [])
            status = d.get("status", "active")

            lines.append(f"### `{name}` — {date}")
            if module:
                lines.append(f"_Modules: {module}_")
            lines.append("")
            lines.append(detail)
            lines.append("")
            if rationale:
                lines.append(f"**Rationale:** {rationale}")
                lines.append("")
            if affects:
                lines.append(f"**Affects:** {', '.join(f'`{a}`' for a in affects)}")
            if source:
                lines.append(f"**Source:** `{source}` · Status: {status}")
            lines.append("")

    # ── Nova Scan Findings ─────────────────────────────────────────────────────
    scan_findings = [
        f for f in findings
        if f.get("entry_type") not in ("doc_classification", "decision")
    ]

    if scan_findings:
        lines.append("---")
        lines.append("")
        lines.append("## Nova Scan Findings")
        lines.append("")
        lines.append("Findings written by Nova's rings, self-reflection, and execution outcomes.")
        lines.append("")

        scan_findings.sort(key=lambda x: x.get("date", ""), reverse=True)
        for sf in scan_findings:
            date = _fmt_date(sf.get("date", ""))
            module = sf.get("module", sf.get("file", ""))
            result = sf.get("result", "")
            detail = sf.get("detail", sf.get("notes", ""))
            ring = sf.get("ring")
            ring_tag = f" Ring {ring}" if ring else ""
            lines.append(f"- **{date}**{ring_tag} `{module}` — {result}: {detail}")

        lines.append("")

    # ── Drift Alerts ───────────────────────────────────────────────────────────
    stale = [d for d in doc_entries if d.get("authority_class") == "stale_snapshot"]
    # Ring-sourced drift alerts: take the most recent entry per (ring, category)
    all_drift = [d for d in findings if d.get("entry_type") == "drift_alert"]
    # Deduplicate: keep latest entry per (ring, category) key
    _seen: dict[tuple, dict] = {}
    for d in all_drift:
        key = (d.get("ring"), d.get("category") or d.get("module", ""))
        _seen[key] = d  # later entries overwrite earlier ones (JSONL order = time order)
    ring_drift = list(_seen.values())

    if stale or ring_drift:
        lines.append("---")
        lines.append("")
        lines.append("## Drift Alerts")
        lines.append("")
        if ring_drift:
            lines.append("### Ring scan gaps (latest per category)")
            lines.append("")
            for d in sorted(ring_drift, key=lambda x: (x.get("ring") or 0, x.get("category", ""))):
                ring_tag = f"Ring {d.get('ring')} " if d.get("ring") else ""
                date_tag = d.get("date", "?")
                detail = d.get("detail", "")
                lines.append(f"- **{date_tag}** {ring_tag}`{d.get('module','')}` — {detail}")
            lines.append("")
        if stale:
            lines.append("### Stale authority documents")
            lines.append("")
            for d in stale:
                lines.append(f"- `{d.get('file')}` — last verified {_fmt_date(d.get('last_verified','?'))}: {d.get('notes','')}")
            lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("_End of ledger. Append entries to the source JSONL files and regenerate to update._")
    lines.append("")

    return "\n".join(lines)


def main() -> None:
    sessions = _load_jsonl(SESSION_LOG)
    findings = _load_jsonl(NOVA_FINDINGS)
    content = render(sessions, findings)
    OUTPUT.write_text(content, encoding="utf-8")
    print(f"Written: {OUTPUT}")
    print(f"  Sessions: {len([s for s in sessions if s.get('entry_type') != 'doc_classification'])}")
    print(f"  Doc classifications: {len([f for f in findings if f.get('entry_type') == 'doc_classification'])}")
    print(f"  Architectural decisions: {len([f for f in findings if f.get('entry_type') == 'decision'])}")
    print(f"  Nova scan findings: {len([f for f in findings if f.get('entry_type') not in ('doc_classification', 'decision')])}")


if __name__ == "__main__":
    main()
