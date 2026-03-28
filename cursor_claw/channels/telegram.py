"""Telegram channel for cursor-claw using python-telegram-bot."""

from __future__ import annotations

import asyncio
import re
import time

from loguru import logger

from cursor_claw.channels.base import BaseChannel
from cursor_claw.config import Settings
from cursor_claw.media import append_attachments, cleanup_temp_dir, make_temp_dir

try:
    from telegram import BotCommand, Update
    from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
    from telegram.request import HTTPXRequest

    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False


def _md_to_html(text: str) -> str:
    """Convert basic markdown to Telegram HTML (safe subset)."""
    if not text:
        return ""

    code_blocks: list[str] = []

    def _save_block(m: re.Match) -> str:
        code_blocks.append(m.group(1))
        return f"\x00CB{len(code_blocks) - 1}\x00"

    inline_codes: list[str] = []

    def _save_inline(m: re.Match) -> str:
        inline_codes.append(m.group(1))
        return f"\x00IC{len(inline_codes) - 1}\x00"

    text = re.sub(r"```[\w]*\n?([\s\S]*?)```", _save_block, text)
    text = re.sub(r"`([^`]+)`", _save_inline, text)
    text = re.sub(r"^#{1,6}\s+(.+)$", r"\1", text, flags=re.MULTILINE)
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"__(.+?)__", r"<b>\1</b>", text)
    text = re.sub(r"(?<![a-zA-Z0-9])_([^_]+)_(?![a-zA-Z0-9])", r"<i>\1</i>", text)
    text = re.sub(r"~~(.+?)~~", r"<s>\1</s>", text)
    text = re.sub(r"^[-*]\s+", "• ", text, flags=re.MULTILINE)

    for i, code in enumerate(inline_codes):
        esc = code.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        text = text.replace(f"\x00IC{i}\x00", f"<code>{esc}</code>")
    for i, code in enumerate(code_blocks):
        esc = code.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        text = text.replace(f"\x00CB{i}\x00", f"<pre><code>{esc}</code></pre>")

    return text


def _split(text: str, max_len: int = 4000) -> list[str]:
    if len(text) <= max_len:
        return [text]
    chunks: list[str] = []
    while text:
        if len(text) <= max_len:
            chunks.append(text)
            break
        cut = text[:max_len]
        pos = cut.rfind("\n")
        if pos == -1:
            pos = cut.rfind(" ")
        if pos == -1:
            pos = max_len
        chunks.append(text[:pos])
        text = text[pos:].lstrip()
    return chunks


