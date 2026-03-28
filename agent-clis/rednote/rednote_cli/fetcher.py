"""Fetch a Xiaohongshu note via Playwright and save it to disk."""

from __future__ import annotations

import asyncio
import json
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from loguru import logger


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------

def _extract_url(share_text: str) -> str:
    share_text = share_text.strip()
    if share_text.startswith(("http://", "https://")):
        return share_text
    xhslink = re.search(r"https?://xhslink\.com/[a-zA-Z0-9/]+", share_text, re.I)
    if xhslink:
        return xhslink.group(0)
    xhs = re.search(r"https?://(?:www\.)?xiaohongshu\.com/[^\s,]+", share_text, re.I)
    if xhs:
        return xhs.group(0)
    return ""


def _extract_note_id(url: str) -> str:
    """Pull the note ID from a resolved xiaohongshu.com URL."""
    m = re.search(
        r"xiaohongshu\.com/(?:explore|discovery/item|note)/([a-f0-9]{24})",
        url,
        re.I,
    )
    if m:
        return m.group(1)
    # fallback: last path segment that looks like a hex ID
    path = urlparse(url).path.rstrip("/")
    seg = path.split("/")[-1]
    if re.fullmatch(r"[a-f0-9]{24}", seg, re.I):
        return seg
    return ""


# ---------------------------------------------------------------------------
# Page script
# ---------------------------------------------------------------------------

_EXTRACT_SCRIPT = """
() => {
    const article = document.querySelector('.note-container');
    if (!article) return null;
    const titleEl = article.querySelector('#detail-title') || article.querySelector('.title');
    const title = titleEl ? titleEl.textContent.trim() : '';
    const contentBlock = article.querySelector('.note-scroller');
    if (!contentBlock) return { title, content: '', tags: [], author: '', imgs: [], likes: 0, comments: 0 };
    const contentSpan = contentBlock.querySelector('.note-content .note-text span');
    const content = contentSpan ? contentSpan.textContent.trim() : '';
    const tags = Array.from(contentBlock.querySelectorAll('.note-content .note-text a'))
                      .map(a => (a.textContent || '').trim().replace('#', ''));
    const authorEl = article.querySelector('.author-container .info .username')
                  || article.querySelector('.author .info .username');
    const author = authorEl ? authorEl.textContent.trim() : '';
    const interact = document.querySelector('.interact-container');
    const likesStr  = interact ? (interact.querySelector('.like-wrapper .count') || {}).textContent || '' : '';
    const commentsStr = interact ? (interact.querySelector('.chat-wrapper .count') || {}).textContent || '' : '';
    function imgUrl(img) { return img.src || img.getAttribute('data-src') || ''; }
    const mediaImgs = Array.from(document.querySelectorAll('.media-container img')).map(imgUrl).filter(Boolean);
    const noteImgs  = Array.from(article.querySelectorAll('img')).map(imgUrl).filter(Boolean);
    const seen = new Set();
    const imgs = [...mediaImgs, ...noteImgs].filter(u => u && !seen.has(u) && seen.add(u));
    function parseCount(s) {
        if (!s) return 0;
        s = s.trim();
        if (s.includes('万')) return Math.round(parseFloat(s) * 10000);
        return parseInt(s.replace(/[^\\d]/g, '')) || 0;
    }
    return { title, content, tags, author, imgs,
             likes: parseCount(likesStr), comments: parseCount(commentsStr) };
}
"""


# ---------------------------------------------------------------------------
# Image downloader
# ---------------------------------------------------------------------------

async def _download_image(url: str, dest: Path, timeout: float = 20.0) -> bool:
    if not url:
        return False
    if url.startswith("//"):
        url = "https:" + url
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=timeout) as client:
            r = await client.get(url)
            r.raise_for_status()
            dest.write_bytes(r.content)
            return True
    except Exception as e:
        logger.warning("rednote-cli: image download failed {}: {}", url[:80], e)
        return False


def _image_ext(url: str, index: int) -> str:
    path = urlparse(url).path
    ext = Path(path).suffix.lower()
    if ext in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
        return ext
    return ".jpg"


# ---------------------------------------------------------------------------
# Main fetch function
# ---------------------------------------------------------------------------

