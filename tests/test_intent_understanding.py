"""
test_intent_understanding.py

Tests for nova_intent_understanding -- multi-level intent classifier.
"""

import json
import unittest
from unittest import mock

from services.nova_intent_understanding import (
    ACCEPT,
    CASUAL,
    CLARIFY,
    COMMANDING,
    CONFIRM,
    CORRECT,
    ENRICH,
    FULFILL,
    GENERAL,
    LOCATION,
    REQUESTING,
    RESPONDING,
    SHARING,
    SYSTEM,
    WEATHER,
    classify_turn_intent,
    record_intent_outcome,
    select_response_strategy,
    self_status_belongs_to_turn,
    _build_intent_gap_signal,
    _default_intent,
    _is_gap_outcome,
    _parse_intent,
)


class TestSelectResponseStrategy(unittest.TestCase):

    def _intent(self, level, domain=WEATHER, confidence=0.85, claim=None):
        return {
            "level": level,
            "domain": domain,
            "confidence": confidence,
            "subject": "test",
            "user_claim": claim,
        }

    def test_requesting_weather_fulfills(self):
        result = select_response_strategy(self._intent(REQUESTING))
        self.assertEqual(result["strategy"], FULFILL)
        self.assertTrue(result["use_tool"])

    def test_commanding_weather_fulfills(self):
        result = select_response_strategy(self._intent(COMMANDING))
        self.assertEqual(result["strategy"], FULFILL)
        self.assertTrue(result["use_tool"])

    def test_responding_fulfills(self):
        result = select_response_strategy(self._intent(RESPONDING))
        self.assertEqual(result["strategy"], FULFILL)
        self.assertTrue(result["use_tool"])

    def test_sharing_weather_no_data_accepts(self):
        result = select_response_strategy(
            self._intent(SHARING, WEATHER, claim="hot today"),
            tool_data_available=False,
        )
        self.assertEqual(result["strategy"], ACCEPT)
        self.assertFalse(result["use_tool"])

    def test_sharing_weather_data_confirms(self):
        result = select_response_strategy(
            self._intent(SHARING, WEATHER, claim="hot today"),
            tool_data_available=True,
            data_confirms_claim=True,
        )
        self.assertEqual(result["strategy"], CONFIRM)
        self.assertTrue(result["use_tool"])

    def test_sharing_weather_data_contradicts(self):
        result = select_response_strategy(
            self._intent(SHARING, WEATHER, claim="hot today"),
            tool_data_available=True,
            data_confirms_claim=False,
        )
        self.assertEqual(result["strategy"], CORRECT)
        self.assertTrue(result["use_tool"])

    def test_sharing_weather_data_available_but_vague_claim(self):
        result = select_response_strategy(
            self._intent(SHARING, WEATHER, claim=None),
            tool_data_available=True,
            data_confirms_claim=None,
        )
        self.assertEqual(result["strategy"], ENRICH)
        self.assertTrue(result["use_tool"])

    def test_casual_weather_remark_accepts(self):
        result = select_response_strategy(self._intent(CASUAL, WEATHER))
        self.assertEqual(result["strategy"], ACCEPT)
        self.assertFalse(result["use_tool"])

    def test_casual_general_accepts(self):
        result = select_response_strategy(self._intent(CASUAL, GENERAL))
        self.assertEqual(result["strategy"], ACCEPT)
        self.assertFalse(result["use_tool"])

    def test_self_status_stays_off_presence_turns(self):
        casual = self._intent(CASUAL, GENERAL)
        self.assertFalse(
            self_status_belongs_to_turn(casual, select_response_strategy(casual))
        )
        feeling = self._intent(REQUESTING, GENERAL)
        self.assertFalse(
            self_status_belongs_to_turn(feeling, select_response_strategy(feeling))
        )
        self.assertTrue(self_status_belongs_to_turn({}, {}))

    def test_self_status_stays_on_for_live_system_asks(self):
        intent = self._intent(REQUESTING, SYSTEM)
        self.assertTrue(
            self_status_belongs_to_turn(intent, select_response_strategy(intent))
        )

    def test_low_confidence_triggers_clarify(self):
        result = select_response_strategy(
            self._intent(REQUESTING, WEATHER, confidence=0.30)
        )
        self.assertEqual(result["strategy"], CLARIFY)
        self.assertFalse(result["use_tool"])

    def test_confidence_just_above_threshold_does_not_clarify(self):
        result = select_response_strategy(
            self._intent(REQUESTING, WEATHER, confidence=0.41)
        )
        self.assertNotEqual(result["strategy"], CLARIFY)

    def test_sharing_location_no_data_accepts(self):
        result = select_response_strategy(
            self._intent(SHARING, LOCATION),
            tool_data_available=False,
        )
        self.assertEqual(result["strategy"], ACCEPT)

    def test_sharing_location_data_confirms(self):
        result = select_response_strategy(
            self._intent(SHARING, LOCATION),
            tool_data_available=True,
            data_confirms_claim=True,
        )
        self.assertEqual(result["strategy"], CONFIRM)

    def test_strategy_has_required_keys(self):
        for level in (SHARING, REQUESTING, COMMANDING, CASUAL, RESPONDING):
            result = select_response_strategy(self._intent(level))
            self.assertIn("strategy", result)
            self.assertIn("use_tool", result)
            self.assertIn("rationale", result)
            self.assertIn(result["strategy"], {ACCEPT, CONFIRM, CORRECT, ENRICH, FULFILL, CLARIFY})
            self.assertIsInstance(result["use_tool"], bool)


