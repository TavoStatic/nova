from __future__ import annotations

import argparse
import json
import re
import time
from dataclasses import asdict
from pathlib import Path

from nova_safety_envelope import evaluate_generated_definitions
from subconscious_live_simulator import (
    TrainingPriorityItem,
    build_default_live_scenario_families,
    build_training_priorities,
    simulate_live_families,
)


ROOT = Path(__file__).resolve().parent
RUNTIME_ROOT = ROOT / "runtime" / "subconscious_runs"
GENERATED_DEFINITIONS_ROOT = ROOT / "runtime" / "test_sessions" / "generated_definitions"


def select_live_scenario_families(family_ids: list[str] | None = None) -> list[object]:
    families = list(build_default_live_scenario_families())
    if not family_ids:
        return families

    requested = [str(item or "").strip() for item in family_ids if str(item or "").strip()]
    if not requested:
        return families

    by_id = {str(getattr(family, "family_id", "")).strip(): family for family in families}
    missing = [family_id for family_id in requested if family_id not in by_id]
    if missing:
        available = ", ".join(sorted(by_id.keys()))
        raise ValueError(f"Unknown family ids: {', '.join(missing)}. Available: {available}")
    return [by_id[family_id] for family_id in requested]


def _priority_to_dict(item: TrainingPriorityItem) -> dict:
    return asdict(item)


def _family_result_to_dict(result: object) -> dict:
    priorities = [_priority_to_dict(item) for item in build_training_priorities(result)]
    variation_results = []
    for variation in list(getattr(result, "variation_results", []) or []):
        snapshot = getattr(variation, "subconscious_snapshot", {})
        backlog = getattr(variation, "training_backlog", {})
        variation_results.append(
            {
                "scenario_id": str(getattr(variation, "scenario_id", "") or "").strip(),
                "variation_id": str(getattr(variation, "variation_id", "") or "").strip(),
                "active_recent_signals": list(snapshot.get("active_recent_signals") or []),
                "replan_requested": bool(snapshot.get("replan_requested")),
                "candidate_tests": list(backlog.get("candidate_tests") or []) if isinstance(backlog, dict) else [],
            }
        )

    return {
        "family_id": str(getattr(result, "family_id", "") or "").strip(),
        "target_seam": str(getattr(result, "target_seam", "") or "").strip(),
        "variation_count": len(list(getattr(result, "variation_results", []) or [])),
        "noise_summary": dict(getattr(result, "noise_summary", {}) or {}),
        "repeated_signals": list(getattr(result, "repeated_signals", []) or []),
        "robust_signals": list(getattr(result, "robust_signals", []) or []),
        "script_specific_signals": list(getattr(result, "script_specific_signals", []) or []),
        "robust_backlog_candidates": list(getattr(result, "robust_backlog_candidates", []) or []),
        "quiet_control_verdict": dict(getattr(result, "quiet_control_verdict", {}) or {}),
        "training_priorities": priorities,
        "variation_results": variation_results,
    }


def build_unattended_report(family_results: list[object], *, label: str = "default") -> dict:
    families = [_family_result_to_dict(result) for result in list(family_results or [])]
    totals = {
        "family_count": len(families),
        "variation_count": sum(int(item.get("variation_count", 0) or 0) for item in families),
        "quiet_variations": sum(int((item.get("noise_summary") or {}).get("quiet_variations", 0) or 0) for item in families),
        "noisy_variations": sum(int((item.get("noise_summary") or {}).get("noisy_variations", 0) or 0) for item in families),
        "useful_variations": sum(int((item.get("noise_summary") or {}).get("useful_variations", 0) or 0) for item in families),
        "robust_signal_count": sum(len(list(item.get("robust_signals") or [])) for item in families),
        "script_specific_signal_count": sum(len(list(item.get("script_specific_signals") or [])) for item in families),
        "training_priority_count": sum(len(list(item.get("training_priorities") or [])) for item in families),
    }
    return {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "label": str(label or "default").strip() or "default",
        "totals": totals,
        "families": families,
    }