async def fetch_note(
    url_or_share: str,
    *,
    data_dir: Path,
    cdp_port: int = 19327,
    max_images: int = 20,
    storage_state_path: str | None = None,
) -> dict[str, Any]:
    """
    Fetch a Xiaohongshu note, save text + images to data_dir/{note_id}/, and
    return a dict with note metadata + note_dir path.

    Raises RuntimeError on unrecoverable errors.
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError as e:
        raise RuntimeError(
            "Playwright is required. Install it with: pip install playwright && playwright install chromium"
        ) from e

    target_url = _extract_url(url_or_share)
    if not target_url:
        raise RuntimeError(f"Could not parse a valid RedNote URL from: {url_or_share!r}")

    cdp_url = f"http://127.0.0.1:{cdp_port}"

    async with async_playwright() as p:
        try:
            browser = await p.chromium.connect_over_cdp(cdp_url, timeout=15_000)
        except Exception as e:
            raise RuntimeError(
                f"Cannot connect to Chrome at {cdp_url}. "
                "Start Chrome with: google-chrome --remote-debugging-port=19327"
            ) from e

        try:
            use_storage = bool(storage_state_path and Path(storage_state_path).exists())
            if use_storage:
                context = await browser.new_context(storage_state=storage_state_path)
            elif browser.contexts:
                context = browser.contexts[0]
            else:
                context = await browser.new_context()

            page = await context.new_page()
            try:
                await page.goto(target_url, wait_until="domcontentloaded", timeout=20_000)
                try:
                    await page.wait_for_load_state("networkidle", timeout=6_000)
                except Exception:
                    pass
                await page.wait_for_selector(".note-container", timeout=25_000)
                try:
                    await page.wait_for_selector(".media-container", timeout=8_000)
                except Exception:
                    pass
                await asyncio.sleep(1.5)

                # The final URL after redirects contains the canonical note ID
                final_url = page.url
                data = await page.evaluate(_EXTRACT_SCRIPT)
            finally:
                await page.close()
        finally:
            await browser.close()

    if not data:
        raise RuntimeError("Note content not found — page structure may have changed.")

    note_id = _extract_note_id(final_url) or _extract_note_id(target_url)
    if not note_id:
        # Last resort: use a timestamp-based ID
        note_id = f"unknown_{int(time.time())}"
        logger.warning("rednote-cli: could not extract note ID from {}", final_url)

    # ------------------------------------------------------------------
    # Save to disk
    # ------------------------------------------------------------------
    note_dir = data_dir / note_id
    note_dir.mkdir(parents=True, exist_ok=True)

    title = (data.get("title") or "").strip()
    content = (data.get("content") or "").strip()
    author = (data.get("author") or "").strip()
    tags: list[str] = data.get("tags") or []
    imgs: list[str] = data.get("imgs") or []
    likes = int(data.get("likes") or 0)
    comments = int(data.get("comments") or 0)

    # content.txt
    text_lines = []
    if title:
        text_lines.append(f"# {title}")
        text_lines.append("")
    if author:
        text_lines.append(f"作者: {author}")
    if tags:
        text_lines.append(f"标签: {' '.join('#' + t for t in tags if t)}")
    if likes or comments:
        text_lines.append(f"点赞: {likes}  评论: {comments}")
    text_lines.append("")
    text_lines.append(content)
    (note_dir / "content.txt").write_text("\n".join(text_lines), encoding="utf-8")

    # images
    saved_images: list[str] = []
    for i, img_url in enumerate(imgs[:max_images]):
        ext = _image_ext(img_url, i)
        dest = note_dir / f"image_{i:02d}{ext}"
        ok = await _download_image(img_url, dest)
        if ok:
            saved_images.append(dest.name)

    # note.json — machine-readable metadata
    meta = {
        "note_id": note_id,
        "url": final_url,
        "title": title,
        "author": author,
        "content": content,
        "tags": tags,
        "likes": likes,
        "comments": comments,
        "images": saved_images,
        "image_count": len(saved_images),
        "note_dir": str(note_dir),
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    (note_dir / "note.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    logger.info(
        "rednote-cli: saved note {} → {} ({} images)",
        note_id,
        note_dir,
        len(saved_images),
    )
    return meta