class TestParseIntent(unittest.TestCase):

    def test_well_formed_sharing_weather(self):
        raw = json.dumps({
            "level": "sharing",
            "domain": "weather",
            "confidence": 0.92,
            "subject": "hot weather today",
            "user_claim": "it is going to be hot today",
        })
        result = _parse_intent(raw)
        self.assertIsNotNone(result)
        self.assertEqual(result["level"], SHARING)
        self.assertEqual(result["domain"], WEATHER)
        self.assertAlmostEqual(result["confidence"], 0.92)
        self.assertEqual(result["user_claim"], "it is going to be hot today")

    def test_well_formed_requesting(self):
        raw = json.dumps({
            "level": "requesting",
            "domain": "weather",
            "confidence": 0.88,
            "subject": "weather today",
            "user_claim": None,
        })
        result = _parse_intent(raw)
        self.assertEqual(result["level"], REQUESTING)
        self.assertIsNone(result["user_claim"])

    def test_unknown_level_falls_back_to_casual(self):
        raw = json.dumps({
            "level": "unknown_level",
            "domain": "weather",
            "confidence": 0.5,
            "subject": "something",
            "user_claim": None,
        })
        result = _parse_intent(raw)
        self.assertEqual(result["level"], CASUAL)

    def test_unknown_domain_falls_back_to_general(self):
        raw = json.dumps({
            "level": "requesting",
            "domain": "crypto",
            "confidence": 0.7,
            "subject": "coins",
            "user_claim": None,
        })
        result = _parse_intent(raw)
        self.assertEqual(result["domain"], GENERAL)

    def test_partial_json_extracted(self):
        raw = ('Here is my classification: {"level":"commanding","domain":"weather",'
               '"confidence":0.95,"subject":"check weather","user_claim":null} done.')
        result = _parse_intent(raw)
        self.assertIsNotNone(result)
        self.assertEqual(result["level"], COMMANDING)

    def test_empty_string_returns_none(self):
        self.assertIsNone(_parse_intent(""))

    def test_malformed_returns_none(self):
        self.assertIsNone(_parse_intent("not json at all"))

    def test_confidence_clamped_to_range(self):
        raw = json.dumps({
            "level": "casual",
            "domain": "general",
            "confidence": 1.5,
            "subject": "",
            "user_claim": None,
        })
        result = _parse_intent(raw)
        self.assertLessEqual(result["confidence"], 1.0)

    def test_null_user_claim_becomes_none(self):
        raw = json.dumps({
            "level": "casual",
            "domain": "general",
            "confidence": 0.7,
            "subject": "hi",
            "user_claim": None,
        })
        result = _parse_intent(raw)
        self.assertIsNone(result["user_claim"])


