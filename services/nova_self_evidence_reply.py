from __future__ import annotations

import re
from typing import Any


SELF_EVIDENCE_NEEDS = {"confirmed_identity", "operational_self"}
MIN_SELF_EVIDENCE_CONFIDENCE = 0.70

_NOVA_SELF_NATURE = re.compile(
    r"\bare you (?:a |an )?(?:chat\s*bot|chatbot|virtual assistant|language model|\bllm\b|ai)\b",
    re.IGNORECASE,
)
_NOVA_SELF_IDENTITY = re.compile(
    r"\b(?:who are you|what are you|who is nova|what is nova|what is leah|who is leah)\b",
    re.IGNORECASE,
)


def _clean(value: object, *, limit: int = 260) -> str:
    text = " ".join(str(value or "").strip().split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def _semantic_evidence_need(packet: dict[str, Any] | None) -> str:
    payload = packet if isinstance(packet, dict) else {}
    planner = payload.get("planner_frame") if isinstance(payload.get("planner_frame"), dict) else {}
    semantic = planner.get("semantic_tool_observation") if isinstance(planner.get("semantic_tool_observation"), dict) else {}
    evidence_need = str(semantic.get("evidence_need") or "").strip().lower()
    answer_target = str(semantic.get("answer_target") or "").strip().lower()
    try:
        confidence = float(semantic.get("confidence", 0.0) or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    if answer_target != "nova_self":
        return ""
    if evidence_need not in SELF_EVIDENCE_NEEDS:
        return ""
    if confidence < MIN_SELF_EVIDENCE_CONFIDENCE:
        return ""
    return evidence_need


def turn_asks_nova_self(text: str) -> str:
    """When the weak router misses, still bind identity/nature asks to evidence."""
    compact = " ".join(str(text or "").strip().split())
    if not compact:
        return ""
    if _NOVA_SELF_NATURE.search(compact):
        return "operational_self"
    if _NOVA_SELF_IDENTITY.search(compact):
        return "operational_self"
    return ""


def _turn_asks_nova_self(text: str) -> str:
    return turn_asks_nova_self(text)


def _identity_facts(context: str) -> dict[str, str]:
    facts: dict[str, str] = {}
    for raw in str(context or "").splitlines():
        line = raw.strip()
        if not line.startswith("Identity fact:"):
            continue
        body = line.split(":", 1)[1].strip()
        if "=" not in body:
            continue
        key, value = body.split("=", 1)
        key = re.sub(r"[^a-zA-Z0-9_]+", "_", key.strip()).strip("_").lower()
        value = _clean(value, limit=160)
        if key and value:
            facts[key] = value
    return facts


def _identity_authority(context: str) -> str:
    for raw in str(context or "").splitlines():
        line = raw.strip()
        if line.startswith("Confirmed Nova identity evidence:"):
            return _clean(line.split(":", 1)[1].strip(), limit=280)
    return ""


def _operational_parts(context: str) -> list[tuple[str, str]]:
    parts: list[tuple[str, str]] = []
    in_section = False
    for raw in str(context or "").splitlines():
        line = raw.strip()
        if line == "Operational Nova self evidence:":
            in_section = True
            continue
        if in_section and line and not line.startswith("-") and not line.startswith("Registered internal surfaces"):
            break
        if not in_section or not line.startswith("-") or ":" not in line:
            continue
        key, description = line.lstrip("-").split(":", 1)
        key_text = _clean(key.replace("_", " "), limit=80)
        description_text = _clean(description, limit=180)
        if key_text and description_text:
            parts.append((key_text, description_text))
    return parts


def maybe_build_self_evidence_reply(
    *,
    fallback_context: dict[str, Any] | None,
    intent_evidence_packet: dict[str, Any] | None,
    current_text: str = "",
) -> dict[str, Any]:
    evidence_need = _semantic_evidence_need(intent_evidence_packet)
    if evidence_need not in SELF_EVIDENCE_NEEDS:
        packet = intent_evidence_packet if isinstance(intent_evidence_packet, dict) else {}
        evidence_need = _turn_asks_nova_self(
            str(current_text or packet.get("current_turn") or "")
        )
    if evidence_need not in SELF_EVIDENCE_NEEDS:
        return {}

    context_payload = fallback_context if isinstance(fallback_context, dict) else {}
    evidence_context = str(context_payload.get("learning_context") or context_payload.get("context") or "")
    identity = _identity_facts(evidence_context)
    authority = _identity_authority(evidence_context)
    operational = _operational_parts(evidence_context)

    has_identity = bool(identity or authority)
    has_operational = bool(operational)
    if evidence_need == "confirmed_identity" and not has_identity:
        return {}
    if evidence_need == "operational_self" and not (has_identity or has_operational):
        return {}

    name = identity.get("assistant_name") or "Nova"
    lines: list[str] = []

    if evidence_need == "confirmed_identity":
        facts = []
        if identity.get("assistant_name"):
            facts.append(f"name={identity['assistant_name']}")
        if identity.get("developer_name"):
            developer = identity["developer_name"]
            if identity.get("developer_nickname"):
                developer += f" ({identity['developer_nickname']})"
            facts.append(f"developer={developer}")
        if authority:
            facts.append(f"authority={authority}")
        if facts:
            lines.append("Current confirmed identity evidence: " + "; ".join(facts) + ".")
        if operational:
            names = [key for key, _description in operational[:10]]
            lines.append("Operational evidence also shows registered internal surfaces: " + ", ".join(names) + ".")
    else:
        lines.append(f"I am {name}. Current evidence shows a local AI runtime with registered internal systems, not only a model reply.")
        if identity.get("developer_name"):
            developer = identity["developer_name"]
            if identity.get("developer_nickname"):
                developer += f" ({identity['developer_nickname']})"
            lines.append(f"Confirmed identity evidence lists the developer as {developer}.")
        if operational:
            names = [key for key, _description in operational[:10]]
            lines.append("Registered operational surfaces: " + ", ".join(names) + ".")

    reply = "\n".join(line for line in lines if line).strip()
    if not reply:
        return {}
    return {
        "handled": True,
        "reply": reply,
        "planner_decision": "evidence_bound_reply",
        "grounded": True,
        "reply_contract": f"self_evidence.{evidence_need}",
        "reply_outcome": {
            "kind": "self_evidence",
            "evidence_need": evidence_need,
            "identity_used": has_identity,
            "operational_identity_used": has_operational,
            "intent_evidence_packet": dict(intent_evidence_packet or {}),
        },
        "llm_time_ms": 0,
        "post_time_ms": 0,
    }
