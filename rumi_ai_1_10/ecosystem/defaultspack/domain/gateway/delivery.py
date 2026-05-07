from __future__ import annotations


class GatewayDelivery:
    def __init__(self) -> None:
        self.messages: list[dict] = []

    def publish(self, event: str, payload: dict) -> dict:
        message = {"event": event, "payload": payload}
        self.messages.append(message)
        return message
