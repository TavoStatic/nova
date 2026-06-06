from __future__ import annotations

import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from services.sock_service import (
    HardwareProfile,
    ModelRecommendation,
    OllamaInventory,
    PolicyDiff,
    SockReport,
    WarmResult,
    _fill_missing,
    _is_stable_pair,
    _routing_safe_for_pair,
    build_diff,
    recommend_models,
    run_sock,
    scan_ollama,
    validate_concurrent_warm,
)


def _hw(**kwargs) -> HardwareProfile:
    defaults = dict(
        cpu_name="AMD Ryzen AI 9 HX 370",
        cpu_cores=12,
        ram_gb=32.0,
        vram_gb=6.0,
        gpu_name="NVIDIA RTX 4050",
        npu_detected=True,
        npu_name="AMD XDNA NPU (Ryzen AI)",
        storage_free_gb=380.0,
        platform_str="Windows-11",
    )
    defaults.update(kwargs)
    return HardwareProfile(**defaults)


def _policy_path(tmp_path: Path, models: dict) -> Path:
    p = tmp_path / "policy.json"
    p.write_text(json.dumps({"models": models}), encoding="utf-8")
    return p


class TestRecommendModels(unittest.TestCase):

    def test_mid_vram_selects_gpu_7b_chat_not_cpu_14b(self):
        # 6 GB VRAM + 32 GB RAM: previously selected CPU 14b, which caused
        # routing VRAM contention.  Now 7b GPU is preferred.
        hw = _hw(ram_gb=32.0, vram_gb=6.0)
        rec = recommend_models(hw)
        self.assertEqual(rec.chat, "qwen2.5:7b")

    def test_mid_vram_produces_stable_pair(self):
        # The recommended pair for 6 GB VRAM must be VRAM-stable (no swap churn).
        hw = _hw(ram_gb=32.0, vram_gb=6.0)
        rec = recommend_models(hw)
        self.assertTrue(_is_stable_pair(rec.chat, rec.routing, hw.vram_gb))

    def test_high_vram_selects_gpu_chat_model(self):
        hw = _hw(ram_gb=32.0, vram_gb=16.0)
        rec = recommend_models(hw)
        self.assertIn("14b", rec.chat)

    def test_no_usable_gpu_falls_back_to_cpu_14b_on_large_ram(self):
        # When VRAM < 4 GB, the CPU 14b path activates for large-RAM machines.
        hw = _hw(ram_gb=32.0, vram_gb=2.0)
        rec = recommend_models(hw)
        self.assertEqual(rec.chat, "qwen2.5:14b")

    def test_limited_ram_and_vram_falls_back_to_3b(self):
        hw = _hw(ram_gb=8.0, vram_gb=2.0)
        rec = recommend_models(hw)
        self.assertEqual(rec.chat, "llama3.2:3b")

    def test_routing_safe_pair_matches_chat_when_split_pair_unstable(self):
        # 6 GB VRAM: qwen2.5:7b chat + qwen2.5:7b routing is stable (same model).
        routing, _ = _routing_safe_for_pair(6.0, 32.0, "qwen2.5:7b")
        self.assertTrue(_is_stable_pair("qwen2.5:7b", routing, 6.0))

    def test_8gb_vram_produces_stable_pair_with_downgraded_routing(self):
        # 8 GB VRAM: llama3.1:8b chat (5 GB) + qwen2.5:14b routing (9 GB) cannot
        # coexist (14 GB > 8 GB), so routing downgrades to llama3.2:3b (2 GB).
        # This is an explicit quality tradeoff — locked here so any future change
        # to this tier requires a deliberate decision.
        hw = _hw(ram_gb=16.0, vram_gb=8.0)
        rec = recommend_models(hw)
        self.assertEqual(rec.chat, "llama3.1:8b")
        self.assertEqual(rec.routing, "llama3.2:3b")
        self.assertTrue(_is_stable_pair(rec.chat, rec.routing, hw.vram_gb))

    def test_routing_upgrades_on_high_vram(self):
        hw = _hw(vram_gb=12.0)
        rec = recommend_models(hw)
        self.assertEqual(rec.routing, "qwen2.5:14b")

    def test_vision_stays_7b_on_low_vram(self):
        hw = _hw(vram_gb=6.0)
        rec = recommend_models(hw)
        self.assertEqual(rec.vision, "qwen2.5vl:7b")

    def test_vision_upgrades_on_high_vram(self):
        hw = _hw(vram_gb=10.0)
        rec = recommend_models(hw)
        self.assertEqual(rec.vision, "qwen2.5vl:14b")

    def test_stt_upgrades_to_medium_on_capable_hardware(self):
        hw = _hw(cpu_cores=12, ram_gb=32.0)
        rec = recommend_models(hw)
        self.assertEqual(rec.stt_size, "medium")

    def test_stt_small_on_moderate_cpu(self):
        hw = _hw(cpu_cores=6, ram_gb=16.0)
        rec = recommend_models(hw)
        self.assertEqual(rec.stt_size, "small")

    def test_stt_base_on_low_core_count(self):
        hw = _hw(cpu_cores=2, ram_gb=8.0)
        rec = recommend_models(hw)
        self.assertEqual(rec.stt_size, "base")

    def test_rationale_populated_for_all_roles(self):
        rec = recommend_models(_hw())
        for role in ("chat", "routing", "vision", "stt_size"):
            self.assertIn(role, rec.rationale)
            self.assertTrue(rec.rationale[role])


