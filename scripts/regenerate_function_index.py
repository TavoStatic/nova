"""
regenerate_function_index.py
-----------------------------

NOVA_DOC:
  category: script
  authority: active_authority
  last_session: 2026-08-05
  last_agent: claude-cowork
  session_state: current
  next_step: none
  open: none
Regenerates docs/FUNCTION_INDEX.md from the active source tree.

Scans all .py files reachable from NOVA_ROOT, extracting:
- Top-level functions and async functions
- Classes and their methods (one level deep, not recursive)

Note: uses shallow scan (top-level + class body only) so it stays fast on
large files like autonomy_maintenance.py (7700 lines) and nova_core.py (3800 lines).
Deeply nested helper functions are not indexed.

Usage:
    python scripts/regenerate_function_index.py

Excluded directories: .venv, .git, runtime, tests, agent-tools, terminals,
__pycache__, archive.
"""
from __future__ import annotations

import ast
from datetime import date
from pathlib import Path

NOVA_ROOT = Path(__file__).parent.parent
OUTPUT = NOVA_ROOT / "docs" / "FUNCTION_INDEX.md"

EXCLUDE: set[str] = {
    ".venv", ".git", "runtime", "tests",
    "agent-tools", "terminals", "__pycache__", "archive",
}

TODAY = date.today().isoformat()


def _compact_sig(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    args = node.args
    parts: list[str] = []
    d_offset = len(args.args) - len(args.defaults)
    for i, a in enumerate(args.args):
        parts.append(f"{a.arg}=…" if i >= d_offset else a.arg)
    if args.vararg:
        parts.append(f"*{args.vararg.arg}")
    elif args.kwonlyargs:
        parts.append("*")
    for i, a in enumerate(args.kwonlyargs):
        parts.append(f"{a.arg}=…" if args.kw_defaults[i] else a.arg)
    if args.kwarg:
        parts.append(f"**{args.kwarg.arg}")
    return f"def {node.name}({', '.join(parts)})"


def _first_doc(node: ast.AST) -> str:
    try:
        ds = ast.get_docstring(node) or ""  # type: ignore[arg-type]
        return ds.split("\n")[0][:80]
    except Exception:
        return ""


def scan_file(path: Path) -> tuple[list[tuple], list[tuple]]:
    """
    Shallow scan: top-level functions + class bodies only.
    Avoids ast.walk() to stay fast on large files.
    """
    try:
        src = path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(src)
    except (SyntaxError, OSError):
        return [], []

    fns: list[tuple] = []
    classes: list[tuple] = []

    for node in tree.body:  # top-level only
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            fns.append((node.lineno, node.name, _compact_sig(node), _first_doc(node)))
        elif isinstance(node, ast.ClassDef):
            classes.append((node.lineno, node.name))
            # One level into class body
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    fns.append((child.lineno, f"{node.name}.{child.name}",
                                _compact_sig(child), _first_doc(child)))

    return fns, classes


def collect_files() -> list[Path]:
    return sorted(
        p for p in NOVA_ROOT.rglob("*.py")
        if not any(ex in p.parts for ex in EXCLUDE)
    )


def render(py_files: list[Path]) -> str:
    sections: list[str] = []
    total_fns = total_classes = file_count = 0

    for path in py_files:
        fns, classes = scan_file(path)
        if not fns and not classes:
            continue
        rel = path.relative_to(NOVA_ROOT).as_posix()
        try:
            lc = path.read_text(encoding="utf-8", errors="replace").count("\n")
        except OSError:
            lc = 0
        total_fns += len(fns)
        total_classes += len(classes)
        file_count += 1

        s: list[str] = [
            f"## `{rel}`",
            "",
            f"Lines: {lc} | Functions/methods: {len(fns)} | Classes: {len(classes)}",
            "",
        ]
        if classes:
            s.append("Classes: " + ", ".join(f"`{n}` (L{l})" for l, n in classes))
            s.append("")
        if fns:
            s.append("| Line | Function or method | Signature | Docstring |")
            s.append("|---:|---|---|---|")
            for lineno, name, sig, ds in fns:
                sig_e = sig.replace("|", "\\|")
                ds_e = ds.replace("|", "\\|")
                s.append(f"| {lineno} | `{name}` | `{sig_e}` | {ds_e} |")
        s.append("")
        sections.append("\n".join(s))

    header = [
        "# Nova Code Surface Function Index",
        "",
        f"Generated from the active source tree on {TODAY}. "
        "This is a mechanical inventory, not a claim that every function is correctly wired.",
        "",
        f"- Python source files indexed: {file_count}",
        f"- Python functions/methods indexed: {total_fns}",
        f"- Python classes indexed: {total_classes}",
        "",
        "- Excluded: `.venv/`, `.git/`, `runtime/`, `tests/`, `agent-tools/`, "
        "`terminals/`, caches.",
        "- Shallow scan: top-level functions + class methods (not recursive). "
        "Deeply nested helpers not indexed.",
        "- Regenerate: `python scripts/regenerate_function_index.py`",
        "",
    ]
    return "\n".join(header + sections)


def main() -> None:
    print("Scanning Python files (shallow)...")
    py_files = collect_files()
    print(f"  Found {len(py_files)} files")
    content = render(py_files)
    OUTPUT.write_text(content, encoding="utf-8")
    out_lines = len(content.splitlines())
    print(f"Written: {OUTPUT}  ({out_lines} lines)")


if __name__ == "__main__":
    main()
