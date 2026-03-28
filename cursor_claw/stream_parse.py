"""Line-delimited JSON from Cursor Agent CLI — tolerant parsing."""

from __future__ import annotations

import json
from typing import Any


def parse_event_line(line: str) -> dict[str, Any] | None:
    line = line.strip()
    if not line:
        return None
    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def event_type(obj: dict[str, Any]) -> str:
    for k in ("type", "event", "kind"):
        v = obj.get(k)
        if isinstance(v, str) and v:
            return v.lower()
    return ""


def extract_session_id(obj: dict[str, Any]) -> str | None:
    sid = obj.get("session_id")
    if isinstance(sid, str) and sid.strip():
        return sid.strip()
    data = obj.get("data")
    if isinstance(data, dict):
        sid = data.get("session_id")
        if isinstance(sid, str) and sid.strip():
            return sid.strip()
    return None


def extract_assistant_text(obj: dict[str, Any]) -> str:
    msg = obj.get("message")
    if isinstance(msg, dict):
        content = msg.get("content")
        if isinstance(content, list):
            parts: list[str] = []
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "text" and isinstance(block.get("text"), str):
                    parts.append(block["text"])
                elif isinstance(block.get("text"), str):
                    parts.append(block["text"])
            return "".join(parts)
        if isinstance(content, str):
            return content
    delta = obj.get("delta")
    if isinstance(delta, dict):
        t = delta.get("text")
        if isinstance(t, str):
            return t
    for k in ("text", "content", "output"):
        v = obj.get(k)
        if isinstance(v, str):
            return v
    return ""