class TelegramChannel(BaseChannel):
    """Telegram channel using long polling (no public IP needed)."""

    name = "telegram"

    BOT_COMMANDS = [
        ("start", "Start the bot"),
        ("new", "Start a new conversation"),
        ("help", "Show available commands"),
    ]

    def __init__(self, settings: Settings) -> None:
        super().__init__(settings)
        self.cfg = settings.channels.telegram
        self._app: "Application | None" = None
        self._typing_tasks: dict[str, asyncio.Task] = {}
        self._active_chat_id: str | None = None

    async def start(self) -> None:
        if not TELEGRAM_AVAILABLE:
            logger.error(
                "python-telegram-bot is not installed. "
                "Run: pip install 'cursor-claw[telegram]'"
            )
            return

        if not self.cfg.token:
            logger.error("Telegram token not configured")
            return

        self._running = True

        req = HTTPXRequest(
            connection_pool_size=16,
            pool_timeout=5.0,
            connect_timeout=30.0,
            read_timeout=30.0,
        )
        builder = (
            Application.builder().token(self.cfg.token).request(req).get_updates_request(req)
        )
        if self.cfg.proxy:
            builder = builder.proxy(self.cfg.proxy).get_updates_proxy(self.cfg.proxy)

        self._app = builder.build()
        self._app.add_error_handler(self._on_error)
        self._app.add_handler(CommandHandler("start", self._on_start))
        self._app.add_handler(CommandHandler("new", self._on_new))
        self._app.add_handler(CommandHandler("help", self._on_help))
        self._app.add_handler(
            MessageHandler(
                (filters.TEXT | filters.PHOTO | filters.Document.IMAGE) & ~filters.COMMAND,
                self._on_message,
            )
        )

        await self._app.initialize()
        await self._app.start()

        bot_info = await self._app.bot.get_me()
        logger.info("Telegram bot @{} connected", bot_info.username)

        try:
            await self._app.bot.set_my_commands(
                [BotCommand(cmd, desc) for cmd, desc in self.BOT_COMMANDS]
            )
        except Exception as e:
            logger.warning("Telegram command registration failed: {}", e)

        await self._app.updater.start_polling(
            allowed_updates=["message"],
            drop_pending_updates=True,
        )

        while self._running:
            await asyncio.sleep(1)

    async def stop(self) -> None:
        self._running = False
        for task in self._typing_tasks.values():
            task.cancel()
        self._typing_tasks.clear()
        if self._app:
            logger.info("Stopping Telegram bot...")
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()
            self._app = None

    # ------------------------------------------------------------------
    # Command handlers
    # ------------------------------------------------------------------

    async def _on_start(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None:
        if not update.message or not update.effective_user:
            return
        await update.message.reply_text(
            f"Hi {update.effective_user.first_name}! I'm cursor-claw, your AI coding agent.\n\n"
            "Send me a message and I'll get to work.\n"
            "/help for commands."
        )

    async def _on_new(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None:
        """Clear session so the next message starts a fresh conversation."""
        if not update.message or not update.effective_user:
            return
        session_key = self._session_key(str(update.message.chat_id))
        self.store.delete("cursor:chat_ids", session_key)
        await update.message.reply_text("Started a new conversation.")

    async def _on_help(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None:
        if not update.message:
            return
        await update.message.reply_text(
            "cursor-claw commands:\n"
            "/new — Start a new conversation\n"
            "/help — Show this message"
        )

    # ------------------------------------------------------------------
    # Message handler
    # ------------------------------------------------------------------

    async def _on_message(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None:
        if not update.message or not update.effective_user:
            return

        user = update.effective_user
        chat_id = str(update.message.chat_id)
        sender_id = f"{user.id}|{user.username}" if user.username else str(user.id)
        # caption covers text that arrives alongside a photo
        text = (update.message.text or update.message.caption or "").strip()
        message_id = update.message.message_id

        if not self.is_allowed(sender_id, self.cfg.allow_from):
            logger.warning("Telegram access denied for {}", sender_id)
            return

        session_key = self._session_key(chat_id)

        async def _run() -> None:
            self._active_chat_id = chat_id  # expose for send_image()
            prompt = text
            temp_dir = None
            try:
                # Download any attached images to a temp dir
                attachments = await self._download_attachments(update)
                if attachments:
                    temp_dir = attachments[0].parent
                    prompt = append_attachments(prompt, attachments)
                    logger.info(
                        "Telegram attachments downloaded count={} dir={}",
                        len(attachments),
                        temp_dir,
                    )

                if not prompt:
                    return

                logger.info(
                    "Telegram message from {} chat={} len={} images={}",
                    sender_id, chat_id, len(text), len(attachments),
                )
                await self._react(int(chat_id), message_id, "👀")
                self._start_typing(chat_id)
                try:
                    await self._run_turn_safe(
                        session_key=session_key,
                        prompt_text=prompt,
                        on_flush=lambda chunk: self._send_with_streaming(int(chat_id), chunk),
                        on_error=lambda msg: self._send_text(int(chat_id), msg),
                    )
                finally:
                    self._stop_typing(chat_id)
                    # Always clear 👀 first; then best-effort add ✅
                    await self._clear_react(int(chat_id), message_id)
                    await self._react(int(chat_id), message_id, "✅")
            finally:
                cleanup_temp_dir(temp_dir)

        asyncio.create_task(_run())

    async def _download_attachments(self, update: "Update") -> list:
        """Download photos / image documents from a Telegram message to a temp dir."""
        from pathlib import Path

        msg = update.message
        if not msg or not self._app:
            return []

        items: list[Path] = []
        temp_dir: Path | None = None

        try:
            # Photos: pick the highest-resolution variant
            if msg.photo:
                if temp_dir is None:
                    temp_dir = make_temp_dir()
                photo = msg.photo[-1]
                tg_file = await self._app.bot.get_file(photo.file_id)
                dest = temp_dir / f"photo_{len(items)}.jpg"
                await tg_file.download_to_drive(str(dest))
                items.append(dest)

            # Image documents (e.g. files sent as "file" not compressed photo)
            if msg.document and msg.document.mime_type and msg.document.mime_type.startswith("image/"):
                if temp_dir is None:
                    temp_dir = make_temp_dir()
                ext = msg.document.file_name.rsplit(".", 1)[-1] if msg.document.file_name else "jpg"
                tg_file = await self._app.bot.get_file(msg.document.file_id)
                dest = temp_dir / f"doc_{len(items)}.{ext}"
                await tg_file.download_to_drive(str(dest))
                items.append(dest)

        except Exception as e:
            logger.warning("Telegram attachment download failed: {}", e)

        return items

    # ------------------------------------------------------------------
    # Typing indicator
    # ------------------------------------------------------------------

    def _start_typing(self, chat_id: str) -> None:
        self._stop_typing(chat_id)
        self._typing_tasks[chat_id] = asyncio.create_task(self._typing_loop(chat_id))

    def _stop_typing(self, chat_id: str) -> None:
        task = self._typing_tasks.pop(chat_id, None)
        if task and not task.done():
            task.cancel()

    async def _typing_loop(self, chat_id: str) -> None:
        try:
            while self._app:
                await self._app.bot.send_chat_action(chat_id=int(chat_id), action="typing")
                await asyncio.sleep(4)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.debug("Typing indicator stopped for {}: {}", chat_id, e)

    # ------------------------------------------------------------------
    # Emoji reaction
    # ------------------------------------------------------------------

    async def _react(self, chat_id: int, message_id: int, emoji: str) -> None:
        """Set an emoji reaction on a message (Bot API 7.0+, best-effort)."""
        if not self._app:
            return
        try:
            from telegram import ReactionTypeEmoji
            await self._app.bot.set_message_reaction(
                chat_id=chat_id,
                message_id=message_id,
                reaction=[ReactionTypeEmoji(emoji)],
            )
        except Exception as e:
            logger.debug("Telegram reaction failed ({}): {}", emoji, e)

    async def _clear_react(self, chat_id: int, message_id: int) -> None:
        """Remove all reactions from a message (empty list = clear)."""
        if not self._app:
            return
        try:
            await self._app.bot.set_message_reaction(
                chat_id=chat_id,
                message_id=message_id,
                reaction=[],
            )
        except Exception as e:
            logger.debug("Telegram clear reaction failed: {}", e)

    # ------------------------------------------------------------------
    # Send helpers
    # ------------------------------------------------------------------

    async def _send_text(self, chat_id: int, text: str) -> None:
        """Send text as a plain Telegram message with markdown→HTML and plain-text fallback."""
        if not self._app:
            return
        for chunk in _split(text, self.cfg.max_message_chars):
            try:
                html = _md_to_html(chunk)
                await self._app.bot.send_message(chat_id=chat_id, text=html, parse_mode="HTML")
            except Exception:
                try:
                    await self._app.bot.send_message(chat_id=chat_id, text=chunk)
                except Exception as e:
                    logger.error("Telegram send failed: {}", e)

    async def _send_with_streaming(self, chat_id: int, text: str) -> None:
        """Animate text via sendMessageDraft (Bot API 9.3+), then persist with send_message.

        Falls back to a plain send_message if the draft API is not available.
        Each agent flush chunk is sent as its own message so that long responses
        arrive in readable segments rather than one giant block.
        """
        if not self._app:
            return
        for chunk in _split(text, self.cfg.max_message_chars):
            draft_fn = getattr(self._app.bot, "send_message_draft", None)
            if draft_fn is None:
                await self._send_text(chat_id, chunk)
                continue
            draft_id = int(time.time() * 1000) % (2**31)
            try:
                step = max(len(chunk) // 8, 40)
                for i in range(step, len(chunk), step):
                    await draft_fn(chat_id=chat_id, draft_id=draft_id, text=chunk[:i])
                    await asyncio.sleep(0.04)
                await draft_fn(chat_id=chat_id, draft_id=draft_id, text=chunk)
                await asyncio.sleep(0.15)
            except Exception:
                pass
            await self._send_text(chat_id, chunk)

    async def send_image(self, path: "Path") -> None:  # type: ignore[override]
        """Send a local image file to the most recently active chat."""
        # We store the current chat_id as a thread-local context via _active_chat_id.
        chat_id = getattr(self, "_active_chat_id", None)
        if not chat_id or not self._app:
            logger.warning("Telegram send_image: no active chat_id, dropping {}", path)
            return
        try:
            with open(path, "rb") as f:
                await self._app.bot.send_photo(chat_id=int(chat_id), photo=f)
            logger.info("Telegram image sent chat={} path={}", chat_id, path)
        except Exception as e:
            logger.error("Telegram send_photo failed {}: {}", path, e)

    async def _on_error(self, update: object, context: "ContextTypes.DEFAULT_TYPE") -> None:
        logger.error("Telegram error: {}", context.error)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _session_key(self, chat_id: str) -> str:
        return f"telegram:{chat_id}"
