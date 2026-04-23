from __future__ import annotations

import json
from pathlib import Path


class ReleaseStatusService:
    """Own release ledger parsing and latest release readiness summaries."""

    @staticmethod
    def ledger_entries(ledger_path: Path, limit: int = 20) -> list[dict]:
        try:
            if not Path(ledger_path).exists():
                return []
            entries: list[dict] = []
            lines = Path(ledger_path).read_text(encoding="utf-8", errors="ignore").splitlines()
            for line in lines:
                text = str(line or "").strip()
                if not text:
                    continue
                try:
                    data = json.loads(text)
                except Exception:
                    continue
                if isinstance(data, dict):
                    entries.append(data)
            entries.sort(key=lambda item: str(item.get("recorded_at") or ""), reverse=True)
            return entries[: max(1, int(limit))]
        except Exception:
            return []

    @staticmethod
    def entry_matches_build(entry: dict, build_entry: dict) -> bool:
        if not isinstance(entry, dict) or not isinstance(build_entry, dict):
            return False
        entry_artifact_path = str(entry.get("artifact_path") or "").strip()
        build_artifact_path = str(build_entry.get("artifact_path") or "").strip()
        if entry_artifact_path and entry_artifact_path == build_artifact_path:
            return True
        entry_version = str(entry.get("artifact_version") or "").strip()
        build_version = str(build_entry.get("artifact_version") or "").strip()
        entry_channel = str(entry.get("release_channel") or "").strip()
        build_channel = str(build_entry.get("release_channel") or "").strip()
        entry_label = str(entry.get("release_label") or "").strip()
        build_label = str(build_entry.get("release_label") or "").strip()
        return bool(entry_version and entry_version == build_version and entry_channel == build_channel and entry_label == build_label)

    def status_payload(self, ledger_path: Path, limit: int = 8) -> dict:
        out = {
            "ok": True,
            "ledger_path": str(ledger_path),
            "latest_state": "no-builds",
            "latest_readiness_state": "no-builds",
            "latest_ready_to_ship": False,
            "latest_readiness_note": "No release builds are recorded yet.",
            "latest_artifact_path": "",
            "latest_artifact_name": "",
            "latest_version": "",
            "latest_channel": "",
            "latest_label": "",
            "latest_build_recorded_at": "",
            "latest_verified_at": "",
            "latest_verification_target": "",
            "latest_promoted_at": "",
            "latest_validation_result": "",
            "latest_validation_note": "",
            "latest_follow_up_owner": "",
            "latest_validation_machine": "",
            "latest_validation_seed_path": "",
            "recent_entries": [],
        }
        entries = self.ledger_entries(ledger_path, max(6, int(limit)))
        if not entries:
            return out

        recent_entries: list[dict] = []
        for entry in entries[: max(1, int(limit))]:
            if not isinstance(entry, dict):
                continue
            recent_entries.append({
                "recorded_at": str(entry.get("recorded_at") or ""),
                "event": str(entry.get("event") or ""),
                "version": str(entry.get("artifact_version") or ""),
                "channel": str(entry.get("release_channel") or ""),
                "label": str(entry.get("release_label") or ""),
                "result": str(entry.get("validation_result") or entry.get("verification_result") or ""),
                "note": str(entry.get("validation_note") or entry.get("verification_note") or ""),
                "artifact_name": str(entry.get("artifact_name") or ""),
                "artifact_path": str(entry.get("artifact_path") or ""),
                "verification_target_path": str(entry.get("verification_target_path") or ""),
                "validation_record_seed_path": str(entry.get("validation_record_seed_path") or ""),
            })
        out["recent_entries"] = recent_entries

        build_entries = [entry for entry in entries if str(entry.get("event") or "") == "build"]
        if not build_entries:
            out["latest_state"] = "ledger-without-builds"
            return out

        latest_build = build_entries[0]
        matching_verifications = [
            entry for entry in entries
            if str(entry.get("event") or "") == "verify" and self.entry_matches_build(entry, latest_build)
        ]
        matching_promotions = [
            entry for entry in entries
            if str(entry.get("event") or "") == "promotion" and self.entry_matches_build(entry, latest_build)
        ]
        latest_verification = matching_verifications[0] if matching_verifications else None
        latest_promotion = matching_promotions[0] if matching_promotions else None

        latest_state = "built-only"
        if latest_promotion:
            result = str(latest_promotion.get("validation_result") or "").strip()
            latest_state = f"promoted-{result}" if result else "promoted"

        readiness_state = "needs-verification"
        ready_to_ship = False
        readiness_note = "Latest build has not been re-verified."
        if latest_verification:
            if latest_promotion is None:
                readiness_state = "needs-promotion"
                readiness_note = "Latest build was verified, but no validation outcome is recorded yet."
            else:
                result = str(latest_promotion.get("validation_result") or "").strip().lower()
                if result == "pass":
                    readiness_state = "ready"
                    ready_to_ship = True
                    readiness_note = "Latest build is verified and promoted with a pass result."
                elif result == "pass-with-notes":
                    readiness_state = "ready-with-notes"
                    ready_to_ship = True
                    readiness_note = "Latest build is verified and promoted with notes."
                elif result == "fail":
                    readiness_state = "blocked"
                    readiness_note = "Latest build has a failing validation result."
                else:
                    readiness_state = "needs-promotion"
                    readiness_note = "Latest build has a promotion entry without a recognized validation result."

        out.update({
            "latest_state": latest_state,
            "latest_readiness_state": readiness_state,
            "latest_ready_to_ship": ready_to_ship,
            "latest_readiness_note": readiness_note,
            "latest_artifact_path": str(latest_build.get("artifact_path") or ""),
            "latest_artifact_name": str(latest_build.get("artifact_name") or ""),
            "latest_version": str(latest_build.get("artifact_version") or ""),
            "latest_channel": str(latest_build.get("release_channel") or ""),
            "latest_label": str(latest_build.get("release_label") or ""),
            "latest_build_recorded_at": str(latest_build.get("recorded_at") or ""),
            "latest_verified_at": str((latest_verification or {}).get("recorded_at") or ""),
            "latest_verification_target": str((latest_verification or {}).get("verification_target_path") or (latest_verification or {}).get("artifact_path") or ""),
            "latest_promoted_at": str((latest_promotion or {}).get("recorded_at") or ""),
            "latest_validation_result": str((latest_promotion or {}).get("validation_result") or ""),
            "latest_validation_note": str((latest_promotion or {}).get("validation_note") or ""),
            "latest_follow_up_owner": str((latest_promotion or {}).get("follow_up_owner") or ""),
            "latest_validation_machine": str((latest_promotion or {}).get("validation_machine") or ""),
            "latest_validation_seed_path": str(latest_build.get("validation_record_seed_path") or ""),
        })
        return out


RELEASE_STATUS_SERVICE = ReleaseStatusService()