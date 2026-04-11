from __future__ import annotations

import re
from typing import Callable

from services.nova_query_classifiers import is_action_history_query
from services.nova_query_classifiers import is_assistant_name_query
from services.nova_query_classifiers import is_capability_query
from services.nova_query_classifiers import is_developer_full_name_query
from services.nova_query_classifiers import is_factual_identity_or_policy_query
from services.nova_query_classifiers import is_identity_or_developer_query
from services.nova_query_classifiers import is_name_origin_question
from services.nova_query_classifiers import is_policy_domain_query
from services.nova_query_classifiers import is_self_identity_web_challenge


def self_identity_web_challenge_reply(*, get_learned_fact_fn: Callable[[str, str], str]) -> str:
    assistant_name = get_learned_fact_fn("assistant_name", "Nova")
    return f"You should not need web research for my name. I already know my name is {assistant_name}, so that should be answered directly from my verified identity facts."


def assistant_name_reply(text: str, *, get_learned_fact_fn: Callable[[str, str], str]) -> str:
    assistant_name = get_learned_fact_fn("assistant_name", "Nova")
    low = (text or "").strip().lower()
    if "your name is nova" in low:
        return f"Correct. My name is {assistant_name}."
    return f"My name is {assistant_name}."


def developer_full_name_reply(*, get_learned_fact_fn: Callable[[str, str], str]) -> str:
    full_name = get_learned_fact_fn("developer_name", "Gustavo")
    if str(full_name or "").strip().lower() == "gustavo":
        full_name = "Gustavo Uribe"
    nickname = get_learned_fact_fn("developer_nickname", "Gus")
    if nickname and nickname.lower() != str(full_name).lower():
        return f"My developer's full name is {full_name}. {nickname} is his nickname."
    return f"My developer's full name is {full_name}."


def rules_reply() -> str:
    return (
        "Yes. I follow strict operating rules: I do not fabricate tool actions or files, "
        "I stay within enabled policy/tool limits, and I should say uncertain when I cannot verify something."
    )


def action_history_reply(
    *,
    latest_action_ledger_record_fn: Callable[[], dict],
    action_ledger_route_summary_fn: Callable[[object], str],
) -> str:
    rec = latest_action_ledger_record_fn()
    if not rec:
        return "No action ledger record exists yet in this runtime."
    tool = str(rec.get("tool") or "").strip() or "none"
    decision = str(rec.get("planner_decision") or "").strip() or "unknown"
    intent = str(rec.get("intent") or "").strip() or "unknown"
    grounded = bool(rec.get("grounded"))
    final_answer = str(rec.get("final_answer") or "").strip()
    route_summary = action_ledger_route_summary_fn(rec)
    if len(final_answer) > 220:
        final_answer = final_answer[:217] + "..."
    return (
        "Last action record: "
        f"intent={intent}; decision={decision}; tool={tool}; grounded={grounded}. "
        f"route={route_summary or '[none]'}. "
        f"final_answer={final_answer or '[none]'}"
    )


