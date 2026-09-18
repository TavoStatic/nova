"""AT-5 honesty tests for leah_memory_recall.

Profile AT-5 (docs/LEAH_INSTANCE_PROFILE.md) is a live, cross-session check:
session A stores a distinctive fact; session B, same user, no prior turns, a
recall-cue query cites that fact. Same-session cite is continuity, not AT-5.

This file does not claim that live AT-5 passed. It exercises three contracts
that the live miss actually depends on:

1. Write path (nova_core / reply spine) — does a Leah chat turn call mem_add?
2. Pin path — does "remember this:" / "remember:" call mem_remember_fact?
3. Read wiring (Leah service) — if mem_recall returned the fact, would it surface?

Live 2026-08-15: same-session CEDAR-2206 cite can be continuity. New session
did not cite it. Pin of "remember this: CEDAR-2206" did return
"Pinned memory saved", so a write can happen — and still not be what
mem_recall returns. Do not promote on these tests.
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from services.memory_production import apply_user_memory_learning
from services.nova_fallback_flow import finalize_llm_fallback_reply
from services.nova_reply_sequence import execute_reply_sequence


CEDAR_FACT = "The orchard lot code is CEDAR-2206."
REMEMBER_THIS = "remember this: CEDAR-2206 is the orchard lot code"
RECALL_CUE = "what did I tell you about the orchard lot code?"


def _learning_spies():
    added: list[tuple[str, str, str]] = []
    remembered: list[str] = []

    def mem_add(kind, source, text):
        added.append((str(kind), str(source), str(text)))

    def mem_remember_fact(fact):
        remembered.append(str(fact))
        mem_add("fact", "pinned", fact)
        return f"Pinned memory saved: {fact}"

    def apply_learning(text, **kwargs):
        return apply_user_memory_learning(
            text,
            input_source=str(kwargs.get("input_source") or "http"),
            mem_enabled_fn=lambda: True,
            mem_add_fn=mem_add,
            mem_remember_fact_fn=mem_remember_fact,
            load_learned_facts_fn=lambda: {},
            save_learned_facts_fn=lambda _data: None,
            get_learned_fact_fn=lambda _key, default="": default,
            set_active_user_fn=lambda _name: None,
            get_active_user_fn=lambda: "gus",
            load_identity_profile_fn=lambda: {},
            save_identity_profile_fn=lambda _data: None,
            store_correction_record_fn=lambda *_args, **_kwargs: None,
        )

    return added, remembered, apply_learning


def _reply_core(*, apply_learning, mem_add):
    return SimpleNamespace(
        _llm_classify_routing_intent=lambda _text, **_kwargs: {
            "tool": "none",
            "args": [],
            "confidence": 0.9,
        },
        build_fallback_context_details=lambda _text, _turns, **_kwargs: {},
        ollama_chat=lambda _text, retrieved_context="", language_mix_spanish_pct=0, **_kwargs: "model reply",
        execute_planned_action=lambda _tool, _args: "",
        _web_allowlist_message=lambda resource: f"No access to {resource}",
        behavior_set_flag=lambda *args, **kwargs: None,
        action_ledger_add_step=lambda *args, **kwargs: None,
        apply_user_memory_learning=apply_learning,
        mem_enabled=lambda: True,
        mem_should_store=lambda _text: True,
        mem_add=mem_add,
    )


def _run_http_turn(text: str, *, apply_learning, mem_add) -> tuple[str, dict]:
    return execute_reply_sequence(
        turns=[],
        text=text,
        pending_action=None,
        turn_acts=["chat"],
        prefer_web_for_data_queries=False,
        language_mix_spanish_pct=0,
        session=None,
        trace=lambda *args, **kwargs: None,
        normalize_reply=lambda reply: reply,
        ensure_reply=lambda reply: reply,
        core=_reply_core(apply_learning=apply_learning, mem_add=mem_add),
        input_source="http",
        channel="http",
    )


class TestAT5WritePathOrdinaryLeahTurnDoesNotMemAdd(unittest.TestCase):
    """The nova_core question: does a Leah chat turn write durable memory?

    Answer from the spine: no. Ordinary chat text is not mem_add'd.
    finalize_llm_fallback_reply is given mem_add_fn and never calls it.
    Policy store_blocked_kinds includes chat_user. mem_should_store is unused
    on the finalize path.
    """

    def test_fallback_finalize_does_not_call_mem_add_for_http_fact(self):
        memories: list[tuple[str, str, str]] = []
        out = finalize_llm_fallback_reply(
            text=CEDAR_FACT,
            raw_user_text=CEDAR_FACT,
            input_source="http",
            retrieved_context="",
            language_mix_spanish_pct=0,
            ollama_chat_fn=lambda text, retrieved_context="", language_mix_spanish_pct=0, **_kwargs: "ok",
            mem_enabled_fn=lambda: True,
            mem_should_store_fn=lambda _text: True,
            mem_add_fn=lambda kind, source, text: memories.append((kind, source, text)),
            strip_mem_leak_fn=lambda reply, _retrieved: reply,
            behavior_record_event_fn=lambda _event: None,
            action_ledger_add_step=lambda *args, **kwargs: None,
            ensure_reply_fn=lambda text: text,
        )
        self.assertTrue(out.get("handled"))
        self.assertEqual(memories, [])

    def test_ordinary_fact_statement_is_not_a_learning_write(self):
        added, remembered, apply_learning = _learning_spies()
        outcome = apply_learning(CEDAR_FACT, input_source="http")
        self.assertFalse(outcome.get("handled"))
        self.assertEqual(outcome.get("action"), "")
        self.assertEqual(added, [])
        self.assertEqual(remembered, [])

    def test_http_reply_sequence_does_not_mem_add_ordinary_leah_turn(self):
        added, _remembered, apply_learning = _learning_spies()
        reply, meta = _run_http_turn(
            CEDAR_FACT,
            apply_learning=apply_learning,
            mem_add=lambda kind, source, text: added.append((kind, source, text)),
        )
        self.assertEqual(reply, "model reply")
        self.assertNotEqual(meta.get("planner_decision"), "memory_learning")
        self.assertEqual(added, [])


class TestAT5WritePathRememberPrefixPins(unittest.TestCase):
    """Explicit remember / remember this: is the chat write that exists.

    That path is apply_user_memory_learning → mem_remember_fact →
    mem_add("fact", "pinned", fact). It is not automatic storage of Leah turns.
    Live pin of CEDAR-2206 wrote and still failed new-session recall — AT-5
    remains open on mem_recall surfacing a pinned fact.
    """

    def test_remember_this_prefix_pins_via_mem_add(self):
        added, remembered, apply_learning = _learning_spies()
        outcome = apply_learning(REMEMBER_THIS, input_source="http")
        self.assertTrue(outcome.get("handled"))
        self.assertEqual(outcome.get("action"), "remember_fact")
        self.assertEqual(remembered, ["CEDAR-2206 is the orchard lot code"])
        self.assertEqual(added, [("fact", "pinned", "CEDAR-2206 is the orchard lot code")])
        self.assertIn("CEDAR-2206", str(outcome.get("early_reply") or ""))

    def test_remember_colon_prefix_also_pins(self):
        added, remembered, apply_learning = _learning_spies()
        outcome = apply_learning("remember: CEDAR-2206 is the orchard lot code", input_source="http")
        self.assertTrue(outcome.get("handled"))
        self.assertEqual(outcome.get("action"), "remember_fact")
        self.assertEqual(added, [("fact", "pinned", "CEDAR-2206 is the orchard lot code")])
        self.assertEqual(remembered, ["CEDAR-2206 is the orchard lot code"])

    def test_http_reply_sequence_short_circuits_remember_this_before_fallback(self):
        added, remembered, apply_learning = _learning_spies()
        reply, meta = _run_http_turn(
            REMEMBER_THIS,
            apply_learning=apply_learning,
            mem_add=lambda kind, source, text: added.append((kind, source, text)),
        )
        self.assertIn("Pinned memory saved", reply)
        self.assertIn("CEDAR-2206", reply)
        self.assertEqual(meta.get("planner_decision"), "memory_learning")
        self.assertEqual(meta.get("memory_learning_action"), "remember_fact")
        self.assertEqual(remembered, ["CEDAR-2206 is the orchard lot code"])
        self.assertEqual(added, [("fact", "pinned", "CEDAR-2206 is the orchard lot code")])


class TestAT5ReadWiringIfMemRecallReturnsFact(unittest.TestCase):
    """Leah service contract only. Mocking mem_recall is not an AT-5 pass.

    Live miss: the cue gate fired and mem_recall returned nothing that
    included CEDAR-2206. These tests prove the inject path, not durable store.
    """

    def _make_service(self, recall_return: str):
        from services.leah_memory_recall import LeahMemoryRecallService

        mem_fn = MagicMock(return_value=recall_return)
        svc = LeahMemoryRecallService(
            mem_recall_fn=mem_fn,
            mem_enabled_fn=lambda: True,
        )
        return svc, mem_fn

    def test_injected_when_mem_recall_returns_the_fact(self):
        svc, mem_fn = self._make_service(recall_return=CEDAR_FACT)
        recall_ctx = svc.recall_for_turn(RECALL_CUE)
        injected = svc.inject_into_message(RECALL_CUE, recall_ctx)
        self.assertEqual(recall_ctx, CEDAR_FACT)
        self.assertIn("CEDAR-2206", injected)
        self.assertIn("[LEAH memory context]", injected)
        mem_fn.assert_called_once()
        self.assertEqual(mem_fn.call_args[0][0], RECALL_CUE)

    def test_empty_when_mem_recall_returns_nothing(self):
        """Mirrors the live new-session miss: gate fires, store returns empty."""
        svc, mem_fn = self._make_service(recall_return="")
        result = svc.recall_for_turn(RECALL_CUE)
        self.assertEqual(result, "")
        mem_fn.assert_called_once()
        self.assertEqual(svc.inject_into_message(RECALL_CUE, result), RECALL_CUE)

    def test_recall_does_not_need_session_turns(self):
        svc, _mem_fn = self._make_service(recall_return=CEDAR_FACT)
        result = svc.recall_for_turn("do you remember the orchard lot code?")
        self.assertEqual(result, CEDAR_FACT)

    def test_status_cue_does_not_call_mem_recall(self):
        svc, mem_fn = self._make_service(recall_return=CEDAR_FACT)
        result = svc.recall_for_turn("what is the sync status?")
        self.assertEqual(result, "")
        mem_fn.assert_not_called()


class TestAT5IsNotClaimedPassed(unittest.TestCase):
    """Guardrail: this file must not be read as a live AT-5 pass."""

    def test_module_doc_refuses_live_pass_claim(self):
        import tests.test_leah_memory_recall_at5 as mod

        doc = str(mod.__doc__ or "")
        self.assertIn("does not claim that live AT-5 passed", doc)
        self.assertIn("Same-session cite is continuity", doc)
        self.assertIn("mem_add", doc)


if __name__ == "__main__":
    unittest.main()
