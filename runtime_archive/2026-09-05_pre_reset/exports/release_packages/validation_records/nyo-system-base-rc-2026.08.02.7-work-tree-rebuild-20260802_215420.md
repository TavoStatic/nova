# NYO System RC Validation Record

Date: 2026-08-02

Use this prefilled record for the fresh-machine or VM validation pass.

## Candidate

- Artifact path: C:\NOVA\runtime\exports\release_packages\nyo-system-base-rc-2026.08.02.7-work-tree-rebuild-20260802_215420.zip
- Artifact version: 2026.08.02.7
- Version source: auto-date-sequence
- Release channel: rc
- Release label: work-tree-rebuild
- Manifest reviewed: yes/no
- Release ledger path: C:\NOVA\runtime\exports\release_packages\release_ledger.jsonl

## Environment

- Machine or VM name:
- Windows version:
- Python source used during install:
- Ollama expected for this target: yes/no

## Results

### Bootstrap

- nova package-verify .:
- nova install:
- Notes:

### Base Validation

- nova doctor:
- nova runtime-status:
- nova smoke-base --fix:
- nova test:
- Notes:

### Operator Surface

- nova run:
- nova webui-start --host 127.0.0.1 --port 8080:
- /control load result:
- Notes:

### Extended Runtime Validation

- nova smoke --fix:
- Notes:

## Final Decision

- Result: pass / pass-with-notes / fail
- Blocking issues:
- Non-blocking issues:
- Follow-up owner:
