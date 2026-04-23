# NYO System Handoff

Date: 2026-03-30

## Purpose

This document is the operator handoff flow for the current NYO System package candidate.

It provides one practical sequence for install, run, verify, inspect, patch, and stop.

The same sequence applies from either a source checkout or an extracted release zip.

## Handoff Sequence

### 1. Bootstrap

If you are operating from an extracted release package or staged artifact directory, verify it first:

```powershell
.\nova.cmd package-verify .
```

Then bootstrap the package or source checkout:

```powershell
.\nova.cmd install
```

### 2. Validate Base Environment

```powershell
.\nova.cmd doctor
.\nova.cmd runtime-status
```

### 3. Start Runtime

Core runtime:

```powershell
.\nova.cmd run
```

Web UI in a second terminal:

```powershell
.\nova.cmd webui-start --host 127.0.0.1 --port 8080
```

### 4. Verify Operator Surface

Check:

- `http://127.0.0.1:8080/control`
- `nova webui-status --port 8080`
- `nova runtime-status`

### 5. Run Package Confidence Checks

```powershell
.\nova.cmd smoke-base --fix
.\nova.cmd smoke --fix
.\nova.cmd test
```

If the candidate came from the local packaging flow rather than an extracted zip, verify the built artifact directly before handoff:

```powershell
.\nova.cmd package-verify
.\nova.cmd package-ledger --count 5
.\nova.cmd package-status
.\nova.cmd package-readiness
```

After a fresh-machine or staged validation pass is complete, record the result:

```powershell
.\nova.cmd package-promote --result pass --version 2026.03.30.2 --note "validated on operator VM"
```

If the operator completed a filled validation record, promote directly from the record:

```powershell
.\nova.cmd package-promote --record runtime\exports\release_packages\validation_records\nyo-system-base-rc-2026.03.30.2-validation-seed-fix-20260330_161051.md --result pass-with-notes
```

Use the package-readiness gate in [BASE_PACKAGE_READINESS.md](BASE_PACKAGE_READINESS.md) to decide whether the package candidate is acceptable.

### 6. Inspect Runtime State

Useful commands:

```powershell
.\nova.cmd logs
.\nova.cmd policy
.\nova.cmd mem
.\nova.cmd runtime-status
```

### 7. Patch Governance

Patch operations remain governed by the existing patch flow documented in [PATCHING.md](PATCHING.md).

Operator expectation:

- inspect previews before approval
- do not treat local previews or generated artifacts as part of the base package

### 8. Stop Runtime Services

Stop HTTP control plane:

```powershell
.\nova.cmd webui-stop
```

Stop guard/core:

```powershell
.\nova.cmd stop
```

## Handoff Boundaries

This handoff currently assumes:

- source checkout deployment
- Windows PowerShell launcher flow
- operator-managed optional dependencies

It does not yet guarantee:

- one-click binary installation
- automatic model provisioning
- zero-touch deployment on an unknown workstation