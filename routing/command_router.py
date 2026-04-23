from __future__ import annotations

import re

from .turn_model import RouteDecision, TurnUnderstanding


def classify_direct_tool_route(turn: TurnUnderstanding, *, looks_like_find_command) -> RouteDecision:
    t = turn.text
    low = turn.low

    if low in {"pulse", "nova pulse", "show pulse", "system pulse"}:
        return RouteDecision(kind="direct_tool", tool="pulse")

    if low in {"update now", "apply update now", "apply updates now"}:
        return RouteDecision(kind="direct_tool", tool="update_now")

    if low.startswith("update now confirm"):
        token = t.split(maxsplit=3)[3].strip() if len(t.split(maxsplit=3)) >= 4 else ""
        return RouteDecision(kind="direct_tool", tool="update_now_confirm", args=((token,) if token else ()))

    if low in {"update now cancel", "cancel update now"}:
        return RouteDecision(kind="direct_tool", tool="update_now_cancel")

    if low in {"queue status", "show queue status", "work queue", "generated queue"}:
        return RouteDecision(kind="direct_tool", tool="queue_status")
    if any(
        phrase in low
        for phrase in (
            "what should you work on next",
            "what should we work on next",
            "what should i work on next",
            "what is next in the queue",
            "what's next in the queue",
            "what is the next item in the queue",
            "what's the next item in the queue",
        )
    ):
        return RouteDecision(kind="direct_tool", tool="queue_status")

    if low in {
        "phase2",
        "phase2 status",
        "phase 2 status",
        "phase2 audit",
        "phase 2 audit",
        "post phase 2 audit",
        "post-phase-2 audit",
    }:
        return RouteDecision(kind="direct_tool", tool="phase2_audit")

    if low in {"screen", "look at my screen"}:
        return RouteDecision(kind="direct_tool", tool="screen")

    if low.startswith("camera"):
        prompt = t[len("camera"):].strip() or "what do you see"
        return RouteDecision(kind="direct_tool", tool="camera", args=(prompt,))

    if low in {
        "health",
        "status",
        "system check",
        "system checks",
        "run system check",
        "run system checks",
    }:
        return RouteDecision(kind="direct_tool", tool="system_check")

    if low == "ls" or low.startswith("ls "):
        path = t.split(maxsplit=1)[1].strip() if len(t.split(maxsplit=1)) > 1 else ""
        return RouteDecision(kind="direct_tool", tool="ls", args=((path,) if path else ()))

    if low.startswith("read "):
        return RouteDecision(kind="direct_tool", tool="read", args=(t.split(maxsplit=1)[1].strip(),))

    if looks_like_find_command(t):
        parts = t.split(maxsplit=2)
        keyword = parts[1] if len(parts) > 1 else ""
        folder = parts[2] if len(parts) > 2 else ""
        args = (keyword,) if not folder else (keyword, folder)
        return RouteDecision(kind="direct_tool", tool="find", args=args)

    if low.startswith("location coords ") or low.startswith("set location coords "):
        value = t[len("set location coords "):].strip() if low.startswith("set location coords ") else t[len("location coords "):].strip()
        return RouteDecision(kind="direct_tool", tool="location_coords", args=(value,))

    if low in {"weather current location", "weather current"}:
        return RouteDecision(kind="direct_tool", tool="weather_current_location")

    if ("use your" in low or low.startswith("use ")) and turn.mentions_location:
        return RouteDecision(kind="direct_tool", tool="weather_current_location")

    if turn.mentions_shared_location and (turn.mentions_weather or any(p in low for p in ("rain", "raining", "forecast", "temperature"))):
        return RouteDecision(kind="direct_tool", tool="weather_current_location")

    if low in {"weather", "check weather"}:
        return RouteDecision(kind="clarify", message="What location should I use for the weather lookup?")

    if low.startswith("weather ") or low.startswith("check weather "):
        value = t[len("check weather "):].strip() if low.startswith("check weather ") else t[len("weather "):].strip()
        return RouteDecision(kind="direct_tool", tool="weather_location", args=(value,))

    if turn.mentions_weather:
        if ("your" in low and turn.mentions_location) or turn.mentions_shared_location or "there" in low or "that location" in low:
            return RouteDecision(kind="direct_tool", tool="weather_current_location")
        if (
            "?" in low
            or any(
                p in low
                for p in [
                    "give me",
                    "check",
                    "show",
                    "tell me",
                    "what is",
                    "what's",
                    "today",
                    "now",
                    "current",
                    "forecast",
                    "temperature",
                    "outside",
                    "notice",
                    "changes in the weather",
                ]
            )
        ):
            return RouteDecision(kind="clarify", message="What location should I use for the weather lookup?")

    if any(x in low for x in ("nmap", "scan my", "scan the")):
        return RouteDecision(kind="clarify", message="I can't run network scans. What specific check would you like me to help with?")

    if turn.url and any(x in low for x in ("gather", "summarize", "collect")):
        return RouteDecision(kind="direct_tool", tool="web_gather", args=(turn.url,))

    if turn.url:
        return RouteDecision(kind="direct_tool", tool="web_fetch", args=(turn.url,))

    if low.startswith("wikipedia ") or low.startswith("wiki "):
        query = t.split(maxsplit=1)[1].strip() if len(t.split(maxsplit=1)) > 1 else ""
        return RouteDecision(kind="direct_tool", tool="wikipedia_lookup", args=((query,) if query else ()))

    if low.startswith("stackexchange "):
        query = t[len("stackexchange "):].strip()
        return RouteDecision(kind="direct_tool", tool="stackexchange_search", args=((query,) if query else ()))

    if low.startswith("stack overflow "):
        query = t[len("stack overflow "):].strip()
        return RouteDecision(kind="direct_tool", tool="stackexchange_search", args=((query,) if query else ()))

    if low.startswith("web search ") or "search the web" in low or "web search" in low:
        query = t[11:].strip() if low.startswith("web search ") else t
        return RouteDecision(kind="direct_tool", tool="web_search", args=(query,))

    research_intent = (
        low.startswith("web research ")
        or "research this" in low
        or "do research" in low
        or "deep research" in low
        or "all the information" in low
        or "all the information on" in low
    )
    if research_intent:
        query = t[13:].strip() if low.startswith("web research ") else t
        return RouteDecision(kind="direct_tool", tool="web_research", args=(query,))

    if "patch apply" in low or ("apply patch" in low and ".zip" in low):
        match = re.search(r"([A-Za-z]:\\[^\s]+\.zip|/[^\s]+\.zip|\S+\.zip)", t)
        path = match.group(0) if match else ""
        return RouteDecision(kind="direct_tool", tool="patch_apply", args=((path,) if path else ()))

    if "patch rollback" in low or "rollback" in low:
        return RouteDecision(kind="direct_tool", tool="patch_rollback")

    if any(x in low for x in ("fix my code", "debug", "bug in", "refactor")):
        return RouteDecision(kind="respond", message="Paste the failing output or file path and I'll look.")

    return RouteDecision(kind="none")