def render_markdown_summary(report: dict) -> str:
    totals = dict(report.get("totals") or {})
    lines = [
        "# Subconscious Batch Summary",
        "",
        f"Generated: {report.get('generated_at', '')}",
        f"Label: {report.get('label', 'default')}",
        "",
        "## Totals",
        "",
        f"- Families: {totals.get('family_count', 0)}",
        f"- Variations: {totals.get('variation_count', 0)}",
        f"- Useful variations: {totals.get('useful_variations', 0)}",
        f"- Quiet variations: {totals.get('quiet_variations', 0)}",
        f"- Noisy variations: {totals.get('noisy_variations', 0)}",
        f"- Robust signals: {totals.get('robust_signal_count', 0)}",
        f"- Script-specific signals: {totals.get('script_specific_signal_count', 0)}",
        f"- Training priorities: {totals.get('training_priority_count', 0)}",
        "",
    ]

    for family in list(report.get("families") or []):
        family_id = str(family.get("family_id") or "family").strip() or "family"
        lines.extend(
            [
                f"## {family_id}",
                "",
                f"Target seam: {family.get('target_seam', '')}",
                f"Variations: {family.get('variation_count', 0)}",
                f"Quiet control: {bool((family.get('quiet_control_verdict') or {}).get('quiet_control'))}",
                "",
            ]
        )
        robust_signals = list(family.get("robust_signals") or [])
        if robust_signals:
            lines.append("Robust signals:")
            for item in robust_signals:
                lines.append(
                    f"- {item.get('signal', '')}: score={item.get('robustness_score', 0.0)} hit_ratio={item.get('variation_hit_ratio', 0.0)}"
                )
            lines.append("")

        priorities = list(family.get("training_priorities") or [])
        if priorities:
            lines.append("Training priorities:")
            for item in priorities:
                lines.append(
                    f"- {item.get('signal', '')} -> {item.get('suggested_test_name', '')} [{item.get('urgency', '')}]"
                )
            lines.append("")

        if not robust_signals and not priorities:
            lines.extend(["No robust cracks surfaced in this family.", ""])

    return "\n".join(lines).strip() + "\n"


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(text or "").lower()).strip("-")
    return slug or "default"


def _session_definition_filename(family_id: str, variation_id: str) -> str:
    return f"subconscious_{_slugify(family_id)}_{_slugify(variation_id)}.json"


def build_generated_session_definitions(report: dict) -> list[dict]:
    source_families = {
        str(getattr(family, "family_id", "") or "").strip(): family
        for family in build_default_live_scenario_families()
    }
    generated: list[dict] = []
    for family_payload in list(report.get("families") or []):
        family_id = str(family_payload.get("family_id") or "").strip()
        training_priorities = list(family_payload.get("training_priorities") or [])
        if not family_id or not training_priorities:
            continue
        source_family = source_families.get(family_id)
        if source_family is None:
            continue
        for scenario in list(getattr(source_family, "scenarios", []) or []):
            messages = [
                str(getattr(turn, "user_text", "") or "").strip()
                for turn in list(getattr(scenario, "turns", []) or [])
                if str(getattr(turn, "user_text", "") or "").strip()
            ]
            if not messages:
                continue
            variation_id = str(getattr(scenario, "variation_id", "baseline") or "baseline")
            generated.append(
                {
                    "file": _session_definition_filename(family_id, variation_id),
                    "payload": {
                        "name": f"Subconscious {family_id} :: {variation_id}",
                        "messages": messages,
                        "source": "subconscious_generated",
                        "label": str(report.get("label") or "default"),
                        "family_id": family_id,
                        "target_seam": str(family_payload.get("target_seam") or ""),
                        "variation_id": variation_id,
                        "training_priorities": training_priorities,
                    },
                }
            )
    return generated


