from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from pipelines.registry import PipelineRegistry


def _repo_root(root: Path | None = None) -> Path:
    return (root or Path(__file__).resolve().parents[1]).resolve()


def _clean_text(value: object) -> str:
    return str(value or "").strip()


def _target_module_name(target: str, *, root: Path) -> str:
    text = _clean_text(target).split("::", 1)[0]
    if not text.startswith("tests."):
        return text

    parts = text.split(".")
    for end in range(len(parts), 1, -1):
        candidate = root / Path(*parts[:end]).with_suffix(".py")
        if candidate.exists():
            return ".".join(parts[:end])
    return text


def _module_name_for_path(path: Path, *, root: Path) -> str:
    relative = path.resolve().relative_to(root)
    return ".".join(relative.with_suffix("").parts)


def _discover_test_files(root: Path) -> list[Path]:
    tests_root = root / "tests"
    if not tests_root.exists():
        return []
    rows: list[Path] = []
    for path in tests_root.rglob("test_*.py"):
        if "__pycache__" in path.parts:
            continue
        rows.append(path.resolve())
    rows.sort(key=lambda item: item.relative_to(root).as_posix())
    return rows


def _active_pipeline_ids(root: Path) -> list[str]:
    try:
        return sorted(str(item.pipeline_id or "").strip() for item in PipelineRegistry(root / "data_sources").discover(refresh=True) if str(item.pipeline_id or "").strip())
    except Exception:
        return []


def _missing_install_lanes(path: Path, text: str, active_pipeline_ids: set[str]) -> list[str]:
    if path.name.lower().startswith("test_edfi"):
        return ["edfi_core"]
    normalized = text.replace("'", '"')
    uses_repo_data_sources = 'parents[1] / "data_sources"' in normalized or 'PipelineRegistry(Path(__file__).resolve().parents[1] / "data_sources")' in normalized
    imports_archived_connector = "data_sources.sis_test" in normalized
    requires_sis_test = '"sis_test"' in normalized and (uses_repo_data_sources or imports_archived_connector or "includes_sis_test" in normalized)
    if requires_sis_test and "sis_test" not in active_pipeline_ids:
        return ["sis_test"]
    return []


def _is_removed_install_surface(path: Path) -> bool:
    return path.name.lower().startswith("test_edfi")


def _optional_inactive_install_lanes(text: str, missing_lanes: list[str]) -> list[str]:
    normalized = text.replace("'", '"').lower()
    optional_markers = (
        "install_profile_inactive_behavior",
        "skip_when_absent",
        "skipunless",
        "not active in this install",
    )
    if not all(marker in normalized for marker in ("sis_test",)):
        return []
    if not any(marker in normalized for marker in optional_markers):
        return []
    return [lane for lane in missing_lanes if lane == "sis_test"]


def _surface_hint(path: Path) -> str:
    name = path.name.lower()
    text = path.as_posix().lower()
    if "pipeline" in text or "sis" in text:
        return "data_pipelines"
    if "work_tree" in text:
        return "work_tree"
    if "runtime" in text or "guard" in text:
        return "runtime_core"
    if "http" in text:
        return "http_api_control"
    if "voice" in text:
        return "voice"
    if "ollama" in text:
        return "model_runtime"
    if "memory" in text or "identity" in text:
        return "memory_identity"
    if "release" in text or "package" in text or "installer" in text:
        return "release"
    if "subconscious" in text:
        return "subconscious"
    if "patch" in text:
        return "patch_pipeline"
    if "policy" in text:
        return "policy_gates"
    if "web" in text or "search" in text or "research" in text:
        return "web_search"
    if "tool" in text:
        return "tool_registry_policy"
    if "reply" in text or "truth" in text or "fallback" in text:
        return "reply_quality_contracts"
    if name in {"test_run_regression.py", "test_test_session_control_service.py"}:
        return "test_ecosystem"
    return "test_ecosystem"


