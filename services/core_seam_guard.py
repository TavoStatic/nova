from __future__ import annotations

from pathlib import Path


class CoreSeamGuardService:
    """Own lightweight structural checks for the core shell surfaces."""

    _HTTP_REQUIRED_FRAGMENTS = (
        "CONTROL_STATUS_SERVICE.control_status_payload(",
        "CONTROL_ACTIONS_SERVICE.build_action_handlers(",
        "CONTROL_ACTIONS_SERVICE.handle_control_action(",
    )

    _HTTP_FORBIDDEN_FRAGMENTS = (
        "from supervisor import Supervisor",
        "import intent_interpreter",
        "from routing.heuristics import",
        "import routing.heuristics",
        "from services.supervisor_routing_rules import",
        "import services.supervisor_routing_rules",
    )

    _CORE_REQUIRED_FRAGMENTS = (
        "from services.nova_routing_support import classify_supervisor_bypass as service_classify_supervisor_bypass",
        "from services.nova_routing_support import looks_like_open_fallback_turn as service_looks_like_open_fallback_turn",
        "return service_classify_supervisor_bypass(",
        "return service_looks_like_open_fallback_turn(",
    )

    _CORE_FORBIDDEN_FRAGMENTS = (
        '"category": "general_qa"',
        "'category': 'general_qa'",
    )

    @staticmethod
    def _read_text(path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return ""

    def run_checks(self, base_dir: Path) -> list[dict[str, object]]:
        root = Path(base_dir)
        http_path = root / "nova_http.py"
        core_path = root / "nova_core.py"
        http_text = self._read_text(http_path)
        core_text = self._read_text(core_path)

        forbidden_http = [fragment for fragment in self._HTTP_FORBIDDEN_FRAGMENTS if fragment in http_text]
        missing_http = [fragment for fragment in self._HTTP_REQUIRED_FRAGMENTS if fragment not in http_text]
        missing_core = [fragment for fragment in self._CORE_REQUIRED_FRAGMENTS if fragment not in core_text]
        forbidden_core = [fragment for fragment in self._CORE_FORBIDDEN_FRAGMENTS if fragment in core_text]

        return [
            {
                "name": "seam:nova_http_transport_boundary",
                "ok": not forbidden_http,
                "required": True,
                "info": "nova_http.py must not import routing/supervisor ownership logic directly"
                if not forbidden_http
                else "forbidden fragments: " + ", ".join(forbidden_http),
            },
            {
                "name": "seam:nova_http_control_delegation",
                "ok": not missing_http,
                "required": True,
                "info": "nova_http.py still delegates status/action orchestration through shared services"
                if not missing_http
                else "missing fragments: " + ", ".join(missing_http),
            },
            {
                "name": "seam:nova_core_routing_support_delegation",
                "ok": not missing_core,
                "required": True,
                "info": "nova_core.py still delegates bypass/open-fallback classification through services.nova_routing_support"
                if not missing_core
                else "missing fragments: " + ", ".join(missing_core),
            },
            {
                "name": "seam:nova_core_no_content_bypass_bucket",
                "ok": not forbidden_core,
                "required": True,
                "info": "nova_core.py does not carry a generic content-driven bypass bucket"
                if not forbidden_core
                else "forbidden fragments: " + ", ".join(forbidden_core),
            },
        ]


CORE_SEAM_GUARD_SERVICE = CoreSeamGuardService()