from __future__ import annotations

import argparse
import io
import json
import re
import sys
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest import mock


BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import nova_core
import nova_http
import run_tools


RUNNER_ROOT = BASE_DIR / "runtime" / "test_sessions"
DEFAULT_SESSIONS_DIR = BASE_DIR / "tests" / "sessions"
DEFAULT_COMPARE_MODES = ("cli", "http")
VALID_COMPARE_MODES = {"cli", "http", "run_tools"}
_ROUTE_NOISE_PREFIXES = (
    "truth_hierarchy:",
    "hard_answer:",
    "policy_gate:",
    "memory_context:",
    "chat_context:",
    "session_fact_sheet:",
    "llm_fallback:",
)


class _SilentTTS:
    def start(self) -> None:
        return None

    def stop(self) -> None:
        return None

    def say(self, _text: str) -> None:
        return None


def _mode_label(mode: str) -> str:
    return {
        "cli": "CLI",
        "http": "HTTP",
        "run_tools": "Run Tools",
    }.get(str(mode or "").strip().lower(), str(mode or "mode").replace("_", " ").title())


def _parse_compare_modes(value: Any) -> list[str]:
    if value is None:
        return list(DEFAULT_COMPARE_MODES)
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError("Session JSON compare_modes must contain exactly two modes")

    modes = [str(item or "").strip().lower() for item in value]
    if any(not item for item in modes):
        raise ValueError("Session JSON compare_modes entries must be non-empty")
    invalid = [item for item in modes if item not in VALID_COMPARE_MODES]
    if invalid:
        raise ValueError(f"Unsupported compare_modes entries: {', '.join(sorted(set(invalid)))}")
    return modes


def load_session(session_name: str) -> dict[str, Any]:
    raw = str(session_name or "").strip()
    candidate = Path(raw)
    windows_abs = bool(re.match(r"^[A-Za-z]:[\\/]", raw))
    if windows_abs and not candidate.exists():
        # Accept legacy Windows absolute paths in generated definitions and remap
        # them into this checkout so Linux CI can load the same session artifact.
        remapped = re.sub(r"^[A-Za-z]:[\\/]", "", raw).replace("\\", "/")
        parts = [p for p in remapped.split("/") if p]
        lowered = [p.lower() for p in parts]
        if parts and lowered[0] == BASE_DIR.name.lower():
            parts = parts[1:]
            lowered = lowered[1:]
        if parts:
            candidate = BASE_DIR.joinpath(*parts)
    elif not candidate.is_absolute():
        candidate = DEFAULT_SESSIONS_DIR / raw

    if not candidate.exists() and windows_abs:
        alt = BASE_DIR / "runtime" / "test_sessions" / "generated_definitions" / Path(raw).name
        if alt.exists():
            candidate = alt

    if not candidate.exists():
        raise FileNotFoundError(f"Session file not found: {candidate}")

    payload = json.loads(candidate.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Session JSON must be an object")

    raw_messages = payload.get("messages")
    if not isinstance(raw_messages, list) or not raw_messages:
        raise ValueError("Session JSON must contain a non-empty 'messages' array")

    messages = [str(item).strip() for item in raw_messages if str(item).strip()]
    if not messages:
        raise ValueError("Session JSON must contain at least one non-empty message")

    return {
        "path": candidate,
        "name": str(payload.get("name") or candidate.stem),
        "messages": messages,
        "compare_modes": _parse_compare_modes(payload.get("compare_modes")),
    }


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except Exception:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows


def _read_ledger_rows(action_dir: Path) -> list[dict[str, Any]]:
    if not action_dir.exists():
        return []
    rows: list[dict[str, Any]] = []
    for path in sorted(action_dir.glob("*.json")):
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _normalize_saved_artifact_text(text: str) -> str:
    normalized = str(text or "")
    normalized = re.sub(r"[A-Za-z]:\\[^\n]*?knowledge\\web\\\d{8}_\d{6}_[^\s)]+", "<saved_web_file>", normalized)
    normalized = re.sub(r"\d{8}_\d{6}", "<stamp>", normalized)
    return normalized


def _assistant_compare_text(value: Any) -> str:
    normalized = _normalize_saved_artifact_text(str(value or "")).strip()
    compact = _normalize_text(normalized)
    if compact.startswith("Web research results (allowlisted crawl) for:"):
        return compact[:250]
    return compact


def _canonical_fact_answer(value: Any) -> str:
    text = _assistant_compare_text(value)
    normalized = str(text or "").strip().strip('"\'')
    normalized = re.sub(r"[.!?]+$", "", normalized).strip()
    patterns = (
        r"^You asked me to remember(?: the)? (?:codeword|topic) (?P<fact>.+)$",
        r"^You said(?: that)? (?P<fact>.+)$",
        r"^The (?:codeword|topic|review|owner|blocker) (?:was|is) (?P<fact>.+)$",
        r"^It (?:was|is) (?P<fact>.+)$",
    )
    for pattern in patterns:
        match = re.match(pattern, normalized, flags=re.I)
        if match:
            normalized = str(match.group("fact") or "").strip().strip('"\'')
            normalized = re.sub(r"[.!?]+$", "", normalized).strip()
            break
    return _normalize_text(normalized).lower()


def _canonical_route_summary(value: Any) -> str:
    text = str(value or "")
    steps = [part.strip() for part in text.split("->") if part.strip()]
    filtered = [
        step for step in steps
        if not any(step.startswith(prefix) for prefix in _ROUTE_NOISE_PREFIXES)
    ]
    return _normalize_text(" -> ".join(filtered))


def _is_question_like(text: str) -> bool:
    return "?" in str(text or "")


def _assistant_equivalent(cli_turn: dict[str, Any], http_turn: dict[str, Any]) -> bool:
    cli_text = _assistant_compare_text(cli_turn.get("assistant"))
    http_text = _assistant_compare_text(http_turn.get("assistant"))
    if cli_text == http_text:
        return True
    if _canonical_fact_answer(cli_text) and _canonical_fact_answer(cli_text) == _canonical_fact_answer(http_text):
        return True
    if str(cli_turn.get("planner_decision") or "") == "llm_fallback" and str(http_turn.get("planner_decision") or "") == "llm_fallback":
        # LLM fallback prompts can vary by phrasing while preserving intent.
        if _is_question_like(cli_text) and _is_question_like(http_text):
            return True
    return False


def _preview_value(value: Any, *, limit: int = 180) -> str:
    text = str(value)
    text = text.replace("\r", " ").replace("\n", " ")
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)] + "..."


