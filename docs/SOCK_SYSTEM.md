<!--
NOVA_DOC
category: subsystem
authority: active_working
last_session: 2026-08-05
last_agent: claude-cowork
session_state: current
next_step: none
open: none
-->

# SOCK System

Last verified from code: 2026-08-05

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

Control status receives `sock_hardware_profile`, `sock_recommendation`, and `sock_policy_diff` through a cached status accessor.

## Boundary

SOCK recommends and reports. Policy application is explicit. A detected accelerator does not imply Nova uses it, and an installed model does not imply the concurrent model pair fits available VRAM.