class TestStablePair(unittest.TestCase):

    def test_same_model_is_always_stable(self):
        self.assertTrue(_is_stable_pair("qwen2.5:7b", "qwen2.5:7b", 4.0))
        self.assertTrue(_is_stable_pair("qwen2.5:14b", "qwen2.5:14b", 2.0))

    def test_both_fitting_in_vram_is_stable(self):
        # 7b (~4.5 GB) + 3b (~2 GB) = 6.5 GB in 8 GB VRAM → stable
        self.assertTrue(_is_stable_pair("qwen2.5:7b", "llama3.2:3b", 8.0))

    def test_split_pair_on_small_vram_is_unstable(self):
        # 14b partial offload fills 6 GB; 7b routing needs 4.5 GB → churn
        self.assertFalse(_is_stable_pair("qwen2.5:14b", "qwen2.5:7b", 6.0))

    def test_truly_cpu_only_chat_allows_routing_in_vram(self):
        # 14b needs 9 GB; VRAM is only 3 GB → 9 > 2×3 = truly CPU-only
        # routing 7b needs 4.5 GB > 3×0.9 = 2.7 GB → still doesn't fit
        self.assertFalse(_is_stable_pair("qwen2.5:14b", "qwen2.5:7b", 3.0))
        # But 3b (2 GB) routing fits within 3 GB × 0.9 = 2.7 GB → stable
        self.assertTrue(_is_stable_pair("qwen2.5:14b", "llama3.2:3b", 3.0))

    def test_routing_safe_for_pair_avoids_unstable_split(self):
        # Old SOCK picked qwen2.5:7b routing for 14b chat on 6 GB VRAM.
        # The new logic must NOT pick an unstable routing.
        routing, _ = _routing_safe_for_pair(6.0, 32.0, "qwen2.5:14b")
        self.assertTrue(_is_stable_pair("qwen2.5:14b", routing, 6.0))


