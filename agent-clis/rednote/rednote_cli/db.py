"""SQLite store for RedNote notes with keyword search."""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from threading import Lock
from typing import Any


class NoteDB:
    """Thread-safe SQLite store for fetched RedNote notes."""

    def __init__(self, db_path: Path) -> None:
        self._path = db_path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self._init()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init(self) -> None:
        with self._lock, self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS notes (
                    note_id      TEXT PRIMARY KEY,
                    url          TEXT NOT NULL,
                    title        TEXT NOT NULL DEFAULT '',
                    author       TEXT NOT NULL DEFAULT '',
                    content      TEXT NOT NULL DEFAULT '',
                    tags         TEXT NOT NULL DEFAULT '[]',
                    likes        INTEGER NOT NULL DEFAULT 0,
                    comments     INTEGER NOT NULL DEFAULT 0,
                    image_count  INTEGER NOT NULL DEFAULT 0,
                    note_dir     TEXT NOT NULL,
                    fetched_at   TEXT NOT NULL
                );

                CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(
                    note_id UNINDEXED,
                    title,
                    author,
                    content,
                    tags,
                    content='notes',
                    content_rowid='rowid'
                );

                CREATE TRIGGER IF NOT EXISTS notes_ai AFTER INSERT ON notes BEGIN
                    INSERT INTO notes_fts(rowid, note_id, title, author, content, tags)
                    VALUES (new.rowid, new.note_id, new.title, new.author, new.content, new.tags);
                END;

                CREATE TRIGGER IF NOT EXISTS notes_ad AFTER DELETE ON notes BEGIN
                    INSERT INTO notes_fts(notes_fts, rowid, note_id, title, author, content, tags)
                    VALUES ('delete', old.rowid, old.note_id, old.title, old.author, old.content, old.tags);
                END;

                CREATE TRIGGER IF NOT EXISTS notes_au AFTER UPDATE ON notes BEGIN
                    INSERT INTO notes_fts(notes_fts, rowid, note_id, title, author, content, tags)
                    VALUES ('delete', old.rowid, old.note_id, old.title, old.author, old.content, old.tags);
                    INSERT INTO notes_fts(rowid, note_id, title, author, content, tags)
                    VALUES (new.rowid, new.note_id, new.title, new.author, new.content, new.tags);
                END;
            """)
            conn.commit()

    def upsert(self, note: dict[str, Any]) -> None:
        note_id = note["note_id"]
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        tags_json = json.dumps(note.get("tags") or [], ensure_ascii=False)
        with self._lock, self._connect() as conn:
            existing = conn.execute(
                "SELECT rowid FROM notes WHERE note_id = ?", (note_id,)
            ).fetchone()
            if existing:
                conn.execute(
                    """UPDATE notes SET
                        url=?, title=?, author=?, content=?, tags=?,
                        likes=?, comments=?, image_count=?, note_dir=?, fetched_at=?
                       WHERE note_id=?""",
                    (
                        note.get("url", ""),
                        note.get("title", ""),
                        note.get("author", ""),
                        note.get("content", ""),
                        tags_json,
                        int(note.get("likes") or 0),
                        int(note.get("comments") or 0),
                        int(note.get("image_count") or 0),
                        str(note.get("note_dir", "")),
                        now,
                        note_id,
                    ),
                )
            else:
                conn.execute(
                    """INSERT INTO notes
                        (note_id, url, title, author, content, tags,
                         likes, comments, image_count, note_dir, fetched_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        note_id,
                        note.get("url", ""),
                        note.get("title", ""),
                        note.get("author", ""),
                        note.get("content", ""),
                        tags_json,
                        int(note.get("likes") or 0),
                        int(note.get("comments") or 0),
                        int(note.get("image_count") or 0),
                        str(note.get("note_dir", "")),
                        now,
                    ),
                )
            conn.commit()

    def search(self, keyword: str, limit: int = 20) -> list[dict[str, Any]]:
        """Full-text search using FTS5. Falls back to LIKE if keyword is empty."""
        with self._lock, self._connect() as conn:
            if not keyword.strip():
                rows = conn.execute(
                    "SELECT * FROM notes ORDER BY fetched_at DESC LIMIT ?", (limit,)
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT n.* FROM notes n
                       JOIN notes_fts f ON n.rowid = f.rowid
                       WHERE notes_fts MATCH ?
                       ORDER BY rank LIMIT ?""",
                    (keyword, limit),
                ).fetchall()
        return [dict(r) for r in rows]

    def get(self, note_id: str) -> dict[str, Any] | None:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM notes WHERE note_id = ?", (note_id,)
            ).fetchone()
        return dict(row) if row else None

    def list_all(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM notes ORDER BY fetched_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]
