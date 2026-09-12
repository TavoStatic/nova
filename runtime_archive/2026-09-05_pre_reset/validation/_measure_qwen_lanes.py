"""Ollama-only lane measure. Does not change Nova policy."""
from __future__ import annotations

import json
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

CASES = [
    {
        "id": "right_path_redundant",
        "ask": "right_path",
        "expected": "skip_until_world_changes",
        "prompt": (
            "A Work Tree finding already has trail judgment redundant / no_marker_advance "
            "for tool source_root_judgment. The open stem is ATTEMPTED on that same tool. "
            "Choose exactly one next approach: remint_same | skip_until_world_changes | mark_complete"
        ),
    },
    {
        "id": "predicted_vs_invoked",
        "ask": "predicted_invoked_agree",
        "expected": "no",
        "prompt": (
            "Pickup offered tool read. Execute invoked source_root_judgment. "
            "Did predicted and invoked agree? Answer exactly: yes | no"
        ),
    },
    {
        "id": "missing_evidence",
        "ask": "missing_evidence_named",
        "expected": "no",
        "prompt": (
            "source_root_judgment ran. No required markers advanced. "
            "Is the finding complete? Answer exactly: yes | no"
        ),
    },
    {
        "id": "repeat_unchanged",
        "ask": "repeat_unchanged_path",
        "expected": "stop_until_ref_changes",
        "prompt": (
            "Same finding, same tool, no marker change, three times. "
            "Choose exactly one next: invoke_again | stop_until_ref_changes"
        ),
    },
    {
        "id": "explanation_vs_done",
        "ask": "explanation_as_completion",
        "expected": "no",
        "prompt": (
            "The model wrote a long explanation of why tests sit outside compact lanes. "
            "No marker moved. Is the finding closed? Answer exactly: yes | no"
        ),
    },
    {
        "id": "edfi_uninstalled",
        "ask": "world_ended",
        "expected": "treat_as_uninstalled_history",
        "prompt": (
            "runtime/backpacks/uninstalled/edfi.json status=uninstalled. "
            "A branch titled data connector backpack fusion is not healthy remains. "
            "Choose exactly one approach: fix_fusion | treat_as_uninstalled_history | ignore"
        ),
    },
    {
        "id": "nyo_identity",
        "ask": "historical_identity",
        "expected": "historical_identity",
        "prompt": (
            "A ready finding source_key contains nyo-system-base-rc-2026.05.21 zip. "
            "Current release stream key is package-zip:rc. "
            "Choose exactly one: live_current_package | historical_identity"
        ),
    },
]


def _chat(model: str, prompt: str) -> dict:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "think": False,
        "options": {"num_ctx": 8192, "temperature": 0, "num_predict": 48},
    }
    req = urllib.request.Request(
        "http://127.0.0.1:11434/api/chat",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=180) as resp:
        body = json.loads(resp.read().decode())
    wall = time.perf_counter() - t0
    msg = body.get("message") if isinstance(body.get("message"), dict) else {}
    content = str(msg.get("content") or "").strip()
    eval_count = int(body.get("eval_count") or 0)
    eval_ns = int(body.get("eval_duration") or 0)
    load_ns = int(body.get("load_duration") or 0)
    tps = (eval_count / (eval_ns / 1e9)) if eval_ns else 0.0
    return {
        "content": content,
        "thinking": str(msg.get("thinking") or "")[:200],
        "wall_sec": round(wall, 3),
        "eval_count": eval_count,
        "tok_per_sec": round(tps, 2),
        "load_sec": round(load_ns / 1e9, 3),
    }


def _score(content: str, expected: str) -> bool:
    text = " ".join(content.lower().split())
    exp = expected.lower()
    if text == exp or text.startswith(exp + " ") or text.endswith(" " + exp):
        return True
    # allow the token appearing as the only choice-like word
    tokens = [t.strip(".,:;!?") for t in text.replace("|", " ").split()]
    return exp in tokens and all(
        other not in tokens
        for other in (
            "remint_same",
            "mark_complete",
            "yes",
            "no",
            "invoke_again",
            "stop_until_ref_changes",
            "fix_fusion",
            "treat_as_uninstalled_history",
            "ignore",
            "live_current_package",
            "historical_identity",
            "skip_until_world_changes",
        )
        if other != exp
    )


def _ps() -> str:
    try:
        import subprocess

        out = subprocess.check_output(["ollama", "ps"], text=True, timeout=10)
        return out.strip()
    except Exception as exc:
        return f"ps_failed:{exc}"


def run_lane(model: str) -> dict:
    print("LANE", model, flush=True)
    rows = []
    hits = 0
    for case in CASES:
        got = _chat(model, case["prompt"])
        ok = _score(got["content"], case["expected"])
        hits += int(ok)
        rec = {**case, **got, "pass": ok}
        rows.append(rec)
        print(
            f"  {case['id']}: {'PASS' if ok else 'FAIL'} expected={case['expected']!r} got={got['content'][:80]!r} "
            f"{got['tok_per_sec']} tok/s {got['wall_sec']}s",
            flush=True,
        )
    return {
        "model": model,
        "ps": _ps(),
        "passed": hits,
        "total": len(CASES),
        "cases": rows,
    }


def main() -> None:
    import sys

    args = sys.argv[1:]
    append = "--append" in args
    models = [a for a in args if not a.startswith("-")] or ["qwen2.5:7b", "qwen3.5:9b"]
    dest = Path(__file__).resolve().parent / "qwen35_9b_lane_measure.json"
    if append and dest.exists():
        out = json.loads(dest.read_text(encoding="utf-8"))
        out.setdefault("lanes", [])
    else:
        out = {
            "at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "num_ctx": 8192,
            "think": False,
            "policy_unchanged": True,
            "lanes": [],
        }
    out["num_ctx"] = 8192
    out["think"] = False
    out["policy_unchanged"] = True
    for model in models:
        out["lanes"] = [lane for lane in out["lanes"] if lane.get("model") != model]
        out["lanes"].append(run_lane(model))
    dest.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print("wrote", dest)
    for lane in out["lanes"]:
        print(f"SUMMARY {lane['model']}: {lane['passed']}/{lane['total']}")
        print(lane["ps"])


if __name__ == "__main__":
    main()
