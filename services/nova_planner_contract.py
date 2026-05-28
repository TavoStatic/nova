from __future__ import annotations

import json
import time
from typing import Callable

from services.work_tree_seeding import WORK_TREE_SEEDING_SERVICE


MIN_NO_ARG_TOOL_CONFIDENCE = 0.70


def _active_work_tree_id(*, pending_action: dict | None, session) -> str:
    if hasattr(session, "active_work_tree_id"):
        tree_id = str(getattr(session, "active_work_tree_id", "") or "").strip()
        if tree_id:
            return tree_id
    pending = pending_action if isinstance(pending_action, dict) else {}
    return str(pending.get("work_tree_id") or "").strip()


def _active_work_identity(*, pending_action: dict | None, session) -> str:
    if hasattr(session, "active_work_identity"):
        identity = str(getattr(session, "active_work_identity", "") or "").strip()
        if identity:
            return identity
    pending = pending_action if isinstance(pending_action, dict) else {}
    return str(pending.get("work_identity_key") or "").strip()


def _format_work_tree_reply(step: dict | None) -> str:
    if step is None:
        return "The active work tree is complete."
    action = str(step.get("action") or "").strip()
    if action == "created":
        snapshot_text = str(step.get("snapshot_text") or "").strip()
        return snapshot_text or "Created a new work tree."
    if action == "inspect":
        snapshot_text = str(step.get("snapshot_text") or "").strip()
        return snapshot_text or "The active work tree is ready."
    if action == "executed":
        tool_name = str(step.get("tool") or "tool").strip()
        result = str(step.get("tool_result") or "").strip()
        if result:
            return result
        task_title = str(step.get("task_title") or step.get("branch_title") or "next task").strip()
        return f"Executed {tool_name} for {task_title}."
    if action == "tool_failed":
        error = str(step.get("error") or "unknown error").strip()
        tool_name = str(step.get("tool") or "tool").strip()
        return f"Work tree tool {tool_name} failed: {error}"
    if str(step.get("action") or "") == "wait_for_tools":
        missing = [str(item).strip() for item in list(step.get("missing_tools") or []) if str(item).strip()]
        missing_text = ", ".join(missing) if missing else "required tools"
        return f"The next work tree branch is waiting for tools: {missing_text}."
    if action == "governance_blocked":
        tool_name = str(step.get("recommended_tool") or "tool").strip() or "tool"
        reason = str(step.get("reason") or "blocked").strip()
        branch_title = str(step.get("branch_title") or step.get("branch_id") or "next branch").strip()
        return f"The next work tree step is governance-blocked on {branch_title}: {tool_name} ({reason})."
    if action == "no_tool_selected":
        branch_title = str(step.get("branch_title") or step.get("branch_id") or "next branch").strip()
        return f"The next work tree step has no governed tool selected for {branch_title}."
    branch_title = str(step.get("branch_title") or step.get("branch_id") or "next branch").strip()
    recommended_tool = str(step.get("recommended_tool") or "").strip()
    if recommended_tool:
        return f"Next work tree step: {branch_title}. Recommended tool: {recommended_tool}."
    return f"Next work tree step: {branch_title}."


def _parse_system_check_payload(tool_output: str) -> dict:
    try:
        payload = json.loads(str(tool_output or "").strip())
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _system_check_rows(payload: dict) -> list[dict]:
    rows: list[dict] = []
    for name, value in payload.items():
        if name in {"ok", "profile"} or not isinstance(value, dict):
            continue
        if "ok" not in value and "info" not in value:
            continue
        rows.append(
            {
                "name": str(name or "").strip(),
                "ok": bool(value.get("ok")),
                "info": str(value.get("info") or "").strip(),
                "required": bool(value.get("required", True)),
            }
        )
    return rows


