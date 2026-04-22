from __future__ import annotations

from typing import Any, Dict, Iterable, Optional

from .client import AIClient


class LLMGateway:
    """Thin gateway that keeps orchestration concerns out of provider adapters."""

    def __init__(self, client: Optional[AIClient] = None) -> None:
        self._client = client or AIClient()

    def complete(self, request: Dict[str, Any]) -> Dict[str, Any]:
        model = str(request.get("model", ""))
        messages = list(request.get("messages", []))
        tools = list(request.get("tools", []))
        params = dict(request.get("params", {}))
        return self._client.complete(model, messages, tools=tools, params=params)

    def stream(self, request: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
        model = str(request.get("model", ""))
        messages = list(request.get("messages", []))
        tools = list(request.get("tools", []))
        params = dict(request.get("params", {}))
        return self._client.stream(model, messages, tools=tools, params=params)
