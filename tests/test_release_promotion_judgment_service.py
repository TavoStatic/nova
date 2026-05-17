from pathlib import Path

from services.release_promotion_judgment import (
    build_release_promotion_judgment,
    release_validation_record_payload,
)


def _write_record(path: Path, *, result: str = "") -> None:
    path.write_text(
        "\n".join(
            [
                "# NYO System RC Validation Record",
                "",
                "## Candidate",
                "",
                "- Artifact path: C:\\NOVA\\runtime\\exports\\release_packages\\nova-rc.zip",
                "- Artifact version: 2026.05.14.7",
                "- Release channel: rc",
                "- Manifest reviewed: yes",
                "",
                "## Environment",
                "",
                "- Machine or VM name: clean-vm",
                "- Windows version: Windows 11",
                "- Python source used during install: py -3.13",
                "- Ollama expected for this target: no",
                "",
                "## Results",
                "",
                "### Bootstrap",
                "",
                "- nova package-verify .: pass",
                "- nova install: pass",
                "",
                "### Base Validation",
                "",
                "- nova doctor: pass",
                "- nova runtime-status: pass",
                "- nova smoke-base --fix: pass",
                "- nova test: pass",
                "",
                "### Operator Surface",
                "",
                "- nova run: pass",
                "- nova webui-start --host 127.0.0.1 --port 8080: pass",
                "- /control load result: pass",
                "",
                "## Final Decision",
                "",
                f"- Result: {result}",
                "- Blocking issues: none",
                "- Non-blocking issues: none",
                "- Follow-up owner: release-clean",
            ]
        ),
        encoding="utf-8",
    )


def _release_status(record_path: Path) -> dict:
    return {
        "latest_readiness_state": "needs-promotion",
        "latest_ready_to_ship": False,
        "latest_artifact_path": "C:\\NOVA\\runtime\\exports\\release_packages\\nova-rc.zip",
        "latest_artifact_name": "nova-rc.zip",
        "latest_version": "2026.05.14.7",
        "latest_channel": "rc",
        "latest_verified_at": "2026-05-14T12:00:00-05:00",
        "latest_promoted_at": "",
        "latest_validation_seed_path": str(record_path),
    }


def test_validation_record_payload_treats_template_result_as_missing(tmp_path: Path) -> None:
    record_path = tmp_path / "nova-rc.md"
    _write_record(record_path, result="pass / pass-with-notes / fail")

    payload = release_validation_record_payload(record_path, release_status=_release_status(record_path))

    assert payload["exists"] is True
    assert payload["result_valid"] is False
    assert payload["complete"] is False
    assert "result" in payload["missing_fields"]


def test_validation_record_payload_reads_seed_continuation_values(tmp_path: Path) -> None:
    record_path = tmp_path / "nova-rc.md"
    record_path.write_text(
        "\n".join([
            "- Artifact path: ",
            "C:\\NOVA\\runtime\\exports\\release_packages\\nova-rc.zip",
            "- Artifact version: ",
            "2026.05.14.7",
            "- Release channel: ",
            "rc",
            "- Result: ",
            "pass / pass-with-notes / fail",
        ]),
        encoding="utf-8",
    )

    payload = release_validation_record_payload(record_path, release_status=_release_status(record_path))

    assert payload["fields"]["artifact path"].endswith("nova-rc.zip")
    assert payload["fields"]["artifact version"] == "2026.05.14.7"
    assert payload["fields"]["release channel"] == "rc"
    assert payload["result_valid"] is False


def test_release_promotion_judgment_reports_missing_validation_outcome(tmp_path: Path) -> None:
    record_path = tmp_path / "nova-rc.md"
    _write_record(record_path, result="")

    judgment = build_release_promotion_judgment(
        release_status=_release_status(record_path),
        branch_payload={},
        evidence_rows=[],
    )

    assert judgment["verdict"] == "incomplete"
    assert judgment["classification"] == "validation_outcome_missing"
    assert "do_not_promote_from_package_verification_only" in judgment["blocked_shortcuts"]


def test_release_promotion_judgment_accepts_complete_matching_record(tmp_path: Path) -> None:
    record_path = tmp_path / "nova-rc.md"
    _write_record(record_path, result="pass-with-notes")

    judgment = build_release_promotion_judgment(
        release_status=_release_status(record_path),
        branch_payload={},
        evidence_rows=[],
    )

    assert judgment["verdict"] == "ready"
    assert judgment["classification"] == "promotion_record_ready"
    assert judgment["validation_record"]["complete"] is True
