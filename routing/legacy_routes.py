from __future__ import annotations


def looks_like_keyword_route(low: str) -> bool:
    return (
        low in {"web continue", "continue web", "continue web research"}
        or low.startswith("search ")
        or low.startswith("findweb ")
        or low.startswith("web ")
    )


def looks_like_command_route(low: str) -> bool:
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
