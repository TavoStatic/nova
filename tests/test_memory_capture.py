import unittest
import uuid
from unittest import mock

import nova_core


class TestMemoryCapture(unittest.TestCase):
    def test_mem_add_and_recall(self):
        unique = f"unittest-memory-{uuid.uuid4().hex}"

        class _FakeMemory:
            def __init__(self):
                self.rows: list[tuple[str, str, str, str, str]] = []

            def recall_explain(self, *_args, **_kwargs):
                return {"results": []}

            def add_memory(self, kind, source, text, user="", scope="shared"):
                self.rows.append((kind, source, user, scope, text))

            def recall(self, query, **_kwargs):
                hits = []
                for _kind, source, user, _scope, text in self.rows:
                    if str(query).lower() in str(text).lower():
                        hits.append((0.95, 0, "test", source, user, text))
                return hits

        fake = _FakeMemory()
        original_user = nova_core.get_active_user()
        try:
            nova_core.set_active_user("ci-test-user")
            with mock.patch.object(nova_core, "memory_mod", fake):
                nova_core.mem_add("test", "unittest", unique)
                out = nova_core.mem_recall(unique)
        finally:
            nova_core.set_active_user(original_user)

        self.assertIsInstance(out, str)
        self.assertIn("unittest-memory", out)


if __name__ == "__main__":
    unittest.main()
