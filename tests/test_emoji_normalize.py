"""Mattermost reaction emoji_name normalization."""

from cursor_claw.channels.mattermost import _normalize_emoji


def test_strip_colons() -> None:
    assert _normalize_emoji(":eyes:") == "eyes"
    assert _normalize_emoji("eyes") == "eyes"
    assert _normalize_emoji("  :+1:  ") == "+1"


def test_empty_defaults_to_eyes() -> None:
    assert _normalize_emoji("") == "eyes"
    assert _normalize_emoji("   :::  ") == "eyes"
