import tempfile
import unittest
from pathlib import Path

import nova_http


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

    def test_developer_who_is_answer_is_deterministic(self):
        nova_http.nova_core.mem_enabled = lambda: True
        nova_http.nova_core.mem_recall = lambda q: ""
        reply = nova_http.process_chat("s1", "who is your developer?")
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
        reply = nova_http.process_chat("s3", "how did he develop you?")
        self.assertIn("do not have detailed build-history", reply)

    def test_fast_smalltalk_greeting(self):
        reply = nova_http.process_chat("s4", "hi nova")
        self.assertEqual("Hello.", reply)

    def test_fast_smalltalk_greeting_ignores_synthetic_runner_user(self):
        reply = nova_http.process_chat("s4_runner", "hi nova", user_id="runner")
        self.assertEqual("Hello.", reply)

    def test_how_are_you_does_not_route_to_grounded_lookup(self):
        reply = nova_http.process_chat("s4_how", "how are you?")
        self.assertEqual("I'm doing well, thanks for asking.", reply)

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

        self.assertIn("local knowledge files", first.lower())
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

            self.assertEqual("Noted.", reply)
            self.assertEqual(stored, [("Brownsville Texas", "typed")])
        finally:
            nova_http.nova_core.set_location_text = orig_set_location_text

    def test_http_declarative_statement_uses_shared_noted_path(self):
        orig_mem_should_store = nova_http.nova_core.mem_should_store
        orig_mem_add = nova_http.nova_core.mem_add
        try:
            stored = []
            nova_http.nova_core.mem_should_store = lambda text: True
            nova_http.nova_core.mem_add = lambda kind, input_source, text: stored.append((kind, input_source, text))

            reply = nova_http.process_chat("s5_decl_store", "I work at Nova Labs")

            self.assertEqual("Noted.", reply)
            self.assertEqual(stored, [("fact", "typed", "I work at Nova Labs")])
        finally:
            nova_http.nova_core.mem_should_store = orig_mem_should_store
            nova_http.nova_core.mem_add = orig_mem_add

    def test_location_self_diagnostic_when_missing(self):
        self.orig_mem_audit = nova_http.nova_core.mem_audit
        self.orig_get_saved_location_text = nova_http.nova_core.get_saved_location_text
        try:
            nova_http.nova_core.mem_audit = lambda q: "{\"results\": []}"
            nova_http.nova_core.get_saved_location_text = lambda: ""
            reply = nova_http.process_chat("s7", "where is nova?")
            self.assertIn("I know:", reply)
            self.assertIn("I do not yet know:", reply)
            self.assertIn("To answer better, I need:", reply)
        finally:
            nova_http.nova_core.mem_audit = self.orig_mem_audit
            nova_http.nova_core.get_saved_location_text = self.orig_get_saved_location_text

    def test_read_text_safely_handles_utf16_without_null_padded_output(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "utf16_sample.txt"
            path.write_text("Public Education Information Management System (PEIMS).", encoding="utf-16")

            out = nova_http._read_text_safely(path)

            self.assertIn("Public Education Information Management System", out)
            self.assertNotIn("\x00", out)

    def test_peims_broad_query_uses_peims_overview_heading(self):
        reply = nova_http.process_chat("s_peims", "what do you know about PEIMS?")
        self.assertIn("I found PEIMS overview details", reply)

    def test_tsds_query_uses_local_knowledge_digest(self):
        reply = nova_http.process_chat("s_tsds", "what is TSDS?")
        self.assertIn("local knowledge files", reply.lower())
        self.assertIn("tsds", reply.lower())

    def test_chat_context_uses_planner_command_route(self):
        nova_http.process_chat("s8", "hello there")
        reply = nova_http.process_chat("s8", "chat context")
        self.assertIn("Current chat context", reply)
        self.assertIn("User: chat context", reply)

    def test_keyword_route_uses_planner_delegation(self):
        nova_http.nova_core.handle_keywords = lambda text: ("tool", "web_research", "continued web research")
        reply = nova_http.process_chat("s9", "web continue")
        self.assertIn("continued web research", reply)

    def test_code_help_uses_planner_respond(self):
        reply = nova_http.process_chat("s10", "can you debug this bug in my code")
        self.assertIn("file path", reply.lower())

    def test_http_pending_weather_action_uses_affirmative_followup(self):
        orig_get_saved_location_text = nova_http.nova_core.get_saved_location_text
        orig_execute_planned_action = nova_http.nova_core.execute_planned_action
        try:
            nova_http.nova_core.get_saved_location_text = lambda: "Brownsville TX"
            nova_http.nova_core.execute_planned_action = lambda tool, args=None: "Brownsville, TX: Today: 66°F, Sunny. [source: api.weather.gov]" if tool == "weather_current_location" else ""
            first = nova_http.process_chat("s11", "check the weather if you can please..")
            self.assertIn("location", first.lower())
            reply = nova_http.process_chat("s11", "yea please do that ..")
            self.assertIn("api.weather.gov", reply)
        finally:
            nova_http.nova_core.get_saved_location_text = orig_get_saved_location_text
            nova_http.nova_core.execute_planned_action = orig_execute_planned_action

    def test_http_pending_weather_action_uses_direct_location_followup(self):
        orig_get_saved_location_text = nova_http.nova_core.get_saved_location_text
        orig_execute_planned_action = nova_http.nova_core.execute_planned_action
        try:
            nova_http.nova_core.get_saved_location_text = lambda: ""
            nova_http.nova_core.execute_planned_action = lambda tool, args=None: "Brownsville, TX 78521: Tomorrow: 72°F, Clear. [source: api.weather.gov]" if tool == "weather_location" else ""
            first = nova_http.process_chat("s11_direct", "check the weather if you can please..")
            self.assertIn("location", first.lower())
            reply = nova_http.process_chat("s11_direct", "Brownsville TX 78521")
            self.assertIn("api.weather.gov", reply)
            session = nova_http.SESSION_STATE_MANAGER.get("s11_direct")
            self.assertIsNone(session.pending_action)
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
