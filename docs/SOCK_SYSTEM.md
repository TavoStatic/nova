# SOCK System

Last verified from code: 2026-07-12

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

## Recommendation Inputs

- CPU name and logical cores
- system RAM
- NVIDIA VRAM and detected GPU names
- NPU presence
- installed and running Ollama models
- estimated model VRAM requirements
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
