from __future__ import annotations

"""SOCK — System Optimization and Compatibility Check.

Scans the local hardware profile, queries the Ollama model inventory,
and produces a tiered model recommendation that maximises Nova's
performance on whatever rig it is running on.

Hardware detection uses PowerShell Get-CimInstance on Windows (the
supported modern API) and nvidia-smi with explicit path search for
NVIDIA VRAM. This avoids the deprecated wmic and the unreliable
platform.processor() fallback.
"""

import json
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "policy.json"
OLLAMA_BASE = "http://127.0.0.1:11434"

# Known install locations for nvidia-smi when it is not on PATH
_NVIDIA_SMI_CANDIDATES = [
    "nvidia-smi",
    r"C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe",
    r"C:\Windows\System32\nvidia-smi.exe",
]

# Known install locations for rocm-smi (AMD ROCm)
_ROCM_SMI_CANDIDATES = [
    "rocm-smi",
    r"C:\Program Files\AMD\ROCm\7.1\bin\rocm-smi.exe",
    r"C:\Program Files\AMD\ROCm\6.3\bin\rocm-smi.exe",
    r"C:\Program Files\AMD\ROCm\6.2\bin\rocm-smi.exe",
    "/opt/rocm/bin/rocm-smi",
    "/usr/bin/rocm-smi",
]


# ── dataclasses ────────────────────────────────────────────────────────────────

@dataclass
class HardwareProfile:
    cpu_name: str = ""
    cpu_cores: int = 0
    ram_gb: float = 0.0
    vram_gb: float = 0.0
    gpu_name: str = ""
    npu_detected: bool = False
    npu_name: str = ""
    storage_free_gb: float = 0.0
    platform_str: str = ""
    detection_notes: list[str] = field(default_factory=list)


@dataclass
class ModelRecommendation:
    chat: str = ""
    routing: str = ""
    vision: str = ""
    stt_size: str = ""
    npu_inference: str = ""  # placeholder — populated when NPU inference layer is available
    rationale: dict[str, str] = field(default_factory=dict)


@dataclass
class OllamaInventory:
    reachable: bool = False
    pulled: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)


@dataclass
class PolicyDiff:
    current: dict[str, str] = field(default_factory=dict)
    recommended: dict[str, str] = field(default_factory=dict)
    changed_keys: list[str] = field(default_factory=list)


@dataclass
class WarmResult:
    model: str = ""
    elapsed_ms: int = 0
    ok: bool = False
    error: str = ""


@dataclass
class CapacityLease:
    """Temporary mill-capacity residency. Does not rewrite policy.json."""

    model: str = ""
    standing: str = ""
    temporary: bool = False
    mill_class: str = ""
    pressure_event: str = ""
    reason: str = ""
    granted: bool = False
    released: bool = False
    ran_model: str = ""


@dataclass
class SockReport:
    hardware: HardwareProfile = field(default_factory=HardwareProfile)
    recommendation: ModelRecommendation = field(default_factory=ModelRecommendation)
    ollama: OllamaInventory = field(default_factory=OllamaInventory)
    diff: PolicyDiff = field(default_factory=PolicyDiff)
    warm_validation: list[WarmResult] = field(default_factory=list)
    validation_ok: bool = True
    applied: bool = False
    errors: list[str] = field(default_factory=list)


# ── PowerShell helper ──────────────────────────────────────────────────────────

def _run_ps(script: str, timeout: int = 12) -> str:
    """Run a PowerShell snippet and return stdout stripped of whitespace."""
    try:
        r = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy", "Bypass",
                "-Command", script,
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return r.stdout.strip()
    except Exception:
        return ""


def _ps_json(script: str, timeout: int = 12) -> Any:
    """Run a PowerShell snippet that emits JSON; parse and return the object."""
    raw = _run_ps(script, timeout=timeout)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


# ── hardware detection — Windows (PowerShell) ──────────────────────────────────

def _detect_cpu_windows() -> tuple[str, int]:
    data = _ps_json(
        "$c = Get-CimInstance Win32_Processor | Select-Object -First 1;"
        "[PSCustomObject]@{ Name=$c.Name.Trim(); Cores=[int]$c.NumberOfCores } | ConvertTo-Json -Compress"
    )
    if data and "Name" in data:
        return str(data["Name"]), int(data.get("Cores") or 1)
    return "unknown", 1


def _detect_ram_windows() -> float:
    data = _ps_json(
        "$b = (Get-CimInstance Win32_PhysicalMemory | Measure-Object -Property Capacity -Sum).Sum;"
        "$b | ConvertTo-Json"
    )
    if data is not None:
        try:
            return float(data) / (1024 ** 3)
        except (TypeError, ValueError):
            pass
    return 0.0


def _find_nvidia_smi() -> str | None:
    """Return the first working nvidia-smi path or None."""
    for candidate in _NVIDIA_SMI_CANDIDATES:
        try:
            r = subprocess.run(
                [candidate, "--query-gpu=name", "--format=csv,noheader"],
                capture_output=True, text=True, timeout=6,
            )
            if r.returncode == 0:
                return candidate
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    return None


def _find_rocm_smi() -> str | None:
    """Return the first working rocm-smi path or None."""
    for candidate in _ROCM_SMI_CANDIDATES:
        try:
            r = subprocess.run(
                [candidate, "--showproductname"],
                capture_output=True, text=True, timeout=6,
            )
            if r.returncode == 0:
                return candidate
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    return None


