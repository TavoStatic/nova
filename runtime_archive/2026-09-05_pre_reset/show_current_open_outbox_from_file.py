import json
from pathlib import Path

path = Path(r'c:\NOVA\runtime\operator_outbox.jsonl')
rows = []
for line in path.read_text(encoding='utf-8', errors='ignore').splitlines():
    if not line.strip():
        continue
    try:
        row = json.loads(line)
    except Exception:
        continue
    if not isinstance(row, dict):
        continue
    if str(row.get('status') or '').lower() in {'resolved', 'dismissed', 'stale'}:
        continue
    rows.append(row)

print('open_count', len(rows))
if rows:
    latest = rows[-1]
    print('latest_id', latest.get('id'))
    print('title', latest.get('title'))
    print('message', latest.get('message'))
    print('severity', latest.get('severity'))
    print('source', latest.get('source'))
    print('payload', json.dumps(latest.get('payload'), indent=2, sort_keys=True))
