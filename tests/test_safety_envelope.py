import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import nova_core
import nova_safety_envelope


class TestSafetyEnvelope(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.policy_path = self.base / "policy.json"
        self.orig_policy_path = nova_core.POLICY_PATH
        self.orig_generated = nova_safety_envelope.GENERATED_DEFINITIONS_ROOT
        self.orig_promoted = nova_safety_envelope.PROMOTED_DEFINITIONS_ROOT
        self.orig_pending = nova_safety_envelope.PENDING_REVIEW_ROOT
        self.orig_quarantine = nova_safety_envelope.QUARANTINE_ROOT
        self.orig_audit = nova_safety_envelope.AUDIT_LOG
        self.orig_latest = nova_safety_envelope.LATEST_SUBCONSCIOUS

        nova_core.POLICY_PATH = self.policy_path
        nova_safety_envelope.GENERATED_DEFINITIONS_ROOT = self.base / "generated"
        nova_safety_envelope.PROMOTED_DEFINITIONS_ROOT = self.base / "promoted"
        nova_safety_envelope.PENDING_REVIEW_ROOT = self.base / "pending"
        nova_safety_envelope.QUARANTINE_ROOT = self.base / "quarantine"
        nova_safety_envelope.AUDIT_LOG = self.base / "promotion_audit.jsonl"
        nova_safety_envelope.LATEST_SUBCONSCIOUS = self.base / "latest.json"

        self._write_policy({"enabled": True, "mode": "observe"})
        self.definition_path = nova_safety_envelope.GENERATED_DEFINITIONS_ROOT / "candidate.json"
        self.definition_path.parent.mkdir(parents=True, exist_ok=True)
        self.definition_path.write_text(
            json.dumps(
                {
                    "name": "candidate",
                    "messages": [
                        "run the patch preview",
                        "check the weather now",
                        "remember my profile",
                        "plan phase 2 improvements",
                    ],
                    "family_id": "new-family",
                    "variation_id": "baseline",
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self):
        nova_core.POLICY_PATH = self.orig_policy_path
        nova_safety_envelope.GENERATED_DEFINITIONS_ROOT = self.orig_generated
        nova_safety_envelope.PROMOTED_DEFINITIONS_ROOT = self.orig_promoted
        nova_safety_envelope.PENDING_REVIEW_ROOT = self.orig_pending
        nova_safety_envelope.QUARANTINE_ROOT = self.orig_quarantine
        nova_safety_envelope.AUDIT_LOG = self.orig_audit
        nova_safety_envelope.LATEST_SUBCONSCIOUS = self.orig_latest
        self.tmp.cleanup()

    def _write_policy(self, safety_envelope: dict):
        merged_envelope = {
            "quarantine_root": str(self.base / "quarantine"),
            "pending_review_root": str(self.base / "pending"),
        }
        merged_envelope.update(safety_envelope)
        self.policy_path.write_text(
            json.dumps(
                {
                    "allowed_root": str(self.base),
                    "tools_enabled": {"web": False},
                    "web": {"enabled": False, "allow_domains": []},
                    "safety_envelope": merged_envelope,
                }
            ),
            encoding="utf-8",
        )

    def test_observe_mode_records_audit_without_copying(self):
        with mock.patch("nova_safety_envelope._run_replay", return_value={"ok": True, "reason": "ok", "comparison": {}, "report_path": ""}), \
            mock.patch("nova_safety_envelope._pool_similarity", return_value=(0.2, "other.json")), \
            mock.patch("nova_safety_envelope._family_fallback_score", return_value=0.2):
            result = nova_safety_envelope.promote_or_quarantine(self.definition_path)

        self.assertEqual(result.get("status"), "observed_review")
        self.assertTrue(nova_safety_envelope.AUDIT_LOG.exists())
        self.assertFalse((nova_safety_envelope.PROMOTED_DEFINITIONS_ROOT / self.definition_path.name).exists())

    def test_enforce_mode_routes_new_family_to_pending_review(self):
        self._write_policy({"enabled": True, "mode": "enforce", "human_veto_first_n": 3})
        with mock.patch("nova_safety_envelope._run_replay", return_value={"ok": True, "reason": "ok", "comparison": {}, "report_path": ""}), \
            mock.patch("nova_safety_envelope._pool_similarity", return_value=(0.2, "other.json")), \
            mock.patch("nova_safety_envelope._family_fallback_score", return_value=None):
            result = nova_safety_envelope.promote_or_quarantine(self.definition_path)

        self.assertEqual(result.get("status"), "pending_review")
        self.assertTrue((nova_safety_envelope.PENDING_REVIEW_ROOT / self.definition_path.name).exists())

    def test_enforce_mode_patch_filter_only_allows_promoted_matches(self):
        self._write_policy({"enabled": True, "mode": "enforce", "human_veto_first_n": 0})
        fingerprint = nova_safety_envelope._fingerprint(self.definition_path)
        nova_safety_envelope.AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
        nova_safety_envelope.AUDIT_LOG.write_text(
            json.dumps(
                {
                    "file": self.definition_path.name,
                    "fingerprint": fingerprint,
                    "status": "promoted",
                }
            )
            + "\n",
            encoding="utf-8",
        )

        selected = nova_safety_envelope.select_patch_candidate_definition_paths(nova_safety_envelope.GENERATED_DEFINITIONS_ROOT)

        self.assertEqual(selected, [self.definition_path])

    def test_short_single_turn_candidate_skips_diversity_gate(self):
        self.definition_path.write_text(
            json.dumps(
                {
                    "name": "short",
                    "messages": ["go ahead"],
                    "family_id": "weather-continuation-fallthrough-family",
                    "variation_id": "bare_go_ahead",
                }
            ),
            encoding="utf-8",
        )
        self._write_policy({"enabled": True, "mode": "enforce", "human_veto_first_n": 0, "diversity_min_messages": 3})
        with mock.patch("nova_safety_envelope._run_replay", return_value={"ok": True, "reason": "ok", "comparison": {}, "report_path": ""}), \
            mock.patch("nova_safety_envelope._pool_similarity", return_value=(0.2, "other.json")), \
            mock.patch("nova_safety_envelope._family_fallback_score", return_value=0.2):
            result = nova_safety_envelope.promote_or_quarantine(self.definition_path)

        self.assertEqual(result.get("status"), "promoted")
        gates = result.get("gates") or {}
        self.assertFalse((gates.get("diversity") or {}).get("measured"))

    def test_pending_review_history_satisfies_human_veto_window(self):
        self._write_policy({"enabled": True, "mode": "enforce", "human_veto_first_n": 3, "diversity_min_messages": 3})
        nova_safety_envelope.AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
        rows = [
            {"file": "a.json", "family_id": "new-family", "status": "pending_review"},
            {"file": "b.json", "family_id": "new-family", "status": "pending_review"},
            {"file": "c.json", "family_id": "new-family", "status": "pending_review"},
        ]
        nova_safety_envelope.AUDIT_LOG.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")

        with mock.patch("nova_safety_envelope._run_replay", return_value={"ok": True, "reason": "ok", "comparison": {}, "report_path": ""}), \
            mock.patch("nova_safety_envelope._pool_similarity", return_value=(0.2, "other.json")), \
            mock.patch("nova_safety_envelope._family_fallback_score", return_value=0.2), \
            mock.patch("nova_safety_envelope._diversity_score", return_value=3.1):
            result = nova_safety_envelope.promote_or_quarantine(self.definition_path)

        self.assertEqual(result.get("status"), "promoted")
        self.assertFalse(result.get("review_required"))

    def test_replay_retry_recovers_transient_failure(self):
        self._write_policy({
            "enabled": True,
            "mode": "enforce",
            "human_veto_first_n": 0,
            "replay_attempts": 2,
            "diversity_min_messages": 3,
        })

        with mock.patch(
            "nova_safety_envelope._run_replay",
            side_effect=[
                {"ok": False, "reason": "replay_failed:exit:0", "comparison": {}, "report_path": ""},
                {"ok": True, "reason": "ok", "comparison": {}, "report_path": ""},
            ],
        ), mock.patch("nova_safety_envelope._pool_similarity", return_value=(0.2, "other.json")), mock.patch(
            "nova_safety_envelope._family_fallback_score", return_value=0.2
        ):
            result = nova_safety_envelope.promote_or_quarantine(self.definition_path)

        self.assertEqual(result.get("status"), "promoted")
        replay_gate = (result.get("gates") or {}).get("replay_stability") or {}
        self.assertTrue(replay_gate.get("passed"))
        self.assertEqual(replay_gate.get("attempts_used"), 2)