def _probe_lines(turn: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    probe_summary = str(turn.get("probe_summary") or "").strip()
    if probe_summary and probe_summary.lower() not in {"all green", "none"}:
        lines.append(probe_summary)
    for item in turn.get("probe_results") or []:
        text = str(item or "").strip()
        if text:
            lines.append(text)
    return lines


def _flagged_probe_lines(turns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    flagged: list[dict[str, Any]] = []
    for turn in turns:
        lines = _probe_lines(turn)
        interesting = [line for line in lines if any(token in line.lower() for token in ("red", "yellow", "drift", "warn", "fail", "unstable", "issue"))]
        if interesting:
            flagged.append({"turn": int(turn.get("turn") or 0), "lines": interesting})
    return flagged


def _turn_record(index: int, user_text: str, assistant_text: str, ledger: dict[str, Any] | None, reflection: dict[str, Any] | None) -> dict[str, Any]:
    ledger = ledger if isinstance(ledger, dict) else {}
    reflection = reflection if isinstance(reflection, dict) else {}
    return {
        "turn": index,
        "user": str(user_text or ledger.get("user_input") or ""),
        "assistant": str(assistant_text or ledger.get("final_answer") or ""),
        "planner_decision": str(ledger.get("planner_decision") or ""),
        "route_summary": str(ledger.get("route_summary") or ""),
        "grounded": bool(ledger.get("grounded", False)),
        "active_subject": str(reflection.get("active_subject") or ledger.get("active_subject") or ""),
        "continuation_used": bool(reflection.get("continuation_used", ledger.get("continuation_used", False))),
        "probe_summary": str(reflection.get("probe_summary") or "All green"),
        "probe_results": list(reflection.get("probe_results") or []),
        "suggestions": list(reflection.get("suggestions") or []),
    }


@contextmanager
def _isolated_runner_state(mode_dir: Path):
    mode_dir.mkdir(parents=True, exist_ok=True)
    action_dir = mode_dir / "actions"
    action_dir.mkdir(parents=True, exist_ok=True)
    session_store = mode_dir / "http_chat_sessions.json"
    health_log = mode_dir / "health.log"
    reflection_log = mode_dir / "self_reflection.jsonl"
    learned_facts = mode_dir / "learned_facts.json"
    identity_file = mode_dir / "identity.json"

    saved_turns = dict(nova_http.SESSION_TURNS)
    saved_owners = dict(nova_http.SESSION_OWNERS)
    saved_active_user = nova_core.get_active_user()

    with mock.patch.object(nova_core, "ACTION_LEDGER_DIR", action_dir), \
         mock.patch.object(nova_core, "SELF_REFLECTION_LOG", reflection_log), \
         mock.patch.object(nova_core, "HEALTH_LOG", health_log), \
         mock.patch.object(nova_core, "LEARNED_FACTS_FILE", learned_facts), \
         mock.patch.object(nova_core, "IDENTITY_FILE", identity_file), \
         mock.patch.object(nova_http, "RUNTIME_DIR", mode_dir), \
         mock.patch.object(nova_http, "SESSION_STORE_PATH", session_store):
        try:
            nova_core.set_active_user(None)
            nova_http.SESSION_TURNS.clear()
            nova_http.SESSION_OWNERS.clear()
            nova_http.SESSION_STATE_MANAGER.clear()
            nova_core.TURN_SUPERVISOR.reset()
            yield {
                "mode_dir": mode_dir,
                "action_dir": action_dir,
                "health_log": health_log,
                "reflection_log": reflection_log,
                "session_store": session_store,
            }
        finally:
            nova_core.set_active_user(saved_active_user)
            nova_http.SESSION_TURNS.clear()
            nova_http.SESSION_TURNS.update(saved_turns)
            nova_http.SESSION_OWNERS.clear()
            nova_http.SESSION_OWNERS.update(saved_owners)
            nova_http.SESSION_STATE_MANAGER.clear()
            nova_core.TURN_SUPERVISOR.reset()


def run_cli_session(messages: list[str], mode_dir: Path) -> dict[str, Any]:
    with _isolated_runner_state(mode_dir) as paths:
        stdout = io.StringIO()
        with mock.patch.object(nova_core, "VOICE_OK", False), \
             mock.patch.object(nova_core, "speak_chunked", lambda *_args, **_kwargs: None), \
             mock.patch("builtins.input", side_effect=messages + ["q"]), \
             mock.patch("sys.stdout", new=stdout):
            nova_core.run_loop(_SilentTTS())

        ledgers = _read_ledger_rows(paths["action_dir"])
        reflections = _read_jsonl(paths["reflection_log"])
        turns: list[dict[str, Any]] = []
        for index, ledger in enumerate(ledgers, start=1):
            reflection = reflections[index - 1] if index - 1 < len(reflections) else {}
            turns.append(_turn_record(index, str(ledger.get("user_input") or ""), str(ledger.get("final_answer") or ""), ledger, reflection))

        return {
            "mode": "cli",
            "turns": turns,
            "stdout": stdout.getvalue(),
            "health_rows": _read_jsonl(paths["health_log"]),
            "reflection_rows": reflections,
            "artifacts": {key: str(value) for key, value in paths.items()},
        }


def run_http_session(messages: list[str], mode_dir: Path) -> dict[str, Any]:
    with _isolated_runner_state(mode_dir) as paths:
        session_id = "http-" + uuid.uuid4().hex[:12]
        turns: list[dict[str, Any]] = []
        reflection_rows: list[dict[str, Any]] = []

        for index, message in enumerate(messages, start=1):
            reply = nova_http.process_chat(session_id, message)
            ledgers = _read_ledger_rows(paths["action_dir"])
            reflections = _read_jsonl(paths["reflection_log"])
            ledger = ledgers[-1] if ledgers else {}
            reflection = reflections[-1] if reflections else {}
            reflection_rows = reflections
            turns.append(_turn_record(index, message, reply, ledger, reflection))

        return {
            "mode": "http",
            "session_id": session_id,
            "turns": turns,
            "health_rows": _read_jsonl(paths["health_log"]),
            "reflection_rows": reflection_rows,
            "artifacts": {key: str(value) for key, value in paths.items()},
        }


def run_run_tools_session(messages: list[str], mode_dir: Path) -> dict[str, Any]:
    with _isolated_runner_state(mode_dir) as paths:
        turns: list[dict[str, Any]] = []
        reflection_rows: list[dict[str, Any]] = []

        for index, message in enumerate(messages, start=1):
            reply = run_tools.ask_nova(message)
            ledgers = _read_ledger_rows(paths["action_dir"])
            reflections = _read_jsonl(paths["reflection_log"])
            ledger = ledgers[-1] if ledgers else {}
            reflection = reflections[-1] if reflections else {}
            reflection_rows = reflections
            turns.append(_turn_record(index, message, reply, ledger, reflection))

        return {
            "mode": "run_tools",
            "session_id": "run-tools",
            "turns": turns,
            "health_rows": _read_jsonl(paths["health_log"]),
            "reflection_rows": reflection_rows,
            "artifacts": {key: str(value) for key, value in paths.items()},
        }


def _run_mode_session(mode: str, messages: list[str], mode_dir: Path) -> dict[str, Any]:
    normalized = str(mode or "").strip().lower()
    if normalized == "cli":
        return run_cli_session(messages, mode_dir)
    if normalized == "http":
        return run_http_session(messages, mode_dir)
    if normalized == "run_tools":
        return run_run_tools_session(messages, mode_dir)
    raise ValueError(f"Unsupported session mode: {mode}")


def _issue_values(left_mode: str, right_mode: str, left_value: Any, right_value: Any) -> dict[str, Any]:
    return {
        "left": left_value,
        "right": right_value,
        left_mode: left_value,
        right_mode: right_value,
    }


def compare_sessions(left_result: dict[str, Any], right_result: dict[str, Any]) -> dict[str, Any]:
    left_mode = str(left_result.get("mode") or "left").strip().lower() or "left"
    right_mode = str(right_result.get("mode") or "right").strip().lower() or "right"
    left_turns = list(left_result.get("turns") or [])
    right_turns = list(right_result.get("turns") or [])
    turn_count = max(len(left_turns), len(right_turns))
    diffs: list[dict[str, Any]] = []

    for index in range(turn_count):
        left_turn = left_turns[index] if index < len(left_turns) else {}
        right_turn = right_turns[index] if index < len(right_turns) else {}
        issues: dict[str, Any] = {}
        if not _assistant_equivalent(left_turn, right_turn):
            issues["assistant"] = _issue_values(left_mode, right_mode, left_turn.get("assistant", ""), right_turn.get("assistant", ""))
        if str(left_turn.get("active_subject") or "") != str(right_turn.get("active_subject") or ""):
            issues["active_subject"] = _issue_values(left_mode, right_mode, left_turn.get("active_subject", ""), right_turn.get("active_subject", ""))
        if bool(left_turn.get("continuation_used", False)) != bool(right_turn.get("continuation_used", False)):
            issues["continuation_used"] = _issue_values(left_mode, right_mode, bool(left_turn.get("continuation_used", False)), bool(right_turn.get("continuation_used", False)))
        if _canonical_route_summary(left_turn.get("route_summary")) != _canonical_route_summary(right_turn.get("route_summary")):
            issues["route_summary"] = _issue_values(left_mode, right_mode, left_turn.get("route_summary", ""), right_turn.get("route_summary", ""))
        if _normalize_text(left_turn.get("probe_summary")) != _normalize_text(right_turn.get("probe_summary")):
            issues["probe_summary"] = _issue_values(left_mode, right_mode, left_turn.get("probe_summary", ""), right_turn.get("probe_summary", ""))
        if issues:
            diffs.append({"turn": index + 1, "issues": issues})

    comparison = {
        "left_mode": left_mode,
        "right_mode": right_mode,
        "left_label": _mode_label(left_mode),
        "right_label": _mode_label(right_mode),
        "turn_count_match": len(left_turns) == len(right_turns),
        "left_turns": len(left_turns),
        "right_turns": len(right_turns),
        "diffs": diffs,
        "left_flagged_probes": _flagged_probe_lines(left_turns),
        "right_flagged_probes": _flagged_probe_lines(right_turns),
    }
    for mode_name, turns, flagged in (
        (left_mode, left_turns, comparison["left_flagged_probes"]),
        (right_mode, right_turns, comparison["right_flagged_probes"]),
    ):
        comparison[f"{mode_name}_turns"] = len(turns)
        comparison[f"{mode_name}_flagged_probes"] = flagged
    return comparison


def _write_report(run_dir: Path, session_meta: dict[str, Any], left_result: dict[str, Any], right_result: dict[str, Any], comparison: dict[str, Any]) -> Path:
    left_mode = str(left_result.get("mode") or "left")
    right_mode = str(right_result.get("mode") or "right")
    report = {
        "session": {
            "name": session_meta["name"],
            "path": str(session_meta["path"]),
            "messages": list(session_meta["messages"]),
            "compare_modes": list(session_meta.get("compare_modes") or list(DEFAULT_COMPARE_MODES)),
        },
        "runs": {
            left_mode: left_result,
            right_mode: right_result,
        },
        "comparison": comparison,
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    if left_mode == "cli":
        report["cli"] = left_result
    if right_mode == "cli":
        report["cli"] = right_result
    if left_mode == "http":
        report["http"] = left_result
    if right_mode == "http":
        report["http"] = right_result
    out = run_dir / "result.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=True, indent=2), encoding="utf-8")
    return out


def _print_drift_details(diffs: list[dict[str, Any]], *, left_mode: str, right_mode: str, left_label: str, right_label: str) -> None:
    for item in diffs:
        turn = int(item.get("turn") or 0)
        print(f"- Turn {turn}:")
        issues = item.get("issues") or {}
        for field_name in sorted(issues.keys()):
            field = issues.get(field_name) or {}
            print(f"  {field_name}:")
            print(f"    {left_label}: {_preview_value(field.get(left_mode, field.get('left', '')))}")
            print(f"    {right_label}: {_preview_value(field.get(right_mode, field.get('right', '')))}")


def _print_summary(session_meta: dict[str, Any], comparison: dict[str, Any], report_path: Path) -> None:
    left_label = str(comparison.get("left_label") or "Left")
    right_label = str(comparison.get("right_label") or "Right")
    left_mode = str(comparison.get("left_mode") or "left")
    right_mode = str(comparison.get("right_mode") or "right")
    print(f"Running session: {session_meta['name']} ({len(session_meta['messages'])} turns)")
    print("")
    print("=== SESSION COMPARISON ===")
    print(f"{left_label} turns:  {comparison['left_turns']}")
    print(f"{right_label} turns: {comparison['right_turns']}")
    print(f"Turn count parity: {'OK' if comparison['turn_count_match'] else 'MISMATCH'}")

    diffs = comparison.get("diffs") or []
    if diffs:
        print("")
        print("Drift detected:")
        _print_drift_details(diffs, left_mode=left_mode, right_mode=right_mode, left_label=left_label, right_label=right_label)
    else:
        print(f"No {left_label}/{right_label} drift detected in replies, route summaries, active subject, continuation flags, or probe summaries.")

    left_flagged = comparison.get("left_flagged_probes") or []
    right_flagged = comparison.get("right_flagged_probes") or []
    if left_flagged or right_flagged:
        print("")
        print("Flagged probes:")
        for label, rows in ((left_label, left_flagged), (right_label, right_flagged)):
            for row in rows:
                print(f"- {label} turn {row['turn']}: {' | '.join(row['lines'])}")
    else:
        print("No red/yellow drift-style probes were flagged in either path.")

    print("")
    print(f"Saved full report to {report_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay a stored test conversation against both CLI and HTTP paths.")
    parser.add_argument("session_file", help="JSON session file name under tests/sessions or a direct path")
    args = parser.parse_args()

    session_meta = load_session(args.session_file)
    compare_modes = list(session_meta.get("compare_modes") or list(DEFAULT_COMPARE_MODES))
    left_mode, right_mode = compare_modes
    stamp = time.strftime("%Y%m%d_%H%M%S")
    run_dir = RUNNER_ROOT / f"{Path(str(session_meta['path'])).stem}_{left_mode}_vs_{right_mode}_{stamp}"
    left_dir = run_dir / left_mode
    right_dir = run_dir / right_mode

    left_result = _run_mode_session(left_mode, session_meta["messages"], left_dir)
    right_result = _run_mode_session(right_mode, session_meta["messages"], right_dir)
    comparison = compare_sessions(left_result, right_result)
    report_path = _write_report(run_dir, session_meta, left_result, right_result, comparison)
    _print_summary(session_meta, comparison, report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())