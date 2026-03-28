"""Run `agent` as a subprocess; yield text chunks to post at flush boundaries.

Stream format
-------------
The agent CLI emits newline-delimited JSON.  Each line is a JSON object whose
``type`` / ``event`` / ``kind`` field determines handling:

``assistant``
    LLM text delta.  ``extract_assistant_text`` pulls text from
    ``message.content[].text``, ``delta.text``, or top-level ``text``.
    Chunks are **accumulated** in ``buffer`` until a flush boundary.

``tool_call`` / ``result``
    **Flush separator**: post the accumulated ``buffer`` to Mattermost, then
    clear it.  This ensures each tool boundary sends a complete segment so
    Mattermost gets discrete readable posts rather than one enormous blob.

``thinking``
    Chain-of-thought text; also accumulated (same buffer as assistant).

``system``
    Metadata / control events; ignored.

``session_id``
    Present on many events; always captured so ``--resume`` works next turn.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import time
from pathlib import Path
from typing import Any, AsyncIterator

from loguru import logger

from cursor_claw.stream_parse import (
    event_type,
    extract_assistant_text,
    extract_session_id,
    parse_event_line,
)


def _extract_tool_name(obj: dict[str, Any]) -> str:
    """Extract tool name from a Cursor agent tool_call event.

    Cursor stream-json format:
      {"type": "tool_call", "tool_call": {"readToolCall": {...}}}
    The tool name is the first key inside the nested "tool_call" object
    (e.g. "readToolCall", "writeToolCall").  Some events use a flat
    "function": {"name": "..."} structure instead.
    """
    tc = obj.get("tool_call")
    if isinstance(tc, dict):
        # Cursor native: first key is the tool type
        for k, v in tc.items():
            if k != "name":
                return k
        # Fallback: explicit "name" key
        v = tc.get("name")
        if isinstance(v, str) and v:
            return v
    # Flat / function-style
    fn = obj.get("function")
    if isinstance(fn, dict):
        v = fn.get("name")
        if isinstance(v, str) and v:
            return v
    for key in ("name", "tool_name"):
        v = obj.get(key)
        if isinstance(v, str) and v:
            return v
    return "<unknown>"


async def run_agent_turn(
    *,
    prompt: str,
    workspace: Path,
    agent_command: str,
    resume_session_id: str | None,
    chunk_timeout_sec: float,
    turn_timeout_sec: float,
) -> AsyncIterator[tuple[str, str | None]]:
    """Yield ``("flush", text)`` for Mattermost posts and a final ``("done", session_id)``.

    ``session_id`` may be None if the stream never contained one.
    """
    workspace = workspace.resolve()
    if not workspace.is_dir():
        raise FileNotFoundError(f"workspace is not a directory: {workspace}")

    exe = agent_command
    if os.sep not in agent_command:
        found = shutil.which(agent_command)
        if found:
            exe = found
        else:
            logger.warning("agent command {!r} not found in PATH", agent_command)

    args = [
        exe,
        "--print",
        "--output-format", "stream-json",
        "--force",
        "--workspace",
        str(workspace),
    ]
    if resume_session_id:
        args.extend(["--resume", resume_session_id])

    logger.info(
        "agent start cmd={!r} workspace={} resume={}",
        exe,
        workspace,
        resume_session_id or "new",
    )

    env = os.environ.copy()
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(workspace),
        env=env,
    )
    assert proc.stdin and proc.stdout

    proc.stdin.write(prompt.encode("utf-8"))
    if not prompt.endswith("\n"):
        proc.stdin.write(b"\n")
    await proc.stdin.drain()
    proc.stdin.close()

    session_id: str | None = resume_session_id
    buffer: list[str] = []
    turn_started = time.monotonic()
    flush_count = 0
    total_chars = 0
    tool_call_count = 0

    async def flush_if_non_empty() -> AsyncIterator[tuple[str, str | None]]:
        nonlocal buffer, flush_count, total_chars
        text = "".join(buffer).strip()
        buffer = []
        if text:
            flush_count += 1
            total_chars += len(text)
            preview = (text[:120] + "…") if len(text) > 120 else text
            logger.info(
                "agent flush #{} chars={} preview={!r}",
                flush_count,
                len(text),
                preview,
            )
            yield ("flush", text)

    try:
        while True:
            elapsed = time.monotonic() - turn_started
            if elapsed >= turn_timeout_sec:
                logger.warning(
                    "agent turn timeout after {:.1f}s (limit {}s), killing",
                    elapsed,
                    turn_timeout_sec,
                )
                proc.kill()
                await asyncio.wait_for(proc.wait(), timeout=30.0)
                async for item in flush_if_non_empty():
                    yield item
                yield ("done", session_id)
                return

            try:
                line_b = await asyncio.wait_for(
                    proc.stdout.readline(),
                    timeout=chunk_timeout_sec,
                )
            except TimeoutError:
                logger.warning(
                    "agent chunk idle {:.0f}s with no output (limit {}s), killing subprocess",
                    chunk_timeout_sec,
                    chunk_timeout_sec,
                )
                proc.kill()
                await asyncio.wait_for(proc.wait(), timeout=30.0)
                async for item in flush_if_non_empty():
                    yield item
                yield ("done", session_id)
                return

            if not line_b:
                break

            line = line_b.decode("utf-8", errors="replace")
            obj = parse_event_line(line)
            if obj is None:
                logger.debug("agent stream non-JSON line: {!r}", line[:200])
                continue

            sid = extract_session_id(obj)
            if sid:
                if sid != session_id:
                    logger.info("agent session_id captured: {}", sid)
                session_id = sid

            et = event_type(obj)
            logger.debug("agent stream event type={!r} keys={}", et, list(obj.keys()))

            if et == "assistant":
                chunk = extract_assistant_text(obj)
                if chunk:
                    buffer.append(chunk)
            elif et == "tool_call":
                tool_call_count += 1
                tool_name = _extract_tool_name(obj)
                subtype = obj.get("subtype", "")
                logger.info(
                    "agent tool_call #{} tool={} subtype={} → flushing {} buffered chars",
                    tool_call_count,
                    tool_name,
                    subtype,
                    sum(len(c) for c in buffer),
                )
                async for item in flush_if_non_empty():
                    yield item
            elif et == "result":
                # Terminal event: flush any remaining buffer, then we're done.
                # The "result" field contains the full concatenated text (duplicate
                # of what was already sent via assistant events), so we don't post it.
                subtype = obj.get("subtype", "")
                is_error = obj.get("is_error", False)
                logger.info(
                    "agent result event subtype={} is_error={} → flushing {} buffered chars",
                    subtype,
                    is_error,
                    sum(len(c) for c in buffer),
                )
                async for item in flush_if_non_empty():
                    yield item
            elif et == "thinking":
                # Thinking / chain-of-thought: log at DEBUG but never send to Mattermost.
                logger.debug("agent thinking (suppressed from reply)")
            elif et in ("system", "user"):
                logger.debug("agent {} event: {}", et, str(obj)[:200])
            else:
                logger.debug("agent unknown event type={!r}", et)

        async for item in flush_if_non_empty():
            yield item

        stderr_data = b""
        if proc.stderr:
            stderr_data = await proc.stderr.read()
        rc = await proc.wait()

        elapsed = time.monotonic() - turn_started
        if stderr_data:
            stderr_text = stderr_data.decode("utf-8", errors="replace").strip()
            if rc != 0:
                logger.warning(
                    "agent stderr (rc={}): {}",
                    rc,
                    stderr_text[:2000],
                )
            else:
                logger.debug("agent stderr: {}", stderr_text[:2000])
        if rc != 0:
            logger.error(
                "agent exited rc={} elapsed={:.1f}s session={} flushes={} chars={}",
                rc,
                elapsed,
                session_id,
                flush_count,
                total_chars,
            )
        else:
            logger.info(
                "agent done rc={} elapsed={:.1f}s session={} flushes={} chars={} tool_calls={}",
                rc,
                elapsed,
                session_id,
                flush_count,
                total_chars,
                tool_call_count,
            )

        yield ("done", session_id)

    except asyncio.CancelledError:
        elapsed = time.monotonic() - turn_started
        logger.warning(
            "agent cancelled after {:.1f}s (flushes={} chars={})",
            elapsed,
            flush_count,
            total_chars,
        )
        proc.kill()
        try:
            await asyncio.wait_for(proc.wait(), timeout=30.0)
        except Exception:
            pass
        raise
    finally:
        if proc.returncode is None:
            proc.kill()
            try:
                await asyncio.wait_for(proc.wait(), timeout=30.0)
            except Exception:
                pass