class TestRecordIntentOutcome(unittest.TestCase):

    def _intent(self, level=SHARING, domain=WEATHER):
        return {
            "level": level,
            "domain": domain,
            "confidence": 0.9,
            "subject": "weather today",
            "user_claim": "it will be hot",
        }

    def _strategy(self, strategy=CONFIRM):
        return {"strategy": strategy, "use_tool": True, "rationale": "test"}

    def test_records_when_mem_fn_provided(self):
        calls = []
        record_intent_outcome(
            "it's going to be hot today",
            self._intent(),
            self._strategy(),
            mem_add_fn=calls.append,
        )
        self.assertEqual(len(calls), 1)
        entry = calls[0]
        self.assertIn("intent_pattern", entry)
        self.assertIn("domain=weather", entry)
        self.assertIn("level=sharing", entry)
        self.assertIn("strategy=confirm_with_data", entry)
        self.assertIn("it's going to be hot today", entry)

    def test_no_crash_without_mem_fn(self):
        record_intent_outcome(
            "test text",
            self._intent(),
            self._strategy(),
            mem_add_fn=None,
        )

    def test_does_not_record_empty_text(self):
        calls = []
        record_intent_outcome(
            "",
            self._intent(),
            self._strategy(),
            mem_add_fn=calls.append,
        )
        self.assertEqual(len(calls), 0)

    def test_does_not_record_missing_level(self):
        calls = []
        record_intent_outcome(
            "some text",
            {"level": "", "domain": WEATHER, "confidence": 0.9, "subject": "", "user_claim": None},
            self._strategy(),
            mem_add_fn=calls.append,
        )
        self.assertEqual(len(calls), 0)

    def test_outcome_included_in_record(self):
        calls = []
        record_intent_outcome(
            "check weather now",
            self._intent(level=COMMANDING),
            self._strategy(FULFILL),
            outcome="tool_ran",
            mem_add_fn=calls.append,
        )
        self.assertIn("outcome=tool_ran", calls[0])

    def test_clarify_strategy_routes_to_work_tree(self):
        mem_calls = []
        signal_calls = []
        record_intent_outcome(
            "weather weather weather",
            self._intent(level=REQUESTING),
            self._strategy(CLARIFY),
            mem_add_fn=mem_calls.append,
            ingest_signal_fn=signal_calls.append,
        )
        self.assertEqual(len(mem_calls), 0, "gap outcome must not write to mem")
        self.assertEqual(len(signal_calls), 1, "gap outcome must ingest a signal")

    def test_clarify_signal_is_governance_pressure(self):
        signal_calls = []
        record_intent_outcome(
            "weather weather weather",
            self._intent(level=REQUESTING, domain=WEATHER),
            self._strategy(CLARIFY),
            ingest_signal_fn=signal_calls.append,
        )
        sig = signal_calls[0]
        self.assertEqual(sig["signal_class"], "governance_pressure")
        self.assertEqual(sig["source"], "intent_understanding")
        self.assertIn("weather", sig["title"])

    def test_clarify_signal_fingerprint_encodes_domain_and_level(self):
        signal_calls = []
        for _ in range(3):
            record_intent_outcome(
                "huh?",
                self._intent(level=REQUESTING, domain=WEATHER),
                self._strategy(CLARIFY),
                ingest_signal_fn=signal_calls.append,
            )
        fingerprints = [s["fingerprint"]["symbol"] for s in signal_calls]
        self.assertEqual(len(set(fingerprints)), 1, "repeated gap must produce same fingerprint")

    def test_successful_outcome_does_not_ingest_signal(self):
        signal_calls = []
        mem_calls = []
        record_intent_outcome(
            "it is going to be hot",
            self._intent(),
            self._strategy(CONFIRM),
            mem_add_fn=mem_calls.append,
            ingest_signal_fn=signal_calls.append,
        )
        self.assertEqual(len(signal_calls), 0)
        self.assertEqual(len(mem_calls), 1)

    def test_no_crash_if_ingest_fn_raises(self):
        def _bad(sig):
            raise RuntimeError("db locked")
        record_intent_outcome(
            "weather weather weather",
            self._intent(),
            self._strategy(CLARIFY),
            ingest_signal_fn=_bad,
        )

    def test_gap_outcome_keyword_routes_to_work_tree(self):
        signal_calls = []
        mem_calls = []
        record_intent_outcome(
            "some text",
            self._intent(level=REQUESTING),
            self._strategy(FULFILL),
            outcome="clarify_needed",
            mem_add_fn=mem_calls.append,
            ingest_signal_fn=signal_calls.append,
        )
        self.assertEqual(len(signal_calls), 1)
        self.assertEqual(len(mem_calls), 0)


