from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Dict, List, Optional, Tuple


@dataclass(frozen=True)
class TurnUnderstanding:
    raw_text: str
    text: str
    low: str
    url: str = ""
    mentions_location: bool = False
    mentions_shared_location: bool = False
    mentions_weather: bool = False


@dataclass(frozen=True)
class RouteDecision:
    kind: str
    tool: str = ""
    args: Tuple[str, ...] = ()
    message: str = ""


def _mentions_location_phrase(text: str) -> bool:
    low = (text or "").lower()
    return any(
        phrase in low
        for phrase in (
            "location",
            "locaiton",
            "physical location",
            "physical locaiton",
        )
    )


def _mentions_shared_location(text: str) -> bool:
    low = (text or "").lower()
    return any(
        cue in low
        for cue in (
            "our location",
            "same location",
            "shared location",
            "share the same location",
            "we share the same location",
            "for our location",
        )
    )


def _looks_like_keyword_route(low: str) -> bool:
    return (
        low in {"web continue", "continue web", "continue web research"}
        or low.startswith("search ")
        or low.startswith("findweb ")
        or low.startswith("web ")
    )


def _looks_like_explicit_web_research(low: str) -> bool:
    text = (low or "").strip()
    if not text:
        return False
    direct_phrases = (
        "just use the web",
        "use the web",
        "only need web",
        "all you need is the web",
        "all you need is web",
        "need is the web",
        "online about",
        "online for",
        "online on",
        "search online",
        "research online",
        "search the web",
        "anything online",
        "find online",
        "look online",
    )
    if any(phrase in text for phrase in direct_phrases):
        return True
    research_terms = ("research", "search", "find", "lookup", "look up", "browse", "fetch")
    web_terms = ("web", "online", "internet", "website", "site", "tea.texas.gov", "txschools.gov")
    return any(term in text for term in research_terms) and any(term in text for term in web_terms)


def _assistant_offered_web_research(last_assistant: str) -> bool:
    low = (last_assistant or "").strip().lower()
    if not low:
        return False
    return (
        "i can try to find more" in low
        or "i can find more" in low
        or "i can try to look" in low
        or "i can look that up" in low
        or "i can try to gather more" in low
    )


def _looks_like_accepting_web_offer(turn: TurnUnderstanding) -> bool:
    low = (turn.low or "").strip()
    if not low:
        return False
    if _looks_like_explicit_web_research(low):
        return True
    if _looks_like_affirmative_followup(low) and any(token in low for token in ("find", "more", "information", "look", "search", "try")):
        return True
    return any(
        phrase in low
        for phrase in (
            "find more information",
            "find more",
            "look into that",
            "try to find more",
            "search for more",
            "tell me more about peims",
        )
    )


def _looks_like_topic_research_followup(turn: TurnUnderstanding) -> bool:
    low = (turn.low or "").strip()
    if not low:
        return False
    if _looks_like_explicit_web_research(low):
        return True
    phrases = (
        "find more information",
        "find more",
        "more information",
        "look into that",
        "try to find more",
        "search for more",
        "dig up",
        "find out more",
        "what else can you find",
    )
    return any(phrase in low for phrase in phrases)


def _looks_like_identity_topic(text: str) -> bool:
    low = (text or "").strip().lower()
    if not low:
        return False
    return any(token in low for token in ("developer", "creator", "gus", "gustavo", "my name", "your name", "who are you"))


def _looks_like_data_domain_query(low: str) -> bool:
    text = (low or "").strip()
    if not text:
        return False
    data_terms = (
        "peims",
        "tsds",
        "attendance",
        "ada",
        "submission",
        "submissions",
        "student data",
        "records",
        "data system",
        "reporting",
    )
    return any(term in text for term in data_terms)


