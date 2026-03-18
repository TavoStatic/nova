# Nova searXNG Setup

This enables API-style web search for Nova using a self-hosted searXNG instance.

## 1. Create local searXNG config

Create `runtime/searxng/settings.yml`:

```yaml
use_default_settings: true

general:
  instance_name: "Nova SearXNG"

search:
  formats:
    - html
    - json

server:
  limiter: false
  public_instance: false
  secret_key: "replace-this-with-your-own-random-secret"
```

## 2. Start searXNG locally

```powershell
docker run --name searxng -d -p 8081:8080 ^
  -v "C:/Nova/runtime/searxng/settings.yml:/etc/searxng/settings.yml" ^
  -e SEARXNG_BASE_URL=http://127.0.0.1:8081/ ^
  searxng/searxng
```

Verify:

```powershell
curl "http://127.0.0.1:8081/search?q=test&format=json"
```

## 3. Configure Nova

Set these `policy.json` values under `web`:

```json
"search_provider": "searxng",
"search_api_endpoint": "http://127.0.0.1:8081/search"
```

## Notes

- In this workspace, `nova_http.py` already uses host port `8080`, so binding searXNG to `8081` avoids a host-port conflict.
- SearXNG can return `403` for `format=json` if JSON output is not enabled.
- Nova falls back to HTML search when the API provider is unavailable.
- allowlist filtering still applies via `web.allow_domains`.