# Ed-Fi ODS Integration — Nova Operational Brief

## What this backpack does

This backpack connects Nova to an Ed-Fi ODS (Operational Data Store) v3 instance.
Ed-Fi is the standard data protocol used by most K-12 SIS vendors in the United States —
including Infinite Campus, Skyward, PowerSchool, eSchoolPlus, and ASCENDER.

Every district that uses an Ed-Fi-compliant SIS exposes the same REST API surface.
This backpack makes Nova the operator of that API for whichever district installs it.

---

## Product role (bridge, not full SIS)

This backpack is a **governed data bridge** into the Ed-Fi / TEA IODS bank. It does **not**
replace a SIS or track every state PEIMS submission.

### Field reality (TEA rate limits)

Live IODS **cannot** be hammered with back-to-back full pulls. That forces the architecture:

1. **Local warehouse (SQLite)** holds the full LEA dataset we care about  
   (`runtime/edfi/warehouse/{connection_id}.sqlite3`).
2. **Paced full sync** (daily window or one manual job) pulls **all** matching rows for
   the LEA — not a 25-row sample — into the warehouse.
3. **Reports / tools / Nova** read the warehouse first. Live ODS is for sync only.
4. **Schedule** is configurable (`warehouse_sync_local_hour`, `warehouse_sync_min_gap_hours`).

JSON extracts under `runtime/edfi/extracts/` remain a thin cache for reports; the warehouse
is the durable store.

## The job

1. **Stay connected.** Authenticate via OAuth2 client credentials. Surface connection health
   from the **local** capability profile — not a live poll every few seconds.

2. **Know what's available.** Discover the ODS resource catalog once; store the profile.

3. **Warehouse sync.** On schedule (or explicit `warehouse-sync --force` once): full-LEA
   collect for configured resources (phase 1: **schools**), write SQLite, promote extract.

4. **Answer data questions.** User reports read warehouse/extract; present reader-friendly
   rows via `services.edfi.present`. Never live-scan the state on every click.

5. **Report blockers.** Connection missing, LEA unset, rate-limited sync — clear codes.

---

## What healthy looks like

- `auth.ok = true` — OAuth2 token obtained
- `discovery.ok = true` — metadata endpoint responded with resource list
- `resource_count > 0` — at least one resource discovered
- `district_lea_id` is set and `list_schools` returns at least one school
- Change cursor exists in `runtime/edfi/change_cursors/{connection_id}.json`

---

## What broken looks like

| Blocker code | What it means | What Nova does |
|---|---|---|
| `edfi_connection_config_missing` | No config saved for this connection_id | Tell account_admin to run install |
| `edfi_capability_profile_missing` | Never successfully profiled | Run `run_self_profile` to authenticate and discover |
| `edfi_profile_auth_not_ok` | Last profile run failed auth | Credentials wrong or expired — prompt reconfigure |
| `district_lea_id_missing` | LEA ID not set in config | Tell account_admin to set it in settings |
| `edfi_auth_failed` | OAuth2 token request failed | Check base_url and credentials |
| `edfi_timeout` | Request timed out | Check network path to ODS; increase timeout_sec |
| `edfi_ssl_error` | SSL verification failed | Check verify_ssl setting or CA bundle path |

---

## How district / region scoping works

**TEA client id/secret is usually statewide** — the key can reach many districts in the
state ODS. It is *not* a per-district secret. Nova still requires a **scope policy** at
install (never from the repo):

| `scope_mode` | Who installs | LEA settings |
|--------------|--------------|--------------|
| `single_lea` (default) | One district | `district_lea_id` required (e.g. BISD `031901` / `31901`) |
| `multi_lea` | Region / multi-district | `allowed_lea_ids` list; optional primary `district_lea_id` |

Every data query is scoped to an LEA. On TEA, collection `$filter` is often ignored, so
Nova applies **client-side** district filtering.

- **District mode:** always the one `district_lea_id` (Nova filter on a wide key).
- **Region mode:** same kind of key; Nova only allows LEAs in `allowed_lea_ids`. Pass
  `district_lea_id` / `lea_id` on the query to pick one. Outside the list → denied even
  if the key could see more.
