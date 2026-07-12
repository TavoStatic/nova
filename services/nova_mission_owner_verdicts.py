from __future__ import annotations

from typing import Any

from services.layer_maturity_policy import evaluate_core_gate


def _as_dict(value: Any) -> dict:
    return dict(value) if isinstance(value, dict) else {}


def _as_list(value: Any) -> list:
    return list(value) if isinstance(value, list) else []


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _text(value: Any, limit: int = 220) -> str:
    return str(value or "").strip()[:limit]


def _regression_status_current(*, status_label: str, stale: bool) -> bool:
    if stale:
        return False
    label = _text(status_label, 80).lower()
    if not label:
        return False
    return label == "ok" or "pass" in label


def _validation_truth_fresh(validation: dict) -> bool:
    if not validation:
        return False
    if _as_bool(validation.get("hidden_by_green_regression"), False):
        return False
    if validation.get("missing_artifact") is True:
        return False
    status = _text(validation.get("status"), 120).lower()
    if status in {
        "validation_actions_missing",
        "validation_actions_unreadable",
        "validation_artifact_truth_unavailable",
    }:
        return False
    return _as_bool(validation.get("ok"), False)


def _release_truth_current(*, release_truth: dict, release_status: dict) -> bool:
    truth = _as_dict(release_truth)
    release = _as_dict(release_status)
    if not truth and not release:
        return False
    payload = truth or release
    drift = _as_bool(
        payload.get("latest_source_changed_after_build")
        or payload.get("runtime_drift_expected"),
        False,
    )
    if drift and not _as_bool(payload.get("runtime_drift_tolerated"), False):
        return False
    identity = _text(
        payload.get("running_build_identity")
        or release.get("latest_artifact_name")
        or release.get("latest_version"),
        200,
    )
    return bool(identity and identity.lower() != "unknown")


def _blocker(owner: str, code: str, *, detail: str = "", source: str = "") -> dict[str, Any]:
    return {
        "owner": _text(owner, 80),
        "code": _text(code, 120),
        "detail": _text(detail, 240),
        "source": _text(source, 160),
    }


def _verdict(
    owner: str,
    *,
    ready: bool,
    source: str,
    blockers: list[dict[str, Any]] | None = None,
    summary: str = "",
    evidence: dict[str, Any] | None = None,
    blocks_green: bool = True,
) -> dict[str, Any]:
    normalized_blockers = [
        dict(item)
        for item in list(blockers or [])
        if isinstance(item, dict) and _text(item.get("code"), 120)
    ]
    return {
        "owner": _text(owner, 80),
        "ready": bool(ready),
        "status": "ready" if ready else "blocked",
        "source": _text(source, 160),
        "summary": _text(summary, 240),
        "blocks_green": bool(blocks_green),
        "blockers": normalized_blockers,
        "evidence": dict(evidence or {}),
    }


def _normalize_owner_verdicts(values: Any) -> list[dict[str, Any]]:
    verdicts: list[dict[str, Any]] = []
    for item in _as_list(values):
        payload = _as_dict(item)
        owner = _text(payload.get("owner"), 80)
        if not owner:
            continue
        blockers: list[dict[str, Any]] = []
        for raw in _as_list(payload.get("blockers")):
            if isinstance(raw, dict):
                code = _text(raw.get("code"), 120)
                if code:
                    blockers.append(
                        _blocker(
                            owner,
                            code,
                            detail=_text(raw.get("detail"), 240),
                            source=_text(raw.get("source"), 160),
                        )
                    )
            else:
                code = _text(raw, 120)
                if code:
                    blockers.append(_blocker(owner, code))
        ready = _as_bool(payload.get("ready"), not blockers)
        blocks_green = _as_bool(payload.get("blocks_green"), True)
        verdicts.append(
            _verdict(
                owner,
                ready=ready,
                source=_text(payload.get("source"), 160) or "external_owner_verdict",
                blockers=blockers,
                summary=_text(payload.get("summary"), 240),
                evidence=_as_dict(payload.get("evidence")),
                blocks_green=blocks_green,
            )
        )
    return verdicts


