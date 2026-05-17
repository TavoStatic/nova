import tempfile
import unittest
from pathlib import Path

from services.core_seam_guard import CORE_SEAM_GUARD_SERVICE


class TestCoreSeamGuardService(unittest.TestCase):
    def test_run_checks_passes_for_expected_shell_patterns(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "nova_http.py").write_text(
                "from services.control_actions import CONTROL_ACTIONS_SERVICE\n"
                "from services.control_status import CONTROL_STATUS_SERVICE\n"
                "from services.nova_control_action_dispatcher import NOVA_CONTROL_ACTION_DISPATCHER\n"
                "\n"
                "def demo():\n"
                "    CONTROL_ACTIONS_SERVICE.refresh_status_action(control_status_payload_fn=lambda: {})\n"
                "    CONTROL_ACTIONS_SERVICE.self_check_action(control_self_check_payload_fn=lambda: {})\n"
                "    CONTROL_STATUS_SERVICE.runtime_supplier_fns_from_scope({})\n"
                "    CONTROL_STATUS_SERVICE.runtime_status_payload(core_module=None, session_turns={}, metrics_totals=(0, 0), supplier_fns={})\n"
                "    return NOVA_CONTROL_ACTION_DISPATCHER.dispatch_control_action_from_runtime('refresh_status', {}, runtime_scope={})\n",
                encoding="utf-8",
            )
            (root / "services").mkdir()
            (root / "services" / "voice_interaction.py").write_text(
                "class VoiceInteractionService:\n"
                "    pass\n",
                encoding="utf-8",
            )
            (root / "nova_core.py").write_text(
                "from services.nova_routing_support import classify_supervisor_bypass as service_classify_supervisor_bypass\n"
                "from services.nova_routing_support import looks_like_open_fallback_turn as service_looks_like_open_fallback_turn\n"
                "\n"
                "def a(text):\n"
                "    return service_classify_supervisor_bypass(text=text)\n"
                "\n"
                "def b(text):\n"
                "    return service_looks_like_open_fallback_turn(text=text)\n",
                encoding="utf-8",
            )

            checks = CORE_SEAM_GUARD_SERVICE.run_checks(root)

        self.assertTrue(all(bool(item.get("ok")) for item in checks))

    def test_run_checks_flags_transport_and_content_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "nova_http.py").write_text(
                "from supervisor import Supervisor\n"
                "\n"
                "def demo():\n"
                "    return Supervisor()\n",
                encoding="utf-8",
            )
            (root / "nova_core.py").write_text(
                "import nova_http\n"
                "_ALLOWED_SUPERVISOR_BYPASSES = ({'category': 'general_qa'},)\n",
                encoding="utf-8",
            )
            (root / "services").mkdir()
            (root / "services" / "voice_interaction.py").write_text(
                "import nova_core\n",
                encoding="utf-8",
            )

            checks = {item.get("name"): item for item in CORE_SEAM_GUARD_SERVICE.run_checks(root)}

        self.assertFalse(bool((checks.get("seam:nova_http_transport_boundary") or {}).get("ok")))
        self.assertFalse(bool((checks.get("seam:nova_core_no_content_bypass_bucket") or {}).get("ok")))
        self.assertFalse(bool((checks.get("seam:nova_core_no_http_import_cycle") or {}).get("ok")))
        self.assertFalse(bool((checks.get("seam:voice_service_dependency_inversion") or {}).get("ok")))
