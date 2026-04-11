from __future__ import annotations


def handle_commands(
    user_text: str,
    *,
    session_turns=None,
    session=None,
    core,
):
    t = core._strip_invocation_prefix((user_text or "").strip())
    low = t.lower()

    if low in {"chat context", "show chat context", "context", "chatctx"}:
        rendered = core._render_chat_context(session_turns or [])
        if not rendered:
            return "No chat context is available yet in this session."
        return "Current chat context:\n" + rendered

    if low in {"queue", "queue status", "work queue", "show queue", "standing work queue"}:
        return str(core.execute_planned_action("queue_status") or "")

    if low in {"pulse", "nova pulse", "show pulse", "system pulse"}:
        return str(core.execute_planned_action("pulse") or "")

    if low in {"update now", "apply update now", "apply updates now"}:
        return str(core.execute_planned_action("update_now") or "")

    if low.startswith("update now confirm"):
        token = t.split(maxsplit=3)[3].strip() if len(t.split(maxsplit=3)) >= 4 else ""
        args = [token] if token else []
        return str(core.execute_planned_action("update_now_confirm", args) or "")

    if low in {"update now cancel", "cancel update now"}:
        return str(core.execute_planned_action("update_now_cancel") or "")

    if "domanins" in low and any(k in low for k in ["domain", "domanins", "allow", "policy", "list", "show"]):
        return "It looks like you meant \"domains\".\n" + core.list_allowed_domains()

    if low in {"domains", "list domains", "show domains", "list the domains", "allowed domains", "allow domains", "policy domains"}:
        return core.list_allowed_domains()

    if low.startswith("policy allow "):
        value = t.split(maxsplit=2)[2] if len(t.split(maxsplit=2)) >= 3 else ""
        return core.policy_allow_domain(value)

    if low.startswith("policy remove "):
        value = t.split(maxsplit=2)[2] if len(t.split(maxsplit=2)) >= 3 else ""
        return core.policy_remove_domain(value)

    if low.startswith("policy audit"):
        parts = t.split()
        n = 20
        if len(parts) >= 3:
            try:
                n = int(parts[2])
            except Exception:
                n = 20
        return core.policy_audit(n)

    if low in {"web mode", "web limits", "web research limits"}:
        return core.web_mode_status()

    if low.startswith("web mode "):
        mode = t.split(maxsplit=2)[2] if len(t.split(maxsplit=2)) >= 3 else ""
        return core.set_web_mode(mode)

    if low.startswith("location coords ") or low.startswith("set location coords "):
        value = t.split(maxsplit=2)[2] if len(t.split(maxsplit=2)) >= 3 else ""
        return core.set_location_coords(value)

    if low in {"weather", "check weather", "weather current location", "weather current"}:
        return str(core.execute_planned_action("weather_current_location") or "")

    if low.startswith("weather ") or low.startswith("check weather "):
        parts = t.split(maxsplit=2)
        location_value = parts[2] if len(parts) >= 3 else (parts[1] if len(parts) >= 2 else "")
        return str(core.execute_planned_action("weather_location", [location_value]) or "")

    normalized = core._normalize_turn_text(t)
    if normalized in {"use your physical location", "use your location nova", "use your location"}:
        return str(core.execute_planned_action("weather_current_location") or "")

    if core._is_saved_location_weather_query(normalized) or (
        "weather" in normalized and any(phrase in normalized for phrase in (
            "give me",
            "can you give me",
            "what is",
            "what's",
            "forecast",
            "current",
            "today",
            "now",
        ))
    ):
        live = core.runtime_device_location_payload()
        if (live.get("available") and not live.get("stale")) or core.get_saved_location_text() or core._coords_from_saved_location():
            return str(core.execute_planned_action("weather_current_location") or "")
        return core._need_confirmed_location_message() + " My location is unknown until live tracking is active, or you tell me or save coordinates."

    if core._is_location_request(normalized):
        return core._location_reply()

    if low.startswith("remember:"):
        return core.mem_remember_fact(t.split(":", 1)[1])

    if low in {"what can you do", "capabilities", "show capabilities"}:
        return core.describe_capabilities()

    if low in {"mem stats", "memory stats"}:
        return core.mem_stats()

    if low in {"mix", "mix status", "language status", "spanglish status"}:
        current = int(getattr(session, "language_mix_spanish_pct", 0) or 0)
        return f"Language mix status: English default with Spanish mix at {current}%"

    if low.startswith("set mix "):
        m = core.re.search(r"set\s+mix\s+(\d{1,3})", low)
        if not m:
            return "Usage: set mix <0-100>"
        value = core._clamp_language_mix(int(m.group(1)))
        if session is not None:
            session.set_language_mix_spanish_pct(value)
        return f"Language mix updated: Spanish {value}% (English {100 - value}%)"

    if low in {"more spanish", "more espanol", "mas espanol"}:
        current = int(getattr(session, "language_mix_spanish_pct", 0) or 0)
        value = core._clamp_language_mix(current + 20)
        if session is not None:
            session.set_language_mix_spanish_pct(value)
        return f"Language mix nudged toward Spanish: {value}%"

    if low in {"more english", "menos espanol"}:
        current = int(getattr(session, "language_mix_spanish_pct", 0) or 0)
        value = core._clamp_language_mix(current - 20)
        if session is not None:
            session.set_language_mix_spanish_pct(value)
        return f"Language mix nudged toward English: Spanish {value}%"

    if low in {"english default", "default english", "english only"}:
        if session is not None:
            session.set_language_mix_spanish_pct(0)
        return "English is now the default response language for this session."

    if low.startswith("mem audit ") or low.startswith("memory audit "):
        q = t.split(maxsplit=2)[2] if len(t.split(maxsplit=2)) >= 3 else ""
        return core.mem_audit(q)

    if low == "kb" or low == "kb help":
        return (
            "KB commands:\n"
            "  kb list\n"
            "  kb use <pack>\n"
            "  kb off\n"
            "  kb add <zip_path> <pack_name>\n"
        )

    if low == "kb list":
        return core.kb_list_packs()

    if low.startswith("kb use "):
        name = t.split(maxsplit=2)[2].strip()
        return core.kb_set_active(name)

    if low == "kb off":
        return core.kb_set_active(None)

    if low.startswith("kb add "):
        parts = t.split(maxsplit=3)
        if len(parts) < 4:
            return "Usage: kb add <zip_path> <pack_name>"
        return core.kb_add_zip(parts[2], parts[3])

    if low == "patch" or low == "patch help":
        return (
            "Patch commands:\n"
            "  patch preview <zip_path>  # preview proposal without applying\n"
            "  patch apply <zip_path> [--force]\n"
            "      # preview runs automatically; use --force to bypass preview check\n"
            "  patch rollback   (roll back to last snapshot)\n"
        )
    if low.startswith("patch apply "):
        raw = t.split(maxsplit=2)[2].strip() if len(t.split(maxsplit=2)) >= 3 else ""
        force = False
        if "--force" in raw:
            force = True
            raw = raw.replace("--force", "").strip()
        return core.execute_patch_action("apply", raw, force=force, is_admin=True)

    if low.startswith("patch preview "):
        p = t.split(maxsplit=2)[2].strip() if len(t.split(maxsplit=2)) >= 3 else ""
        return core.execute_patch_action("preview", p, is_admin=True)

    if low == "patch list-previews":
        return core.execute_patch_action("list_previews", is_admin=True)

    if low.startswith("patch show "):
        p = t.split(maxsplit=2)[2].strip() if len(t.split(maxsplit=2)) >= 3 else ""
        return core.execute_patch_action("show", p, is_admin=True)

    if low.startswith("patch approve "):
        p = t.split(maxsplit=2)[2].strip() if len(t.split(maxsplit=2)) >= 3 else ""
        return core.execute_patch_action("approve", p, is_admin=True)

    if low.startswith("patch reject "):
        p = t.split(maxsplit=2)[2].strip() if len(t.split(maxsplit=2)) >= 3 else ""
        return core.execute_patch_action("reject", p, is_admin=True)

    if low == "patch rollback":
        return core.execute_patch_action("rollback", is_admin=True)

    if low == "kidney" or low == "kidney help":
        return (
            "Kidney commands:\n"
            "  kidney status\n"
            "  kidney now\n"
            "  kidney dry-run\n"
            "  kidney protect <pattern>\n"
        )

    if low == "kidney status":
        import kidney

        return kidney.render_status()

    if low in {
        "phase2",
        "phase2 status",
        "phase 2 status",
        "phase2 audit",
        "phase 2 audit",
        "post phase 2 audit",
        "post-phase-2 audit",
    }:
        return str(core.execute_planned_action("phase2_audit") or "")

    if low == "kidney now":
        import kidney

        return kidney.render_run(dry_run=False)

    if low == "kidney dry-run":
        import kidney

        return kidney.render_run(dry_run=True)

    if low.startswith("kidney protect "):
        import kidney

        pattern = t.split(maxsplit=2)[2].strip() if len(t.split(maxsplit=2)) >= 3 else ""
        return kidney.add_protect_pattern(pattern)

    if low.startswith("teach "):
        parts = t.split(maxsplit=1)
        sub = parts[1].strip() if len(parts) > 1 else ""
        if sub.startswith("remember "):
            body = sub[len("remember "):].strip()
            if "=>" in body:
                orig, corr = body.split("=>", 1)
                orig = orig.strip().strip("\"'")
                corr = corr.strip().strip("\"'")
                return core._teach_store_example(orig, corr)
            return "Usage: teach remember <original text> => <correction text>"

        if sub == "list":
            return core._teach_list_examples()

        if sub.startswith("propose"):
            desc = sub[len("propose"):].strip()
            return core._teach_propose_patch(desc)

        if sub.startswith("autoapply "):
            body = sub[len("autoapply "):].strip()
            apply_live = False
            zp = body
            if body.startswith("apply "):
                apply_live = True
                zp = body[len("apply "):].strip()
            elif "--apply" in body:
                apply_live = True
                zp = body.replace("--apply", "").strip()
            return core._teach_autoapply_proposal(zp, apply_live=apply_live)

        if sub.startswith("apply "):
            zp = sub[len("apply "):].strip()
            return core.execute_patch_action("apply", zp, is_admin=True)

        return (
            "Teach commands:\n"
            "  teach remember <orig> => <correction>\n"
            "  teach list\n"
            "  teach propose <description>\n"
            "  teach autoapply <zip>              # run staging tests (safe)\n"
            "  teach autoapply apply <zip>       # run staging tests and APPLY if tests pass\n"
            "  teach autoapply <zip> --apply     # same as above\n"
        )
    if low == "inspect":
        data = core.inspect_environment()
        return core.format_report(data)

    if low.startswith("casual_mode") or low.startswith("casual mode"):
        parts = low.replace("casual mode", "casual_mode").split()
        cmd = parts[1] if len(parts) > 1 else "status"
        statefile = core.DEFAULT_STATEFILE
        try:
            if cmd in {"on", "1", "true"}:
                core.os.environ["CASUAL_MODE"] = "1"
                core.set_core_state(statefile, "casual_mode", True)
                return "casual_mode enabled"
            if cmd in {"off", "0", "false"}:
                core.os.environ["CASUAL_MODE"] = "0"
                core.set_core_state(statefile, "casual_mode", False)
                return "casual_mode disabled"
            if cmd == "toggle":
                cur = core.os.environ.get("CASUAL_MODE", "1").lower() in {"1", "true"}
                nxt = not cur
                core.os.environ["CASUAL_MODE"] = "1" if nxt else "0"
                core.set_core_state(statefile, "casual_mode", bool(nxt))
                return f"casual_mode set to {core.os.environ['CASUAL_MODE']}"
            cur = core.os.environ.get("CASUAL_MODE", "1")
            return f"casual_mode={cur}"
        except Exception as e:
            return f"Failed to set casual_mode: {e}"

    if low in {"behavior stats", "behavior metrics", "behavior"}:
        return core.json.dumps(core.behavior_get_metrics(), ensure_ascii=True, indent=2)

    if low in {"learning state", "learning status", "self correction status", "what are you learning"}:
        m = core.behavior_get_metrics()
        return (
            "Learning state:\n"
            f"- correction_learned: {int(m.get('correction_learned', 0))}\n"
            f"- correction_applied: {int(m.get('correction_applied', 0))}\n"
            f"- self_correction_applied: {int(m.get('self_correction_applied', 0))}\n"
            f"- deterministic_hit: {int(m.get('deterministic_hit', 0))}\n"
            f"- llm_fallback: {int(m.get('llm_fallback', 0))}\n"
            f"- top_repeated_failure_class: {m.get('top_repeated_failure_class', '') or 'none'}\n"
            f"- top_repeated_correction_class: {m.get('top_repeated_correction_class', '') or 'none'}\n"
            f"- routing_stable: {bool(m.get('routing_stable', True))}\n"
            f"- unsupported_claims_blocked: {bool(m.get('unsupported_claims_blocked', False))}\n"
            f"- last_event: {m.get('last_event', '')}"
        )

    return None