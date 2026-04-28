import unittest

from services import nova_reflection_health


class _BehaviorMetricsStore:
    def __init__(self):
        self.calls = []

    def update_from_reflection(self, payload, count_total):
        self.calls.append((payload, count_total))


class _SubconsciousService:
    @staticmethod
    def get_snapshot(_session_state):
        return {"replan_reasons": ["fallback_pressure"]}


class _Supervisor:
    @staticmethod
    def process_turn(**kwargs):
        return {
            "probe_summary": "All green",
            "probe_results": [],
            "suggestions": [],
            "entry_point": kwargs.get("entry_point", ""),
        }


class _SessionState:
    def __init__(self):
        self.last_reflection = None
        self.subconscious_live_family_summary = {"family": "ok"}

    @staticmethod
    def reflection_summary():
        return {"summary": "ok"}

    def set_last_reflection(self, reflection):
        self.last_reflection = reflection


class TestNovaReflectionHealthService(unittest.TestCase):
    def test_maybe_log_self_reflection_accepts_runtime_scope(self):
        store = _BehaviorMetricsStore()
        captured = []

        payload = nova_reflection_health.maybe_log_self_reflection(
            records=[{"intent": "weather", "tool": "tool_weather", "continuation_used": False}],
            total_records=5,
            every=5,
            runtime_scope={
                "_recent_action_ledger_records": lambda limit: [{"intent": "weather", "tool": "tool_weather"}],
                "_detect_repeated_tool_intent_without_execution": lambda **kwargs: {"summary": "", "class": "", "intent": "", "selected": 0, "completed": 0},
                "_top_repeated_correction_class": lambda **kwargs: {"class": "", "count": 0},
                "_routing_stable_recently": lambda **kwargs: True,
                "_count_unsupported_claim_blocks_recently": lambda **kwargs: 0,
                "_count_routing_overrides_recently": lambda **kwargs: 0,
                "_record_used_routing_override": lambda record: False,
                "_sample_intents_last": lambda **kwargs: ["weather"],
                "_provider_name_from_tool": lambda tool: "weather_provider",
                "_append_self_reflection": lambda row: captured.append(row),
                "record_health_snapshot": lambda **kwargs: None,
                "BEHAVIOR_METRICS_STORE": store,
            },
        )

        self.assertEqual(payload["turn_count"], 5)
        self.assertEqual(payload["sample_intents_last5"], ["weather"])
        self.assertEqual(len(captured), 1)
        self.assertEqual(len(store.calls), 1)

    def test_build_turn_reflection_accepts_runtime_scope(self):
        session = _SessionState()

        reflection = nova_reflection_health.build_turn_reflection(
            session,
            entry_point="cli",
            session_id="abc123",
            current_decision={"intent": "weather"},
            runtime_scope={
                "SUBCONSCIOUS_SERVICE": _SubconsciousService(),
                "TURN_SUPERVISOR": _Supervisor(),
                "_recent_action_ledger_records": lambda limit: [],
                "_recent_self_reflection_rows": lambda limit: [],
                "build_training_backlog_summary": lambda snapshot: {"items": len(snapshot.get("replan_reasons", []))},
                "build_robust_weakness_summary": lambda summary: {"family": "ok"} if summary else None,
            },
        )

        self.assertEqual(reflection["session_id"], "abc123")
        self.assertEqual(reflection["entry_point"], "cli")
        self.assertEqual(reflection["subconscious_training_backlog"], {"items": 1})
        self.assertEqual(session.last_reflection, reflection)


if __name__ == "__main__":
    unittest.main()
