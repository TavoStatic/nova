# Privileged Pipeline Protocol

This protocol exists so Nova can keep its main runtime under a normal user account while a narrow data lane runs under a different Windows identity.

## Goal

Only the protected pipeline worker runs under the trusted account.

- Nova runtime: normal user
- pipeline worker: trusted or elevated identity
- bridge: request/response artifacts under `runtime/pipelines/<pipeline_id>`

## Artifact Flow

```text
runtime/
└─ pipelines/
   └─ sis_test/
      ├─ requests/
      ├─ responses/
      └─ archive/
```

1. Nova writes a request file into `requests/`
2. The trusted worker claims it by renaming it to `.working.json`
3. The worker executes the governed live query
4. The worker writes a response file into `responses/`
5. The processed request moves into `archive/`

## Entry Points

- Queue/wait bridge:
  - [C:\Nova\services\pipeline_privileged_bridge.py](C:/Nova/services/pipeline_privileged_bridge.py)
- Worker loop:
  - [C:\Nova\scripts\pipeline_worker.py](C:/Nova/scripts/pipeline_worker.py)

## Run the SIS Worker Under the Trusted Identity

From the trusted district pipeline account session:

```powershell
cd C:\Nova
.\.venv\Scripts\python.exe .\scripts\pipeline_worker.py --pipeline sis_test
```

For a single request only:

```powershell
cd C:\Nova
.\.venv\Scripts\python.exe .\scripts\pipeline_worker.py --pipeline sis_test --once
```

## Nova-Side Usage

```python
from services.pipeline_privileged_bridge import run_privileged_pipeline_query

result = run_privileged_pipeline_query(
    "sis_test",
    "student_lookup",
    {"student_id": "12345"},
    row_limit=5,
    requested_by="nova_core",
    timeout_sec=60,
)
```

## Why This Protocol Exists

- Nova should not need the whole runtime under the district identity
- the SIS lane still needs trusted Windows auth
- the protocol keeps the sensitive execution boundary narrow and inspectable
