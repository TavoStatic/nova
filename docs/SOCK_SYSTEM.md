<!--
NOVA_DOC
category: subsystem
authority: active_working
last_session: 2026-09-01
last_agent: grok
session_state: current
next_step: none
open: none
-->

# SOCK System

Last verified from code: 2026-09-01

SOCK is Nova's System Optimization and Compatibility Check. It profiles the host, inspects Ollama inventory, recommends a compatible model set, compares the recommendation to policy, optionally applies policy, and can validate concurrent model warming.

## Owner

- service: `services/sock_service.py`
- CLI: `scripts/run_sock.py`
- front door: `nova sock [--apply]`
- status projection: `get_sock_status_keys()` into control status and wiring inventory

## Flow

```text
hardware scan
  -> CPU, RAM, NVIDIA VRAM, GPU names, NPU presence
  -> Ollama model and running-model inventory
  -> chat/routing/vision/STT recommendation
  -> policy diff
  -> optional policy apply
  -> optional concurrent warm validation
  -> status keys and report
```

## Hardware Detection (as of Aug 2026)

- **NVIDIA GPU**: VRAM via `nvidia-smi`, GPU names, running model VRAM cross-referenced against live Ollama metadata
- **ROCm/HIP (AMD GPU)**: detected via `rocm-smi` or `hipinfo`; VRAM reported when available
- **NPU**: detected via WMI (`Win32_PnPEntity`, keywords: NPU, Neural, AI Processor, VPU) and `rocm-smi --showallinfo`; wired into recommendation engine as a weight modifier
- **Live VRAM estimates**: Ollama model metadata (`/api/show`) provides per-model VRAM sizes at runtime; estimates prefer live data over static lookup tables
- **Cache invalidation**: Ollama inventory change trigger (`nova_root_inventory` watcher) clears SOCK cache on model install/removal so status never serves stale recommendations

## Recommendation Inputs

- CPU name and logical cores
- system RAM
- NVIDIA/AMD VRAM and detected GPU names
- NPU presence and type
- installed and running Ollama models with live VRAM estimates
- stable chat/routing pair constraints

## Outputs

- `HardwareProfile`
- `OllamaInventory`
- `ModelRecommendation`
- `PolicyDiff`
- `WarmResult`
- `SockReport`
- `CapacityLease` — temporary mill residency; does not rewrite `policy.json`

Control status receives `sock_hardware_profile`, `sock_recommendation`, and `sock_policy_diff` through a cached status accessor.

## Mill capacity lease (2026-09-01)

The mill does **not** name a model. It exposes derived `mill_judgment_signal` (`class` + `pressure_event`) from solution-trail kind. SOCK chooses among **evidenced** candidates, filters by hardware and inventory, grants a short residency, invokes, unloads, restores standing.

Rule: mill class + pressure → hardware filter → model with evidence for that class → lease → unload. Not “more pressure → more parameters.”

Standing on this box (applied 2026-09-01, operator-requested):

| Role | Model |
|---|---|
| chat + routing | `qwen3.5:4b` |
| vision | `qwen2.5vl:7b` (sequential; do not co-reside with chat) |
| mill sip | `qwen3.5:9b` for `refused` and `redundant`+`empty_claim` only |
| not in combo | 0.8B, 2B, `qwen2.5:7b` as judge, `qwen2.5:14b` |

`qwen2.5:14b` has **no evidenced mill class** on this rig. Paid-trail (`redundant` + `inherited_attempt`) stays standing — 9B and 4B both said `mark_complete` on that class.

Score table and method: `docs/MILL_LANE_MEASURE_2026-09-01.md`. Raw JSON: `runtime/validation/qwen35_9b_lane_measure.json`.

APIs: `choose_mill_capacity`, `grant_capacity_lease`, `release_capacity_lease`, `run_with_mill_capacity` in `services/sock_service.py`. Lease record (temporary only): `runtime/_internal/capacity_lease.json`.

Skip/remint/stop/pulse mill-cycle control is live-promoted 2026-09-01 (`docs/AUTONOMY_AND_MISSION.md`). Mill sip-execute when `source_root_judgment` is reached is **not** live-promoted.

## Boundary

SOCK recommends and reports. Policy application is explicit. A mill lease is not a policy apply: standing stays in `policy.json`; the sip is temporary residency. A detected accelerator does not imply Nova uses it, and an installed model does not imply the concurrent model pair fits available VRAM. Do not mix this box's RTX 4050 with the Radeon 890M for inference.