class TestValidateConcurrentWarm(unittest.TestCase):

    def _make_fast_post(self, status: int = 200):
        class _Resp:
            def __init__(self):
                self.status_code = status
        return lambda *a, **kw: _Resp()

    def _make_slow_post(self, delay: float = 10.0, status: int = 200):
        import time as _t
        class _Resp:
            def __init__(self):
                self.status_code = status
        def _fn(*a, **kw):
            _t.sleep(delay)
            return _Resp()
        return _fn

    def test_fast_warm_returns_ok(self):
        rec = ModelRecommendation(chat="llama3.2:3b", routing="llama3.2:3b")
        results, ok = validate_concurrent_warm(
            rec, requests_post_fn=self._make_fast_post(200),
            routing_threshold_sec=5.0, chat_threshold_sec=15.0,
        )
        self.assertTrue(ok)
        self.assertEqual(len(results), 3)
        self.assertTrue(all(r.ok for r in results))

    def test_slow_routing_rewarm_marks_validation_failed(self):
        import time as _t
        call_count = [0]
        class _Resp:
            def __init__(self):
                self.status_code = 200
        def _post(*a, **kw):
            call_count[0] += 1
            # Third call (routing re-warm after chat load) is slow
            if call_count[0] == 3:
                _t.sleep(0.2)  # simulate exceeding threshold in test
            return _Resp()
        rec = ModelRecommendation(chat="qwen2.5:7b", routing="qwen2.5:7b")
        results, ok = validate_concurrent_warm(
            rec, requests_post_fn=_post,
            routing_threshold_sec=0.05,  # very tight threshold to trigger failure
            chat_threshold_sec=15.0,
        )
        self.assertFalse(ok)
        self.assertEqual(len(results), 3)

    def test_unreachable_ollama_returns_not_ok(self):
        def _failing(*a, **kw):
            raise ConnectionRefusedError("offline")
        rec = ModelRecommendation(chat="llama3.2:3b", routing="llama3.2:3b")
        results, ok = validate_concurrent_warm(
            rec, requests_post_fn=_failing,
            routing_threshold_sec=5.0, chat_threshold_sec=15.0,
        )
        self.assertFalse(ok)
        self.assertTrue(all(not r.ok for r in results))


