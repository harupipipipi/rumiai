from __future__ import annotations

from domain.gateway.routing import session_key


class ChannelAdapter:
    channel = "channel"

    def route(self, payload: dict) -> str:
        return session_key(
            agent_id=payload.get("agent_id", "main"),
            channel=self.channel,
            channel_id=payload.get("channel_id"),
            user_id=payload.get("user_id"),
        )
