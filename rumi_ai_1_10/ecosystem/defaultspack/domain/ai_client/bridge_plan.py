from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from domain.chat.ir_blocks import BridgeAction, DroppedFeature, ProviderWarning


@dataclass
class PlannedProviderRequest:
    ir: Any
    model: str
    provider_capabilities: dict[str, Any]
    provider_tools: list[dict[str, Any]] = field(default_factory=list)
    params: dict[str, Any] = field(default_factory=dict)
    bridge_actions: list[BridgeAction] = field(default_factory=list)
    dropped_features: list[DroppedFeature] = field(default_factory=list)
    warnings: list[ProviderWarning] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "provider_capabilities": dict(self.provider_capabilities or {}),
            "provider_tools": list(self.provider_tools or []),
            "params": dict(self.params or {}),
            "bridge_actions": [item.to_dict() for item in self.bridge_actions],
            "dropped_features": [item.to_dict() for item in self.dropped_features],
            "warnings": [item.to_dict() for item in self.warnings],
            "metadata": dict(self.metadata or {}),
        }
