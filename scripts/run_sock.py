#!/usr/bin/env python3
"""SOCK — System Optimization and Compatibility Check.

Usage:
  nova sock                  # scan and report
  nova sock --apply          # scan, report, and write recommended policy.json
  nova sock --json           # machine-readable JSON output
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.sock_service import (
    PolicyDiff,
    SockReport,
    run_sock,
)

STATUS_OK     = "[OK]  "
STATUS_UP     = "[UP]  "
STATUS_WARN   = "[WARN]"
STATUS_CHANGE = "[>>>>]"
STATUS_PULL   = "[PULL]"


def _bar(label: str, value: str, width: int = 16) -> str:
    return f"  {label:<{width}}: {value}"


def _model_line(role: str, current: str, recommended: str, changed: bool, rationale: str) -> str:
    tag = STATUS_CHANGE if changed else STATUS_OK
    arrow = f"  {current}  ->  {recommended}" if changed else f"  {current}"
    note = f"\n              ({rationale})" if changed else ""
    return f"  {tag} {role:<10}{arrow}{note}"


def format_report(report: SockReport) -> str:
    hw = report.hardware
    rec = report.recommendation
    diff = report.diff
    ollama = report.ollama
    lines: list[str] = []

    lines.append("")
    lines.append("=" * 62)
    lines.append("  SOCK — System Optimization and Compatibility Check")
    lines.append("=" * 62)

    # Hardware
    lines.append("")
    lines.append("  Hardware Profile")
    lines.append("  " + "-" * 40)
    lines.append(_bar("CPU", hw.cpu_name[:52] if hw.cpu_name else "unknown"))
    lines.append(_bar("Cores", str(hw.cpu_cores)))
    lines.append(_bar("RAM", f"{hw.ram_gb:.1f} GB"))
    if hw.gpu_name:
        lines.append(_bar("GPU", f"{hw.gpu_name} ({hw.vram_gb:.1f} GB VRAM)"))
    else:
        lines.append(_bar("GPU", "none detected"))
    if hw.npu_detected:
        lines.append(_bar("NPU", f"{hw.npu_name}  [future optimization candidate]"))
    lines.append(_bar("Storage free", f"{hw.storage_free_gb:.1f} GB"))

    # Ollama
    lines.append("")
    lines.append("  Ollama")
    lines.append("  " + "-" * 40)
    if ollama.reachable:
        lines.append(f"  {STATUS_OK} API reachable")
        if ollama.pulled:
            lines.append(_bar("Pulled", ", ".join(ollama.pulled)))
        else:
            lines.append(f"  {STATUS_WARN} No models pulled yet")
        if ollama.missing:
            for m in ollama.missing:
                lines.append(f"  {STATUS_PULL} {m}  (not pulled — run: ollama pull {m})")
        else:
            lines.append(f"  {STATUS_OK} All recommended models already pulled")
    else:
        lines.append(f"  {STATUS_WARN} Ollama not reachable — model pull status unknown")

    # Models
    lines.append("")
    lines.append("  Model Recommendations")
    lines.append("  " + "-" * 40)
    for role in ("chat", "routing", "vision", "stt_size"):
        current = diff.current.get(role, "")
        recommended = diff.recommended.get(role, "")
        changed = role in diff.changed_keys
        rationale = rec.rationale.get(role, "")
        lines.append(_model_line(role, current or "(unset)", recommended, changed, rationale))

    # Summary
    lines.append("")
    if diff.changed_keys:
        lines.append(f"  {STATUS_CHANGE} {len(diff.changed_keys)} model(s) can be upgraded for this hardware.")
        if not report.applied:
            lines.append("  Run 'nova sock --apply' to write the recommended policy.json.")
            if ollama.missing:
                lines.append("  Pull missing models first:")
                for m in ollama.missing:
                    lines.append(f"    ollama pull {m}")
    else:
        lines.append(f"  {STATUS_OK} Policy is already optimal for this hardware.")

    if report.applied:
        lines.append(f"  {STATUS_OK} policy.json updated. Backup saved as policy.json.sock_backup.")
        lines.append("  Restart Nova for changes to take effect.")

    for err in report.errors:
        lines.append(f"  {STATUS_WARN} {err}")

    lines.append("")
    return "\n".join(lines)


def _format_warm_validation(report: SockReport) -> str:
    if not report.warm_validation:
        return ""
    lines: list[str] = []
    lines.append("")
    lines.append("  Warm Validation")
    lines.append("  " + "-" * 40)
    labels = ["routing (cold)", "chat (while routing resident)", "routing (re-warm after chat)"]
    for result, label in zip(report.warm_validation, labels):
        elapsed = f"{result.elapsed_ms / 1000:.1f}s"
        if result.ok:
            tag = STATUS_OK
            detail = elapsed
        else:
            tag = STATUS_WARN
            detail = f"{elapsed}  error: {result.error}" if result.error else elapsed
        lines.append(f"  {tag} {label:<38} {detail}")
    if report.validation_ok:
        lines.append(f"  {STATUS_OK} Pair validated — routing re-warms within budget after chat load.")
    else:
        lines.append(f"  {STATUS_WARN} Validation FAILED — routing warm exceeded threshold after chat load.")
        lines.append("  This pair will cause intermittent latency on first interactive turns.")
        lines.append("  Run 'nova sock' (without --apply) to review the recommended safe pair.")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="nova sock",
        description="SOCK — System Optimization and Compatibility Check",
    )
    parser.add_argument("--apply", action="store_true", help="Write recommended policy.json")
    parser.add_argument(
        "--validate",
        action="store_true",
        default=False,
        help="Probe both models for concurrent warm latency before applying",
    )
    parser.add_argument("--json", action="store_true", dest="as_json", help="JSON output")
    args = parser.parse_args()

    report = run_sock(apply=args.apply, validate=args.validate)

    if args.as_json:
        import dataclasses
        print(json.dumps(dataclasses.asdict(report), indent=2))
        return 0

    print(format_report(report))
    warm_section = _format_warm_validation(report)
    if warm_section:
        print(warm_section)

    # Exit 1 if upgrades available but not applied, or validation failed
    if (report.diff.changed_keys and not report.applied) or not report.validation_ok:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