def _render_system_check_reply(tool_output: str) -> tuple[str, dict]:
    payload = _parse_system_check_payload(tool_output)
    if not payload:
        return str(tool_output or ""), {}

    rows = _system_check_rows(payload)
    overall_ok = bool(payload.get("ok"))
    profile = str(payload.get("profile") or "").strip()
    lines = [f"System check: {'OK' if overall_ok else 'needs attention'}."]
    if profile:
        lines.append(f"Profile: {profile}.")
    if rows:
        lines.append("Evidence:")
        for row in rows:
            state = "ok" if row.get("ok") else "attention"
            info = str(row.get("info") or "").strip()
            required = "" if bool(row.get("required", True)) else " optional"
            suffix = f" ({info})" if info else ""
            lines.append(f"- {row.get('name')}: {state}{required}{suffix}")
    needs_attention = [str(row.get("name") or "") for row in rows if not bool(row.get("ok")) and bool(row.get("required", True))]
    if needs_attention:
        lines.append("Needs attention: " + ", ".join(needs_attention) + ".")
    return "\n".join(lines).strip(), {
        "ok": overall_ok,
        "profile": profile,
        "checks": rows,
    }


def build_planner_config(
    *,
    turns: list[tuple[str, str]],
    pending_action: dict | None,
    prefer_web_for_data_queries: bool,
) -> dict:
    return {
        "session_turns": turns,
        "pending_action": pending_action or {},
        "prefer_web_for_data_queries": prefer_web_for_data_queries,
    }


def _route_evidence(*, owner: str, action_type: str, tool: str = "") -> dict:
    payload = {
        "final_owner": owner,
        "planner_owner": owner,
        "planner_action": action_type,
    }
    if tool:
        payload["planner_tool"] = tool
    return payload


def _actions_from_semantic_tool_intent(intent: dict | None) -> list[dict]:
    payload = intent if isinstance(intent, dict) else {}
    tool = str(payload.get("tool") or "").strip()
    if not tool or tool == "none":
        return []
    args = payload.get("args")
    normalized_args = [str(item).strip() for item in list(args or []) if str(item).strip()] if isinstance(args, list) else []
    if tool in {"work_tree_next", "work_tree_execute", "work_tree_status", "work_tree_create"}:
        return [{"type": "work_tree", "tool": tool, "args": normalized_args, "semantic_intent": dict(payload)}]
    return [{"type": "run_tool", "tool": tool, "args": normalized_args, "semantic_intent": dict(payload)}]


