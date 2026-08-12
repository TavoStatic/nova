from __future__ import annotations

import autonomy_maintenance as am
import work_tree

tree_id = "tree_f7f132c4"
branch_id = "branch_e4817a26"
task_id = "task_c55640e5"
tool = "release_validation_run"

payload = work_tree.get_visual_tree_data(tree_id)
print(
    "visual",
    {
        "status": (payload or {}).get("status"),
        "kind": (payload or {}).get("kind"),
        "next": (payload or {}).get("next_step"),
    },
)
pin = am._resolve_targeted_work_pin(
    payload or {}, branch_target=branch_id, task_target=task_id
)
print("pin", pin)
branch = work_tree.get_branch(branch_id)
print(
    "branch",
    branch.branch_id if branch else None,
    getattr(branch, "tree_id", None),
    getattr(branch, "preferred_tool", None),
    getattr(branch, "status", None),
)
tasks = work_tree.list_branch_tasks(branch_id) if branch else []
for t in tasks:
    print(
        "task",
        t.task_id,
        t.status,
        t.title[:60],
        (t.meta or {}).get("expected_tool"),
    )
print(
    "pinned",
    am._pin_active_work_payload(
        payload or {},
        branch_target=branch_id,
        task_target=task_id,
        tool_target=tool,
    )
    is not None,
)
cands = am._resolve_targeted_active_work_candidates(
    target_tree_id=tree_id,
    target_branch_id=branch_id,
    target_task_id=task_id,
    target_tool=tool,
)
print("cands", len(cands), cands[0].get("next_step") if cands else None)
