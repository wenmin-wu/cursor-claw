"""CLI: `cursorclaw init`, `cursorclaw start` (and `cursor-claw run` alias)."""

from __future__ import annotations

import asyncio

import typer
from loguru import logger

from cursor_claw.app import run_bot
from cursor_claw.config import cursorclaw_home, cursorclaw_workspace, load_settings, write_default_config_file
from cursor_claw.prompt import sync_workspace_templates

app = typer.Typer(no_args_is_help=True)


def _start_bot() -> None:
    settings = load_settings()
    if not settings.workspace.exists():
        logger.error("workspace does not exist: {}", settings.workspace)
        raise typer.Exit(1)

    ch = settings.channels
    if not any([ch.mattermost.enabled, ch.telegram.enabled, ch.qq.enabled]):
        logger.error(
            "No channels are enabled. "
            "Edit ~/.cursorclaw/config.json and set at least one channel to enabled=true."
        )
        raise typer.Exit(1)

    try:
        asyncio.run(run_bot(settings))
    except KeyboardInterrupt:
        logger.info("stopped")


@app.command("init")
def init_cmd(
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Overwrite existing ~/.cursorclaw/config.json",
    ),
) -> None:
    """Create ~/.cursorclaw, write config.json, and scaffold AGENT.md / SOUL.md / MEMORY.md."""
    path = cursorclaw_home() / "config.json"
    existed = path.exists()
    if existed and not force:
        logger.info("config already exists at {} (use --force to overwrite)", path)
    else:
        out = write_default_config_file(overwrite=force)
        logger.info("wrote {}", out)

    context_dir = cursorclaw_workspace()
    added = sync_workspace_templates(context_dir)
    if added:
        logger.info("scaffolded context files in {}: {}", context_dir, added)
    else:
        logger.info("context directory already populated at {}", context_dir)

    if existed and not force:
        raise typer.Exit(0)


@app.command("start")
def start_cmd() -> None:
    """Connect to all enabled channels and handle messages until interrupted."""
    _start_bot()


@app.command("run")
def run_cmd() -> None:
    """Same as start (alias for cursor-claw run)."""
    _start_bot()


def main() -> None:
    app()


if __name__ == "__main__":
    main()
