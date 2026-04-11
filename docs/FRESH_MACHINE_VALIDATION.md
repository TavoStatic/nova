# NYO System Fresh Machine Validation

Date: 2026-03-30

## Purpose

This checklist is the canonical release-candidate validation flow for a built NYO System artifact on a clean Windows machine or VM.

Use it together with [RELEASE_ARTIFACT.md](RELEASE_ARTIFACT.md) and record the result in [RC_VALIDATION_TEMPLATE.md](RC_VALIDATION_TEMPLATE.md).

## Pre-Validation Inputs

- release zip produced by `nova package-build`
- matching prefilled validation seed from `runtime/exports/release_packages/validation_records/` when available
- target Windows machine or VM
- confirmation whether Ollama is expected in the target deployment

## Validation Flow

### 1. Extract The Artifact

- extract the zip to a writable folder
- open PowerShell in the extracted package root

### 2. Bootstrap The Package

```powershell
.\nova.cmd package-verify .
.\nova.cmd install
```

Expected result:

- package verification passes against the extracted package root
- `.venv` is created
- dependencies install successfully
- `doctor --fix` completes without required failures

### 3. Base Validation

```powershell
.\nova.cmd doctor
.\nova.cmd runtime-status
.\nova.cmd smoke-base --fix
.\nova.cmd test
```

Expected result:

- doctor passes
- runtime-status is readable and scoped to the extracted package root
- base smoke passes
- compact regression passes

### 4. Operator Surface Validation

```powershell
.\nova.cmd run
```

In a second shell:

```powershell
.\nova.cmd webui-start --host 127.0.0.1 --port 8080
```

Expected result:

- `/control` loads
- runtime status tiles populate
- no obvious stale-process leakage from other local checkouts

### 5. Extended Runtime Validation

Run this only when Ollama-backed runtime behavior is part of the release target:

```powershell
.\nova.cmd smoke --fix
```

Expected result:

- runtime smoke passes
- Ollama dependency is available and healthy

## Exit Conditions

The candidate is acceptable only when:

- base validation is green
- operator surface validation is acceptable
- extended runtime validation is green when applicable
- all deviations are recorded in the RC validation record

After the record is complete, append the outcome to the release ledger from the packaging workspace:

```powershell
.\nova.cmd package-promote --result pass-with-notes --version 2026.03.30.2 --note "recorded from fresh machine checklist"
.\nova.cmd package-promote --record runtime\exports\release_packages\validation_records\nyo-system-base-rc-2026.03.30.2-validation-seed-fix-20260330_161051.md --result pass-with-notes
```