def hard_answer(
    user_text: str,
    *,
    arithmetic_expression_reply_fn: Callable[[str], str | None],
    get_learned_fact_fn: Callable[[str, str], str],
    get_active_user_fn: Callable[[], str],
    speaker_matches_developer_fn: Callable[[], bool],
    self_identity_web_challenge_reply_fn: Callable[[], str],
    get_name_origin_story_fn: Callable[[], str],
    prefix_from_earlier_memory_fn: Callable[[str], str],
    extract_developer_color_preferences_from_memory_fn: Callable[[], list[str]],
    describe_capabilities_fn: Callable[[], str],
    mem_get_recent_learned_fn: Callable[[int], list[str]],
) -> str | None:
    candidate = (user_text or "").strip().lower()
    candidate = re.sub(r"\byor\b", "your", candidate)

    arithmetic_reply = arithmetic_expression_reply_fn(user_text)
    if arithmetic_reply:
        return arithmetic_reply

    assistant_name = get_learned_fact_fn("assistant_name", "Nova")
    developer_name = get_learned_fact_fn("developer_name", "Gustavo")
    if str(developer_name or "").strip().lower() == "gustavo":
        developer_name = "Gustavo Uribe"
    developer_nickname = get_learned_fact_fn("developer_nickname", "Gus")
    active_user_raw = (get_active_user_fn() or "").strip()
    active_user = active_user_raw.lower()

    if (
        re.search(r"\b(what\s+is|what'?s)\s+your\s+name\b", candidate)
        or re.search(r"\bwho\s+are\s+you\b", candidate)
        or re.search(r"\bare\s+\w*ou\s+sure\b.*\bname\b", candidate)
    ):
        return f"My name is {assistant_name}."

    if is_self_identity_web_challenge(candidate):
        return self_identity_web_challenge_reply_fn()

    if bool(re.fullmatch(r"how\s+are\s+you\??", candidate)):
        return "I'm doing well, thanks for asking."

    if any(query in candidate for query in ["do you remember me", "do you know me"]):
        if speaker_matches_developer_fn():
            if developer_nickname and developer_nickname.lower() != str(developer_name).lower():
                return f"Yes. I remember you as {developer_name}, and you also go by {developer_nickname}."
            return f"Yes. I remember you as {developer_name}."
        if active_user_raw:
            return f"I remember your current session identity as {active_user_raw}. I do not have more verified personal facts yet."
        return "Uncertain. I do not have a verified user identity bound for this session yet."

    if re.search(r"\b(what\s+is|what'?s)\s+my\s+name\b", candidate) or "do you know my name" in candidate:
        if speaker_matches_developer_fn():
            return f"Your name is {developer_name}."
        if active_user_raw:
            return f"The only verified name I have for you in this session is {active_user_raw}."
        return "Uncertain. I do not have a verified name for you yet."

    why_name_query = (
        (("why are you called" in candidate) and "nova" in candidate)
        or (("why is your name" in candidate) and "nova" in candidate)
        or bool(re.search(r"\bwhy\s+your\s+called\s+nova\b", candidate))
        or bool(re.search(r"\bwhy\s+.*\bcalled\s+nova\b", candidate))
    )
    if why_name_query:
        story = get_name_origin_story_fn().strip()
        if story:
            low_story = story.lower()
            if "was given its name" in low_story and "creator" in low_story:
                return story
            return f"{assistant_name} was given its name by its creator, {developer_nickname}. {story}"
        return "I do not have a saved name-origin story yet. You can teach me with: remember this ..."

    full_story_query = (
        "full story behind your name" in candidate
        or "tell me the full story behind your name" in candidate
        or ("full story" in candidate and "name" in candidate)
    )
    if full_story_query:
        story = get_name_origin_story_fn().strip()
        if story:
            return story
        return "I do not have a saved full name-origin story yet. You can teach me with: remember this ..."

    if (
        "if you could name yourself" in candidate
        or "what name would you give yourself" in candidate
        or "if you had to rename yourself" in candidate
    ):
        return f"I would keep the name {assistant_name}."

    if "would you like to know the story behind your name" in candidate:
        return "Yes. Please share it, and I will remember it."

    if "where your name comes from" in candidate or "where your name came from" in candidate:
        story = get_name_origin_story_fn().strip()
        if story:
            return story
        return "I do not have a saved name-origin story yet. You can teach me with: remember this ..."

    if "who gave you that name" in candidate or "who gave you your name" in candidate:
        return prefix_from_earlier_memory_fn(f"My name was given by my developer, {developer_name} ({developer_nickname}).")

    creator_query = (
        bool(re.search(r"\bwho\s+is\s+your\s+creator\b", candidate))
        or bool(re.search(r"\bwho\s+made\s+you\b", candidate))
        or bool(re.search(r"\bwho\s+created\s+you\b", candidate))
        or bool(re.search(r"\bso\s+gus\s+is\s+your\s+creator\b", candidate))
        or bool(re.search(r"\bis\s+(?:gus|gustavo)\s+your\s+creator\b", candidate))
    )
    if creator_query:
        if developer_nickname and developer_nickname.lower() != str(developer_name).lower():
            return prefix_from_earlier_memory_fn(f"My creator is {developer_name}. He created me. {developer_nickname} is his nickname.")
        return prefix_from_earlier_memory_fn(f"My creator is {developer_name}. He created me.")

    if any(query in candidate for query in ["what do you know about me", "what else do you know about me", "what do you remember about me"]):
        facts = []
        if speaker_matches_developer_fn():
            facts.append(f"You are {developer_name}.")
            if developer_nickname and developer_nickname.lower() != str(developer_name).lower():
                facts.append(f"You also go by {developer_nickname}.")
            colors = extract_developer_color_preferences_from_memory_fn()
            if colors:
                if len(colors) == 1:
                    facts.append(f"Your known favorite color is {colors[0]}.")
                else:
                    facts.append("Your known favorite colors are " + ", ".join(colors[:-1]) + f", and {colors[-1]}.")
            story = get_name_origin_story_fn().strip()
            if story:
                facts.append("You gave me the name Nova.")
            if facts:
                return " ".join(facts)
        if active_user_raw:
            return f"I have one verified personal fact for this session: your name is {active_user_raw}. I do not have enough other structured personal facts yet."
        return "Uncertain. I do not have enough structured personal facts yet."

    if (
        "just knowing my name" in candidate
        or ("find out more" in candidate and "my name" in candidate)
        or ("know more about me" in candidate and "my name" in candidate)
    ):
        if speaker_matches_developer_fn():
            return (
                f"No. Knowing your name alone does not justify inventing more personal facts about you. "
                f"I should only state verified facts I actually learned, such as that you are {developer_name}."
            )
        if active_user_raw:
            return (
                f"No. Knowing the name {active_user_raw} alone is not enough for me to claim more personal facts. "
                "I should only use verified facts you explicitly gave me."
            )
        return "No. A name alone is not enough for me to claim personal facts. I should only use verified facts you explicitly gave me."

    my_full_name_query = (
        "my full name" in candidate
        or bool(re.search(r"\bif i am\s+gus\b.*\bfull name\b", candidate))
    )
    if my_full_name_query:
        developer_name_low = str(developer_name).lower()
        developer_nickname_low = str(developer_nickname).lower()
        if developer_name and (
            "i am gus" in candidate
            or (active_user and active_user in {developer_nickname_low, developer_name_low})
            or (developer_nickname_low and developer_nickname_low in candidate)
        ):
            return f"Your full name is {developer_name}."

    if "full name" in candidate and any(token in candidate for token in ["developer", "creator", "his", "gus", "nickname"]):
        return developer_full_name_reply(get_learned_fact_fn=get_learned_fact_fn)

    if any(token in candidate for token in ["what are your abilities", "what are you capable", "know what your capable", "know what you're capable", "what can you do"]):
        return describe_capabilities_fn()

    if candidate in {
        "what have you learned from me",
        "what have you learned from me?",
        "what did you learn from me",
        "what did you learn from me?",
        "show me what you've learned",
        "show me what you have learned",
    }:
        learned_items = mem_get_recent_learned_fn(5)
        if not learned_items:
            return "I haven't learned anything specific from you recently."
        return "Here's what I've learned from you recently:\n- " + "\n- ".join(learned_items)

    if candidate in {"can you code", "can you code?", "do you code", "do you code?"}:
        return (
            "Yes. I can write code, debug it, and explain it. "
            "I just can’t scan your machine or execute system actions unless you trigger an explicit tool command."
        )

    if "scan my machine" in candidate or "scan my computer" in candidate or "run a scan" in candidate or "nmap" in candidate:
        return (
            "No. I can’t scan your machine or run tools like nmap by myself. "
            "Tell me what you want checked and I’ll give you safe commands to run, then paste the output and I’ll interpret it."
        )

    return None


