# NYO System RC Validation Record

Date: 2026-03-30

Use this template to record each release-candidate validation run.

## Candidate

- Artifact path:
- Artifact version:
- Version source: explicit / auto-date-sequence
- Release channel:
- Release label:
- Manifest reviewed: yes/no
- Release ledger path:

## Environment

- Machine or VM name:
- Windows version:
- Python source used during install:
- Ollama expected for this target: yes/no

## Results

### Bootstrap

- `nova package-verify .`:
- `nova install`:
- Notes:

### Base Validation

- `nova doctor`:
- `nova runtime-status`:
- `nova smoke-base --fix`:
- `nova test`:
- Notes:

### Operator Surface

- `nova run`:
- `nova webui-start --host 127.0.0.1 --port 8080`:
- `/control` load result:
- Notes:

### Extended Runtime Validation

- `nova smoke --fix`:
- Notes:

## Final Decision

- Result: pass / pass-with-notes / fail
- Blocking issues:
- Non-blocking issues:
- Follow-up owner:
- Ledger updated with `nova package-promote`: yes/no