# Nova Packaging Matrix

Date: 2026-03-25

## Purpose

This file is the canonical packaging boundary for Nova.

It answers one practical question:

What is shipped as part of the base package, what is expected to be local or generated, and what is operator-provided?

## Category Definitions

### Shipped Source

Tracked code and documentation that define the runtime, interfaces, contracts, tooling, tests, and launch flows.

### Shipped Assets

Tracked non-source files that the current repo treats as part of the runnable package because there is not yet a documented bootstrap path that recreates them.

### Generated Local State

Machine-local files created by running Nova. These are not source of truth and should not be part of the portable package payload.

### Disposable Runtime Artifacts

Logs, caches, snapshots, previews, and temporary outputs that may be deleted or regenerated without changing the package definition.

### Operator-Provided Inputs

Inputs intentionally supplied by the operator or deployment environment, rather than bundled silently into the public base package.

## Packaging Matrix

| Path / Class | Category | Ship In Base Package | Notes |
| --- | --- | --- | --- |
| `*.py`, `nova.cmd`, `nova.ps1`, `run.py`, `health.py`, `doctor.py` | Shipped source | Yes | Core runtime, launchers, operator entrypoints |
| `docs/` | Shipped source | Yes | Canonical contracts, architecture, operations, package guidance |
| `tests/` | Shipped source | Yes | Validation surface for package integrity |
| `tools/`, `TOOL_MANIFEST.json` | Shipped source | Yes | Tool contract and registry surface |
| `templates/`, `static/` | Shipped source | Yes | Browser runtime console and operator-console UI assets |
| `policy.example.json` | Shipped source | Yes | Example/default policy template |
| `policy.json` | Shipped source | Yes, with care | Current repo treats it as part of the runnable package; environment-specific deployments may override it later |
| `capabilities.json` | Shipped source | Yes | Declared capability inventory |
| `scripts/` | Shipped source | Yes | Smoke, diagnostics, session replay, probes, and support tooling |
| `nova_safety_envelope.py`, `kidney.py`, `autonomy_maintenance.py`, `subconscious_runner.py`, related subconscious modules | Shipped source | Yes | Runtime governance, maintenance orchestration, and unattended scenario generation |
| `piper/`, `tts/` shipped runtime assets | Shipped assets | Yes, for now | Keep tracked until bootstrap/download path exists for recreating them |
| `.venv/` | Generated local state | No | Local environment only |
| `runtime/` | Generated local state | No | Runtime identity, heartbeat, session state, audits, exports |
| `logs/` | Generated local state | No | Machine-local execution logs |
| `memory/` | Generated local state | No | Local identity and learned-state files |
| `nova_memory.sqlite` | Generated local state | No | Local memory database |
| `knowledge/web/` | Generated local state | No | Downloaded web snapshots and gathered source material |
| `__pycache__/`, `tests/__pycache__/` | Disposable runtime artifacts | No | Interpreter cache only |
| `updates/previews/` | Disposable runtime artifacts | No | Review-time preview artifacts |
| `updates/*.zip`, local patch proposals, snapshots | Disposable runtime artifacts | No | Generated upgrade artifacts, not base package definition |
| `runtime/test_sessions/pending_review/`, `runtime/test_sessions/quarantine/`, `runtime/test_sessions/promotion_audit.jsonl` | Disposable runtime artifacts | No | Safety-envelope governance outputs and review queues |
| `runtime/kidney/` | Disposable runtime artifacts | No | Kidney status, protect patterns, snapshots, and archives |
| `full_suite_out.txt`, `*.log`, ad hoc output captures | Disposable runtime artifacts | No | Debug output only |
| `knowledge/packs/*` active pack content | Operator-provided inputs | No by default | Optional domain extension points loaded explicitly by operators |
| `knowledge/peims/`, `knowledge/peims_knowledge_pack.zip` | Operator-provided inputs | No | Public repo no longer treats PEIMS content as bundled product knowledge |
| chat users, control credentials, env vars | Operator-provided inputs | No | Deployment-specific auth and secrets |
| external model/runtime backends such as local Ollama availability | Operator-provided inputs | No | Runtime dependency supplied by the deployment environment |

## Current Policy Summary

Base-package intent today is:

- ship the runtime, contracts, UI surfaces, tools, tests, and current required bundled assets
- keep machine-local state out of version control and out of the portable package boundary
- treat domain specialization as explicit operator input rather than hidden bundled knowledge
- keep safety-envelope and kidney governance logs as local runtime artifacts, not package payload
- build the distributable candidate as a source-bootstrap zip via `nova package-build`

## Important Exceptions

### Piper / TTS Assets

These are still treated as shipped assets because the repo does not yet have a documented bootstrap/download path that recreates them reliably.

When that bootstrap path exists, they can move from `Shipped Assets` to `Bootstrap-Fetched Assets` or another local/runtime category in a separate packaging decision.

### Policy Files

`policy.json` is currently part of the runnable repo state, but longer term it may split into:

- shipped default policy
- operator override policy
- environment-specific secure values

That split is not final yet, so this matrix records current reality rather than an aspirational future state.

## What This Matrix Still Does Not Solve

This matrix defines the boundary, but not future installer formats beyond the current source-bootstrap zip.

The remaining work is:

1. continued enforcement so new generated/runtime files do not drift back into the shipped boundary
2. release-candidate validation of the produced zip artifact on a fresh machine or VM
3. later decision on whether NYO System also needs a frozen installer or another higher-convenience artifact

## Related Docs

- `docs/BASE_PACKAGE_READINESS.md`
- `docs/BOOTSTRAP.md`
- `docs/DEPENDENCY_CONTRACT.md`
- `docs/HANDOFF.md`
- `docs/OPERATIONS.md`
- `docs/RELEASE_ARTIFACT.md`
- `docs/PATCHING.md`