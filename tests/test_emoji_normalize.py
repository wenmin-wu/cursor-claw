"""Mattermost reaction emoji_name normalization."""

from cursor_claw.app import normalize_mattermost_emoji_name


def test_strip_colons() -> None:
    assert normalize_mattermost_emoji_name(":eyes:") == "eyes"
    assert normalize_mattermost_emoji_name("eyes") == "eyes"
    assert normalize_mattermost_emoji_name("  :+1:  ") == "+1"


def test_empty_defaults_to_eyes() -> None:
    assert normalize_mattermost_emoji_name("") == "eyes"
    assert normalize_mattermost_emoji_name("   :::  ") == "eyes"