def _detect_gpu_amd_rocm(rocm_smi: str) -> tuple[float, str, list[str]]:
    """
    Use rocm-smi to get accurate dedicated VRAM for AMD GPUs.

    rocm-smi --showmeminfo vram gives exact dedicated VRAM — no shared RAM
    contamination unlike WMI AdapterRAM.
    """
    notes: list[str] = []
    try:
        # Get GPU name
        r_name = subprocess.run(
            [rocm_smi, "--showproductname", "--json"],
            capture_output=True, text=True, timeout=8,
        )
        # Get VRAM total
        r_mem = subprocess.run(
            [rocm_smi, "--showmeminfo", "vram", "--json"],
            capture_output=True, text=True, timeout=8,
        )
        gpu_name = "AMD GPU"
        vram_bytes = 0

        if r_name.returncode == 0 and r_name.stdout.strip():
            try:
                data = json.loads(r_name.stdout)
                # rocm-smi JSON: {"card0": {"Card series": "...", ...}}
                for card_data in data.values():
                    if isinstance(card_data, dict):
                        gpu_name = (
                            card_data.get("Card series")
                            or card_data.get("Card model")
                            or card_data.get("Card vendor", "AMD GPU")
                        )
                        break
            except (json.JSONDecodeError, AttributeError):
                pass

        if r_mem.returncode == 0 and r_mem.stdout.strip():
            try:
                data = json.loads(r_mem.stdout)
                for card_data in data.values():
                    if isinstance(card_data, dict):
                        total = card_data.get("VRAM Total Memory (B)") or card_data.get("vram Total Memory (B)", 0)
                        vram_bytes = int(total)
                        break
            except (json.JSONDecodeError, AttributeError, ValueError):
                pass

        if vram_bytes > 0:
            vram_gb = round(vram_bytes / (1024 ** 3), 1)
            notes.append(f"AMD VRAM via rocm-smi — dedicated VRAM only, no shared RAM contamination")
            return vram_gb, str(gpu_name), notes

    except Exception as exc:
        notes.append(f"rocm-smi found but failed: {exc}")

    return 0.0, "", notes


