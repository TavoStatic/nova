# Nova Ed-Fi Core (V1)

Infrastructure layer for connecting to any Ed-Fi ODS. This package is **not** PEIMS, TSDS, or vendor-specific.

## V1 Golden Rule

```text
services/edfi/ must never import PEIMS, TSDS, Texas, attendance, SPED, or vendor-specific modules.
```

No `get_peims_attendance()`. No Texas field maps. No TSDS codes.

Downstream domain modules (PEIMS, reporting, analytics) consume Ed-Fi Core through its public API and stored capability profiles. They live outside this package.

## Milestone: NOVA-EDFI-001

**Self-Profiling Ed-Fi Connector**

Pass condition:

```text
Given a base URL, client key, and secret,
Nova can authenticate, discover metadata, save a profile,
and return a health payload without touching PEIMS logic.
```

## Package layout (V1)

```text
services/edfi/
  README.md          ← this file
  __init__.py        ← public entry points
  config.py          ← connection config + runtime paths
  auth.py            ← OAuth2 client credentials
  client.py          ← HTTP transport
  discovery.py       ← metadata + capability profile
  diagnostics.py     ← latency, errors, health payload
```

Deferred to later milestones: `resources.py` (CRUD paging), `change_tracking.py` (delta sync), compatibility probe tooling.

## Runtime artifacts

| Path | Purpose |
|------|---------|
| `runtime/edfi/connections/<id>/local_config.json` | Operator-local credentials (never in repo) |
| `runtime/edfi/profiles/<id>.json` | Learned `nova.edfi_capability.v1` profile |
| `runtime/edfi/edfi_audit.jsonl` | Structured probe/auth/discovery events |

## Single gateway rule

**Every Ed-Fi HTTP interaction must go through `EdFiClient`.** No other Nova module should call `requests.get(...)` against an Ed-Fi ODS.

```python
from services.edfi import EdFiClient, connection_config_from_dict

config = connection_config_from_dict({...})
client = EdFiClient(config)
schools = client.get("schools")      # relative resource name
metadata = client.get(config.metadata_url())  # absolute URL also works
```

`auth.py` owns token exchange; `client.py` owns authenticated API calls. Retries, caching, throttling, and version upgrades land in one place.

## Usage (library)

```python
from services.edfi import run_self_profile

result = run_self_profile(
    connection_id="district-main",
    base_url="https://district.ed-fi.org",
    client_id="...",
    client_secret="...",
)
# result["health"] — diagnostics payload
# result["profile_path"] — saved capability profile
```

## Usage (Monday probe CLI)

```bash
python scripts/run_edfi_profile.py \
  --connection-id district-main \
  --base-url https://district.ed-fi.org \
  --client-id ... \
  --client-secret ...
```

Exit code `0` means auth + metadata discovery succeeded. `watch` (sample GET failed) exits `1` but still saves a partial capability profile with per-stage results under `discovery.stages`.

## Hardening (pre-integration)

| Area | Behavior |
|------|----------|
| Config | Specific codes for missing URL/id/secret, invalid JSON, bad SSL options |
| Auth | Classified 401/403, timeout, DNS, SSL, connection errors |
| Discovery | `discovery.stages.metadata` and `discovery.stages.sample_get` show partial success |
| Audit | `runtime/edfi/edfi_audit.jsonl` — one JSON object per line, sorted keys |

## Ed-Fi SOCKS (planned)

Automatic compatibility probing (version, paging, change versions) builds on this milestone. V1 proves connect → discover → profile → health.