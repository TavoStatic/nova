"""
Tests for the ToolRegistryService.

These tests validate:
1. Tool registry wrapping and delegation
2. Manifest loading and caching
3. Tool invocation event logging
4. Event serialization
"""

import json
import tempfile
import unittest
from pathlib import Path

from services.tool_registry import ToolRegistryService, ToolInvocationEvent
from tools import ToolRegistry, ToolContext


class MockTool:
    """Mock tool for testing."""
    name = "test_tool"
    
    def metadata(self):
        return {
            "name": self.name,
            "description": "Test tool",
            "safe": True,
            "requires_admin": False,
            "locality": "local",
            "mutating": False,
            "scope": "user",
        }
    
    def check_policy(self, args, context):
        return (True, "")
    
    def run(self, args, context):
        return "test_result"


class TestToolInvocationEvent(unittest.TestCase):
    """Test ToolInvocationEvent."""
    
    def test_event_to_dict_basic(self):
        """Test event serialization to dict."""
        event = ToolInvocationEvent(
            tool="test",
            user="user1",
            session="session1",
            status="ok",
            safe=True,
            ts=1000,
        )
        result = event.to_dict()
        
        self.assertEqual(result["tool"], "test")
        self.assertEqual(result["user"], "user1")
        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["safe"])
        self.assertEqual(result["ts"], 1000)
    
    def test_event_to_dict_with_reason(self):
        """Test event with denial reason."""
        event = ToolInvocationEvent(
            tool="test",
            status="denied",
            reason="policy_denied",
            ts=1000,
        )
        result = event.to_dict()
        
        self.assertEqual(result["status"], "denied")
        self.assertEqual(result["reason"], "policy_denied")
    
    def test_event_to_dict_with_error(self):
        """Test event with error."""
        event = ToolInvocationEvent(
            tool="test",
            status="error",
            error="tool_failed",
            duration_ms=50,
            ts=1000,
        )
        result = event.to_dict()
        
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"], "tool_failed")
        self.assertEqual(result["duration_ms"], 50)


class TestToolRegistryService(unittest.TestCase):
    """Test ToolRegistryService."""
    
    def setUp(self):
        """Create service with temporary files."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.manifest_path = self.temp_dir / "manifest.json"
        self.events_path = self.temp_dir / "events.jsonl"
        
        # Create mock registry
        self.registry = ToolRegistry([])
        
        self.service = ToolRegistryService(
            self.registry,
            self.manifest_path,
            self.events_path,
        )
    
    def tearDown(self):
        """Clean up temp files."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_get_manifest_no_file(self):
        """Test manifest loading when file doesn't exist."""
        manifest = self.service.get_manifest()
        self.assertEqual(manifest, {})
    
    def test_get_manifest_caching(self):
        """Test manifest caching."""
        self.manifest_path.write_text(json.dumps({"tools": []}))
        
        # First load
        m1 = self.service.get_manifest()
        self.assertEqual(m1, {"tools": []})
        
        # Modify file
        self.manifest_path.write_text(json.dumps({"tools": ["new"]}))
        
        # Second load should return cached version
        m2 = self.service.get_manifest()
        self.assertEqual(m2, {"tools": []})
        
        # Invalidate cache and load again
        self.service.invalidate_manifest_cache()
        m3 = self.service.get_manifest()
        self.assertEqual(m3, {"tools": ["new"]})
    
    def test_append_event_creates_file(self):
        """Test that events are appended to log file."""
        event = ToolInvocationEvent(
            tool="test",
            status="ok",
            ts=1000,
        )
        self.service._append_event(event)
        
        # Verify file exists and contains event
        self.assertTrue(self.events_path.exists())
        lines = self.events_path.read_text().strip().split("\n")
        self.assertEqual(len(lines), 1)
        
        parsed = json.loads(lines[0])
        self.assertEqual(parsed["tool"], "test")
        self.assertEqual(parsed["status"], "ok")
    
    def test_append_event_appends_multiple(self):
        """Test that multiple events are appended to the same file."""
        for i in range(3):
            event = ToolInvocationEvent(
                tool=f"tool_{i}",
                status="ok",
                ts=1000 + i,
            )
            self.service._append_event(event)
        
        lines = self.events_path.read_text().strip().split("\n")
        self.assertEqual(len(lines), 3)
    
    def test_list_tools_delegates_to_registry(self):
        """Test that list_tools delegates to registry."""
        tools = self.service.list_tools()
        # Registry is empty, so should return empty list
        self.assertEqual(tools, [])
    
    def test_describe_tools_delegates_to_registry(self):
        """Test that describe_tools delegates to registry."""
        desc = self.service.describe_tools()
        # Should return string description
        self.assertIsInstance(desc, str)


if __name__ == "__main__":
    unittest.main()
