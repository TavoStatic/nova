from __future__ import annotations

from typing import Any


DEFAULT_PORT_SPECS = [
    {
        "service": "http_ui",
        "port": 8080,
        "expected_cmdline_fragments": ["nova_http.py"],
    },
    {
        "service": "searxng",
        "port": 8081,
    },
    {
        "service": "ollama",
        "port": 11434,
        "expected_process_fragments": ["ollama"],
    },
]


class PortOwnershipService:
    """Report listener ownership for runtime ports without shelling out."""

    @staticmethod
    def _addr_payload(laddr: Any) -> tuple[str, int]:
        try:
            return str(getattr(laddr, "ip") or ""), int(getattr(laddr, "port") or 0)
        except Exception:
            pass
        try:
            values = list(laddr or [])
            return str(values[0] if values else ""), int(values[1] if len(values) > 1 else 0)
        except Exception:
            return "", 0

    @staticmethod
    def _process_payload(psutil_module: Any, pid: int | None) -> dict[str, Any]:
        if not isinstance(pid, int) or pid <= 0:
            return {"pid": pid, "name": "", "exe": "", "cmdline": [], "status": "", "create_time": None}
        try:
            process = psutil_module.Process(pid)
            return {
                "pid": pid,
                "name": str(process.name() or ""),
                "exe": str(process.exe() or ""),
                "cmdline": [str(item) for item in list(process.cmdline() or [])],
                "status": str(process.status() or ""),
                "create_time": float(process.create_time() or 0.0),
            }
        except Exception as exc:
            return {
                "pid": pid,
                "name": "",
                "exe": "",
                "cmdline": [],
                "status": "unknown",
                "create_time": None,
                "error": str(exc),
            }

    @staticmethod
    def _owner_matches(owner: dict[str, Any], spec: dict[str, Any]) -> bool | None:
        process_fragments = [
            str(item or "").strip().lower()
            for item in list(spec.get("expected_process_fragments") or [])
            if str(item or "").strip()
        ]
        cmdline_fragments = [
            str(item or "").strip().lower()
            for item in list(spec.get("expected_cmdline_fragments") or [])
            if str(item or "").strip()
        ]
        if not process_fragments and not cmdline_fragments:
            return None

        name_text = str(owner.get("name") or "").lower()
        exe_text = str(owner.get("exe") or "").lower()
        cmdline_text = " ".join(str(item or "") for item in list(owner.get("cmdline") or [])).lower()
        process_text = f"{name_text} {exe_text} {cmdline_text}"

        process_ok = True if not process_fragments else any(fragment in process_text for fragment in process_fragments)
        cmdline_ok = True if not cmdline_fragments else all(fragment in cmdline_text for fragment in cmdline_fragments)
        return bool(process_ok and cmdline_ok)

    def payload(self, *, psutil_module: Any, service_specs: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        specs = [dict(item) for item in list(service_specs or DEFAULT_PORT_SPECS) if isinstance(item, dict)]
        target_ports = {int(item.get("port") or 0) for item in specs if int(item.get("port") or 0) > 0}
        listeners_by_port: dict[int, list[dict[str, Any]]] = {port: [] for port in target_ports}
        issues: list[dict[str, Any]] = []
        listen_status = getattr(psutil_module, "CONN_LISTEN", "LISTEN")

        try:
            connections = list(psutil_module.net_connections(kind="inet") or [])
        except Exception as exc:
            return {
                "ok": False,
                "status": "unavailable",
                "error": str(exc),
                "ports": {},
                "issues": [{"code": "port_scan_failed", "detail": str(exc)}],
                "issue_count": 1,
            }

        for conn in connections:
            status = str(getattr(conn, "status", "") or "")
            if status != str(listen_status):
                continue
            host, port = self._addr_payload(getattr(conn, "laddr", None))
            if port not in target_ports:
                continue
            pid_raw = getattr(conn, "pid", None)
            try:
                pid = int(pid_raw) if pid_raw is not None else None
            except Exception:
                pid = None
            owner = self._process_payload(psutil_module, pid)
            owner["address"] = host
            owner["port"] = port
            listeners_by_port.setdefault(port, []).append(owner)

        ports_payload: dict[str, dict[str, Any]] = {}
        for spec in specs:
            port = int(spec.get("port") or 0)
            if port <= 0:
                continue
            service = str(spec.get("service") or f"port_{port}").strip() or f"port_{port}"
            owners = sorted(
                listeners_by_port.get(port, []),
                key=lambda item: (str(item.get("address") or ""), int(item.get("pid") or 0)),
            )
            expected_matches = [self._owner_matches(owner, spec) for owner in owners]
            expected_owner_present = None
            if any(match is not None for match in expected_matches):
                expected_owner_present = any(match is True for match in expected_matches)
            row = {
                "service": service,
                "port": port,
                "listening": bool(owners),
                "listener_count": len(owners),
                "owners": owners,
                "expected_owner_present": expected_owner_present,
            }
            ports_payload[str(port)] = row
            if bool(owners) and expected_owner_present is False:
                issues.append({
                    "code": "unexpected_port_owner",
                    "service": service,
                    "port": port,
                    "detail": f"Port {port} is listening, but no owner matches the expected {service} process identity.",
                })

        return {
            "ok": not issues,
            "status": "ok" if not issues else "watch",
            "ports": ports_payload,
            "issues": issues,
            "issue_count": len(issues),
        }


PORT_OWNERSHIP_SERVICE = PortOwnershipService()
