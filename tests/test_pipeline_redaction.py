import unittest

from pipelines.redaction import apply_redaction_to_payload, redact_row, resolve_redaction_profile


class TestPipelineRedaction(unittest.TestCase):
    def test_sensitive_profile_redacts_personal_fields(self) -> None:
        redacted = redact_row(
            {"item_id": "123", "name": "Ada", "email": "ada@example.test", "status": "active"},
            "sensitive_default",
        )
        self.assertEqual(redacted["item_id"], "123")
        self.assertEqual(redacted["name"], "[REDACTED]")
        self.assertEqual(redacted["email"], "[REDACTED]")
        self.assertEqual(redacted["status"], "active")

    def test_metadata_only_clears_rows(self) -> None:
        result = apply_redaction_to_payload(
            {"ok": True, "pipeline_id": "example_connector", "rows": [{"item_id": "1"}], "row_count": 1},
            "metadata_only",
        )
        self.assertEqual(result["rows"], [])
        self.assertEqual(result["row_count"], 1)

    def test_backpack_resource_selects_sensitive_profile(self) -> None:
        profile = resolve_redaction_profile(resource="backpack/items", template_profile="none")
        self.assertEqual(profile, "sensitive_default")

        result = apply_redaction_to_payload(
            {"ok": True, "resource": "backpack/items", "items": [{"name": "Ada"}]},
            "none",
        )
        self.assertEqual(result["redaction_profile"], "sensitive_default")
        self.assertEqual(result["items"][0]["name"], "[REDACTED]")


if __name__ == "__main__":
    unittest.main()
