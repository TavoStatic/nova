import json
import urllib.request

url = 'http://127.0.0.1:8080/api/control/status'
raw = urllib.request.urlopen(url, timeout=10).read().decode('utf-8')
data = json.loads(raw)

print('operator_outbox_open_count', data.get('operator_outbox_open_count'))
print('operator_outbox_latest_open_id', data.get('operator_outbox_latest_open_id'))
print('operator_outbox_latest_open', json.dumps(data.get('operator_outbox_latest_open'), indent=2, sort_keys=True))
print('operator_outbox', json.dumps(data.get('operator_outbox'), indent=2, sort_keys=True))
