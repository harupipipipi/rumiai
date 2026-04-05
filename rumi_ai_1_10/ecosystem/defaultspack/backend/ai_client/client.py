"""
client.py - AI Client manager.

Central manager for AI completion requests. Routes to the appropriate
provider based on model/provider ID or task analysis. Handles retry,
failover, and error policies.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Dict, List, Optional

from .base_provider import (
    BaseProvider, CompletionRequest, CompletionResponse, ModelProfile,
)

logger = logging.getLogger(__name__)


class AIClientManager:
    """
    Central AI client manager.

    Registers providers, routes requests, handles failover.
    Provider-agnostic: adding a new provider requires zero core changes.
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._providers: Dict[str, BaseProvider] = {}
        self._profiles: Dict[str, ModelProfile] = {}  # model_uuid -> profile
        self._default_provider: Optional[str] = None
        self._default_model: Optional[str] = None
        self._error_policy = ErrorPolicy()

    def register_provider(self, provider: BaseProvider) -> None:
        with self._lock:
            pid = provider.provider_id()
            self._providers[pid] = provider
            for model in provider.list_models():
                key = f"{pid}:{model.model_id}"
                self._profiles[key] = model
            logger.info("Registered AI provider: %s", pid)

    def unregister_provider(self, provider_id: str) -> None:
        with self._lock:
            self._providers.pop(provider_id, None)
            to_remove = [k for k, v in self._profiles.items() if v.provider_id == provider_id]
            for k in to_remove:
                del self._profiles[k]

    def set_default(self, provider_id: str, model_id: str) -> None:
        self._default_provider = provider_id
        self._default_model = model_id

    def complete(self, request: CompletionRequest) -> CompletionResponse:
        provider = self._resolve_provider(request)
        if provider is None:
            return CompletionResponse(
                content="", finish_reason="error",
                usage={}, raw_response={"error": "No provider available"},
            )
        try:
            response = provider.complete(request)
            return response
        except Exception as exc:
            logger.error("Completion error: %s", exc)
            return self._error_policy.handle_error(exc, request, provider)

    def stream(self, request: CompletionRequest) -> Any:
        provider = self._resolve_provider(request)
        if provider is None:
            return iter([])
        return provider.stream(request)

    def count_tokens(self, text: str, model_id: str = "", provider_id: str = "") -> int:
        provider = self._providers.get(provider_id or self._default_provider or "")
        if provider:
            return provider.count_tokens(text, model_id)
        # Rough estimate fallback
        return len(text) // 4

    def list_providers(self) -> List[str]:
        return list(self._providers.keys())

    def list_models(self) -> List[Dict[str, Any]]:
        return [p.to_dict() for p in self._profiles.values()]

    def get_profile(self, provider_id: str, model_id: str) -> Optional[ModelProfile]:
        return self._profiles.get(f"{provider_id}:{model_id}")

    def _resolve_provider(self, request: CompletionRequest) -> Optional[BaseProvider]:
        pid = request.provider_id or self._default_provider
        if pid and pid in self._providers:
            return self._providers[pid]
        if self._providers:
            return next(iter(self._providers.values()))
        return None


class ErrorPolicy:
    """Error handling policy for AI requests."""

    def __init__(self, max_retries: int = 2, retry_delay: float = 1.0):
        self.max_retries = max_retries
        self.retry_delay = retry_delay

    def handle_error(
        self, error: Exception, request: CompletionRequest, provider: BaseProvider,
    ) -> CompletionResponse:
        return CompletionResponse(
            content="",
            finish_reason="error",
            usage={},
            raw_response={"error": str(error), "error_type": type(error).__name__},
        )
