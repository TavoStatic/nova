#!/usr/bin/env python3
"""Nova startup preflight validator.

Checks that the local workspace is complete enough for a safe launch.
Exit code:
- 0 when required checks pass
- 1 when any required check fails
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent


@dataclass
class CheckResult:
    name: str
    ok: bool
    required: bool
    info: str


def _exists_file(path: Path) -> bool:
    return path.exists() and path.is_file()


def _exists_dir(path: Path) -> bool:
    return path.exists() and path.is_dir()


def _default_policy() -> dict:
    return {
        "allowed_root": str(BASE_DIR),
        "allow_shell": False,
        "confirm_writes": True,
        "confirm_exec": True,
        "tools_enabled": {
            "screen": True,
            "camera": True,
            "files": True,
            "health": True,
            "web": False,
        },
        "models": {
            "chat": "llama3.1:8b",
            "vision": "qwen2.5vl:7b",
            "stt_size": "base",
        },
        "memory": {
            "enabled": False,
            "mode": "B",
            "top_k": 5,
            "min_score": 0.25,
            "exclude_sources": ["voice"],
        },
        "web": {
            "enabled": False,
            "allow_domains": [],
            "max_bytes": 20_000_000,
        },
    }


def apply_lightweight_fixes() -> list[str]:
    actions: list[str] = []

    for rel in ("runtime", "logs"):
        p = BASE_DIR / rel
        if not p.exists():
            p.mkdir(parents=True, exist_ok=True)
            actions.append(f"created_dir:{rel}")

    policy_path = BASE_DIR / "policy.json"
    if not policy_path.exists():
        example_path = BASE_DIR / "policy.example.json"
        try:
            if example_path.exists() and example_path.is_file():
                policy_path.write_text(example_path.read_text(encoding="utf-8"), encoding="utf-8")
                actions.append("created_policy_from_example")
            else:
                policy_path.write_text(json.dumps(_default_policy(), indent=2), encoding="utf-8")
                actions.append("created_policy_default")
        except Exception as e:
            actions.append(f"policy_create_failed:{e}")

    return actions


def run_preflight() -> list[CheckResult]:
    results: list[CheckResult] = []

    required_files = [
        "nova_core.py",
        "nova_guard.py",
        "stop_guard.py",
        "task_engine.py",
        "tts_piper.py",
        "action_planner.py",
        "agent.py",
        "health.py",
        "policy.json",
    ]

    for rel in required_files:
        p = BASE_DIR / rel
        results.append(CheckResult(name=f"file:{rel}", ok=_exists_file(p), required=True, info=str(p)))

    required_dirs = ["runtime", "logs", "knowledge"]
    for rel in required_dirs:
        p = BASE_DIR / rel
        results.append(CheckResult(name=f"dir:{rel}", ok=_exists_dir(p), required=True, info=str(p)))

    venv_python = BASE_DIR / ".venv" / "Scripts" / "python.exe"
    results.append(CheckResult(name="venv:python", ok=_exists_file(venv_python), required=True, info=str(venv_python)))

    policy_path = BASE_DIR / "policy.json"
    if _exists_file(policy_path):
        try:
            policy = json.loads(policy_path.read_text(encoding="utf-8"))
            has_allowed_root = isinstance(policy.get("allowed_root"), str) and bool(policy.get("allowed_root", "").strip())
            has_tools = isinstance(policy.get("tools_enabled"), dict)
            has_models = isinstance(policy.get("models"), dict)
            results.append(CheckResult("policy:allowed_root", has_allowed_root, True, "policy.json"))
            results.append(CheckResult("policy:tools_enabled", has_tools, True, "policy.json"))
            results.append(CheckResult("policy:models", has_models, True, "policy.json"))
        except Exception as e:
            results.append(CheckResult("policy:json_valid", False, True, f"{policy_path}: {e}"))
    else:
        results.append(CheckResult("policy:json_valid", False, True, f"missing: {policy_path}"))

    piper_exe = BASE_DIR / "piper" / "piper.exe"
    piper_model = BASE_DIR / "piper" / "models" / "en_US-lessac-medium.onnx"
    results.append(CheckResult("tts:piper_exe", _exists_file(piper_exe), False, str(piper_exe)))
    results.append(CheckResult("tts:piper_model", _exists_file(piper_model), False, str(piper_model)))

    has_ollama = shutil.which("ollama") is not None
    results.append(CheckResult("runtime:ollama_on_path", has_ollama, False, "PATH"))

    return results


def summarize(results: list[CheckResult], quiet: bool = False) -> int:
    failed_required = [r for r in results if r.required and not r.ok]

    if not quiet:
        print("=== Nova Doctor ===")
        for r in results:
            prefix = "[OK]" if r.ok else ("[FAIL]" if r.required else "[WARN]")
            print(f"{prefix} {r.name} :: {r.info}")
        print()

    summary = {
        "required_ok": len(failed_required) == 0,
        "required_failed": [r.name for r in failed_required],
        "checks_total": len(results),
    }
    if not quiet:
        print(json.dumps(summary, indent=2))

    return 0 if len(failed_required) == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--fix", action="store_true", help="Apply lightweight local fixes before preflight")
    args = parser.parse_args()

    fix_actions: list[str] = []
    if args.fix:
        fix_actions = apply_lightweight_fixes()
        if (not args.quiet) and fix_actions:
            print("=== Nova Doctor Fixes ===")
            for action in fix_actions:
                print(f"[FIX] {action}")
            print()

    results = run_preflight()
    code = summarize(results, quiet=args.quiet)

    if args.as_json:
        out = {
            "required_ok": code == 0,
            "fix_applied": bool(args.fix),
            "fix_actions": fix_actions,
            "checks": [
                {
                    "name": r.name,
                    "ok": r.ok,
                    "required": r.required,
                    "info": r.info,
                }
                for r in results
            ],
        }
        print(json.dumps(out, indent=2))

    return code


if __name__ == "__main__":
    sys.exit(main())
