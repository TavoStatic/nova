# NYO System Windows Installer Plan

Date: 2026-03-30

## Purpose

This document defines the first practical Windows executable-installer path for NYO System.

It is intentionally narrower than a frozen all-in-one executable build.

The goal is:

- keep the current source-bootstrap runtime intact
- wrap it in a Windows installer executable
- automate environment setup and readiness checks
- preserve the current package boundary and release-governance flow

## Recommended Direction

Use a bootstrap installer executable rather than a frozen Nova runtime executable.

Why:

- current runtime already has a working bootstrap path via `nova install`
- release packaging already produces a clean source-bootstrap artifact via `nova package-build`
- bootstrap installer work is incremental and compatible with current release validation
- frozen-exe packaging would force a much larger redesign around Python runtime bundling, process ownership, assets, updates, and optional local services

## Installer Shape

Recommended first implementation:

- installer technology: Inno Setup
- payload source: extracted output of the existing `nova package-build` artifact
- installer behavior: unpack payload, run readiness check, run `nova install`, present result, offer shortcuts

Current repo status:

- the Inno Setup definition exists at `installer/NYO_System.iss`
- the repo now exposes `nova installer-build` as the build entrypoint for producing the installer executable from a verified package zip
- the remaining work is validation and hardening, not inventing a new installer pipeline

This keeps one release truth:

- ship the NYO System package as source payload
- add a convenience wrapper for Windows installation and first-run setup

## Installation Routes

Yes: the installer should offer multiple routes and let the operator choose.

That is better than forcing one install path because NYO System has different user types:

- operators who want the recommended guided install
- technical users who want files laid down but prefer to bootstrap manually
- evaluators who only want to inspect package contents and readiness before committing

Recommended installer routes:

### 1. Recommended Guided Install

- copy payload
- run hardware/environment check
- run `nova install`
- run `nova doctor`
- run `nova runtime-status`
- create shortcuts

This should be the default route.

### 2. Base Package Only

- copy payload
- run hardware/environment check
- do not create `.venv`
- do not install dependencies automatically

Use this when the operator wants the package on disk but wants to control bootstrap separately.

### 3. Manual / Advanced Setup

- copy payload
- skip automatic bootstrap and validation commands
- optionally still create shortcuts

Use this for developers, lab machines, and controlled deployment scripts.

### 4. Future: Bundled-Python Guided Install

- copy payload
- unpack or fetch supported Python runtime
- create `.venv`
- install dependencies
- run validation

This is a Phase 2 route, not required for the first installer release.

## Route Selection Rules

The installer should make routes explicit instead of hiding behavior.

Good UX:

- show a short explanation for each route
- mark the recommended route clearly
- allow advanced users to skip automation
- show the exact commands that will be run for the chosen route

The installer should also show what is not being done, for example:

- `Ollama not installed; runtime will be limited`
- `Python not found; guided bootstrap cannot proceed`
- `Base package installed without environment bootstrap`

## Responsibilities

The installer should do the following.

### 1. Lay Down The Payload

- copy the packaged NYO System files into the install directory
- default install root: `C:\Program Files\NYO System`
- support alternate install directory when admin install is not desired
- allow command-line current-user installs for isolated same-machine validation and non-admin operator scenarios

### 2. Run Hardware And Environment Checks

The installer should gather and display:

- CPU architecture and logical core count
- total RAM and currently available RAM
- free disk space on target drive
- Windows version and build
- GPU adapter names and reported video memory when available
- whether Python is already available
- whether Ollama is installed
- whether ports such as `8080` and `11434` are already in use

The installer should classify readiness as:

- `Base package OK`
- `Base package limited`
- `Runtime OK`
- `Runtime limited: Ollama missing`
- `Blocked`

### 3. Create Or Supply Python Runtime

Phase 1:

- use existing Python on `PATH` if available
- otherwise fail with a clear prerequisite message

Phase 2:

- optionally bundle or fetch a supported Python runtime automatically

### 4. Bootstrap The Environment

After payload copy:

- run `nova install`
- create `.venv`
- install dependencies from `requirements.txt`
- run `doctor.py --fix`

### 5. Validate Readiness

After bootstrap:

- run `nova doctor`
- run `nova runtime-status`
- optionally run `nova smoke-base --fix`

### 6. Detect Optional Runtime Tier

The installer should separately report whether model-backed runtime is ready.

This should include:

- Ollama command presence
- Ollama endpoint reachability on `127.0.0.1:11434`
- whether runtime ports are already occupied by another process

### 7. Create Shortcuts

Recommended Start Menu entries:

- `NYO System Shell`
- `NYO System Control`
- `NYO System Logs`
- `Uninstall NYO System`

## Packaging Flow

The Windows installer should sit on top of the current release flow.

### Current Flow

1. `nova package-build`
2. `nova package-verify`
3. fresh-machine or near-clean validation
4. `nova package-promote`

### Installer Flow

1. build verified package artifact
2. extract package payload into installer staging directory
3. compile Inno Setup installer executable from that staging directory
4. validate installer on fresh machine or VM
5. record installer validation separately from package-boundary validation

## Scope Boundaries

The installer should not silently change the current product definition.

Still true after installer work:

- `runtime/`, `logs/`, `memory/`, and `.venv/` remain local/generated state
- optional services such as Ollama remain operator-provided unless explicitly bundled later
- package-boundary validation remains mandatory before installer creation

## Phased Roadmap

### Phase 1: Bootstrap Installer

- add hardware/environment check script
- add Inno Setup installer definition
- add route selection inside the installer
- install payload to disk
- run `nova install`
- show readiness summary

### Phase 2: Python Convenience

- support embedded or downloaded Python runtime
- remove Python-on-PATH requirement for most users

### Phase 3: First-Run UX

- add installer pages for readiness summary and runtime tier
- add explicit launch options for shell and control UI
- add clearer handling for port conflicts and missing Ollama

### Phase 4: Optional Productization

- decide whether NYO System should remain a bootstrap-installed runtime or move toward a frozen executable distribution

## First Implementation Choice

Recommended first implementation tool: Inno Setup.

Why:

- easy single-file Windows installer output
- straightforward file copy and post-install command execution
- low complexity compared with WiX
- fits current PowerShell/bootstrap model cleanly

## Related Files

- `installer/NYO_System.iss`
- `scripts/installer_hardware_check.ps1`
- `docs/BOOTSTRAP.md`
- `docs/RELEASE_ARTIFACT.md`
- `docs/PACKAGING_MATRIX.md`