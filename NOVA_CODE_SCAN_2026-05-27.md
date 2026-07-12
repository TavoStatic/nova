# Nova Project — Full Code Scan Report

Historical scan. Superseded for current architecture and function inventory by `docs/CODE_TRUTH_AUDIT_2026-07-12.md`.
**Date:** 2026-05-27
**Scanned by:** Claude (Cowork)
**Scope:** All active source files in C:\NOVA (excluding `.venv/`, `runtime/`, `__pycache__/`, `.git/`)

---

## Executive Summary

Nova is a large, actively developed Python runtime (~239 source files, 147 services, 184 test files). The **unit test suite is green** as of today and the project is well-structured with meaningful separation of concerns. However, the **latest release package is failing validation**, there are **22 active source files with BOM encoding errors** (concentrated in the `tools/` directory), key core files lack a logging framework, and the two heaviest files are significantly over-sized. The project is healthy at the unit level but not yet releasable without closing the missing test lanes.

---

## Overall Health: 🟡 AMBER

| Area | Status | Notes |
|---|---|---|
| Unit tests | ✅ PASSING | regression_status.json: OK, returncode 0 |
| Release validation | ❌ FAILING | Missing behavior + integration lanes; nova test failed |
| Encoding (BOM) | ⚠️ 22 files | All of `tools/` + 2 service files affected |
| Uncommitted changes | ⚠️ 21 files | 950 insertions in-flight, not yet committed |
| Line endings (CRLF) | ⚠️ Mixed | 21 files triggering git LF→CRLF warnings |
| File sizes | ⚠️ God files | autonomy_maintenance.py (4,165 lines), nova_core.py (3,974 lines) |
| Security | ✅ Clean | No shell=True, no eval/exec, no hardcoded secrets |
| Type hints | ✅ Good | 233 / 198 / 107 typed functions in core files |
| Docstrings | ⚠️ Sparse | nova_core.py: 9 docstrings across 3,974 lines |
| Logging | ⚠️ Absent | None of the 3 core files use Python's `logging` module |
| Architecture | ✅ Sound | Clean services/, tools/, routing/ separation; no circular imports |

---

## 1. Test & Release Status

### Unit Regression — GREEN ✅
The regression runner (`scripts/run_regression.py`) produced a clean run today at 22:19:14:
- **175 curated test targets** covered by **169 test files**
- **172 test files** at project root, 184 total across all dirs
- 0 profile gaps, 0 profile drift
- 3 optional-inactive tests (not blocking)

### Latest Release Validation — FAILING ❌
The most recent release package (`nyo-system-base-rc-2026.05.27.2`) was validated and came back **not ok** with two blocking issues:

1. `full regression status missing required lanes: behavior, integration`
   — Only the `unit` lane is recorded. The release gate requires `behavior` and `integration` lanes to pass before a package can be promoted.

2. `nova test failed`
   — The extracted-package smoke test against the release zip did not pass.

One non-blocking issue noted: fresh-machine or VM independence is not proven by same-machine extraction alone.

**Action needed:** Run behavior and integration lanes and fix the nova test failure before the next release promotion attempt.

---

## 2. Encoding Issues — 22 BOM Files ⚠️

22 active source files begin with a UTF-8 BOM (`U+FEFF`). Python 3 on Linux will refuse to parse these with a `SyntaxError: invalid non-printable character`. They currently work on Windows (which is tolerant of BOM) but will silently break any Linux CI, Docker, or cross-platform run.

**All tools/ files are affected:**
- `tools/__init__.py`, `tools/base_tool.py`, `tools/filesystem_tool.py`, `tools/patch_tool.py`
- `tools/registry.py`, `tools/research_tool.py`, `tools/runtime_processes.py`
- `tools/system_tool.py`, `tools/vision_tool.py`

**Other active source files:**
- `choice_presenter.py`, `conversation_manager.py`, `dynamic_replanner.py`
- `fit_evaluator.py`, `fulfillment_contracts.py`, `fulfillment_flow_example.py`
- `fulfillment_model_generator.py`, `intent_interpreter.py`
- `services/nova_knowledge_packs.py`, `services/nova_reply_sequence.py`
- `tests/test_nova_reply_runtime.py`, `tests/test_nova_session_state_service.py`, `tests/test_work_tree.py`

**Fix (one-liner):**
```bash
# Strip BOM from all affected files
for f in tools/*.py tools/__init__.py choice_presenter.py conversation_manager.py \
          dynamic_replanner.py fit_evaluator.py fulfillment_contracts.py \
          fulfillment_flow_example.py fulfillment_model_generator.py \
          intent_interpreter.py services/nova_knowledge_packs.py \
          services/nova_reply_sequence.py tests/test_nova_reply_runtime.py \
          tests/test_nova_session_state_service.py tests/test_work_tree.py; do
    sed -i 's/^\xef\xbb\xbf//' "$f"
done
```

---

## 3. Uncommitted Changes ⚠️

There are **21 modified files** with **950 insertions and 166 deletions** not yet committed. The changes touch the heaviest files in the project:

| File | Change |
|---|---|
| `autonomy_maintenance.py` | +175 lines |
| `services/work_tree_signal_ingestion.py` | +99 lines |
| `services/nova_reply_sequence.py` | +59 lines |
| `services/nova_fallback_flow.py` | −131 / +some lines (net shrink) |
| `work_tree.py` | +9 lines |
| `nova_core.py` | +5 lines |
| Tests (9 files) | New test coverage matching changes |

