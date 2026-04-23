# NYO System Bootstrap

Date: 2026-03-30

## Purpose

This document is the canonical fresh-machine bootstrap path for the current NYO System base package.

It describes the supported source-first install flow that turns either a fresh checkout or an extracted release zip into a runnable local runtime.

Current packaging reality:

- this is a source package with a bootstrap command, not a binary installer
- the canonical bootstrap entrypoint is `nova install`
- optional local services such as Ollama and SearXNG may still be supplied by the operator environment

## Minimum Requirements

- Windows with PowerShell available
- Python 3 with `venv` support on `PATH`
- a writable package root directory containing the NYO System files

Optional but recommended:

- Ollama on `PATH` for local chat/model-backed runtime flows
- bundled Piper assets kept intact for voice output
- SearXNG only if the deployment wants that search provider

## Bootstrap Path

From the package root:

```powershell
.\nova.cmd install
```

What `nova install` does now:

1. creates `.venv` if it does not exist
2. upgrades `pip`
3. installs dependencies from `requirements.txt`
4. runs `doctor.py --fix`

## Post-Install Validation

After bootstrap completes, run:

```powershell
.\nova.cmd doctor
.\nova.cmd runtime-status
```

Expected result:

- doctor exits cleanly
- runtime status shows no unexpected stale state before launch

## First Launch

Start the runtime core:

```powershell
.\nova.cmd run
```

Start the web UI in a separate shell:

```powershell
.\nova.cmd webui-start --host 127.0.0.1 --port 8080
```

Then verify the control room:

- `http://127.0.0.1:8080/control`

## Smoke Validation

Once bootstrap and basic launch are clean, run:

```powershell
.\nova.cmd smoke-base --fix
```

This is the minimum base-package confidence check for the current source package.

For the extended model-backed runtime gate, run:

```powershell
.\nova.cmd smoke --fix
```

Current constraint:

- `nova smoke --fix` requires Ollama to be installed, reachable on `127.0.0.1:11434`, and able to answer the health probe

## Optional Runtime Dependencies

### Ollama

If Ollama is not installed, install and provision the models required by the current policy/runtime setup.

The package bootstrap does not install Ollama for you.

### Piper

Voice output depends on the shipped `piper/` assets currently tracked in the repo.

If those assets are missing, runtime text features can still work, but voice output may remain unavailable.

### SearXNG

Only required if the operator switches search policy to `searxng`.

The base package does not require SearXNG for initial bootstrap.

## Failure Handling

If `nova install` fails:

1. verify Python is installed and available on `PATH`
2. rerun `.\nova.cmd doctor`
3. inspect `policy.json`, `runtime/`, and `logs/` creation
4. resolve missing optional dependencies only if the target workflow requires them

## Scope

This bootstrap path covers the current base package only.

It does not claim:

- a frozen installer build
- zero-configuration model provisioning
- cross-platform packaging parity

Those are later productization steps.