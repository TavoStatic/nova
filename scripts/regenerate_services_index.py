"""
regenerate_services_index.py
----------------------------
Regenerates docs/SERVICES_INDEX.md from the actual services/ directory.

For each .py file in services/ (including subdirectories), extracts:
- Line count
- Module-level docstring (first paragraph)
- Top-level class and function names
- Service singleton name (pattern: *_SERVICE or NOVA_*_DISPATCHER or SCHEDULE_REGISTRY)

Usage:
    python scripts/regenerate_services_index.py
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

NOVA_ROOT = Path(__file__).parent.parent
SERVICES_DIR = NOVA_ROOT / "services"
OUTPUT = NOVA_ROOT / "docs" / "SERVICES_INDEX.md"

# Files to skip (contracts, stubs, empty)
SKIP_IF_EMPTY = True
MIN_LINES = 3


def _module_docstring(tree: ast.Module) -> str:
    """Extract and clean first paragraph of module docstring."""
    ds = ast.get_docstring(tree)
    if not ds:
        return ""
    first = ds.split("\n\n")[0].strip().replace("\n", " ")
    return first[:200] + ("…" if len(first) > 200 else "")


def _public_names(tree: ast.Module) -> list[str]:
    """Top-level class and function names (no leading underscore)."""
    names = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if not node.name.startswith("_"):
                names.append(node.name)
    return names


def _singleton(source: str) -> str:
    """Look for singleton assignment patterns like FOO_SERVICE = FooService()."""
    patterns = [
        r"^([A-Z][A-Z0-9_]*_SERVICE)\s*[:=]",
        r"^([A-Z][A-Z0-9_]*_DISPATCHER)\s*[:=]",
        r"^(SCHEDULE_REGISTRY)\s*[:=]",
        r"^(NOVA_[A-Z0-9_]+)\s*=\s*\w+\(",
    ]
    for pat in patterns:
        m = re.search(pat, source, re.MULTILINE)
        if m:
            return m.group(1)
    return ""


def scan_services() -> list[dict]:
    entries = []
    for path in sorted(SERVICES_DIR.rglob("*.py")):
        rel = path.relative_to(NOVA_ROOT).as_posix()
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        line_count = len(lines)
        if SKIP_IF_EMPTY and line_count < MIN_LINES:
            continue
        source = "\n".join(lines)
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError:
            entries.append({
                "rel": rel,
                "lines": line_count,
                "docstring": "(syntax error — could not parse)",
                "public": [],
                "singleton": "",
            })
            continue
        entries.append({
            "rel": rel,
            "lines": line_count,
            "docstring": _module_docstring(tree),
            "public": _public_names(tree),
            "singleton": _singleton(source),
        })
    return entries


def group_entries(entries: list[dict]) -> dict[str, list[dict]]:
    """Group by subsystem prefix."""
    groups: dict[str, list[dict]] = {}
    order = [
        ("services/backpack_host/", "Backpack Host"),
        ("services/edfi/", "data connector Data Layer"),
        ("services/nova_shell/", "Nova Shell"),
    ]
    flat: list[dict] = []
    subgroup_buckets: dict[str, list[dict]] = {label: [] for _, label in order}

    for e in entries:
        matched = False
        for prefix, label in order:
            if e["rel"].startswith(prefix):
                subgroup_buckets[label].append(e)
                matched = True
                break
        if not matched:
            flat.append(e)

    result = {}
    result["Core Services"] = flat
    for _, label in order:
        if subgroup_buckets[label]:
            result[label] = subgroup_buckets[label]
    return result


def render(entries: list[dict]) -> str:
    from datetime import date
    today = date.today().isoformat()
    grouped = group_entries(entries)

    lines = [
        "# Services Index",
        "",
        f"Last generated from code: {today}",
        "",
        "This is the exhaustive service-module index. Architectural ownership is described in `SYSTEM_MAP.md`; function-level detail is in `FUNCTION_INDEX.md`.",
        "",
        "**Check `docs/NOVA_LEDGER.md` drift alerts before relying on line counts or function lists — this index may lag recent changes.**",
        "",
        "## Ownership Domains",
        "",
        "- Runtime and process truth: `runtime_*`, `control_status*`, `port_ownership`, `ollama_health`, `server_side_runtime`.",
        "- HTTP and operator surfaces: `nova_http_*`, `control_*`, `operator_*`, `leah_*`, `session_*`, `chat_identity`.",
        "- Conversation and reply behavior: `nova_routing_*`, `nova_planner_contract`, `nova_reply_*`, `nova_fallback_flow`, `fulfillment_flow`, `supervisor_*`.",
        "- Memory and identity: `memory_*`, `identity_memory`, `nova_memory_*`, `nova_operational_identity`.",
        "- Tools and policy: `tool_*`, `nova_tool_*`, `policy_*`, `os_*`, `evidence_validity`.",
        "- Autonomy and feedback: `autonomy_*`, `nova_mission*`, `work_tree_*`, `subconscious_*`, `core_*`, `layer_maturity_policy`.",
        "- Patch, codegen, test, and release: `nova_patching`, `patch_*`, `codegen_*`, `test_session_*`, `regression_*`, `validation_*`, `release_*`, `installer_validation`.",
        "- Data and data connector: `data_pipeline_registry`, `control_pipelines`, `pipeline_privileged_bridge`, and `services/edfi/*`.",
        "- Backpack Host: `services/backpack_host/*` — discovery, install, grant enforcement, uninstall sanitizer, residue scan.",
        "- Nova Shell: `services/nova_shell/*` — operator authentication, TOTP, role management, session trust.",
        "- Decision Judge: `decision_proposal_judge` — pre-execution claim evaluation with judge reports and episodes.",
        "- Solution Trail: `solution_trail` — solution path tracking and breadcrumb recording.",
        "- Media, time, retrieval, and environment: `nova_voice_runtime`, `nova_vision_runtime`, `nova_temporal_service`, `nova_calendar_ingestion`, `nova_web_*`, `nova_location_weather`, `sock_service`.",
        "- Inventory and diagnosis: `nova_wiring_inventory`, `nova_root_inventory`, `end_to_end_wiring`, `source_root_judgment`, `storage_watch`, `ops_journal`, `self_scan_rings`.",
        "",
    ]

    for group_name, group_items in grouped.items():
        lines.append(f"## {group_name}")
        lines.append("")
        lines.append("| Module | Lines | Public classes/functions | Singleton | Description |")
        lines.append("|---|---:|---|---|---|")
        for e in group_items:
            rel = e["rel"]
            lc = e["lines"]
            pub = ", ".join(e["public"][:8])
            if len(e["public"]) > 8:
                pub += f", +{len(e['public']) - 8} more"
            sing = e["singleton"] or "-"
            doc = e["docstring"] or "-"
            # escape pipes in doc
            doc = doc.replace("|", "\\|")
            pub = pub.replace("|", "\\|")
            lines.append(f"| `{rel}` | {lc} | {pub} | {sing} | {doc} |")
        lines.append("")

    lines += [
        "## Maintenance Rule",
        "",
        "Any added, removed, or renamed file under `services/` must update this index.",
        "Regenerate with: `python scripts/regenerate_services_index.py`",
        "A service is not documented merely because a nearby subsystem is described.",
        "",
    ]

    return "\n".join(lines)


def main() -> None:
    print("Scanning services/...")
    entries = scan_services()
    print(f"  Found {len(entries)} service files")
    content = render(entries)
    OUTPUT.write_text(content, encoding="utf-8")
    print(f"Written: {OUTPUT}")
    lc = len(content.splitlines())
    print(f"  {lc} lines")


if __name__ == "__main__":
    main()
