import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_smoke_base_frontdoor_does_not_start_guard() -> None:
    script = (ROOT / "nova.ps1").read_text(encoding="utf-8")
    match = re.search(
        r"function Invoke-NovaSmoke\(\[string\]\$tier=\"runtime\", \[bool\]\$useFix=\$false\) \{(?P<body>.*?)\nfunction Ensure-Logs",
        script,
        flags=re.S,
    )
    assert match is not None
    body = match.group("body")
    base_match = re.search(
        r'if \(\$tier -ieq "base"\) \{(?P<body>.*?)\n  \}',
        body,
        flags=re.S,
    )
    assert base_match is not None
    base_body = base_match.group("body")

    assert 'SMOKEPY "--tier" "base"' in base_body
    assert "Start-Process" not in base_body
    assert "GUARDPY" not in base_body
