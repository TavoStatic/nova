from __future__ import annotations

from pathlib import Path
import re
from typing import Any


VALID_VALIDATION_RESULTS = {"pass", "pass-with-notes", "fail"}

_FIELD_PATTERN = re.compile(r"^\s*-\s*`?([^`:]+?)`?\s*:\s*(.*)$")
_PLACEHOLDER_VALUES = {
    "",
    "yes/no",
    "pass / pass-with-notes / fail",
    "not-run",
}
_BASE_REQUIRED_FIELDS = (
    "artifact path",
    "artifact version",
    "release channel",
    "manifest reviewed",
    "machine or vm name",
    "windows version",
    "python source used during install",
    "ollama expected for this target",
    "nova package-verify .",
    "nova install",
    "nova doctor",
    "nova runtime-status",
    "nova smoke-base --fix",
    "nova test",
    "nova run",
    "nova webui-start --host 127.0.0.1 --port 8080",
    "/control load result",
    "result",
)


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _field_key(value: Any) -> str:
    text = _clean_text(value).strip("`")
    text = re.sub(r"\s+", " ", text)
    return text.lower()


def _field_value_is_missing(value: Any) -> bool:
    text = _clean_text(value)
    return text.lower() in _PLACEHOLDER_VALUES


def _read_validation_record_fields(record_path: Path) -> tuple[dict[str, str], str]:
    try:
        lines = record_path.read_text(encoding="utf-8-sig", errors="ignore").splitlines()
    except Exception as exc:
        return {}, str(exc)

    fields: dict[str, str] = {}
    index = 0
    while index < len(lines):
        line = lines[index]
        match = _FIELD_PATTERN.match(str(line or ""))
        if not match:
            index += 1
            continue
        key = _field_key(match.group(1))
        if not key:
            index += 1
            continue
        value = _clean_text(match.group(2))
        if not value:
            next_index = index + 1
            while next_index < len(lines) and not _clean_text(lines[next_index]):
                next_index += 1
            if next_index < len(lines):
                candidate = _clean_text(lines[next_index])
                if (
                    candidate
                    and not _FIELD_PATTERN.match(candidate)
                    and not candidate.startswith("#")
                ):
                    value = candidate
                    index = next_index
        fields[key] = value
        index += 1
    return fields, ""


def release_validation_record_payload(
    record_path: str | Path,
    *,
    release_status: dict[str, Any] | None = None,
) -> dict[str, Any]:
    path_text = _clean_text(record_path)
    payload: dict[str, Any] = {
        "path": path_text,
        "exists": False,
        "readable": False,
        "error": "",
        "fields": {},
        "result": "",
        "result_valid": False,
        "complete": False,
        "missing_fields": list(_BASE_REQUIRED_FIELDS),
        "artifact_matches": False,
        "artifact_mismatch_reason": "",
        "ollama_expected": "",
    }
    if not path_text:
        payload["error"] = "validation_record_path_missing"
        return payload

    path = Path(path_text)
    payload["exists"] = path.exists()
    if not path.exists():
        payload["error"] = "validation_record_missing"
        return payload

    fields, error = _read_validation_record_fields(path)
    payload["readable"] = not bool(error)
    payload["error"] = error
    payload["fields"] = dict(fields)
    if error:
        return payload

    result = _clean_text(fields.get("result")).lower()
    payload["result"] = result
    payload["result_valid"] = result in VALID_VALIDATION_RESULTS
    payload["ollama_expected"] = _clean_text(fields.get("ollama expected for this target")).lower()

    required_fields = list(_BASE_REQUIRED_FIELDS)
    if payload["ollama_expected"] in {"yes", "true", "required"}:
        required_fields.append("nova smoke --fix")

    missing_fields = [
        field for field in required_fields
        if _field_value_is_missing(fields.get(field))
    ]
    if result and result not in VALID_VALIDATION_RESULTS and "result" not in missing_fields:
        missing_fields.append("result")

    status = release_status if isinstance(release_status, dict) else {}
    expected_artifact_path = _clean_text(status.get("latest_artifact_path"))
    expected_version = _clean_text(status.get("latest_version"))
    expected_channel = _clean_text(status.get("latest_channel"))
    record_artifact_path = _clean_text(fields.get("artifact path"))
    record_version = _clean_text(fields.get("artifact version"))
    record_channel = _clean_text(fields.get("release channel"))

    mismatch_reasons: list[str] = []
    if expected_artifact_path and record_artifact_path and expected_artifact_path != record_artifact_path:
        mismatch_reasons.append("artifact_path")
    if expected_version and record_version and expected_version != record_version:
        mismatch_reasons.append("artifact_version")
    if expected_channel and record_channel and expected_channel != record_channel:
        mismatch_reasons.append("release_channel")

    payload["artifact_matches"] = not mismatch_reasons and bool(record_artifact_path or record_version)
    payload["artifact_mismatch_reason"] = ",".join(mismatch_reasons)
    payload["missing_fields"] = missing_fields
    payload["complete"] = bool(payload["result_valid"]) and not missing_fields and not mismatch_reasons
    return payload


