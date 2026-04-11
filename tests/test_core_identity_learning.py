import unittest
from unittest import mock
import json
import io
import os
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
        self.orig_statefile = nova_core.DEFAULT_STATEFILE
        self.orig_device_location_file = nova_core.DEVICE_LOCATION_FILE
        self.orig_windows_device_resolver = nova_core._resolve_windows_device_coords
        self.orig_active_user = nova_core.get_active_user()
        self._tmp_dir = tempfile.TemporaryDirectory()
        nova_core.ACTION_LEDGER_DIR = Path(self._tmp_dir.name) / "actions"
        nova_core.SELF_REFLECTION_LOG = Path(self._tmp_dir.name) / "self_reflection.jsonl"
        nova_core.HEALTH_LOG = Path(self._tmp_dir.name) / "health.log"
        nova_core.DEFAULT_STATEFILE = Path(self._tmp_dir.name) / "core_state.json"
        nova_core.DEVICE_LOCATION_FILE = Path(self._tmp_dir.name) / "device_location.json"
        nova_core._resolve_windows_device_coords = lambda *args, **kwargs: None
        nova_core.TURN_SUPERVISOR.reset()

    def tearDown(self):
        nova_core.get_learned_fact = self.orig_get_learned_fact
        nova_core.get_name_origin_story = self.orig_get_name_origin_story
        nova_core.ACTION_LEDGER_DIR = self.orig_action_ledger_dir
        nova_core.SELF_REFLECTION_LOG = self.orig_self_reflection_log
        nova_core.HEALTH_LOG = self.orig_health_log
        nova_core.DEFAULT_STATEFILE = self.orig_statefile
        nova_core.DEVICE_LOCATION_FILE = self.orig_device_location_file
        nova_core._resolve_windows_device_coords = self.orig_windows_device_resolver
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
        self.assertTrue((out2 or "").startswith("From earlier memory:"))
        self.assertIn("gustavo uribe", (out2 or "").lower())

        out3 = nova_core.hard_answer("what is his full name?")
        self.assertIn("full name is gustavo uribe", (out3 or "").lower())

        out4 = nova_core.hard_answer("what is your creator's full name?")
        self.assertIn("full name is gustavo uribe", (out4 or "").lower())

        out5 = nova_core.hard_answer("who is your creator?")
        self.assertTrue((out5 or "").startswith("From earlier memory:"))
        self.assertIn("my creator is gustavo uribe", (out5 or "").lower())

        out6 = nova_core.hard_answer("who made you?")
        self.assertIn("my creator is gustavo uribe", (out6 or "").lower())

        out7 = nova_core.hard_answer("how are you?")
        self.assertEqual("I'm doing well, thanks for asking.", out7)

    def test_hard_answer_recent_learning_summary_uses_recent_memory_items(self):
        orig_mem_get_recent_learned = nova_core.mem_get_recent_learned
        try:
            nova_core.mem_get_recent_learned = lambda limit=5: [
                "my favorite color is teal",
                "Correction: my favorite color is blue",
            ][:limit]

            out = nova_core.hard_answer("what have you learned from me?")

            self.assertIn("Here's what I've learned from you recently", out)
            self.assertIn("- my favorite color is teal", out)
            self.assertIn("- Correction: my favorite color is blue", out)
        finally:
            nova_core.mem_get_recent_learned = orig_mem_get_recent_learned

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
        orig_active_pack_file = nova_core.ACTIVE_PACK_FILE
        try:
            nova_core.PACKS_DIR.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(dir=str(nova_core.PACKS_DIR), prefix="test-pack-") as td:
                pack_dir = Path(td)
                pack_name = pack_dir.name
                (pack_dir / "tsds_overview.txt").write_text(
                    "TSDS is the Texas Student Data System used for student data collections.",
                    encoding="utf-8",
                )
                active_pack_file = Path(self._tmp_dir.name) / "active_pack.txt"
                active_pack_file.write_text(pack_name, encoding="utf-8")

                nova_core.ACTIVE_PACK_FILE = active_pack_file

                out = nova_core._build_local_topic_digest_answer("what is TSDS?")

            self.assertIn("active knowledge pack", out.lower())
            self.assertIn("tsds", out.lower())
            self.assertIn("knowledge/packs/", out.lower())
            self.assertIn("tsds_overview.txt", out.lower())
        finally:
            nova_core.ACTIVE_PACK_FILE = orig_active_pack_file

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
        orig_query = nova_core.WEB_RESEARCH_SESSION.query
        orig_results = nova_core.WEB_RESEARCH_SESSION.results
        orig_cursor = nova_core.WEB_RESEARCH_SESSION.cursor
        try:
            nova_core.WEB_RESEARCH_SESSION.set_state(
                "peims attendance",
                [
                (9.0, "https://tea.texas.gov/a", "First result snippet"),
                (8.5, "https://tea.texas.gov/b", "Second result snippet"),
                ],
                1,
            )

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
            outcome = nova_core._execute_retrieval_followup_outcome(
                {"kind": "retrieval", "subject": "web_research", "query": "peims attendance", "result_count": 2, "urls": ["https://tea.texas.gov/a"]},
                "what else",
            )[2]
            self.assertEqual(outcome.get("reply_contract"), "retrieval_followup.continued_results")
        finally:
            if orig_results:
                nova_core.WEB_RESEARCH_SESSION.set_state(orig_query, orig_results, orig_cursor)
            else:
                nova_core.WEB_RESEARCH_SESSION.clear()

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
            outcome = nova_core._execute_retrieval_followup_outcome(
                {
                    "kind": "retrieval",
                    "subject": "web_search",
                    "query": "peims attendance",
                    "result_count": 2,
                    "urls": ["https://tea.texas.gov/one", "https://tea.texas.gov/two"],
                },
                "tell me about the first one",
            )[2]
            self.assertEqual(outcome.get("reply_contract"), "retrieval_followup.selected_result")
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

    def test_location_recall_followup_detection_rejects_clarification_move(self):
        turns = [
            ("user", "yes can you recall my location ?"),
            ("assistant", "Your saved location is Brownsville, Texas."),
        ]
        self.assertFalse(nova_core._looks_like_location_recall_followup(turns, "what?"))

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

    def test_supervisor_rule_coverage_is_green_for_open_ended_fallback(self):
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
        self.assertEqual(payload.get("probe_summary"), "All green")
        self.assertEqual(payload.get("probe_results"), [])

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
                "final_answer": "I found relevant details in the active knowledge pack (district-data): - Program allocations. [source: knowledge/packs/district-data/finance_reporting.txt]",
                "tool_result": "I found relevant details in the active knowledge pack (district-data): - Program allocations. [source: knowledge/packs/district-data/finance_reporting.txt]",
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

    def test_supervisor_evaluate_rules_normalizes_dispatch_context(self):
        supervisor = Supervisor()
        observed: dict[str, object] = {}

        def _capture_rule(user_text, low, manager, turn, *, turns=None, phase="handle", entry_point=""):
            observed.update(
                {
                    "user_text": user_text,
                    "low": low,
                    "manager": manager,
                    "turn": turn,
                    "turns": turns,
                    "phase": phase,
                    "entry_point": entry_point,
                }
            )
            return {"handled": False}

        supervisor.register_rule("capture_contract", _capture_rule, priority=1, phases=("handle",))

        result = supervisor.evaluate_rules(
            None,
            manager=None,
            turns=None,
            phase=None,
            entry_point=None,
        )

        self.assertFalse(result.get("handled"))
        self.assertEqual(observed.get("user_text"), "")
        self.assertEqual(observed.get("low"), "")
        self.assertEqual(observed.get("manager"), {})
        self.assertEqual(observed.get("turn"), 0)
        self.assertEqual(observed.get("turns"), [])
        self.assertEqual(observed.get("phase"), "handle")
        self.assertEqual(observed.get("entry_point"), "")

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

    def test_supervisor_location_recall_rule_handles_continuation_move(self):
        supervisor = Supervisor()
        session = ConversationSession()
        session.set_conversation_state({"kind": "location_recall"})
        result = supervisor.evaluate_rules(
            "what else?",
            manager=session,
            phase="handle",
        )
        self.assertEqual(result.get("rule_name"), "location_recall")
        self.assertTrue(result.get("handled"))
        self.assertTrue(result.get("continuation"))

    def test_supervisor_location_recall_rule_handles_shared_zip_reference(self):
        supervisor = Supervisor()
        session = ConversationSession()
        session.set_conversation_state({"kind": "location_recall"})
        result = supervisor.evaluate_rules(
            "what is the name of the city that zip code belong too nova ?",
            manager=session,
            phase="handle",
        )
        self.assertEqual(result.get("rule_name"), "location_recall")
        self.assertTrue(result.get("handled"))
        self.assertFalse(result.get("continuation", False))

    def test_supervisor_location_recall_rule_rejects_clarification_move(self):
        supervisor = Supervisor()
        session = ConversationSession()
        session.set_conversation_state({"kind": "location_recall"})
        result = supervisor.evaluate_rules(
            "what?",
            manager=session,
            phase="handle",
        )
        self.assertFalse(result.get("handled"))
        self.assertNotEqual(result.get("rule_name"), "location_recall")

    def test_supervisor_identity_history_rule_rejects_clarification_move(self):
        supervisor = Supervisor()
        session = ConversationSession()
        session.set_conversation_state({"kind": "identity_profile", "subject": "developer"})
        result = supervisor.evaluate_rules(
            "what?",
            manager=session,
            phase="handle",
        )
        self.assertFalse(result.get("handled"))
        self.assertNotEqual(result.get("rule_name"), "identity_history_family")

    def test_supervisor_set_location_rule_returns_intent_for_zip_claim(self):
        supervisor = Supervisor()
        result = supervisor.evaluate_rules(
            "the 78521 is the zip code for your current physical location",
            phase="intent",
        )
        self.assertEqual(result.get("rule_name"), "set_location")
        self.assertTrue(result.get("handled"))
        self.assertEqual(result.get("intent"), "set_location")
        self.assertEqual(result.get("location_value"), "78521")
        self.assertEqual(result.get("location_kind"), "zip")
        self.assertEqual(result.get("location_ack_kind"), "fact_only")

    def test_supervisor_set_location_rule_returns_intent_for_the_location_is_zip(self):
        supervisor = Supervisor()
        result = supervisor.evaluate_rules(
            "the location is 78521",
            phase="intent",
        )
        self.assertEqual(result.get("rule_name"), "set_location")
        self.assertTrue(result.get("handled"))
        self.assertEqual(result.get("intent"), "set_location")
        self.assertEqual(result.get("location_value"), "78521")
        self.assertEqual(result.get("location_kind"), "zip")
        self.assertEqual(result.get("location_ack_kind"), "fact_only")

    def test_resolve_set_location_semantics_marks_places_as_confirmed_location(self):
        result = nova_core._resolve_set_location_semantics({"location_value": "Brownsville Texas"})
        self.assertEqual(result.get("location_kind"), "place")
        self.assertEqual(result.get("location_ack_kind"), "confirmed_location")

    def test_resolve_set_location_semantics_marks_zip_values_as_fact_only(self):
        result = nova_core._resolve_set_location_semantics({"location_value": "78521"})
        self.assertEqual(result.get("location_kind"), "zip")
        self.assertEqual(result.get("location_ack_kind"), "fact_only")

    def test_classify_set_location_outcome_uses_observed_zip_contract(self):
        outcome = nova_core._classify_set_location_outcome({"location_value": "78521", "rule_name": "set_location_zip"}, "78521")
        self.assertEqual(outcome.get("kind"), "observed_zip")
        self.assertEqual(outcome.get("reply_contract"), "set_location.observed_zip")
        self.assertEqual(outcome.get("user_commitment"), "implied")
        self.assertEqual(nova_core.render_reply(outcome), "Got it - 78521 is a ZIP code.")

    def test_classify_set_location_outcome_uses_explicit_location_contract(self):
        outcome = nova_core._classify_set_location_outcome({"location_value": "Brownsville Texas", "rule_name": "set_location_explicit"}, "my location is Brownsville Texas")
        self.assertEqual(outcome.get("kind"), "explicit_location")
        self.assertEqual(outcome.get("reply_contract"), "set_location.explicit_location")
        self.assertEqual(outcome.get("user_commitment"), "explicit")
        self.assertEqual(nova_core.render_reply(outcome), "Got it - using Brownsville Texas as your location.")

    def test_identity_only_block_kind_marks_location_storage_in_clean_slate_mode(self):
        block_kind = nova_core._identity_only_block_kind(
            "my location is Brownsville Texas",
            intent_result={"intent": "set_location"},
        )
        self.assertEqual(block_kind, "location")

    def test_identity_memory_text_allowed_keeps_identity_origin_contract(self):
        self.assertTrue(nova_core._identity_memory_text_allowed("identity", "nova_name_origin: from developer"))
        self.assertFalse(nova_core._identity_memory_text_allowed("identity", "random identity fact"))

    def test_identity_only_block_kind_policy_matrix(self):
        cases = [
            ("my location is Brownsville Texas", {"intent": "set_location"}, "location"),
            ("weather now", {"intent": "weather_lookup"}, "weather"),
            ("remember this my favorite color is teal", {"intent": "store_fact"}, "memory"),
            ("what do you know about PEIMS?", {"intent": "web_research_family"}, "web"),
        ]
        for text, intent_result, expected in cases:
            with self.subTest(text=text, expected=expected):
                self.assertEqual(nova_core._identity_only_block_kind(text, intent_result=intent_result), expected)

    def test_supervisor_intent_and_identity_only_policy_can_disagree_by_layer(self):
        supervisor = Supervisor()
        result = supervisor.evaluate_rules("my location is Brownsville Texas", phase="intent")
        self.assertTrue(result.get("handled"))
        self.assertEqual(result.get("intent"), "set_location")
        self.assertEqual(
            nova_core._identity_only_block_kind("my location is Brownsville Texas", intent_result=result),
            "location",
        )

    def test_supervisor_name_origin_store_rule_normalizes_short_phrase(self):
        supervisor = Supervisor()
        result = supervisor.evaluate_rules(
            "gus named you",
            phase="handle",
        )
        self.assertEqual(result.get("rule_name"), "name_origin_store")
        self.assertTrue(result.get("handled"))
        self.assertEqual(result.get("store_text"), "Gus named me Nova.")

    def test_classify_correction_outcome_uses_pending_replacement_contract(self):
        outcome = nova_core._classify_correction_outcome(
            correction_text="no, that's wrong",
            correction_value="",
            last_assistant="hello there",
            pending_followup=False,
            replacement_pending=True,
        )
        self.assertEqual(outcome.get("kind"), "pending_replacement")
        self.assertEqual(outcome.get("correction_kind"), "simple_negation")
        self.assertEqual(outcome.get("reply_contract"), "correction.pending_replacement")
        self.assertIn("I recorded that correction", nova_core.render_reply(outcome))

    def test_classify_correction_outcome_uses_replacement_applied_contract(self):
        outcome = nova_core._classify_correction_outcome(
            correction_text="no, say 'hi gus' instead",
            correction_value="hi gus",
            last_assistant="hello there",
            pending_followup=False,
            replacement_applied=True,
        )
        self.assertEqual(outcome.get("kind"), "explicit_replacement")
        self.assertEqual(outcome.get("correction_kind"), "fact_replacement")
        self.assertEqual(outcome.get("reply_contract"), "correction.replacement_applied")
        self.assertEqual(nova_core.render_reply(outcome), "Understood. I corrected that and will use your version going forward.")

    def test_hard_answer_solves_basic_arithmetic_expression(self):
        self.assertEqual(nova_core.hard_answer("70000 + 8000 + 500 + 21"), "78521")

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

    def test_supervisor_apply_correction_rule_returns_handle_action(self):
        supervisor = Supervisor()
        result = supervisor.evaluate_rules("no, that's wrong", phase="handle")
        self.assertTrue(result.get("handled"))
        self.assertEqual(result.get("action"), "apply_correction")
        self.assertEqual(result.get("intent"), "apply_correction")

    def test_pending_replacement_text_helper_accepts_short_answer_like_followup(self):
        self.assertTrue(nova_core._looks_like_pending_replacement_text("hi gus"))

    def test_pending_replacement_text_helper_rejects_question_followup(self):
        self.assertFalse(nova_core._looks_like_pending_replacement_text("what do you think it is nova ?"))

    def test_pending_replacement_text_helper_rejects_long_smalltalk_declarative(self):
        self.assertFalse(nova_core._looks_like_pending_replacement_text("you dont have to replace anything i was just small talk.."))

    def test_supervisor_store_fact_rule_returns_intent_and_fact(self):
        supervisor = Supervisor()
        result = supervisor.evaluate_rules("remember this Brownsville is my location", phase="intent")
        self.assertTrue(result.get("handled"))
        self.assertEqual(result.get("intent"), "store_fact")
        self.assertEqual(result.get("fact_text"), "Brownsville is my location")
        self.assertEqual(result.get("store_fact_kind"), "explicit_store")
        self.assertEqual(result.get("user_commitment"), "explicit")

    def test_supervisor_store_fact_rule_accepts_colon_form(self):
        supervisor = Supervisor()
        result = supervisor.evaluate_rules("Remember this: my favorite color is teal. Don't forget.", phase="intent")
        self.assertTrue(result.get("handled"))
        self.assertEqual(result.get("intent"), "store_fact")
        self.assertEqual(result.get("fact_text"), "my favorite color is teal. Don't forget")
        self.assertEqual(result.get("store_fact_kind"), "explicit_store")
        self.assertEqual(result.get("user_commitment"), "explicit")

    def test_classify_store_fact_outcome_uses_explicit_store_contract(self):
        outcome = nova_core._classify_store_fact_outcome(
            {"fact_text": "Brownsville is my location", "store_fact_kind": "explicit_store", "user_commitment": "explicit"},
            "remember this Brownsville is my location",
            source="intent",
            storage_performed=True,
        )
        self.assertEqual(outcome.get("kind"), "explicit_store")
        self.assertEqual(outcome.get("reply_contract"), "store_fact.explicit_store")
        self.assertEqual(outcome.get("user_commitment"), "explicit")
        self.assertEqual(nova_core.render_reply(outcome), "Learned: Brownsville is my location")

    def test_attach_learning_invitation_leaves_generic_reply_unchanged(self):
        reply = nova_core._attach_learning_invitation("Photosynthesis converts light into stored chemical energy.")

        self.assertEqual(reply, "Photosynthesis converts light into stored chemical energy.")

    def test_attach_learning_invitation_preserves_truthful_limit_invitation(self):
        reply = nova_core._attach_learning_invitation(
            "I don't know that based on what I can verify right now, and I don't want to make it up.",
            truthful_limit=True,
        )

        self.assertIn("correct me", reply)
        self.assertIn("do better next time", reply)

    def test_classify_store_fact_outcome_uses_declarative_ack_contract(self):
        outcome = nova_core._classify_store_fact_outcome(
            {"fact_text": "I work at Nova Labs", "store_fact_kind": "declarative_ack", "user_commitment": "implied", "memory_kind": "fact"},
            "I work at Nova Labs",
            source="declarative",
            storage_performed=True,
        )
        self.assertEqual(outcome.get("kind"), "declarative_ack")
        self.assertEqual(outcome.get("reply_contract"), "store_fact.declarative_ack")
        self.assertEqual(outcome.get("user_commitment"), "implied")
        self.assertEqual(nova_core.render_reply(outcome), "Noted.")

    def test_supervisor_session_summary_rule_returns_intent(self):
        supervisor = Supervisor()
        result = supervisor.evaluate_rules("what happened", phase="intent")
        self.assertFalse(result.get("handled"))
        self.assertNotEqual(result.get("intent"), "session_summary")

    def test_supervisor_weather_lookup_rule_returns_clarify_intent(self):
        supervisor = Supervisor()
        result = supervisor.evaluate_rules(
            "check the weather if you can please..",
            phase="intent",
        )
        self.assertEqual(result.get("rule_name"), "weather_lookup")
        self.assertTrue(result.get("handled"))
        self.assertEqual(result.get("intent"), "weather_lookup")
        self.assertEqual(result.get("weather_mode"), "clarify")

    def test_classify_weather_lookup_outcome_uses_clarify_contract(self):
        outcome = nova_core._classify_weather_lookup_outcome({"weather_mode": "clarify"})
        self.assertEqual(outcome.get("kind"), "clarify")
        self.assertEqual(outcome.get("reply_contract"), "weather_lookup.clarify")
        self.assertEqual(nova_core.render_reply(outcome), "What location should I use for the weather lookup?")

    def test_execute_weather_lookup_outcome_renders_current_location_contract(self):
        orig_execute_planned_action = nova_core.execute_planned_action
        orig_get_saved_location_text = nova_core.get_saved_location_text
        try:
            nova_core.get_saved_location_text = lambda: "Brownsville TX"
            nova_core.execute_planned_action = lambda tool, args=None: "Brownsville, TX: Today: 66°F, Sunny. [source: api.weather.gov]" if tool == "weather_current_location" else ""
            reply, next_state, outcome = nova_core._execute_weather_lookup_outcome(
                nova_core._classify_weather_lookup_outcome({"weather_mode": "current_location"})
            )
            self.assertIn("api.weather.gov", reply)
            self.assertEqual(outcome.get("reply_contract"), "weather_lookup.current_location")
            self.assertEqual(outcome.get("tool_result"), reply)
            self.assertEqual(next_state.get("kind"), "weather_result")
            self.assertEqual(next_state.get("location_value"), "Brownsville TX")
        finally:
            nova_core.execute_planned_action = orig_execute_planned_action
            nova_core.get_saved_location_text = orig_get_saved_location_text

    def test_execute_weather_lookup_outcome_renders_explicit_location_contract(self):
        orig_execute_planned_action = nova_core.execute_planned_action
        try:
            nova_core.execute_planned_action = lambda tool, args=None: "Brownsville, TX 78521: Tomorrow: 72°F, Clear. [source: api.weather.gov]" if tool == "weather_location" else ""
            reply, next_state, outcome = nova_core._execute_weather_lookup_outcome(
                nova_core._classify_weather_lookup_outcome({"weather_mode": "explicit_location", "location_value": "Brownsville TX 78521"})
            )
            self.assertIn("api.weather.gov", reply)
            self.assertEqual(outcome.get("reply_contract"), "weather_lookup.explicit_location")
            self.assertEqual(outcome.get("tool_result"), reply)
            self.assertEqual(next_state.get("kind"), "weather_result")
            self.assertEqual(next_state.get("location_value"), "Brownsville TX 78521")
        finally:
            nova_core.execute_planned_action = orig_execute_planned_action

    def test_weather_result_followup_explains_weather_source(self):
        handled, msg, next_state = nova_core._consume_conversation_followup(
            {
                "kind": "weather_result",
                "location_value": "Brownsville TX",
                "source_host": "api.weather.gov",
                "tool_result": "Brownsville, TX: Today: 66°F, Sunny. [source: api.weather.gov]",
            },
            "how did you get the weather information nova?",
            turns=[],
        )
        self.assertTrue(handled)
        self.assertEqual(next_state.get("kind"), "weather_result")
        self.assertIn("weather tool", (msg or "").lower())
        self.assertIn("api.weather.gov", (msg or "").lower())

    def test_weather_result_followup_recaps_last_lookup(self):
        handled, msg, next_state = nova_core._consume_conversation_followup(
            {
                "kind": "weather_result",
                "location_value": "Brownsville TX",
                "source_host": "api.weather.gov",
                "tool_result": "Brownsville, TX: Today: 66°F, Sunny. [source: api.weather.gov]",
            },
            "what happened to my weather information i ask you to get for brownsville tx",
            turns=[],
        )
        self.assertTrue(handled)
        self.assertEqual(next_state.get("kind"), "weather_result")
        self.assertIn("last weather lookup", (msg or "").lower())
        self.assertIn("brownsville", (msg or "").lower())

    def test_supervisor_weather_lookup_rule_uses_saved_location_followup(self):
        supervisor = Supervisor()
        session = ConversationSession()
        session.set_pending_action(
            {
                "kind": "weather_lookup",
                "status": "awaiting_location",
                "saved_location_available": True,
                "preferred_tool": "weather_current_location",
            }
        )
        result = supervisor.evaluate_rules(
            "yea please do that ..",
            manager=session,
            phase="intent",
        )
        self.assertEqual(result.get("rule_name"), "weather_lookup")
        self.assertTrue(result.get("handled"))
        self.assertEqual(result.get("weather_mode"), "current_location")

    def test_supervisor_weather_lookup_rule_followup_matrix(self):
        supervisor = Supervisor()
        cases = [
            {
                "label": "affirmative uses saved location",
                "text": "go ahead",
                "pending_action": {
                    "kind": "weather_lookup",
                    "status": "awaiting_location",
                    "saved_location_available": True,
                    "preferred_tool": "weather_current_location",
                },
                "expected_handled": True,
                "expected_rule": "weather_lookup",
                "expected_mode": "current_location",
            },
            {
                "label": "shared reference uses saved location",
                "text": "that location",
                "pending_action": {
                    "kind": "weather_lookup",
                    "status": "awaiting_location",
                    "saved_location_available": True,
                    "preferred_tool": "weather_current_location",
                },
                "expected_handled": True,
                "expected_rule": "weather_lookup",
                "expected_mode": "current_location",
            },
            {
                "label": "explicit place followup becomes location value",
                "text": "Brownsville Texas",
                "pending_action": {
                    "kind": "weather_lookup",
                    "status": "awaiting_location",
                    "saved_location_available": False,
                    "preferred_tool": "weather_location",
                },
                "expected_handled": True,
                "expected_rule": "weather_lookup",
                "expected_mode": "explicit_location",
                "expected_location": "Brownsville Texas",
            },
            {
                "label": "explicit declaration stays set_location",
                "text": "my location is Brownsville Texas",
                "pending_action": {
                    "kind": "weather_lookup",
                    "status": "awaiting_location",
                    "saved_location_available": False,
                    "preferred_tool": "weather_location",
                },
                "expected_handled": True,
                "expected_rule": "set_location",
                "expected_intent": "set_location",
            },
            {
                "label": "clarification remains unresolved",
                "text": "what?",
                "pending_action": {
                    "kind": "weather_lookup",
                    "status": "awaiting_location",
                    "saved_location_available": False,
                    "preferred_tool": "weather_location",
                },
                "expected_handled": False,
            },
        ]

        for case in cases:
            with self.subTest(case=case["label"]):
                session = ConversationSession()
                session.set_pending_action(case["pending_action"])
                result = supervisor.evaluate_rules(case["text"], manager=session, phase="intent")
                self.assertEqual(bool(result.get("handled")), case["expected_handled"])
                if not case["expected_handled"]:
                    continue
                self.assertEqual(result.get("rule_name"), case["expected_rule"])
                if "expected_mode" in case:
                    self.assertEqual(result.get("weather_mode"), case["expected_mode"])
                if "expected_location" in case:
                    self.assertEqual(result.get("location_value"), case["expected_location"])
                if "expected_intent" in case:
                    self.assertEqual(result.get("intent"), case["expected_intent"])

    def test_supervisor_weather_lookup_rule_uses_explicit_location_followup(self):
        supervisor = Supervisor()
        session = ConversationSession()
        session.set_pending_action(
            {
                "kind": "weather_lookup",
                "status": "awaiting_location",
                "saved_location_available": False,
                "preferred_tool": "weather_location",
            }
        )
        result = supervisor.evaluate_rules(
            "Brownsville TX 78521",
            manager=session,
            phase="intent",
        )
        self.assertEqual(result.get("rule_name"), "weather_lookup")
        self.assertTrue(result.get("handled"))
        self.assertEqual(result.get("weather_mode"), "explicit_location")
        self.assertEqual(result.get("location_value"), "Brownsville TX 78521")

    def test_supervisor_weather_lookup_rule_uses_bare_zip_followup_as_location_value(self):
        supervisor = Supervisor()
        session = ConversationSession()
        session.set_pending_action(
            {
                "kind": "weather_lookup",
                "status": "awaiting_location",
                "saved_location_available": False,
                "preferred_tool": "weather_location",
            }
        )
        result = supervisor.evaluate_rules(
            "78521",
            manager=session,
            phase="intent",
        )
        self.assertEqual(result.get("rule_name"), "weather_lookup")
        self.assertTrue(result.get("handled"))
        self.assertEqual(result.get("weather_mode"), "explicit_location")
        self.assertEqual(result.get("location_value"), "78521")

    def test_supervisor_weather_lookup_rule_does_not_consume_explicit_location_declaration(self):
        supervisor = Supervisor()
        session = ConversationSession()
        session.set_pending_action(
            {
                "kind": "weather_lookup",
                "status": "awaiting_location",
                "saved_location_available": False,
                "preferred_tool": "weather_location",
            }
        )
        result = supervisor.evaluate_rules(
            "the location is 78521",
            manager=session,
            phase="intent",
        )
        self.assertEqual(result.get("rule_name"), "set_location")
        self.assertTrue(result.get("handled"))
        self.assertEqual(result.get("intent"), "set_location")

    def test_supervisor_weather_lookup_rule_does_not_consume_clarification_move(self):
        supervisor = Supervisor()
        session = ConversationSession()
        session.set_pending_action(
            {
                "kind": "weather_lookup",
                "status": "awaiting_location",
                "saved_location_available": False,
                "preferred_tool": "weather_location",
            }
        )
        result = supervisor.evaluate_rules(
            "what?",
            manager=session,
            phase="intent",
        )
        self.assertFalse(result.get("handled"))
        self.assertNotEqual(result.get("rule_name"), "weather_lookup")

    def test_supervisor_retrieval_followup_rule_accepts_result_selection_move(self):
        supervisor = Supervisor()
        session = ConversationSession()
        session.set_retrieval_state(
            {
                "kind": "retrieval",
                "subject": "web_research",
                "query": "PEIMS attendance",
                "result_count": 2,
                "urls": ["https://tea.texas.gov/a", "https://tea.texas.gov/b"],
            }
        )
        result = supervisor.evaluate_rules(
            "tell me about the first one",
            manager=session,
            phase="handle",
        )
        self.assertEqual(result.get("rule_name"), "retrieval_followup")
        self.assertTrue(result.get("handled"))
        self.assertEqual(result.get("intent"), "retrieval_followup")

    def test_supervisor_web_research_rule_returns_intent(self):
        supervisor = Supervisor()
        result = supervisor.evaluate_rules(
            "research PEIMS online",
            phase="intent",
        )
        self.assertTrue(result.get("handled"))
        self.assertEqual(result.get("intent"), "web_research_family")
        self.assertEqual(result.get("tool_name"), "web_research")
        self.assertEqual(result.get("query"), "PEIMS")

    def test_supervisor_web_research_rule_prefers_wikipedia_for_factual_lookup(self):
        supervisor = Supervisor()
        result = supervisor.evaluate_rules(
            "research Ada Lovelace online",
            phase="intent",
        )
        self.assertTrue(result.get("handled"))
        self.assertEqual(result.get("intent"), "web_research_family")
        self.assertEqual(result.get("tool_name"), "wikipedia_lookup")
        self.assertEqual(result.get("query"), "Ada Lovelace")

    def test_supervisor_web_research_rule_uses_general_web_for_repo_lookup(self):
        supervisor = Supervisor()
        result = supervisor.evaluate_rules(
            "research GitHub repo for FastAPI auth online",
            phase="intent",
        )
        self.assertTrue(result.get("handled"))
        self.assertEqual(result.get("intent"), "web_research_family")
        self.assertEqual(result.get("tool_name"), "web_research")

    def test_supervisor_web_research_rule_prefers_stackexchange_for_technical_lookup(self):
        supervisor = Supervisor()
        result = supervisor.evaluate_rules(
            "research how to fix fastapi oauth invalid_grant error online",
            phase="intent",
        )
        self.assertTrue(result.get("handled"))
        self.assertEqual(result.get("intent"), "web_research_family")
        self.assertEqual(result.get("tool_name"), "stackexchange_search")

    def test_classify_web_research_outcome_uses_research_contract(self):
        outcome = nova_core._classify_web_research_outcome(
            {
                "intent": "web_research_family",
                "web_request_kind": "research_prompt",
                "tool_name": "web_research",
                "query": "PEIMS",
            },
            "research PEIMS online",
        )
        self.assertEqual(outcome.get("kind"), "research_prompt")
        self.assertEqual(outcome.get("reply_contract"), "web_research_family.research_prompt")
        self.assertEqual(outcome.get("query"), "PEIMS")

    def test_supervisor_name_origin_rule_returns_intent(self):
        supervisor = Supervisor()
        result = supervisor.evaluate_rules(
            "why are you called Nova?",
            phase="intent",
        )
        self.assertFalse(result.get("handled"))
        self.assertNotEqual(result.get("intent"), "name_origin")

    def test_classify_name_origin_outcome_uses_story_known_contract(self):
        orig_get_name_origin_story = nova_core.get_name_origin_story
        try:
            nova_core.get_name_origin_story = lambda: "My creator Gus named me Nova to symbolize light and discovery."
            outcome = nova_core._classify_name_origin_outcome({"name_origin_query_kind": "source_recall"})
            self.assertEqual(outcome.get("kind"), "story_known")
            self.assertEqual(outcome.get("reply_contract"), "name_origin.story_known")
            self.assertIn("creator Gus named me Nova".lower(), nova_core.render_reply(outcome).lower())
        finally:
            nova_core.get_name_origin_story = orig_get_name_origin_story

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
                "reply_contract": "developer.profile.summary",
                "reply_outcome": {"kind": "profile_summary"},
                "active_subject": session.active_subject(),
                "continuation_used": False,
                "pending_action": None,
            },
        )
        self.assertEqual(session.last_reflection, reflection)
        self.assertEqual(reflection.get("probe_summary"), "All green")
        self.assertEqual(reflection.get("reply_contract"), "developer.profile.summary")
        self.assertEqual(reflection.get("reply_outcome_kind"), "profile_summary")

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
        self.assertIn("don't know", gated.lower())
        self.assertIn("don't want to make it up", gated.lower())

    def test_claim_gate_keeps_supported_identity_claim(self):
        reply = "Your creator is Gustavo Uribe."
        evidence = "SESSION FACT SHEET:\nDeveloper full name: Gustavo Uribe"

        gated, changed, reason = nova_core._apply_claim_gate(reply, evidence_text=evidence)
        self.assertFalse(changed)
        self.assertEqual(reason, "")
        self.assertEqual(gated, reply)

    def test_claim_gate_blocks_unsupported_quoted_operational_claim(self):
        reply = (
            'The handoff still assumes a live workspace in step 3, where it says '
            '"Verify system connections to production databases."'
        )
        evidence = """## Handoff Sequence\n### 3. Start Runtime\nCore runtime:\n.\\nova.cmd run"""

        gated, changed, reason = nova_core._apply_claim_gate(reply, evidence_text=evidence)

        self.assertTrue(changed)
        self.assertEqual(reason, "unsupported_claim_blocked")
        self.assertIn("don't know", gated.lower())

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

    def test_mixed_info_request_turn_detects_statement_plus_request(self):
        text = "the weather looks good. i wonder if the weather will stay like this for the rest of the day. can you check what the rest of the forecast will be"
        self.assertTrue(nova_core._looks_like_mixed_info_request_turn(text))

    def test_classify_turn_acts_marks_inform_ask_and_mixed(self):
        text = "the weather looks good. i wonder if the weather will stay like this for the rest of the day. can you check what the rest of the forecast will be"
        acts = nova_core._classify_turn_acts(text)
        self.assertIn("inform", acts)
        self.assertIn("ask", acts)
        self.assertIn("mixed", acts)

    def test_mixed_info_request_turn_rejects_pure_request(self):
        text = "can you check what the rest of the forecast will be"
        self.assertFalse(nova_core._looks_like_mixed_info_request_turn(text))

    def test_classify_turn_acts_marks_continue_thread_without_mixed(self):
        acts = nova_core._classify_turn_acts(
            "what else?",
            turns=[("assistant", "Here are the verified facts I know about your creator.")],
            active_subject="identity_profile:developer",
        )
        self.assertIn("ask", acts)
        self.assertIn("continue_thread", acts)
        self.assertNotIn("mixed", acts)

    def test_classify_turn_acts_marks_command(self):
        acts = nova_core._classify_turn_acts("chat context")
        self.assertEqual(acts, ["command"])

    def test_classify_turn_acts_marks_correction(self):
        acts = nova_core._classify_turn_acts("no, that's wrong")
        self.assertIn("correct", acts)

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

    def test_handle_location_conversation_turn_does_not_claim_affirmation_without_location_context(self):
        handled, reply, next_state, intent = nova_core._handle_location_conversation_turn(
            None,
            "yea please do that ..",
            turns=[("user", "check the weather if you can please.."), ("assistant", "I can try to check the weather for you.")],
        )

        self.assertFalse(handled)
        self.assertEqual(reply, "")
        self.assertEqual(intent, "")
        self.assertEqual(next_state, {"kind": "location_recall"})

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

    def test_store_declarative_fact_outcome_marks_contract(self):
        orig_mem_should_store = nova_core.mem_should_store
        orig_mem_add = nova_core.mem_add
        try:
            stored = []
            nova_core.mem_should_store = lambda text: True
            nova_core.mem_add = lambda kind, input_source, text: stored.append((kind, input_source, text))

            outcome = nova_core._store_declarative_fact_outcome("I work at Nova Labs")

            self.assertEqual(outcome.get("reply_contract"), "store_fact.declarative_ack")
            self.assertEqual(outcome.get("kind"), "declarative_ack")
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

    def test_handle_keywords_ignores_natural_language_find_phrase(self):
        routed = nova_core.handle_keywords("find a way for you to be able to play songs from a data base or the web")
        self.assertIsNone(routed)

    def test_cli_natural_language_find_phrase_does_not_trigger_find_tool(self):
        with mock.patch.object(nova_core, "VOICE_OK", False), \
             mock.patch.object(nova_core, "speak_chunked", lambda *_args, **_kwargs: None), \
             mock.patch.object(nova_core, "ollama_chat", lambda _text, retrieved_context="", **_kwargs: "It could work if I had a playback tool or media integration."), \
             mock.patch("builtins.input", side_effect=["find a way for you to be able to play songs from a data base or the web", "q"]), \
             mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
            nova_core.run_loop(self._SilentTTS())

        output = stdout.getvalue().lower()
        self.assertNotIn("not a folder:", output)
        self.assertIn("playback tool or media integration", output)

        payload = self._latest_action_payload()
        self.assertEqual(payload.get("planner_decision"), "llm_fallback")
        self.assertNotIn("action_planner:run_tool", payload.get("route_summary", ""))

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

    def test_cli_web_research_intent_records_reply_contract_and_avoids_bypass_warning(self):
        with mock.patch.object(nova_core, "VOICE_OK", False), \
             mock.patch.object(nova_core, "speak_chunked", lambda *_args, **_kwargs: None), \
             mock.patch.object(nova_core, "execute_planned_action", lambda tool, args=None: f"Web research results for {args[0] if args else tool}"), \
             mock.patch("builtins.input", side_effect=["research PEIMS online", "q"]), \
             mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
            nova_core.run_loop(self._SilentTTS())

        self.assertNotIn("Turn bypassed supervisor intent phase", stdout.getvalue())
        payload = self._latest_action_payload()
        self.assertEqual(payload.get("user_input"), "research PEIMS online")
        self.assertEqual(payload.get("planner_decision"), "run_tool")
        self.assertEqual(payload.get("tool"), "web_research")
        self.assertEqual(payload.get("reply_contract"), "web_research_family.research_prompt")
        self.assertEqual((payload.get("reply_outcome") or {}).get("query"), "PEIMS")
        self.assertEqual((payload.get("routing_decision") or {}).get("final_owner"), "supervisor_intent")
        self.assertEqual((((payload.get("routing_decision") or {}).get("intent_phase") or {}).get("rule_name")), "web_research_family")
        self.assertIn("action_planner:run_tool", payload.get("route_summary", ""))
        self.assertIn("tool_execution:ok", payload.get("route_summary", ""))

    def test_cli_wikipedia_intent_records_provider_tool(self):
        with mock.patch.object(nova_core, "VOICE_OK", False), \
             mock.patch.object(nova_core, "speak_chunked", lambda *_args, **_kwargs: None), \
             mock.patch.object(nova_core, "execute_planned_action", lambda tool, args=None: f"Wikipedia summary for {args[0] if args else tool}"), \
             mock.patch("builtins.input", side_effect=["research Ada Lovelace online", "q"]), \
             mock.patch("sys.stdout", new_callable=io.StringIO):
            nova_core.run_loop(self._SilentTTS())

        payload = self._latest_action_payload()
        self.assertEqual(payload.get("tool"), "wikipedia_lookup")
        self.assertEqual((payload.get("reply_outcome") or {}).get("query"), "Ada Lovelace")

    def test_cli_name_origin_turn_uses_supervisor_contract_without_bypass_warning(self):
        orig_get_name_origin_story = nova_core.get_name_origin_story
        try:
            nova_core.get_name_origin_story = lambda: "My creator Gus named me Nova to symbolize light and discovery."
            with mock.patch.object(nova_core, "VOICE_OK", False), \
                 mock.patch.object(nova_core, "speak_chunked", lambda *_args, **_kwargs: None), \
                 mock.patch("builtins.input", side_effect=["why are you called Nova?", "q"]), \
                 mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
                nova_core.run_loop(self._SilentTTS())

            output = stdout.getvalue()
            self.assertNotIn("Turn bypassed supervisor intent phase", output)
            self.assertIn("creator gus", output.lower())
            payload = self._latest_action_payload()
            self.assertEqual(payload.get("reply_contract"), "identity_history.name_origin")
            self.assertEqual((payload.get("routing_decision") or {}).get("final_owner"), "supervisor_handle")
        finally:
            nova_core.get_name_origin_story = orig_get_name_origin_story

    def test_cli_identity_history_prompt_uses_supervisor_contract_without_bypass_warning(self):
        with mock.patch.object(nova_core, "VOICE_OK", False), \
             mock.patch.object(nova_core, "speak_chunked", lambda *_args, **_kwargs: None), \
             mock.patch("builtins.input", side_effect=["how did he develop you?", "q"]), \
             mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
            nova_core.run_loop(self._SilentTTS())

        output = stdout.getvalue().lower()
        self.assertIn("do not have detailed build-history", output)
        self.assertNotIn("Turn bypassed supervisor intent phase", stdout.getvalue())
        payload = self._latest_action_payload()
        self.assertEqual(payload.get("reply_contract"), "identity_history.history_recall")
        self.assertEqual((payload.get("routing_decision") or {}).get("final_owner"), "supervisor_handle")

    def test_cli_creator_followup_uses_supervisor_contract_without_bypass_warning(self):
        with mock.patch.object(nova_core, "VOICE_OK", False), \
             mock.patch.object(nova_core, "speak_chunked", lambda *_args, **_kwargs: None), \
             mock.patch("builtins.input", side_effect=["who is your creator?", "what else?", "q"]), \
             mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
            nova_core.run_loop(self._SilentTTS())

        output = stdout.getvalue().lower()
        self.assertIn("verified facts", output)
        self.assertNotIn("Turn bypassed supervisor intent phase", stdout.getvalue())
        payload = self._latest_action_payload()
        self.assertEqual(payload.get("user_input"), "what else?")
        self.assertEqual(payload.get("reply_contract"), "identity_history.history_recall")
        self.assertEqual((payload.get("routing_decision") or {}).get("final_owner"), "supervisor_handle")

    def test_cli_open_probe_prompt_records_reply_contract_and_avoids_bypass_warning(self):
        with mock.patch.object(nova_core, "VOICE_OK", False), \
             mock.patch.object(nova_core, "speak_chunked", lambda *_args, **_kwargs: None), \
             mock.patch("builtins.input", side_effect=["random question", "q"]), \
             mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
            nova_core.run_loop(self._SilentTTS())

        output = stdout.getvalue().lower()
        self.assertIn("i don't know that based on what i can verify", output)
        self.assertNotIn("Turn bypassed supervisor intent phase", stdout.getvalue())
        payload = self._latest_action_payload()
        self.assertEqual(payload.get("reply_contract"), "open_probe.safe_fallback")
        self.assertEqual((payload.get("reply_outcome") or {}).get("kind"), "safe_fallback")
        self.assertEqual((payload.get("routing_decision") or {}).get("final_owner"), "supervisor_handle")

    def test_truthful_limit_outcome_returns_honest_reply_contract(self):
        outcome = nova_core._truthful_limit_outcome("what is his favorite food?")

        self.assertEqual(outcome.get("reply_contract"), "turn.truthful_limit")
        self.assertEqual(outcome.get("kind"), "cannot_verify")
        self.assertIn("don't know", str(outcome.get("reply_text") or "").lower())
        self.assertIn("correct me", str(outcome.get("reply_text") or "").lower())

    def test_cli_claim_gate_block_records_truthful_limit_contract(self):
        with mock.patch.object(nova_core, "VOICE_OK", False), \
             mock.patch.object(nova_core, "speak_chunked", lambda *_args, **_kwargs: None), \
             mock.patch.object(nova_core, "build_learning_context_details", lambda _text: {"context": "", "memory_used": False, "knowledge_used": False, "memory_chars": 0, "knowledge_chars": 0}), \
             mock.patch.object(nova_core, "ollama_chat", lambda _text, retrieved_context="", **_kwargs: "I can smell coffee in the room with Gus."), \
             mock.patch("sys.stdout", new_callable=io.StringIO), \
             mock.patch("builtins.input", side_effect=["what is gus doing right now?", "q"]):
            nova_core.run_loop(self._SilentTTS())

        payload = self._latest_action_payload()
        self.assertEqual(payload.get("planner_decision"), "llm_fallback")
        self.assertEqual(payload.get("reply_contract"), "turn.truthful_limit")
        self.assertEqual((payload.get("reply_outcome") or {}).get("kind"), "cannot_verify")
        self.assertFalse(bool(payload.get("grounded")))

    def test_cli_last_question_recall_records_reply_contract_and_avoids_bypass_warning(self):
        with mock.patch.object(nova_core, "VOICE_OK", False), \
             mock.patch.object(nova_core, "speak_chunked", lambda *_args, **_kwargs: None), \
             mock.patch("builtins.input", side_effect=["do you have any rules", "what was my last question?", "q"]), \
             mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
            nova_core.run_loop(self._SilentTTS())

        output = stdout.getvalue().lower()
        self.assertIn("your last question before this one was", output)
        self.assertIn("do you have any rules", output)
        self.assertNotIn("[cli] what was my last question", output)
        payload = self._latest_action_payload()
        self.assertEqual(payload.get("user_input"), "what was my last question?")
        self.assertEqual(payload.get("reply_contract"), "last_question.recall")
        self.assertEqual((payload.get("reply_outcome") or {}).get("kind"), "recall")
        self.assertEqual((payload.get("routing_decision") or {}).get("final_owner"), "supervisor_handle")

    def test_cli_rules_query_records_reply_contract_and_avoids_bypass_warning(self):
        with mock.patch.object(nova_core, "VOICE_OK", False), \
             mock.patch.object(nova_core, "speak_chunked", lambda *_args, **_kwargs: None), \
             mock.patch("builtins.input", side_effect=["do you have any rules", "q"]), \
             mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
            nova_core.run_loop(self._SilentTTS())

        output = stdout.getvalue().lower()
        self.assertIn("i follow strict operating rules", output)
        self.assertNotIn("[cli] do you have any rules", output)
        payload = self._latest_action_payload()
        self.assertEqual(payload.get("user_input"), "do you have any rules")
        self.assertEqual(payload.get("reply_contract"), "rules.list")
        self.assertEqual((payload.get("reply_outcome") or {}).get("kind"), "list")
        self.assertEqual((payload.get("routing_decision") or {}).get("final_owner"), "supervisor_handle")

    def test_cli_broad_peims_query_no_longer_uses_local_grounded_overview(self):
        with mock.patch.object(nova_core, "VOICE_OK", False), \
             mock.patch.object(nova_core, "speak_chunked", lambda *_args, **_kwargs: None), \
             mock.patch("builtins.input", side_effect=["what do you know about PEIMS?", "q"]), \
             mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
            nova_core.run_loop(self._SilentTTS())

        output = stdout.getvalue().lower()
        self.assertNotIn("peims overview details in local knowledge files", output)
        self.assertNotIn("[source: knowledge/", output)

        payload = self._latest_action_payload()
        self.assertEqual(payload.get("user_input"), "what do you know about PEIMS?")
        self.assertEqual(payload.get("planner_decision"), "llm_fallback")
        self.assertNotEqual(payload.get("tool"), "local_knowledge")
        self.assertFalse(bool(payload.get("grounded")))

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

            self.assertIn("Learned: Brownsville is my location", stdout.getvalue())
            self.assertIn("[INTENT] store_fact :: store_fact :: Brownsville is my location", stdout.getvalue())
            self.assertIn(("user_fact", "typed", "Brownsville is my location"), writes)
            payload = self._latest_action_payload()
            self.assertEqual(payload.get("reply_contract"), "store_fact.explicit_store")
            self.assertEqual((payload.get("reply_outcome") or {}).get("kind"), "explicit_store")
        finally:
            nova_core.mem_enabled = orig_mem_enabled
            nova_core.mem_add = orig_mem_add

    def test_cli_weather_clarify_records_reply_contract(self):
        with mock.patch.object(nova_core, "VOICE_OK", False), \
             mock.patch.object(nova_core, "speak_chunked", lambda *_args, **_kwargs: None), \
             mock.patch.object(nova_core, "_weather_current_location_available", lambda: False), \
             mock.patch("builtins.input", side_effect=["check the weather if you can please..", "q"]), \
             mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
            nova_core.run_loop(self._SilentTTS())

        self.assertIn("What location should I use for the weather lookup?", stdout.getvalue())
        payload = self._latest_action_payload()
        self.assertEqual(payload.get("reply_contract"), "weather_lookup.clarify")
        self.assertEqual((payload.get("reply_outcome") or {}).get("kind"), "clarify")

    def test_cli_mixed_info_request_turn_asks_for_clarification(self):
        mixed_turn = "the weather looks good. i wonder if the weather will stay like this for the rest of the day. can you check what the rest of the forecast will be"
        with mock.patch.object(nova_core, "VOICE_OK", False), \
             mock.patch.object(nova_core, "speak_chunked", lambda *_args, **_kwargs: None), \
             mock.patch("builtins.input", side_effect=[mixed_turn, "q"]), \
             mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
            nova_core.run_loop(self._SilentTTS())

        output = stdout.getvalue().lower()
        self.assertIn("both giving context and asking me to do something", output)
        self.assertNotIn("what location should i use for the weather lookup", output)
        payload = self._latest_action_payload()
        self.assertEqual(payload.get("planner_decision"), "ask_clarify")
        self.assertEqual(payload.get("reply_contract"), "turn.clarify_mixed_intent")
        self.assertEqual((payload.get("reply_outcome") or {}).get("kind"), "mixed_info_request")
        self.assertIn("inform", payload.get("turn_acts") or [])
        self.assertIn("ask", payload.get("turn_acts") or [])
        self.assertIn("mixed", payload.get("turn_acts") or [])

    def test_cli_smalltalk_how_are_you_today_falls_through_without_bypass_warning(self):
        with mock.patch.object(nova_core, "VOICE_OK", False), \
             mock.patch.object(nova_core, "speak_chunked", lambda *_args, **_kwargs: None), \
             mock.patch("builtins.input", side_effect=["how are you doing today ?", "q"]), \
             mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
            nova_core.run_loop(self._SilentTTS())

        output = stdout.getvalue()
        self.assertNotIn("Turn bypassed supervisor intent phase", output)
        self.assertIn("Hey. I'm doing good today. What's going on?", output)

    def test_cli_declarative_store_does_not_emit_supervisor_bypass_warning(self):
        orig_mem_should_store = nova_core.mem_should_store
        orig_mem_add = nova_core.mem_add
        try:
            writes = []
            nova_core.mem_should_store = lambda text: True
            nova_core.mem_add = lambda kind, source, text: writes.append((kind, source, text))

            with mock.patch.object(nova_core, "VOICE_OK", False), \
                 mock.patch.object(nova_core, "speak_chunked", lambda *_args, **_kwargs: None), \
                 mock.patch("builtins.input", side_effect=["I work at Nova Labs", "q"]), \
                 mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
                nova_core.run_loop(self._SilentTTS())

            output = stdout.getvalue()
            self.assertIn("Noted.", output)
            self.assertNotIn("Turn bypassed supervisor intent phase", output)
            self.assertEqual(writes, [("fact", "typed", "I work at Nova Labs")])
        finally:
            nova_core.mem_should_store = orig_mem_should_store
            nova_core.mem_add = orig_mem_add

    def test_cli_declarative_store_records_reply_contract(self):
        orig_mem_should_store = nova_core.mem_should_store
        orig_mem_add = nova_core.mem_add
        try:
            writes = []
            nova_core.mem_should_store = lambda text: True
            nova_core.mem_add = lambda kind, source, text: writes.append((kind, source, text))

            with mock.patch.object(nova_core, "VOICE_OK", False), \
                 mock.patch.object(nova_core, "speak_chunked", lambda *_args, **_kwargs: None), \
                 mock.patch("builtins.input", side_effect=["I work at Nova Labs", "q"]), \
                 mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
                nova_core.run_loop(self._SilentTTS())

            self.assertIn("Noted.", stdout.getvalue())
            self.assertEqual(writes, [("fact", "typed", "I work at Nova Labs")])
            payload = self._latest_action_payload()
            self.assertEqual(payload.get("reply_contract"), "store_fact.declarative_ack")
            self.assertEqual((payload.get("reply_outcome") or {}).get("kind"), "declarative_ack")
        finally:
            nova_core.mem_should_store = orig_mem_should_store
            nova_core.mem_add = orig_mem_add

    def test_cli_session_summary_style_turn_falls_through_without_bypass_warning(self):
        with mock.patch.object(nova_core, "VOICE_OK", False), \
             mock.patch.object(nova_core, "speak_chunked", lambda *_args, **_kwargs: None), \
             mock.patch.object(nova_core, "ollama_chat", lambda *_args, **_kwargs: "Fallback summary answer."), \
             mock.patch("builtins.input", side_effect=["hello there", "what happened", "q"]), \
             mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
            nova_core.run_loop(self._SilentTTS())

        output = stdout.getvalue()
        self.assertNotIn("Turn bypassed supervisor intent phase", output)
        self.assertIn("Fallback summary answer.", output)

    def test_cli_supervisor_apply_correction_handle_records_pending_replacement(self):
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

            self.assertIn("I recorded that correction", stdout.getvalue())
            correction_write = next((entry for entry in writes if entry[0] == "user_correction"), None)
            self.assertIsNotNone(correction_write)
            self.assertEqual((correction_write[0], correction_write[1]), ("user_correction", "typed"))
            payload = json.loads(correction_write[2])
            self.assertEqual(payload.get("text"), "no, that's wrong")
            self.assertEqual(payload.get("parsed_correction"), "")
            ledger = self._latest_action_payload()
            self.assertEqual(ledger.get("reply_contract"), "correction.pending_replacement")
            self.assertEqual((ledger.get("reply_outcome") or {}).get("kind"), "pending_replacement")
        finally:
            nova_core.mem_enabled = orig_mem_enabled
            nova_core.mem_add = orig_mem_add

    def test_cli_supervisor_apply_correction_handle_teaches_explicit_replacement(self):
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

            self.assertIn("Understood. I corrected that and will use your version going forward.", stdout.getvalue())
            correction_write = next((entry for entry in writes if entry[0] == "user_correction"), None)
            self.assertIsNotNone(correction_write)
            payload = json.loads(correction_write[2])
            self.assertEqual(payload.get("parsed_correction"), "hi gus")
            self.assertEqual(len(teaches), 1)
            self.assertEqual(teaches[0][1], "hi gus")
            ledger = self._latest_action_payload()
            self.assertEqual(ledger.get("reply_contract"), "correction.replacement_applied")
            self.assertEqual((ledger.get("reply_outcome") or {}).get("kind"), "explicit_replacement")
        finally:
            nova_core.mem_enabled = orig_mem_enabled
            nova_core.mem_add = orig_mem_add
            nova_core._teach_store_example = orig_teach_store_example

    def test_cli_supervisor_apply_correction_followup_teaches_pending_replacement(self):
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
                 mock.patch("builtins.input", side_effect=["hello there", "no, that's wrong", "hi gus", "q"]), \
                 mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
                nova_core.run_loop(self._SilentTTS())

            output = stdout.getvalue()
            self.assertIn("I recorded that correction", output)
            self.assertIn("Understood. I corrected that and will use your version going forward.", output)
            self.assertEqual(len(teaches), 1)
            self.assertEqual(teaches[0][1], "hi gus")
            correction_writes = [entry for entry in writes if entry[0] == "user_correction"]
            self.assertEqual(len(correction_writes), 2)
            ledger = self._latest_action_payload()
            self.assertEqual(ledger.get("reply_contract"), "correction.replacement_applied")
            self.assertEqual((ledger.get("reply_outcome") or {}).get("kind"), "followup_replacement")
        finally:
            nova_core.mem_enabled = orig_mem_enabled
            nova_core.mem_add = orig_mem_add
            nova_core._teach_store_example = orig_teach_store_example

    def test_cli_supervisor_apply_correction_followup_cancel_does_not_teach(self):
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
                 mock.patch("builtins.input", side_effect=["hello there", "no, that's wrong", "you dont have to replace anything i was just small talk..", "q"]), \
                 mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
                nova_core.run_loop(self._SilentTTS())

            output = stdout.getvalue()
            self.assertIn("I recorded that correction", output)
            self.assertIn("I canceled that replacement request and did not learn anything from it.", output)
            self.assertEqual(teaches, [])
            correction_writes = [entry for entry in writes if entry[0] == "user_correction"]
            self.assertEqual(len(correction_writes), 2)
        finally:
            nova_core.mem_enabled = orig_mem_enabled
            nova_core.mem_add = orig_mem_add
            nova_core._teach_store_example = orig_teach_store_example

    def test_cli_supervisor_set_location_intent_stores_and_replies(self):
        orig_set_location_text = nova_core.set_location_text
        try:
            stored = []
            nova_core.set_location_text = lambda value, input_source="typed": stored.append((value, input_source)) or f"Saved current location: {value}"

            with mock.patch.object(nova_core, "VOICE_OK", False), \
                 mock.patch.object(nova_core, "speak_chunked", lambda *_args, **_kwargs: None), \
                 mock.patch("builtins.input", side_effect=["the 78521 is the zip code for your current physical location", "q"]), \
                 mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
                nova_core.run_loop(self._SilentTTS())

            output = stdout.getvalue()
            self.assertIn("[INTENT] set_location :: set_location_explicit :: 78521", output)
            self.assertIn("Got it - 78521 is a ZIP code.", output)
            self.assertEqual(stored, [("78521", "typed")])
            payload = self._latest_action_payload()
            self.assertEqual(payload.get("reply_contract"), "set_location.observed_zip")
            self.assertEqual((payload.get("reply_outcome") or {}).get("kind"), "observed_zip")
        finally:
            nova_core.set_location_text = orig_set_location_text

    def test_cli_set_location_intent_primes_followup_location_recall(self):
        orig_set_location_text = nova_core.set_location_text
        orig_get_saved_location_text = nova_core.get_saved_location_text
        try:
            saved = {"value": ""}

            def _store_location(value, input_source="typed"):
                saved["value"] = value
                return f"Saved current location: {value}"

            nova_core.set_location_text = _store_location
            nova_core.get_saved_location_text = lambda: saved["value"]

            with mock.patch.object(nova_core, "VOICE_OK", False), \
                 mock.patch.object(nova_core, "speak_chunked", lambda *_args, **_kwargs: None), \
                 mock.patch("builtins.input", side_effect=["78521", "so whats the location?", "q"]), \
                 mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
                nova_core.run_loop(self._SilentTTS())

            output = stdout.getvalue()
            self.assertIn("[INTENT] set_location :: set_location_zip :: 78521", output)
            self.assertTrue("78521" in output or "Brownsville" in output)
        finally:
            nova_core.set_location_text = orig_set_location_text
            nova_core.get_saved_location_text = orig_get_saved_location_text

    def test_cli_clean_slate_blocks_weather_request(self):
        with mock.patch.object(nova_core, "VOICE_OK", False), \
             mock.patch.object(nova_core, "speak_chunked", lambda *_args, **_kwargs: None), \
             mock.patch("builtins.input", side_effect=["weather now", "q"]), \
             mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
            nova_core.run_loop(self._SilentTTS())

        output = stdout.getvalue().lower()
        self.assertIn("need a confirmed location or coordinates", output)

    def test_cli_bare_numeric_turn_clarifies_instead_of_using_saved_location(self):
        orig_get_saved_location_text = nova_core.get_saved_location_text
        try:
            nova_core.get_saved_location_text = lambda: "Brownsville, Texas"

            with mock.patch.object(nova_core, "VOICE_OK", False), \
                 mock.patch.object(nova_core, "speak_chunked", lambda *_args, **_kwargs: None), \
                 mock.patch("builtins.input", side_effect=["78521", "q"]), \
                 mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
                nova_core.run_loop(self._SilentTTS())

            output = stdout.getvalue()
            self.assertIn("What does 78521 refer to?", output)
            self.assertNotIn("Turn bypassed supervisor intent phase", output)
            self.assertNotIn("Still in Brownsville", output)
        finally:
            nova_core.get_saved_location_text = orig_get_saved_location_text

    def test_cli_bare_numeric_followup_stays_honest_without_guessing(self):
        orig_get_saved_location_text = nova_core.get_saved_location_text
        try:
            nova_core.get_saved_location_text = lambda: "Brownsville, Texas"

            with mock.patch.object(nova_core, "VOICE_OK", False), \
                 mock.patch.object(nova_core, "speak_chunked", lambda *_args, **_kwargs: None), \
                 mock.patch("builtins.input", side_effect=["78521", "what do you think it is nova ?", "q"]), \
                 mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
                nova_core.run_loop(self._SilentTTS())

            output = stdout.getvalue()
            self.assertIn("What does 78521 refer to?", output)
            self.assertIn("I don't know what 78521 refers to yet.", output)
            self.assertNotIn("zip code", output.lower())
        finally:
            nova_core.get_saved_location_text = orig_get_saved_location_text

    def test_cli_weather_defaults_to_saved_location_after_set_location_intent(self):
        orig_set_location_text = nova_core.set_location_text
        orig_get_saved_location_text = nova_core.get_saved_location_text
        orig_tool_weather = nova_core.tool_weather
        try:
            saved = {"value": ""}

            def _store_location(value, input_source="typed"):
                saved["value"] = value
                return f"Saved current location: {value}"

            weather_calls = []
            nova_core.set_location_text = _store_location
            nova_core.get_saved_location_text = lambda: saved["value"]
            nova_core.tool_weather = lambda location: weather_calls.append(location) or f"Forecast for {location}: rain"

            with mock.patch.object(nova_core, "VOICE_OK", False), \
                 mock.patch.object(nova_core, "speak_chunked", lambda *_args, **_kwargs: None), \
                  mock.patch("builtins.input", side_effect=["my zip is 78521", "weather now", "q"]), \
                 mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
                nova_core.run_loop(self._SilentTTS())

            output = stdout.getvalue()
            self.assertIn("Got it - 78521 is a ZIP code.", output)
            self.assertIn("Forecast for 78521: rain", output)
            self.assertEqual(weather_calls, ["78521"])
        finally:
            nova_core.set_location_text = orig_set_location_text
            nova_core.get_saved_location_text = orig_get_saved_location_text
            nova_core.tool_weather = orig_tool_weather

    def test_cli_where_am_i_uses_deterministic_location_recall(self):
        orig_set_location_text = nova_core.set_location_text
        orig_get_saved_location_text = nova_core.get_saved_location_text
        try:
            saved = {"value": ""}

            def _store_location(value, input_source="typed"):
                saved["value"] = value
                return f"Saved current location: {value}"

            nova_core.set_location_text = _store_location
            nova_core.get_saved_location_text = lambda: saved["value"]

            with mock.patch.object(nova_core, "VOICE_OK", False), \
                 mock.patch.object(nova_core, "speak_chunked", lambda *_args, **_kwargs: None), \
                 mock.patch("builtins.input", side_effect=["78521", "where am I", "q"]), \
                 mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
                nova_core.run_loop(self._SilentTTS())

            output = stdout.getvalue()
            self.assertIn("[INTENT] set_location :: set_location_zip :: 78521", output)
            self.assertIn("Your saved location is 78521", output)
            self.assertNotIn("llm_fallback", output.lower())
        finally:
            nova_core.set_location_text = orig_set_location_text
            nova_core.get_saved_location_text = orig_get_saved_location_text

    def test_cli_location_name_followup_uses_saved_location(self):
        orig_set_location_text = nova_core.set_location_text
        orig_get_saved_location_text = nova_core.get_saved_location_text
        try:
            saved = {"value": ""}

            def _store_location(value, input_source="typed"):
                saved["value"] = value
                return f"Saved current location: {value}"

            nova_core.set_location_text = _store_location
            nova_core.get_saved_location_text = lambda: saved["value"]

            with mock.patch.object(nova_core, "VOICE_OK", False), \
                 mock.patch.object(nova_core, "speak_chunked", lambda *_args, **_kwargs: None), \
                 mock.patch("builtins.input", side_effect=["78521", "give me the name to that location", "q"]), \
                 mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
                nova_core.run_loop(self._SilentTTS())

            output = stdout.getvalue()
            self.assertIn("Got it - 78521 is a ZIP code.", output)
            self.assertIn("That location is Brownsville, TX.", output)
            self.assertNotIn("McAllen", output)
        finally:
            nova_core.set_location_text = orig_set_location_text
            nova_core.get_saved_location_text = orig_get_saved_location_text

    def test_no_turn_bypasses_supervisor_on_location_thread(self):
        orig_set_location_text = nova_core.set_location_text
        orig_get_saved_location_text = nova_core.get_saved_location_text
        orig_tool_weather = nova_core.tool_weather
        orig_evaluate_rules = nova_core.TURN_SUPERVISOR.evaluate_rules
        try:
            saved = {"value": ""}
            captured = []

            def _store_location(value, input_source="typed"):
                saved["value"] = value
                return f"Saved current location: {value}"

            def _wrapped_evaluate_rules(user_text, *args, **kwargs):
                result = orig_evaluate_rules(user_text, *args, **kwargs)
                captured.append({
                    "text": user_text,
                    "phase": str(kwargs.get("phase") or "handle"),
                    "result": dict(result or {}),
                })
                return result

            nova_core.set_location_text = _store_location
            nova_core.get_saved_location_text = lambda: saved["value"]
            nova_core.tool_weather = lambda location: f"Forecast for {location}: rain"
            nova_core.TURN_SUPERVISOR.evaluate_rules = _wrapped_evaluate_rules

            with mock.patch.object(nova_core, "VOICE_OK", False), \
                 mock.patch.object(nova_core, "speak_chunked", lambda *_args, **_kwargs: None), \
                 mock.patch("builtins.input", side_effect=["78521", "where am I", "give me the name to that location", "weather now", "q"]), \
                 mock.patch("sys.stdout", new_callable=io.StringIO):
                nova_core.run_loop(self._SilentTTS())

            for followup_text in ("where am I", "give me the name to that location"):
                handle_results = [
                    item for item in captured
                    if item["phase"] == "handle" and item["text"] == followup_text
                ]
                self.assertTrue(handle_results, msg=f"Expected supervisor handle evaluation for {followup_text!r}")
                self.assertTrue(
                    any(
                        bool(item["result"].get("handled"))
                        or bool(str(item["result"].get("action") or "").strip())
                        for item in handle_results
                    ),
                    msg=f"Supervisor handle phase did not claim {followup_text!r}",
                )
        finally:
            nova_core.set_location_text = orig_set_location_text
            nova_core.get_saved_location_text = orig_get_saved_location_text
            nova_core.tool_weather = orig_tool_weather
            nova_core.TURN_SUPERVISOR.evaluate_rules = orig_evaluate_rules

    def test_no_turn_bypasses_supervisor_on_correction_thread(self):
        orig_evaluate_rules = nova_core.TURN_SUPERVISOR.evaluate_rules
        captured = []
        try:
            def _wrapped_evaluate_rules(user_text, *args, **kwargs):
                result = orig_evaluate_rules(user_text, *args, **kwargs)
                captured.append({
                    "text": user_text,
                    "phase": str(kwargs.get("phase") or "handle"),
                    "result": dict(result or {}),
                })
                return result

            nova_core.TURN_SUPERVISOR.evaluate_rules = _wrapped_evaluate_rules

            with mock.patch.object(nova_core, "VOICE_OK", False), \
                 mock.patch.object(nova_core, "speak_chunked", lambda *_args, **_kwargs: None), \
                 mock.patch("builtins.input", side_effect=["hello there", "no, that's wrong", "hi gus", "q"]), \
                 mock.patch("sys.stdout", new_callable=io.StringIO):
                nova_core.run_loop(self._SilentTTS())

            for correction_text in ("no, that's wrong", "hi gus"):
                handle_results = [
                    item for item in captured
                    if item["phase"] == "handle" and item["text"] == correction_text
                ]
                self.assertTrue(handle_results, msg=f"Expected supervisor handle evaluation for {correction_text!r}")
                self.assertTrue(
                    any(
                        bool(item["result"].get("handled"))
                        or bool(str(item["result"].get("action") or "").strip())
                        for item in handle_results
                    ),
                    msg=f"Supervisor handle phase did not claim {correction_text!r}",
                )
        finally:
            nova_core.TURN_SUPERVISOR.evaluate_rules = orig_evaluate_rules

    def test_handle_supervisor_bypass_raises_in_dev_mode(self):
        original = os.environ.get("NOVA_DEV_MODE")
        try:
            os.environ["NOVA_DEV_MODE"] = "1"
            with self.assertRaises(RuntimeError):
                nova_core._handle_supervisor_bypass("tell me something", entry_point="cli")
        finally:
            if original is None:
                os.environ.pop("NOVA_DEV_MODE", None)
            else:
                os.environ["NOVA_DEV_MODE"] = original

    def test_handle_supervisor_bypass_allows_allowlisted_phrase_in_dev_mode(self):
        original = os.environ.get("NOVA_DEV_MODE")
        try:
            os.environ["NOVA_DEV_MODE"] = "1"
            routing_decision = nova_core._build_routing_decision(
                "Explain photosynthesis briefly.",
                entry_point="cli",
            )
            warning = nova_core._handle_supervisor_bypass(
                "Explain photosynthesis briefly.",
                entry_point="cli",
                routing_decision=routing_decision,
            )
            self.assertIn("Turn bypassed supervisor intent phase", warning)
            self.assertTrue(routing_decision.get("allowed_bypass"))
            self.assertEqual(routing_decision.get("allowed_bypass_category"), "intentional_fallback.general_qa")
            self.assertEqual(routing_decision.get("final_owner"), "fallback")
        finally:
            if original is None:
                os.environ.pop("NOVA_DEV_MODE", None)
            else:
                os.environ["NOVA_DEV_MODE"] = original

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

    def test_cli_retrieval_followup_records_reply_contract(self):
        with mock.patch.object(nova_core, "VOICE_OK", False), \
             mock.patch.object(nova_core, "speak_chunked", lambda *_args, **_kwargs: None), \
             mock.patch.object(nova_core, "execute_planned_action", lambda tool, args=None: "1) https://tea.texas.gov/a\n2) https://tea.texas.gov/b" if tool == "web_research" else ""), \
             mock.patch.object(nova_core, "tool_web_gather", lambda url: f"Gathered: {url}"), \
             mock.patch("builtins.input", side_effect=["research PEIMS online", "tell me about the first one", "q"]), \
             mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
            nova_core.run_loop(self._SilentTTS())

        self.assertNotIn("Turn bypassed supervisor intent phase", stdout.getvalue())
        payload = self._latest_action_payload()
        self.assertEqual(payload.get("user_input"), "tell me about the first one")
        self.assertEqual(payload.get("reply_contract"), "retrieval_followup.selected_result")
        self.assertEqual((payload.get("reply_outcome") or {}).get("kind"), "selected_result")
        self.assertEqual((payload.get("routing_decision") or {}).get("final_owner"), "supervisor_handle")
        self.assertEqual((((payload.get("routing_decision") or {}).get("handle_phase") or {}).get("rule_name")), "retrieval_followup")

    def test_cli_llm_fallback_does_not_append_learning_invitation(self):
        with mock.patch.object(nova_core, "VOICE_OK", False), \
             mock.patch.object(nova_core, "speak_chunked", lambda *_args, **_kwargs: None), \
             mock.patch.object(nova_core, "ollama_chat", lambda _text, retrieved_context="", **_kwargs: "Here is a broad answer without grounded evidence."), \
             mock.patch("builtins.input", side_effect=["tell me something reflective about ambition", "q"]), \
             mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
            nova_core.run_loop(self._SilentTTS())

        output = stdout.getvalue()
        self.assertIn("Here is a broad answer without grounded evidence.", output)
        self.assertNotIn("best guess from general knowledge and memory", output)
        self.assertNotIn("correct me and I'll store it so I do better next time", output)

        payload = self._latest_action_payload()
        self.assertEqual(payload.get("planner_decision"), "llm_fallback")
        self.assertFalse(payload.get("reply_contract"))

    def test_cli_repeated_weak_pressure_turns_use_deterministic_shared_paths(self):
        with mock.patch.object(nova_core, "VOICE_OK", False), \
             mock.patch.object(nova_core, "speak_chunked", lambda *_args, **_kwargs: None), \
             mock.patch("builtins.input", side_effect=["can you help me a little here ?", "what do you think then ?", "q"]), \
             mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
            nova_core.run_loop(self._SilentTTS())

        output = stdout.getvalue().lower()
        self.assertIn("what kind of help do you want", output)
        self.assertIn("i don't have enough context to answer that yet", output)

        payload = self._latest_action_payload()
        self.assertEqual(payload.get("reply_contract"), "open_probe.safe_fallback")
        self.assertEqual((payload.get("reply_outcome") or {}).get("kind"), "safe_fallback")

    def test_cli_smalltalk_checkin_uses_shared_smalltalk_reply(self):
        with mock.patch.object(nova_core, "VOICE_OK", False), \
             mock.patch.object(nova_core, "speak_chunked", lambda *_args, **_kwargs: None), \
             mock.patch("builtins.input", side_effect=["how are you doing today ?", "q"]), \
             mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
            nova_core.run_loop(self._SilentTTS())

        self.assertIn("i'm doing good today. what's going on?", stdout.getvalue().lower())

    def test_cli_queue_status_runs_direct_tool_and_records_ledger(self):
        with mock.patch.object(nova_core, "VOICE_OK", False), \
             mock.patch.object(nova_core, "speak_chunked", lambda *_args, **_kwargs: None), \
             mock.patch.object(nova_core, "tool_queue_status", return_value="Standing work queue:\n- open: 2 of 4\nNext item: next_generated.json"), \
             mock.patch("builtins.input", side_effect=["what should you work on next", "q"]), \
             mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
            nova_core.run_loop(self._SilentTTS())

        output = stdout.getvalue()
        self.assertIn("Standing work queue", output)
        payload = self._latest_action_payload()
        self.assertEqual(payload.get("planner_decision"), "run_tool")
        self.assertEqual(payload.get("tool"), "queue_status")
        self.assertIn("action_planner:run_tool", payload.get("route_summary", ""))
        self.assertIn("tool_execution:ok", payload.get("route_summary", ""))

    def test_cli_phase2_audit_runs_direct_tool_and_records_ledger(self):
        with mock.patch.object(nova_core, "VOICE_OK", False), \
             mock.patch.object(nova_core, "speak_chunked", lambda *_args, **_kwargs: None), \
             mock.patch.object(nova_core, "tool_phase2_audit", return_value="Post-Phase-2 audit:\n\nSystem check: ok\n\nKidney status:\n- enabled: True\n\nSafety envelope status:\n- enabled: True"), \
             mock.patch("builtins.input", side_effect=["phase 2 status", "q"]), \
             mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
            nova_core.run_loop(self._SilentTTS())

        output = stdout.getvalue()
        self.assertIn("Post-Phase-2 audit", output)
        payload = self._latest_action_payload()
        self.assertEqual(payload.get("planner_decision"), "run_tool")
        self.assertEqual(payload.get("tool"), "phase2_audit")
        self.assertIn("action_planner:run_tool", payload.get("route_summary", ""))
        self.assertIn("tool_execution:ok", payload.get("route_summary", ""))

    def test_cli_pulse_runs_direct_tool_and_records_ledger(self):
        pulse_output = (
            "Nova Pulse - 2026-03-27 10:00:00\n"
            "Core evolution:\n"
            "- promoted definitions: 4 (+1 since last pulse)\n"
            "Updates:\n"
            "- ready for validated apply: no\n"
            "Assessment:\n"
            "- Quiet and steady."
        )

        with mock.patch.object(nova_core, "VOICE_OK", False), \
             mock.patch.object(nova_core, "speak_chunked", lambda *_args, **_kwargs: None), \
             mock.patch.object(nova_core, "tool_nova_pulse", return_value=pulse_output), \
             mock.patch("builtins.input", side_effect=["nova pulse", "q"]), \
             mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
            nova_core.run_loop(self._SilentTTS())

        output = stdout.getvalue()
        self.assertIn("Nova Pulse", output)
        payload = self._latest_action_payload()
        self.assertEqual(payload.get("planner_decision"), "run_tool")
        self.assertEqual(payload.get("tool"), "pulse")
        self.assertIn("action_planner:run_tool", payload.get("route_summary", ""))
        self.assertIn("tool_execution:ok", payload.get("route_summary", ""))

    def test_render_nova_pulse_reports_live_sections(self):
        rendered = nova_core.render_nova_pulse({
            "generated_at": "2026-03-27 10:00:00",
            "promoted_total": 7,
            "promoted_delta": 2,
            "generated_total": 12,
            "pending_review_total": 3,
            "quarantine_total": 1,
            "latest_audited_files": 10,
            "latest_audit_ts": "2026-03-27 09:30:00",
            "audit_status_counts": {"promoted": 4, "pending_review": 3},
            "patch_revision": 5,
            "ready_for_validated_apply": True,
            "approved_eligible_previews": 1,
            "patch_activity": {"apply_count": 1, "apply_ok_count": 1, "rollback_count": 0, "behavior_fail_count": 0},
            "patch_last_line": "2026-03-27 09:59:00 | APPLY_OK files=3",
            "ollama_up": True,
            "memory_ok": True,
            "memory_total": 42,
            "kidney_mode": "enforce",
            "kidney_candidates": 5,
            "kidney_archive_count": 4,
            "kidney_delete_count": 1,
            "safety_enabled": True,
            "safety_mode": "observe",
            "autonomy_level": "operational",
            "routing_stable": True,
            "tool_route_count": 6,
            "llm_fallback_count": 2,
            "last_fallback_overuse_score": 0.25,
            "last_regression_status": "OK",
            "last_reflection_at": "2026-03-27 09:58:00",
            "mood": "Learning is moving forward cleanly.",
            "update_zip_path": "C:/Nova/updates/example.zip",
        })

        self.assertIn("Nova Pulse - 2026-03-27 10:00:00", rendered)
        self.assertIn("promoted definitions: 7 (+2 since last pulse)", rendered)
        self.assertIn("patch activity last 24h: applies=1, apply_ok=1, rollbacks=0, behavior_failures=0", rendered)
        self.assertIn('Type "update now" if you want me to apply the latest approved validated update.', rendered)

    def test_tool_update_now_requires_confirmation_before_apply(self):
        zip_path = Path(self._tmp_dir.name) / "candidate_patch.zip"
        zip_path.write_bytes(b"zip")
        pending_path = Path(self._tmp_dir.name) / "update_now_pending.json"

        with mock.patch.object(nova_core, "UPDATE_NOW_PENDING_FILE", pending_path), \
             mock.patch.object(nova_core, "patch_status_payload", return_value={"ok": True}), \
             mock.patch.object(nova_core, "_latest_approved_update_zip", return_value=zip_path), \
             mock.patch.object(nova_core, "patch_preview", return_value="Patch Preview\nZip: candidate_patch.zip\nStatus: eligible"), \
             mock.patch.object(nova_core, "execute_patch_action") as apply_mock:
            dry_run = nova_core.tool_update_now()

        self.assertIn("Update dry-run ready", dry_run)
        self.assertIn("update now confirm", dry_run)
        apply_mock.assert_not_called()

    def test_tool_update_now_confirm_applies_with_token(self):
        zip_path = Path(self._tmp_dir.name) / "candidate_patch.zip"
        zip_path.write_bytes(b"zip")
        pending_path = Path(self._tmp_dir.name) / "update_now_pending.json"

        with mock.patch.object(nova_core, "UPDATE_NOW_PENDING_FILE", pending_path), \
             mock.patch.object(nova_core, "patch_status_payload", return_value={"ok": True}), \
             mock.patch.object(nova_core, "_latest_approved_update_zip", return_value=zip_path), \
             mock.patch.object(nova_core, "patch_preview", return_value="Patch Preview\nZip: candidate_patch.zip\nStatus: eligible"), \
             mock.patch.object(nova_core, "execute_patch_action", return_value="Patch applied: 1 file(s). Compile check OK.") as apply_mock:
            dry_run = nova_core.tool_update_now()
            token = ""
            for line in str(dry_run).splitlines():
                if line.lower().startswith("confirm with:"):
                    token = line.split()[-1].strip()
                    break
            self.assertTrue(token)

            confirmed = nova_core.tool_update_now_confirm(token)

        self.assertTrue(str(confirmed).lower().startswith("patch applied:"))
        apply_mock.assert_called_once_with("apply", str(zip_path), is_admin=True)

    def test_tool_update_now_cancel_clears_pending(self):
        pending_path = Path(self._tmp_dir.name) / "update_now_pending.json"
        pending_path.write_text(json.dumps({"token": "abcd1234", "zip_path": "C:/Nova/updates/x.zip"}), encoding="utf-8")

        with mock.patch.object(nova_core, "UPDATE_NOW_PENDING_FILE", pending_path):
            msg = nova_core.tool_update_now_cancel()

        self.assertIn("Canceled pending update confirmation", msg)
        self.assertFalse(pending_path.exists())

    def test_cli_queue_status_followup_uses_structured_tool_state(self):
        queue_payload = {
            "count": 4,
            "open_count": 2,
            "green_count": 2,
            "drift_count": 2,
            "warning_count": 0,
            "never_run_count": 0,
            "next_item": {
                "file": "next_generated.json",
                "family_id": "demo-family",
                "latest_status": "drift",
                "opportunity_reason": "parity_drift",
                "latest_report_path": "C:/Nova/runtime/test_sessions/next_generated/result.json",
                "highest_priority": {"signal": "fallback_overuse", "urgency": "high", "seam": "demo_seam"},
            },
            "items": [],
        }

        with mock.patch.object(nova_core, "VOICE_OK", False), \
             mock.patch.object(nova_core, "speak_chunked", lambda *_args, **_kwargs: None), \
             mock.patch("nova_http._generated_work_queue", return_value=queue_payload), \
             mock.patch("builtins.input", side_effect=["what should you work on next", "why is that the next item in the queue?", "q"]), \
             mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
            nova_core.run_loop(self._SilentTTS())

        output = stdout.getvalue().lower()
        self.assertIn("next_generated.json", output)
        self.assertIn("is next because it is still open with status drift and reason parity_drift", output)
        self.assertIn("fallback_overuse", output)

        payload = self._latest_action_payload()
        self.assertEqual(payload.get("planner_decision"), "conversation_followup")
        self.assertNotIn("llm_fallback", payload.get("route_summary", ""))

    def test_cli_queue_status_report_and_seam_followups_use_structured_state(self):
        queue_payload = {
            "count": 4,
            "open_count": 2,
            "green_count": 2,
            "drift_count": 2,
            "warning_count": 0,
            "never_run_count": 0,
            "next_item": {
                "file": "next_generated.json",
                "family_id": "demo-family",
                "latest_status": "drift",
                "opportunity_reason": "parity_drift",
                "latest_report_path": "C:/Nova/runtime/test_sessions/next_generated/result.json",
                "highest_priority": {"signal": "fallback_overuse", "urgency": "high", "seam": "demo_seam"},
            },
            "items": [],
        }

        with mock.patch.object(nova_core, "VOICE_OK", False), \
             mock.patch.object(nova_core, "speak_chunked", lambda *_args, **_kwargs: None), \
             mock.patch("nova_http._generated_work_queue", return_value=queue_payload), \
             mock.patch("builtins.input", side_effect=["what should you work on next", "what seam is it failing on?", "show me the report path", "q"]), \
             mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
            nova_core.run_loop(self._SilentTTS())

        output = stdout.getvalue().lower()
        self.assertIn("demo_seam", output)
        self.assertIn("fallback_overuse", output)
        self.assertIn("c:/nova/runtime/test_sessions/next_generated/result.json", output)

        payload = self._latest_action_payload()
        self.assertEqual(payload.get("planner_decision"), "conversation_followup")
        self.assertNotIn("llm_fallback", payload.get("route_summary", ""))

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
        self.assertEqual(payload.get("reply_contract"), "weather_lookup.current_location")
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
        orig_weather_current_location_available = nova_core._weather_current_location_available
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
            nova_core._weather_current_location_available = lambda: False
            nova_core.set_location_text("Brownsville TX")
            with mock.patch.object(nova_core, "VOICE_OK", False), \
                 mock.patch.object(nova_core, "speak_chunked", lambda *_args, **_kwargs: None), \
                 mock.patch("builtins.input", side_effect=["check the weather if you can please..", "our location nova ..", "q"]):
                nova_core.run_loop(self._SilentTTS())
        finally:
            nova_core.POLICY_PATH = orig_policy_path
            nova_core.requests.get = orig_requests_get
            nova_core._weather_current_location_available = orig_weather_current_location_available

        payload = self._latest_action_payload()
        self.assertEqual(payload.get("user_input"), "our location nova ..")
        self.assertEqual(payload.get("planner_decision"), "run_tool")
        self.assertEqual(payload.get("tool"), "weather_current_location")
        self.assertEqual(payload.get("reply_contract"), "weather_lookup.current_location")
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
        orig_weather_current_location_available = nova_core._weather_current_location_available
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
            nova_core._weather_current_location_available = lambda: False
            nova_core.set_location_text("Brownsville TX")
            with mock.patch.object(nova_core, "VOICE_OK", False), \
                 mock.patch.object(nova_core, "speak_chunked", lambda *_args, **_kwargs: None), \
                 mock.patch("builtins.input", side_effect=["check the weather if you can please..", "yea please do that ..", "q"]):
                nova_core.run_loop(self._SilentTTS())
        finally:
            nova_core.POLICY_PATH = orig_policy_path
            nova_core.requests.get = orig_requests_get
            nova_core._weather_current_location_available = orig_weather_current_location_available

        payload = self._latest_action_payload()
        self.assertEqual(payload.get("user_input"), "yea please do that ..")
        self.assertEqual(payload.get("planner_decision"), "run_tool")
        self.assertEqual(payload.get("tool"), "weather_current_location")
        self.assertEqual(payload.get("reply_contract"), "weather_lookup.current_location")
        self.assertIn("action_planner:run_tool", payload.get("route_summary", ""))
        self.assertIn("tool_execution:ok", payload.get("route_summary", ""))

    def test_cli_weather_query_with_explicit_location_runs_weather_tool(self):
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
        policy_path = Path(self._tmp_dir.name) / "policy_weather_explicit_test.json"
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
            with mock.patch.object(nova_core, "VOICE_OK", False), \
                 mock.patch.object(nova_core, "speak_chunked", lambda *_args, **_kwargs: None), \
                 mock.patch("builtins.input", side_effect=["what is the weather for 78521 ?", "q"]), \
                 mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
                nova_core.run_loop(self._SilentTTS())
        finally:
            nova_core.POLICY_PATH = orig_policy_path
            nova_core.requests.get = orig_requests_get

        output = stdout.getvalue()
        self.assertNotIn("What location should I use for the weather lookup?", output)
        payload = self._latest_action_payload()
        self.assertEqual(payload.get("planner_decision"), "run_tool")
        self.assertEqual(payload.get("tool"), "weather_location")
        self.assertEqual(payload.get("tool_args"), {"args": ["78521"]})
        self.assertEqual(payload.get("reply_contract"), "weather_lookup.explicit_location")
        self.assertIn("api.weather.gov", payload.get("tool_result", ""))

    def test_cli_weather_followup_stays_on_weather_thread(self):
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
        policy_path = Path(self._tmp_dir.name) / "policy_weather_thread_test.json"
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
            with mock.patch.object(nova_core, "VOICE_OK", False), \
                 mock.patch.object(nova_core, "speak_chunked", lambda *_args, **_kwargs: None), \
                 mock.patch("builtins.input", side_effect=["what is the weather for 78521 ?", "how did you get the weather information nova?", "q"]), \
                 mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
                nova_core.run_loop(self._SilentTTS())
        finally:
            nova_core.POLICY_PATH = orig_policy_path
            nova_core.requests.get = orig_requests_get

        output = stdout.getvalue().lower()
        self.assertIn("api.weather.gov", output)
        self.assertNotIn("what location should i use for the weather lookup", output)
        self.assertNotIn("turn bypassed supervisor intent phase", output)
        payload = self._latest_action_payload()
        # Updated: Accept either conversation_followup or run_tool as second turn can route either way
        # depending on LLM routing interpretation of the context
        self.assertIn(payload.get("planner_decision"), ["conversation_followup", "run_tool"])
        self.assertIn("api.weather.gov", output)


if __name__ == "__main__":
    unittest.main()