def _looks_like_command_route(low: str) -> bool:
    if low in {"chat context", "show chat context", "context", "chatctx"}:
        return True
    if "domanins" in low and any(k in low for k in ["domain", "domanins", "allow", "policy", "list", "show"]):
        return True
    if low in {"domains", "list domains", "show domains", "list the domains", "allowed domains", "allow domains", "policy domains"}:
        return True
    if low.startswith("policy allow ") or low.startswith("policy remove ") or low.startswith("policy audit"):
        return True
    if low in {"web mode", "web limits", "web research limits"} or low.startswith("web mode "):
        return True
    if low.startswith("remember:"):
        return True
    if low in {"what can you do", "capabilities", "show capabilities"}:
        return True
    if low in {"mem stats", "memory stats"} or low.startswith("mem audit ") or low.startswith("memory audit "):
        return True
    if low in {"kb", "kb help", "kb list", "kb off", "patch", "patch help", "patch list-previews", "inspect"}:
        return True
    if low.startswith("kb use ") or low.startswith("kb add "):
        return True
    if low.startswith("patch apply ") or low.startswith("patch preview ") or low.startswith("patch show ") or low.startswith("patch approve ") or low.startswith("patch reject ") or low == "patch rollback":
        return True
    if low.startswith("teach "):
        return True
    if low.startswith("casual_mode") or low.startswith("casual mode"):
        return True
    if low in {"behavior stats", "behavior metrics", "behavior"}:
        return True
    if low in {"learning state", "learning status", "self correction status", "what are you learning"}:
        return True
    return False


def _last_assistant_turn(turns: object) -> str:
    if not isinstance(turns, list):
        return ""
    for item in reversed(turns):
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            continue
        role = str(item[0] or "").strip().lower()
        text = str(item[1] or "").strip()
        if role == "assistant" and text:
            return text
    return ""


def _last_user_question(turns: object, current_text: str = "") -> str:
    current_low = str(current_text or "").strip().lower()
    if not isinstance(turns, list):
        return ""
    for item in reversed(turns):
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            continue
        role = str(item[0] or "").strip().lower()
        text = str(item[1] or "").strip()
        if role != "user" or not text:
            continue
        low = text.lower()
        if current_low and low == current_low:
            continue
        if "?" in text or low.startswith(("what", "how", "why", "who", "where", "when", "which")):
            return text
    return ""


def _looks_like_affirmative_followup(low: str) -> bool:
    compact = (low or "").strip()
    if not compact:
        return False
    return (
        compact in {"yes", "yeah", "yea", "sure", "okay", "ok", "please", "do that", "go ahead"}
        or compact.startswith("yes ")
        or compact.startswith("yeah ")
        or compact.startswith("yea ")
        or compact.startswith("please ")
        or "do that" in compact
    )


def _extract_followup_location_candidate(turn: TurnUnderstanding) -> str:
    text = (turn.text or "").strip().strip(" .,!?")
    low = turn.low
    if not text:
        return ""
    if turn.url or turn.mentions_weather or turn.mentions_shared_location:
        return ""
    if any(token in low for token in ("your location", "our location", "same location", "shared location")):
        return ""
    if _looks_like_keyword_route(low) or _looks_like_command_route(low):
        return ""
    if len(text) > 80:
        return ""
    if text.endswith("?"):
        return ""
    if re.match(r"^(yes|yeah|yea|sure|okay|ok|please|do that|go ahead)\b", low):
        return ""
    return text


def understand_turn(text: str) -> TurnUnderstanding:
    cleaned = (text or "").strip()
    low = cleaned.lower()
    url_match = re.search(r"https?://[\w\-\.\/:?=&%]+", cleaned)
    return TurnUnderstanding(
        raw_text=text or "",
        text=cleaned,
        low=low,
        url=url_match.group(0) if url_match else "",
        mentions_location=_mentions_location_phrase(low),
        mentions_shared_location=_mentions_shared_location(low),
        mentions_weather="weather" in low and not low.startswith("web "),
    )


