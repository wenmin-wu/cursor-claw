#!/usr/bin/env python3
"""Local note index and search using SQLite FTS5.

Usage:
    python notes_db.py index [--data-dir DIR]   # index / re-index all notes
    python notes_db.py search QUERY [--data-dir DIR] [--limit N]
    python notes_db.py status [--data-dir DIR]
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path


def _default_data_dir() -> Path:
    config_path = Path(__file__).parent.parent / "config.json"
    if config_path.exists():
        try:
            cfg = json.loads(config_path.read_text())
            data_dir = cfg.get("data_dir", "")
            if data_dir:
                return Path(data_dir).expanduser()
        except Exception:
            pass
    return Path.home() / ".local" / "share" / "rednote-cli" / "notes"


def _db_path(data_dir: Path) -> Path:
    return data_dir / "notes_index.db"


def _connect(data_dir: Path) -> sqlite3.Connection:
    data_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_db_path(data_dir))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS notes_meta (
            note_id TEXT PRIMARY KEY,
            indexed_at INTEGER
        )
    """)
    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(
            note_id UNINDEXED,
            title,
            desc,
            tags,
            author,
            content='',
            tokenize='unicode61'
        )
    """)
    conn.commit()
    return conn


def _parse_note(note_json: dict) -> dict:
    data = note_json.get("data") or note_json  # handle both raw and enveloped
    tags = " ".join(
        t.get("name", "") for t in (data.get("tag_list") or data.get("tags") or [])
        if isinstance(t, dict)
    )
    author = ""
    raw_author = data.get("author") or data.get("user") or {}
    if isinstance(raw_author, dict):
        author = raw_author.get("nickname") or raw_author.get("name") or ""
    return {
        "note_id": data.get("id") or data.get("note_id") or "",
        "title": data.get("title") or "",
        "desc": data.get("desc") or "",
        "tags": tags,
        "author": author,
    }


def cmd_index(data_dir: Path) -> None:
    conn = _connect(data_dir)
    import time

    indexed = skipped = errors = 0
    existing_ids: set[str] = {
        row["note_id"] for row in conn.execute("SELECT note_id FROM notes_meta")
    }

    for note_dir in sorted(data_dir.iterdir()):
        note_file = note_dir / "note.json"
        if not note_file.exists():
            continue

        note_id = note_dir.name
        mtime = int(note_file.stat().st_mtime)

        if note_id in existing_ids:
            row = conn.execute(
                "SELECT indexed_at FROM notes_meta WHERE note_id = ?", (note_id,)
            ).fetchone()
            if row and row["indexed_at"] >= mtime:
                skipped += 1
                continue

        try:
            raw = json.loads(note_file.read_text(encoding="utf-8"))
            parsed = _parse_note(raw)
            if not parsed["note_id"]:
                parsed["note_id"] = note_id

            conn.execute(
                "DELETE FROM notes_fts WHERE note_id = ?", (note_id,)
            )
            conn.execute(
                "INSERT INTO notes_fts(note_id, title, desc, tags, author) VALUES (?,?,?,?,?)",
                (parsed["note_id"], parsed["title"], parsed["desc"], parsed["tags"], parsed["author"]),
            )
            conn.execute(
                "INSERT OR REPLACE INTO notes_meta(note_id, indexed_at) VALUES (?,?)",
                (note_id, mtime),
            )
            conn.commit()
            indexed += 1
        except Exception as exc:
            print(f"  [warn] {note_id}: {exc}", file=sys.stderr)
            errors += 1

    conn.close()
    print(json.dumps({"indexed": indexed, "skipped": skipped, "errors": errors,
                      "db": str(_db_path(data_dir))}))


def cmd_search(data_dir: Path, query: str, limit: int) -> None:
    db = _db_path(data_dir)
    if not db.exists():
        print(json.dumps({"error": "Index not found. Run: python notes_db.py index"}))
        sys.exit(1)

    conn = _connect(data_dir)
    rows = conn.execute(
        """
        SELECT note_id, title, desc, tags, author,
               snippet(notes_fts, 2, '[', ']', '...', 16) AS snippet
        FROM notes_fts
        WHERE notes_fts MATCH ?
        ORDER BY rank
        LIMIT ?
        """,
        (query, limit),
    ).fetchall()
    conn.close()

    results = [dict(r) for r in rows]
    print(json.dumps({"query": query, "count": len(results), "results": results},
                     ensure_ascii=False, indent=2))


def cmd_status(data_dir: Path) -> None:
    db = _db_path(data_dir)
    if not db.exists():
        print(json.dumps({"indexed": 0, "db": str(db), "exists": False}))
        return
    conn = _connect(data_dir)
    count = conn.execute("SELECT COUNT(*) FROM notes_meta").fetchone()[0]
    conn.close()
    print(json.dumps({"indexed": count, "db": str(db), "exists": True}))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["index", "search", "status"])
    parser.add_argument("query", nargs="?", default="")
    parser.add_argument("--data-dir", default="")
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()

    data_dir = Path(args.data_dir).expanduser() if args.data_dir else _default_data_dir()

    if args.command == "index":
        cmd_index(data_dir)
    elif args.command == "search":
        if not args.query:
            print("Error: query required for search", file=sys.stderr)
            sys.exit(2)
        cmd_search(data_dir, args.query, args.limit)
    elif args.command == "status":
        cmd_status(data_dir)


if __name__ == "__main__":
    main()
