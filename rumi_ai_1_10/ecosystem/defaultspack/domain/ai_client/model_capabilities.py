from __future__ import annotations

from typing import Any

from domain.ai_client.model_capability_inference import infer_model_capabilities
from domain.ai_client.model_capability_schema import knowledge_band_for_level


def capability_record_for_model(model: dict[str, Any]) -> dict[str, Any]:
    return infer_model_capabilities(model).to_dict()


def flatten_capability_fields(model: dict[str, Any]) -> dict[str, Any]:
    record = capability_record_for_model(model)
    capabilities = record["capabilities"]
    thinking = record["thinking"]
    routing = record["routing"]
    roles = record["roles"]
    return {
        "supports_vision": bool(capabilities.get("vision")),
        "supports_image_input": bool(capabilities.get("image_input")),
        "supports_audio": bool(capabilities.get("audio_input")),
        "supports_audio_input": bool(capabilities.get("audio_input")),
        "supports_tool_calling": bool(capabilities.get("tool_calling")),
        "supports_fast": routing.get("speed_tier") == "fast",
        "supports_thinking": bool(capabilities.get("thinking")),
        "thinking_levels": list(thinking.get("levels") or []),
        "default_thinking_level": thinking.get("default_level"),
        "speed_tier": routing.get("speed_tier", "balanced"),
        "quality_tier": routing.get("quality_tier", "unknown"),
        "knowledge_level": int(routing.get("knowledge_level") or 0),
        "knowledge_band": routing.get("knowledge_band") or knowledge_band_for_level(0),
        "cost_tier": routing.get("cost_tier", "unknown"),
        "latency_tier": routing.get("latency_tier", "medium"),
        "capability_tags": list(record.get("capability_tags") or []),
        "allowed_roles": list(roles.get("allowed") or []),
        "recommended_roles": list(roles.get("recommended") or []),
        "model_capabilities": record,
    }
