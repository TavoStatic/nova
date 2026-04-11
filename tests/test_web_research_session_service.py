import unittest

from services.web_research_session import WebResearchSessionStore


class TestWebResearchSessionStore(unittest.TestCase):
    def test_set_results_and_paginate(self):
        store = WebResearchSessionStore()
        rows = [
            (9.1, "https://example.com/1", "one"),
            (8.3, "https://example.com/2", "two"),
            (7.7, "https://example.com/3", "three"),
        ]

        store.set_results("peims", rows)
        self.assertTrue(store.has_results())
        self.assertEqual(store.query, "peims")
        self.assertEqual(store.result_count(), 3)

        first = store.next_page(2)
        self.assertIsNotNone(first)
        self.assertEqual(first.start, 0)
        self.assertEqual(first.end, 2)
        self.assertEqual(len(first.rows), 2)
        self.assertEqual(store.remaining_count(), 1)

        second = store.next_page(2)
        self.assertIsNotNone(second)
        self.assertEqual(second.start, 2)
        self.assertEqual(second.end, 3)
        self.assertEqual(len(second.rows), 1)
        self.assertEqual(store.remaining_count(), 0)

    def test_next_page_empty_returns_none(self):
        store = WebResearchSessionStore()
        self.assertIsNone(store.next_page(5))


if __name__ == "__main__":
    unittest.main()