def build_regression_profile_inventory_payload(
    *,
    root: Path | None = None,
    test_lanes: Mapping[str, list[str]] | None = None,
) -> dict[str, Any]:
    repo_root = _repo_root(root)
    lanes = dict(test_lanes or {})
    active_ids = set(_active_pipeline_ids(repo_root))
    curated_modules: dict[str, list[str]] = {}
    curated_target_count = 0
    for lane, targets in lanes.items():
        for target in list(targets or []):
            curated_target_count += 1
            module_name = _target_module_name(str(target), root=repo_root)
            curated_modules.setdefault(module_name, []).append(str(lane))

    tests_root = repo_root / "tests"
    rows: list[dict[str, Any]] = []
    counts: dict[str, int] = {
        "curated": 0,
        "source_observed": 0,
        "install_profile_inactive": 0,
        "install_profile_optional_inactive": 0,
        "removed_install_surface": 0,
        "authoritative_behavior": 0,
        "legacy_excluded": 0,
        "runtime_live": 0,
        "unclassified": 0,
    }
    root_test_file_count = 0
    for path in _discover_test_files(repo_root):
        relative = path.relative_to(repo_root).as_posix()
        module_name = _module_name_for_path(path, root=repo_root)
        if path.parent == tests_root:
            root_test_file_count += 1

        try:
            text = path.read_text(encoding="utf-8-sig")
        except Exception:
            text = ""
        missing_lanes = _missing_install_lanes(path, text, active_ids)
        optional_inactive_lanes = _optional_inactive_install_lanes(text, missing_lanes)

        if module_name in curated_modules:
            profile_class = "curated"
        elif _is_removed_install_surface(path):
            profile_class = "removed_install_surface"
        elif missing_lanes and sorted(optional_inactive_lanes) == sorted(missing_lanes):
            profile_class = "install_profile_optional_inactive"
        elif missing_lanes:
            profile_class = "install_profile_inactive"
        elif "/legacy/" in f"/{relative}":
            profile_class = "legacy_excluded"
        elif "/runtime/" in f"/{relative}":
            profile_class = "runtime_live"
        elif "/authoritative/" in f"/{relative}":
            profile_class = "authoritative_behavior"
        else:
            profile_class = "source_observed"

        counts[profile_class] = counts.get(profile_class, 0) + 1
        rows.append({
            "path": relative,
            "module": module_name,
            "profile_class": profile_class,
            "lanes": curated_modules.get(module_name, []),
            "surface_hint": _surface_hint(path),
            "missing_install_lanes": missing_lanes,
            "optional_inactive_install_lanes": optional_inactive_lanes,
        })

    source_observed = counts.get("source_observed", 0)
    install_profile_inactive = counts.get("install_profile_inactive", 0)
    install_profile_optional_inactive = counts.get("install_profile_optional_inactive", 0)
    unclassified = counts.get("unclassified", 0)
    profile_gap_count = install_profile_inactive + unclassified
    profile_drift_count = source_observed + profile_gap_count
    profile_attention_count = (
        source_observed
        + install_profile_inactive
        + install_profile_optional_inactive
        + unclassified
    )
    gap_tests = [
        row for row in rows
        if row.get("profile_class") in {"install_profile_inactive", "unclassified"}
    ]
    profile_drift_tests = [
        row for row in rows
        if row.get("profile_class") in {"source_observed", "install_profile_inactive", "unclassified"}
    ]
    attention_tests = [
        row for row in rows
        if row.get("profile_class") in {
            "source_observed",
            "install_profile_inactive",
            "install_profile_optional_inactive",
            "unclassified",
        }
    ]

    return {
        "schema": "nova.regression_profile_inventory.v1",
        "ok": profile_drift_count == 0,
        "root": str(repo_root),
        "active_pipeline_ids": sorted(active_ids),
        "lane_count": len(lanes),
        "lane_counts": {str(lane): len(list(targets or [])) for lane, targets in lanes.items()},
        "curated_target_count": curated_target_count,
        "curated_test_file_count": counts.get("curated", 0),
        "root_test_file_count": root_test_file_count,
        "all_test_file_count": len(rows),
        "source_observed_count": source_observed,
        "outside_curated_count": source_observed,
        "install_profile_inactive_count": install_profile_inactive,
        "install_profile_optional_inactive_count": install_profile_optional_inactive,
        "unclassified_count": unclassified,
        "profile_gap_count": profile_gap_count,
        "profile_drift_count": profile_drift_count,
        "profile_attention_count": profile_attention_count,
        "counts": counts,
        "gap_tests": gap_tests[:80],
        "profile_drift_tests": profile_drift_tests[:80],
        "attention_tests": attention_tests[:80],
        "tests": rows,
        "rationale": (
            "The compact regression lanes are only one validation profile. "
            "Nova must distinguish compact-lane tests, source-observed tests outside compact regression, "
            "and tests tied to inactive install lanes. Source-observed tests are living source truth "
            "that still needs a validation-profile decision."
        ),
    }


REGRESSION_PROFILE_INVENTORY_SERVICE = build_regression_profile_inventory_payload
