# Nova-server-side

Date: 2026-06-25

## Purpose

`Nova-server-side` is the infrastructure layer that fronts and supports Nova without replacing Nova core runtime behavior.

This layer exists to avoid rebuilding solved web infrastructure while keeping Nova as the source of truth for control-plane logic, policy actions, and runtime orchestration.

## Scope

Nova-server-side is responsible for:

- HTTP front-door concerns (hostnames, ports, TLS termination)
- Reverse-proxy routing into Nova WebUI/API (`http://127.0.0.1:8080`)
- Optional static landing pages and operator shortcuts
- Startup ordering and readiness checks for supporting processes

Nova-server-side is not responsible for:

- Re-implementing Nova control APIs in PHP or another stack
- Replacing Nova runtime orchestration (`nova_guard.py`, `nova_http.py`, `nova_core.py`)
- Splitting Nova policy/state ownership across multiple app servers

## Operating Model

1. Nova remains the application server and control API owner.
2. Nova-server-side acts as the front-door layer.
3. Requests for `/control` and `/api/control/*` are proxied to Nova.
4. Support services are treated as optional dependencies, not hard runtime requirements.

## Minimal Extraction Set (from UniServerZ)

Use only what is needed:

- Apache runtime and config (`core/apache2`)
- Vhost patterns (`vhosts`)
- TLS material and cert tooling (`ssl`, Apache cert paths)
- Optional static web root scaffolding (`www`)

Do not pull by default:

- PHP runtime (`core/php83`)
- MySQL runtime (`core/mysql`)
- Mail stack (`core/msmtp`)
- Controller wrappers that attempt to own Nova internals

## Dependency Position

- Docker is optional and not required by Nova-server-side.
- Nova should run natively as Python processes.
- Search/model backends may remain external dependencies, but container orchestration is not required.

## Rollout Rules

1. Keep Nova direct URL operational first (`127.0.0.1:8080`).
2. Add front-door proxy with no behavior change.
3. Validate `/control` and `/api/control/status` through proxy.
4. Enable TLS/hostnames after parity is proven.
5. Keep rollback path: bypass proxy and hit Nova directly.

## Acceptance Criteria

Nova-server-side is considered successful when:

- Nova control page remains fully functional through front-door proxy
- Control APIs return identical payloads compared to direct Nova access
- Docker is not required for Nova boot path
- Startup and health checks are deterministic and operator-visible
