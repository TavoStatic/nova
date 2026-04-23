import unittest

from services import nova_memory_learning


class TestNovaMemoryLearningService(unittest.TestCase):
    def test_get_learned_fact_returns_default_when_missing(self):
        value = nova_memory_learning.get_learned_fact(
            "developer_name",
            "Gustavo Uribe",
            load_learned_facts_fn=lambda: {},
        )

        self.assertEqual(value, "Gustavo Uribe")

    def test_learn_self_identity_binding_binds_known_developer(self):
        bound = []

        learned, message = nova_memory_learning.learn_self_identity_binding(
            "I am gus!",
            set_active_user_fn=lambda value: bound.append(value),
            get_learned_fact_fn=lambda key, default="": {
                "developer_name": "Gustavo Uribe",
                "developer_nickname": "Gus",
            }.get(key, default),
        )

        self.assertTrue(learned)
        self.assertIn("identity confirmed", message.lower())
        self.assertEqual(bound, ["Gustavo Uribe"])

    def test_learn_contextual_self_facts_stores_developer_colors(self):
        writes = []

        learned, message = nova_memory_learning.learn_contextual_self_facts(
            "my favorite colors are silver, blue and red",
            speaker_matches_developer_fn=lambda: True,
            extract_color_preferences_from_text_fn=lambda text: ["silver", "blue", "red"],
            mem_enabled_fn=lambda: True,
            mem_add_fn=lambda kind, source, text: writes.append((kind, source, text)),
        )

        self.assertTrue(learned)
        self.assertIn("favorite colors", message.lower())
        self.assertEqual(writes, [("identity", "typed", "Gus favorite colors are silver, blue, and red.")])

    def test_remember_and_recall_name_origin_story(self):
        profile = {}

        result = nova_memory_learning.remember_name_origin(
            "Nova was given its name by Gus as a symbol of new light and new beginnings.",
            load_identity_profile_fn=lambda: dict(profile),
            save_identity_profile_fn=lambda data: profile.update(data),
            mem_enabled_fn=lambda: False,
            mem_add_fn=lambda kind, source, text: None,
        )

        recalled = nova_memory_learning.get_name_origin_story(
            load_identity_profile_fn=lambda: dict(profile),
            mem_recall_fn=lambda query: "",
        )

        self.assertIn("stored", result.lower())
        self.assertIn("new light", recalled.lower())

    def test_mem_recall_skips_when_router_blocks(self):
        events = []

        class _FailIfCalled:
            def recall(self, *_args, **_kwargs):
                raise AssertionError("recall should not run when router blocks")

        out = nova_memory_learning.mem_recall(
            "tell me a joke about weather",
            mem_enabled_fn=lambda: True,
            memory_recall_plan_fn=lambda *_args, **_kwargs: type("Plan", (), {"allow": False, "reason": "not_memory_seeking", "purpose": "general"})(),
            memory_runtime_user_fn=lambda: "tester",
            memory_mod=_FailIfCalled(),
            mem_context_top_k_fn=lambda: 3,
            mem_min_score_fn=lambda: 0.25,
            mem_exclude_sources_fn=lambda: [],
            mem_scope_fn=lambda: "private",
            format_memory_recall_hits_fn=lambda hits: "formatted",
            record_memory_event_fn=lambda *args, **kwargs: events.append((args, kwargs)),
            python_path="python",
            base_dir=__import__("pathlib").Path("."),
        )

        self.assertEqual(out, "")
        self.assertEqual(events[0][0][0], "recall")
        self.assertEqual(events[0][0][1], "skipped")
        self.assertEqual(events[0][1].get("reason"), "not_memory_seeking")

    def test_mem_recall_uses_memory_when_router_allows(self):
        events = []

        class _FakeMemory:
            def recall(self, *_args, **_kwargs):
                return [(0.9, 0, "fact", "typed", "tester", "favorite color is blue")]

        out = nova_memory_learning.mem_recall(
            "what colors does the user like favorite color preference",
            mem_enabled_fn=lambda: True,
            memory_recall_plan_fn=lambda *_args, **_kwargs: type("Plan", (), {"allow": True, "reason": "purpose_match", "purpose": "user_preferences"})(),
            memory_runtime_user_fn=lambda: "tester",
            memory_mod=_FakeMemory(),
            mem_context_top_k_fn=lambda: 3,
            mem_min_score_fn=lambda: 0.25,
            mem_exclude_sources_fn=lambda: [],
            mem_scope_fn=lambda: "private",
            format_memory_recall_hits_fn=lambda hits: hits[0][5],
            record_memory_event_fn=lambda *args, **kwargs: events.append((args, kwargs)),
            python_path="python",
            base_dir=__import__("pathlib").Path("."),
        )

        self.assertIn("blue", out)
        self.assertEqual(events[0][0][1], "ok")
        self.assertEqual(events[0][1].get("mode"), "user_preferences")

    def test_mem_get_recent_learned_skips_when_router_blocks(self):
        events = []

        class _FailIfCalled:
            def connect(self):
                raise AssertionError("recent learned should not read rows when router blocks")

        out = nova_memory_learning.mem_get_recent_learned(
            5,
            mem_enabled_fn=lambda: True,
            memory_mod=_FailIfCalled(),
            memory_runtime_user_fn=lambda: "tester",
            mem_scope_fn=lambda: "private",
            normalize_recent_learning_item_fn=lambda kind, text: text,
            load_learned_facts_fn=lambda: {},
            memory_read_plan_fn=lambda *_args, **_kwargs: type("Plan", (), {"allow": False, "lane": "durable_user", "reason": "session_priority", "purpose": "recent_learning_summary"})(),
            record_memory_event_fn=lambda *args, **kwargs: events.append((args, kwargs)),
        )

        self.assertEqual(out, [])
        self.assertEqual(events[0][0][0], "recent_learned")
        self.assertEqual(events[0][0][1], "skipped")
        self.assertEqual(events[0][1].get("reason"), "session_priority")

    def test_mem_get_recent_learned_records_allowed_read(self):
        events = []

        class _FakeMemory:
            def connect(self):
                return object()

            def select_memory_rows(self, _connection, _user, _scope):
                return [
                    (0, "user_fact", "typed", "tester", "my favorite color is teal", None),
                    (0, "user_correction", "typed", "tester", '{"parsed_correction": "my favorite color is blue"}', None),
                ]

        out = nova_memory_learning.mem_get_recent_learned(
            5,
            mem_enabled_fn=lambda: True,
            memory_mod=_FakeMemory(),
            memory_runtime_user_fn=lambda: "tester",
            mem_scope_fn=lambda: "private",
            normalize_recent_learning_item_fn=nova_memory_learning.normalize_recent_learning_item,
            load_learned_facts_fn=lambda: {},
            memory_read_plan_fn=lambda *_args, **_kwargs: type("Plan", (), {"allow": True, "lane": "durable_user", "reason": "purpose_match", "purpose": "recent_learning_summary"})(),
            record_memory_event_fn=lambda *args, **kwargs: events.append((args, kwargs)),
        )

        self.assertEqual(out, ["my favorite color is teal", "Correction: my favorite color is blue"])
        self.assertEqual(events[0][0][0], "recent_learned")
        self.assertEqual(events[0][0][1], "ok")
        self.assertEqual(events[0][1].get("mode"), "recent_learning_summary")


if __name__ == "__main__":
    unittest.main()