"""
nova_ledger_ingest.py
---------------------

NOVA_DOC:
  category: script
  authority: active_authority
  last_session: 2026-08-05
  last_agent: claude-cowork
  session_state: current
  next_step: none
  open: none
Nova's write path to the living ledger.
Called by Ring scans, self-reflection, execution findings, and memory hygiene.

Usage (from Nova's own processes):
    from scripts.nova_ledger_ingest import ingest_finding

    ingest_finding(
        entry_type="ring1_scan",
        module="sock_service",
        result="verified",
        detail="Evidence files present, wiring surface confirmed",
        ring=1,
    )

    ingest_finding(
        entry_type="doc_classification",
        file="docs/SOCK_SYSTEM.md",
        authority_class="stale_snapshot",
        notes="ROCm/NPU additions not yet reflected",
    )

Or run as a script to ingest from a JSON file:
    python scripts/nova_ledger_ingest.py --from-file findings.json
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Any

NOVA_ROOT = Path(__file__).parent.parent
NOVA_FINDINGS = NOVA_ROOT / "docs" / "ledger" / "nova_findings.jsonl"
GENERATE_SCRIPT = NOVA_ROOT / "scripts" / "generate_nova_ledger.py"

VALID_ENTRY_TYPES = {
    "ring1_scan",
    "ring2_scan",
    "ring3_scan",
    "doc_classification",
    "execution_finding",
    "memory_finding",
    "self_reflection",
    "drift_alert",
    "decision",  # architectural WHY decisions mined from sessions and transcripts
}

VALID_AUTHORITY_CLASSES = {
    "active_authority",
    "active_working",
    "stale_snapshot",
    "historical",
}

VALID_RESULTS = {
    "verified",
    "drifted",
    "missing",
    "unclassified",
    "caution",
}


def ingest_finding(
    *,
    entry_type: str,
    module: str = "",
    file: str = "",
    result: str = "",
    detail: str = "",
    notes: str = "",
    ring: int | None = None,
    authority_class: str = "",
    last_verified: str | None = None,
    verified_by: str = "nova",
    extra: dict[str, Any] | None = None,
    entry_date: str | None = None,
    regenerate: bool = False,
) -> dict:
    """Write one finding entry to nova_findings.jsonl."""
    if entry_type not in VALID_ENTRY_TYPES:
        raise ValueError(f"Unknown entry_type: {entry_type!r}. Valid: {sorted(VALID_ENTRY_TYPES)}")

    if authority_class and authority_class not in VALID_AUTHORITY_CLASSES:
        raise ValueError(f"Unknown authority_class: {authority_class!r}")

    entry: dict[str, Any] = {
        "date": entry_date or str(date.today()),
        "source": "nova",
        "entry_type": entry_type,
    }
    if ring is not None:
        entry["ring"] = ring
    if module:
        entry["module"] = module
    if file:
        entry["file"] = file
    if result:
        entry["result"] = result
    if detail:
        entry["detail"] = detail
    if notes:
        entry["notes"] = notes
    if authority_class:
        entry["authority_class"] = authority_class
    if last_verified:
        entry["last_verified"] = last_verified
    if verified_by:
        entry["verified_by"] = verified_by
    if extra:
        entry.update(extra)

    NOVA_FINDINGS.parent.mkdir(parents=True, exist_ok=True)
    with open(NOVA_FINDINGS, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")

    if regenerate:
        subprocess.run(
            [sys.executable, str(GENERATE_SCRIPT)],
            capture_output=True, text=True
        )

    return entry


def ingest_ring_scan(
    *,
    ring: int,
    module: str,
    result: str,
    detail: str = "",
    regenerate: bool = False,
) -> dict:
    """Convenience wrapper for Ring 1/2/3 scan entries."""
    return ingest_finding(
        entry_type=f"ring{ring}_scan",
        ring=ring,
        module=module,
        result=result,
        detail=detail,
        regenerate=regenerate,
    )


def ingest_doc_classification(
    *,
    file: str,
    authority_class: str,
    notes: str = "",
    last_verified: str | None = None,
    regenerate: bool = False,
) -> dict:
    """Convenience wrapper for doc classification updates."""
    return ingest_finding(
        entry_type="doc_classification",
        file=file,
        authority_class=authority_class,
        notes=notes,
        last_verified=last_verified or str(date.today()),
        verified_by="nova",
        regenerate=regenerate,
    )


def ingest_scan_rings_result(
    rings_result: dict,
    *,
    regenerate: bool = False,
) -> list[dict]:
    """
    Write one ledger entry per ring from a run_self_scan_rings() result dict.

    Called by autonomy_maintenance.py after every maintenance cycle that runs
    the ring scans. Does not regenerate the ledger by default — the caller
    controls whether to regenerate after the full cycle.

    Returns a list of the entries written (one per ring present in the result).
    """
    rings = (rings_result or {}).get("rings") or {}
    entries: list[dict] = []

    ring_map = {
        "1_map_integrity":    (1, "map_integrity"),
        "2_contract_integrity": (2, "contract_integrity"),
        "3_climb_integrity":  (3, "climb_integrity"),
    }

    for key, (ring_num, name) in ring_map.items():
        ring_data = rings.get(key) or {}
        if not ring_data:
            continue

        ok = bool(ring_data.get("ok"))
        gap_count = int(ring_data.get("gap_count") or 0)
        result_val = "verified" if ok else ("drifted" if gap_count > 0 else "caution")

        # Build a concise detail string from findings
        findings = ring_data.get("findings") or {}
        detail_parts: list[str] = [f"gap_count={gap_count}"]
        if ring_num == 1:
            uw = len(findings.get("unwired_roots") or [])
            me = len(findings.get("missing_evidence_roots") or [])
            us = len(findings.get("unclassified_source_files") or [])
            dc = findings.get("nova_doc_coverage") or {}
            undeclared = dc.get("undeclared_count", 0)
            stale_doc = dc.get("stale_count", 0)
            if uw:
                detail_parts.append(f"unwired_roots={uw}")
            if me:
                detail_parts.append(f"missing_evidence={me}")
            if us:
                detail_parts.append(f"unclassified_files={us}")
            if undeclared:
                detail_parts.append(f"undeclared_docs={undeclared}")
            if stale_doc:
                detail_parts.append(f"stale_docs={stale_doc}")
        elif ring_num == 2:
            wgc = findings.get("wiring_gap_count", 0)
            cgc = findings.get("closure_gap_count", 0)
            pgc = findings.get("probe_gap_count", 0)
            probe_ctx = ring_data.get("probe_context", "")
            detail_parts.append(f"probe_context={probe_ctx}")
            if wgc:
                detail_parts.append(f"wiring_gaps={wgc}")
            if cgc:
                detail_parts.append(f"closure_gaps={cgc}")
            if pgc:
                detail_parts.append(f"probe_gaps={pgc}")
        elif ring_num == 3:
            climbable = ring_data.get("climbable_count", 0)
            unclimbable = ring_data.get("unclimbable_count", 0)
            queue = ring_data.get("queue_count", 0)
            detail_parts.append(f"queue={queue} climbable={climbable} unclimbable={unclimbable}")

        entry = ingest_finding(
            entry_type=f"ring{ring_num}_scan",
            ring=ring_num,
            module=name,
            result=result_val,
            detail=", ".join(detail_parts),
            regenerate=False,
        )
        entries.append(entry)

    if regenerate and entries:
        import subprocess, sys as _sys
        subprocess.run(
            [_sys.executable, str(GENERATE_SCRIPT)],
            capture_output=True, text=True,
        )

    return entries


def emit_drift_alerts_from_ring_result(
    rings_result: dict,
    *,
    regenerate: bool = False,
) -> list[dict]:
    """
    Emit drift_alert ledger entries for every gap category found in ring scan results.

    Called alongside ingest_scan_rings_result() so the "Drift Alerts" ledger
    section reflects current ring state.  Emits one entry per non-zero gap
    category (not one per file) — the detail string carries the count.

    Returns the list of entries written (empty when all rings are clean).
    """
    rings = (rings_result or {}).get("rings") or {}
    entries: list[dict] = []
    today = str(date.today())

    # ── Ring 1: map integrity ─────────────────────────────────────────────────
    r1 = rings.get("1_map_integrity") or {}
    findings1 = r1.get("findings") or {}

    uw = len(findings1.get("unwired_roots") or [])
    me = len(findings1.get("missing_evidence_roots") or [])
    us = len(findings1.get("unclassified_source_files") or [])
    dc = findings1.get("nova_doc_coverage") or {}
    undeclared = int(dc.get("undeclared_count") or 0)
    stale_doc = int(dc.get("stale_count") or 0)

    if uw:
        entries.append(ingest_finding(
            entry_type="drift_alert", ring=1,
            module="nova_root_inventory",
            result="drifted",
            detail=f"{uw} source root(s) not wired in nova_root_inventory.py",
            extra={"category": "unwired_roots", "count": uw},
            entry_date=today, regenerate=False,
        ))
    if me:
        entries.append(ingest_finding(
            entry_type="drift_alert", ring=1,
            module="nova_root_inventory",
            result="drifted",
            detail=f"{me} source root(s) missing evidence file",
            extra={"category": "missing_evidence_roots", "count": me},
            entry_date=today, regenerate=False,
        ))
    if us:
        entries.append(ingest_finding(
            entry_type="drift_alert", ring=1,
            module="nova_root_inventory",
            result="drifted",
            detail=f"{us} source file(s) have no SOURCE_ROOT classification",
            extra={"category": "unclassified_source_files", "count": us},
            entry_date=today, regenerate=False,
        ))
    if undeclared:
        entries.append(ingest_finding(
            entry_type="drift_alert", ring=1,
            module="nova_doc_coverage",
            result="drifted",
            detail=f"{undeclared} doc(s) in docs/ missing NOVA_DOC header block",
            extra={"category": "undeclared_docs", "count": undeclared},
            entry_date=today, regenerate=False,
        ))
    if stale_doc:
        entries.append(ingest_finding(
            entry_type="drift_alert", ring=1,
            module="nova_doc_coverage",
            result="drifted",
            detail=f"{stale_doc} doc(s) have stale NOVA_DOC block (last_session > 30 days)",
            extra={"category": "stale_docs", "count": stale_doc},
            entry_date=today, regenerate=False,
        ))

    # ── Ring 2: contract integrity ─────────────────────────────────────────────
    r2 = rings.get("2_contract_integrity") or {}
    findings2 = r2.get("findings") or {}
    probe_ctx = r2.get("probe_context", "")

    wgc = int(findings2.get("wiring_gap_count") or 0)
    cgc = int(findings2.get("closure_gap_count") or 0)
    pgc = int(findings2.get("probe_gap_count") or 0)

    if wgc:
        entries.append(ingest_finding(
            entry_type="drift_alert", ring=2,
            module="ring2_contract_integrity",
            result="drifted",
            detail=f"{wgc} wiring gap(s): service/script registered but not surfaced in status",
            extra={"category": "wiring_gaps", "count": wgc},
            entry_date=today, regenerate=False,
        ))
    if cgc:
        entries.append(ingest_finding(
            entry_type="drift_alert", ring=2,
            module="ring2_contract_integrity",
            result="drifted",
            detail=f"{cgc} closure gap(s): work-tree tracks open but no resolution evidence",
            extra={"category": "closure_gaps", "count": cgc},
            entry_date=today, regenerate=False,
        ))
    if pgc:
        ctx_note = f" ({probe_ctx})" if probe_ctx else ""
        entries.append(ingest_finding(
            entry_type="drift_alert", ring=2,
            module="ring2_contract_integrity",
            result="drifted",
            detail=f"{pgc} contract probe gap(s){ctx_note}: services lack HTTP-reachable health probe",
            extra={"category": "probe_gaps", "count": pgc, "probe_context": probe_ctx},
            entry_date=today, regenerate=False,
        ))

    if regenerate and entries:
        import subprocess, sys as _sys
        subprocess.run(
            [_sys.executable, str(GENERATE_SCRIPT)],
            capture_output=True, text=True,
        )

    return entries


def ingest_from_file(path: Path, regenerate: bool = True) -> list[dict]:
    """Ingest multiple findings from a JSON file (list of dicts)."""
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    if not isinstance(raw, list):
        raw = [raw]
    results = []
    for item in raw:
        results.append(ingest_finding(**item, regenerate=False))
    if regenerate:
        subprocess.run(
            [sys.executable, str(GENERATE_SCRIPT)],
            capture_output=True, text=True
        )
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest Nova findings into the living ledger")
    parser.add_argument("--from-file", help="JSON file with list of finding dicts")
    parser.add_argument("--entry-type", help="Finding entry type")
    parser.add_argument("--module", default="")
    parser.add_argument("--file", default="")
    parser.add_argument("--result", default="")
    parser.add_argument("--detail", default="")
    parser.add_argument("--notes", default="")
    parser.add_argument("--ring", type=int, default=None)
    parser.add_argument("--authority-class", default="")
    parser.add_argument("--regenerate", action="store_true")
    args = parser.parse_args()

    if args.from_file:
        entries = ingest_from_file(Path(args.from_file), regenerate=args.regenerate)
        print(f"Ingested {len(entries)} findings from {args.from_file}")
    elif args.entry_type:
        entry = ingest_finding(
            entry_type=args.entry_type,
            module=args.module,
            file=args.file,
            result=args.result,
            detail=args.detail,
            notes=args.notes,
            ring=args.ring,
            authority_class=args.authority_class,
            regenerate=args.regenerate,
        )
        print(f"Ingested: {json.dumps(entry, indent=2)}")
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
