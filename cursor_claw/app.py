"""Mattermost WebSocket listener + per-thread agent runs.

Inbound ``posted`` handling follows the same control flow as
``finclaw/channels/mattermost.py`` (MattermostChannel._on_websocket_event):
``system_*`` post types only, DM vs channel chatmode gating, thread continuation
via ``_bot_threads``, strip mention/onchar, then acknowledgement reaction before work.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections import deque
from typing import Any

from loguru import logger
from mattermostautodriver import AsyncDriver

from cursor_claw.agent_runner import run_agent_turn
from cursor_claw.config import Settings, cursorclaw_workspace
from cursor_claw.prompt import build_prompt
from cursor_claw.store import StateStore

_NS_CHAT = "cursor:chat_ids"
_NS_SEEN = "cursor:last_seen_ts"


def normalize_mattermost_emoji_name(name: str) -> str:
    """Mattermost API expects emoji_name without colons (e.g. eyes, not :eyes:)."""
    s = (name or "").strip()
    while s.startswith(":"):
        s = s[1:].lstrip()
    while s.endswith(":"):
        s = s[:-1].rstrip()
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


class CursorMattermostBot:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.store = StateStore(settings.state_db)
        self._driver: AsyncDriver | None = None
        self._bot_user_id: str | None = None
        self._bot_username: str | None = None
        self._running = False
        self._bot_threads: set[str] = set()
        self._seen_posts: deque[str] = deque(maxlen=8000)
        self._locks: dict[str, asyncio.Lock] = {}

    async def _add_reaction(self, post_id: str) -> None:
        """Add the acknowledgement reaction to the trigger post (best-effort)."""
        if not post_id or not self._bot_user_id or not self._driver:
            return
        emoji = normalize_mattermost_emoji_name(self.settings.react_emoji)
        try:
            await self._driver.reactions.save_reaction(
                options={
                    "user_id": self._bot_user_id,
                    "post_id": post_id,
                    "emoji_name": emoji,
                }
            )
            logger.info("reaction added emoji={} post_id={}", emoji, post_id)
        except Exception as e:
            logger.warning("reaction add failed post_id={} emoji={}: {}", post_id, emoji, e)

    async def _remove_reaction(self, post_id: str) -> None:
        """Remove the acknowledgement reaction from the trigger post (best-effort)."""
        if not post_id or not self._bot_user_id or not self._driver:
            return
        emoji = normalize_mattermost_emoji_name(self.settings.react_emoji)
        try:
            await self._driver.reactions.delete_reaction(
                user_id=self._bot_user_id,
                post_id=post_id,
                emoji_name=emoji,
            )
            logger.info("reaction removed emoji={} post_id={}", emoji, post_id)
        except Exception as e:
            logger.debug("reaction remove failed post_id={} emoji={}: {}", post_id, emoji, e)

    def _thread_lock(self, thread_key: str) -> asyncio.Lock:
        if thread_key not in self._locks:
            self._locks[thread_key] = asyncio.Lock()
        return self._locks[thread_key]

    async def start(self) -> None:
        if not self.settings.mattermost_bot_token or not self.settings.mattermost_base_url:
            raise ValueError("mattermost_bot_token and mattermost_base_url are required")

        url = self.settings.mattermost_base_url.rstrip("/")
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
                "token": self.settings.mattermost_bot_token,
                "port": port,
                "scheme": scheme,
                "verify": self.settings.mattermost_verify,
            }
        )
        await self._driver.login()
        me = await self._driver.users.get_user("me")
        self._bot_user_id = me.get("id")
        self._bot_username = me.get("username")
        logger.info(
            "cursor-claw connected to Mattermost as {} ({})",
            self._bot_username,
            self._bot_user_id,
        )
        logger.info("Starting Mattermost WebSocket listener...")
        self._running = True
        await self._driver.init_websocket(self._on_websocket_event)

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

    def _is_allowed(self, sender_id: str, chat_id: str, channel_type: str) -> bool:
        if channel_type == "D":
            if not self.settings.dm_enabled:
                return False
            # Empty list = open (any user may DM); non-empty = allowlist of Mattermost user IDs.
            if self.settings.dm_allow_from:
                return sender_id in self.settings.dm_allow_from
            return True
        if self.settings.group_policy == "allowlist":
            return chat_id in self.settings.group_allow_from
        return True

    def _should_respond(self, text: str, channel_type: str) -> bool:
        # Same as finclaw MattermostChannel._should_respond; caller skips this for DMs.
        mode = self.settings.chatmode
        if mode == "onmessage":
            return True
        if mode == "oncall":
            return self._is_mentioned(text)
        if mode == "onchar":
            if self._is_mentioned(text):
                return True
            return any(text.startswith(p) for p in self.settings.onchar_prefixes)
        return False

    def _is_mentioned(self, text: str) -> bool:
        if not self._bot_username:
            return False
        return f"@{self._bot_username}" in text

    def _strip_bot_mention(self, text: str) -> str:
        if not text or not self._bot_username:
            return text
        return re.sub(rf"@{re.escape(self._bot_username)}\s*", "", text).strip()

    def _strip_onchar_prefix(self, text: str) -> str:
        if self.settings.chatmode != "onchar":
            return text
        for prefix in self.settings.onchar_prefixes:
            if text.startswith(prefix):
                return text[len(prefix):].strip()
        return text

    async def _on_websocket_event(self, event_data: dict[str, Any] | str) -> None:
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
        # Thread root for session continuity (finclaw: root_id = raw_root_id or post_id)
        root_id = raw_root_id or post_id

        if self._bot_user_id and sender_id == self._bot_user_id:
            return

        ptype = post.get("type")
        if isinstance(ptype, str) and ptype.startswith("system_"):
            return

        channel_type = data.get("channel_type", "")

        logger.debug(
            "Mattermost event: channel_type={} sender={} channel={} text={}",
            channel_type,
            sender_id,
            chat_id,
            text[:80],
        )

        if not sender_id or not chat_id:
            return

        if not post_id or post_id in self._seen_posts:
            return

        if not self._is_allowed(sender_id, chat_id, channel_type):
            return

        thread_mm = f"{chat_id}:{raw_root_id}" if raw_root_id else ""
        is_bot_thread = bool(raw_root_id) and thread_mm in self._bot_threads

        if channel_type != "D" and not is_bot_thread and not self._should_respond(text, channel_type):
            return

        if self._is_mentioned(text):
            text = self._strip_bot_mention(text)
        text = self._strip_onchar_prefix(text)
        if not text.strip():
            return

        thread_key = f"{chat_id}:{root_id}"
        self._seen_posts.append(post_id)
        logger.info(
            "Mattermost posted → agent post_id={} channel={} root_id={} prompt_len={}",
            post_id,
            chat_id,
            root_id,
            len(text),
        )

        if raw_root_id:
            self._bot_threads.add(thread_mm)

        # Schedule the turn; reaction add is the first thing the task does so the
        # WebSocket handler returns immediately without blocking on the HTTP call.
        asyncio.create_task(self._process_turn_safe(thread_key, root_id, chat_id, text, post_id))

    async def _process_turn_safe(
        self,
        thread_key: str,
        session_root_id: str,
        channel_id: str,
        prompt: str,
        trigger_post_id: str,
    ) -> None:
        # React immediately — this is the first async op in the task, so it fires
        # as soon as the event loop schedules us (next iteration after WS handler returns).
        await self._add_reaction(trigger_post_id)
        lock = self._thread_lock(thread_key)
        async with lock:
            try:
                await self._process_turn(thread_key, session_root_id, channel_id, prompt, trigger_post_id)
            except Exception:
                logger.exception("turn failed thread={}", thread_key)
                await self._post_error(channel_id, session_root_id, "Sorry, something went wrong running the agent.")
            finally:
                await self._remove_reaction(trigger_post_id)

    async def _post_error(self, channel_id: str, session_root_id: str, msg: str) -> None:
        if not self._driver:
            return
        body: dict[str, Any] = {"channel_id": channel_id, "message": msg}
        if self.settings.reply_in_thread and session_root_id:
            body["root_id"] = session_root_id
        try:
            await self._driver.posts.create_post(options=body)
        except Exception as e:
            logger.error("post error message failed: {}", e)

    async def _post_chunks(self, channel_id: str, session_root_id: str, content: str) -> None:
        if not self._driver or not content.strip():
            return
        for part in _split_message(content, self.settings.max_post_chars):
            body: dict[str, Any] = {"channel_id": channel_id, "message": part}
            if self.settings.reply_in_thread and session_root_id:
                body["root_id"] = session_root_id
            try:
                await self._driver.posts.create_post(options=body)
            except Exception as e:
                logger.error("create_post failed: {}", e)

    async def _process_turn(
        self,
        thread_key: str,
        session_root_id: str,
        channel_id: str,
        prompt: str,
        trigger_post_id: str,
    ) -> None:
        assert self._driver
        resume = self.store.get(_NS_CHAT, thread_key)
        self.store.set(_NS_SEEN, thread_key, trigger_post_id)

        self._bot_threads.add(thread_key)

        final_session: str | None = resume
        logger.info(
            "agent turn start thread_key={} workspace={} resume={}",
            thread_key,
            self.settings.workspace,
            resume is not None,
        )

        context_dir = cursorclaw_workspace()
        full_prompt = build_prompt(prompt, context_dir, workspace=self.settings.workspace)
        logger.debug("prompt with system context: {} chars (original: {})", len(full_prompt), len(prompt))

        async def _inner() -> None:
            nonlocal final_session
            async for kind, payload in run_agent_turn(
                prompt=full_prompt,
                workspace=self.settings.workspace,
                agent_command=self.settings.agent_command,
                resume_session_id=resume,
                chunk_timeout_sec=self.settings.chunk_timeout_sec,
                turn_timeout_sec=self.settings.turn_timeout_sec,
            ):
                if kind == "flush" and isinstance(payload, str):
                    await self._post_chunks(channel_id, session_root_id, payload)
                elif kind == "done":
                    if isinstance(payload, str) and payload.strip():
                        final_session = payload.strip()

        timed_out = False
        task = asyncio.create_task(_inner())
        try:
            await asyncio.wait_for(task, timeout=self.settings.outer_timeout_sec)
        except TimeoutError:
            timed_out = True
            logger.warning("outer timeout {}", self.settings.outer_timeout_sec)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            await self._post_error(channel_id, session_root_id, "Turn timed out (outer limit).")

        if not timed_out and final_session:
            self.store.set(_NS_CHAT, thread_key, final_session)


async def run_bot(settings: Settings) -> None:
    bot = CursorMattermostBot(settings)
    await bot.start()
