import types
import unittest

from services import nova_command_handlers


class _SessionStub:
    def __init__(self):
        self.language_mix_spanish_pct = 0

    def set_language_mix_spanish_pct(self, value):
        self.language_mix_spanish_pct = value


class _CoreStub:
    def __init__(self):
        self.actions = []
        self.patch_calls = []
        self.DEFAULT_STATEFILE = "runtime/state.json"
        self.os = types.SimpleNamespace(environ={})
        self.re = __import__("re")
        self.json = __import__("json")

    def _strip_invocation_prefix(self, text):
        return text

    def _render_chat_context(self, turns):
        return ""

    def execute_planned_action(self, tool, args=None):
        self.actions.append((tool, args))
        return f"action:{tool}:{args}"

    def list_allowed_domains(self):
        return "example.com"

    def policy_allow_domain(self, value):
        return f"allow:{value}"

    def policy_remove_domain(self, value):
        return f"remove:{value}"

    def policy_audit(self, limit):
        return f"audit:{limit}"

    def web_mode_status(self):
        return "web-status"

    def set_web_mode(self, mode):
        return f"web:{mode}"

    def set_location_coords(self, value):
        return f"coords:{value}"

    def _normalize_turn_text(self, text):
        return text.lower()

    def _is_saved_location_weather_query(self, _text):
        return False

    def runtime_device_location_payload(self):
        return {"available": False, "stale": True}

    def get_saved_location_text(self):
        return ""

    def _coords_from_saved_location(self):
        return None

    def _need_confirmed_location_message(self):
        return "need location"

    def _is_location_request(self, _text):
        return False

    def _location_reply(self):
        return "location"

    def mem_remember_fact(self, text):
        return f"remember:{text}"

    def describe_capabilities(self):
        return "capabilities"

    def mem_stats(self):
        return "stats"

    def _clamp_language_mix(self, value):
        return max(0, min(100, int(value)))

    def mem_audit(self, query):
        return f"audit:{query}"

    def kb_list_packs(self):
        return "packs"

    def kb_set_active(self, name):
        return f"kb:{name}"

    def kb_add_zip(self, path, name):
        return f"kbadd:{path}:{name}"

    def execute_patch_action(self, action, value="", *, force=False, is_admin=True):
        self.patch_calls.append((action, value, force, is_admin))
        return f"patch:{action}:{value}:{force}:{is_admin}"

    def _teach_store_example(self, orig, corr):
        return f"teach:{orig}:{corr}"

    def _teach_list_examples(self):
        return "teach:list"

    def _teach_propose_patch(self, desc):
        return f"teach:propose:{desc}"

    def _teach_autoapply_proposal(self, zp, apply_live=False):
        return f"teach:auto:{zp}:{apply_live}"

    def inspect_environment(self):
        return {"ok": True}

    def format_report(self, data):
        return f"report:{data['ok']}"

    def set_core_state(self, _statefile, _key, _value):
        return None

    def behavior_get_metrics(self):
        return {
            "correction_learned": 1,
            "correction_applied": 2,
            "self_correction_applied": 3,
            "deterministic_hit": 4,
            "llm_fallback": 5,
            "top_repeated_failure_class": "none",
            "top_repeated_correction_class": "none",
            "routing_stable": True,
            "unsupported_claims_blocked": False,
            "last_event": "ok",
        }


class TestNovaCommandHandlersService(unittest.TestCase):
    def test_queue_command_routes_through_planned_action(self):
        core = _CoreStub()

        out = nova_command_handlers.handle_commands("queue status", core=core)

        self.assertEqual(out, "action:queue_status:None")
        self.assertEqual(core.actions, [("queue_status", None)])

    def test_patch_apply_parses_force_flag(self):
        core = _CoreStub()

        out = nova_command_handlers.handle_commands("patch apply proposal.zip --force", core=core)

        self.assertEqual(out, "patch:apply:proposal.zip:True:True")
        self.assertEqual(core.patch_calls, [("apply", "proposal.zip", True, True)])

    def test_set_mix_updates_session_language_percentage(self):
        core = _CoreStub()
        session = _SessionStub()

        out = nova_command_handlers.handle_commands("set mix 35", session=session, core=core)

        self.assertEqual(out, "Language mix updated: Spanish 35% (English 65%)")
        self.assertEqual(session.language_mix_spanish_pct, 35)


if __name__ == "__main__":
    unittest.main()