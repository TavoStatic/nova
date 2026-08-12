import sqlite3, json, urllib.request
c = sqlite3.connect(r"runtime/_internal/work_tree.db")
rows = c.execute(
    """
    SELECT t.title, t.status, b.title, w.title
    FROM work_tree_tasks t
    JOIN work_tree_branches b ON b.branch_id = t.branch_id
    JOIN work_trees w ON w.tree_id = b.tree_id
    WHERE w.status = 'active'
      AND t.status IN ('open', 'blocked', 'ready', 'in_progress')
    """
).fetchall()
print("open_tasks", len(rows))
for r in rows:
    print(" -", r[1], "|", r[0], "| branch:", r[2])
d = json.loads(urllib.request.urlopen("http://127.0.0.1:8080/api/control/status/surfaces", timeout=45).read())
print("work_tree_open_task_count", d.get("work_tree_open_task_count"))
print("work_tree_blocked_branch_count", d.get("work_tree_blocked_branch_count"))
print("webui", d.get("webui"))
print("guard running", (d.get("guard") or {}).get("running"))
print("core_running", d.get("core_running"))
for k in sorted(d):
    if "health" in k.lower() and not isinstance(d[k], (dict, list)):
        print(k, d[k])
