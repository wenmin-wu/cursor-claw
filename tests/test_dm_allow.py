"""DM allowlist semantics (empty list = open, not deny-all)."""

from cursor_claw.app import CursorMattermostBot
from cursor_claw.config import Settings


def test_dm_open_when_allowlist_empty() -> None:
    s = Settings.model_validate({"dm_enabled": True, "dm_allow_from": []})
    bot = CursorMattermostBot(s)
    assert bot._is_allowed("any-user-id", "channel", "D") is True


def test_dm_disabled_blocks() -> None:
    s = Settings.model_validate({"dm_enabled": False, "dm_allow_from": []})
    bot = CursorMattermostBot(s)
    assert bot._is_allowed("any-user-id", "channel", "D") is False


def test_dm_allowlist_only_listed_users() -> None:
    s = Settings.model_validate({"dm_enabled": True, "dm_allow_from": ["u1", "u2"]})
    bot = CursorMattermostBot(s)
    assert bot._is_allowed("u1", "channel", "D") is True
    assert bot._is_allowed("u2", "channel", "D") is True
    assert bot._is_allowed("other", "channel", "D") is False


def test_group_channel_unaffected_by_dm_allowlist() -> None:
    s = Settings.model_validate(
        {"dm_enabled": True, "dm_allow_from": [], "group_policy": "open"}
    )
    bot = CursorMattermostBot(s)
    assert bot._is_allowed("any", "ch1", "O") is True
