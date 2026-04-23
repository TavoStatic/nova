from services.nova_keyword_tools import handle_keywords
from services.nova_keyword_tools import is_brief_command_form


def test_is_brief_command_form_rejects_questions():
    assert not is_brief_command_form("read notes.txt?", "read", 2)


def test_handle_keywords_routes_camera_and_find():
    assert handle_keywords(
        "camera sunset",
        tool_screen_fn=lambda: "screen",
        tool_camera_fn=lambda prompt: f"camera:{prompt}",
        tool_ls_fn=lambda value: f"ls:{value}",
        tool_read_fn=lambda value: f"read:{value}",
        tool_find_fn=lambda kw, folder: f"find:{kw}|{folder}",
        tool_health_fn=lambda: "health",
        is_brief_command_form_fn=is_brief_command_form,
    ) == ("tool", "camera", "camera:sunset")

    assert handle_keywords(
        "find todo docs",
        tool_screen_fn=lambda: "screen",
        tool_camera_fn=lambda prompt: f"camera:{prompt}",
        tool_ls_fn=lambda value: f"ls:{value}",
        tool_read_fn=lambda value: f"read:{value}",
        tool_find_fn=lambda kw, folder: f"find:{kw}|{folder}",
        tool_health_fn=lambda: "health",
        is_brief_command_form_fn=is_brief_command_form,
    ) == ("tool", "find", "find:todo|docs")


def test_handle_keywords_returns_none_for_non_keyword_text():
    assert (
        handle_keywords(
            "tell me something interesting",
            tool_screen_fn=lambda: "screen",
            tool_camera_fn=lambda prompt: f"camera:{prompt}",
            tool_ls_fn=lambda value: f"ls:{value}",
            tool_read_fn=lambda value: f"read:{value}",
            tool_find_fn=lambda kw, folder: f"find:{kw}|{folder}",
            tool_health_fn=lambda: "health",
            is_brief_command_form_fn=is_brief_command_form,
        )
        is None
    )
