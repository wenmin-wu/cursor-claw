"""SQLite store tests."""

from pathlib import Path

from cursor_claw.store import StateStore


def test_roundtrip(tmp_path: Path) -> None:
    db = tmp_path / "t.db"
    s = StateStore(db)
    assert s.get("n", "k") is None
    s.set("n", "k", "v1")
    assert s.get("n", "k") == "v1"
    s.set("n", "k", "v2")
    assert s.get("n", "k") == "v2"
