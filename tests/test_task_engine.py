import unittest

import nova_core
import task_engine


class TestTaskEngine(unittest.TestCase):
    def test_peims_role_statement_does_not_require_database_capabilities(self):
        out = task_engine.analyze_request(
            "yes your correct nova he is a full stack developer that works as PEIMS Data Specialist"
        )
        self.assertTrue(out.allow_llm)
        self.assertIsNone(out.message)

    def test_explicit_web_research_peims_query_requires_web_not_database(self):
        req = task_engine.extract_requirements("research PEIMS online")
        self.assertIn("web_access", req)
        self.assertNotIn("database_connection", req)
        self.assertNotIn("query_execution", req)

    def test_session_web_override_skips_database_requirements(self):
        req = task_engine.extract_requirements(
            "give me anything about PEIMS",
            config={"prefer_web_for_data_queries": True},
        )
        self.assertIn("web_access", req)
        self.assertNotIn("database_connection", req)
        self.assertNotIn("query_execution", req)


class TestDeveloperFactLearning(unittest.TestCase):
    def test_contextual_developer_facts_store_work_role_with_peims_title(self):
        orig_mem_enabled = nova_core.mem_enabled
        orig_mem_add = nova_core.mem_add
        try:
            writes = []
            nova_core.mem_enabled = lambda: True
            nova_core.mem_add = lambda kind, source, text: writes.append((kind, source, text))

            learned, msg = nova_core._learn_contextual_developer_facts(
                [("user", "can you also guess what type of work does gus do..")],
                "yes your correct nova he is a full stack developer that works as PEIMS Data Specialist",
            )
            self.assertTrue(learned)
            self.assertIn("full stack developer", msg.lower())
            self.assertTrue(any("peims data specialist" in item[2].lower() for item in writes))
        finally:
            nova_core.mem_enabled = orig_mem_enabled
            nova_core.mem_add = orig_mem_add


if __name__ == "__main__":
    unittest.main()