<!--
NOVA_DOC
category: evidence
authority: historical
last_session: 2026-09-01
last_agent: grok
session_state: current
next_step: none
open: none
-->

# Mill lane measure — 2026-09-01

Evidence only. Does not override code or live mill. Standing/sip contract lives in `docs/SOCK_SYSTEM.md`. Raw runs: `runtime/validation/qwen35_9b_lane_measure.json`. Harness: `runtime/validation/_measure_qwen_lanes.py`.

## Method

Ollama `/api/chat` only. `think: false`, `num_ctx: 8192`, `temperature: 0`. Seven forced mill-judgment tokens. **Not** a Nova execute path. `policy.json` was unchanged during the measure; standing 4B was applied after the scores, operator-requested.

Host: RTX 4050 Laptop 6141 MiB, 32 GB RAM. Do not mix 4050 + 890M.

## Scores (exact token match)

| Model | Score | Fit notes |
|---|---|---|
| `qwen3.5:9b` | **6/7** | 45/55 CPU/GPU, ~4385 MiB — evidenced mill sip |
| `qwen3.5:4b` | **5/7** | 100% GPU, 3.3 GB — standing resident (applied after) |
| `qwen3.5:2b` | 3/7 | 100% GPU — ties 2.5 7B; misses predicted / EDFI / NYO |
| `qwen2.5:7b` | 3/7 | prior standing |
| `qwen2.5:14b` | 3/7 | 61/39 CPU/GPU — hardware boundary, **no mill class** |
| `qwen3.5:0.8b` | 0/7 | too small to hold Nova's world |

There is **no Qwen 3.5 14B**. Next 3.5 sizes are 27B / 35B-A3B — past GPU-resident fit here. `qwen3:14b` (Qwen 3, not 3.5) was not measured.

## Case calls that matter

| Case | 2.5 7B | 3.5 4B | 3.5 9B | 2.5 14B |
|---|---|---|---|---|
| paid trail (skip vs close) | named skip (prose) | `mark_complete` | `mark_complete` | named skip (prose) |
| predicted vs invoked | `no` | `no` | `no` | `no` |
| missing evidence | `yes` | `no` | `no` | `no` |
| repeat unchanged | stop | stop | stop | named stop (prose) |
| explanation vs done | `no` | `no` | `no` | `no` |
| EDFI uninstalled | `fix_fusion` | treat as history | treat as history | never chose |
| NYO identity | never chose | named history (markdown, scored fail) | `historical_identity` | never chose |

4B NYO was a format miss, not a wrong mill call. Paid trail is a **3.5 family miss** at 4B and 9B. SOCK therefore does **not** sip 9B on `redundant` + `inherited_attempt`.

## What this proved

Nova's mill set distinguishes **which generation understands Nova's world**, independent of size. 3.5 4B beat 2.5 14B. 2.5 14B did not beat 2.5 7B. 3.5 0.8B did not get a pass for being new.

Discovery is not “a better model.” It is that this eval can tell whether a model shares mill world (world-ended, dropped identity, no-marker vs complete, explanation vs done, predicted vs invoked).

## Applied combo (after measure)

- Standing chat + routing: `qwen3.5:4b`
- Mill sip: `qwen3.5:9b` on `refused` and `redundant`+`empty_claim`, then unload
- Vision: `qwen2.5vl:7b`
- 7B kept pulled as fallback
- Backup: `policy.json.sock_backup` restores 7B standing

Overnight after apply (~23:45 2026-08-31 → 06:41 2026-09-01): 74 cycles `ok`, mill execute 0, **no capacity lease**. The combo was not exercised by the mill. Spine fired `REPEATED_UNCHANGED_PATH` on `pulse_status`, not on mill skip.
