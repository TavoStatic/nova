# NYO System Release Artifact

Date: 2026-03-30

## Purpose

This document defines the current base-package release artifact for NYO System.

## Canonical Artifact

The current release candidate format is:

- a source-bootstrap zip produced by `nova package-build`

This artifact contains the runnable source package and bundled assets, but excludes machine-local state and disposable runtime artifacts.

It is intentionally not:

- a frozen executable build
- an MSI installer
- an all-dependencies appliance image

## Build Command

From the package root:

```powershell
.\nova.cmd package-build
```

Optional arguments:

```powershell
.\nova.cmd package-build --label rc1 --version 2026.03.30 --channel rc
.\nova.cmd package-build --output runtime\exports\release_packages
.\nova.cmd package-build --channel rc
.\nova.cmd package-verify
.\nova.cmd package-ledger --count 5 --event build
.\nova.cmd package-status
.\nova.cmd package-readiness
.\nova.cmd package-promote --result pass --version 2026.03.30.2 --note "validated on VM"
.\nova.cmd package-promote --record runtime\exports\release_packages\validation_records\nyo-system-base-rc-2026.03.30.2-validation-seed-fix-20260330_161051.md --result pass-with-notes
.\nova.cmd package-verify runtime\exports\release_packages\nyo-system-base-rc-2026.03.30-launcher-check-20260330_152355.zip
```

Build output:

- staged package directory under `runtime/exports/release_packages/_stage/`
- zip artifact under `runtime/exports/release_packages/`
- generated `package_manifest.json` inside the staged package and zip
- release metadata including version, channel, label, and validation-profile commands inside `package_manifest.json`
- appended release build ledger at `runtime/exports/release_packages/release_ledger.jsonl`
- generated prefilled validation record seed under `runtime/exports/release_packages/validation_records/`

If `--version` is omitted, `nova package-build` now generates a monotonic daily version token for the selected channel:

- first build of the day: `YYYY.MM.DD`
- later same-day builds: `YYYY.MM.DD.1`, `YYYY.MM.DD.2`, and so on

Explicit `--version` still overrides the auto-generated token.

## Verification Command

Use the verifier after each candidate build:

```powershell
.\nova.cmd package-verify
.\nova.cmd package-ledger --count 10
.\nova.cmd package-status
.\nova.cmd package-readiness
.\nova.cmd package-promote --result pass-with-notes --version 2026.03.30.2 --note "fresh machine pass; Ollama not installed"
```

Behavior:

- with no path, verifies the latest zip under `runtime/exports/release_packages/`
- with a path, verifies the selected zip or extracted stage/package directory
- checks `package_manifest.json`, required package files, and referenced validation docs
- `package-ledger` shows recent build or promotion records, including validation result when present
- `package-status` reports the latest built artifact and whether it remains build-only or has a recorded promotion outcome
- `package-readiness` reports whether the latest candidate is still waiting on verification, waiting on promotion, blocked, or ready to ship
- `package-promote` appends the final RC decision back into the ledger after an operator completes validation
- `package-promote --record ...` can read artifact/version/result/owner details from a completed validation markdown record

## Artifact Contents

Included:

- tracked source files
- docs
- tests
- templates and static assets
- `requirements.txt`
- `policy.json`
- bundled Piper assets

Excluded:

- `.venv`
- `runtime/`
- `logs/`
- `memory/`
- update previews and snapshots
- interpreter caches
- ad hoc local session and output files

## Install After Extract

After extracting the zip, enter the extracted package root and run:

```powershell
.\nova.cmd package-verify .
.\nova.cmd install
.\nova.cmd doctor
.\nova.cmd runtime-status
.\nova.cmd smoke-base --fix
```

For the extended runtime gate, continue with:

```powershell
.\nova.cmd smoke --fix
.\nova.cmd test
```

## Validation Status

The current artifact strategy is backed by near-clean validation completed on `2026-03-30`:

- staged package copy bootstrapped successfully outside the live workspace tree
- staged `nova doctor` passed
- staged `nova runtime-status` was corrected to scope web UI discovery to the current package root
- staged `nova test` passed

## Remaining Work

- rerun artifact validation from the produced zip on a fresh machine or VM for release candidates
- decide later whether NYO System also needs a higher-convenience installer format

## Windows Installer Layer

When Inno Setup is available, the repo can now compile a Windows installer wrapper on top of the verified package artifact:

```powershell
.\nova.cmd installer-build
.\nova.cmd installer-verify
.\nova.cmd installer-ledger --count 5
.\nova.cmd installer-status
.\nova.cmd installer-readiness
.\nova.cmd installer-promote --result pass-with-notes --note "validated on VM"
.\nova.cmd installer-build --artifact runtime\exports\release_packages\nyo-system-base-rc-2026.03.30.2.zip
.\nova.cmd installer-build --compiler "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
```

This does not replace the package zip as the release truth.

It wraps the verified package artifact in the current Inno Setup installer defined in `installer/NYO_System.iss`.

Installer artifacts now participate in the same shared release ledger lifecycle as package zips:

- `build` event when `nova installer-build` produces the `.exe`
- `verify` event when `nova installer-verify` confirms the installer file and its source-package provenance
- `promotion` event when `nova installer-promote` records the manual validation outcome

That means the installer path now has the same history, status, and readiness surfaces as the package zip, just filtered to `windows-installer` artifacts.

For machine-local validation without installing into `Program Files`, the installer now allows command-line privilege override. That makes isolated same-machine validation possible with a command such as:

```powershell
.\runtime\exports\installers\nyo-system-installer-2026.03.30.3.exe /SP- /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /CURRENTUSER /TASKS="route_baseonly" /DIR="C:\path\to\isolated\install"
```

For now, the release truth is simpler: ship the source-bootstrap zip and keep the boundary honest.