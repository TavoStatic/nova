import unittest

from services.control_work_trees import CONTROL_WORK_TREES_SERVICE


class TestControlWorkTreesService(unittest.TestCase):
    def test_payload_summarizes_visible_tree_counts(self):
        payload = [
            {
                "tree_id": "tree_1",
                "title": "Queue repair",
                "status": "active",
                "active_branch_id": "branch_1",
                "counts": {
                    "open_tasks": 2,
                    "branches": {
                        "active": 1,
                        "ready": 2,
                        "blocked": 1,
                        "complete": 3,
                    },
                },
            },
            {
                "tree_id": "tree_2",
                "title": "Closed review",
                "status": "complete",
                "active_branch_id": "",
                "counts": {
                    "open_tasks": 0,
                    "branches": {
                        "complete": 2,
                    },
                },
            },
        ]

        result = CONTROL_WORK_TREES_SERVICE.payload(
            list_visual_trees_fn=lambda limit=None: payload,
            limit=32,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["counts"]["total"], 2)
        self.assertEqual(result["counts"]["active"], 1)
        self.assertEqual(result["counts"]["branches"], 9)
        self.assertEqual(result["counts"]["open_tasks"], 2)
        self.assertEqual(result["counts"]["working"], 1)
        self.assertEqual(result["counts"]["pending"], 2)
        self.assertEqual(result["counts"]["blocked"], 1)
        self.assertEqual(result["counts"]["complete"], 5)

    def test_payload_keeps_priority_tree_visible_when_trimmed(self):
        limited_payload = [
            {
                "tree_id": "tree_1",
                "title": "Queue repair",
                "status": "active",
                "active_branch_id": "branch_1",
                "counts": {
                    "open_tasks": 1,
                    "branches": {"active": 1},
                },
            }
        ]
        generated_queue_tree = {
            "tree_id": "tree_generated",
            "title": "Generated Queue: governed self-repair",
            "kind": "generated_queue",
            "status": "complete",
            "active_branch_id": "",
            "counts": {
                "open_tasks": 0,
                "branches": {"complete": 1},
            },
        }

        def _list_visual_trees(limit=None):
            if limit is None:
                return limited_payload + [generated_queue_tree]
            return limited_payload

        result = CONTROL_WORK_TREES_SERVICE.payload(
            list_visual_trees_fn=_list_visual_trees,
            limit=1,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["counts"]["total"], 2)
        self.assertEqual(
            [tree.get("tree_id") for tree in result["trees"]],
            ["tree_1", "tree_generated"],
        )

    def test_payload_semantically_dedupes_runtime_ops_shells(self):
        runtime_ops_chat = {
            "tree_id": "tree_chat_runtime_ops",
            "title": "Chat: inspect runtime queue pressure",
            "kind": "system",
            "source": "chat",
            "work_identity_key": "work:inspect-pressure-queue-runtime|terms:inspect|pressure|queue|runtime",
            "work_identity_label": "inspect / pressure / queue / runtime",
            "status": "complete",
            "active_branch_id": "",
            "counts": {
                "open_tasks": 0,
                "branches": {"complete": 0},
            },
        }
        runtime_ops_health = {
            "tree_id": "tree_health_runtime_ops",
            "title": "Health: verify runtime heartbeat",
            "kind": "system",
            "source": "health",
            "work_identity_key": "work:heartbeat-runtime-verify|terms:heartbeat|runtime|verify",
            "work_identity_label": "heartbeat / runtime / verify",
            "status": "complete",
            "active_branch_id": "",
            "counts": {
                "open_tasks": 0,
                "branches": {"complete": 0},
            },
        }
        unrelated_tree = {
            "tree_id": "tree_unrelated",
            "title": "Chat: unrelated ui redesign",
            "kind": "system",
            "source": "chat",
            "work_identity_key": "work:redesign-unrelated|terms:redesign|unrelated",
            "work_identity_label": "redesign / unrelated",
            "status": "complete",
            "active_branch_id": "",
            "counts": {
                "open_tasks": 0,
                "branches": {"complete": 0},
            },
        }

        payload = [runtime_ops_chat, runtime_ops_health, unrelated_tree]

        result = CONTROL_WORK_TREES_SERVICE.payload(
            list_visual_trees_fn=lambda limit=None: payload,
            limit=32,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["counts"]["total"], 2)
        self.assertEqual(
            [tree.get("tree_id") for tree in result["trees"]],
            ["tree_chat_runtime_ops", "tree_unrelated"],
        )


if __name__ == "__main__":
    unittest.main()
