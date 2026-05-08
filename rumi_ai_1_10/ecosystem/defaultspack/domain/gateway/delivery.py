from __future__ import annotations

from core_runtime.runtime_audit_helpers import redact_sensitive


class GatewayDelivery:
    def __init__(self) -> None:
        self.messages: list[dict] = []

    def publish(self, event: str, payload: dict) -> dict:
        message = {"event": event, "payload": redact_sensitive(payload)}
        self.messages.append(message)
        return message
