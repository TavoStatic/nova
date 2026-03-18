from __future__ import annotations

import json
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
RUNTIME_DIR = BASE_DIR / "runtime"
ACTION_LEDGER_DIR = RUNTIME_DIR / "actions"
SELF_REFLECTION_LOG = RUNTIME_DIR / "self_reflection.jsonl"
TOOL_INTENT_LABELS = {
    "weather_lookup": "Weather route",
    "web_fetch": "Web fetch route",
    "web_search": "Web search route",
    "web_gather": "Web gather route",
    "web_research": "Web research route",
}


def _record_completed_tool_execution(record: dict) -> bool:
    trace = record.get("route_trace") if isinstance(record, dict) else None
    if not isinstance(trace, list):
        return False
    for step in trace:
        if not isinstance(step, dict):
            continue
        if str(step.get("stage") or "") == "tool_execution" and str(step.get("outcome") or "") == "ok":
            return True
        if str(step.get("stage") or "") in {"keyword_tool", "command"} and str(step.get("outcome") or "") == "matched" and str(record.get("tool_result") or "").strip():
            return True
    return False


def _record_requested_tool_clarification(record: dict) -> bool:
    if not isinstance(record, dict):
        return False
    if str(record.get("planner_decision") or "").strip() == "ask_clarify":
        return True
    trace = record.get("route_trace")
    if not isinstance(trace, list):
        return False
    for step in trace:
        if not isinstance(step, dict):
            continue
        stage = str(step.get("stage") or "").strip()
        outcome = str(step.get("outcome") or "").strip()
        if stage == "action_planner" and outcome == "ask_clarify":
            return True
        if stage == "pending_action" and outcome == "awaiting_location":
            return True
        if stage == "finalize" and outcome == "ask_clarify":
            return True
    return False


def _intent_stats(records: list[dict], intent: str) -> tuple[int, int]:
    selected = 0
    completed = 0
    for rec in records:
        if str(rec.get("intent") or "").strip() != intent:
            continue
        if _record_requested_tool_clarification(rec):
            continue
        selected += 1
        if _record_completed_tool_execution(rec):
            completed += 1
    return selected, completed


def _failure_from_reflection(item: dict) -> dict:
    failure = item.get("failure_top") if isinstance(item.get("failure_top"), dict) else {}
    return {
        "intent": str(failure.get("intent") or ""),
        "selected": int(failure.get("selected", 0) or 0),
        "completed": int(failure.get("completed", 0) or 0),
        "summary": str(failure.get("summary") or item.get("top_repeated_failure_class") or "none"),
    }


def _pct(completed: int, selected: int) -> int:
    if selected <= 0:
        return 100
    return int(round((completed / selected) * 100))


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except Exception:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _read_recent_ledger(limit: int = 20) -> list[dict]:
    if not ACTION_LEDGER_DIR.exists():
        return []
    rows: list[dict] = []
    for path in sorted(ACTION_LEDGER_DIR.glob("*.json"))[-max(1, int(limit)):]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _rank_failures(records: list[dict]) -> list[str]:
    counts: dict[str, list[int]] = {}
    for rec in records:
        intent = str(rec.get("intent") or "unknown").strip() or "unknown"
        if intent not in TOOL_INTENT_LABELS:
            continue
        if _record_requested_tool_clarification(rec):
            continue
        completed = _record_completed_tool_execution(rec)
        bucket = counts.setdefault(intent, [0, 0])
        bucket[0] += 1
        if not completed:
            bucket[1] += 1

    ranked = sorted(counts.items(), key=lambda item: (item[1][1], item[1][0]), reverse=True)
    lines: list[str] = []
    for idx, (intent, (selected, incomplete)) in enumerate(ranked[:5], start=1):
        if selected < 2 or incomplete <= 0:
            continue
        label = TOOL_INTENT_LABELS.get(intent, intent)
        lines.append(f"{idx}. {label:<28} {incomplete}x / {selected} attempts")
    return lines


def _latest_reflections(limit: int = 3) -> list[dict]:
    rows = _read_jsonl(SELF_REFLECTION_LOG)
    return rows[-max(1, int(limit)):]