def _evidence_tools(evidence_rows: list[dict[str, Any]]) -> list[str]:
    tools: list[str] = []
    for row in evidence_rows:
        if not isinstance(row, dict):
            continue
        tool_name = _clean_text(row.get("tool_name"))
        args = row.get("tool_args") if isinstance(row.get("tool_args"), list) else []
        label = tool_name
        if args:
            label = f"{tool_name}({', '.join(_clean_text(item) for item in args[:3])})"
        if label and label not in tools:
            tools.append(label)
    return tools


def build_release_promotion_judgment(
    *,
    release_status: dict[str, Any],
    branch_payload: dict[str, Any] | None = None,
    evidence_rows: list[dict[str, Any]] | None = None,
    branch_id: str = "",
) -> dict[str, Any]:
    status = dict(release_status or {})
    payload = dict(branch_payload or {})
    evidence = [dict(row) for row in list(evidence_rows or []) if isinstance(row, dict)]
    readiness_state = _clean_text(status.get("latest_readiness_state") or payload.get("latest_readiness_state")).lower()
    ready_to_ship = bool(status.get("latest_ready_to_ship", payload.get("latest_ready_to_ship", False)))
    record_path = _clean_text(status.get("latest_validation_seed_path") or payload.get("latest_validation_seed_path"))
    record = release_validation_record_payload(record_path, release_status=status)

    if ready_to_ship:
        verdict = "ready"
        classification = "already_promoted"
        root_cause = "The release ledger already contains a recognized promotion outcome for the latest build."
        next_work = ["No release promotion work is open for this build."]
    elif readiness_state == "source-changed-after-build":
        verdict = "incomplete"
        classification = "source_changed_after_build"
        root_cause = "Live source changed after the current release package was built."
        next_work = ["Rebuild and verify the release package from current source before promotion judgment."]
    elif readiness_state == "needs-verification":
        verdict = "incomplete"
        classification = "package_verification_missing"
        root_cause = "The latest release build has no current package verification record."
        next_work = ["Run package verification for the latest artifact before release promotion judgment."]
    elif readiness_state == "blocked":
        verdict = "blocked"
        classification = "ledger_validation_failed"
        root_cause = "The release ledger records a failing validation result for the latest build."
        next_work = ["Use the validation failure evidence to open the owner-root repair lane."]
    elif not record.get("exists"):
        verdict = "incomplete"
        classification = "validation_record_missing"
        root_cause = "The latest build points to no readable validation record."
        next_work = ["Regenerate or locate the validation record for the current release artifact."]
    elif not record.get("result_valid"):
        verdict = "incomplete"
        classification = "validation_outcome_missing"
        root_cause = "The package is manifest-verified, but the validation record has no real pass/pass-with-notes/fail outcome."
        next_work = [
            "Run the release validation profile on the intended target environment.",
            "Record the observed result in the validation record before any promotion ledger write.",
        ]
    elif record.get("artifact_mismatch_reason"):
        verdict = "blocked"
        classification = "validation_record_artifact_mismatch"
        root_cause = f"Validation record does not match the latest artifact: {record.get('artifact_mismatch_reason')}."
        next_work = ["Use a validation record generated for the current artifact before promotion."]
    elif not record.get("complete"):
        verdict = "incomplete"
        classification = "validation_record_incomplete"
        root_cause = "The validation record has an outcome, but required validation fields are still blank or placeholders."
        next_work = [
            "Complete the missing validation record fields from an actual validation run.",
            "Then record the completed outcome in the release ledger.",
        ]
    elif record.get("result") == "fail":
        verdict = "blocked"
        classification = "validation_record_failed"
        root_cause = "The validation record reports fail for the current artifact."
        next_work = ["Open the owner-root repair lane from the recorded blocking issues before rebuilding."]
    else:
        verdict = "ready"
        classification = "promotion_record_ready"
        root_cause = "The validation record is complete and matches the current artifact; only the ledger promotion record is missing."
        next_work = ["Record the completed validation outcome in the release ledger."]

    return {
        "ok": True,
        "verdict": verdict,
        "classification": classification,
        "root_cause": root_cause,
        "branch_id": _clean_text(branch_id),
        "readiness_state": readiness_state or "unknown",
        "ready_to_ship": ready_to_ship,
        "artifact": {
            "path": _clean_text(status.get("latest_artifact_path") or payload.get("latest_artifact_path")),
            "name": _clean_text(status.get("latest_artifact_name") or payload.get("latest_artifact_name")),
            "version": _clean_text(status.get("latest_version") or payload.get("latest_version")),
            "channel": _clean_text(status.get("latest_channel") or payload.get("latest_channel")),
            "label": _clean_text(status.get("latest_label") or payload.get("latest_label")),
            "verified_at": _clean_text(status.get("latest_verified_at") or payload.get("latest_verified_at")),
            "promoted_at": _clean_text(status.get("latest_promoted_at") or payload.get("latest_promoted_at")),
        },
        "validation_record": record,
        "evidence": {
            "row_count": len(evidence),
            "tools": _evidence_tools(evidence),
        },
        "blocked_shortcuts": [
            "do_not_promote_from_package_verification_only",
            "do_not_mark_ready_without_a_real_validation_outcome",
            "do_not_convert_missing_validation_evidence_into_operator_hold",
        ],
        "next_work": next_work,
    }


