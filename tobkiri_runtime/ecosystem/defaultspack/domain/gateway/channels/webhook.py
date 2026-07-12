from __future__ import annotations

from domain.gateway.routing import session_key


def route_webhook(webhook_id: str) -> str:
    return session_key(webhook_id=webhook_id)
