"""Pack-aggregated provider and model catalog loader.

defaultspack owns the loader only. Concrete provider/model entries live in
installed packs such as rumi_model_catalog_pack under extensions/llm/providers.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List

from ecosystem.defaultspack.domain.ai_client.providers import build_profile_catalog, get_all_known_models, get_provider_catalog


def list_provider_catalog() -> List[Dict[str, Any]]:
    return [_with_legacy_provider_fields(provider) for provider in get_provider_catalog()]


def list_model_catalog(provider: str = "") -> List[Dict[str, Any]]:
    models = get_all_known_models()
    if provider:
        models = [model for model in models if model.get("provider_id") == provider or model.get("provider") == provider]
    return [_with_legacy_model_fields(model) for model in models]


def list_profile_catalog() -> List[Dict[str, Any]]:
    return [_with_legacy_profile_fields(profile) for profile in build_profile_catalog()]


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
    item.setdefault("category", kind)
    item["configured"] = bool(availability.get("configured"))
    item["configured_envs"] = configured_envs
    item["local"] = kind == "local" or "local" in capabilities
    item["openai_compatible"] = "openai_compatible" in capabilities or bool(metadata.get("openai_compatible"))
    item["catalog_only"] = bool(metadata.get("catalog_only", availability.get("catalog_only", False)))
    item["supports_invoke"] = bool(metadata.get("supports_invoke", availability.get("supports_invoke", False)))
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
    if "supports_thinking" in model:
        return bool(model.get("supports_thinking"))
    model_type = str(model.get("type") or "chat").lower()
    model_id = str(model.get("model_id") or model.get("id") or "").lower()
    return model_type in {"chat", "reasoning"} and any(token in model_id for token in ("gpt-5", "claude", "gemini", "deepseek"))


def _with_legacy_model_fields(model: Dict[str, Any]) -> Dict[str, Any]:
    item = dict(model)
    canonical = _canonical_model_id(item)
    max_context = _model_context(item)
    supports_thinking = _supports_thinking(item)
    thinking_levels = item.get("thinking_levels")
    if not isinstance(thinking_levels, list):
        thinking_levels = ["low", "medium", "high", "xhigh"] if supports_thinking else []
    item["canonical_model_id"] = canonical
    item["same_model_across_providers_key"] = str(item.get("same_model_across_providers_key") or canonical)
    item["max_context"] = max_context
    item["max_context_tokens"] = max_context
    item["supports_thinking"] = supports_thinking
    item["thinking_levels"] = thinking_levels
    item["default_thinking_level"] = item.get("default_thinking_level", "medium" if supports_thinking else None)
    metadata = dict(item.get("metadata", {}))
    metadata.update(
        {
            "max_context": max_context,
            "supports_thinking": supports_thinking,
            "thinking_levels": thinking_levels,
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
        "metadata": item.get("metadata", {}),
    }
    enriched = _with_legacy_model_fields(model_like)
    item["max_context"] = enriched["max_context"]
    item["max_context_tokens"] = enriched["max_context_tokens"]
    item["supports_thinking"] = enriched["supports_thinking"]
    item["thinking_levels"] = enriched["thinking_levels"]
    item["default_thinking_level"] = enriched["default_thinking_level"]
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
