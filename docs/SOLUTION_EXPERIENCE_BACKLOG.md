# Solution experience — later work

Living list for the **solution experience** surface (solution progress, solution trail, how autonomy climbs findings, control-panel honesty).  
Not current implementation truth. Park ideas here while active work stays on smoothing progress itself.

**Current focus:** get the progress experience smoothed out (honest motion, climb ladders, no thrash, real next stems).

**Same fractal (do not duplicate):** architecture self-scan is progress at larger scale. Spec: `docs/SELF_SCAN_RINGS_DESIGN.md` (wiring design — not `nova_grok.md`).

**Backpack adoption (parked):** Three rings = backpack adoption protocol. Manifest declares source root + wiring surface + status keys. Nova verifies through rings before treating backpack as hers.

---

## Must do down the road

1. **Operator plain-language translator for control panel cards**  
  Control inspector language is system dialect and often misleading (e.g. blocked outbox wait still shows `Next step: execute | tool=read`, “moving” from failure thrash, signal-class jargon instead of a clear human ask).  
  **Need:** one translator that turns branch/tree/next-step/actionability into easy operator English first — e.g. *who is waiting*, *what I need from you*, *what Nova is doing* — with plumbing (tool, execute, motion) demoted or hidden when the real state is operator hold.  
  Wire into the existing work-tree / inspector path (not a second parallel UI truth).  
  **Why parked:** progress experience must settle first; plain language is the handoff layer on top of honest progress.

2. **Self-scan rings weave (handoff + climb integrity)** — **landed in code** (`services/self_scan_rings.py` + probe context + climb on candidates). See `docs/SELF_SCAN_RINGS_DESIGN.md`. Further polish: control UI surface, backpack manifest adoption loop.

---

## Notes

- Prefer root-cause wiring over band-aids when these land.
- Do not invent a dual status system; translate or surface the same work-tree truth more clearly.
- Do not invent a second progress system for architecture gaps — weave into existing scanners + climb.
