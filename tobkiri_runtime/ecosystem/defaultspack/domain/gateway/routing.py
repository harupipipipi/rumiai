from __future__ import annotations


def session_key(
    *,
    agent_id: str = "main",
    conversation_id: str | None = None,
    channel: str | None = None,
    channel_id: str | None = None,
    user_id: str | None = None,
    job_id: str | None = None,
    webhook_id: str | None = None,
) -> str:
    if job_id:
        return f"cron:{job_id}"
    if webhook_id:
        return f"webhook:{webhook_id}"
    if conversation_id:
        return f"agent:{agent_id}:chat:{conversation_id}"
    if channel and user_id:
        return f"agent:{agent_id}:{channel}:user:{user_id}"
    if channel and channel_id:
        return f"agent:{agent_id}:{channel}:channel:{channel_id}"
    return f"agent:{agent_id}:main"
