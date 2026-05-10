from __future__ import annotations

from typing import Any


class ResponseAdapter:
    provider = "generic"

    def send(self, plan: dict[str, Any], *, event=None, context: dict[str, Any] | None = None) -> dict[str, Any]:
        raise NotImplementedError
