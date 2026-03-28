"""QQ channel for cursor-claw using qq-botpy SDK."""

from __future__ import annotations

import asyncio
from collections import deque

from loguru import logger

from cursor_claw.channels.base import BaseChannel
from cursor_claw.config import Settings
from cursor_claw.media import append_attachments, cleanup_temp_dir, download_url, make_temp_dir

try:
    import botpy
    from botpy.message import C2CMessage

    QQ_AVAILABLE = True
except ImportError:
    QQ_AVAILABLE = False
    botpy = None  # type: ignore[assignment]
    C2CMessage = None  # type: ignore[assignment,misc]


def _make_bot_class(channel: "QQChannel") -> "type":
    """Build a botpy Client subclass wired to this channel instance."""
    intents = botpy.Intents(public_messages=True, direct_message=True)

    class _Bot(botpy.Client):
        def __init__(self) -> None:
            super().__init__(intents=intents, ext_handlers=False)

        async def on_ready(self) -> None:
            logger.info("QQ bot ready: {}", self.robot.name)

        async def on_c2c_message_create(self, message: "C2CMessage") -> None:
            await channel._on_message(message)

        async def on_direct_message_create(self, message: "C2CMessage") -> None:
            await channel._on_message(message)

    return _Bot


class QQChannel(BaseChannel):
    """QQ channel using botpy WebSocket (no public IP needed)."""

    name = "qq"

    def __init__(self, settings: Settings) -> None:
        super().__init__(settings)
        self.cfg = settings.channels.qq
        self._client: "botpy.Client | None" = None
        self._processed_ids: deque[str] = deque(maxlen=1000)
        self._active_user_id: str | None = None
        self._active_msg_id: str | None = None

    async def start(self) -> None:
        if not QQ_AVAILABLE:
            logger.error(
                "qq-botpy is not installed. Run: pip install 'cursor-claw[qq]'"
            )
            return

        if not self.cfg.app_id or not self.cfg.secret:
            logger.error("QQ app_id and secret not configured")
            return

        self._running = True
        BotClass = _make_bot_class(self)
        self._client = BotClass()
        logger.info("QQ bot starting (C2C private messages)...")
        await self._run_with_reconnect()

    async def _run_with_reconnect(self) -> None:
        while self._running:
            try:
                await self._client.start(  # type: ignore[union-attr]
                    appid=self.cfg.app_id, secret=self.cfg.secret
                )
            except Exception as e:
                logger.warning("QQ bot error: {}", e)
            if self._running:
                logger.info("QQ bot reconnecting in 5s...")
                await asyncio.sleep(5)

    async def stop(self) -> None:
        self._running = False
        if self._client:
            try:
                await self._client.close()
            except Exception:
                pass
        logger.info("QQ bot stopped")

    async def send_reply(self, openid: str, content: str, msg_id: str | None) -> None:
        if not self._client:
            return
        try:
            await self._client.api.post_c2c_message(  # type: ignore[union-attr]
                openid=openid,
                msg_type=0,
                content=content,
                msg_id=msg_id,
            )
        except Exception as e:
            logger.error("QQ send failed: {}", e)

    async def send_image(self, path: "Path") -> None:  # type: ignore[override]  # noqa: F821
        """Send a local image back over QQ C2C.

        QQ's open-platform API requires uploading rich media to their CDN before
        posting (msg_type=7).  That flow is complex and token-scoped; for now we
        fall back to sending the file path as a plain text message so the user at
        least knows the image was produced.
        """
        user_id = getattr(self, "_active_user_id", None)
        msg_id = getattr(self, "_active_msg_id", None)
        if not user_id:
            logger.warning("QQ send_image: no active user, dropping {}", path)
            return
        # Attempt rich-media upload (msg_type 7 = file/media) — best-effort.
        if self._client:
            try:
                # Upload the file, get file_info token, then post as media message.
                import base64

                with open(path, "rb") as f:
                    file_data = f.read()
                b64 = base64.b64encode(file_data).decode()
                upload_resp = await self._client.api.post_c2c_files(  # type: ignore[union-attr]
                    openid=user_id,
                    file_type=1,  # 1 = image
                    file_data=b64,
                )
                file_info = upload_resp.get("file_info") if isinstance(upload_resp, dict) else None
                if file_info:
                    await self._client.api.post_c2c_message(  # type: ignore[union-attr]
                        openid=user_id,
                        msg_type=7,
                        msg_id=msg_id,
                        media={"file_info": file_info},
                    )
                    logger.info("QQ image sent user={} path={}", user_id, path)
                    return
            except Exception as e:
                logger.warning("QQ rich-media send failed, falling back to text: {}", e)
        # Fallback: plain text with the local path
        await self.send_reply(user_id, f"[图片已生成，本地路径：{path}]", msg_id)

    _NEW_COMMANDS = {"/new", "/新建", "新建对话"}

    async def _on_message(self, data: "C2CMessage") -> None:
        try:
            if data.id in self._processed_ids:
                return
            self._processed_ids.append(data.id)

            author = data.author
            user_id = str(
                getattr(author, "id", None) or getattr(author, "user_openid", "unknown")
            )
            content = (data.content or "").strip()
            if not content:
                return

            if not self.is_allowed(user_id, self.cfg.allow_from):
                logger.warning("QQ access denied for {}", user_id)
                return

            msg_id = data.id
            session_key = f"qq:{user_id}"

            # /new command — reset session
            if content.lower() in self._NEW_COMMANDS:
                self.store.delete("cursor:chat_ids", session_key)
                await self.send_reply(user_id, "已开始新对话。(New conversation started.)", msg_id)
                logger.info("QQ /new session cleared for {}", user_id)
                return

            self._active_user_id = user_id  # expose for send_image()
            self._active_msg_id = msg_id
            logger.info("QQ message from {} len={}", user_id, len(content))

            async def _flush(chunk: str) -> None:
                await self.send_reply(user_id, chunk, msg_id)

            async def _error(msg: str) -> None:
                await self.send_reply(user_id, msg, msg_id)

            async def _run() -> None:
                prompt = content
                temp_dir = None
                try:
                    paths = await self._download_attachments(data)
                    if paths:
                        temp_dir = paths[0].parent
                        prompt = append_attachments(prompt, paths)
                        logger.info(
                            "QQ attachments downloaded count={} dir={}",
                            len(paths),
                            temp_dir,
                        )
                    await self._run_turn_safe(
                        session_key=session_key,
                        prompt_text=prompt,
                        on_flush=_flush,
                        on_error=_error,
                    )
                finally:
                    cleanup_temp_dir(temp_dir)

            asyncio.create_task(_run())
        except Exception:
            logger.exception("QQ message handling error")

    async def _download_attachments(self, data: "C2CMessage") -> list:
        """Download image attachments from a QQ C2CMessage to a temp dir."""
        from pathlib import Path

        raw_attachments = getattr(data, "attachments", None) or []
        if not raw_attachments:
            return []

        temp_dir = make_temp_dir()
        paths: list[Path] = []

        for att in raw_attachments:
            url = getattr(att, "url", None)
            if not url:
                continue
            content_type = getattr(att, "content_type", "") or ""
            if content_type and not content_type.startswith("image/"):
                continue  # skip non-images
            filename = getattr(att, "filename", None) or ""
            ext = filename.rsplit(".", 1)[-1] if "." in filename else "jpg"
            dest = temp_dir / f"attachment_{len(paths)}.{ext}"
            try:
                await download_url(url, dest)
                paths.append(dest)
            except Exception as e:
                logger.warning("QQ attachment download failed url={}: {}", url, e)

        if not paths:
            cleanup_temp_dir(temp_dir)
        return paths