- **LEA forms:** PEIMS `031901` and Ed-Fi `31901` are the same identity (`int` match).

If `list_schools` returns empty after LEA scoping, the LEA ID is wrong. Stop and alert.
Do not unscoped full-state scans casually — TEA will rate-limit.

### Credential access tier (key power)

Install also records `credential_access_tier` as declared by the operator:
`read` | `limited` | `full` — what the **client id/secret** was issued for (app registration),
not “which districts.” This is separate from Nova Shell roles (who may click Run).
Client secret is always supplied at install and stored only under `runtime/` on that machine.

---

## What Nova decides autonomously

- Re-authenticate when the token is within 30 seconds of expiry (before the request fails)
- Retry a failed request once with a fresh token before reporting error
- Cap all reads at `max_rows_hard_cap = 50` regardless of what the caller requests
- Apply redaction profile to strip PII fields not needed for the operation

## What Nova escalates to account_admin

- Credential rotation (client_secret change)
- LEA ID correction
- SSL certificate issues
- Any blocker that requires a settings change

## What Nova escalates to the user

- Empty result sets after a scoped query (district may have no data for that resource)
- Change version gaps (cursor advanced past available data — requires full re-seed)

---

## Change tracking mechanics

The Ed-Fi ODS exposes `/changeQueries/v1/availableChangeVersions` which returns
the newest available change version. Nova stores the last-seen version in
`runtime/edfi/change_cursors/{connection_id}.json`.

On each sync:
1. Read `min_change_version` from cursor file (0 if first sync)
2. Call `changes_since` with `min_change_version`
3. Process results
4. Advance cursor to `next_change_version` returned by the ODS
5. Write updated cursor to disk

If `next_change_version` comes back 0 or null — do not advance. Log a warning.
If the cursor gets ahead of `newest_change_version` — the ODS was reset. Re-seed from 0.

---

## Runtime files Nova owns

```
runtime/edfi/
  edfi_audit.jsonl                          ← append-only operation log
  connections/{connection_id}/
    local_config.json                       ← ODS URL, credentials, LEA ID
  profiles/{connection_id}.json             ← capability profile (resources, auth status)
  change_cursors/{connection_id}.json       ← last seen change version per resource
```

Nova writes these. Nova reads these. Account_admin sets the source values in settings.
The profile is rebuilt by running `install` → `run_self_profile`.

---

## Protocol notes

- Ed-Fi ODS v3 uses OAuth2 client credentials (not authorization code)
- Token endpoint is typically `{base_url}/oauth/token`
- Data API root is typically `{base_url}/data/v3`
- Resources live at `{api_root}/ed-fi/{resourceName}` or `{api_root}/{namespace}/{resourceName}`
- Pagination uses `offset` and `limit` query parameters (no cursor-based pagination)
- Change queries live at `{base_url}/changeQueries/v1/`

---

## What this backpack does NOT do

- No write operations to the ODS (read-only governed lane)
- No PEIMS or TSDS-specific logic (Texas state reporting is a separate backpack)
- No cross-district queries (always scoped to installing district's LEA)
- No PII export without explicit redaction review

---

## Live path (Host v0)

Nova core installs first and can run with **zero** backpacks. Ed-Fi is added later from the
control panel (or CLI) once the environment has settled.

- **Control panel:** view **Backpacks** → select Ed-Fi → paste settings → Save / Install + profile
- **API:** `GET /api/control/backpacks`, actions `backpack_install`, `backpack_settings_save`, `backpack_probe_lea`
- **CLI:** `python scripts/run_backpack.py install edfi --settings <file.json>`
- **Status:** `python scripts/run_backpack.py status edfi --role account_admin`
- **Query:** `python scripts/run_backpack.py query edfi list_schools --role standard_user`
- **Tool:** Nova `edfi_explore` uses `pipeline_id=edfi` via `services.backpack_host` (not the privileged worker).

### Legacy lane

`data_sources/edfi_bisd` is the **legacy** BISD-named pipeline. New districts and new code paths should use **`backpacks/edfi`** (`pipeline_id=edfi`). Keep `edfi_bisd` until an instance is migrated (connection + LEA under backpack settings), then prefer disabling that lane.
