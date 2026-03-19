# Nova — Not Your Ordinary AI System (NYO)

**Agent Operating System (AAOS)**  
Deterministic • Traceable • Testable AI Behavior

![Status](https://img.shields.io/badge/status-active-success)
![Tests](https://img.shields.io/badge/tests-375%2B%20passing-brightgreen)
![Architecture](https://img.shields.io/badge/architecture-supervisor--first-blue)
![Platform](https://img.shields.io/badge/platform-AAOS-purple)

---

## What is Nova?

Nova is not just an AI assistant.

It is an **Agent Operating System (AAOS)** designed to enforce:

- deterministic behavior
- structured execution
- full traceability

Unlike traditional AI systems that rely on loosely controlled outputs, Nova introduces **governance at the core of the runtime**.

---

## Why Nova Exists

Most AI systems optimize for:

- more tools
- more autonomy
- more output

Nova optimizes for:

- **correct behavior**
- **predictable execution**
- **observable decisions**

---

## Architecture

```text
User Input
    ↓
Supervisor (routing authority)
    ↓
Core (execution + outcome classification)
    ↓
Contract Renderer (semantic → response)
    ↓
Ledger + Reflection (traceability)
    ↓
HTTP / CLI (transport layer)
```

---

## Quick Start

### Install Dependencies

```powershell
C:\Nova\.venv\Scripts\python.exe -m pip install -r C:\Nova\requirements.txt
```

### Start Nova

```powershell
C:\Nova\nova.ps1 doctor
C:\Nova\.venv\Scripts\python.exe C:\Nova\nova_guard.py
```

Optional:

```powershell
C:\Nova\nova.ps1 guard --fix
C:\Nova\nova.ps1 smoke --fix
```

### Stop Nova

```powershell
C:\Nova\.venv\Scripts\python.exe C:\Nova\stop_guard.py
```

---

## Health Check

```powershell
C:\Nova\.venv\Scripts\python.exe C:\Nova\health.py
```

---

## Memory

```powershell
C:\Nova\.venv\Scripts\python.exe C:\Nova\memory.py stats
```

---

## Runtime Model

Nova follows a supervisor-first model:

- Supervisor → routing  
- Core → execution  
- Contracts → response structure  
- Ledger → trace  

Each response includes:

```json
{
  "reply_contract": "...",
  "reply_outcome": "..."
}
```

---

## Vision

Nova is evolving into:

**AAOS — Agent Operating System**

---

## Final Thought

Nova is not trying to be the smartest AI.  
It is trying to be the most reliable.