def render_release_promotion_judgment(judgment: dict[str, Any]) -> str:
    record = judgment.get("validation_record") if isinstance(judgment.get("validation_record"), dict) else {}
    evidence = judgment.get("evidence") if isinstance(judgment.get("evidence"), dict) else {}
    artifact = judgment.get("artifact") if isinstance(judgment.get("artifact"), dict) else {}
    lines = [
        "Release Promotion Judgment",
        f"- verdict: {judgment.get('verdict')}",
        f"- classification: {judgment.get('classification')}",
        f"- root cause: {judgment.get('root_cause')}",
        f"- branch: {judgment.get('branch_id') or ''}",
        f"- readiness state: {judgment.get('readiness_state')}",
        f"- ready to ship: {bool(judgment.get('ready_to_ship'))}",
        f"- artifact: {artifact.get('name') or artifact.get('path') or 'unknown'}",
        f"- verified at: {artifact.get('verified_at') or 'missing'}",
        f"- promoted at: {artifact.get('promoted_at') or 'missing'}",
        f"- validation record: {'present' if record.get('exists') else 'missing'} ({record.get('path') or ''})",
        f"- validation result: {record.get('result') or 'missing'}; valid={bool(record.get('result_valid'))}; complete={bool(record.get('complete'))}",
        f"- record artifact matches: {bool(record.get('artifact_matches'))}; mismatch={record.get('artifact_mismatch_reason') or 'none'}",
        f"- missing record fields: {', '.join(record.get('missing_fields') or []) or 'none'}",
        f"- evidence rows: {int(evidence.get('row_count', 0) or 0)}",
        f"- evidence tools: {', '.join(evidence.get('tools') or []) or 'none'}",
    ]
    lines.append("Blocked shortcuts:")
    lines.extend(f"- {item}" for item in list(judgment.get("blocked_shortcuts") or []))
    lines.append("Next work:")
    lines.extend(f"- {item}" for item in list(judgment.get("next_work") or []))
    return "\n".join(lines)
