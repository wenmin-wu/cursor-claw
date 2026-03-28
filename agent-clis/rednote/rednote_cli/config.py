"""Config management for rednote-cli (~/.config/rednote-cli/config.json)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def config_dir() -> Path:
    return Path.home() / ".config" / "rednote-cli"


def config_path() -> Path:
    return config_dir() / "config.json"


def default_data_dir() -> Path:
    return Path.home() / ".local" / "share" / "rednote-cli" / "notes"


def default_db_path() -> Path:
    return Path.home() / ".local" / "share" / "rednote-cli" / "notes.db"


_DEFAULTS: dict[str, Any] = {
    "data_dir": "",          # empty = default_data_dir()
    "cdp_port": 19327,
    "max_images": 20,
    "storage_state_path": "",  # path to Playwright storage state (cookies)
}


def load_config() -> dict[str, Any]:
    path = config_path()
    cfg = dict(_DEFAULTS)
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                cfg.update({k: v for k, v in raw.items() if v is not None})
        except Exception:
            pass
    return cfg


def save_config(cfg: dict[str, Any]) -> Path:
    config_dir().mkdir(parents=True, exist_ok=True)
    path = config_path()
    path.write_text(
        json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return path


def init_config(overwrite: bool = False) -> Path:
    path = config_path()
    if path.exists() and not overwrite:
        return path
    return save_config(dict(_DEFAULTS))


def get_data_dir(cfg: dict[str, Any] | None = None) -> Path:
    if cfg is None:
        cfg = load_config()
    raw = (cfg.get("data_dir") or "").strip()
    p = Path(raw).expanduser() if raw else default_data_dir()
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_db_path(cfg: dict[str, Any] | None = None) -> Path:
    if cfg is None:
        cfg = load_config()
    data_dir = get_data_dir(cfg)
    # Store db alongside notes dir, one level up
    db = data_dir.parent / "notes.db"
    return db
