import unittest

from services.nova_query_classifiers import is_action_history_query
from services.nova_query_classifiers import is_assistant_name_query
from services.nova_query_classifiers import is_developer_full_name_query
from services.nova_query_classifiers import is_identity_or_developer_query
from services.nova_query_classifiers import is_self_identity_web_challenge


class TestNovaQueryClassifiers(unittest.TestCase):
    def test_identity_or_developer_query_normalizes_yor_typo(self):
        self.assertTrue(is_identity_or_developer_query("what is yor name"))

    def test_action_history_query_does_not_claim_findings_question(self):
        self.assertFalse(is_action_history_query("what did you find"))

    def test_assistant_name_query_detects_confidence_challenge(self):
        self.assertTrue(is_assistant_name_query("are you sure that is your name?"))

    def test_self_identity_web_challenge_requires_web_and_identity_cues(self):
        self.assertTrue(is_self_identity_web_challenge("why should i use the web for your name"))
        self.assertFalse(is_self_identity_web_challenge("why should i use the web for weather"))

    def test_developer_full_name_query_requires_developer_context(self):
        self.assertTrue(is_developer_full_name_query("do you know Gus's full name?"))
        self.assertFalse(is_developer_full_name_query("what is the full name of that file"))


if __name__ == "__main__":
    unittest.main()