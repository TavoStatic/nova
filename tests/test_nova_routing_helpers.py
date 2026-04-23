import unittest

from services import nova_routing_helpers


class TestNovaRoutingHelpers(unittest.TestCase):
    def test_strip_invocation_prefix_removes_direct_address(self):
        self.assertEqual(
            nova_routing_helpers.strip_invocation_prefix("nova, what is the weather"),
            "what is the weather",
        )

    def test_strip_invocation_prefix_keeps_non_invocation_phrase(self):
        self.assertEqual(
            nova_routing_helpers.strip_invocation_prefix("nova project status"),
            "nova project status",
        )

    def test_resolve_research_provider_prefers_priority_match(self):
        result = nova_routing_helpers.resolve_research_provider(
            ["general_web", "wikipedia"],
            get_search_provider_priority_fn=lambda: ["wikipedia", "general_web"],
            provider_name_from_tool_fn=lambda tool_name: "general_web" if tool_name == "web_research" else "",
        )

        self.assertEqual(result, {"provider": "wikipedia", "tool_name": "wikipedia_lookup"})

    def test_resolve_research_provider_falls_back_to_default_tool(self):
        result = nova_routing_helpers.resolve_research_provider(
            [],
            default_tool="web_research",
            get_search_provider_priority_fn=lambda: ["stackexchange", "general_web"],
            provider_name_from_tool_fn=lambda tool_name: "general_web",
        )

        self.assertEqual(result, {"provider": "general_web", "tool_name": "web_research"})


if __name__ == "__main__":
    unittest.main()