def _format_active_subject(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return "none"
    if text.startswith("identity_profile"):
        return "Profile thread"
    if text.startswith("developer_identity"):
        return "Developer mode"
    if text.startswith("weather"):
        return "Weather lookup"
    if text.startswith("retrieval"):
        return "Search / retrieval"
    return text


def main() -> None:
    reflections = _latest_reflections(limit=3)
    ledgers = _read_recent_ledger(limit=20)

    if reflections:
        latest = reflections[-1]
        previous = reflections[-2] if len(reflections) >= 2 else {}
        latest_failure = _failure_from_reflection(latest)
        previous_failure = _failure_from_reflection(previous) if previous else {"intent": "", "selected": 0, "completed": 0, "summary": "none"}
        latest_weather_selected = latest_failure.get("selected", 0) if latest_failure.get("intent") == "weather_lookup" else 0
        latest_weather_completed = latest_failure.get("completed", 0) if latest_failure.get("intent") == "weather_lookup" else 0
        if latest_weather_selected <= 0:
            latest_weather_selected, latest_weather_completed = _intent_stats(ledgers, "weather_lookup")
        latest_web_selected, latest_web_completed = _intent_stats(ledgers, "web_fetch")
        current_pct = _pct(latest_failure.get("completed", 0), latest_failure.get("selected", 0)) if latest_failure.get("intent") == "weather_lookup" else _pct(latest_weather_completed, latest_weather_selected)
        previous_pct = _pct(previous_failure.get("completed", 0), previous_failure.get("selected", 0)) if previous_failure.get("intent") == "weather_lookup" else current_pct
        top_issue = latest_failure.get("summary") or "none"
        print(f"Latest reflection (turn {latest.get('turn_count', '')}):")
        print(f"Weather reliability: {current_pct}% ({latest_weather_completed}/{latest_weather_selected or 0} completed) - previous snapshot {previous_pct}%")
        print(f"Top issue: {top_issue}")
        print(f"Web fetch: {(_pct(latest_web_completed, latest_web_selected))}% success ({latest_web_completed}/{latest_web_selected or 0} completed)")
        print(f"Probe summary: {latest.get('probe_summary', 'All green')}")
        for line in list(latest.get("probe_results") or [])[:5]:
            print(line)
        for line in list(latest.get("suggestions") or [])[:3]:
            print(f"Suggestion: {line}")
        print(f"Routing stability: {bool(latest.get('routing_stable', True))}")
        print(f"Routing overrides in recent window: {int(latest.get('routing_overrides', 0) or 0)}")
        print(f"Routing override used on latest turn: {bool(latest.get('routing_override_used_latest_turn', False))}")
        print(
            f"Active: {_format_active_subject(str(latest.get('active_subject') or ''))} | "
            f"Continuations in recent window: {int(latest.get('continuations_last_window', 0) or 0)} "
            f"(retrieval: {int(latest.get('retrieval_continuations', 0) or 0)})"
        )
        print(f"Continuation used on latest turn: {bool(latest.get('continuation_used', False))}")
        print("")

    print("Top failure patterns (last 20 records):")
    lines = _rank_failures(ledgers)
    if lines:
        for line in lines:
            print(line)
    else:
        print("1. none")

    print("\nLatest reflection snapshots:")
    if not reflections:
        print("- none")
        return
    for item in reflections:
        failure = item.get("failure_top") if isinstance(item.get("failure_top"), dict) else {}
        correction = item.get("correction_top") if isinstance(item.get("correction_top"), dict) else {}
        print(
            f"- ts={item.get('ts', '')} turns={item.get('turn_count', '')} "
            f"failure={failure.get('summary') or item.get('top_repeated_failure_class', 'none')} "
            f"correction={correction.get('class') or item.get('top_repeated_correction_class', 'none')} "
            f"probe_summary={item.get('probe_summary', 'All green')} "
            f"suggestions={item.get('suggestions', [])} "
            f"routing_stable={item.get('routing_stable', True)} claims_blocked={item.get('claims_blocked', 0)} "
            f"routing_overrides={int(item.get('routing_overrides', 0) or 0)} "
            f"routing_override_used_latest_turn={bool(item.get('routing_override_used_latest_turn', False))} "
            f"active_subject={_format_active_subject(str(item.get('active_subject') or ''))} "
            f"continuation_used={bool(item.get('continuation_used', False))} "
            f"retrieval_continuations={int(item.get('retrieval_continuations', 0) or 0)} "
            f"sample_intents_last5={item.get('sample_intents_last5', [])}"
        )


if __name__ == "__main__":
    main()