"""SQLite key-value store (namespace + key → value)."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from threading import Lock


class StateStore:
    """Thread-safe SQLite store for cursor-claw session and state persistence."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = Lock()
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS state (
                    namespace TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (namespace, key)
                )
                """
            )
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        return conn

    def get(self, namespace: str, key: str) -> str | None:
        with self._lock:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT value FROM state WHERE namespace = ? AND key = ?",
                    (namespace, key),
                ).fetchone()
                return str(row["value"]) if row else None

    def set(self, namespace: str, key: str, value: str) -> None:
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO state (namespace, key, value, updated_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(namespace, key) DO UPDATE SET
                        value = excluded.value,
                        updated_at = excluded.updated_at
                    """,
                    (namespace, key, value, now),
                )
                conn.commit()

    def delete(self, namespace: str, key: str) -> None:
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    "DELETE FROM state WHERE namespace = ? AND key = ?",
                    (namespace, key),
                )
                conn.commit()
