"""Multi-channel runner: starts all enabled channels concurrently."""

from __future__ import annotations

import asyncio

from loguru import logger

from cursor_claw.channels.base import BaseChannel
from cursor_claw.config import Settings


async def run_bot(settings: Settings) -> None:
    """Instantiate and start every enabled channel concurrently."""
    channels: list[BaseChannel] = []

    if settings.channels.mattermost.enabled:
        try:
            from cursor_claw.channels.mattermost import MattermostChannel
            channels.append(MattermostChannel(settings))
            logger.info("Mattermost channel enabled")
        except ImportError as e:
            logger.warning("Mattermost channel unavailable: {}", e)

    if settings.channels.telegram.enabled:
        try:
            from cursor_claw.channels.telegram import TelegramChannel
            channels.append(TelegramChannel(settings))
            logger.info("Telegram channel enabled")
        except ImportError as e:
            logger.warning("Telegram channel unavailable: {}", e)

    if settings.channels.qq.enabled:
        try:
            from cursor_claw.channels.qq import QQChannel
            channels.append(QQChannel(settings))
            logger.info("QQ channel enabled")
        except ImportError as e:
            logger.warning("QQ channel unavailable: {}", e)

    if not channels:
        logger.error(
            "No channels enabled. "
            "Set channels.mattermost.enabled, channels.telegram.enabled, "
            "or channels.qq.enabled to true in ~/.cursorclaw/config.json"
        )
        return

    await asyncio.gather(*(c.start() for c in channels), return_exceptions=True)
