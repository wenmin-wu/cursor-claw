"""Settings from ~/.cursorclaw/config.json with CURSOR_CLAW_* env overrides."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def cursorclaw_home() -> Path:
    return Path.home() / ".cursorclaw"


def cursorclaw_workspace() -> Path:
    """Directory where AGENT.md, SOUL.md, MEMORY.md live."""
    return cursorclaw_home() / "workspace"


def default_config_document() -> dict[str, Any]:
    """Serializable defaults for `cursorclaw init` (all knobs in one place)."""
    ch = cursorclaw_home()
    return {
        "mattermost_base_url": "",
        "mattermost_bot_token": "",
        "mattermost_verify": True,
        "workspace": ".",
        "agent_command": "agent",
        "state_db": str(ch / "state.db"),
        "chunk_timeout_sec": 300.0,
        "turn_timeout_sec": 1800.0,
        "outer_timeout_sec": 1800.0,
        "chatmode": "oncall",
        "onchar_prefixes": [">"],
        "dm_enabled": True,
        "dm_allow_from": [],
        "group_policy": "open",
        "group_allow_from": [],
        "react_emoji": "eyes",
        "reply_in_thread": True,
        "max_post_chars": 15000,
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


def load_settings() -> Settings:
    cfg_path = cursorclaw_home() / "config.json"
    data: dict[str, Any] = {}
    if cfg_path.exists():
        with cfg_path.open(encoding="utf-8") as f:
            raw = json.load(f)
        if isinstance(raw, dict):
            data = {k: v for k, v in raw.items() if v is not None}
    return Settings(**data)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CURSOR_CLAW_",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    mattermost_base_url: str = Field(
        default="",
        description="Mattermost server URL, e.g. http://127.0.0.1:8065",
    )
    mattermost_bot_token: str = Field(default="", description="Bot account token")
    mattermost_verify: bool = Field(
        default=True,
        description="Verify TLS certificates when connecting to Mattermost",
    )

    workspace: Path = Field(
        default=Path("."),
        description="Directory passed to agent --workspace (the code repo)",
    )
    agent_command: str = Field(default="agent", description="Cursor agent executable name or path")

    state_db: Path = Field(
        default_factory=lambda: cursorclaw_home() / "state.db",
        description="SQLite path for session_id and last_seen",
    )

    chunk_timeout_sec: float = Field(default=300.0, ge=1.0)
    turn_timeout_sec: float = Field(default=1800.0, ge=1.0)
    outer_timeout_sec: float = Field(default=1800.0, ge=1.0)

    chatmode: Literal["oncall", "onmessage", "onchar"] = "oncall"
    onchar_prefixes: list[str] = Field(default_factory=lambda: [">"])

    dm_enabled: bool = True
    dm_allow_from: list[str] = Field(
        default_factory=list,
        description="If non-empty, only these Mattermost user IDs may DM the bot; "
        "if empty, any user may DM when dm_enabled is true.",
    )

    group_policy: Literal["open", "allowlist"] = "open"
    group_allow_from: list[str] = Field(default_factory=list)

    react_emoji: str = "eyes"
    reply_in_thread: bool = True

    max_post_chars: int = Field(default=15000, ge=1000)

    @field_validator("workspace", "state_db", mode="before")
    @classmethod
    def _expand_path(cls, v: object) -> object:
        if v is None:
            return v
        if isinstance(v, str):
            return Path(v).expanduser()
        if isinstance(v, Path):
            return v.expanduser()
        return v
