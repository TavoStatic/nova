import unittest
from unittest import mock

from services.server_side_runtime import SERVER_SIDE_RUNTIME_SERVICE


class TestServerSideRuntimeService(unittest.TestCase):
    def test_status_payload_direct_mode_uses_local_runtime_probe(self):
        with mock.patch.object(
            SERVER_SIDE_RUNTIME_SERVICE,
            "_probe_url",
            side_effect=[(True, 200, "http_200", 0.01), (True, 200, "http_200", 0.01)],
        ) as probe_mock:
            payload = SERVER_SIDE_RUNTIME_SERVICE.status_payload(
                {"mode": "native", "frontdoor": "direct", "frontdoor_base_url": ""},
                direct_base_url="http://127.0.0.1:8080",
            )

        self.assertTrue(payload["ok"])
        self.assertFalse(payload["reverse_proxy_frontdoor_enabled"])
        self.assertEqual(payload["probe_target_base_url"], "http://127.0.0.1:8080")
        self.assertEqual(probe_mock.call_count, 2)

    def test_status_payload_proxy_mode_requires_frontdoor_base_url(self):
        payload = SERVER_SIDE_RUNTIME_SERVICE.status_payload(
            {"mode": "proxy", "frontdoor": "apache", "frontdoor_base_url": ""}
        )

        self.assertFalse(payload["ok"])
        self.assertTrue(payload["reverse_proxy_frontdoor_enabled"])
        self.assertEqual(payload["server_side_runtime_note"], "proxy_config_incomplete:frontdoor_base_url_missing")

    def test_render_apache_reverse_proxy_vhost_contains_proxy_rules(self):
        text = SERVER_SIDE_RUNTIME_SERVICE.render_apache_reverse_proxy_vhost(
            server_name="nova.local",
            listen_port=8088,
            upstream_url="http://127.0.0.1:8080",
        )

        self.assertIn("<VirtualHost *:8088>", text)
        self.assertIn("ServerName nova.local", text)
        self.assertIn("ProxyPass / http://127.0.0.1:8080/", text)
        self.assertIn("ProxyPassReverse / http://127.0.0.1:8080/", text)


if __name__ == "__main__":
    unittest.main()
