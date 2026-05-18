"""Pack-aggregated provider and model catalog loader.

defaultspack owns the loader only. Concrete provider/model entries live in
installed packs such as rumi_model_catalog_pack under extensions/llm/providers.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List

from ecosystem.defaultspack.domain.ai_client.providers import (
    build_profile_catalog,
    get_all_known_models,
    get_provider_catalog,
    validate_provider_catalog_coverage,
)
from ecosystem.defaultspack.domain.ai_client.api_key_store import provider_named_api_keys
from ecosystem.defaultspack.domain.ai_client.model_capabilities import (
    flatten_capability_fields,
)
from ecosystem.defaultspack.domain.ai_client.model_capability_schema import (
    knowledge_band_for_level,
)


def list_provider_catalog() -> List[Dict[str, Any]]:
    return [_with_legacy_provider_fields(provider) for provider in get_provider_catalog()]


def list_model_catalog(provider: str = "") -> List[Dict[str, Any]]:
    models = get_all_known_models()
    if provider:
        models = [model for model in models if model.get("provider_id") == provider or model.get("provider") == provider]
    return [_with_legacy_model_fields(model) for model in models]


def list_profile_catalog() -> List[Dict[str, Any]]:
    return [_with_legacy_profile_fields(profile) for profile in build_profile_catalog()]


def validate_catalog_coverage() -> List[Dict[str, Any]]:
    return validate_provider_catalog_coverage()


def _with_legacy_provider_fields(provider: Dict[str, Any]) -> Dict[str, Any]:
    item = dict(provider)
    availability = dict(item.get("availability", {}))
    configuration_source = availability.get("configuration_source")
    env_source = next((env_name for env_name in item.get("env_vars", []) if os.environ.get(str(env_name))), None)
    if env_source:
        configuration_source = env_source
    configured_envs = [configuration_source] if configuration_source else []
    capabilities = set(item.get("capabilities", []))
    kind = str(item.get("kind") or "")
    metadata = dict(item.get("metadata", {}))
    default_model_for = item.get("default_model_for")
    if isinstance(default_model_for, dict):
        item["default_model_for"] = {str(key): str(value) for key, value in default_model_for.items()}
        metadata["default_model_for"] = dict(item["default_model_for"])
    item.setdefault("category", kind)
    item["configured"] = bool(availability.get("configured"))
    item["configured_envs"] = configured_envs
    item["local"] = kind == "local" or "local" in capabilities
    item["openai_compatible"] = "openai_compatible" in capabilities or bool(metadata.get("openai_compatible"))
    item["catalog_only"] = bool(metadata.get("catalog_only", availability.get("catalog_only", False)))
    item["supports_invoke"] = bool(metadata.get("supports_invoke", availability.get("supports_invoke", False)))
    named_apis = provider_named_api_keys(str(item.get("provider_id") or item.get("id") or ""))
    item["configured_api_count"] = len([api for api in named_apis if api.get("configured")])
    item["named_apis"] = named_apis
    return item


def _canonical_model_id(model: Dict[str, Any]) -> str:
    return str(model.get("canonical_model_id") or model.get("model_id") or model.get("model_name") or model.get("id") or "")


def _model_context(model: Dict[str, Any]) -> int:
    qualified = str(model.get("qualified_model_id") or model.get("id") or "")
    if qualified == "stub/default":
        return -1
    raw = model.get("max_context", model.get("max_context_tokens", model.get("context_window", -1)))
    try:
        return int(raw)
    except (TypeError, ValueError):
        return -1


def _supports_thinking(model: Dict[str, Any]) -> bool:
    model_type = str(model.get("type") or "chat").lower()
    model_id = str(model.get("model_id") or model.get("id") or "").lower()
    if model_type not in {"chat", "reasoning"}:
        return False
    if model.get("supports_thinking") is not None:
        return bool(model.get("supports_thinking"))
    if bool(model.get("supports_thinking")):
        return True
    return any(token in model_id for token in ("gpt-5", "claude", "gemini", "deepseek"))


def _capability_enrichment(model: Dict[str, Any]) -> Dict[str, Any]:
    try:
        return flatten_capability_fields(model)
    except Exception:
        supports_thinking = _supports_thinking(model)
        return {
            "supports_vision": False,
            "supports_image_input": False,
            "supports_tool_calling": False,
            "supports_fast": False,
            "supports_thinking": supports_thinking,
            "thinking_levels": ["low", "medium", "high", "xhigh"] if supports_thinking else [],
            "default_thinking_level": "medium" if supports_thinking else None,
            "speed_tier": "balanced",
            "quality_tier": "unknown",
            "knowledge_level": 0,
            "knowledge_band": knowledge_band_for_level(0),
            "cost_tier": "unknown",
            "latency_tier": "medium",
            "capability_tags": ["thinking"] if supports_thinking else [],
            "allowed_roles": ["primary_chat"],
            "recommended_roles": ["primary_chat"],
            "model_capabilities": {},
        }


def _supports_vision(model: Dict[str, Any]) -> bool:
    return bool(_capability_enrichment(model).get("supports_vision"))


def _supports_tool_calling(model: Dict[str, Any]) -> bool:
    return bool(_capability_enrichment(model).get("supports_tool_calling"))


def _supports_fast_mode(model: Dict[str, Any]) -> bool:
    return bool(_capability_enrichment(model).get("supports_fast"))


def _knowledge_level(model: Dict[str, Any]) -> int:
    try:
        return int(_capability_enrichment(model).get("knowledge_level") or 0)
    except (TypeError, ValueError):
        return 0


def _speed_tier(model: Dict[str, Any]) -> str:
    return str(_capability_enrichment(model).get("speed_tier") or "balanced")


def _capability_tags(model: Dict[str, Any]) -> list[str]:
    tags = _capability_enrichment(model).get("capability_tags")
    return [str(tag) for tag in tags] if isinstance(tags, list) else []


def _with_legacy_model_fields(model: Dict[str, Any]) -> Dict[str, Any]:
    item = dict(model)
    canonical = _canonical_model_id(item)
    max_context = _model_context(item)
    capability_fields = _capability_enrichment(item)
    supports_thinking = bool(capability_fields.get("supports_thinking", _supports_thinking(item)))
    defaults = dict(item.get("defaults", {})) if isinstance(item.get("defaults"), dict) else {}
    pricing = dict(item.get("pricing", {})) if isinstance(item.get("pricing"), dict) else {}
    thinking_levels = capability_fields.get("thinking_levels", item.get("thinking_levels"))
    if not isinstance(thinking_levels, list):
        thinking_levels = ["low", "medium", "high", "xhigh"] if supports_thinking else []
    item["canonical_model_id"] = canonical
    item["same_model_across_providers_key"] = str(item.get("same_model_across_providers_key") or canonical)
    item["max_context"] = max_context
    item["max_context_tokens"] = max_context
    item["supports_thinking"] = supports_thinking
    item["thinking_levels"] = thinking_levels
    item["default_thinking_level"] = capability_fields.get(
        "default_thinking_level",
        item.get("default_thinking_level", "medium" if supports_thinking else None),
    )
    item["supports_vision"] = bool(capability_fields.get("supports_vision"))
    item["supports_image_input"] = bool(capability_fields.get("supports_image_input"))
    item["supports_tool_calling"] = bool(capability_fields.get("supports_tool_calling"))
    item["supports_fast"] = bool(capability_fields.get("supports_fast"))
    item["speed_tier"] = str(capability_fields.get("speed_tier") or "balanced")
    item["quality_tier"] = str(capability_fields.get("quality_tier") or "unknown")
    item["knowledge_level"] = int(capability_fields.get("knowledge_level") or 0)
    item["knowledge_band"] = str(capability_fields.get("knowledge_band") or knowledge_band_for_level(item["knowledge_level"]))
    item["cost_tier"] = str(capability_fields.get("cost_tier") or "unknown")
    item["latency_tier"] = str(capability_fields.get("latency_tier") or "medium")
    item["capability_tags"] = list(capability_fields.get("capability_tags") or [])
    item["allowed_roles"] = list(capability_fields.get("allowed_roles") or [])
    item["recommended_roles"] = list(capability_fields.get("recommended_roles") or [])
    item["model_capabilities"] = dict(capability_fields.get("model_capabilities") or {})
    item["defaults"] = defaults
    item["pricing"] = pricing
    metadata = dict(item.get("metadata", {}))
    metadata.update(
        {
            "max_context": max_context,
            "supports_thinking": supports_thinking,
            "thinking_levels": thinking_levels,
            "supports_vision": item["supports_vision"],
            "supports_image_input": item["supports_image_input"],
            "supports_tool_calling": item["supports_tool_calling"],
            "supports_fast": item["supports_fast"],
            "speed_tier": item["speed_tier"],
            "quality_tier": item["quality_tier"],
            "knowledge_level": item["knowledge_level"],
            "knowledge_band": item["knowledge_band"],
            "cost_tier": item["cost_tier"],
            "latency_tier": item["latency_tier"],
            "capability_tags": item["capability_tags"],
            "allowed_roles": item["allowed_roles"],
            "recommended_roles": item["recommended_roles"],
            "model_capabilities": item["model_capabilities"],
            "defaults": defaults,
            "pricing": pricing,
        }
    )
    item["metadata"] = metadata
    return item


def _with_legacy_profile_fields(profile: Dict[str, Any]) -> Dict[str, Any]:
    item = dict(profile)
    model_like = {
        "id": item.get("qualified_model_id") or item.get("profile_id"),
        "model_id": item.get("model_id"),
        "type": item.get("type", "chat"),
        "context_window": item.get("context_window", item.get("max_context", 0)),
        "supports_thinking": item.get("supports_thinking"),
        "thinking_levels": item.get("thinking_levels"),
        "default_thinking_level": item.get("default_thinking_level"),
        "metadata": item.get("metadata", {}),
        "defaults": item.get("defaults", {}),
        "pricing": item.get("pricing", {}),
        "capabilities": item.get("capabilities", []),
        "supports_vision": item.get("supports_vision"),
        "supports_image_input": item.get("supports_image_input"),
        "supports_tool_calling": item.get("supports_tool_calling"),
        "supports_fast": item.get("supports_fast"),
        "speed_tier": item.get("speed_tier"),
        "quality_tier": item.get("quality_tier"),
        "knowledge_level": item.get("knowledge_level"),
        "knowledge_band": item.get("knowledge_band"),
        "cost_tier": item.get("cost_tier"),
        "model_roles": item.get("model_roles"),
    }
    enriched = _with_legacy_model_fields(model_like)
    item["max_context"] = enriched["max_context"]
    item["max_context_tokens"] = enriched["max_context_tokens"]
    item["supports_thinking"] = enriched["supports_thinking"]
    item["thinking_levels"] = enriched["thinking_levels"]
    item["default_thinking_level"] = enriched["default_thinking_level"]
    item["supports_vision"] = enriched["supports_vision"]
    item["supports_image_input"] = enriched["supports_image_input"]
    item["supports_tool_calling"] = enriched["supports_tool_calling"]
    item["supports_fast"] = enriched["supports_fast"]
    item["speed_tier"] = enriched["speed_tier"]
    item["quality_tier"] = enriched["quality_tier"]
    item["knowledge_level"] = enriched["knowledge_level"]
    item["knowledge_band"] = enriched["knowledge_band"]
    item["cost_tier"] = enriched["cost_tier"]
    item["latency_tier"] = enriched["latency_tier"]
    item["capability_tags"] = enriched["capability_tags"]
    item["allowed_roles"] = enriched["allowed_roles"]
    item["recommended_roles"] = enriched["recommended_roles"]
    item["model_capabilities"] = enriched["model_capabilities"]
    item["defaults"] = enriched.get("defaults", {})
    item["pricing"] = enriched.get("pricing", {})
    item["same_model_across_providers_key"] = str(
        item.get("same_model_across_providers_key")
        or item.get("canonical_model_id")
        or item.get("model_id")
        or item.get("model_name")
        or ""
    )
    metadata = dict(item.get("metadata", {}))
    metadata.update(enriched["metadata"])
    item["metadata"] = metadata
    return item
