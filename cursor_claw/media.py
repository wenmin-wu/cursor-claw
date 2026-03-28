"""Shared utilities for downloading message attachments to temp files,
and for parsing [SEND_IMAGE: /path] markers that Cursor embeds in its replies."""

from __future__ import annotations

import asyncio
import re
import shutil
import tempfile
import urllib.request
from pathlib import Path

from loguru import logger

# Cursor embeds this marker when it wants to send an image back to the user.
# Example: [SEND_IMAGE: /tmp/cursorclaw_abc/chart.png]
_SEND_IMAGE_RE = re.compile(r"^\[SEND_IMAGE:\s*(.+?)\]\s*$", re.MULTILINE)


def extract_send_images(text: str) -> tuple[str, list[Path]]:
    """Scan *text* for ``[SEND_IMAGE: /path]`` markers.

    Returns ``(clean_text, paths)`` where *clean_text* has the marker lines
    removed and *paths* is a list of existing local files to send.
    """
    paths: list[Path] = []

    def _replace(m: re.Match) -> str:
        p = Path(m.group(1).strip())
        if p.exists():
            paths.append(p)
        else:
            logger.warning("SEND_IMAGE path not found: {}", p)
        return ""

    clean = _SEND_IMAGE_RE.sub(_replace, text).strip()
    return clean, paths


def make_temp_dir() -> Path:
    """Create a per-turn temp directory prefixed with cursorclaw_."""
    return Path(tempfile.mkdtemp(prefix="cursorclaw_"))


def cleanup_temp_dir(path: Path | None) -> None:
    """Remove a temp directory after the agent turn completes."""
    if path is None:
        return
    try:
        shutil.rmtree(path, ignore_errors=True)
    except Exception as e:
        logger.warning("cleanup_temp_dir failed {}: {}", path, e)


def append_attachments(prompt: str, paths: list[Path]) -> str:
    """Append local temp-file paths to the prompt so Cursor can read the images.

    Example suffix added to prompt:
        [Attached image files (temp paths — Cursor can read them directly):
          /tmp/cursorclaw_abc/photo_0.jpg
          /tmp/cursorclaw_abc/photo_1.png]
    """
    if not paths:
        return prompt
    lines = ["\n\n[Attached image files (temp paths — Cursor can read them directly):"]
    for p in paths:
        lines.append(f"  {p}")
    lines.append("]")
    return prompt + "\n".join(lines)


async def download_url(
    url: str,
    dest: Path,
    headers: dict[str, str] | None = None,
) -> None:
    """Download *url* to *dest*, running the blocking I/O in a thread pool."""

    def _sync() -> None:
        req = urllib.request.Request(url, headers=headers or {})
        with urllib.request.urlopen(req, timeout=30) as resp:
            dest.write_bytes(resp.read())

    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _sync)
