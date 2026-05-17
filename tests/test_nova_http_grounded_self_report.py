import nova_http


def test_http_no_longer_exposes_grounded_self_report_phrase_helper() -> None:
    assert not hasattr(nova_http, "_grounded_self_report_reply")


def test_core_no_longer_exposes_grounded_self_report_phrase_helper() -> None:
    assert not hasattr(nova_http.nova_core, "grounded_self_report_reply")
