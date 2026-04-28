import unittest

from services.nova_query_classifiers import is_action_history_query
from services.nova_query_classifiers import is_assistant_name_query
from services.nova_query_classifiers import is_conversational_clarification
from services.nova_query_classifiers import is_developer_full_name_query
from services.nova_query_classifiers import is_identity_or_developer_query
from services.nova_query_classifiers import is_self_identity_web_challenge
from services.nova_query_classifiers import is_student_data_attendance_rules_query
from services.nova_query_classifiers import is_web_preferred_data_query


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

    def test_student_data_attendance_rules_query_requires_peims_and_attendance_rules(self):
        self.assertTrue(is_student_data_attendance_rules_query("Tell me the PEIMS attendance reporting rules"))
        self.assertFalse(is_student_data_attendance_rules_query("Tell me the PEIMS submission calendar"))

    def test_web_preferred_data_query_requires_data_terms_and_broad_cues(self):
        self.assertTrue(is_web_preferred_data_query("Explain PEIMS attendance reporting"))
        self.assertFalse(is_web_preferred_data_query("PEIMS attendance code 01"))

    def test_conversational_clarification_detects_probeback_phrasing(self):
        self.assertTrue(is_conversational_clarification("What are you talking about?"))
        self.assertFalse(is_conversational_clarification("Please explain PEIMS attendance rules."))


if __name__ == "__main__":
    unittest.main()
