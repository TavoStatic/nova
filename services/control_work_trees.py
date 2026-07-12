from __future__ import annotations

from services.work_tree_pressure_snapshot import build_work_tree_pressure_snapshot_from_module


class ControlWorkTreesService:
    """Own HTTP work-tree payload shaping outside the HTTP transport shell."""

    @staticmethod
    def _branch_total(tree_payload: dict) -> int:
        counts = tree_payload.get("counts") if isinstance(tree_payload.get("counts"), dict) else {}
        branch_counts = counts.get("branches") if isinstance(counts.get("branches"), dict) else {}
        return sum(int(value or 0) for value in branch_counts.values())

    def _semantic_family_key(self, tree_payload: dict) -> str:
        if not isinstance(tree_payload, dict):
            return ""
        counts = tree_payload.get("counts") if isinstance(tree_payload.get("counts"), dict) else {}
        status = str(tree_payload.get("status") or "").strip().lower()
        open_tasks = int(counts.get("open_tasks") or 0)
        if status != "complete" or open_tasks > 0 or self._branch_total(tree_payload) > 0:
            return ""
        kind = str(tree_payload.get("kind") or "").strip().lower()
        source = str(tree_payload.get("source") or "").strip().lower()
        if kind != "system" or source not in {"chat", "health", "maintenance"}:
            return ""
        text = " ".join(
            [
                str(tree_payload.get("title") or ""),
                str(tree_payload.get("work_identity_key") or ""),
                str(tree_payload.get("work_identity_label") or ""),
            ]
        ).lower()
        token_hits = {
            token
            for token in ("runtime", "health", "queue", "pressure", "heartbeat", "guard", "inspect", "monitor", "verify", "check", "system")
            if token in text
        }
        if "runtime" in token_hits and len(token_hits) >= 3:
            return "semantic:runtime-ops"
        if {"health", "system"} <= token_hits and len(token_hits) >= 3:
            return "semantic:runtime-ops"
        return ""

    def _priority_tree(self, tree_payload: dict) -> bool:
        if not isinstance(tree_payload, dict):
            return False
        kind = str(tree_payload.get("kind") or "").strip().lower()
        title = str(tree_payload.get("title") or "").strip().lower()
        return kind in {"patch_queue", "generated_queue"} or title.startswith(("patch queue:", "generated queue:"))

    def _dedupe_key(self, tree_payload: dict) -> str:
        if not isinstance(tree_payload, dict):
            return ""
        semantic_family_key = self._semantic_family_key(tree_payload)
        if semantic_family_key:
            return semantic_family_key
        work_identity_key = str(tree_payload.get("work_identity_key") or "").strip().lower()
        if work_identity_key:
            return f"identity:{work_identity_key}"
        kind = str(tree_payload.get("kind") or "").strip().lower()
        source = str(tree_payload.get("source") or "").strip().lower()
        title = str(tree_payload.get("title") or "").strip().lower()
        if kind and source and title:
            return f"shape:{kind}|{source}|{title}"
        return ""

    def _dedupe_visible_trees(self, items: list[dict]) -> list[dict]:
        kept: list[dict] = []
        seen: set[str] = set()
        for item in list(items or []):
            if not isinstance(item, dict):
                continue
            key = self._dedupe_key(item)
            if key and key in seen:
                continue
            if key:
                seen.add(key)
            kept.append(item)
        return kept

    @staticmethod
    def _compact_value(value, *, depth: int = 0, max_depth: int = 3):
        if depth >= max_depth:
            if isinstance(value, str):
                return value[:300]
            if isinstance(value, (int, float, bool)) or value is None:
                return value
            return str(value)[:300]
        if isinstance(value, dict):
            compacted: dict = {}
            for idx, (key, item) in enumerate(value.items()):
                if idx >= 40:
                    break
                compacted[key] = ControlWorkTreesService._compact_value(
                    item,
                    depth=depth + 1,
                    max_depth=max_depth,
                )
            return compacted
        if isinstance(value, list):
            return [
                ControlWorkTreesService._compact_value(item, depth=depth + 1, max_depth=max_depth)
                for item in value[:40]
            ]
        if isinstance(value, str):
            return value[:300]
        return value

    def _compact_tree_payload(self, tree_payload: dict) -> dict:
        if not isinstance(tree_payload, dict):
            return tree_payload
        compacted = dict(tree_payload)
        nodes = compacted.get("nodes")
        if isinstance(nodes, list):
            compacted_nodes: list[dict] = []
            for node in nodes:
                if not isinstance(node, dict):
                    compacted_nodes.append(node)
                    continue
                compacted_node = dict(node)
                for heavy_key in (
                    "source_payload",
                    "meta",
                    "payload",
                    "task",
                    "tasks",
                    "evidence",
                    "details",
                ):
                    if heavy_key in compacted_node:
                        compacted_node[heavy_key] = self._compact_value(compacted_node.get(heavy_key))
                compacted_nodes.append(compacted_node)
            compacted["nodes"] = compacted_nodes
        if "source_payload" in compacted:
            compacted["source_payload"] = self._compact_value(compacted.get("source_payload"))
        return compacted

    def payload(self, *, list_visual_trees_fn, limit: int = 32) -> dict:
        try:
            all_trees = list_visual_trees_fn(None)
        except Exception as exc:
            return {
                "ok": False,
                "error": f"work_tree_payload_failed:{exc}",
                "counts": {"total": 0, "active": 0},
                "trees": [],
            }

        full_tree_list = list(all_trees) if isinstance(all_trees, list) else []
        if limit is not None:
            safe_trees = full_tree_list[: max(1, int(limit or 1))]
            seen_tree_ids = {str(item.get("tree_id") or "").strip() for item in safe_trees if isinstance(item, dict)}
            for tree_payload in full_tree_list:
                if not self._priority_tree(tree_payload):
                    continue
                tree_id = str((tree_payload or {}).get("tree_id") or "").strip()
                if not tree_id or tree_id in seen_tree_ids:
                    continue
                safe_trees.append(tree_payload)
                seen_tree_ids.add(tree_id)
        else:
            safe_trees = full_tree_list

        safe_trees = self._dedupe_visible_trees(safe_trees)
        safe_trees = [self._compact_tree_payload(tree_payload) for tree_payload in safe_trees]

        total = len(safe_trees)
        active = 0
        branch_total = 0
        open_task_total = 0
        working_total = 0
        pending_total = 0
        blocked_total = 0
        complete_total = 0

        for tree_payload in safe_trees:
            if not isinstance(tree_payload, dict):
                continue
            counts = tree_payload.get("counts") if isinstance(tree_payload.get("counts"), dict) else {}
            branch_counts = counts.get("branches") if isinstance(counts.get("branches"), dict) else {}
            status = str(tree_payload.get("status") or "").strip().lower()
            active_branch_id = str(tree_payload.get("active_branch_id") or "").strip()
            if active_branch_id or status == "active":
                active += 1
            branch_total += self._branch_total(tree_payload)
            open_task_total += int(counts.get("open_tasks") or 0)
            working_total += int(branch_counts.get("active") or 0)
            pending_total += int(branch_counts.get("ready") or 0)
            blocked_total += int(branch_counts.get("blocked") or 0)
            complete_total += int(branch_counts.get("complete") or 0)

        return {
            "ok": True,
            "counts": {
                "total": total,
                "active": active,
                "branches": branch_total,
                "open_tasks": open_task_total,
                "working": working_total,
                "pending": pending_total,
                "blocked": blocked_total,
                "complete": complete_total,
            },
            "trees": safe_trees,
        }

    def pressure_payload(self, *, work_tree_module) -> dict:
        try:
            snapshot = build_work_tree_pressure_snapshot_from_module(work_tree_module)
        except Exception as exc:
            return {
                "ok": False,
                "error": f"work_tree_pressure_payload_failed:{exc}",
                "status": "unknown",
                "tree_count": 0,
                "active_tree_count": 0,
                "branch_count": 0,
                "open_task_count": 0,
                "blocked_branch_count": 0,
                "operator_hold_branch_count": 0,
                "self_repair_blocked_branch_count": 0,
                "self_repair_observing_branch_count": 0,
                "observing_branch_count": 0,
                "latent_root_signal_count": 0,
                "release_stale_ready_count": 0,
            }
        return {"ok": True, **snapshot}


CONTROL_WORK_TREES_SERVICE = ControlWorkTreesService()