class TestBuildDiff(unittest.TestCase):

    def test_detects_changed_keys(self):
        import tempfile, os
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "policy.json"
            p.write_text(json.dumps({"models": {
                "chat": "llama3.2:3b",
                "routing": "qwen2.5vl:7b",
                "vision": "qwen2.5vl:7b",
                "stt_size": "base",
            }}), encoding="utf-8")
            rec = ModelRecommendation(
                chat="qwen2.5:14b",
                routing="qwen2.5:7b",
                vision="qwen2.5vl:7b",
                stt_size="medium",
            )
            diff = build_diff(rec, policy_path=p)
            self.assertIn("chat", diff.changed_keys)
            self.assertIn("stt_size", diff.changed_keys)
            self.assertNotIn("vision", diff.changed_keys)

    def test_no_changes_when_policy_matches(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "policy.json"
            p.write_text(json.dumps({"models": {
                "chat": "qwen2.5:14b",
                "routing": "qwen2.5:7b",
                "vision": "qwen2.5vl:7b",
                "stt_size": "medium",
            }}), encoding="utf-8")
            rec = ModelRecommendation(
                chat="qwen2.5:14b", routing="qwen2.5:7b",
                vision="qwen2.5vl:7b", stt_size="medium",
            )
            diff = build_diff(rec, policy_path=p)
            self.assertEqual(diff.changed_keys, [])


class TestScanOllama(unittest.TestCase):

    def test_parses_pulled_models(self):
        def _get(url, timeout=3):
            return SimpleNamespace(json=lambda: {
                "models": [{"name": "llama3.2:3b"}, {"name": "qwen2.5vl:7b"}]
            })
        inv = scan_ollama(requests_get_fn=_get)
        self.assertTrue(inv.reachable)
        self.assertIn("llama3.2:3b", inv.pulled)

    def test_unreachable_ollama(self):
        def _get(url, timeout=3):
            raise ConnectionRefusedError("offline")
        inv = scan_ollama(requests_get_fn=_get)
        self.assertFalse(inv.reachable)
        self.assertEqual(inv.pulled, [])


class TestFillMissing(unittest.TestCase):

    def test_flags_unpulled_recommended_model(self):
        inv = OllamaInventory(reachable=True, pulled=["llama3.2:3b", "qwen2.5vl:7b"])
        rec = ModelRecommendation(chat="qwen2.5:14b", routing="qwen2.5:7b", vision="qwen2.5vl:7b")
        result = _fill_missing(inv, rec)
        self.assertIn("qwen2.5:14b", result.missing)

    def test_no_missing_when_all_pulled(self):
        inv = OllamaInventory(reachable=True, pulled=["qwen2.5:14b", "qwen2.5:7b", "qwen2.5vl:7b"])
        rec = ModelRecommendation(chat="qwen2.5:14b", routing="qwen2.5:7b", vision="qwen2.5vl:7b")
        result = _fill_missing(inv, rec)
        self.assertEqual(result.missing, [])


class TestRunSock(unittest.TestCase):

    def test_run_returns_report_with_hardware_and_recommendation(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "policy.json"
            p.write_text(json.dumps({"models": {
                "chat": "llama3.2:3b", "routing": "qwen2.5vl:7b",
                "vision": "qwen2.5vl:7b", "stt_size": "base",
            }}), encoding="utf-8")

            def _fake_get(url, timeout=3):
                return SimpleNamespace(json=lambda: {"models": []})

            with mock.patch("services.sock_service.scan_hardware") as mock_hw:
                mock_hw.return_value = _hw()
                report = run_sock(policy_path=p, requests_get_fn=_fake_get)

            self.assertIsInstance(report, SockReport)
            self.assertIsInstance(report.recommendation, ModelRecommendation)
            self.assertTrue(report.diff.changed_keys)
            self.assertFalse(report.applied)

    def test_apply_writes_policy(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "policy.json"
            p.write_text(json.dumps({"models": {
                "chat": "llama3.2:3b", "routing": "qwen2.5vl:7b",
                "vision": "qwen2.5vl:7b", "stt_size": "base",
            }}), encoding="utf-8")

            def _fake_get(url, timeout=3):
                return SimpleNamespace(json=lambda: {"models": []})

            with mock.patch("services.sock_service.scan_hardware") as mock_hw:
                mock_hw.return_value = _hw()
                report = run_sock(apply=True, policy_path=p, requests_get_fn=_fake_get)

            self.assertTrue(report.applied)
            written = json.loads(p.read_text(encoding="utf-8"))
            self.assertEqual(written["models"]["chat"], "qwen2.5:7b")
            self.assertTrue((Path(tmp) / "policy.json.sock_backup").exists())

    def test_no_apply_when_policy_already_optimal(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "policy.json"

            with mock.patch("services.sock_service.scan_hardware") as mock_hw:
                mock_hw.return_value = _hw()
                # Pre-fill with what SOCK would recommend
                from services.sock_service import recommend_models
                rec = recommend_models(_hw())
                p.write_text(json.dumps({"models": {
                    "chat": rec.chat, "routing": rec.routing,
                    "vision": rec.vision, "stt_size": rec.stt_size,
                }}), encoding="utf-8")
                report = run_sock(apply=True, policy_path=p)

            self.assertFalse(report.applied)
            self.assertEqual(report.diff.changed_keys, [])


if __name__ == "__main__":
    unittest.main()


class TestDetectionWindows(unittest.TestCase):
    """Tests for the PowerShell-backed detection functions.
    All subprocess calls are mocked so these run on any platform."""

    def test_detect_cpu_windows_parses_ps_json(self):
        with mock.patch("services.sock_service._ps_json") as m:
            m.return_value = {"Name": "AMD Ryzen AI 9 HX 370", "Cores": 12}
            from services.sock_service import _detect_cpu_windows
            name, cores = _detect_cpu_windows()
        self.assertEqual(name, "AMD Ryzen AI 9 HX 370")
        self.assertEqual(cores, 12)

    def test_detect_cpu_windows_falls_back_on_none(self):
        with mock.patch("services.sock_service._ps_json", return_value=None):
            from services.sock_service import _detect_cpu_windows
            name, cores = _detect_cpu_windows()
        self.assertEqual(name, "unknown")
        self.assertEqual(cores, 1)

    def test_detect_ram_windows_converts_bytes(self):
        # 32 GB in bytes
        with mock.patch("services.sock_service._ps_json", return_value=34359738368.0):
            from services.sock_service import _detect_ram_windows
            ram = _detect_ram_windows()
        self.assertAlmostEqual(ram, 32.0, places=1)

    def test_detect_ram_windows_returns_zero_on_none(self):
        with mock.patch("services.sock_service._ps_json", return_value=None):
            from services.sock_service import _detect_ram_windows
            ram = _detect_ram_windows()
        self.assertEqual(ram, 0.0)

    def test_detect_gpu_windows_nvidia_smi_path(self):
        """When nvidia-smi is found, VRAM comes from its output."""
        smi_output = "NVIDIA GeForce RTX 4050 Laptop GPU, 6144\n"
        with mock.patch("services.sock_service._find_nvidia_smi", return_value="nvidia-smi"), \
             mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = mock.Mock(returncode=0, stdout=smi_output)
            from services.sock_service import _detect_gpu_windows
            vram, name, notes = _detect_gpu_windows()
        self.assertAlmostEqual(vram, 6.0, places=0)
        self.assertIn("RTX 4050", name)
        self.assertEqual(notes, [])

    def test_detect_gpu_windows_falls_back_to_cim(self):
        """When nvidia-smi is absent, falls back to CIM with approximate note."""
        with mock.patch("services.sock_service._find_nvidia_smi", return_value=None), \
             mock.patch("services.sock_service._ps_json") as mock_ps:
            mock_ps.return_value = {"Name": "AMD Radeon RX 7800 XT", "VRAM": 17179869184}
            from services.sock_service import _detect_gpu_windows
            vram, name, notes = _detect_gpu_windows()
        self.assertAlmostEqual(vram, 16.0, places=0)
        self.assertIn("AMD Radeon", name)
        self.assertTrue(any("approximate" in n for n in notes))

    def test_detect_gpu_windows_no_gpu_returns_zero(self):
        with mock.patch("services.sock_service._find_nvidia_smi", return_value=None), \
             mock.patch("services.sock_service._ps_json", return_value=None):
            from services.sock_service import _detect_gpu_windows
            vram, name, notes = _detect_gpu_windows()
        self.assertEqual(vram, 0.0)
        self.assertEqual(name, "")

    def test_detect_npu_windows_pnp_device_found(self):
        with mock.patch("services.sock_service._run_ps", return_value="AMD XDNA NPU"):
            from services.sock_service import _detect_npu_windows
            detected, label = _detect_npu_windows("AMD Ryzen AI 9 HX 370")
        self.assertTrue(detected)
        self.assertIn("XDNA", label)

    def test_detect_npu_windows_falls_back_to_cpu_name(self):
        with mock.patch("services.sock_service._run_ps", return_value=""):
            from services.sock_service import _detect_npu_windows
            detected, label = _detect_npu_windows("AMD Ryzen AI 9 HX 370")
        self.assertTrue(detected)
        self.assertIn("Ryzen AI", label)

    def test_detect_npu_windows_not_detected_on_standard_cpu(self):
        with mock.patch("services.sock_service._run_ps", return_value=""):
            from services.sock_service import _detect_npu_windows
            detected, label = _detect_npu_windows("Intel Core i7-12700H")
        self.assertFalse(detected)
        self.assertEqual(label, "")

    def test_find_nvidia_smi_returns_working_path(self):
        def _fake_run(cmd, **kwargs):
            if "nvidia-smi" in cmd[0]:
                return mock.Mock(returncode=0, stdout="RTX 4050\n")
            return mock.Mock(returncode=1, stdout="")
        with mock.patch("subprocess.run", side_effect=_fake_run):
            from services.sock_service import _find_nvidia_smi
            result = _find_nvidia_smi()
        self.assertEqual(result, "nvidia-smi")

    def test_find_nvidia_smi_returns_none_when_absent(self):
        with mock.patch("subprocess.run", side_effect=FileNotFoundError):
            from services.sock_service import _find_nvidia_smi
            result = _find_nvidia_smi()
        self.assertIsNone(result)