def truth_hierarchy_answer(
    user_text: str,
    *,
    is_action_history_query_fn: Callable[[str], bool],
    action_history_reply_fn: Callable[[], str],
    is_identity_or_developer_query_fn: Callable[[str], bool],
    hard_answer_fn: Callable[[str], str],
    get_name_origin_story_fn: Callable[[], str],
    is_capability_query_fn: Callable[[str], bool],
    describe_capabilities_fn: Callable[[], str],
    is_policy_domain_query_fn: Callable[[str], bool],
    policy_web_fn: Callable[[], dict],
) -> tuple[bool, str, str, bool]:
    t = (user_text or "").strip()
    if not t:
        return False, "", "", False

    if is_action_history_query_fn(t):
        return True, action_history_reply_fn(), "action_ledger", True

    if is_identity_or_developer_query_fn(t):
        hard = hard_answer_fn(t)
        if hard:
            return True, hard, "learned_facts", True
        story = str(get_name_origin_story_fn() or "").strip()
        if "did you learn about your name" in t.lower() and story:
            return True, story, "learned_facts", True
        return False, "", "", False

    if is_capability_query_fn(t):
        return True, describe_capabilities_fn(), "capability_registry", True

    if is_policy_domain_query_fn(t):
        web = policy_web_fn()
        domains = list(web.get("allow_domains") or [])
        enabled = bool(web.get("enabled", False))
        lines = [f"Policy web access enabled: {enabled}"]
        if domains:
            lines.append("Allowed domains: " + ", ".join(domains))
        else:
            lines.append("Allowed domains: none configured")
        return True, "\n".join(lines), "policy_json", True

    return False, "", "", False