# 🚀 Nova — Not Your Ordinary AI System (NYO)

**Agent Operating System (AAOS)**  
Deterministic • Traceable • Testable AI Behavior

---

## 🧠 What is NYO & Who is Nova?

**NYO (Not Your Ordinary)** is the philosophy behind the system.

It represents a shift away from traditional AI behavior:
- not just generating responses  
- not just calling tools  
- but executing structured, controlled decisions  

---

**Nova** is the system.

Nova is a **supervisor-driven Agent Operating System (AAOS)** that enforces:

- deterministic routing  
- contract-based responses  
- full traceability  
- consistent behavior across CLI and HTTP  

---

## ⚙️ Architecture

```
User Input
    ↓
Supervisor (routing authority)
    ↓
Core (execution + outcome classification)
    ↓
Contract Renderer
    ↓
Ledger + Reflection
    ↓
HTTP / CLI
```

---

## 🧱 Core Components

- `supervisor.py` — routing authority  
- `nova_core.py` — execution + contracts  
- `nova_http.py` — transport layer  
- `nova_guard.py` — runtime watchdog  
- `policy.json` — configuration  
- `runtime/` — system state  

---

## 🚀 Quick Start

### Install Dependencies

```powershell
C:\Nova\.venv\Scripts\python.exe -m pip install -r C:\Nova\requirements.txt
```

### Start Nova

```powershell
C:\Nova\nova.ps1 doctor
C:\Nova\.venv\Scripts\python.exe C:\Nova\nova_guard.py
```

### Stop Nova

```powershell
C:\Nova\.venv\Scripts\python.exe C:\Nova\stop_guard.py
```

---

## 🩺 Health Check

```powershell
C:\Nova\.venv\Scripts\python.exe C:\Nova\health.py
```

---

## 🧠 Runtime Model

Nova follows a **supervisor-first execution model**:

- Supervisor → decides ownership  
- Core → executes behavior  
- Contracts → define responses  
- Ledger → records decisions  

Example:

```json
{
  "reply_contract": "...",
  "reply_outcome": "..."
}
```

---

## 📊 Current Status

- Supervisor-first routing implemented  
- Contract/outcome system active  
- Full test suite passing  

---

## 🧠 Vision

Nova is evolving into:

**AAOS — Agent Operating System**

A system where:
- behavior is enforced, not guessed  
- routing is explicit  
- AI becomes predictable  

---

## ⭐ Final Thought

Nova is not trying to be the smartest AI.  
It is trying to be the most reliable.# 🚀  Not Your Ordinary AI System (NYO)

**Agent Operating System (AAOS)**  
Deterministic • Traceable • Testable AI Behavior

---

## 🧠 What is NYO & Who is Nova?

Nova is not just an AI assistant.

It is a **supervisor-driven Agent Operating System (AAOS)** designed to enforce:

- deterministic behavior  
- structured execution  
- full traceability

  NYO is the philosophy.

---

**Nova** is the runtime.

Nova is the **Agent Operating System (AAOS)** that brings NYO to life by enforcing:

- deterministic routing (via the supervisor)  
- contract-based responses (not string-based logic)  
- full traceability (ledger + reflection)  
- consistent behavior across CLI and HTTP  

---

### 🧩 In simple terms

- **NYO** = the mindset  
- **Nova** = the system  

---

### ⚙️ What Nova actually does

Nova does not “guess” what to do.

It:

1. routes input through a **supervisor**
2. determines **who owns the turn**
3. executes through the **core system**
4. produces a response using **contracts**
5. records everything for **traceability**

---

### 🔥 Why this matters

Most AI systems:
- generate answers

Nova:
- **executes decisions**

---

### 🧠 One-line definition

> NYO is the philosophy.  
> Nova is the system that enforces it.

---

## ⚙️ Architecture

```text
User Input
    ↓
Supervisor (routing authority)
    ↓
Core (execution + outcome classification)
    ↓
Contract Renderer
    ↓
Ledger + Reflection
    ↓
HTTP / CLI
```

---

## 🧱 Core Components

| Component | Description |
|----------|-------------|
| `supervisor.py` | Routing authority (who owns the turn) |
| `nova_core.py` | Execution engine + contract system |
| `nova_http.py` | Transport layer (mirrors core only) |
| `nova_guard.py` | Runtime watchdog + heartbeat |
| `policy.json` | Configuration (tools, memory, models) |
| `runtime/` | Live system state |

---

## 🚀 Quick Start

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

## 🩺 Health & Diagnostics

```powershell
C:\Nova\.venv\Scripts\python.exe C:\Nova\health.py
C:\Nova\.venv\Scripts\python.exe C:\Nova\health.py check
C:\Nova\.venv\Scripts\python.exe C:\Nova\health.py diag
C:\Nova\.venv\Scripts\python.exe C:\Nova\health.py repair
```

---

## 🧪 Smoke Test

```powershell
C:\Nova\nova.ps1 smoke --fix
```

Runs:

```text
doctor → guard → smoke_test → stop
```

---

## 🧠 Runtime Model

Nova follows a **supervisor-first execution model**:

- Supervisor → decides ownership  
- Core → executes behavior  
- Contracts → define response structure  
- Ledger → records decisions  

Each deterministic response includes:

```json
{
  "reply_contract": "...",
  "reply_outcome": "..."
}
```

---

## 📊 Current Status

- ✔ Supervisor-first routing implemented  
- ✔ Contract/outcome system active  
- ✔ Multiple behavior families migrated  
- ✔ Full test suite passing  

---

## 🧱 Runtime Files

Located in `runtime/`:

- `core_state.json` — system state  
- `core.heartbeat` — live signal  
- `guard.stop` — shutdown trigger  
- `core.fail` — failure indicator  

---

## ⚠️ Development Notes

- `NOVA_DEV_MODE` enables strict enforcement  
- HTTP must mirror core behavior (no divergence)  
- Smoke tests validate full system integrity  

---

## 🧠 Vision

Nova is evolving into:

**AAOS — Agent Operating System**

A system where:

- behavior is enforced, not guessed  
- routing is explicit, not implicit  
- AI becomes **predictable infrastructure**

---

## ⭐ Support

If you find this project useful:

- Star the repo  
- Follow its evolution  

---

## 🔥 Final Thought

Nova is not trying to be the smartest AI.  
It is trying to be the most reliable system for AI behavior.
