"""rednote-cli — fetch and locally search Xiaohongshu notes."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Optional

import typer
from loguru import logger

from rednote_cli.config import (
    config_path,
    get_data_dir,
    get_db_path,
    init_config,
    load_config,
    save_config,
)
from rednote_cli.db import NoteDB
from rednote_cli.fetcher import fetch_note

app = typer.Typer(no_args_is_help=True, help="Fetch and search Xiaohongshu (RedNote) notes.")

# Suppress loguru default handler; only show WARNING+ to stderr
logger.remove()
logger.add(sys.stderr, level="WARNING", format="{level}: {message}")


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------

@app.command("init")
def init_cmd(
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite existing config"),
) -> None:
    """Create ~/.config/rednote-cli/config.json with default settings."""
    path = init_config(overwrite=force)
    typer.echo(f"Config: {path}")
    cfg = load_config()
    typer.echo(f"data_dir: {get_data_dir(cfg)}")


# ---------------------------------------------------------------------------
# config
# ---------------------------------------------------------------------------

@app.command("config")
def config_cmd(
    data_dir: Optional[str] = typer.Option(None, "--data-dir", help="Set note storage directory"),
    cdp_port: Optional[int] = typer.Option(None, "--cdp-port", help="Set Chrome CDP port"),
    max_images: Optional[int] = typer.Option(None, "--max-images", help="Max images per note"),
    storage_state: Optional[str] = typer.Option(None, "--storage-state", help="Playwright storage state path"),
    show: bool = typer.Option(False, "--show", "-s", help="Print current config"),
) -> None:
    """View or update ~/.config/rednote-cli/config.json."""
    cfg = load_config()
    changed = False
    if data_dir is not None:
        cfg["data_dir"] = data_dir
        changed = True
    if cdp_port is not None:
        cfg["cdp_port"] = cdp_port
        changed = True
    if max_images is not None:
        cfg["max_images"] = max_images
        changed = True
    if storage_state is not None:
        cfg["storage_state_path"] = storage_state
        changed = True
    if changed:
        save_config(cfg)
        typer.echo(f"Saved to {config_path()}")
    if show or not changed:
        typer.echo(json.dumps(cfg, indent=2, ensure_ascii=False))


# ---------------------------------------------------------------------------
# fetch
# ---------------------------------------------------------------------------

@app.command("fetch")
def fetch_cmd(
    url: str = typer.Argument(..., help="Xiaohongshu note URL or share text"),
    data_dir: Optional[str] = typer.Option(None, "--data-dir", help="Override note storage directory"),
    cdp_port: Optional[int] = typer.Option(None, "--cdp-port", help="Override Chrome CDP port"),
    max_images: Optional[int] = typer.Option(None, "--max-images", help="Override max images"),
    json_output: bool = typer.Option(False, "--json", help="Output metadata as JSON"),
) -> None:
    """
    Fetch a Xiaohongshu note and save it to disk.

    Saves to: <data_dir>/<note_id>/
      content.txt   — title, author, tags, body text
      image_00.jpg  — downloaded images (if any)
      note.json     — full metadata

    Also indexes the note in the local SQLite database for --local search.
    """
    cfg = load_config()
    resolved_data_dir = Path(data_dir).expanduser() if data_dir else get_data_dir(cfg)
    resolved_data_dir.mkdir(parents=True, exist_ok=True)
    resolved_cdp_port = cdp_port if cdp_port is not None else int(cfg.get("cdp_port", 19327))
    resolved_max_images = max_images if max_images is not None else int(cfg.get("max_images", 20))
    storage_state = cfg.get("storage_state_path") or None

    try:
        meta = asyncio.run(
            fetch_note(
                url,
                data_dir=resolved_data_dir,
                cdp_port=resolved_cdp_port,
                max_images=resolved_max_images,
                storage_state_path=storage_state,
            )
        )
    except RuntimeError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    # Index in SQLite
    db = NoteDB(get_db_path(cfg))
    db.upsert(meta)

    if json_output:
        typer.echo(json.dumps(meta, indent=2, ensure_ascii=False))
    else:
        typer.echo(f"note_id:   {meta['note_id']}")
        typer.echo(f"title:     {meta['title']}")
        typer.echo(f"author:    {meta['author']}")
        typer.echo(f"images:    {meta['image_count']}")
        typer.echo(f"note_dir:  {meta['note_dir']}")


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------

@app.command("search")
def search_cmd(
    keyword: str = typer.Argument("", help="Keyword to search (empty = list all)"),
    local: bool = typer.Option(True, "--local/--no-local", help="Search local SQLite index"),
    limit: int = typer.Option(20, "--limit", "-n", help="Max results"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """
    Search locally indexed notes by keyword.

        rednote-cli search --local "健康食谱"
        rednote-cli search ""            # list all notes
    """
    cfg = load_config()
    db = NoteDB(get_db_path(cfg))
    results = db.search(keyword, limit=limit)

    if not results:
        typer.echo("No notes found.")
        return

    if json_output:
        typer.echo(json.dumps(results, indent=2, ensure_ascii=False))
        return

    for r in results:
        note_dir = Path(r["note_dir"])
        tags = json.loads(r.get("tags") or "[]")
        tag_str = " ".join(f"#{t}" for t in tags) if tags else ""
        typer.echo(
            f"[{r['note_id']}] {r['title']}\n"
            f"  作者: {r['author']}  点赞: {r['likes']}  评论: {r['comments']}\n"
            f"  {tag_str}\n"
            f"  dir: {note_dir}\n"
        )


# ---------------------------------------------------------------------------
# show
# ---------------------------------------------------------------------------

@app.command("show")
def show_cmd(
    note_id: str = typer.Argument(..., help="Note ID to display"),
    json_output: bool = typer.Option(False, "--json", help="Output metadata as JSON"),
) -> None:
    """Show a locally saved note by ID."""
    cfg = load_config()
    db = NoteDB(get_db_path(cfg))
    note = db.get(note_id)
    if not note:
        typer.echo(f"Note {note_id!r} not found in local index.", err=True)
        raise typer.Exit(1)

    if json_output:
        typer.echo(json.dumps(note, indent=2, ensure_ascii=False))
        return

    note_dir = Path(note["note_dir"])
    content_file = note_dir / "content.txt"
    tags = json.loads(note.get("tags") or "[]")

    typer.echo(f"ID:      {note['note_id']}")
    typer.echo(f"URL:     {note['url']}")
    typer.echo(f"Title:   {note['title']}")
    typer.echo(f"Author:  {note['author']}")
    if tags:
        typer.echo(f"Tags:    {' '.join('#' + t for t in tags)}")
    typer.echo(f"Likes:   {note['likes']}  Comments: {note['comments']}")
    typer.echo(f"Images:  {note['image_count']}")
    typer.echo(f"Dir:     {note_dir}")
    typer.echo("")
    if content_file.exists():
        typer.echo(content_file.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------

@app.command("list")
def list_cmd(
    limit: int = typer.Option(50, "--limit", "-n", help="Max results"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """List all locally indexed notes (newest first)."""
    cfg = load_config()
    db = NoteDB(get_db_path(cfg))
    results = db.list_all(limit=limit)
    if not results:
        typer.echo("No notes indexed yet. Use `rednote-cli fetch <url>` to add some.")
        return
    if json_output:
        typer.echo(json.dumps(results, indent=2, ensure_ascii=False))
        return
    for r in results:
        typer.echo(f"[{r['fetched_at']}] {r['note_id']}  {r['title'][:60]}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
