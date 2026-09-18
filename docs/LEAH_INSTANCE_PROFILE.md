<!--
NOVA_DOC
category: plan
authority: live
last_session: 2026-08-15
last_agent: grok
session_state: paused
next_step: none
open: leah_memory_recall AT-5 (cross-session recall)
-->

# Leah Instance Profile

**Paused 2026-08-15.** Operator stopped Leah build here. Continuity stays promoted.
Do not promote `leah_memory_recall`. Do not start voice or emotion. Resume only on
explicit operator ask. Open brick on resume: AT-5 — new session must cite a pinned
fact that is not in that session's turns.

Document class: instance profile. Required by LEAH_INSTANCE_PROMOTION_PLAN.md Phase B before
any capability is promoted. This document is the operator's declaration of how THIS Nova
instance should use Leah, in what order, and what proves each capability is working.

---

## 1) Instance Identity

**Operator:** Gus  
**Nova role:** Local autonomous operator — runs pipelines, manages backpacks, self-governs  
**Leah role:** Conversational front door for the operator. A working interface, not a chatbot.

---

## 2) How This Instance Uses Leah

Leah is the surface the operator reaches when working with Nova conversationally.
Primary use patterns:

- **Operational questions** — "what's running", "what's blocked", "did the sync finish"
- **Status checks** — pipeline health, runtime state, queue pressure
- **File review** — staging a file and asking Nova to read or summarize it
- **Session continuity** — returning to a mid-session question after navigating away or reloading

The operator does not want a chatbot. Leah should speak from what Nova actually knows.
If Nova has nothing to report, the open door is enough. Do not fill silence with invention.

---

## 3) Capability Priority (Ordered)

| Priority | Capability | Reason |
|---|---|---|
| 1 | leah_conversation_continuity | Operator navigates mid-session frequently; losing context is the primary friction point today |
| 2 | leah_memory_recall | Operator asks recurring questions; instance recall reduces repeated context-setting |
| 3 | leah_voice_persona_engine | Voice is built in UI; not required yet for this instance |
| 4 | leah_emotional_state_model | Deferred until continuity and recall are validated in real usage |

Only Priority 1 is promoted in Phase C. Priorities 2–4 are declared for sequencing awareness
only — not promoted, not targeted by codegen until Priority 1 is validated.

---

## 4) Persona Expectations

- **Tone:** Direct. No filler.
- **Silence behavior:** Idle presence is the open door. Nova does not manufacture conversation.
- **Source discipline:** Speak from runtime facts (`leah_nova_pulse`) and session context only.
  Do not speculate about anything not in the pulse or the current session.
- **Volume:** Brief. One clear answer.

---

## 5) Acceptance Tests — leah_conversation_continuity

Pass/fail criteria for Phase C. Continuity is validated when ALL of the following hold
in real operator usage on this instance:

### AT-1: Turn recovery after reload

**Setup:** Operator sends a message in Leah. Reloads the page. Sends a follow-up.  
**Pass:** Nova's response to the follow-up reflects awareness of the prior turn.  
**Fail:** Nova treats the follow-up as a brand new conversation.  
**Mechanism:** `_recover_leah_continuity_turns()` in nova_http.py → `LeahConversationContinuityStore.load_turns()` → `runtime/leah_sessions/`.

### AT-2: Attachment context survival within TTL

**Setup:** Operator stages a file in Leah. Navigates away. Returns. Asks about the file.  
**Pass:** Nova acknowledges the file and can describe it.  
**Fail:** Nova has no record of the staged file.  
**Mechanism:** `remember_session_context()` writes to continuity store; `recent_session_context()` reads it back. 30-minute TTL applies.

### AT-3: No cross-session bleed

**Setup:** Operator opens a new browser session (new session ID).  
**Pass:** Nova does not surface turn history from the prior session.  
**Fail:** Prior session turns appear in the new session.  
**Mechanism:** Continuity store is keyed by session ID — different ID, different file.

### AT-4: Continuity failure does not break chat

**Setup:** `runtime/leah_sessions/` is missing or the session file is corrupt.  
**Pass:** Leah responds normally; continuity degrades gracefully.  
**Fail:** Leah returns an error because continuity lookup failed.  
**Mechanism:** `_recover_leah_continuity_turns()` returns `[]` on any exception.

---

## 5b) Acceptance Test — leah_memory_recall

One AT. Must pass before `leah_memory_recall` is promoted.

### AT-5: Cross-session fact recall

**Setup:** In session A, tell Leah a specific fact with a distinctive label (e.g. a codeword or project name). End the session. Open a new session B with the same user. Send a recall-cue query about that fact ("what did I tell you about…", "do you remember…").  
**Pass:** Nova's reply cites the stored fact from session A without it being present in session B's turn history.  
**Fail:** Nova guesses, generalizes, or returns nothing. Same-session recall does not count — turns in session history are continuity, not durable memory.  
**Mechanism:** `LeahMemoryRecallService.recall_for_turn()` calls `nova_core.mem_recall(query)` → memory system returns stored fact → injected into message before reply spine.  
**Write path (code, 2026-08-15):** Ordinary Leah chat turns do not call `mem_add`. `finalize_llm_fallback_reply` is handed `mem_add_fn` and never uses it; policy `store_blocked_kinds` includes `chat_user`. The only chat write on this spine is the explicit pin: `remember` / `remember this:` → `apply_user_memory_learning` → `mem_remember_fact` → `mem_add("fact", "pinned", ...)`. Live pin of CEDAR-2206 wrote (`Pinned memory saved`) and new-session recall still missed — so AT-5 is open on `mem_recall` surfacing a pinned fact, not on Leah inject wiring. Same-session cite is continuity.  
**Automated test:** `tests/test_leah_memory_recall_at5.py` proves the write-path split and the inject-if-hit contract. It does not prove live AT-5. Do not promote on it.

---

## 6) Rollback Criteria

Continuity promotion is rolled back if any of the following occur within 14 days:

- A Leah chat turn errors because of the continuity store
- `runtime/leah_sessions/` grows past 50MB (runaway session accumulation)
- Core gate flips false during or after promotion
- Operator reports wrong session context surfacing in a new session

Rollback: remove `leah_conversation_continuity` from `promoted_capabilities` in `policy.json`.
Session files are preserved; the promotion is simply rescinded.

---

## 7) Definition of Done for Phase C

- All four acceptance tests pass in real operator usage — **DONE 2026-08-15**
- No new persistent blocked branches since promotion — **DONE 2026-08-15**
- `capability_finish_ownership` updated to reflect validated (not just coded) — **DONE 2026-08-15**
- `capabilities_roadmap.json` gap for this capability marked resolved — **DONE 2026-08-15**
- This document updated with validation date — **DONE 2026-08-15**

**leah_conversation_continuity validated in real operator usage: 2026-08-15**

AT-2 required a fix: the post-navigation path (`elif` branch in `nova_http_request_binding.handle_chat_request`) was not consulting the store when the browser sent no attachments. Fixed and retested before validation was declared.