This looks like an active feature/fix session. The test files appear to be paired with the source changes which is a good sign. These should be committed (or stashed) before the next release attempt.

---

## 4. Line Ending Inconsistency ⚠️

Git is warning about `LF → CRLF` conversion on 21 files every time a diff is run. This is a sign of mixed origins (files edited on both Linux and Windows environments). It's not a crash risk on Windows but causes noise in diffs and can confuse tools that check encoding.

The `.gitattributes` file exists — verify it has `*.py text eol=lf` to force consistent LF storage.

---

## 5. God Files — Refactoring Targets ⚠️

Two files are significantly oversized and carry the most risk as the project grows:

### `autonomy_maintenance.py` — 4,165 lines
The single largest file. Contains the entire autonomy loop. The `run_once()` function alone is **401 lines** — the longest function in the entire project. Other functions of concern:
- `_sync_signal_intake_work_tree`: 134 lines
- `_sync_patch_queue_work_tree`: 119 lines
- `_apply_patch_queue_branch_state`: 115 lines
- `_triage_hints_for_orchestrator`: 109 lines

### `nova_core.py` — 3,974 lines, 310 functions
The core entry point has grown very large. The good news is most individual functions are well-sized (only `_self_report_work_tree_truth` exceeds 60 lines at 65). The surface area risk is the sheer number of responsibilities held in one file — imports alone run to line 80+.

### `work_tree.py` — 2,545 lines
- `execute_autonomous_step`: 190 lines
- `next_autonomous_step`: 101 lines
- `_apply_schema_migrations`: 99 lines

**Recommendation:** These don't need to be split immediately, but `run_once()` in `autonomy_maintenance.py` is a clear refactoring target — it should be broken into named sub-phases each under ~60 lines.

---

## 6. No Logging Framework ⚠️

`nova_core.py`, `nova_http.py`, and `work_tree.py` — the three most critical runtime files — use **zero calls to Python's `logging` module**. The codebase uses `print()` in a few spots and otherwise relies on structured JSON output or silent exception handling (`except Exception:`).

This makes operational debugging harder: there's no way to set a log level, route log output to a file, or filter noise in production without changing code.

**Recommendation:** Introduce a project-wide `logging` config (even a single `logging.getLogger("nova")` setup in a shared module) and replace the scattered `print()` calls in `nova_core.py` with `logger.debug/info/warning`.

---

## 7. Exception Handling Style

`nova_core.py` uses `except Exception:` (not bare `except:`) in 20+ places. This is intentional defensive coding for a runtime that must not crash — the pattern is appropriate given the design goal of keeping the loop alive. No concerns here.

---

## 8. Security Posture — Clean ✅

Scanned across all active source files:
- **No `shell=True`** in any subprocess calls — all subprocess invocations use list arguments
- **No `eval()` or `exec()`** usage
- **No hardcoded passwords, API keys, or secrets** — all external credentials reference environment variable names (`_env` pattern)
- **`policy.json`** enforces: `allow_shell: false`, `confirm_writes: true`, `confirm_exec: true`, allowlisted domains for web fetch

The safety envelope is solid.

---

## 9. Architecture Overview — Sound ✅

The project has clean separation:

```
nova_core.py          — Main runtime entry, CLI/HTTP wiring
nova_guard.py         — Process watchdog, maintenance loop supervisor
nova_http.py          — HTTP front door
services/             — 147 modules, well-named, no circular imports back to core
tools/                — Tool registry, base classes, OS capability tools
routing/              — Turn model and execution plan
tests/                — 184 test files with 1:1 mapping to services
docs/                 — 27 markdown docs covering architecture, operations, release
```

No circular imports detected from services/ back to nova_core. Type hints are healthy (233 typed functions in nova_core alone). The policy/safety envelope and operator outbox pattern show deliberate safety-first thinking.

---

## 10. Docstrings — Sparse ⚠️

`nova_core.py` contains only **9 triple-quote strings** across 3,974 lines. `nova_http.py` has 1. Most functions rely on clear naming rather than inline documentation. This is a readability concern for onboarding or future contributors but not a runtime risk.

---

## Priority Action List

| Priority | Issue | Fix |
|---|---|---|
| 🔴 HIGH | Release validation failing (missing lanes + nova test) | Run behavior + integration lanes; debug nova test failure |
| 🔴 HIGH | 22 BOM-encoded source files | Strip BOM with sed one-liner (see Section 2) |
| 🟡 MED | 21 uncommitted changes in-flight | Commit or stash before next release attempt |
| 🟡 MED | `run_once()` at 401 lines | Break into named sub-phase functions |
| 🟡 MED | No logging framework in core | Add `logging.getLogger("nova")` to core files |
| 🟢 LOW | CRLF/LF line ending noise | Enforce `*.py text eol=lf` in `.gitattributes` |
| 🟢 LOW | Sparse docstrings in nova_core.py | Add function-level docstrings incrementally |

---

*Generated by full static analysis of C:\NOVA on 2026-05-27. Runtime test execution was not available in this environment (Windows .venv not executable on Linux sandbox). Findings are based on AST parsing, git status, file metrics, and pattern scanning.*
