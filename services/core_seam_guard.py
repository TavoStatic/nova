from __future__ import annotations

from pathlib import Path


class CoreSeamGuardService:
    """Own lightweight structural checks for the core shell surfaces."""

    _HTTP_REQUIRED_FRAGMENTS = (
        "CONTROL_STATUS_SERVICE.runtime_status_payload(",
        "CONTROL_STATUS_SERVICE.runtime_supplier_fns_from_scope(",
        "NOVA_CONTROL_ACTION_DISPATCHER.dispatch_control_action_from_runtime(",
        "CONTROL_ACTIONS_SERVICE.refresh_status_action(",
        "CONTROL_ACTIONS_SERVICE.self_check_action(",
    )

    _HTTP_FORBIDDEN_FRAGMENTS = (
        "from supervisor import Supervisor",
        "import intent_interpreter",
        "from routing.heuristics import",
        "import routing.heuristics",
        "from services.supervisor_routing_rules import",
        "import services.supervisor_routing_rules",
    )

    _CORE_REQUIRED_FRAGMENTS = ()

    _CORE_FORBIDDEN_FRAGMENTS = (
        '"category": "general_qa"',
        "'category': 'general_qa'",
    )

    _CORE_HTTP_IMPORT_FORBIDDEN_FRAGMENTS = (
        "import nova_http",
        "from nova_http",
    )

    _VOICE_SERVICE_FORBIDDEN_FRAGMENTS = (
        "import nova_core",
        "from nova_core",
        "import nova_http",
        "from nova_http",
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
        voice_service_path = root / "services" / "voice_interaction.py"
        http_text = self._read_text(http_path)
        core_text = self._read_text(core_path)
        voice_service_text = self._read_text(voice_service_path)

        forbidden_http = [fragment for fragment in self._HTTP_FORBIDDEN_FRAGMENTS if fragment in http_text]
        missing_http = [fragment for fragment in self._HTTP_REQUIRED_FRAGMENTS if fragment not in http_text]
        missing_core = [fragment for fragment in self._CORE_REQUIRED_FRAGMENTS if fragment not in core_text]
        forbidden_core = [fragment for fragment in self._CORE_FORBIDDEN_FRAGMENTS if fragment in core_text]
        forbidden_core_http_imports = [
            fragment
            for fragment in self._CORE_HTTP_IMPORT_FORBIDDEN_FRAGMENTS
            if fragment in core_text
        ]
        forbidden_voice_service_imports = [
            fragment
            for fragment in self._VOICE_SERVICE_FORBIDDEN_FRAGMENTS
            if fragment in voice_service_text
        ]

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
                "info": "nova_core.py no longer carries bypass/open-fallback chat classifiers"
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
            {
                "name": "seam:nova_core_no_http_import_cycle",
                "ok": not forbidden_core_http_imports,
                "required": True,
                "info": "nova_core.py does not import nova_http.py"
                if not forbidden_core_http_imports
                else "forbidden fragments: " + ", ".join(forbidden_core_http_imports),
            },
            {
                "name": "seam:voice_service_dependency_inversion",
                "ok": not forbidden_voice_service_imports,
                "required": True,
                "info": "services/voice_interaction.py receives shell dependencies instead of importing nova_core/nova_http"
                if not forbidden_voice_service_imports
                else "forbidden fragments: " + ", ".join(forbidden_voice_service_imports),
            },
        ]


CORE_SEAM_GUARD_SERVICE = CoreSeamGuardService()
