# capabilities.py
# Nova capability awareness layer

from pathlib import Path
import json

BASE_DIR = Path(__file__).resolve().parent

CAPABILITY_FILE = BASE_DIR / "capabilities.json"


def load_capabilities():
    if not CAPABILITY_FILE.exists():
        return {}
    with open(CAPABILITY_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_capabilities(data):
    with open(CAPABILITY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def register_capability(name, description):
    data = load_capabilities()
    data[name] = description
    save_capabilities(data)



def has_capability(name):
    data = load_capabilities()
    return name in data


def explain_missing(task, required):
    missing = []

    for cap in required:
        if not has_capability(cap):
            missing.append(cap)

    if not missing:
        return None

    msg = "I cannot complete this task yet.\n\nMissing capability:\n"

    for m in missing:
        msg += f"• {m}\n"

    return msg

def list_capabilities():
    return load_capabilities()


def describe_capabilities():
    data = load_capabilities()
    if not data:
        return "I do not currently know of any registered capabilities."

    msg = "Current capabilities:\n"
    for name, desc in data.items():
        msg += f"• {name}: {desc}\n"
    return msg

def analyze_task(task: str) -> dict:  # ← change return type for clarity
    t = task.lower().strip()
    requirements = []

    # Education/PEIMS specific
    if any(word in t for word in ["attendance", "peims", "tsds", "student data", "enrollment", "gradebook"]):
        requirements += ["database_connection", "sis_attendance_table", "query_execution"]

    if any(word in t for word in ["student", "grades", "report card", "transcript", "aeries", "skyward"]):
        requirements += ["database_connection", "student_records_table", "query_execution"]

    # Web / external access
    if any(word in t for word in ["web", "internet", "browse", "search", "lookup", "tea.texas.gov", "fetch"]):
        requirements += ["web_access"]

    # Default: most tasks don't require special caps
    if not requirements:
        return {"allow_llm": True, "message": ""}  # Let LLM handle it

    # Check what we have
    missing = [r for r in requirements if not has_capability(r)]

    if not missing:
        return {"allow_llm": True, "message": ""}

    msg = "This task requires capabilities I don't have yet:\n" + "\n".join(f"• {m}" for m in missing)
    return {"allow_llm": False, "message": msg}