def write_generated_session_definitions(report: dict, *, output_root: Path = GENERATED_DEFINITIONS_ROOT) -> dict:
    generated = build_generated_session_definitions(report)
    output_root.mkdir(parents=True, exist_ok=True)
    files: list[str] = []
    for item in generated:
        path = output_root / str(item.get("file") or "session.json")
        payload = dict(item.get("payload") or {})
        path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
        files.append(str(path))

    manifest = {
        "generated_at": str(report.get("generated_at") or ""),
        "label": str(report.get("label") or "default"),
        "definition_count": len(files),
        "files": files,
    }
    manifest_payload = json.dumps(manifest, ensure_ascii=True, indent=2)
    manifest_path = output_root / "generated_manifest.json"
    latest_manifest_path = output_root / "latest_manifest.json"
    manifest_path.write_text(manifest_payload, encoding="utf-8")
    latest_manifest_path.write_text(manifest_payload, encoding="utf-8")
    return {
        "definition_count": len(files),
        "files": files,
        "manifest": str(manifest_path),
        "latest_manifest": str(latest_manifest_path),
    }


def write_report_bundle(report: dict, *, output_root: Path = RUNTIME_ROOT, stamp: str | None = None) -> dict:
    effective_stamp = str(stamp or time.strftime("%Y%m%d_%H%M%S")).strip()
    label = _slugify(str(report.get("label") or "default"))
    run_dir = output_root / f"{effective_stamp}_{label}"
    run_dir.mkdir(parents=True, exist_ok=True)

    json_path = run_dir / "report.json"
    markdown_path = run_dir / "summary.md"
    latest_json = output_root / "latest.json"
    latest_markdown = output_root / "latest.md"

    payload = json.dumps(report, ensure_ascii=True, indent=2)
    summary = render_markdown_summary(report)

    json_path.write_text(payload, encoding="utf-8")
    markdown_path.write_text(summary, encoding="utf-8")
    output_root.mkdir(parents=True, exist_ok=True)
    latest_json.write_text(payload, encoding="utf-8")
    latest_markdown.write_text(summary, encoding="utf-8")

    return {
        "run_dir": str(run_dir),
        "report_json": str(json_path),
        "summary_markdown": str(markdown_path),
        "latest_json": str(latest_json),
        "latest_markdown": str(latest_markdown),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run unattended subconscious scenario families and write report artifacts.")
    parser.add_argument("--output-dir", default=str(RUNTIME_ROOT), help="Directory where run artifacts should be written")
    parser.add_argument(
        "--generated-output-dir",
        default=str(GENERATED_DEFINITIONS_ROOT),
        help="Directory where generated test session definitions should be written",
    )
    parser.add_argument("--label", default="default", help="Label used in the report and output folder")
    parser.add_argument("--family", action="append", default=[], help="Specific family id to run; may be repeated")
    args = parser.parse_args(argv)

    try:
        families = select_live_scenario_families(list(args.family or []))
    except ValueError as exc:
        print(str(exc))
        return 2

    results = simulate_live_families(families)
    report = build_unattended_report(results, label=args.label)
    paths = write_report_bundle(report, output_root=Path(str(args.output_dir)))
    generated = write_generated_session_definitions(report, output_root=Path(str(args.generated_output_dir)))
    safety_summary = evaluate_generated_definitions(generated.get("files") or [])

    totals = report.get("totals") or {}
    print(f"Subconscious batch complete: label={report.get('label', 'default')}")
    print(f"Families: {totals.get('family_count', 0)} | Variations: {totals.get('variation_count', 0)} | Training priorities: {totals.get('training_priority_count', 0)}")
    print(f"Generated session definitions: {generated['definition_count']}")
    print(
        "Safety envelope: "
        f"evaluated={safety_summary.get('evaluated_count', 0)} "
        f"observed={safety_summary.get('observed_count', 0)} "
        f"pending_review={safety_summary.get('pending_review_count', 0)} "
        f"promoted={safety_summary.get('promoted_count', 0)} "
        f"quarantined={safety_summary.get('quarantined_count', 0)}"
    )
    print(f"Report JSON: {paths['report_json']}")
    print(f"Summary MD: {paths['summary_markdown']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())