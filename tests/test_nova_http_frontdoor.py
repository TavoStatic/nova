import unittest
from pathlib import Path

from services.nova_http_frontdoor import NOVA_HTTP_FRONTDOOR_SERVICE


class TestNovaHttpFrontdoorService(unittest.TestCase):
    def test_route_contract_contains_frontdoor_and_control_surfaces(self):
        contract = NOVA_HTTP_FRONTDOOR_SERVICE.route_contract(
            public_renderers={
                "/": lambda: "root",
                "/leah": lambda: "leah",
            },
            static_routes={
                "/static/control.css": (Path("control.css"), "text/css"),
                "/static/leah.css": (Path("leah.css"), "text/css"),
                "/static/leah.js": (Path("leah.js"), "application/javascript"),
                "/static/leah_fx.js": (Path("leah_fx.js"), "application/javascript"),
            },
        )

        self.assertIn("/", contract["public_pages"])
        self.assertIn("/leah", contract["public_pages"])
        self.assertIn("/control", contract["protected_pages"])
        self.assertIn("/static/leah.css", contract["static_assets"])
        self.assertIn("/api/control/work-trees", contract["control_api_get"])
        self.assertIn("/api/chat/upload", contract["chat_api_post"])

    def test_startup_banner_lines_reflect_auth_and_lan_state(self):
        lines = NOVA_HTTP_FRONTDOOR_SERVICE.startup_banner_lines(
            host="0.0.0.0",
            port=8080,
            dev_mode_enabled=False,
            control_token_enabled=True,
            control_login_enabled=True,
        )

        joined = "\n".join(lines)
        self.assertIn("http://0.0.0.0:8080", joined)
        self.assertIn("LAN mode enabled.", joined)
        self.assertIn("NOVA_CONTROL_TOKEN is enabled", joined)
        self.assertIn("Control Room login: enabled", joined)

    def test_serve_from_runtime_sets_and_clears_server_state(self):
        events = []
        runtime_scope = {
            "_load_persisted_sessions": lambda: events.append("load_sessions"),
            "nova_core": type("CoreStub", (), {"ensure_ollama_boot": staticmethod(lambda: events.append("ensure_boot"))})(),
            "ThreadingHTTPServer": lambda addr, handler: type(
                "ServerStub",
                (),
                {
                    "serve_forever": staticmethod(lambda: events.append(("serve", addr, handler))),
                    "server_close": staticmethod(lambda: events.append("close")),
                },
            )(),
            "_dev_mode_enabled": lambda: False,
            "_control_login_enabled": lambda: True,
            "os": type("OsStub", (), {"environ": {"NOVA_CONTROL_TOKEN": "token"}})(),
            "_HTTP_SERVER": None,
            "_HTTP_BIND_HOST": "",
            "_HTTP_BIND_PORT": 0,
        }

        printed = []
        NOVA_HTTP_FRONTDOOR_SERVICE.serve_from_runtime(
            runtime_scope,
            handler_class=object(),
            argv=["--host", "127.0.0.1", "--port", "9090"],
            print_fn=lambda line, flush=False: printed.append((line, flush)),
        )

        self.assertEqual(runtime_scope["_HTTP_BIND_HOST"], "127.0.0.1")
        self.assertEqual(runtime_scope["_HTTP_BIND_PORT"], 9090)
        self.assertIsNone(runtime_scope["_HTTP_SERVER"])
        self.assertIn("load_sessions", events)
        self.assertIn("ensure_boot", events)
        self.assertIn("close", events)
        self.assertTrue(any("http://127.0.0.1:9090" in line for line, _flush in printed))


if __name__ == "__main__":
    unittest.main()
