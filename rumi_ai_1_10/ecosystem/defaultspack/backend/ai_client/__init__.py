"""AI client compatibility layer for the defaultspack backend slice."""

from __future__ import annotations

from typing import Any, Dict, Iterator, Optional

from .ai_profile import AIProfile, AIProfileManager, ModelProfile, ModelProfileManager
from .base_provider import (
    BaseProvider,
    CompletionRequest,
    CompletionResponse,
    ProviderAdapter,
    ProviderConfig,
    RetryPolicy,
    StreamChunk,
)
from .provider_registry import ProviderRegistry, get_provider_registry, invoke, model_uuid, token_count
from .router import ModelRouter, RoutingRule, TaskRouter
from .token_counter import TokenCounter


class AIClient:
    def __init__(self, registry: Optional[ProviderRegistry] = None) -> None:
        self.registry = registry or get_provider_registry()
        self.router = ModelRouter(self.registry)

    def register_provider(self, provider: Any) -> Any:
        return self.registry.register_provider(provider)

    def register_profile(self, profile: ModelProfile | Dict[str, Any]) -> ModelProfile:
        return self.registry.register_profile(profile)

    def invoke(self, *args: Any, **kwargs: Any) -> Any:
        return self.registry.invoke(*args, **kwargs)

    def complete(self, *args: Any, **kwargs: Any) -> Any:
        return self.invoke(*args, **kwargs)

    def stream(self, *args: Any, **kwargs: Any) -> Iterator[Any]:
        return self.registry.stream(*args, **kwargs)

    def token_count(self, *args: Any, **kwargs: Any) -> int:
        return self.registry.token_count(*args, **kwargs)

    def route_task(self, task: Dict[str, Any]) -> Any:
        return self.registry.route_task(task)


__all__ = [
    "AIClient",
    "AIProfile",
    "AIProfileManager",
    "BaseProvider",
    "CompletionRequest",
    "CompletionResponse",
    "ModelProfile",
    "ModelProfileManager",
    "ModelRouter",
    "ProviderAdapter",
    "ProviderConfig",
    "ProviderRegistry",
    "RetryPolicy",
    "RoutingRule",
    "TaskRouter",
    "StreamChunk",
    "TokenCounter",
    "get_provider_registry",
    "invoke",
    "model_uuid",
    "token_count",
]
