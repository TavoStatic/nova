import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from services.end_to_end_wiring import run_end_to_end_wiring_check

report = run_end_to_end_wiring_check(include_runtime=False)
failed = {c["name"]: c.get("detail") for c in report["checks"] if not c.get("ok")}
print("failed:", failed or "none")