class TestGapOutcomeHelpers(unittest.TestCase):

    def test_clarify_strategy_is_gap(self):
        self.assertTrue(_is_gap_outcome(CLARIFY, "completed"))

    def test_successful_strategies_are_not_gaps(self):
        for strat in (ACCEPT, CONFIRM, CORRECT, ENRICH, FULFILL):
            self.assertFalse(_is_gap_outcome(strat, "completed"), strat)

    def test_gap_outcome_keyword_is_gap(self):
        self.assertTrue(_is_gap_outcome(FULFILL, "clarify_needed"))
        self.assertTrue(_is_gap_outcome(FULFILL, "gap_detected"))
        self.assertTrue(_is_gap_outcome(FULFILL, "intent_failed"))

    def test_build_signal_has_required_fields(self):
        sig = _build_intent_gap_signal(WEATHER, REQUESTING, CLARIFY, "completed", "test text")
        self.assertEqual(sig["signal_class"], "governance_pressure")
        self.assertIn("source", sig)
        self.assertIn("title", sig)
        self.assertIn("fingerprint", sig)
        self.assertIn("payload", sig)
        self.assertEqual(sig["fingerprint"]["symbol"], "{}_{}".format(WEATHER, REQUESTING))

    def test_build_signal_sample_text_truncated(self):
        long_text = "a" * 300
        sig = _build_intent_gap_signal(WEATHER, REQUESTING, CLARIFY, "completed", long_text)
        self.assertLessEqual(len(sig["payload"]["sample_text"]), 120)


class TestClassifyTurnIntentRobustness(unittest.TestCase):

    def _hooks(self, post_fn=None, live=True):
        return dict(
            live_ollama_calls_allowed_fn=lambda: live,
            chat_model_fn=lambda: "qwen2.5:7b",
            ollama_base="http://localhost:11434",
            requests_post_fn=post_fn,
        )

    def test_ollama_down_returns_default(self):
        def _fail(*a, **kw):
            raise ConnectionError("ollama down")
        result = classify_turn_intent(
            "it's going to be hot today",
            [],
            **self._hooks(post_fn=_fail),
        )
        self.assertEqual(result["level"], CASUAL)
        self.assertEqual(result["domain"], GENERAL)
        self.assertEqual(result["confidence"], 0.0)

    def test_live_not_allowed_returns_default(self):
        result = classify_turn_intent(
            "what is the weather?",
            [],
            **self._hooks(live=False),
        )
        self.assertEqual(result, _default_intent())

    def test_empty_text_returns_default(self):
        result = classify_turn_intent(
            "",
            [],
            **self._hooks(),
        )
        self.assertEqual(result, _default_intent())

    def test_well_formed_ollama_response_parsed(self):
        payload = json.dumps({
            "level": "sharing",
            "domain": "weather",
            "confidence": 0.93,
            "subject": "hot day",
            "user_claim": "it's going to be hot today",
        })

        class _Resp:
            def raise_for_status(self): pass
            def json(self): return {"message": {"content": payload}}

        result = classify_turn_intent(
            "it's going to be hot today",
            [],
            **self._hooks(post_fn=lambda *a, **kw: _Resp()),
        )
        self.assertEqual(result["level"], SHARING)
        self.assertEqual(result["domain"], WEATHER)
        self.assertAlmostEqual(result["confidence"], 0.93)
        self.assertEqual(result["user_claim"], "it's going to be hot today")

    def test_malformed_ollama_response_returns_default(self):
        class _Resp:
            def raise_for_status(self): pass
            def json(self): return {"message": {"content": "not json"}}

        result = classify_turn_intent(
            "weather weather weather",
            [],
            **self._hooks(post_fn=lambda *a, **kw: _Resp()),
        )
        self.assertEqual(result, _default_intent())

    def test_timeout_returns_default(self):
        import socket
        def _timeout(*a, **kw):
            raise socket.timeout("timed out")
        result = classify_turn_intent(
            "should I bring a jacket?",
            [],
            **self._hooks(post_fn=_timeout),
        )
        self.assertEqual(result, _default_intent())


if __name__ == "__main__":
    unittest.main()
