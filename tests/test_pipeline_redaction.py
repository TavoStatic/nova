import unittest

from pipelines.redaction import (
    apply_redaction_to_payload,
    redact_edfi_result,
    redact_row,
    resolve_redaction_profile,
)


class TestPipelineRedaction(unittest.TestCase):
    def test_student_default_redacts_sensitive_fields(self) -> None:
        row = {
            "studentUniqueId": "123",
            "firstName": "Ada",
            "birthDate": "2010-01-01",
            "addresses": [{"street": "1 Main"}],
        }
        redacted = redact_row(row, "student_default")
        self.assertEqual(redacted["studentUniqueId"], "123")
        self.assertEqual(redacted["firstName"], "[REDACTED]")
        self.assertEqual(redacted["birthDate"], "[REDACTED]")
        self.assertEqual(redacted["addresses"], "[REDACTED]")

    def test_apply_redaction_to_payload_marks_profile(self) -> None:
        payload = {
            "ok": True,
            "rows": [{"schoolId": 1, "website": "https://example.com"}],
            "row_count": 1,
        }
        result = apply_redaction_to_payload(payload, "education_org_default", resource="ed-fi/schools")
        self.assertTrue(result["redaction_applied"])
        self.assertEqual(result["redaction_profile"], "education_org_default")
        self.assertEqual(result["rows"][0]["website"], "[REDACTED]")

    def test_metadata_only_clears_rows(self) -> None:
        payload = {
            "ok": True,
            "pipeline_id": "edfi_bisd",
            "rows": [{"studentUniqueId": "1"}],
            "items": [{"studentUniqueId": "1"}],
            "row_count": 1,
        }
        result = apply_redaction_to_payload(payload, "metadata_only")
        self.assertEqual(result["rows"], [])
        self.assertEqual(result["items"], [])
        self.assertEqual(result["row_count"], 1)

    def test_resolve_redaction_profile_upgrades_student_changes_since(self) -> None:
        profile = resolve_redaction_profile(
            operation="changes_since",
            template_profile="education_org_default",
            resource="ed-fi/students",
        )
        self.assertEqual(profile, "student_default")

    def test_apply_redaction_to_payload_redacts_nested_edfi_items(self) -> None:
        payload = {
            "ok": False,
            "edfi": {
                "resource": "ed-fi/students",
                "items": [
                    {
                        "studentUniqueId": "S123",
                        "firstName": "Ada",
                        "birthDate": "2010-01-01",
                    }
                ],
            },
        }
        result = apply_redaction_to_payload(payload, "student_default")
        self.assertEqual(result["edfi"]["items"][0]["firstName"], "[REDACTED]")
        self.assertEqual(result["edfi"]["items"][0]["studentUniqueId"], "S123")

    def test_apply_redaction_upgrades_student_resource_profile(self) -> None:
        payload = {
            "ok": True,
            "resource": "ed-fi/students",
            "items": [{"studentUniqueId": "S123", "firstName": "Ada"}],
        }
        result = apply_redaction_to_payload(payload, "education_org_default", resource="ed-fi/students")
        self.assertEqual(result["redaction_profile"], "student_default")
        self.assertTrue(result["redaction_applied"])
        self.assertEqual(result["items"][0]["firstName"], "[REDACTED]")

    def test_student_profile_marks_student_resource_protected(self) -> None:
        payload = {
            "ok": True,
            "resource": "ed-fi/students",
            "items": [{"studentUniqueId": "S123", "firstName": "Ada"}],
        }
        result = apply_redaction_to_payload(payload, "student_default", resource="ed-fi/students")
        self.assertTrue(result["redaction_applied"])
        self.assertEqual(result["items"][0]["firstName"], "[REDACTED]")

    def test_redact_edfi_result_uses_resource_for_explore_reads(self) -> None:
        result = redact_edfi_result(
            {
                "ok": True,
                "resource": "ed-fi/students",
                "items": [
                    {
                        "studentUniqueId": "S123",
                        "firstName": "Ada",
                    }
                ],
            },
            operation="students",
        )
        self.assertEqual(result["redaction_profile"], "student_default")
        self.assertEqual(result["items"][0]["firstName"], "[REDACTED]")


if __name__ == "__main__":
    unittest.main()