def _owner_blockers(owner_verdicts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    for verdict in owner_verdicts:
        owner = _text(verdict.get("owner"), 80)
        for blocker in _as_list(verdict.get("blockers")):
            payload = _as_dict(blocker)
            code = _text(payload.get("code"), 120)
            if not owner or not code:
                continue
            blockers.append(
                _blocker(
                    owner,
                    code,
                    detail=_text(payload.get("detail"), 240),
                    source=_text(payload.get("source") or verdict.get("source"), 160),
                )
            )
    return blockers


def _legacy_blocker_codes(owner_verdicts: list[dict[str, Any]]) -> list[str]:
    codes: list[str] = []
    for verdict in owner_verdicts:
        if not _as_bool(_as_dict(verdict).get("blocks_green"), True):
            continue
        for blocker in _as_list(_as_dict(verdict).get("blockers")):
            code = _text(_as_dict(blocker).get("code"), 120)
            if code and code not in codes:
                codes.append(code)
    return codes


def _core_gate_from_owner(evidence: dict) -> tuple[dict[str, Any], str]:
    layer_maturity = _as_dict(evidence.get("layer_maturity"))
    core_gate = _as_dict(layer_maturity.get("core_gate"))
    if core_gate:
        return core_gate, "layer_maturity.core_gate"
    return evaluate_core_gate(
        {
            "release_status": _as_dict(evidence.get("release_status")),
            "release_runtime_truth": _as_dict(evidence.get("release_runtime_truth")),
            "root_closure_inventory": _as_dict(evidence.get("root_closure_inventory")),
            "layer_maturity": layer_maturity,
        }
    ), "layer_maturity.compat_core_gate"


def build_mission_truth_gate(
    *,
    truth_evidence: dict | None,
    queue: dict,
    policy: dict,
) -> dict[str, Any]:
    evidence = _as_dict(truth_evidence)
    validation = _as_dict(evidence.get("validation_artifact_truth"))
    if not validation and evidence.get("validation_artifact_truth_ok") is not None:
        validation = {
            "ok": _as_bool(evidence.get("validation_artifact_truth_ok"), False),
            "status": _text(evidence.get("validation_artifact_truth_status"), 120),
            "hidden_by_green_regression": _as_bool(
                evidence.get("validation_artifact_hidden_by_green_regression"),
                False,
            ),
        }

    validation_fresh = _validation_truth_fresh(validation)
    regression_current = _regression_status_current(
        status_label=_text(evidence.get("last_regression_status"), 80),
        stale=_as_bool(evidence.get("last_regression_stale"), False),
    )
    release_truth_current = _release_truth_current(
        release_truth=_as_dict(evidence.get("release_runtime_truth")),
        release_status=_as_dict(evidence.get("release_status")),
    )
    generated_actionable = _as_int(queue.get("generated_actionable_count"))
    generated_pending = _as_int(queue.get("generated_pending_count"))
    generated_untested = max(
        generated_actionable,
        generated_pending if generated_actionable <= 0 else 0,
    )
    core_gate, core_gate_source = _core_gate_from_owner(evidence)
    core_gate_ok = _as_bool(core_gate.get("ok"), False)

    owner_verdicts = [
        _verdict(
            "validation",
            ready=validation_fresh,
            source="validation_artifact_truth",
            blockers=[]
            if validation_fresh
            else [
                _blocker(
                    "validation",
                    "validation_truth_missing",
                    detail=_text(validation.get("status"), 160),
                    source="validation_artifact_truth",
                )
            ],
            summary=_text(validation.get("status"), 160) or "validation artifact truth",
            evidence={"status": _text(validation.get("status"), 120), "ok": _as_bool(validation.get("ok"), False)},
        ),
        _verdict(
            "regression",
            ready=regression_current,
            source="runtime/regression_status.json",
            blockers=[]
            if regression_current
            else [
                _blocker(
                    "regression",
                    "regression_stale",
                    detail=_text(evidence.get("last_regression_status"), 160),
                    source="runtime/regression_status.json",
                )
            ],
            summary=_text(evidence.get("last_regression_status"), 160) or "regression status missing",
            evidence={
                "status": _text(evidence.get("last_regression_status"), 80),
                "stale": _as_bool(evidence.get("last_regression_stale"), False),
            },
        ),
        _verdict(
            "release",
            ready=release_truth_current,
            source="release_runtime_truth",
            blockers=[]
            if release_truth_current
            else [
                _blocker(
                    "release",
                    "release_truth_stale",
                    detail=_text(
                        _as_dict(evidence.get("release_runtime_truth")).get("runtime_drift_reason"),
                        160,
                    ),
                    source="release_runtime_truth",
                )
            ],
            summary=_text(
                _as_dict(evidence.get("release_runtime_truth")).get("running_build_identity")
                or _as_dict(evidence.get("release_status")).get("latest_artifact_name"),
                180,
            )
            or "release runtime truth missing",
            evidence=dict(_as_dict(evidence.get("release_runtime_truth"))),
        ),
        _verdict(
            "generated_queue",
            ready=generated_untested <= 0,
            source="generated_work_queue",
            blockers=[]
            if generated_untested <= 0
            else [
                _blocker(
                    "generated_queue",
                    "generated_queue_untested",
                    detail=f"{generated_untested} untested generated queue item(s)",
                    source="generated_work_queue",
                )
            ],
            summary="generated queue clear" if generated_untested <= 0 else "generated queue needs testing",
            evidence={"untested_count": generated_untested},
        ),
    ]

    layer_blockers: list[dict[str, Any]] = []
    require_core_gate = _as_bool(policy.get("require_core_gate_for_green"), True)
    if require_core_gate and not core_gate_ok:
        if _as_bool(core_gate.get("drift_blocked"), False):
            layer_blockers.append(
                _blocker(
                    "layer_maturity",
                    "core_gate_release_drift",
                    source=core_gate_source,
                )
            )
        elif list(core_gate.get("missing_roots") or []):
            layer_blockers.append(
                _blocker(
                    "layer_maturity",
                    "core_gate_roots_blocked",
                    detail=", ".join(str(item) for item in list(core_gate.get("missing_roots") or [])[:8]),
                    source=core_gate_source,
                )
            )
    owner_verdicts.append(
        _verdict(
            "layer_maturity",
            ready=not layer_blockers,
            source=core_gate_source,
            blockers=layer_blockers,
            summary="core gate ready" if not layer_blockers else "core gate blocked",
            evidence={"core_gate": core_gate, "require_core_gate": require_core_gate},
        )
    )

    explicit_verdicts = _normalize_owner_verdicts(evidence.get("owner_verdicts"))
    if explicit_verdicts:
        explicit_by_owner = {
            _text(verdict.get("owner"), 80): verdict
            for verdict in explicit_verdicts
            if _text(verdict.get("owner"), 80)
        }
        owner_verdicts = [
            explicit_by_owner.pop(_text(verdict.get("owner"), 80), verdict)
            for verdict in owner_verdicts
        ]
        owner_verdicts.extend(explicit_by_owner.values())

    ready_by_owner = {
        _text(verdict.get("owner"), 80): _as_bool(verdict.get("ready"), False)
        for verdict in owner_verdicts
        if _text(verdict.get("owner"), 80)
    }
    validation_fresh = ready_by_owner.get("validation", validation_fresh)
    regression_current = ready_by_owner.get("regression", regression_current)
    release_truth_current = ready_by_owner.get("release", release_truth_current)

    blockers = _owner_blockers(owner_verdicts)
    truth_ready = all(
        _as_bool(verdict.get("ready"), False) or not _as_bool(verdict.get("blocks_green"), True)
        for verdict in owner_verdicts
    )
    green_blockers = [
        blocker
        for verdict in owner_verdicts
        if _as_bool(_as_dict(verdict).get("blocks_green"), True)
        for blocker in _as_list(_as_dict(verdict).get("blockers"))
        if isinstance(blocker, dict)
    ]
    return {
        "truth_ready": truth_ready,
        "truth_blockers": _legacy_blocker_codes(owner_verdicts),
        "owner_verdicts": owner_verdicts,
        "owner_blockers": blockers,
        "green_blockers": green_blockers,
        "validation_fresh": validation_fresh,
        "regression_current": regression_current,
        "release_truth_current": release_truth_current,
        "generated_queue_untested_count": generated_untested,
        "core_gate_ok": core_gate_ok,
        "core_gate": core_gate,
        "core_gate_source": core_gate_source,
    }
