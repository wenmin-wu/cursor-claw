"""QQ channel for cursor-claw using qq-botpy SDK."""

from __future__ import annotations

import asyncio
from collections import deque

from loguru import logger

from cursor_claw.channels.base import BaseChannel
from cursor_claw.config import Settings

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
            logger.info("QQ message from {} len={}", user_id, len(content))

            async def _flush(chunk: str) -> None:
                await self.send_reply(user_id, chunk, msg_id)

            async def _error(msg: str) -> None:
                await self.send_reply(user_id, msg, msg_id)

            asyncio.create_task(
                self._run_turn_safe(
                    session_key=session_key,
                    prompt_text=content,
                    on_flush=_flush,
                    on_error=_error,
                )
            )
        except Exception:
            logger.exception("QQ message handling error")
