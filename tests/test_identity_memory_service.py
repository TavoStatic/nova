"""
Tests for the IdentityMemoryService.

These tests validate identity memory text rules only. Chat routing/tool behavior
must not be managed by trigger phrases in this service.
"""

import unittest
from services.identity_memory import IdentityMemoryService


class TestIdentityMemoryService(unittest.TestCase):
    """Test IdentityMemoryService methods."""

    def setUp(self):
        """Create a fresh service instance for each test."""
        self.service = IdentityMemoryService()

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


if __name__ == "__main__":
    unittest.main()