def _detect_gpu_windows() -> tuple[float, str, list[str]]:
    """Return (vram_gb, gpu_name, notes).

    NVIDIA: nvidia-smi with explicit path search — gives exact dedicated VRAM.
    AMD: rocm-smi with explicit path search — gives exact dedicated VRAM.
    Intel/fallback: PowerShell Get-CimInstance — AdapterRAM may include shared RAM,
    flagged in notes so the operator knows.
    """
    notes: list[str] = []

    # NVIDIA first — most accurate
    smi = _find_nvidia_smi()
    if smi:
        try:
            r = subprocess.run(
                [smi, "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=8,
            )
            if r.returncode == 0:
                for line in r.stdout.strip().splitlines():
                    parts = [p.strip() for p in line.split(",")]
                    if len(parts) >= 2:
                        try:
                            return round(float(parts[1]) / 1024, 1), parts[0], notes
                        except ValueError:
                            pass
        except Exception as exc:
            notes.append(f"nvidia-smi found but failed: {exc}")
    else:
        notes.append("nvidia-smi not found — NVIDIA driver may not be installed or GPU is not NVIDIA")

    # AMD via rocm-smi — exact dedicated VRAM, no shared RAM contamination
    rocm = _find_rocm_smi()
    if rocm:
        vram_gb, gpu_name, rocm_notes = _detect_gpu_amd_rocm(rocm)
        notes.extend(rocm_notes)
        if vram_gb > 0:
            return vram_gb, gpu_name, notes

    # Intel / fallback via CIM — dedicated VRAM only, exclude shared adapters
    data = _ps_json(
        "$gpus = Get-CimInstance Win32_VideoController |"
        " Where-Object { $_.AdapterRAM -gt 0 -and $_.AdapterRAM -lt 34359738368 } |"  # < 32 GB avoids shared RAM misreads
        " Sort-Object AdapterRAM -Descending | Select-Object -First 1;"
        " if ($gpus) { [PSCustomObject]@{ Name=$gpus.Name; VRAM=$gpus.AdapterRAM } | ConvertTo-Json -Compress }"
        " else { 'null' }"
    )
    if data and data != "null" and isinstance(data, dict):
        vram_gb = round(float(data.get("VRAM", 0)) / (1024 ** 3), 1)
        name = str(data.get("Name", "unknown GPU"))
        notes.append(
            "GPU VRAM read via WMI AdapterRAM — may include shared system RAM for AMD/Intel iGPU; "
            "treat as approximate"
        )
        return vram_gb, name, notes

    notes.append("No GPU detected or GPU VRAM could not be read")
    return 0.0, "", notes


def _detect_npu_windows(cpu_name: str) -> tuple[bool, str]:
    """Check PnP device list first; fall back to CPU name heuristic."""
    # PnP enumeration — looks for NPU/IPU/XDNA devices in device manager
    raw = _run_ps(
        "$d = Get-PnpDevice -Status OK -ErrorAction SilentlyContinue |"
        " Where-Object { $_.FriendlyName -match 'NPU|Neural|XDNA|IPU|VPU' } |"
        " Select-Object -First 1 -ExpandProperty FriendlyName;"
        " if ($d) { $d } else { '' }"
    )
    if raw:
        return True, raw.strip()

    # CPU name heuristic fallback
    cpu_lower = cpu_name.lower()
    if "ryzen ai" in cpu_lower or "xdna" in cpu_lower:
        return True, "AMD XDNA NPU (inferred from CPU model — Ryzen AI)"
    if "core ultra" in cpu_lower:
        return True, "Intel NPU (inferred from CPU model — Core Ultra)"
    if "snapdragon" in cpu_lower or "oryon" in cpu_lower:
        return True, "Qualcomm NPU (inferred from CPU model — Snapdragon X)"
    return False, ""


# ── hardware detection — non-Windows fallback ──────────────────────────────────

def _detect_cpu_fallback() -> tuple[str, int]:
    name = platform.processor() or "unknown"
    try:
        import psutil
        cores = psutil.cpu_count(logical=False) or 1
    except Exception:
        import os
        cores = os.cpu_count() or 1
    return name, cores


def _detect_ram_fallback() -> float:
    try:
        import psutil
        return psutil.virtual_memory().total / (1024 ** 3)
    except Exception:
        return 0.0


def _detect_gpu_fallback() -> tuple[float, str, list[str]]:
    smi = _find_nvidia_smi()
    notes: list[str] = []
    if smi:
        try:
            r = subprocess.run(
                [smi, "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=8,
            )
            if r.returncode == 0:
                for line in r.stdout.strip().splitlines():
                    parts = [p.strip() for p in line.split(",")]
                    if len(parts) >= 2:
                        try:
                            return round(float(parts[1]) / 1024, 1), parts[0], notes
                        except ValueError:
                            pass
        except Exception:
            pass
    notes.append("Non-Windows: GPU detection limited to nvidia-smi")
    return 0.0, "", notes


# ── public scan_hardware ───────────────────────────────────────────────────────

def scan_hardware(
    _run_ps_fn: Any = None,  # injection point for tests
) -> HardwareProfile:
    is_windows = platform.system().lower().startswith("win")
    notes: list[str] = []

    if is_windows:
        cpu_name, cpu_cores = _detect_cpu_windows()
        ram_gb = _detect_ram_windows()
        vram_gb, gpu_name, gpu_notes = _detect_gpu_windows()
        notes.extend(gpu_notes)
        npu_detected, npu_name = _detect_npu_windows(cpu_name)
    else:
        cpu_name, cpu_cores = _detect_cpu_fallback()
        ram_gb = _detect_ram_fallback()
        vram_gb, gpu_name, gpu_notes = _detect_gpu_fallback()
        notes.extend(gpu_notes)
        cpu_lower = cpu_name.lower()
        npu_detected = "ryzen ai" in cpu_lower or "core ultra" in cpu_lower
        npu_name = "NPU inferred from CPU model (non-Windows)" if npu_detected else ""
        notes.append("Non-Windows: hardware detection limited — PowerShell not available")

    storage_free_gb = 0.0
    try:
        storage_free_gb = round(shutil.disk_usage(str(ROOT)).free / (1024 ** 3), 1)
    except Exception:
        pass

    return HardwareProfile(
        cpu_name=cpu_name,
        cpu_cores=cpu_cores,
        ram_gb=round(ram_gb, 1),
        vram_gb=vram_gb,
        gpu_name=gpu_name,
        npu_detected=npu_detected,
        npu_name=npu_name,
        storage_free_gb=storage_free_gb,
        platform_str=platform.platform(),
        detection_notes=notes,
    )


# ── ollama inventory ───────────────────────────────────────────────────────────

def scan_ollama(
    ollama_base: str = OLLAMA_BASE,
    requests_get_fn: Any = None,
) -> OllamaInventory:
    try:
        if requests_get_fn is None:
            import urllib.request
            with urllib.request.urlopen(f"{ollama_base}/api/tags", timeout=3) as resp:
                data = json.loads(resp.read())
        else:
            resp = requests_get_fn(f"{ollama_base}/api/tags", timeout=3)
            data = resp.json()
        pulled = [m.get("name", "") for m in data.get("models", []) if m.get("name")]
        return OllamaInventory(reachable=True, pulled=pulled)
    except Exception:
        return OllamaInventory(reachable=False)


# ── VRAM budget and stable-pair constraint ────────────────────────────────────

# Fallback estimated VRAM required (GB) for full GPU residency at Q4_K_M quantization.
# Used when Ollama metadata is unavailable. Live query via _vram_estimate_live()
# is always preferred over these static values.
_VRAM_ESTIMATE_GB: dict[str, float] = {
    # Qwen 2.5 text
    "qwen2.5:32b":   20.0,
    "qwen2.5:14b":    9.0,
    "qwen2.5:7b":     4.5,
    "qwen3.5:9b":     6.6,
    "qwen3.5:4b":     3.4,
    "qwen3.5:2b":     2.7,
    "qwen3.5:0.8b":   1.0,
    "qwen2.5:3b":     2.0,
    # Qwen 2.5 vision
    "qwen2.5vl:72b": 42.0,
    "qwen2.5vl:14b":  9.0,
    "qwen2.5vl:7b":   4.5,
    # Phi-4 (Microsoft — strong reasoning at 14B)
    "phi4:14b":       9.0,
    "phi4":           9.0,
    # Llama
    "llama3.1:8b":    5.0,
    "llama3.2:3b":    2.0,
    "llama3.3:70b":  42.0,
    # Gemma 3
    "gemma3:27b":    17.0,
    "gemma3:12b":     7.5,
    "gemma3:4b":      2.5,
    # Mistral
    "mistral:7b":     4.5,
    "mistral-small3.1:24b": 15.0,
}

# When a model exceeds VRAM, Ollama does partial layer offload and still
# consumes most of the available VRAM.  This fraction models that behaviour.
_PARTIAL_OFFLOAD_FILL = 0.85

# Cache live VRAM estimates from Ollama to avoid repeated /api/show calls
_LIVE_VRAM_CACHE: dict[str, float] = {}


def _vram_estimate_live(
    model: str,
    ollama_base: str = OLLAMA_BASE,
) -> float | None:
    """
    Query Ollama /api/show for actual model size in bytes and convert to GB.

    Returns None if Ollama is unreachable, model is unknown, or the response
    does not include size metadata. Caches results per model name.
    """
    if model in _LIVE_VRAM_CACHE:
        return _LIVE_VRAM_CACHE[model]
    try:
        import urllib.request as _urlreq
        body = json.dumps({"name": model}).encode()
        req = _urlreq.Request(
            f"{ollama_base}/api/show",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        with _urlreq.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
        # Ollama /api/show returns model_info with parameter_count and quantization,
        # or details.parameter_size. We use size (bytes on disk) as the VRAM proxy.
        size_bytes = data.get("size") or 0
        if size_bytes and int(size_bytes) > 0:
            vram_gb = round(int(size_bytes) / (1024 ** 3), 2)
            _LIVE_VRAM_CACHE[model] = vram_gb
            return vram_gb
    except Exception:
        pass
    return None


def _vram_estimate(model: str, ollama_base: str = OLLAMA_BASE) -> float:
    """
    Return estimated full-GPU VRAM need (GB) for a model name.

    Tries Ollama /api/show first for actual model size; falls back to the
    static lookup table and then to parameter-count heuristics.
    """
    live = _vram_estimate_live(model, ollama_base)
    if live is not None:
        return live
    if model in _VRAM_ESTIMATE_GB:
        return _VRAM_ESTIMATE_GB[model]
    low = model.lower()
    if "14b" in low:
        return 9.0
    if "8b" in low or "7b" in low:
        return 4.5
    if "3b" in low:
        return 2.0
    return 4.5  # conservative default


def _effective_chat_vram(vram_gb: float, chat: str) -> float:
    """
    Estimate how much VRAM the chat model will actually occupy at runtime.

    When a model is larger than available VRAM, Ollama performs partial layer
    offload and fills the GPU.  We model this as PARTIAL_OFFLOAD_FILL * vram_gb
    rather than the full model estimate, because Ollama will always try to
    maximise GPU use even for nominally 'CPU' models.
    """
    need = _vram_estimate(chat)
    if need <= vram_gb:
        return need  # fits fully in GPU
    # Partial offload: Ollama loads as many layers as possible
    return vram_gb * _PARTIAL_OFFLOAD_FILL


def _is_stable_pair(chat: str, routing: str, vram_gb: float) -> bool:
    """
    True when chat+routing can coexist in VRAM without causing swap churn.

    A pair is stable when:
    - both models are the same (single residency, no dual-load), or
    - the chat effective VRAM + routing full VRAM fits within available VRAM, or
    - chat is genuinely too large for any GPU offload (need > 2× vram) so routing
      occupies VRAM alone without competition.
    """
    if chat == routing:
        return True  # single model, Ollama keeps one copy loaded
    chat_eff = _effective_chat_vram(vram_gb, chat)
    routing_need = _vram_estimate(routing)
    chat_full_need = _vram_estimate(chat)
    # Chat is truly CPU-only (far too large to partially offload usefully)
    if chat_full_need > 2.0 * vram_gb:
        return routing_need <= vram_gb * 0.9
    # Both can coexist fully
    return (chat_eff + routing_need) <= vram_gb


# ── preferred_models policy override ──────────────────────────────────────────

def _preferred_models() -> dict[str, str]:
    """Read preferred_models overrides from policy.json.

    Keys map to tier slots: tier_24gb_chat, tier_12gb_chat, tier_8gb_chat,
    tier_4gb_chat, tier_cpu32_chat, tier_cpu16_chat, tier_24gb_vision,
    tier_12gb_vision, tier_4gb_vision, routing.
    """
    try:
        p = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
        pm = p.get("preferred_models") or {}
        return {k: str(v) for k, v in pm.items() if k != "_comment" and v}
    except Exception:
        return {}


# ── tier mapping and model selection ──────────────────────────────────────────

def _chat_model(vram_gb: float, ram_gb: float) -> tuple[str, str]:
    pm = _preferred_models()
    if vram_gb >= 24.0:
        m = pm.get("tier_24gb_chat", "qwen2.5:32b")
        return m, f"GPU ({vram_gb:.0f} GB VRAM) supports 32B+ models"
    if vram_gb >= 12.0:
        m = pm.get("tier_12gb_chat", "phi4:14b")
        return m, f"GPU ({vram_gb:.0f} GB VRAM) fits 14B fully — strong reasoning"
    if vram_gb >= 8.0:
        m = pm.get("tier_8gb_chat", "qwen2.5:14b")
        return m, f"GPU ({vram_gb:.0f} GB VRAM) fits 14B with headroom"
    if vram_gb >= 4.0:
        # Mid-tier GPU: prefer GPU-resident 7B over CPU-based 14B.
        # A CPU 14B model still partially offloads layers to VRAM, which
        # competes with the routing model and causes swap churn on <8 GB VRAM.
        m = pm.get("tier_4gb_chat", "qwen2.5:7b")
        return m, (
            f"GPU ({vram_gb:.0f} GB VRAM) fits 7B fully — "
            "preferred over CPU 14B to avoid routing VRAM contention"
        )
    if ram_gb >= 32.0:
        m = pm.get("tier_cpu32_chat", "qwen2.5:14b")
        return m, f"32 GB+ RAM supports CPU inference for 14B (Q4 ~9 GB) — no usable GPU"
    if ram_gb >= 16.0:
        m = pm.get("tier_cpu16_chat", "llama3.1:8b")
        return m, f"16 GB+ RAM supports CPU inference for 8B"
    return "llama3.2:3b", f"Baseline — limited RAM ({ram_gb:.0f} GB) or VRAM ({vram_gb:.0f} GB)"


def _routing_model(vram_gb: float, ram_gb: float) -> tuple[str, str]:
    pm = _preferred_models()
    preferred_routing = pm.get("routing", "")
    if preferred_routing:
        return preferred_routing, f"routing model from preferred_models policy override"
    if vram_gb >= 8.0:
        return "qwen2.5:7b", f"GPU ({vram_gb:.0f} GB VRAM) — 7B routing keeps headroom for chat"
    if vram_gb >= 4.0:
        return "qwen2.5:7b", f"GPU ({vram_gb:.0f} GB VRAM) fits 7B routing — fast intent classification"
    if ram_gb >= 16.0:
        return "qwen2.5:7b", f"CPU fallback — 7B routing on {ram_gb:.0f} GB RAM"
    return "qwen2.5:7b", "Baseline routing model"


def _routing_safe_for_pair(vram_gb: float, ram_gb: float, chat_name: str) -> tuple[str, str]:
    """
    Select the best routing model that forms a stable VRAM pair with chat_name.

    Falls back progressively:
      1. Ideal routing if the pair is stable.
      2. A lighter routing model that fits alongside chat.
      3. Same model as chat (single Ollama residency — no swap at all).
    """
    ideal, ideal_why = _routing_model(vram_gb, ram_gb)
    if _is_stable_pair(chat_name, ideal, vram_gb):
        return ideal, ideal_why

    # Ideal routing would cause swap churn.  Try lighter alternatives.
    for candidate in ["llama3.2:3b", "qwen2.5:7b"]:
        if candidate != ideal and _is_stable_pair(chat_name, candidate, vram_gb):
            return candidate, (
                f"Downgraded from {ideal} — "
                f"{chat_name}+{ideal} cannot stably coexist in {vram_gb:.0f} GB VRAM; "
                f"{candidate} fits within remaining headroom"
            )

    # Last resort: same model as chat — single Ollama residency, zero swap risk.
    return chat_name, (
        f"Matched to chat model {chat_name} — "
        f"no routing model fits stably alongside chat in {vram_gb:.0f} GB VRAM; "
        "single residency eliminates swap churn"
    )


def _vision_model(vram_gb: float) -> tuple[str, str]:
    pm = _preferred_models()
    if vram_gb >= 24.0:
        m = pm.get("tier_24gb_vision", "qwen2.5vl:72b")
        return m, f"GPU ({vram_gb:.0f} GB VRAM) supports 72B vision model"
    if vram_gb >= 12.0:
        m = pm.get("tier_12gb_vision", "qwen2.5vl:14b")
        return m, f"GPU ({vram_gb:.0f} GB VRAM) fits 14B vision fully"
    m = pm.get("tier_4gb_vision", "qwen2.5vl:7b")
    return m, f"GPU ({vram_gb:.0f} GB VRAM) fits 7B vision model"


def _stt_size(cpu_cores: int, ram_gb: float) -> tuple[str, str]:
    if cpu_cores >= 12 and ram_gb >= 32.0:
        return "medium", f"{cpu_cores} cores + {ram_gb:.0f} GB RAM — medium Whisper viable"
    if cpu_cores >= 6:
        return "small", f"{cpu_cores} cores — small Whisper recommended"
    return "base", "Baseline Whisper (limited CPU)"


def _npu_inference(npu_detected: bool, npu_name: str) -> tuple[str, str]:
    """
    Return NPU inference recommendation and rationale.

    Currently a readiness hook — Nova does not yet route inference to the NPU.
    When the NPU inference layer lands, this function gates the decision.
    NPU is best suited for lightweight routing / embedding workloads where
    latency matters more than throughput and VRAM headroom is scarce.
    """
    if not npu_detected:
        return "", "No NPU detected — GPU/CPU inference only"
    # NPU detected: flag as available, note it is not yet wired into inference routing
    return "available", (
        f"NPU detected ({npu_name}) — reserved for future lightweight inference routing. "
        "Wire nova_npu_runtime when the inference layer is ready."
    )


def recommend_models(hw: HardwareProfile) -> ModelRecommendation:
    chat, chat_why = _chat_model(hw.vram_gb, hw.ram_gb)
    routing, routing_why = _routing_safe_for_pair(hw.vram_gb, hw.ram_gb, chat)
    vision, vision_why = _vision_model(hw.vram_gb)
    stt, stt_why = _stt_size(hw.cpu_cores, hw.ram_gb)
    npu, npu_why = _npu_inference(hw.npu_detected, hw.npu_name)
    return ModelRecommendation(
        chat=chat,
        routing=routing,
        vision=vision,
        stt_size=stt,
        npu_inference=npu,
        rationale={
            "chat": chat_why,
            "routing": routing_why,
            "vision": vision_why,
            "stt_size": stt_why,
            "npu_inference": npu_why,
        },
    )


# — mill capacity lease (temporary residency; does not rewrite policy) ———

# Lane measure 2026-09-01. Key is mill class + pressure_event.
# 9B won refused (world-ended / identity) and redundant+empty_claim
# (missing evidence). 9B lost redundant+inherited_attempt (paid trail).
# 14B has no class until it wins one. Missing key → standing.
_DELIBERATE_EVIDENCE: dict[tuple[str, str], str] = {
    ("refused", ""): "qwen3.5:9b",
    ("refused", "inherited_attempt"): "qwen3.5:9b",
    ("refused", "empty_claim"): "qwen3.5:9b",
    ("redundant", "empty_claim"): "qwen3.5:9b",
}


def _lease_record_path(record_path: Path | None = None) -> Path:
    if record_path is not None:
        return record_path
    try:
        from services.nova_runtime_context import RUNTIME_DIR

        return Path(RUNTIME_DIR) / "_internal" / "capacity_lease.json"
    except Exception:
        return ROOT / "runtime" / "_internal" / "capacity_lease.json"


def _standing_chat(policy_path: Path = POLICY_PATH) -> str:
    models = _read_policy(policy_path).get("models") or {}
    return str(models.get("chat") or "").strip() or "qwen2.5:7b"


def _signal_packet(signal: Any) -> dict[str, Any]:
    row = dict(signal) if isinstance(signal, dict) else {}
    return {
        "class": str(row.get("class") or "").strip().lower(),
        "controlling": bool(row.get("controlling")),
        "pressure_event": str(row.get("pressure_event") or "").strip().lower(),
        "invoke": True if row.get("invoke") is None else bool(row.get("invoke")),
        "reason": str(row.get("reason") or "").strip()[:120],
        "source": str(row.get("source") or "").strip()[:80],
    }


def _deliberate_candidate(klass: str, pressure_event: str) -> str:
    if klass == "refused":
        return "qwen3.5:9b"
    return _DELIBERATE_EVIDENCE.get((klass, pressure_event), "")


def _model_pulled(model: str, inventory: OllamaInventory) -> bool:
    name = str(model or "").strip()
    if not name:
        return False
    pulled = list(inventory.pulled or [])
    if name in pulled:
        return True
    base = name.split(":")[0]
    return any(str(item).split(":")[0] == base and str(item) == name for item in pulled)


def _temporary_feasible(model: str, hw: HardwareProfile) -> bool:
    """Can this box serve *model* as a short sip after standing is unloaded."""
    ram = float(getattr(hw, "ram_gb", 0) or 0)
    vram = float(getattr(hw, "vram_gb", 0) or 0)
    need = _vram_estimate(model)
    if ram < 16.0:
        return False
    # Sequential residency: standing is unloaded first, so the sip may split.
    if need <= vram:
        return True
    return ram >= 24.0 and vram >= 4.0


def _standing_lease(
    standing: str,
    packet: dict[str, Any],
    reason: str,
) -> CapacityLease:
    return CapacityLease(
        model=standing,
        standing=standing,
        temporary=False,
        mill_class=str(packet.get("class") or ""),
        pressure_event=str(packet.get("pressure_event") or ""),
        reason=reason,
    )


def choose_mill_capacity(
    signal: Any,
    *,
    standing: str = "",
    hw: HardwareProfile | None = None,
    inventory: OllamaInventory | None = None,
    policy_path: Path = POLICY_PATH,
) -> CapacityLease:
    """Pick capacity from mill class+pressure and hardware. Does not write policy."""
    packet = _signal_packet(signal)
    stand = str(standing or _standing_chat(policy_path) or "").strip() or "qwen2.5:7b"
    candidate = _deliberate_candidate(str(packet.get("class") or ""), str(packet.get("pressure_event") or ""))
    if not candidate or candidate == stand:
        why = "standing" if not candidate else "candidate_is_standing"
        return _standing_lease(stand, packet, why)
    pulled = inventory
    if pulled is None:
        pulled = scan_ollama()
    if not _model_pulled(candidate, pulled):
        return _standing_lease(stand, packet, "deliberate_not_pulled")
    profile = hw if hw is not None else scan_hardware()
    if not _temporary_feasible(candidate, profile):
        return _standing_lease(stand, packet, "deliberate_not_feasible")
    return CapacityLease(
        model=candidate,
        standing=stand,
        temporary=True,
        mill_class=str(packet.get("class") or ""),
        pressure_event=str(packet.get("pressure_event") or ""),
        reason="evidenced_deliberate",
    )


def _write_lease_record(lease: CapacityLease, record_path: Path | None = None) -> None:
    if record_path is None and not lease.temporary:
        return
    path = _lease_record_path(record_path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "model": lease.model,
                    "standing": lease.standing,
                    "temporary": lease.temporary,
                    "mill_class": lease.mill_class,
                    "pressure_event": lease.pressure_event,
                    "reason": lease.reason,
                    "granted": lease.granted,
                    "released": lease.released,
                    "ran_model": lease.ran_model,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    except Exception:
        pass


def _ollama_stop(model: str, stop_fn: Callable[[str], None] | None = None) -> None:
    name = str(model or "").strip()
    if not name:
        return
    if stop_fn is not None:
        stop_fn(name)
        return
    try:
        subprocess.run(
            ["ollama", "stop", name],
            capture_output=True,
            timeout=20,
            check=False,
        )
    except Exception:
        pass


def grant_capacity_lease(
    lease: CapacityLease,
    *,
    stop_fn: Callable[[str], None] | None = None,
    record_path: Path | None = None,
) -> CapacityLease:
    if lease.temporary and lease.model and lease.model != lease.standing:
        _ollama_stop(lease.standing, stop_fn=stop_fn)
    lease.granted = True
    _write_lease_record(lease, record_path)
    return lease


def release_capacity_lease(
    lease: CapacityLease,
    *,
    stop_fn: Callable[[str], None] | None = None,
    record_path: Path | None = None,
) -> CapacityLease:
    if lease.temporary and lease.model and lease.model != lease.standing:
        _ollama_stop(lease.model, stop_fn=stop_fn)
    lease.released = True
    _write_lease_record(lease, record_path)
    return lease


def run_with_mill_capacity(
    signal: Any,
    invoke_fn: Callable[[str], Any],
    *,
    standing: str = "",
    hw: HardwareProfile | None = None,
    inventory: OllamaInventory | None = None,
    policy_path: Path = POLICY_PATH,
    stop_fn: Callable[[str], None] | None = None,
    record_path: Path | None = None,
) -> tuple[CapacityLease, Any]:
    """Grant a temporary sip, invoke, unload, restore standing. Policy unchanged."""
    lease = choose_mill_capacity(
        signal,
        standing=standing,
        hw=hw,
        inventory=inventory,
        policy_path=policy_path,
    )
    before = ""
    try:
        before = policy_path.read_text(encoding="utf-8")
    except Exception:
        before = ""
    try:
        grant_capacity_lease(lease, stop_fn=stop_fn, record_path=record_path)
        result = invoke_fn(lease.model)
        lease.ran_model = lease.model
        return lease, result
    finally:
        release_capacity_lease(lease, stop_fn=stop_fn, record_path=record_path)
        try:
            after = policy_path.read_text(encoding="utf-8")
            if before and after != before:
                policy_path.write_text(before, encoding="utf-8")
        except Exception:
            pass


# — policy diff and apply ——————————————————————————————————————————————

def _read_policy(policy_path: Path = POLICY_PATH) -> dict:
    try:
        return json.loads(policy_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def build_diff(rec: ModelRecommendation, policy_path: Path = POLICY_PATH) -> PolicyDiff:
    current = _read_policy(policy_path)
    current_models = {
        "chat": current.get("models", {}).get("chat", ""),
        "routing": current.get("models", {}).get("routing", ""),
        "vision": current.get("models", {}).get("vision", ""),
        "stt_size": current.get("models", {}).get("stt_size", ""),
    }
    recommended = {
        "chat": rec.chat,
        "routing": rec.routing,
        "vision": rec.vision,
        "stt_size": rec.stt_size,
    }
    changed = [k for k in recommended if recommended[k] and recommended[k] != current_models.get(k)]
    return PolicyDiff(current=current_models, recommended=recommended, changed_keys=changed)


def apply_policy(rec: ModelRecommendation, policy_path: Path = POLICY_PATH) -> None:
    policy = _read_policy(policy_path)
    if "models" not in policy:
        policy["models"] = {}
    policy["models"]["chat"] = rec.chat
    policy["models"]["routing"] = rec.routing
    policy["models"]["vision"] = rec.vision
    policy["models"]["stt_size"] = rec.stt_size
    backup = policy_path.with_suffix(".json.sock_backup")
    backup.write_text(policy_path.read_text(encoding="utf-8"), encoding="utf-8")
    policy_path.write_text(json.dumps(policy, indent=2), encoding="utf-8")


# — missing model list —————————————————————————————————————————————————————————————————————————————

def _fill_missing(inventory: OllamaInventory, rec: ModelRecommendation) -> OllamaInventory:
    needed = {rec.chat, rec.routing, rec.vision}
    pulled_bases = {m.split(":")[0] for m in inventory.pulled}
    missing = []
    for model in sorted(needed):
        base = model.split(":")[0]
        if model not in inventory.pulled and base not in pulled_bases:
            missing.append(model)
    inventory.missing = missing
    return inventory


# — concurrent warm validation ———————————————————————————————————————————

_WARM_CLASSIFY_BUDGET_SEC = 4.0
_WARM_ROUTING_THRESHOLD_SEC = 8.0
_WARM_CHAT_THRESHOLD_SEC = 20.0


def _warm_single(
    model: str,
    ollama_base: str,
    timeout: float,
    requests_post_fn: Any = None,
) -> WarmResult:
    import time as _time
    start = _time.monotonic()
    try:
        body = json.dumps({
            "model": model,
            "messages": [{"role": "user", "content": "hi"}],
            "stream": False,
            "options": {"num_predict": 1},
        }).encode()
        if requests_post_fn is not None:
            resp = requests_post_fn(
                f"{ollama_base}/api/chat",
                data=body,
                headers={"Content-Type": "application/json"},
                timeout=timeout,
            )
            elapsed_ms = int((_time.monotonic() - start) * 1000)
            ok = bool(getattr(resp, "status_code", 0) in range(200, 300))
            err = "" if ok else f"status={getattr(resp, 'status_code', '?')}"
        else:
            import urllib.request as _urlreq
            req = _urlreq.Request(
                f"{ollama_base}/api/chat",
                data=body,
                headers={"Content-Type": "application/json"},
            )
            with _urlreq.urlopen(req, timeout=timeout) as r:
                elapsed_ms = int((_time.monotonic() - start) * 1000)
                ok = r.status == 200
                err = "" if ok else f"status={r.status}"
    except Exception as exc:
        elapsed_ms = int((_time.monotonic() - start) * 1000)
        ok = False
        err = str(exc)[:120]
    return WarmResult(model=model, elapsed_ms=elapsed_ms, ok=ok, error=err)


def validate_concurrent_warm(
    rec: ModelRecommendation,
    ollama_base: str = OLLAMA_BASE,
    requests_post_fn: Any = None,
    routing_threshold_sec: float = _WARM_ROUTING_THRESHOLD_SEC,
    chat_threshold_sec: float = _WARM_CHAT_THRESHOLD_SEC,
) -> tuple[list[WarmResult], bool]:
    """
    Probe routing then chat then routing again to stress concurrent residency.

    Sequential probing exercises the same Ollama scheduling path as real
    interactive use.  routing re-warm after chat load is the critical gate.
    """
    results: list[WarmResult] = []
    routing_timeout = routing_threshold_sec + 2.0
    r_routing = _warm_single(rec.routing, ollama_base, routing_timeout, requests_post_fn)
    results.append(r_routing)
    chat_timeout = chat_threshold_sec + 5.0
    r_chat = _warm_single(rec.chat, ollama_base, chat_timeout, requests_post_fn)
    results.append(r_chat)
    r_routing2 = _warm_single(rec.routing, ollama_base, routing_timeout, requests_post_fn)
    results.append(r_routing2)
    routing_ok = (
        r_routing.ok
        and r_routing2.ok
        and (r_routing2.elapsed_ms / 1000.0) <= routing_threshold_sec
    )
    chat_ok = r_chat.ok and (r_chat.elapsed_ms / 1000.0) <= chat_threshold_sec
    return results, bool(routing_ok and chat_ok)


# — main entry ————————————————————————————————————————————————————————————————————————————————

def run_sock(
    apply: bool = False,
    validate: bool = False,
    policy_path: Path = POLICY_PATH,
    ollama_base: str = OLLAMA_BASE,
    requests_get_fn: Any = None,
    requests_post_fn: Any = None,
) -> SockReport:
    report = SockReport()
    report.hardware = scan_hardware()
    report.recommendation = recommend_models(report.hardware)
    ollama = scan_ollama(ollama_base=ollama_base, requests_get_fn=requests_get_fn)
    report.ollama = _fill_missing(ollama, report.recommendation)
    report.diff = build_diff(report.recommendation, policy_path)

    if validate and ollama.reachable and not ollama.missing:
        warm_results, val_ok = validate_concurrent_warm(
            report.recommendation,
            ollama_base=ollama_base,
            requests_post_fn=requests_post_fn,
        )
        report.warm_validation = warm_results
        report.validation_ok = val_ok
        if not val_ok:
            report.errors.append(
                "warm_validation_failed: routing re-warm exceeded threshold after chat load"
            )

    if apply and report.diff.changed_keys and report.validation_ok:
        try:
            apply_policy(report.recommendation, policy_path)
            report.applied = True
        except Exception as exc:
            report.errors.append(f"apply failed: {exc}")
    elif apply and not report.validation_ok:
        report.errors.append("apply skipped: warm validation failed")
    return report


# ── cached status-payload accessor ────────────────────────────────────────────

import dataclasses
import threading
import time as _time

_SOCK_STATUS_CACHE: dict = {}
_SOCK_STATUS_LOCK = threading.Lock()
_SOCK_STATUS_TTL = 300  # seconds — hardware doesn't change frequently


def get_sock_status_keys() -> dict:
    """Return sock_hardware_profile / sock_recommendation / sock_policy_diff dicts.

    Runs scan_hardware() + recommend_models() + build_diff() at most once per
    TTL window so status polling doesn't pay PowerShell subprocess cost every tick.
    Returns empty dicts on any error so the caller is never blocked.
    """
    with _SOCK_STATUS_LOCK:
        now = _time.monotonic()
        if _SOCK_STATUS_CACHE and now - _SOCK_STATUS_CACHE.get("_ts", 0.0) < _SOCK_STATUS_TTL:
            return {k: v for k, v in _SOCK_STATUS_CACHE.items() if not k.startswith("_")}
        try:
            hw = scan_hardware()
            rec = recommend_models(hw)
            diff = build_diff(rec, POLICY_PATH)
            payload = {
                "sock_hardware_profile": dataclasses.asdict(hw),
                "sock_recommendation": dataclasses.asdict(rec),
                "sock_policy_diff": dataclasses.asdict(diff),
            }
        except Exception:
            payload = {
                "sock_hardware_profile": {},
                "sock_recommendation": {},
                "sock_policy_diff": {},
            }
        _SOCK_STATUS_CACHE.clear()
        _SOCK_STATUS_CACHE.update(payload)
        _SOCK_STATUS_CACHE["_ts"] = now
        return {k: v for k, v in _SOCK_STATUS_CACHE.items() if not k.startswith("_")}


def invalidate_sock_cache(reason: str = "") -> None:
    """
    Invalidate the SOCK status cache and live VRAM estimates.

    Call this whenever the Ollama model inventory changes — model pulled,
    model deleted, or Ollama restarted — so the next get_sock_status_keys()
    call re-scans hardware and re-queries Ollama rather than serving stale data.

    reason: optional string logged for diagnostics (e.g. 'model_pulled:qwen2.5:14b')
    """
    with _SOCK_STATUS_LOCK:
        _SOCK_STATUS_CACHE.clear()
        _LIVE_VRAM_CACHE.clear()


def notify_ollama_model_change(event: str, model: str = "") -> None:
    """
    Notify SOCK that Ollama's model inventory has changed.

    Wire this into wherever Nova detects Ollama model pulls or deletions.
    event: 'pulled' | 'deleted' | 'restarted'
    model: model name if known (e.g. 'qwen2.5:14b')
    """
    reason = f"{event}:{model}" if model else event
    invalidate_sock_cache(reason=reason)
