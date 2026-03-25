import io
import json
import tempfile
import unittest
from unittest import mock
from pathlib import Path

import nova_http
import nova_core


class TestHttpIdentityChat(unittest.TestCase):
    def setUp(self):
        nova_http.SESSION_TURNS.clear()
        nova_http.SESSION_STATE_MANAGER.clear()
        self.orig_remember_name_origin = nova_core.remember_name_origin
        self.orig_get_name_origin_story = nova_core.get_name_origin_story
        self.orig_mem_enabled = nova_core.mem_enabled
        self.orig_mem_should_store = nova_core.mem_should_store
        self.orig_mem_add = nova_core.mem_add
        self.orig_build_learning_context = nova_core.build_learning_context
        self.orig_build_fallback_context_details = nova_core.build_fallback_context_details
        self.orig_render_chat_context = nova_core._render_chat_context
        self.orig_ollama_chat = nova_core.ollama_chat
        self.orig_sanitize = nova_core.sanitize_llm_reply
        self.orig_tool_web_research = nova_core.tool_web_research
        self.orig_tool_web_gather = nova_core.tool_web_gather
        self.orig_mem_recall = nova_core.mem_recall
        self.orig_learned_facts_file = nova_core.LEARNED_FACTS_FILE
        self.orig_identity_file = nova_core.IDENTITY_FILE
        self.orig_action_ledger_dir = nova_core.ACTION_LEDGER_DIR
        self.orig_self_reflection_log = nova_core.SELF_REFLECTION_LOG
        self.orig_health_log = nova_core.HEALTH_LOG
        self._tmp_dir = tempfile.TemporaryDirectory()
        nova_core.LEARNED_FACTS_FILE = Path(self._tmp_dir.name) / "learned_facts_test.json"
        nova_core.IDENTITY_FILE = Path(self._tmp_dir.name) / "identity_test.json"
        nova_core.ACTION_LEDGER_DIR = Path(self._tmp_dir.name) / "actions"
        nova_core.SELF_REFLECTION_LOG = Path(self._tmp_dir.name) / "self_reflection.jsonl"
        nova_core.HEALTH_LOG = Path(self._tmp_dir.name) / "health.log"
        nova_core.TURN_SUPERVISOR.reset()

        nova_core.mem_should_store = lambda _text: False
        nova_core.mem_add = lambda *args, **kwargs: None
        nova_core.build_learning_context = lambda _text: ""
        nova_core._render_chat_context = lambda _turns: ""
        nova_core.ollama_chat = lambda text, retrieved_context="", **_kwargs: f"LLM:{text}"
        nova_core.sanitize_llm_reply = lambda text, _tool: text
        nova_core.tool_web_research = lambda _q: "Web research summary"

    def tearDown(self):
        nova_core.remember_name_origin = self.orig_remember_name_origin
        nova_core.get_name_origin_story = self.orig_get_name_origin_story
        nova_core.mem_enabled = self.orig_mem_enabled
        nova_core.mem_should_store = self.orig_mem_should_store
        nova_core.mem_add = self.orig_mem_add
        nova_core.build_learning_context = self.orig_build_learning_context
        nova_core.build_fallback_context_details = self.orig_build_fallback_context_details
        nova_core._render_chat_context = self.orig_render_chat_context
        nova_core.ollama_chat = self.orig_ollama_chat
        nova_core.sanitize_llm_reply = self.orig_sanitize
        nova_core.tool_web_research = self.orig_tool_web_research
        nova_core.tool_web_gather = self.orig_tool_web_gather
        nova_core.mem_recall = self.orig_mem_recall
        nova_core.LEARNED_FACTS_FILE = self.orig_learned_facts_file
        nova_core.IDENTITY_FILE = self.orig_identity_file
        nova_core.ACTION_LEDGER_DIR = self.orig_action_ledger_dir
        nova_core.SELF_REFLECTION_LOG = self.orig_self_reflection_log
        nova_core.HEALTH_LOG = self.orig_health_log
        nova_core.TURN_SUPERVISOR.reset()
        nova_http.SESSION_STATE_MANAGER.clear()
        self._tmp_dir.cleanup()

    def _latest_action_payload(self):
        files = sorted(nova_core.ACTION_LEDGER_DIR.glob("*.json"))
        self.assertTrue(files)
        return json.loads(files[-1].read_text(encoding="utf-8"))

    def test_remember_this_stores_name_origin(self):
        calls = []

        def fake_store(text: str) -> str:
            calls.append(text)
            return "Stored. I will remember this as the story behind my name."

        nova_core.remember_name_origin = fake_store

        out = nova_http.process_chat(
            "s1",
            "Here is the story behind your name. remember this nova... Nova was named by Gus.",
        )
        self.assertIn("Stored.", out)
        self.assertEqual(len(calls), 1)

    def test_last_question_reply_uses_session_history(self):
        nova_core.remember_name_origin = lambda _text: "Stored"
        nova_core.get_name_origin_story = lambda: ""

        out1 = nova_http.process_chat("s2", "do you have any rules")
        self.assertIn("I follow strict operating rules", out1)
        session = nova_http.SESSION_STATE_MANAGER.get("s2")
        self.assertEqual((session.last_reflection or {}).get("reply_contract"), "rules.list")
        self.assertEqual((session.last_reflection or {}).get("reply_outcome_kind"), "list")

        out2 = nova_http.process_chat("s2", "what was my last question ?")
        self.assertIn("do you have any rules", out2.lower())
        session = nova_http.SESSION_STATE_MANAGER.get("s2")
        self.assertEqual((session.last_reflection or {}).get("reply_contract"), "last_question.recall")
        self.assertEqual((session.last_reflection or {}).get("reply_outcome_kind"), "recall")

    def test_name_origin_question_prefers_saved_story(self):
        nova_core.remember_name_origin = lambda _text: "Stored"
        nova_core.get_name_origin_story = lambda: "My creator Gus named me Nova to symbolize light and discovery."

        out = nova_http.process_chat("s3", "so do you now know where your name comes from ?")
        self.assertIn("creator gus", out.lower())

    def test_peims_attendance_rules_routes_to_sourced_research(self):
        nova_core.remember_name_origin = lambda _text: "Stored"
        nova_core.get_name_origin_story = lambda: ""
        nova_core.tool_web_research = lambda _q: "Web research:\nhttps://tea.texas.gov/reports-and-data/data-submission/peims"
        nova_core.tool_web_gather = lambda _u: "[OK] Saved ...\nSummary snippet:\nAttendance data must be reported daily for each instructional day in PEIMS submissions."

        out = nova_http.process_chat("s4", "What are the attendance reporting rules for PEIMS?")
        low = out.lower()
        self.assertIn("allowlisted", low)
        self.assertIn("tea.texas.gov", low)

    def test_ui_tip_line_is_stripped_from_reply(self):
        nova_core.remember_name_origin = lambda _text: "Stored"
        nova_core.get_name_origin_story = lambda: ""
        nova_core.ollama_chat = lambda _text, retrieved_context="", **_kwargs: "Answer line\nTip: start server with --host 0.0.0.0 to test"

        out = nova_http.process_chat("s5", "Explain photosynthesis briefly.")
        self.assertIn("Answer line", out)
        self.assertNotIn("Tip: start server", out)

    def test_grounded_answer_adds_source_citations(self):
        nova_core.remember_name_origin = lambda _text: "Stored"
        nova_core.get_name_origin_story = lambda: ""

        def fake_research(_q: str):
            return "Web research results:\n1) https://tea.texas.gov/reports-and-data/data-submission/peims\n2) https://www.texasstudentdatasystem.org/"

        def fake_gather(url: str):
            if "tea.texas.gov" in url:
                return "[OK] Saved ...\nSummary snippet:\nAttendance data is required for each instructional day."
            return "[OK] Saved ...\nSummary snippet:\nTSDS explains PEIMS submission guidance and deadlines."

        nova_core.tool_web_research = fake_research
        nova_core.tool_web_gather = fake_gather

        out = nova_http.process_chat("s6", "What are the attendance reporting rules for PEIMS?")
        self.assertIn("[source: tea.texas.gov]", out)
        self.assertIn("attendance data is required", out.lower())

    def test_session_recap_returns_recent_topics(self):
        nova_core.remember_name_origin = lambda _text: "Stored"
        nova_core.get_name_origin_story = lambda: ""

        nova_http.process_chat("s7", "What are the attendance reporting rules for PEIMS?")
        nova_http.process_chat("s7", "can you do a deep search and let me know what else you dig up?")
        out = nova_http.process_chat("s7", "give me a recap of this entire chat session nova")

        self.assertIn("recap of this session", out.lower())
        self.assertIn("attendance reporting rules", out.lower())
        self.assertIn("deep search", out.lower())

    def test_peims_local_fallback_when_web_research_returns_no_urls(self):
        nova_core.remember_name_origin = lambda _text: "Stored"
        nova_core.get_name_origin_story = lambda: ""
        nova_core.tool_web_research = lambda _q: "No relevant pages found across allowlisted domains for that query."
        nova_core.tool_web_gather = lambda _u: ""

        out = nova_http.process_chat("s8", "What are the attendance reporting rules for PEIMS?")
        self.assertIn("don't have bundled peims guidance", out.lower())
        self.assertIn("web research peims attendance reporting rules", out.lower())

    def test_llm_path_always_includes_recent_chat_context(self):
        nova_core.remember_name_origin = lambda _text: "Stored"
        nova_core.get_name_origin_story = lambda: ""
        nova_core._render_chat_context = lambda turns: "\n".join([f"{r}:{t}" for r, t in turns[-4:]])

        captured = {"retrieved": ""}

        def fake_ollama(text: str, retrieved_context: str = "", **_kwargs) -> str:
            captured["retrieved"] = retrieved_context
            return "ok"

        nova_core.ollama_chat = fake_ollama

        nova_http.process_chat("s9", "Explain photosynthesis briefly.")
        nova_http.process_chat("s9", "why?")

        self.assertIn("CURRENT CHAT CONTEXT", captured["retrieved"])
        self.assertIn("Explain photosynthesis briefly.", captured["retrieved"])

    def test_llm_path_includes_session_fact_sheet(self):
        nova_core.remember_name_origin = lambda _text: "Stored"
        nova_core.get_name_origin_story = lambda: "Nova was named by Gus."
        captured = {"retrieved": ""}

        def fake_ollama(text: str, retrieved_context: str = "", **_kwargs) -> str:
            captured["retrieved"] = retrieved_context
            return "ok"

        nova_core.ollama_chat = fake_ollama

        nova_http.process_chat("s9_fact_sheet", "I need help deciding.")

        self.assertIn("SESSION FACT SHEET", captured["retrieved"])
        self.assertIn("Assistant name:", captured["retrieved"])
        self.assertIn("Developer nickname:", captured["retrieved"])

    def test_http_llm_path_uses_shared_fallback_context_builder(self):
        captured = {"retrieved": ""}

        nova_core.build_fallback_context_details = lambda query, turns=None: {
            "context": "LEARNING\n\nCURRENT CHAT CONTEXT:\nUser: hello\n\nSESSION FACT SHEET:\nAssistant name: Nova",
            "learning_context": "LEARNING",
            "chat_context": "User: hello",
            "session_fact_sheet": "Assistant name: Nova",
            "memory_used": False,
            "knowledge_used": False,
            "memory_chars": 0,
            "knowledge_chars": 0,
        }

        def fake_ollama(text: str, retrieved_context: str = "", **_kwargs) -> str:
            captured["retrieved"] = retrieved_context
            return "ok"

        nova_core.ollama_chat = fake_ollama

        nova_http.process_chat("shared_builder_http", "I need help deciding.")

        self.assertEqual(
            captured["retrieved"],
            "LEARNING\n\nCURRENT CHAT CONTEXT:\nUser: hello\n\nSESSION FACT SHEET:\nAssistant name: Nova",
        )

    def test_http_llm_path_records_policy_gate_allowed_before_fallback(self):
        nova_core.ollama_chat = lambda _text, retrieved_context="", **_kwargs: "ok"

        nova_http.process_chat("policy_gate_http", "I need help deciding.")

        payload = self._latest_action_payload()
        self.assertIn("policy_gate:allowed", str(payload.get("route_summary") or ""))

    def test_peims_weak_web_snippet_falls_back_to_local_citations(self):
        nova_core.remember_name_origin = lambda _text: "Stored"
        nova_core.get_name_origin_story = lambda: ""
        nova_core.tool_web_research = lambda _q: "Web research:\nhttps://tea.texas.gov/"
        nova_core.tool_web_gather = lambda _u: "[OK] Saved ...\nSummary snippet:\nWelcome to Texas Education Agency | Texas Education Agency Skip to main content Mega Menu"

        out = nova_http.process_chat("s10", "What are the attendance reporting rules for PEIMS?")
        self.assertIn("don't have bundled peims guidance", out.lower())
        self.assertIn("web research peims attendance reporting rules", out.lower())

    def test_http_session_web_override_sticks_for_followup_peims_query(self):
        nova_core.remember_name_origin = lambda _text: "Stored"
        nova_core.get_name_origin_story = lambda: ""
        orig_execute_planned_action = nova_core.execute_planned_action
        try:
            nova_core.execute_planned_action = lambda tool, args=None: "Web research summary" if tool == "web_research" else ""
            ack = nova_http.process_chat("s10_override", "all you need is the Web")
            out = nova_http.process_chat("s10_override", "give me anything about PEIMS")
            self.assertIn("prefer web research", ack.lower())
            self.assertEqual(out, "Web research summary")
        finally:
            nova_core.execute_planned_action = orig_execute_planned_action

    def test_http_broad_peims_query_no_longer_uses_local_overview(self):
        nova_core.remember_name_origin = lambda _text: "Stored"
        nova_core.get_name_origin_story = lambda: ""

        out = nova_http.process_chat("s10_overview", "what do you know about PEIMS?")
        self.assertNotIn("peims overview details in local knowledge files", out.lower())
        self.assertNotIn("[source: knowledge/peims/", out.lower())

    def test_http_creator_followup_uses_session_conversation_state(self):
        nova_core.remember_name_origin = lambda _text: "Stored"
        nova_core.get_name_origin_story = lambda: "Nova was given its name by Gus."

        first = nova_http.process_chat("s10_profile", "who is your creator ?")
        followup = nova_http.process_chat("s10_profile", "what else?")

        self.assertIn("gustavo", first.lower())
        self.assertIn("verified facts", followup.lower())
        self.assertIn("gustavo", followup.lower())

    def test_http_retrieval_followup_uses_session_conversation_state(self):
        nova_core.remember_name_origin = lambda _text: "Stored"
        nova_core.get_name_origin_story = lambda: ""
        orig_execute_planned_action = nova_core.execute_planned_action
        orig_tool_web_gather = nova_core.tool_web_gather
        try:
            nova_core.execute_planned_action = lambda tool, args=None: "1) https://tea.texas.gov/a\n2) https://tea.texas.gov/b" if tool == "web_research" else ""
            nova_core.tool_web_gather = lambda url: f"Gathered: {url}"

            first = nova_http.process_chat("s10_retrieval", "research PEIMS online")
            followup = nova_http.process_chat("s10_retrieval", "tell me about the first one")
            session = nova_http.SESSION_STATE_MANAGER.get("s10_retrieval")

            self.assertIn("https://tea.texas.gov/a", first.lower())
            self.assertEqual(followup, "Gathered: https://tea.texas.gov/a")
            self.assertEqual(session.active_subject(), "retrieval:web_gather")
            self.assertEqual((session.retrieval_state() or {}).get("top_url"), "https://tea.texas.gov/a")
        finally:
            nova_core.execute_planned_action = orig_execute_planned_action
            nova_core.tool_web_gather = orig_tool_web_gather

    def test_http_creator_query_after_retrieval_resets_followup_to_creator_thread(self):
        nova_core.remember_name_origin = lambda _text: "Stored"
        nova_core.get_name_origin_story = lambda: "Nova was given its name by Gus."
        orig_execute_planned_action = nova_core.execute_planned_action
        try:
            nova_core.execute_planned_action = lambda tool, args=None: "1) https://tea.texas.gov/a\n2) https://tea.texas.gov/b" if tool == "web_research" else ""

            nova_http.process_chat("s10_mix", "research PEIMS online")
            nova_http.process_chat("s10_mix", "tell me about the first one")
            creator = nova_http.process_chat("s10_mix", "who is your creator?")
            followup = nova_http.process_chat("s10_mix", "what else?")
            session = nova_http.SESSION_STATE_MANAGER.get("s10_mix")

            self.assertIn("gustavo", creator.lower())
            self.assertIn("verified facts", followup.lower())
            self.assertIn("gustavo", followup.lower())
            self.assertEqual(session.active_subject(), "identity_profile:developer")
        finally:
            nova_core.execute_planned_action = orig_execute_planned_action

    def test_javascript_placeholder_snippet_is_rejected_as_grounding(self):
        nova_core.remember_name_origin = lambda _text: "Stored"
        nova_core.get_name_origin_story = lambda: ""
        nova_core.tool_web_research = lambda _q: "Web research:\nhttps://tea.texas.gov/"
        nova_core.tool_web_gather = lambda _u: "[OK] Saved ...\nSummary snippet:\nYou need to enable JavaScript to run this app."

        out = nova_http.process_chat("s10b", "What are the attendance reporting rules for PEIMS?")
        self.assertIn("don't have bundled peims guidance", out.lower())
        self.assertNotIn("enable javascript", out.lower())

    def test_name_origin_ignores_polluted_memory_lines(self):
        nova_core.get_name_origin_story = self.orig_get_name_origin_story
        nova_core.mem_recall = lambda _q: "- name: gus\n- my name is gus"

        out = nova_http.process_chat("s11", "why are you called Nova?")
        self.assertIn("do not have a saved name-origin story", out.lower())
        self.assertNotIn("my name is gus", out.lower())

    def test_assistant_name_correction_is_deterministic(self):
        nova_core.remember_name_origin = lambda _text: "Stored"
        nova_core.get_name_origin_story = lambda: ""

        ack = nova_http.process_chat("s12", "no he does not your developer's name is gus .. your name is Nova")
        self.assertIn("i learned", ack.lower())
        out = nova_http.process_chat("s12", "what is your name?")
        self.assertIn("my name is nova", out.lower())

    def test_developer_full_name_query(self):
        nova_core.remember_name_origin = lambda _text: "Stored"
        nova_core.get_name_origin_story = lambda: ""

        out = nova_http.process_chat("s13", "and that is just his nick name what is his full name ?")
        self.assertIn("full name is gustavo", out.lower())

    def test_creator_query_uses_deterministic_developer_profile(self):
        nova_core.remember_name_origin = lambda _text: "Stored"
        nova_core.get_name_origin_story = lambda: ""

        out = nova_http.process_chat("s13b", "who is your creator ?")
        self.assertIn("gustavo", out.lower())
        self.assertIn("created me", out.lower())

    def test_creator_confirmation_query_stays_deterministic(self):
        nova_core.remember_name_origin = lambda _text: "Stored"
        nova_core.get_name_origin_story = lambda: ""

        out = nova_http.process_chat("s13c", "so gus is your creator ?")
        self.assertIn("gustavo", out.lower())
        self.assertIn("created me", out.lower())

    def test_assistant_name_typo_confirmation(self):
        nova_core.remember_name_origin = lambda _text: "Stored"
        nova_core.get_name_origin_story = lambda: ""

        out = nova_http.process_chat("s14", "are hou sure that is your name ?")
        self.assertIn("my name is nova", out.lower())

    def test_clarification_prompt_does_not_trigger_web_lookup(self):
        nova_core.remember_name_origin = lambda _text: "Stored"
        nova_core.get_name_origin_story = lambda: ""
        nova_core.tool_web_research = lambda _q: "Web research:\nhttps://tea.texas.gov/"
        nova_core.tool_web_gather = lambda _u: "[OK] Saved ...\nSummary snippet:\nYou need to enable JavaScript to run this app."

        first = nova_http.process_chat("s14b", "who is your creator ?")
        self.assertIn("gustavo", first.lower())

        out = nova_http.process_chat("s14b", "what are you talking about ?")
        self.assertNotIn("allowlisted references", out.lower())
        self.assertNotIn("enable javascript", out.lower())
        self.assertIn("web lookup", out.lower())
        session = nova_http.SESSION_STATE_MANAGER.get("s14b")
        self.assertEqual((session.last_reflection or {}).get("reply_contract"), "open_probe.clarification")
        self.assertEqual((session.last_reflection or {}).get("reply_outcome_kind"), "clarification")

    def test_learning_updates_assistant_name(self):
        nova_core.remember_name_origin = lambda _text: "Stored"
        nova_core.get_name_origin_story = lambda: ""

        ack = nova_http.process_chat("s15", "your name is NovaPrime")
        self.assertIn("i learned", ack.lower())

        out = nova_http.process_chat("s15", "what is your name?")
        self.assertIn("novaprime", out.lower())

    def test_learning_updates_developer_full_name(self):
        nova_core.remember_name_origin = lambda _text: "Stored"
        nova_core.get_name_origin_story = lambda: ""

        ack = nova_http.process_chat("s16", "his full name is Gustavo Uribe")
        self.assertIn("i learned", ack.lower())

        out = nova_http.process_chat("s16", "what is his full name?")
        self.assertIn("gustavo uribe", out.lower())

    def test_http_pending_correction_flow(self):
        nova_core.remember_name_origin = lambda _text: "Stored"
        nova_core.get_name_origin_story = lambda: ""

        # Seed a prior assistant answer to be corrected.
        nova_http._append_session_turn("s17", "assistant", "Old incorrect answer")
        out1 = nova_http.process_chat("s17", "you gave me garbage back .. why ?")
        self.assertIn("exact corrected answer", out1.lower())
        self.assertEqual(nova_http.SESSION_STATE_MANAGER.get("s17").pending_correction_target, "Old incorrect answer")

        out2 = nova_http.process_chat("s17", "My name is Nova. Please use Nova going forward.")
        self.assertIn("corrected that", out2.lower())
        self.assertEqual(nova_http.SESSION_STATE_MANAGER.get("s17").pending_correction_target, "")

    def test_http_writes_action_ledger_record(self):
        nova_core.remember_name_origin = lambda _text: "Stored"
        nova_core.get_name_origin_story = lambda: ""
        out = nova_http.process_chat("ledger1", "random question for ledger")
        self.assertIn("i don't know that based on what i can verify", out.lower())

        files = sorted(nova_core.ACTION_LEDGER_DIR.glob("*.json"))
        self.assertTrue(files)
        payload = json.loads(files[-1].read_text(encoding="utf-8"))
        self.assertEqual(payload.get("user_input"), "random question for ledger")
        self.assertEqual(payload.get("reply_contract"), "open_probe.safe_fallback")
        self.assertEqual((payload.get("reply_outcome") or {}).get("kind"), "safe_fallback")
        self.assertEqual(((payload.get("routing_decision") or {}).get("final_owner")), "supervisor_handle")
        self.assertIn("planner_decision", payload)
        self.assertIn("final_answer", payload)
        self.assertIn("grounded", payload)
        self.assertIn("route_trace", payload)
        self.assertTrue(isinstance(payload.get("route_trace"), list))
        self.assertTrue(payload.get("route_summary"))
        session = nova_http.SESSION_STATE_MANAGER.get("ledger1")
        self.assertEqual(session.last_reflection.get("probe_summary"), "All green")
        self.assertEqual(session.last_reflection.get("probe_results"), [])
        self.assertEqual((session.last_reflection or {}).get("reply_contract"), "open_probe.safe_fallback")
        self.assertEqual((session.last_reflection or {}).get("reply_outcome_kind"), "safe_fallback")

    def test_http_claim_gate_block_records_truthful_limit_contract(self):
        nova_core.ollama_chat = lambda _text, retrieved_context="", **_kwargs: "I can smell coffee in the room with Gus."

        with mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
            out = nova_http.process_chat("ledger_truthful_limit", "what is gus doing right now?")

        self.assertIn("don't know", out.lower())
        self.assertIn("correct me", out.lower())
        self.assertNotIn("Turn bypassed supervisor intent phase", stdout.getvalue())
        payload = self._latest_action_payload()
        self.assertEqual(payload.get("planner_decision"), "llm_fallback")
        self.assertEqual(payload.get("reply_contract"), "turn.truthful_limit")
        self.assertEqual((payload.get("reply_outcome") or {}).get("kind"), "cannot_verify")
        self.assertFalse(bool(payload.get("grounded")))
        session = nova_http.SESSION_STATE_MANAGER.get("ledger_truthful_limit")
        self.assertEqual((session.last_reflection or {}).get("reply_contract"), "turn.truthful_limit")
        self.assertEqual((session.last_reflection or {}).get("reply_outcome_kind"), "cannot_verify")

    def test_http_llm_fallback_does_not_append_learning_invitation(self):
        nova_core.ollama_chat = lambda _text, retrieved_context="", **_kwargs: "Here is a broad answer without grounded evidence."

        with mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
            out = nova_http.process_chat("llm_guess", "tell me something reflective about ambition")

        self.assertIn("Here is a broad answer without grounded evidence.", out)
        self.assertNotIn("best guess from general knowledge and memory", out)
        self.assertNotIn("correct me", out)
        self.assertNotIn("[INFO] Open fallback - learning invitation active", stdout.getvalue())
        self.assertNotIn("[WARN] Turn bypassed supervisor intent phase", stdout.getvalue())
        payload = self._latest_action_payload()
        self.assertEqual(payload.get("planner_decision"), "llm_fallback")
        self.assertFalse(payload.get("reply_contract"))

    def test_http_repeated_weak_pressure_turns_use_deterministic_shared_paths(self):
        out1 = nova_http.process_chat("weak-pressure-http", "can you help me a little here ?")
        out2 = nova_http.process_chat("weak-pressure-http", "what do you think then ?")

        self.assertEqual(out1, "What kind of help do you want?")
        self.assertEqual(out2, "I don't have enough context to answer that yet. Tell me the topic or decision you want help with, and I'll stay on it.")

        payload = self._latest_action_payload()
        self.assertEqual(payload.get("reply_contract"), "open_probe.safe_fallback")
        self.assertEqual((payload.get("reply_outcome") or {}).get("kind"), "safe_fallback")

    def test_http_smalltalk_checkin_uses_shared_smalltalk_reply(self):
        out = nova_http.process_chat("smalltalk-http", "how are you doing today ?")
        self.assertEqual(out, "Hey. I'm doing good today. What's going on?")

    def test_http_store_fact_colon_form_routes_and_stores(self):
        writes = []
        nova_core.mem_enabled = lambda: True
        nova_core.mem_add = lambda kind, source, text: writes.append((kind, source, text))

        out = nova_http.process_chat("store_fact_colon", "Remember this: my favorite color is teal. Don't forget.")

        self.assertEqual(out, "Learned: my favorite color is teal. Don't forget")
        self.assertIn(("user_fact", "typed", "my favorite color is teal. Don't forget"), writes)
        payload = self._latest_action_payload()
        self.assertEqual(payload.get("planner_decision"), "deterministic")
        self.assertEqual(payload.get("intent"), "store_fact")
        self.assertEqual(payload.get("reply_contract"), "store_fact.explicit_store")
        self.assertEqual((payload.get("reply_outcome") or {}).get("fact_text"), "my favorite color is teal. Don't forget")
        session = nova_http.SESSION_STATE_MANAGER.get("store_fact_colon")
        self.assertEqual((session.last_reflection or {}).get("reply_contract"), "store_fact.explicit_store")
        self.assertEqual((session.last_reflection or {}).get("reply_outcome_kind"), "explicit_store")

    def test_delete_session_writes_session_end_health_snapshot(self):
        nova_core.ollama_chat = lambda _text, retrieved_context="", **_kwargs: "Simple answer"
        nova_http.process_chat("ledger_delete", "random question for ledger")

        ok, msg = nova_http._delete_session("ledger_delete")

        self.assertTrue(ok)
        self.assertEqual(msg, "session_deleted")
        rows = [json.loads(line) for line in nova_core.HEALTH_LOG.read_text(encoding="utf-8").splitlines() if line.strip()]
        self.assertEqual(rows[-1].get("session_id"), "ledger_delete")
        self.assertTrue(bool(rows[-1].get("session_end")))

    def test_http_action_ledger_records_planner_owned_command_route(self):
        nova_core._render_chat_context = lambda turns: "User: hello there"
        nova_http.process_chat("ledger_cmd", "hello there")
        out = nova_http.process_chat("ledger_cmd", "chat context")
        self.assertIn("Current chat context", out)

        payload = self._latest_action_payload()
        self.assertEqual(payload.get("user_input"), "chat context")
        self.assertEqual(payload.get("planner_decision"), "command")
        self.assertIn("action_planner:route_command", payload.get("route_summary", ""))
        self.assertIn("command:matched", payload.get("route_summary", ""))

    def test_http_action_ledger_records_planner_owned_keyword_route(self):
        orig_handle_keywords = nova_core.handle_keywords
        try:
            nova_core.handle_keywords = lambda _text: ("tool", "web_research", "continued web research")
            out = nova_http.process_chat("ledger_kw", "web continue")
            self.assertIn("continued web research", out)
        finally:
            nova_core.handle_keywords = orig_handle_keywords

        payload = self._latest_action_payload()
        self.assertEqual(payload.get("user_input"), "web continue")
        self.assertEqual(payload.get("planner_decision"), "run_tool")
        self.assertEqual(payload.get("tool"), "web_research")
        self.assertIn("action_planner:route_keyword", payload.get("route_summary", ""))
        self.assertIn("keyword_tool:matched", payload.get("route_summary", ""))

    def test_http_queue_status_runs_direct_tool_and_records_ledger(self):
        queue_text = "Standing work queue:\n- open: 2 of 4\nNext item: next_generated.json"
        with mock.patch.object(nova_core, "tool_queue_status", return_value=queue_text):
            out = nova_http.process_chat("ledger_queue_http", "what should you work on next")

        self.assertIn("Standing work queue", out)
        payload = self._latest_action_payload()
        self.assertEqual(payload.get("planner_decision"), "run_tool")
        self.assertEqual(payload.get("tool"), "queue_status")
        self.assertIn("action_planner:run_tool", payload.get("route_summary", ""))
        self.assertIn("tool_execution:ok", payload.get("route_summary", ""))

    def test_http_queue_status_followup_uses_structured_tool_state(self):
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

        with mock.patch("nova_http._generated_work_queue", return_value=queue_payload):
            first = nova_http.process_chat("queue_followup_http", "what should you work on next")
            second = nova_http.process_chat("queue_followup_http", "why is that the next item in the queue?")

        self.assertIn("next_generated.json", first)
        self.assertIn("next_generated.json is next because it is still open", second)
        self.assertIn("fallback_overuse", second)

        payload = self._latest_action_payload()
        self.assertEqual(payload.get("planner_decision"), "conversation_followup")
        self.assertNotIn("llm_fallback", payload.get("route_summary", ""))

    def test_http_queue_status_report_and_seam_followups_use_structured_state(self):
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

        with mock.patch("nova_http._generated_work_queue", return_value=queue_payload):
            nova_http.process_chat("queue_followup_http_detail", "what should you work on next")
            seam = nova_http.process_chat("queue_followup_http_detail", "what seam is it failing on?")
            report = nova_http.process_chat("queue_followup_http_detail", "show me the report path")

        self.assertIn("demo_seam", seam)
        self.assertIn("fallback_overuse", seam)
        self.assertIn("C:/Nova/runtime/test_sessions/next_generated/result.json", report)

        payload = self._latest_action_payload()
        self.assertEqual(payload.get("planner_decision"), "conversation_followup")
        self.assertNotIn("llm_fallback", payload.get("route_summary", ""))

    def test_http_action_ledger_records_planner_owned_respond_route(self):
        out = nova_http.process_chat("ledger_rsp", "can you debug this bug in my code")
        self.assertIn("file path", out.lower())

        payload = self._latest_action_payload()
        self.assertEqual(payload.get("user_input"), "can you debug this bug in my code")
        self.assertEqual(payload.get("planner_decision"), "respond")
        self.assertIn("action_planner:respond", payload.get("route_summary", ""))

    def test_http_capability_self_correction(self):
        nova_core.remember_name_origin = lambda _text: "Stored"
        nova_core.get_name_origin_story = lambda: ""
        nova_core.ollama_chat = lambda _text, retrieved_context="", **_kwargs: "I can autonomously enhance myself and self-sustain."

        out = nova_http.process_chat("ledger2", "what are your abilities?")
        self.assertIn("Current capabilities:", out)
        self.assertIn("web_access", out)

    def test_http_what_do_you_do_routes_to_capabilities_not_local_knowledge(self):
        nova_core.remember_name_origin = lambda _text: "Stored"
        nova_core.get_name_origin_story = lambda: ""

        out = nova_http.process_chat("ledger2b", "what do you do nova ?")
        self.assertIn("Current capabilities:", out)
        self.assertIn("web_access", out)
        self.assertNotIn("local knowledge files", out.lower())

    def test_http_developer_location_pronoun_followup_avoids_grounded_lookup(self):
        nova_core.remember_name_origin = lambda _text: "Stored"
        nova_core.get_name_origin_story = lambda: ""

        nova_http.process_chat("ledger2c", "what do you know about gus?")
        out = nova_http.process_chat("ledger2c", "do you know his current location?")

        self.assertIn("uncertain about gus's current location", out.lower())
        self.assertNotIn("local knowledge files", out.lower())

    def test_http_self_location_query_stays_deterministic_after_peims_turn(self):
        nova_core.set_location_text("Brownsville, Texas")

        nova_http.process_chat("location_http_1", "what do you know about PEIMS?")
        out = nova_http.process_chat("location_http_1", "What is your current physical location nova?")

        self.assertIn("my location is brownsville, texas", out.lower())
        self.assertNotIn("local knowledge files", out.lower())

    def test_http_learns_developer_location_relation_and_reuses_saved_location(self):
        nova_core.set_location_text("Brownsville, Texas")

        ack = nova_http.process_chat("location_http_2", "well gus' locatio is the same as yours..")
        out = nova_http.process_chat("location_http_2", "what is his location ?")

        self.assertIn("i learned", ack.lower())
        self.assertIn("brownsville, texas", out.lower())

    def test_http_reflective_followup_uses_learned_developer_location_relation(self):
        nova_core.set_location_text("Brownsville, Texas")

        nova_http.process_chat("location_http_3", "who is your creator?")
        nova_http.process_chat("location_http_3", "gus' locatio is the same as yours")
        out = nova_http.process_chat("location_http_3", "if you think for a bit.. you now know gus' locaiton do you not?")

        self.assertIn("brownsville, texas", out.lower())

    def test_http_policy_domain_query_uses_truth_hierarchy(self):
        orig_policy_web = nova_core.policy_web
        try:
            nova_core.policy_web = lambda: {"enabled": True, "allow_domains": ["tea.texas.gov"]}
            out = nova_http.process_chat("ledger3", "what domain access do you have?")
            self.assertIn("Policy web access enabled", out)
            self.assertIn("tea.texas.gov", out)
        finally:
            nova_core.policy_web = orig_policy_web


if __name__ == "__main__":
    unittest.main()
