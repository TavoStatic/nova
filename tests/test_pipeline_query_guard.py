import unittest

from pipelines.query_guard import PipelineQueryGuard
from pipelines.query_guard import QueryGuardError


class TestPipelineQueryGuard(unittest.TestCase):
    def setUp(self):
        self.guard = PipelineQueryGuard(max_rows_default=100)
        self.templates = {
            "student_lookup": {
                "params": ["student_id", "local_id", "campus_id"],
                "required_any": [["student_id"], ["local_id"]],
                "max_rows": 25,
            },
            "campus_summary": {
                "params": ["campus_id", "school_year"],
                "required_all": ["campus_id", "school_year"],
                "max_rows": 50,
            },
        }

    def test_rejects_unknown_operation(self):
        with self.assertRaises(QueryGuardError):
            self.guard.validate(self.templates, "missing_op")

    def test_requires_one_of_required_any_groups(self):
        with self.assertRaises(QueryGuardError):
            self.guard.validate(self.templates, "student_lookup", {"campus_id": "101"})

    def test_rejects_unexpected_parameter(self):
        with self.assertRaises(QueryGuardError):
            self.guard.validate(
                self.templates,
                "campus_summary",
                {"campus_id": "101", "school_year": "2025", "sql": "select *"},
            )

    def test_clamps_row_limit_to_template_cap(self):
        result = self.guard.validate(
            self.templates,
            "student_lookup",
            {"student_id": "12345"},
            row_limit=200,
        )
        self.assertEqual(result["requested_row_limit"], 200)
        self.assertEqual(result["effective_row_limit"], 25)
        self.assertTrue(result["row_limit_clamped"])


if __name__ == "__main__":
    unittest.main()
