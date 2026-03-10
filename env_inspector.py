# env_inspector.py

import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def check_file(path: Path):
    return path.exists()


def load_json(path: Path):
    try:
        if not path.exists():
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def inspect_environment():

    report = {}

    # policy
    policy_path = BASE_DIR / "policy.json"
    report["policy_loaded"] = check_file(policy_path)

    policy = load_json(policy_path)
    if policy:
        report["tools_enabled"] = policy.get("tools_enabled", {})
        report["allowed_root"] = policy.get("allowed_root")
    else:
        report["tools_enabled"] = {}
        report["allowed_root"] = None

    # capabilities
    caps_path = BASE_DIR / "capabilities.json"
    report["capabilities_file"] = check_file(caps_path)

    caps = load_json(caps_path)
    report["registered_capabilities"] = list(caps.keys()) if caps else []

    # knowledge directory
    knowledge_dir = BASE_DIR / "knowledge"
    report["knowledge_dir"] = check_file(knowledge_dir)

    web_dir = knowledge_dir / "web"
    report["web_cache_dir"] = check_file(web_dir)

    if web_dir.exists():
        files = list(web_dir.glob("*"))
        report["web_files"] = len(files)
    else:
        report["web_files"] = 0

    # memory
    memory_file = BASE_DIR / "nova_memory.sqlite"
    report["memory_db"] = check_file(memory_file)

    return report


def format_report(data):

    lines = []
    lines.append("Environment inspection:\n")

    lines.append(f"Policy loaded: {data.get('policy_loaded')}")
    lines.append(f"Allowed root: {data.get('allowed_root')}\n")

    lines.append("Tools enabled:")
    for k, v in data.get("tools_enabled", {}).items():
        lines.append(f"  {k}: {v}")

    lines.append("\nCapabilities:")
    for c in data.get("registered_capabilities", []):
        lines.append(f"  {c}")

    lines.append("\nKnowledge:")
    lines.append(f"  knowledge folder: {data.get('knowledge_dir')}")
    lines.append(f"  web cache: {data.get('web_cache_dir')}")
    lines.append(f"  cached web files: {data.get('web_files')}")

    lines.append("\nMemory:")
    lines.append(f"  memory database: {data.get('memory_db')}")

    return "\n".join(lines)