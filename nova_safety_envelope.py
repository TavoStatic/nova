from __future__ import annotations

import hashlib
import json
import math
import re
import shutil
import subprocess
import time
from collections import Counter
from pathlib import Path
from typing import Any

import nova_core


ROOT = Path(__file__).resolve().parent
VENV_PY = ROOT / ".venv" / "Scripts" / "python.exe"
TEST_SESSION_RUNNER = ROOT / "scripts" / "run_test_session.py"
GENERATED_DEFINITIONS_ROOT = ROOT / "runtime" / "test_sessions" / "generated_definitions"
PROMOTED_DEFINITIONS_ROOT = ROOT / "runtime" / "test_sessions" / "promoted"
PENDING_REVIEW_ROOT = ROOT / "runtime" / "test_sessions" / "pending_review"
QUARANTINE_ROOT = ROOT / "runtime" / "test_sessions" / "quarantine"
AUDIT_LOG = ROOT / "runtime" / "test_sessions" / "promotion_audit.jsonl"
LATEST_SUBCONSCIOUS = ROOT / "runtime" / "subconscious_runs" / "latest.json"
_MANIFEST_NAMES = {"generated_manifest.json", "latest_manifest.json"}
_TOKEN_RE = re.compile(r"[a-z0-9']+")
_REPORT_RE = re.compile(r"Saved full report to\s+(.+)$", re.MULTILINE)


def policy_safety_envelope() -> dict[str, Any]:
    raw = (nova_core.load_policy().get("safety_envelope") or {}) if hasattr(nova_core, "load_policy") else {}
    cfg = dict(raw if isinstance(raw, dict) else {})
    cfg.setdefault("enabled", True)
    cfg.setdefault("mode", "observe")
    cfg.setdefault("replay_threshold", 1.0)
    cfg.setdefault("replay_attempts", 2)
    cfg.setdefault("novelty_min", 0.35)
    cfg.setdefault("entropy_min", 2.8)
    cfg.setdefault("diversity_min_messages", 3)
    cfg.setdefault("human_veto_first_n", 3)
    cfg.setdefault("auto_demote_threshold", 0.90)
    cfg.setdefault("max_candidates_per_cycle", 3)
    cfg.setdefault("full_regression_required", False)
    cfg.setdefault("quarantine_root", str(QUARANTINE_ROOT))
    cfg.setdefault("pending_review_root", str(PENDING_REVIEW_ROOT))
    return cfg


def _definition_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return [path for path in sorted(root.glob("*.json")) if path.is_file() and path.name not in _MANIFEST_NAMES]


def _load_definition(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _messages(payload: dict[str, Any]) -> list[str]:
    raw = payload.get("messages") or []
    if not isinstance(raw, list):
        return []
    return [str(item).strip() for item in raw if str(item).strip()]


def _fingerprint(path: Path) -> str:
    return hashlib.sha1(path.read_bytes()).hexdigest()


def _append_audit(entry: dict[str, Any]) -> None:
    AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with AUDIT_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=True) + "\n")


def _latest_audit_by_file() -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    if not AUDIT_LOG.exists():
        return latest
    for line in AUDIT_LOG.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except Exception:
            continue
        if not isinstance(row, dict):
            continue
        file_name = str(row.get("file") or "").strip()
        if not file_name:
            continue
        latest[file_name] = row
    return latest


def render_status() -> str:
    cfg = policy_safety_envelope()
    generated = _definition_files(GENERATED_DEFINITIONS_ROOT)
    promoted = _definition_files(PROMOTED_DEFINITIONS_ROOT)
    pending = _definition_files(PENDING_REVIEW_ROOT)
    quarantined = _definition_files(QUARANTINE_ROOT)
    latest = _latest_audit_by_file()

    status_counts = Counter(str(row.get("status") or "unknown") for row in latest.values())
    pending_audit = 0
    for path in generated:
        row = latest.get(path.name) or {}
        if str(row.get("fingerprint") or "") != _fingerprint(path):
            pending_audit += 1

    latest_ts = "unknown"
    if latest:
        latest_ts = max(str(row.get("ts") or "") for row in latest.values()) or "unknown"

    lines = [
        "Safety envelope status:",
        f"- enabled: {bool(cfg.get('enabled', True))}",
        f"- mode: {str(cfg.get('mode') or 'observe')}",
        f"- generated definitions: {len(generated)}",
        f"- promoted pool: {len(promoted)}",
        f"- pending review: {len(pending)}",
        f"- quarantine: {len(quarantined)}",
        f"- latest audited files: {len(latest)}",
        f"- pending audit: {pending_audit}",
        f"- last audit ts: {latest_ts}",
    ]
    if status_counts:
        pieces = [f"{name}={count}" for name, count in sorted(status_counts.items())]
        lines.append(f"- audit statuses: {', '.join(pieces)}")
    preview = sorted(generated, key=lambda path: path.name)[:5]
    if preview:
        lines.append("- generated preview:")
        for path in preview:
            row = latest.get(path.name) or {}
            status = str(row.get("status") or "pending_audit")
            lines.append(f"  {path.name} ({status})")
    return "\n".join(lines)


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(str(text or "").lower())


