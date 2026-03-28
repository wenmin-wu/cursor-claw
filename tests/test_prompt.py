"""Tests for system context injection via prompt.py."""

from pathlib import Path

import pytest

from cursor_claw.prompt import build_prompt, build_system_block, sync_workspace_templates


def test_build_system_block_empty_dir(tmp_path: Path) -> None:
    """No markdown files → empty string (no system block injected)."""
    result = build_system_block(tmp_path)
    assert result == ""


def test_build_system_block_with_agent_md(tmp_path: Path) -> None:
    (tmp_path / "AGENT.md").write_text("Be helpful.", encoding="utf-8")
    block = build_system_block(tmp_path)
    assert "<system>" in block
    assert "</system>" in block
    assert "AGENT.md" in block
    assert "Be helpful." in block
    assert str(tmp_path.resolve()) in block


def test_build_system_block_all_files(tmp_path: Path) -> None:
    (tmp_path / "AGENT.md").write_text("Instructions", encoding="utf-8")
    (tmp_path / "SOUL.md").write_text("Personality", encoding="utf-8")
    (tmp_path / "MEMORY.md").write_text("Facts", encoding="utf-8")
    block = build_system_block(tmp_path)
    assert "Instructions" in block
    assert "Personality" in block
    assert "Facts" in block


def test_build_system_block_includes_workspace(tmp_path: Path) -> None:
    (tmp_path / "AGENT.md").write_text("x", encoding="utf-8")
    workspace = Path("/some/project")
    block = build_system_block(tmp_path, workspace=workspace)
    assert "Agent workspace:" in block


def test_build_system_block_skips_empty_files(tmp_path: Path) -> None:
    (tmp_path / "AGENT.md").write_text("   \n  ", encoding="utf-8")  # whitespace only
    result = build_system_block(tmp_path)
    assert result == ""


def test_build_prompt_prepends_block(tmp_path: Path) -> None:
    (tmp_path / "AGENT.md").write_text("Instructions", encoding="utf-8")
    result = build_prompt("hello world", tmp_path)
    assert result.startswith("<system>")
    assert "hello world" in result
    assert result.index("<system>") < result.index("hello world")


def test_build_prompt_no_files_returns_original(tmp_path: Path) -> None:
    result = build_prompt("hello world", tmp_path)
    assert result == "hello world"


def test_sync_workspace_templates_creates_files(tmp_path: Path) -> None:
    added = sync_workspace_templates(tmp_path, silent=True)
    # Should create at least some files from the bundled templates
    assert len(added) > 0
    for name in added:
        assert (tmp_path / name).exists()


def test_sync_workspace_templates_does_not_overwrite(tmp_path: Path) -> None:
    (tmp_path / "AGENT.md").write_text("custom content", encoding="utf-8")
    sync_workspace_templates(tmp_path, silent=True)
    # The existing file should not be overwritten
    assert (tmp_path / "AGENT.md").read_text(encoding="utf-8") == "custom content"
