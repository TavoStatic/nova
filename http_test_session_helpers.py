from __future__ import annotations

from typing import Any, Callable, Mapping


def generated_queue_operator_note(item: Mapping[str, Any]) -> str:
    selected = item if isinstance(item, Mapping) else {}
    latest_comparison = selected.get("latest_comparison") if isinstance(selected.get("latest_comparison"), Mapping) else {}
    diffs = list(latest_comparison.get("diffs") or []) if isinstance(latest_comparison, Mapping) else []
    highest = selected.get("highest_priority") if isinstance(selected.get("highest_priority"), Mapping) else {}

    lines = [
        f"Investigate generated queue item: {str(selected.get('file') or 'unknown').strip() or 'unknown'}",
        f"Family: {str(selected.get('family_id') or 'n/a').strip() or 'n/a'} | variation: {str(selected.get('variation_id') or 'n/a').strip() or 'n/a'}",
        f"Latest status: {str(selected.get('latest_status') or 'unknown').strip() or 'unknown'} | reason: {str(selected.get('opportunity_reason') or 'n/a').strip() or 'n/a'}",
    ]
    if highest:
        lines.append(
            "Highest priority: "
            + f"{str(highest.get('signal') or 'signal')} [{str(highest.get('urgency') or 'n/a')}]"
            + f" | seam={str(highest.get('seam') or 'n/a')}"
            + f" | robustness={float(highest.get('robustness', 0.0) or 0.0):.2f}"
        )
    report_path = str(selected.get("latest_report_path") or "").strip()
    if report_path:
        lines.append(f"Latest report path: {report_path}")
    if diffs:
        lines.append("Recent drift summary:")
        for diff in diffs[:3]:
            if not isinstance(diff, Mapping):
                continue
            turn = int(diff.get("turn", 0) or 0)
            issues = diff.get("issues") if isinstance(diff.get("issues"), Mapping) else {}
            fields = ", ".join(sorted(str(key) for key in issues.keys())) or "unknown"
            lines.append(f"- turn {turn}: {fields}")
    lines.append("Use the latest report artifact and recommend the smallest concrete fix or next validation step.")
    return "\n".join(lines)


def investigate_generated_work_queue_item(
    *,
    session_file: str = "",
    session_id: str = "",
    user_id: str = "operator",
    generated_work_queue: Callable[[int], dict],
    resolve_operator_macro: Callable[[str], Any],
    render_operator_macro_prompt: Callable[[Any, dict, str], tuple[bool, str, dict[str, str]]],
    normalize_user_id: Callable[[str], str],
    assert_session_owner: Callable[[str, str], tuple[bool, str]],
    process_chat: Callable[[str, str, str], str],
    session_summaries: Callable[[int], list[dict]],
) -> tuple[bool, str, dict]:
    queue_payload = generated_work_queue(24)
    selected: dict[str, Any] = {}
    requested_file = str(session_file or "").strip()
    if requested_file:
        selected = next((dict(item) for item in list(queue_payload.get("items") or []) if str(item.get("file") or "") == requested_file), {})
    if not selected:
        selected = dict(queue_payload.get("next_item") or {})
    if not selected:
        return False, "generated_work_queue_investigation_no_open_item", {"work_queue": queue_payload}

    macro = resolve_operator_macro("subconscious-review")
    operator_note = generated_queue_operator_note(selected)
    resolved_macro_values: dict[str, str] = {}
    if macro is not None:
        ok_macro, rendered_message, resolved_macro_values = render_operator_macro_prompt(macro, {}, note=operator_note)
        if not ok_macro:
            rendered_message = operator_note
    else:
        rendered_message = operator_note

    effective_session_id = str(session_id or "").strip() or "operator-generated-queue"
    normalized_user = normalize_user_id(str(user_id or "operator")) or "operator"
    ok_owner, reason_owner = assert_session_owner(effective_session_id, normalized_user)
    if not ok_owner:
        return False, reason_owner, {"session_id": effective_session_id, "selected": selected, "work_queue": queue_payload}

    try:
        reply = process_chat(effective_session_id, rendered_message, user_id=normalized_user)
        sessions = session_summaries(80)
        session_summary = next((item for item in sessions if str(item.get("session_id") or "") == effective_session_id), None)
        return True, "generated_work_queue_investigation_started", {
            "selected": selected,
            "session_id": effective_session_id,
            "user_id": normalized_user,
            "macro": dict(macro or {}),
            "resolved_macro_values": resolved_macro_values,
            "message": rendered_message,
            "reply": reply,
            "session": session_summary or {},
            "sessions": sessions,
            "work_queue": generated_work_queue(24),
        }
    except Exception as e:
        return False, f"generated_work_queue_investigation_failed:{e}", {
            "selected": selected,
            "session_id": effective_session_id,
            "work_queue": queue_payload,
        }