def _counter_cosine(left: Counter[str], right: Counter[str]) -> float:
    if not left or not right:
        return 0.0
    common = set(left) & set(right)
    numerator = sum(float(left[token]) * float(right[token]) for token in common)
    left_norm = math.sqrt(sum(float(value) * float(value) for value in left.values()))
    right_norm = math.sqrt(sum(float(value) * float(value) for value in right.values()))
    if left_norm <= 0.0 or right_norm <= 0.0:
        return 0.0
    return numerator / (left_norm * right_norm)


def _shannon_entropy(labels: list[str]) -> float:
    if not labels:
        return 0.0
    counts = Counter(label for label in labels if label)
    total = float(sum(counts.values()) or 0.0)
    if total <= 0.0:
        return 0.0
    entropy = 0.0
    for value in counts.values():
        p = float(value) / total
        entropy -= p * math.log2(p)
    return entropy


def _intent_label(message: str) -> str:
    text = str(message or "").lower()
    if any(token in text for token in ["weather", "forecast", "temperature", "rain"]):
        return "weather"
    if any(token in text for token in ["patch", "preview", "rollback", "apply"]):
        return "patch"
    if any(token in text for token in ["memory", "remember", "name", "profile"]):
        return "memory_identity"
    if any(token in text for token in ["web", "research", "search", "online"]):
        return "web_research"
    if any(token in text for token in ["phase", "plan", "draft", "implement"]):
        return "planning"
    if any(token in text for token in ["guard", "maintenance", "cycle", "regression", "test"]):
        return "operations"
    return "general"


def _shape_label(message: str) -> str:
    text = str(message or "").strip().lower()
    if not text:
        return "empty"
    if text.endswith("?"):
        return "question"
    if any(text.startswith(prefix) for prefix in ["run ", "show ", "fix ", "apply ", "monitor ", "feed ", "plan ", "implement "]):
        return "command"
    return "statement"


def _command_density_label(message: str) -> str:
    text = str(message or "").lower()
    count = sum(1 for token in ["run", "apply", "fix", "show", "monitor", "feed", "plan", "implement", "restart", "watch"] if token in text)
    if count <= 0:
        return "none"
    if count == 1:
        return "single"
    return "dense"


def _diversity_score(messages: list[str]) -> float:
    intents = [_intent_label(message) for message in messages]
    shapes = [_shape_label(message) for message in messages]
    command_bins = [_command_density_label(message) for message in messages]
    return _shannon_entropy(intents) + 0.5 * _shannon_entropy(shapes) + 0.5 * _shannon_entropy(command_bins)


def _pool_similarity(path: Path, payload: dict[str, Any]) -> tuple[float, str]:
    target_messages = _messages(payload)
    target_counter = Counter(_tokenize(" ".join(target_messages)))
    best_similarity = 0.0
    best_match = ""
    for candidate in _definition_files(PROMOTED_DEFINITIONS_ROOT):
        if candidate.resolve() == path.resolve():
            continue
        other_payload = _load_definition(candidate)
        other_counter = Counter(_tokenize(" ".join(_messages(other_payload))))
        similarity = _counter_cosine(target_counter, other_counter)
        if similarity > best_similarity:
            best_similarity = similarity
            best_match = candidate.name
    return best_similarity, best_match


