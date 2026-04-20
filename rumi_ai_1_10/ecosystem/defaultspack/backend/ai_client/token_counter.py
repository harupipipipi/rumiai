"""Token counting helpers for the AI client slice."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .provider_registry import ProviderRegistry, get_provider_registry


class TokenCounter:
    def __init__(self, registry: Optional[ProviderRegistry] = None) -> None:
        self.registry = registry or get_provider_registry()

    def count(self, value: Any, provider_id: str = "", model_id: str = "") -> int:
        return self.registry.token_count(value, provider_id=provider_id, model_name=model_id)

    def count_tokens(
        self,
        value: Any,
        model_ref: str = "",
        provider_id: str = "",
        model_name: str = "",
    ) -> int:
        return self.registry.token_count(
            value,
            model_ref=model_ref,
            provider_id=provider_id,
            model_name=model_name,
        )

    def token_count(
        self,
        value: Any,
        model_ref: str = "",
        provider_id: str = "",
        model_name: str = "",
    ) -> int:
        return self.count_tokens(value, model_ref=model_ref, provider_id=provider_id, model_name=model_name)
