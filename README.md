# Project Not Your Ordinary AI System

Minimal notes to run and operate Nova locally.

Quick start

1. Ensure a Python virtual environment exists at `C:\Nova\.venv` and required packages are installed:

```powershell
C:\Nova\.venv\Scripts\python.exe -m pip install -r C:\Nova\requirements.txt
```

2. Start the guard (recommended):

```powershell
C:\Nova\nova.ps1 doctor
C:\Nova\.venv\Scripts\python.exe C:\Nova\nova_guard.py

# optional: preflight with lightweight auto-fix before guard start
C:\Nova\nova.ps1 guard --fix

# one-command operator smoke cycle
C:\Nova\nova.ps1 smoke --fix
```

3. Stop Nova (deterministic):

```powershell
C:\Nova\.venv\Scripts\python.exe C:\Nova\stop_guard.py
```

Health check

```powershell
C:\Nova\.venv\Scripts\python.exe C:\Nova\health.py
```

Startup preflight

```powershell
C:\Nova\.venv\Scripts\python.exe C:\Nova\doctor.py
# or
C:\Nova\nova.ps1 doctor

# lightweight auto-fix (creates runtime/logs and policy.json if missing)
C:\Nova\nova.ps1 doctor --fix

# optional: apply lightweight fix during startup preflight
C:\Nova\nova.ps1 run --fix

# one-command smoke cycle (doctor -> guard -> smoke_test -> stop)
C:\Nova\nova.ps1 smoke --fix
```

Additional health modes

```powershell
# Machine-readable JSON check (used by smoke_test.py)
C:\Nova\.venv\Scripts\python.exe C:\Nova\health.py check

# Human-readable diagnostics (GPU/mic/camera/Ollama/models)
C:\Nova\.venv\Scripts\python.exe C:\Nova\health.py diag

# Best-effort Ollama repair, then diagnostics
C:\Nova\.venv\Scripts\python.exe C:\Nova\health.py repair
```

Files of interest
- `nova_core.py` — main assistant loop (STT, LLM, TTS, tools)
- `nova_guard.py` — deterministic supervisor (heartbeat + statefile)
- `policy.json` — controls allowed root, tools, models, memory
- `runtime/` — runtime files (heartbeat, core_state.json, guard.stop, core.fail)

Memory quick check

```powershell
C:\Nova\.venv\Scripts\python.exe C:\Nova\memory.py stats
# or from Nova core chat: "mem stats"

# memory relevance audit for a query
C:\Nova\.venv\Scripts\python.exe C:\Nova\memory.py audit --query "peims reporting timeline"
# or from Nova core chat: "mem audit peims reporting timeline"
```

Memory relevance tuning (policy.json)
- `memory.min_score` → higher = stricter semantic recall, lower = more recall
- `memory.context_top_k` → number of recalled memory snippets injected into prompt
- `memory.store_min_chars` → minimum length required to store a message in memory

Web research commands (Nova core)
- `web <url>` → fetch and save allowlisted URL
- `web search <query>` → find allowlisted links for a query
- `web research <query>` → crawl allowlisted domains and rank relevant pages
- `web gather <url>` → fetch allowlisted URL and return a cleaned text snippet

If you want me to package this into a single ZIP bundle for backup or deploy, tell me and I'll create it.
