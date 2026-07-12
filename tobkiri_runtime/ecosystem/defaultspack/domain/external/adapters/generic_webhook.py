from __future__ import annotations

from typing import Any

from domain.external.response_adapter import ResponseAdapter


class GenericWebhookResponseAdapter(ResponseAdapter):
    provider = "generic"

    def send(self, plan: dict[str, Any], *, event=None, context: dict[str, Any] | None = None) -> dict[str, Any]:
        del event, context
        return {"sent": True, "mode": "json", "response": plan}
