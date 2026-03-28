"""Tests for JSON line parsing helpers."""

from cursor_claw.stream_parse import (
    event_type,
    extract_assistant_text,
    extract_session_id,
    parse_event_line,
)


def test_parse_event_line_skips_garbage() -> None:
    assert parse_event_line("") is None
    assert parse_event_line("not json") is None


def test_session_id_top_level() -> None:
    obj = {"type": "system", "session_id": "sess-1"}
    assert extract_session_id(obj) == "sess-1"


def test_assistant_nested_content() -> None:
    obj = {
        "type": "assistant",
        "message": {"content": [{"type": "text", "text": "hello"}]},
    }
    assert extract_assistant_text(obj) == "hello"
    assert event_type(obj) == "assistant"
