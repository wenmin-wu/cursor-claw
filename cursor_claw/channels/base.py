"""Base channel class with shared agent-turn logic."""

from __future__ import annotations

import asyncio
from collections import deque
from typing import Any, Awaitable, Callable

from loguru import logger

from cursor_claw.agent_runner import run_agent_turn
from cursor_claw.config import Settings, cursorclaw_workspace
from cursor_claw.media import extract_send_images
from cursor_claw.prompt import build_prompt
from cursor_claw.store import StateStore

_NS_CHAT = "cursor:chat_ids"


class BaseChannel:
    """
    Abstract base for cursor-claw chat channels.

    Subclasses implement `start()` and `stop()` for platform-specific
    connection logic, then call `_run_turn_safe()` when a message arrives.
    The base class owns agent execution and session-persistence.
    """

    name: str = "base"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.store = StateStore(settings.state_db)
        self._running = False
        self._locks: dict[str, asyncio.Lock] = {}
        self._seen_ids: deque[str] = deque(maxlen=8000)

    # ------------------------------------------------------------------
    # Subclass interface
    # ------------------------------------------------------------------

    async def start(self) -> None:
        raise NotImplementedError

    async def stop(self) -> None:
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Access control
    # ------------------------------------------------------------------

    def is_allowed(self, user_id: str, allow_from: list[str]) -> bool:
        """Return True if user_id is on the allow-list (empty list = allow all)."""
        if not allow_from:
            return True
        uid = str(user_id)
        if uid in allow_from:
            return True
        # Support "numeric_id|username" composite IDs (Telegram)
        if "|" in uid:
            for part in uid.split("|"):
                if part and part in allow_from:
                    return True
        return False

    # ------------------------------------------------------------------
    # Dedup helpers
    # ------------------------------------------------------------------

    def _is_seen(self, msg_id: str) -> bool:
        return msg_id in self._seen_ids

    def _mark_seen(self, msg_id: str) -> None:
        self._seen_ids.append(msg_id)

    # ------------------------------------------------------------------
    # Per-thread locking
    # ------------------------------------------------------------------

    def _thread_lock(self, key: str) -> asyncio.Lock:
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()
        return self._locks[key]

    # ------------------------------------------------------------------
    # Agent turn
    # ------------------------------------------------------------------

    async def send_image(self, path: "Path") -> None:  # noqa: F821
        """Send a local image file back to the user.  Override in each channel."""
        logger.warning("{}: send_image not implemented, dropping {}", self.name, path)

    async def _run_turn_safe(
        self,
        *,
        session_key: str,
        prompt_text: str,
        on_flush: Callable[[str], Awaitable[None]],
        on_error: Callable[[str], Awaitable[None]],
        on_image: "Callable[[Path], Awaitable[None]] | None" = None,  # noqa: F821
    ) -> None:
        """
        Acquire per-thread lock and run one full agent turn.

        Calls `on_flush(chunk)` for each text chunk produced by the agent,
        strips ``[SEND_IMAGE: /path]`` markers and routes them to `on_image`
        (defaults to `self.send_image`), and calls `on_error(msg)` on failure.
        """
        _image_cb = on_image or self.send_image

        async def _intercepting_flush(chunk: str) -> None:
            clean, paths = extract_send_images(chunk)
            for p in paths:
                logger.info("{}: SEND_IMAGE detected path={}", self.name, p)
                try:
                    await _image_cb(p)
                except Exception as e:
                    logger.error("{}: send_image failed {}: {}", self.name, p, e)
            if clean:
                await on_flush(clean)

        lock = self._thread_lock(session_key)
        async with lock:
            try:
                await self._execute_turn(
                    session_key=session_key,
                    prompt_text=prompt_text,
                    on_flush=_intercepting_flush,
                    on_error=on_error,
                )
            except Exception:
                logger.exception("{}: turn failed key={}", self.name, session_key)
                await on_error("Sorry, something went wrong running the agent.")

    async def _execute_turn(
        self,
        *,
        session_key: str,
        prompt_text: str,
        on_flush: Callable[[str], Awaitable[None]],
        on_error: Callable[[str], Awaitable[None]],
    ) -> None:
        resume = self.store.get(_NS_CHAT, session_key)
        context_dir = cursorclaw_workspace()
        full_prompt = build_prompt(
            prompt_text, context_dir, workspace=self.settings.workspace
        )

        final_session: list[str] = [resume] if resume else [None]  # type: ignore[list-item]

        async def _inner() -> None:
            async for kind, payload in run_agent_turn(
                prompt=full_prompt,
                workspace=self.settings.workspace,
                agent_command=self.settings.agent_command,
                resume_session_id=resume,
                chunk_timeout_sec=self.settings.chunk_timeout_sec,
                turn_timeout_sec=self.settings.turn_timeout_sec,
            ):
                if kind == "flush" and isinstance(payload, str):
                    await on_flush(payload)
                elif kind == "done" and isinstance(payload, str) and payload.strip():
                    final_session[0] = payload.strip()

        timed_out = False
        task = asyncio.create_task(_inner())
        try:
            await asyncio.wait_for(task, timeout=self.settings.outer_timeout_sec)
        except TimeoutError:
            timed_out = True
            logger.warning(
                "{}: outer timeout {}s key={}",
                self.name,
                self.settings.outer_timeout_sec,
                session_key,
            )
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            await on_error("Turn timed out (outer limit).")
        except asyncio.CancelledError:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            raise

        if not timed_out and final_session[0]:
            self.store.set(_NS_CHAT, session_key, final_session[0])
