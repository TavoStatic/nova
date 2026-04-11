import unittest

from services.memory_adapter import MemoryAdapterService


class TestMemoryAdapterService(unittest.TestCase):
    def _service(self, policy: dict, user: str | None = None) -> MemoryAdapterService:
        return MemoryAdapterService(
            policy_memory_getter=lambda: dict(policy),
            active_user_getter=lambda: user,
        )

    def test_scope_validation(self):
        svc = self._service({"scope": "hybrid"})
        self.assertEqual(svc.mem_scope(), "hybrid")
        svc_bad = self._service({"scope": "weird"})
        self.assertEqual(svc_bad.mem_scope(), "private")

    def test_context_top_k_clamped(self):
        svc = self._service({"context_top_k": 99})
        self.assertEqual(svc.mem_context_top_k(), 10)

    def test_memory_should_keep_text_question_rejected(self):
        svc = self._service({"store_min_chars": 2})
        keep, reason = svc.memory_should_keep_text("what is this?")
        self.assertFalse(keep)
        self.assertEqual(reason, "question")

    def test_memory_should_keep_text_policy_include(self):
        svc = self._service({"store_include_patterns": ["always keep me"], "store_min_chars": 2})
        keep, reason = svc.memory_should_keep_text("please always keep me in memory")
        self.assertTrue(keep)
        self.assertEqual(reason, "policy_include")

    def test_memory_should_keep_text_durable_marker(self):
        svc = self._service({"store_min_chars": 2})
        keep, reason = svc.memory_should_keep_text("my favorite color is teal")
        self.assertTrue(keep)
        self.assertEqual(reason, "durable_fact")

    def test_format_memory_recall_hits_dedup(self):
        svc = self._service({"context_top_k": 3})
        hits = [
            (0.9, 1, "fact", "x", "u", "Favorite color is teal"),
            (0.8, 2, "fact", "x", "u", "Favorite color is teal."),
            (0.7, 3, "fact", "x", "u", "Lives in Brownsville"),
        ]
        out = svc.format_memory_recall_hits(hits)
        self.assertIn("Favorite color is teal", out)
        self.assertIn("Lives in Brownsville", out)


if __name__ == "__main__":
    unittest.main()
