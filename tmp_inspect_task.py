import sqlite3, json
conn = sqlite3.connect(r"runtime/_internal/work_tree.db")
conn.row_factory = sqlite3.Row
rows = conn.execute("SELECT task_id, title, status, branch_id, meta_json FROM work_tree_tasks WHERE status IN ('open','blocked','ready','in_progress') ORDER BY created_at").fetchall()
print('COUNT', len(rows))
for r in rows:
    print('TASK', dict(r))
    meta = json.loads(r['meta_json'] or '{}')
    print('META_KEYS', sorted(meta.keys()))
    print('EXPECTED_TOOL', meta.get('expected_tool'))
    print('ALLOWED', meta.get('allowed_tools'))
    print('TOOL_ARGS', meta.get('tool_args'))
    br = conn.execute("SELECT branch_id, title, source_payload_json, tool_state_json FROM work_tree_branches WHERE branch_id=?", (r['branch_id'],)).fetchone()
    print('BRANCH', dict(br))
    print('---')
