from __future__ import annotations

from typing import Any


def session_key_for(context: dict[str, Any] | None, *, agent_id: str | None = None) -> str:
    context = context if isinstance(context, dict) else {}
    if isinstance(context.get("session_key"), str) and context["session_key"]:
        return context["session_key"]
    agent = agent_id or context.get("agent_id") or "main"
    conversation_id = context.get("conversation_id")
    if conversation_id:
        return f"agent:{agent}:chat:{conversation_id}"
    channel = context.get("channel")
    channel_id = context.get("channel_id")
    if channel and channel_id:
        return f"agent:{agent}:{channel}:{channel_id}"
    return f"agent:{agent}:main"
