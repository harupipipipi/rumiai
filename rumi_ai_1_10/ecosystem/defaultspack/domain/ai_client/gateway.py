from __future__ import annotations

from typing import Any, Dict, Iterable, Optional

from .client import AIClient
from .providers.stub_provider import StubProvider


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

    def supports_stream(self, model: str) -> bool:
        return bool(self._client.supports_stream(model))

    def resolve_provider(self, model: str) -> tuple[Any, Any]:
        return self._client.resolve_provider(model)

    def has_real_provider(self, model: str) -> bool:
        provider, _ = self.resolve_provider(model)
        return not isinstance(provider, StubProvider)

    def runtime_model_matches(self, model: str) -> list[dict[str, Any]]:
        return list(self._client._runtime_model_matches(str(model or "")))
