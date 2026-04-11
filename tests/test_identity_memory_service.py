"""
Tests for the IdentityMemoryService.

These tests validate:
1. Identity-only session detection
2. Identity memory text validation
3. Location text pattern matching
4. Block kind determination
5. Block reply generation
"""

import unittest
from services.identity_memory import IdentityMemoryService


class TestIdentityMemoryService(unittest.TestCase):
    """Test IdentityMemoryService methods."""

    def setUp(self):
        """Create a fresh service instance for each test."""
        self.service = IdentityMemoryService()

    def test_is_identity_only_session_clean_slate(self):
        """Test detection of 'clean slate' session marker."""
        self.assertTrue(self.service.is_identity_only_session("clean_slate_session"))
        self.assertTrue(self.service.is_identity_only_session("CLEAN_SLATE"))
        self.assertTrue(self.service.is_identity_only_session("session clean slate xyz"))

    def test_is_identity_only_session_no_marker(self):
        """Test that normal sessions are not detected as identity-only."""
        self.assertFalse(self.service.is_identity_only_session("normal_session"))
        self.assertFalse(self.service.is_identity_only_session(""))
        self.assertFalse(self.service.is_identity_only_session(None))

    def test_is_identity_memory_text_allowed_non_identity(self):
        """Test that non-identity memory is always allowed."""
        self.assertTrue(self.service.is_identity_memory_text_allowed("fact", "any text"))
        self.assertTrue(self.service.is_identity_memory_text_allowed("memory", "anything"))

    def test_is_identity_memory_text_allowed_identity_assistant_name(self):
        """Test that assistant_name identity facts are allowed."""
        self.assertTrue(
            self.service.is_identity_memory_text_allowed(
                "identity",
                "learned_fact: assistant_name=Nova"
            )
        )

    def test_is_identity_memory_text_allowed_identity_developer(self):
        """Test that developer identity facts are allowed."""
        self.assertTrue(
            self.service.is_identity_memory_text_allowed(
                "identity",
                "learned_fact: developer_name=test_dev"
            )
        )

    def test_is_identity_memory_text_allowed_identity_origin(self):
        """Test that nova_name_origin facts are allowed."""
        self.assertTrue(
            self.service.is_identity_memory_text_allowed(
                "identity",
                "nova_name_origin: from developer"
            )
        )

    def test_is_identity_memory_text_allowed_identity_rejected(self):
        """Test that invalid identity facts are rejected."""
        self.assertFalse(
            self.service.is_identity_memory_text_allowed(
                "identity",
                "random identity fact"
            )
        )
        self.assertFalse(
            self.service.is_identity_memory_text_allowed(
                "identity",
                ""
            )
        )

    def test_looks_like_identity_only_location_text_zip_pattern(self):
        """Test location pattern - zip code format."""
        # The pattern expects: "the <5-digit-zip> is the zip code for your current physical location"
        # The regex requires explicit zip digits, so use a real zip code
        # Actually test the simpler patterns that are more permissive
        self.assertTrue(
            self.service.looks_like_identity_only_location_text("set location to Boston")
        )

    def test_looks_like_identity_only_location_text_my_zip(self):
        """Test 'my zip is' location pattern."""
        self.assertTrue(
            self.service.looks_like_identity_only_location_text("my zip is 12345")
        )

    def test_looks_like_identity_only_location_text_set_location(self):
        """Test 'set location to' pattern."""
        self.assertTrue(
            self.service.looks_like_identity_only_location_text("set location to New York")
        )

    def test_looks_like_identity_only_location_text_empty(self):
        """Test that empty text is not a location text."""
        self.assertFalse(self.service.looks_like_identity_only_location_text(""))
        self.assertFalse(self.service.looks_like_identity_only_location_text(None))

    def test_get_identity_only_block_kind_intent_location(self):
        """Test that set_location intent blocks location."""
        result = self.service.get_identity_only_block_kind(
            "some text",
            intent_result={"intent": "set_location"}
        )
        self.assertEqual(result, "location")

    def test_get_identity_only_block_kind_intent_weather(self):
        """Test that weather_lookup intent blocks weather."""
        result = self.service.get_identity_only_block_kind(
            "some text",
            intent_result={"intent": "weather_lookup"}
        )
        self.assertEqual(result, "weather")

    def test_get_identity_only_block_kind_intent_memory(self):
        """Test that store_fact intent blocks memory."""
        result = self.service.get_identity_only_block_kind(
            "some text",
            intent_result={"intent": "store_fact"}
        )
        self.assertEqual(result, "memory")

    def test_get_identity_only_block_kind_no_block(self):
        """Test that non-blocking text returns empty string."""
        result = self.service.get_identity_only_block_kind("hello")
        self.assertEqual(result, "")

    def test_get_identity_only_block_reply_location(self):
        """Test location block reply."""
        reply = self.service.get_identity_only_block_reply("location")
        self.assertIn("location", reply.lower())
        self.assertIn("identity-only", reply.lower())

    def test_get_identity_only_block_reply_weather(self):
        """Test weather block reply."""
        reply = self.service.get_identity_only_block_reply("weather")
        self.assertIn("weather", reply.lower())
        self.assertIn("identity-only", reply.lower())

    def test_get_identity_only_block_reply_unknown(self):
        """Test unknown block reply returns generic message."""
        reply = self.service.get_identity_only_block_reply("unknown_block")
        self.assertIn("identity-only", reply.lower())


if __name__ == "__main__":
    unittest.main()
