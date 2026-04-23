import unittest

from services import nova_retrieval_followups


class TestNovaRetrievalFollowupsService(unittest.TestCase):
    def test_meta_question_returns_meta_summary_contract(self):
        reply, state, outcome = nova_retrieval_followups.execute_retrieval_followup_outcome(
            {"query": "Gus Wenner", "result_count": 2, "urls": ["https://example.com/1"]},
            "what did you find?",
            extract_retrieval_result_index_fn=lambda text: None,
            is_retrieval_meta_question_fn=lambda text: True,
            retrieval_meta_reply_fn=lambda state: "I found 2 sources.",
            tool_web_gather_fn=lambda url: "",
            make_retrieval_conversation_state_fn=lambda tool, query, result: state,
            looks_like_retrieval_followup_fn=lambda text: False,
            tool_web_research_continue_fn=lambda: "",
            web_research_query_fn=lambda: "",
            web_research_result_count_fn=lambda: 0,
            web_research_has_results_fn=lambda: False,
            render_reply_fn=lambda outcome: str(outcome.get("reply_text") or ""),
        )
        self.assertEqual(reply, "I found 2 sources.")
        self.assertEqual(state.get("query"), "Gus Wenner")
        self.assertEqual(outcome.get("reply_contract"), "retrieval_followup.meta_summary")

    def test_selected_result_gathers_url_and_updates_state(self):
        reply, state, outcome = nova_retrieval_followups.execute_retrieval_followup_outcome(
            {"query": "Gus Wenner", "result_count": 2, "urls": ["https://example.com/1", "https://example.com/2"]},
            "show me the second one",
            extract_retrieval_result_index_fn=lambda text: 2,
            is_retrieval_meta_question_fn=lambda text: False,
            retrieval_meta_reply_fn=lambda state: "",
            tool_web_gather_fn=lambda url: f"Gathered {url}",
            make_retrieval_conversation_state_fn=lambda tool, query, result: {"kind": "retrieval", "query": query, "result": result},
            looks_like_retrieval_followup_fn=lambda text: False,
            tool_web_research_continue_fn=lambda: "",
            web_research_query_fn=lambda: "",
            web_research_result_count_fn=lambda: 0,
            web_research_has_results_fn=lambda: False,
            render_reply_fn=lambda outcome: str(outcome.get("reply_text") or ""),
        )
        self.assertIn("https://example.com/2", reply)
        self.assertEqual(state.get("kind"), "retrieval")
        self.assertEqual(outcome.get("reply_contract"), "retrieval_followup.selected_result")

    def test_guidance_path_returns_guidance_contract(self):
        reply, state, outcome = nova_retrieval_followups.execute_retrieval_followup_outcome(
            {"query": "Gus Wenner", "result_count": 1, "urls": ["https://example.com/1"]},
            "go on",
            extract_retrieval_result_index_fn=lambda text: None,
            is_retrieval_meta_question_fn=lambda text: False,
            retrieval_meta_reply_fn=lambda state: "",
            tool_web_gather_fn=lambda url: "",
            make_retrieval_conversation_state_fn=lambda tool, query, result: None,
            looks_like_retrieval_followup_fn=lambda text: False,
            tool_web_research_continue_fn=lambda: "",
            web_research_query_fn=lambda: "",
            web_research_result_count_fn=lambda: 0,
            web_research_has_results_fn=lambda: False,
            render_reply_fn=lambda outcome: str(outcome.get("reply_text") or ""),
        )
        self.assertIn("Continuing from your last retrieval", reply)
        self.assertEqual(state.get("query"), "Gus Wenner")
        self.assertEqual(outcome.get("reply_contract"), "retrieval_followup.guidance")
