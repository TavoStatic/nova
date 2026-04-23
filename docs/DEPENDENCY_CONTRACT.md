# NYO System Dependency Contract

Date: 2026-03-30

## Purpose

This document is the canonical dependency contract for the current NYO System base package.

It defines what is required to bootstrap the package, what is bundled inside the package, and which external services are only needed for specific runtime tiers.

## Contract Levels

### Level 1: Bootstrap Required

These are required to run `nova install` and create a working local package environment.

- Windows with PowerShell
- Python 3 with `venv` support available on `PATH`
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

### Level 3: Installed Python Dependencies

`nova install` currently installs the following package set from `requirements.txt`:

- `requests`
- `psutil`
- `faster-whisper`
- `sounddevice`
- `scipy`
- `pyttsx3`

Current contract:

- these are treated as part of the base runtime environment, not optional extras
- if NYO System later splits feature tiers, that should happen as an explicit packaging decision rather than silent drift

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