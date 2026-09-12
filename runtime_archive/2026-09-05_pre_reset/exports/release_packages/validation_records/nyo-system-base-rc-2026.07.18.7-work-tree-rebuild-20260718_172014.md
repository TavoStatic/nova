# NYO System RC Validation Record

Date: 2026-07-18

Generated from an observed release validation profile.

## Candidate

- Artifact path: C:\NOVA\runtime\exports\release_packages\nyo-system-base-rc-2026.07.18.7-work-tree-rebuild-20260718_171854.zip
- Artifact version: 2026.07.18.7
- Version source: 
- Release channel: rc
- Release label: work-tree-rebuild
- Manifest reviewed: yes
- Release ledger path: C:\NOVA\runtime\exports\release_packages\release_ledger.jsonl

## Environment

- Machine or VM name: Rogue_One
- Windows version: Windows-11-10.0.26200-SP0
- Python source used during install: C:\nova\.venv\Scripts\python.exe (3.13.1)
- Ollama expected for this target: no

## Results

### Bootstrap

- nova package-verify .: pass
- nova install: pass
- Notes: observed from extracted package root

### Base Validation

- full regression status: pass
- full regression source: C:\NOVA\runtime\regression_status.json
- full regression generated_at: 2026-07-18 12:55:51
- full regression lanes: unit, behavior, integration
- nova doctor: pass
- nova runtime-status: pass
- nova smoke-base --fix: pass
- nova test: pass
- nova wiring-check --offline: pass
- Notes: base package validation commands were executed before final decision

### Operator Surface

- nova run: pass (launch/exit)
- nova webui-start --host 127.0.0.1 --port 8080: fail (exit 1)
- /control load result: not-run
- Notes: web UI validation used an available local port when 8080 was already owned

### Extended Runtime Validation

- nova smoke --fix: not-run (Ollama not expected for this target)
- Notes: extended runtime validation is required only when Ollama is expected for this target

## Final Decision

- Result: fail
- Blocking issues: nova webui-start --host 127.0.0.1 --port 8080 failed
- Non-blocking issues: fresh-machine or VM independence not proven by same-machine extracted-package profile
- Follow-up owner: release-validation
