import unittest

from services.nova_tool_policy import web_allowlist_message


class TestNovaToolPolicyService(unittest.TestCase):
    def test_web_allowlist_message_reports_policy_boundary_not_backend_failure(self):
        message = web_allowlist_message(
            "nova runtime search dependency probe",
            policy_web_fn=lambda: {"allow_domains": ["wikipedia.org", "127.0.0.1"]},
        )

        self.assertIn("Web access for nova runtime search dependency probe is limited", message)
        self.assertIn("wikipedia.org", message)
        self.assertIn("127.0.0.1", message)
        self.assertNotIn("cannot access the web", message.lower())

    def test_web_allowlist_message_reports_empty_allowlist_without_dependency_failure(self):
        message = web_allowlist_message(policy_web_fn=lambda: {"allow_domains": []})

        self.assertEqual(message, "Web policy has no allowlisted domains configured.")
        self.assertNotIn("cannot access the web", message.lower())


if __name__ == "__main__":
    unittest.main()