def _floatish(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _semantic_tool_intent_has_authority(intent: dict | None) -> bool:
    payload = intent if isinstance(intent, dict) else {}
    tool = str(payload.get("tool") or "").strip()
    if not tool or tool == "none":
        return False
    answer_target = str(payload.get("answer_target") or "").strip()
    evidence_need = str(payload.get("evidence_need") or "").strip()
    if tool == "self_status":
        return answer_target == "nova_live_state" and evidence_need == "live_self_status"
    args = [str(item).strip() for item in list(payload.get("args") or []) if str(item).strip()] if isinstance(payload.get("args"), list) else []
    confidence = _floatish(payload.get("confidence"), 0.0)
    if not args and confidence < MIN_NO_ARG_TOOL_CONFIDENCE:
        return False
    if tool in {"web_fetch", "web_gather", "read", "find", "location_coords", "patch_apply", "update_now_confirm"}:
        return bool(args)
    return True


def _classify_semantic_tool_actions(
    *,
    text: str,
    turns: list[tuple[str, str]],
    pending_action: dict | None,
    turn_acts: list[str] | None = None,
    core,
    trace: Callable[..., None],
    semantic_tool_observer_fn: Callable[[dict], None] | None = None,
) -> tuple[list[dict], int, str]:
    classify_tool_intent_fn = getattr(core, "_llm_classify_routing_intent", None)
    if not callable(classify_tool_intent_fn):
        return [], 0, "unavailable"
    del turn_acts
    semantic_started = time.perf_counter()
    try:
        semantic_intent = classify_tool_intent_fn(
            text,
            turns=turns,
            pending_action=pending_action,
            return_none_payload=True,
        )
    except TypeError:
        try:
            semantic_intent = classify_tool_intent_fn(text, turns=turns)
        except Exception:
            semantic_intent = None
    except Exception:
        semantic_intent = None
    semantic_ms = int((time.perf_counter() - semantic_started) * 1000)
    trace("timing", "completed", "semantic_tool_intent", duration_ms=semantic_ms)
    def _observe(status: str, payload: dict | None = None) -> None:
        if not callable(semantic_tool_observer_fn):
            return
        try:
            semantic_tool_observer_fn(
                {
                    "status": str(status or "").strip(),
                    "intent": dict(payload or {}) if isinstance(payload, dict) else {},
                    "duration_ms": semantic_ms,
                }
            )
        except Exception:
            return

    if isinstance(semantic_intent, dict) and str(semantic_intent.get("tool") or "").strip() == "none":
        _observe("none", semantic_intent)
        trace(
            "action_planner",
            "semantic_none",
            str(semantic_intent.get("reason") or ""),
            confidence=_floatish(semantic_intent.get("confidence"), 0.0),
        )
        return [], semantic_ms, "none"
    semantic_actions = _actions_from_semantic_tool_intent(semantic_intent)
    if semantic_actions:
        if not _semantic_tool_intent_has_authority(semantic_intent):
            weak_payload = {
                "tool": "none",
                "args": [],
                "confidence": _floatish((semantic_intent or {}).get("confidence"), 0.0),
                "reason": "weak_tool_route",
                "evidence_need": "conversation",
                "answer_target": "current_conversation",
                "source": "blocked_tool_route",
            }
            _observe("weak_tool_route", weak_payload)
            trace(
                "action_planner",
                "semantic_weak_tool_route",
                "",
                tool=str((semantic_intent or {}).get("tool") or ""),
                confidence=_floatish((semantic_intent or {}).get("confidence"), 0.0),
            )
            return [], semantic_ms, "weak_tool_route"
        _observe("tool", semantic_intent)
        trace(
            "action_planner",
            "semantic_intent",
            str((semantic_intent or {}).get("reason") or ""),
            tool=str((semantic_intent or {}).get("tool") or ""),
            confidence=_floatish((semantic_intent or {}).get("confidence"), 0.0),
        )
        return semantic_actions, semantic_ms, "tool"
    _observe("unavailable", semantic_intent if isinstance(semantic_intent, dict) else {})
    return [], semantic_ms, "unavailable"


def _handle_semantic_work_tree_action(
    *,
    action: dict,
    text: str,
    pending_action: dict | None,
    session,
    core,
    trace: Callable[..., None],
    normalize_reply: Callable[[str], str],
    ensure_active_work_tree_fn: Callable[[str], str] | None = None,
) -> tuple[str, dict] | None:
    work_tree_started = time.perf_counter()
    tool = str(action.get("tool") or "").strip()
    semantic_args = action.get("args")
    seed_text = " ".join(str(item).strip() for item in list(semantic_args or []) if str(item).strip()) if isinstance(semantic_args, list) else ""
    if not seed_text:
        seed_text = str(text or "")
    tree_id = _active_work_tree_id(pending_action=pending_action, session=session)
    active_identity = _active_work_identity(pending_action=pending_action, session=session)
    if tool == "work_tree_create" and not tree_id and callable(ensure_active_work_tree_fn):
        tree_id = str(ensure_active_work_tree_fn(seed_text) or "").strip()
    if tree_id and hasattr(session, "set_active_work_tree_id"):
        try:
            session.set_active_work_tree_id(tree_id)
        except Exception:
            pass
    if tree_id and tool in {"work_tree_next", "work_tree_execute", "work_tree_status"} and hasattr(session, "set_last_work_continuity"):
        try:
            session.set_last_work_continuity("continuing_existing_work")
        except Exception:
            pass
    if tree_id and hasattr(session, "set_active_work_identity") and not active_identity:
        inferred_identity = WORK_TREE_SEEDING_SERVICE.build_work_identity_key(seed_text)
        if inferred_identity:
            try:
                session.set_active_work_identity(inferred_identity)
                active_identity = inferred_identity
            except Exception:
                pass
    if not tree_id:
        reply = "No active Work Tree is selected."
        return normalize_reply(reply), {
            "planner_decision": "work_tree",
            "tool": tool,
            "tool_args": {"query": seed_text},
            "tool_result": "",
            "grounded": False,
            "pending_action": dict(pending_action or {}),
            "route_evidence": _route_evidence(owner="work_tree", action_type="no_active_tree", tool=tool),
        }
    try:
        import work_tree
    except Exception:
        return None
    if tool == "work_tree_create":
        step = {
            "action": "created",
            "tree_id": tree_id,
            "snapshot_text": work_tree.format_tree_snapshot(tree_id),
        }
    elif tool == "work_tree_status":
        step = {
            "action": "inspect",
            "tree_id": tree_id,
            "snapshot_text": work_tree.format_tree_snapshot(tree_id),
        }
    elif tool == "work_tree_execute":
        step_started = time.perf_counter()
        step = work_tree.execute_autonomous_step(tree_id, execute_planned_action_fn=core.execute_planned_action)
        trace("timing", "completed", "work_tree_step", duration_ms=int((time.perf_counter() - step_started) * 1000))
    else:
        step_started = time.perf_counter()
        step = work_tree.next_autonomous_step(tree_id)
        trace("timing", "completed", "work_tree_step", duration_ms=int((time.perf_counter() - step_started) * 1000))
    action_type = str((step or {}).get("action") or tool or "work_tree")
    trace("work_tree", "semantic_matched", detail=action_type)
    trace("timing", "completed", "work_tree_sequence", duration_ms=int((time.perf_counter() - work_tree_started) * 1000))
    reply = _format_work_tree_reply(step)
    return normalize_reply(reply), {
        "planner_decision": "work_tree",
        "tool": str((step or {}).get("recommended_tool") or tool or "work_tree"),
        "tool_args": {"tree_id": tree_id},
        "tool_result": json.dumps(step, ensure_ascii=True) if isinstance(step, dict) else "",
        "grounded": True,
        "pending_action": {
            **dict(pending_action or {}),
            "work_tree_id": tree_id,
            "work_identity_key": active_identity or WORK_TREE_SEEDING_SERVICE.build_work_identity_key(seed_text),
        },
        "route_evidence": _route_evidence(owner="work_tree", action_type=action_type, tool=str((step or {}).get("recommended_tool") or tool)),
    }


def _weather_location_available(core) -> bool:
    available_fn = getattr(core, "_weather_current_location_available", None)
    if not callable(available_fn):
        return True
    try:
        return bool(available_fn())
    except Exception:
        return True


def _pending_weather_action(core) -> dict:
    pending_fn = getattr(core, "make_pending_weather_action", None)
    if callable(pending_fn):
        try:
            pending = pending_fn()
            if isinstance(pending, dict):
                return pending
        except Exception:
            pass
    return {"kind": "weather_lookup", "status": "awaiting_location", "preferred_tool": "weather_location"}


def _intent_continues_same_tool_evidence(intent: dict | None, tool: str) -> bool:
    payload = intent if isinstance(intent, dict) else {}
    return (
        str(payload.get("answer_target") or "").strip() == "nova_live_state"
        and str(payload.get("evidence_need") or "").strip() == "live_self_status"
        and str(payload.get("tool") or "").strip() == str(tool or "").strip()
    )


def _session_has_tool_evidence(session, tool: str, *, semantic_intent: dict | None = None) -> bool:
    state = getattr(session, "conversation_state", None)
    if not isinstance(state, dict):
        return False
    if str(state.get("kind") or "").strip() != "last_tool_evidence":
        return False
    if str(state.get("tool") or "").strip() != str(tool or "").strip():
        return False
    if not _intent_continues_same_tool_evidence(semantic_intent, tool):
        return False
    return bool(str(state.get("tool_result") or "").strip())


def merge_route_evidence(routing_decision: dict | None, meta: dict | None) -> dict | None:
    if not isinstance(meta, dict):
        return routing_decision
    route_evidence = meta.get("route_evidence")
    if not isinstance(route_evidence, dict) or not route_evidence:
        return routing_decision
    payload = dict(routing_decision or {})
    payload.update(route_evidence)
    return payload


def maybe_handle_planner_sequence(
    *,
    text: str,
    turns: list[tuple[str, str]],
    pending_action: dict | None,
    turn_acts: list[str] | None = None,
    prefer_web_for_data_queries: bool,
    session,
    core,
    trace: Callable[..., None],
    normalize_reply: Callable[[str], str],
    ensure_active_work_tree_fn: Callable[[str], str] | None = None,
    work_tree_seed_source: str = "",
    work_tree_seed_mode: str = "",
    semantic_tool_observer_fn: Callable[[dict], None] | None = None,
) -> tuple[str, dict] | None:
    planner_started = time.perf_counter()
    tool_selection_ms = 0
    tool_time_ms = 0

    def _planner_elapsed_ms() -> int:
        return int((time.perf_counter() - planner_started) * 1000)

    def _record_tool_timing(tool_name: str, duration_ms: int) -> None:
        trace("timing", "completed", "tool_response", duration_ms=int(duration_ms or 0), tool=str(tool_name or ""))
        if str(tool_name or "").startswith("web"):
            trace("timing", "completed", "web_search", duration_ms=int(duration_ms or 0), tool=str(tool_name or ""))

    def _return_with_timing(reply: str, meta: dict) -> tuple[str, dict]:
        planner_ms = _planner_elapsed_ms()
        trace("timing", "completed", "planner", duration_ms=planner_ms)
        payload = dict(meta or {})
        timing = dict(payload.get("timing") or {})
        timing["planner_time"] = planner_ms
        timing["tool_selection_time"] = int(tool_selection_ms or 0)
        timing["tool_time"] = int(tool_time_ms or 0)
        payload["timing"] = timing
        return reply, payload

    del prefer_web_for_data_queries
    actions, semantic_ms, semantic_status = _classify_semantic_tool_actions(
        text=text,
        turns=turns,
        pending_action=pending_action,
        turn_acts=turn_acts,
        core=core,
        trace=trace,
        semantic_tool_observer_fn=semantic_tool_observer_fn,
    )
    tool_selection_ms += semantic_ms
    trace("timing", "completed", "tool_selection", duration_ms=tool_selection_ms)

    if actions:
        act = actions[0]
        atype = str(act.get("type") or "").strip()
        if atype == "ask_clarify":
            trace("action_planner", "ask_clarify")
            reply = act.get("question") or act.get("note") or "Can you clarify?"
            return _return_with_timing(normalize_reply(reply), {
                "planner_decision": "ask_clarify",
                "tool": "",
                "tool_args": {"query": text},
                "tool_result": str(reply or ""),
                "grounded": False,
                "pending_action": {},
                "route_evidence": _route_evidence(owner="action_planner", action_type=atype),
            })

        if atype == "respond":
            trace("action_planner", "respond")
            reply = act.get("note") or act.get("message") or "Tell me a bit more about what you want me to inspect."
            return _return_with_timing(normalize_reply(reply), {
                "planner_decision": "respond",
                "tool": "",
                "tool_args": {"query": text},
                "tool_result": str(reply or ""),
                "grounded": False,
                "route_evidence": _route_evidence(owner="action_planner", action_type=atype),
            })

        if atype == "work_tree":
            trace("action_planner", "work_tree", tool=str(act.get("tool") or ""))
            work_tree_action = _handle_semantic_work_tree_action(
                action=act,
                text=text,
                pending_action=pending_action,
                session=session,
                core=core,
                trace=trace,
                normalize_reply=normalize_reply,
                ensure_active_work_tree_fn=ensure_active_work_tree_fn,
            )
            if work_tree_action is not None:
                return _return_with_timing(work_tree_action[0], work_tree_action[1])

        if atype == "run_tool":
            tool = str(act.get("tool") or "")
            args = act.get("args") or []
            trace("action_planner", "run_tool", tool=tool)
            normalized_args = [str(item).strip() for item in list(args or []) if str(item).strip()] if isinstance(args, list) else []
            semantic_intent = act.get("semantic_intent") if isinstance(act.get("semantic_intent"), dict) else {}
            if not normalized_args and _session_has_tool_evidence(session, tool, semantic_intent=semantic_intent):
                if callable(semantic_tool_observer_fn):
                    semantic_tool_observer_fn(
                        {
                            "status": "prior_tool_evidence_present",
                            "intent": {
                                "tool": "none",
                                "args": [],
                                "confidence": 0.0,
                                "reason": "prior_tool_evidence_present",
                                "evidence_need": "conversation",
                                "answer_target": "current_conversation",
                                "source": "prior_tool_evidence",
                            },
                        }
                    )
                trace("action_planner", "prior_tool_evidence_present", tool=tool)
                return None
            if tool == "weather_current_location" and not _weather_location_available(core):
                reply = "What location should I use for the weather lookup?"
                return _return_with_timing(normalize_reply(reply), {
                    "planner_decision": "ask_clarify",
                    "tool": "",
                    "tool_args": {"query": text},
                    "tool_result": str(reply or ""),
                    "grounded": False,
                    "pending_action": _pending_weather_action(core),
                    "route_evidence": _route_evidence(owner="action_planner", action_type="semantic_weather_needs_location"),
                    "reply_contract": "weather_lookup.clarify",
                    "reply_outcome": {
                        "intent": "weather_lookup",
                        "kind": "needs_location",
                        "reply_contract": "weather_lookup.clarify",
                    },
                })
            tool_started = time.perf_counter()
            out = core.execute_planned_action(tool, args)
            tool_time_ms = int((time.perf_counter() - tool_started) * 1000)
            _record_tool_timing(tool, tool_time_ms)
            route_evidence = _route_evidence(owner="action_planner", action_type=atype, tool=tool)
            if out is None or (isinstance(out, str) and not out.strip()):
                trace("tool_execution", "empty_result", tool=tool)
                reply = core._web_allowlist_message("requested resource") if tool.startswith("web") else f"The {tool} tool did not return a result. No data was available."
                return _return_with_timing(normalize_reply(reply), {
                    "planner_decision": "run_tool",
                    "tool": tool,
                    "tool_args": {"args": list(args) if isinstance(args, (list, tuple)) else args},
                    "tool_result": "",
                    "grounded": False,
                    "pending_action": {},
                    "route_evidence": route_evidence,
                })
            if isinstance(out, dict) and not out.get("ok", True):
                trace("tool_execution", "error", tool=tool, error=str(out.get("error") or "unknown error"))
                err = out.get("error", "unknown error")
                if isinstance(err, str) and ("not allowed" in err.lower() or "domain not allowed" in err.lower()):
                    reply = core._web_allowlist_message(args[0] if args else "")
                else:
                    reply = f"Tool {tool} failed: {err}"
                return _return_with_timing(normalize_reply(reply), {
                    "planner_decision": "run_tool",
                    "tool": tool,
                    "tool_args": {"args": list(args) if isinstance(args, (list, tuple)) else args},
                    "tool_result": json.dumps(out, ensure_ascii=True),
                    "grounded": False,
                    "pending_action": {},
                    "route_evidence": route_evidence,
                })
            rendered_out = str(out or "")
            if tool == "web_research" and hasattr(core, "_ground_web_research_reply"):
                grounded_out = core._ground_web_research_reply(text, rendered_out)
                if grounded_out:
                    rendered_out = grounded_out
            reply_contract = ""
            reply_outcome: dict[str, object] = {}
            if tool == "weather_current_location":
                reply_contract = "weather_lookup.current_location"
                reply_outcome = {
                    "intent": "weather_lookup",
                    "kind": "current_location",
                    "reply_contract": reply_contract,
                }
            elif tool == "weather_location":
                reply_contract = "weather_lookup.explicit_location"
                location_value = str(args[0] if isinstance(args, (list, tuple)) and args else "").strip()
                reply_outcome = {
                    "intent": "weather_lookup",
                    "kind": "explicit_location",
                    "reply_contract": reply_contract,
                    "location_value": location_value,
                }
            elif tool == "self_status":
                reply_contract = "self_status.current"
                reply_outcome = {
                    "intent": "self_status",
                    "kind": "current",
                    "reply_contract": reply_contract,
                }
                trace("tool_execution", "ok", tool=tool, grounded=bool(rendered_out.strip()))
                return _return_with_timing("", {
                    "planner_decision": "tool_evidence_for_fallback",
                    "tool": tool,
                    "tool_args": {"args": list(args) if isinstance(args, (list, tuple)) else args},
                    "tool_result": rendered_out,
                    "grounded": bool(rendered_out.strip()),
                    "pending_action": {},
                    "route_evidence": route_evidence,
                    "reply_contract": reply_contract,
                    "reply_outcome": reply_outcome,
                    "defer_to_fallback": True,
                })
            elif tool == "system_check":
                reply_contract = "system_check.current"
                rendered_reply, evidence = _render_system_check_reply(rendered_out)
                if rendered_reply:
                    rendered_out = rendered_reply
                reply_outcome = {
                    "intent": "system_check",
                    "kind": "current",
                    "reply_contract": reply_contract,
                }
                if evidence:
                    reply_outcome["evidence"] = evidence
            trace("tool_execution", "ok", tool=tool, grounded=bool(rendered_out.strip()))
            return _return_with_timing(normalize_reply(rendered_out), {
                "planner_decision": "run_tool",
                "tool": tool,
                "tool_args": {"args": list(args) if isinstance(args, (list, tuple)) else args},
                "tool_result": rendered_out,
                "grounded": bool(rendered_out.strip()),
                "pending_action": {},
                "route_evidence": route_evidence,
                "reply_contract": reply_contract,
                "reply_outcome": reply_outcome,
            })

    return None
