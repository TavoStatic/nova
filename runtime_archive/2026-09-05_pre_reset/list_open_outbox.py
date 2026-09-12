import json
from pathlib import Path

path = Path(r'c:\NOVA\runtime\operator_outbox.jsonl')
open_rows = []
for idx, line in enumerate(path.read_text(encoding='utf-8', errors='ignore').splitlines(), start=1):
    if not line.strip():
        continue
    try:
        row = json.loads(line)
    except Exception:
        continue
    if not isinstance(row, dict):
        continue
    status = str(row.get('status') or '').strip().lower()
    if status in {'resolved', 'dismissed', 'stale'}:
        continue
    open_rows.append((idx, row))

print('open_count', len(open_rows))
for idx, row in open_rows:
    print('line', idx)
    print('id', row.get('id'))
    print('title', row.get('title'))
    print('message', row.get('message'))
    print('status', row.get('status'))
    print('source', row.get('source'))
    print('payload.request_kind', (row.get('payload') or {}).get('request_kind'))
    print('payload.source_type', (row.get('payload') or {}).get('source_type'))
    print('---')
