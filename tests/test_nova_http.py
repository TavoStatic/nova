import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from unittest.mock import patch

import nova_http
from fulfillment_contracts import ChoiceMode, ChoiceSet, CollapseStatus, FitAssessment, FrameScore, FulfillmentModel, Intent


def _fulfillment_intent(intent_id: str = "intent-http-bridge") -> Intent:
    return Intent(
        intent_id=intent_id,
        achievement_goal="reach a workable result",
        success_criteria=["result achieved"],
        constraints=["stay within current constraints"],
        preferences=["useful", "low friction"],
    )


def _fulfillment_models() -> list[FulfillmentModel]:
    return [
        FulfillmentModel(
            model_id="http-guided",
            intent_id="intent-http-bridge",
            label="Guided path",
            description="Lower-friction option.",
            path_shape="guided_decision",
            differentiators=["lower user effort"],
            strengths=["lower friction"],
            expected_friction=["slower upfront"],
        ),
        FulfillmentModel(
            model_id="http-direct",
            intent_id="intent-http-bridge",
            label="Direct path",
            description="Faster option.",
            path_shape="direct_resolution",
            differentiators=["faster completion"],
            strengths=["faster timing"],
            expected_friction=["more commitment earlier"],
        ),
    ]


def _fulfillment_assessments() -> list[FitAssessment]:
    return [
        FitAssessment(
            assessment_id="ha1",
            intent_id="intent-http-bridge",
            model_id="http-guided",
            overall_fit_score=0.84,
            fit_band="strong_fit",
            valid=True,
            keep_reasons=["lower friction remains valuable"],
            frame_scores=[
                FrameScore(frame="explicit_constraint_fit", score=0.9),
                FrameScore(frame="achievement_goal_fit", score=0.82),
                FrameScore(frame="friction", score=0.95),
                FrameScore(frame="timing", score=0.58),
                FrameScore(frame="risk", score=0.82),
                FrameScore(frame="usefulness", score=0.86),
            ],
        ),
        FitAssessment(
            assessment_id="ha2",
            intent_id="intent-http-bridge",
            model_id="http-direct",
            overall_fit_score=0.83,
            fit_band="strong_fit",
            valid=True,
            keep_reasons=["faster timing remains valuable"],
            frame_scores=[
                FrameScore(frame="explicit_constraint_fit", score=0.9),
                FrameScore(frame="achievement_goal_fit", score=0.82),
                FrameScore(frame="friction", score=0.6),
                FrameScore(frame="timing", score=0.96),
                FrameScore(frame="risk", score=0.78),
                FrameScore(frame="usefulness", score=0.85),
            ],
        ),
    ]


def _http_choice_set() -> ChoiceSet:
    presenter = __import__("choice_presenter").ChoicePresenter()
    return presenter.present(_fulfillment_intent(), _fulfillment_models(), _fulfillment_assessments())


