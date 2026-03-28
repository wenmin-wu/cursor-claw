"""Settings loaded from ~/.cursorclaw/config.json."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


def cursorclaw_home() -> Path:
    return Path.home() / ".cursorclaw"


def cursorclaw_workspace() -> Path:
    """Directory where AGENT.md, SOUL.md, MEMORY.md live."""
    return cursorclaw_home() / "workspace"


# ---------------------------------------------------------------------------
# Per-channel config models
# ---------------------------------------------------------------------------

class MattermostChannelConfig(BaseModel):
    enabled: bool = False
    base_url: str = Field(default="", description="Mattermost server URL, e.g. http://127.0.0.1:8065")
    bot_token: str = Field(default="", description="Bot account token")
    verify: bool = Field(default=True, description="Verify TLS certificates")
    chatmode: Literal["oncall", "onmessage", "onchar"] = "oncall"
    onchar_prefixes: list[str] = Field(default_factory=lambda: [">"])
    dm_enabled: bool = True
    dm_allow_from: list[str] = Field(default_factory=list)
    group_policy: Literal["open", "allowlist"] = "open"
    group_allow_from: list[str] = Field(default_factory=list)
    react_emoji: str = "eyes"
    reply_in_thread: bool = True
    max_post_chars: int = Field(default=15000, ge=1000)


class TelegramChannelConfig(BaseModel):
    enabled: bool = False
    token: str = Field(default="", description="Bot token from @BotFather")
    allow_from: list[str] = Field(
        default_factory=list,
        description="Telegram user IDs allowed to use the bot (empty = anyone)",
    )
    proxy: str | None = Field(default=None, description="Optional HTTP/SOCKS5 proxy URL")
    max_message_chars: int = Field(default=4000, ge=100)


class QQChannelConfig(BaseModel):
    enabled: bool = False
    app_id: str = Field(default="", description="QQ bot AppID from open.qq.com")
    secret: str = Field(default="", description="QQ bot AppSecret")
    allow_from: list[str] = Field(
        default_factory=list,
        description="QQ user openids allowed to use the bot (empty = anyone)",
    )


class ChannelsConfig(BaseModel):
    mattermost: MattermostChannelConfig = Field(default_factory=MattermostChannelConfig)
    telegram: TelegramChannelConfig = Field(default_factory=TelegramChannelConfig)
    qq: QQChannelConfig = Field(default_factory=QQChannelConfig)


# ---------------------------------------------------------------------------
# Top-level settings
# ---------------------------------------------------------------------------

class Settings(BaseModel):
    workspace: Path = Field(
        default_factory=lambda: Path("."),
        description="Code repo directory passed to agent --workspace",
    )
    agent_command: str = Field(default="agent", description="Cursor agent executable name or path")
    state_db: Path = Field(
        default_factory=lambda: cursorclaw_home() / "state.db",
        description="SQLite path for session_id and last_seen",
    )
    chunk_timeout_sec: float = Field(default=300.0, ge=1.0)
    turn_timeout_sec: float = Field(default=1800.0, ge=1.0)
    outer_timeout_sec: float = Field(default=1800.0, ge=1.0)
    channels: ChannelsConfig = Field(default_factory=ChannelsConfig)

    @field_validator("workspace", "state_db", mode="before")
    @classmethod
    def _expand_path(cls, v: object) -> object:
        if isinstance(v, str):
            return Path(v).expanduser()
        if isinstance(v, Path):
            return v.expanduser()
        return v


# ---------------------------------------------------------------------------
# Default config document (for `cursorclaw init`)
# ---------------------------------------------------------------------------

def default_config_document() -> dict[str, Any]:
    ch = cursorclaw_home()
    return {
        "workspace": ".",
        "agent_command": "agent",
        "state_db": str(ch / "state.db"),
        "chunk_timeout_sec": 300.0,
        "turn_timeout_sec": 1800.0,
        "outer_timeout_sec": 1800.0,
        "channels": {
            "mattermost": {
                "enabled": False,
                "base_url": "",
                "bot_token": "",
                "verify": True,
                "chatmode": "oncall",
                "onchar_prefixes": [">"],
                "dm_enabled": True,
                "dm_allow_from": [],
                "group_policy": "open",
                "group_allow_from": [],
                "react_emoji": "eyes",
                "reply_in_thread": True,
                "max_post_chars": 15000,
            },
            "telegram": {
                "enabled": False,
                "token": "",
                "allow_from": [],
                "proxy": None,
                "max_message_chars": 4000,
            },
            "qq": {
                "enabled": False,
                "app_id": "",
                "secret": "",
                "allow_from": [],
            },
        },
    }


def write_default_config_file(*, overwrite: bool = False) -> Path:
    """Create ~/.cursorclaw and write config.json. Returns path to config file."""
    home = cursorclaw_home()
    home.mkdir(parents=True, exist_ok=True)
    path = home / "config.json"
    if path.exists() and not overwrite:
        return path
    path.write_text(
        json.dumps(default_config_document(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path


def _migrate_flat_config(raw: dict[str, Any]) -> dict[str, Any]:
    """Convert old flat config keys to the new nested channels structure."""
    if "channels" in raw:
        return raw  # already new format

    mm: dict[str, Any] = {}
    flat_mm_keys = {
        "mattermost_base_url": "base_url",
        "mattermost_bot_token": "bot_token",
        "mattermost_verify": "verify",
        "chatmode": "chatmode",
        "onchar_prefixes": "onchar_prefixes",
        "dm_enabled": "dm_enabled",
        "dm_allow_from": "dm_allow_from",
        "group_policy": "group_policy",
        "group_allow_from": "group_allow_from",
        "react_emoji": "react_emoji",
        "reply_in_thread": "reply_in_thread",
        "max_post_chars": "max_post_chars",
    }
    for old, new in flat_mm_keys.items():
        if old in raw:
            mm[new] = raw.pop(old)
    if mm:
        mm.setdefault("enabled", bool(mm.get("base_url") and mm.get("bot_token")))
        raw["channels"] = {"mattermost": mm}
    return raw


def load_settings() -> Settings:
    cfg_path = cursorclaw_home() / "config.json"
    data: dict[str, Any] = {}
    if cfg_path.exists():
        with cfg_path.open(encoding="utf-8") as f:
            raw = json.load(f)
        if isinstance(raw, dict):
            data = {k: v for k, v in raw.items() if v is not None}
        data = _migrate_flat_config(data)
    return Settings(**data)
