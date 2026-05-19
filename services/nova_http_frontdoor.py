from __future__ import annotations

import argparse
from pathlib import Path
from typing import Callable


class NovaHttpFrontdoorService:
    """Own the HTTP frontdoor route map and startup banner outside the transport shell."""

    @staticmethod
    def _runtime_fn(runtime_scope: dict[str, object], name: str):
        return runtime_scope[name]

    @staticmethod
    def public_surface_renderers(
        *,
        runtime_console_renderer: Callable[[], str],
        leah_renderer: Callable[[], str],
    ) -> dict[str, Callable[[], str]]:
        return {
            "/": runtime_console_renderer,
            "/leah": leah_renderer,
        }

    @staticmethod
    def static_asset_routes(
        *,
        control_css_path: Path,
        control_js_path: Path,
        leah_css_path: Path,
        leah_js_path: Path,
        leah_fx_js_path: Path,
    ) -> dict[str, tuple[Path, str]]:
        return {
            "/static/control.css": (control_css_path, "text/css; charset=utf-8"),
            "/static/control.js": (control_js_path, "application/javascript; charset=utf-8"),
            "/static/leah.css": (leah_css_path, "text/css; charset=utf-8"),
            "/static/leah.js": (leah_js_path, "application/javascript; charset=utf-8"),
            "/static/leah_fx.js": (leah_fx_js_path, "application/javascript; charset=utf-8"),
        }

    @staticmethod
    def public_surface_renderers_from_runtime(
        runtime_scope: dict[str, object],
    ) -> dict[str, Callable[[], str]]:
        runtime_fn = NovaHttpFrontdoorService._runtime_fn
        return NovaHttpFrontdoorService.public_surface_renderers(
            runtime_console_renderer=runtime_fn(runtime_scope, "_render_runtime_console_html"),
            leah_renderer=runtime_fn(runtime_scope, "_render_leah_html"),
        )

    @staticmethod
    def static_asset_routes_from_runtime(
        runtime_scope: dict[str, object],
    ) -> dict[str, tuple[Path, str]]:
        runtime_fn = NovaHttpFrontdoorService._runtime_fn
        return NovaHttpFrontdoorService.static_asset_routes(
            control_css_path=runtime_fn(runtime_scope, "CONTROL_CSS_PATH"),
            control_js_path=runtime_fn(runtime_scope, "CONTROL_JS_PATH"),
            leah_css_path=runtime_fn(runtime_scope, "LEAH_CSS_PATH"),
            leah_js_path=runtime_fn(runtime_scope, "LEAH_JS_PATH"),
            leah_fx_js_path=runtime_fn(runtime_scope, "LEAH_FX_JS_PATH"),
        )

    @staticmethod
    def route_contract(
        *,
        public_renderers: dict[str, Callable[[], str]],
        static_routes: dict[str, tuple[Path, str]],
    ) -> dict[str, tuple[str, ...]]:
        return {
            "public_pages": tuple(public_renderers.keys()),
            "protected_pages": ("/control/login", "/control"),
            "static_assets": tuple(static_routes.keys()),
            "public_api_get": ("/api/health",),
            "chat_api_get": ("/api/chat/history",),
            "control_api_get": (
                "/api/control/status",
                "/api/control/policy",
                "/api/control/metrics",
                "/api/control/sessions",
                "/api/control/test-sessions",
                "/api/control/work-trees",
                "/api/control/pipelines",
            ),
            "chat_api_post": (
                "/api/chat",
                "/api/chat/upload",
                "/api/chat/resume",
                "/api/chat/login",
                "/api/chat/logout",
            ),
            "control_api_post": (
                "/api/control/action",
                "/api/control/login",
                "/api/control/logout",
            ),
        }

    @staticmethod
    def route_contract_from_runtime(runtime_scope: dict[str, object]) -> dict[str, tuple[str, ...]]:
        return NovaHttpFrontdoorService.route_contract(
            public_renderers=NovaHttpFrontdoorService.public_surface_renderers_from_runtime(runtime_scope),
            static_routes=NovaHttpFrontdoorService.static_asset_routes_from_runtime(runtime_scope),
        )

    @staticmethod
    def startup_banner_lines(
        *,
        host: str,
        port: int,
        dev_mode_enabled: bool,
        control_token_enabled: bool,
        control_login_enabled: bool,
    ) -> list[str]:
        lines = [
            f"Nova HTTP runtime console ready at http://{host}:{port}",
            f"Control Room: http://{host}:{port}/control",
        ]
        if host == "0.0.0.0":
            lines.append(f"LAN mode enabled. Open from another device via http://<this-pc-ip>:{port}")
        if dev_mode_enabled:
            lines.append("Control Room auth: DEVELOPMENT MODE enabled (NOVA_DEV_MODE=1, auth checks bypassed).")
        elif control_token_enabled:
            lines.append("Control Room auth: NOVA_CONTROL_TOKEN is enabled (required for admin API access).")
        else:
            lines.append("Control Room auth: local-only mode (set NOVA_CONTROL_TOKEN for LAN-secure access).")
        if control_login_enabled:
            lines.append("Control Room login: enabled (set via NOVA_CONTROL_USER / NOVA_CONTROL_PASS).")
        else:
            lines.append("Control Room login: disabled (optional).")
        return lines

    @staticmethod
    def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
        ap = argparse.ArgumentParser(description="Nova LAN HTTP interface")
        ap.add_argument("--host", default="127.0.0.1", help="Bind host (use 0.0.0.0 for LAN)")
        ap.add_argument("--port", type=int, default=8080, help="Bind port")
        return ap.parse_args(argv)

    @staticmethod
    def serve_from_runtime(
        runtime_scope: dict[str, object],
        *,
        handler_class,
        argv: list[str] | None = None,
        print_fn=print,
    ) -> None:
        runtime_fn = NovaHttpFrontdoorService._runtime_fn
        args = NovaHttpFrontdoorService.parse_args(argv)
        runtime_scope["_HTTP_BIND_HOST"] = str(args.host)
        runtime_scope["_HTTP_BIND_PORT"] = int(args.port)
        runtime_fn(runtime_scope, "_load_persisted_sessions")()
        try:
            core = runtime_fn(runtime_scope, "nova_core")
            core.ensure_ollama_boot()
            warm_fn = getattr(core, "warm_ollama_chat_model", None)
            if callable(warm_fn):
                warm_fn(reason="http_startup")
        except Exception:
            pass

        server_factory = runtime_fn(runtime_scope, "ThreadingHTTPServer")
        srv = server_factory((args.host, args.port), handler_class)
        runtime_scope["_HTTP_SERVER"] = srv
        try:
            for line in NovaHttpFrontdoorService.startup_banner_lines(
                host=str(args.host),
                port=int(args.port),
                dev_mode_enabled=runtime_fn(runtime_scope, "_dev_mode_enabled")(),
                control_token_enabled=bool((runtime_fn(runtime_scope, "os").environ.get("NOVA_CONTROL_TOKEN") or "").strip()),
                control_login_enabled=runtime_fn(runtime_scope, "_control_login_enabled")(),
            ):
                print_fn(line, flush=True)
            srv.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            runtime_scope["_HTTP_SERVER"] = None
            srv.server_close()


NOVA_HTTP_FRONTDOOR_SERVICE = NovaHttpFrontdoorService()