class TestNovaHttpProfile(unittest.TestCase):
    def setUp(self):
        self.orig_mem_recall = nova_http.nova_core.mem_recall
        self.orig_mem_enabled = nova_http.nova_core.mem_enabled
        self.orig_dev_bilingual = nova_http.nova_core._developer_is_bilingual
        self.orig_dev_bilingual_mem = nova_http.nova_core._developer_is_bilingual_from_memory
        self.orig_dev_colors = nova_http.nova_core._extract_developer_color_preferences
        self.orig_dev_colors_mem = nova_http.nova_core._extract_developer_color_preferences_from_memory
        self.orig_handle_keywords = nova_http.nova_core.handle_keywords
        nova_http.SESSION_TURNS.clear()
        nova_http.SESSION_STATE_MANAGER.clear()
        nova_http._CONTROL_STATUS_CACHE["computed_at"] = 0.0
        nova_http._CONTROL_STATUS_CACHE["payload"] = None

    def tearDown(self):
        nova_http.nova_core.mem_recall = self.orig_mem_recall
        nova_http.nova_core.mem_enabled = self.orig_mem_enabled
        nova_http.nova_core._developer_is_bilingual = self.orig_dev_bilingual
        nova_http.nova_core._developer_is_bilingual_from_memory = self.orig_dev_bilingual_mem
        nova_http.nova_core._extract_developer_color_preferences = self.orig_dev_colors
        nova_http.nova_core._extract_developer_color_preferences_from_memory = self.orig_dev_colors_mem
        nova_http.nova_core.handle_keywords = self.orig_handle_keywords
        nova_http.SESSION_TURNS.clear()
        nova_http.SESSION_STATE_MANAGER.clear()
        nova_http._CONTROL_STATUS_CACHE["computed_at"] = 0.0
        nova_http._CONTROL_STATUS_CACHE["payload"] = None

    def test_cached_control_status_payload_reuses_recent_value(self):
        payloads = [{"ok": True, "seq": 1}, {"ok": True, "seq": 2}]

        with mock.patch("nova_http._control_status_payload", side_effect=payloads) as status_mock, \
            mock.patch("nova_http.time.monotonic", side_effect=[100.0, 100.0, 100.1, 101.0, 103.5, 103.5, 103.6]):
            first = nova_http._cached_control_status_payload(2.0)
            second = nova_http._cached_control_status_payload(2.0)
            third = nova_http._cached_control_status_payload(2.0)

        self.assertEqual(first["seq"], 1)
        self.assertEqual(second["seq"], 1)
        self.assertEqual(third["seq"], 2)
        self.assertEqual(status_mock.call_count, 2)

    def test_developer_who_is_answer_is_deterministic(self):
        nova_http.nova_core.mem_enabled = lambda: True
        nova_http.nova_core.mem_recall = lambda q: ""
        reply = nova_http.process_chat("s1", "who is your developer?")
        self.assertTrue(reply.startswith("From earlier memory:"))
        self.assertIn("Gustavo", reply)
        self.assertIn("created me", reply.lower())

    def test_developer_profile_includes_known_facts(self):
        nova_http.nova_core.mem_enabled = lambda: True
        nova_http.nova_core.mem_recall = lambda q: "- developer note: gus works locally"
        nova_http.nova_core._developer_is_bilingual = lambda turns: True
        nova_http.nova_core._developer_is_bilingual_from_memory = lambda: True
        nova_http.nova_core._extract_developer_color_preferences = lambda turns: ["silver", "red", "blue"]
        nova_http.nova_core._extract_developer_color_preferences_from_memory = lambda: ["silver", "red", "blue"]

        reply = nova_http.process_chat("s2", "what else do you know about gus?")
        self.assertTrue(reply.startswith("From earlier memory:"))
        self.assertIn("bilingual", reply.lower())
        self.assertIn("silver", reply.lower())
        self.assertIn("developer", reply.lower())

    def test_developer_profile_self_diagnostic_when_partial(self):
        nova_http.nova_core.mem_enabled = lambda: True
        nova_http.nova_core.mem_recall = lambda q: ""
        nova_http.nova_core._developer_is_bilingual = lambda turns: None
        nova_http.nova_core._developer_is_bilingual_from_memory = lambda: None
        nova_http.nova_core._extract_developer_color_preferences = lambda turns: []
        nova_http.nova_core._extract_developer_color_preferences_from_memory = lambda: []

        reply = nova_http.process_chat("s6", "what else do you know about Gus your developer?")
        self.assertIn("his full name is gustavo", reply.lower())
        self.assertIn("don't have any additional verified information", reply.lower())

    def test_developer_location_followup_stays_on_developer_thread(self):
        reply1 = nova_http.process_chat("s6_loc", "what do you know about Gus?")
        reply2 = nova_http.process_chat("s6_loc", "do you know his current location")
        self.assertIn("gustavo", reply1.lower())
        self.assertIn("uncertain about gus's current location", reply2.lower())
        self.assertNotIn("local knowledge files", reply2.lower())

    def test_http_direct_developer_location_uses_shared_turn_helper(self):
        reply = nova_http.process_chat("s6_loc_direct", "where is gus right now?")
        self.assertIn("uncertain about gus's current location", reply.lower())
        session = nova_http.SESSION_STATE_MANAGER.get("s6_loc_direct")
        self.assertIsNotNone(session)
        self.assertEqual("identity_profile:developer", session.active_subject())

    def test_who_is_gus_seeds_developer_profile_subject(self):
        reply = nova_http.process_chat("s6_subject", "who is gus ?")
        self.assertIn("gustavo", reply.lower())
        session = nova_http.SESSION_STATE_MANAGER.get("s6_subject")
        self.assertIsNotNone(session)
        self.assertEqual("identity_profile:developer", session.active_subject())

    def test_developer_profile_certainty_challenge_stays_on_profile_thread(self):
        nova_http.process_chat("s6_cert", "what do you know about Gus?")
        reply = nova_http.process_chat("s6_cert", "are you sure that is all the information you about him?")
        self.assertNotIn("web research results", reply.lower())
        self.assertIn("verified facts", reply.lower())

    def test_profile_thread_resource_question_does_not_fall_into_local_knowledge(self):
        nova_http.process_chat("s6_res", "what do you know about Gus?")
        nova_http.process_chat("s6_res", "are you sure that is all the information you about him?")
        reply = nova_http.process_chat("s6_res", "what type of resources are you tring to fetch nova ?")
        self.assertIn("not trying to fetch web resources", reply.lower())
        self.assertNotIn("local knowledge files", reply.lower())

    def test_developer_how_built_has_non_hallucinated_limit(self):
        nova_http.nova_core.mem_enabled = lambda: True
        nova_http.nova_core.mem_recall = lambda q: ""
        with mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
            reply = nova_http.process_chat("s3", "how did he develop you?")
        self.assertIn("do not have detailed build-history", reply)
        self.assertNotIn("Turn bypassed supervisor intent phase", stdout.getvalue())
        session = nova_http.SESSION_STATE_MANAGER.get("s3")
        self.assertIsNotNone(session)
        self.assertEqual((session.last_reflection or {}).get("reply_contract"), "identity_history.history_recall")
        self.assertEqual((session.last_reflection or {}).get("reply_outcome_kind"), "history_recall")

    def test_fast_smalltalk_greeting(self):
        reply = nova_http.process_chat("s4", "hi nova")
        self.assertEqual("Hello.", reply)

    def test_fast_smalltalk_greeting_ignores_synthetic_runner_user(self):
        reply = nova_http.process_chat("s4_runner", "hi nova", user_id="runner")
        self.assertEqual("Hello.", reply)

    def test_how_are_you_does_not_route_to_grounded_lookup(self):
        reply = nova_http.process_chat("s4_how", "how are you?")
        self.assertEqual("I'm doing well, thanks for asking.", reply)

    def test_http_fulfillment_bridge_handles_model_space_turn(self):
        with patch("intent_interpreter.IntentInterpreter.interpret", return_value=_fulfillment_intent()), patch(
            "fulfillment_model_generator.FulfillmentModelGenerator.generate",
            return_value=_fulfillment_models(),
        ), patch(
            "fit_evaluator.FitEvaluator.evaluate",
            return_value=_fulfillment_assessments(),
        ):
            reply = nova_http.process_chat("s_fulfillment_http", "Show me workable options without collapsing too early.")

        self.assertIn("multiple meaningful fulfillment paths", reply.lower())
        session = nova_http.SESSION_STATE_MANAGER.get("s_fulfillment_http")
        self.assertIsNotNone(session)
        self.assertIsInstance(getattr(session, "fulfillment_state", None), dict)

    def test_http_fulfillment_bridge_replans_existing_state(self):
        session = nova_http.SESSION_STATE_MANAGER.get("s_fulfillment_replan")
        session.fulfillment_state = {
            "intent": _fulfillment_intent(),
            "models": _fulfillment_models(),
            "assessments": _fulfillment_assessments(),
            "choice_set": _http_choice_set(),
        }
        replanned_choice = ChoiceSet(
            choice_set_id="choice:intent-http-bridge",
            intent_id="intent-http-bridge",
            mode=ChoiceMode.SINGLE_RESULT,
            collapse_status=CollapseStatus.COLLAPSED,
            options=_http_choice_set().options[:1],
            selected_model_id="http-guided",
            collapse_reason="single distinct valid fulfillment shape",
            user_decision_needed=False,
        )

        with patch(
            "dynamic_replanner.DynamicReplanner.replan",
            return_value=(_fulfillment_intent(), [_fulfillment_models()[0]], [_fulfillment_assessments()[0]], replanned_choice),
        ):
            reply = nova_http.process_chat("s_fulfillment_replan", "New information makes the faster path less safe.")

        self.assertIn("one current fulfillment result", reply.lower())
        self.assertEqual(session.fulfillment_state.get("choice_set").selected_model_id, "http-guided")

    def test_http_mixed_info_request_turn_asks_for_clarification(self):
        mixed_turn = "the weather looks good. i wonder if the weather will stay like this for the rest of the day. can you check what the rest of the forecast will be"
        reply = nova_http.process_chat("s4_mixed_weather", mixed_turn)
        self.assertIn("both giving context and asking me to do something", reply.lower())
        session = nova_http.SESSION_STATE_MANAGER.get("s4_mixed_weather")
        self.assertEqual((session.last_reflection or {}).get("reply_contract"), "turn.clarify_mixed_intent")
        self.assertEqual((session.last_reflection or {}).get("reply_outcome_kind"), "mixed_info_request")
        self.assertIn("inform", (session.last_reflection or {}).get("turn_acts") or [])
        self.assertIn("ask", (session.last_reflection or {}).get("turn_acts") or [])
        self.assertIn("mixed", (session.last_reflection or {}).get("turn_acts") or [])

    def test_fast_smalltalk_ready_to_get_to_work(self):
        reply = nova_http.process_chat("s4_ready", "ready to get to work?")
        self.assertIn("ready when you are", reply.lower())
        self.assertIn("task for today", reply.lower())
        self.assertNotIn("local knowledge files", reply.lower())

    def test_creator_query_uses_hard_answer_before_grounded_lookup(self):
        reply = nova_http.process_chat("s4_creator", "who made you?")
        self.assertIn("my creator is gustavo uribe", reply.lower())
        self.assertNotIn("local knowledge files", reply.lower())

    def test_http_name_query_typo_and_web_challenge_stay_deterministic(self):
        nova_http.SESSION_TURNS.clear()
        nova_http.SESSION_STATE_MANAGER.clear()

        first = nova_http.process_chat("s_name_ui", "what is TSDS?")
        second = nova_http.process_chat("s_name_ui", "what is yor name?")
        third = nova_http.process_chat("s_name_ui", "why should i try to use the web for your name ?")

        self.assertNotIn("local knowledge files", first.lower())
        self.assertNotIn("[source:", first.lower())
        self.assertIn("my name is nova", second.lower())
        self.assertNotIn("web research results", third.lower())
        self.assertIn("should not need web research", third.lower())

    def test_fast_smalltalk_who_is_developer(self):
        reply = nova_http.process_chat("s5", "who is your developer?")
        self.assertIn("Gustavo", reply)

    def test_http_location_statement_uses_shared_noted_path(self):
        orig_set_location_text = nova_http.nova_core.set_location_text
        try:
            stored = []
            nova_http.nova_core.set_location_text = lambda value, input_source="typed": stored.append((value, input_source)) or value

            reply = nova_http.process_chat("s5_loc_store", "my location is Brownsville Texas")

            self.assertEqual("Got it - using Brownsville Texas as your location.", reply)
            self.assertEqual(stored, [("Brownsville Texas", "typed")])
        finally:
            nova_http.nova_core.set_location_text = orig_set_location_text

    def test_http_set_location_zip_claim_stores_and_replies(self):
        orig_set_location_text = nova_http.nova_core.set_location_text
        try:
            stored = []
            nova_http.nova_core.set_location_text = lambda value, input_source="typed": stored.append((value, input_source)) or value

            reply = nova_http.process_chat("s5_zip_store", "the 78521 is the zip code for your current physical location")

            self.assertEqual("Got it - 78521 is a ZIP code.", reply)
            self.assertEqual(stored, [("78521", "typed")])
        finally:
            nova_http.nova_core.set_location_text = orig_set_location_text

    def test_http_weather_uses_saved_location_after_set_location(self):
        orig_set_location_text = nova_http.nova_core.set_location_text
        orig_get_saved_location_text = nova_http.nova_core.get_saved_location_text
        orig_tool_weather = nova_http.nova_core.tool_weather
        try:
            saved = {"value": ""}

            def _store_location(value, input_source="typed"):
                saved["value"] = value
                return value

            weather_calls = []
            nova_http.nova_core.set_location_text = _store_location
            nova_http.nova_core.get_saved_location_text = lambda: saved["value"]
            nova_http.nova_core.tool_weather = lambda location: weather_calls.append(location) or f"Forecast for {location}: rain"

            first = nova_http.process_chat("s5_weather_zip", "78521")
            second = nova_http.process_chat("s5_weather_zip", "weather now")

            self.assertIn("Got it - 78521 is a ZIP code.", first)
            self.assertIn("Forecast for 78521: rain", second)
            self.assertEqual(weather_calls, ["78521"])
        finally:
            nova_http.nova_core.set_location_text = orig_set_location_text
            nova_http.nova_core.get_saved_location_text = orig_get_saved_location_text
            nova_http.nova_core.tool_weather = orig_tool_weather

    def test_http_where_am_i_uses_deterministic_location_recall(self):
        orig_set_location_text = nova_http.nova_core.set_location_text
        orig_get_saved_location_text = nova_http.nova_core.get_saved_location_text
        try:
            saved = {"value": ""}

            def _store_location(value, input_source="typed"):
                saved["value"] = value
                return value

            nova_http.nova_core.set_location_text = _store_location
            nova_http.nova_core.get_saved_location_text = lambda: saved["value"]

            first = nova_http.process_chat("s5_where_am_i", "78521")
            second = nova_http.process_chat("s5_where_am_i", "where am I")

            self.assertIn("Got it - 78521 is a ZIP code.", first)
            self.assertIn("Your saved location is 78521", second)
        finally:
            nova_http.nova_core.set_location_text = orig_set_location_text
            nova_http.nova_core.get_saved_location_text = orig_get_saved_location_text

    def test_http_location_name_followup_uses_saved_location(self):
        orig_set_location_text = nova_http.nova_core.set_location_text
        orig_get_saved_location_text = nova_http.nova_core.get_saved_location_text
        try:
            saved = {"value": ""}

            def _store_location(value, input_source="typed"):
                saved["value"] = value
                return value

            nova_http.nova_core.set_location_text = _store_location
            nova_http.nova_core.get_saved_location_text = lambda: saved["value"]

            first = nova_http.process_chat("s5_location_name", "78521")
            second = nova_http.process_chat("s5_location_name", "give me the name to that location")

            self.assertIn("Got it - 78521 is a ZIP code.", first)
            self.assertEqual("That location is Brownsville, TX.", second)
            self.assertNotIn("McAllen", second)
        finally:
            nova_http.nova_core.set_location_text = orig_set_location_text
            nova_http.nova_core.get_saved_location_text = orig_get_saved_location_text

    def test_http_saved_zip_followup_city_name_stays_in_location_thread(self):
        orig_set_location_text = nova_http.nova_core.set_location_text
        orig_get_saved_location_text = nova_http.nova_core.get_saved_location_text
        try:
            saved = {"value": ""}

            def _store_location(value, input_source="typed"):
                saved["value"] = value
                return value

            nova_http.nova_core.set_location_text = _store_location
            nova_http.nova_core.get_saved_location_text = lambda: saved["value"]

            first = nova_http.process_chat("s5_location_zip_city", "78521")
            second = nova_http.process_chat("s5_location_zip_city", "what is the name of the city that zip code belong too nova ?")

            self.assertIn("Got it - 78521 is a ZIP code.", first)
            self.assertIn("Brownsville", second)
            self.assertNotIn("local knowledge files", second.lower())
        finally:
            nova_http.nova_core.set_location_text = orig_set_location_text
            nova_http.nova_core.get_saved_location_text = orig_get_saved_location_text

    def test_http_clean_slate_blocks_location_storage(self):
        orig_set_location_text = nova_http.nova_core.set_location_text
        try:
            stored = []
            nova_http.nova_core.set_location_text = lambda value, input_source="typed": stored.append((value, input_source)) or value

            reply = nova_http.process_chat("s5_clean_slate_loc", "my location is Brownsville Texas")

            self.assertEqual(stored, [])
        finally:
            nova_http.nova_core.set_location_text = orig_set_location_text

    def test_http_clean_slate_blocks_weather_request(self):
        reply = nova_http.process_chat("s5_clean_slate_weather", "weather now")
        self.assertNotIn("api.weather.gov", reply.lower())

    def test_http_clean_slate_blocks_peims_grounding(self):
        reply = nova_http.process_chat("s5_clean_slate_peims", "what do you know about PEIMS?")
        self.assertNotIn("local knowledge files", reply.lower())
        self.assertNotIn("[source:", reply.lower())

    def test_http_bare_numeric_turn_clarifies_instead_of_using_saved_location(self):
        orig_get_saved_location_text = nova_http.nova_core.get_saved_location_text
        try:
            nova_http.nova_core.get_saved_location_text = lambda: "Brownsville, Texas"

            reply = nova_http.process_chat("s5_numeric_clarify", "78521")

            self.assertEqual("What does 78521 refer to?", reply)
            self.assertNotIn("brownsville", reply.lower())
        finally:
            nova_http.nova_core.get_saved_location_text = orig_get_saved_location_text

    def test_http_bare_numeric_followup_stays_honest_without_guessing(self):
        orig_get_saved_location_text = nova_http.nova_core.get_saved_location_text
        try:
            nova_http.nova_core.get_saved_location_text = lambda: "Brownsville, Texas"

            first = nova_http.process_chat("s5_numeric_followup", "78521")
            second = nova_http.process_chat("s5_numeric_followup", "what do you think it is nova ?")

            self.assertEqual("What does 78521 refer to?", first)
            self.assertIn("I don't know what 78521 refers to yet.", second)
            self.assertNotIn("zip code", second.lower())
        finally:
            nova_http.nova_core.get_saved_location_text = orig_get_saved_location_text

    def test_http_correction_handle_teaches_explicit_replacement(self):
        orig_mem_enabled = nova_http.nova_core.mem_enabled
        orig_mem_add = nova_http.nova_core.mem_add
        orig_teach_store_example = nova_http.nova_core._teach_store_example
        try:
            writes = []
            teaches = []
            nova_http.nova_core.mem_enabled = lambda: True
            nova_http.nova_core.mem_add = lambda kind, source, text: writes.append((kind, source, text))
            nova_http.nova_core._teach_store_example = lambda original, correction, user=None: teaches.append((original, correction, user)) or "OK"

            nova_http.process_chat("s5_correction_http", "what is tsds?")
            reply = nova_http.process_chat("s5_correction_http", "no, say 'hi gus' instead")

            self.assertEqual("Understood. I corrected that and will use your version going forward.", reply)
            correction_write = next((entry for entry in writes if entry[0] == "user_correction"), None)
            self.assertIsNotNone(correction_write)
            payload = json.loads(correction_write[2])
            self.assertEqual(payload.get("parsed_correction"), "hi gus")
            self.assertEqual(len(teaches), 1)
            self.assertEqual(teaches[0][1], "hi gus")
        finally:
            nova_http.nova_core.mem_enabled = orig_mem_enabled
            nova_http.nova_core.mem_add = orig_mem_add
            nova_http.nova_core._teach_store_example = orig_teach_store_example

    def test_http_correction_followup_teaches_pending_replacement(self):
        orig_mem_enabled = nova_http.nova_core.mem_enabled
        orig_mem_add = nova_http.nova_core.mem_add
        orig_teach_store_example = nova_http.nova_core._teach_store_example
        try:
            writes = []
            teaches = []
            nova_http.nova_core.mem_enabled = lambda: True
            nova_http.nova_core.mem_add = lambda kind, source, text: writes.append((kind, source, text))
            nova_http.nova_core._teach_store_example = lambda original, correction, user=None: teaches.append((original, correction, user)) or "OK"

            nova_http.process_chat("s5_correction_followup_http", "what is tsds?")
            first = nova_http.process_chat("s5_correction_followup_http", "no, that's wrong")
            second = nova_http.process_chat("s5_correction_followup_http", "hi gus")

            self.assertIn("I recorded that correction", first)
            self.assertEqual("Understood. I corrected that and will use your version going forward.", second)
            self.assertEqual(len(teaches), 1)
            self.assertEqual(teaches[0][1], "hi gus")
            correction_writes = [entry for entry in writes if entry[0] == "user_correction"]
            self.assertEqual(len(correction_writes), 2)
        finally:
            nova_http.nova_core.mem_enabled = orig_mem_enabled
            nova_http.nova_core.mem_add = orig_mem_add
            nova_http.nova_core._teach_store_example = orig_teach_store_example

    def test_http_declarative_statement_uses_shared_noted_path(self):
        orig_mem_should_store = nova_http.nova_core.mem_should_store
        orig_mem_add = nova_http.nova_core.mem_add
        try:
            stored = []
            nova_http.nova_core.mem_should_store = lambda text: True
            nova_http.nova_core.mem_add = lambda kind, input_source, text: stored.append((kind, input_source, text))

            with mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
                reply = nova_http.process_chat("s5_decl_store", "I work at Nova Labs")

            self.assertEqual("Noted.", reply)
            self.assertNotIn("Turn bypassed supervisor intent phase", stdout.getvalue())
            self.assertEqual(stored, [("fact", "typed", "I work at Nova Labs")])
        finally:
            nova_http.nova_core.mem_should_store = orig_mem_should_store
            nova_http.nova_core.mem_add = orig_mem_add

    def test_location_self_diagnostic_when_missing(self):
        self.orig_mem_audit = nova_http.nova_core.mem_audit
        self.orig_get_saved_location_text = nova_http.nova_core.get_saved_location_text
        self.orig_runtime_device_location_payload = nova_http.nova_core.runtime_device_location_payload
        try:
            nova_http.nova_core.mem_audit = lambda q: "{\"results\": []}"
            nova_http.nova_core.get_saved_location_text = lambda: ""
            nova_http.nova_core.runtime_device_location_payload = lambda *args, **kwargs: {"available": False, "stale": True}
            reply = nova_http.process_chat("s7", "where is nova?")
            self.assertIn("I don't have a stored location yet.", reply)
        finally:
            nova_http.nova_core.mem_audit = self.orig_mem_audit
            nova_http.nova_core.get_saved_location_text = self.orig_get_saved_location_text
            nova_http.nova_core.runtime_device_location_payload = self.orig_runtime_device_location_payload

    def test_read_text_safely_handles_utf16_without_null_padded_output(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "utf16_sample.txt"
            path.write_text("Public Education Information Management System (PEIMS).", encoding="utf-16")

            out = nova_http._read_text_safely(path)

            self.assertIn("Public Education Information Management System", out)
            self.assertNotIn("\x00", out)

    def test_peims_broad_query_no_longer_uses_peims_overview_heading(self):
        reply = nova_http.process_chat("s_peims", "what do you know about PEIMS?")
        self.assertNotIn("I found PEIMS overview details", reply)
        self.assertNotIn("[source: knowledge/", reply.lower())

    def test_tsds_query_no_longer_uses_local_knowledge_digest(self):
        reply = nova_http.process_chat("s_tsds", "what is TSDS?")
        self.assertNotIn("local knowledge files", reply.lower())
        self.assertNotIn("[source: knowledge/", reply.lower())

    def test_chat_context_uses_planner_command_route(self):
        nova_http.process_chat("s8", "hello there")
        reply = nova_http.process_chat("s8", "chat context")
        self.assertIn("Current chat context", reply)
        self.assertIn("User: chat context", reply)

    def test_keyword_route_uses_planner_delegation(self):
        nova_http.nova_core.handle_keywords = lambda text: ("tool", "web_research", "continued web research")
        reply = nova_http.process_chat("s9", "web continue")
        self.assertIn("continued web research", reply)

    def test_http_online_research_intent_uses_supervisor_tool_route_without_bypass_warning(self):
        orig_execute_planned_action = nova_http.nova_core.execute_planned_action
        try:
            nova_http.nova_core.execute_planned_action = lambda tool, args=None: "1) https://tea.texas.gov/a\n2) https://tea.texas.gov/b" if tool == "web_research" else ""
            with mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
                reply = nova_http.process_chat("s9_online", "research PEIMS online")

            self.assertIn("https://tea.texas.gov/a", reply.lower())
            self.assertNotIn("Turn bypassed supervisor intent phase", stdout.getvalue())
            session = nova_http.SESSION_STATE_MANAGER.get("s9_online")
            self.assertIsNotNone(session)
            self.assertEqual(session.active_subject(), "retrieval:web_research")
            self.assertEqual((session.retrieval_state() or {}).get("query"), "PEIMS")
        finally:
            nova_http.nova_core.execute_planned_action = orig_execute_planned_action

    def test_http_name_origin_turn_uses_supervisor_contract_without_bypass_warning(self):
        orig_get_name_origin_story = nova_http.nova_core.get_name_origin_story
        try:
            nova_http.nova_core.get_name_origin_story = lambda: "My creator Gus named me Nova to symbolize light and discovery."
            with mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
                reply = nova_http.process_chat("s9_name_origin", "why are you called Nova?")

            self.assertIn("creator gus", reply.lower())
            self.assertNotIn("Turn bypassed supervisor intent phase", stdout.getvalue())
            session = nova_http.SESSION_STATE_MANAGER.get("s9_name_origin")
            self.assertIsNotNone(session)
            self.assertEqual((session.last_reflection or {}).get("reply_contract"), "identity_history.name_origin")
        finally:
            nova_http.nova_core.get_name_origin_story = orig_get_name_origin_story

    def test_http_retrieval_followup_uses_supervisor_contract(self):
        orig_execute_planned_action = nova_http.nova_core.execute_planned_action
        orig_tool_web_gather = nova_http.nova_core.tool_web_gather
        try:
            nova_http.nova_core.execute_planned_action = lambda tool, args=None: "1) https://tea.texas.gov/a\n2) https://tea.texas.gov/b" if tool == "web_research" else ""
            nova_http.nova_core.tool_web_gather = lambda url: f"Gathered: {url}"
            with mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
                nova_http.process_chat("s9_retrieval_contract", "research PEIMS online")
                reply = nova_http.process_chat("s9_retrieval_contract", "tell me about the first one")

            self.assertEqual(reply, "Gathered: https://tea.texas.gov/a")
            self.assertNotIn("Turn bypassed supervisor intent phase", stdout.getvalue())
            session = nova_http.SESSION_STATE_MANAGER.get("s9_retrieval_contract")
            self.assertIsNotNone(session)
            self.assertEqual((session.last_reflection or {}).get("reply_contract"), "retrieval_followup.selected_result")
            self.assertEqual((session.last_reflection or {}).get("reply_outcome_kind"), "selected_result")
        finally:
            nova_http.nova_core.execute_planned_action = orig_execute_planned_action
            nova_http.nova_core.tool_web_gather = orig_tool_web_gather

    def test_http_creator_followup_uses_supervisor_contract_without_bypass_warning(self):
        with mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
            first = nova_http.process_chat("s9_identity_history", "who is your creator ?")
            reply = nova_http.process_chat("s9_identity_history", "what else?")

        self.assertIn("gustavo", first.lower())
        self.assertIn("verified facts", reply.lower())
        self.assertNotIn("Turn bypassed supervisor intent phase", stdout.getvalue())
        session = nova_http.SESSION_STATE_MANAGER.get("s9_identity_history")
        self.assertIsNotNone(session)
        self.assertEqual((session.last_reflection or {}).get("reply_contract"), "identity_history.history_recall")

    def test_code_help_uses_planner_respond(self):
        reply = nova_http.process_chat("s10", "can you debug this bug in my code")
        self.assertIn("file path", reply.lower())

    def test_http_rules_query_uses_supervisor_contract(self):
        with mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
            reply = nova_http.process_chat("s10_rules", "do you have any rules")

        self.assertIn("i follow strict operating rules", reply.lower())
        self.assertNotIn("[http] do you have any rules", stdout.getvalue())
        session = nova_http.SESSION_STATE_MANAGER.get("s10_rules")
        self.assertIsNotNone(session)
        self.assertEqual((session.last_reflection or {}).get("reply_contract"), "rules.list")
        self.assertEqual((session.last_reflection or {}).get("reply_outcome_kind"), "list")

    def test_http_pending_weather_action_uses_affirmative_followup(self):
        orig_get_saved_location_text = nova_http.nova_core.get_saved_location_text
        orig_execute_planned_action = nova_http.nova_core.execute_planned_action
        orig_weather_current_location_available = nova_http.nova_core._weather_current_location_available
        try:
            nova_http.nova_core.get_saved_location_text = lambda: "Brownsville TX"
            nova_http.nova_core._weather_current_location_available = lambda: False
            nova_http.nova_core.execute_planned_action = lambda tool, args=None: "Brownsville, TX: Today: 66°F, Sunny. [source: api.weather.gov]" if tool == "weather_current_location" else ""
            first = nova_http.process_chat("s11", "check the weather if you can please..")
            self.assertIn("location", first.lower())
            reply = nova_http.process_chat("s11", "yea please do that ..")
            self.assertIn("api.weather.gov", reply)
            session = nova_http.SESSION_STATE_MANAGER.get("s11")
            self.assertEqual((session.last_reflection or {}).get("reply_contract"), "weather_lookup.current_location")
            self.assertEqual((session.last_reflection or {}).get("reply_outcome_kind"), "current_location")
        finally:
            nova_http.nova_core.get_saved_location_text = orig_get_saved_location_text
            nova_http.nova_core.execute_planned_action = orig_execute_planned_action
            nova_http.nova_core._weather_current_location_available = orig_weather_current_location_available

    def test_http_pending_weather_action_current_location_followup_matrix(self):
        orig_get_saved_location_text = nova_http.nova_core.get_saved_location_text
        orig_execute_planned_action = nova_http.nova_core.execute_planned_action
        orig_weather_current_location_available = nova_http.nova_core._weather_current_location_available
        try:
            nova_http.nova_core.get_saved_location_text = lambda: "Brownsville TX"
            nova_http.nova_core._weather_current_location_available = lambda: False
            nova_http.nova_core.execute_planned_action = lambda tool, args=None: "Brownsville, TX: Today: 66°F, Sunny. [source: api.weather.gov]" if tool == "weather_current_location" else ""
            cases = [
                ("affirmative", "go ahead"),
                ("shared_reference", "that location"),
            ]
            for suffix, followup in cases:
                with self.subTest(followup=followup):
                    session_id = f"s11_matrix_{suffix}"
                    first = nova_http.process_chat(session_id, "check the weather if you can please..")
                    self.assertIn("location", first.lower())
                    reply = nova_http.process_chat(session_id, followup)
                    self.assertIn("api.weather.gov", reply)
                    session = nova_http.SESSION_STATE_MANAGER.get(session_id)
                    self.assertEqual((session.last_reflection or {}).get("reply_contract"), "weather_lookup.current_location")
                    self.assertEqual((session.last_reflection or {}).get("reply_outcome_kind"), "current_location")
        finally:
            nova_http.nova_core.get_saved_location_text = orig_get_saved_location_text
            nova_http.nova_core.execute_planned_action = orig_execute_planned_action
            nova_http.nova_core._weather_current_location_available = orig_weather_current_location_available

    def test_http_pending_weather_action_uses_direct_location_followup(self):
        orig_get_saved_location_text = nova_http.nova_core.get_saved_location_text
        orig_execute_planned_action = nova_http.nova_core.execute_planned_action
        orig_weather_current_location_available = nova_http.nova_core._weather_current_location_available
        try:
            nova_http.nova_core.get_saved_location_text = lambda: ""
            nova_http.nova_core._weather_current_location_available = lambda: False
            nova_http.nova_core.execute_planned_action = lambda tool, args=None: "Brownsville, TX 78521: Tomorrow: 72°F, Clear. [source: api.weather.gov]" if tool == "weather_location" else ""
            first = nova_http.process_chat("s11_direct", "check the weather if you can please..")
            self.assertIn("location", first.lower())
            reply = nova_http.process_chat("s11_direct", "Brownsville TX 78521")
            self.assertIn("api.weather.gov", reply)
            session = nova_http.SESSION_STATE_MANAGER.get("s11_direct")
            self.assertIsNone(session.pending_action)
            self.assertEqual((session.last_reflection or {}).get("reply_contract"), "weather_lookup.explicit_location")
            self.assertEqual((session.last_reflection or {}).get("reply_outcome_kind"), "explicit_location")
        finally:
            nova_http.nova_core.get_saved_location_text = orig_get_saved_location_text
            nova_http.nova_core.execute_planned_action = orig_execute_planned_action
            nova_http.nova_core._weather_current_location_available = orig_weather_current_location_available

    def test_http_generic_weather_query_uses_current_location_when_available(self):
        orig_get_saved_location_text = nova_http.nova_core.get_saved_location_text
        orig_execute_planned_action = nova_http.nova_core.execute_planned_action
        try:
            nova_http.nova_core.get_saved_location_text = lambda: "Brownsville TX"
            nova_http.nova_core.execute_planned_action = lambda tool, args=None: "Brownsville, TX: Today: 66°F, Sunny. [source: api.weather.gov]" if tool == "weather_current_location" else ""
            reply = nova_http.process_chat("s11_generic_weather", "what is the weather like today ?")
            self.assertIn("api.weather.gov", reply)
            session = nova_http.SESSION_STATE_MANAGER.get("s11_generic_weather")
            self.assertIsNotNone(session)
            self.assertEqual((session.last_reflection or {}).get("reply_contract"), "weather_lookup.current_location")
            self.assertEqual((session.last_reflection or {}).get("reply_outcome_kind"), "current_location")
        finally:
            nova_http.nova_core.get_saved_location_text = orig_get_saved_location_text
            nova_http.nova_core.execute_planned_action = orig_execute_planned_action

    def test_http_developer_followup_uses_local_developer_facts_for_nonlocal_user_id(self):
        orig_default_local_user_id = nova_http.nova_core._default_local_user_id
        try:
            nova_http.nova_core.mem_enabled = lambda: True
            nova_http.nova_core._default_local_user_id = lambda: "local-owner"

            def fake_mem_recall(_query):
                active = (nova_http.nova_core.get_active_user() or "").strip().lower()
                if active == "runner":
                    return ""
                return "\n".join([
                    "Gus works as a full stack developer and PEIMS Data Specialist.",
                    "Gus favorite colors are silver, red, and blue.",
                ])

            nova_http.nova_core.mem_recall = fake_mem_recall

            first = nova_http.process_chat("s_http_mem", "what do you know about Gus?", user_id="runner")
            followup = nova_http.process_chat("s_http_mem", "what else?", user_id="runner")

            self.assertIn("gustavo", first.lower())
            self.assertIn("full stack developer", followup.lower())
            self.assertIn("silver", followup.lower())
        finally:
            nova_http.nova_core._default_local_user_id = orig_default_local_user_id

    def test_http_developer_work_guess_uses_shared_turn_helper(self):
        reply = nova_http.process_chat("s_http_guess", "can you also guess what type of work does gus do..?")
        self.assertIn("grounded guess", reply.lower())
        session = nova_http.SESSION_STATE_MANAGER.get("s_http_guess")
        self.assertIsNotNone(session)
        self.assertEqual("developer_role_guess:Gus", session.active_subject())


if __name__ == "__main__":
    unittest.main()
