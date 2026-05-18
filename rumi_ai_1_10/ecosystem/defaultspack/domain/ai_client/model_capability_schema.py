from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


KNOWLEDGE_BANDS: tuple[tuple[int, str], ...] = (
    (96, "gpt_5_5_pro_tier"),
    (92, "frontier"),
    (85, "high_end_cloud"),
    (75, "strong_local_or_mid_cloud"),
    (65, "70b_class"),
    (55, "30b_class"),
    (40, "13b_class"),
    (30, "7b_class"),
    (20, "3b_class"),
    (10, "1b_class"),
    (0, "unknown"),
)

VALID_SPEED_TIERS = {"slow", "balanced", "fast"}
VALID_QUALITY_TIERS = {"unknown", "local", "mid", "high", "frontier"}
VALID_COST_TIERS = {"unknown", "free", "low", "medium", "high"}
VALID_MODEL_ROLES = {
    "primary_chat",
    "fast_reply",
    "deep_reasoning",
    "vision_ocr",
    "coding",
    "tool_selector",
    "prompt_compactor",
    "context_summarizer",
    "model_router",
    "subagent_default",
}


def knowledge_band_for_level(level: int) -> str:
    try:
        value = max(0, min(100, int(level)))
    except (TypeError, ValueError):
        value = 0
    for floor, band in KNOWLEDGE_BANDS:
        if value >= floor:
            return band
    return "unknown"


@dataclass(frozen=True)
class ModelCapabilityFlags:
    text: bool = True
    vision: bool = False
    image_input: bool = False
    audio_input: bool = False
    tool_calling: bool = False
    json_schema: bool = False
    structured_output: bool = False
    thinking: bool = False
    parallel_tool_calls: bool = False
    streaming: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ThinkingCapability:
    supported: bool = False
    levels: list[str] = field(default_factory=list)
    default_level: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RoutingCapability:
    speed_tier: str = "balanced"
    quality_tier: str = "unknown"
    knowledge_level: int = 0
    knowledge_band: str = "unknown"
    cost_tier: str = "unknown"
    latency_tier: str = "medium"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ModalityCapability:
    input: list[str] = field(default_factory=lambda: ["text"])
    output: list[str] = field(default_factory=lambda: ["text"])

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RoleCapability:
    allowed: list[str] = field(default_factory=lambda: ["primary_chat"])
    recommended: list[str] = field(default_factory=lambda: ["primary_chat"])

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ModelCapabilityRecord:
    qualified_model_id: str
    provider_id: str
    model_id: str
    capabilities: ModelCapabilityFlags
    thinking: ThinkingCapability
    routing: RoutingCapability
    modalities: ModalityCapability
    roles: RoleCapability
    capability_tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "qualified_model_id": self.qualified_model_id,
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "capabilities": self.capabilities.to_dict(),
            "thinking": self.thinking.to_dict(),
            "routing": self.routing.to_dict(),
            "modalities": self.modalities.to_dict(),
            "roles": self.roles.to_dict(),
            "capability_tags": list(self.capability_tags),
        }
