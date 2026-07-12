"""Routing helpers for provider/model selection."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .provider_registry import ProviderRegistry, get_provider_registry


@dataclass
class RoutingRule:
    task_type: str = ""
    preferred_provider: str = ""
    preferred_model: str = ""
    fallback_provider: str = ""
    fallback_model: str = ""
    conditions: Dict[str, Any] = field(default_factory=dict)

    def matches(self, context: Optional[Dict[str, Any]] = None) -> bool:
        context = context or {}
        if self.task_type and context.get("task_type") != self.task_type:
            return False
        for key, expected in self.conditions.items():
            if context.get(key) != expected:
                return False
        return True


class ModelRouter:
    def __init__(self, registry: Optional[ProviderRegistry] = None) -> None:
        self.registry = registry or get_provider_registry()
        self._rules: List[RoutingRule] = []
        self._default_provider: str = ""
        self._default_model: str = ""

    def add_rule(self, rule: RoutingRule) -> None:
        self._rules.append(rule)

    def set_default(self, provider: str, model: str) -> None:
        self._default_provider = provider
        self._default_model = model

    def list_rules(self) -> List[RoutingRule]:
        return list(self._rules)

    def route(
        self,
        task_type: str = "",
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, str]:
        context = dict(context or {})
        if task_type:
            context.setdefault("task_type", task_type)
        for rule in self._rules:
            if rule.matches(context):
                return {
                    "provider": rule.preferred_provider,
                    "model": rule.preferred_model,
                    "fallback_provider": rule.fallback_provider,
                    "fallback_model": rule.fallback_model,
                }
        models = self.registry.list_models()
        if models:
            profile = models[0]
            return {
                "provider": profile.provider_id,
                "model": profile.model_name,
                "fallback_provider": self._default_provider,
                "fallback_model": self._default_model,
            }
        return {
            "provider": self._default_provider,
            "model": self._default_model,
            "fallback_provider": "",
            "fallback_model": "",
        }


TaskRouter = ModelRouter
