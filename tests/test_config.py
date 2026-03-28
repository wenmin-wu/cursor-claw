"""Config path and JSON loading."""

import json
from pathlib import Path

import pytest

from cursor_claw.config import (
    cursorclaw_home,
    default_config_document,
    load_settings,
    write_default_config_file,
)


def test_cursorclaw_home_uses_dot_cursorclaw(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert cursorclaw_home() == tmp_path / ".cursorclaw"


def test_load_settings_new_format(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """New nested channels format is parsed correctly."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    home = cursorclaw_home()
    home.mkdir(parents=True, exist_ok=True)
    deep = tmp_path / "ws"
    deep.mkdir()
    cfg = home / "config.json"
    cfg.write_text(
        json.dumps(
            {
                "workspace": str(deep),
                "chunk_timeout_sec": 60.0,
                "channels": {
                    "mattermost": {
                        "enabled": True,
                        "base_url": "http://mm.example",
                        "bot_token": "tok",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    s = load_settings()
    assert s.channels.mattermost.base_url == "http://mm.example"
    assert s.channels.mattermost.bot_token == "tok"
    assert s.channels.mattermost.enabled is True
    assert s.workspace == deep
    assert s.chunk_timeout_sec == 60.0
    assert s.turn_timeout_sec == 1800.0


def test_load_settings_migrates_flat_format(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Old flat config keys are migrated to the nested channels structure."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    home = cursorclaw_home()
    home.mkdir(parents=True, exist_ok=True)
    deep = tmp_path / "ws"
    deep.mkdir()
    cfg = home / "config.json"
    cfg.write_text(
        json.dumps(
            {
                "mattermost_base_url": "http://mm.example",
                "mattermost_bot_token": "tok",
                "workspace": str(deep),
                "chunk_timeout_sec": 60.0,
            }
        ),
        encoding="utf-8",
    )
    s = load_settings()
    assert s.channels.mattermost.base_url == "http://mm.example"
    assert s.channels.mattermost.bot_token == "tok"
    assert s.workspace == deep


def test_write_default_config_file_creates_json(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    home = cursorclaw_home()
    assert not (home / "config.json").exists()
    path = write_default_config_file(overwrite=False)
    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert "channels" in data
    assert "mattermost" in data["channels"]
    assert data["channels"]["mattermost"]["bot_token"] == ""
    assert Path(data["state_db"]) == home / "state.db"


def test_default_config_document_has_all_channels() -> None:
    doc = default_config_document()
    assert "channels" in doc
    assert "mattermost" in doc["channels"]
    assert "telegram" in doc["channels"]
    assert "qq" in doc["channels"]
    assert isinstance(doc["channels"]["mattermost"]["onchar_prefixes"], list)
