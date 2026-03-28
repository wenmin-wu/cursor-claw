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


def test_load_settings_merges_json_and_expands_tilde(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    home = cursorclaw_home()
    home.mkdir(parents=True, exist_ok=True)
    cfg = home / "config.json"
    deep = tmp_path / "ws"
    deep.mkdir()
    cfg.write_text(
        json.dumps(
            {
                "mattermost_base_url": "http://mm.example",
                "mattermost_bot_token": "tok",
                "workspace": str(deep),
                "agent_command": "agent",
                "state_db": "~/.cursorclaw/state.db",
                "chunk_timeout_sec": 60.0,
            }
        ),
        encoding="utf-8",
    )
    s = load_settings()
    assert s.mattermost_base_url == "http://mm.example"
    assert s.mattermost_bot_token == "tok"
    assert s.workspace == deep
    assert s.state_db == home / "state.db"
    assert s.chunk_timeout_sec == 60.0
    assert s.turn_timeout_sec == 1800.0


def test_write_default_config_file_creates_json(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    home = cursorclaw_home()
    assert not (home / "config.json").exists()
    path = write_default_config_file(overwrite=False)
    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["mattermost_base_url"] == ""
    assert "state_db" in data
    assert Path(data["state_db"]) == home / "state.db"


def test_default_config_document_is_stable_subset() -> None:
    doc = default_config_document()
    assert "mattermost_verify" in doc
    assert isinstance(doc["onchar_prefixes"], list)
