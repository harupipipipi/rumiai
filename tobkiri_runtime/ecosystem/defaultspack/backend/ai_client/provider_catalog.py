"""Finite legacy projection over selected AI catalog and registry owners.

defaultspack owns no catalog or connection state. The active resolved profile
selects the global owners; this module only preserves legacy response fields.
"""

from __future__ import annotations

from typing import Any, Dict, List

from core_runtime.di_container import get_container
from core_runtime.global_contract_dispatch import (
    GlobalContractInvocationError,
    GlobalContractUnavailable,
    invoke_global_contract,
)
from ecosystem.defaultspack.domain.ai_client.model_capabilities import (
    flatten_capability_fields,
)
from ecosystem.defaultspack.domain.ai_client.model_capability_schema import (
    knowledge_band_for_level,
)
from ecosystem.defaultspack.domain.ai_client.model_metadata_schema import context_window_value

_MODEL_CATALOG_CONTRACT = "rumi.resource.ai.model.catalog.v1"
_MODEL_PROFILE_CONTRACT = "rumi.resource.ai.model.profile.v1"
_PROVIDER_REGISTRY_CONTRACT = "rumi.resource.ai.provider.registry.v1"


def _invoke(contract_id: str, operation: str, payload: Dict[str, Any]) -> Any:
    registry = get_container().get_or_none("interface_registry")
    if registry is None:
        raise GlobalContractUnavailable("interface registry is unavailable")
    return invoke_global_contract(registry, contract_id, operation, payload)


def list_provider_catalog() -> List[Dict[str, Any]]:
    try:
        catalog = _invoke(_MODEL_CATALOG_CONTRACT, "list", {})
        connections = _invoke(_PROVIDER_REGISTRY_CONTRACT, "list", {})
    except (GlobalContractInvocationError, GlobalContractUnavailable):
        return []
    providers = catalog.get("providers") if isinstance(catalog, dict) else None
    providers = providers if isinstance(providers, list) else []
    connection_items = (
        connections.get("providers") if isinstance(connections, dict) else None
    )
    connection_items = connection_items if isinstance(connection_items, list) else []
    configured = {
        str(item.get("provider_instance_id") or "")
        for item in connection_items
        if isinstance(item, dict) and item.get("enabled", True)
    }
    return [
        _with_legacy_provider_fields(
            provider,
            configured=f"provider.{provider.get('provider_id')}" in configured,
        )
        for provider in providers
        if isinstance(provider, dict)
    ]


def list_model_catalog(provider: str = "") -> List[Dict[str, Any]]:
    try:
        result = _invoke(
            _MODEL_CATALOG_CONTRACT,
            "list",
            {"provider_id": provider} if provider else {},
        )
    except (GlobalContractInvocationError, GlobalContractUnavailable):
        return []
    models = result.get("models") if isinstance(result, dict) else None
    models = models if isinstance(models, list) else []
    return [_with_legacy_model_fields(model) for model in models]


def list_profile_catalog() -> List[Dict[str, Any]]:
    try:
        result = _invoke(_MODEL_PROFILE_CONTRACT, "list", {})
    except (GlobalContractInvocationError, GlobalContractUnavailable):
        return []
    profiles = result.get("profiles") if isinstance(result, dict) else None
    profiles = profiles if isinstance(profiles, list) else []
    return [
        _with_legacy_profile_fields(profile)
        for profile in profiles
        if isinstance(profile, dict)
    ]


def validate_catalog_coverage() -> List[Dict[str, Any]]:
    providers = {item.get("provider_id") for item in list_provider_catalog()}
    return [
        {
            "code": "catalog_provider_missing",
            "model_id": item.get("model_id"),
            "provider_id": item.get("provider_id"),
        }
        for item in list_model_catalog()
        if item.get("provider_id") not in providers
    ]


