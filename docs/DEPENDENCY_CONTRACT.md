<!--
NOVA_DOC
category: subsystem
authority: active_working
last_session: 2026-08-05
last_agent: codex
session_state: needs_update
next_step: verify contract still holds
open: none
-->

# Nova Dependency Contract

Date: 2026-05-18
Last verified: 2026-05-20

Verification note: dependencies are validated by `nova install` from the current ledger-owned extracted package during release validation. Package bootstrap remains source-first and does not lock every transitive dependency version. Git LFS is also required for clean source checkout of the tracked Piper assets.

## Purpose

This document is the canonical dependency contract for the current Nova base package.

It defines what is required to bootstrap the package, what is bundled inside the package, and which external services are only needed for specific runtime tiers.

## Contract Levels

### Level 1: Bootstrap Required

These are required to run `nova install` and create a working local package environment.

- Windows with PowerShell
- Python 3.11 or 3.12 with `venv` support on `PATH` or available through the Windows `py` launcher
- network access sufficient for `pip install -r requirements.txt`

### Level 2: Bundled In The Current Base Package

These ship inside the current package artifact.

- runtime source and launcher files
- docs, tests, templates, and static assets
- `requirements.txt`
- `policy.json`
- Piper runtime assets currently tracked under `piper/`

Current decision:

- Piper remains bundled until there is a trustworthy bootstrap-fetch path for those assets
- Piper assets are tracked by Git LFS pointers; release/development machines need Git LFS installed so the pointers resolve cleanly

### Level 3: Installed Python Dependencies

`nova install` installs the complete package set from the root [`requirements.txt`](../requirements.txt). That manifest is the current authority for package names and version bounds, including the web, voice, imaging, scheduling, database, and Nova Shell dependencies. Inspect it before changing or auditing a dependency; this document does not duplicate a versioned package inventory.

Current contract:

- these are treated as part of the base runtime environment, not optional extras
- if Nova later splits feature tiers, that should happen as an explicit packaging decision rather than silent drift

### Level 4: External Runtime Services

These are not bundled by `nova install` and remain operator-provided.

#### Ollama

Required for:

- model-backed runtime flows via `nova run`
- live HTTP chat/model responses
- `health.py check`
- `nova smoke-runtime --fix`
- `nova smoke --fix`

Not required for:

- `nova install`
- `nova doctor`
- `nova runtime-status`
- `nova test`

Current expectation:

- Ollama should be installed on `PATH`
- the API should be reachable at `http://127.0.0.1:11434`

#### SearXNG

Required only when the active search provider is switched to `searxng`.

Not required for base bootstrap, compact regression, or default package installation.

#### Operator Secrets And Credentials

Deployment-specific credentials, chat users, and environment overrides remain operator inputs and are not part of the package payload.

## Command-Level Expectations

| Command | Required Dependency Tier |
| --- | --- |
| `nova install` | Level 1 + Level 3 |
| `nova doctor` | Level 2 + installed environment from `nova install` |
| `nova runtime-status` | Level 2 |
| `nova smoke-base --fix` | Level 2 + Level 3 |
| `nova test` | Level 2 + Level 3 |
| `nova smoke --fix` | Level 2 + Level 3 + Ollama |
| `nova smoke-runtime --fix` | Level 2 + Level 3 + Ollama |
| `nova run` | Level 2 + Level 3 + Ollama |
| `nova webui-start` | Level 2 + Level 3; Ollama required for model-backed chat behavior |

## Current Packaging Decision

- keep Ollama external rather than trying to bundle model runtime installation into the base package
- keep SearXNG optional and provider-gated
- keep Piper bundled for now

This keeps the current package honest: a bootstrap-ready local runtime, not a zero-configuration all-services appliance.