def _run_replay(path: Path) -> dict[str, Any]:
    if not VENV_PY.exists() or not TEST_SESSION_RUNNER.exists():
        return {"ok": False, "reason": "runner_missing", "comparison": {}, "report_path": ""}
    try:
        proc = subprocess.run(
            [str(VENV_PY), str(TEST_SESSION_RUNNER), str(path)],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=300,
        )
    except Exception as exc:
        return {"ok": False, "reason": f"runner_failed:{exc}", "comparison": {}, "report_path": ""}

    output = ((proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")).strip()
    report_path = ""
    report_payload: dict[str, Any] = {}
    match = _REPORT_RE.search(output)
    if match:
        report_path = match.group(1).strip()
        try:
            report_payload = json.loads(Path(report_path).read_text(encoding="utf-8"))
        except Exception:
            report_payload = {}
    comparison = dict(report_payload.get("comparison") or {}) if isinstance(report_payload, dict) else {}
    cli_flagged = list(comparison.get("cli_flagged_probes") or []) if isinstance(comparison, dict) else []
    http_flagged = list(comparison.get("http_flagged_probes") or []) if isinstance(comparison, dict) else []
    diffs = list(comparison.get("diffs") or []) if isinstance(comparison, dict) else []
    ok = bool(proc.returncode == 0 and comparison.get("turn_count_match") and not diffs and not cli_flagged and not http_flagged)
    return {
        "ok": ok,
        "reason": "ok" if ok else f"replay_failed:exit:{proc.returncode}",
        "stdout_tail": output[-2000:],
        "report_path": report_path,
        "comparison": comparison,
    }


def _run_full_regression() -> dict[str, Any]:
    try:
        proc = subprocess.run(
            [str(VENV_PY), "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py", "--buffer"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=5400,
        )
    except Exception as exc:
        return {"ok": False, "reason": f"full_regression_failed:{exc}", "tail": ""}
    output = ((proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")).strip()
    return {
        "ok": proc.returncode == 0,
        "reason": "ok" if proc.returncode == 0 else f"full_regression_failed:exit:{proc.returncode}",
        "tail": output[-2000:],
    }


def _family_fallback_score(family_id: str) -> float | None:
    if not family_id or not LATEST_SUBCONSCIOUS.exists():
        return None
    try:
        payload = json.loads(LATEST_SUBCONSCIOUS.read_text(encoding="utf-8"))
    except Exception:
        return None
    for family in list(payload.get("families") or []):
        if str(family.get("family_id") or "").strip() != family_id:
            continue
        best = 0.0
        found = False
        for item in list(family.get("robust_signals") or []):
            if str(item.get("signal") or "").strip() != "fallback_overuse":
                continue
            found = True
            try:
                best = max(best, float(item.get("robustness_score") or 0.0))
            except Exception:
                continue
        return best if found else 0.0
    return None


def _family_promoted_count(family_id: str) -> int:
    if not family_id:
        return 0
    count = 0
    for path in _definition_files(PROMOTED_DEFINITIONS_ROOT):
        payload = _load_definition(path)
        if str(payload.get("family_id") or "").strip() == family_id:
            count += 1
    return count


def _family_reviewed_count(family_id: str) -> int:
    if not family_id:
        return 0
    latest = _latest_audit_by_file()
    count = 0
    for row in latest.values():
        if str(row.get("family_id") or "").strip() != family_id:
            continue
        status = str(row.get("status") or "").strip().lower()
        if status in {"pending_review", "promoted"}:
            count += 1
    return count


def _cfg_float(cfg: dict[str, Any], key: str, default: float) -> float:
    try:
        return float(cfg.get(key, default))
    except Exception:
        return float(default)


def _cfg_int(cfg: dict[str, Any], key: str, default: int) -> int:
    try:
        return int(cfg.get(key, default))
    except Exception:
        return int(default)


def evaluate_promotion_contract(definition_path: str | Path, *, run_full_regression: bool = False) -> dict[str, Any]:
    path = Path(definition_path)
    payload = _load_definition(path)
    messages = _messages(payload)
    fingerprint = _fingerprint(path) if path.exists() else ""
    cfg = policy_safety_envelope()
    replay_threshold = _cfg_float(cfg, "replay_threshold", 1.0)
    novelty_min = _cfg_float(cfg, "novelty_min", 0.35)
    entropy_min = _cfg_float(cfg, "entropy_min", 2.8)
    auto_demote_threshold = _cfg_float(cfg, "auto_demote_threshold", 0.90)
    human_veto_first_n = _cfg_int(cfg, "human_veto_first_n", 3)

    if not path.exists() or not messages:
        return {
            "passed": False,
            "review_required": False,
            "file": path.name,
            "path": str(path),
            "fingerprint": fingerprint,
            "reasons": ["definition_invalid"],
            "gates": {},
            "metrics": {},
        }

    replay_attempts = max(1, _cfg_int(cfg, "replay_attempts", 2))
    replay = _run_replay(path)
    replay_attempts_used = 1
    while replay_attempts_used < replay_attempts and not replay.get("ok"):
        replay_attempts_used += 1
        next_try = _run_replay(path)
        replay = next_try
        if next_try.get("ok"):
            break
    replay_score = 1.0 if replay.get("ok") else 0.0
    similarity, nearest_file = _pool_similarity(path, payload)
    novelty = max(0.0, 1.0 - similarity)
    diversity = _diversity_score(messages)
    message_count = len(messages)
    family_id = str(payload.get("family_id") or "").strip()
    fallback_score = _family_fallback_score(family_id)
    overfit_measured = fallback_score is not None
    overfit_ok = bool(overfit_measured and float(fallback_score or 0.0) <= auto_demote_threshold)

    full_regression = {"ok": True, "reason": "skipped"}
    if bool(run_full_regression or cfg.get("full_regression_required", False)):
        full_regression = _run_full_regression()

    family_promoted_count = _family_promoted_count(family_id)
    family_reviewed_count = _family_reviewed_count(family_id)
    review_required = family_reviewed_count < max(0, human_veto_first_n)
    if not overfit_measured:
        review_required = True

    diversity_min_messages = max(1, _cfg_int(cfg, "diversity_min_messages", 3))
    diversity_measured = message_count >= max(1, diversity_min_messages)

    gates = {
        "replay_stability": {
            "passed": replay_score >= replay_threshold,
            "measured": True,
            "value": replay_score,
            "threshold": replay_threshold,
            "reason": str(replay.get("reason") or ""),
            "attempts_used": replay_attempts_used,
            "attempts_configured": replay_attempts,
        },
        "novelty": {
            "passed": novelty >= novelty_min,
            "measured": True,
            "value": novelty,
            "threshold": novelty_min,
            "nearest_match": nearest_file,
            "max_similarity": similarity,
        },
        "diversity": {
            "passed": True if not diversity_measured else diversity >= entropy_min,
            "measured": diversity_measured,
            "value": diversity,
            "threshold": entropy_min,
            "message_count": message_count,
            "min_messages": diversity_min_messages,
        },
        "overfit_guard": {
            "passed": overfit_ok,
            "measured": overfit_measured,
            "value": fallback_score,
            "threshold": auto_demote_threshold,
        },
        "full_regression": {
            "passed": bool(full_regression.get("ok")),
            "measured": bool(run_full_regression or cfg.get("full_regression_required", False)),
            "reason": str(full_regression.get("reason") or ""),
        },
    }

    reasons: list[str] = []
    for name, gate in gates.items():
        if gate.get("measured") and not gate.get("passed"):
            reasons.append(f"gate_failed:{name}")
    if review_required:
        reasons.append("pending_human_review")

    passed = all(
        bool(gate.get("passed"))
        for gate in gates.values()
        if bool(gate.get("measured"))
    )

    return {
        "passed": passed,
        "review_required": review_required,
        "file": path.name,
        "path": str(path),
        "fingerprint": fingerprint,
        "family_id": family_id,
        "variation_id": str(payload.get("variation_id") or "").strip(),
        "reasons": reasons,
        "gates": gates,
        "metrics": {
            "replay_score": replay_score,
            "novelty": novelty,
            "nearest_similarity": similarity,
            "nearest_match": nearest_file,
            "diversity": diversity,
            "fallback_overuse": fallback_score,
            "family_promoted_count": family_promoted_count,
            "family_reviewed_count": family_reviewed_count,
            "replay_attempts_used": replay_attempts_used,
        },
        "artifacts": {
            "replay_report_path": str(replay.get("report_path") or ""),
            "replay_tail": str(replay.get("stdout_tail") or ""),
            "full_regression_tail": str(full_regression.get("tail") or ""),
        },
    }


def promote_or_quarantine(definition_path: str | Path, *, run_full_regression: bool = False) -> dict[str, Any]:
    path = Path(definition_path)
    cfg = policy_safety_envelope()
    result = evaluate_promotion_contract(path, run_full_regression=run_full_regression)
    mode = str(cfg.get("mode") or "observe").strip().lower() or "observe"

    status = "observed"
    target_path = ""
    if not bool(cfg.get("enabled", True)):
        status = "disabled"
    elif mode == "observe":
        status = "observed_review" if result.get("review_required") else ("observed_pass" if result.get("passed") else "observed_fail")
    elif result.get("review_required"):
        pending_root = Path(str(cfg.get("pending_review_root") or PENDING_REVIEW_ROOT))
        pending_root.mkdir(parents=True, exist_ok=True)
        target = pending_root / path.name
        shutil.copy2(path, target)
        status = "pending_review"
        target_path = str(target)
    elif result.get("passed"):
        PROMOTED_DEFINITIONS_ROOT.mkdir(parents=True, exist_ok=True)
        target = PROMOTED_DEFINITIONS_ROOT / path.name
        shutil.copy2(path, target)
        status = "promoted"
        target_path = str(target)
    else:
        quarantine_root = Path(str(cfg.get("quarantine_root") or QUARANTINE_ROOT))
        quarantine_root.mkdir(parents=True, exist_ok=True)
        target = quarantine_root / path.name
        shutil.copy2(path, target)
        status = "quarantined"
        target_path = str(target)

    audit_row = {
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "file": path.name,
        "path": str(path),
        "fingerprint": str(result.get("fingerprint") or ""),
        "mode": mode,
        "status": status,
        "target_path": target_path,
        "passed": bool(result.get("passed")),
        "review_required": bool(result.get("review_required")),
        "family_id": str(result.get("family_id") or ""),
        "variation_id": str(result.get("variation_id") or ""),
        "reasons": list(result.get("reasons") or []),
        "metrics": dict(result.get("metrics") or {}),
        "gates": dict(result.get("gates") or {}),
    }
    _append_audit(audit_row)
    output = dict(result)
    output["status"] = status
    output["target_path"] = target_path
    return output


def evaluate_generated_definitions(paths: list[str] | list[Path], *, max_candidates: int | None = None) -> dict[str, Any]:
    cfg = policy_safety_envelope()
    latest = _latest_audit_by_file()
    cap = int(max_candidates if max_candidates is not None else cfg.get("max_candidates_per_cycle", 3) or 3)
    evaluated: list[dict[str, Any]] = []
    skipped = 0
    candidates = [Path(item) for item in paths]
    for path in candidates:
        if not path.exists() or path.name in _MANIFEST_NAMES:
            skipped += 1
            continue
        latest_row = latest.get(path.name) or {}
        fingerprint = _fingerprint(path)
        if str(latest_row.get("fingerprint") or "") == fingerprint:
            skipped += 1
            continue
        if len(evaluated) >= max(1, cap):
            skipped += 1
            continue
        evaluated.append(promote_or_quarantine(path))

    summary = {
        "evaluated_count": len(evaluated),
        "skipped_count": skipped,
        "promoted_count": sum(1 for item in evaluated if str(item.get("status") or "") == "promoted"),
        "pending_review_count": sum(1 for item in evaluated if str(item.get("status") or "") == "pending_review"),
        "quarantined_count": sum(1 for item in evaluated if str(item.get("status") or "") == "quarantined"),
        "observed_count": sum(1 for item in evaluated if str(item.get("status") or "").startswith("observed")),
        "results": evaluated,
    }
    return summary


def select_patch_candidate_definition_paths(root: Path | None = None) -> list[Path]:
    source_root = root or GENERATED_DEFINITIONS_ROOT
    files = _definition_files(source_root)
    cfg = policy_safety_envelope()
    mode = str(cfg.get("mode") or "observe").strip().lower() or "observe"
    if not bool(cfg.get("enabled", True)) or mode == "observe":
        return files

    latest = _latest_audit_by_file()
    selected: list[Path] = []
    for path in files:
        row = latest.get(path.name) or {}
        if str(row.get("status") or "") != "promoted":
            continue
        if str(row.get("fingerprint") or "") != _fingerprint(path):
            continue
        selected.append(path)
    return selected
