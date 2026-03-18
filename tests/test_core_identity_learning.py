import unittest
from unittest import mock
import json
import io
import tempfile
from pathlib import Path

import nova_core
from conversation_manager import ConversationSession
from supervisor import Supervisor


class TestCoreIdentityLearning(unittest.TestCase):
    class _SilentTTS:
        def say(self, _text: str) -> None:
            return None

    def setUp(self):
        self.orig_get_learned_fact = nova_core.get_learned_fact
        self.orig_get_name_origin_story = nova_core.get_name_origin_story
        self.orig_action_ledger_dir = nova_core.ACTION_LEDGER_DIR
        self.orig_self_reflection_log = nova_core.SELF_REFLECTION_LOG
        self.orig_health_log = nova_core.HEALTH_LOG
        self.orig_active_user = nova_core.get_active_user()
        self._tmp_dir = tempfile.TemporaryDirectory()
        nova_core.ACTION_LEDGER_DIR = Path(self._tmp_dir.name) / "actions"
        nova_core.SELF_REFLECTION_LOG = Path(self._tmp_dir.name) / "self_reflection.jsonl"
        nova_core.HEALTH_LOG = Path(self._tmp_dir.name) / "health.log"
        nova_core.TURN_SUPERVISOR.reset()

    def tearDown(self):
        nova_core.get_learned_fact = self.orig_get_learned_fact
        nova_core.get_name_origin_story = self.orig_get_name_origin_story
        nova_core.ACTION_LEDGER_DIR = self.orig_action_ledger_dir
        nova_core.SELF_REFLECTION_LOG = self.orig_self_reflection_log
        nova_core.HEALTH_LOG = self.orig_health_log
        nova_core.set_active_user(self.orig_active_user)
        nova_core.TURN_SUPERVISOR.reset()
        self._tmp_dir.cleanup()

    def _latest_action_payload(self):
        files = sorted(nova_core.ACTION_LEDGER_DIR.glob("*.json"))
        self.assertTrue(files)
        return json.loads(files[-1].read_text(encoding="utf-8"))

    def test_hard_answer_name_and_developer(self):
        facts = {
            "assistant_name": "Nova",
            "developer_name": "Gustavo Uribe",
            "developer_nickname": "Gus",
        }
        nova_core.get_learned_fact = lambda k, default="": facts.get(k, default)
        nova_core.get_name_origin_story = lambda: "Nova was named to symbolize new light and new beginnings."

        out1 = nova_core.hard_answer("what is your name?")
        self.assertIn("my name is nova", (out1 or "").lower())

        out2 = nova_core.hard_answer("who gave you that name?")
        self.assertIn("gustavo uribe", (out2 or "").lower())

        out3 = nova_core.hard_answer("what is his full name?")
        self.assertIn("full name is gustavo uribe", (out3 or "").lower())

        out4 = nova_core.hard_answer("what is your creator's full name?")
        self.assertIn("full name is gustavo uribe", (out4 or "").lower())

        out5 = nova_core.hard_answer("who is your creator?")
        self.assertIn("my creator is gustavo uribe", (out5 or "").lower())

        out6 = nova_core.hard_answer("who made you?")
        self.assertIn("my creator is gustavo uribe", (out6 or "").lower())

        out7 = nova_core.hard_answer("how are you?")
        self.assertEqual("I'm doing well, thanks for asking.", out7)

    def test_hard_answer_name_query_tolerates_spacing(self):
        facts = {
            "assistant_name": "Nova",
            "developer_name": "Gustavo",
            "developer_nickname": "Gus",
        }
        nova_core.get_learned_fact = lambda k, default="": facts.get(k, default)
        out = nova_core.hard_answer("what is your name ?")
        self.assertIn("my name is nova", (out or "").lower())

    def test_hard_answer_name_query_tolerates_yor_typo(self):
        facts = {
            "assistant_name": "Nova",
            "developer_name": "Gustavo",
            "developer_nickname": "Gus",
        }
        nova_core.get_learned_fact = lambda k, default="": facts.get(k, default)

        out = nova_core.hard_answer("what is yor name?")
        self.assertIn("my name is nova", (out or "").lower())

    def test_hard_answer_identity_web_challenge_stays_deterministic(self):
        facts = {
            "assistant_name": "Nova",
            "developer_name": "Gustavo",
            "developer_nickname": "Gus",
        }
        nova_core.get_learned_fact = lambda k, default="": facts.get(k, default)

        out = nova_core.hard_answer("why should i try to use the web for your name ?")
        self.assertIn("should not need web research", (out or "").lower())
        self.assertIn("my name is nova", (out or "").lower())

    def test_normalize_turn_text_fixes_common_query_typos(self):
        out = nova_core._normalize_turn_text("what is yor name ?")
        self.assertEqual(out, "what is your name ?")

    def test_normalize_turn_text_fixes_resource_meta_typos(self):
        out = nova_core._normalize_turn_text("what type of resources are you tring to fetch nova ?")
        self.assertIn("trying", out)
        self.assertIn("resources", out)

    def test_normalize_turn_text_fixes_location_typo(self):
        out = nova_core._normalize_turn_text("Give me the weather for your current physical locaiton nova")
        self.assertIn("location", out)

    def test_local_topic_digest_returns_tsds_knowledge(self):
        out = nova_core._build_local_topic_digest_answer("what is TSDS?")
        self.assertIn("local knowledge files", out.lower())
        self.assertIn("tsds", out.lower())

    def test_hard_answer_why_is_name_nova(self):
        facts = {
            "assistant_name": "Nova",
            "developer_name": "Gustavo",
            "developer_nickname": "Gus",
        }
        nova_core.get_learned_fact = lambda k, default="": facts.get(k, default)
        nova_core.get_name_origin_story = lambda: "Nova symbolizes new light and new beginnings."
        out = nova_core.hard_answer("Why is your name Nova?")
        self.assertIn("new light", (out or "").lower())

    def test_extract_name_origin_teach_text(self):
        t1 = "Please remember this ... Nova was given its name by its creator, Gus, as a symbol of new light."
        out1 = nova_core.extract_name_origin_teach_text(t1)
        self.assertNotIn("remember this", out1.lower())
        self.assertIn("nova was given", out1.lower())

        t2 = (
            "Nova was given as a symbol of new light and new beginnings. "
            "In astronomy, a nova occurs when a star suddenly becomes brighter. "
            "That idea inspired the name."
        )
        out2 = nova_core.extract_name_origin_teach_text(t2)
        self.assertIn("symbol of new light", out2.lower())

    def test_learn_from_mixed_name_correction_phrase(self):
        # Isolate persistence for this test by stubbing load/save.
        orig_load = nova_core.load_learned_facts
        orig_save = nova_core.save_learned_facts
        orig_mem_enabled = nova_core.mem_enabled
        try:
            state = {}
            nova_core.load_learned_facts = lambda: dict(state)
            nova_core.save_learned_facts = lambda d: state.update(d)
            nova_core.mem_enabled = lambda: False

            changed, msg = nova_core.learn_from_user_correction(
                "your right about something, your name is Nova and my name is Nova because that's the name I was given"
            )
            self.assertTrue(changed)
            self.assertIn("assistant_name=Nova", msg)
        finally:
            nova_core.load_learned_facts = orig_load
            nova_core.save_learned_facts = orig_save
            nova_core.mem_enabled = orig_mem_enabled

    def test_learn_from_typoed_developer_full_name_with_suffix(self):
        orig_load = nova_core.load_learned_facts
        orig_save = nova_core.save_learned_facts
        orig_mem_enabled = nova_core.mem_enabled
        try:
            state = {}
            nova_core.load_learned_facts = lambda: dict(state)
            nova_core.save_learned_facts = lambda d: state.update(d)
            nova_core.mem_enabled = lambda: False

            changed, msg = nova_core.learn_from_user_correction("the develper's full name is Gustavo Uribe Jr")
            self.assertTrue(changed)
            self.assertIn("developer_name=Gustavo Uribe Jr", msg)
        finally:
            nova_core.load_learned_facts = orig_load
            nova_core.save_learned_facts = orig_save
            nova_core.mem_enabled = orig_mem_enabled

    def test_learn_from_creator_self_identification_sets_developer_nickname(self):
        orig_load = nova_core.load_learned_facts
        orig_save = nova_core.save_learned_facts
        orig_mem_enabled = nova_core.mem_enabled
        try:
            state = {"developer_name": "Gustavo Uribe"}
            nova_core.load_learned_facts = lambda: dict(state)
            nova_core.save_learned_facts = lambda d: state.update(d)
            nova_core.mem_enabled = lambda: False
            nova_core.set_active_user(None)

            changed, msg = nova_core.learn_from_user_correction(
                "I am Gus the creator and developer of Nova"
            )
            self.assertTrue(changed)
            self.assertIn("developer_nickname=Gus", msg)
            self.assertEqual(state.get("developer_nickname"), "Gus")
            self.assertEqual(nova_core.get_active_user(), "Gus")
        finally:
            nova_core.load_learned_facts = orig_load
            nova_core.save_learned_facts = orig_save
            nova_core.mem_enabled = orig_mem_enabled

    def test_learn_from_typoed_creator_binding_uses_known_developer_identity(self):
        orig_load = nova_core.load_learned_facts
        orig_save = nova_core.save_learned_facts
        orig_mem_enabled = nova_core.mem_enabled
        orig_get_learned_fact = nova_core.get_learned_fact
        try:
            state = {}
            nova_core.load_learned_facts = lambda: dict(state)
            nova_core.save_learned_facts = lambda d: state.update(d)
            nova_core.mem_enabled = lambda: False
            nova_core.get_learned_fact = lambda k, default="": {
                "developer_name": "Gustavo Uribe",
                "developer_nickname": "Gus",
            }.get(k, default)
            nova_core.set_active_user(None)

            changed, msg = nova_core.learn_from_user_correction("yes Iam nova's creator")
            self.assertTrue(changed)
            self.assertIn("identity_binding=developer", msg)
            self.assertEqual(nova_core.get_active_user(), "Gustavo Uribe")
        finally:
            nova_core.load_learned_facts = orig_load
            nova_core.save_learned_facts = orig_save
            nova_core.mem_enabled = orig_mem_enabled
            nova_core.get_learned_fact = orig_get_learned_fact

    def test_learn_from_same_person_developer_statement_does_not_capture_your_as_name(self):
        orig_load = nova_core.load_learned_facts
        orig_save = nova_core.save_learned_facts
        orig_mem_enabled = nova_core.mem_enabled
        try:
            state = {
                "developer_name": "Gustavo Uribe",
                "developer_nickname": "Gus",
            }
            nova_core.load_learned_facts = lambda: dict(state)
            nova_core.save_learned_facts = lambda d: state.update(d)
            nova_core.mem_enabled = lambda: False
            nova_core.set_active_user(None)

            changed, msg = nova_core.learn_from_user_correction(
                "well i am the same person and i am your developer and i am fixing you"
            )
            self.assertTrue(changed)
            self.assertIn("identity_binding=developer", msg)
            self.assertEqual(state.get("developer_nickname"), "Gus")
            self.assertEqual(nova_core.get_active_user(), "Gustavo Uribe")
            self.assertNotIn("developer_nickname=Your", msg)
        finally:
            nova_core.load_learned_facts = orig_load
            nova_core.save_learned_facts = orig_save
            nova_core.mem_enabled = orig_mem_enabled

    def test_greeting_ignores_default_local_username(self):
        orig_default_local_user_id = nova_core._default_local_user_id
        try:
            nova_core._default_local_user_id = lambda: "guribe"
            out = nova_core._build_greeting_reply("hi nova", active_user="guribe")
            self.assertEqual(out, "Hello.")
        finally:
            nova_core._default_local_user_id = orig_default_local_user_id

    def test_sanitize_learned_facts_repairs_invalid_developer_nickname(self):
        out = nova_core._sanitize_learned_facts(
            {"developer_name": "Gustavo Uribe", "developer_nickname": "Your"}
        )
        self.assertNotIn("developer_nickname", out)

    def test_simple_i_am_gus_binds_known_developer_identity(self):
        orig_get_learned_fact = nova_core.get_learned_fact
        try:
            nova_core.get_learned_fact = lambda k, default="": {
                "developer_name": "Gustavo Uribe",
                "developer_nickname": "Gus",
            }.get(k, default)
            nova_core.set_active_user(None)

            changed, msg = nova_core._learn_self_identity_binding("I am gus!")
            self.assertTrue(changed)
            self.assertIn("identity confirmed", msg.lower())
            self.assertEqual(nova_core.get_active_user(), "Gustavo Uribe")
        finally:
            nova_core.get_learned_fact = orig_get_learned_fact

    def test_contextual_self_facts_store_colors_for_bound_developer(self):
        orig_mem_enabled = nova_core.mem_enabled
        orig_mem_add = nova_core.mem_add
        orig_get_learned_fact = nova_core.get_learned_fact
        try:
            writes = []
            nova_core.mem_enabled = lambda: True
            nova_core.mem_add = lambda kind, source, text: writes.append((kind, source, text))
            nova_core.get_learned_fact = lambda k, default="": {
                "developer_name": "Gustavo Uribe",
                "developer_nickname": "Gus",
            }.get(k, default)
            nova_core.set_active_user("Gustavo Uribe")

            learned, msg = nova_core._learn_contextual_self_facts(
                "my favortie colors are silver , blue and red"
            )
            self.assertTrue(learned)
            self.assertIn("favorite colors", msg.lower())
            self.assertTrue(any(item[2] == "Gus favorite colors are silver, blue, and red." for item in writes))
        finally:
            nova_core.mem_enabled = orig_mem_enabled
            nova_core.mem_add = orig_mem_add
            nova_core.get_learned_fact = orig_get_learned_fact

    def test_hard_answer_what_do_you_know_about_me_uses_bound_identity(self):
        orig_get_learned_fact = nova_core.get_learned_fact
        orig_get_name_origin_story = nova_core.get_name_origin_story
        orig_extract_developer_color_preferences_from_memory = nova_core._extract_developer_color_preferences_from_memory
        try:
            nova_core.get_learned_fact = lambda k, default="": {
                "assistant_name": "Nova",
                "developer_name": "Gustavo Uribe",
                "developer_nickname": "Gus",
            }.get(k, default)
            nova_core.get_name_origin_story = lambda: "Nova was given its name by Gus."
            nova_core._extract_developer_color_preferences_from_memory = lambda: ["silver", "blue", "red"]
            nova_core.set_active_user("Gustavo Uribe")

            out = nova_core.hard_answer("what else do you know about me?")
            self.assertIn("you are gustavo uribe", (out or "").lower())
            self.assertIn("favorite colors", (out or "").lower())
        finally:
            nova_core.get_learned_fact = orig_get_learned_fact
            nova_core.get_name_origin_story = orig_get_name_origin_story
            nova_core._extract_developer_color_preferences_from_memory = orig_extract_developer_color_preferences_from_memory

    def test_hard_answer_remember_me_uses_verified_identity_only(self):
        orig_get_learned_fact = nova_core.get_learned_fact
        try:
            nova_core.get_learned_fact = lambda k, default="": {
                "assistant_name": "Nova",
                "developer_name": "Gustavo Uribe",
                "developer_nickname": "Gus",
            }.get(k, default)
            nova_core.set_active_user("Gustavo Uribe")

            out = nova_core.hard_answer("do you remember me ?")
            self.assertIn("i remember you as gustavo uribe", (out or "").lower())
            self.assertNotIn("classic rock", (out or "").lower())
        finally:
            nova_core.get_learned_fact = orig_get_learned_fact

    def test_hard_answer_what_is_my_name_returns_verified_name(self):
        orig_get_learned_fact = nova_core.get_learned_fact
        try:
            nova_core.get_learned_fact = lambda k, default="": {
                "assistant_name": "Nova",
                "developer_name": "Gustavo Uribe",
                "developer_nickname": "Gus",
            }.get(k, default)
            nova_core.set_active_user("Gustavo Uribe")

            out = nova_core.hard_answer("yes so what is my name ?")
            self.assertIn("your name is gustavo uribe", (out or "").lower())
            self.assertNotIn("gus told me", (out or "").lower())
        finally:
            nova_core.get_learned_fact = orig_get_learned_fact

    def test_hard_answer_what_else_do_you_know_about_me_returns_bounded_known_name(self):
        orig_get_learned_fact = nova_core.get_learned_fact
        try:
            nova_core.get_learned_fact = lambda k, default="": {
                "assistant_name": "Nova",
                "developer_name": "Gustavo Uribe",
                "developer_nickname": "Gus",
            }.get(k, default)
            nova_core.set_active_user("Gustavo Uribe")

            out = nova_core.hard_answer("what else do you know about me nova ?")
            self.assertIn("you are gustavo uribe", (out or "").lower())
            self.assertNotIn("classic rock", (out or "").lower())
        finally:
            nova_core.get_learned_fact = orig_get_learned_fact

    def test_hard_answer_rejects_name_only_personal_inference(self):
        orig_get_learned_fact = nova_core.get_learned_fact
        try:
            nova_core.get_learned_fact = lambda k, default="": {
                "assistant_name": "Nova",
                "developer_name": "Gustavo Uribe",
                "developer_nickname": "Gus",
            }.get(k, default)
            nova_core.set_active_user("Gustavo Uribe")

            out = nova_core.hard_answer("you know my name and i am sure you can find out more info by just knowing my name gus")
            self.assertIn("knowing your name alone does not justify inventing more personal facts", (out or "").lower())
            self.assertNotIn("classic rock", (out or "").lower())
        finally:
            nova_core.get_learned_fact = orig_get_learned_fact

    def test_contextual_developer_fact_learning_stores_colors_and_bilingual(self):
        orig_mem_enabled = nova_core.mem_enabled
        orig_mem_add = nova_core.mem_add
        try:
            writes = []
            nova_core.mem_enabled = lambda: True
            nova_core.mem_add = lambda kind, source, text: writes.append((kind, source, text))

            learned, msg = nova_core._learn_contextual_developer_facts(
                [("user", "What do you know about Gus?")],
                "favorite colors are silver, blue and red and he's bilingual in English and Spanish",
            )
            self.assertTrue(learned)
            self.assertIn("favorite colors", msg.lower())
            self.assertIn("bilingual", msg.lower())
            self.assertIn(("identity", "typed", "Gus is bilingual in English and Spanish."), writes)
            self.assertTrue(any("Gus favorite colors are silver, blue, and red." == item[2] for item in writes))
        finally:
            nova_core.mem_enabled = orig_mem_enabled
            nova_core.mem_add = orig_mem_add

    def test_developer_role_guess_query_detected(self):
        self.assertTrue(nova_core._is_developer_work_guess_query("can you also guess what type of work does gus do..?"))

    def test_developer_work_guess_turn_returns_reply_and_state(self):
        reply, state = nova_core._developer_work_guess_turn("can you also guess what type of work does gus do..?")
        self.assertIn("grounded guess", reply.lower())
        self.assertEqual({"kind": "developer_role_guess", "subject": "Gus"}, state)

    def test_stateful_developer_role_followup_learns_without_name_repeated(self):
        orig_mem_enabled = nova_core.mem_enabled
        orig_mem_add = nova_core.mem_add
        try:
            writes = []
            nova_core.mem_enabled = lambda: True
            nova_core.mem_add = lambda kind, source, text: writes.append((kind, source, text))

            handled, msg, next_state = nova_core._consume_conversation_followup(
                {"kind": "developer_role_guess", "subject": "Gus"},
                "yes you're right nova he is a full stack developer that works as PEIMS Data Specialist",
            )
            self.assertTrue(handled)
            self.assertIsNone(next_state)
            self.assertIn("full stack developer", (msg or "").lower())
            self.assertTrue(any("peims data specialist" in item[2].lower() for item in writes))
        finally:
            nova_core.mem_enabled = orig_mem_enabled
            nova_core.mem_add = orig_mem_add

    def test_profile_state_followup_returns_verified_developer_facts(self):
        orig_get_learned_fact = nova_core.get_learned_fact
        orig_get_name_origin_story = nova_core.get_name_origin_story
        orig_extract_developer_color_preferences_from_memory = nova_core._extract_developer_color_preferences_from_memory
        orig_developer_is_bilingual_from_memory = nova_core._developer_is_bilingual_from_memory
        orig_extract_developer_roles_from_memory = nova_core._extract_developer_roles_from_memory
        try:
            nova_core.get_learned_fact = lambda k, default="": {
                "developer_name": "Gustavo Uribe",
                "developer_nickname": "Gus",
            }.get(k, default)
            nova_core.get_name_origin_story = lambda: "Nova was given its name by Gus."
            nova_core._extract_developer_color_preferences_from_memory = lambda: ["silver", "blue"]
            nova_core._developer_is_bilingual_from_memory = lambda: True
            nova_core._extract_developer_roles_from_memory = lambda: ["full stack developer", "PEIMS Data Specialist"]

            handled, msg, next_state = nova_core._consume_conversation_followup(
                {"kind": "identity_profile", "subject": "developer"},
                "go on",
                turns=[],
            )
            self.assertTrue(handled)
            self.assertEqual(next_state, {"kind": "identity_profile", "subject": "developer"})
            low = (msg or "").lower()
            self.assertIn("gustavo uribe", low)
            self.assertIn("peims data specialist", low)
            self.assertIn("english and spanish", low)
        finally:
            nova_core.get_learned_fact = orig_get_learned_fact
            nova_core.get_name_origin_story = orig_get_name_origin_story
            nova_core._extract_developer_color_preferences_from_memory = orig_extract_developer_color_preferences_from_memory
            nova_core._developer_is_bilingual_from_memory = orig_developer_is_bilingual_from_memory
            nova_core._extract_developer_roles_from_memory = orig_extract_developer_roles_from_memory

    def test_profile_state_name_followup_returns_verified_developer_identity(self):
        orig_get_learned_fact = nova_core.get_learned_fact
        orig_get_name_origin_story = nova_core.get_name_origin_story
        try:
            nova_core.get_learned_fact = lambda k, default="": {
                "assistant_name": "Nova",
                "developer_name": "Gustavo Uribe",
                "developer_nickname": "Gus",
            }.get(k, default)
            nova_core.get_name_origin_story = lambda: "Nova was given its name by Gus."
            nova_core.set_active_user("Gustavo Uribe")

            handled, msg, next_state = nova_core._consume_conversation_followup(
                {"kind": "identity_profile", "subject": "self"},
                "tell me more about my name",
                turns=[],
            )
            self.assertTrue(handled)
            self.assertEqual(next_state, {"kind": "identity_profile", "subject": "self"})
            low = (msg or "").lower()
            self.assertIn("your verified full name is gustavo uribe", low)
            self.assertIn("you also go by gus", low)
            self.assertIn("you gave me the name nova", low)
        finally:
            nova_core.get_learned_fact = orig_get_learned_fact
            nova_core.get_name_origin_story = orig_get_name_origin_story

    def test_infer_profile_conversation_state_uses_developer_identity_when_session_confirmed(self):
        orig_get_learned_fact = nova_core.get_learned_fact
        try:
            nova_core.get_learned_fact = lambda k, default="": {
                "developer_name": "Gustavo Uribe",
                "developer_nickname": "Gus",
            }.get(k, default)
            nova_core.set_active_user("Gustavo Uribe")

            state = nova_core._infer_profile_conversation_state("what colors do I like?")
            self.assertEqual(state, {"kind": "developer_identity", "subject": "developer"})
        finally:
            nova_core.get_learned_fact = orig_get_learned_fact

    def test_developer_identity_followup_returns_richer_name_story(self):
        orig_get_learned_fact = nova_core.get_learned_fact
        orig_get_name_origin_story = nova_core.get_name_origin_story
        orig_extract_developer_roles_from_memory = nova_core._extract_developer_roles_from_memory
        try:
            nova_core.get_learned_fact = lambda k, default="": {
                "assistant_name": "Nova",
                "developer_name": "Gustavo Uribe",
                "developer_nickname": "Gus",
            }.get(k, default)
            nova_core.get_name_origin_story = lambda: "Nova was given its name as a symbol of new light and new beginnings."
            nova_core._extract_developer_roles_from_memory = lambda: ["PEIMS Data Specialist"]
            nova_core.set_active_user("Gustavo Uribe")

            handled, msg, next_state = nova_core._consume_conversation_followup(
                {"kind": "developer_identity", "subject": "developer"},
                "tell me more about my name",
                turns=[],
            )
            self.assertTrue(handled)
            self.assertEqual(next_state, {"kind": "developer_identity", "subject": "developer"})
            low = (msg or "").lower()
            self.assertIn("about your name and identity", low)
            self.assertIn("gustavo uribe", low)
            self.assertIn("you are the creator who gave me the name nova", low)
            self.assertIn("new light and new beginnings", low)
        finally:
            nova_core.get_learned_fact = orig_get_learned_fact
            nova_core.get_name_origin_story = orig_get_name_origin_story
            nova_core._extract_developer_roles_from_memory = orig_extract_developer_roles_from_memory

    def test_developer_identity_general_followup_returns_richer_profile(self):
        orig_get_learned_fact = nova_core.get_learned_fact
        orig_get_name_origin_story = nova_core.get_name_origin_story
        orig_extract_developer_roles_from_memory = nova_core._extract_developer_roles_from_memory
        orig_extract_developer_color_preferences_from_memory = nova_core._extract_developer_color_preferences_from_memory
        orig_developer_is_bilingual_from_memory = nova_core._developer_is_bilingual_from_memory
        try:
            nova_core.get_learned_fact = lambda k, default="": {
                "assistant_name": "Nova",
                "developer_name": "Gustavo Uribe",
                "developer_nickname": "Gus",
            }.get(k, default)
            nova_core.get_name_origin_story = lambda: "Nova was given its name by Gus."
            nova_core._extract_developer_roles_from_memory = lambda: ["full stack developer", "PEIMS Data Specialist"]
            nova_core._extract_developer_color_preferences_from_memory = lambda: ["silver", "blue"]
            nova_core._developer_is_bilingual_from_memory = lambda: True
            nova_core.set_active_user("Gustavo Uribe")

            handled, msg, next_state = nova_core._consume_conversation_followup(
                {"kind": "developer_identity", "subject": "developer"},
                "go on",
                turns=[],
            )
            self.assertTrue(handled)
            self.assertEqual(next_state, {"kind": "developer_identity", "subject": "developer"})
            low = (msg or "").lower()
            self.assertIn("richer verified developer facts", low)
            self.assertIn("full stack developer", low)
            self.assertIn("peims data specialist", low)
            self.assertIn("english and spanish", low)
        finally:
            nova_core.get_learned_fact = orig_get_learned_fact
            nova_core.get_name_origin_story = orig_get_name_origin_story
            nova_core._extract_developer_roles_from_memory = orig_extract_developer_roles_from_memory
            nova_core._extract_developer_color_preferences_from_memory = orig_extract_developer_color_preferences_from_memory
            nova_core._developer_is_bilingual_from_memory = orig_developer_is_bilingual_from_memory

    def test_retrieval_followup_continues_cached_web_research(self):
        orig_last_query = nova_core.WEB_RESEARCH_LAST_QUERY
        orig_last_results = list(nova_core.WEB_RESEARCH_LAST_RESULTS)
        orig_cursor = nova_core.WEB_RESEARCH_CURSOR
        try:
            nova_core.WEB_RESEARCH_LAST_QUERY = "peims attendance"
            nova_core.WEB_RESEARCH_LAST_RESULTS = [
                (9.0, "https://tea.texas.gov/a", "First result snippet"),
                (8.5, "https://tea.texas.gov/b", "Second result snippet"),
            ]
            nova_core.WEB_RESEARCH_CURSOR = 1

            handled, msg, next_state = nova_core._consume_conversation_followup(
                {"kind": "retrieval", "subject": "web_research", "query": "peims attendance", "result_count": 2, "urls": ["https://tea.texas.gov/a"]},
                "what else",
                turns=[],
            )
            self.assertTrue(handled)
            self.assertEqual(next_state.get("kind"), "retrieval")
            self.assertEqual(next_state.get("subject"), "web_research")
            self.assertIn("continued", (msg or "").lower())
            self.assertIn("peims attendance", (msg or "").lower())
        finally:
            nova_core.WEB_RESEARCH_LAST_QUERY = orig_last_query
            nova_core.WEB_RESEARCH_LAST_RESULTS = orig_last_results
            nova_core.WEB_RESEARCH_CURSOR = orig_cursor

    def test_retrieval_followup_gathers_selected_result(self):
        orig_tool_web_gather = nova_core.tool_web_gather
        try:
            nova_core.tool_web_gather = lambda url: f"[OK] Gathered {url}\nSummary snippet:\nExample content"
            handled, msg, next_state = nova_core._consume_conversation_followup(
                {
                    "kind": "retrieval",
                    "subject": "web_search",
                    "query": "peims attendance",
                    "result_count": 2,
                    "urls": ["https://tea.texas.gov/one", "https://tea.texas.gov/two"],
                },
                "tell me about the first one",
                turns=[],
            )
            self.assertTrue(handled)
            self.assertIn("gathered https://tea.texas.gov/one", (msg or "").lower())
            self.assertEqual(next_state.get("kind"), "retrieval")
            self.assertEqual(next_state.get("subject"), "web_gather")
        finally:
            nova_core.tool_web_gather = orig_tool_web_gather

    def test_extract_memory_teach_text(self):
        out = nova_core._extract_memory_teach_text(
            "think you can remember that PEIMS applies to BISD submissions too"
        )
        self.assertEqual(out, "PEIMS applies to BISD submissions too")

    def test_hard_answer_resolves_my_full_name_from_active_developer_identity(self):
        facts = {
            "assistant_name": "Nova",
            "developer_name": "Gustavo Uribe",
            "developer_nickname": "Gus",
        }
        nova_core.get_learned_fact = lambda k, default="": facts.get(k, default)
        nova_core.set_active_user("Gus")

        out = nova_core.hard_answer("so do you know my full name?")
        self.assertIn("your full name is gustavo uribe", (out or "").lower())

    def test_analyze_routing_text_reuses_prior_identity_question_for_keep_trying(self):
        turns = [
            ("user", "do you know my full name ?"),
            ("assistant", "Uncertain. No structured identity fact is available yet."),
            ("user", "keep trying"),
        ]
        effective, reason = nova_core._analyze_routing_text(turns, "keep trying")
        self.assertEqual(effective, "do you know my full name ?")
        self.assertEqual(reason, "reflective_retry_prior_question")

    def test_analyze_routing_text_reuses_prior_color_question_for_almost_there(self):
        turns = [
            ("user", "what are Gus's favorite colors?"),
            ("assistant", "I don't have Gus's color preferences yet."),
            ("user", "keep trying your almost there .."),
        ]
        effective, reason = nova_core._analyze_routing_text(turns, "keep trying your almost there ..")
        self.assertEqual(effective, "what are Gus's favorite colors?")
        self.assertEqual(reason, "reflective_retry_prior_question")

    def test_determine_turn_direction_marks_identity_query_and_bypasses_pattern_routes(self):
        turns = [("user", "what else do you know about me?")]
        out = nova_core._determine_turn_direction(turns, "what else do you know about me?")
        self.assertEqual(out.get("primary"), "identity_query")
        self.assertTrue(out.get("identity_focused"))
        self.assertTrue(out.get("bypass_pattern_routes"))

    def test_determine_turn_direction_marks_remember_me_as_identity_query(self):
        out = nova_core._determine_turn_direction([], "do you remember me ?")
        self.assertEqual(out.get("primary"), "identity_query")
        self.assertTrue(out.get("identity_focused"))
        self.assertTrue(out.get("bypass_pattern_routes"))

    def test_determine_turn_direction_reframes_reflective_retry_before_routing(self):
        turns = [
            ("user", "what are Gus's favorite colors?"),
            ("assistant", "I don't have Gus's color preferences yet."),
            ("user", "keep trying search your logs and data banks"),
        ]
        out = nova_core._determine_turn_direction(turns, "keep trying search your logs and data banks")
        self.assertEqual(out.get("primary"), "identity_query")
        self.assertEqual(out.get("effective_query"), "what are Gus's favorite colors?")
        self.assertTrue(out.get("bypass_pattern_routes"))

    def test_determine_turn_direction_keeps_explicit_commands_pattern_routable(self):
        out = nova_core._determine_turn_direction([], "web search weather in brownsville")
        self.assertEqual(out.get("primary"), "explicit_command")
        self.assertFalse(out.get("bypass_pattern_routes"))

    def test_web_override_request_detects_all_you_need_is_the_web_phrase(self):
        self.assertTrue(nova_core._is_web_research_override_request(
            "you do not need all those tools to know more about PEIMS.. all you need is the Web"
        ))

    def test_action_history_query_does_not_claim_what_did_you_find(self):
        self.assertFalse(nova_core._is_action_history_query("what did you find"))

    def test_location_recall_query_detection(self):
        self.assertTrue(nova_core._is_location_recall_query("yes can you recall my location ?"))

    def test_location_recall_reply_uses_saved_location(self):
        orig_get_saved_location_text = nova_core.get_saved_location_text
        try:
            nova_core.get_saved_location_text = lambda: "Brownsville, Texas"
            out = nova_core._location_recall_reply()
            self.assertIn("your saved location is brownsville, texas", (out or "").lower())
        finally:
            nova_core.get_saved_location_text = orig_get_saved_location_text

    def test_location_recall_followup_detection_uses_recent_context(self):
        turns = [
            ("user", "yes can you recall my location ?"),
            ("assistant", "Your saved location is Brownsville, Texas."),
        ]
        self.assertTrue(nova_core._looks_like_location_recall_followup(turns, "well what did you find ?"))

    def test_location_recall_state_handles_generic_followup(self):
        orig_get_saved_location_text = nova_core.get_saved_location_text
        try:
            nova_core.get_saved_location_text = lambda: "Brownsville, Texas"
            handled, msg, next_state = nova_core._consume_conversation_followup(
                {"kind": "location_recall"},
                "what else?",
            )
            self.assertTrue(handled)
            self.assertEqual(next_state, {"kind": "location_recall"})
            self.assertIn("brownsville, texas", (msg or "").lower())
        finally:
            nova_core.get_saved_location_text = orig_get_saved_location_text

    def test_profile_state_followup_returns_verified_self_facts(self):
        orig_extract_color_preferences_from_memory = nova_core._extract_color_preferences_from_memory
        orig_extract_animal_preferences_from_memory = nova_core._extract_animal_preferences_from_memory
        try:
            nova_core.set_active_user("Ana")
            nova_core._extract_color_preferences_from_memory = lambda: ["green"]
            nova_core._extract_animal_preferences_from_memory = lambda: ["dogs"]

            handled, msg, next_state = nova_core._consume_conversation_followup(
                {"kind": "identity_profile", "subject": "self"},
                "what else?",
                turns=[],
            )
            self.assertTrue(handled)
            self.assertEqual(next_state, {"kind": "identity_profile", "subject": "self"})
            low = (msg or "").lower()
            self.assertIn("ana", low)
            self.assertIn("green", low)
            self.assertIn("dogs", low)
        finally:
            nova_core._extract_color_preferences_from_memory = orig_extract_color_preferences_from_memory
            nova_core._extract_animal_preferences_from_memory = orig_extract_animal_preferences_from_memory

    def test_profile_state_followup_handles_are_you_sure_thats_all(self):
        handled, msg, next_state = nova_core._consume_conversation_followup(
            {"kind": "identity_profile", "subject": "developer"},
            "are you sure that is all the information you about him?",
            turns=[],
        )
        self.assertTrue(handled)
        self.assertEqual(next_state, {"kind": "identity_profile", "subject": "developer"})
        self.assertIn("verified facts", (msg or "").lower())

    def test_retrieval_state_handles_resource_meta_question(self):
        handled, msg, next_state = nova_core._consume_conversation_followup(
            {
                "kind": "retrieval",
                "subject": "web_research",
                "query": "gus developer facts",
                "urls": ["https://tea.texas.gov/", "https://txschools.gov/"],
                "result_count": 2,
            },
            "what type of resources are you tring to fetch nova ?",
            turns=[],
        )
        self.assertTrue(handled)
        self.assertEqual(next_state.get("kind"), "retrieval")
        low = (msg or "").lower()
        self.assertIn("allowlisted web sources", low)
        self.assertIn("tea.texas.gov", low)

    def test_profile_state_handles_resource_meta_question_without_web_lookup(self):
        handled, msg, next_state = nova_core._consume_conversation_followup(
            {"kind": "identity_profile", "subject": "developer"},
            "what type of resources are you tring to fetch nova ?",
            turns=[],
        )
        self.assertTrue(handled)
        self.assertEqual(next_state, {"kind": "identity_profile", "subject": "developer"})
        self.assertIn("not trying to fetch web resources", (msg or "").lower())

    def test_infer_profile_conversation_state_marks_creator_as_developer_profile(self):
        state = nova_core._infer_profile_conversation_state("who is your creator?")
        self.assertEqual(state, {"kind": "identity_profile", "subject": "developer"})

    def test_retrieval_status_reply_asks_for_target(self):
        self.assertEqual(nova_core._retrieval_status_reply("retreiving data"), "What data do you want me to retrieve?")

    def test_negative_feedback_detection(self):
        self.assertTrue(nova_core._is_negative_feedback("you gave me garbage back why"))
        self.assertTrue(nova_core._is_negative_feedback("you are wrong about that"))
        self.assertFalse(nova_core._is_negative_feedback("thanks that helped"))

    def test_extract_authoritative_correction_text(self):
        t = "You're right about something. Nova was given its name by its creator, Gus, as a symbol of new light and new beginnings."
        out = nova_core._extract_authoritative_correction_text(t)
        self.assertIsNotNone(out)
        self.assertIn("nova was given", (out or "").lower())

        q = "why is your name nova?"
        out_q = nova_core._extract_authoritative_correction_text(q)
        self.assertIsNone(out_q)

        s = "My name is Nova. Please use Nova going forward."
        out_s = nova_core._extract_authoritative_correction_text(s)
        self.assertIsNotNone(out_s)
        self.assertIn("my name is nova", (out_s or "").lower())

    def test_normalize_correction_for_storage(self):
        raw = "My name is Nova. Please use Nova going forward."
        out = nova_core._normalize_correction_for_storage(raw)
        self.assertEqual(out, "My name is Nova.")

    def test_should_block_low_confidence(self):
        self.assertTrue(nova_core.should_block_low_confidence("what are the PEIMS rules?", retrieved_context="", tool_context=""))
        self.assertFalse(nova_core.should_block_low_confidence("what are the PEIMS rules?", retrieved_context="some context", tool_context=""))

    def test_behavior_stats_command(self):
        out = nova_core.handle_commands("behavior stats")
        self.assertIn("deterministic_hit", (out or ""))

    def test_learning_state_command(self):
        out = nova_core.handle_commands("learning state")
        self.assertIn("correction_learned", (out or ""))
        self.assertIn("self_correction_applied", (out or ""))
        self.assertIn("routing_stable", (out or ""))

    def test_detect_repeated_tool_intent_without_execution(self):
        records = [
            {
                "intent": "weather_lookup",
                "planner_decision": "ask_clarify",
                "route_trace": [
                    {"stage": "input", "outcome": "received"},
                    {"stage": "action_planner", "outcome": "ask_clarify"},
                ],
                "tool_result": "",
            },
            {
                "intent": "weather_lookup",
                "route_trace": [
                    {"stage": "input", "outcome": "received"},
                    {"stage": "llm_fallback", "outcome": "invoked"},
                ],
                "tool_result": "",
            },
            {
                "intent": "weather_lookup",
                "route_trace": [
                    {"stage": "input", "outcome": "received"},
                    {"stage": "action_planner", "outcome": "run_tool"},
                ],
                "tool_result": "",
            },
        ]
        out = nova_core._detect_repeated_tool_intent_without_execution(records=records)
        self.assertEqual(out.get("intent"), "weather_lookup")
        self.assertEqual(out.get("selected"), 2)
        self.assertEqual(out.get("completed"), 0)
        self.assertIn("Weather route selected 2 times, execution completed 0 times.", out.get("summary", ""))

    def test_maybe_log_self_reflection_every_five_turns(self):
        records = [
            {
                "intent": "weather_lookup",
                "planner_decision": "ask_clarify",
                "active_subject": "developer_identity:developer" if _ == 4 else "",
                "continuation_used": _ == 4,
                "route_trace": [
                    {"stage": "action_planner", "outcome": "ask_clarify"},
                    {"stage": "llm_postprocess", "outcome": "self_corrected", "detail": "autonomy_guard"},
                ],
                "tool_result": "",
            }
            for _ in range(5)
        ]
        payload = nova_core.maybe_log_self_reflection(records=records, total_records=5, every=5)
        self.assertEqual(payload.get("turn_count"), 5)
        self.assertEqual(payload.get("top_repeated_failure_class"), "none")
        self.assertEqual(payload.get("top_repeated_correction_class"), "autonomy_guard")
        self.assertEqual(payload.get("failure_top", {}).get("class"), "none")
        self.assertEqual(payload.get("failure_top", {}).get("count"), 0)
        self.assertEqual(payload.get("correction_top", {}).get("class"), "autonomy_guard")
        self.assertEqual(payload.get("correction_top", {}).get("count"), 5)
        self.assertTrue(bool(payload.get("routing_stable", True)))
        self.assertTrue(bool(payload.get("unsupported_claims_blocked", False)))
        self.assertEqual(int(payload.get("claims_blocked", 0)), 5)
        self.assertEqual(payload.get("active_subject"), "developer_identity:developer")
        self.assertTrue(bool(payload.get("continuation_used", False)))
        self.assertEqual(payload.get("sample_intents_last5"), ["weather_lookup"] * 5)
        self.assertTrue(nova_core.SELF_REFLECTION_LOG.exists())

    def test_maybe_log_self_reflection_counts_retrieval_continuations(self):
        records = [
            {
                "intent": "web_research",
                "active_subject": "retrieval:web_research",
                "continuation_used": idx < 2,
                "route_trace": [{"stage": "conversation_followup", "outcome": "used"}] if idx < 2 else [],
                "tool_result": "",
            }
            for idx in range(5)
        ]
        payload = nova_core.maybe_log_self_reflection(records=records, total_records=5, every=5)
        self.assertEqual(int(payload.get("continuations_last_window", 0)), 2)
        self.assertEqual(int(payload.get("retrieval_continuations", 0)), 2)

    def test_maybe_log_self_reflection_counts_routing_overrides(self):
        records = [
            {
                "intent": "chat",
                "route_trace": [{"stage": "routing_override", "outcome": "enabled"}] if idx < 3 else [],
                "tool_result": "",
            }
            for idx in range(5)
        ]
        payload = nova_core.maybe_log_self_reflection(records=records, total_records=5, every=5)
        self.assertEqual(int(payload.get("routing_overrides", 0)), 3)
        self.assertFalse(bool(payload.get("routing_override_used_latest_turn", False)))

    def test_maybe_log_self_reflection_marks_latest_turn_routing_override(self):
        records = [
            {
                "intent": "chat",
                "route_trace": [{"stage": "routing_override", "outcome": "enabled"}] if idx == 4 else [],
                "tool_result": "",
            }
            for idx in range(5)
        ]
        payload = nova_core.maybe_log_self_reflection(records=records, total_records=5, every=5)
        self.assertEqual(int(payload.get("routing_overrides", 0)), 1)
        self.assertTrue(bool(payload.get("routing_override_used_latest_turn", False)))

    def test_maybe_log_self_reflection_includes_probe_summary(self):
        records = [
            {
                "intent": "chat",
                "route_trace": [],
                "tool_result": "",
                "final_answer": "hello",
            }
            for _ in range(5)
        ]
        payload = nova_core.maybe_log_self_reflection(
            records=records,
            total_records=5,
            every=5,
            extra_payload={
                "probe_summary": "1 issue detected",
                "probe_results": ["RED: rule_coverage - Turn reached llm_fallback"],
            },
        )
        self.assertEqual(payload.get("probe_summary"), "1 issue detected")
        self.assertEqual(payload.get("probe_results"), ["RED: rule_coverage - Turn reached llm_fallback"])

    def test_supervisor_entrypoint_parity_flags_subject_drift(self):
        supervisor = Supervisor()
        first = supervisor.process_turn(
            entry_point="cli",
            session_id="s1",
            session_summary={"active_subject": "retrieval:web", "continuation_used": True, "overrides_active": []},
            current_decision={
                "user_input": "tell me about the first one",
                "active_subject": "retrieval:web",
                "continuation_used": True,
                "planner_decision": "conversation_followup",
                "final_answer": "Here is the first result.",
                "pending_action": None,
            },
        )
        second = supervisor.process_turn(
            entry_point="http",
            session_id="s2",
            session_summary={"active_subject": "developer_identity:developer", "continuation_used": False, "overrides_active": []},
            current_decision={
                "user_input": "tell me about the first one",
                "active_subject": "developer_identity:developer",
                "continuation_used": False,
                "planner_decision": "deterministic",
                "final_answer": "I know Gustavo created me.",
                "pending_action": None,
            },
        )
        self.assertEqual(first.get("probe_summary"), "All green")
        self.assertIn("RED: entrypoint_parity", "\n".join(second.get("probe_results", [])))

    def test_supervisor_pending_action_leak_is_red(self):
        supervisor = Supervisor()
        payload = supervisor.process_turn(
            entry_point="http",
            session_id="s1",
            session_summary={"active_subject": "weather", "continuation_used": False, "overrides_active": []},
            current_decision={
                "user_input": "yes use that location",
                "active_subject": "weather",
                "continuation_used": False,
                "planner_decision": "run_tool",
                "tool": "weather_current_location",
                "tool_result": "Brownsville [source: api.weather.gov]",
                "grounded": True,
                "final_answer": "Brownsville [source: api.weather.gov]",
                "pending_action": {"kind": "weather_lookup", "status": "awaiting_location"},
            },
        )
        self.assertIn("RED: pending_action_leak", "\n".join(payload.get("probe_results", [])))

    def test_supervisor_rule_coverage_is_yellow_for_open_ended_fallback(self):
        supervisor = Supervisor()
        payload = supervisor.process_turn(
            entry_point="http",
            session_id="s-open",
            session_summary={"active_subject": "", "continuation_used": False, "overrides_active": []},
            current_decision={
                "user_input": "tell me something interesting",
                "planner_decision": "llm_fallback",
                "final_answer": "Here is something interesting.",
                "pending_action": None,
            },
        )
        self.assertIn("YELLOW: rule_coverage", "\n".join(payload.get("probe_results", [])))

    def test_supervisor_rule_coverage_is_red_for_suspicious_fallback(self):
        supervisor = Supervisor()
        payload = supervisor.process_turn(
            entry_point="http",
            session_id="s-suspicious",
            session_summary={"active_subject": "", "continuation_used": False, "overrides_active": []},
            current_decision={
                "user_input": "what is the weather in brownsville",
                "planner_decision": "llm_fallback",
                "final_answer": "I think it might be sunny.",
                "pending_action": None,
            },
        )
        self.assertIn("RED: rule_coverage", "\n".join(payload.get("probe_results", [])))

    def test_supervisor_identity_location_route_flags_local_knowledge_misroute(self):
        supervisor = Supervisor()
        payload = supervisor.process_turn(
            entry_point="http",
            session_id="s-location-route",
            session_summary={"active_subject": "", "continuation_used": False, "overrides_active": []},
            current_decision={
                "user_input": "What is your current physical location nova?",
                "planner_decision": "grounded_lookup",
                "final_answer": "I found relevant details in local knowledge files: - Program allocations. [source: knowledge/peims/08_finance_reporting.txt]",
                "tool_result": "I found relevant details in local knowledge files: - Program allocations. [source: knowledge/peims/08_finance_reporting.txt]",
                "pending_action": None,
            },
        )
        self.assertIn("RED: identity_location_route", "\n".join(payload.get("probe_results", [])))

    def test_supervisor_reflective_retry_rule_rewrites_to_prior_question(self):
        supervisor = Supervisor()
        result = supervisor.evaluate_rules(
            "keep trying your almost there ..",
            turns=[
                ("user", "what are Gus's favorite colors?"),
                ("assistant", "I don't have Gus's color preferences yet."),
                ("user", "keep trying your almost there .."),
            ],
            phase="rewrite",
        )
        self.assertEqual(result.get("rule_name"), "reflective_retry")
        self.assertEqual(result.get("rewrite_text"), "what are Gus's favorite colors?")
        self.assertEqual(result.get("analysis_reason"), "reflective_retry_prior_question")

    def test_supervisor_reflective_retry_rule_handles_developer_location(self):
        supervisor = Supervisor()
        session = ConversationSession()
        session.set_conversation_state({"kind": "identity_profile", "subject": "developer"})

        result = supervisor.evaluate_rules(
            "if you think for a bit.. you now know gus' locaiton do you not?",
            manager=session,
            turns=[("user", "who is your creator?")],
            phase="handle",
        )
        self.assertEqual(result.get("rule_name"), "reflective_retry")
        self.assertTrue(result.get("handled"))
        self.assertEqual(result.get("action"), "developer_location")
        self.assertTrue(result.get("continuation"))

    def test_supervisor_self_location_rule_handles_direct_query(self):
        supervisor = Supervisor()
        result = supervisor.evaluate_rules(
            "What is your current physical location nova?",
            phase="handle",
        )
        self.assertEqual(result.get("rule_name"), "self_location")
        self.assertTrue(result.get("handled"))
        self.assertEqual(result.get("action"), "self_location")
        self.assertEqual(result.get("next_state"), {"kind": "location_recall"})

    def test_supervisor_name_origin_store_rule_normalizes_short_phrase(self):
        supervisor = Supervisor()
        result = supervisor.evaluate_rules(
            "gus named you",
            phase="handle",
        )
        self.assertEqual(result.get("rule_name"), "name_origin_store")
        self.assertTrue(result.get("handled"))
        self.assertEqual(result.get("store_text"), "Gus named me Nova.")

    def test_supervisor_profile_certainty_rule_handles_identity_profile_followup(self):
        supervisor = Supervisor()
        session = ConversationSession()
        session.set_conversation_state({"kind": "identity_profile", "subject": "developer"})

        result = supervisor.evaluate_rules(
            "are you sure that is all the information you about him?",
            manager=session,
            phase="handle",
        )
        self.assertEqual(result.get("rule_name"), "profile_certainty")
        self.assertTrue(result.get("handled"))
        self.assertEqual(result.get("action"), "identity_profile_followup")
        self.assertEqual(result.get("subject"), "developer")

    def test_supervisor_developer_profile_state_rule_seeds_subject_for_who_is_gus(self):
        supervisor = Supervisor()
        result = supervisor.evaluate_rules(
            "who is gus ?",
            phase="state",
        )
        self.assertEqual(result.get("rule_name"), "developer_profile_state")
        self.assertEqual(result.get("state_update"), {"kind": "identity_profile", "subject": "developer"})

    def test_supervisor_apply_correction_rule_returns_intent(self):
        supervisor = Supervisor()
        result = supervisor.evaluate_rules("no, that's wrong", phase="intent")
        self.assertTrue(result.get("handled"))
        self.assertEqual(result.get("intent"), "apply_correction")

    def test_supervisor_store_fact_rule_returns_intent_and_fact(self):
        supervisor = Supervisor()
        result = supervisor.evaluate_rules("remember this Brownsville is my location", phase="intent")
        self.assertTrue(result.get("handled"))
        self.assertEqual(result.get("intent"), "store_fact")
        self.assertEqual(result.get("fact_text"), "Brownsville is my location")

    def test_supervisor_session_summary_rule_returns_intent(self):
        supervisor = Supervisor()
        result = supervisor.evaluate_rules("what happened", phase="intent")
        self.assertTrue(result.get("handled"))
        self.assertEqual(result.get("intent"), "session_summary")

    def test_supervisor_repeated_issue_emits_hardening_suggestion(self):
        supervisor = Supervisor()
        recent_reflections = [
            {"probe_results": ["RED: pending_action_leak - Pending action still set after successful run_tool"]},
            {"probe_results": ["RED: pending_action_leak - Pending action still set after successful run_tool"]},
        ]
        payload = supervisor.process_turn(
            entry_point="http",
            session_id="s-repeat",
            session_summary={"active_subject": "weather", "continuation_used": False, "overrides_active": []},
            current_decision={
                "user_input": "yes use that location",
                "active_subject": "weather",
                "planner_decision": "run_tool",
                "tool_result": "Brownsville [source: api.weather.gov]",
                "grounded": True,
                "pending_action": {"kind": "weather_lookup", "status": "awaiting_location"},
            },
            recent_reflections=recent_reflections,
        )
        self.assertTrue(any("Repeated pending_action_leak (3x)" in item for item in payload.get("suggestions", [])))

    def test_maybe_log_self_reflection_writes_health_snapshot_every_ten_turns(self):
        records = [
            {
                "intent": "chat",
                "route_trace": [],
                "tool_result": "",
                "final_answer": f"hello {idx}",
            }
            for idx in range(10)
        ]
        payload = nova_core.maybe_log_self_reflection(
            records=records,
            total_records=10,
            every=1,
            extra_payload={"session_id": "s-health", "probe_summary": "All green", "probe_results": []},
        )
        self.assertEqual(payload.get("session_id"), "s-health")
        self.assertTrue(nova_core.HEALTH_LOG.exists())
        rows = [json.loads(line) for line in nova_core.HEALTH_LOG.read_text(encoding="utf-8").splitlines() if line.strip()]
        self.assertEqual(rows[-1].get("session_id"), "s-health")
        self.assertFalse(bool(rows[-1].get("session_end")))

    def test_build_turn_reflection_stores_last_reflection_on_session(self):
        session = ConversationSession()
        session.set_conversation_state({"kind": "identity_profile", "subject": "developer"})
        reflection = nova_core.build_turn_reflection(
            session,
            entry_point="http",
            session_id="s-build",
            current_decision={
                "user_input": "who is your developer?",
                "planner_decision": "deterministic",
                "final_answer": "My developer is Gustavo Uribe.",
                "active_subject": session.active_subject(),
                "continuation_used": False,
                "pending_action": None,
            },
        )
        self.assertEqual(session.last_reflection, reflection)
        self.assertEqual(reflection.get("probe_summary"), "All green")

    def test_self_correct_reply_for_capability_query(self):
        corrected, changed, reason = nova_core._self_correct_reply(
            "what are your abilities?",
            "I can autonomously enhance myself and do anything you ask.",
        )
        self.assertTrue(changed)
        self.assertEqual(reason, "capability_alignment")
        self.assertEqual(corrected.strip(), nova_core.describe_capabilities().strip())

    def test_truth_hierarchy_identity_query(self):
        facts = {
            "assistant_name": "Nova",
            "developer_name": "Gustavo Uribe",
            "developer_nickname": "Gus",
        }
        nova_core.get_learned_fact = lambda k, default="": facts.get(k, default)
        handled, answer, source, grounded = nova_core.truth_hierarchy_answer("what is your creator's full name?")
        self.assertTrue(handled)
        self.assertEqual(source, "learned_facts")
        self.assertTrue(grounded)
        self.assertIn("gustavo uribe", answer.lower())

    def test_truth_hierarchy_identity_miss_does_not_terminate_reasoning(self):
        orig_get_learned_fact = nova_core.get_learned_fact
        orig_get_name_origin_story = nova_core.get_name_origin_story
        try:
            nova_core.get_learned_fact = lambda k, default="": {
                "assistant_name": "Nova",
                "developer_name": "Gustavo Uribe",
                "developer_nickname": "Gus",
            }.get(k, default)
            nova_core.get_name_origin_story = lambda: ""

            handled, answer, source, grounded = nova_core.truth_hierarchy_answer("did you learn about your name?")
            self.assertFalse(handled)
            self.assertEqual(answer, "")
            self.assertEqual(source, "")
            self.assertFalse(grounded)
        finally:
            nova_core.get_learned_fact = orig_get_learned_fact
            nova_core.get_name_origin_story = orig_get_name_origin_story

    def test_session_fact_sheet_collects_known_identity_and_preferences(self):
        orig_get_learned_fact = nova_core.get_learned_fact
        orig_get_name_origin_story = nova_core.get_name_origin_story
        orig_extract_developer_color_preferences_from_memory = nova_core._extract_developer_color_preferences_from_memory
        orig_developer_is_bilingual_from_memory = nova_core._developer_is_bilingual_from_memory
        try:
            nova_core.get_learned_fact = lambda k, default="": {
                "assistant_name": "Nova",
                "developer_name": "Gustavo Uribe",
                "developer_nickname": "Gus",
            }.get(k, default)
            nova_core.get_name_origin_story = lambda: "Nova was named as a symbol of new light."
            nova_core._extract_developer_color_preferences_from_memory = lambda: ["silver", "blue", "red"]
            nova_core._developer_is_bilingual_from_memory = lambda: True
            nova_core.set_active_user("Gustavo Uribe")

            turns = [
                ("user", "my favorite animal is dogs"),
                ("assistant", "Noted."),
            ]
            out = nova_core._build_session_fact_sheet(turns)
            low = (out or "").lower()
            self.assertIn("assistant name: nova", low)
            self.assertIn("developer full name: gustavo uribe", low)
            self.assertIn("developer nickname: gus", low)
            self.assertIn("active speaker identity: gustavo uribe", low)
            self.assertIn("developer color preferences: silver, blue, red", low)
            self.assertIn("developer languages: english, spanish", low)
            self.assertIn("user-stated animal preferences: dogs", low)
        finally:
            nova_core.get_learned_fact = orig_get_learned_fact
            nova_core.get_name_origin_story = orig_get_name_origin_story
            nova_core._extract_developer_color_preferences_from_memory = orig_extract_developer_color_preferences_from_memory
            nova_core._developer_is_bilingual_from_memory = orig_developer_is_bilingual_from_memory

    def test_claim_gate_removes_unsupported_risky_sentence(self):
        reply = "Your creator is Gustavo Uribe. I can smell coffee in the room with Gus."
        evidence = "SESSION FACT SHEET:\nDeveloper full name: Gustavo Uribe\nDeveloper nickname: Gus"

        gated, changed, reason = nova_core._apply_claim_gate(reply, evidence_text=evidence)
        self.assertTrue(changed)
        self.assertEqual(reason, "unsupported_claim_removed")
        self.assertIn("gustavo uribe", gated.lower())
        self.assertNotIn("smell coffee", gated.lower())

    def test_claim_gate_blocks_when_all_risky_claims_are_unsupported(self):
        reply = "I can smell coffee in the room with Gus."

        gated, changed, reason = nova_core._apply_claim_gate(reply, evidence_text="")
        self.assertTrue(changed)
        self.assertEqual(reason, "unsupported_claim_blocked")
        self.assertIn("not sure", gated.lower())

    def test_claim_gate_keeps_supported_identity_claim(self):
        reply = "Your creator is Gustavo Uribe."
        evidence = "SESSION FACT SHEET:\nDeveloper full name: Gustavo Uribe"

        gated, changed, reason = nova_core._apply_claim_gate(reply, evidence_text=evidence)
        self.assertFalse(changed)
        self.assertEqual(reason, "")
        self.assertEqual(gated, reply)

    def test_truth_hierarchy_policy_query(self):
        orig_policy_web = nova_core.policy_web
        try:
            nova_core.policy_web = lambda: {"enabled": True, "allow_domains": ["tea.texas.gov", "texasstudentdatasystem.org"]}
            handled, answer, source, grounded = nova_core.truth_hierarchy_answer("what domain access do you have?")
            self.assertTrue(handled)
            self.assertEqual(source, "policy_json")
            self.assertTrue(grounded)
            self.assertIn("tea.texas.gov", answer)
        finally:
            nova_core.policy_web = orig_policy_web

    def test_truth_hierarchy_action_history_query(self):
        rec = {
            "intent": "weather_lookup",
            "planner_decision": "run_tool",
            "tool": "weather",
            "grounded": True,
            "final_answer": "Brownsville: 83 F [source: api.weather.gov]",
        }
        p = nova_core.ACTION_LEDGER_DIR / "9999_test.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(rec, ensure_ascii=True), encoding="utf-8")

        handled, answer, source, grounded = nova_core.truth_hierarchy_answer("what did you just do?")
        self.assertTrue(handled)
        self.assertEqual(source, "action_ledger")
        self.assertTrue(grounded)
        self.assertIn("intent=weather_lookup", answer)

    def test_declarative_detector_avoids_request_like_i_am(self):
        self.assertFalse(nova_core._is_declarative_info("I am curious to know if you know what your capable of doing ?"))
        self.assertTrue(nova_core._is_declarative_info("my location is brownsville texas"))

    def test_location_fact_extraction_and_normalization(self):
        out = nova_core._extract_location_fact("Your physical location is United states Brownsville TX 78521  .")
        self.assertEqual(out, "United states Brownsville TX 78521")

        normalized = nova_core._normalize_location_preview("Your physical location is United states Brownsville TX 78521.")
        self.assertEqual(normalized, "United states Brownsville TX 78521")

    def test_store_location_fact_reply_skips_pending_weather_followup(self):
        orig_set_location_text = nova_core.set_location_text
        try:
            stored = []
            nova_core.set_location_text = lambda value, input_source="typed": stored.append((value, input_source)) or value

            out = nova_core._store_location_fact_reply(
                "my location is brownsville texas",
                pending_action={"kind": "weather_lookup", "status": "awaiting_location"},
            )

            self.assertEqual(out, "")
            self.assertEqual(stored, [])
        finally:
            nova_core.set_location_text = orig_set_location_text

    def test_store_location_fact_reply_persists_and_acknowledges(self):
        orig_set_location_text = nova_core.set_location_text
        try:
            stored = []
            nova_core.set_location_text = lambda value, input_source="typed": stored.append((value, input_source)) or value

            out = nova_core._store_location_fact_reply("my location is brownsville texas")

            self.assertEqual(out, "Noted.")
            self.assertEqual(stored, [("brownsville texas", "typed")])
        finally:
            nova_core.set_location_text = orig_set_location_text

    def test_store_declarative_fact_reply_ignores_request_like_text(self):
        out = nova_core._store_declarative_fact_reply("I am curious to know if you know what your capable of doing ?")
        self.assertEqual(out, "")

    def test_store_declarative_fact_reply_persists_and_acknowledges(self):
        orig_mem_should_store = nova_core.mem_should_store
        orig_mem_add = nova_core.mem_add
        try:
            stored = []
            nova_core.mem_should_store = lambda text: True
            nova_core.mem_add = lambda kind, input_source, text: stored.append((kind, input_source, text))

            out = nova_core._store_declarative_fact_reply("I work at Nova Labs")

            self.assertEqual(out, "Noted.")
            self.assertEqual(stored, [("fact", "typed", "I work at Nova Labs")])
        finally:
            nova_core.mem_should_store = orig_mem_should_store
            nova_core.mem_add = orig_mem_add

    def test_developer_location_turn_returns_reply_and_state(self):
        reply, state = nova_core._developer_location_turn("where is gus right now?")
        self.assertIn("uncertain about gus's current location", reply.lower())
        self.assertEqual({"kind": "identity_profile", "subject": "developer"}, state)

    def test_core_read_text_safely_handles_utf16_without_null_padded_output(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "utf16_sample.txt"
            path.write_text("Public Education Information Management System (PEIMS).", encoding="utf-16")

            out = nova_core._read_text_safely(path)

            self.assertIn("Public Education Information Management System", out)
            self.assertNotIn("\x00", out)

    def test_action_ledger_record_write(self):
        rec = nova_core.start_action_ledger_record(
            "give me weather for your location",
            channel="cli",
            session_id="",
            input_source="typed",
        )
        path = nova_core.finalize_action_ledger_record(
            rec,
            final_answer="Brownsville: 83 F [source: api.weather.gov]",
            planner_decision="run_tool",
            tool="weather",
            tool_args={"location": "current_physical_location"},
            tool_result="Brownsville: 83 F [source: api.weather.gov]",
            grounded=True,
            intent="weather_lookup",
            active_subject="location_recall",
            continuation_used=True,
        )
        self.assertIsNotNone(path)
        self.assertTrue(Path(path).exists())

        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        self.assertEqual(payload.get("intent"), "weather_lookup")
        self.assertEqual(payload.get("planner_decision"), "run_tool")
        self.assertEqual(payload.get("tool"), "weather")
        self.assertTrue(payload.get("grounded"))
        self.assertIn("route_trace", payload)
        self.assertTrue(isinstance(payload.get("route_trace"), list))
        self.assertTrue(payload.get("route_summary"))
        self.assertEqual(payload.get("route_trace", [])[0].get("stage"), "input")
        self.assertEqual(payload.get("active_subject"), "location_recall")
        self.assertTrue(payload.get("continuation_used"))

    def test_cli_action_ledger_records_planner_owned_command_route(self):
        with mock.patch.object(nova_core, "VOICE_OK", False), \
             mock.patch.object(nova_core, "speak_chunked", lambda *_args, **_kwargs: None), \
             mock.patch("builtins.input", side_effect=["hello there", "chat context", "q"]):
            nova_core.run_loop(self._SilentTTS())

        payload = self._latest_action_payload()
        self.assertEqual(payload.get("user_input"), "chat context")
        self.assertEqual(payload.get("planner_decision"), "command")
        self.assertIn("action_planner:route_command", payload.get("route_summary", ""))
        self.assertIn("command:matched", payload.get("route_summary", ""))

    def test_cli_action_ledger_records_planner_owned_keyword_route(self):
        with mock.patch.object(nova_core, "VOICE_OK", False), \
             mock.patch.object(nova_core, "speak_chunked", lambda *_args, **_kwargs: None), \
             mock.patch.object(nova_core, "handle_keywords", lambda _text: ("tool", "web_research", "continued web research")), \
             mock.patch("builtins.input", side_effect=["web continue", "q"]):
            nova_core.run_loop(self._SilentTTS())

        payload = self._latest_action_payload()
        self.assertEqual(payload.get("user_input"), "web continue")
        self.assertEqual(payload.get("planner_decision"), "run_tool")
        self.assertEqual(payload.get("tool"), "web_research")
        self.assertIn("action_planner:route_keyword", payload.get("route_summary", ""))
        self.assertIn("keyword_tool:matched", payload.get("route_summary", ""))

    def test_cli_web_override_makes_peims_query_use_web_research(self):
        with mock.patch.object(nova_core, "VOICE_OK", False), \
             mock.patch.object(nova_core, "speak_chunked", lambda *_args, **_kwargs: None), \
             mock.patch.object(nova_core, "execute_planned_action", lambda tool, args=None: f"Web research results for {args[0] if args else tool}"), \
             mock.patch("builtins.input", side_effect=["just use the web for this", "give me anything online about PEIMS", "q"]):
            nova_core.run_loop(self._SilentTTS())

        payload = self._latest_action_payload()
        self.assertEqual(payload.get("user_input"), "give me anything online about PEIMS")
        self.assertEqual(payload.get("planner_decision"), "run_tool")
        self.assertEqual(payload.get("tool"), "web_research")
        self.assertIn("tool_execution:ok", payload.get("route_summary", ""))

    def test_cli_broad_peims_query_prefers_local_grounded_overview(self):
        with mock.patch.object(nova_core, "VOICE_OK", False), \
             mock.patch.object(nova_core, "speak_chunked", lambda *_args, **_kwargs: None), \
             mock.patch("builtins.input", side_effect=["what do you know about PEIMS?", "q"]), \
             mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
            nova_core.run_loop(self._SilentTTS())

        output = stdout.getvalue().lower()
        self.assertIn("peims overview details in local knowledge files", output)

        payload = self._latest_action_payload()
        self.assertEqual(payload.get("user_input"), "what do you know about PEIMS?")
        self.assertEqual(payload.get("planner_decision"), "grounded_lookup")
        self.assertEqual(payload.get("tool"), "local_knowledge")
        self.assertTrue(bool(payload.get("grounded")))

    def test_cli_supervisor_store_fact_intent_stores_and_replies(self):
        orig_mem_enabled = nova_core.mem_enabled
        orig_mem_add = nova_core.mem_add
        try:
            writes = []
            nova_core.mem_enabled = lambda: True
            nova_core.mem_add = lambda kind, source, text: writes.append((kind, source, text))

            with mock.patch.object(nova_core, "VOICE_OK", False), \
                 mock.patch.object(nova_core, "speak_chunked", lambda *_args, **_kwargs: None), \
                 mock.patch("builtins.input", side_effect=["remember this Brownsville is my location", "q"]), \
                 mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
                nova_core.run_loop(self._SilentTTS())

            self.assertIn("Stored.", stdout.getvalue())
            self.assertIn("[INTENT] store_fact :: store_fact :: Brownsville is my location", stdout.getvalue())
            self.assertIn(("user_fact", "typed", "Brownsville is my location"), writes)
        finally:
            nova_core.mem_enabled = orig_mem_enabled
            nova_core.mem_add = orig_mem_add

    def test_cli_supervisor_session_summary_intent_uses_recap_reply(self):
        with mock.patch.object(nova_core, "VOICE_OK", False), \
             mock.patch.object(nova_core, "speak_chunked", lambda *_args, **_kwargs: None), \
             mock.patch("builtins.input", side_effect=["hello there", "what happened", "q"]), \
             mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
            nova_core.run_loop(self._SilentTTS())

        output = stdout.getvalue()
        self.assertIn("Recap of this session so far:", output)
        self.assertIn("1. hello there", output)

    def test_cli_supervisor_apply_correction_intent_acknowledges(self):
        orig_mem_enabled = nova_core.mem_enabled
        orig_mem_add = nova_core.mem_add
        try:
            writes = []
            nova_core.mem_enabled = lambda: True
            nova_core.mem_add = lambda kind, source, text: writes.append((kind, source, text))

            with mock.patch.object(nova_core, "VOICE_OK", False), \
                 mock.patch.object(nova_core, "speak_chunked", lambda *_args, **_kwargs: None), \
                 mock.patch("builtins.input", side_effect=["hello there", "no, that's wrong", "q"]), \
                 mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
                nova_core.run_loop(self._SilentTTS())

            self.assertIn("Got it - correcting that.", stdout.getvalue())
            self.assertIn("[INTENT] apply_correction :: apply_correction :: no, that's wrong", stdout.getvalue())
            correction_write = next((entry for entry in writes if entry[0] == "user_correction"), None)
            self.assertIsNotNone(correction_write)
            self.assertEqual((correction_write[0], correction_write[1]), ("user_correction", "typed"))
            payload = json.loads(correction_write[2])
            self.assertEqual(payload.get("text"), "no, that's wrong")
            self.assertEqual(payload.get("parsed_correction"), "")
        finally:
            nova_core.mem_enabled = orig_mem_enabled
            nova_core.mem_add = orig_mem_add

    def test_cli_supervisor_apply_correction_intent_teaches_explicit_replacement(self):
        orig_mem_enabled = nova_core.mem_enabled
        orig_mem_add = nova_core.mem_add
        orig_teach_store_example = nova_core._teach_store_example
        try:
            writes = []
            teaches = []
            nova_core.mem_enabled = lambda: True
            nova_core.mem_add = lambda kind, source, text: writes.append((kind, source, text))
            nova_core._teach_store_example = lambda original, correction, user=None: teaches.append((original, correction, user)) or "OK"

            with mock.patch.object(nova_core, "VOICE_OK", False), \
                 mock.patch.object(nova_core, "speak_chunked", lambda *_args, **_kwargs: None), \
                 mock.patch("builtins.input", side_effect=["hello there", "no, say 'hi gus' instead", "q"]), \
                 mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
                nova_core.run_loop(self._SilentTTS())

            self.assertIn("[INTENT] apply_correction :: apply_correction :: no, say 'hi gus' instead", stdout.getvalue())
            correction_write = next((entry for entry in writes if entry[0] == "user_correction"), None)
            self.assertIsNotNone(correction_write)
            payload = json.loads(correction_write[2])
            self.assertEqual(payload.get("parsed_correction"), "hi gus")
            self.assertEqual(len(teaches), 1)
            self.assertEqual(teaches[0][1], "hi gus")
        finally:
            nova_core.mem_enabled = orig_mem_enabled
            nova_core.mem_add = orig_mem_add
            nova_core._teach_store_example = orig_teach_store_example

    def test_cli_self_location_query_still_uses_shared_legacy_route(self):
        with mock.patch.object(nova_core, "VOICE_OK", False), \
             mock.patch.object(nova_core, "speak_chunked", lambda *_args, **_kwargs: None), \
             mock.patch.object(nova_core, "get_saved_location_text", lambda: ""), \
             mock.patch("builtins.input", side_effect=["What is your current physical location nova?", "q"]), \
             mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
            nova_core.run_loop(self._SilentTTS())

        output = stdout.getvalue()
        self.assertIn("I don't have a stored location yet.", output)
        self.assertNotIn("[INTENT]", output)

    def test_cli_creator_query_after_retrieval_resets_followup_to_creator_thread(self):
        with mock.patch.object(nova_core, "VOICE_OK", False), \
             mock.patch.object(nova_core, "speak_chunked", lambda *_args, **_kwargs: None), \
             mock.patch.object(nova_core, "execute_planned_action", lambda tool, args=None: "1) https://tea.texas.gov/a\n2) https://tea.texas.gov/b" if tool == "web_research" else ""), \
             mock.patch.object(nova_core, "tool_web_gather", lambda url: f"Gathered: {url}"), \
             mock.patch.object(nova_core, "get_name_origin_story", lambda: "Nova was given its name by Gus."), \
             mock.patch("builtins.input", side_effect=["research PEIMS online", "tell me about the first one", "who is your creator?", "what else?", "q"]), \
             mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
            nova_core.run_loop(self._SilentTTS())

        output = stdout.getvalue().lower()
        self.assertIn("my creator is gustavo uribe", output)
        self.assertIn("verified facts", output)
        self.assertIn("gustavo", output)

        payload = self._latest_action_payload()
        self.assertEqual(payload.get("user_input"), "what else?")
        self.assertEqual(payload.get("active_subject"), "identity_profile:developer")
        self.assertTrue(bool(payload.get("continuation_used")))

    def test_cli_developer_profile_and_location_use_shared_deterministic_replies(self):
        with mock.patch.object(nova_core, "VOICE_OK", False), \
             mock.patch.object(nova_core, "speak_chunked", lambda *_args, **_kwargs: None), \
             mock.patch("builtins.input", side_effect=["what do you know about Gus?", "do you know his current location?", "q"]), \
             mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
            nova_core.run_loop(self._SilentTTS())

        output = stdout.getvalue().lower()
        self.assertIn("verified facts i have about my developer", output)
        self.assertIn("his full name is gustavo uribe", output)
        self.assertIn("uncertain about gus's current location", output)

    def test_cli_action_ledger_records_shared_location_weather_route(self):
        class _FakeResponse:
            def __init__(self, payload):
                self._payload = payload

            def raise_for_status(self):
                return None

            def json(self):
                return self._payload

        def fake_get(url, headers=None, timeout=0):
            if "api.weather.gov/points/" in url:
                return _FakeResponse({"properties": {"forecast": "https://api.weather.gov/gridpoints/BRO/64,48/forecast"}})
            return _FakeResponse(
                {
                    "properties": {
                        "periods": [
                            {
                                "name": "Today",
                                "temperature": 66,
                                "temperatureUnit": "F",
                                "shortForecast": "Sunny",
                                "windSpeed": "18 to 24 mph",
                                "windDirection": "N",
                            }
                        ]
                    }
                }
            )

        orig_policy_path = nova_core.POLICY_PATH
        orig_requests_get = nova_core.requests.get
        policy_path = Path(self._tmp_dir.name) / "policy_weather_test.json"
        policy_path.write_text(
            json.dumps(
                {
                    "allowed_root": "C:/Nova",
                    "tools_enabled": {"web": True},
                    "web": {"enabled": True, "allow_domains": ["api.weather.gov"], "max_bytes": 1000},
                }
            ),
            encoding="utf-8",
        )

        try:
            nova_core.POLICY_PATH = policy_path
            nova_core.requests.get = fake_get
            nova_core.set_location_text("Brownsville TX")
            with mock.patch.object(nova_core, "VOICE_OK", False), \
                 mock.patch.object(nova_core, "speak_chunked", lambda *_args, **_kwargs: None), \
                 mock.patch("builtins.input", side_effect=["yes get the weather for our location", "q"]):
                nova_core.run_loop(self._SilentTTS())
        finally:
            nova_core.POLICY_PATH = orig_policy_path
            nova_core.requests.get = orig_requests_get

        payload = self._latest_action_payload()
        self.assertEqual(payload.get("user_input"), "yes get the weather for our location")
        self.assertEqual(payload.get("planner_decision"), "run_tool")
        self.assertEqual(payload.get("tool"), "weather_current_location")
        self.assertIn("action_planner:run_tool", payload.get("route_summary", ""))
        self.assertIn("tool_execution:ok", payload.get("route_summary", ""))
        self.assertIn("api.weather.gov", payload.get("tool_result", ""))

    def test_cli_weather_location_followup_uses_shared_location_context(self):
        class _FakeResponse:
            def __init__(self, payload):
                self._payload = payload

            def raise_for_status(self):
                return None

            def json(self):
                return self._payload

        def fake_get(url, headers=None, timeout=0):
            if "api.weather.gov/points/" in url:
                return _FakeResponse({"properties": {"forecast": "https://api.weather.gov/gridpoints/BRO/64,48/forecast"}})
            return _FakeResponse(
                {
                    "properties": {
                        "periods": [
                            {
                                "name": "Today",
                                "temperature": 66,
                                "temperatureUnit": "F",
                                "shortForecast": "Sunny",
                                "windSpeed": "18 to 24 mph",
                                "windDirection": "N",
                            }
                        ]
                    }
                }
            )

        orig_policy_path = nova_core.POLICY_PATH
        orig_requests_get = nova_core.requests.get
        policy_path = Path(self._tmp_dir.name) / "policy_weather_followup_test.json"
        policy_path.write_text(
            json.dumps(
                {
                    "allowed_root": "C:/Nova",
                    "tools_enabled": {"web": True},
                    "web": {"enabled": True, "allow_domains": ["api.weather.gov"], "max_bytes": 1000},
                }
            ),
            encoding="utf-8",
        )

        try:
            nova_core.POLICY_PATH = policy_path
            nova_core.requests.get = fake_get
            nova_core.set_location_text("Brownsville TX")
            with mock.patch.object(nova_core, "VOICE_OK", False), \
                 mock.patch.object(nova_core, "speak_chunked", lambda *_args, **_kwargs: None), \
                 mock.patch("builtins.input", side_effect=["check the weather if you can please..", "our location nova ..", "q"]):
                nova_core.run_loop(self._SilentTTS())
        finally:
            nova_core.POLICY_PATH = orig_policy_path
            nova_core.requests.get = orig_requests_get

        payload = self._latest_action_payload()
        self.assertEqual(payload.get("user_input"), "our location nova ..")
        self.assertEqual(payload.get("planner_decision"), "run_tool")
        self.assertEqual(payload.get("tool"), "weather_current_location")
        self.assertIn("action_planner:run_tool", payload.get("route_summary", ""))
        self.assertIn("tool_execution:ok", payload.get("route_summary", ""))

    def test_cli_pending_weather_action_uses_affirmative_followup(self):
        class _FakeResponse:
            def __init__(self, payload):
                self._payload = payload

            def raise_for_status(self):
                return None

            def json(self):
                return self._payload

        def fake_get(url, headers=None, timeout=0):
            if "api.weather.gov/points/" in url:
                return _FakeResponse({"properties": {"forecast": "https://api.weather.gov/gridpoints/BRO/64,48/forecast"}})
            return _FakeResponse(
                {
                    "properties": {
                        "periods": [
                            {
                                "name": "Today",
                                "temperature": 66,
                                "temperatureUnit": "F",
                                "shortForecast": "Sunny",
                                "windSpeed": "18 to 24 mph",
                                "windDirection": "N",
                            }
                        ]
                    }
                }
            )

        orig_policy_path = nova_core.POLICY_PATH
        orig_requests_get = nova_core.requests.get
        policy_path = Path(self._tmp_dir.name) / "policy_weather_affirm_test.json"
        policy_path.write_text(
            json.dumps(
                {
                    "allowed_root": "C:/Nova",
                    "tools_enabled": {"web": True},
                    "web": {"enabled": True, "allow_domains": ["api.weather.gov"], "max_bytes": 1000},
                }
            ),
            encoding="utf-8",
        )

        try:
            nova_core.POLICY_PATH = policy_path
            nova_core.requests.get = fake_get
            nova_core.set_location_text("Brownsville TX")
            with mock.patch.object(nova_core, "VOICE_OK", False), \
                 mock.patch.object(nova_core, "speak_chunked", lambda *_args, **_kwargs: None), \
                 mock.patch("builtins.input", side_effect=["check the weather if you can please..", "yea please do that ..", "q"]):
                nova_core.run_loop(self._SilentTTS())
        finally:
            nova_core.POLICY_PATH = orig_policy_path
            nova_core.requests.get = orig_requests_get

        payload = self._latest_action_payload()
        self.assertEqual(payload.get("user_input"), "yea please do that ..")
        self.assertEqual(payload.get("planner_decision"), "run_tool")
        self.assertEqual(payload.get("tool"), "weather_current_location")
        self.assertIn("action_planner:run_tool", payload.get("route_summary", ""))
        self.assertIn("tool_execution:ok", payload.get("route_summary", ""))


if __name__ == "__main__":
    unittest.main()
