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
It is trying to be the most reliable.
