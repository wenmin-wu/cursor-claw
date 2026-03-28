"""Mattermost WebSocket channel for cursor-claw."""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from loguru import logger
from mattermostautodriver import AsyncDriver

from cursor_claw.channels.base import BaseChannel
from cursor_claw.config import MattermostChannelConfig, Settings
from cursor_claw.media import append_attachments, cleanup_temp_dir, download_url, make_temp_dir


def _normalize_emoji(name: str) -> str:
    """Strip colons from emoji name for the Mattermost API."""
    s = (name or "").strip().strip(":")
    return s if s else "eyes"


def _split_message(text: str, max_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text] if text else []
    parts: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        chunk = text[start:end]
        if end < len(text):
            nl = chunk.rfind("\n\n")
            if nl > max_chars // 2:
                chunk = chunk[: nl + 2]
                end = start + nl + 2
        parts.append(chunk.strip())
        start = end
    return [p for p in parts if p]


class MattermostChannel(BaseChannel):
    """Mattermost channel using the WebSocket real-time API."""

    name = "mattermost"

    def __init__(self, settings: Settings) -> None:
        super().__init__(settings)
        self.cfg: MattermostChannelConfig = settings.channels.mattermost
        self._driver: AsyncDriver | None = None
        self._bot_user_id: str | None = None
        self._bot_username: str | None = None
        self._bot_threads: set[str] = set()
        self._active_channel_id: str | None = None
        self._active_root_id: str | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        if not self.cfg.bot_token or not self.cfg.base_url:
            raise ValueError("mattermost.bot_token and mattermost.base_url are required")

        url = self.cfg.base_url.rstrip("/")
        scheme = "https" if url.startswith("https") else "http"
        host_port = url.removeprefix("https://").removeprefix("http://")
        if ":" in host_port:
            host, port_str = host_port.rsplit(":", 1)
            port = int(port_str)
        else:
            host = host_port
            port = 443 if scheme == "https" else 80

        self._driver = AsyncDriver(
            {
                "url": host,
                "token": self.cfg.bot_token,
                "port": port,
                "scheme": scheme,
                "verify": self.cfg.verify,
            }
        )
        await self._driver.login()
        me = await self._driver.users.get_user("me")
        self._bot_user_id = me.get("id")
        self._bot_username = me.get("username")
        logger.info(
            "Mattermost connected as {} ({})",
            self._bot_username,
            self._bot_user_id,
        )
        self._running = True
        await self._driver.init_websocket(self._on_ws_event)

    async def stop(self) -> None:
        self._running = False
        if self._driver:
            try:
                ws = getattr(getattr(self._driver, "driver", None), "websocket", None)
                if ws is not None:
                    await ws.close()
            except Exception as e:
                logger.warning("Mattermost WebSocket close failed: {}", e)
            try:
                await self._driver.logout()
            except Exception as e:
                logger.warning("Mattermost logout failed: {}", e)
            self._driver = None

    # ------------------------------------------------------------------
    # Event handling
    # ------------------------------------------------------------------

    async def _on_ws_event(self, event_data: dict[str, Any] | str) -> None:
        if not self._running or not self._driver:
            return

        if isinstance(event_data, str):
            try:
                event_data = json.loads(event_data)
            except Exception:
                return

        if event_data.get("event") != "posted":
            return

        data = event_data.get("data", {})
        broadcast = event_data.get("broadcast", {})

        post_str = data.get("post", "{}")
        try:
            post = json.loads(post_str) if isinstance(post_str, str) else post_str
        except Exception:
            return
        if not isinstance(post, dict):
            return

        sender_id = post.get("user_id", "")
        chat_id = post.get("channel_id", "") or broadcast.get("channel_id", "")
        text = post.get("message", "")
        post_id = post.get("id", "")
        raw_root_id = post.get("root_id", "")
        root_id = raw_root_id or post_id
        channel_type = data.get("channel_type", "")

        if self._bot_user_id and sender_id == self._bot_user_id:
            return

        ptype = post.get("type")
        if isinstance(ptype, str) and ptype.startswith("system_"):
            return

        if not sender_id or not chat_id or not post_id:
            return

        if self._is_seen(post_id):
            return

        if not self._is_allowed_post(sender_id, chat_id, channel_type):
            return

        thread_mm = f"{chat_id}:{raw_root_id}" if raw_root_id else ""
        is_bot_thread = bool(raw_root_id) and thread_mm in self._bot_threads

        if channel_type != "D" and not is_bot_thread and not self._should_respond(text):
            return

        if self._is_mentioned(text):
            text = re.sub(
                rf"@{re.escape(self._bot_username or '')}\s*", "", text
            ).strip()
        if self.cfg.chatmode == "onchar":
            for prefix in self.cfg.onchar_prefixes:
                if text.startswith(prefix):
                    text = text[len(prefix):].strip()
                    break
        if not text.strip():
            return

        thread_key = f"mattermost:{chat_id}:{root_id}"
        self._mark_seen(post_id)
        if raw_root_id:
            self._bot_threads.add(thread_mm)

        # Collect image file IDs and their metadata from the post
        file_ids: list[str] = post.get("file_ids") or []
        file_meta: dict[str, dict] = {}
        for f in (post.get("metadata") or {}).get("files") or []:
            if isinstance(f, dict) and f.get("id"):
                file_meta[f["id"]] = f

        logger.info(
            "Mattermost post → agent post_id={} channel={} root_id={} files={}",
            post_id,
            chat_id,
            root_id,
            len(file_ids),
        )
        asyncio.create_task(
            self._handle_turn(thread_key, chat_id, root_id, text, post_id, file_ids, file_meta)
        )

    def _set_active_thread(self, channel_id: str, root_id: str) -> None:
        self._active_channel_id = channel_id
        self._active_root_id = root_id

    async def send_image(self, path: "Path") -> None:  # type: ignore[override]
        """Upload an image file to Mattermost and post it in the active thread."""
        from pathlib import Path as _Path

        channel_id = getattr(self, "_active_channel_id", None)
        root_id = getattr(self, "_active_root_id", None)
        if not channel_id or not self._driver:
            logger.warning("Mattermost send_image: no active channel, dropping {}", path)
            return
        try:
            filename = _Path(path).name
            with open(path, "rb") as f:
                data = f.read()
            resp = await self._driver.files.upload_file(
                channel_id=channel_id,
                files={"files": (filename, data, "image/png")},
            )
            fid = resp["file_infos"][0]["id"]
            body: dict[str, Any] = {
                "channel_id": channel_id,
                "message": "",
                "file_ids": [fid],
            }
            if self.cfg.reply_in_thread and root_id:
                body["root_id"] = root_id
            await self._driver.posts.create_post(options=body)
            logger.info("Mattermost image sent channel={} path={}", channel_id, path)
        except Exception as e:
            logger.error("Mattermost send_image failed {}: {}", path, e)

    async def _handle_turn(
        self,
        thread_key: str,
        channel_id: str,
        root_id: str,
        prompt: str,
        trigger_post_id: str,
        file_ids: list[str] | None = None,
        file_meta: dict[str, dict] | None = None,
    ) -> None:
        self._set_active_thread(channel_id, root_id)
        await self._add_reaction(trigger_post_id)
        self._bot_threads.add(thread_key)
        temp_dir = None
        try:
            if file_ids:
                paths = await self._download_files(file_ids, file_meta or {})
                if paths:
                    temp_dir = paths[0].parent
                    prompt = append_attachments(prompt, paths)
                    logger.info("Mattermost attachments count={} dir={}", len(paths), temp_dir)

            await self._run_turn_safe(
                session_key=thread_key,
                prompt_text=prompt,
                on_flush=lambda text: self._post_chunks(channel_id, root_id, text),
                on_error=lambda msg: self._post_error(channel_id, root_id, msg),
            )
        finally:
            await self._remove_reaction(trigger_post_id)
            cleanup_temp_dir(temp_dir)

    async def _download_files(
        self,
        file_ids: list[str],
        file_meta: dict[str, dict],
    ) -> list:
        """Download image attachments from Mattermost to a temp dir."""
        from pathlib import Path

        temp_dir = make_temp_dir()
        paths: list[Path] = []
        base_url = self.cfg.base_url.rstrip("/")
        headers = {"Authorization": f"Bearer {self.cfg.bot_token}"}

        for fid in file_ids:
            meta = file_meta.get(fid, {})
            mime = meta.get("mime_type", "")
            if mime and not mime.startswith("image/"):
                continue  # skip non-images
            ext = meta.get("extension") or "bin"
            dest = temp_dir / f"attachment_{len(paths)}.{ext}"
            url = f"{base_url}/api/v4/files/{fid}"
            try:
                await download_url(url, dest, headers=headers)
                paths.append(dest)
            except Exception as e:
                logger.warning("Mattermost file download failed id={}: {}", fid, e)

        if not paths:
            cleanup_temp_dir(temp_dir)
        return paths

    # ------------------------------------------------------------------
    # Mattermost API helpers
    # ------------------------------------------------------------------

    def _is_allowed_post(self, sender_id: str, chat_id: str, channel_type: str) -> bool:
        if channel_type == "D":
            if not self.cfg.dm_enabled:
                return False
            if self.cfg.dm_allow_from:
                return sender_id in self.cfg.dm_allow_from
            return True
        if self.cfg.group_policy == "allowlist":
            return chat_id in self.cfg.group_allow_from
        return True

    def _should_respond(self, text: str) -> bool:
        if self.cfg.chatmode == "onmessage":
            return True
        if self.cfg.chatmode == "oncall":
            return self._is_mentioned(text)
        if self.cfg.chatmode == "onchar":
            if self._is_mentioned(text):
                return True
            return any(text.startswith(p) for p in self.cfg.onchar_prefixes)
        return False

    def _is_mentioned(self, text: str) -> bool:
        if not self._bot_username:
            return False
        return f"@{self._bot_username}" in text

    async def _add_reaction(self, post_id: str) -> None:
        if not post_id or not self._bot_user_id or not self._driver:
            return
        emoji = _normalize_emoji(self.cfg.react_emoji)
        try:
            await self._driver.reactions.save_reaction(
                options={
                    "user_id": self._bot_user_id,
                    "post_id": post_id,
                    "emoji_name": emoji,
                }
            )
        except Exception as e:
            logger.warning("Mattermost reaction add failed: {}", e)

    async def _remove_reaction(self, post_id: str) -> None:
        if not post_id or not self._bot_user_id or not self._driver:
            return
        emoji = _normalize_emoji(self.cfg.react_emoji)
        try:
            await self._driver.reactions.delete_reaction(
                user_id=self._bot_user_id,
                post_id=post_id,
                emoji_name=emoji,
            )
        except Exception as e:
            logger.debug("Mattermost reaction remove failed: {}", e)

    async def _post_error(self, channel_id: str, root_id: str, msg: str) -> None:
        if not self._driver:
            return
        body: dict[str, Any] = {"channel_id": channel_id, "message": msg}
        if self.cfg.reply_in_thread and root_id:
            body["root_id"] = root_id
        try:
            await self._driver.posts.create_post(options=body)
        except Exception as e:
            logger.error("Mattermost post error failed: {}", e)

    async def _post_chunks(self, channel_id: str, root_id: str, content: str) -> None:
        if not self._driver or not content.strip():
            return
        for part in _split_message(content, self.cfg.max_post_chars):
            body: dict[str, Any] = {"channel_id": channel_id, "message": part}
            if self.cfg.reply_in_thread and root_id:
                body["root_id"] = root_id
            try:
                await self._driver.posts.create_post(options=body)
            except Exception as e:
                logger.error("Mattermost create_post failed: {}", e)
