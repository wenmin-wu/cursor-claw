"""DM allowlist semantics (empty list = open, not deny-all)."""

from cursor_claw.channels.mattermost import MattermostChannel
from cursor_claw.config import MattermostChannelConfig, Settings


def _make_settings(**mm_kwargs) -> Settings:
    return Settings.model_validate(
        {"channels": {"mattermost": {"enabled": True, **mm_kwargs}}}
    )


def _channel(settings: Settings) -> MattermostChannel:
    return MattermostChannel(settings)


def test_dm_open_when_allowlist_empty() -> None:
    s = _make_settings(dm_enabled=True, dm_allow_from=[])
    ch = _channel(s)
    assert ch._is_allowed_post("any-user-id", "channel", "D") is True


def test_dm_disabled_blocks() -> None:
    s = _make_settings(dm_enabled=False, dm_allow_from=[])
    ch = _channel(s)
    assert ch._is_allowed_post("any-user-id", "channel", "D") is False


def test_dm_allowlist_only_listed_users() -> None:
    s = _make_settings(dm_enabled=True, dm_allow_from=["u1", "u2"])
    ch = _channel(s)
    assert ch._is_allowed_post("u1", "channel", "D") is True
    assert ch._is_allowed_post("u2", "channel", "D") is True
    assert ch._is_allowed_post("other", "channel", "D") is False


def test_group_channel_unaffected_by_dm_allowlist() -> None:
    s = _make_settings(dm_enabled=True, dm_allow_from=[], group_policy="open")
    ch = _channel(s)
    assert ch._is_allowed_post("any", "ch1", "O") is True
