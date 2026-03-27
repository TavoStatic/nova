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


RUNNER_ROOT = BASE_DIR / "runtime" / "test_sessions"
DEFAULT_SESSIONS_DIR = BASE_DIR / "tests" / "sessions"
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


def compare_sessions(cli_result: dict[str, Any], http_result: dict[str, Any]) -> dict[str, Any]:
    cli_turns = list(cli_result.get("turns") or [])
    http_turns = list(http_result.get("turns") or [])
    turn_count = max(len(cli_turns), len(http_turns))
    diffs: list[dict[str, Any]] = []

    for index in range(turn_count):
        cli_turn = cli_turns[index] if index < len(cli_turns) else {}
        http_turn = http_turns[index] if index < len(http_turns) else {}
        issues: dict[str, Any] = {}
        if not _assistant_equivalent(cli_turn, http_turn):
            issues["assistant"] = {
                "cli": cli_turn.get("assistant", ""),
                "http": http_turn.get("assistant", ""),
            }
        if str(cli_turn.get("active_subject") or "") != str(http_turn.get("active_subject") or ""):
            issues["active_subject"] = {
                "cli": cli_turn.get("active_subject", ""),
                "http": http_turn.get("active_subject", ""),
            }
        if bool(cli_turn.get("continuation_used", False)) != bool(http_turn.get("continuation_used", False)):
            issues["continuation_used"] = {
                "cli": bool(cli_turn.get("continuation_used", False)),
                "http": bool(http_turn.get("continuation_used", False)),
            }
        if _canonical_route_summary(cli_turn.get("route_summary")) != _canonical_route_summary(http_turn.get("route_summary")):
            issues["route_summary"] = {
                "cli": cli_turn.get("route_summary", ""),
                "http": http_turn.get("route_summary", ""),
            }
        if _normalize_text(cli_turn.get("probe_summary")) != _normalize_text(http_turn.get("probe_summary")):
            issues["probe_summary"] = {
                "cli": cli_turn.get("probe_summary", ""),
                "http": http_turn.get("probe_summary", ""),
            }
        if issues:
            diffs.append({"turn": index + 1, "issues": issues})

    return {
        "turn_count_match": len(cli_turns) == len(http_turns),
        "cli_turns": len(cli_turns),
        "http_turns": len(http_turns),
        "diffs": diffs,
        "cli_flagged_probes": _flagged_probe_lines(cli_turns),
        "http_flagged_probes": _flagged_probe_lines(http_turns),
    }


def _write_report(run_dir: Path, session_meta: dict[str, Any], cli_result: dict[str, Any], http_result: dict[str, Any], comparison: dict[str, Any]) -> Path:
    report = {
        "session": {
            "name": session_meta["name"],
            "path": str(session_meta["path"]),
            "messages": list(session_meta["messages"]),
        },
        "cli": cli_result,
        "http": http_result,
        "comparison": comparison,
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    out = run_dir / "result.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=True, indent=2), encoding="utf-8")
    return out


def _print_drift_details(diffs: list[dict[str, Any]]) -> None:
    for item in diffs:
        turn = int(item.get("turn") or 0)
        print(f"- Turn {turn}:")
        issues = item.get("issues") or {}
        for field_name in sorted(issues.keys()):
            field = issues.get(field_name) or {}
            print(f"  {field_name}:")
            print(f"    CLI : {_preview_value(field.get('cli', ''))}")
            print(f"    HTTP: {_preview_value(field.get('http', ''))}")


def _print_summary(session_meta: dict[str, Any], comparison: dict[str, Any], report_path: Path) -> None:
    print(f"Running session: {session_meta['name']} ({len(session_meta['messages'])} turns)")
    print("")
    print("=== SESSION COMPARISON ===")
    print(f"CLI turns:  {comparison['cli_turns']}")
    print(f"HTTP turns: {comparison['http_turns']}")
    print(f"Turn count parity: {'OK' if comparison['turn_count_match'] else 'MISMATCH'}")

    diffs = comparison.get("diffs") or []
    if diffs:
        print("")
        print("Drift detected:")
        _print_drift_details(diffs)
    else:
        print("No CLI/HTTP drift detected in replies, route summaries, active subject, continuation flags, or probe summaries.")

    cli_flagged = comparison.get("cli_flagged_probes") or []
    http_flagged = comparison.get("http_flagged_probes") or []
    if cli_flagged or http_flagged:
        print("")
        print("Flagged probes:")
        for label, rows in (("CLI", cli_flagged), ("HTTP", http_flagged)):
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
    stamp = time.strftime("%Y%m%d_%H%M%S")
    run_dir = RUNNER_ROOT / f"{Path(str(session_meta['path'])).stem}_{stamp}"
    cli_dir = run_dir / "cli"
    http_dir = run_dir / "http"

    cli_result = run_cli_session(session_meta["messages"], cli_dir)
    http_result = run_http_session(session_meta["messages"], http_dir)
    comparison = compare_sessions(cli_result, http_result)
    report_path = _write_report(run_dir, session_meta, cli_result, http_result, comparison)
    _print_summary(session_meta, comparison, report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())