def _with_legacy_provider_fields(
    provider: Dict[str, Any],
    *,
    configured: bool,
) -> Dict[str, Any]:
    item = dict(provider)
    availability = dict(item.get("availability", {}))
    configured_envs: List[str] = []
    capabilities = set(item.get("capabilities", []))
    kind = str(item.get("kind") or "")
    metadata = dict(item.get("metadata", {}))
    default_model_for = item.get("default_model_for")
    if isinstance(default_model_for, dict):
        item["default_model_for"] = {str(key): str(value) for key, value in default_model_for.items()}
        metadata["default_model_for"] = dict(item["default_model_for"])
    item.setdefault("category", kind)
    item["configured"] = configured
    item["configured_envs"] = configured_envs
    item["local"] = kind == "local" or "local" in capabilities
    item["openai_compatible"] = "openai_compatible" in capabilities or bool(metadata.get("openai_compatible"))
    item["catalog_only"] = bool(metadata.get("catalog_only", availability.get("catalog_only", False)))
    item["supports_invoke"] = bool(metadata.get("supports_invoke", availability.get("supports_invoke", False)))
    item["configured_api_count"] = 1 if configured else 0
    item["named_apis"] = []
    return item


def _canonical_model_id(model: Dict[str, Any]) -> str:
    return str(model.get("canonical_model_id") or model.get("model_id") or model.get("model_name") or model.get("id") or "")


def _model_context(model: Dict[str, Any]) -> int:
    qualified = str(model.get("qualified_model_id") or model.get("id") or "")
    if qualified == "stub/default":
        return -1
    try:
        return context_window_value(model, default=-1)
    except Exception:
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
    declared = model.get("capabilities")
    if isinstance(declared, list):
        values = {str(item) for item in declared}
        supports_thinking = "thinking" in values
        return {
            "supports_vision": "image_input" in values,
            "supports_image_input": "image_input" in values,
            "supports_audio": "audio_input" in values,
            "supports_audio_input": "audio_input" in values,
            "supports_tool_calling": "tool_calling" in values,
            "supports_fast": "fast" in values,
            "supports_thinking": supports_thinking,
            "thinking_levels": (
                ["low", "medium", "high", "xhigh"]
                if supports_thinking else []
            ),
            "default_thinking_level": (
                "medium" if supports_thinking else None
            ),
            "speed_tier": "balanced",
            "quality_tier": "unknown",
            "knowledge_level": 0,
            "knowledge_band": knowledge_band_for_level(0),
            "cost_tier": "unknown",
            "latency_tier": "medium",
            "capability_tags": sorted(values),
            "allowed_roles": ["primary_chat"],
            "recommended_roles": ["primary_chat"],
            "model_capabilities": {key: True for key in sorted(values)},
        }
    try:
        return flatten_capability_fields(model)
    except Exception:
        supports_thinking = _supports_thinking(model)
        return {
            "supports_vision": False,
            "supports_image_input": False,
            "supports_audio": False,
            "supports_audio_input": False,
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
    item["supports_audio"] = bool(capability_fields.get("supports_audio"))
    item["supports_audio_input"] = bool(capability_fields.get("supports_audio_input") or capability_fields.get("supports_audio"))
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
            "supports_audio": item["supports_audio"],
            "supports_audio_input": item["supports_audio_input"],
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
            "routing": dict(item.get("routing", {})) if isinstance(item.get("routing"), dict) else {},
            "request_features": dict(item.get("request_features", {})) if isinstance(item.get("request_features"), dict) else {},
            "thinking": dict(item.get("thinking", {})) if isinstance(item.get("thinking"), dict) else {},
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
        "routing": item.get("routing", {}),
        "request_features": item.get("request_features", {}),
        "thinking": item.get("thinking", {}),
        "pricing": item.get("pricing", {}),
        "capabilities": item.get("capabilities", []),
        "supports_vision": item.get("supports_vision"),
        "supports_image_input": item.get("supports_image_input"),
        "supports_audio": item.get("supports_audio"),
        "supports_audio_input": item.get("supports_audio_input"),
        "supports_tool_calling": item.get("supports_tool_calling"),
        "supports_fast": item.get("supports_fast"),
        "capability_tags": item.get("capability_tags"),
        "tags": item.get("tags"),
        "traits": item.get("traits"),
        "input_modalities": item.get("input_modalities"),
        "modalities": item.get("modalities"),
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
    item["supports_audio"] = enriched["supports_audio"]
    item["supports_audio_input"] = enriched["supports_audio_input"]
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
