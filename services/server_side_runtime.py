from __future__ import annotations

import time
import urllib.error
import urllib.request
from urllib.parse import urljoin


class ServerSideRuntimeService:
    """Own server-side/frontdoor runtime probing and reverse-proxy config rendering."""

    @staticmethod
    def _normalize_settings(server_side: dict | None) -> dict:
        raw = dict(server_side or {})
        mode = str(raw.get("mode") or "native").strip().lower()
        if mode not in {"native", "proxy"}:
            mode = "native"

        frontdoor = str(raw.get("frontdoor") or "direct").strip().lower()
        if frontdoor not in {"direct", "apache", "uniserver"}:
            frontdoor = "direct"

        frontdoor_base_url = str(raw.get("frontdoor_base_url") or "").strip().rstrip("/")
        docker_enabled = bool(raw.get("docker_enabled", False))

        return {
            "mode": mode,
            "frontdoor": frontdoor,
            "frontdoor_base_url": frontdoor_base_url,
            "docker_enabled": docker_enabled,
        }

    @staticmethod
    def _probe_url(url: str, timeout_sec: float) -> tuple[bool, int, str, float]:
        started = time.monotonic()
        req = urllib.request.Request(url, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=max(0.1, float(timeout_sec))) as response:
                status = int(getattr(response, "status", 0) or 0)
                detail = f"http_{status}" if status else "ok"
                return status < 500, status, detail, round(time.monotonic() - started, 3)
        except urllib.error.HTTPError as exc:
            status = int(getattr(exc, "code", 0) or 0)
            detail = f"http_{status}"
            return status < 500, status, detail, round(time.monotonic() - started, 3)
        except Exception as exc:
            return False, 0, f"unreachable:{exc}", round(time.monotonic() - started, 3)

    def status_payload(
        self,
        server_side: dict | None,
        *,
        direct_base_url: str = "http://127.0.0.1:8080",
        timeout_sec: float = 2.5,
    ) -> dict:
        settings = self._normalize_settings(server_side)
        mode = settings["mode"]
        frontdoor = settings["frontdoor"]
        configured_base_url = settings["frontdoor_base_url"]

        reverse_proxy_enabled = mode == "proxy" or frontdoor in {"apache", "uniserver"}
        if reverse_proxy_enabled:
            target_base_url = configured_base_url
        else:
            target_base_url = str(direct_base_url or "").strip().rstrip("/")

        health_url = ""
        control_url = ""
        health_ok = False
        control_ok = False
        health_status = 0
        control_status = 0
        health_detail = "not_checked"
        control_detail = "not_checked"
        health_latency_sec = 0.0
        control_latency_sec = 0.0

        if target_base_url:
            health_url = urljoin(target_base_url + "/", "api/health")
            control_url = urljoin(target_base_url + "/", "api/control/status")
            health_ok, health_status, health_detail, health_latency_sec = self._probe_url(health_url, timeout_sec)
            control_ok, control_status, control_detail, control_latency_sec = self._probe_url(control_url, timeout_sec)
        elif reverse_proxy_enabled:
            health_detail = "frontdoor_base_url_missing"
            control_detail = "frontdoor_base_url_missing"

        runtime_ok = bool(health_ok and control_ok)
        if reverse_proxy_enabled and not target_base_url:
            runtime_note = "proxy_config_incomplete:frontdoor_base_url_missing"
        elif reverse_proxy_enabled and runtime_ok:
            runtime_note = "proxy_reachable"
        elif reverse_proxy_enabled:
            runtime_note = "proxy_unreachable"
        elif runtime_ok:
            runtime_note = "direct_runtime_reachable"
        else:
            runtime_note = "direct_runtime_unreachable"

        return {
            "ok": runtime_ok,
            "mode": mode,
            "frontdoor": frontdoor,
            "frontdoor_base_url": configured_base_url,
            "docker_enabled": bool(settings["docker_enabled"]),
            "reverse_proxy_frontdoor_enabled": reverse_proxy_enabled,
            "reverse_proxy_frontdoor_ok": bool(runtime_ok if reverse_proxy_enabled else True),
            "server_side_runtime_ok": runtime_ok,
            "server_side_runtime_note": runtime_note,
            "probe_target_base_url": target_base_url,
            "health_url": health_url,
            "health_ok": bool(health_ok),
            "health_status": int(health_status or 0),
            "health_detail": health_detail,
            "health_latency_sec": float(health_latency_sec),
            "control_status_url": control_url,
            "control_status_ok": bool(control_ok),
            "control_status_http": int(control_status or 0),
            "control_status_detail": control_detail,
            "control_status_latency_sec": float(control_latency_sec),
        }

    @staticmethod
    def render_apache_reverse_proxy_vhost(
        *,
        server_name: str = "localhost",
        listen_port: int = 80,
        upstream_url: str = "http://127.0.0.1:8080",
    ) -> str:
        upstream = str(upstream_url or "http://127.0.0.1:8080").strip().rstrip("/")
        host = str(server_name or "localhost").strip() or "localhost"
        port = int(listen_port or 80)
        return (
            f"<VirtualHost *:{port}>\n"
            f"    ServerName {host}\n"
            f"\n"
            "    ProxyPreserveHost On\n"
            "    ProxyRequests Off\n"
            "\n"
            f"    ProxyPass / {upstream}/\n"
            f"    ProxyPassReverse / {upstream}/\n"
            "\n"
            "    RequestHeader set X-Forwarded-Proto \"http\"\n"
            "    RequestHeader set X-Forwarded-Port \"80\"\n"
            "</VirtualHost>\n"
        )


SERVER_SIDE_RUNTIME_SERVICE = ServerSideRuntimeService()