def classify_route(turn: TurnUnderstanding) -> RouteDecision:
    t = turn.text
    low = turn.low

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

    if low in {"screen", "look at my screen"}:
        return RouteDecision(kind="direct_tool", tool="screen")

    if low.startswith("camera"):
        prompt = t[len("camera"):].strip() or "what do you see"
        return RouteDecision(kind="direct_tool", tool="camera", args=(prompt,))

    if low in {"health", "status"}:
        return RouteDecision(kind="direct_tool", tool="health")

    if low == "ls" or low.startswith("ls "):
        path = t.split(maxsplit=1)[1].strip() if len(t.split(maxsplit=1)) > 1 else ""
        return RouteDecision(kind="direct_tool", tool="ls", args=((path,) if path else ()))

    if low.startswith("read "):
        return RouteDecision(kind="direct_tool", tool="read", args=(t.split(maxsplit=1)[1].strip(),))

    if low.startswith("find "):
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

    if _looks_like_keyword_route(low):
        return RouteDecision(kind="legacy_keyword")

    if _looks_like_command_route(low):
        return RouteDecision(kind="legacy_command")

    return RouteDecision(kind="none")


def classify_route_with_context(turn: TurnUnderstanding, config: Optional[dict] = None) -> RouteDecision:
    route = classify_route(turn)
    if route.kind != "none":
        return route

    cfg = config if isinstance(config, dict) else {}
    if _looks_like_explicit_web_research(turn.low):
        return RouteDecision(kind="direct_tool", tool="web_research", args=(turn.text,))

    if bool(cfg.get("prefer_web_for_data_queries")) and _looks_like_data_domain_query(turn.low):
        return RouteDecision(kind="direct_tool", tool="web_research", args=(turn.text,))

    pending_action = cfg.get("pending_action") if isinstance(cfg.get("pending_action"), dict) else {}
    last_assistant = _last_assistant_turn(cfg.get("session_turns"))
    last_low = last_assistant.lower()

    if _assistant_offered_web_research(last_assistant) and _looks_like_accepting_web_offer(turn):
        prior_topic = _last_user_question(cfg.get("session_turns"), turn.text)
        query = prior_topic or turn.text
        return RouteDecision(kind="direct_tool", tool="web_research", args=(query,))

    if _looks_like_topic_research_followup(turn):
        prior_topic = _last_user_question(cfg.get("session_turns"), turn.text)
        if prior_topic and not _looks_like_identity_topic(prior_topic):
            return RouteDecision(kind="direct_tool", tool="web_research", args=(prior_topic,))

    if pending_action.get("kind") == "weather_lookup" and pending_action.get("status") == "awaiting_location":
        if turn.mentions_shared_location or turn.low in {"our location", "our location nova", "same location", "shared location"}:
            return RouteDecision(kind="direct_tool", tool="weather_current_location")
        if ("your" in turn.low and turn.mentions_location) or "that location" in turn.low or "there" in turn.low:
            return RouteDecision(kind="direct_tool", tool="weather_current_location")
        if pending_action.get("saved_location_available") and _looks_like_affirmative_followup(turn.low):
            return RouteDecision(kind="direct_tool", tool="weather_current_location")
        explicit_location = _extract_followup_location_candidate(turn)
        if explicit_location:
            return RouteDecision(kind="direct_tool", tool="weather_location", args=(explicit_location,))

    if "what location should i use for the weather lookup" in last_low:
        if turn.mentions_shared_location or turn.low in {"our location", "our location nova", "same location", "shared location"}:
            return RouteDecision(kind="direct_tool", tool="weather_current_location")

    return route


def choose_execution(route: RouteDecision) -> List[Dict]:
    if route.kind == "direct_tool":
        return [{"type": "run_tool", "tool": route.tool, "args": list(route.args)}]
    if route.kind == "legacy_command":
        return [{"type": "route_command"}]
    if route.kind == "legacy_keyword":
        return [{"type": "route_keyword"}]
    if route.kind == "respond":
        return [{"type": "respond", "note": route.message}]
    if route.kind == "clarify":
        return [{"type": "ask_clarify", "question": route.message}]
    return []


def decide_turn(text: str, config: Optional[dict] = None) -> List[Dict]:
    understanding = understand_turn(text)
    route = classify_route_with_context(understanding, config=config)
    return choose_execution(route)